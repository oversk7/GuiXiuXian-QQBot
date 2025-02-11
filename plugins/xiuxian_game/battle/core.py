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
_BATTLE_TIMEOUT = 600

class BattleType(PyEnum):
    SOLO = "单人战斗"
    TEAM = "组队战斗"
    # PVP = "PVP战斗"


class BattleActor:
    """战斗参与者基类"""
    __slots__ = ['id', 'name', 'is_player', 'hp', 'max_hp', 'mp', 'max_mp', 
                'attack', 'defense', 'agility', 'fear_resistance', 'luck',
                'behavior', 'skills', 'action_weights']
    
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
            self.behavior = entity.get('behavior', 'normal')
            self.skills = entity.get('skills', [])
            self.action_weights = entity.get('action_weights', (70, 20, 10))  # 使用元组节省内存
        
    def calculate_hit_chance(self, target) -> float:
        """根据双方敏捷计算命中率"""
        return min(0.95, max(0.05, self.agility / (self.agility + target.agility)))

class BattleInstance:
    """战斗实例管理"""
    __slots__ = ['battle_id', 'battle_type', 'players', 'enemies', 
                'turn', 'last_active', 'actions', 'logs', 'latest_event', 'max_logs']
    
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
        self.max_logs = 5  # 只保留最近5回合日志

    @property
    def is_expired(self) -> bool:
        return (datetime.now() - self.last_active).seconds > _BATTLE_TIMEOUT

    async def process_turn(self):
        """优化后的回合处理逻辑"""
        self.turn += 1
        self.last_active = datetime.now()
        
        # 等待所有存活玩家提交行动
        await self._wait_for_actions()
        
        # 合并所有存活的参与者并按敏捷排序
        all_actors = self.players + self.enemies
        actors = sorted(
            [a for a in all_actors if a.hp > 0],
            key=lambda x: x.agility,
            reverse=True
        )
        
        battle_log = []
        for actor in actors:
            if not actor.hp > 0:
                continue
            
            # 玩家行动
            if actor.is_player:
                if action := self.actions.get(actor.id):
                    act_type, target_id = action
                    await self._handle_player_action(actor, act_type, target_id, battle_log)
            # 敌人行动
            else:
                await self._handle_enemy_action(actor, battle_log)
        
        # 生成回合报告
        report = create_rich_message(
            f"🌀 第{self.turn}回合结算：\n" +
            "\n".join(battle_log) + "\n\n" +
            "📊 当前状态：\n" +
            "👥 队友状态：\n" + 
            "\n".join([f"{'💀' if p.hp <=0 else '👤'} {p.name} ❤️ {p.hp if p.hp>0 else 0}/{p.max_hp} | 💧 {p.mp}/{p.max_mp}" 
                      for p in self.players]) + 
            "\n👹 敌人状态：\n" +
            "\n".join([f"{'💀' if e.hp <=0 else '👹'} {e.name} ❤️ {e.hp if e.hp>0 else 0}/{e.max_hp}" 
                      for e in self.enemies])
        )
        
        # 处理战斗结果
        if all(e.hp <= 0 for e in self.enemies):
            return "players_win", report
        if all(p.hp <= 0 for p in self.players):
            return "enemies_win", report
        return "continue", report

    async def _wait_for_actions(self):
        """等待所有存活玩家提交行动（无超时）"""
        while True:
            alive_players = [p.id for p in self.players if p.hp > 0]
            if len(self.actions) >= len(alive_players):
                return
            await asyncio.sleep(1)

    async def _handle_player_action(self, actor, act_type, target_id, battle_log):
        """玩家行动处理"""
        target = next((e for e in self.enemies if e.id == target_id), None)
        if not target:
            return
        
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

    async def _handle_enemy_action(self, enemy: BattleActor, battle_log: list):
        """敌人每回合随机选择行动"""
        valid_players = [p for p in self.players if p.hp > 0]
        if not valid_players:
            return
        
        # 根据概率随机选择行动类型
        action_type = random.choices(
            ['normal', 'skill', 'debuff'],
            weights=enemy.action_weights,
            k=1
        )[0]

        # 选择目标策略：优先攻击血量最低的玩家
        target = min(valid_players, key=lambda x: x.hp)
        
        # 根据随机结果执行不同行动
        if action_type == 'normal':
            await self._handle_normal_attack(enemy, target, battle_log)
        elif action_type == 'skill':
            await self._handle_skill_attack(enemy, target, battle_log)
        else:
            await self._handle_debuff_attack(enemy, target, battle_log)

    async def _handle_normal_attack(self, attacker, target, battle_log):
        """普通攻击处理"""
        hit_chance = attacker.calculate_hit_chance(target)
        if random.random() > hit_chance:
            battle_log.append(f"✨ {target.name} 灵巧地躲过了 {attacker.name} 的反击！")
            return
            
        damage = max(0, attacker.attack - target.defense)
        target.hp = max(0, target.hp - damage)
        battle_log.append(f"👹 {attacker.name} 反击 {target.name} 造成 {damage} 伤害！")

    async def _handle_debuff_attack(self, attacker, target, battle_log):
        """异常状态攻击"""
        hit_chance = attacker.calculate_hit_chance(target) * 0.8  # 技能命中率较低
        if random.random() > hit_chance:
            battle_log.append(f"✨ {target.name} 抵抗了 {attacker.name} 的异常攻击！")
            return
            
        # 随机选择debuff（示例）
        debuff = random.choice(["中毒", "虚弱", "恐惧"])
        battle_log.append(f"☠️ {attacker.name} 使 {target.name} 陷入【{debuff}】状态！")
        # 这里可以扩展debuff的持续效果存储

    async def _handle_skill_attack(self, attacker, target, battle_log):
        """技能攻击（更高伤害但命中率较低）"""
        hit_chance = attacker.calculate_hit_chance(target) * 0.7
        if random.random() > hit_chance:
            battle_log.append(f"✨ {target.name} 惊险躲过了 {attacker.name} 的技能！")
            return
        
        damage = int((attacker.attack * 1.5 - target.defense) * random.uniform(0.8, 1.2))
        target.hp = max(0, target.hp - damage)
        battle_log.append(f"🔥 {attacker.name} 发动技能攻击！对 {target.name} 造成 {damage} 伤害！")

    def _add_log(self, log: str):
        """优化日志存储"""
        if len(self.logs) >= self.max_logs:
            self.logs.pop(0)
        self.logs.append(log)


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
                       generate_enemy("精英怪", max(m.level for m in members)),
                       ]
            
            battle = BattleInstance(BattleType.TEAM, members, enemies, event)
            await send_battle_ui(battle, event)
        else:  # 单人战斗逻辑
            # 获取当前玩家
            player = await session.get(Player, user_id)
            if not player:
                await battle_start.finish("⛔ 请先创建角色后再进行战斗")
            
            # 生成适合玩家等级的敌人
            enemy_level = player.level
            enemies = [generate_enemy("试炼傀儡", enemy_level)]
            
            # 创建单人战斗实例
            battle = BattleInstance(BattleType.SOLO, [player], enemies, event)
            await send_battle_ui(battle, event)

def generate_enemy(base_name: str, level: int) -> Dict:
    """根据玩家等级生成敌人（优化内存）"""
    # 不同类型敌人配置不同行动概率
    action_config = {
        "法师": (50, 30, 20),    # 普通50%，技能30%，异常20%
        "刺客": (90, 10, 0)      # 普通攻击90%，技能10%
    }.get(base_name, (100, 0, 0))  # 默认配置

    return {
        "name": f"{base_name}",
        "max_hp": 50 + level * 10,
        "attack": 15 + level * 2,
        "defense": 5 + level,
        "agility": 5 + level,
        "action_weights": action_config,  # 添加行动概率配置
        "skills": []
    }

async def send_battle_ui(battle: BattleInstance, event: MessageEvent):
    """生成美观的战斗界面"""
    # 启动战斗循环
    asyncio.create_task(battle_loop(battle, event))
    enemy_info = "\n".join([
        f"{idx+1}. {'💀' if e.hp <=0 else '👹'} {e.name} ❤️ {e.hp if e.hp>0 else 0}/{e.max_hp} | ⚡ {e.agility}"
        for idx, e in enumerate(battle.enemies)
    ])
    player_info = "\n".join([
        f"{'💀' if p.hp <=0 else '👤'} {p.name} ❤️ {p.hp if p.hp>0 else 0}/{p.max_hp} | 💧 {p.mp}/{p.max_mp}"
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
    """优化后的战斗主循环"""
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
            
            # 减少循环间隔（原5秒改为1秒）
            await asyncio.sleep(1)
            
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
        if not arg:  # 无参数时选择第一个存活的敌人
            if not battle.enemies:
                await attack_cmd.finish("⚠️ 战场上已无敌人")
            # 寻找第一个存活的敌人
            for enemy in battle.enemies:
                if enemy.hp > 0:
                    target = enemy
                    break
            else:
                await attack_cmd.finish("⚠️ 所有敌人都已被击败")
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