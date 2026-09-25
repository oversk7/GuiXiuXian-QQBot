from __future__ import annotations

"""诡域生成服务
怪物原型与属性计算、区域材料、商人商品、掉落结算、格子生成（纯业务逻辑）
"""

import hashlib
import random
from datetime import datetime, date

from sqlalchemy import select

from ..config import config
from ..models.player import Player
from ..models.world_tile import WorldTile


# 手动探索宝箱的独立材料奖励，供结算与图鉴共用。
TREASURE_MATERIAL_ITEM_ID = "pet_evolution_stone"
TREASURE_MATERIAL_CHANCE = 0.005


def _roll_additional_equipment(monster_level: int, is_elite: bool, luck: int, rng):
    from ..utils import luck_prob

    candidates = []
    weights = []
    for item_id in config.items_config["by_type"].get("EQUIPMENT", []):
        tpl = config.items_config["by_id"][item_id]
        drop = tpl.dungeon_drop
        if not drop or tpl.rarity == "red":
            continue
        if monster_level < max(tpl.required_level, drop["min_level"]):
            continue
        if drop.get("max_level") is not None and monster_level > drop["max_level"]:
            continue
        candidates.append(tpl)
        weights.append(drop["weight"])

    if not candidates:
        return None
    drop_rate = 0.01 if is_elite else 0.0025
    if rng.random() >= drop_rate * (1 + luck_prob(luck)):
        return None
    return rng.choices(candidates, weights=weights, k=1)[0]


def _stable_tile_hash(seed: str) -> int:
    """跨进程稳定的种子哈希。内置 hash() 每次启动随机化，会破坏"同一天同格子确定性"。"""
    return int.from_bytes(hashlib.md5(seed.encode("utf-8")).digest()[:8], "big")


_TILE_EVENT_TYPES = ["MATERIAL", "TREASURE", "EMPTY", "REST", "MERCHANT", "ELITE"]


def _event_weights_for_tier(tier: int) -> list[int]:
    """各事件类型的生成权重，顺序与 _TILE_EVENT_TYPES 一致"""
    if tier <= 2:
        # 低级诡域：基础事件为主
        return [15, 5, 70, 5, 2, 3]
    elif tier <= 4:
        # 中级诡域：增加商人和精英怪
        return [12, 5, 70, 7, 2, 4]
    # 高级诡域：更多特殊事件
    return [10, 5, 70, 5, 4, 6]

# -------- 材料掉落权重配置 --------
RARITY_WEIGHTS = {
    "white": 50,    # 白色材料权重
    "green": 25,    # 绿色材料权重
    "blue": 15,     # 蓝色材料权重
    "purple": 8,    # 紫色材料权重
    "orange": 2     # 橙色材料权重
}

# -------- 铭文掉落配置（Phase 3）--------
INSCRIPTION_DROP_RATES = {60: 0.0, 100: 0.03, 200: 0.04, 9999: 0.05}
INSCRIPTION_TYPE_WEIGHTS = {"basic": 60, "advanced": 40}
ADVANCED_RARITY_WEIGHTS = {"purple": 80, "orange": 20}
ADVANCED_ORANGE_MIN_LEVEL = 150
CELESTIAL_GRADE_MIN_LEVEL = 3000
FRAGMENT_DROP_RATE = 0.08
FRAGMENT_ITEM_ID = "inscription_fragment"

# -------- 怪物原型配置 --------
MONSTER_ARCHETYPES = {
    "balanced": {  # 平衡型：无前缀，属性均衡
        "name": "平衡", "prefix": "", "icon": "",
        "stat_mult": {"hp": 1.0, "attack": 1.0, "agility": 1.0},
        "special_profile": {"crit_rate": 1.0, "combo_rate": 1.0, "counter_rate": 1.0, "anti_crit_rate": 1.0, "true_damage_rate": 0, "defense_ratio": 0.0, "accuracy_bonus": 0},
        "weight": {"low": 50, "mid": 30, "high": 15}, "elite_weight": 3,
    },
    "berserker": {  # 狂暴型：高暴击高攻，脆皮
        "name": "狂暴", "prefix": "狂暴·", "icon": "🔥",
        "stat_mult": {"hp": 0.7, "attack": 1.35, "agility": 1.0},
        "special_profile": {"crit_rate": 2.5, "combo_rate": 0.5, "counter_rate": 0.3, "anti_crit_rate": 0.0, "true_damage_rate": 0, "defense_ratio": 0.0, "accuracy_bonus": 0},
        "weight": {"low": 10, "mid": 20, "high": 20}, "elite_weight": 15,
    },
    "tank": {  # 坚韧型：高HP高防高抗暴，低攻
        "name": "坚韧", "prefix": "坚韧·", "icon": "🛡️",
        "stat_mult": {"hp": 1.5, "attack": 0.65, "agility": 0.7},
        "special_profile": {"crit_rate": 0.0, "combo_rate": 0.0, "counter_rate": 0.8, "anti_crit_rate": 1.5, "true_damage_rate": 0, "defense_ratio": 0.35, "accuracy_bonus": 0},
        "weight": {"low": 10, "mid": 15, "high": 18}, "elite_weight": 15,
    },
    "swift": {  # 迅捷型：高敏捷高连击高反击
        "name": "迅捷", "prefix": "迅捷·", "icon": "💨",
        "stat_mult": {"hp": 0.85, "attack": 0.9, "agility": 1.6},
        "special_profile": {"crit_rate": 0.5, "combo_rate": 2.5, "counter_rate": 2.0, "anti_crit_rate": 0.3, "true_damage_rate": 0, "defense_ratio": 0.0, "accuracy_bonus": 15},
        "weight": {"low": 8, "mid": 18, "high": 18}, "elite_weight": 15,
    },
    "piercer": {  # 穿透型：有真伤，高攻，低HP
        "name": "穿透", "prefix": "穿透·", "icon": "🗡️",
        "stat_mult": {"hp": 0.65, "attack": 1.2, "agility": 0.9},
        "special_profile": {"crit_rate": 0.8, "combo_rate": 0.3, "counter_rate": 0.5, "anti_crit_rate": 0.3, "true_damage_rate": 15, "defense_ratio": 0.0, "accuracy_bonus": 20},
        "weight": {"low": 2, "mid": 8, "high": 12}, "elite_weight": 12,
    },
    "trickster": {  # 诡诈型：高反击高抗暴
        "name": "诡诈", "prefix": "诡诈·", "icon": "🎭",
        "stat_mult": {"hp": 1.0, "attack": 0.95, "agility": 1.1},
        "special_profile": {"crit_rate": 0.6, "combo_rate": 0.4, "counter_rate": 2.5, "anti_crit_rate": 1.8, "true_damage_rate": 0, "defense_ratio": 0.1, "accuracy_bonus": 10},
        "weight": {"low": 5, "mid": 10, "high": 12}, "elite_weight": 12,
    },
    "devourer": {  # 噬魂型：高暴击+真伤，稀有强力型
        "name": "噬魂", "prefix": "噬魂·", "icon": "👁️",
        "stat_mult": {"hp": 0.75, "attack": 1.3, "agility": 1.1},
        "special_profile": {"crit_rate": 2.0, "combo_rate": 1.0, "counter_rate": 0.5, "anti_crit_rate": 0.5, "true_damage_rate": 10, "defense_ratio": 0.0, "accuracy_bonus": 25},
        "weight": {"low": 0, "mid": 2, "high": 5}, "elite_weight": 8,
    },
    "guardian": {  # 守卫型：极高防御和HP，极低攻击
        "name": "守卫", "prefix": "守卫·", "icon": "🏰",
        "stat_mult": {"hp": 1.8, "attack": 0.5, "agility": 0.5},
        "special_profile": {"crit_rate": 0.0, "combo_rate": 0.0, "counter_rate": 1.2, "anti_crit_rate": 2.0, "true_damage_rate": 0, "defense_ratio": 0.5, "accuracy_bonus": -10},
        "weight": {"low": 5, "mid": 7, "high": 10}, "elite_weight": 8,
    },
}

# 怪物特殊属性上限
MONSTER_SPECIAL_CAPS = {
    "crit_rate": (50, 65),         # (普通上限, 精英上限)
    "combo_rate": (30, 40),
    "counter_rate": (60, 75),
    "anti_crit_rate": (95, 99),
    "true_damage_rate": (25, 35),
    "accuracy_rate": (200, 250),   # 命中率随层级提升，对抗玩家闪避堆叠
}

def get_materials_by_rarity(rarity: str) -> list:
    """获取指定稀有度的所有材料(排除里界专属材料和活动限定材料)"""
    materials = []
    for item_id in config.items_config["by_type"]["MATERIAL"]:
        item_config = config.items_config["by_id"].get(item_id)
        if item_config and item_config.rarity == rarity:
            # 过滤掉里界专属材料、活动限定材料和非掉落材料（如铭文碎片）
            if "inner_realm_only" not in item_config.tags and "event_only" not in item_config.tags and "no_drop" not in item_config.tags:
                materials.append(item_id)
    return materials

def get_region_materials(region: str) -> dict:
    """获取区域材料配置（支持无限层诡域）"""
    # 检查是否为新的层级制诡域
    if "层诡域" in region:
        try:
            level_str = region.replace("层诡域", "")
            # 兼容"第N层诡域"格式，移除开头的"第"字
            if level_str.startswith("第"):
                level_str = level_str[1:]
            level = int(level_str)
            # 优先从预生成配置获取，如果不存在则动态生成（支持无限层）
            region_config = config.map_config.get("dungeon_levels", {}).get(level)
            if not region_config:
                # 动态生成超过100层的配置
                region_config = config._generate_dungeon_level_config(
                    level, config.map_config.get("dungeon_generation_rules", {})
                )
            return {
                "merchant": region_config.get("merchant_materials", []),  # 商人材料（高价值）
                "basic": region_config.get("basic_materials", [])         # 基础材料（材料格子）
            }
        except ValueError:
            pass

    # 兼容旧的命名诡域
    region_config = config.map_config["regions"].get(region, {})
    return {
        "merchant": region_config.get("merchant_materials", []),  # 商人材料（高价值）
        "basic": region_config.get("basic_materials", [])         # 基础材料（材料格子）
    }

def select_monster_archetype(monster_level: int, is_elite: bool, rng) -> str | None:
    """根据怪物等级选择原型，200级以下返回None"""
    if monster_level < 200:
        return None

    # 确定权重档位
    if monster_level < 500:
        tier_key = "low"
    elif monster_level < 2000:
        tier_key = "mid"
    else:
        tier_key = "high"

    archetypes = list(MONSTER_ARCHETYPES.keys())
    if is_elite:
        weights = []
        for key in archetypes:
            arch = MONSTER_ARCHETYPES[key]
            w = arch["elite_weight"]
            # 精英怪中平衡型权重降到 1/3
            if key == "balanced":
                w = max(1, w // 3)
            weights.append(w)
    else:
        weights = [MONSTER_ARCHETYPES[key]["weight"][tier_key] for key in archetypes]

    return rng.choices(archetypes, weights=weights, k=1)[0]


def get_monster_display_name(base_name: str, archetype: str | None, is_elite: bool) -> str:
    """生成怪物显示名称（含原型前缀和精英标记）"""
    if not archetype or archetype == "balanced":
        prefix = ""
    else:
        arch = MONSTER_ARCHETYPES[archetype]
        prefix = f"{arch['icon']}{arch['prefix']}"

    if is_elite:
        return f"精英·{prefix}{base_name}"
    return f"{prefix}{base_name}"


def calculate_monster_attributes(monster_level: int, is_elite: bool = False, archetype: str | None = None, rng_instance=None) -> dict:
    """
    计算诡异属性，支持无限层级（200+级开始有特殊属性）和怪物原型
    爬塔系统：诡异强度逐层递增，保持挑战性
    200层以后（约1000级）大幅提高抗暴率，应对高暴击伤害玩家

    archetype: 怪物原型key（如"berserker"），None时走原有逻辑
    rng_instance: 外部传入的随机数生成器，None时创建新实例
    """
    import random

    # 优化的属性计算，支持高等级
    if monster_level <= 50:
        # 前期线性增长（1-50级）
        base_hp = 1.2 * monster_level + 15
        base_attack = 0.6 * monster_level + 2
        base_agility = 0.5 * monster_level
    elif monster_level <= 100:
        # 中期增长（51-100级）
        base_hp = 1.5 * monster_level + 40
        base_attack = 0.7 * monster_level + 25
        base_agility = 0.5 * monster_level + 20
    elif monster_level <= 200:
        # 高期增长（101-200级）
        base_hp = 2.0 * monster_level + 80
        base_attack = 1.0 * monster_level + 50
        base_agility = 0.6 * monster_level + 30
    elif monster_level <= 500:
        # 超高期增长（201-500级）
        base_hp = 2.5 * monster_level + 200
        base_attack = 1.2 * monster_level + 100
        base_agility = 0.7 * monster_level + 50
    else:
        # 终极期（501+级）- 支持无限扩展
        base_hp = 3.0 * monster_level + 500
        base_attack = 1.5 * monster_level + 200
        base_agility = 0.8 * monster_level + 100

    # 添加随机波动（±5%，减少波动保持平衡）
    rng = rng_instance if rng_instance else random.Random()
    hp_variation = rng.uniform(0.95, 1.05)
    attack_variation = rng.uniform(0.95, 1.05)
    agility_variation = rng.uniform(0.95, 1.05)

    hp = int(base_hp * hp_variation)
    attack = int(base_attack * attack_variation)
    agility = int(base_agility * agility_variation)

    # 精英诡异属性提升
    if is_elite:
        if monster_level <= 100:
            elite_multiplier = 1.8
        elif monster_level <= 500:
            elite_multiplier = 2.0
        elif monster_level <= 1000:
            elite_multiplier = 2.2
        else:
            elite_multiplier = 2.5  # 1000级以后的精英怪更强

        hp = int(hp * elite_multiplier)
        attack = int(attack * elite_multiplier)
        agility = int(agility * elite_multiplier)

    # 为200级以后的诡异添加特殊战斗属性（200层约1000级怪物）
    special_attributes = {}
    defense = 0
    true_damage_rate = 0

    if monster_level >= 200:
        # 基础特殊属性计算（基于层级）
        level_factor = (monster_level - 200) / 100  # 每100级为一个档次

        # 200-999级：基础特殊属性
        if monster_level < 1000:
            crit_rate = min(8, 2 + level_factor * 1)
            combo_rate = min(5, 1 + level_factor * 0.5)
            counter_rate = min(10, 3 + level_factor * 1)
            anti_crit_rate = min(40, 15 + level_factor * 3)
            accuracy_rate = 85 + level_factor * 1.5
        else:
            # 1000级以后：超高特殊属性（200层以后）
            high_level_factor = (monster_level - 1000) / 100
            crit_rate = min(25, 5 + high_level_factor * 2)
            combo_rate = min(15, 3 + high_level_factor * 1.5)
            counter_rate = min(30, 8 + high_level_factor * 2)
            anti_crit_rate = min(80, 50 + high_level_factor * 5)
            accuracy_rate = 95 + high_level_factor * 4

        if archetype and archetype in MONSTER_ARCHETYPES:
            # ---- 原型系统：应用原型倍率 ----
            arch = MONSTER_ARCHETYPES[archetype]
            profile = arch["special_profile"]

            # 三维属性应用原型倍率
            hp = int(hp * arch["stat_mult"]["hp"])
            attack = int(attack * arch["stat_mult"]["attack"])
            agility = int(agility * arch["stat_mult"]["agility"])

            # 特殊属性应用原型倍率（命中为加法修正：迅捷/穿透/噬魂高命中，守卫低命中）
            crit_rate *= profile["crit_rate"]
            combo_rate *= profile["combo_rate"]
            counter_rate *= profile["counter_rate"]
            anti_crit_rate *= profile["anti_crit_rate"]
            accuracy_rate += profile.get("accuracy_bonus", 0)

            # 精英怪原型强化：倍率>1.0的属性额外×1.3
            if is_elite:
                if profile["crit_rate"] > 1.0:
                    crit_rate *= 1.3
                if profile["combo_rate"] > 1.0:
                    combo_rate *= 1.3
                if profile["counter_rate"] > 1.0:
                    counter_rate *= 1.3
                if profile["anti_crit_rate"] > 1.0:
                    anti_crit_rate *= 1.3

            # 计算防御（基于当前攻击力）
            if profile["defense_ratio"] > 0:
                defense = int(attack * profile["defense_ratio"])

            # 设置真伤率（固定值）
            true_damage_rate = profile["true_damage_rate"]

            # 精英怪真伤强化
            if is_elite and true_damage_rate > 0:
                true_damage_rate *= 1.3

            # 精英怪命中强化
            if is_elite:
                accuracy_rate += 10

            # 应用特殊属性上限
            cap_idx = 1 if is_elite else 0
            crit_rate = min(crit_rate, MONSTER_SPECIAL_CAPS["crit_rate"][cap_idx])
            combo_rate = min(combo_rate, MONSTER_SPECIAL_CAPS["combo_rate"][cap_idx])
            counter_rate = min(counter_rate, MONSTER_SPECIAL_CAPS["counter_rate"][cap_idx])
            anti_crit_rate = min(anti_crit_rate, MONSTER_SPECIAL_CAPS["anti_crit_rate"][cap_idx])
            true_damage_rate = min(true_damage_rate, MONSTER_SPECIAL_CAPS["true_damage_rate"][cap_idx])
            accuracy_rate = min(accuracy_rate, MONSTER_SPECIAL_CAPS["accuracy_rate"][cap_idx])
        else:
            # ---- 无原型：保持原有精英加成逻辑 ----
            if is_elite:
                if monster_level < 1000:
                    crit_rate = min(15, crit_rate * 1.5)
                    combo_rate = min(8, combo_rate * 1.3)
                    counter_rate = min(15, counter_rate * 1.2)
                    anti_crit_rate = min(60, anti_crit_rate * 1.4)
                else:
                    crit_rate = min(35, crit_rate * 1.3)
                    combo_rate = min(20, combo_rate * 1.2)
                    counter_rate = min(40, counter_rate * 1.2)
                    anti_crit_rate = min(95, anti_crit_rate * 1.15)
                accuracy_rate += 10
            accuracy_rate = min(accuracy_rate, MONSTER_SPECIAL_CAPS["accuracy_rate"][1 if is_elite else 0])

        special_attributes = {
            "crit_rate": round(crit_rate, 1),
            "combo_rate": round(combo_rate, 1),
            "counter_rate": round(counter_rate, 1),
            "anti_crit_rate": round(anti_crit_rate, 1),
            "accuracy_rate": round(accuracy_rate, 1),
        }

    result = {
        "hp": hp,
        "attack": attack,
        "agility": agility,
        "defense": defense,
    }

    if archetype:
        result["archetype"] = archetype

    if true_damage_rate > 0:
        result["true_damage_rate"] = round(true_damage_rate, 1)

    # 如果有特殊属性，添加到结果中
    if special_attributes:
        result.update(special_attributes)

    return result

def get_monster_material_rates(monster_level: int) -> dict:
    """普通材料品质判定概率，供战斗结算和图鉴共用。"""
    # 根据诡异等级确定掉落概率和稀有度
    if monster_level <= 20:
        # 低级诡异：30%掉落白色，10%绿色
        drop_rates = {"white": 0.30, "green": 0.10}
    elif monster_level <= 60:
        # 中级诡异：40%白色，20%绿色，5%蓝色
        drop_rates = {"white": 0.40, "green": 0.20, "blue": 0.05}
    elif monster_level <= 100:
        # 高级诡异：30%白色，25%绿色，15%蓝色，3%紫色
        drop_rates = {"white": 0.30, "green": 0.25, "blue": 0.15, "purple": 0.03}
    elif monster_level <= 200:
        # 顶级诡异：20%白色，20%绿色，20%蓝色，8%紫色，1%橙色
        drop_rates = {"white": 0.20, "green": 0.20, "blue": 0.20, "purple": 0.08, "orange": 0.01}
    else:
        # 超级诡异（200层以后）：15%白色，15%绿色，25%蓝色，12%紫色，3%橙色
        drop_rates = {"white": 0.15, "green": 0.15, "blue": 0.25, "purple": 0.12, "orange": 0.03}

    return drop_rates


def get_monster_material_candidates(region_materials: dict, rarity: str) -> list:
    """保持结算顺序：白色判定用基础池，非白色优先当地商人池，橙色不全局回退。"""
    if rarity == "white":
        return list(region_materials["basic"])
    candidates = [item_id for item_id in region_materials["merchant"]
                  if (item := config.items_config["by_id"].get(item_id)) and item.rarity == rarity]
    if not candidates and rarity != "orange":
        return get_materials_by_rarity(rarity)
    return candidates


def get_merchant_extra_rarities(tier: int) -> list[str]:
    """商人随机补充材料可选品质，与实际生成共用。"""
    if tier <= 2:
        return ["green"]
    if tier <= 4:
        return ["green", "blue"]
    return ["blue", "purple", "orange"]


def generate_merchant_goods(region: str, tier: int, rng) -> list:
    """生成商人商品列表 - 专门出售高价值材料和低级宝石"""
    goods = []
    region_materials = get_region_materials(region)

    # 商人主要出售区域的高价值材料
    merchant_materials = region_materials["merchant"]

    # 生成3-5个商品，优先使用商人专属材料
    goods_count = rng.randint(3, 5)
    for _ in range(goods_count):
        if merchant_materials and rng.random() < 0.8:
            # 80%概率选择商人专属材料
            material_id = rng.choice(merchant_materials)
        else:
            # 20%概率选择其他稀有材料
            rarities = get_merchant_extra_rarities(tier)

            rarity = rng.choice(rarities)
            rarity_materials = get_materials_by_rarity(rarity)
            material_id = rng.choice(rarity_materials) if rarity_materials else None

        if material_id:
            item_config = config.items_config["by_id"].get(material_id)
            if item_config:
                # 商人价格比正常价格高30-60%（物有所值）
                price_multiplier = rng.uniform(1.3, 1.6)
                price = int(item_config.price * price_multiplier)
                quantity = rng.randint(1, 2)  # 稀有材料数量较少

                goods.append({
                    "item_id": material_id,
                    "quantity": quantity,
                    "price": price
                })

    # 50%概率追加1-2个低级宝石，价格为原价3-5倍（稀缺高价）
    if rng.random() < 0.5:
        gem_ids = [item_id for item_id in config.items_config["by_type"].get("GEM", [])
                   if config.items_config["by_id"].get(item_id) and
                   config.items_config["by_id"][item_id].rarity == "white"
                   and not item_id.startswith("spirit_burst_amethyst_")]
        if gem_ids:
            gem_count = rng.randint(1, 2)
            for _ in range(gem_count):
                gem_id = rng.choice(gem_ids)
                gem_cfg = config.items_config["by_id"].get(gem_id)
                if gem_cfg and gem_cfg.price > 0:
                    gem_price = int(gem_cfg.price * rng.uniform(3.0, 5.0))
                    goods.append({
                        "item_id": gem_id,
                        "quantity": 1,
                        "price": gem_price
                    })

    return goods

async def handle_monster_drops(session, player: Player, monster_level: int, region: str, rng, is_elite: bool = False) -> str:
    """处理诡异掉落材料"""
    from ..models.inventory import ItemInstance
    from ..utils import luck_prob

    drop_rates = get_monster_material_rates(monster_level)

    # 精英怪掉落率翻倍，并且有更高概率掉落稀有材料
    if is_elite:
        enhanced_rates = {}
        for rarity, rate in drop_rates.items():
            if rarity in ["purple", "orange"]:
                enhanced_rates[rarity] = min(rate * 3, 0.5)  # 紫橙材料3倍概率
            else:
                enhanced_rates[rarity] = min(rate * 2, 0.8)  # 其他材料2倍概率
        drop_rates = enhanced_rates

    drops = {}
    region_materials = get_region_materials(region)

    # 检查每个稀有度的掉落
    for rarity, base_rate in drop_rates.items():
        # 幸运值影响掉落率
        final_rate = base_rate * (1 + luck_prob(player.luck))

        if rng.random() < final_rate:
            # 选择掉落的材料
            candidate_materials = get_monster_material_candidates(region_materials, rarity)

            if candidate_materials:
                material_id = rng.choice(candidate_materials)
                quantity = rng.randint(1, 2)  # 1-2个

                # 幸运加成可能翻倍
                if rng.random() < luck_prob(player.luck):
                    quantity *= 2

                try:
                    await ItemInstance.add_item(session, player.id, material_id, quantity)
                    item_config = config.items_config["by_id"].get(material_id)
                    if item_config:
                        display_name = item_config.get_display_name()
                        if display_name in drops:
                            drops[display_name] += quantity
                        else:
                            drops[display_name] = quantity
                except ValueError:
                    # 背包满了，跳过这个掉落
                    pass

    # ===== 装备掉落（词缀系统 Phase 1）=====
    from ..item.affix_service import generate_affixes, VIP_EQUIPMENT_IDS

    # 保留原有装备池与掉率；独立池在所有原有掉落结算后判定。
    if is_elite:
        if monster_level > 200:
            equip_drop_rate = 0.12   # 200+精英 12%
            equip_rarities = ["purple", "purple", "orange"]  # 橙装唯一来源
        elif monster_level > 100:
            equip_drop_rate = 0.10   # 101-200精英 10%
            equip_rarities = ["blue"]
        elif monster_level > 40:
            equip_drop_rate = 0.09   # 41-100精英 9%
            equip_rarities = ["green"]
        else:
            equip_drop_rate = 0.08   # ≤40精英 8%
            equip_rarities = ["white"]
    elif monster_level > 200:
        equip_drop_rate = 0.025  # 200+普通怪 2.5%
        equip_rarities = ["blue", "purple"]
    elif monster_level > 100:
        equip_drop_rate = 0.02   # 101-200普通怪 2%
        equip_rarities = ["green", "blue"]
    elif monster_level > 40:
        equip_drop_rate = 0.015  # 41-100普通怪 1.5%
        equip_rarities = ["white", "green"]
    else:
        equip_drop_rate = 0.01   # ≤40普通怪 1%
        equip_rarities = ["white"]

    # 幸运值加成
    equip_drop_rate *= (1 + luck_prob(player.luck))

    if rng.random() < equip_drop_rate:
        # 选择掉落装备的稀有度
        drop_rarity = rng.choice(equip_rarities)

        def _collect_candidates(rarity: str) -> list:
            result = []
            for eq_item_id in config.items_config["by_type"].get("EQUIPMENT", []):
                eq_item_cfg = config.items_config["by_id"].get(eq_item_id)
                if not eq_item_cfg:
                    continue
                if eq_item_cfg.rarity != rarity:
                    continue
                if eq_item_id in VIP_EQUIPMENT_IDS:
                    continue
                if eq_item_cfg.dungeon_drop:
                    continue
                # 匹配怪物等级段
                if eq_item_cfg.required_level <= monster_level:
                    result.append(eq_item_id)
            return result

        # 从 items_config 中按稀有度筛选装备；候选池为空时按稀有度降档回退，不浪费掉率判定
        rarity_ladder = ["orange", "purple", "blue", "green", "white"]
        candidate_equips = _collect_candidates(drop_rarity)
        while not candidate_equips:
            next_idx = rarity_ladder.index(drop_rarity) + 1
            if next_idx >= len(rarity_ladder):
                break
            drop_rarity = rarity_ladder[next_idx]
            candidate_equips = _collect_candidates(drop_rarity)

        if candidate_equips:
            chosen_equip_id = rng.choice(candidate_equips)
            chosen_cfg = config.items_config["by_id"][chosen_equip_id]

            # 生成词缀
            affixes = generate_affixes(drop_rarity, rng)

            # 创建装备实例
            new_equip = ItemInstance(
                player_id=player.id,
                item_id=chosen_equip_id,
                quantity=1,
                durability=chosen_cfg.durability,
                extra_attrs={"_affixes": affixes} if affixes else {},
            )
            session.add(new_equip)

            # 展示掉落信息
            affix_count = len(affixes)
            affix_hint = f"({affix_count}条词缀)" if affix_count > 0 else "(素装)"
            equip_display = f"{chosen_cfg.get_display_name()} {affix_hint}"
            drops[f"⚔️{equip_display}"] = 1

    # ===== 铭文掉落（Phase 3，仅精英怪）=====
    if is_elite:
        from ..item.inscription_service import generate_inscription_drop

        # 确定铭文掉落率；超过最高档位（9999）时维持最高档掉率，避免高层断档
        insc_base_rate = INSCRIPTION_DROP_RATES[max(INSCRIPTION_DROP_RATES)]
        for level_cap, rate in sorted(INSCRIPTION_DROP_RATES.items()):
            if monster_level <= level_cap:
                insc_base_rate = rate
                break
        insc_final_rate = insc_base_rate * (1 + luck_prob(player.luck))

        if insc_base_rate > 0 and rng.random() < insc_final_rate:
            # 决定铭文类型：基础 or 高级
            type_roll = rng.randint(1, 100)
            if type_roll <= INSCRIPTION_TYPE_WEIGHTS["basic"]:
                # 基础铭文：从34种中选1种（排除高级铭文）
                basic_ids = [iid for iid in config.items_config["by_type"].get("INSCRIPTION", [])
                             if not getattr(config.items_config["by_id"].get(iid), 'inscription_type', None)
                             and not iid.startswith("adv_")]
                if basic_ids:
                    chosen_id = rng.choice(basic_ids)
                    drop_attrs = generate_inscription_drop(chosen_id, rng, monster_level)
                    try:
                        insc_inst = ItemInstance(
                            player_id=player.id, item_id=chosen_id, quantity=1,
                            extra_attrs=drop_attrs,
                        )
                        session.add(insc_inst)
                        insc_cfg = config.items_config["by_id"].get(chosen_id)
                        grade = drop_attrs.get("_inscription_grade", "")
                        grade_str = f"{{{grade}}}" if grade else ""
                        drops[f"📜{insc_cfg.name}{grade_str}"] = 1
                    except ValueError:
                        pass
            else:
                # 高级铭文：按稀有度权重选
                rarity_roll = rng.randint(1, 100)
                target_rarity = "orange" if rarity_roll <= ADVANCED_RARITY_WEIGHTS["orange"] else "purple"
                if target_rarity == "orange" and monster_level < ADVANCED_ORANGE_MIN_LEVEL:
                    target_rarity = "purple"

                adv_ids = [iid for iid in config.items_config["by_type"].get("INSCRIPTION", [])
                           if getattr(config.items_config["by_id"].get(iid), 'inscription_type', None) == "advanced"
                           and getattr(config.items_config["by_id"].get(iid), 'rarity', '') == target_rarity]
                if adv_ids:
                    chosen_id = rng.choice(adv_ids)
                    drop_attrs = generate_inscription_drop(chosen_id, rng, monster_level)
                    try:
                        insc_inst = ItemInstance(
                            player_id=player.id, item_id=chosen_id, quantity=1,
                            extra_attrs=drop_attrs,
                        )
                        session.add(insc_inst)
                        insc_cfg = config.items_config["by_id"].get(chosen_id)
                        grade = drop_attrs.get("_inscription_grade", "")
                        grade_str = f"{{{grade}}}" if grade else ""
                        drops[f"📜{insc_cfg.name}{grade_str}"] = 1
                    except ValueError:
                        pass

        # 铭文碎片掉落（独立于铭文判定）
        if rng.random() < FRAGMENT_DROP_RATE * (1 + luck_prob(player.luck)):
            frag_qty = 1
            try:
                await ItemInstance.add_item(session, player.id, FRAGMENT_ITEM_ID, frag_qty)
                drops[f"📜铭文碎片"] = drops.get("📜铭文碎片", 0) + frag_qty
            except ValueError:
                pass

    extra_equipment = _roll_additional_equipment(monster_level, is_elite, player.luck, rng)
    if extra_equipment:
        affixes = generate_affixes(extra_equipment.rarity, rng)
        session.add(ItemInstance(
            player_id=player.id,
            item_id=extra_equipment.item_id,
            quantity=1,
            durability=extra_equipment.durability,
            extra_attrs={"_affixes": affixes} if affixes else {},
        ))
        affix_hint = f"({len(affixes)}条词缀)" if affixes else "(素装)"
        drops[f"⚔️{extra_equipment.get_display_name()} {affix_hint}"] = 1

    if drops:
        drop_texts = [f"{name} ✖️{quantity}" for name, quantity in drops.items()]
        return f"💎 战利品：{', '.join(drop_texts)}"
    else:
        return ""

# ----------------- 工具函数 -----------------
async def get_or_create_tile(session, region: str, x: int, y: int, server_id: int = 1) -> WorldTile:
    """获取或创建今日坐标格，并在创建时生成事件"""
    today = date.today()

    # 先尝试简单查询，避免使用 with_for_update() 造成锁定
    result = await session.execute(
        select(WorldTile)
        .where(WorldTile.server_id == server_id, WorldTile.region == region, WorldTile.x == x, WorldTile.y == y)
    )
    tile = result.scalars().first()

    # 若不存在或已过期（日期变化）则重新生成
    if (not tile) or (tile.refreshed_at.date() != today):
        if not tile:
            # 创建新的tile
            tile = WorldTile(server_id=server_id, region=region, x=x, y=y)
            session.add(tile)

        # 更新tile信息
        tile.refreshed_at = datetime.now()

        # 生成事件 - 支持双层坐标系统
        tile.seed = f"{region}:{x}:{y}:{today.isoformat()}"
        rng = random.Random(_stable_tile_hash(tile.seed))

        # 获取区域配置（支持新旧两种配置格式）
        region_config = None
        tier = 1

        if region == "大都会":
            # 现实世界不生成事件
            tile.event_type = "EMPTY"
            tile.state = {}
            return tile
        elif "层诡域" in region:
            # 新的层级制诡域
            try:
                level_str = region.replace("层诡域", "")
                # 兼容"第N层诡域"格式，移除开头的"第"字
                if level_str.startswith("第"):
                    level_str = level_str[1:]
                level = int(level_str)
                # 优先从预生成配置获取，如果不存在则动态生成（支持无限层）
                region_config = config.map_config.get("dungeon_levels", {}).get(level)
                if not region_config:
                    # 动态生成超过100层的配置
                    region_config = config._generate_dungeon_level_config(
                        level, config.map_config.get("dungeon_generation_rules", {})
                    )
                tier = region_config.get("tier", level)  # 层级即为tier
            except ValueError:
                pass

        if not region_config:
            # 兼容旧的命名诡域
            region_config = config.map_config.get("regions", {}).get(region, {})
            tier = region_config.get("tier", 1)

        # 根据诡域层级调整事件权重
        tile.event_type = rng.choices(
            _TILE_EVENT_TYPES,
            weights=_event_weights_for_tier(tier),
            k=1
        )[0]
        tile.state = {}

        if tile.event_type == "EMPTY":
            # 使用获取到的region_config
            if region_config and region_config.get("monsters"):
                monster = rng.choice(region_config["monsters"])
                level_range = region_config.get("level_range", [1, 10])
                monster_level = rng.randint(level_range[0], level_range[1])

                # 选择怪物原型
                archetype = select_monster_archetype(monster_level, False, rng)
                # 使用新的诡异属性计算函数
                monster_attrs = calculate_monster_attributes(monster_level, is_elite=False, archetype=archetype, rng_instance=rng)
                display_name = get_monster_display_name(monster, archetype, False)
                tile.state = {
                    "name": display_name,
                    "base_name": monster,
                    "level": monster_level,
                    "hp": monster_attrs["hp"],
                    "attack": monster_attrs["attack"],
                    "agility": monster_attrs["agility"],
                    "defense": monster_attrs.get("defense", 0),
                    "defeated_by": []  # 记录击败过的玩家，避免原地无限刷
                }
                if archetype:
                    tile.state["archetype"] = archetype

                # 为200级以后的诡异添加特殊属性
                if monster_level >= 200:
                    tile.state.update({
                        "crit_rate": monster_attrs.get("crit_rate", 0),
                        "combo_rate": monster_attrs.get("combo_rate", 0),
                        "counter_rate": monster_attrs.get("counter_rate", 0),
                        "anti_crit_rate": monster_attrs.get("anti_crit_rate", 0),
                        "accuracy_rate": monster_attrs.get("accuracy_rate", 80)
                    })
                    if monster_attrs.get("true_damage_rate", 0) > 0:
                        tile.state["true_damage_rate"] = monster_attrs["true_damage_rate"]
            else:
                # 默认诡异配置
                tile.state = {
                    "name": "未知诡影",
                    "level": 1,
                    "hp": 20,
                    "attack": 5,
                    "agility": 1,
                    "defeated_by": []
                }
        elif tile.event_type == "TREASURE":
            tile.state = {"looted": False}
        elif tile.event_type == "MATERIAL":
            # 材料格子只掉落基础材料（白色）
            region_materials = get_region_materials(region)
            basic_materials = region_materials["basic"]

            if basic_materials:
                item_id = rng.choice(basic_materials)
            else:
                # 如果没有配置基础材料，从白色材料中随机选择
                white_materials = get_materials_by_rarity("white")
                item_id = rng.choice(white_materials) if white_materials else "grave_soil"

            tile.state = {
                "item_id": item_id,
                "quantity": rng.randint(1, 4),  # 基础材料数量稍多一些
                # 个人事件：记录已拾取玩家ID，避免相互影响
                "looted_by": [],
            }
        elif tile.event_type == "MERCHANT":
            # 卖货郎：出售稀有材料
            tile.state = {
                "visited_by": [],  # 记录已访问的玩家
                "goods": generate_merchant_goods(region, tier, rng)
            }
        elif tile.event_type == "ELITE":
            # 精英诡异：强化版诡异
            if region_config and region_config.get("monsters"):
                monster = rng.choice(region_config["monsters"])
                level_range = region_config.get("level_range", [1, 10])
                monster_level = rng.randint(level_range[0], level_range[1])

                # 选择怪物原型
                archetype = select_monster_archetype(monster_level, True, rng)
                # 使用新的诡异属性计算函数（精英版）
                monster_attrs = calculate_monster_attributes(monster_level, is_elite=True, archetype=archetype, rng_instance=rng)
                display_name = get_monster_display_name(monster, archetype, True)
                tile.state = {
                    "name": display_name,
                    "base_name": monster,
                    "level": monster_level,
                    "hp": monster_attrs["hp"],
                    "attack": monster_attrs["attack"],
                    "agility": monster_attrs["agility"],
                    "defense": monster_attrs.get("defense", 0),
                    "is_elite": True,
                    "defeated_by": []  # 记录击败过的玩家
                }
                if archetype:
                    tile.state["archetype"] = archetype

                # 为200级以后的精英诡异添加特殊属性
                if monster_level >= 200:
                    tile.state.update({
                        "crit_rate": monster_attrs.get("crit_rate", 0),
                        "combo_rate": monster_attrs.get("combo_rate", 0),
                        "counter_rate": monster_attrs.get("counter_rate", 0),
                        "anti_crit_rate": monster_attrs.get("anti_crit_rate", 0),
                        "accuracy_rate": monster_attrs.get("accuracy_rate", 80)
                    })
                    if monster_attrs.get("true_damage_rate", 0) > 0:
                        tile.state["true_damage_rate"] = monster_attrs["true_damage_rate"]
            else:
                # 默认精英怪配置
                tile.state = {
                    "name": "精英·未知诡影",
                    "level": 5,
                    "hp": 100,
                    "attack": 20,
                    "agility": 5,
                    "is_elite": True,
                    "defeated_by": []
                }

        # 使用 merge 来处理可能的并发冲突
        try:
            await session.flush()
        except Exception:
            # 如果出现冲突，重新查询最新的tile
            await session.rollback()
            result = await session.execute(
                select(WorldTile)
                .where(WorldTile.server_id == server_id, WorldTile.region == region, WorldTile.x == x, WorldTile.y == y)
            )
            tile = result.scalars().first()
            if not tile:
                # 如果还是没有，说明出现了异常情况，创建一个基本的tile
                tile = WorldTile(server_id=server_id, region=region, x=x, y=y, refreshed_at=datetime.now())
                tile.event_type = "EMPTY"
                tile.state = {}
                session.add(tile)
                await session.flush()

    return tile


async def sense_level_elites(session, level: int, server_id: int, player_id: str) -> str:
    """免费精英感知：进层时报出本重精英数量，不报位置（与付费全视之眼形成梯度）。

    已生成格子读库，未生成格子按当天种子确定性预测（与 get_or_create_tile 同一算法）。
    """
    region = f"{level}层诡域"
    today = date.today()

    # 今日已生成的格子直接读库（事件已定型）
    today_start = datetime.combine(today, datetime.min.time())
    stmt = select(WorldTile).where(
        WorldTile.server_id == server_id,
        WorldTile.region == region,
        WorldTile.refreshed_at >= today_start,
    )
    existing = {(t.x, t.y): t for t in (await session.execute(stmt)).scalars()}

    dungeon_config = config.map_config.get("dungeon_levels", {}).get(level)
    if not dungeon_config:
        dungeon_config = config._generate_dungeon_level_config(
            level, config.map_config.get("dungeon_generation_rules", {})
        )
    weights = _event_weights_for_tier(dungeon_config.get("tier", 1))

    total = 0
    defeated = 0
    for x in range(-5, 6):
        for y in range(-5, 6):
            tile = existing.get((x, y))
            if tile is not None:
                if tile.event_type == "ELITE":
                    total += 1
                    if player_id in (tile.state or {}).get("defeated_by", []):
                        defeated += 1
            else:
                seed = f"{region}:{x}:{y}:{today.isoformat()}"
                rng = random.Random(_stable_tile_hash(seed))
                if rng.choices(_TILE_EVENT_TYPES, weights=weights, k=1)[0] == "ELITE":
                    total += 1

    if total == 0:
        return "🕯️ 你凝神感知。这一重没有特别强烈的恶意——今天没有。"
    msg = f"🕯️ 你凝神感知：这一重潜伏着 {total} 股强烈的恶意"
    if defeated:
        msg += f"，其中 {defeated} 股已被你抹除"
    return msg + "。方位无从知晓。"
