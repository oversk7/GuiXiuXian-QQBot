"""
NPC和Location自动清理机制
防止任务NPC和临时地点无限累积
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, and_, delete
from nonebot import get_driver
from nonebot_plugin_apscheduler import scheduler

from ..models.db import safe_session
from ..models.npc import NPC, NPCType, NPCStatus
from ..models.location import Location
from ..models.daily_task import DailyTask

logger = logging.getLogger(__name__)

driver = get_driver()


class NPCLocationCleanup:
    """NPC和Location清理服务"""

    # 清理配置
    DEAD_NPC_CLEANUP_HOURS = 24  # 已击杀鬼怪24小时后清理
    ABANDONED_GHOST_CLEANUP_HOURS = 72  # 未完成任务鬼怪72小时后清理
    TEMP_LOCATION_DAYS = 7  # 临时地点7天后清理

    @staticmethod
    async def cleanup_expired_npcs():
        """清理过期的动态NPC"""
        try:
            async with safe_session() as session:
                current_time = datetime.now()

                # 1. 清理已死亡的鬼怪NPC（24小时前）
                dead_cutoff = current_time - timedelta(hours=NPCLocationCleanup.DEAD_NPC_CLEANUP_HOURS)
                dead_stmt = select(NPC).where(
                    and_(
                        NPC.is_dynamic == True,
                        NPC.npc_type == NPCType.GHOST.value,
                        NPC.status == NPCStatus.DEAD.value,
                        NPC.created_at < dead_cutoff
                    )
                )
                dead_npcs = (await session.execute(dead_stmt)).scalars().all()

                # 2. 清理未完成任务的鬼怪NPC（72小时前）
                abandoned_cutoff = current_time - timedelta(hours=NPCLocationCleanup.ABANDONED_GHOST_CLEANUP_HOURS)
                abandoned_stmt = select(NPC).where(
                    and_(
                        NPC.is_dynamic == True,
                        NPC.npc_type == NPCType.GHOST.value,
                        NPC.status != NPCStatus.DEAD.value,  # 未死亡的
                        NPC.created_at < abandoned_cutoff
                    )
                )
                abandoned_npcs = (await session.execute(abandoned_stmt)).scalars().all()

                # 执行清理
                cleanup_count = 0

                # 清理已死亡的鬼怪
                for npc in dead_npcs:
                    logger.info(f"🧹 清理已死亡鬼怪: {npc.npc_id} ({npc.name}) - 创建于 {npc.created_at}")
                    await session.delete(npc)
                    cleanup_count += 1

                # 清理未完成任务的鬼怪
                for npc in abandoned_npcs:
                    logger.info(f"🧹 清理未完成任务鬼怪: {npc.npc_id} ({npc.name}) - 创建于 {npc.created_at}")
                    await session.delete(npc)
                    cleanup_count += 1

                if cleanup_count > 0:
                    await session.commit()
                    logger.info(f"✅ NPC清理完成: 共清理 {cleanup_count} 个过期鬼怪")
                else:
                    logger.debug("🧹 NPC清理: 没有需要清理的过期鬼怪")

                return cleanup_count

        except Exception as e:
            logger.error(f"❌ NPC清理任务失败: {e}", exc_info=True)
            return 0

    @staticmethod
    async def cleanup_expired_locations():
        """清理过期的临时地点"""
        try:
            async with safe_session() as session:
                current_time = datetime.now()
                cutoff_time = current_time - timedelta(days=NPCLocationCleanup.TEMP_LOCATION_DAYS)

                # 查找过期或超过7天的临时地点
                stmt = select(Location).where(
                    and_(
                        Location.location_id.like("task_location_%"),  # 任务临时地点
                        Location.created_at < cutoff_time  # 创建时间超过7天
                    )
                )
                expired_locations = (await session.execute(stmt)).scalars().all()

                if not expired_locations:
                    logger.debug("🧹 Location清理: 没有需要清理的过期地点")
                    return 0

                cleanup_count = 0
                for location in expired_locations:
                    # 检查该地点是否还有活跃的NPC
                    npc_check = select(NPC).where(
                        and_(
                            NPC.location_id == location.id,
                            NPC.is_active == True
                        )
                    )
                    active_npcs = (await session.execute(npc_check)).scalars().all()

                    if active_npcs:
                        logger.debug(f"⚠️ 跳过清理地点 {location.location_id}: 还有 {len(active_npcs)} 个活跃NPC")
                        continue

                    logger.info(f"🧹 清理过期临时地点: {location.location_id} ({location.name}) - 创建于 {location.created_at}")
                    await session.delete(location)
                    cleanup_count += 1

                if cleanup_count > 0:
                    await session.commit()
                    logger.info(f"✅ Location清理完成: 共清理 {cleanup_count} 个过期临时地点")
                else:
                    logger.debug("🧹 Location清理: 没有需要清理的地点")

                return cleanup_count

        except Exception as e:
            logger.error(f"❌ Location清理任务失败: {e}", exc_info=True)
            return 0

    @staticmethod
    async def get_cleanup_stats():
        """获取清理统计信息"""
        try:
            async with safe_session() as session:
                # 统计动态鬼怪NPC
                ghost_stmt = select(NPC).where(
                    and_(
                        NPC.is_dynamic == True,
                        NPC.npc_type == NPCType.GHOST.value
                    )
                )
                all_ghosts = (await session.execute(ghost_stmt)).scalars().all()

                alive_ghosts = [g for g in all_ghosts if g.status != NPCStatus.DEAD.value]
                dead_ghosts = [g for g in all_ghosts if g.status == NPCStatus.DEAD.value]

                # 统计临时地点
                location_stmt = select(Location).where(
                    Location.location_id.like("task_location_%")
                )
                temp_locations = (await session.execute(location_stmt)).scalars().all()

                stats = {
                    "total_ghost_npcs": len(all_ghosts),
                    "alive_ghost_npcs": len(alive_ghosts),
                    "dead_ghost_npcs": len(dead_ghosts),
                    "temp_locations": len(temp_locations),
                }

                return stats

        except Exception as e:
            logger.error(f"❌ 获取清理统计失败: {e}")
            return {}


@driver.on_startup
async def setup_npc_location_cleanup():
    """设置NPC和Location清理定时任务"""
    try:
        # 检查任务是否已存在，避免重复设置
        existing_job = scheduler.get_job("npc_location_cleanup")
        if existing_job:
            logger.info("⚠️ NPC和Location清理定时任务已存在，跳过设置")
            return

        # 添加每天凌晨2点执行的清理任务
        scheduler.add_job(
            func=perform_npc_location_cleanup,
            trigger="cron",
            hour=2,  # 每天凌晨2点执行
            id="npc_location_cleanup",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        logger.info("✅ NPC和Location清理定时任务已设置 - 每天凌晨2点执行")
        logger.info(
            f"📋 清理规则: "
            f"已死亡鬼怪{NPCLocationCleanup.DEAD_NPC_CLEANUP_HOURS}小时清理, "
            f"未完成任务鬼怪{NPCLocationCleanup.ABANDONED_GHOST_CLEANUP_HOURS}小时清理, "
            f"临时地点{NPCLocationCleanup.TEMP_LOCATION_DAYS}天清理"
        )

    except Exception as e:
        logger.error(f"❌ 设置NPC和Location清理定时任务失败: {e}")


async def perform_npc_location_cleanup():
    """执行NPC和Location清理"""
    try:
        logger.info("🔄 开始执行NPC和Location清理...")

        # 获取清理前统计
        before_stats = await NPCLocationCleanup.get_cleanup_stats()
        logger.info(
            f"📊 清理前统计: "
            f"鬼怪NPC {before_stats.get('total_ghost_npcs', 0)}个 "
            f"(存活{before_stats.get('alive_ghost_npcs', 0)}/死亡{before_stats.get('dead_ghost_npcs', 0)}), "
            f"临时地点 {before_stats.get('temp_locations', 0)}个"
        )

        # 清理NPC
        npc_cleanup_count = await NPCLocationCleanup.cleanup_expired_npcs()

        # 清理Location
        location_cleanup_count = await NPCLocationCleanup.cleanup_expired_locations()

        # 获取清理后统计
        after_stats = await NPCLocationCleanup.get_cleanup_stats()

        logger.info(
            f"✅ NPC和Location清理完成: "
            f"清理NPC {npc_cleanup_count}个, "
            f"清理Location {location_cleanup_count}个. "
            f"剩余鬼怪NPC {after_stats.get('total_ghost_npcs', 0)}个, "
            f"临时地点 {after_stats.get('temp_locations', 0)}个"
        )

    except Exception as e:
        logger.error(f"❌ NPC和Location清理任务失败: {e}", exc_info=True)


@driver.on_shutdown
async def cleanup_npc_location_scheduler():
    """清理NPC和Location清理调度器"""
    try:
        if scheduler.get_job("npc_location_cleanup"):
            scheduler.remove_job("npc_location_cleanup")
            logger.info("🧹 NPC和Location清理定时任务已清理")
    except Exception as e:
        logger.error(f"❌ 清理NPC和Location清理定时任务失败: {e}")
