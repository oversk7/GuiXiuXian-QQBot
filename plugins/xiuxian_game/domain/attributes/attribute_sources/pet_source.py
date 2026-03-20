"""宠物属性来源 - 为玩家提供宠物伴侣的被动战斗加成"""
import time
from typing import Dict, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from nonebot import logger

from ..interfaces import IAttributeSource, AttributeBonus


class PetAttributeSource(IAttributeSource):
    """
    宠物属性来源

    查询玩家当前激活的宠物，计算其提供的属性加成。
    使用60秒TTL缓存减少数据库查询。
    """

    def __init__(self, cache_ttl: float = 60.0):
        self._cache_ttl = cache_ttl
        self._cache: Dict[str, Tuple[AttributeBonus, float]] = {}

    @property
    def source_name(self) -> str:
        return "pet"

    @property
    def is_persisted(self) -> bool:
        return False

    async def calculate_bonus(self, player, session: AsyncSession) -> AttributeBonus:
        player_id = player.id

        # 检查缓存
        if player_id in self._cache:
            bonus, timestamp = self._cache[player_id]
            if time.time() - timestamp < self._cache_ttl:
                return bonus

        bonus = await self._query_pet_bonus(player_id, session)
        self._cache[player_id] = (bonus, time.time())
        return bonus

    async def _query_pet_bonus(self, player_id: str, session: AsyncSession) -> AttributeBonus:
        from ....models.pet_instance import PetInstance

        stmt = select(PetInstance).where(
            PetInstance.player_id == player_id,
            PetInstance.is_active == True
        )
        result = await session.execute(stmt)
        pet = result.scalar_one_or_none()

        if not pet:
            return AttributeBonus()

        from ....pet.config import PetConfigManager
        config = PetConfigManager()
        mood_mult = config.get_mood_multiplier(pet.mood)

        attack = int(pet.bonus_attack * mood_mult)
        defense = int(pet.bonus_defense * mood_mult)
        hp = int(pet.bonus_hp * mood_mult)
        crit_rate = round(pet.bonus_crit_rate * mood_mult, 4)
        dodge_rate = round(pet.bonus_dodge_rate * mood_mult, 4)

        # 饰品加成
        if pet.accessories:
            for acc_id in pet.accessories.values():
                acc = config.get_accessory(acc_id)
                if acc:
                    attack += int(acc.bonus.get("attack", 0))
                    defense += int(acc.bonus.get("defense", 0))
                    hp += int(acc.bonus.get("hp", 0))
                    crit_rate += acc.bonus.get("crit_rate", 0)
                    dodge_rate += acc.bonus.get("dodge_rate", 0)

        return AttributeBonus(
            attack=attack,
            defense=defense,
            hp=hp,
            max_hp=hp,
            crit_rate=crit_rate,
            dodge_rate=dodge_rate,
        )

    def invalidate_cache(self, player_id: str):
        if player_id in self._cache:
            del self._cache[player_id]

    def clear_cache(self):
        self._cache.clear()
