"""
工作单元实现

基于 REFACTORING_PLAN_v4.md 第2.2节的设计，解决多会话问题

重要提示：
- 不要在 async with UnitOfWork() 内部调用 finish()
- 如果需要提前返回，使用 return 而非 finish()
- 在 UnitOfWork 外部调用 finish()
"""

from typing import Callable, Optional, TypeVar, Awaitable
from sqlalchemy.ext.asyncio import AsyncSession
from nonebot import logger
from functools import wraps

T = TypeVar('T')


class UnitOfWork:
    """
    工作单元 - 管理事务边界

    解决的问题:
    - player/info.py 打开4个独立会话，破坏事务原子性
    - 统一管理所有仓储，确保它们共享同一个会话
    - 提供清晰的事务边界（commit/rollback）

    使用示例:
    ```python
    async with UnitOfWork(session_factory) as uow:
        # 所有仓储共享同一个会话
        player = await uow.players.get_by_id(player_id)

        if player.guild_id:
            guild = await uow.guilds.get_by_id(player.guild_id)

        # 查询临时buff
        buffs = await uow.buffs.get_active_buffs(player_id)

        # 所有操作在同一个事务中
        await uow.commit()
    ```
    """

    def __init__(self, session_factory: Callable[[], AsyncSession]):
        """
        初始化工作单元

        Args:
            session_factory: 会话工厂函数，用于创建新的数据库会话
        """
        self._session_factory = session_factory
        self._session: Optional[AsyncSession] = None

        # 仓储实例（延迟初始化）
        self._players = None
        self._items = None
        self._guilds = None
        self._buffs = None
        self._invite_rewards = None

        # Stock相关仓储
        self._stocks = None
        self._stock_holdings = None
        self._stock_transactions = None
        self._stock_events = None
        self._bank_accounts = None

        # 打工相关仓储
        self._part_time_jobs = None
        self._job_locations = None
        self._player_job_stats = None

        # 每日任务和世界相关仓储
        self._daily_tasks = None
        self._locations = None
        self._npcs = None

        # 公会相关仓储
        self._guild_buildings = None
        self._player_donation_logs = None

    @property
    def players(self):
        """玩家仓储"""
        if self._players is None:
            from ..repositories.player_repository import PlayerRepository
            self._players = PlayerRepository(self._session)
        return self._players

    @property
    def items(self):
        """物品仓储"""
        if self._items is None:
            from ..repositories.item_repository import ItemRepository
            self._items = ItemRepository(self._session)
        return self._items

    @property
    def guilds(self):
        """公会仓储"""
        if self._guilds is None:
            from ..repositories.guild_repository import GuildRepository
            self._guilds = GuildRepository(self._session)
        return self._guilds

    @property
    def buffs(self):
        """临时buff仓储"""
        if self._buffs is None:
            from ..repositories.buff_repository import BuffRepository
            self._buffs = BuffRepository(self._session)
        return self._buffs

    @property
    def invite_rewards(self):
        """邀请奖励仓储"""
        if self._invite_rewards is None:
            from ..repositories.invite_reward_repository import InviteRewardRepository
            self._invite_rewards = InviteRewardRepository(self._session)
        return self._invite_rewards

    @property
    def stocks(self):
        """股票仓储"""
        if self._stocks is None:
            from ..repositories.stock_repository import StockRepository
            self._stocks = StockRepository(self._session)
        return self._stocks

    @property
    def stock_holdings(self):
        """股票持仓仓储"""
        if self._stock_holdings is None:
            from ..repositories.stock_holding_repository import StockHoldingRepository
            self._stock_holdings = StockHoldingRepository(self._session)
        return self._stock_holdings

    @property
    def stock_transactions(self):
        """股票交易记录仓储"""
        if self._stock_transactions is None:
            from ..repositories.stock_transaction_repository import StockTransactionRepository
            self._stock_transactions = StockTransactionRepository(self._session)
        return self._stock_transactions

    @property
    def stock_events(self):
        """股票事件仓储"""
        if self._stock_events is None:
            from ..repositories.stock_event_repository import StockEventRepository
            self._stock_events = StockEventRepository(self._session)
        return self._stock_events

    @property
    def bank_accounts(self):
        """银行账户仓储"""
        if self._bank_accounts is None:
            from ..repositories.bank_account_repository import BankAccountRepository
            self._bank_accounts = BankAccountRepository(self._session)
        return self._bank_accounts

    @property
    def part_time_jobs(self):
        """打工记录仓储"""
        if self._part_time_jobs is None:
            from ..repositories.part_time_job_repository import PartTimeJobRepository
            self._part_time_jobs = PartTimeJobRepository(self._session)
        return self._part_time_jobs

    @property
    def job_locations(self):
        """工作地点仓储"""
        if self._job_locations is None:
            from ..repositories.job_location_repository import JobLocationRepository
            self._job_locations = JobLocationRepository(self._session)
        return self._job_locations

    @property
    def player_job_stats(self):
        """玩家打工统计仓储"""
        if self._player_job_stats is None:
            from ..repositories.player_job_stats_repository import PlayerJobStatsRepository
            self._player_job_stats = PlayerJobStatsRepository(self._session)
        return self._player_job_stats

    @property
    def daily_tasks(self):
        """每日任务仓储"""
        if self._daily_tasks is None:
            from ..repositories.daily_task_repository import DailyTaskRepository
            self._daily_tasks = DailyTaskRepository(self._session)
        return self._daily_tasks

    @property
    def locations(self):
        """地点仓储"""
        if self._locations is None:
            from ..repositories.location_repository import LocationRepository
            self._locations = LocationRepository(self._session)
        return self._locations

    @property
    def npcs(self):
        """NPC仓储"""
        if self._npcs is None:
            from ..repositories.npc_repository import NPCRepository
            self._npcs = NPCRepository(self._session)
        return self._npcs

    @property
    def guild_buildings(self):
        """公会建筑仓储"""
        if self._guild_buildings is None:
            from ..repositories.guild_building_repository import GuildBuildingRepository
            self._guild_buildings = GuildBuildingRepository(self._session)
        return self._guild_buildings

    @property
    def player_donation_logs(self):
        """玩家捐献日志仓储"""
        if self._player_donation_logs is None:
            from ..repositories.player_donation_log_repository import PlayerDonationLogRepository
            self._player_donation_logs = PlayerDonationLogRepository(self._session)
        return self._player_donation_logs

    @property
    def session(self) -> AsyncSession:
        """获取当前数据库会话"""
        if self._session is None:
            raise RuntimeError("会话未初始化，请在 async with UnitOfWork() 中使用")
        return self._session

    async def __aenter__(self):
        """进入上下文：创建会话"""
        self._session = self._session_factory()
        logger.debug(f"🔧 [UnitOfWork] 创建新会话: {id(self._session)}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        退出上下文：自动提交或回滚

        - 如果发生异常，自动回滚
        - 如果没有异常，自动提交
        - 总是关闭会话

        重要：不会吞掉异常，会向上传播
        """
        try:
            if exc_type is not None:
                # 发生异常，回滚事务
                logger.warning(f"⚠️ [UnitOfWork] 会话 {id(self._session)} 回滚: {exc_type.__name__}: {exc_val}")
                await self._session.rollback()
            else:
                # 没有异常，提交事务
                logger.debug(f"✅ [UnitOfWork] 会话 {id(self._session)} 提交")
                await self._session.commit()
        finally:
            # 无论如何都要关闭会话
            logger.debug(f"🔒 [UnitOfWork] 会话 {id(self._session)} 关闭")
            await self._session.close()

        # 不抑制异常，让异常继续向上传播
        # 返回 False 或不返回值（默认 None），表示不处理异常
        return False

    async def commit(self):
        """手动提交事务"""
        logger.debug(f"💾 [UnitOfWork] 手动提交会话 {id(self._session)}")
        await self._session.commit()

    async def rollback(self):
        """手动回滚事务"""
        await self._session.rollback()

    async def flush(self):
        """刷新会话（将更改写入数据库但不提交）"""
        await self._session.flush()

    @property
    def session(self) -> AsyncSession:
        """获取当前会话（用于需要直接访问会话的特殊情况）"""
        return self._session


# ==================== 工具函数 ====================

def with_uow(session_factory: Callable):
    """
    装饰器：自动处理 UnitOfWork 和 finish() 的交互

    使用这个装饰器可以避免连接泄漏问题，无需手动管理消息返回逻辑。

    使用示例：
    ```python
    @with_uow(lambda: AsyncSessionLocal())
    async def handle_command(event, uow):
        player = await get_unified_player(uow.session, event)
        if not player:
            return "⛔ 请先创建角色"  # 直接 return，不用 finish

        # 业务逻辑...
        return "✅ 执行成功"

    @some_cmd.handle()
    async def _(event: MessageEvent):
        result = await handle_command(event)
        await some_cmd.finish(result)  # 在外部 finish
    ```

    Args:
        session_factory: 创建 AsyncSession 的工厂函数

    Returns:
        装饰器函数
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            async with UnitOfWork(session_factory) as uow:
                # 将 uow 注入到函数参数中
                return await func(*args, uow=uow, **kwargs)
            # UnitOfWork 自动关闭，然后返回结果
            # 调用者可以拿到结果后再 finish()
        return wrapper
    return decorator
