"""
银行理财产品数据模型
"""
from sqlalchemy import String, Integer, BigInteger, Float, DateTime, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from datetime import datetime


class BankFund(Base):
    """银行理财基金（活期理财）"""
    __tablename__ = "bank_fund"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="基金ID")
    fund_name: Mapped[str] = mapped_column(String(100), comment="基金名称")
    fund_type: Mapped[str] = mapped_column(String(50), default="lively", comment="基金类型(lively=活期)")
    daily_return: Mapped[float] = mapped_column(Float, default=0.0, comment="当日收益率")
    total_scale: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0', comment="基金总规模(金币)")
    participant_count: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="参与人数")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


class FundHolding(Base):
    """玩家理财持仓"""
    __tablename__ = "fund_holding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="持仓ID")
    player_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="玩家ID")
    fund_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, comment="基金ID")
    principal: Mapped[int] = mapped_column(BigInteger, comment="本金(金币)")
    current_value: Mapped[int] = mapped_column(BigInteger, comment="当前市值(金币)")
    accumulated_profit: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0', comment="累计盈亏(金币)")
    buy_date: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="购买时间")
    last_settlement: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="最后结算时间")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='1', comment="是否持有中")

    # 索引
    __table_args__ = (
        {'comment': '理财持仓表'},
    )
