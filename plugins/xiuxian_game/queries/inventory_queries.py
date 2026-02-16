"""
背包查询模块 (CQRS Query Side)

在 DB 层完成过滤和分页，避免加载全部物品到内存再 Python 过滤。
"""

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from . import readonly_session
from ..models.inventory import ItemInstance, ItemType
from ..config import config


def _get_item_ids_by_category(category_key: str) -> list[str] | None:
    """根据分类标识获取对应的 item_id 列表

    Returns:
        item_id 列表，如果无法映射则返回 None
    """
    items_by_id = config.items_config.get("by_id", {})

    if category_key == "ELIXIR":
        return [iid for iid in items_by_id if iid.endswith("_elixir")]
    elif category_key == "CONSUMABLE":
        # 普通消耗品（不含丹药）
        return [
            iid for iid, cfg in items_by_id.items()
            if cfg.type == ItemType.CONSUMABLE and not iid.endswith("_elixir")
        ]
    else:
        # 其他类型直接匹配
        return [
            iid for iid, cfg in items_by_id.items()
            if cfg.type.value == category_key
        ]


def _get_equipment_item_ids() -> list[str]:
    """获取所有装备类 item_id"""
    return config.items_config.get("by_type", {}).get("EQUIPMENT", [])


def _get_fish_item_ids() -> list[str]:
    """获取所有鱼类 item_id"""
    items_by_id = config.items_config.get("by_id", {})
    return [iid for iid, cfg in items_by_id.items() if getattr(cfg, "is_fish", False)]


@dataclass
class InventoryPage:
    """背包分页结果"""
    items: list[ItemInstance]
    total_items: int  # 当前过滤条件下的总物品种类数
    page: int
    page_size: int
    used_slots: int  # 已使用的背包格数（不含装备和鱼）
    effective_capacity: int  # 有效容量

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items - 1) // self.page_size + 1)


async def query_inventory_page(
    player_id: str,
    category: str | None = None,
    page: int = 1,
    page_size: int = 15,
    exclude_equipment: bool = True,
    exclude_fish: bool = True,
) -> tuple[list[ItemInstance], int]:
    """在 DB 层完成过滤和分页

    Args:
        player_id: 玩家 ID
        category: 内部分类标识（如 "MATERIAL", "ELIXIR"），None 表示全部
        page: 页码（1-indexed）
        page_size: 每页大小
        exclude_equipment: 是否排除装备
        exclude_fish: 是否排除鱼类

    Returns:
        (当前页的 ItemInstance 列表, 过滤后的总数)
    """
    async with readonly_session() as session:
        # 构建基础条件
        conditions = [
            ItemInstance.player_id == player_id,
            ItemInstance.quantity > 0,
        ]

        # 排除装备和鱼类
        exclude_ids: set[str] = set()
        if exclude_equipment:
            exclude_ids.update(_get_equipment_item_ids())
        if exclude_fish:
            exclude_ids.update(_get_fish_item_ids())

        if exclude_ids:
            conditions.append(ItemInstance.item_id.notin_(list(exclude_ids)))

        # 分类过滤
        if category:
            category_ids = _get_item_ids_by_category(category)
            if category_ids is not None:
                conditions.append(ItemInstance.item_id.in_(category_ids))

        # 查询总数
        count_stmt = select(func.count()).select_from(ItemInstance).where(*conditions)
        total = (await session.execute(count_stmt)).scalar_one()

        if total == 0:
            return [], 0

        # 分页查询
        offset = (max(1, page) - 1) * page_size
        items_stmt = (
            select(ItemInstance)
            .where(*conditions)
            .order_by(ItemInstance.item_id)
            .offset(offset)
            .limit(page_size)
        )
        items = (await session.execute(items_stmt)).scalars().all()

        return list(items), total


async def query_inventory_usage(player_id: str) -> tuple[int, int]:
    """查询背包容量使用情况

    Returns:
        (已用格数, 总物品行数含装备鱼)  —— 不含装备和鱼的格数
    """
    exclude_ids: set[str] = set()
    exclude_ids.update(_get_equipment_item_ids())
    exclude_ids.update(_get_fish_item_ids())

    async with readonly_session() as session:
        conditions = [
            ItemInstance.player_id == player_id,
            ItemInstance.quantity > 0,
        ]
        if exclude_ids:
            conditions.append(ItemInstance.item_id.notin_(list(exclude_ids)))

        count_stmt = select(func.count()).select_from(ItemInstance).where(*conditions)
        used_slots = (await session.execute(count_stmt)).scalar_one()

    return used_slots
