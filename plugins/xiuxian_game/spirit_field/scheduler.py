"""
灵田系统 - 定时任务

使用 APScheduler 实现:
- 每日灌溉次数重置
- 每日诡兽自动扣费
"""

from nonebot import get_driver, logger
from nonebot_plugin_apscheduler import scheduler

from ..models.db import AsyncSessionLocal
from ..infrastructure.uow.unit_of_work import UnitOfWork
from .guardian_service import GuardianService

# 获取驱动器
driver = get_driver()

# 服务实例
guardian_service = GuardianService()


@scheduler.scheduled_job("cron", hour="0", minute="5", id="spirit_field_daily_reset")
async def spirit_field_daily_reset():
    """
    灵田每日重置任务

    每日00:05执行:
    1. 重置所有地块灌溉次数
    2. 自动扣除诡兽灵食费
    """
    logger.info("开始执行灵田每日重置...")

    try:
        async with UnitOfWork(AsyncSessionLocal) as uow:
            # 1. 重置灌溉次数
            await uow.spirit_field_plots.reset_all_water_counts()

            # 2. 自动扣除诡兽灵食费
            fed_count = await guardian_service.auto_feed_all(uow)

            logger.info(f"灵田每日重置完成: 灌溉重置, 诡兽喂食{fed_count}只")

    except Exception as e:
        logger.error(f"灵田每日重置失败: {e}")


@driver.on_startup
async def on_startup():
    """Bot启动时执行"""
    logger.info("灵田系统定时任务已注册")
    logger.info("  - 每日00:05: 灌溉重置 + 诡兽扣费")
