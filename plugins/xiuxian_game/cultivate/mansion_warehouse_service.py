"""
阴宅仓库服务层

提供玩家个人仓库的存取物品、查看容量等功能。
访问限制：玩家必须在自己的阴宅坐标位置才能存取。
允许物品类型：MATERIAL（材料）、CONSUMABLE（消耗品）、GEM（宝石）
"""
from math import ceil
from typing import List, Dict, Tuple

from ..config import config
from ..models.inventory import STACK_SIZE, ItemType
from ..models.mansion_warehouse import MansionWarehouseItem
from ..infrastructure.repositories.mansion_warehouse_item_repository import MansionWarehouseItemRepository
from ..infrastructure.repositories.item_repository import ItemRepository


# 允许存入仓库的物品类型
ALLOWED_ITEM_TYPES = {ItemType.MATERIAL, ItemType.CONSUMABLE, ItemType.GEM}
ALLOWED_TYPE_NAMES = "材料、消耗品、宝石"


class MansionWarehouseService:
    """阴宅仓库服务"""

    def __init__(
        self,
        warehouse_repo: MansionWarehouseItemRepository,
        item_repo: ItemRepository,
    ):
        self._warehouse_repo = warehouse_repo
        self._item_repo = item_repo

    # ─── 容量计算 ───────────────────────────────────────────────────────────────

    @staticmethod
    def get_capacity(mansion_level: int) -> int:
        """
        根据阴宅等级计算仓库容量（堆叠格数）

        分段递增，越高等级每级增量越大：
        - 1-10级：基础50格，每级+5（Level 1=50，Level 10=95）
        - 11-20级：每级+15（Level 11=110，Level 20=245）
        - 21-30级：每级+30（Level 21=275，Level 30=545）
        """
        if mansion_level <= 0:
            return 0
        if mansion_level <= 10:
            return 50 + (mansion_level - 1) * 5
        if mansion_level <= 20:
            return 95 + (mansion_level - 10) * 15
        return 245 + (mansion_level - 20) * 30

    # ─── 查看仓库 ───────────────────────────────────────────────────────────────

    async def get_warehouse_items(self, player_id: str) -> List[Dict]:
        """
        获取仓库物品列表，合并同种物品的多个堆叠后按名称排序显示

        Returns:
            列表，每项包含 item_id / name / quantity / type_name
        """
        stacks = await self._warehouse_repo.get_all_by_player_id(player_id)

        # 合并相同 item_id 的堆叠
        merged: Dict[str, int] = {}
        for stack in stacks:
            merged[stack.item_id] = merged.get(stack.item_id, 0) + stack.quantity

        result = []
        for item_id, quantity in merged.items():
            item_cfg = config.items_config["by_id"].get(item_id)
            name = item_cfg.name if item_cfg else item_id
            type_name = item_cfg.type.value if item_cfg else "未知"
            result.append({
                "item_id": item_id,
                "name": name,
                "quantity": quantity,
                "type_name": type_name,
            })

        result.sort(key=lambda x: x["name"])
        return result

    async def format_warehouse_display(self, player_id: str, mansion_level: int) -> str:
        """格式化仓库展示文本"""
        capacity = self.get_capacity(mansion_level)
        used_slots = await self._warehouse_repo.get_total_slots_count(player_id)
        items = await self.get_warehouse_items(player_id)

        lines = [
            f"🏚️ 阴宅仓库（{mansion_level}级）",
            f"━━━━━━━━━━━━━",
            f"容量：{used_slots}/{capacity} 格",
            f"━━━━━━━━━━━━━",
        ]

        if not items:
            lines.append("（仓库空空如也）")
        else:
            for idx, item in enumerate(items, 1):
                lines.append(f"{idx}. {item['name']} ×{item['quantity']}")

        lines += [
            f"━━━━━━━━━━━━━",
            f"💡 允许存入：{ALLOWED_TYPE_NAMES}",
            f"💡 【存入阴宅 <物品名> <数量>】存入物品",
            f"💡 【取出阴宅 <序号> <数量>】取出物品",
        ]
        return "\n".join(lines)

    # ─── 存入物品 ───────────────────────────────────────────────────────────────

    async def deposit_item(self, player_id: str, mansion_level: int, item_id: str, quantity: int) -> Tuple[bool, str]:
        """
        将玩家背包中的物品存入阴宅仓库

        Args:
            player_id: 玩家ID
            mansion_level: 阴宅等级（决定容量）
            item_id: 物品模板ID
            quantity: 存入数量

        Returns:
            (是否成功, 结果信息)
        """
        if quantity <= 0:
            return False, "存入数量必须大于0"

        # 检查物品类型是否允许
        item_cfg = config.items_config["by_id"].get(item_id)
        if not item_cfg:
            return False, "物品不存在"
        if item_cfg.type not in ALLOWED_ITEM_TYPES:
            return False, f"只能存入{ALLOWED_TYPE_NAMES}类型的物品，【{item_cfg.name}】属于{item_cfg.type.value}类型"

        # 检查玩家背包中是否有足够数量
        player_stacks = await self._item_repo.get_by_player_and_item_id(player_id, item_id)
        total_owned = sum(s.quantity for s in player_stacks)
        if total_owned < quantity:
            return False, f"背包中该物品数量不足（拥有 {total_owned}，需要 {quantity}）"

        # 计算存入后需要的额外格子数
        existing_stacks = await self._warehouse_repo.get_by_player_and_item_id(player_id, item_id)
        existing_qty = sum(s.quantity for s in existing_stacks)
        new_total_qty = existing_qty + quantity
        new_slots_needed = ceil(new_total_qty / STACK_SIZE)
        current_slots_for_item = len(existing_stacks)
        additional_slots = new_slots_needed - current_slots_for_item

        capacity = self.get_capacity(mansion_level)
        current_total_slots = await self._warehouse_repo.get_total_slots_count(player_id)
        if current_total_slots + additional_slots > capacity:
            return False, (
                f"仓库格子不足（已用 {current_total_slots}/{capacity} 格，"
                f"存入 {quantity} 个需要额外 {additional_slots} 格）"
            )

        # 从玩家背包扣除物品（优先消耗最小堆叠）
        remaining_to_deduct = quantity
        for stack in sorted(player_stacks, key=lambda s: s.quantity):
            if remaining_to_deduct <= 0:
                break
            deduct = min(stack.quantity, remaining_to_deduct)
            stack.quantity -= deduct
            remaining_to_deduct -= deduct
            if stack.quantity <= 0:
                await self._item_repo.delete_item_instance(stack)
            else:
                await self._item_repo.update(stack)

        # 向仓库添加物品（优先填满现有堆叠）
        remaining_to_add = quantity
        for stack in existing_stacks:
            if remaining_to_add <= 0:
                break
            space = STACK_SIZE - stack.quantity
            if space > 0:
                fill = min(space, remaining_to_add)
                stack.quantity += fill
                remaining_to_add -= fill
                await self._warehouse_repo.update(stack)

        # 剩余数量创建新堆叠
        while remaining_to_add > 0:
            stack_qty = min(STACK_SIZE, remaining_to_add)
            new_stack = MansionWarehouseItem(
                player_id=player_id,
                item_id=item_id,
                quantity=stack_qty,
            )
            await self._warehouse_repo.add(new_stack)
            remaining_to_add -= stack_qty

        return True, f"成功将 {item_cfg.name} ×{quantity} 存入阴宅仓库"

    # ─── 取出物品 ───────────────────────────────────────────────────────────────

    async def withdraw_item(self, player_id: str, mansion_level: int, item_index: int, quantity: int) -> Tuple[bool, str]:
        """
        从阴宅仓库取出物品到玩家背包

        Args:
            player_id: 玩家ID
            mansion_level: 阴宅等级
            item_index: 仓库展示列表中的序号（1起）
            quantity: 取出数量

        Returns:
            (是否成功, 结果信息)
        """
        if quantity <= 0:
            return False, "取出数量必须大于0"

        items = await self.get_warehouse_items(player_id)
        if item_index < 1 or item_index > len(items):
            return False, f"无效的序号，仓库共有 {len(items)} 种物品"

        selected = items[item_index - 1]
        if selected["quantity"] < quantity:
            return False, f"仓库中该物品数量不足（仅有 {selected['quantity']} 个）"

        # 尝试添加到玩家背包（ItemInstance.add_item 会检查背包容量）
        from ..models.inventory import ItemInstance
        success = await ItemInstance.add_item(
            self._item_repo._session, player_id, selected["item_id"], quantity
        )
        if not success:
            return False, "背包空间不足，无法取出"

        # 从仓库扣除（按存入时间降序，优先取最新的）
        warehouse_stacks = await self._warehouse_repo.get_by_player_and_item_id_desc(
            player_id, selected["item_id"]
        )
        remaining = quantity
        for stack in warehouse_stacks:
            if remaining <= 0:
                break
            take = min(stack.quantity, remaining)
            stack.quantity -= take
            remaining -= take
            if stack.quantity <= 0:
                await self._warehouse_repo.delete(stack.id)
            else:
                await self._warehouse_repo.update(stack)

        return True, f"成功从阴宅仓库取出 {selected['name']} ×{quantity}"
