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

    # 不同股票类型的基础波动率
    TYPE_VOLATILITY = {
        StockType.TECH: 0.08,       # 科技股波动较大
        StockType.FINANCE: 0.04,    # 金融股相对稳定
        StockType.ENERGY: 0.06,     # 能源股中等波动
        StockType.CONSUMER: 0.03,   # 消费股较稳定
        StockType.HEALTHCARE: 0.05, # 医疗股中等波动
        StockType.MATERIALS: 0.07,  # 材料股波动较大
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

            # 确定当前小时的市场情绪（可复现的情绪日程表）
            dt_now = datetime.now().replace(minute=0, second=0, microsecond=0)
            market_sentiment = cls.get_sentiment_for_hour(dt_now)

            for stock in stocks:
                # 趋势因子衰减并收敛到1.0，削弱交易长期影响
                stock.trend_factor = 1.0 + (stock.trend_factor - 1.0) * 0.9
                stock.trend_factor = max(0.95, min(1.05, stock.trend_factor))

                old_price = stock.current_price
                new_price = await cls._calculate_new_price(session, stock, market_sentiment, dt_now)

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
    async def _calculate_new_price(cls, session: AsyncSession, stock: Stock, market_sentiment: float, dt: datetime) -> int:
        """计算股票新价格（每支股票每小时可复现）"""
        current_price = stock.current_price

        # 1. 基础波动率（根据股票类型）
        base_volatility = cls.TYPE_VOLATILITY.get(stock.stock_type, 0.05)

        # 2. 个股波动率
        individual_volatility = stock.volatility

        # 3. 综合波动率
        total_volatility = (base_volatility + individual_volatility) / 2

        # 4. 随机波动因子（正态分布）- 使用确定性种子，保证与私享预测一致
        seed = f"{stock.symbol}-{dt.strftime('%Y%m%d%H')}"
        rng = random.Random(seed)
        random_factor = rng.gauss(0, total_volatility)

        # 5. 趋势因子影响
        trend_influence = (stock.trend_factor - 1.0) * 0.01

        # 6. 市场情绪影响
        sentiment_influence = (market_sentiment - 1.0)

        # 7. 历史价格回归因子（防止价格偏离基础价格太远）
        regression_factor = cls._calculate_regression_factor(stock)

        # 8. 综合计算价格变化率
        total_change_rate = (
            random_factor +           # 随机波动
            trend_influence +         # 个股趋势
            sentiment_influence +     # 市场情绪
            regression_factor         # 价格回归
        )

        # 9. 限制单次变化幅度（±20%）
        total_change_rate = max(-0.20, min(0.20, total_change_rate))

        # 10. 计算新价格
        new_price = int(current_price * (1 + total_change_rate))

        # 11. 确保价格不低于基础价格的20%
        min_price = max(1, int(stock.base_price * 0.2))
        new_price = max(min_price, new_price)

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
    def get_sentiment_for_hour(cls, dt: datetime) -> float:
        """基于日期与小时生成可复现的市场情绪值
        - 使用确定性种子，保证同一小时内引擎与预测一致
        - 概率分布与原先一致：熊30% / 中性40% / 牛30%
        """
        seed = dt.strftime("%Y%m%d%H") + "_mkt"
        rng = random.Random(seed)
        r = rng.random()
        if r < 0.3:
            return cls.MARKET_SENTIMENT["bear"]
        elif r < 0.7:
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
        regression_strength = 0.02  # 2%的回归强度

        # 回归因子（负值表示向基础价格回归）
        regression_factor = -deviation * regression_strength

        return regression_factor

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

        # 计算交易量对价格的影响（显著降低系数，弱化交易扰动）
        volume_impact = transaction_volume / stock.circulating_shares if stock.circulating_shares else 0

        # 买入推高价格，卖出压低价格（影响系数从1%降至0.1%）
        coef = 0.001
        if transaction_type == "BUY":
            price_impact = volume_impact * coef
        else:  # SELL
            price_impact = -volume_impact * coef

        # 更新趋势因子并收敛到更窄范围
        stock.trend_factor += price_impact
        stock.trend_factor = max(0.95, min(1.05, stock.trend_factor))  # 限制在0.95-1.05之间

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
