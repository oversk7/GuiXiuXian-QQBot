"""
公会建筑系统服务 - DI架构版本

将GuildBuildingService改造为依赖注入架构，通过Repository抽象数据访问
"""

from typing import Dict, List, Tuple
from ..models.guild import Guild, GuildBuilding, BuildingType
from ..models.inventory import ItemInstance
from ..infrastructure.repositories.guild_repository import GuildRepository
from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
from ..infrastructure.repositories.item_repository import ItemRepository
from .guild_permission import GuildPermission


class GuildBuildingService:
    """公会建筑服务类 - DI架构版本"""

    # 建筑配置（类常量，保持向后兼容）
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
            "max_level": 8,
            "base_cost": {"gold": 80000, "materials": {"墓土": 200, "阴煞精华": 60, "腐坏的内丹": 40}},
            "effects": {
                1: {"daily_production": 4, "pill_quality": "basic"},
                2: {"daily_production": 7, "pill_quality": "basic"},
                3: {"daily_production": 9, "pill_quality": "intermediate"},
                4: {"daily_production": 12, "pill_quality": "intermediate"},
                5: {"daily_production": 14, "pill_quality": "advanced"},
                6: {"daily_production": 16, "pill_quality": "advanced"},
                7: {"daily_production": 18, "pill_quality": "master"},
                8: {"daily_production": 20, "pill_quality": "legendary"}
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
    }

    def __init__(
        self,
        guild_repo: GuildRepository,
        building_repo: GuildBuildingRepository,
        item_repo: ItemRepository,
    ):
        """
        初始化公会建筑服务

        Args:
            guild_repo: 公会仓储
            building_repo: 公会建筑仓储
            item_repo: 物品仓储
        """
        self._guild_repo = guild_repo
        self._building_repo = building_repo
        self._item_repo = item_repo

    @staticmethod
    def get_effects_for_level(building_type: BuildingType, level: int) -> Dict:
        """获取指定等级的建筑效果，超出预定义等级时自动外推"""
        config = GuildBuildingService.BUILDING_CONFIGS[building_type]
        effects_dict = config["effects"]

        if level in effects_dict:
            return effects_dict[level]

        # 超出预定义等级，基于公式外推
        max_defined = max(effects_dict.keys())
        last_effects = effects_dict[max_defined]
        extra = level - max_defined

        extrapolated = {}
        for key, value in last_effects.items():
            if key == "exp_multiplier":
                extrapolated[key] = round(1.0 + level * 0.1, 1)
            elif key == "treasury_limit":
                extrapolated[key] = int(value * (2 ** extra))
            elif key == "cultivation_bonus":
                extrapolated[key] = round(value + extra * 0.05, 2)
            elif key == "teleport_range":
                extrapolated[key] = value + extra * 100
            elif key == "daily_uses":
                extrapolated[key] = value + max(0, extra // 3)
            elif key == "daily_production":
                extrapolated[key] = value + extra * 2
            elif key == "pill_quality":
                extrapolated[key] = "legendary"
            elif key == "storage_slots":
                extrapolated[key] = value + extra * 100
            else:
                extrapolated[key] = value

        return extrapolated

    def _get_building_max_level(self, guild_level: int, building_type: BuildingType) -> int:
        """建筑等级上限：公会10级以下取配置上限，10级及以上突破至公会等级"""
        config_max = self.BUILDING_CONFIGS[building_type].get("max_level", 10)
        if guild_level < 10:
            return config_max
        return guild_level

    async def can_build(
        self, guild_id: int, building_type: BuildingType
    ) -> Tuple[bool, str]:
        """
        检查是否可以建造指定建筑
        """
        guild = await self._guild_repo.get_by_id(guild_id)
        guild_level = guild.level if guild else 1
        max_level = self._get_building_max_level(guild_level, building_type)

        # 检查是否已存在该类型建筑
        existing = await self._building_repo.get_by_guild_and_type(
            guild_id, building_type
        )

        if existing:
            config = self.BUILDING_CONFIGS[building_type]
            if existing.level >= max_level:
                return False, f"{config['name']}已达到最高等级（{max_level}级）"
            else:
                return True, f"可以升级{config['name']}"

        return True, "可以建造"

    async def get_build_cost(
        self, guild_id: int, building_type: BuildingType
    ) -> Dict:
        """
        获取建造/升级成本

        Args:
            guild_id: 公会ID
            building_type: 建筑类型

        Returns:
            成本字典 {"gold": int, "materials": {material_name: qty}}

        对应原代码:
            guild_building_service.py Line 156-185
        """
        config = self.BUILDING_CONFIGS[building_type]

        # 检查当前等级
        existing = await self._building_repo.get_by_guild_and_type(
            guild_id, building_type
        )

        current_level = existing.level if existing else 0
        target_level = current_level + 1

        guild = await self._guild_repo.get_by_id(guild_id)
        guild_level = guild.level if guild else 1
        max_level = self._get_building_max_level(guild_level, building_type)
        if target_level > max_level:
            return {}

        # 计算成本（等级越高成本越高）
        base_cost = config["base_cost"]

        cost = {
            "gold": base_cost["gold"] * target_level,
            "materials": {}
        }

        for material, amount in base_cost["materials"].items():
            cost["materials"][material] = amount * target_level

        # 10级以上：金币二次增长 + 额外稀有材料
        if target_level > 10:
            cost["gold"] = base_cost["gold"] * target_level * (target_level - 9)

            extra = target_level - 10
            # 蓝色材料
            cost["materials"]["魂魄结晶"] = cost["materials"].get("魂魄结晶", 0) + 8 * extra
            cost["materials"]["诅咒镜片"] = cost["materials"].get("诅咒镜片", 0) + 5 * extra
            cost["materials"]["幽魂丝线"] = cost["materials"].get("幽魂丝线", 0) + 5 * extra
            # 紫色材料
            cost["materials"]["恶魔之心"] = cost["materials"].get("恶魔之心", 0) + 5 * extra
            cost["materials"]["虚无精华"] = cost["materials"].get("虚无精华", 0) + 3 * extra
            cost["materials"]["灵石"] = cost["materials"].get("灵石", 0) + 10 * extra

            # 16级以上额外需要橙色材料
            if target_level > 15:
                orange_extra = target_level - 15
                cost["materials"]["神明之泪"] = cost["materials"].get("神明之泪", 0) + 2 * orange_extra
                cost["materials"]["世界碎片"] = cost["materials"].get("世界碎片", 0) + 1 * orange_extra
                cost["materials"]["时光尘埃"] = cost["materials"].get("时光尘埃", 0) + 1 * orange_extra

        return cost

    async def build_or_upgrade(
        self, guild_id: int, building_type: BuildingType, player_id: str
    ) -> Tuple[bool, str]:
        """
        建造或升级建筑

        Args:
            guild_id: 公会ID
            building_type: 建筑类型
            player_id: 操作玩家ID

        Returns:
            (是否成功, 消息)

        对应原代码:
            guild_building_service.py Line 187-265

        Note:
            ✅ 原代码无P0问题：未发现内部commit
            新版本移除session参数，通过Repository操作数据
        """
        # 权限检查（暂时继续使用GuildPermission静态方法）
        can_build, reason = await GuildPermission.can_build(
            self._guild_repo._session, player_id, guild_id
        )
        if not can_build:
            return False, reason

        # 检查是否可以建造
        can_build_check, build_reason = await self.can_build(
            guild_id, building_type
        )
        if not can_build_check:
            return False, build_reason

        # 获取成本
        cost = await self.get_build_cost(guild_id, building_type)
        if not cost:
            return False, "无法计算建造成本"

        # 检查公会资金
        guild = await self._guild_repo.get_by_id(guild_id)
        if not guild:
            return False, "公会不存在"

        if guild.treasury < cost["gold"]:
            return False, f"公会资金不足，需要{cost['gold']}金币"

        # 检查材料（从玩家背包中扣除）
        from ..config import config

        for material_name, required_qty in cost["materials"].items():
            # 通过名称查找物品配置
            material_config = config.items_config["by_name"].get(material_name)
            if not material_config:
                return False, f"材料配置错误：{material_name}"

            # 检查玩家背包中的材料数量
            material_instances = await self._item_repo.get_by_player_and_item_id(
                player_id, material_config.item_id
            )
            total_qty = sum(instance.quantity for instance in material_instances)

            if total_qty < required_qty:
                return False, f"材料不足：{material_name} (需要{required_qty}，拥有{total_qty})"

        # 扣除资金
        guild.treasury -= cost["gold"]
        await self._guild_repo.update(guild)

        # 扣除材料
        for material_name, required_qty in cost["materials"].items():
            material_config = config.items_config["by_name"].get(material_name)
            try:
                # 使用ItemRepository的consume_item方法
                success_consume = await self._item_repo.consume_item(
                    player_id, material_config.item_id, required_qty
                )
                if not success_consume:
                    return False, f"扣除材料失败：{material_name}"
            except ValueError as e:
                return False, f"扣除材料失败：{str(e)}"

        # 建造或升级建筑
        existing = await self._building_repo.get_by_guild_and_type(
            guild_id, building_type
        )

        building_config = self.BUILDING_CONFIGS[building_type]

        if existing:
            # 升级
            existing.level += 1
            await self._building_repo.update(existing)
            return True, f"{building_config['name']}升级至{existing.level}级成功！"
        else:
            # 新建
            new_building = GuildBuilding(
                guild_id=guild_id,
                building_type=building_type,
                level=1
            )
            await self._building_repo.add(new_building)
            return True, f"{building_config['name']}建造成功！"

    async def get_guild_buildings(self, guild_id: int) -> List[Dict]:
        """
        获取公会所有建筑

        Args:
            guild_id: 公会ID

        Returns:
            建筑信息列表

        对应原代码:
            guild_building_service.py Line 267-288
        """
        buildings = await self._building_repo.get_all_by_guild_id(guild_id)

        guild = await self._guild_repo.get_by_id(guild_id)
        guild_level = guild.level if guild else 1

        result = []
        for building in buildings:
            config = self.BUILDING_CONFIGS[building.building_type]
            effects = self.get_effects_for_level(building.building_type, building.level)
            max_level = self._get_building_max_level(guild_level, building.building_type)

            result.append({
                "type": building.building_type,
                "name": config["name"],
                "level": building.level,
                "max_level": max_level,
                "description": config["description"],
                "effects": effects,
                "built_at": building.built_at
            })

        return result

    async def get_guild_bonuses(self, guild_id: int) -> Dict:
        """
        获取公会建筑提供的所有加成

        Args:
            guild_id: 公会ID

        Returns:
            加成字典

        对应原代码:
            guild_building_service.py Line 290-326
        """
        buildings = await self.get_guild_buildings(guild_id)

        bonuses = {
            "exp_multiplier": 1.0,
            "treasury_limit": 100000,  # 基础资金上限
            "cultivation_bonus": 0.0,
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
                        bonuses[effect_type] = max(bonuses[effect_type], value)
                    else:
                        bonuses[effect_type] += value
                elif effect_type == "daily_uses":
                    bonuses["daily_teleport_uses"] = max(bonuses["daily_teleport_uses"], value)
                elif effect_type == "daily_production":
                    bonuses["daily_alchemy_production"] = max(bonuses["daily_alchemy_production"], value)
                elif effect_type == "storage_slots":
                    bonuses["warehouse_capacity"] = max(bonuses["warehouse_capacity"], value)

        return bonuses

    @staticmethod
    def format_building_effects(effects: Dict) -> str:
        """
        格式化建筑效果为中文显示

        Args:
            effects: 效果字典

        Returns:
            格式化后的效果字符串

        对应原代码:
            guild_building_service.py Line 328-377

        Note:
            保留为静态方法，因为是纯函数，无需依赖注入
        """
        # 效果名称中文映射
        effect_name_map = {
            "exp_multiplier": "经验倍率",
            "treasury_limit": "资金上限",
            "cultivation_bonus": "修为加成",
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
            "advanced": "高级",
            "master": "顶级",
            "legendary": "传说"
        }

        effects_list = []
        for k, v in effects.items():
            chinese_name = effect_name_map.get(k, k)
            if k == "exp_multiplier":
                effects_list.append(f"{chinese_name} {v:.1f}x")
            elif k == "treasury_limit":
                effects_list.append(f"{chinese_name} {v:,}")
            elif k in ["cultivation_bonus"]:
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
