"""
红包后台任务

- 过期关闭（每分钟）：用 Redis 剩余金额退款，避免红包过期后卡死（既发不出新红包、又抢不到旧红包、且余额不退还）。
- 对账（每 5 分钟）：已领总额 + 退款 = 实发金额。
- 入账消费者：随进程启动，把 Redis Stream 里的领取消息写入数据库。

未配置 Redis 时红包功能不可用，这些任务也不启动。
"""
import asyncio
import logging
from nonebot import get_driver
from nonebot_plugin_apscheduler import scheduler
from redis.exceptions import ResponseError
from sqlalchemy.exc import SQLAlchemyError

from ..infrastructure.redis_service import RedisUnavailable
from .red_envelope_settlement import (
    RedEnvelopeSettler,
    close_expired_envelopes,
    reconcile_envelopes,
    set_settler,
)
from .red_envelope_store import get_red_envelope_store

logger = logging.getLogger(__name__)

driver = get_driver()

_JOB_IDS = ("red_envelope_cleanup", "red_envelope_reconcile")
_settler_task: asyncio.Task | None = None


async def cleanup_expired_envelopes():
    """关闭过期红包，按 Redis 剩余金额退还给发包人"""
    try:
        count = await close_expired_envelopes(get_red_envelope_store())
        if count > 0:
            logger.info(f"🧧 红包过期清理完成：关闭了 {count} 个过期红包并退还余额")
    except (SQLAlchemyError, RedisUnavailable, ResponseError) as e:
        logger.error(f"❌ 红包过期清理任务失败: {type(e).__name__}: {e}")


async def reconcile_red_envelopes():
    """对账：已领总额 + 退款 = 实发金额"""
    try:
        summary = await reconcile_envelopes()
        if summary:
            logger.info(f"🧧 红包对账完成：{ {state.name: n for state, n in summary.items()} }")
    except SQLAlchemyError as e:
        logger.error(f"❌ 红包对账任务失败: {type(e).__name__}: {e}")


@driver.on_startup
async def setup_red_envelope_cleanup():
    """设置红包后台任务"""
    global _settler_task
    store = get_red_envelope_store()
    if not store.configured:
        logger.warning("⚠️ 未配置 GUIX_REDIS_URL，红包功能不可用")
        return

    for job_id, func, minutes in (
        ("red_envelope_cleanup", cleanup_expired_envelopes, 1),
        ("red_envelope_reconcile", reconcile_red_envelopes, 5),
    ):
        scheduler.add_job(
            func=func,
            trigger="interval",
            minutes=minutes,
            id=job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    settler = RedEnvelopeSettler(store)
    set_settler(settler)
    _settler_task = asyncio.create_task(settler.run_forever())
    logger.info("✅ 红包入账消费者已启动；过期清理每1分钟、对账每5分钟执行一次")


@driver.on_shutdown
async def cleanup_red_envelope_scheduler():
    """关闭时停止入账消费者并移除定时任务"""
    global _settler_task
    task, _settler_task = _settler_task, None
    if task is not None:
        # 处理到一半的消息没有确认，下次启动会从待确认列表里重新处理
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        set_settler(None)
    for job_id in _JOB_IDS:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
