"""
装备业务逻辑服务（DI架构版本）

提供装备相关的核心业务逻辑：
1. 重新计算装备属性加成
2. 处理 mp_from_hp 特效
3. 装备相关常量定义

此版本采用依赖注入架构，通过Repository访问数据。
"""

from typing import Optional
from ..models import Player, ItemInstance
from ..config import config
from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.repositories.player_repository import PlayerRepository


# 获取所有装备物品ID
EQUIP_ITEM_IDS = config.items_config["by_type"]["EQUIPMENT"]


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
        base_attrs = {
            "attack": player.attack,
            "defense": player.defense,
            "agility": player.agility,
            "luck": player.luck,
            "max_hp": player.max_hp,
            "max_mp": player.max_mp,
        }

        for eq in equipped_items:
            eq.equipped = True

            attrs_temp = base_attrs.copy()
            eq.apply_attr_bonus(attrs_temp, base_attrs)
            new_delta = {}
            for k in attrs_temp:
                if k in base_attrs:
                    if attrs_temp[k] != base_attrs[k]:
                        new_delta[k] = attrs_temp[k] - base_attrs[k]
                else:
                    if attrs_temp[k] != 0:
                        new_delta[k] = attrs_temp[k]

            for k, v in new_delta.items():
                setattr(player, k, getattr(player, k) + v)

            extra = eq.extra_attrs or {}
            extra["_persist_bonus"] = new_delta
            eq.extra_attrs = extra

        # 批量更新装备的extra_attrs
        await self._item_repo.update_extra_attrs_batch(equipped_items)

        # 3. 再处理 mp_from_hp 类全局被动
        await self._apply_mp_from_hp_effects(player, equipped_items)

        # 4. 确保当前 HP/MP 不超过新的上限
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

        mp_from_hp_effects: list[tuple[ItemInstance, float, int, bool]] = []
        total_pct = 0.0
        total_flat = 0

        for eq in equipped_items:
            if not getattr(eq, "equipped", False):
                continue
            cfg = eq.config if hasattr(eq, "config") else None
            if not cfg or not getattr(cfg, "special_effects", None):
                continue

            for eff in cfg.special_effects:
                if eff.get("effect") != "mp_from_hp":
                    continue
                is_pct = bool(eff.get("is_percentage", True))
                if is_pct:
                    val_pct = float(eff.get("value", 0) or 0)
                    if val_pct > 0:
                        total_pct += val_pct
                        mp_from_hp_effects.append((eq, val_pct, 0, True))
                else:
                    val_flat = int(eff.get("value", 0) or 0)
                    if val_flat > 0:
                        total_flat += val_flat
                        mp_from_hp_effects.append((eq, 0.0, val_flat, False))

        if not mp_from_hp_effects:
            return

        current_hp_after_all = int(getattr(player, "max_hp", 0) or 0)
        hp_from_self_equips = 0
        for eq, _, _, _ in mp_from_hp_effects:
            delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
            hp_from_self_equips += int(delta.get("max_hp", 0) or 0)

        base_for_convert = max(1, current_hp_after_all - hp_from_self_equips)
        bonus_from_pct = int(base_for_convert * total_pct / 100.0) if total_pct > 0 else 0
        total_bonus_mp = bonus_from_pct + int(total_flat)
        if total_bonus_mp <= 0:
            return

        remaining = total_bonus_mp
        for idx, (eq, pct, flat, is_pct) in enumerate(mp_from_hp_effects):
            part = 0
            if is_pct and pct > 0:
                part = int(base_for_convert * pct / 100.0)
            elif (not is_pct) and flat > 0:
                part = int(flat)

            if idx == len(mp_from_hp_effects) - 1:
                part = remaining
            else:
                part = min(part, remaining)

            if part <= 0:
                continue

            remaining = max(0, remaining - part)
            player.max_mp = int(getattr(player, "max_mp", 0)) + part

            extra = eq.extra_attrs or {}
            persist = dict(extra.get("_persist_bonus", {}))
            persist["max_mp"] = int(persist.get("max_mp", 0)) + part
            extra["_persist_bonus"] = persist
            eq.extra_attrs = extra

        # 批量更新装备的extra_attrs
        await self._item_repo.update_extra_attrs_batch(equipped_items)
