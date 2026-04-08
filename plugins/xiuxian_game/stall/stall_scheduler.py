"""
摊位系统定时任务

任务：每5分钟检查过期摊位并自动收摊
"""

from nonebot import get_driver, logger
from nonebot_plugin_apscheduler import scheduler

from ..models.db import AsyncSessionLocal
from ..infrastructure.uow.unit_of_work import UnitOfWork

driver = get_driver()


@scheduler.scheduled_job(
    "interval",
    minutes=5,
    id="stall_expiry_check",
    max_instances=1,
    coalesce=True,
)
async def stall_expiry_check():
    """每5分钟检查并收摊过期摊位"""
    from . import stall_service

    try:
        async with UnitOfWork(AsyncSessionLocal) as uow:
            count = await stall_service.expire_stalls(uow)
            await uow.commit()

        if count > 0:
            logger.info(f"[摊位] 自动收摊 {count} 个过期摊位")

    except Exception as e:
        logger.error(f"[摊位] 定时任务失败: {e}", exc_info=True)


@driver.on_startup
async def on_startup():
    logger.info("🏪 摊位定时任务已注册")
    logger.info("  - 每5分钟：检查过期摊位并自动收摊")
