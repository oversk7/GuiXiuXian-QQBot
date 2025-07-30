from datetime import date
from sqlalchemy import Integer, String, Date, func
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from ..config import config
from .inventory import ItemEffectType

class ElixirUsageLog(Base):
    """记录玩家每日服用丹药数量"""
    __tablename__ = "elixir_usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True)
    item_id: Mapped[str] = mapped_column(String(32))
    use_date: Mapped[Date] = mapped_column(Date, index=True, default=date.today)
    quantity: Mapped[int] = mapped_column(Integer, default=0)

    def get_attribute_bonus(self) -> dict:
        """获取该记录对应的属性加成"""
        item_cfg = config.items_config["by_id"].get(self.item_id)
        if not item_cfg or item_cfg.effect_type != ItemEffectType.BUFF:
            return {}
        
        effect_params = item_cfg.effect_params or {}
        bonus = {}
        for attr, value in effect_params.items():
            if isinstance(value, (int, float)):
                bonus[attr] = int(value) * self.quantity
        
        return bonus

    @classmethod
    async def get_or_create_log(cls, session, player_id: str, item_id: str, use_date: date = None):
        """获取或创建当日使用记录"""
        if use_date is None:
            use_date = date.today()

        from sqlalchemy import select
        stmt = select(cls).where(
            cls.player_id == player_id,
            cls.item_id == item_id,
            cls.use_date == use_date
        )
        log = (await session.execute(stmt)).scalars().first()

        if not log:
            log = cls(
                player_id=player_id,
                item_id=item_id,
                use_date=use_date,
                quantity=0
            )
            session.add(log)

        return log