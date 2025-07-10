from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base
from enum import Enum as PyEnum
from math import ceil

STACK_SIZE = 100  # 每个背包格可堆叠的最大数量

class ItemType(str,PyEnum):
    CONSUMABLE = "CONSUMABLE"
    MATERIAL = "MATERIAL"
    EQUIPMENT = "EQUIPMENT"
    GOODS = "GOODS"

class ItemEffectType(str, PyEnum):
    RESTORE_HP = "RESTORE_HP" 
    RESTORE_MP = "RESTORE_MP"
    BUFF = "BUFF"
    REVIVE = "REVIVE"
    GAIN_EXP = "GAIN_EXP"
    RESET_ATTR = "RESET_ATTR"
    # 以下类型不使用 apply_effect 处理
    CHANGE_NAME = "CHANGE_NAME"
    TELEPORT = "TELEPORT"
    APPOINT_PRESIDENT = "APPOINT_PRESIDENT"

class ItemConfig:
    def __init__(self, data: dict):
        self.item_id = data["item_id"]
        self.name = data["name"]
        self.type = ItemType(data["type"])
        self.description = data["description"]
        self.effect_type = ItemEffectType(data.get("effect_type", "BUFF"))
        self.effect_params = data.get("effect_params", {})
        self.price = data.get("price", 0)
        self.durability = data.get("durability", 0)
        self.attr_bonus = data.get("attr_bonus", {})
        self.attr_ratio = data.get("attr_ratio", {})
        # 部分材料可拥有怨念值，用于献祭
        self.grudge_value = data.get("grudge_value", 0)
        # 装备锻造配方：{"materials": {"item_id": qty, ...}, "gold": 1000}
        self.recipe = data.get("recipe")
        # 装备修复单价（每 1 点耐久消耗金币数），若为空则默认按 price/durability 计算
        self.repair_cost = data.get("repair_cost")
        

class Inventory(Base):
    __tablename__ = "inventory"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True)
    item_id: Mapped[str] = mapped_column(String(32), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    
    @property
    def slot_count(self) -> int:
        """当前记录占用的背包格数（向上取整）"""
        return ceil(self.quantity / STACK_SIZE)

    @property
    def available_space(self) -> int:
        """当前这格剩余可放置数量（0~STACK_SIZE）"""
        remainder = self.quantity % STACK_SIZE
        return STACK_SIZE - remainder if remainder else STACK_SIZE
    
    @property
    def config(self) -> ItemConfig:
        from ..config import config
        return config.items_config["by_id"].get(self.item_id) 

    # ---------------------- 工具方法 ----------------------
    @staticmethod
    async def add_item(session, player_id: str, item_id: str, quantity: int) -> bool:
        """向玩家背包添加物品，自动处理堆叠和超出 STACK_SIZE 拆分。

        当背包容量不足时，将返回 **False** 且**不会**对数据库做出任何修改；
        成功添加时返回 **True**。
        """
        if quantity <= 0:
            return True  # 无需添加视为成功

        from sqlalchemy import select
        from .player import Player  # 运行时导入避免循环
        from math import ceil

        # ------- 背包容量检查 -------
        player: Player | None = await session.get(Player, player_id)
        if not player:
            return False  # 未找到玩家视为失败

        result_inv = await session.execute(
            select(Inventory).where(Inventory.player_id == player_id)
        )
        stacks_all = result_inv.scalars().all()

        used_slots = sum(inv.slot_count for inv in stacks_all)
        existing_qty = sum(inv.quantity for inv in stacks_all if inv.item_id == item_id)

        # 计算添加后需要的新背包格
        new_total_qty = existing_qty + quantity
        new_slot_cnt = ceil(new_total_qty / STACK_SIZE)
        current_slot_cnt = ceil(existing_qty / STACK_SIZE) if existing_qty else 0
        extra_slots_needed = new_slot_cnt - current_slot_cnt

        if used_slots + extra_slots_needed > player.inventory_capacity:
            return False  # 背包空间不足

        # ------- 开始执行添加逻辑 -------
        result = await session.execute(
            select(Inventory)
            .where(Inventory.player_id == player_id, Inventory.item_id == item_id)
            .order_by(Inventory.id)
        )
        stacks = result.scalars().all()
        # 按顺序填充
        for inv in stacks:
            if quantity == 0:
                break
            space = inv.available_space
            if space <= 0:
                continue
            take = min(space, quantity)
            inv.quantity += take
            quantity -= take
            session.add(inv)
        # 剩余数量分新堆
        while quantity > 0:
            put_qty = min(STACK_SIZE, quantity)
            session.add(Inventory(player_id=player_id, item_id=item_id, quantity=put_qty))
            quantity -= put_qty 

        return True

    @staticmethod
    async def consume_item(session, player_id: str, item_id: str, quantity: int) -> bool:
        """从玩家背包扣除物品，优先消耗未满堆叠；数量不足时返回 False。

        扣除逻辑：
        1. 查询所有同类物品堆叠，按数量升序（小堆在前）。
        2. 逐堆扣除，若堆数量归零则删除该记录。
        3. 最终确认累计扣除达到 *quantity*。
        """
        if quantity <= 0:
            return True

        from sqlalchemy import select
        result = await session.execute(
            select(Inventory)
            .where(Inventory.player_id == player_id, Inventory.item_id == item_id)
            .order_by(Inventory.quantity.asc())
        )
        stacks = result.scalars().all()

        # ------- 先行校验：总量是否足够 -------
        total_qty = sum(inv.quantity for inv in stacks)
        if total_qty < quantity:
            return False

        # ------- 扣除逻辑 -------
        remaining = quantity
        for inv in stacks:
            if remaining <= 0:
                break
            take = min(inv.quantity, remaining)
            inv.quantity -= take
            remaining -= take
            if inv.quantity <= 0:
                await session.delete(inv)
            else:
                session.add(inv)

        return True 