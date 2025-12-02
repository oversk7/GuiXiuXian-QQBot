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
            # 添加每周黑天鹅事件检查（每周一凌晨执行）
            scheduler.add_job(
                func=perform_weekly_black_swan_check,
                trigger="cron",
                day_of_week="mon",
                hour=0,  # 每周一凌晨0点执行
                id="stock_weekly_black_swan",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            logger.info("✅ 黑天鹅事件定时任务已设置 - 每周一凌晨执行")

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

        # TODO: 实现黑天鹅事件触发逻辑
        # 这部分逻辑比较复杂，暂时留空
        # 后续可以添加事件配置和触发机制

        logger.info("✅ 黑天鹅事件检查完成（当前未实现）")

    except Exception as e:
        logger.error(f"❌ 黑天鹅事件检查失败: {e}")


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

    except Exception as e:
        logger.error(f"❌ 清理股票定时任务失败: {e}")
