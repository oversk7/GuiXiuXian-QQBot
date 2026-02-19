"""
灵田系统 - 常量配置
"""
import yaml
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from nonebot import logger


# ==================== 灵田等级配置 ====================

# 灵田等级 -> 灵壤数量
FIELD_LEVEL_PLOTS = {
    1: 4,
    2: 6,
    3: 8,
    4: 10,
    5: 12,
    6: 14,
    7: 16,
    8: 18,
    9: 20,
}

# 灵田升级费用
FIELD_UPGRADE_COST = {
    1: 0,       # 初始无需升级
    2: 5000,
    3: 15000,
    4: 40000,
    5: 100000,
    6: 250000,
    7: 500000,
    8: 1000000,
    9: 2500000,
}

# 各等级解锁的稀有度
FIELD_LEVEL_UNLOCK_RARITY = {
    1: ["white"],
    2: ["white"],
    3: ["white", "green"],
    4: ["white", "green"],
    5: ["white", "green", "blue"],
    6: ["white", "green", "blue"],
    7: ["white", "green", "blue", "purple"],
    8: ["white", "green", "blue", "purple"],
    9: ["white", "green", "blue", "purple", "orange"],
}

# ==================== 灌溉配置 ====================

WATER_MAX_PER_DAY = 3        # 每地块每日灌溉上限
WATER_COOLDOWN_MINUTES = 30  # 灌溉冷却(分钟)
WATER_TIME_REDUCE_PERCENT = 0.15  # 每次灌溉减少15%剩余成长时间

# ==================== 窃灵配置 ====================

STEAL_MAX_PER_DAY = 5         # 每日窃灵总次数上限
STEAL_COOLDOWN_MINUTES = 15   # 窃灵冷却(分钟)
STEAL_PERCENT = 0.20          # 每次偷取上限(目标每种成熟作物的20%)
STEAL_MIN_QUANTITY = 1        # 至少偷1株
STEAL_TARGET_ACTIVE_HOURS = 48  # 目标范围:48小时内有活跃记录
STEAL_TARGET_LIST_LIMIT = 10   # 可偷目标列表最多显示

# ==================== 诡兽配置 ====================

GUARDIAN_HUNGRY_HOURS = 24     # 24小时未喂食进入饥饿状态
GUARDIAN_HUNGRY_RATE_PENALTY = 0.5  # 饥饿状态拦截率减半

# ==================== 采收配置 ====================

HARVEST_SEED_RETURN_CHANCE = 0.10  # 10%概率额外获得1颗同种种子

# ==================== 开田费用 ====================

FIELD_CREATE_COST = 1000  # 开辟灵田费用


# ==================== 作物配置加载 ====================

@dataclass
class CropData:
    """作物数据类"""
    crop_id: str
    name: str
    type: str       # VEGETABLE or HERB
    rarity: str     # white/green/blue/purple/orange
    grow_hours: float
    min_yield: int
    max_yield: int
    seed_id: str
    harvest_item_id: str
    seed_price: int
    sell_price: int
    description: str


@dataclass
class GuardianBeastData:
    """诡兽数据类"""
    beast_id: str
    name: str
    rarity: str
    intercept_rate: int
    penalty_gold: int
    daily_feed_cost: int
    item_id: str
    shop_price: int
    description: str


class CropManager:
    """作物配置管理器 - 加载和缓存作物配置"""

    _instance = None
    _crops: Dict[str, CropData] = {}
    _crops_by_seed: Dict[str, CropData] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_crops()
        return cls._instance

    def _load_crops(self):
        """从 YAML 文件加载作物配置"""
        crops_file = Path(__file__).parent.parent / "data" / "crops.yaml"

        if not crops_file.exists():
            logger.error(f"作物配置文件不存在: {crops_file}")
            return

        try:
            with open(crops_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            for crop_data in data.get("crops", []):
                crop = CropData(**crop_data)
                self._crops[crop.crop_id] = crop
                self._crops_by_seed[crop.seed_id] = crop

            logger.info(f"成功加载 {len(self._crops)} 个作物配置")
        except Exception as e:
            logger.error(f"加载作物配置失败: {e}")

    def get_crop(self, crop_id: str) -> Optional[CropData]:
        """根据作物ID获取配置"""
        return self._crops.get(crop_id)

    def get_crop_by_seed(self, seed_id: str) -> Optional[CropData]:
        """根据种子ID获取作物配置"""
        return self._crops_by_seed.get(seed_id)

    def get_crop_by_name(self, name: str) -> Optional[CropData]:
        """根据作物名称获取配置"""
        for crop in self._crops.values():
            if crop.name == name:
                return crop
        return None

    def get_crops_by_rarity(self, rarity: str) -> List[CropData]:
        """获取指定稀有度的作物"""
        return [c for c in self._crops.values() if c.rarity == rarity]

    def get_all_crops(self) -> List[CropData]:
        """获取所有作物"""
        return list(self._crops.values())

    def get_shop_crops(self) -> List[CropData]:
        """获取商店可购买的作物(白色+绿色)"""
        return [c for c in self._crops.values() if c.rarity in ("white", "green")]


class GuardianBeastManager:
    """诡兽配置管理器"""

    _instance = None
    _beasts: Dict[str, GuardianBeastData] = {}
    _beasts_by_item: Dict[str, GuardianBeastData] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_beasts()
        return cls._instance

    def _load_beasts(self):
        """从 YAML 文件加载诡兽配置"""
        beasts_file = Path(__file__).parent.parent / "data" / "guardian_beasts.yaml"

        if not beasts_file.exists():
            logger.error(f"诡兽配置文件不存在: {beasts_file}")
            return

        try:
            with open(beasts_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            for beast_data in data.get("guardian_beasts", []):
                beast = GuardianBeastData(**beast_data)
                self._beasts[beast.beast_id] = beast
                self._beasts_by_item[beast.item_id] = beast

            logger.info(f"成功加载 {len(self._beasts)} 个诡兽配置")
        except Exception as e:
            logger.error(f"加载诡兽配置失败: {e}")

    def get_beast(self, beast_id: str) -> Optional[GuardianBeastData]:
        return self._beasts.get(beast_id)

    def get_beast_by_item_id(self, item_id: str) -> Optional[GuardianBeastData]:
        return self._beasts_by_item.get(item_id)

    def get_beast_by_name(self, name: str) -> Optional[GuardianBeastData]:
        for beast in self._beasts.values():
            if beast.name == name:
                return beast
        return None

    def get_shop_beasts(self) -> List[GuardianBeastData]:
        """获取商店可购买的诡兽"""
        return [b for b in self._beasts.values() if b.shop_price > 0]

    def get_all_beasts(self) -> List[GuardianBeastData]:
        return list(self._beasts.values())
