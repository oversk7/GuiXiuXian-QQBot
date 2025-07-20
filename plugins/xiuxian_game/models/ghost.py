from sqlalchemy import String, Integer, Boolean, JSON, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.ext.mutable import MutableDict
from datetime import datetime
from .db import Base


class Ghost(Base):
    """鬼怪模板配置表
    
    存储所有鬼怪的基础信息，包括属性、威压等级、掉落配置等
    """
    __tablename__ = "ghost"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ghost_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="鬼怪ID")
    name: Mapped[str] = mapped_column(String(64), comment="鬼怪名称")
    description: Mapped[str] = mapped_column(Text, comment="鬼怪描述")
    
    # 基础属性
    hp: Mapped[int] = mapped_column(Integer, comment="生命值")
    attack: Mapped[int] = mapped_column(Integer, comment="攻击力")
    defense: Mapped[int] = mapped_column(Integer, comment="防御力")
    agility: Mapped[int] = mapped_column(Integer, comment="敏捷")
    
    # 威压相关
    base_prestige_level: Mapped[int] = mapped_column(Integer, default=1, comment="基础威压等级")
    required_attribute: Mapped[str] = mapped_column(String(16), comment="驾驭所需属性类型(理智/攻击/防御等)")
    attribute_per_level: Mapped[int] = mapped_column(Integer, default=50, comment="每级威压所需属性点数")
    
    # 掉落配置
    fragment_item_id: Mapped[str] = mapped_column(String(32), comment="对应碎片物品ID")
    fragment_drop_rate: Mapped[float] = mapped_column(default=0.3, comment="碎片掉落概率")
    fragments_to_complete: Mapped[int] = mapped_column(Integer, default=10, comment="合成完整鬼怪所需碎片数量")
    
    # 其他配置
    rarity: Mapped[str] = mapped_column(String(16), default="common", comment="稀有度(common/rare/epic/legendary)")
    special_abilities: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, comment="特殊能力配置")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())
    
    def calculate_prestige_level(self, player_attribute_value: int) -> int:
        """根据玩家属性值计算该鬼在玩家手中的威压等级"""
        bonus_levels = player_attribute_value // self.attribute_per_level
        return self.base_prestige_level + bonus_levels
    
    def get_fragment_drop_count(self) -> int:
        """获取掉落的碎片数量（可以根据稀有度调整）"""
        import random
        base_count = 1
        if self.rarity == "rare":
            base_count = random.randint(1, 2)
        elif self.rarity == "epic":
            base_count = random.randint(2, 3)
        elif self.rarity == "legendary":
            base_count = random.randint(3, 5)
        return base_count
