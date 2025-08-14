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

    
    @property
    def game_config(self) -> dict:
        """获取游戏配置"""
        return _load_config(self.config_file)

    @property
    def items_config(self) -> dict:
        """返回结构化物品配置"""
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
        return {"by_id": configs, "by_name": name_index, "by_type": type_index}

    @property
    def map_config(self) -> dict:
        config_data = _load_config(self.map_file)
        # 添加动态生成的无限层诡域配置
        config_data["dungeon_levels"] = self._generate_infinite_dungeon_levels()
        return config_data

    def _generate_infinite_dungeon_levels(self) -> dict:
        """动态生成无限重里世界配置"""
        rules = _load_config(self.map_file).get("dungeon_generation_rules", {})

        # 预生成前100重的配置（按需可扩展到更多）
        levels = {}
        for level in range(1, 101):
            levels[level] = self._generate_dungeon_level_config(level, rules)

        return levels

    def _generate_dungeon_level_config(self, level: int, rules: dict) -> dict:
        """生成单个里世界深度的配置"""
        import random

        # 计算诡异等级
        base_creature_level = level * 5  # 里世界深度 * 5
        variance = rules.get("monster_level_variance", 2)
        creature_level_min = max(1, base_creature_level - variance)
        creature_level_max = base_creature_level + variance

        # 计算理智消耗（每10重+1）
        mp_cost = max(1, 1 + (level - 1) // 10)

        # 随机选择诡异名称
        creature_names = rules.get("monster_names", ["未知诡异"])
        selected_creatures = random.sample(creature_names, min(3, len(creature_names)))

        # 根据深度选择材料
        merchant_materials, basic_materials = self._get_materials_for_level(level, rules)

        return {
            "name": f"{level}层诡域",
            "required_level": 1,  # 里世界系统不限制玩家等级，只限制深度解锁
            "tier": min(10, (level - 1) // 10 + 1),  # 每10重一个tier
            "mp_cost": mp_cost,
            "level_range": [creature_level_min, creature_level_max],
            "monsters": selected_creatures,
            "merchant_materials": merchant_materials,
            "basic_materials": basic_materials
        }

    def _get_materials_for_level(self, level: int, rules: dict) -> tuple[list, list]:
        """根据里世界深度获取材料配置"""
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
        
