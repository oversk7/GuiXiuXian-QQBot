from sqlalchemy import Integer, String, DateTime, func, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from enum import Enum
from .db import Base


class TradeType(Enum):
    """交易类型"""
    BUY = "buy"      # 购买
    SELL = "sell"    # 出售


class TradeRecord(Base):
    """交易记录表 - 记录玩家在跑商系统中的所有交易"""
    __tablename__ = "trade_record"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True, comment="玩家ID")
    trade_type: Mapped[TradeType] = mapped_column(SAEnum(TradeType), comment="交易类型")
    market_id: Mapped[str] = mapped_column(String(32), index=True, comment="市场ID")
    item_id: Mapped[str] = mapped_column(String(32), index=True, comment="商品ID")
    quantity: Mapped[int] = mapped_column(Integer, comment="交易数量")
    unit_price: Mapped[int] = mapped_column(Integer, comment="单价")
    total_amount: Mapped[int] = mapped_column(Integer, comment="总金额")
    trade_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), comment="交易时间")
    
    @classmethod
    async def can_sell_at_market(cls, session, player_id: str, market_id: str, item_id: str, hours: int = 8) -> bool:
        """
        检查玩家是否可以在指定市场出售指定商品
        规则：在某地购买的商品，指定小时数内不允许在同一地点出售
        
        Args:
            session: 数据库会话
            player_id: 玩家ID
            market_id: 市场ID
            item_id: 商品ID
            hours: 限制时间（小时）
            
        Returns:
            bool: True表示可以出售，False表示不可以出售
        """
        from sqlalchemy import select, and_
        from datetime import timedelta
        
        # 计算时间限制
        time_limit = datetime.now() - timedelta(hours=hours)
        
        # 查询玩家在指定时间内在该市场购买该商品的记录
        stmt = select(cls).where(
            and_(
                cls.player_id == player_id,
                cls.market_id == market_id,
                cls.item_id == item_id,
                cls.trade_type == TradeType.BUY,
                cls.trade_time > time_limit
            )
        )
        
        result = await session.execute(stmt)
        recent_purchases = result.scalars().all()
        
        # 如果有最近的购买记录，则不允许出售
        return len(recent_purchases) == 0
    
    @classmethod
    async def get_recent_purchases_at_market(cls, session, player_id: str, market_id: str, item_id: str, hours: int = 8):
        """
        获取玩家在指定市场最近购买指定商品的记录
        
        Returns:
            list: 最近的购买记录列表
        """
        from sqlalchemy import select, and_
        from datetime import timedelta
        
        time_limit = datetime.now() - timedelta(hours=hours)
        
        stmt = select(cls).where(
            and_(
                cls.player_id == player_id,
                cls.market_id == market_id,
                cls.item_id == item_id,
                cls.trade_type == TradeType.BUY,
                cls.trade_time > time_limit
            )
        ).order_by(cls.trade_time.desc())
        
        result = await session.execute(stmt)
        return result.scalars().all()
    
    @classmethod
    async def can_list_item(cls, session, player_id: str, item_id: str, hours: int = 8) -> tuple[bool, str]:
        """
        检查玩家是否可以挂牌指定商品
        规则：8小时内购买的商品不允许挂牌

        Args:
            session: 数据库会话
            player_id: 玩家ID
            item_id: 商品ID
            hours: 限制时间（小时）

        Returns:
            tuple[bool, str]: (是否可以挂牌, 错误信息)
        """
        from sqlalchemy import select, and_
        from datetime import timedelta

        # 计算时间限制
        time_limit = datetime.now() - timedelta(hours=hours)

        # 查询玩家在指定时间内购买该商品的记录（任何市场）
        stmt = select(cls).where(
            and_(
                cls.player_id == player_id,
                cls.item_id == item_id,
                cls.trade_type == TradeType.BUY,
                cls.trade_time > time_limit
            )
        ).order_by(cls.trade_time.desc())

        result = await session.execute(stmt)
        recent_purchases = result.scalars().all()

        # 如果有最近的购买记录，则不允许挂牌
        if recent_purchases:
            latest_purchase = recent_purchases[0]
            unlock_time = latest_purchase.trade_time + timedelta(hours=hours)
            from ..config import config
            item_cfg = config.items_config["by_id"].get(item_id)
            item_name = item_cfg.name if item_cfg else item_id

            return False, (
                f"⛔ 挂牌限制！\n"
                f"你在 {latest_purchase.trade_time.strftime('%m-%d %H:%M')} 购买了 {item_name}\n"
                f"需要等到 {unlock_time.strftime('%m-%d %H:%M')} 才能挂牌\n"
                f"💡 此限制防止通过挂牌给小号来规避跑商机制"
            )

        return True, ""

    @classmethod
    async def get_daily_purchase_quantity(cls, session, player_id: str, market_id: str, item_id: str) -> int:
        """
        查询玩家当日在指定市场购买指定商品的总数量（使用09:00日切）

        Args:
            session: 数据库会话
            player_id: 玩家ID
            market_id: 市场ID
            item_id: 商品ID

        Returns:
            int: 当日已购买总数量
        """
        from sqlalchemy import select, and_, func as sa_func
        from datetime import time, timedelta, date

        # 与 _current_seed_day() 一致的 09:00 日切逻辑
        now = datetime.now()
        day = now.date()
        if now.time() < time(hour=9):
            day -= timedelta(days=1)
        day_start = datetime.combine(day, time(hour=9))

        stmt = select(sa_func.coalesce(sa_func.sum(cls.quantity), 0)).where(
            and_(
                cls.player_id == player_id,
                cls.market_id == market_id,
                cls.item_id == item_id,
                cls.trade_type == TradeType.BUY,
                cls.trade_time >= day_start
            )
        )

        result = await session.execute(stmt)
        return result.scalar() or 0

    @classmethod
    async def get_daily_cross_market_sell_count(cls, session, player_id: str) -> int:
        """
        查询玩家当日跨市场出售笔数（使用09:00日切，排除黑市）

        Args:
            session: 数据库会话
            player_id: 玩家ID

        Returns:
            int: 当日跨市场出售笔数
        """
        from sqlalchemy import select, and_, func as sa_func
        from datetime import time, timedelta, date

        # 与 _current_seed_day() 一致的 09:00 日切逻辑
        now = datetime.now()
        day = now.date()
        if now.time() < time(hour=9):
            day -= timedelta(days=1)
        day_start = datetime.combine(day, time(hour=9))

        stmt = select(sa_func.count(cls.id)).where(
            and_(
                cls.player_id == player_id,
                cls.trade_type == TradeType.SELL,
                cls.trade_time >= day_start,
                cls.market_id != 'black_market'
            )
        )

        result = await session.execute(stmt)
        return result.scalar() or 0

    @classmethod
    async def record_trade(cls, session, player_id: str, trade_type: TradeType, market_id: str,
                          item_id: str, quantity: int, unit_price: int, total_amount: int):
        """
        记录一笔交易

        Args:
            session: 数据库会话
            player_id: 玩家ID
            trade_type: 交易类型
            market_id: 市场ID
            item_id: 商品ID
            quantity: 交易数量
            unit_price: 单价
            total_amount: 总金额
        """
        trade_record = cls(
            player_id=player_id,
            trade_type=trade_type,
            market_id=market_id,
            item_id=item_id,
            quantity=quantity,
            unit_price=unit_price,
            total_amount=total_amount,
            trade_time=datetime.now()
        )
        session.add(trade_record)
        return trade_record
