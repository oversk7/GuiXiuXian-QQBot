"""宠物状态衰减定时任务"""
from nonebot import require, logger
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler
from sqlalchemy import update, func, case
from ..models.db import AsyncSessionLocal
from ..models.pet_instance import PetInstance
from .config import PetConfigManager


@scheduler.scheduled_job("interval", hours=1, id="pet_status_decay")
async def pet_status_decay():
    """每小时执行一次宠物状态衰减（批量UPDATE，不逐条加载）"""
    config = PetConfigManager()
    hunger_decay = config.settings["hunger_decay_per_hour"]
    mood_decay = config.settings["mood_decay_per_hour"]
    hungry_threshold = config.settings["hungry_threshold"]
    affection_decay_starving = config.settings.get("affection_decay_when_starving", 2)
    affection_decay_sad = config.settings.get("affection_decay_when_sad", 1)
    affection_sad_threshold = config.settings.get("affection_sad_threshold", 20)

    async with AsyncSessionLocal() as session:
        # 批量更新饱食度
        await session.execute(
            update(PetInstance).values(
                hunger=func.greatest(0, PetInstance.hunger - hunger_decay)
            )
        )

        # 批量更新心情（饥饿时加速下降）
        await session.execute(
            update(PetInstance).values(
                mood=func.greatest(0, PetInstance.mood - case(
                    (PetInstance.hunger < hungry_threshold, mood_decay * 3),
                    else_=mood_decay
                ))
            )
        )

        # 好感度衰减：长期挨饿（hunger=0）
        await session.execute(
            update(PetInstance)
            .where(PetInstance.hunger == 0)
            .values(affection=func.greatest(0, PetInstance.affection - affection_decay_starving))
        )

        # 好感度衰减：情绪持续极差（mood<阈值），可与饥饿惩罚叠加
        await session.execute(
            update(PetInstance)
            .where(PetInstance.mood < affection_sad_threshold)
            .values(affection=func.greatest(0, PetInstance.affection - affection_decay_sad))
        )

        await session.commit()
        logger.info("[PetScheduler] 状态衰减完成")
