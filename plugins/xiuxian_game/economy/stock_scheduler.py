"""股票价格更新定时任务调度器"""
import logging
from nonebot import get_driver
from nonebot_plugin_apscheduler import scheduler
from .stock_price_engine import StockMarketScheduler

logger = logging.getLogger(__name__)

driver = get_driver()


@driver.on_startup
async def setup_stock_scheduler():
    """设置股票价格更新定时任务"""
    try:
        # 检查任务是否已存在，避免重复设置
        existing_hourly_job = scheduler.get_job("stock_hourly_update")
        existing_daily_job = scheduler.get_job("stock_daily_update")
        existing_holding_fee_job = scheduler.get_job("stock_daily_holding_fee")
        existing_black_swan_job = scheduler.get_job("stock_weekly_black_swan")
        existing_relist_job = scheduler.get_job("stock_daily_relist_check")

        if existing_hourly_job:
            logger.info("⚠️ 股票备用更新定时任务已存在，跳过设置")
        else:
            # 添加备用价格更新任务（降低频率，作为被动触发的备用机制）
            scheduler.add_job(
                func=perform_backup_update,
                trigger="interval",
                hours=12,  # 改为12小时执行一次，作为备用机制
                id="stock_hourly_update",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            logger.info("✅ 股票备用价格更新定时任务已设置（12小时间隔）")

        if existing_daily_job:
            logger.info("⚠️ 股票每日更新定时任务已存在，跳过设置")
        else:
            # 添加每日执行一次的市场更新任务（每天9点执行）
            scheduler.add_job(
                func=perform_daily_update,
                trigger="cron",
                hour=9,  # 每天9点执行
                id="stock_daily_update",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            logger.info("✅ 股票每日市场更新定时任务已设置 - 每天9点执行")

        if existing_holding_fee_job:
            logger.info("⚠️ 持仓管理费定时任务已存在，跳过设置")
        else:
            # 添加每日持仓管理费扣除任务（每天凌晨3点执行）
            scheduler.add_job(
                func=perform_daily_holding_fee,
                trigger="cron",
                hour=3,  # 每天凌晨3点执行
                id="stock_daily_holding_fee",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            logger.info("✅ 持仓管理费定时任务已设置 - 每天凌晨3点执行")

        if existing_black_swan_job:
            logger.info("⚠️ 黑天鹅事件定时任务已存在，跳过设置")
        else:
            # 添加每日黑天鹅事件检查（每天凌晨2点执行）- 提高触发频率
            scheduler.add_job(
                func=perform_weekly_black_swan_check,
                trigger="cron",
                hour=2,  # 每天凌晨2点执行（避开其他任务）
                id="stock_weekly_black_swan",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            logger.info("✅ 黑天鹅事件定时任务已设置 - 每天凌晨2点执行")

        if existing_relist_job:
            logger.info("⚠️ 股票重新上市检查定时任务已存在，跳过设置")
        else:
            # 添加每日重新上市检查任务（每天凌晨1点执行）
            scheduler.add_job(
                func=perform_daily_relist_check,
                trigger="cron",
                hour=1,  # 每天凌晨1点执行
                id="stock_daily_relist_check",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            logger.info("✅ 股票重新上市检查定时任务已设置 - 每天凌晨1点执行")

    except Exception as e:
        logger.error(f"❌ 设置股票价格更新定时任务失败: {e}")


async def perform_backup_update():
    """执行备用股票价格更新（降低频率的备用机制）"""
    try:
        logger.info("🔄 开始执行股票备用价格更新...")
        results = await StockMarketScheduler.hourly_market_update()

        # 统计更新结果
        total_stocks = len(results)
        up_count = sum(1 for r in results.values() if r["change_amount"] > 0)
        down_count = sum(1 for r in results.values() if r["change_amount"] < 0)
        flat_count = total_stocks - up_count - down_count

        logger.info(f"✅ 股票备用价格更新完成: 共{total_stocks}只股票, 上涨{up_count}只, 下跌{down_count}只, 平盘{flat_count}只")

    except Exception as e:
        logger.error(f"❌ 股票备用价格更新失败: {e}")


async def perform_daily_update():
    """执行每日股票市场更新"""
    try:
        logger.info("🔄 开始执行股票每日市场更新...")
        results = await StockMarketScheduler.daily_market_update()

        # 统计更新结果
        total_stocks = len(results)
        up_count = sum(1 for r in results.values() if r["change_amount"] > 0)
        down_count = sum(1 for r in results.values() if r["change_amount"] < 0)
        flat_count = total_stocks - up_count - down_count

        logger.info(f"✅ 股票每日市场更新完成: 共{total_stocks}只股票, 上涨{up_count}只, 下跌{down_count}只, 平盘{flat_count}只")

        # 可以在这里添加每日市场报告的逻辑
        # 比如：向管理员发送市场总结报告

    except Exception as e:
        logger.error(f"❌ 股票每日市场更新失败: {e}")


async def perform_daily_holding_fee():
    """执行每日持仓管理费扣除"""
    try:
        logger.info("💰 开始扣除持仓管理费...")

        from ..infrastructure.uow.unit_of_work import UnitOfWork
        from ..models.db import AsyncSessionLocal
        from .stock_service_new import StockService

        def session_factory():
            return AsyncSessionLocal()

        async with UnitOfWork(session_factory) as uow:
            stock_service = StockService(
                player_repo=uow.players,
                stock_repo=uow.stocks,
                stock_holding_repo=uow.stock_holdings,
                stock_transaction_repo=uow.stock_transactions,
                bank_account_repo=uow.bank_accounts
            )

            stats = await stock_service.apply_holding_cost()
            await uow.commit()

        logger.info(
            f"✅ 持仓管理费扣除完成: "
            f"处理{stats['total_players']}名玩家, "
            f"总计{stats['total_fees']}金币, "
            f"强制卖出{stats['forced_sell_count']}次"
        )

    except Exception as e:
        logger.error(f"❌ 持仓管理费扣除失败: {e}")


async def perform_weekly_black_swan_check():
    """执行每周黑天鹅事件检查"""
    try:
        logger.info("🦢 开始检查黑天鹅事件...")

        from ..infrastructure.uow.unit_of_work import UnitOfWork
        from ..models.db import AsyncSessionLocal
        from .black_swan_service import BlackSwanService

        def session_factory():
            return AsyncSessionLocal()

        async with UnitOfWork(session_factory) as uow:
            black_swan_service = BlackSwanService(
                stock_repo=uow.stocks,
                stock_event_repo=uow.stock_events
            )

            triggered_events = await black_swan_service.check_and_trigger_events()
            await uow.commit()

        if triggered_events:
            logger.info(f"✅ 黑天鹅事件检查完成: 触发了 {len(triggered_events)} 个事件")
            for event in triggered_events:
                logger.info(f"  - {event['event_name']}: {event['stock_name']} 暴跌 {abs(event['price_impact'])*100:.0f}%")
        else:
            logger.info("✅ 黑天鹅事件检查完成: 本周未触发任何事件")

    except Exception as e:
        logger.error(f"❌ 黑天鹅事件检查失败: {e}", exc_info=True)


async def perform_daily_relist_check():
    """执行每日股票重新上市检查"""
    try:
        logger.info("🔄 开始检查股票重新上市...")

        from .stock_relist_service import StockRelistService

        # 1. 检查并重新上市符合条件的退市股票
        relist_stats = await StockRelistService.check_and_relist_stocks()

        # 2. 确保最小股票数量
        ensure_stats = await StockRelistService.ensure_minimum_stocks()

        total_relisted = relist_stats["relisted_count"] + ensure_stats["created_count"]
        # 使用 ensure_stats 的统计数据，因为它在最后执行，包含了所有变化
        total_active = ensure_stats["total_active"]

        if total_relisted > 0:
            logger.info(
                f"✅ 股票重新上市检查完成: "
                f"重新上市{relist_stats['relisted_count']}只, "
                f"新建{ensure_stats['created_count']}只, "
                f"当前活跃{total_active}只"
            )
        else:
            logger.info(f"✅ 股票重新上市检查完成: 当前活跃{total_active}只,无需补充")

    except Exception as e:
        logger.error(f"❌ 股票重新上市检查失败: {e}", exc_info=True)


@driver.on_shutdown
async def cleanup_stock_scheduler():
    """清理股票调度器"""
    try:
        if scheduler.get_job("stock_hourly_update"):
            scheduler.remove_job("stock_hourly_update")
            logger.info("🧹 股票备用更新定时任务已清理")

        if scheduler.get_job("stock_daily_update"):
            scheduler.remove_job("stock_daily_update")
            logger.info("🧹 股票每日更新定时任务已清理")

        if scheduler.get_job("stock_daily_holding_fee"):
            scheduler.remove_job("stock_daily_holding_fee")
            logger.info("🧹 持仓管理费定时任务已清理")

        if scheduler.get_job("stock_weekly_black_swan"):
            scheduler.remove_job("stock_weekly_black_swan")
            logger.info("🧹 黑天鹅事件定时任务已清理")

        if scheduler.get_job("stock_daily_relist_check"):
            scheduler.remove_job("stock_daily_relist_check")
            logger.info("🧹 股票重新上市检查定时任务已清理")

    except Exception as e:
        logger.error(f"❌ 清理股票定时任务失败: {e}")
