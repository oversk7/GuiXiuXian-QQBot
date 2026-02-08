"""
定时任务 - 餐厅每小时结算

使用 APScheduler 实现定时任务
"""

from nonebot import require, get_driver, logger
from nonebot_plugin_apscheduler import scheduler

from ..models.db import AsyncSessionLocal
from ..infrastructure.uow.unit_of_work import UnitOfWork
from .settlement_service import SettlementService

# 获取驱动器
driver = get_driver()

# 创建结算服务实例
settlement_service = SettlementService()


@scheduler.scheduled_job("cron", hour="*", minute="0", id="restaurant_settlement")
async def restaurant_hourly_settlement():
    """
    餐厅每小时结算任务

    每小时整点执行一次，结算所有营业中的餐厅
    """

    logger.info("🕐 开始执行餐厅小时结算...")

    try:
        async with UnitOfWork(AsyncSessionLocal) as uow:
            settled_count = await settlement_service.settle_all_restaurants(uow)

            if settled_count > 0:
                logger.info(f"✅ 餐厅小时结算完成，共结算 {settled_count} 家餐厅")
            else:
                logger.debug("⚪ 当前没有营业中的餐厅")

    except Exception as e:
        logger.error(f"❌ 餐厅结算任务失败: {e}")


# 可选:每日清理过期的厨师候选
@scheduler.scheduled_job("cron", hour="3", minute="0", id="clear_expired_chef_candidates")
async def clear_expired_chef_candidates():
    """
    清理过期的厨师候选

    每天凌晨3点执行，清理超过24小时的候选
    """

    logger.info("🧹 开始清理过期厨师候选...")

    try:
        async with UnitOfWork(AsyncSessionLocal) as uow:
            deleted_count = await uow.chef_candidates.clear_expired(hours=24)
            await uow.commit()

            if deleted_count > 0:
                logger.info(f"✅ 清理完成，删除 {deleted_count} 条过期候选")
            else:
                logger.debug("⚪ 没有过期的厨师候选")

    except Exception as e:
        logger.error(f"❌ 清理厨师候选任务失败: {e}")


# 可选:每周清理旧的餐厅日志
@scheduler.scheduled_job("cron", day_of_week="sun", hour="4", minute="0", id="clear_old_restaurant_logs")
async def clear_old_restaurant_logs():
    """
    清理旧的餐厅日志

    每周日凌晨4点执行，清理超过7天的日志
    """

    logger.info("🧹 开始清理旧餐厅日志...")

    try:
        async with UnitOfWork(AsyncSessionLocal) as uow:
            # 获取所有餐厅
            from sqlalchemy import select
            from ..models.restaurant import Restaurant

            result = await uow.session.execute(select(Restaurant))
            restaurants = result.scalars().all()

            total_deleted = 0
            for restaurant in restaurants:
                deleted_count = await uow.restaurant_logs.clear_old_logs(days=7)
                total_deleted += deleted_count

            await uow.commit()

            if total_deleted > 0:
                logger.info(f"✅ 清理完成，删除 {total_deleted} 条旧日志")
            else:
                logger.debug("⚪ 没有需要清理的旧日志")

    except Exception as e:
        logger.error(f"❌ 清理餐厅日志任务失败: {e}")


@driver.on_startup
async def on_startup():
    """Bot启动时执行"""
    logger.info("🏪 餐厅系统定时任务已注册")
    logger.info("  - 每小时整点: 餐厅结算")
    logger.info("  - 每日03:00: 清理过期厨师候选")
    logger.info("  - 每周日04:00: 清理旧餐厅日志")
