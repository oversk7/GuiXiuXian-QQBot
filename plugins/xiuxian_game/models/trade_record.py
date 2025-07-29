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
