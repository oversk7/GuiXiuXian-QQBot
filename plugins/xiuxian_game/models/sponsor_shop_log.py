"""
赞助商店兑换日志

记录每一笔诡烛消费，用于对账和纠纷处理。
"""
from datetime import datetime
from sqlalchemy import Integer, BigInteger, String, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from .db import Base


class SponsorShopLog(Base):
    """赞助商店兑换日志"""

    __tablename__ = "sponsor_shop_log"

    __table_args__ = (
        Index("ix_sponsor_shop_log_player_time", "player_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 玩家信息（快照，避免改名后查不到）
    player_id: Mapped[str] = mapped_column(String(32), index=True, comment="玩家平台ID")
    uid: Mapped[int] = mapped_column(Integer, index=True, comment="玩家UID")
    nickname: Mapped[str] = mapped_column(String(32), comment="购买时昵称快照")

    # 兑换内容
    action: Mapped[str] = mapped_column(String(32), index=True, comment="兑换类型，如：棺材钉/哭坟帽/背包扩容/初级月卡等")
    detail: Mapped[str] = mapped_column(String(128), default="", server_default="", comment="补充信息，如扩容格数、称号名称")

    # 诡烛变动
    cost: Mapped[int] = mapped_column(Integer, comment="本次消耗诡烛")
    balance_before: Mapped[int] = mapped_column(BigInteger, comment="兑换前余额")
    balance_after: Mapped[int] = mapped_column(BigInteger, comment="兑换后余额")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(), comment="兑换时间"
    )

    @classmethod
    async def add_log(
        cls,
        session,
        player,
        action: str,
        detail: str,
        cost: int,
        balance_before: int,
    ) -> "SponsorShopLog":
        """插入一条兑换日志（在同一事务内调用，与购买操作原子提交）"""
        log = cls(
            player_id=player.id,
            uid=player.uid,
            nickname=player.nickname,
            action=action,
            detail=detail,
            cost=cost,
            balance_before=balance_before,
            balance_after=balance_before - cost,
        )
        session.add(log)
        return log
