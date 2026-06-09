"""
拍卖行定时任务

任务：
- 每5分钟：结算已到期拍卖 + 发送30分钟提醒
"""

from nonebot import get_driver, logger
from nonebot_plugin_apscheduler import scheduler

from ..models.db import AsyncSessionLocal
from ..infrastructure.uow.unit_of_work import UnitOfWork

driver = get_driver()


@scheduler.scheduled_job(
    "interval",
    minutes=5,
    id="auction_settlement_check",
    max_instances=1,
    coalesce=True,
)
async def auction_settlement_check():
    """
    每5分钟执行：
    1. 发送即将结束（30分钟内）的拍卖提醒
    2. 结算所有已到期的拍卖
    """
    from . import auction_service

    try:
        async with UnitOfWork(AsyncSessionLocal) as uow:
            # 先发提醒（在结算前，避免刚到期就被结算掉）
            reminded = await auction_service.send_30min_reminders(uow)
            await uow.commit()

        async with UnitOfWork(AsyncSessionLocal) as uow:
            # 再结算
            settled = await auction_service.settle_expired_auctions(uow)
            await uow.commit()

        if reminded > 0 or settled > 0:
            logger.info(
                f"[拍卖行] 定时任务完成：发送提醒 {reminded} 条，结算拍卖 {settled} 件"
            )

    except Exception as e:
        logger.error(f"[拍卖行] 定时任务失败: {e}", exc_info=True)


@driver.on_startup
async def on_startup():
    """Bot启动时执行"""
    logger.info("🏛️ 拍卖行定时任务已注册")
    logger.info("  - 每分钟：检查到期结算 + 30分钟提醒广播")
