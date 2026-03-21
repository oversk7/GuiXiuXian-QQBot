"""宠物系统配置加载"""
from dataclasses import dataclass
from typing import Dict, List, Optional
from pathlib import Path
import yaml
from nonebot import logger


@dataclass
class BeastConfig:
    """诡兽种族配置"""
    beast_id: str
    name: str
    rarity: str
    intercept_rate: int
    description: str
    transform_name: str
    transform_description: str
    transform_name_male: str = ""
    transform_description_male: str = ""


@dataclass
class GrowthConfig:
    """每级属性成长"""
    attack: float
    defense: float
    hp: float
    crit_rate: float
    dodge_rate: float


@dataclass
class AccessoryConfig:
    """饰品配置"""
    accessory_id: str
    name: str
    slot: str
    rarity: str
    price: int
    description_prefix: str
    bonus: Dict[str, float]
    description: str


@dataclass
class PetPersonality:
    """宠物人设（兽形/人形）"""
    role: str
    pronouns: List[str]
    speech_patterns: List[str]
    key_words: List[str]
    background: str
    behavioral_rules: List[str]


# 属性名中英翻译
ATTR_NAME_CN = {
    "attack": "攻击",
    "defense": "防御",
    "hp": "生命",
    "max_hp": "生命上限",
    "crit_rate": "暴击率",
    "dodge_rate": "闪避率",
    "accuracy": "命中率",
    "agility": "敏捷",
    "critical_damage": "暴击伤害",
    "combo_rate": "连击率",
    "penetration_rate": "穿透率",
    "counter_rate": "反击率",
    "lifesteal_rate": "吸血率",
    "accuracy_rate": "命中率",
}


def format_bonus(bonus: dict) -> str:
    """将属性加成字典格式化为中文文本"""
    parts = []
    for k, v in bonus.items():
        name = ATTR_NAME_CN.get(k, k)
        if isinstance(v, float) and v < 1:
            parts.append(f"{name}+{v:.1%}")
        else:
            parts.append(f"{name}+{v}")
    return ", ".join(parts)


class PetConfigManager:
    """宠物配置管理器（单例）"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def __init__(self):
        if not self._loaded:
            self._load_all()
            self._loaded = True

    def _load_all(self):
        data_dir = Path(__file__).parent.parent / "data"

        # 加载主配置
        with open(data_dir / "pet_config.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        self.settings: dict = config["settings"]
        self.level_exp_table: Dict[int, int] = {int(k): v for k, v in config["level_exp_table"].items()}
        self.mood_multiplier: Dict[int, float] = {int(k): v for k, v in config["mood_multiplier"].items()}
        self.affection_levels: Dict[int, str] = {int(k): v for k, v in config["affection_levels"].items()}

        # 解析种族配置
        self._beasts: Dict[str, BeastConfig] = {}
        for beast_id, data in config["beasts"].items():
            self._beasts[beast_id] = BeastConfig(beast_id=beast_id, **data)

        # 解析成长配置
        self._growth: Dict[str, GrowthConfig] = {}
        for rarity, data in config["growth_per_level"].items():
            self._growth[rarity] = GrowthConfig(**data)

        # 加载饰品配置
        with open(data_dir / "pet_accessories.yaml", "r", encoding="utf-8") as f:
            acc_config = yaml.safe_load(f)

        self._accessories: Dict[str, AccessoryConfig] = {}
        self._accessories_by_name: Dict[str, AccessoryConfig] = {}
        for data in acc_config["accessories"]:
            acc = AccessoryConfig(**data)
            self._accessories[acc.accessory_id] = acc
            self._accessories_by_name[acc.name] = acc
        self.accessory_slots: List[str] = acc_config["slots"]

        # 加载进化配置
        self.rarity_order: List[str] = config.get("rarity_order", ["white", "green", "blue", "purple", "orange"])
        self._evolution: Dict[str, dict] = config.get("evolution", {})

        # 加载人设配置
        with open(data_dir / "pet_personalities.yaml", "r", encoding="utf-8") as f:
            pers_config = yaml.safe_load(f)

        self._personalities: Dict[str, Dict[str, PetPersonality]] = {}
        for beast_id, forms in pers_config["personalities"].items():
            parsed = {
                "beast": PetPersonality(**forms["beast_form"]),
                "human": PetPersonality(**forms["human_form"]),
            }
            if "human_form_male" in forms:
                parsed["human_male"] = PetPersonality(**forms["human_form_male"])
            self._personalities[beast_id] = parsed

        logger.info(
            f"宠物配置加载完成: {len(self._beasts)}种族, "
            f"{len(self._accessories)}饰品, {len(self._personalities)}人设"
        )

    def get_beast(self, beast_id: str) -> Optional[BeastConfig]:
        return self._beasts.get(beast_id)

    def get_beast_by_name(self, name: str) -> Optional[BeastConfig]:
        for beast in self._beasts.values():
            if beast.name == name or beast.transform_name == name:
                return beast
        return None

    def get_all_beasts(self) -> List[BeastConfig]:
        return list(self._beasts.values())

    def get_growth(self, rarity: str) -> Optional[GrowthConfig]:
        return self._growth.get(rarity)

    def get_accessory(self, accessory_id: str) -> Optional[AccessoryConfig]:
        return self._accessories.get(accessory_id)

    def get_accessory_by_name(self, name: str) -> Optional[AccessoryConfig]:
        return self._accessories_by_name.get(name)

    def get_accessories_by_slot(self, slot: str) -> List[AccessoryConfig]:
        return [a for a in self._accessories.values() if a.slot == slot]

    def get_all_accessories(self) -> List[AccessoryConfig]:
        return list(self._accessories.values())

    def get_personality(self, beast_id: str, is_transformed: bool, gender: str = "") -> Optional[PetPersonality]:
        forms = self._personalities.get(beast_id)
        if not forms:
            return None
        if not is_transformed:
            return forms["beast"]
        # 化形后优先使用对应性别人设
        if gender == "male" and "human_male" in forms:
            return forms["human_male"]
        return forms["human"]  # 默认女性或无性别指定

    def get_exp_for_level(self, level: int) -> int:
        """获取到达某等级所需经验（线性插值）"""
        keys = sorted(self.level_exp_table.keys())
        if level <= keys[0]:
            return self.level_exp_table[keys[0]]
        if level >= keys[-1]:
            return self.level_exp_table[keys[-1]]

        for i in range(len(keys) - 1):
            if keys[i] <= level < keys[i + 1]:
                lo, hi = keys[i], keys[i + 1]
                ratio = (level - lo) / (hi - lo)
                return int(
                    self.level_exp_table[lo]
                    + ratio * (self.level_exp_table[hi] - self.level_exp_table[lo])
                )
        return 0

    def get_mood_multiplier(self, mood: int) -> float:
        """根据心情值获取属性倍率"""
        keys = sorted(self.mood_multiplier.keys(), reverse=True)
        for threshold in keys:
            if mood >= threshold:
                return self.mood_multiplier[threshold]
        return 0.5

    def get_affection_level_name(self, affection: int) -> str:
        """获取好感度等级名称"""
        keys = sorted(self.affection_levels.keys(), reverse=True)
        for threshold in keys:
            if affection >= threshold:
                return self.affection_levels[threshold]
        return "陌生"

    def get_next_rarity(self, current_rarity: str) -> Optional[str]:
        """获取下一个稀有度，已是最高则返回 None"""
        try:
            idx = self.rarity_order.index(current_rarity)
            if idx + 1 < len(self.rarity_order):
                return self.rarity_order[idx + 1]
        except ValueError:
            pass
        return None

    def get_evolution_config(self, from_rarity: str, to_rarity: str) -> Optional[dict]:
        """获取进化配置"""
        key = f"{from_rarity}_to_{to_rarity}"
        return self._evolution.get(key)

    def get_transform_name(self, beast_id: str, gender: str = "") -> str:
        """根据性别获取化形名"""
        beast = self.get_beast(beast_id)
        if not beast:
            return "未知"
        if gender == "male" and beast.transform_name_male:
            return beast.transform_name_male
        return beast.transform_name

    def get_transform_description(self, beast_id: str, gender: str = "") -> str:
        """根据性别获取化形描述"""
        beast = self.get_beast(beast_id)
        if not beast:
            return ""
        if gender == "male" and beast.transform_description_male:
            return beast.transform_description_male
        return beast.transform_description
