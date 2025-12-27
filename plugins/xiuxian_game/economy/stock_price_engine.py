"""股票价格波动引擎

实现股票价格的动态变化算法，包括：
1. 基础价格波动
2. 随机市场因素
3. 交易量影响
4. 市场情绪
5. 定时价格更新
"""

import random
import math
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..models.stock import Stock, StockPriceHistory, StockType
from ..models.db import safe_session


class StockPriceEngine:
    """股票价格引擎"""
    
    # 不同股票类型的基础波动率（反套利设计值）
    TYPE_VOLATILITY = {
        StockType.TECH: 0.08,       # 科技股波动率
        StockType.FINANCE: 0.04,    # 金融股波动率
        StockType.ENERGY: 0.06,     # 能源股波动率
        StockType.CONSUMER: 0.03,   # 消费股波动率
        StockType.HEALTHCARE: 0.05, # 医疗股波动率
        StockType.MATERIALS: 0.07,  # 材料股波动率
    }
    
    # 市场情绪因子（全局影响）
    MARKET_SENTIMENT = {
        "bull": 1.02,      # 牛市：价格倾向上涨
        "bear": 0.98,      # 熊市：价格倾向下跌
        "neutral": 1.0,    # 中性市场
    }
    
    @classmethod
    async def update_all_prices(cls) -> Dict[str, Dict]:
        """更新所有股票价格"""
        results = {}
        
        async with safe_session() as session:
            # 获取所有活跃股票
            stmt = select(Stock).where(Stock.is_active == True)
            stocks = (await session.execute(stmt)).scalars().all()
            
            # 确定当前市场情绪
            market_sentiment = cls._get_market_sentiment()
            
            for stock in stocks:
                old_price = stock.current_price
                new_price = await cls._calculate_new_price(session, stock, market_sentiment)
                
                # 更新股票价格
                stock.current_price = new_price
                stock.updated_at = datetime.now()
                
                # 记录价格历史
                change_amount = new_price - old_price
                change_rate = (change_amount / old_price) * 100 if old_price > 0 else 0
                
                # 生成虚拟交易量，让市场看起来更活跃
                virtual_volume = random.randint(100, 1000)

                price_history = StockPriceHistory(
                    stock_id=stock.id,
                    price=new_price,
                    change_amount=change_amount,
                    change_rate=change_rate,
                    volume=virtual_volume  # 使用虚拟交易量
                )
                session.add(price_history)
                
                results[stock.symbol] = {
                    "old_price": old_price,
                    "new_price": new_price,
                    "change_amount": change_amount,
                    "change_rate": change_rate
                }
            
            await session.commit()
        
        return results
    
    @classmethod
    async def _calculate_new_price(cls, session: AsyncSession, stock: Stock, market_sentiment: float) -> int:
        """计算股票新价格（无套利版本）

        核心改动：
        1. 移除正向趋势因子（trend_influence）
        2. 添加健康度更新逻辑
        3. 检查退市条件
        """
        current_price = stock.current_price

        # 1. 基础波动率（根据股票类型）
        base_volatility = cls.TYPE_VOLATILITY.get(stock.stock_type, 0.05)

        # 2. 个股波动率
        individual_volatility = stock.volatility

        # 3. 综合波动率
        total_volatility = (base_volatility + individual_volatility) / 2

        # 4. 随机波动因子（正态分布，期望值=0）
        random_factor = random.gauss(0, total_volatility)

        # 5. 市场情绪影响（随机，期望=0）
        sentiment = random.choice([-0.02, 0, 0.02])  # -2%, 0%, +2%

        # 6. 历史价格回归因子（防止价格偏离基础价格太远）
        regression_factor = cls._calculate_regression_factor(stock)

        # 7. 综合计算价格变化率（移除正向趋势！）
        total_change_rate = (
            random_factor +           # 随机波动（期望=0）
            sentiment +               # 市场情绪（期望=0）
            regression_factor         # 价格回归
        )

        # 8. 限制单次变化幅度（±15%）
        total_change_rate = max(-0.15, min(0.15, total_change_rate))

        # 9. 计算新价格
        new_price = int(current_price * (1 + total_change_rate))

        # 10. 确保价格不低于基础价格的30%
        min_price = max(1, int(stock.base_price * 0.3))
        new_price = max(min_price, new_price)

        # 11. 更新健康度
        cls._update_health(stock, total_change_rate)

        # 12. 检查是否需要退市
        if stock.health <= 0:
            await cls._delist_stock(session, stock)
            return 0

        return new_price
    
    @classmethod
    def _get_market_sentiment(cls) -> float:
        """获取当前市场情绪"""
        # 简单的随机市场情绪，可以后续改为更复杂的算法
        rand = random.random()
        if rand < 0.3:
            return cls.MARKET_SENTIMENT["bear"]
        elif rand < 0.7:
            return cls.MARKET_SENTIMENT["neutral"]
        else:
            return cls.MARKET_SENTIMENT["bull"]
    
    @classmethod
    def _calculate_regression_factor(cls, stock: Stock) -> float:
        """计算价格回归因子"""
        current_price = stock.current_price
        base_price = stock.base_price

        # 计算当前价格相对于基础价格的偏离程度
        deviation = (current_price - base_price) / base_price

        # 回归强度（偏离越大，回归力度越强）
        regression_strength = 0.01  # 1%的弱回归强度

        # 回归因子（负值表示向基础价格回归）
        regression_factor = -deviation * regression_strength

        return regression_factor

    @classmethod
    def _update_health(cls, stock: Stock, change_rate: float) -> None:
        """更新股票健康度（反套利机制）

        规则：
        1. 价格下跌时损耗健康度（跌1% = -1点健康）
        2. 价格上涨时恢复健康度（涨1% = +0.5点健康，恢复速度是损耗速度的一半）
        3. 健康度衰减速度由 health_decay_rate 控制
        """
        if change_rate < 0:
            # 下跌：损耗健康度
            health_loss = abs(change_rate) * 100 * stock.health_decay_rate
            stock.health -= int(health_loss)
        else:
            # 上涨：恢复健康度（恢复速度是损耗速度的一半）
            health_gain = change_rate * 50 * stock.health_decay_rate
            stock.health += int(health_gain)

        # 限制健康度范围 [0, 100]
        stock.health = max(0, min(100, stock.health))

    @classmethod
    async def _delist_stock(cls, session: AsyncSession, stock: Stock) -> None:
        """股票退市处理

        退市流程：
        1. 标记股票为已退市
        2. 立即清空所有玩家持仓（玩家损失所有投资）
        3. 记录退市信息

        注意：此方法在update_all_prices的session上下文中调用
        不需要单独commit,由外层session统一管理事务
        """
        from ..models.stock import StockHolding
        from ..infrastructure.repositories.stock_holding_repository import StockHoldingRepository

        # 标记为已退市
        stock.is_active = False
        stock.delisted_at = datetime.now()
        stock.delist_reason = "健康度归零"

        # 立即清空所有玩家持仓
        stock_holding_repo = StockHoldingRepository(session)
        holdings = await stock_holding_repo.get_all_holdings_by_stock(stock.id)

        if holdings:
            for holding in holdings:
                # 删除持仓记录，玩家损失所有投资
                await stock_holding_repo.delete_holding(holding)

            # 注意：不在这里commit，由外层update_all_prices统一管理事务

    @classmethod
    async def get_price_trend(cls, session: AsyncSession, stock_id: int, days: int = 7) -> List[Dict]:
        """获取股票价格趋势"""
        # 获取最近N天的价格历史
        start_date = datetime.now() - timedelta(days=days)
        stmt = select(StockPriceHistory).where(
            StockPriceHistory.stock_id == stock_id,
            StockPriceHistory.recorded_at >= start_date
        ).order_by(StockPriceHistory.recorded_at.desc()).limit(days * 24)  # 假设每小时更新一次
        
        price_history = (await session.execute(stmt)).scalars().all()
        
        return [
            {
                "price": record.price,
                "change_rate": record.change_rate,
                "time": record.recorded_at
            }
            for record in reversed(price_history)
        ]
    
    @classmethod
    async def simulate_market_impact(cls, session: AsyncSession, stock_id: int, 
                                   transaction_volume: int, transaction_type: str) -> None:
        """模拟交易对市场的影响"""
        stock = await session.get(Stock, stock_id)
        if not stock:
            return
        
        # 计算交易量对价格的影响
        volume_impact = transaction_volume / stock.circulating_shares
        
        # 买入推高价格，卖出压低价格
        if transaction_type == "BUY":
            price_impact = volume_impact * 0.01  # 1%的影响系数
        else:  # SELL
            price_impact = -volume_impact * 0.01
        
        # 更新趋势因子
        stock.trend_factor += price_impact
        stock.trend_factor = max(0.8, min(1.2, stock.trend_factor))  # 限制在0.8-1.2之间
        
        session.add(stock)


class StockMarketScheduler:
    """股票市场调度器"""
    
    @classmethod
    async def daily_market_update(cls):
        """每日市场更新"""
        # 更新所有股票价格
        results = await StockPriceEngine.update_all_prices()
        
        # 可以在这里添加其他每日更新逻辑
        # 比如：分红、股票拆分、新股上市等
        
        return results
    
    @classmethod
    async def hourly_market_update(cls):
        """每小时市场更新"""
        # 小幅度价格调整
        results = await StockPriceEngine.update_all_prices()
        return results
