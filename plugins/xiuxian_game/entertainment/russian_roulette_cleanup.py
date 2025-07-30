"""
俄罗斯轮盘房间自动清理机制
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from nonebot import get_driver
from nonebot_plugin_apscheduler import scheduler

from ..models.db import safe_session
from ..models.russian_roulette import RussianRouletteRoom, RussianRouletteGame, RoomStatus, GameStatus
from ..models.inventory import ItemInstance
from ..models.player import Player

logger = logging.getLogger(__name__)

driver = get_driver()


class RussianRouletteCleanup:
    """俄罗斯轮盘房间清理服务"""
    
    # 清理配置
    INACTIVE_TIMEOUT_MINUTES = 30  # 30分钟无活动自动清理
    WAITING_TIMEOUT_MINUTES = 60   # 等待状态房间60分钟自动清理
    
    @staticmethod
    async def cleanup_inactive_rooms():
        """清理长时间无活动的房间"""
        try:
            async with safe_session() as session:
                current_time = datetime.now()
                
                # 计算超时时间点
                inactive_cutoff = current_time - timedelta(minutes=RussianRouletteCleanup.INACTIVE_TIMEOUT_MINUTES)
                waiting_cutoff = current_time - timedelta(minutes=RussianRouletteCleanup.WAITING_TIMEOUT_MINUTES)
                
                # 查找需要清理的房间
                stmt = select(RussianRouletteRoom).where(
                    and_(
                        RussianRouletteRoom.status.in_([
                            RoomStatus.WAITING.value, 
                            RoomStatus.BETTING.value, 
                            RoomStatus.PLAYING.value
                        ]),
                        # 等待状态的房间60分钟清理，其他状态30分钟清理
                        or_(
                            and_(
                                RussianRouletteRoom.status == RoomStatus.WAITING.value,
                                RussianRouletteRoom.updated_at < waiting_cutoff
                            ),
                            and_(
                                RussianRouletteRoom.status.in_([RoomStatus.BETTING.value, RoomStatus.PLAYING.value]),
                                RussianRouletteRoom.updated_at < inactive_cutoff
                            )
                        )
                    )
                )
                
                rooms_to_cleanup = (await session.execute(stmt)).scalars().all()
                
                if not rooms_to_cleanup:
                    logger.debug("🧹 俄罗斯轮盘房间清理：没有需要清理的房间")
                    return
                
                cleanup_count = 0
                for room in rooms_to_cleanup:
                    try:
                        await RussianRouletteCleanup._cleanup_single_room(session, room)
                        cleanup_count += 1
                    except Exception as e:
                        logger.error(f"❌ 清理房间 {room.room_id} 失败: {e}")
                
                await session.commit()
                
                if cleanup_count > 0:
                    logger.info(f"🧹 俄罗斯轮盘房间清理完成：清理了 {cleanup_count} 个无活动房间")
                
        except Exception as e:
            logger.error(f"❌ 俄罗斯轮盘房间清理任务失败: {e}")
    
    @staticmethod
    async def _cleanup_single_room(session: AsyncSession, room: RussianRouletteRoom):
        """清理单个房间"""
        logger.info(f"🧹 清理无活动房间: {room.room_id} (状态: {room.status}, 最后活动: {room.updated_at})")
        
        # 返还玩家筹码
        await RussianRouletteCleanup._refund_room_bets(session, room)
        
        # 删除相关游戏记录
        game_stmt = select(RussianRouletteGame).where(RussianRouletteGame.room_id == room.room_id)
        games = (await session.execute(game_stmt)).scalars().all()
        for game in games:
            await session.delete(game)
        
        # 删除房间
        await session.delete(room)
    
    @staticmethod
    async def _refund_room_bets(session: AsyncSession, room: RussianRouletteRoom):
        """返还房间内玩家的筹码"""
        try:
            # 返还玩家1的筹码
            if room.player1_gold_bet > 0 or room.player1_items_bet:
                player1 = await session.get(Player, room.player1_id)
                if player1:
                    if room.player1_gold_bet > 0:
                        player1.gold += room.player1_gold_bet
                        logger.debug(f"返还玩家1 {room.player1_id} 金币: {room.player1_gold_bet}")
                    
                    if room.player1_items_bet:
                        import json
                        items = json.loads(room.player1_items_bet)
                        for item_id in items:
                            await ItemInstance.add_item(session, room.player1_id, item_id, 1)
                        logger.debug(f"返还玩家1 {room.player1_id} 道具: {len(items)}个")
            
            # 返还玩家2的筹码
            if room.player2_id and (room.player2_gold_bet > 0 or room.player2_items_bet):
                player2 = await session.get(Player, room.player2_id)
                if player2:
                    if room.player2_gold_bet > 0:
                        player2.gold += room.player2_gold_bet
                        logger.debug(f"返还玩家2 {room.player2_id} 金币: {room.player2_gold_bet}")
                    
                    if room.player2_items_bet:
                        import json
                        items = json.loads(room.player2_items_bet)
                        for item_id in items:
                            await ItemInstance.add_item(session, room.player2_id, item_id, 1)
                        logger.debug(f"返还玩家2 {room.player2_id} 道具: {len(items)}个")
                        
        except Exception as e:
            logger.error(f"❌ 返还房间 {room.room_id} 筹码失败: {e}")


@driver.on_startup
async def setup_russian_roulette_cleanup():
    """设置俄罗斯轮盘房间清理定时任务"""
    try:
        # 检查任务是否已存在，避免重复设置
        existing_job = scheduler.get_job("russian_roulette_cleanup")
        if existing_job:
            logger.info("⚠️ 俄罗斯轮盘房间清理定时任务已存在，跳过设置")
            return

        # 添加每10分钟执行一次的清理任务
        scheduler.add_job(
            func=RussianRouletteCleanup.cleanup_inactive_rooms,
            trigger="interval",
            minutes=10,  # 每10分钟执行一次
            id="russian_roulette_cleanup",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        logger.info("✅ 俄罗斯轮盘房间清理定时任务已设置 - 每10分钟执行一次")
        logger.info(f"📋 清理规则: 等待状态房间{RussianRouletteCleanup.WAITING_TIMEOUT_MINUTES}分钟无活动清理，其他状态{RussianRouletteCleanup.INACTIVE_TIMEOUT_MINUTES}分钟无活动清理")

    except Exception as e:
        logger.error(f"❌ 设置俄罗斯轮盘房间清理定时任务失败: {e}")


@driver.on_shutdown
async def cleanup_russian_roulette_scheduler():
    """清理俄罗斯轮盘房间清理调度器"""
    try:
        if scheduler.get_job("russian_roulette_cleanup"):
            scheduler.remove_job("russian_roulette_cleanup")
            logger.info("🧹 俄罗斯轮盘房间清理定时任务已清理")
    except Exception as e:
        logger.error(f"❌ 清理俄罗斯轮盘房间清理定时任务失败: {e}")
