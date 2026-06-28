"""
公会建筑系统服务（DI架构）

通过Repository抽象数据访问；模块级入口 get_guild_bonuses
兼容旧的 session 直传调用风格（加成计算只有这一份实现）
"""

from typing import Dict, List, Tuple
from ..models.guild import Guild, GuildBuilding, BuildingType
from ..models.inventory import ItemInstance
from ..infrastructure.repositories.guild_repository import GuildRepository
from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.repositories.guild_warehouse_item_repository import GuildWarehouseItemRepository
from .guild_permission import GuildPermission


class GuildBuildingService:
    """公会建筑服务类 - DI架构版本"""

    GRID_SIZE = 3

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
        },
        BuildingType.SPIRIT_TOWER: {
            "name": "聚灵阵",
            "description": "强化相邻建筑的灵脉收益",
            "max_level": 8,
            "base_cost": {"gold": 90000, "materials": {"墓土": 220, "灵石": 80, "阴煞精华": 50}},
            "effects": {
                1: {"adjacency_power": 1},
                2: {"adjacency_power": 2},
                3: {"adjacency_power": 3},
                4: {"adjacency_power": 4},
                5: {"adjacency_power": 5},
                6: {"adjacency_power": 6},
                7: {"adjacency_power": 7},
                8: {"adjacency_power": 8}
            }
        },
        BuildingType.ARTIFACT_FORGE: {
            "name": "铸器坊",
            "description": "允许成员在公会基地锻造装备",
            "max_level": 8,
            "base_cost": {"gold": 100000, "materials": {"墓土": 260, "铁锈": 120, "诡异石": 50, "灵石": 40}},
            "effects": {
                1: {"forge_enabled": True, "forge_gold_discount": 0.02},
                2: {"forge_enabled": True, "forge_gold_discount": 0.04},
                3: {"forge_enabled": True, "forge_gold_discount": 0.06},
                4: {"forge_enabled": True, "forge_gold_discount": 0.08},
                5: {"forge_enabled": True, "forge_gold_discount": 0.10},
                6: {"forge_enabled": True, "forge_gold_discount": 0.12},
                7: {"forge_enabled": True, "forge_gold_discount": 0.14},
                8: {"forge_enabled": True, "forge_gold_discount": 0.16}
            }
        },
        BuildingType.REFINING_PAVILION: {
            "name": "淬灵台",
            "description": "在公会基地升阶装备时获得加成",
            "max_level": 8,
            "base_cost": {"gold": 120000, "materials": {"墓土": 240, "魂魄结晶": 40, "诡异石": 70, "灵石": 60}},
            "effects": {
                1: {"upgrade_success_bonus": 0.01, "upgrade_gold_discount": 0.01},
                2: {"upgrade_success_bonus": 0.02, "upgrade_gold_discount": 0.02},
                3: {"upgrade_success_bonus": 0.03, "upgrade_gold_discount": 0.03},
                4: {"upgrade_success_bonus": 0.04, "upgrade_gold_discount": 0.04},
                5: {"upgrade_success_bonus": 0.05, "upgrade_gold_discount": 0.05},
                6: {"upgrade_success_bonus": 0.06, "upgrade_gold_discount": 0.06},
                7: {"upgrade_success_bonus": 0.07, "upgrade_gold_discount": 0.07},
                8: {"upgrade_success_bonus": 0.08, "upgrade_gold_discount": 0.08}
            }
        },
        BuildingType.DEFENSE_WALL: {
            "name": "防御城墙",
            "description": "旧版遗留防御建筑",
            "max_level": 3,
            "base_cost": {"gold": 100000, "materials": {"墓土": 300, "诡异石": 60, "诅咒镜片": 25, "虚无精华": 8}},
            "effects": {
                1: {"defense_bonus": 0.10},
                2: {"defense_bonus": 0.15},
                3: {"defense_bonus": 0.25}
            }
        }
    }

    BUILDING_NAME_TO_TYPE = {
        "经验神龛": BuildingType.EXPERIENCE_SHRINE,
        "资金金库": BuildingType.TREASURY_VAULT,
        "训练场": BuildingType.TRAINING_GROUND,
        "传送阵": BuildingType.TELEPORT_ARRAY,
        "丹房": BuildingType.ALCHEMY_ROOM,
        "公会仓库": BuildingType.GUILD_WAREHOUSE,
        "聚灵阵": BuildingType.SPIRIT_TOWER,
        "铸器坊": BuildingType.ARTIFACT_FORGE,
        "淬灵台": BuildingType.REFINING_PAVILION,
    }

    def __init__(
        self,
        guild_repo: GuildRepository,
        building_repo: GuildBuildingRepository,
        item_repo: ItemRepository,
        warehouse_item_repo: GuildWarehouseItemRepository | None = None,
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
        self._warehouse_item_repo = warehouse_item_repo

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
            elif key == "forge_enabled":
                extrapolated[key] = True
            elif key == "forge_gold_discount":
                extrapolated[key] = min(0.25, round(value + extra * 0.02, 2))
            elif key == "upgrade_success_bonus":
                extrapolated[key] = min(0.15, round(value + extra * 0.01, 2))
            elif key == "upgrade_gold_discount":
                extrapolated[key] = min(0.20, round(value + extra * 0.01, 2))
            elif key == "adjacency_power":
                extrapolated[key] = value + extra
            else:
                extrapolated[key] = value

        return extrapolated

    def _get_building_max_level(self, guild_level: int, building_type: BuildingType) -> int:
        """建筑等级上限：公会10级以下取配置上限，10级及以上突破至公会等级"""
        config_max = self.BUILDING_CONFIGS[building_type].get("max_level", 10)
        if guild_level < 10:
            return config_max
        return guild_level

    @classmethod
    def parse_building_name(cls, building_name: str) -> BuildingType | None:
        """通过中文建筑名获取建筑类型"""
        return cls.BUILDING_NAME_TO_TYPE.get(building_name)

    @classmethod
    def get_buildable_names(cls) -> list[str]:
        """获取当前开放建造的建筑名"""
        return list(cls.BUILDING_NAME_TO_TYPE.keys())

    @classmethod
    def is_valid_position(cls, plot_x: int, plot_y: int) -> bool:
        """检查基地布局坐标是否合法"""
        return 1 <= plot_x <= cls.GRID_SIZE and 1 <= plot_y <= cls.GRID_SIZE

    @staticmethod
    def _is_adjacent(a: GuildBuilding, b: GuildBuilding) -> bool:
        """四向相邻才触发邻接加成"""
        if a.plot_x is None or a.plot_y is None or b.plot_x is None or b.plot_y is None:
            return False
        return abs(a.plot_x - b.plot_x) + abs(a.plot_y - b.plot_y) == 1

    @classmethod
    def _get_spirit_tower_power(cls, spirit_tower: GuildBuilding) -> int:
        """聚灵阵等级决定相邻建筑的额外收益强度。"""
        effects = cls.get_effects_for_level(BuildingType.SPIRIT_TOWER, spirit_tower.level)
        return max(1, int(effects.get("adjacency_power", 1)))

    async def _find_empty_position(self, guild_id: int) -> tuple[int, int] | None:
        """按从左到右、从上到下自动寻找空格"""
        buildings = await self._building_repo.get_all_by_guild_id(guild_id)
        occupied = {
            (b.plot_x, b.plot_y)
            for b in buildings
            if b.plot_x is not None and b.plot_y is not None
        }
        for plot_y in range(1, self.GRID_SIZE + 1):
            for plot_x in range(1, self.GRID_SIZE + 1):
                if (plot_x, plot_y) not in occupied:
                    return plot_x, plot_y
        return None

    async def _backfill_missing_positions(self, guild_id: int) -> None:
        """为旧版本已建造但没有布局坐标的建筑补齐空位。"""
        buildings = await self._building_repo.get_all_by_guild_id(guild_id)
        occupied = {
            (b.plot_x, b.plot_y)
            for b in buildings
            if b.plot_x is not None and b.plot_y is not None
        }
        empty_positions = [
            (plot_x, plot_y)
            for plot_y in range(1, self.GRID_SIZE + 1)
            for plot_x in range(1, self.GRID_SIZE + 1)
            if (plot_x, plot_y) not in occupied
        ]

        changed = False
        for building in buildings:
            if building.plot_x is not None and building.plot_y is not None:
                continue
            if not empty_positions:
                break
            building.plot_x, building.plot_y = empty_positions.pop(0)
            await self._building_repo.update(building)
            changed = True

        if changed:
            await self._guild_repo._session.flush()

    async def _validate_new_position(
        self, guild_id: int, plot_x: int | None, plot_y: int | None
    ) -> tuple[bool, str, tuple[int, int] | None]:
        """校验新建筑或移动建筑的布局坐标"""
        if plot_x is None and plot_y is None:
            position = await self._find_empty_position(guild_id)
            if not position:
                return False, "公会基地布局已满，请先调整建筑位置", None
            return True, "可以放置", position

        if plot_x is None or plot_y is None:
            return False, "布局坐标需要同时提供 x y，例如：建造 铸器坊 2 1", None

        if not self.is_valid_position(plot_x, plot_y):
            return False, f"布局坐标范围为 1-{self.GRID_SIZE}，例如：建造 铸器坊 2 1", None

        existing = await self._building_repo.get_by_guild_and_position(guild_id, plot_x, plot_y)
        if existing:
            existing_name = self.BUILDING_CONFIGS[existing.building_type]["name"]
            return False, f"坐标({plot_x},{plot_y})已放置{existing_name}", None

        return True, "可以放置", (plot_x, plot_y)

    async def _get_warehouse_material_quantity(self, guild_id: int, item_id: str) -> int:
        """获取公会仓库中指定材料总量。"""
        if not self._warehouse_item_repo:
            return 0
        stacks = await self._warehouse_item_repo.get_by_guild_and_item_id(guild_id, item_id)
        return sum(stack.quantity for stack in stacks)

    async def _consume_warehouse_material(self, guild_id: int, item_id: str, quantity: int) -> int:
        """从公会仓库消耗材料，返回实际消耗数量。"""
        if not self._warehouse_item_repo or quantity <= 0:
            return 0

        consumed = 0
        stacks = await self._warehouse_item_repo.get_by_guild_and_item_id(guild_id, item_id)
        for stack in stacks:
            if consumed >= quantity:
                break
            take = min(stack.quantity, quantity - consumed)
            stack.quantity -= take
            consumed += take
            if stack.quantity <= 0:
                await self._warehouse_item_repo.delete(stack.id)
            else:
                await self._warehouse_item_repo.update(stack)
        return consumed

    async def validate_build_or_upgrade(
        self,
        guild_id: int,
        building_type: BuildingType,
        player_id: str,
        plot_x: int | None = None,
        plot_y: int | None = None,
    ) -> Tuple[bool, str, Dict]:
        """校验建造/升级条件，不修改数据。"""
        can_build, reason = await GuildPermission.can_build(
            self._guild_repo._session, player_id, guild_id
        )
        if not can_build:
            return False, reason, {}

        can_build_check, build_reason = await self.can_build(guild_id, building_type)
        if not can_build_check:
            return False, build_reason, {}

        existing = await self._building_repo.get_by_guild_and_type(guild_id, building_type)
        new_position: tuple[int, int] | None = None
        if not existing:
            valid_position, position_reason, new_position = await self._validate_new_position(
                guild_id, plot_x, plot_y
            )
            if not valid_position or not new_position:
                return False, position_reason, {}

        cost = await self.get_build_cost(guild_id, building_type)
        if not cost:
            return False, "无法计算建造成本", {}

        guild = await self._guild_repo.get_by_id(guild_id)
        if not guild:
            return False, "公会不存在", {}

        if guild.treasury < cost["gold"]:
            return False, f"公会资金不足，需要{cost['gold']}金币", {}

        if not self._item_repo:
            return False, "物品仓储未初始化，无法检查材料", {}

        from ..config import config

        material_sources = {}
        for material_name, required_qty in cost["materials"].items():
            material_config = config.items_config["by_name"].get(material_name)
            if not material_config:
                return False, f"材料配置错误：{material_name}", {}

            warehouse_qty = await self._get_warehouse_material_quantity(guild_id, material_config.item_id)
            material_instances = await self._item_repo.get_by_player_and_item_id(
                player_id, material_config.item_id
            )
            bag_qty = sum(instance.quantity for instance in material_instances)
            total_qty = warehouse_qty + bag_qty

            material_sources[material_name] = {
                "item_id": material_config.item_id,
                "required": required_qty,
                "warehouse": warehouse_qty,
                "bag": bag_qty,
                "total": total_qty,
            }
            if total_qty < required_qty:
                return (
                    False,
                    f"材料不足：{material_name} (需要{required_qty}，仓库{warehouse_qty}，背包{bag_qty})",
                    {},
                )

        return True, "可以建造", {
            "cost": cost,
            "new_position": new_position,
            "material_sources": material_sources,
        }

    @classmethod
    def get_adjacency_bonus_descriptions(cls, buildings: list[GuildBuilding]) -> list[str]:
        """获取当前布局触发的邻接加成说明"""
        descriptions = []
        by_type = {building.building_type: building for building in buildings}

        spirit_tower = by_type.get(BuildingType.SPIRIT_TOWER)
        if spirit_tower:
            power = cls._get_spirit_tower_power(spirit_tower)
            for building in buildings:
                if building.id == spirit_tower.id or not cls._is_adjacent(spirit_tower, building):
                    continue
                name = cls.BUILDING_CONFIGS[building.building_type]["name"]
                if building.building_type == BuildingType.ALCHEMY_ROOM:
                    descriptions.append(f"聚灵阵邻接{name}：丹房日产 +{power}")
                elif building.building_type == BuildingType.TRAINING_GROUND:
                    descriptions.append(f"聚灵阵邻接{name}：修为加成 +{power * 2}%")
                elif building.building_type == BuildingType.ARTIFACT_FORGE:
                    descriptions.append(f"聚灵阵邻接{name}：锻造金币折扣 +{power * 2}%")
                elif building.building_type == BuildingType.REFINING_PAVILION:
                    descriptions.append(f"聚灵阵邻接{name}：升阶成功率 +{power}%")

        forge = by_type.get(BuildingType.ARTIFACT_FORGE)
        refining = by_type.get(BuildingType.REFINING_PAVILION)
        if forge and refining and cls._is_adjacent(forge, refining):
            descriptions.append("铸器坊邻接淬灵台：锻造折扣 +3%，升阶成功率 +1%")

        warehouse = by_type.get(BuildingType.GUILD_WAREHOUSE)
        if forge and warehouse and cls._is_adjacent(forge, warehouse):
            descriptions.append("铸器坊邻接公会仓库：锻造金币折扣 +2%")

        return descriptions

    @classmethod
    def get_adjacency_bonuses(cls, buildings: list[GuildBuilding]) -> Dict:
        """根据布局邻接关系计算额外加成"""
        bonuses = {
            "daily_alchemy_production": 0,
            "cultivation_bonus": 0.0,
            "forge_gold_discount": 0.0,
            "upgrade_success_bonus": 0.0,
        }
        by_type = {building.building_type: building for building in buildings}

        spirit_tower = by_type.get(BuildingType.SPIRIT_TOWER)
        if spirit_tower:
            power = cls._get_spirit_tower_power(spirit_tower)
            for building in buildings:
                if building.id == spirit_tower.id or not cls._is_adjacent(spirit_tower, building):
                    continue
                if building.building_type == BuildingType.ALCHEMY_ROOM:
                    bonuses["daily_alchemy_production"] += power
                elif building.building_type == BuildingType.TRAINING_GROUND:
                    bonuses["cultivation_bonus"] += power * 0.02
                elif building.building_type == BuildingType.ARTIFACT_FORGE:
                    bonuses["forge_gold_discount"] += power * 0.02
                elif building.building_type == BuildingType.REFINING_PAVILION:
                    bonuses["upgrade_success_bonus"] += power * 0.01

        forge = by_type.get(BuildingType.ARTIFACT_FORGE)
        refining = by_type.get(BuildingType.REFINING_PAVILION)
        if forge and refining and cls._is_adjacent(forge, refining):
            bonuses["forge_gold_discount"] += 0.03
            bonuses["upgrade_success_bonus"] += 0.01

        warehouse = by_type.get(BuildingType.GUILD_WAREHOUSE)
        if forge and warehouse and cls._is_adjacent(forge, warehouse):
            bonuses["forge_gold_discount"] += 0.02

        return bonuses

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
        self,
        guild_id: int,
        building_type: BuildingType,
        player_id: str,
        plot_x: int | None = None,
        plot_y: int | None = None,
    ) -> Tuple[bool, str]:
        """
        建造或升级建筑

        Args:
            guild_id: 公会ID
            building_type: 建筑类型
            player_id: 操作玩家ID
            plot_x: 新建建筑布局X坐标，不传则自动放置
            plot_y: 新建建筑布局Y坐标，不传则自动放置

        Returns:
            (是否成功, 消息)

        对应原代码:
            guild_building_service.py Line 187-265

        Note:
            ✅ 原代码无P0问题：未发现内部commit
            新版本移除session参数，通过Repository操作数据
        """
        valid, reason, validation = await self.validate_build_or_upgrade(
            guild_id, building_type, player_id, plot_x, plot_y
        )
        if not valid:
            return False, reason

        cost = validation["cost"]
        new_position = validation["new_position"]
        material_sources = validation["material_sources"]
        guild = await self._guild_repo.get_by_id(guild_id)
        if not guild:
            return False, "公会不存在"

        # 扣除资金
        guild.treasury -= cost["gold"]
        await self._guild_repo.update(guild)

        # 扣除材料
        for material_name, source in material_sources.items():
            required_qty = source["required"]
            item_id = source["item_id"]
            warehouse_consumed = await self._consume_warehouse_material(
                guild_id, item_id, required_qty
            )
            bag_required = required_qty - warehouse_consumed
            if bag_required > 0:
                success_consume = await self._item_repo.consume_item(
                    player_id, item_id, bag_required
                )
                if not success_consume:
                    return False, f"扣除材料失败：{material_name}"

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
                level=1,
                plot_x=new_position[0],
                plot_y=new_position[1],
            )
            await self._building_repo.add(new_building)
            return True, f"{building_config['name']}建造成功，已放置在({new_position[0]},{new_position[1]})！"

    async def move_building(
        self,
        guild_id: int,
        building_type: BuildingType,
        player_id: str,
        plot_x: int,
        plot_y: int,
    ) -> Tuple[bool, str]:
        """移动已建造建筑到新的布局坐标"""
        can_build, reason = await GuildPermission.can_build(
            self._guild_repo._session, player_id, guild_id
        )
        if not can_build:
            return False, reason

        building = await self._building_repo.get_by_guild_and_type(guild_id, building_type)
        if not building:
            return False, "公会尚未建造该建筑"

        if building.plot_x == plot_x and building.plot_y == plot_y:
            return False, "建筑已经在该位置"

        if not self.is_valid_position(plot_x, plot_y):
            return False, f"布局坐标范围为 1-{self.GRID_SIZE}"

        occupied = await self._building_repo.get_by_guild_and_position(guild_id, plot_x, plot_y)
        building_name = self.BUILDING_CONFIGS[building_type]["name"]

        if occupied and occupied.id != building.id:
            occupied_name = self.BUILDING_CONFIGS[occupied.building_type]["name"]
            occupied.plot_x = building.plot_x
            occupied.plot_y = building.plot_y
            await self._building_repo.update(occupied)
            building.plot_x = plot_x
            building.plot_y = plot_y
            await self._building_repo.update(building)
            return True, f"{building_name}与{occupied_name}交换了位置"

        building.plot_x = plot_x
        building.plot_y = plot_y
        await self._building_repo.update(building)
        return True, f"{building_name}已移动到({plot_x},{plot_y})"

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
        await self._backfill_missing_positions(guild_id)
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
                "built_at": building.built_at,
                "plot_x": building.plot_x,
                "plot_y": building.plot_y,
            })

        return result

    @classmethod
    def format_layout(cls, buildings: List[Dict]) -> List[str]:
        """格式化3x3公会基地布局"""
        grid = [["空" for _ in range(cls.GRID_SIZE)] for _ in range(cls.GRID_SIZE)]
        unplaced = []

        for building in buildings:
            plot_x = building.get("plot_x")
            plot_y = building.get("plot_y")
            short_name = str(building["name"])[:2]
            if plot_x is None or plot_y is None:
                unplaced.append(building["name"])
                continue
            if cls.is_valid_position(plot_x, plot_y):
                grid[plot_y - 1][plot_x - 1] = short_name

        lines = ["**基地布局：**"]
        for idx, row in enumerate(grid, 1):
            lines.append(f"{idx}　" + " | ".join(f"{cell:^2}" for cell in row))
        lines.append("　1　 2　 3")
        if unplaced:
            lines.append("未布局：" + "、".join(unplaced))
        return lines

    @staticmethod
    def get_player_guide_lines() -> List[str]:
        """给玩家展示的建筑玩法说明"""
        return [
            "**怎么玩：**",
            "1. 会长先设置基地，再建造建筑",
            "2. 建筑放进3x3格子，坐标是 x y",
            "3. 只有上下左右相邻生效，斜角不算",
            "4. 用移动建筑免费调整布局",
            "",
            "**常用建筑：**",
            "训练场：全员修炼/闭关加成",
            "传送阵：回基地或从基地传送到势力范围",
            "丹房：每日产丹，用积分兑换",
            "公会仓库：在基地存取材料",
            "铸器坊/淬灵台：在基地锻造/升阶装备",
            "聚灵阵：只强化相邻建筑，本身不直接给修为",
            "",
            "**推荐相邻：**",
            "聚灵阵+训练场：修为加成 +2%",
            "聚灵阵+丹房：日产 +1",
            "聚灵阵+铸器坊：锻造金币折扣 +2%",
            "聚灵阵+淬灵台：升阶成功率 +1%",
            "铸器坊+淬灵台：锻造折扣 +3%，升阶成功率 +1%",
            "铸器坊+公会仓库：锻造金币折扣 +2%",
        ]

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
            "warehouse_capacity": 0,
            "forge_enabled": False,
            "forge_gold_discount": 0.0,
            "upgrade_success_bonus": 0.0,
            "upgrade_gold_discount": 0.0,
            "adjacency_descriptions": [],
        }

        for building in buildings:
            effects = building["effects"]
            for effect_type, value in effects.items():
                if effect_type == "forge_enabled":
                    bonuses["forge_enabled"] = bonuses["forge_enabled"] or bool(value)
                elif effect_type in bonuses:
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

        raw_buildings = await self._building_repo.get_all_by_guild_id(guild_id)
        adjacency_bonuses = self.get_adjacency_bonuses(raw_buildings)
        bonuses["daily_alchemy_production"] += adjacency_bonuses["daily_alchemy_production"]
        bonuses["cultivation_bonus"] += adjacency_bonuses["cultivation_bonus"]
        bonuses["forge_gold_discount"] += adjacency_bonuses["forge_gold_discount"]
        bonuses["upgrade_success_bonus"] += adjacency_bonuses["upgrade_success_bonus"]
        bonuses["adjacency_descriptions"] = self.get_adjacency_bonus_descriptions(raw_buildings)

        bonuses["forge_gold_discount"] = min(0.25, bonuses["forge_gold_discount"])
        bonuses["upgrade_success_bonus"] = min(0.15, bonuses["upgrade_success_bonus"])
        bonuses["upgrade_gold_discount"] = min(0.20, bonuses["upgrade_gold_discount"])

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
            "storage_slots": "仓库格子",
            "forge_enabled": "基地锻造",
            "forge_gold_discount": "锻造金币折扣",
            "upgrade_success_bonus": "升阶成功率",
            "upgrade_gold_discount": "升阶金币折扣",
            "adjacency_power": "灵脉强度",
            "defense_bonus": "防御加成",
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
            elif k == "forge_enabled":
                effects_list.append(f"{chinese_name} 开启")
            elif k in ["forge_gold_discount", "upgrade_success_bonus", "upgrade_gold_discount"]:
                effects_list.append(f"{chinese_name} +{v*100:.0f}%")
            elif k == "adjacency_power":
                effects_list.append(f"{chinese_name} {v}")
            elif k == "defense_bonus":
                effects_list.append(f"{chinese_name} +{v*100:.0f}%")
            else:
                effects_list.append(f"{chinese_name} {v}")

        return ", ".join(effects_list)


async def get_guild_bonuses(session, guild_id: int) -> Dict:
    """模块级入口：基于现有 session 计算公会建筑加成（委托唯一的Service实现）。"""
    service = GuildBuildingService(
        guild_repo=GuildRepository(session),
        building_repo=GuildBuildingRepository(session),
        item_repo=None,
    )
    return await service.get_guild_bonuses(guild_id)
