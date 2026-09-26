"""
装备业务逻辑服务

提供装备相关的核心业务逻辑：
1. 重新计算装备属性加成（EquipmentService，DI架构）
2. 处理 mp_from_hp / hp_from_attack 特效
3. 装备相关常量定义
4. 模块级入口 recalc_equipment_attributes（兼容旧的 session 直传调用风格）
"""

from typing import Optional
from ..models import Player, ItemInstance
from ..config import config
from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.repositories.player_repository import PlayerRepository
from .attribute_preview_service import MAIN_ATTRS, equipment_delta, conversion_parts


# 获取所有装备物品ID
EQUIP_ITEM_IDS = config.items_config["by_type"]["EQUIPMENT"]

ATTR_NAME_MAP = {
    "attack": "攻击力", "defense": "防御力", "agility": "敏捷",
    "luck": "运气", "hp": "生命值", "mp": "理智值",
    "max_hp": "最大生命值", "max_mp": "最大理智值",
}

VIP_EQUIPMENT_IDS = frozenset(
    item_id for item_id in EQUIP_ITEM_IDS
    if getattr(config.items_config["by_id"].get(item_id), "rarity", None) == "red"
)


class EquipmentService:
    """装备服务（DI架构）"""

    def __init__(
        self,
        item_repo: ItemRepository,
        player_repo: PlayerRepository
    ):
        """
        初始化装备服务

        Args:
            item_repo: 物品仓储
            player_repo: 玩家仓储
        """
        self._item_repo = item_repo
        self._player_repo = player_repo

    async def recalc_equipment_attributes(
        self,
        player: Player,
        equipped_items: Optional[list[ItemInstance]] = None,
    ) -> None:
        """
        重新计算玩家当前装备提供的属性加成（包含 mp_from_hp 特效）

        Args:
            player: 玩家对象
            equipped_items: 已装备物品列表（可选，若为None则自动查询）
        """
        # 如果未提供装备列表，从数据库查询
        if equipped_items is None:
            equipped_items = await self._item_repo.get_equipped_equipment(
                player.id,
                EQUIP_ITEM_IDS
            )

        # 如果没有装备，仅确保HP/MP不超过上限
        if not equipped_items:
            if player.hp > player.max_hp:
                player.hp = player.max_hp
            if player.mp > player.max_mp:
                player.mp = player.max_mp
            await self._player_repo.update(player)
            return

        # 1. 先移除所有已记录的装备加成
        # 注意：只处理equipped=True的装备，跳过已卸下的（equipped=False）
        # 因为"卸下装备"命令会在调用recalc前手动移除属性
        for eq in equipped_items:
            if not getattr(eq, "equipped", False):
                continue
            delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
            for k, v in delta.items():
                current_value = getattr(player, k, 0)
                setattr(player, k, max(0, current_value - int(v or 0)))

            if "_persist_bonus" in (eq.extra_attrs or {}):
                extra_new = {k: v for k, v in eq.extra_attrs.items() if k != "_persist_bonus"}
                eq.extra_attrs = extra_new

            eq.equipped = False

        # 2. 基于当前基础属性重新应用装备加成
        # 注意：此时player属性已经是真实的无装备基础属性
        base_attrs = {key: getattr(player, key) for key in MAIN_ATTRS}

        # 3. 重新应用装备加成
        for eq in equipped_items:
            eq.equipped = True
            new_delta = equipment_delta(eq, base_attrs)

            for k, v in new_delta.items():
                setattr(player, k, getattr(player, k) + v)

            extra = eq.extra_attrs or {}
            extra["_persist_bonus"] = new_delta
            eq.extra_attrs = extra

        # 批量更新装备的extra_attrs
        await self._item_repo.update_extra_attrs_batch(equipped_items)

        # 4. 再处理 mp_from_hp 类全局被动（只处理equipped=True的装备）
        equipped_only = [eq for eq in equipped_items if getattr(eq, "equipped", False)]
        await self._apply_mp_from_hp_effects(player, equipped_only)

        # 4b. 再处理 hp_from_attack 类全局被动（诡面骰骰相·命，以总攻击力为基数）
        await self._apply_hp_from_attack_effects(player, equipped_only)

        # 5. 确保当前 HP/MP 不超过新的上限
        if player.hp > player.max_hp:
            player.hp = player.max_hp
        if player.mp > player.max_mp:
            player.mp = player.max_mp

        # 更新玩家
        await self._player_repo.update(player)

    async def _apply_mp_from_hp_effects(
        self,
        player: Player,
        equipped_items: list[ItemInstance]
    ) -> None:
        """
        将拥有 mp_from_hp 特效的装备的加成重新应用到玩家身上

        Args:
            player: 玩家对象
            equipped_items: 已装备物品列表
        """
        if not equipped_items:
            return

        parts = conversion_parts(
            equipped_items, "mp_from_hp", max(1, int(getattr(player, "max_hp", 0) or 0))
        )
        if not parts:
            return

        for eq, part in parts:
            player.max_mp = int(getattr(player, "max_mp", 0)) + part

            extra = eq.extra_attrs or {}
            persist = dict(extra.get("_persist_bonus", {}))
            persist["max_mp"] = int(persist.get("max_mp", 0)) + part
            extra["_persist_bonus"] = persist
            eq.extra_attrs = extra

        # 批量更新装备的extra_attrs
        await self._item_repo.update_extra_attrs_batch(equipped_items)

    async def _apply_hp_from_attack_effects(
        self,
        player,
        equipped_items: list,
    ) -> None:
        """将拥有 hp_from_attack 特效的装备的加成持久写入玩家属性。

        以穿装备后的总攻击力为基数，按百分比计算 max_hp 加成，
        写入 player.max_hp 并记录到 _persist_bonus["max_hp"]。
        """
        if not equipped_items:
            return

        parts = conversion_parts(
            equipped_items, "hp_from_attack", max(1, int(getattr(player, "attack", 0) or 0))
        )
        if not parts:
            return

        for eq, part in parts:
            player.max_hp = int(getattr(player, "max_hp", 0)) + part

            extra = eq.extra_attrs or {}
            persist = dict(extra.get("_persist_bonus", {}))
            persist["max_hp"] = int(persist.get("max_hp", 0)) + part
            extra["_persist_bonus"] = persist
            eq.extra_attrs = extra

        await self._item_repo.update_extra_attrs_batch(equipped_items)


async def recalc_equipment_attributes(
    session,
    player: Player,
    equipped_items: Optional[list[ItemInstance]] = None,
) -> None:
    """重新计算玩家当前装备提供的属性加成（模块级入口）。

    基于调用方传入的 session 构造仓储并委托给 EquipmentService，
    不新开会话、不提交事务，与原静态实现语义一致。
    """
    service = EquipmentService(
        item_repo=ItemRepository(session),
        player_repo=PlayerRepository(session),
    )
    await service.recalc_equipment_attributes(player, equipped_items)
