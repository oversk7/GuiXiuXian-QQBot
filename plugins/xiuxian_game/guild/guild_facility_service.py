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
        
        # 计算距离
        distance = math.sqrt((player.x - guild.base_x) ** 2 + (player.y - guild.base_y) ** 2)
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
        
        # 记录传送前位置
        from_x, from_y = player.x, player.y
        
        # 传送到公会基地
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
        """获取公会仓库物品列表"""
        stmt = select(GuildWarehouseItem).where(GuildWarehouseItem.guild_id == guild_id).order_by(GuildWarehouseItem.deposited_at.desc())
        items = (await session.execute(stmt)).scalars().all()

        result = []
        for item in items:
            item_config = config.items_config["by_id"].get(item.item_id)
            if item_config:
                depositor = await session.get(Player, item.deposited_by)
                result.append({
                    "id": item.id,
                    "item_id": item.item_id,
                    "item_name": item_config.name,
                    "quantity": item.quantity,
                    "deposited_by": depositor.nickname if depositor else "未知",
                    "deposited_at": item.deposited_at
                })

        return result

    @staticmethod
    async def deposit_to_warehouse(session: AsyncSession, player_id: str, guild_id: int, item_id: str, quantity: int) -> Tuple[bool, str]:
        """存入物品到公会仓库"""
        # 检查是否有仓库
        capacity = await GuildFacilityService.get_warehouse_capacity(session, guild_id)
        if capacity == 0:
            return False, "公会尚未建造仓库"

        # 检查仓库格子数（不同物品占用不同格子）
        stmt = select(func.count(GuildWarehouseItem.id)).where(GuildWarehouseItem.guild_id == guild_id)
        current_slots_used = (await session.execute(stmt)).scalar_one() or 0

        # 检查是否已有该物品（如果有，不占用新格子）
        stmt = select(GuildWarehouseItem).where(
            and_(GuildWarehouseItem.guild_id == guild_id, GuildWarehouseItem.item_id == item_id)
        )
        existing_item = (await session.execute(stmt)).scalars().first()

        # 如果是新物品且仓库已满，则拒绝
        if not existing_item and current_slots_used >= capacity:
            return False, f"仓库格子已满，当前{current_slots_used}/{capacity}格，无法存入新物品"

        # 检查玩家是否有该物品
        stmt = select(ItemInstance).where(
            and_(ItemInstance.player_id == player_id, ItemInstance.item_id == item_id)
        )
        player_item = (await session.execute(stmt)).scalars().first()

        if not player_item or player_item.quantity < quantity:
            return False, "你没有足够的该物品"

        # 检查物品是否为诡异道具（材料类型）
        item_config = config.items_config["by_id"].get(item_id)
        if not item_config or item_config.type.value != "MATERIAL":
            return False, "只能存入诡异道具（材料类型）"

        # 扣除玩家物品
        player_item.quantity -= quantity
        if player_item.quantity <= 0:
            await session.delete(player_item)
        else:
            session.add(player_item)

        # 检查仓库是否已有该物品
        stmt = select(GuildWarehouseItem).where(
            and_(GuildWarehouseItem.guild_id == guild_id, GuildWarehouseItem.item_id == item_id)
        )
        existing_item = (await session.execute(stmt)).scalars().first()

        if existing_item:
            # 增加数量到现有格子
            existing_item.quantity += quantity
            session.add(existing_item)
        else:
            # 新增物品（占用新格子）
            warehouse_item = GuildWarehouseItem(
                guild_id=guild_id,
                item_id=item_id,
                quantity=quantity,
                deposited_by=player_id
            )
            session.add(warehouse_item)

        return True, f"成功存入{item_config.name}×{quantity}"

    @staticmethod
    async def withdraw_from_warehouse(session: AsyncSession, player_id: str, guild_id: int, warehouse_item_id: int, quantity: int) -> Tuple[bool, str]:
        """从公会仓库取出物品"""
        # 检查仓库物品
        warehouse_item = await session.get(GuildWarehouseItem, warehouse_item_id)
        if not warehouse_item or warehouse_item.guild_id != guild_id:
            return False, "仓库物品不存在"

        if warehouse_item.quantity < quantity:
            return False, f"仓库中该物品数量不足（仅有{warehouse_item.quantity}个）"

        # 检查玩家背包容量
        player = await session.get(Player, player_id)
        try:
            await ItemInstance.add_item(session, player_id, warehouse_item.item_id, quantity)
        except ValueError as e:
            return False, f"背包空间不足：{str(e)}"

        # 扣除仓库物品
        warehouse_item.quantity -= quantity
        if warehouse_item.quantity <= 0:
            await session.delete(warehouse_item)
        else:
            session.add(warehouse_item)

        item_config = config.items_config["by_id"].get(warehouse_item.item_id)
        item_name = item_config.name if item_config else warehouse_item.item_id

        return True, f"成功取出{item_name}×{quantity}"
