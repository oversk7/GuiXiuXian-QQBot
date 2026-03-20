"""宠物状态衰减定时任务"""
from nonebot import require, logger
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler
from sqlalchemy import select
from ..models.db import AsyncSessionLocal
from ..models.pet_instance import PetInstance
from .config import PetConfigManager


@scheduler.scheduled_job("interval", hours=1, id="pet_status_decay")
async def pet_status_decay():
    """每小时执行一次宠物状态衰减"""
    config = PetConfigManager()
    hunger_decay = config.settings["hunger_decay_per_hour"]
    mood_decay = config.settings["mood_decay_per_hour"]
    hungry_threshold = config.settings["hungry_threshold"]

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(PetInstance))
        pets = result.scalars().all()

        updated = 0
        for pet in pets:
            pet.hunger = max(0, pet.hunger - hunger_decay)
            # 饥饿时心情加速下降
            actual_mood_decay = mood_decay * 3 if pet.hunger < hungry_threshold else mood_decay
            pet.mood = max(0, pet.mood - actual_mood_decay)
            updated += 1

        await session.commit()
        logger.info(f"[PetScheduler] 状态衰减完成，更新{updated}只宠物")
