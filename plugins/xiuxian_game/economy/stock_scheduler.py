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
            
    except Exception as e:
        logger.error(f"❌ 清理股票定时任务失败: {e}")
