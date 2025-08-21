"""
公会设施服务 - 处理传送阵、丹房、仓库等功能
"""
from typing import Dict, List, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, delete
from datetime import datetime, date, timedelta
import random
import math

from ..models.guild import Guild, GuildBuilding, BuildingType, GuildWarehouseItem, GuildAlchemyProduction, GuildTeleportLog
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..config import config
from .guild_building_service import GuildBuildingService


class GuildFacilityService:
    """公会设施服务类"""
    
    # 丹房产出的丹药配置（按品质分类）
    ALCHEMY_PILLS = {
        "basic": [
            {"item_id": "blood_pact", "weight": 30},
            {"item_id": "revive_potion", "weight": 30},
            {"item_id": "spirit_elixir", "weight": 20},  # 升灵丹
        ],
        "intermediate": [
            {"item_id": "blood_pact", "weight": 25},  # 血契丹
            {"item_id": "spirit_elixir", "weight": 25},
            {"item_id": "blood_heart_elixir", "weight": 15},  # 血心丹
        ],
        "advanced": [
            {"item_id": "night_soul_elixir", "weight": 10},  # 夜魂丹
            {"item_id": "void_eye_elixir", "weight": 20},
        ]
    }

    @staticmethod
    def get_pill_quality_chinese(quality: str) -> str:
        """获取丹药品质的中文名称"""
        quality_map = {
            "basic": "初级",
            "intermediate": "中级",
            "advanced": "高级"
        }
        return quality_map.get(quality, quality)

    @staticmethod
    async def can_use_teleport(session: AsyncSession, player_id: str, guild_id: int) -> Tuple[bool, str]:
        """检查玩家是否可以使用传送阵"""
        # 检查公会是否有传送阵
        stmt = select(GuildBuilding).where(
            and_(GuildBuilding.guild_id == guild_id, GuildBuilding.building_type == BuildingType.TELEPORT_ARRAY)
        )
        teleport_building = (await session.execute(stmt)).scalars().first()
        
        if not teleport_building:
            return False, "公会尚未建造传送阵"
        
        # 获取传送阵效果
        config = GuildBuildingService.BUILDING_CONFIGS[BuildingType.TELEPORT_ARRAY]
        effects = config["effects"][teleport_building.level]
        teleport_range = effects["teleport_range"]
        daily_uses = effects["daily_uses"]
        
        # 检查玩家位置是否在传送范围内
        player = await session.get(Player, player_id)
        guild = await session.get(Guild, guild_id)
        
        if guild.base_x is None or guild.base_y is None:
            return False, "公会尚未设置基地坐标"
        
        # 计算距离 - 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        distance = math.sqrt((current_x - guild.base_x) ** 2 + (current_y - guild.base_y) ** 2)
        if distance > teleport_range:
            return False, f"距离公会基地太远，传送阵范围为{teleport_range}格（当前距离{distance:.1f}格）"
        
        # 检查今日使用次数
        today = date.today()
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())
        
        stmt = select(func.count(GuildTeleportLog.id)).where(
            and_(
                GuildTeleportLog.player_id == player_id,
                GuildTeleportLog.guild_id == guild_id,
                GuildTeleportLog.teleported_at >= today_start,
                GuildTeleportLog.teleported_at <= today_end
            )
        )
        used_count = (await session.execute(stmt)).scalar_one()
        
        if used_count >= daily_uses:
            return False, f"今日传送次数已用完（{used_count}/{daily_uses}）"
        
        return True, "可以传送"
    
    @staticmethod
    async def teleport_to_guild(session: AsyncSession, player_id: str, guild_id: int) -> Tuple[bool, str]:
        """传送玩家到公会基地"""
        can_teleport, reason = await GuildFacilityService.can_use_teleport(session, player_id, guild_id)
        if not can_teleport:
            return False, reason
        
        player = await session.get(Player, player_id)
        guild = await session.get(Guild, guild_id)
        
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
        session.add(player)
        
        # 记录传送日志
        teleport_log = GuildTeleportLog(
            guild_id=guild_id,
            player_id=player_id,
            from_x=from_x,
            from_y=from_y,
            to_x=guild.base_x,
            to_y=guild.base_y
        )
        session.add(teleport_log)
        
        return True, f"传送成功！从({from_x}, {from_y})传送到公会基地({guild.base_x}, {guild.base_y})"
    
    @staticmethod
    async def get_alchemy_production(session: AsyncSession, guild_id: int) -> List[Dict]:
        """获取丹房产出列表"""
        stmt = select(GuildAlchemyProduction).where(
            and_(GuildAlchemyProduction.guild_id == guild_id, GuildAlchemyProduction.claimed == False)
        ).order_by(GuildAlchemyProduction.produced_at.desc())

        productions = (await session.execute(stmt)).scalars().all()

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

    @staticmethod
    async def get_alchemy_production_grouped(session: AsyncSession, guild_id: int) -> List[Dict]:
        """获取丹房产出列表（按物品类型分组）"""
        stmt = select(GuildAlchemyProduction).where(
            and_(GuildAlchemyProduction.guild_id == guild_id, GuildAlchemyProduction.claimed == False)
        ).order_by(GuildAlchemyProduction.produced_at.desc())

        productions = (await session.execute(stmt)).scalars().all()

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
    
    @staticmethod
    async def claim_alchemy_item(session: AsyncSession, player_id: str, guild_id: int, production_id: int, points_cost: int) -> Tuple[bool, str]:
        """用积分兑换丹房产出的丹药"""
        # 检查产出记录
        production = await session.get(GuildAlchemyProduction, production_id)
        if not production or production.guild_id != guild_id:
            return False, "产出记录不存在"

        if production.claimed:
            return False, "该物品已被领取"

        # 检查玩家积分
        player = await session.get(Player, player_id)
        if player.gold2 < points_cost:
            return False, f"积分不足，需要{points_cost}积分"

        # 扣除积分
        player.gold2 -= points_cost
        session.add(player)

        # 添加物品到玩家背包
        try:
            await ItemInstance.add_item(session, player_id, production.item_id, production.quantity)
        except ValueError as e:
            return False, f"背包空间不足：{str(e)}"

        # 标记为已领取
        production.claimed = True
        production.claimed_by = player_id
        production.claimed_at = datetime.now()
        session.add(production)

        item_config = config.items_config["by_id"].get(production.item_id)
        item_name = item_config.name if item_config else production.item_id

        return True, f"成功兑换{item_name}×{production.quantity}，消耗{points_cost}积分"

    @staticmethod
    async def claim_alchemy_item_by_name(session: AsyncSession, player_id: str, guild_id: int, item_name: str, quantity: int) -> Tuple[bool, str]:
        """按名称和数量兑换丹房产出的丹药"""
        # 获取分组后的产出列表
        grouped_productions = await GuildFacilityService.get_alchemy_production_grouped(session, guild_id)

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
        player = await session.get(Player, player_id)
        if player.gold2 < total_points_cost:
            return False, f"积分不足，需要{total_points_cost}积分，当前拥有{player.gold2}积分"

        # 扣除积分
        player.gold2 -= total_points_cost
        session.add(player)

        # 添加物品到玩家背包
        try:
            await ItemInstance.add_item(session, player_id, target_item["item_id"], quantity)
        except ValueError as e:
            return False, f"背包空间不足：{str(e)}"

        # 标记对应数量的产出记录为已领取
        claimed_count = 0
        for production_id in target_item["production_ids"]:
            if claimed_count >= quantity:
                break

            production = await session.get(GuildAlchemyProduction, production_id)
            if production and not production.claimed:
                production.claimed = True
                production.claimed_by = player_id
                production.claimed_at = datetime.now()
                session.add(production)
                claimed_count += production.quantity

        return True, f"成功兑换{item_name}×{quantity}，消耗{total_points_cost}积分"
    
    @staticmethod
    async def generate_daily_alchemy_production(session: AsyncSession, guild_id: int) -> int:
        """生成每日丹房产出"""
        # 检查是否有丹房
        stmt = select(GuildBuilding).where(
            and_(GuildBuilding.guild_id == guild_id, GuildBuilding.building_type == BuildingType.ALCHEMY_ROOM)
        )
        alchemy_building = (await session.execute(stmt)).scalars().first()
        
        if not alchemy_building:
            return 0
        
        # 获取丹房效果
        config = GuildBuildingService.BUILDING_CONFIGS[BuildingType.ALCHEMY_ROOM]
        effects = config["effects"][alchemy_building.level]
        daily_production = effects["daily_production"]
        pill_quality = effects["pill_quality"]
        
        # 检查今日是否已生成
        today = date.today()
        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())
        
        stmt = select(func.count(GuildAlchemyProduction.id)).where(
            and_(
                GuildAlchemyProduction.guild_id == guild_id,
                GuildAlchemyProduction.produced_at >= today_start,
                GuildAlchemyProduction.produced_at <= today_end
            )
        )
        today_count = (await session.execute(stmt)).scalar_one()
        
        if today_count >= daily_production:
            return 0  # 今日已生成足够数量
        
        # 生成丹药
        pills_to_generate = daily_production - today_count
        generated_count = 0
        
        for _ in range(pills_to_generate):
            # 根据品质随机选择丹药
            pill_pool = GuildFacilityService.ALCHEMY_PILLS.get(pill_quality, [])
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
                session.add(production)
                generated_count += 1
        
        return generated_count

    @staticmethod
    async def get_warehouse_capacity(session: AsyncSession, guild_id: int) -> int:
        """获取公会仓库容量"""
        stmt = select(GuildBuilding).where(
            and_(GuildBuilding.guild_id == guild_id, GuildBuilding.building_type == BuildingType.GUILD_WAREHOUSE)
        )
        warehouse_building = (await session.execute(stmt)).scalars().first()

        if not warehouse_building:
            return 0

        config = GuildBuildingService.BUILDING_CONFIGS[BuildingType.GUILD_WAREHOUSE]
        effects = config["effects"][warehouse_building.level]
        return effects["storage_slots"]

    @staticmethod
    async def get_warehouse_items(session: AsyncSession, guild_id: int) -> List[Dict]:
        """获取公会仓库物品列表，合并显示相同物品的多个堆叠"""
        stmt = select(GuildWarehouseItem).where(GuildWarehouseItem.guild_id == guild_id).order_by(GuildWarehouseItem.deposited_at.desc())
        items = (await session.execute(stmt)).scalars().all()

        # 按物品ID分组合并
        item_groups = {}
        for item in items:
            item_config = config.items_config["by_id"].get(item.item_id)
            if item_config:
                if item.item_id not in item_groups:
                    # 找到最新的存入者作为代表（因为items已按deposited_at降序排列，第一个就是最新的）
                    depositor = await session.get(Player, item.deposited_by)
                    item_groups[item.item_id] = {
                        "item_id": item.item_id,
                        "item_name": item_config.name,
                        "quantity": 0,
                        "deposited_by": depositor.nickname if depositor else "未知",
                        "deposited_at": item.deposited_at,  # 使用最新的存入时间
                        "stack_ids": []  # 记录所有堆叠的ID，用于取出时的处理
                    }

                item_groups[item.item_id]["quantity"] += item.quantity
                item_groups[item.item_id]["stack_ids"].append(item.id)

        # 转换为列表并按存入时间排序
        result = list(item_groups.values())
        result.sort(key=lambda x: x["deposited_at"], reverse=True)

        # 为每个合并的物品组分配一个虚拟ID（用于取出时的索引）
        for idx, item_group in enumerate(result):
            item_group["id"] = f"group_{idx}"

        return result

    @staticmethod
    async def deposit_to_warehouse(session: AsyncSession, player_id: str, guild_id: int, item_id: str, quantity: int) -> Tuple[bool, str]:
        """存入物品到公会仓库"""
        from math import ceil
        from ..models.inventory import STACK_SIZE

        # 检查是否有仓库
        capacity = await GuildFacilityService.get_warehouse_capacity(session, guild_id)
        if capacity == 0:
            return False, "公会尚未建造仓库"

        # 检查物品是否为诡异道具（材料类型）
        item_config = config.items_config["by_id"].get(item_id)
        if not item_config or item_config.type.value != "MATERIAL":
            return False, "只能存入诡异道具（材料类型）"

        # 检查玩家是否有该物品（需要统计所有堆叠的总数量）
        stmt = select(ItemInstance).where(
            and_(ItemInstance.player_id == player_id, ItemInstance.item_id == item_id)
        )
        player_items = (await session.execute(stmt)).scalars().all()
        total_quantity = sum(item.quantity for item in player_items)

        if total_quantity < quantity:
            return False, f"你没有足够的该物品（拥有{total_quantity}，需要{quantity}）"

        # 获取仓库中该物品的现有堆叠
        stmt = select(GuildWarehouseItem).where(
            and_(GuildWarehouseItem.guild_id == guild_id, GuildWarehouseItem.item_id == item_id)
        ).order_by(GuildWarehouseItem.id)
        existing_stacks = (await session.execute(stmt)).scalars().all()

        # 计算现有数量和格子数
        existing_quantity = sum(stack.quantity for stack in existing_stacks)
        new_total_quantity = existing_quantity + quantity

        # 计算需要的格子数（按照玩家背包的堆叠规则）
        new_slots_needed = ceil(new_total_quantity / STACK_SIZE)
        current_slots_for_this_item = len(existing_stacks)
        additional_slots_needed = new_slots_needed - current_slots_for_this_item

        # 检查仓库总格子数
        stmt = select(func.count(GuildWarehouseItem.id)).where(GuildWarehouseItem.guild_id == guild_id)
        current_total_slots = (await session.execute(stmt)).scalar_one() or 0

        if current_total_slots + additional_slots_needed > capacity:
            return False, f"仓库格子不足，当前{current_total_slots}/{capacity}格，存入{quantity}个需要额外{additional_slots_needed}格"

        # 扣除玩家物品（使用统一的消耗方法处理多个堆叠）
        try:
            success_consume = await ItemInstance.consume_item(session, player_id, item_id, quantity)
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
                session.add(stack)

        # 剩余数量创建新堆叠
        while remaining_quantity > 0:
            stack_quantity = min(STACK_SIZE, remaining_quantity)
            warehouse_item = GuildWarehouseItem(
                guild_id=guild_id,
                item_id=item_id,
                quantity=stack_quantity,
                deposited_by=player_id
            )
            session.add(warehouse_item)
            remaining_quantity -= stack_quantity

        return True, f"成功存入{item_config.name}×{quantity}"

    @staticmethod
    async def withdraw_from_warehouse(session: AsyncSession, player_id: str, guild_id: int, item_index: int, quantity: int) -> Tuple[bool, str]:
        """从公会仓库取出物品"""
        # 获取仓库物品列表（合并显示的）
        items = await GuildFacilityService.get_warehouse_items(session, guild_id)

        if item_index < 1 or item_index > len(items):
            return False, "无效的物品序号"

        selected_item = items[item_index - 1]

        if selected_item["quantity"] < quantity:
            return False, f"仓库中该物品数量不足（仅有{selected_item['quantity']}个）"

        # 检查玩家背包容量
        try:
            await ItemInstance.add_item(session, player_id, selected_item["item_id"], quantity)
        except ValueError as e:
            return False, f"背包空间不足：{str(e)}"

        # 从实际的堆叠中扣除物品（按照存入时间降序，与显示顺序保持一致）
        stmt = select(GuildWarehouseItem).where(
            and_(GuildWarehouseItem.guild_id == guild_id, GuildWarehouseItem.item_id == selected_item["item_id"])
        ).order_by(GuildWarehouseItem.deposited_at.desc())  # 按存入时间降序，与显示顺序一致

        warehouse_stacks = (await session.execute(stmt)).scalars().all()

        remaining_to_withdraw = quantity
        for stack in warehouse_stacks:
            if remaining_to_withdraw <= 0:
                break

            withdraw_from_stack = min(stack.quantity, remaining_to_withdraw)
            stack.quantity -= withdraw_from_stack
            remaining_to_withdraw -= withdraw_from_stack

            if stack.quantity <= 0:
                await session.delete(stack)
            else:
                session.add(stack)

        item_config = config.items_config["by_id"].get(selected_item["item_id"])
        item_name = item_config.name if item_config else selected_item["item_id"]

        return True, f"成功取出{item_name}×{quantity}"
