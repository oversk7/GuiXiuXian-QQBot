from sqlalchemy import Integer, BigInteger, String, DateTime, Date, Float, func, JSON
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, date
from .db import Base
from typing import Dict, Any


class MarketState(Base):
    """市场状态表 - 存储每个市场的动态数据"""
    __tablename__ = "market_state"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market_id: Mapped[str] = mapped_column(String(32), index=True, comment="市场ID")
    item_id: Mapped[str] = mapped_column(String(32), index=True, comment="商品ID")
    
    # 库存相关
    current_stock: Mapped[int] = mapped_column(Integer, default=100, comment="当前库存")
    max_stock: Mapped[int] = mapped_column(Integer, default=100, comment="最大库存")
    daily_sold: Mapped[int] = mapped_column(Integer, default=0, comment="今日已售出数量")
    daily_bought: Mapped[int] = mapped_column(Integer, default=0, comment="今日已收购数量")
    
    # 价格影响因子
    demand_factor: Mapped[float] = mapped_column(Float, default=1.0, comment="需求因子(>1推高价格,<1降低价格)")
    supply_factor: Mapped[float] = mapped_column(Float, default=1.0, comment="供给因子(>1降低价格,<1推高价格)")
    
    # 时间相关
    last_refresh_date: Mapped[date] = mapped_column(Date, default=date.today, comment="上次刷新日期")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    
    # 扩展数据（JSON格式存储额外信息）
    extra_data: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, comment="扩展数据")
    
    @classmethod
    async def get_or_create(cls, session, market_id: str, item_id: str) -> 'MarketState':
        """获取或创建市场状态记录"""
        from sqlalchemy import select
        
        # 先尝试获取现有记录
        result = await session.execute(
            select(cls).where(
                cls.market_id == market_id,
                cls.item_id == item_id
            )
        )
        market_state = result.scalar_one_or_none()
        
        if market_state is None:
            # 创建新记录
            market_state = cls(
                market_id=market_id,
                item_id=item_id,
                current_stock=100,  # 默认库存
                max_stock=100,
                daily_sold=0,
                daily_bought=0,
                demand_factor=1.0,
                supply_factor=1.0,
                last_refresh_date=date.today(),
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            session.add(market_state)
            await session.flush()
        
        return market_state
    
    async def check_daily_refresh(self, session):
        """检查是否需要每日刷新"""
        today = date.today()

        # 处理 last_refresh_date 可能是 datetime 或 date 类型的情况
        last_date = self.last_refresh_date
        if isinstance(last_date, datetime):
            last_date = last_date.date()

        if last_date < today:
            await self.daily_refresh(session)
    
    async def daily_refresh(self, session):
        """每日刷新市场状态"""
        today = date.today()
        
        # 重置每日统计
        self.daily_sold = 0
        self.daily_bought = 0
        
        # 库存恢复（部分恢复，不是完全重置）
        stock_recovery = min(20, self.max_stock - self.current_stock)  # 每日恢复20个或补满
        self.current_stock = min(self.max_stock, self.current_stock + stock_recovery)
        
        # 价格因子衰减（逐渐回归1.0）
        self.demand_factor = self.demand_factor * 0.8 + 1.0 * 0.2  # 20%回归正常
        self.supply_factor = self.supply_factor * 0.8 + 1.0 * 0.2
        
        # 更新刷新日期
        self.last_refresh_date = today
        self.updated_at = datetime.now()
        
        session.add(self)
    
    def apply_purchase(self, quantity: int):
        """应用购买操作对市场状态的影响"""
        # 减少库存
        self.current_stock = max(0, self.current_stock - quantity)

        # 增加今日售出统计
        self.daily_sold += quantity

        # 推高需求因子（购买越多，需求越高，价格越高）
        # 降低影响强度，避免价格波动过大
        demand_increase = quantity * 0.005  # 每购买1个商品，需求因子增加0.005
        self.demand_factor = min(1.3, self.demand_factor + demand_increase)  # 最高1.3倍

        # 降低供给因子（库存减少，供给紧张，价格上涨）
        if self.current_stock < self.max_stock * 0.3:  # 库存低于30%时
            supply_decrease = quantity * 0.003  # 降低影响
            self.supply_factor = max(0.8, self.supply_factor - supply_decrease)  # 最低0.8倍

        self.updated_at = datetime.now()
    
    def apply_sale(self, quantity: int):
        """应用出售操作对市场状态的影响"""
        # 增加库存（但不超过最大值）
        self.current_stock = min(self.max_stock, self.current_stock + quantity)

        # 增加今日收购统计
        self.daily_bought += quantity

        # 降低需求因子（出售越多，市场饱和，价格下降）
        demand_decrease = quantity * 0.004  # 每出售1个商品，需求因子减少0.004
        self.demand_factor = max(0.8, self.demand_factor - demand_decrease)  # 最低0.8倍

        # 提高供给因子（库存增加，供给充足，价格下降）
        if self.current_stock > self.max_stock * 0.7:  # 库存高于70%时
            supply_increase = quantity * 0.002  # 降低影响
            self.supply_factor = min(1.2, self.supply_factor + supply_increase)  # 最高1.2倍

        self.updated_at = datetime.now()
    
    def get_price_multiplier(self) -> float:
        """获取价格倍数（基于供需因子）"""
        # 综合需求和供给因子计算最终价格倍数
        # 需求高 + 供给低 = 价格高
        # 需求低 + 供给高 = 价格低
        multiplier = (self.demand_factor / self.supply_factor)

        # 限制在更保守的范围内 (0.8 - 1.25)，减少极端价格波动
        return max(0.8, min(1.25, multiplier))
    
    def can_purchase(self, quantity: int) -> bool:
        """检查是否可以购买指定数量"""
        return self.current_stock >= quantity
    
    def get_stock_status(self) -> str:
        """获取库存状态描述"""
        stock_ratio = self.current_stock / self.max_stock
        if stock_ratio >= 0.8:
            return "充足"
        elif stock_ratio >= 0.5:
            return "一般"
        elif stock_ratio >= 0.2:
            return "紧张"
        else:
            return "稀缺"
