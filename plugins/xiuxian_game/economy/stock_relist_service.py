"""股票重新上市服务

负责处理退市股票的重新上市逻辑:
1. 检查退市超过3天的股票
2. 重置股票状态
3. 恢复股票价格到基础价格
4. 确保至少有12只活跃股票
"""

import logging
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.stock import Stock, StockType
from ..models.db import safe_session

logger = logging.getLogger(__name__)


class StockRelistService:
    """股票重新上市服务"""

    # 最小活跃股票数量
    MIN_ACTIVE_STOCKS = 12

    # 退市后重新上市等待天数
    RELIST_DAYS = 3

    @classmethod
    async def check_and_relist_stocks(cls) -> dict:
        """检查并重新上市符合条件的股票

        Returns:
            dict: 重新上市统计信息
        """
        stats = {
            "relisted_count": 0,
            "total_active": 0,
            "relisted_symbols": []
        }

        try:
            async with safe_session() as session:
                # 1. 检查活跃股票数量
                active_stmt = select(Stock).where(Stock.is_active == True)
                active_stocks = (await session.execute(active_stmt)).scalars().all()
                stats["total_active"] = len(active_stocks)

                # 2. 如果活跃股票数量不足，查找可重新上市的股票
                if len(active_stocks) < cls.MIN_ACTIVE_STOCKS:
                    needed = cls.MIN_ACTIVE_STOCKS - len(active_stocks)

                    # 3. 查找退市超过3天的股票
                    relist_threshold = datetime.now() - timedelta(days=cls.RELIST_DAYS)
                    delisted_stmt = select(Stock).where(
                        Stock.is_active == False,
                        Stock.delisted_at < relist_threshold
                    ).order_by(Stock.delisted_at.asc()).limit(needed)

                    delisted_stocks = (await session.execute(delisted_stmt)).scalars().all()

                    # 4. 重新上市这些股票
                    for stock in delisted_stocks:
                        cls._relist_stock(stock)
                        stats["relisted_count"] += 1
                        stats["relisted_symbols"].append(stock.symbol)
                        logger.info(f"📈 股票重新上市: {stock.symbol} - {stock.name}")

                    await session.commit()

                return stats

        except Exception as e:
            logger.error(f"❌ 检查重新上市股票失败: {e}", exc_info=True)
            return stats

    @classmethod
    def _relist_stock(cls, stock: Stock) -> None:
        """重新上市单只股票

        Args:
            stock: 要重新上市的股票对象
        """
        # 重置所有状态
        stock.is_active = True
        stock.health = 100
        stock.current_price = stock.base_price
        stock.delisted_at = None
        stock.delist_reason = None

        logger.debug(f"重新上市股票: {stock.symbol} - {stock.name}")

    @classmethod
    async def ensure_minimum_stocks(cls) -> dict:
        """确保系统中有最少12只活跃股票

        如果现有股票+可重新上市股票不足12只，则创建新股票

        Returns:
            dict: 补充统计信息
        """
        stats = {
            "created_count": 0,
            "total_active": 0,
            "created_symbols": []
        }

        try:
            async with safe_session() as session:
                # 1. 统计当前活跃股票和可重新上市股票
                active_stmt = select(Stock).where(Stock.is_active == True)
                active_stocks = (await session.execute(active_stmt)).scalars().all()

                relist_threshold = datetime.now() - timedelta(days=cls.RELIST_DAYS)
                delisted_stmt = select(Stock).where(
                    Stock.is_active == False,
                    Stock.delisted_at < relist_threshold
                )
                delisted_stocks = (await session.execute(delisted_stmt)).scalars().all()

                available_count = len(active_stocks) + len(delisted_stocks)

                # 2. 如果仍然不足，创建新股票
                if available_count < cls.MIN_ACTIVE_STOCKS:
                    needed = cls.MIN_ACTIVE_STOCKS - available_count

                    for i in range(needed):
                        new_stock = cls._create_new_stock(len(active_stocks) + i + 1)
                        session.add(new_stock)
                        stats["created_count"] += 1
                        stats["created_symbols"].append(new_stock.symbol)
                        logger.info(f"🆕 创建新股票: {new_stock.symbol} - {new_stock.name}")

                    await session.commit()

                stats["total_active"] = len(active_stocks)
                return stats

        except Exception as e:
            logger.error(f"❌ 确保最小股票数量失败: {e}", exc_info=True)
            return stats

    @classmethod
    def _create_new_stock(cls, index: int) -> Stock:
        """创建新股票

        Args:
            index: 股票索引号

        Returns:
            Stock: 新创建的股票对象
        """
        # 定义股票类型模板
        stock_templates = [
            {
                "type": StockType.TECH,
                "prefix": "FA",
                "names": ["炼器气运", "法宝气运", "天工符箓"],
                "base_prices": [1000, 1200, 1500],
                "volatilities": [0.08, 0.10, 0.12]
            },
            {
                "type": StockType.FINANCE,
                "prefix": "JR",
                "names": ["钱庄气运", "汇通气运"],
                "base_prices": [800, 1000],
                "volatilities": [0.04, 0.05]
            },
            {
                "type": StockType.ENERGY,
                "prefix": "LQ",
                "names": ["灵石气运", "灵脉气运"],
                "base_prices": [900, 1100],
                "volatilities": [0.06, 0.07]
            },
            {
                "type": StockType.CONSUMER,
                "prefix": "DY",
                "names": ["丹药气运", "符材气运"],
                "base_prices": [700, 800],
                "volatilities": [0.03, 0.04]
            },
            {
                "type": StockType.HEALTHCARE,
                "prefix": "YI",
                "names": ["医道气运"],
                "base_prices": [850],
                "volatilities": [0.05]
            },
            {
                "type": StockType.MATERIALS,
                "prefix": "CL",
                "names": ["材料气运", "矿脉气运"],
                "base_prices": [950, 1050],
                "volatilities": [0.07, 0.08]
            }
        ]

        # 简单的循环选择模板
        template = stock_templates[index % len(stock_templates)]
        template_index = (index // len(stock_templates)) % len(template["names"])

        # 生成股票代码
        symbol = f"{template['prefix']}{index:03d}"

        # 创建股票
        stock = Stock(
            symbol=symbol,
            name=template["names"][template_index],
            stock_type=template["type"],
            base_price=template["base_prices"][template_index],
            current_price=template["base_prices"][template_index],
            volatility=template["volatilities"][template_index],
            health=100,
            health_decay_rate=1.0,
            is_active=True
        )

        return stock

    @classmethod
    async def reset_all_delisted_stocks(cls) -> dict:
        """重置所有已退市股票（管理员功能）

        Returns:
            dict: 重置统计信息
        """
        stats = {
            "reset_count": 0,
            "total_active": 0,
            "reset_symbols": []
        }

        try:
            async with safe_session() as session:
                # 1. 查找所有已退市股票
                delisted_stmt = select(Stock).where(Stock.is_active == False)
                delisted_stocks = (await session.execute(delisted_stmt)).scalars().all()

                # 2. 重新上市所有退市股票
                for stock in delisted_stocks:
                    cls._relist_stock(stock)
                    stats["reset_count"] += 1
                    stats["reset_symbols"].append(stock.symbol)
                    logger.info(f"🔄 重置退市股票: {stock.symbol} - {stock.name}")

                await session.commit()

                # 3. 统计活跃股票数量
                active_stmt = select(Stock).where(Stock.is_active == True)
                active_stocks = (await session.execute(active_stmt)).scalars().all()
                stats["total_active"] = len(active_stocks)

                return stats

        except Exception as e:
            logger.error(f"❌ 重置退市股票失败: {e}", exc_info=True)
            return stats
