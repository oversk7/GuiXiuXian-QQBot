from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from nonebot.params import CommandArg
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from enum import Enum as PyEnum
import random
import asyncio
from ..config import config
from ..data.db import safe_session
from ..models.player import Player
from ..models.item import Inventory, Item
from ..utils import create_rich_message, parse_uid
from sqlalchemy.orm import joinedload

# 战斗缓存结构
_active_battles: Dict[str, 'BattleInstance'] = {}  # 战斗ID到实例的映射
_player_battle_map: Dict[str, str] = {}  # 玩家ID到战斗ID的映射
_BATTLE_TIMEOUT = 120  # 2分钟无操作自动结束战斗

# 组队系统缓存
_team_invitations: Dict[str, Dict[str, datetime]] = {}  # {发起者ID: {受邀者ID: 过期时间}}
_active_teams: Dict[str, List[str]] = {}  # {队伍ID: [成员UID列表]}

class BattleType(PyEnum):
    SOLO = "单人PVE"
    TEAM = "组队PVE"
    PVP = "多人PVP"


class BattleActor:
    """战斗参与者基类"""
    __slots__ = ['id', 'name', 'is_player', 'hp', 'max_hp', 'mp', 'max_mp', 
                'attack', 'defense', 'agility', 'fear_resistance', 'luck']
    
    def __init__(self, entity: Any, is_player: bool = True):
        self.id = str(id(entity)) if not is_player else entity.id
        self.name = getattr(entity, 'nickname', '未知') if is_player else entity['name']
        self.is_player = is_player
        
        # 玩家属性（从Player对象获取）
        if is_player:
            self.hp = entity.hp
            self.max_hp = entity.max_hp
            self.mp = entity.mp
            self.max_mp = entity.max_mp
            self.attack = entity.attack
            self.defense = entity.defense
            self.agility = entity.agility
            self.fear_resistance = entity.fear_resistance
            self.luck = entity.luck
        # 敌人属性（从字典配置获取）
        else:
            self.max_hp = entity['max_hp']
            self.hp = entity.get('hp', self.max_hp)
            self.max_mp = entity.get('max_mp', 0)
            self.mp = entity.get('mp', 0)
            self.attack = entity['attack']
            self.defense = entity['defense']
            self.agility = entity['agility']
            self.fear_resistance = entity.get('fear_resistance', 0)
            self.luck = entity.get('luck', 0)

class BattleInstance:
    """战斗实例管理"""
    __slots__ = ['battle_id', 'battle_type', 'players', 'enemies', 
                'turn', 'last_active', 'actions', 'logs']
    
    def __init__(self, battle_type: BattleType, players: List[Player], enemies: List[Dict]):
        # 生成唯一战斗ID（包含所有参与者ID的哈希）
        participants = [p.id for p in players] + [e['id'] for e in enemies]
        self.battle_id = f"battle_{hash(frozenset(participants))}_{datetime.now().timestamp()}"
        
        # 注册玩家到战斗映射
        for p in players:
            _player_battle_map[p.id] = self.battle_id
        
        self.battle_type = battle_type
        self.players = [BattleActor(p) for p in players]
        self.enemies = [BattleActor(e, False) for e in enemies]
        self.turn = 0
        self.last_active = datetime.now()
        self.actions = {}
        self.logs = []

    @property
    def is_expired(self) -> bool:
        return (datetime.now() - self.last_active).seconds > _BATTLE_TIMEOUT

    async def process_turn(self):
        """处理战斗回合（新增多人协同）"""
        self.turn += 1
        self.last_active = datetime.now()
        
        # 等待所有存活玩家提交行动
        alive_players = [p.id for p in self.players if p.hp > 0]
        while len(self.actions) < len(alive_players):
            await asyncio.sleep(1)
        
        # 按敏捷排序行动顺序
        actors = sorted(
            [a for a in self.players + self.enemies if a.hp > 0],
            key=lambda x: x.agility,
            reverse=True
        )
        
        battle_log = []
        for actor in actors:
            if action := self.actions.get(actor.id):
                act_type, target_id = action
                
                # 执行攻击
                if act_type == 'attack':
                    target = next((e for e in (self.players + self.enemies) if e.id == target_id), None)
                    if not target:
                        continue
                    
                    # 计算伤害
                    damage = max(0, actor.attack - target.defense)
                    damage = int(damage * random.uniform(0.9, 1.1))
                    target.hp = max(0, target.hp - damage)
                    
                    log = f"{actor.name} ➔ {target.name} 造成{damage}点伤害！"
                    battle_log.append(log)
        
        # 清理行动记录
        self.actions.clear()
        
        # 生成回合报告
        report = (
            f"🌀 第{self.turn}回合结算：\n" +
            "\n".join(battle_log) + "\n\n" +
            "📊 当前状态：\n" +
            "\n".join([f"{p.name} HP: {p.hp}/{p.max_hp}" for p in self.players]) + "\n" +
            "\n".join([f"{e.name} HP: {e.hp}/{e.max_hp}" for e in self.enemies])
        )
        
        # 检查战斗结果
        if all(e.hp <= 0 for e in self.enemies):
            return "players_win", report
        if all(p.hp <= 0 for p in self.players):
            return "enemies_win", report
        return "continue", report

# 战斗命令
battle_start = on_command("战斗", aliases={"挑战"}, block=True, priority=5)
attack_cmd = on_command("攻击", block=True, priority=5)
use_item_cmd = on_command("使用", block=True, priority=5)
escape_cmd = on_command("逃跑", block=True, priority=5)

# 组队命令
team_cmd = on_command("组队", block=True, priority=5)
join_cmd = on_command("加入队伍", block=True, priority=5)

class TeamStatus(PyEnum):
    FORMING = "组队中"
    READY = "已就绪"

class BattleTeam:
    """组队管理器"""
    __slots__ = ['leader', 'members', 'status', 'created_at']
    
    def __init__(self, leader_id: str):
        self.leader = leader_id
        self.members = [leader_id]
        self.status = TeamStatus.FORMING
        self.created_at = datetime.now()

# 组队处理逻辑
@team_cmd.handle()
async def handle_team(event: MessageEvent, args: Message = CommandArg()):
    """组队命令示例：组队邀请 100"""
    args_text = args.extract_plain_text().strip()
    user_id = event.get_user_id()
    uid = args_text
    
    # 创建/更新邀请
    _team_invitations.setdefault(user_id, {})
    _team_invitations[user_id][uid] = datetime.now() + timedelta(minutes=5)

    await team_cmd.finish(f"📨 已向玩家{uid}发送组队邀请，有效期5分钟")

@join_cmd.handle()
async def handle_join(event: MessageEvent, args: Message = CommandArg()):
    """加入队伍 发起者UID"""
    inviter_uid = parse_uid(args.extract_plain_text().strip())
    user_id = event.get_user_id()
    
    if not inviter_uid or inviter_uid not in _team_invitations:
        await join_cmd.finish("⛔ 无效的邀请码或邀请已过期")
    
    # 检查是否被邀请
    if user_id not in _team_invitations[inviter_uid]:
        await join_cmd.finish("⛔ 你没有收到该玩家的组队邀请")
    
    # 加入队伍
    if inviter_uid not in _active_teams:
        _active_teams[inviter_uid] = [inviter_uid]
    _active_teams[inviter_uid].append(user_id)
    
    # 删除邀请
    del _team_invitations[inviter_uid][user_id]
    
    await join_cmd.finish(f"🎉 成功加入{inviter_uid}的队伍！当前成员：{'、'.join(_active_teams[inviter_uid])}")

# 修改战斗开始逻辑
@battle_start.handle()
async def start_team_battle(event: MessageEvent):
    user_id = event.get_user_id()
    
    # 检查是否队长
    if user_id not in _active_teams or _active_teams[user_id][0] != user_id:
        await battle_start.finish("⛔ 只有队长可以开始战斗")
    
    async with safe_session() as session:
        # 加载所有队员数据
        members = await session.query(Player).filter(
            Player.id.in_(_active_teams[user_id])
        ).options(joinedload(Player.inventory)).all()
        
        # 生成敌人（根据队伍人数动态调整）
        enemy_count = max(2, len(members))
        enemies = [{
            "name": f"变异村民#{i+1}",
            "max_hp": 80,
            "attack": 20,
            "defense": 8,
            "agility": 5
        } for i in range(enemy_count)]
        
        # 创建战斗实例
        battle = BattleInstance(BattleType.TEAM, members, enemies)
        _active_battles[battle.battle_id] = battle
        
        # 生成战斗界面
        enemy_status = "\n".join([f"{e.name} HP: {e.hp}/{e.max_hp}" for e in battle.enemies])
        member_status = "\n".join([f"{m.name} HP: {m.hp}/{m.max_hp}" for m in battle.players])
        
        msg = (
            f"⚔️ 团队战斗开始！\n"
            f"👥 队友：\n{member_status}\n"
            f"👹 敌人：\n{enemy_status}\n"
            f"请使用【攻击 目标】或【使用 道具】指令"
        )
        await battle_start.finish(create_rich_message(msg, event))

@attack_cmd.handle()
async def handle_attack(event: MessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()
    battle_id = _player_battle_map.get(user_id)
    
    if not battle_id or (battle := _active_battles.get(battle_id)) is None:
        await attack_cmd.finish("⛔ 你当前没有参与战斗")
    
    # 解析攻击目标
    target_name = args.extract_plain_text().strip()
    target = next((e for e in battle.enemies if e.name == target_name), None)
    
    if not target:
        await attack_cmd.finish(f"⛔ 目标不存在，可用目标：{'/'.join(e.name for e in battle.enemies)}")
    
    # 记录行动
    battle.actions[user_id] = ('attack', target.id)
    await attack_cmd.finish("✅ 攻击指令已记录，等待回合结算")

@use_item_cmd.handle()
async def handle_use_item(event: MessageEvent):
    # 调用现有背包系统
    async with safe_session() as session:
        inventory = await session.get(Inventory, event.get_user_id())

# 清理过期战斗
async def clean_expired_battles():
    while True:
        await asyncio.sleep(300)

        expired_battles = [b for b in _active_battles.values() if b.is_expired]
        for battle in expired_battles:
            # 清理玩家映射
            for p in battle.players:
                if p.id in _player_battle_map:
                    del _player_battle_map[p.id]
            # 清理战斗实例
            del _active_battles[battle.battle_id]

# 清理过期邀请的定时任务
async def clean_expired_invites():
    while True:
        await asyncio.sleep(60)
        now = datetime.now()
        for leader in list(_team_invitations.keys()):
            expired = [uid for uid, t in _team_invitations[leader].items() if t < now]
            for uid in expired:
                del _team_invitations[leader][uid]
            if not _team_invitations[leader]:
                del _team_invitations[leader]