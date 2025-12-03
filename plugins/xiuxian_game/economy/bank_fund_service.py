"""
银行理财产品Service
基于DI架构,提供理财产品的核心业务逻辑
"""
from datetime import datetime
import random
from typing import Optional, List, Tuple

from ..infrastructure.repositories.bank_fund_repository import BankFundRepository
from ..infrastructure.repositories.fund_holding_repository import FundHoldingRepository
from ..infrastructure.repositories.bank_account_repository import BankAccountRepository
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..models.bank_fund import BankFund, FundHolding
from ..models.bank_account import BankAccount
from ..models.player import Player


class BankFundService:
    """银行理财产品Service"""

    # 活期理财配置
    LIVELY_FUND_CONFIG = {
        "min_investment": 10_000,      # 最低投资1万
        "max_investment": 1_000_000,   # 最高投资100万
        "management_fee_rate": 0.001,  # 管理费0.1%/天
        "volatility": 0.03,            # 波动率标准差3%
        "max_daily_change": 0.05,      # 单日最大变化±5%
    }

    def __init__(
        self,
        fund_repo: BankFundRepository,
        holding_repo: FundHoldingRepository,
        bank_account_repo: BankAccountRepository,
        player_repo: PlayerRepository
    ):
        """
        初始化理财服务

        Args:
            fund_repo: 理财基金仓储
            holding_repo: 持仓仓储
            bank_account_repo: 银行账户仓储
            player_repo: 玩家仓储
        """
        self._fund_repo = fund_repo
        self._holding_repo = holding_repo
        self._bank_account_repo = bank_account_repo
        self._player_repo = player_repo

    async def get_or_create_lively_fund(self) -> BankFund:
        """获取或创建活期理财基金"""
        fund = await self._fund_repo.get_by_type("lively")

        if not fund:
            fund = BankFund(
                fund_name="冥界活期理财基金",
                fund_type="lively",
                daily_return=0.0,
                total_scale=0,
                participant_count=0
            )
            fund = await self._fund_repo.add(fund)

        return fund

    async def buy_fund(
        self,
        player: Player,
        amount: int,
        use_bank: bool = True
    ) -> Tuple[bool, str]:
        """
        购买理财产品

        Args:
            player: 玩家对象
            amount: 投资金额
            use_bank: 是否从银行账户扣款

        Returns:
            (成功标志, 消息)
        """
        # 1. 验证投资金额
        if amount < self.LIVELY_FUND_CONFIG["min_investment"]:
            return False, f"⛔ 最低投资 {self.LIVELY_FUND_CONFIG['min_investment']:,} 金币"

        if amount > self.LIVELY_FUND_CONFIG["max_investment"]:
            return False, f"⛔ 最高投资 {self.LIVELY_FUND_CONFIG['max_investment']:,} 金币"

        # 2. 检查资金来源
        if use_bank:
            bank_acc = await self._bank_account_repo.get_by_id(player.id)
            if not bank_acc or bank_acc.balance < amount:
                return False, "⛔ 银行存款不足"
            bank_acc.balance -= amount
            await self._bank_account_repo.update(bank_acc)
        else:
            if player.gold < amount:
                return False, "⛔ 金币不足"
            player.gold -= amount
            await self._player_repo.update(player)

        # 3. 获取基金
        fund = await self.get_or_create_lively_fund()

        # 4. 创建持仓记录
        holding = FundHolding(
            player_id=player.id,
            fund_id=fund.id,
            principal=amount,
            current_value=amount,
            accumulated_profit=0,
            buy_date=datetime.now(),
            last_settlement=datetime.now(),
            is_active=True
        )
        holding = await self._holding_repo.add(holding)

        # 5. 更新基金规模
        fund.total_scale += amount
        fund.participant_count += 1
        await self._fund_repo.update(fund)

        return True, (
            f"✅ 购买成功\n"
            f"━━━━━━━━━━━━━\n"
            f"💰 投资金额：{amount:,} 金币\n"
            f"📊 理财产品：{fund.fund_name}\n"
            f"💡 每日自动结算，使用「我的理财」查看收益"
        )

    async def sell_fund(
        self,
        player: Player,
        holding_id: int,
        to_bank: bool = True
    ) -> Tuple[bool, str]:
        """
        赎回理财产品

        Args:
            player: 玩家对象
            holding_id: 持仓ID
            to_bank: 是否存入银行

        Returns:
            (成功标志, 消息)
        """
        # 1. 获取持仓记录
        holding = await self._holding_repo.get_by_id(holding_id)
        if not holding or holding.player_id != player.id or not holding.is_active:
            return False, "⛔ 持仓不存在或已赎回"

        # 2. 结算最新收益
        fund = await self._fund_repo.get_by_id(holding.fund_id)
        if fund:
            await self._settle_holding(holding, fund.daily_return)

        # 3. 赎回资金
        redeem_amount = holding.current_value
        profit = holding.accumulated_profit

        if to_bank:
            bank_acc = await self._bank_account_repo.get_or_create(player.id)
            bank_acc.balance += redeem_amount
            await self._bank_account_repo.update(bank_acc)
        else:
            player.gold += redeem_amount
            await self._player_repo.update(player)

        # 4. 更新持仓状态
        holding.is_active = False
        await self._holding_repo.update(holding)

        # 5. 更新基金规模
        if fund:
            fund.total_scale -= redeem_amount
            fund.participant_count -= 1
            await self._fund_repo.update(fund)

        profit_str = f"+{profit:,}" if profit >= 0 else f"{profit:,}"
        return True, (
            f"✅ 赎回成功\n"
            f"━━━━━━━━━━━━━\n"
            f"💰 赎回金额：{redeem_amount:,} 金币\n"
            f"📈 累计盈亏：{profit_str} 金币\n"
            f"💵 已{'存入银行' if to_bank else '转入现金'}"
        )

    async def get_player_holdings(self, player_id: str) -> List[FundHolding]:
        """获取玩家的所有持仓"""
        return await self._holding_repo.get_player_holdings(player_id, active_only=True)

    async def daily_settlement(self) -> Tuple[float, int]:
        """每日结算所有持仓（定时任务调用）

        Returns:
            (今日收益率, 结算持仓数量)
        """
        # 1. 计算今日收益率
        fund = await self.get_or_create_lively_fund()
        daily_return = self._calculate_daily_return()
        fund.daily_return = daily_return
        await self._fund_repo.update(fund)

        # 2. 结算所有活跃持仓
        holdings = await self._holding_repo.get_all_active_holdings()

        for holding in holdings:
            await self._settle_holding(holding, daily_return)

        return daily_return, len(holdings)

    async def _settle_holding(self, holding: FundHolding, daily_return: float):
        """结算单个持仓"""
        # 计算收益
        profit = int(holding.current_value * daily_return)

        # 扣除管理费
        fee = int(holding.current_value * self.LIVELY_FUND_CONFIG["management_fee_rate"])

        # 更新市值
        holding.current_value += profit - fee
        holding.accumulated_profit += profit - fee
        holding.last_settlement = datetime.now()

        await self._holding_repo.update(holding)

    def _calculate_daily_return(self) -> float:
        """计算每日收益率（随机波动）"""
        # 随机波动（正态分布，期望=0）
        base_return = random.gauss(0, self.LIVELY_FUND_CONFIG["volatility"])

        # 市场情绪（随机）
        sentiment = random.choice([-0.02, 0, 0.02])

        # 综合收益率
        daily_return = base_return + sentiment

        # 限制±5%
        daily_return = max(
            -self.LIVELY_FUND_CONFIG["max_daily_change"],
            min(self.LIVELY_FUND_CONFIG["max_daily_change"], daily_return)
        )

        return daily_return
