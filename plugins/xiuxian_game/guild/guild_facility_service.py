"""
公会设施服务 - DI架构版本

将GuildFacilityService改造为依赖注入架构，处理传送阵、丹房、仓库等功能
"""

from typing import Dict, List, Tuple, Optional
from datetime import datetime, date, timedelta
import random
import math

from ..models.guild import Guild, GuildBuilding, BuildingType, GuildWarehouseItem, GuildAlchemyProduction, GuildTeleportLog, GuildWarehouseLog, WarehouseLogType
from ..models.player import Player
from ..models.inventory import ItemInstance, STACK_SIZE
from ..config import config
from ..infrastructure.repositories.guild_repository import GuildRepository
from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.repositories.guild_teleport_log_repository import GuildTeleportLogRepository
from ..infrastructure.repositories.guild_alchemy_production_repository import GuildAlchemyProductionRepository
from ..infrastructure.repositories.guild_warehouse_item_repository import GuildWarehouseItemRepository
from ..infrastructure.repositories.guild_warehouse_log_repository import GuildWarehouseLogRepository
from .guild_building_service import GuildBuildingService


class GuildFacilityService:
    """公会设施服务类 - DI架构版本"""

    # 丹房产出的丹药配置（按品质分类）
    ALCHEMY_PILLS = {
        "basic": [
            {"item_id": "spirit_elixir", "weight": 20},  # 升灵丹
            {"item_id": "life_recovery_elixir", "weight": 20},  # 回生丹
            {"item_id": "soul_recovery_elixir", "weight": 20},  # 凝魂丹
            {"item_id": "berry_shield_elixir", "weight": 10},  # 阴莓护体丹
            {"item_id": "blood_pact", "weight": 15},  # 血契丹
            {"item_id": "revive_potion", "weight": 10},  # 仿制还魂丹
        ],
        "intermediate": [
            {"item_id": "blood_heart_elixir", "weight": 20},  # 血心丹
            {"item_id": "great_life_recovery_elixir", "weight": 18},  # 大回生丹
            {"item_id": "great_soul_recovery_elixir", "weight": 18},  # 大凝魂丹
            {"item_id": "perfect_revive_elixir", "weight": 12},  # 完美还魂丹
            {"item_id": "iron_body_elixir", "weight": 10},  # 金刚体丹
            {"item_id": "vine_body_elixir", "weight": 8},  # 魂藤淬骨丹
            {"item_id": "orchid_battle_elixir", "weight": 8},  # 血兰战魄丹
        ],
        "advanced": [
            {"item_id": "night_soul_elixir", "weight": 18},  # 夜魂丹
            {"item_id": "divine_blessing_elixir", "weight": 12},  # 神明恩赐丹
            {"item_id": "supreme_revive_elixir", "weight": 8},  # 真还魂丹
            {"item_id": "void_eye_elixir", "weight": 10},  # 虚眼丹
            {"item_id": "battle_god_elixir", "weight": 10},  # 战神丹
            {"item_id": "fortune_elixir", "weight": 10},  # 鸿运丹
            {"item_id": "wisdom_elixir", "weight": 8},  # 悟道丹
            {"item_id": "nightmare_break_elixir", "weight": 7},  # 噩梦破境丹
        ],
        "master": [
            {"item_id": "world_power_elixir", "weight": 6},  # 世界之力丹
            {"item_id": "berserker_elixir", "weight": 10},  # 狂战丹
            {"item_id": "shadow_step_elixir", "weight": 10},  # 影步丹
            {"item_id": "eagle_eye_elixir", "weight": 8},  # 鹰眼丹
            {"item_id": "combo_master_elixir", "weight": 6},  # 连击丹
            {"item_id": "vitality_elixir", "weight": 8},  # 生机丹
            {"item_id": "swift_wind_elixir", "weight": 8},  # 疾风丹
        ],
        "legendary": [
            {"item_id": "berserk_fury_elixir", "weight": 8},  # 暴怒丹
            {"item_id": "strength_essence_elixir", "weight": 4},  # 力之精华丹
            {"item_id": "agility_essence_elixir", "weight": 4},  # 敏之精华丹
            {"item_id": "defense_essence_elixir", "weight": 4},  # 防之精华丹
            {"item_id": "vitality_essence_elixir", "weight": 4},  # 体之精华丹
            {"item_id": "fate_contract_elixir", "weight": 4},  # 命运契丹
            {"item_id": "cursed_essence_elixir", "weight": 3},  # 诅咒精魄丹
            {"item_id": "reforge_strength_elixir", "weight": 1},  # 归元破力丹
            {"item_id": "reforge_agility_elixir", "weight": 1},  # 归元化敏丹
            {"item_id": "reforge_defense_elixir", "weight": 1},  # 归元散防丹
            {"item_id": "reforge_vitality_elixir", "weight": 1},  # 归元化体丹
            {"item_id": "reforge_wisdom_elixir", "weight": 1},  # 归元凝神丹
            {"item_id": "reforge_luck_elixir", "weight": 1},  # 归元化运丹
            {"item_id": "void_restore_elixir", "weight": 1},  # 虚空归元丹
        ]
    }

    # 跨池产出配置：高级品质池可以产出低级池的热门丹药
    # 格式: {"当前品质": {"包含品质": 权重百分比(0-100)}}
    # 例如: "master"可以产出30%的advanced丹药
    CROSS_POOL_CONFIG = {
        "master": {
            "advanced": 25,  # 25%概率产出advanced池丹药(含虚眼丹等)
            "current": 75   # 75%概率产出master池丹药
        },
        "legendary": {
            "master": 20,    # 20%概率产出master池丹药
            "advanced": 15,  # 15%概率产出advanced池丹药(含虚眼丹等)
            "current": 65    # 65%概率产出legendary池丹药
        }
    }

    # 丹房存储上限配置（按日产量倍数）
    STORAGE_CAPACITY_MULTIPLIER = 3  # 存储上限 = 日产量 * 3

    def __init__(
        self,
        guild_repo: GuildRepository,
        building_repo: GuildBuildingRepository,
        player_repo: PlayerRepository,
        item_repo: ItemRepository,
        teleport_log_repo: GuildTeleportLogRepository,
        alchemy_production_repo: GuildAlchemyProductionRepository,
        warehouse_item_repo: GuildWarehouseItemRepository,
        warehouse_log_repo: GuildWarehouseLogRepository = None,
    ):
        self._guild_repo = guild_repo
        self._building_repo = building_repo
        self._player_repo = player_repo
        self._item_repo = item_repo
        self._teleport_log_repo = teleport_log_repo
        self._alchemy_production_repo = alchemy_production_repo
        self._warehouse_item_repo = warehouse_item_repo
        self._warehouse_log_repo = warehouse_log_repo

    @staticmethod
    def get_pill_quality_chinese(quality: str) -> str:
        """获取丹药品质的中文名称"""
        quality_map = {
            "basic": "初级",
            "intermediate": "中级",
            "advanced": "高级",
            "master": "顶级",
            "legendary": "传说"
        }
        return quality_map.get(quality, quality)

    async def can_use_teleport(self, player_id: str, guild_id: int) -> Tuple[bool, str]:
        """
        检查玩家是否可以使用传送阵

        对应原代码:
            guild_facility_service.py Line 82-131
        """
        # 检查公会是否有传送阵
        teleport_building = await self._building_repo.get_by_guild_and_type(
            guild_id, BuildingType.TELEPORT_ARRAY
        )

        if not teleport_building:
            return False, "公会尚未建造传送阵"

        # 获取传送阵效果
        building_service = GuildBuildingService(
            self._guild_repo, self._building_repo, self._item_repo
        )
        effects = building_service.get_effects_for_level(BuildingType.TELEPORT_ARRAY, teleport_building.level)
        teleport_range = effects["teleport_range"]
        daily_uses = effects["daily_uses"]

        # 检查玩家位置是否在传送范围内
        player = await self._player_repo.get_by_id(player_id)
        guild = await self._guild_repo.get_by_id(guild_id)

        if guild.base_x is None or guild.base_y is None:
            return False, "公会尚未设置基地坐标"

        # 计算距离 - 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        distance = math.sqrt((current_x - guild.base_x) ** 2 + (current_y - guild.base_y) ** 2)
        if distance > teleport_range:
            return False, f"距离公会基地太远，传送阵范围为{teleport_range}格（当前距离{distance:.1f}格）"

        # 检查今日使用次数
        today = date.today()
        used_count = await self._teleport_log_repo.get_today_teleport_count(
            player_id, guild_id, today
        )

        if used_count >= daily_uses:
            return False, f"今日传送次数已用完（{used_count}/{daily_uses}）"

        return True, "可以传送"

    async def teleport_to_guild(self, player_id: str, guild_id: int) -> Tuple[bool, str]:
        """
        传送玩家到公会基地

        对应原代码:
            guild_facility_service.py Line 133-168
        """
        can_teleport, reason = await self.can_use_teleport(player_id, guild_id)
        if not can_teleport:
            return False, reason

        player = await self._player_repo.get_by_id(player_id)
        guild = await self._guild_repo.get_by_id(guild_id)

        # 记录传送前位置（使用当前活跃坐标）
        from_x, from_y = player.get_current_coordinates()

        # 传送到公会基地（只能在现实世界使用）
        if player.is_in_dungeon():
            return False, "⛔ 在诡域中无法使用公会传送功能"

        # 更新现实世界坐标
        player.real_world_x = guild.base_x
        player.real_world_y = guild.base_y
        player.x = guild.base_x
        player.y = guild.base_y
        await self._player_repo.update(player)

        # 记录传送日志
        teleport_log = GuildTeleportLog(
            guild_id=guild_id,
            player_id=player_id,
            from_x=from_x,
            from_y=from_y,
            to_x=guild.base_x,
            to_y=guild.base_y
        )
        await self._teleport_log_repo.add(teleport_log)

        return True, f"传送成功！从({from_x}, {from_y})传送到公会基地({guild.base_x}, {guild.base_y})"

    async def get_alchemy_production(self, guild_id: int) -> List[Dict]:
        """
        获取丹房产出列表

        对应原代码:
            guild_facility_service.py Line 170-191
        """
        productions = await self._alchemy_production_repo.get_unclaimed_productions(guild_id)

        result = []
        for prod in productions:
            item_config = config.items_config["by_id"].get(prod.item_id)
            if item_config:
                result.append({
                    "id": prod.id,
                    "item_id": prod.item_id,
                    "item_name": item_config.name,
                    "quantity": prod.quantity,
                    "produced_at": prod.produced_at
                })

        return result

    async def get_alchemy_production_grouped(self, guild_id: int) -> List[Dict]:
        """
        获取丹房产出列表（按物品类型分组）

        对应原代码:
            guild_facility_service.py Line 193-229
        """
        productions = await self._alchemy_production_repo.get_unclaimed_productions(guild_id)

        # 按物品ID分组统计
        grouped = {}
        production_ids = {}  # 记录每种物品对应的产出记录ID列表

        for prod in productions:
            item_config = config.items_config["by_id"].get(prod.item_id)
            if item_config:
                if prod.item_id not in grouped:
                    grouped[prod.item_id] = {
                        "item_id": prod.item_id,
                        "item_name": item_config.name,
                        "total_quantity": 0,
                        "points_cost": max(1, item_config.price // 100)  # 单个积分成本
                    }
                    production_ids[prod.item_id] = []

                grouped[prod.item_id]["total_quantity"] += prod.quantity
                production_ids[prod.item_id].append(prod.id)

        # 转换为列表并添加产出记录ID
        result = []
        for item_id, data in grouped.items():
            data["production_ids"] = production_ids[item_id]
            result.append(data)

        # 按物品名称排序
        result.sort(key=lambda x: x["item_name"])
        return result

    async def claim_alchemy_item(self, player_id: str, guild_id: int, production_id: int, points_cost: int) -> Tuple[bool, str]:
        """
        用积分兑换丹房产出的丹药

        对应原代码:
            guild_facility_service.py Line 231-266
        """
        # 检查产出记录
        production = await self._alchemy_production_repo.get_by_id(production_id)
        if not production or production.guild_id != guild_id:
            return False, "产出记录不存在"

        if production.claimed:
            return False, "该物品已被领取"

        # 检查玩家积分
        player = await self._player_repo.get_by_id(player_id)
        if player.gold2 < points_cost:
            return False, f"积分不足，需要{points_cost}积分"

        # 先添加物品到玩家背包，成功后再扣积分（背包满时不能吞积分）
        try:
            await ItemInstance.add_item(self._item_repo._session, player_id, production.item_id, production.quantity)
        except ValueError as e:
            return False, f"背包空间不足：{str(e)}"

        # 扣除积分
        player.gold2 -= points_cost
        await self._player_repo.update(player)

        # 标记为已领取
        production = await self._alchemy_production_repo.mark_as_claimed(production, player_id)

        item_config = config.items_config["by_id"].get(production.item_id)
        item_name = item_config.name if item_config else production.item_id

        return True, f"成功兑换{item_name}×{production.quantity}，消耗{points_cost}积分"

    async def claim_alchemy_item_by_name(self, player_id: str, guild_id: int, item_name: str, quantity: int) -> Tuple[bool, str]:
        """
        按名称和数量兑换丹房产出的丹药

        对应原代码:
            guild_facility_service.py Line 268-322
        """
        # 获取分组后的产出列表
        grouped_productions = await self.get_alchemy_production_grouped(guild_id)

        # 查找指定名称的丹药
        target_item = None
        for item in grouped_productions:
            if item["item_name"] == item_name:
                target_item = item
                break

        if not target_item:
            return False, f"未找到丹药：{item_name}"

        if quantity > target_item["total_quantity"]:
            return False, f"数量不足，{item_name}库存只有{target_item['total_quantity']}个"

        if quantity <= 0:
            return False, "兑换数量必须大于0"

        # 计算总积分成本
        total_points_cost = target_item["points_cost"] * quantity

        # 检查玩家积分
        player = await self._player_repo.get_by_id(player_id)
        if player.gold2 < total_points_cost:
            return False, f"积分不足，需要{total_points_cost}积分，当前拥有{player.gold2}积分"

        # 先添加物品到玩家背包，成功后再扣积分（背包满时不能吞积分）
        try:
            await ItemInstance.add_item(self._item_repo._session, player_id, target_item["item_id"], quantity)
        except ValueError as e:
            return False, f"背包空间不足：{str(e)}"

        # 扣除积分
        player.gold2 -= total_points_cost
        await self._player_repo.update(player)

        # 标记对应数量的产出记录为已领取
        claimed_count = 0
        for production_id in target_item["production_ids"]:
            if claimed_count >= quantity:
                break

            production = await self._alchemy_production_repo.get_by_id(production_id)
            if production and not production.claimed:
                production = await self._alchemy_production_repo.mark_as_claimed(production, player_id)
                claimed_count += production.quantity

        return True, f"成功兑换{item_name}×{quantity}，消耗{total_points_cost}积分"

    async def get_alchemy_storage_capacity(self, guild_id: int) -> int:
        """
        获取丹房存储上限

        Args:
            guild_id: 公会ID

        Returns:
            存储上限数量

        对应原代码:
            新增功能
        """
        alchemy_building = await self._building_repo.get_by_guild_and_type(
            guild_id, BuildingType.ALCHEMY_ROOM
        )

        if not alchemy_building:
            return 0

        building_service = GuildBuildingService(
            self._guild_repo, self._building_repo, self._item_repo
        )
        bonuses = await building_service.get_guild_bonuses(guild_id)
        daily_production = bonuses["daily_alchemy_production"]

        # 存储上限 = 日产量 * 倍数
        return daily_production * self.STORAGE_CAPACITY_MULTIPLIER

    async def get_alchemy_storage_used(self, guild_id: int) -> int:
        """
        获取丹房当前已使用的存储空间

        Args:
            guild_id: 公会ID

        Returns:
            已使用的存储数量

        对应原代码:
            新增功能
        """
        unclaimed_productions = await self._alchemy_production_repo.get_unclaimed_productions(guild_id)
        return len(unclaimed_productions)

    def _select_pill_pool(self, primary_quality: str) -> str:
        """
        根据跨池配置选择实际使用的丹药池

        Args:
            primary_quality: 主要品质(如"master", "legendary")

        Returns:
            实际使用的丹药池品质

        对应原代码:
            新增功能
        """
        # 检查是否有跨池配置
        cross_pool_config = self.CROSS_POOL_CONFIG.get(primary_quality)
        if not cross_pool_config:
            return primary_quality

        # 按权重随机选择池
        rand_value = random.randint(1, 100)
        current_percentage = 0

        for pool_quality, percentage in cross_pool_config.items():
            current_percentage += percentage
            if rand_value <= current_percentage:
                return pool_quality if pool_quality != "current" else primary_quality

        return primary_quality

    async def generate_daily_alchemy_production(self, guild_id: int) -> int:
        """
        生成每日丹房产出

        对应原代码:
            guild_facility_service.py Line 324-390
        """
        # 检查是否有丹房
        alchemy_building = await self._building_repo.get_by_guild_and_type(
            guild_id, BuildingType.ALCHEMY_ROOM
        )

        if not alchemy_building:
            return 0

        # 获取丹房效果
        building_service = GuildBuildingService(
            self._guild_repo, self._building_repo, self._item_repo
        )
        effects = building_service.get_effects_for_level(
            BuildingType.ALCHEMY_ROOM, alchemy_building.level
        )
        bonuses = await building_service.get_guild_bonuses(guild_id)
        daily_production = bonuses["daily_alchemy_production"]
        pill_quality = effects["pill_quality"]

        # 检查存储空间
        storage_capacity = await self.get_alchemy_storage_capacity(guild_id)
        storage_used = await self.get_alchemy_storage_used(guild_id)

        if storage_used >= storage_capacity:
            return -1  # 存储已满,返回特殊值

        # 检查今日是否已生成
        today = date.today()
        today_count = await self._alchemy_production_repo.get_today_production_count(guild_id, today)

        if today_count >= daily_production:
            return 0  # 今日已生成足够数量

        # 生成丹药
        pills_to_generate = min(daily_production - today_count, storage_capacity - storage_used)
        generated_count = 0

        for _ in range(pills_to_generate):
            # 根据跨池配置选择实际使用的丹药池
            actual_pill_quality = self._select_pill_pool(pill_quality)

            # 根据品质随机选择丹药
            pill_pool = self.ALCHEMY_PILLS.get(actual_pill_quality, [])
            if not pill_pool:
                continue

            # 按权重随机选择
            total_weight = sum(pill["weight"] for pill in pill_pool)
            rand_value = random.randint(1, total_weight)

            current_weight = 0
            selected_pill = None
            for pill in pill_pool:
                current_weight += pill["weight"]
                if rand_value <= current_weight:
                    selected_pill = pill
                    break

            if selected_pill:
                production = GuildAlchemyProduction(
                    guild_id=guild_id,
                    item_id=selected_pill["item_id"],
                    quantity=1
                )
                await self._alchemy_production_repo.add(production)
                generated_count += 1

        return generated_count

    async def get_warehouse_capacity(self, guild_id: int) -> int:
        """
        获取公会仓库容量

        对应原代码:
            guild_facility_service.py Line 392-405
        """
        warehouse_building = await self._building_repo.get_by_guild_and_type(
            guild_id, BuildingType.GUILD_WAREHOUSE
        )

        if not warehouse_building:
            return 0

        building_service = GuildBuildingService(
            self._guild_repo, self._building_repo, self._item_repo
        )
        effects = building_service.get_effects_for_level(BuildingType.GUILD_WAREHOUSE, warehouse_building.level)
        return effects["storage_slots"]

    async def get_warehouse_items(self, guild_id: int) -> List[Dict]:
        """
        获取公会仓库物品列表，合并显示相同物品的多个堆叠

        对应原代码:
            guild_facility_service.py Line 407-440
        """
        items = await self._warehouse_item_repo.get_all_by_guild_id(guild_id)

        # 按物品ID分组合并
        item_groups = {}
        for item in items:
            item_config = config.items_config["by_id"].get(item.item_id)
            if item_config:
                if item.item_id not in item_groups:
                    # 找到最新的存入者作为代表（因为items已按deposited_at降序排列，第一个就是最新的）
                    depositor = await self._player_repo.get_by_id(item.deposited_by)
                    item_groups[item.item_id] = {
                        "item_id": item.item_id,
                        "item_name": item_config.name,
                        "quantity": 0,
                        "deposited_by": depositor.nickname if depositor else "未知",
                        "deposited_at": item.deposited_at,  # 使用最新的存入时间
                        "earliest_deposited_at": item.deposited_at,  # 记录最早的存入时间
                    }
                else:
                    # 更新最早的存入时间
                    if item.deposited_at < item_groups[item.item_id]["earliest_deposited_at"]:
                        item_groups[item.item_id]["earliest_deposited_at"] = item.deposited_at

                item_groups[item.item_id]["quantity"] += item.quantity

        # 转换为列表并按最早存入时间排序（保证稳定的排序）
        result = list(item_groups.values())
        result.sort(key=lambda x: x["earliest_deposited_at"])

        return result

    async def deposit_to_warehouse(self, player_id: str, guild_id: int, item_id: str, quantity: int) -> Tuple[bool, str]:
        """
        存入物品到公会仓库

        对应原代码:
            guild_facility_service.py Line 442-524
        """
        # 检查是否有仓库
        capacity = await self.get_warehouse_capacity(guild_id)
        if capacity == 0:
            return False, "公会尚未建造仓库"

        # 检查物品是否为诡异道具（材料类型）
        item_config = config.items_config["by_id"].get(item_id)
        if not item_config or item_config.type.value != "MATERIAL":
            return False, "只能存入诡异道具（材料类型）"

        # 检查玩家是否有该物品（需要统计所有堆叠的总数量）
        player_items = await self._item_repo.get_by_player_and_item_id(player_id, item_id)
        total_quantity = sum(item.quantity for item in player_items)

        if total_quantity < quantity:
            return False, f"你没有足够的该物品（拥有{total_quantity}，需要{quantity}）"

        # 获取仓库中该物品的现有堆叠
        existing_stacks = await self._warehouse_item_repo.get_by_guild_and_item_id(guild_id, item_id)

        # 计算现有数量和格子数
        existing_quantity = sum(stack.quantity for stack in existing_stacks)
        new_total_quantity = existing_quantity + quantity

        # 计算需要的格子数（每格最多堆叠100个）
        from math import ceil
        new_slots_needed = ceil(new_total_quantity / STACK_SIZE)
        current_slots_for_this_item = len(existing_stacks)
        additional_slots_needed = new_slots_needed - current_slots_for_this_item

        # 检查仓库总格子数
        current_total_slots = await self._warehouse_item_repo.get_total_slots_count(guild_id)

        if current_total_slots + additional_slots_needed > capacity:
            # 计算当前最多能存入多少（现有堆叠剩余空间 + 空闲格子可容纳的数量）
            existing_space = sum(STACK_SIZE - s.quantity for s in existing_stacks)
            free_slots = capacity - current_total_slots
            max_deposit = existing_space + free_slots * STACK_SIZE
            return False, (
                f"仓库格子不足（当前{current_total_slots}/{capacity}格），"
                f"该物品最多还能存入{max_deposit}个"
            )

        # 扣除玩家物品（使用统一的消耗方法处理多个堆叠）
        try:
            success_consume = await ItemInstance.consume_item(self._item_repo._session, player_id, item_id, quantity)
            if not success_consume:
                return False, "扣除物品失败"
        except ValueError as e:
            return False, f"扣除物品失败：{str(e)}"

        # 按照堆叠规则存入仓库
        remaining_quantity = quantity

        # 先填充现有的未满堆叠
        for stack in existing_stacks:
            if remaining_quantity <= 0:
                break
            available_space = STACK_SIZE - stack.quantity
            if available_space > 0:
                add_to_stack = min(available_space, remaining_quantity)
                stack.quantity += add_to_stack
                remaining_quantity -= add_to_stack
                await self._warehouse_item_repo.update(stack)

        # 剩余数量创建新堆叠
        while remaining_quantity > 0:
            stack_quantity = min(STACK_SIZE, remaining_quantity)
            warehouse_item = GuildWarehouseItem(
                guild_id=guild_id,
                item_id=item_id,
                quantity=stack_quantity,
                deposited_by=player_id
            )
            await self._warehouse_item_repo.add(warehouse_item)
            remaining_quantity -= stack_quantity

        # 写入仓库操作日志
        await self._write_warehouse_log(
            guild_id, player_id, WarehouseLogType.DEPOSIT,
            item_id, item_config.name, quantity
        )

        return True, f"成功存入{item_config.name}×{quantity}"

    async def _do_withdraw(self, player_id: str, guild_id: int, item_id: str, item_name: str, quantity: int) -> Tuple[bool, str]:
        """执行仓库取出的核心逻辑"""
        # 检查玩家背包容量
        try:
            await ItemInstance.add_item(self._item_repo._session, player_id, item_id, quantity)
        except ValueError as e:
            return False, f"背包空间不足：{str(e)}"

        # 从实际的堆叠中扣除物品（按照存入时间降序，优先取出最新的）
        warehouse_stacks = await self._warehouse_item_repo.get_by_guild_and_item_id_desc(
            guild_id, item_id
        )

        remaining_to_withdraw = quantity
        for stack in warehouse_stacks:
            if remaining_to_withdraw <= 0:
                break

            withdraw_from_stack = min(stack.quantity, remaining_to_withdraw)
            stack.quantity -= withdraw_from_stack
            remaining_to_withdraw -= withdraw_from_stack

            if stack.quantity <= 0:
                await self._warehouse_item_repo.delete(stack.id)
            else:
                await self._warehouse_item_repo.update(stack)

        # 写入仓库操作日志
        await self._write_warehouse_log(
            guild_id, player_id, WarehouseLogType.WITHDRAW,
            item_id, item_name, quantity
        )

        return True, f"成功取出{item_name}×{quantity}"

    async def withdraw_from_warehouse(self, player_id: str, guild_id: int, item_index: int, quantity: int) -> Tuple[bool, str]:
        """从公会仓库按序号取出物品"""
        # 获取仓库物品列表（合并显示的）
        items = await self.get_warehouse_items(guild_id)

        if item_index < 1 or item_index > len(items):
            return False, "无效的物品序号"

        selected_item = items[item_index - 1]

        if selected_item["quantity"] < quantity:
            return False, f"仓库中该物品数量不足（仅有{selected_item['quantity']}个）"

        item_config = config.items_config["by_id"].get(selected_item["item_id"])
        display_name = item_config.name if item_config else selected_item["item_id"]

        return await self._do_withdraw(player_id, guild_id, selected_item["item_id"], display_name, quantity)

    async def withdraw_from_warehouse_by_name(self, player_id: str, guild_id: int, item_name: str, quantity: int) -> Tuple[bool, str]:
        """从公会仓库按物品名取出物品"""
        # 通过物品名查找 item_id
        item_config = config.items_config["by_name"].get(item_name)
        if not item_config:
            return False, f"未找到名为【{item_name}】的物品"

        # 检查仓库中是否有该物品
        warehouse_stacks = await self._warehouse_item_repo.get_by_guild_and_item_id_desc(
            guild_id, item_config.item_id
        )
        total_quantity = sum(s.quantity for s in warehouse_stacks)
        if total_quantity == 0:
            return False, f"仓库中没有【{item_name}】"
        if total_quantity < quantity:
            return False, f"仓库中该物品数量不足（仅有{total_quantity}个）"

        return await self._do_withdraw(player_id, guild_id, item_config.item_id, item_name, quantity)

    async def _write_warehouse_log(
        self, guild_id: int, player_id: str,
        operation: WarehouseLogType, item_id: str, item_name: str, quantity: int
    ):
        """写入仓库操作日志，并自动清理超出上限的旧记录"""
        if not self._warehouse_log_repo:
            return

        # 获取玩家昵称
        player = await self._player_repo.get_by_id(player_id)
        player_name = player.nickname if player else "未知"

        log = GuildWarehouseLog(
            guild_id=guild_id,
            player_id=player_id,
            player_name=player_name,
            operation=operation,
            item_id=item_id,
            item_name=item_name,
            quantity=quantity,
        )
        await self._warehouse_log_repo.add(log)

        # 自动清理超出上限的旧日志
        await self._warehouse_log_repo.cleanup_old_logs(guild_id)

    async def get_warehouse_logs(self, guild_id: int, limit: int = 20) -> List[Dict]:
        """
        获取公会仓库操作日志

        Args:
            guild_id: 公会ID
            limit: 返回条数

        Returns:
            日志列表
        """
        if not self._warehouse_log_repo:
            return []

        logs = await self._warehouse_log_repo.get_recent_by_guild(guild_id, limit)

        result = []
        for log in logs:
            result.append({
                "player_name": log.player_name,
                "operation": "存入" if log.operation == WarehouseLogType.DEPOSIT else "取出",
                "item_name": log.item_name,
                "quantity": log.quantity,
                "operated_at": log.operated_at,
            })
        return result
