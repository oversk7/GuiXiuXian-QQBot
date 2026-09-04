from sqlalchemy import String, Integer, Boolean, JSON, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, load_only, mapped_column, relationship
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
    FISH = "FISH"
    GIFT = "GIFT"  # 好感度礼物
    SEASONING = "SEASONING"  # 调料
    DISH = "DISH"  # 菜肴
    RECIPE = "RECIPE"  # 食谱
    VEGETABLE = "VEGETABLE"  # 灵蔬(灵田产出，联动烹饪)
    HERB = "HERB"  # 诡药(灵田产出，联动炼丹)
    SEED = "SEED"  # 灵种(灵田种子)
    GUARDIAN_BEAST = "GUARDIAN_BEAST"  # 诡兽(守田用)
    INSCRIPTION = "INSCRIPTION"        # 铭文(独立效果物品，插入宝石孔)
    PET_ACCESSORY = "PET_ACCESSORY"    # 宠物饰品

class ItemEffectType(str, PyEnum):
    RESTORE_HP = "RESTORE_HP"
    RESTORE_MP = "RESTORE_MP"
    RESTORE_HP_PERCENT = "RESTORE_HP_PERCENT"
    RESTORE_MP_PERCENT = "RESTORE_MP_PERCENT"
    BUFF = "BUFF"
    BUFF_PERCENT = "BUFF_PERCENT"  # 永久百分比属性加成
    TEMPORARY_BUFF = "TEMPORARY_BUFF"  # 临时属性加成丹药
    TEMPORARY_BUFF_PERCENT = "TEMPORARY_BUFF_PERCENT"  # 临时百分比属性加成
    REVIVE = "REVIVE"
    GAIN_EXP = "GAIN_EXP"
    GAIN_EXP_SCALED = "GAIN_EXP_SCALED"  # 按等级伸缩的经验丹
    GAIN_RESENTMENT = "GAIN_RESENTMENT"
    RESET_ATTR = "RESET_ATTR"
    REFORGE_ATTR = "REFORGE_ATTR"  # 洗髓丹药：转换属性点
    REFORGE_MULTI_ATTR = "REFORGE_MULTI_ATTR"  # 多属性洗髓：同时转换多种属性点（虚空归元丹）
    EXPAND_TERRITORY = "EXPAND_TERRITORY"
    SWEEP_DUNGEON = "SWEEP_DUNGEON"
    WORLD_BOSS_CHEST = "WORLD_BOSS_CHEST"
    MONTHLY_CARD_BOX = "MONTHLY_CARD_BOX"
    RULE_HORROR_CHEST = "RULE_HORROR_CHEST"  # 怪谈稀有宝箱：规则怪谈通关奖励
    DIVINE_PUNISHMENT = "DIVINE_PUNISHMENT"  # 天罚符：强制击杀指定目标
    SANTA_TELEPORT = "SANTA_TELEPORT"  # 圣诞老人代驾券：瞬移到任意位置
    LEARN_RECIPE = "LEARN_RECIPE"  # 学习食谱：解锁烹饪食谱
    RESTORE_HP_MP_PERCENT = "RESTORE_HP_MP_PERCENT"  # 同时按百分比回复生命和理智
    PERMANENT_ATTR_VIP = "PERMANENT_ATTR_VIP"  # 永久属性加成（轮回后保留，使用VIPEquipmentBonus）
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

        # 标签信息，用于扩展分类，例如活动限定物等
        self.tags = set(data.get("tags", []))

        # 丹药每日使用限制
        self.daily_limit = data.get("daily_limit", 0)  # 每日服用上限，0表示无限制

        # 装备扩展属性
        self.required_level = data.get("required_level", 1)  # 装备等级要求
        self.required_reincarnation = data.get("required_reincarnation", 0)  # 装备转数要求（冥返次数≥该值才可穿戴）
        self.gem_slots = data.get("gem_slots", 0)  # 宝石孔位数量
        self.equipment_slot_bonus = data.get("equipment_slot_bonus", 0)  # 额外装备槽数量
        self.max_upgrade_level = data.get("max_upgrade_level", 10)  # 最大升阶等级

        # 特殊效果配置(增强战斗系统)
        self.special_effects = data.get("special_effects", [])  # 特殊效果列表

        # 铭文效果配置
        self.inscription_effect = data.get("inscription_effect")
        # 高级铭文扩展
        self.inscription_type = data.get("inscription_type")  # "advanced" 或 None
        self.inscription_effects = data.get("inscription_effects")  # 多效果列表(高级铭文)

        # 礼物系统: 好感度加成
        self.favorability = data.get("favorability", 0)  # 赠送时增加的好感度

    def get_rarity_display(self) -> str:
        """获取稀有度显示文本"""
        rarity_map = {
            "white": "⚪",
            "green": "🟢",
            "blue": "🔵",
            "purple": "🟣",
            "orange": "🟠",
            "red": "🔴"
        }
        return rarity_map.get(self.rarity, "⚪")

    def get_display_name(self) -> str:
        """获取带稀有度标识的物品名称"""
        return f"{self.get_rarity_display()}{self.name}"

    @property
    def is_fish(self) -> bool:
        """判断是否为鱼类物品"""
        if self.type == ItemType.FISH:
            return True
        return "fish" in self.tags

class ItemInstance(Base):
    """统一的物品实例模型
    
    设计理念：
    1. 所有物品都是实例化的，包括普通物品
    2. 装备有耐久度，普通物品有数量
    3. 装备不可堆叠（quantity=1），普通物品可堆叠
    4. 统一存储在玩家背包中
    """
    __tablename__ = "inventory"
    __table_args__ = (
        Index("ix_inventory_player_item", "player_id", "item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True)
    item_id: Mapped[str] = mapped_column(String(64), index=True, comment="items.yaml 内物品模板 ID")
    quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1", comment="数量（装备固定为1）")
    durability: Mapped[int] = mapped_column(Integer, default=0, server_default="0",comment="当前耐久度（仅装备有效）")
    equipped: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", comment="是否已穿戴（仅装备有效）")
    extra_attrs: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, comment="强化等附加属性")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default="2025-01-01 00:00:00", comment="获得时间")

    # 装备扩展字段
    upgrade_level: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="装备升阶等级（0-10阶）")
    gem_slots_data: Mapped[dict] = mapped_column(MutableDict.as_mutable(JSON), default=dict, comment="宝石孔位数据：{slot_index: gem_item_id}")
    
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
    def is_inscription(self) -> bool:
        """是否为铭文物品"""
        return self.config is not None and self.config.type == ItemType.INSCRIPTION

    @property
    def is_fish(self) -> bool:
        """是否为鱼类物品"""
        tpl = self.config
        return bool(tpl and tpl.is_fish)

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
        # 仅应用“合法的属性键”，避免将装备元数据（如计数/日期等）误加到玩家身上
        extra = self.extra_attrs or {}
        if extra:
            allowed_keys = set(base_attrs.keys()) if base_attrs else {
                "max_hp","max_mp","attack","defense","agility","luck",
                "critical_rate","critical_power","combo_rate","counter_rate","dodge_rate","accuracy_rate",
                "skill_crit_rate","penetration_rate","anti_crit_rate",
                "anti_combo_rate","anti_counter_rate",
                "lifesteal_rate","immobilize_rate","true_damage_rate","regen_rate"
            }
            for k, v in extra.items():
                if k.startswith("_"):
                    continue  # 内部字段，如 _persist_bonus、_robexxx
                if k not in allowed_keys:
                    continue  # 忽略不在属性白名单内的键（如 robe_die_cnt/robe_die_day 等元数据）
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

        for slot_index, gem_data in self.gem_slots_data.items():
            if isinstance(gem_data, dict):
                continue  # 铭文不贡献属性加成，由战斗触发器处理
            gem_config = config.items_config["by_id"].get(gem_data)
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
        """扣除耐久。返回 True 如果耐久降至0（已损坏，需要自动卸下）。"""
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

    def get_gem_in_slot(self, slot_index: int) -> str | dict | None:
        """获取指定孔位中的宝石ID或铭文数据

        返回 str 表示宝石item_id，dict 表示铭文数据，None 表示空孔位
        """
        if not self.is_equipment:
            return None
        return (self.gem_slots_data or {}).get(str(slot_index))

    def set_gem_in_slot(self, slot_index: int, value: str | dict | None):
        """在指定孔位设置宝石或铭文

        value 为 str 时表示宝石 item_id（向后兼容）
        value 为 dict 时表示铭文数据 {"item_id": ..., "values": {...}}
        value 为 None 时移除孔位内容
        """
        if not self.is_equipment:
            return
        if self.gem_slots_data is None:
            self.gem_slots_data = {}
        if value is None:
            self.gem_slots_data.pop(str(slot_index), None)
        else:
            self.gem_slots_data[str(slot_index)] = value

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
        当背包容量不足时，抛出 ValueError 且不会对数据库做出任何修改；
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
        is_inscription = item_config.type == ItemType.INSCRIPTION
        is_fish = item_config.is_fish

        # 获取玩家
        player: Player | None = await session.get(Player, player_id)
        if not player:
            raise ValueError(f"玩家 {player_id} 不存在")

        if is_equipment or is_inscription:
            # 装备/铭文不占用背包容量，直接添加（每件独立实例）
            item_durability = durability if durability is not None else (item_config.durability if is_equipment else None)
            for _ in range(quantity):
                inst = ItemInstance(
                    player_id=player_id,
                    item_id=template_id,
                    quantity=1,
                )
                if item_durability is not None:
                    inst.durability = item_durability
                session.add(inst)
            await session.flush()

            if is_equipment:
                from ..achievement.achievement_service import AchievementService
                await AchievementService.update_stat(session, player_id, "equipment_obtained", quantity)

            return True

        inventory_columns = (
            ItemInstance.id,
            ItemInstance.player_id,
            ItemInstance.item_id,
            ItemInstance.quantity,
        )
        if is_fish:
            # 鱼类不占背包容量，只需读取同类堆叠。
            result_inv = await session.execute(
                select(ItemInstance)
                .options(load_only(*inventory_columns))
                .where(
                    ItemInstance.player_id == player_id,
                    ItemInstance.item_id == template_id,
                )
            )
            stacks_all: list[ItemInstance] = result_inv.scalars().all()
        else:
            result_inv = await session.execute(
                select(ItemInstance)
                .options(load_only(*inventory_columns))
                .where(ItemInstance.player_id == player_id)
            )
            stacks_all = result_inv.scalars().all()

            used_slots = sum(
                1
                for item in stacks_all
                if not item.is_equipment and not item.is_fish and not item.is_inscription
            )
            effective_capacity = await player.get_effective_inventory_capacity(session)

        # 普通物品处理 - 先检查空间
        stacks = sorted(
            (
                inv
                for inv in stacks_all
                if inv.item_id == template_id and not inv.is_equipment
            ),
            key=lambda inv: inv.id or 0,
        )
        existing_qty = sum(inv.quantity for inv in stacks)
        new_total_qty = existing_qty + quantity
        if not is_fish:
            new_slot_cnt = ceil(new_total_qty / STACK_SIZE)
            current_slot_cnt = ceil(existing_qty / STACK_SIZE) if existing_qty else 0
            extra_slots_needed = new_slot_cnt - current_slot_cnt

            if used_slots + extra_slots_needed > effective_capacity:
                raise ValueError(f"背包空间不足")

        # 空间足够，开始添加物品
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

        # 确保所有物品添加操作立即刷新到数据库
        await session.flush()
        return True

    @staticmethod
    async def add_item_partial(session, player_id: str, template_id: str, quantity: int = 1) -> int:
        """
        向玩家背包添加物品（尽量装入模式）。

        与 add_item 的区别：背包空间不足时不抛异常，只装入可容纳的部分，
        返回实际入库数量（0 ~ quantity）。适用于扫荡等批量掉落场景，
        由调用方根据返回值提示玩家溢出丢失的部分。

        仅支持普通堆叠物品，不支持装备/铭文（它们不占背包格，请用 add_item）。
        """
        from sqlalchemy import select
        from .player import Player  # 运行时导入避免循环
        from ..config import config

        if quantity <= 0:
            return 0

        item_config: ItemConfig | None = config.items_config["by_id"].get(template_id)
        if not item_config:
            raise ValueError(f"物品模板 {template_id} 不存在")
        if item_config.type in (ItemType.EQUIPMENT, ItemType.INSCRIPTION):
            raise ValueError("add_item_partial 不支持装备/铭文类物品，请使用 add_item")

        player: Player | None = await session.get(Player, player_id)
        if not player:
            raise ValueError(f"玩家 {player_id} 不存在")

        if item_config.is_fish:
            # 鱼类不占背包格，只需读取同类堆叠。
            result_inv = await session.execute(
                select(ItemInstance)
                .options(load_only(
                    ItemInstance.id,
                    ItemInstance.player_id,
                    ItemInstance.item_id,
                    ItemInstance.quantity,
                ))
                .where(
                    ItemInstance.player_id == player_id,
                    ItemInstance.item_id == template_id,
                )
            )
            stacks_all: list[ItemInstance] = result_inv.scalars().all()
            addable = quantity
        else:
            result_inv = await session.execute(
                select(ItemInstance)
                .options(load_only(
                    ItemInstance.id,
                    ItemInstance.player_id,
                    ItemInstance.item_id,
                    ItemInstance.quantity,
                ))
                .where(ItemInstance.player_id == player_id)
            )
            stacks_all = result_inv.scalars().all()
            used_slots = sum(
                1 for item in stacks_all
                if not item.is_equipment and not item.is_fish and not item.is_inscription
            )
            effective_capacity = await player.get_effective_inventory_capacity(session)
            free_slots = max(0, effective_capacity - used_slots)
            # 已有同类堆叠的剩余空间（负数视为0，避免超量堆叠干扰）
            stack_space = sum(
                max(0, inv.available_space) for inv in stacks_all
                if inv.item_id == template_id and not inv.is_equipment
            )
            addable = min(quantity, stack_space + free_slots * STACK_SIZE)

        if addable <= 0:
            return 0

        # 填充已有堆叠
        stacks = sorted(
            (inv for inv in stacks_all if inv.item_id == template_id and not inv.is_equipment),
            key=lambda inv: inv.id or 0,
        )
        remaining = addable
        for inv in stacks:
            if remaining == 0:
                break
            space = max(0, inv.available_space)
            if space == 0:
                continue
            take = min(space, remaining)
            inv.quantity += take
            remaining -= take
            session.add(inv)

        # 剩余数量分新堆
        while remaining > 0:
            put_qty = min(STACK_SIZE, remaining)
            session.add(ItemInstance(player_id=player_id, item_id=template_id, quantity=put_qty))
            remaining -= put_qty

        await session.flush()
        return addable

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
        if remaining > 0:
            # 并发等特殊情况下可能出现数量不足，抛出异常由上层回滚处理
            raise ValueError("物品数量不足")
        return True
