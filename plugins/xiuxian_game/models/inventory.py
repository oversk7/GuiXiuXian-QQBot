from sqlalchemy import String, Integer, Boolean, JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base
from .player import Player
from enum import Enum as PyEnum
from math import ceil
from datetime import datetime
from sqlalchemy.sql import func

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

class ItemInstance(Base):
    """统一的物品实例模型
    
    设计理念：
    1. 所有物品都是实例化的，包括普通物品
    2. 装备有耐久度，普通物品有数量
    3. 装备不可堆叠（quantity=1），普通物品可堆叠
    4. 统一存储在玩家背包中
    """
    __tablename__ = "inventory"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True)
    item_id: Mapped[str] = mapped_column(String(32), index=True, comment="items.yaml 内物品模板 ID")
    quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1", comment="数量（装备固定为1）")
    durability: Mapped[int] = mapped_column(Integer, default=0, server_default="0",comment="当前耐久度（仅装备有效）")
    equipped: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", comment="是否已穿戴（仅装备有效）")
    on_market: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", comment="是否已上架交易市场")
    extra_attrs: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}", comment="强化等附加属性")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default="2025-01-01 00:00:00", comment="获得时间")
    
    owner: Mapped["Player"] = relationship("Player", backref="item_instances")
    
    @property
    def config(self) -> ItemConfig:
        """返回 YAML 中的 ItemConfig 模板"""
        from ..config import config
        return config.items_config["by_id"].get(self.item_id)
    
    @property
    def is_equipment(self) -> bool:
        """是否为装备"""
        return self.config and self.config.type == ItemType.EQUIPMENT
    
    @property
    def slot_count(self) -> int:
        """当前记录占用的背包格数（装备固定为1，普通物品按堆叠计算）"""
        if self.is_equipment:
            return 1
        return ceil(self.quantity / STACK_SIZE)
    
    @property
    def available_space(self) -> int:
        """当前这格剩余可放置数量（装备为0，普通物品为0~STACK_SIZE，若为负数则表示需要拆分）"""
        if self.is_equipment:
            return 0
        return STACK_SIZE - self.quantity
    
    def apply_attr_bonus(self, attrs: dict):
        """将此装备的属性加成应用到 attrs（就地修改）。
        attrs: 形如 {"hp": 100, "attack": 10} 的玩家基础属性 dict
        """
        if not self.is_equipment or not self.equipped:
            return
        
        tpl = self.config
        if not tpl:
            return
            
        # 固定值
        key_map = {"hp": "max_hp", "mp": "max_mp"}
        for k, v in (tpl.attr_bonus or {}).items():
            key = key_map.get(k, k)
            attrs[key] = attrs.get(key, 0) + int(v)
        # 百分比
        for k, r in (tpl.attr_ratio or {}).items():
            key = key_map.get(k, k)
            attrs[key] = int(attrs.get(key, 0) * (1 + float(r)))
        # 额外属性（强化）
        for k, v in (self.extra_attrs or {}).items():
            if k.startswith("_"):
                continue  # 跳过内部字段，如 _persist_bonus
            if not isinstance(v, (int, float)):
                continue
            attrs[k] = attrs.get(k, 0) + int(v)

        # 叠加持久化 bonus（如果存在）
        persist = (self.extra_attrs or {}).get("_persist_bonus", {})
        for k, v in persist.items():
            if not isinstance(v, (int, float)):
                continue
            attrs[k] = attrs.get(k, 0) + int(v)
        return attrs

    def lose_durability(self, amount: int = 1) -> bool:
        """扣除耐久。返回 True 如果装备已损坏并应销毁。"""
        if not self.is_equipment:
            return False
        self.durability = max(0, self.durability - amount)
        return self.durability == 0

    # ---------------------- 静态工具方法 ----------------------
    @staticmethod
    async def add_item(session, player_id: str, template_id: str, quantity: int = 1, durability: int = None) -> bool:
        """
        向玩家背包添加物品，自动处理堆叠和超出 STACK_SIZE 拆分。
        当背包容量不足时，将返回False且不会对数据库做出任何修改；
        成功添加时返回True。
        """
        from sqlalchemy import select
        from .player import Player  # 运行时导入避免循环
        from math import ceil
        from ..config import config

        item_config: ItemConfig | None = config.items_config["by_id"].get(template_id)
        if not item_config:
            raise ValueError(f"物品模板 {template_id} 不存在")
        is_equipment = item_config.type == ItemType.EQUIPMENT

        # 获取玩家和背包所有物品
        player: Player | None = await session.get(Player, player_id)
        if not player:
            raise ValueError(f"玩家 {player_id} 不存在")

        result_inv = await session.execute(
            select(ItemInstance).where(ItemInstance.player_id == player_id)
        )
        stacks_all: list[ItemInstance] = result_inv.scalars().all()
        used_slots = len(stacks_all)

        if is_equipment:
            # 装备每个占1格
            if used_slots + quantity > player.inventory_capacity:
                raise ValueError(f"背包空间不足")
            equip_durability = durability if durability is not None else item_config.durability
            for _ in range(quantity):
                session.add(ItemInstance(
                    player_id=player_id,
                    item_id=template_id,
                    quantity=1,
                    durability=equip_durability
                ))
            return True

        # 普通物品处理
        existing_qty = sum(inv.quantity for inv in stacks_all if inv.item_id == template_id)
        new_total_qty = existing_qty + quantity
        new_slot_cnt = ceil(new_total_qty / STACK_SIZE)
        current_slot_cnt = ceil(existing_qty / STACK_SIZE) if existing_qty else 0
        extra_slots_needed = new_slot_cnt - current_slot_cnt

        if used_slots + extra_slots_needed > player.inventory_capacity:
            raise ValueError(f"背包空间不足")

        # 填充已有堆叠
        result = await session.execute(
            select(ItemInstance)
            .where(ItemInstance.player_id == player_id, ItemInstance.item_id == template_id)
            .order_by(ItemInstance.id)
        )
        stacks: list[ItemInstance] = result.scalars().all()
        # 整理并填充已有堆叠
        for inv in stacks:
            if quantity == 0:
                break
            space = inv.available_space
            if space == 0:
                continue
            take = min(space, quantity)
            inv.quantity += take
            quantity -= take
            session.add(inv)
        # 剩余数量分新堆
        while quantity > 0:
            put_qty = min(STACK_SIZE, quantity)
            session.add(ItemInstance(player_id=player_id, item_id=template_id, quantity=put_qty))
            quantity -= put_qty
        return True

    @staticmethod
    async def consume_item(session, player_id: str, template_id: str, quantity: int = 1) -> bool:
        """从玩家背包扣除物品，优先消耗未满堆叠；数量不足时返回 False。

        扣除逻辑：
        1. 查询所有同类物品堆叠，按数量升序（小堆在前）。
        2. 逐堆扣除，若堆数量归零则删除该记录。
        3. 最终确认累计扣除达到quantity。
        """
        from sqlalchemy import select
        result = await session.execute(
            select(ItemInstance)
            .where(ItemInstance.player_id == player_id, ItemInstance.item_id == template_id)
            .order_by(ItemInstance.quantity.asc())
        )
        stacks: list[ItemInstance] = result.scalars().all()

        total_qty = sum(inv.quantity for inv in stacks)
        if total_qty < quantity:
            raise ValueError(f"物品数量不足")

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
                break
        return True
