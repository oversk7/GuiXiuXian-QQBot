"""黑天鹅事件服务"""
import random
import yaml
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy import select, and_
from ..models.stock import Stock, StockEvent, StockType

logger = logging.getLogger(__name__)


class BlackSwanService:
    """黑天鹅事件服务"""

    def __init__(self, stock_repo, stock_event_repo):
        self.stock_repo = stock_repo
        self.stock_event_repo = stock_event_repo
        self._config = None

    def _load_config(self) -> Dict:
        """加载黑天鹅事件配置"""
        if self._config is None:
            config_path = Path(__file__).parent.parent / "data" / "black_swan_events.yaml"
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._config = yaml.safe_load(f)
            except Exception as e:
                logger.error(f"加载黑天鹅事件配置失败: {e}")
                self._config = {'events': [], 'settings': {'enabled': False}}
        return self._config

    async def check_and_trigger_events(self) -> List[Dict]:
        """检查并触发黑天鹅事件"""
        config = self._load_config()

        if not config['settings'].get('enabled', False):
            logger.info("⚠️ 黑天鹅事件系统已禁用")
            return []

        logger.info("🦢 开始检查黑天鹅事件...")
        logger.info(f"   - 全局概率倍率: {config['settings'].get('global_probability_multiplier', 1.0)}x")
        logger.info(f"   - 冷却期: {config['settings'].get('cooldown_days', 7)}天")
        logger.info(f"   - 可用事件数量: {len(config['events'])}个")

        triggered_events = []
        global_multiplier = config['settings'].get('global_probability_multiplier', 1.0)
        cooldown_days = config['settings'].get('cooldown_days', 7)

        for event_config in config['events']:
            # 计算实际概率
            actual_probability = event_config['probability'] * global_multiplier
            logger.debug(f"   检查事件: {event_config['name']} (概率: {actual_probability:.2%})")

            # 检查是否应该触发
            if await self._should_trigger_event(event_config, global_multiplier, cooldown_days):
                triggered_event = await self._trigger_event(event_config)
                if triggered_event:
                    triggered_events.append(triggered_event)

        logger.info(f"🦢 黑天鹅事件检查完成: 触发了 {len(triggered_events)} 个事件")
        return triggered_events

    async def _should_trigger_event(
        self,
        event_config: Dict,
        global_multiplier: float,
        cooldown_days: int
    ) -> bool:
        """判断是否应该触发事件"""
        # 计算实际触发概率
        probability = event_config['probability'] * global_multiplier
        roll = random.random()

        logger.debug(
            f"   🎲 概率判定: {event_config['name']} - "
            f"需要 {probability:.2%}, 随出 {roll:.2%}"
        )

        # 随机判断
        if roll > probability:
            logger.debug(f"   ❌ {event_config['name']} 未通过概率判定")
            return False

        # 检查冷却期（同一类型气运的事件不能在冷却期内重复触发）
        affected_type = event_config['affected_type']
        cooldown_end = datetime.now() - timedelta(days=cooldown_days)

        session = self.stock_event_repo._session  # 使用_session而不是session

        # 查询该类型气运最近的事件
        stmt = (
            select(StockEvent)
            .join(Stock, StockEvent.affected_stock_id == Stock.id)
            .where(
                and_(
                    Stock.stock_type == affected_type,
                    StockEvent.trigger_date > cooldown_end
                )
            )
            .order_by(StockEvent.trigger_date.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        recent_event = result.scalar_one_or_none()

        if recent_event:
            logger.info(f"事件 {event_config['event_id']} 处于冷却期，跳过触发")
            return False

        return True

    async def _trigger_event(self, event_config: Dict) -> Optional[Dict]:
        """触发事件"""
        try:
            # 查找受影响类型的所有活跃气运
            affected_type = event_config['affected_type']
            session = self.stock_repo._session  # 使用_session而不是session

            # 先查询所有活跃气运,用于调试
            all_stocks_stmt = select(Stock).where(Stock.is_active == True)
            all_stocks_result = await session.execute(all_stocks_stmt)
            all_stocks = all_stocks_result.scalars().all()

            logger.debug(f"   🔍 查找类型 {affected_type} 的气运")
            logger.debug(f"   📊 当前活跃气运类型: {[s.stock_type for s in all_stocks]}")

            stmt = (
                select(Stock)
                .where(
                    and_(
                        Stock.stock_type == affected_type,
                        Stock.is_active == True
                    )
                )
            )
            result = await session.execute(stmt)
            affected_stocks = result.scalars().all()

            if not affected_stocks:
                logger.warning(f"未找到类型为 {affected_type} 的活跃气运")
                logger.warning(f"可用的气运类型: {set(s.stock_type for s in all_stocks)}")
                return None

            # 随机选择一只气运作为主要受影响对象
            target_stock = random.choice(affected_stocks)

            # 应用价格影响
            old_price = target_stock.current_price
            price_impact = event_config['price_impact']
            target_stock.current_price = int(target_stock.current_price * (1 + price_impact))

            # 确保价格不低于基础价格的30%
            min_price = int(target_stock.base_price * 0.3)
            target_stock.current_price = max(target_stock.current_price, min_price)

            # 应用健康度影响
            health_impact = event_config['health_impact']
            target_stock.health = max(0, target_stock.health + health_impact)

            # 如果健康度归零，标记为退市
            if target_stock.health <= 0:
                target_stock.is_active = False
                target_stock.delisted_at = datetime.now()
                target_stock.delist_reason = f"黑天鹅事件: {event_config['name']}"

            # 记录事件到数据库
            stock_event = StockEvent(
                event_id=event_config['event_id'],
                event_name=event_config['name'],
                description=event_config['description'],
                affected_stock_id=target_stock.id,
                price_impact=price_impact,
                health_impact=health_impact,
                trigger_date=datetime.now(),
                duration_days=event_config['duration_days'],
                is_active=True
            )
            session.add(stock_event)

            logger.info(
                f"⚡ 触发黑天鹅事件: {event_config['name']} "
                f"- {target_stock.name} 价格 {old_price} → {target_stock.current_price} "
                f"(跌幅 {abs(price_impact)*100:.0f}%), "
                f"健康度 -{abs(health_impact)}"
            )

            # 返回事件信息（用于通知）
            return {
                'event_id': event_config['event_id'],
                'event_name': event_config['name'],
                'stock_id': target_stock.id,
                'stock_name': target_stock.name,
                'stock_symbol': target_stock.symbol,
                'old_price': old_price,
                'new_price': target_stock.current_price,
                'price_impact': price_impact,
                'health_impact': health_impact,
                'announcement': event_config['announcement'],
                'is_delisted': target_stock.health <= 0
            }

        except Exception as e:
            logger.error(f"触发事件 {event_config['event_id']} 失败: {e}", exc_info=True)
            return None

    async def get_recent_events(self, limit: int = 10) -> List[Dict]:
        """获取最近的黑天鹅事件"""
        session = self.stock_event_repo._session  # 使用_session而不是session

        stmt = (
            select(StockEvent, Stock)
            .join(Stock, StockEvent.affected_stock_id == Stock.id)
            .order_by(StockEvent.trigger_date.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        rows = result.all()

        events = []
        for stock_event, stock in rows:
            events.append({
                'event_id': stock_event.event_id,
                'event_name': stock_event.event_name,
                'description': stock_event.description,
                'stock_name': stock.name,
                'stock_symbol': stock.symbol,
                'price_impact': stock_event.price_impact,
                'health_impact': stock_event.health_impact,
                'trigger_date': stock_event.trigger_date,
                'is_active': stock_event.is_active
            })

        return events
