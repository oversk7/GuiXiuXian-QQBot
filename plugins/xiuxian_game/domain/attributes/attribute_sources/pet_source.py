"""宠物属性来源 - 为玩家提供宠物伴侣的被动战斗加成"""
import time
from typing import Dict, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


# 饰品bonus key → Player模型属性名的映射
# 小数类属性(crit_rate等)在pet_config中是0.03格式，需乘100转为百分比整数
_ACC_DECIMAL_KEYS = {"crit_rate", "dodge_rate", "combo_rate", "penetration_rate",
                     "counter_rate", "critical_damage", "lifesteal_rate",
                     "accuracy_rate", "skill_crit_rate", "anti_crit_rate"}

_ACC_TO_PLAYER = {
    "attack": "attack",
    "defense": "defense",
    "hp": "max_hp",
    "crit_rate": "critical_rate",
    "dodge_rate": "dodge_rate",
    "combo_rate": "combo_rate",
    "penetration_rate": "penetration_rate",
    "counter_rate": "counter_rate",
    "critical_damage": "critical_power",
    "lifesteal_rate": "lifesteal_rate",
    "accuracy_rate": "accuracy_rate",
    "skill_crit_rate": "skill_crit_rate",
    "anti_crit_rate": "anti_crit_rate",
}


class PetAttributeSource:
    """
    宠物属性来源

    查询玩家当前激活的宠物，计算其提供的属性加成。
    使用60秒TTL缓存减少数据库查询。
    """

    def __init__(self, cache_ttl: float = 60.0):
        self._cache_ttl = cache_ttl
        self._full_cache: Dict[str, Tuple[dict, float]] = {}

    async def calculate_full_bonus(self, player, session: AsyncSession) -> dict:
        """返回完整加成dict（使用Player模型属性名，百分比已转为整数）"""
        player_id = player.id

        if player_id in self._full_cache:
            full_dict, timestamp = self._full_cache[player_id]
            if time.time() - timestamp < self._cache_ttl:
                return full_dict

        full_dict = await self._query_pet_full_bonus(player_id, session)
        now = time.time()
        self._full_cache[player_id] = (full_dict, now)
        return full_dict

    async def _query_pet_full_bonus(self, player_id: str, session: AsyncSession) -> dict:
        """查询宠物完整加成，返回使用Player模型属性名的dict"""
        from ....models.pet_instance import PetInstance

        stmt = select(PetInstance).where(
            PetInstance.player_id == player_id,
            PetInstance.is_active == True
        )
        result = await session.execute(stmt)
        pet = result.scalar_one_or_none()

        if not pet:
            return {}

        from ....pet.config import PetConfigManager
        config = PetConfigManager()
        mood_mult = config.get_mood_multiplier(pet.mood)

        # 宠物等级基础加成（整数属性）
        raw = {
            "attack": int(pet.bonus_attack * mood_mult),
            "defense": int(pet.bonus_defense * mood_mult),
            "hp": int(pet.bonus_hp * mood_mult),
            "crit_rate": round(pet.bonus_crit_rate * mood_mult, 4),
            "dodge_rate": round(pet.bonus_dodge_rate * mood_mult, 4),
        }

        # 饰品加成（累加所有饰品的所有bonus key）
        if pet.accessories:
            for acc_id in pet.accessories.values():
                acc = config.get_accessory(acc_id)
                if acc:
                    for key, val in acc.bonus.items():
                        raw[key] = raw.get(key, 0) + val

        # 转换为Player模型属性名，小数类乘100
        out = {}
        for raw_key, val in raw.items():
            player_key = _ACC_TO_PLAYER.get(raw_key)
            if not player_key:
                continue
            if raw_key in _ACC_DECIMAL_KEYS:
                val = round(val * 100, 1)
            else:
                val = int(val)
            out[player_key] = out.get(player_key, 0) + val

        # hp → max_hp（等级基础hp也映射到max_hp）
        if "hp" in raw and "max_hp" not in _ACC_TO_PLAYER.get("hp", ""):
            pass  # 已在_ACC_TO_PLAYER中映射

        return out

    def invalidate_cache(self, player_id: str):
        if player_id in self._full_cache:
            del self._full_cache[player_id]

    def clear_cache(self):
        self._full_cache.clear()


# 全局单例：宠物加成缓存全局共享
_instance: Optional[PetAttributeSource] = None


def get_pet_source() -> PetAttributeSource:
    """获取宠物属性来源单例"""
    global _instance
    if _instance is None:
        _instance = PetAttributeSource()
    return _instance


def invalidate_pet_cache(player_id: str):
    """使指定玩家的宠物属性缓存失效（宠物激活/喂食/进化/饰品变更后调用）"""
    if _instance:
        _instance.invalidate_cache(player_id)
