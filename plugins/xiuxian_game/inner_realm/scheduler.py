"""
定时任务 - 里界会话清理

使用 APScheduler 实现定时任务:
- 每日04:30 清理已结算超过7天的旧会话
- 每日04:30 强制结算超过30天未活动的会话
"""

from datetime import datetime, timedelta

from nonebot import get_driver, logger
from nonebot_plugin_apscheduler import scheduler

from ..models.db import AsyncSessionLocal
from ..infrastructure.uow.unit_of_work import UnitOfWork

# 获取驱动器
driver = get_driver()


@scheduler.scheduled_job("cron", hour="4", minute="30", id="inner_realm_session_cleanup")
async def inner_realm_session_cleanup():
    """
    里界会话清理任务

    每日04:30执行:
    1. 删除已结算超过7天的旧会话
    2. 强制结算超过30天未活动的会话
    """

    logger.info("开始执行里界会话清理...")

    try:
        async with UnitOfWork(AsyncSessionLocal) as uow:
            # 1. 删除已结算超过7天的旧会话
            cutoff_date = datetime.now() - timedelta(days=7)
            deleted_count = await uow.inner_realm_sessions.delete_old_sessions(cutoff_date)

            if deleted_count > 0:
                logger.info(f"清理已结算旧会话: 删除 {deleted_count} 条")

            # 2. 强制结算超过30天未活动的会话
            stale_date = datetime.now() - timedelta(days=30)
            stale_sessions = await uow.inner_realm_sessions.get_sessions_need_refresh(stale_date)

            settled_count = 0
            for session in stale_sessions:
                session.is_settled = True
                settled_count += 1

                # 清空对应玩家的里界标记
                from ..models.player import Player
                from sqlalchemy import select
                result = await uow.session.execute(
                    select(Player).where(Player.id == session.player_id)
                )
                player = result.scalar_one_or_none()
                if player and player.inner_realm == session.realm_name:
                    player.inner_realm = None

            await uow.commit()

            if settled_count > 0:
                logger.info(f"强制结算过期会话: {settled_count} 条")

            if deleted_count == 0 and settled_count == 0:
                logger.debug("里界会话清理: 无需处理")

    except Exception as e:
        logger.error(f"里界会话清理任务失败: {e}")


@driver.on_startup
async def on_startup():
    """Bot启动时执行"""
    logger.info("里界系统定时任务已注册")
    logger.info("  - 每日04:30: 会话清理（删除旧会话 + 强制结算过期会话）")
