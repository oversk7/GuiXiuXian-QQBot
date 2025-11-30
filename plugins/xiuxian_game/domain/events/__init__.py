"""
领域事件模块

提供事件系统的核心接口和基础设施：
- IEvent: 事件接口
- EventBus: 事件总线（发布/订阅）
- 各种领域事件定义
"""

from .interfaces import IEvent, IEventHandler
from .event_bus import EventBus
from .game_events import (
    # 玩家事件
    PlayerLevelUpEvent,
    PlayerBreakthroughEvent,
    PlayerAttributeChangeEvent,
    PlayerDeathEvent,
    # 战斗事件
    MonsterKilledEvent,
    PvPBattleEvent,
    WorldBossDamageEvent,
    # 经济事件
    ItemTradedEvent,
    GoldChangeEvent,
    # 社交事件
    GuildDonationEvent,
    MarriageCreatedEvent,
    MentorshipEstablishedEvent,
    GiftGivenEvent,
    # 物品事件
    ItemCraftedEvent,
    EquipmentEnhancedEvent,
    # 世界事件
    DungeonEnteredEvent,
    DungeonCompletedEvent,
    ResourceNodeGatheredEvent,
)

# 导出全局事件总线实例
event_bus = EventBus()

__all__ = [
    # 核心接口
    "IEvent",
    "IEventHandler",
    "EventBus",
    "event_bus",
    # 玩家事件
    "PlayerLevelUpEvent",
    "PlayerBreakthroughEvent",
    "PlayerAttributeChangeEvent",
    "PlayerDeathEvent",
    # 战斗事件
    "MonsterKilledEvent",
    "PvPBattleEvent",
    "WorldBossDamageEvent",
    # 经济事件
    "ItemTradedEvent",
    "GoldChangeEvent",
    # 社交事件
    "GuildDonationEvent",
    "MarriageCreatedEvent",
    "MentorshipEstablishedEvent",
    "GiftGivenEvent",
    # 物品事件
    "ItemCraftedEvent",
    "EquipmentEnhancedEvent",
    # 世界事件
    "DungeonEnteredEvent",
    "DungeonCompletedEvent",
    "ResourceNodeGatheredEvent",
]
