"""
物品仓储实现（占位符）

TODO: 完整实现
"""

from typing import Optional, List
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.inventory import ItemInstance


class ItemRepository(IRepository[ItemInstance]):
    """物品仓储实现"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, item_id: str) -> Optional[ItemInstance]:
        stmt = select(ItemInstance).where(ItemInstance.id == item_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_equipped_items(self, player_id: str) -> List[ItemInstance]:
        """获取玩家已装备的物品"""
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player_id,
            ItemInstance.equipped == True
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def add(self, item: ItemInstance) -> ItemInstance:
        self._session.add(item)
        await self._session.flush()
        return item

    async def update(self, item: ItemInstance) -> ItemInstance:
        self._session.add(item)
        return item

    async def delete(self, item_id: str) -> bool:
        item = await self.get_by_id(item_id)
        if item:
            await self._session.delete(item)
            return True
        return False

    async def exists(self, item_id: str) -> bool:
        item = await self.get_by_id(item_id)
        return item is not None

    async def count(self) -> int:
        # TODO: 实现
        return 0

    async def get_equipped_equipment(
        self, player_id: str, equipment_item_ids: List[str]
    ) -> List[ItemInstance]:
        """
        获取玩家已装备的所有装备

        Args:
            player_id: 玩家ID
            equipment_item_ids: 装备物品ID列表（从EQUIP_ITEM_IDS获取）

        Returns:
            已装备的装备列表
        """
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player_id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(equipment_item_ids)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_extra_attrs_batch(self, items: List[ItemInstance]) -> None:
        """
        批量更新ItemInstance的extra_attrs字段

        Args:
            items: 需要更新的物品列表

        Note:
            此方法将所有items标记为dirty，在下一次flush/commit时更新到数据库
        """
        for item in items:
            self._session.add(item)

    async def get_available_equipment_for_upgrade(
        self, player_id: str, equipment_item_id: str, required_level: int
    ) -> List[ItemInstance]:
        """
        获取可用于升阶的相同装备列表

        Args:
            player_id: 玩家ID
            equipment_item_id: 装备物品ID
            required_level: 需要的升阶等级

        Returns:
            可用于升阶的装备列表（按耐久度升序排列）
        """
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player_id,
            ItemInstance.item_id == equipment_item_id,
            ItemInstance.upgrade_level == required_level,
            ItemInstance.equipped == False
        ).order_by(ItemInstance.durability.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_material_total_quantity(
        self, player_id: str, material_id: str
    ) -> int:
        """
        获取材料总数量

        Args:
            player_id: 玩家ID
            material_id: 材料物品ID

        Returns:
            材料总数量
        """
        stmt = select(func.sum(ItemInstance.quantity)).where(
            ItemInstance.player_id == player_id,
            ItemInstance.item_id == material_id
        )
        result = await self._session.execute(stmt)
        total = result.scalar()
        return int(total) if total is not None else 0

    async def delete_item_instance(self, item: ItemInstance) -> None:
        """
        删除物品实例

        Args:
            item: 要删除的物品实例
        """
        await self._session.delete(item)

    async def add_item(
        self, player_id: str, item_id: str, quantity: int = 1
    ) -> None:
        """
        添加物品到玩家背包（封装ItemInstance.add_item静态方法）

        Args:
            player_id: 玩家ID
            item_id: 物品ID
            quantity: 数量

        Note:
            此方法调用ItemInstance.add_item静态方法，保持向后兼容
        """
        await ItemInstance.add_item(self._session, player_id, item_id, quantity)

    async def consume_item(
        self, player_id: str, item_id: str, quantity: int
    ) -> bool:
        """
        消耗玩家背包中的物品（封装ItemInstance.consume_item静态方法）

        Args:
            player_id: 玩家ID
            item_id: 物品ID
            quantity: 数量

        Returns:
            是否成功消耗

        Note:
            此方法调用ItemInstance.consume_item静态方法，保持向后兼容
        """
        try:
            await ItemInstance.consume_item(self._session, player_id, item_id, quantity)
            return True
        except ValueError:
            return False

    async def get_by_player_and_item_id(
        self, player_id: str, item_id: str
    ) -> List[ItemInstance]:
        """
        获取玩家的指定物品ID的所有物品实例

        Args:
            player_id: 玩家ID
            item_id: 物品ID（如"furnace"表示炼丹炉）

        Returns:
            物品实例列表（按升阶等级降序、耐久度降序排列）

        对应原代码:
            alchemy/service.py Line 107-111（获取玩家的炼丹炉）

        Note:
            - 排序规则：升阶等级高的优先，同等级时耐久度高的优先
            - 主要用于AlchemyService获取炼丹炉
        """
        stmt = (
            select(ItemInstance)
            .where(
                ItemInstance.player_id == player_id,
                ItemInstance.item_id == item_id
            )
            .order_by(
                ItemInstance.upgrade_level.desc(),
                ItemInstance.durability.desc()
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_by_player_id(self, player_id: str) -> List[ItemInstance]:
        """
        获取玩家的所有物品实例

        Args:
            player_id: 玩家ID

        Returns:
            物品实例列表

        对应原代码:
            alchemy/service.py Line 123（检查材料）

        Note:
            - 主要用于AlchemyService.check_materials()一次性查询所有物品
            - 避免N+1查询问题
        """
        stmt = select(ItemInstance).where(ItemInstance.player_id == player_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_non_equipment_non_fish(self, player_id: str) -> List[ItemInstance]:
        """
        获取玩家所有非装备非鱼类物品

        Args:
            player_id: 玩家ID

        Returns:
            物品实例列表

        对应原代码:
            gift_service.py Line 135-137（计算背包已用格数）

        Note:
            - 用于计算背包容量时排除装备和鱼类物品
        """
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player_id
        )
        result = await self._session.execute(stmt)
        all_items = result.scalars().all()
        return [it for it in all_items if not it.is_equipment and not it.is_fish]

    async def get_items_by_item_id(self, player_id: str, item_id: str) -> List[ItemInstance]:
        """
        获取玩家特定物品的所有堆叠

        Args:
            player_id: 玩家ID
            item_id: 物品ID

        Returns:
            物品实例列表（按ID排序）

        对应原代码:
            gift_service.py Line 141-146（查询接收者该物品的现有堆叠）
        """
        stmt = (
            select(ItemInstance)
            .where(ItemInstance.player_id == player_id, ItemInstance.item_id == item_id)
            .order_by(ItemInstance.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ==================== 装备交易相关方法 ====================

    async def get_player_equipment_list(
        self,
        player_id: str,
        item_id: str,
        equipped: bool = False
    ) -> List[ItemInstance]:
        """
        获取玩家指定装备的所有实例，按升阶等级排序

        Args:
            player_id: 玩家ID
            item_id: 装备物品ID
            equipped: 是否包含已装备的装备（默认False，仅查询未装备）

        Returns:
            装备实例列表（按升阶等级降序，ID升序）

        对应原代码:
            equipment_trade_service.py Line 58-72（获取玩家装备列表）
        """
        stmt = select(ItemInstance).where(
            and_(
                ItemInstance.player_id == player_id,
                ItemInstance.item_id == item_id,
                ItemInstance.equipped == equipped
            )
        ).order_by(
            ItemInstance.upgrade_level.desc(),  # 升阶等级高的在前
            ItemInstance.id.asc()  # 同等级按ID排序
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def freeze_equipment(self, equipment: ItemInstance) -> bool:
        """
        冻结装备实例（标记为交易中）

        在extra_attrs中添加_frozen_for_trade标记

        Args:
            equipment: 装备实例

        Returns:
            True表示冻结成功，False表示冻结失败（已装备）

        对应原代码:
            equipment_trade_service.py Line 75-99（冻结装备）
        """
        if equipment.equipped:
            return False

        # 在extra_attrs中标记为冻结状态
        extra_attrs = equipment.extra_attrs or {}
        extra_attrs["_frozen_for_trade"] = True
        equipment.extra_attrs = extra_attrs
        self._session.add(equipment)
        await self._session.flush()

        return True

    async def unfreeze_equipment(self, equipment: ItemInstance) -> None:
        """
        解冻装备实例（移除交易中标记）

        从extra_attrs中移除_frozen_for_trade标记

        Args:
            equipment: 装备实例

        对应原代码:
            equipment_trade_service.py Line 101-106（解冻装备）
        """
        extra_attrs = equipment.extra_attrs or {}
        extra_attrs.pop("_frozen_for_trade", None)
        equipment.extra_attrs = extra_attrs
        self._session.add(equipment)
        await self._session.flush()

    async def transfer_equipment(self, equipment: ItemInstance, new_owner_id: str) -> bool:
        """
        转移装备所有权

        Args:
            equipment: 装备实例
            new_owner_id: 新拥有者ID

        Returns:
            True表示转移成功，False表示转移失败（已装备或已冻结）

        对应原代码:
            equipment_trade_service.py Line 108-121（转移装备）
        """
        if equipment.equipped:
            return False

        extra_attrs = equipment.extra_attrs or {}
        if extra_attrs.get("_frozen_for_trade"):
            return False

        equipment.player_id = new_owner_id
        self._session.add(equipment)
        await self._session.flush()

        return True
