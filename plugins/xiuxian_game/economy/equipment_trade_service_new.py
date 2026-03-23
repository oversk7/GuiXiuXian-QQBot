"""
装备实例交易服务 - DI架构版本

改造自原版equipment_trade_service.py，采用混合设计模式：
1. 构造函数注入Repository依赖
2. 4个纯计算方法保留为静态方法（无数据库操作）
3. 5个数据访问方法改为实例方法（通过Repository访问数据）
4. 移除session参数，由外部UnitOfWork控制事务

改造日期: 2025-11-29
"""

from typing import List, Tuple, Optional
from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.repositories.market_order_repository import MarketOrderRepository
from ..models.inventory import ItemInstance
from ..config import config


class EquipmentTradeService:
    """装备实例交易服务类 - DI版本

    混合设计模式：
    - 静态方法：4个纯计算函数（判断、摘要生成、列表格式化、价值估算）
    - 实例方法：5个数据访问方法（通过Repository操作数据）
    """

    def __init__(
        self,
        item_repo: ItemRepository,
        market_order_repo: MarketOrderRepository
    ):
        """
        初始化装备交易服务

        Args:
            item_repo: 物品仓储
            market_order_repo: 市场订单仓储
        """
        self._item_repo = item_repo
        self._market_order_repo = market_order_repo

    # ==================== 静态方法：纯计算函数 ====================

    @staticmethod
    def is_equipment_trade(item_id: str) -> bool:
        """判断是否为装备交易（纯函数）

        Args:
            item_id: 物品ID

        Returns:
            True表示是装备类型，False表示不是
        """
        item_config = config.items_config["by_id"].get(item_id)
        return item_config and item_config.type.value == "EQUIPMENT"

    @staticmethod
    def generate_equipment_summary(equipment: ItemInstance) -> str:
        """生成装备摘要信息用于显示（含稀有度、词缀、铭文）

        Args:
            equipment: 装备实例

        Returns:
            装备摘要字符串（包含稀有度、名称、升阶、宝石、词缀、铭文、耐久度等信息）
        """
        if not equipment.is_equipment:
            return equipment.config.name

        tpl = equipment.config
        # 稀有度图标 + 名称
        parts = [tpl.get_display_name()]

        # 升阶等级
        if equipment.upgrade_level > 0:
            parts.append(f"+{equipment.upgrade_level}阶")

        # 宝石镶嵌信息
        if equipment.available_gem_slots > 0:
            used_slots = equipment.used_gem_slots
            total_slots = equipment.available_gem_slots
            if used_slots > 0:
                parts.append(f"[💎{used_slots}/{total_slots}]")
            else:
                parts.append(f"[🔘{total_slots}]")

        # 词缀数量
        from ..item.affix_service import get_affixes_from_equipment
        affixes = get_affixes_from_equipment(equipment.extra_attrs)
        if affixes:
            parts.append(f"🔮{len(affixes)}词缀")

        # 铭文数量
        from ..item.inscription_service import get_inscriptions_from_equipment
        inscriptions = get_inscriptions_from_equipment(equipment.gem_slots_data)
        if inscriptions:
            parts.append(f"📜{len(inscriptions)}铭文")

        # 耐久度（低于80%时显示）
        if tpl:
            durability_ratio = equipment.durability / tpl.durability
            if durability_ratio < 0.8:
                parts.append(f"🛠️{equipment.durability}/{tpl.durability}")

        return " ".join(parts)

    @staticmethod
    def format_equipment_selection_list(equipment_list: List[ItemInstance]) -> List[str]:
        """格式化装备选择列表（纯函数）

        Args:
            equipment_list: 装备实例列表

        Returns:
            格式化后的列表字符串列表
        """
        lines = []
        for i, eq in enumerate(equipment_list, 1):
            summary = EquipmentTradeService.generate_equipment_summary(eq)
            lines.append(f"{i}. 🆔{eq.id} {summary}")
        return lines

    @staticmethod
    def calculate_equipment_value_range(equipment: ItemInstance) -> Tuple[int, int]:
        """计算装备价值范围（用于估价参考）（纯函数）

        Args:
            equipment: 装备实例

        Returns:
            (最低价格, 最高价格) 元组
        """
        if not equipment.is_equipment or not equipment.config:
            return 0, 0

        base_value = equipment.config.price

        # 升阶加成
        upgrade_multiplier = equipment.get_upgrade_bonus_multiplier()
        value_with_upgrade = int(base_value * upgrade_multiplier)

        # 宝石价值估算
        gem_value = 0
        if equipment.gem_slots_data:
            for gem_item_id in equipment.gem_slots_data.values():
                gem_config = config.items_config["by_id"].get(gem_item_id)
                if gem_config:
                    gem_value += gem_config.price

        # 耐久度影响
        durability_ratio = equipment.durability / equipment.config.durability if equipment.config.durability > 0 else 1.0
        durability_factor = max(0.5, durability_ratio)  # 最低50%价值

        total_value = int((value_with_upgrade + gem_value) * durability_factor)

        # 返回建议价格范围（-20% ~ +30%）
        min_price = int(total_value * 0.8)
        max_price = int(total_value * 1.3)

        return min_price, max_price

    # ==================== 实例方法：数据访问函数 ====================

    async def get_player_equipment_list(
        self, player_id: str, item_id: str
    ) -> List[ItemInstance]:
        """获取玩家指定装备的所有实例，按品质排序

        Args:
            player_id: 玩家ID
            item_id: 装备物品ID

        Returns:
            装备实例列表（按升阶等级降序，ID升序）
        """
        return await self._item_repo.get_player_equipment_list(
            player_id, item_id, equipped=False
        )

    async def freeze_equipment(self, equipment: ItemInstance) -> bool:
        """冻结装备实例（标记为交易中）

        Args:
            equipment: 装备实例

        Returns:
            True表示冻结成功，False表示冻结失败（已装备或已在交易中）
        """
        if equipment.equipped:
            return False

        # 检查是否已经在交易中
        existing_order = await self._market_order_repo.find_by_equipment_instance(equipment.id)

        if existing_order:
            return False  # 已经在交易中

        # 调用Repository冻结装备
        return await self._item_repo.freeze_equipment(equipment)

    async def unfreeze_equipment(self, equipment: ItemInstance):
        """解冻装备实例

        Args:
            equipment: 装备实例
        """
        await self._item_repo.unfreeze_equipment(equipment)

    async def transfer_equipment(
        self, equipment: ItemInstance, new_owner_id: str
    ) -> bool:
        """转移装备所有权

        Args:
            equipment: 装备实例
            new_owner_id: 新拥有者ID

        Returns:
            True表示转移成功，False表示转移失败
        """
        # 先解冻装备
        await self.unfreeze_equipment(equipment)

        # 调用Repository转移装备
        return await self._item_repo.transfer_equipment(equipment, new_owner_id)

    async def get_equipment_by_instance_id(
        self, instance_id: int
    ) -> Optional[ItemInstance]:
        """根据实例ID获取装备

        Args:
            instance_id: 装备实例ID

        Returns:
            装备实例，不存在返回None
        """
        return await self._item_repo.get_by_id(instance_id)
