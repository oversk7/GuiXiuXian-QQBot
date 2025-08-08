from sqlalchemy import String, Integer, Boolean, JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base
from .player import Player
from enum import Enum as PyEnum
from math import ceil
from datetime import datetime
from sqlalchemy.sql import func
from sqlalchemy.ext.mutable import MutableDict

STACK_SIZE = 100  # 每个背包格可堆叠的最大数量

class ItemType(str,PyEnum):
    CONSUMABLE = "CONSUMABLE"
    MATERIAL = "MATERIAL"
    EQUIPMENT = "EQUIPMENT"
    GOODS = "GOODS"
    GHOST_FRAGMENT = "GHOST_FRAGMENT"
    GEM = "GEM"

class ItemEffectType(str, PyEnum):
    RESTORE_HP = "RESTORE_HP"
    RESTORE_MP = "RESTORE_MP"
    RESTORE_HP_PERCENT = "RESTORE_HP_PERCENT"
    RESTORE_MP_PERCENT = "RESTORE_MP_PERCENT"
    BUFF = "BUFF"
    REVIVE = "REVIVE"
    GAIN_EXP = "GAIN_EXP"
    GAIN_RESENTMENT = "GAIN_RESENTMENT"
    RESET_ATTR = "RESET_ATTR"
    EXPAND_TERRITORY = "EXPAND_TERRITORY"
    SWEEP_DUNGEON = "SWEEP_DUNGEON"
    WORLD_BOSS_CHEST = "WORLD_BOSS_CHEST"
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
        # 材料稀有度
        self.rarity = data.get("rarity", "white")

        # 丹药每日使用限制
        self.daily_limit = data.get("daily_limit", 0)  # 每日服用上限，0表示无限制

        # 装备扩展属性
        self.required_level = data.get("required_level", 1)  # 装备等级要求
        self.gem_slots = data.get("gem_slots", 0)  # 宝石孔位数量
        self.max_upgrade_level = data.get("max_upgrade_level", 10)  # 最大升阶等级

    def get_rarity_display(self) -> str:
        """获取稀有度显示文本"""
        rarity_map = {
            "white": "⚪",
            "green": "🟢",
            "blue": "🔵",
            "purple": "🟣",
            "orange": "🟠"
        }
        return rarity_map.get(self.rarity, "⚪")

    def get_display_name(self) -> str:
        """获取带稀有度标识的物品名称"""
        return f"{self.get_rarity_display()}{self.name}"

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
    extra_attrs: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, server_default="{}", comment="强化等附加属性")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default="2025-01-01 00:00:00", comment="获得时间")

    # 装备扩展字段
    upgrade_level: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="装备升阶等级（0-10阶）")
    gem_slots_data: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, server_default="{}", comment="宝石孔位数据：{slot_index: gem_item_id}")
    
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
    
    def apply_attr_bonus(self, attrs: dict, base_attrs: dict = None):
        """将此装备的属性加成应用到 attrs（就地修改）。
        attrs: 形如 {"hp": 100, "attack": 10} 的玩家当前属性 dict
        base_attrs: 形如 {"hp": 100, "attack": 10} 的玩家基础属性 dict（无装备加成）
                   如果提供，百分比加成将基于此计算；否则基于 attrs 计算

        注意：此方法只计算装备的理论属性加成，不包含已持久化的bonus。
        已持久化的bonus(_persist_bonus)已经应用到玩家属性上，不应重复计算。
        """
        if not self.is_equipment or not self.equipped:
            return

        tpl = self.config
        if not tpl:
            return

        # 获取升阶加成倍率
        upgrade_multiplier = self.get_upgrade_bonus_multiplier()

        # 固定值（考虑升阶加成）
        key_map = {"hp": "max_hp", "mp": "max_mp"}
        for k, v in (tpl.attr_bonus or {}).items():
            key = key_map.get(k, k)
            bonus_value = int(v * upgrade_multiplier)
            attrs[key] = attrs.get(key, 0) + bonus_value

        # 百分比 - 基于基础属性计算（考虑升阶加成）
        ratio_base = base_attrs if base_attrs else attrs
        for k, r in (tpl.attr_ratio or {}).items():
            key = key_map.get(k, k)
            base_value = ratio_base.get(key, 0)
            ratio_bonus = int(base_value * float(r) * upgrade_multiplier)
            attrs[key] = attrs.get(key, 0) + ratio_bonus

        # 额外属性（强化）
        for k, v in (self.extra_attrs or {}).items():
            if k.startswith("_"):
                continue  # 跳过内部字段，如 _persist_bonus
            if not isinstance(v, (int, float)):
                continue
            attrs[k] = attrs.get(k, 0) + int(v)

        # 宝石镶嵌属性加成
        self._apply_gem_bonus(attrs, base_attrs)

        return attrs

    def _apply_gem_bonus(self, attrs: dict, base_attrs: dict = None):
        """应用宝石镶嵌的属性加成"""
        if not self.is_equipment or not self.gem_slots_data:
            return

        from ..config import config

        for slot_index, gem_item_id in self.gem_slots_data.items():
            gem_config = config.items_config["by_id"].get(gem_item_id)
            if not gem_config:
                continue

            # 应用宝石的固定属性加成
            key_map = {"hp": "max_hp", "mp": "max_mp"}
            for k, v in (gem_config.attr_bonus or {}).items():
                key = key_map.get(k, k)
                attrs[key] = attrs.get(key, 0) + int(v)

            # 应用宝石的百分比属性加成
            ratio_base = base_attrs if base_attrs else attrs
            for k, r in (gem_config.attr_ratio or {}).items():
                key = key_map.get(k, k)
                base_value = ratio_base.get(key, 0)
                ratio_bonus = int(base_value * float(r))
                attrs[key] = attrs.get(key, 0) + ratio_bonus

    def lose_durability(self, amount: int = 1) -> bool:
        """扣除耐久。返回 True 如果装备已损坏并应销毁。"""
        if not self.is_equipment:
            return False
        self.durability = max(0, self.durability - amount)
        return self.durability == 0

    @property
    def available_gem_slots(self) -> int:
        """获取可用的宝石孔位数量"""
        if not self.is_equipment:
            return 0
        return self.config.gem_slots if self.config else 0

    @property
    def used_gem_slots(self) -> int:
        """获取已使用的宝石孔位数量"""
        if not self.is_equipment:
            return 0
        return len(self.gem_slots_data or {})

    @property
    def free_gem_slots(self) -> int:
        """获取剩余可用的宝石孔位数量"""
        return max(0, self.available_gem_slots - self.used_gem_slots)

    def get_gem_in_slot(self, slot_index: int) -> str | None:
        """获取指定孔位中的宝石ID"""
        if not self.is_equipment:
            return None
        return (self.gem_slots_data or {}).get(str(slot_index))

    def set_gem_in_slot(self, slot_index: int, gem_item_id: str | None):
        """在指定孔位设置宝石"""
        if not self.is_equipment:
            return
        if self.gem_slots_data is None:
            self.gem_slots_data = {}
        if gem_item_id is None:
            # 移除宝石
            self.gem_slots_data.pop(str(slot_index), None)
        else:
            # 设置宝石
            self.gem_slots_data[str(slot_index)] = gem_item_id

    def get_upgrade_bonus_multiplier(self) -> float:
        """获取升阶等级的属性加成倍率"""
        if not self.is_equipment or self.upgrade_level <= 0:
            return 1.0
        # 每阶提升20%属性
        return 1.0 + (self.upgrade_level * 0.2)

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

        # 获取有效背包容量（包含月卡加成）
        effective_capacity = await player.get_effective_inventory_capacity(session)

        if is_equipment:
            # 装备每个占1格 - 先检查空间
            if used_slots + quantity > effective_capacity:
                raise ValueError(f"背包空间不足")
            # 空间足够，添加装备
            equip_durability = durability if durability is not None else item_config.durability
            for _ in range(quantity):
                session.add(ItemInstance(
                    player_id=player_id,
                    item_id=template_id,
                    quantity=1,
                    durability=equip_durability
                ))
            return True

        # 普通物品处理 - 先检查空间
        existing_qty = sum(inv.quantity for inv in stacks_all if inv.item_id == template_id)
        new_total_qty = existing_qty + quantity
        new_slot_cnt = ceil(new_total_qty / STACK_SIZE)
        current_slot_cnt = ceil(existing_qty / STACK_SIZE) if existing_qty else 0
        extra_slots_needed = new_slot_cnt - current_slot_cnt

        if used_slots + extra_slots_needed > effective_capacity:
            raise ValueError(f"背包空间不足")

        # 空间足够，开始添加物品
        # 填充已有堆叠
        result = await session.execute(
            select(ItemInstance)
            .where(ItemInstance.player_id == player_id, ItemInstance.item_id == template_id)
            .order_by(ItemInstance.id)
        )
        stacks: list[ItemInstance] = result.scalars().all()

        # 记录原始数量，以便在出错时恢复
        original_quantities = {}
        for inv in stacks:
            original_quantities[inv.id] = inv.quantity

        # 整理并填充已有堆叠
        remaining_qty = quantity
        for inv in stacks:
            if remaining_qty == 0:
                break
            space = inv.available_space
            if space == 0:
                continue
            take = min(space, remaining_qty)
            inv.quantity += take
            remaining_qty -= take
            session.add(inv)

        # 剩余数量分新堆
        while remaining_qty > 0:
            put_qty = min(STACK_SIZE, remaining_qty)
            session.add(ItemInstance(player_id=player_id, item_id=template_id, quantity=put_qty))
            remaining_qty -= put_qty
        return True

    @staticmethod
    async def consume_item(session, player_id: str, template_id: str, quantity: int = 1, durability: int = None) -> bool:
        """从玩家背包扣除物品，优先消耗未满堆叠；数量不足时返回 False。

        扣除逻辑：
        1. 查询所有同类物品堆叠，按数量升序（小堆在前）。
        2. 逐堆扣除，若堆数量归零则删除该记录。
        3. 最终确认累计扣除达到quantity。
        """
        from sqlalchemy import select
        from ..config import config

        item_config: ItemConfig | None = config.items_config["by_id"].get(template_id)
        if not item_config:
            raise ValueError(f"物品模板 {template_id} 不存在")
        is_equipment = item_config.type == ItemType.EQUIPMENT

        if is_equipment:
            equip_durability = durability if durability is not None else item_config.durability
            result = await session.execute(
                select(ItemInstance)
                .where(ItemInstance.player_id == player_id, ItemInstance.item_id == template_id, ItemInstance.durability == equip_durability)
            )
            stacks: list[ItemInstance] = result.scalars().all()
            if len(stacks) < quantity:
                raise ValueError(f"完整耐久度的装备数量不足")

            for _ in range(quantity):
                await session.delete(stacks[0])
            return True

        # 普通物品处理
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