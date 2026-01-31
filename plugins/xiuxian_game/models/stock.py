from sqlalchemy import String, Integer, BigInteger, DateTime, Float, Boolean, ForeignKey, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import Optional
from enum import Enum as PyEnum
from .db import Base


class StockType(str, PyEnum):
    """股票类型"""
    TECH = "TECH"           # 科技股
    FINANCE = "FINANCE"     # 金融股
    ENERGY = "ENERGY"       # 能源股
    CONSUMER = "CONSUMER"   # 消费股
    HEALTHCARE = "HEALTHCARE"  # 医疗股
    MATERIALS = "MATERIALS"    # 材料股


class TransactionType(str, PyEnum):
    """交易类型"""
    BUY = "BUY"     # 买入
    SELL = "SELL"   # 卖出


class Stock(Base):
    """股票基本信息表"""
    __tablename__ = "stocks"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(10), unique=True, index=True, comment="股票代码")
    name: Mapped[str] = mapped_column(String(50), comment="股票名称")
    stock_type: Mapped[StockType] = mapped_column(String(20), comment="股票类型")
    
    # 价格信息
    base_price: Mapped[int] = mapped_column(Integer, comment="基础价格（金币）")
    current_price: Mapped[int] = mapped_column(Integer, comment="当前价格（金币）")
    
    # 市场数据
    total_shares: Mapped[int] = mapped_column(BigInteger, default=1000000, comment="总股本")
    circulating_shares: Mapped[int] = mapped_column(BigInteger, default=1000000, comment="流通股本")
    
    # 波动参数
    volatility: Mapped[float] = mapped_column(Float, default=0.05, comment="波动率（0.01-0.20）")
    trend_factor: Mapped[float] = mapped_column(Float, default=1.0, comment="趋势因子（0.8-1.2）")

    # 健康度系统（反套利机制）
    health: Mapped[int] = mapped_column(Integer, default=100, comment="健康度(100-0)")
    health_decay_rate: Mapped[float] = mapped_column(Float, default=1.0, comment="健康度衰减速度倍率")

    # 状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否活跃（未退市）")
    delisted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="退市时间")
    delist_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="退市原因")
    relisted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="重新上市时间")
    relist_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="重新上市原因")

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 关系
    holdings: Mapped[list["StockHolding"]] = relationship("StockHolding", back_populates="stock")
    transactions: Mapped[list["StockTransaction"]] = relationship("StockTransaction", back_populates="stock")
    price_history: Mapped[list["StockPriceHistory"]] = relationship("StockPriceHistory", back_populates="stock")


class StockHolding(Base):
    """玩家股票持仓表"""
    __tablename__ = "stock_holdings"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stocks.id"), index=True)
    
    # 持仓信息
    shares: Mapped[int] = mapped_column(Integer, default=0, comment="持有股数")
    avg_cost: Mapped[int] = mapped_column(Integer, default=0, comment="平均成本价（金币）")
    total_cost: Mapped[int] = mapped_column(BigInteger, default=0, comment="总成本（金币）")
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 关系
    player: Mapped["Player"] = relationship("Player")
    stock: Mapped["Stock"] = relationship("Stock", back_populates="holdings")
    
    # 复合索引
    __table_args__ = (
        Index('idx_player_stock', 'player_id', 'stock_id', unique=True),
    )
    
    @property
    def current_value(self) -> int:
        """当前市值"""
        return self.shares * self.stock.current_price
    
    @property
    def profit_loss(self) -> int:
        """盈亏金额"""
        return self.current_value - self.total_cost
    
    @property
    def profit_loss_rate(self) -> float:
        """盈亏比例"""
        if self.total_cost == 0:
            return 0.0
        return (self.profit_loss / self.total_cost) * 100


class StockTransaction(Base):
    """股票交易记录表"""
    __tablename__ = "stock_transactions"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stocks.id"), index=True)
    
    # 交易信息
    transaction_type: Mapped[TransactionType] = mapped_column(String(10), comment="交易类型")
    shares: Mapped[int] = mapped_column(Integer, comment="交易股数")
    price: Mapped[int] = mapped_column(Integer, comment="交易价格（金币/股）")
    total_amount: Mapped[int] = mapped_column(BigInteger, comment="交易总金额（金币）")
    
    # 手续费
    commission: Mapped[int] = mapped_column(Integer, default=0, comment="手续费（金币）")
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    # 关系
    player: Mapped["Player"] = relationship("Player")
    stock: Mapped["Stock"] = relationship("Stock", back_populates="transactions")


class StockPriceHistory(Base):
    """股票价格历史表"""
    __tablename__ = "stock_price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stocks.id"), index=True)

    # 价格信息
    price: Mapped[int] = mapped_column(Integer, comment="价格（金币）")
    change_amount: Mapped[int] = mapped_column(Integer, default=0, comment="变动金额")
    change_rate: Mapped[float] = mapped_column(Float, default=0.0, comment="变动比例")

    # 成交信息
    volume: Mapped[int] = mapped_column(Integer, default=0, comment="成交量")

    # 时间戳
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    # 关系
    stock: Mapped["Stock"] = relationship("Stock", back_populates="price_history")

    # 索引
    __table_args__ = (
        Index('idx_stock_time', 'stock_id', 'recorded_at'),
    )


class StockEvent(Base):
    """股票突发事件表"""
    __tablename__ = "stock_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(50), comment="事件ID")
    event_name: Mapped[str] = mapped_column(String(100), comment="事件名称")
    description: Mapped[str] = mapped_column(String(500), comment="事件描述")
    affected_stock_id: Mapped[int] = mapped_column(Integer, ForeignKey("stocks.id"), index=True, comment="受影响股票ID")
    price_impact: Mapped[float] = mapped_column(Float, comment="价格影响（-0.4表示跌40%）")
    health_impact: Mapped[int] = mapped_column(Integer, comment="健康度影响")
    trigger_date: Mapped[datetime] = mapped_column(DateTime, comment="触发时间")
    duration_days: Mapped[int] = mapped_column(Integer, comment="持续天数")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否生效中")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # 关系
    stock: Mapped["Stock"] = relationship("Stock", foreign_keys=[affected_stock_id])

    # 索引
    __table_args__ = (
        Index('idx_stock_event', 'affected_stock_id', 'is_active'),
    )
