"""
游戏领域事件定义

包含玩家、战斗、社交等核心游戏事件。
这些事件用于解耦跨模块功能，如成就、统计、通知等。
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .interfaces import IEvent


# ==================== 玩家事件 ====================

@dataclass
class PlayerLevelUpEvent(IEvent):
    """玩家升级事件"""
    player_id: str
    old_level: int
    new_level: int
    realm: str  # 当前境界

    @property
    def event_name(self) -> str:
        return f"玩家升级 [{self.player_id}] {self.old_level}→{self.new_level}"


@dataclass
class PlayerBreakthroughEvent(IEvent):
    """玩家突破境界事件"""
    player_id: str
    old_realm: str
    new_realm: str
    level: int  # 突破后的等级

    @property
    def event_name(self) -> str:
        return f"玩家突破 [{self.player_id}] {self.old_realm}→{self.new_realm}"


@dataclass
class PlayerAttributeChangeEvent(IEvent):
    """玩家属性变化事件（用于成就、统计）"""
    player_id: str
    attribute_name: str  # 属性名称
    old_value: float
    new_value: float
    change_reason: str  # 变化原因（如"升级"、"装备"、"buff"）

    @property
    def event_name(self) -> str:
        return f"属性变化 [{self.player_id}] {self.attribute_name}: {self.old_value}→{self.new_value}"


@dataclass
class PlayerDeathEvent(IEvent):
    """玩家死亡事件"""
    player_id: str
    killer_id: Optional[str]  # 击杀者ID（可能是怪物或其他玩家）
    killer_type: str  # 击杀者类型: "player", "monster", "environment"
    location: str  # 死亡地点
    lost_items: list  # 掉落的物品列表

    @property
    def event_name(self) -> str:
        if self.killer_type == "player":
            return f"玩家死亡 [{self.player_id}] 被玩家 {self.killer_id} 击杀"
        elif self.killer_type == "monster":
            return f"玩家死亡 [{self.player_id}] 被怪物 {self.killer_id} 击杀"
        else:
            return f"玩家死亡 [{self.player_id}] 在 {self.location}"


# ==================== 战斗事件 ====================

@dataclass
class MonsterKilledEvent(IEvent):
    """怪物击杀事件"""
    player_id: str
    monster_id: str  # 怪物ID
    monster_name: str  # 怪物名称
    monster_level: int  # 怪物等级
    location: str  # 击杀地点
    exp_gained: int  # 获得的经验
    is_boss: bool = False  # 是否为BOSS

    @property
    def event_name(self) -> str:
        boss_flag = "[BOSS]" if self.is_boss else ""
        return f"击杀怪物 [{self.player_id}] {boss_flag}{self.monster_name}(Lv.{self.monster_level})"


@dataclass
class PvPBattleEvent(IEvent):
    """PvP战斗事件"""
    attacker_id: str
    defender_id: str
    winner_id: str  # 胜利者ID
    battle_type: str  # 战斗类型: "pk", "arena", "world_boss_pvp"
    damage_dealt: int  # 造成的总伤害
    rounds: int  # 战斗回合数

    @property
    def event_name(self) -> str:
        return f"PvP战斗 [{self.attacker_id} vs {self.defender_id}] 胜者:{self.winner_id}"


@dataclass
class WorldBossDamageEvent(IEvent):
    """世界BOSS伤害事件（用于排行榜统计）"""
    player_id: str
    boss_id: str
    boss_name: str
    damage: int  # 本次造成的伤害
    total_damage: int  # 累计总伤害
    is_final_blow: bool = False  # 是否为最后一击

    @property
    def event_name(self) -> str:
        final_flag = "[最后一击]" if self.is_final_blow else ""
        return f"BOSS伤害 [{self.player_id}] {final_flag}对{self.boss_name}造成{self.damage:,}伤害"


# ==================== 经济事件 ====================

@dataclass
class ItemTradedEvent(IEvent):
    """物品交易事件"""
    seller_id: str
    buyer_id: str
    item_id: str
    item_name: str
    quantity: int
    price: int  # 交易价格

    @property
    def event_name(self) -> str:
        return f"物品交易 [{self.seller_id}→{self.buyer_id}] {self.item_name}x{self.quantity} 价格:{self.price:,}"


@dataclass
class GoldChangeEvent(IEvent):
    """金币变化事件"""
    player_id: str
    change_amount: int  # 变化量（正数为获得，负数为消耗）
    reason: str  # 变化原因
    final_balance: int  # 变化后的余额

    @property
    def event_name(self) -> str:
        action = "获得" if self.change_amount > 0 else "消耗"
        return f"金币{action} [{self.player_id}] {abs(self.change_amount):,} 原因:{self.reason}"


# ==================== 社交事件 ====================

@dataclass
class GuildDonationEvent(IEvent):
    """公会捐献事件"""
    player_id: str
    guild_id: str
    donation_type: str  # 捐献类型: "gold", "item", "material"
    amount: int  # 捐献数量
    contribution_gained: int  # 获得的贡献度

    @property
    def event_name(self) -> str:
        return f"公会捐献 [{self.player_id}→{self.guild_id}] {self.donation_type}x{self.amount}"


@dataclass
class MarriageCreatedEvent(IEvent):
    """结婚事件"""
    player1_id: str
    player2_id: str
    marriage_id: str

    @property
    def event_name(self) -> str:
        return f"结婚 [{self.player1_id} ♥ {self.player2_id}]"


@dataclass
class MentorshipEstablishedEvent(IEvent):
    """师徒关系建立事件"""
    master_id: str
    apprentice_id: str

    @property
    def event_name(self) -> str:
        return f"收徒 [{self.master_id}→{self.apprentice_id}]"


@dataclass
class GiftGivenEvent(IEvent):
    """送礼事件"""
    sender_id: str
    receiver_id: str
    item_id: str
    item_name: str
    quantity: int
    favorability_gained: int  # 获得的好感度

    @property
    def event_name(self) -> str:
        return f"送礼 [{self.sender_id}→{self.receiver_id}] {self.item_name}x{self.quantity} +{self.favorability_gained}好感"


# ==================== 物品事件 ====================

@dataclass
class ItemCraftedEvent(IEvent):
    """物品制作事件"""
    player_id: str
    item_id: str
    item_name: str
    quantity: int
    quality: Optional[str] = None  # 品质（如果有）

    @property
    def event_name(self) -> str:
        quality_str = f"[{self.quality}]" if self.quality else ""
        return f"制作物品 [{self.player_id}] {quality_str}{self.item_name}x{self.quantity}"


@dataclass
class EquipmentEnhancedEvent(IEvent):
    """装备强化事件"""
    player_id: str
    equipment_id: str
    equipment_name: str
    old_level: int
    new_level: int
    success: bool  # 是否成功

    @property
    def event_name(self) -> str:
        result = "成功" if self.success else "失败"
        return f"装备强化 [{self.player_id}] {self.equipment_name} +{self.old_level}→+{self.new_level} {result}"


# ==================== 世界事件 ====================

@dataclass
class DungeonEnteredEvent(IEvent):
    """进入诡域事件"""
    player_id: str
    dungeon_id: str
    dungeon_name: str
    difficulty: str  # 难度等级

    @property
    def event_name(self) -> str:
        return f"进入诡域 [{self.player_id}] {self.dungeon_name}({self.difficulty})"


@dataclass
class DungeonCompletedEvent(IEvent):
    """完成诡域事件"""
    player_id: str
    dungeon_id: str
    dungeon_name: str
    completion_time: int  # 完成时间（秒）
    score: int  # 评分

    @property
    def event_name(self) -> str:
        return f"完成诡域 [{self.player_id}] {self.dungeon_name} 用时:{self.completion_time}s 评分:{self.score}"


@dataclass
class ResourceNodeGatheredEvent(IEvent):
    """资源点采集事件"""
    player_id: str
    resource_type: str  # 资源类型
    quantity: int
    location: str  # 采集地点

    @property
    def event_name(self) -> str:
        return f"资源采集 [{self.player_id}] {self.resource_type}x{self.quantity} @{self.location}"
