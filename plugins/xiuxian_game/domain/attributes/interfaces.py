"""
属性计算接口定义

定义属性来源的统一接口和数据结构
"""

from typing import Protocol, Dict
from dataclasses import dataclass, field


@dataclass
class AttributeBonus:
    """属性加成数据类"""

    # 基础战斗属性
    attack: int = 0
    defense: int = 0
    hp: int = 0
    max_hp: int = 0
    mp: int = 0
    max_mp: int = 0

    # 修炼属性
    cultivation: int = 0
    realm: int = 0

    # 战斗属性
    crit_rate: float = 0.0
    crit_damage: float = 0.0
    dodge_rate: float = 0.0
    accuracy: float = 0.0
    agility: int = 0
    luck: int = 0

    # 资源属性
    gold_multiplier: float = 1.0
    exp_multiplier: float = 1.0

    def __add__(self, other: 'AttributeBonus') -> 'AttributeBonus':
        """支持 + 运算符，合并两个属性加成"""
        if not isinstance(other, AttributeBonus):
            return NotImplemented

        return AttributeBonus(
            attack=self.attack + other.attack,
            defense=self.defense + other.defense,
            hp=self.hp + other.hp,
            max_hp=self.max_hp + other.max_hp,
            mp=self.mp + other.mp,
            max_mp=self.max_mp + other.max_mp,
            cultivation=self.cultivation + other.cultivation,
            realm=self.realm + other.realm,
            crit_rate=self.crit_rate + other.crit_rate,
            crit_damage=self.crit_damage + other.crit_damage,
            dodge_rate=self.dodge_rate + other.dodge_rate,
            accuracy=self.accuracy + other.accuracy,
            agility=self.agility + other.agility,
            luck=self.luck + other.luck,
            gold_multiplier=self.gold_multiplier * other.gold_multiplier,
            exp_multiplier=self.exp_multiplier * other.exp_multiplier,
        )

    def to_dict(self) -> Dict[str, int | float]:
        """转换为字典，兼容旧代码"""
        return {
            "attack": self.attack,
            "defense": self.defense,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "mp": self.mp,
            "max_mp": self.max_mp,
            "cultivation": self.cultivation,
            "realm": self.realm,
            "crit_rate": self.crit_rate,
            "crit_damage": self.crit_damage,
            "dodge_rate": self.dodge_rate,
            "accuracy": self.accuracy,
            "agility": self.agility,
            "luck": self.luck,
            "gold_multiplier": self.gold_multiplier,
            "exp_multiplier": self.exp_multiplier,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, int | float]) -> 'AttributeBonus':
        """从字典创建，兼容旧代码"""
        return cls(
            attack=data.get("attack", 0),
            defense=data.get("defense", 0),
            hp=data.get("hp", 0),
            max_hp=data.get("max_hp", 0),
            mp=data.get("mp", 0),
            max_mp=data.get("max_mp", 0),
            cultivation=data.get("cultivation", 0),
            realm=data.get("realm", 0),
            crit_rate=data.get("crit_rate", 0.0),
            crit_damage=data.get("crit_damage", 0.0),
            dodge_rate=data.get("dodge_rate", 0.0),
            accuracy=data.get("accuracy", 0.0),
            agility=data.get("agility", 0),
            luck=data.get("luck", 0),
            gold_multiplier=data.get("gold_multiplier", 1.0),
            exp_multiplier=data.get("exp_multiplier", 1.0),
        )


@dataclass
class AttributeBreakdown:
    """属性明细分解 - 用于调试和展示各来源加成"""

    base: AttributeBonus
    equipment: AttributeBonus = field(default_factory=AttributeBonus)
    buff: AttributeBonus = field(default_factory=AttributeBonus)
    elixir: AttributeBonus = field(default_factory=AttributeBonus)
    vip: AttributeBonus = field(default_factory=AttributeBonus)
    total: AttributeBonus = field(default_factory=AttributeBonus)

    def calculate_total(self):
        """计算总属性"""
        self.total = (
            self.base +
            self.equipment +
            self.buff +
            self.elixir +
            self.vip
        )


class IAttributeSource(Protocol):
    """
    属性来源接口

    所有属性来源（装备、buff、丹药、VIP等）都实现此接口
    """

    async def calculate_bonus(self, player, session) -> AttributeBonus:
        """
        计算属性加成

        Args:
            player: Player实例
            session: 数据库会话

        Returns:
            AttributeBonus: 属性加成
        """
        ...

    @property
    def source_name(self) -> str:
        """属性来源名称（用于调试）"""
        ...
