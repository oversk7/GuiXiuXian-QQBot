"""
工作单元实现

基于 REFACTORING_PLAN_v4.md 第2.2节的设计，解决多会话问题

重要提示：
- 不要在 async with UnitOfWork() 内部调用 finish()
- 如果需要提前返回，使用 return 而非 finish()
- 在 UnitOfWork 外部调用 finish()
"""

from typing import Callable, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from nonebot import logger


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

        # 理财相关仓储
        self._bank_funds = None
        self._fund_holdings = None

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
        self._guild_task_records = None
        self._social_applications = None

        # 任务相关仓储
        self._player_task_stats = None

        # 关系相关仓储
        self._player_relationships = None

        # 里界系统仓储
        self._inner_realm_sessions = None
        self._inner_realm_tiles = None

        # 烹饪餐厅系统仓储
        self._restaurants = None
        self._restaurant_storage = None
        self._restaurant_menus = None
        self._chefs = None
        self._chef_candidates = None
        self._restaurant_logs = None
        self._player_recipes = None

        # 灵田系统仓储
        self._spirit_fields = None
        self._spirit_field_plots = None
        self._spirit_field_steal_logs = None

        # 下位世界系统仓储
        self._lower_world_strongholds = None

        # 阴宅仓库系统仓储
        self._mansion_warehouse_items = None

        # 拍卖行系统仓储
        self._auction_items = None
        self._auction_bid_histories = None

        # 宠物伴侣系统仓储
        self._pets = None
        self._pet_dialogue_histories = None

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
    def bank_funds(self):
        """理财基金仓储"""
        if self._bank_funds is None:
            from ..repositories.bank_fund_repository import BankFundRepository
            self._bank_funds = BankFundRepository(self._session)
        return self._bank_funds

    @property
    def fund_holdings(self):
        """理财持仓仓储"""
        if self._fund_holdings is None:
            from ..repositories.fund_holding_repository import FundHoldingRepository
            self._fund_holdings = FundHoldingRepository(self._session)
        return self._fund_holdings

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
    def guild_task_records(self):
        """公会任务记录仓储"""
        if self._guild_task_records is None:
            from ..repositories.guild_task_record_repository import GuildTaskRecordRepository
            self._guild_task_records = GuildTaskRecordRepository(self._session)
        return self._guild_task_records

    @property
    def social_applications(self):
        """社交申请仓储"""
        if self._social_applications is None:
            from ..repositories.social_application_repository import SocialApplicationRepository
            self._social_applications = SocialApplicationRepository(self._session)
        return self._social_applications

    @property
    def player_task_stats(self):
        """玩家任务统计仓储"""
        if self._player_task_stats is None:
            from ..repositories.player_task_stats_repository import PlayerTaskStatsRepository
            self._player_task_stats = PlayerTaskStatsRepository(self._session)
        return self._player_task_stats

    @property
    def player_relationships(self):
        """玩家关系仓储"""
        if self._player_relationships is None:
            from ..repositories.player_relationship_repository import PlayerRelationshipRepository
            self._player_relationships = PlayerRelationshipRepository(self._session)
        return self._player_relationships

    @property
    def inner_realm_sessions(self):
        """里界会话仓储"""
        if self._inner_realm_sessions is None:
            from ..repositories.inner_realm_session_repository import InnerRealmSessionRepository
            self._inner_realm_sessions = InnerRealmSessionRepository(self._session)
        return self._inner_realm_sessions

    @property
    def inner_realm_tiles(self):
        """里界地块仓储"""
        if self._inner_realm_tiles is None:
            from ..repositories.inner_realm_tile_repository import InnerRealmTileRepository
            self._inner_realm_tiles = InnerRealmTileRepository(self._session)
        return self._inner_realm_tiles

    @property
    def restaurants(self):
        """餐厅仓储"""
        if self._restaurants is None:
            from ..repositories.restaurant_repository import RestaurantRepository
            self._restaurants = RestaurantRepository(self._session)
        return self._restaurants

    @property
    def restaurant_storage(self):
        """餐厅仓库仓储"""
        if self._restaurant_storage is None:
            from ..repositories.restaurant_storage_repository import RestaurantStorageRepository
            self._restaurant_storage = RestaurantStorageRepository(self._session)
        return self._restaurant_storage

    @property
    def restaurant_menus(self):
        """餐厅菜单仓储"""
        if self._restaurant_menus is None:
            from ..repositories.restaurant_menu_repository import RestaurantMenuRepository
            self._restaurant_menus = RestaurantMenuRepository(self._session)
        return self._restaurant_menus

    @property
    def chefs(self):
        """厨师仓储"""
        if self._chefs is None:
            from ..repositories.chef_repository import ChefRepository
            self._chefs = ChefRepository(self._session)
        return self._chefs

    @property
    def chef_candidates(self):
        """厨师候选仓储"""
        if self._chef_candidates is None:
            from ..repositories.chef_repository import ChefCandidateRepository
            self._chef_candidates = ChefCandidateRepository(self._session)
        return self._chef_candidates

    @property
    def restaurant_logs(self):
        """餐厅日志仓储"""
        if self._restaurant_logs is None:
            from ..repositories.restaurant_log_repository import RestaurantLogRepository
            self._restaurant_logs = RestaurantLogRepository(self._session)
        return self._restaurant_logs

    @property
    def player_recipes(self):
        """玩家食谱仓储"""
        if self._player_recipes is None:
            from ..repositories.player_recipe_repository import PlayerRecipeRepository
            self._player_recipes = PlayerRecipeRepository(self._session)
        return self._player_recipes

    @property
    def spirit_fields(self):
        """灵田仓储"""
        if self._spirit_fields is None:
            from ..repositories.spirit_field_repository import SpiritFieldRepository
            self._spirit_fields = SpiritFieldRepository(self._session)
        return self._spirit_fields

    @property
    def spirit_field_plots(self):
        """灵田地块仓储"""
        if self._spirit_field_plots is None:
            from ..repositories.spirit_field_plot_repository import SpiritFieldPlotRepository
            self._spirit_field_plots = SpiritFieldPlotRepository(self._session)
        return self._spirit_field_plots

    @property
    def spirit_field_steal_logs(self):
        """偷菜记录仓储"""
        if self._spirit_field_steal_logs is None:
            from ..repositories.spirit_field_steal_log_repository import SpiritFieldStealLogRepository
            self._spirit_field_steal_logs = SpiritFieldStealLogRepository(self._session)
        return self._spirit_field_steal_logs

    @property
    def lower_world_strongholds(self):
        """下位世界山寨仓储"""
        if self._lower_world_strongholds is None:
            from ..repositories.lower_world_repository import LowerWorldRepository
            self._lower_world_strongholds = LowerWorldRepository(self._session)
        return self._lower_world_strongholds

    @property
    def mansion_warehouse_items(self):
        """阴宅仓库物品仓储"""
        if self._mansion_warehouse_items is None:
            from ..repositories.mansion_warehouse_item_repository import MansionWarehouseItemRepository
            self._mansion_warehouse_items = MansionWarehouseItemRepository(self._session)
        return self._mansion_warehouse_items

    @property
    def auction_items(self):
        """拍卖行仓储"""
        if self._auction_items is None:
            from ..repositories.auction_repository import AuctionRepository
            self._auction_items = AuctionRepository(self._session)
        return self._auction_items

    @property
    def auction_bid_histories(self):
        """竞价历史仓储"""
        if self._auction_bid_histories is None:
            from ..repositories.auction_repository import AuctionBidHistoryRepository
            self._auction_bid_histories = AuctionBidHistoryRepository(self._session)
        return self._auction_bid_histories

    @property
    def pets(self):
        """宠物仓储"""
        if self._pets is None:
            from ..repositories.pet_repository import PetRepository
            self._pets = PetRepository(self._session)
        return self._pets

    @property
    def pet_dialogue_histories(self):
        """宠物对话历史仓储"""
        if self._pet_dialogue_histories is None:
            from ..repositories.pet_dialogue_history_repository import PetDialogueHistoryRepository
            self._pet_dialogue_histories = PetDialogueHistoryRepository(self._session)
        return self._pet_dialogue_histories

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
        - 特殊处理 Nonebot2 流程控制异常（FinishedException等）：提交而不是回滚
        - 总是关闭会话

        重要：不会吞掉异常，会向上传播
        """
        try:
            if exc_type is not None:
                # 特殊处理 Nonebot2 流程控制异常
                # 这些异常是正常流程控制，应该提交事务而不是回滚
                try:
                    from nonebot.exception import FinishedException, PausedException, RejectedException
                    if exc_type in (FinishedException, PausedException, RejectedException):
                        # 流程控制异常：静默提交事务（不记录日志）
                        self._update_player_cache()
                        await self._session.commit()
                    else:
                        # 其他异常：回滚事务
                        logger.warning(f"⚠️ [UnitOfWork] 会话 {id(self._session)} 回滚: {exc_type.__name__}: {exc_val}")
                        await self._session.rollback()
                except ImportError:
                    # 如果无法导入 Nonebot 异常（非 Nonebot 环境），按原逻辑回滚
                    logger.warning(f"⚠️ [UnitOfWork] 会话 {id(self._session)} 回滚: {exc_type.__name__}: {exc_val}")
                    await self._session.rollback()
            else:
                # 没有异常，提交事务
                logger.debug(f"✅ [UnitOfWork] 会话 {id(self._session)} 提交")
                self._update_player_cache()
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
