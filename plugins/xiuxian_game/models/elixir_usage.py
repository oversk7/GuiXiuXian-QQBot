from datetime import date
from sqlalchemy import Integer, String, Date, func
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class ElixirUsageLog(Base):
    """记录玩家每日服用丹药数量"""
    __tablename__ = "elixir_usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True)
    item_id: Mapped[str] = mapped_column(String(32))
    use_date: Mapped[Date] = mapped_column(Date, index=True, default=date.today)
    quantity: Mapped[int] = mapped_column(Integer, default=0)

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