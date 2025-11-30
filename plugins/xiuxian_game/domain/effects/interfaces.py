"""
效果系统统一接口定义

提供IEffect抽象基类和相关数据结构，用于统一物品效果和战斗效果
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum


class TriggerType(Enum):
    """效果触发类型（统一物品和战斗）"""

    # 物品触发类型
    ON_USE = "on_use"  # 使用物品时

    # 战斗触发类型（来自battle_effects.py）
    ON_ATTACK = "on_attack"  # 攻击时
    ON_DEFENSE = "on_defense"  # 防御时
    ON_CRITICAL = "on_critical"  # 暴击时
    ON_DODGE = "on_dodge"  # 闪避时
    ON_HIT = "on_hit"  # 命中时
    ON_MISS = "on_miss"  # 未命中时
    ON_KILL = "on_kill"  # 击杀时
    ON_ROUND_START = "on_round_start"  # 回合开始时
    ON_ROUND_END = "on_round_end"  # 回合结束时
    ON_BATTLE_START = "on_battle_start"  # 战斗开始时
    ON_BATTLE_END = "on_battle_end"  # 战斗结束时
    ON_DAMAGED = "on_damaged"  # 受到伤害时


@dataclass
class EffectContext:
    """
    效果执行上下文

    统一的上下文对象，包含执行效果所需的所有信息
    设计原则：向后兼容，可扩展
    """
    # 核心参数
    player: Any  # Player对象（施法者）
    session: Any  # AsyncSession（数据库会话）

    # 触发信息
    trigger_type: TriggerType

    # 目标信息（可选）
    target: Optional[Any] = None  # 目标Player对象（战斗中使用）

    # 物品效果相关（兼容旧的item_effects.py）
    item_config: Optional[Any] = None  # ItemConfig对象
    quantity: int = 1  # 物品数量

    # 战斗效果相关（兼容旧的battle_effects.py）
    attacker: Optional[Any] = None  # 攻击者
    defender: Optional[Any] = None  # 防御者
    damage_dealt: Optional[int] = None  # 造成的伤害
    is_critical: bool = False  # 是否暴击

    # 通用元数据（扩展字段）
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 上下文类型（用于区分世界/战斗/诡域等场景）
    context_type: str = "world"  # "world", "battle", "dungeon"


@dataclass
class EffectResult:
    """
    效果执行结果

    统一的结果对象，表示效果执行后的状态和变化
    """
    # 执行状态
    success: bool
    message: str

    # 属性变化（用于日志和展示）
    attribute_changes: Dict[str, int] = field(default_factory=dict)

    # 状态变化（buff/debuff等）
    status_changes: List[str] = field(default_factory=list)

    # 额外数据（扩展字段）
    extra_data: Dict[str, Any] = field(default_factory=dict)


class IEffect(ABC):
    """
    效果接口 - 所有效果的统一抽象

    设计原则：
    1. 统一物品效果和战斗效果的接口
    2. 支持同步和异步执行
    3. 支持触发条件判断
    4. 支持持续性效果管理
    """

    @property
    @abstractmethod
    def effect_id(self) -> str:
        """
        效果唯一标识

        命名规范：
        - 物品效果：item_<effect_type>（如item_restore_hp）
        - 战斗效果：battle_<effect_type>（如battle_lifesteal）
        """
        pass

    @abstractmethod
    def can_trigger(self, context: EffectContext) -> bool:
        """
        判断是否可以触发此效果

        Args:
            context: 效果执行上下文

        Returns:
            bool: 是否可以触发
        """
        pass

    @abstractmethod
    async def execute(self, context: EffectContext) -> EffectResult:
        """
        执行效果

        Args:
            context: 效果执行上下文

        Returns:
            EffectResult: 执行结果
        """
        pass

    def tick(self) -> bool:
        """
        回合结算（仅用于持续性效果）

        对于一次性效果（如物品效果），直接返回True
        对于持续性效果（如战斗buff），更新持续时间并返回是否仍然有效

        Returns:
            bool: 效果是否仍然有效
        """
        return True  # 默认一次性效果


class BaseItemEffect(IEffect):
    """
    物品效果基类

    为物品效果提供通用实现，简化子类编写
    """

    def __init__(self, effect_id: str):
        self._effect_id = effect_id

    @property
    def effect_id(self) -> str:
        return self._effect_id

    def can_trigger(self, context: EffectContext) -> bool:
        """物品效果通常在使用时触发"""
        return context.trigger_type == TriggerType.ON_USE

    @abstractmethod
    async def execute(self, context: EffectContext) -> EffectResult:
        """子类实现具体效果逻辑"""
        pass


class BaseBattleEffect(IEffect):
    """
    战斗效果基类

    为战斗效果提供通用实现，包括持续时间管理
    """

    def __init__(
        self,
        effect_id: str,
        trigger_type: TriggerType,
        duration: int = 0,  # 0表示立即效果，-1表示永久，>0表示持续回合数
        max_stacks: int = 1  # 最大叠加层数
    ):
        self._effect_id = effect_id
        self._trigger_type = trigger_type
        self._duration = duration
        self._max_stacks = max_stacks
        self._current_stacks = 1

    @property
    def effect_id(self) -> str:
        return self._effect_id

    @property
    def trigger_type(self) -> TriggerType:
        return self._trigger_type

    @property
    def duration(self) -> int:
        return self._duration

    @property
    def current_stacks(self) -> int:
        return self._current_stacks

    def can_trigger(self, context: EffectContext) -> bool:
        """检查触发类型是否匹配"""
        return context.trigger_type == self._trigger_type

    def tick(self) -> bool:
        """持续性效果回合结算"""
        if self._duration > 0:
            self._duration -= 1
        return self._duration > 0 or self._duration == -1  # -1表示永久

    def add_stack(self) -> bool:
        """增加叠加层数"""
        if self._current_stacks < self._max_stacks:
            self._current_stacks += 1
            return True
        return False

    @abstractmethod
    async def execute(self, context: EffectContext) -> EffectResult:
        """子类实现具体效果逻辑"""
        pass
