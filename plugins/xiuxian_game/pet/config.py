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

        # 加载人设配置
        with open(data_dir / "pet_personalities.yaml", "r", encoding="utf-8") as f:
            pers_config = yaml.safe_load(f)

        self._personalities: Dict[str, Dict[str, PetPersonality]] = {}
        for beast_id, forms in pers_config["personalities"].items():
            self._personalities[beast_id] = {
                "beast": PetPersonality(**forms["beast_form"]),
                "human": PetPersonality(**forms["human_form"]),
            }

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

    def get_personality(self, beast_id: str, is_transformed: bool) -> Optional[PetPersonality]:
        forms = self._personalities.get(beast_id)
        if not forms:
            return None
        return forms["human"] if is_transformed else forms["beast"]

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
