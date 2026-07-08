from pydantic_settings import BaseSettings
from pathlib import Path
import yaml
from functools import lru_cache

class Config(BaseSettings):
    data_dir: Path = Path(__file__).parent / "data"
    config_file: Path = data_dir / "config.yaml"
    items_file: Path = data_dir / "items.yaml"
    map_file: Path = data_dir / "map.yaml"
    elixirs_file: Path = data_dir / "elixirs.yaml"

    # 缓存 items_config，避免每次访问都重新生成
    _cached_items_config: dict = None
    # 缓存 map_config，避免每次访问都重新生成100层诡域配置
    _cached_map_config: dict = None

    @property
    def game_config(self) -> dict:
        """获取游戏配置"""
        return _load_config(self.config_file)

    @property
    def items_config(self) -> dict:
        """返回结构化物品配置（缓存版本，支持动态注册）"""
        # 如果已经缓存，直接返回
        if self._cached_items_config is not None:
            return self._cached_items_config

        # 首次加载：从 YAML 文件加载并建立索引
        from .models.inventory import ItemConfig, ItemType
        items = _load_config(self.items_file)
        # 建立三种索引
        configs = {}
        name_index = {}
        type_index = {t.value: [] for t in ItemType}
        for category in items["items"].values():
            for item in category:
                config = ItemConfig(item)
                configs[item["item_id"]] = config
                name_index[item["name"]] = config
                type_index[config.type.value].append(config.item_id)

        # 缓存结果
        self._cached_items_config = {"by_id": configs, "by_name": name_index, "by_type": type_index}
        return self._cached_items_config

    @property
    def map_config(self) -> dict:
        # 如果已经缓存，直接返回（生成过程是确定性的，缓存安全）
        if self._cached_map_config is not None:
            return self._cached_map_config

        config_data = _load_config(self.map_file)
        # 添加动态生成的无限层诡域配置
        config_data["dungeon_levels"] = self._generate_infinite_dungeon_levels()
        self._cached_map_config = config_data
        return self._cached_map_config

    def _generate_infinite_dungeon_levels(self) -> dict:
        """动态生成无限重诡域配置"""
        rules = _load_config(self.map_file).get("dungeon_generation_rules", {})

        # 预生成前100重的配置（按需可扩展到更多）
        levels = {}
        for level in range(1, 101):
            levels[level] = self._generate_dungeon_level_config(level, rules)

        return levels

    def _generate_dungeon_level_config(self, level: int, rules: dict) -> dict:
        """生成单个诡域深度的配置（确定性：同一深度每次生成结果一致）"""
        import random

        # 计算诡异等级
        base_creature_level = level * 5  # 诡域深度 * 5
        variance = rules.get("monster_level_variance", 2)
        creature_level_min = max(1, base_creature_level - variance)
        creature_level_max = base_creature_level + variance

        # 计算理智消耗（两段式）
        # 前10000层：线性递增  level // 10
        #   第10层=1, 第100层=10, 第1000层=100, 第5000层=500, 第10000层=1000
        # 10001层+：平方增长  1000 + ((level-10000) // 50)²
        #   第11000层=1400, 第15000层=11000, 第20000层=41000
        if level <= 10000:
            mp_cost = max(1, level // 10)
        else:
            excess = level - 10000
            mp_cost = 1000 + (excess // 50) ** 2
        mp_cost = max(1, mp_cost)

        # 按深度确定性选择诡异名称（无种子的 random 会导致每次读配置怪名池漂移）
        creature_names = rules.get("monster_names", ["未知诡异"])
        rng = random.Random(f"dungeon_monsters:{level}")
        selected_creatures = rng.sample(creature_names, min(3, len(creature_names)))

        # 根据深度选择材料
        merchant_materials, basic_materials = self._get_materials_for_level(level, rules)

        return {
            "name": f"{level}层诡域",
            "required_level": 1,  # 诡域系统不限制玩家等级，只限制深度解锁
            "tier": min(10, (level - 1) // 10 + 1),  # 每10重一个tier
            "mp_cost": mp_cost,
            "level_range": [creature_level_min, creature_level_max],
            "monsters": selected_creatures,
            "merchant_materials": merchant_materials,
            "basic_materials": basic_materials
        }

    def _get_materials_for_level(self, level: int, rules: dict) -> tuple[list, list]:
        """根据诡域深度获取材料配置"""
        material_tiers = rules.get("material_tiers", {})

        # 查找匹配的材料深度
        for tier_range, materials in material_tiers.items():
            if "-" in tier_range:
                start, end = map(int, tier_range.split("-"))
                if start <= level <= end:
                    return materials.get("merchant_materials", []), materials.get("basic_materials", [])

        # 默认材料
        return ["wanted_poster"], ["grave_soil", "bone_fragment"]

    @property
    def elixirs_config(self) -> dict:
        """返回丹方配置"""
        return _load_config(self.elixirs_file)

@lru_cache(maxsize=None)
def _load_config(config_file: Path) -> dict:
    """独立配置加载函数"""
    if not config_file.exists():
        raise FileNotFoundError(f"配置文件 {config_file} 不存在")
    with open(config_file, "r", encoding="utf8") as f:
        return yaml.safe_load(f)
    
config = Config()
        
