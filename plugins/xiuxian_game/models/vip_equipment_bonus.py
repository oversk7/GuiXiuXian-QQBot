"""
VIP装备永久属性加成记录

用于持久化VIP装备（斩龙闪、镜怨之衣）的永久属性提升，
确保这些加成在冥返（轮回）后不会被清除。
"""

from sqlalchemy import Integer, String, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class VIPEquipmentBonus(Base):
    """VIP装备永久属性加成记录"""
    __tablename__ = "vip_equipment_bonus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True, unique=True)
    
    # 存储各属性的累计加成值
    # 格式: {"attack": 100, "max_mp": 80, "defense": 40, ...}
    bonus_attrs: Mapped[dict] = mapped_column(JSON, default=dict)

    def add_bonus(self, attr_name: str, value: int):
        """增加指定属性的加成"""
        if not self.bonus_attrs:
            self.bonus_attrs = {}
        self.bonus_attrs[attr_name] = self.bonus_attrs.get(attr_name, 0) + value

    def get_total_bonus(self) -> dict:
        """获取所有属性的总加成"""
        return self.bonus_attrs or {}

    @classmethod
    async def get_or_create(cls, session, player_id: str):
        """获取或创建玩家的VIP装备加成记录"""
        from sqlalchemy import select
        stmt = select(cls).where(cls.player_id == player_id)
        result = await session.execute(stmt)
        record = result.scalars().first()
        
        if not record:
            record = cls(player_id=player_id, bonus_attrs={})
            session.add(record)
            await session.flush()
        
        return record

