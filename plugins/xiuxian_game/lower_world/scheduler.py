"""
下位世界定时任务

每2小时：为所有未封印、没有待挑战英雄的山寨生成新一波英雄。
注意：QQ 不支持主动发消息，玩家通过主动查【镇守】或【迎战】发现英雄到来。
"""
from datetime import datetime

from nonebot import get_driver, logger
from nonebot_plugin_apscheduler import scheduler

from ..models.db import AsyncSessionLocal
from ..infrastructure.uow.unit_of_work import UnitOfWork

driver = get_driver()


@scheduler.scheduled_job("interval", hours=2, id="lower_world_wave_push")
async def generate_hero_waves():
    """
    每2小时执行一次：
    1. 查出所有山寨
    2. 跳过封印中的
    3. 跳过 next_wave_at 还未到时间的（上一波还没过期）
    4. 跳过已有 pending_hero 且未超时的
    5. 其余山寨安排新一波英雄
    """
    logger.info("[下位世界] 开始生成英雄波次...")

    try:
        from sqlalchemy import select
        from ..models.lower_world import LowerWorldStronghold
        from ..models.player import Player
        from .service import has_pending_hero, schedule_next_wave

        async with UnitOfWork(AsyncSessionLocal) as uow:
            result = await uow.session.execute(select(LowerWorldStronghold))
            all_strongholds = result.scalars().all()

            pushed_count = 0
            for stronghold in all_strongholds:
                # 跳过封印中的
                if stronghold.sealed_until and datetime.now() < stronghold.sealed_until:
                    continue

                # 跳过已有未超时英雄的
                if has_pending_hero(stronghold):
                    continue

                # 跳过 next_wave_at 还没到的（刚打完，下一波还没到时间）
                if stronghold.next_wave_at and datetime.now() < stronghold.next_wave_at:
                    continue

                # 获取玩家等级用于生成英雄
                player_result = await uow.session.execute(
                    select(Player).where(Player.id == stronghold.player_id)
                )
                player = player_result.scalar_one_or_none()
                if not player:
                    continue

                await schedule_next_wave(uow, stronghold, player.level)
                pushed_count += 1

            await uow.commit()
            logger.info(f"[下位世界] 波次生成完成，共处理 {pushed_count} 个山寨")

    except Exception as e:
        logger.error(f"[下位世界] 波次生成任务失败: {e}")


@driver.on_startup
async def on_startup():
    logger.info("[下位世界] 定时任务已注册：每2小时生成英雄波次")
