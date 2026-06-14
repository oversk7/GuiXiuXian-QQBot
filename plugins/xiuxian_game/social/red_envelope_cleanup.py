"""
红包过期自动清理机制

定时把已过期但状态仍为 ACTIVE 的红包置为 EXPIRED，并退还剩余余额给发包人。
不依赖玩家"抢红包"被动触发清理，避免红包过期后卡死（既发不出新红包、又抢不到旧红包、且余额不退还）。
"""
import logging
from nonebot import get_driver
from nonebot_plugin_apscheduler import scheduler

from ..models.db import safe_session
from ..infrastructure.repositories.red_envelope_repository import RedEnvelopeRepository
from ..infrastructure.repositories.player_repository import PlayerRepository
from .red_envelope_service import RedEnvelopeService

logger = logging.getLogger(__name__)

driver = get_driver()


async def cleanup_expired_envelopes():
    """清理过期红包，退还余额给发包人"""
    try:
        async with safe_session() as session:
            service = RedEnvelopeService(
                envelope_repo=RedEnvelopeRepository(session),
                player_repo=PlayerRepository(session),
            )
            count = await service.expire_stale_envelopes()
            if count > 0:
                logger.info(f"🧧 红包过期清理完成：清理了 {count} 个过期红包并退还余额")
            else:
                logger.debug("🧧 红包过期清理：没有需要清理的红包")
    except Exception as e:
        logger.error(f"❌ 红包过期清理任务失败: {e}")


@driver.on_startup
async def setup_red_envelope_cleanup():
    """设置红包过期清理定时任务"""
    try:
        if scheduler.get_job("red_envelope_cleanup"):
            logger.info("⚠️ 红包过期清理定时任务已存在，跳过设置")
            return

        scheduler.add_job(
            func=cleanup_expired_envelopes,
            trigger="interval",
            minutes=10,
            id="red_envelope_cleanup",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        logger.info("✅ 红包过期清理定时任务已设置 - 每10分钟执行一次")

    except Exception as e:
        logger.error(f"❌ 设置红包过期清理定时任务失败: {e}")


@driver.on_shutdown
async def cleanup_red_envelope_scheduler():
    """关闭时移除红包过期清理定时任务"""
    try:
        if scheduler.get_job("red_envelope_cleanup"):
            scheduler.remove_job("red_envelope_cleanup")
            logger.info("🧹 红包过期清理定时任务已移除")
    except Exception as e:
        logger.error(f"❌ 移除红包过期清理定时任务失败: {e}")
