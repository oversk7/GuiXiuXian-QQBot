"""股票交易核心服务 - DI重构版本

实现股票买卖的核心逻辑，包括：
1. 买入股票
2. 卖出股票
3. 持仓管理
4. 交易记录
5. 手续费计算
6. 被动价格更新（玩家查看时触发）

重构说明：
- 所有@classmethod改为实例方法
- 通过构造函数注入Repository依赖
- 不再接收session参数，改为使用注入的仓储
- 保持业务逻辑完全一致
"""

from typing import Tuple, List, Dict
from datetime import datetime, timedelta

from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.stock_repository import StockRepository
from ..infrastructure.repositories.stock_holding_repository import StockHoldingRepository
from ..infrastructure.repositories.stock_transaction_repository import StockTransactionRepository
from ..infrastructure.repositories.bank_account_repository import BankAccountRepository
from ..models.stock import TransactionType
from .stock_price_engine import StockPriceEngine


class StockService:
    """股票交易服务 - DI版本

    通过构造函数注入所需的Repository，不再使用静态方法
    """

    # 手续费配置
    COMMISSION_RATE = 0.03
    MIN_COMMISSION = 1
    MAX_COMMISSION = 1000000

    # 持仓限制配置
    MAX_SHARES_PER_STOCK = 1000000  # 每种股票最多持有100万份

    # 价格刷新配置
    PRICE_UPDATE_INTERVAL = timedelta(hours=1)  # 被动触发更新间隔：1小时

    def __init__(
        self,
        player_repo: PlayerRepository,
        stock_repo: StockRepository,
        stock_holding_repo: StockHoldingRepository,
        stock_transaction_repo: StockTransactionRepository,
        bank_account_repo: BankAccountRepository
    ):
        """
        初始化股票服务

        Args:
            player_repo: 玩家仓储
            stock_repo: 股票仓储
            stock_holding_repo: 持仓仓储
            stock_transaction_repo: 交易记录仓储
            bank_account_repo: 银行账户仓储
        """
        self._player_repo = player_repo
        self._stock_repo = stock_repo
        self._stock_holding_repo = stock_holding_repo
        self._stock_transaction_repo = stock_transaction_repo
        self._bank_account_repo = bank_account_repo

    async def check_and_update_prices(self, force_update: bool = False) -> bool:
        """检查并更新股票价格（被动触发）

        只有满足以下条件之一才会执行更新：
        1. force_update=True（管理员强制更新）
        2. 距离上次更新时间 >= PRICE_UPDATE_INTERVAL（1小时）

        Args:
            force_update: 是否强制更新，忽略时间间隔

        Returns:
            bool: 是否执行了价格更新
        """
        # 获取最近更新的股票，检查是否需要更新
        latest_stock = await self._stock_repo.get_latest_updated_stock()

        if not latest_stock:
            return False

        now = datetime.now()
        time_since_update = now - latest_stock.updated_at

        # 判断是否需要更新
        should_update = (
            force_update or
            time_since_update >= self.PRICE_UPDATE_INTERVAL
        )

        if should_update:
            # 执行价格更新
            await StockPriceEngine.update_all_prices()
            return True

        return False

    async def buy_stock(self, player_id: str, stock_symbol: str, shares: int,
                       use_bank: bool = False) -> Tuple[bool, str]:
        """买入股票

        Args:
            player_id: 玩家ID
            stock_symbol: 股票代码
            shares: 购买数量
            use_bank: 是否使用银行账户
        """
        # 获取玩家信息
        player = await self._player_repo.get_by_id(player_id)
        if not player:
            return False, "玩家不存在"

        # 获取股票信息
        stock = await self._stock_repo.get_by_symbol(stock_symbol)
        if not stock or not stock.is_active:
            return False, f"气运项目 {stock_symbol} 不存在或已停止投资"

        # 验证交易数量
        if shares <= 0:
            return False, "交易数量必须大于0"

        # 检查持仓限制
        existing_holding = await self._stock_holding_repo.get_by_player_and_stock(
            player_id, stock.id
        )
        current_shares = existing_holding.shares if existing_holding else 0

        # 检查买入后是否超过限制
        if current_shares + shares > self.MAX_SHARES_PER_STOCK:
            remaining = self.MAX_SHARES_PER_STOCK - current_shares
            if remaining <= 0:
                return False, f"已达到持仓上限，每种气运最多持有 {self.MAX_SHARES_PER_STOCK:,} 份"
            else:
                return False, f"超过持仓上限，当前持有 {current_shares:,} 份，最多还能买入 {remaining:,} 份"

        # 计算交易金额和手续费
        unit_price = stock.current_price
        total_amount = unit_price * shares
        commission = self._calculate_commission(total_amount)
        total_cost = total_amount + commission

        # 检查资金并扣款
        if use_bank:
            # 使用银行账户资金
            has_balance = await self._bank_account_repo.has_sufficient_balance(
                player_id, total_cost
            )
            if not has_balance:
                return False, f"银行账户余额不足，需要 {total_cost} 金币"

            # 扣除银行资金
            success = await self._bank_account_repo.withdraw(player_id, total_cost)
            if not success:
                return False, "扣款失败"
        else:
            # 使用现金
            if player.gold < total_cost:
                return False, f"金币不足，需要 {total_cost} 金币"

            # 扣除现金
            player.gold -= total_cost
            await self._player_repo.update(player)

        # 更新持仓
        await self._update_holding_buy(player_id, stock.id, shares, unit_price, total_amount)

        # 记录交易
        await self._stock_transaction_repo.create_transaction(
            player_id=player_id,
            stock_id=stock.id,
            transaction_type=TransactionType.BUY,
            shares=shares,
            price=unit_price,
            total_amount=total_amount,
            commission=commission
        )

        # 注释掉市场影响，避免少玩家时被操控
        # await StockPriceEngine.simulate_market_impact(session, stock.id, shares, "BUY")

        return True, f"成功投资 {stock.name}({stock_symbol}) {shares}份，" \
                    f"成交价 {unit_price} 金币/份，手续费 {commission} 金币"

    async def sell_stock(self, player_id: str, stock_symbol: str, shares: int,
                        to_bank: bool = False) -> Tuple[bool, str]:
        """卖出股票

        Args:
            player_id: 玩家ID
            stock_symbol: 股票代码
            shares: 卖出数量
            to_bank: 是否存入银行账户
        """
        # 获取玩家信息
        player = await self._player_repo.get_by_id(player_id)
        if not player:
            return False, "玩家不存在"

        # 获取股票信息
        stock = await self._stock_repo.get_by_symbol(stock_symbol)
        if not stock or not stock.is_active:
            return False, f"气运项目 {stock_symbol} 不存在或已停止投资"

        # 获取持仓信息
        holding = await self._stock_holding_repo.get_by_player_and_stock(
            player_id, stock.id
        )

        if not holding or holding.shares < shares:
            return False, f"投资不足，当前持有 {holding.shares if holding else 0} 份"

        # 验证交易数量
        if shares <= 0:
            return False, "交易数量必须大于0"

        # 计算交易金额和手续费
        unit_price = stock.current_price
        total_amount = unit_price * shares
        commission = self._calculate_commission(total_amount)
        net_proceeds = total_amount - commission

        # 更新持仓
        await self._update_holding_sell(holding, shares, unit_price, total_amount)

        # 添加资金
        if to_bank:
            # 存入银行账户
            await self._bank_account_repo.deposit(player_id, net_proceeds)
        else:
            # 添加到现金
            player.gold += net_proceeds
            await self._player_repo.update(player)

        # 记录交易
        await self._stock_transaction_repo.create_transaction(
            player_id=player_id,
            stock_id=stock.id,
            transaction_type=TransactionType.SELL,
            shares=shares,
            price=unit_price,
            total_amount=total_amount,
            commission=commission
        )

        # 注释掉市场影响，避免少玩家时被操控
        # await StockPriceEngine.simulate_market_impact(session, stock.id, shares, "SELL")

        return True, f"成功出售 {stock.name}({stock_symbol}) {shares}份，" \
                    f"成交价 {unit_price} 金币/份，手续费 {commission} 金币，净收入 {net_proceeds} 金币"

    async def get_player_holdings(self, player_id: str) -> List[Dict]:
        """获取玩家持仓

        Args:
            player_id: 玩家ID

        Returns:
            持仓列表
        """
        # 使用优化的查询方法（已预加载stock关联）
        holdings = await self._stock_holding_repo.get_player_holdings_with_stock(player_id)

        result = []
        for holding in holdings:
            if holding.shares <= 0:
                continue

            stock = holding.stock
            result.append({
                "symbol": stock.symbol,
                "name": stock.name,
                "shares": holding.shares,
                "avg_cost": holding.avg_cost,
                "current_price": stock.current_price,
                "current_value": holding.current_value,
                "total_cost": holding.total_cost,
                "profit_loss": holding.profit_loss,
                "profit_loss_rate": holding.profit_loss_rate
            })

        return result

    async def get_player_transactions(self, player_id: str, limit: int = 20) -> List[Dict]:
        """获取玩家交易记录

        Args:
            player_id: 玩家ID
            limit: 返回记录数量限制

        Returns:
            交易记录列表
        """
        # 使用优化的查询方法（已预加载stock关联）
        transactions = await self._stock_transaction_repo.get_player_transactions_with_stock(
            player_id, limit
        )

        result = []
        for trans in transactions:
            stock = trans.stock
            result.append({
                "symbol": stock.symbol,
                "name": stock.name,
                "type": trans.transaction_type,
                "shares": trans.shares,
                "price": trans.price,
                "total_amount": trans.total_amount,
                "commission": trans.commission,
                "created_at": trans.created_at
            })

        return result

    def _calculate_commission(self, amount: int) -> int:
        """计算手续费"""
        commission = int(amount * self.COMMISSION_RATE)
        return max(self.MIN_COMMISSION, min(self.MAX_COMMISSION, commission))

    async def _update_holding_buy(self, player_id: str, stock_id: int,
                                 shares: int, unit_price: int, total_amount: int):
        """更新买入持仓"""
        holding = await self._stock_holding_repo.get_by_player_and_stock(
            player_id, stock_id
        )

        if holding:
            # 更新现有持仓
            new_total_cost = holding.total_cost + total_amount
            new_shares = holding.shares + shares
            new_avg_cost = new_total_cost // new_shares

            holding.shares = new_shares
            holding.avg_cost = new_avg_cost
            holding.total_cost = new_total_cost
            holding.updated_at = datetime.now()

            await self._stock_holding_repo.update(holding)
        else:
            # 创建新持仓
            from ..models.stock import StockHolding
            holding = StockHolding(
                player_id=player_id,
                stock_id=stock_id,
                shares=shares,
                avg_cost=unit_price,
                total_cost=total_amount
            )
            await self._stock_holding_repo.add(holding)

    async def _update_holding_sell(self, holding, shares: int,
                                  unit_price: int, total_amount: int):
        """更新卖出持仓"""
        # 计算卖出成本（按比例）
        sold_cost = (holding.total_cost * shares) // holding.shares

        # 更新持仓
        holding.shares -= shares
        holding.total_cost -= sold_cost
        holding.updated_at = datetime.now()

        # 如果全部卖出，删除持仓记录
        if holding.shares == 0:
            await self._stock_holding_repo.delete_holding(holding)
        else:
            await self._stock_holding_repo.update(holding)
