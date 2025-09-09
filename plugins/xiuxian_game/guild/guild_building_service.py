"""
公会建筑系统服务
"""
from typing import Dict, List, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from ..models.guild import Guild, GuildBuilding, BuildingType
from ..models.inventory import ItemInstance
from .guild_permission import GuildPermission


class GuildBuildingService:
    """公会建筑服务类"""
    
    # 建筑配置
    BUILDING_CONFIGS = {
        BuildingType.EXPERIENCE_SHRINE: {
            "name": "经验神龛",
            "description": "提升公会经验转换倍率",
            "max_level": 10,
            "base_cost": {"gold": 50000, "materials": {"墓土": 200, "阴煞精华": 50, "血肉结晶": 20}},
            "effects": {
                1: {"exp_multiplier": 1.1},
                2: {"exp_multiplier": 1.2},
                3: {"exp_multiplier": 1.3},
                4: {"exp_multiplier": 1.4},
                5: {"exp_multiplier": 1.5},
                6: {"exp_multiplier": 1.6},
                7: {"exp_multiplier": 1.7},
                8: {"exp_multiplier": 1.8},
                9: {"exp_multiplier": 1.9},
                10: {"exp_multiplier": 2.0}
            }
        },
        BuildingType.TREASURY_VAULT: {
            "name": "资金金库",
            "description": "增加公会资金上限",
            "max_level": 5,
            "base_cost": {"gold": 80000, "materials": {"墓土": 150, "诡异石": 30, "魂魄结晶": 15}},
            "effects": {
                1: {"treasury_limit": 500000},
                2: {"treasury_limit": 1000000},
                3: {"treasury_limit": 2000000},
                4: {"treasury_limit": 5000000},
                5: {"treasury_limit": 10000000},
            }
        },
        BuildingType.TRAINING_GROUND: {
            "name": "训练场",
            "description": "提升成员修为加成",
            "max_level": 10,
            "base_cost": {"gold": 60000, "materials": {"墓土": 180, "梦魇丝线": 40, "诡异石": 25}},
            "effects": {
                1: {"cultivation_bonus": 0.05},
                2: {"cultivation_bonus": 0.08},
                3: {"cultivation_bonus": 0.12},
                4: {"cultivation_bonus": 0.15},
                5: {"cultivation_bonus": 0.20},
                6: {"cultivation_bonus": 0.25},
                7: {"cultivation_bonus": 0.30},
                8: {"cultivation_bonus": 0.35},
                9: {"cultivation_bonus": 0.40},
                10: {"cultivation_bonus": 0.50}
            }
        },
        BuildingType.TELEPORT_ARRAY: {
            "name": "传送阵",
            "description": "允许公会成员传送到基地",
            "max_level": 5,
            "base_cost": {"gold": 100000, "materials": {"墓土": 300, "诡异石": 80, "灵石": 50}},
            "effects": {
                1: {"teleport_range": 50, "daily_uses": 1},
                2: {"teleport_range": 100, "daily_uses": 1},
                3: {"teleport_range": 200, "daily_uses": 2},
                4: {"teleport_range": 300, "daily_uses": 2},
                5: {"teleport_range": 500, "daily_uses": 2}
            }
        },
        BuildingType.ALCHEMY_ROOM: {
            "name": "丹房",
            "description": "每日随机产出丹药",
            "max_level": 5,
            "base_cost": {"gold": 80000, "materials": {"墓土": 200, "阴煞精华": 60, "腐坏的内丹": 40}},
            "effects": {
                1: {"daily_production": 5, "pill_quality": "basic"},
                2: {"daily_production": 10, "pill_quality": "basic"},
                3: {"daily_production": 8, "pill_quality": "intermediate"},
                4: {"daily_production": 12, "pill_quality": "intermediate"},
                5: {"daily_production": 10, "pill_quality": "advanced"}
            }
        },
        BuildingType.GUILD_WAREHOUSE: {
            "name": "公会仓库",
            "description": "提供公共空间存放物品",
            "max_level": 10,
            "base_cost": {"gold": 70000, "materials": {"墓土": 250, "灵石": 80, "诅咒丝线": 30, "铁锈": 50}},
            "effects": {
                1: {"storage_slots": 30},
                2: {"storage_slots": 50},
                3: {"storage_slots": 100},
                4: {"storage_slots": 200},
                5: {"storage_slots": 300},
                6: {"storage_slots": 400},
                7: {"storage_slots": 500},
                8: {"storage_slots": 600},
                9: {"storage_slots": 700},
                10: {"storage_slots": 800}
            }
        }
        # 注意：灵塔和防御城墙暂时下架，功能还不稳定
        # BuildingType.SPIRIT_TOWER: {
        #     "name": "灵塔",
        #     "description": "提升公会整体属性",
        #     "max_level": 3,
        #     "base_cost": {"gold": 120000, "materials": {"墓土": 250, "诡异石": 50, "灵石": 20, "恶魔之心": 5}},
        #     "effects": {
        #         1: {"all_attributes": 0.03},
        #         2: {"all_attributes": 0.05},
        #         3: {"all_attributes": 0.08}
        #     }
        # },
        # BuildingType.DEFENSE_WALL: {
        #     "name": "防御城墙",
        #     "description": "提升公会防御力",
        #     "max_level": 3,
        #     "base_cost": {"gold": 100000, "materials": {"墓土": 300, "诡异石": 60, "诅咒镜片": 25, "虚无精华": 8}},
        #     "effects": {
        #         1: {"defense_bonus": 0.1},
        #         2: {"defense_bonus": 0.15},
        #         3: {"defense_bonus": 0.25}
        #     }
        # }
    }
    
    @staticmethod
    async def can_build(session: AsyncSession, guild_id: int, building_type: BuildingType) -> Tuple[bool, str]:
        """检查是否可以建造指定建筑"""
        # 检查是否已存在该类型建筑
        stmt = select(GuildBuilding).where(
            and_(GuildBuilding.guild_id == guild_id, GuildBuilding.building_type == building_type)
        )
        existing = (await session.execute(stmt)).scalars().first()
        
        if existing:
            config = GuildBuildingService.BUILDING_CONFIGS[building_type]
            if existing.level >= config["max_level"]:
                return False, f"{config['name']}已达到最高等级"
            else:
                return True, f"可以升级{config['name']}"
        
        return True, "可以建造"
    
    @staticmethod
    async def get_build_cost(session: AsyncSession, guild_id: int, building_type: BuildingType) -> Dict:
        """获取建造/升级成本"""
        config = GuildBuildingService.BUILDING_CONFIGS[building_type]
        
        # 检查当前等级
        stmt = select(GuildBuilding).where(
            and_(GuildBuilding.guild_id == guild_id, GuildBuilding.building_type == building_type)
        )
        existing = (await session.execute(stmt)).scalars().first()
        
        current_level = existing.level if existing else 0
        target_level = current_level + 1
        
        if target_level > config["max_level"]:
            return {}
        
        # 计算成本（等级越高成本越高）
        base_cost = config["base_cost"]
        multiplier = target_level
        
        cost = {
            "gold": base_cost["gold"] * multiplier,
            "materials": {}
        }
        
        for material, amount in base_cost["materials"].items():
            cost["materials"][material] = amount * multiplier
        
        return cost
    
    @staticmethod
    async def build_or_upgrade(session: AsyncSession, guild_id: int, building_type: BuildingType, player_id: str) -> Tuple[bool, str]:
        """建造或升级建筑"""
        # 权限检查
        can_build, reason = await GuildPermission.can_build(session, player_id, guild_id)
        if not can_build:
            return False, reason
        
        # 检查是否可以建造
        can_build_check, build_reason = await GuildBuildingService.can_build(session, guild_id, building_type)
        if not can_build_check:
            return False, build_reason
        
        # 获取成本
        cost = await GuildBuildingService.get_build_cost(session, guild_id, building_type)
        if not cost:
            return False, "无法计算建造成本"
        
        # 检查公会资金
        guild = await session.get(Guild, guild_id)
        if guild.treasury < cost["gold"]:
            return False, f"公会资金不足，需要{cost['gold']}金币"
        
        # 检查材料（从玩家背包中扣除）
        from ..models.inventory import ItemInstance
        from ..config import config

        for material_name, required_qty in cost["materials"].items():
            # 通过名称查找物品配置
            material_config = config.items_config["by_name"].get(material_name)
            if not material_config:
                return False, f"材料配置错误：{material_name}"

            # 检查玩家背包中的材料数量
            stmt = select(ItemInstance).where(
                and_(ItemInstance.player_id == player_id, ItemInstance.item_id == material_config.item_id)
            )
            material_instances = (await session.execute(stmt)).scalars().all()
            total_qty = sum(instance.quantity for instance in material_instances)

            if total_qty < required_qty:
                return False, f"材料不足：{material_name} (需要{required_qty}，拥有{total_qty})"
        
        # 扣除资金
        guild.treasury -= cost["gold"]
        session.add(guild)

        # 扣除材料
        for material_name, required_qty in cost["materials"].items():
            material_config = config.items_config["by_name"].get(material_name)
            try:
                success_consume = await ItemInstance.consume_item(session, player_id, material_config.item_id, required_qty)
                if not success_consume:
                    return False, f"扣除材料失败：{material_name}"
            except ValueError as e:
                return False, f"扣除材料失败：{str(e)}"
        
        # 建造或升级建筑
        stmt = select(GuildBuilding).where(
            and_(GuildBuilding.guild_id == guild_id, GuildBuilding.building_type == building_type)
        )
        existing = (await session.execute(stmt)).scalars().first()

        building_config = GuildBuildingService.BUILDING_CONFIGS[building_type]

        if existing:
            # 升级
            existing.level += 1
            session.add(existing)
            return True, f"{building_config['name']}升级至{existing.level}级成功！"
        else:
            # 新建
            new_building = GuildBuilding(
                guild_id=guild_id,
                building_type=building_type,
                level=1
            )
            session.add(new_building)
            return True, f"{building_config['name']}建造成功！"
    
    @staticmethod
    async def get_guild_buildings(session: AsyncSession, guild_id: int) -> List[Dict]:
        """获取公会所有建筑"""
        stmt = select(GuildBuilding).where(GuildBuilding.guild_id == guild_id)
        buildings = (await session.execute(stmt)).scalars().all()
        
        result = []
        for building in buildings:
            config = GuildBuildingService.BUILDING_CONFIGS[building.building_type]
            effects = config["effects"].get(building.level, {})
            
            result.append({
                "type": building.building_type,
                "name": config["name"],
                "level": building.level,
                "max_level": config["max_level"],
                "description": config["description"],
                "effects": effects,
                "built_at": building.built_at
            })
        
        return result
    
    @staticmethod
    async def get_guild_bonuses(session: AsyncSession, guild_id: int) -> Dict:
        """获取公会建筑提供的所有加成"""
        buildings = await GuildBuildingService.get_guild_buildings(session, guild_id)
        
        bonuses = {
            "exp_multiplier": 1.0,
            "treasury_limit": 100000,  # 基础资金上限
            "cultivation_bonus": 0.0,
            "all_attributes": 0.0,
            "defense_bonus": 0.0,
            "teleport_range": 0,
            "daily_teleport_uses": 0,
            "daily_alchemy_production": 0,
            "warehouse_capacity": 0
        }
        
        for building in buildings:
            effects = building["effects"]
            for effect_type, value in effects.items():
                if effect_type in bonuses:
                    if effect_type in ["exp_multiplier", "treasury_limit", "teleport_range", "warehouse_capacity"]:
                        # 这些效果取最大值
                        bonuses[effect_type] = max(bonuses[effect_type], value)
                    elif effect_type in ["daily_uses", "daily_production"]:
                        # 特殊处理：传送次数和丹药产出
                        if effect_type == "daily_uses":
                            bonuses["daily_teleport_uses"] = max(bonuses["daily_teleport_uses"], value)
                        elif effect_type == "daily_production":
                            bonuses["daily_alchemy_production"] = max(bonuses["daily_alchemy_production"], value)
                    elif effect_type == "storage_slots":
                        bonuses["warehouse_capacity"] = max(bonuses["warehouse_capacity"], value)
                    else:
                        # 其他效果累加
                        bonuses[effect_type] += value
        
        return bonuses

    @staticmethod
    def format_building_effects(effects: Dict) -> str:
        """格式化建筑效果为中文显示"""
        # 效果名称中文映射
        effect_name_map = {
            "exp_multiplier": "经验倍率",
            "treasury_limit": "资金上限",
            "cultivation_bonus": "修为加成",
            "all_attributes": "全属性加成",
            "defense_bonus": "防御加成",
            "daily_production": "日产",
            "pill_quality": "丹药品质",
            "teleport_range": "传送范围",
            "daily_uses": "每日次数",
            "storage_slots": "仓库格子"
        }

        # 丹药品质中文映射
        pill_quality_map = {
            "basic": "初级",
            "intermediate": "中级",
            "advanced": "高级"
        }

        effects_list = []
        for k, v in effects.items():
            chinese_name = effect_name_map.get(k, k)
            if k == "exp_multiplier":
                effects_list.append(f"{chinese_name} {v:.1f}x")
            elif k == "treasury_limit":
                effects_list.append(f"{chinese_name} {v:,}")
            elif k in ["cultivation_bonus", "all_attributes", "defense_bonus"]:
                effects_list.append(f"{chinese_name} +{v*100:.1f}%")
            elif k == "teleport_range":
                effects_list.append(f"{chinese_name} {v}格")
            elif k == "daily_uses":
                effects_list.append(f"{chinese_name} {v}次")
            elif k == "storage_slots":
                effects_list.append(f"{chinese_name} {v}格")
            elif k == "pill_quality":
                chinese_quality = pill_quality_map.get(v, v)
                effects_list.append(f"{chinese_name} {chinese_quality}")
            elif k == "daily_production":
                effects_list.append(f"{chinese_name} {v}个")
            else:
                effects_list.append(f"{chinese_name} {v}")

        return ", ".join(effects_list)
