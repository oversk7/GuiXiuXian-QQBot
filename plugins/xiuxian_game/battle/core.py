from nonebot import on_command, on_keyword
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

# 战斗缓存结构
_active_battles: Dict[str, 'BattleInstance'] = {}  # 战斗ID到实例的映射
_player_battle_map: Dict[str, str] = {}  # 玩家ID到战斗ID的映射
_BATTLE_TIMEOUT = 120  # 2分钟无操作自动结束战斗

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
        """处理战斗回合"""
        self.turn += 1
        self.last_active = datetime.now()
        
        # 处理玩家行动
        for actor in [a for a in self.players + self.enemies if a.hp > 0]:
            if action := self.actions.get(actor.id):
                # 执行具体行动逻辑
                pass
        
        # 清理缓存行动
        self.actions.clear()
        
        # 检查战斗结束条件
        if all(e.hp <= 0 for e in self.enemies):
            return "players_win"
        if all(p.hp <= 0 for p in self.players):
            return "enemies_win"
        return "continue"

# 战斗命令
battle_start = on_command("战斗", aliases={"挑战"}, block=True, priority=5)
attack_cmd = on_command("攻击", block=True, priority=5)
use_item_cmd = on_command("使用", block=True, priority=5)
escape_cmd = on_command("逃跑", block=True, priority=5)

@battle_start.handle()
async def start_battle(event: MessageEvent, args: Message = CommandArg()):
    """示例：触发普通战斗"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await battle_start.finish("⛔ 请先创建角色")
        
        # 生成示例敌人
        enemies = [{
            "name": "诡异村民",
            "hp": 50,
            "max_hp": 50,
            "attack": 15,
            "defense": 5,
            "agility": 3
        }]
        
        battle = BattleInstance(BattleType.SOLO, [player], enemies)
        _active_battles[battle.battle_id] = battle
        
        msg = f"⚔️ 战斗开始！\n" \
              f"敌人：{'、'.join(e['name'] for e in enemies)}\n" \
              f"可用指令：攻击/使用/逃跑"
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