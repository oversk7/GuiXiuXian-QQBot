from nonebot import on_command, get_bot
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
from ..utils import create_rich_message
from sqlalchemy.orm import joinedload
from sqlalchemy import select
from ..models.team import Team, TeamMember

# 战斗命令
battle_start = on_command("战斗", aliases={"挑战"}, block=True, priority=5)
attack_cmd = on_command("攻击", block=True, priority=5)
use_item_cmd = on_command("使用", block=True, priority=5)
escape_cmd = on_command("逃跑", block=True, priority=5)

# 战斗缓存结构
_player_battles: Dict[str, 'BattleInstance'] = {}  # 玩家ID映射到战斗实例
_BATTLE_TIMEOUT = 120

class BattleType(PyEnum):
    SOLO = "单人战斗"
    TEAM = "组队战斗"
    # PVP = "PVP战斗"


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
                'turn', 'last_active', 'actions', 'logs', 'latest_event']
    
    def __init__(self, battle_type: BattleType, players: List[Player], enemies: List[Dict], latest_event: MessageEvent):
        # 生成唯一战斗ID（包含所有参与者ID的哈希）
        participants = [p.id for p in players]
        self.battle_id = f"battle_{hash(frozenset(participants))}_{datetime.now().timestamp()}"
        
        # 注册玩家到战斗映射
        for p in players:
            _player_battles[p.id] = self  # 直接存储实例引用
        
        self.battle_type = battle_type
        self.players = [BattleActor(p) for p in players]
        self.enemies = [BattleActor(e, False) for e in enemies]
        self.turn = 0
        self.last_active = datetime.now()
        self.actions = {}
        self.logs = []
        self.latest_event = latest_event

    @property
    def is_expired(self) -> bool:
        return (datetime.now() - self.last_active).seconds > _BATTLE_TIMEOUT

    async def process_turn(self):
        """优化后的回合处理逻辑"""
        self.turn += 1
        self.last_active = datetime.now()
        
        # 等待存活玩家提交行动（最多等待30秒）
        try:
            await asyncio.wait_for(
                self._wait_for_actions(),
                timeout=30
            )
        except asyncio.TimeoutError:
            self.logs.append("🕒 回合超时，自动结算")
        
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
                    target = next((e for e in self.enemies if e.id == target_id), None)
                    if not target:
                        continue
                    
                    # 计算伤害（加入暴击和闪避判定）
                    is_crit = random.random() < (actor.luck / 1000)
                    is_dodge = random.random() < (target.agility / 1000)
                    
                    if is_dodge:
                        log = f"✨ {target.name} 灵巧地躲过了攻击！"
                    else:
                        damage = max(0, actor.attack - target.defense)
                        if is_crit:
                            damage = int(damage * 1.5)
                        damage = int(damage * random.uniform(0.9, 1.1))
                        target.hp = max(0, target.hp - damage)
                        
                        crit_mark = "💥 " if is_crit else ""
                        log = f"{crit_mark}{actor.name} ➔ {target.name} 造成{damage}点伤害！"
                    
                    battle_log.append(log)
        
        # 生成更清晰的回合报告
        report = create_rich_message(
            f"🌀 第{self.turn}回合结算：\n" +
            "\n".join(battle_log) + "\n\n" +
            "📊 当前状态：\n" +
            "👥 队友状态：\n" + 
            "\n".join([f"{p.name} ❤️ {p.hp}/{p.max_hp} | 💧 {p.mp}/{p.max_mp}" for p in self.players]) + 
            "\n👹 敌人状态：\n" +
            "\n".join([f"{e.name} ❤️ {e.hp}/{e.max_hp}" for e in self.enemies])
        )
        
        # 处理战斗结果
        if all(e.hp <= 0 for e in self.enemies):
            # 发放奖励
            return "players_win", report
        if all(p.hp <= 0 for p in self.players):
            return "enemies_win", report
        return "continue", report

    async def _wait_for_actions(self):
        """等待所有存活玩家提交行动"""
        while True:
            alive_players = [p.id for p in self.players if p.hp > 0]
            if len(self.actions) >= len(alive_players):
                return
            await asyncio.sleep(1)


# 优化战斗开始逻辑
@battle_start.handle()
async def handle_battle_start(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    user_id = event.get_user_id()
    
    async with safe_session() as session:
        if arg == "组队":
            # 获取用户所在的队伍
            team_member = await session.execute(
                select(TeamMember)
                .where(TeamMember.player_id == user_id)
                .options(joinedload(TeamMember.team))
            )
            team_member = team_member.scalars().first()
            
            if not team_member:
                await battle_start.finish("⛔ 你还没有准备好战斗的队伍")
                
            # 获取所有队员
            members = await session.execute(
                select(Player)
                .join(TeamMember, TeamMember.player_id == Player.id)
                .where(TeamMember.team_id == team_member.team.id)
            )
            members = members.scalars().all()
            
            # 生成敌人
            enemies = [generate_enemy("精英怪", max(m.level for m in members)),
                       generate_enemy("精英怪1", max(m.level for m in members)),
                       generate_enemy("精英怪2", max(m.level for m in members)),
                       ]
            
            battle = BattleInstance(BattleType.TEAM, members, enemies, event)
            await send_battle_ui(battle, event)

def generate_enemy(base_name: str, level: int) -> Dict:
    """根据玩家等级生成敌人"""
    return {
        "name": f"{base_name}",
        "max_hp": 50 + level * 10,
        "attack": 15 + level * 2,
        "defense": 5 + level,
        "agility": 3 + level // 2
    }

async def send_battle_ui(battle: BattleInstance, event: MessageEvent):
    """生成美观的战斗界面"""
    # 启动战斗循环
    asyncio.create_task(battle_loop(battle, event))
    enemy_info = "\n".join([
        f"{idx+1}. 👹 {e.name} ❤️ {e.hp}/{e.max_hp} | ⚡ {e.agility}"
        for idx, e in enumerate(battle.enemies)
    ])
    player_info = "\n".join([
        f"👤 {p.name} ❤️ {p.hp}/{p.max_hp} | 💧 {p.mp}/{p.max_mp}"
        for p in battle.players
    ])
    
    msg = (
        f"⚔️ {'组队' if battle.battle_type == BattleType.TEAM else '单人'}战斗开始！\n"
        f"------------------------\n"
        f"{player_info}\n"
        f"------------------------\n"
        f"VS\n"
        f"------------------------\n"
        f"{enemy_info}\n"
        f"------------------------\n"
        f"可用指令：\n"
        f"攻击 序号 | 使用 道具名 | 逃跑"
    )
    await battle_start.finish(create_rich_message(msg, event))

async def battle_loop(battle: BattleInstance, event: MessageEvent):
    """战斗主循环"""
    try:
        bot = get_bot()
        while True:
            # 处理回合
            result, report = await battle.process_turn()
            
            # 发送回合报告到最新上下文
            if battle.latest_event:
                await bot.send(battle.latest_event, report)

            # 处理战斗结果
            if result != "continue":
                result_msg = "🎉 战斗胜利！" if result == "players_win" else "💀 战斗失败，敌人获得了胜利..."
                await bot.send(battle.latest_event, result_msg)

                # 清理缓存
                for p in battle.players:
                    _player_battles.pop(p.id, None)
                return
                
            # 重置行动记录
            battle.actions.clear()
            
            # 等待5秒后进入下一回合
            await asyncio.sleep(5)
            
    except asyncio.CancelledError:
        # 清理过期的战斗
        for p in battle.players:
            _player_battles.pop(p.id, None)

@attack_cmd.handle()
async def handle_attack(event: MessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()
    battle = _player_battles.get(user_id)
    
    if not battle or battle.is_expired:
        await attack_cmd.finish("⛔ 你当前没有参与战斗")
    if battle.actions.get(user_id, None):
        return

    # 更新玩家最新消息上下文
    battle.latest_event = event
    
    # 解析攻击目标（按序号）
    arg = args.extract_plain_text().strip()
    
    try:
        if not arg:  # 无参数时默认第一个
            if not battle.enemies:
                await attack_cmd.finish("⚠️ 战场上已无敌人")
            target = battle.enemies[0]
        else:
            # 尝试转换为数字序号
            index = int(arg) - 1
            if index < 0 or index >= len(battle.enemies):
                raise ValueError
            target = battle.enemies[index]
            
    except ValueError:
        # 生成带序号的敌人列表提示
        enemy_list = "\n".join([f"{i+1}. {e.name}" for i, e in enumerate(battle.enemies)])
        await attack_cmd.finish(f"⛔ 请输入有效序号：\n{enemy_list}")

    # 记录行动
    battle.actions[user_id] = ('attack', target.id)
    await attack_cmd.finish(f"✅ 已锁定目标 {target.name}，等待回合结算")

@use_item_cmd.handle()
async def handle_use_item(event: MessageEvent):
    user_id = event.get_user_id()
    battle = _player_battles.get(user_id)
    
    if not battle or battle.is_expired:
        await use_item_cmd.finish("⛔ 你当前没有参与战斗")
    
    # 更新玩家最新消息上下文
    battle.latest_event = event
    
    # 调用现有背包系统
    async with safe_session() as session:
        inventory = await session.get(Inventory, user_id)