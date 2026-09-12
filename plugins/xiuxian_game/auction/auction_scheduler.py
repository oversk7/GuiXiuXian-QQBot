"""
拍卖行定时任务

任务：
- 每5分钟：结算已到期拍卖 + 发送30分钟提醒
"""

from nonebot import get_driver, logger
from nonebot_plugin_apscheduler import scheduler

from sqlalchemy.exc import SQLAlchemyError

from ..models.db import AsyncSessionLocal
from ..models.auction import AuctionItem
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

    async with UnitOfWork(AsyncSessionLocal) as uow:
        reminder_ids = [a.id for a in await uow.auction_items.find_near_ending_unreminded()]
        expired_ids = [a.id for a in await uow.auction_items.find_expired_unsettled()]

    reminded = settled = 0
    failures = []
    jobs = [(auction_id, True) for auction_id in reminder_ids]
    jobs.extend((auction_id, False) for auction_id in expired_ids)
    for auction_id, is_reminder in jobs:
        try:
            # 每件拍卖独立提交，避免跨拍卖累积根锁和玩家锁。
            async with UnitOfWork(AsyncSessionLocal) as uow:
                if is_reminder:
                    success = await auction_service.send_30min_reminder(uow, auction_id)
                else:
                    auction = await uow.session.get(AuctionItem, auction_id)
                    success = False
                    if auction is not None:
                        success, _ = await auction_service._settle_auction(uow, auction)
            if success:
                if is_reminder:
                    reminded += 1
                else:
                    settled += 1
                    await auction_service.notify_settlement(auction_id)
        except (SQLAlchemyError, ValueError) as exc:
            logger.error(f"[拍卖行] 处理拍卖 #{auction_id} 失败: {exc}", exc_info=True)
            failures.append(exc)

    if failures:
        raise failures[0]
    if reminded > 0 or settled > 0:
        logger.info(
            f"[拍卖行] 定时任务完成：发送提醒 {reminded} 条，结算拍卖 {settled} 件"
        )


@driver.on_startup
async def on_startup():
    """Bot启动时执行"""
    logger.info("🏛️ 拍卖行定时任务已注册")
    logger.info("  - 每分钟：检查到期结算 + 30分钟提醒广播")
