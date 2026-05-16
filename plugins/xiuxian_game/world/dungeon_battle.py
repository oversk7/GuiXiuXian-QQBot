from __future__ import annotations

"""世界与坐标系统
1. 传送 <区域名> 切换区域，但坐标与现实世界相同
2. 前往 <上|下|左|右|x,y> 改变坐标（同区域内移动）
3. get_or_create_tile: 按天刷新、确定性种子生成事件
"""

from nonebot import on_command, on_regex
from nonebot.matcher import Matcher
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams
from nonebot.params import CommandArg
from typing import Tuple, Dict
from datetime import datetime, date, timedelta
import asyncio
import random
import base64
import io
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from sqlalchemy import select, func, and_
from ..models.db import safe_session, retry_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..models.world_tile import WorldTile
from ..models.monthly_card import get_player_card_benefits
from ..config import config
from ..utils import message_add_head, luck_prob
from ..utils_markdown import cmd, build_markdown
from ..platform_utils import get_unified_player
from ..item.equipment_service import recalc_equipment_attributes
from ..battle.battle_log_filter import filter_battle_log, get_player_log_mode

# Feature Flag（在文件顶部靠近其他导入的位置）
async def check_equipment_durability(session, player_id: str) -> str:
    """检查玩家装备耐久度，如果有装备耐久度低于10，返回提醒消息"""
    # 查询玩家所有已装备的装备
    result_eq = await session.execute(
        select(ItemInstance).where(
            ItemInstance.player_id == player_id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(config.items_config["by_type"]["EQUIPMENT"])
        )
    )
    equipped_items = result_eq.scalars().all()

    low_durability_items = []
    for eq in equipped_items:
        if eq.durability < 10:
            low_durability_items.append(f"{eq.config.name}(ID:{eq.id}, 耐久:{eq.durability}/{eq.config.durability})")

    if low_durability_items:
        warning_msg = "⚠️ 装备耐久度警告！以下装备耐久度过低，建议及时修理：\n"
        warning_msg += "\n".join([f"🔧 {item}" for item in low_durability_items])
        warning_msg += "\n💡 使用【修理 装备ID/名称】命令进行修理"
        return warning_msg

    return ""

# ----------------- 常量 -----------------
DIRECTIONS: Dict[str, Tuple[int, int]] = {
    "上": (0, 1),
    "下": (0, -1),
    "左": (-1, 0),
    "右": (1, 0),
}


# 诡域坐标边界 (-5,-5) 到 (5,5)
_DUNGEON_MIN = -5
_DUNGEON_MAX = 5


class BattleResult:
    """诡域战斗结果，主 handler 用以识别并把日志改用 bash 代码块包裹。"""

    __slots__ = ("log_lines", "victory", "monster_display")

    def __init__(self, log_lines: list[str], victory: bool, monster_display: str):
        self.log_lines = log_lines
        self.victory = victory
        self.monster_display = monster_display


async def _query_explored_coords(session, region: str, server_id: int = 1) -> set[tuple[int, int]]:
    """查询当前诡域 region 今天已生成的所有格子坐标（视为已探索）。"""
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    tomorrow_start = today_start + timedelta(days=1)
    stmt = select(WorldTile.x, WorldTile.y).where(
        and_(
            WorldTile.region == region,
            WorldTile.server_id == server_id,
            WorldTile.refreshed_at >= today_start,
            WorldTile.refreshed_at < tomorrow_start,
        )
    )
    rows = (await session.execute(stmt)).all()
    return {(r[0], r[1]) for r in rows}


def _build_dungeon_minimap(
    x: int,
    y: int,
    explored: set[tuple[int, int]],
    radius: int = 2,
) -> str:
    """生成以 (x,y) 为中心的诡域小地图（默认 5x5）。

    🟨 你、🟩 今日已探索、⬜ 未探索、⬛ 边界
    """
    rows = []
    # 北(y+) 在上，南(y-) 在下
    for dy in range(radius, -radius - 1, -1):
        cy = y + dy
        cells = []
        for dx in range(-radius, radius + 1):
            cx = x + dx
            if cx < _DUNGEON_MIN or cx > _DUNGEON_MAX or cy < _DUNGEON_MIN or cy > _DUNGEON_MAX:
                cells.append("⬛")
            elif cx == x and cy == y:
                cells.append("🟨")
            elif (cx, cy) in explored:
                cells.append("🟩")
            else:
                cells.append("⬜")
        rows.append("".join(cells))
    return "\n".join(rows)



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
        "special_profile": {"crit_rate": 1.0, "combo_rate": 1.0, "counter_rate": 1.0, "anti_crit_rate": 1.0, "true_damage_rate": 0, "defense_ratio": 0.0},
        "weight": {"low": 50, "mid": 30, "high": 15}, "elite_weight": 3,
    },
    "berserker": {  # 狂暴型：高暴击高攻，脆皮
        "name": "狂暴", "prefix": "狂暴·", "icon": "🔥",
        "stat_mult": {"hp": 0.7, "attack": 1.35, "agility": 1.0},
        "special_profile": {"crit_rate": 2.5, "combo_rate": 0.5, "counter_rate": 0.3, "anti_crit_rate": 0.0, "true_damage_rate": 0, "defense_ratio": 0.0},
        "weight": {"low": 10, "mid": 20, "high": 20}, "elite_weight": 15,
    },
    "tank": {  # 坚韧型：高HP高防高抗暴，低攻
        "name": "坚韧", "prefix": "坚韧·", "icon": "🛡️",
        "stat_mult": {"hp": 1.5, "attack": 0.65, "agility": 0.7},
        "special_profile": {"crit_rate": 0.0, "combo_rate": 0.0, "counter_rate": 0.8, "anti_crit_rate": 1.5, "true_damage_rate": 0, "defense_ratio": 0.35},
        "weight": {"low": 10, "mid": 15, "high": 18}, "elite_weight": 15,
    },
    "swift": {  # 迅捷型：高敏捷高连击高反击
        "name": "迅捷", "prefix": "迅捷·", "icon": "💨",
        "stat_mult": {"hp": 0.85, "attack": 0.9, "agility": 1.6},
        "special_profile": {"crit_rate": 0.5, "combo_rate": 2.5, "counter_rate": 2.0, "anti_crit_rate": 0.3, "true_damage_rate": 0, "defense_ratio": 0.0},
        "weight": {"low": 8, "mid": 18, "high": 18}, "elite_weight": 15,
    },
    "piercer": {  # 穿透型：有真伤，高攻，低HP
        "name": "穿透", "prefix": "穿透·", "icon": "🗡️",
        "stat_mult": {"hp": 0.65, "attack": 1.2, "agility": 0.9},
        "special_profile": {"crit_rate": 0.8, "combo_rate": 0.3, "counter_rate": 0.5, "anti_crit_rate": 0.3, "true_damage_rate": 15, "defense_ratio": 0.0},
        "weight": {"low": 2, "mid": 8, "high": 12}, "elite_weight": 12,
    },
    "trickster": {  # 诡诈型：高反击高抗暴
        "name": "诡诈", "prefix": "诡诈·", "icon": "🎭",
        "stat_mult": {"hp": 1.0, "attack": 0.95, "agility": 1.1},
        "special_profile": {"crit_rate": 0.6, "combo_rate": 0.4, "counter_rate": 2.5, "anti_crit_rate": 1.8, "true_damage_rate": 0, "defense_ratio": 0.1},
        "weight": {"low": 5, "mid": 10, "high": 12}, "elite_weight": 12,
    },
    "devourer": {  # 噬魂型：高暴击+真伤，稀有强力型
        "name": "噬魂", "prefix": "噬魂·", "icon": "👁️",
        "stat_mult": {"hp": 0.75, "attack": 1.3, "agility": 1.1},
        "special_profile": {"crit_rate": 2.0, "combo_rate": 1.0, "counter_rate": 0.5, "anti_crit_rate": 0.5, "true_damage_rate": 10, "defense_ratio": 0.0},
        "weight": {"low": 0, "mid": 2, "high": 5}, "elite_weight": 8,
    },
    "guardian": {  # 守卫型：极高防御和HP，极低攻击
        "name": "守卫", "prefix": "守卫·", "icon": "🏰",
        "stat_mult": {"hp": 1.8, "attack": 0.5, "agility": 0.5},
        "special_profile": {"crit_rate": 0.0, "combo_rate": 0.0, "counter_rate": 1.2, "anti_crit_rate": 2.0, "true_damage_rate": 0, "defense_ratio": 0.5},
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
        else:
            # 1000级以后：超高特殊属性（200层以后）
            high_level_factor = (monster_level - 1000) / 100
            crit_rate = min(25, 5 + high_level_factor * 2)
            combo_rate = min(15, 3 + high_level_factor * 1.5)
            counter_rate = min(30, 8 + high_level_factor * 2)
            anti_crit_rate = min(80, 50 + high_level_factor * 5)

        if archetype and archetype in MONSTER_ARCHETYPES:
            # ---- 原型系统：应用原型倍率 ----
            arch = MONSTER_ARCHETYPES[archetype]
            profile = arch["special_profile"]

            # 三维属性应用原型倍率
            hp = int(hp * arch["stat_mult"]["hp"])
            attack = int(attack * arch["stat_mult"]["attack"])
            agility = int(agility * arch["stat_mult"]["agility"])

            # 特殊属性应用原型倍率
            crit_rate *= profile["crit_rate"]
            combo_rate *= profile["combo_rate"]
            counter_rate *= profile["counter_rate"]
            anti_crit_rate *= profile["anti_crit_rate"]

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

            # 应用特殊属性上限
            cap_idx = 1 if is_elite else 0
            crit_rate = min(crit_rate, MONSTER_SPECIAL_CAPS["crit_rate"][cap_idx])
            combo_rate = min(combo_rate, MONSTER_SPECIAL_CAPS["combo_rate"][cap_idx])
            counter_rate = min(counter_rate, MONSTER_SPECIAL_CAPS["counter_rate"][cap_idx])
            anti_crit_rate = min(anti_crit_rate, MONSTER_SPECIAL_CAPS["anti_crit_rate"][cap_idx])
            true_damage_rate = min(true_damage_rate, MONSTER_SPECIAL_CAPS["true_damage_rate"][cap_idx])
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

        special_attributes = {
            "crit_rate": round(crit_rate, 1),
            "combo_rate": round(combo_rate, 1),
            "counter_rate": round(counter_rate, 1),
            "anti_crit_rate": round(anti_crit_rate, 1),
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
            if tier <= 2:
                rarities = ["green"]
            elif tier <= 4:
                rarities = ["green", "blue"]
            else:
                rarities = ["blue", "purple", "orange"]

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
                   config.items_config["by_id"][item_id].rarity == "white"]
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
            candidate_materials = []

            # 诡异掉落优先从商人材料中选择（更有价值）
            if rarity != "white":  # 白色材料从基础材料中选择
                for material_id in region_materials["merchant"]:
                    item_config = config.items_config["by_id"].get(material_id)
                    if item_config and item_config.rarity == rarity:
                        candidate_materials.append(material_id)

            # 如果没有找到，从全局材料中选择
            if not candidate_materials:
                if rarity == "white":
                    # 白色材料从基础材料中选择
                    candidate_materials = region_materials["basic"]
                else:
                    candidate_materials = get_materials_by_rarity(rarity)

                    # 特殊处理：200层以后的诡异，橙色材料掉落时确保包含世界碎片
                    if rarity == "orange" and monster_level > 200:
                        # 确保世界碎片在候选列表中（如果不在的话添加）
                        if "world_fragment" not in candidate_materials:
                            candidate_materials.append("world_fragment")

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

    # 装备掉落率配置（按怪物等级匹配装备品阶，精英怪是核心装备来源）
    if is_elite:
        if monster_level > 200:
            equip_drop_rate = 0.09   # 200+精英 9%
            equip_rarities = ["blue", "purple", "purple", "orange"]  # 紫色权重高
        elif monster_level > 100:
            equip_drop_rate = 0.08   # 101-200精英 8%
            equip_rarities = ["green", "blue", "blue", "purple"]     # 蓝色权重高
        elif monster_level > 60:
            equip_drop_rate = 0.07   # 61-100精英 7%
            equip_rarities = ["green", "blue"]
        else:
            equip_drop_rate = 0.06   # ≤60精英 6%
            equip_rarities = ["green"]
    elif monster_level > 200:
        equip_drop_rate = 0.025  # 200+普通怪 2.5%
        equip_rarities = ["green", "blue"]
    elif monster_level > 100:
        equip_drop_rate = 0.02   # 101-200普通怪 2%
        equip_rarities = ["white", "green", "blue"]
    elif monster_level > 60:
        equip_drop_rate = 0.015  # 61-100普通怪 1.5%
        equip_rarities = ["white", "green"]
    else:
        equip_drop_rate = 0.01   # ≤60普通怪 1%
        equip_rarities = ["white"]

    # 幸运值加成
    equip_drop_rate *= (1 + luck_prob(player.luck))

    if rng.random() < equip_drop_rate:
        # 选择掉落装备的稀有度
        drop_rarity = rng.choice(equip_rarities)

        # 从 items_config 中按稀有度筛选装备
        candidate_equips = []
        for eq_item_id in config.items_config["by_type"].get("EQUIPMENT", []):
            eq_item_cfg = config.items_config["by_id"].get(eq_item_id)
            if not eq_item_cfg:
                continue
            if eq_item_cfg.rarity != drop_rarity:
                continue
            if eq_item_id in VIP_EQUIPMENT_IDS:
                continue
            # 匹配怪物等级段
            if eq_item_cfg.required_level <= monster_level:
                candidate_equips.append(eq_item_id)

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

        # 确定铭文掉落率
        insc_base_rate = 0.0
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
        rng = random.Random(hash(tile.seed))

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
        if tier <= 2:
            # 低级诡域：基础事件为主
            event_weights = [15, 5, 70, 5, 2, 3]  # MATERIAL, TREASURE, EMPTY, REST, MERCHANT, ELITE
        elif tier <= 4:
            # 中级诡域：增加商人和精英怪
            event_weights = [12, 5, 70, 7, 2, 4]
        else:
            # 高级诡域：更多特殊事件
            event_weights = [10, 5, 70, 5, 4, 6]

        tile.event_type = rng.choices(
            ["MATERIAL", "TREASURE", "EMPTY", "REST", "MERCHANT", "ELITE"],
            weights=event_weights,
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
                        "anti_crit_rate": monster_attrs.get("anti_crit_rate", 0)
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
                        "anti_crit_rate": monster_attrs.get("anti_crit_rate", 0)
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


# ----------------- 指令：移动 -----------------
move_cmd = on_regex(r"^\s*(上|下|左|右)\s*$", block=True, priority=5)

@move_cmd.handle()
async def _(event: MessageEvent):
    direction = event.get_plaintext().strip()
    user_id = event.get_user_id()

    async with retry_session() as session:
        player: Player | None = await get_unified_player(session, event)
        if not player:
            await move_cmd.finish("⛔ 请先创建角色")

        if not player.is_in_dungeon():
            await move_cmd.finish("⛔ 单格移动只能在诡域使用\n⬇️ 【导航 <x> <y>】在现实世界移动")

        # 解析方向
        if direction not in DIRECTIONS:
            await move_cmd.finish("⛔ 无效的方向")
        dx, dy = DIRECTIONS[direction]

        # 使用新的移动系统（自动处理坐标限制）
        old_x, old_y = player.dungeon_x, player.dungeon_y
        player.move_in_current_world(dx, dy)
        new_x, new_y = player.dungeon_x, player.dungeon_y

        # 检查是否真的移动了（可能被边界限制）
        if old_x == new_x and old_y == new_y:
            await move_cmd.finish(f"⛔ 无法向{direction}移动，已到达诡域边界\n📍 当前坐标范围：(-5,-5) 到 (5,5)")

        # 根据诡域层级获取配置并扣除理智
        dungeon_config = config.map_config.get("dungeon_levels", {}).get(player.dungeon_level)
        if not dungeon_config:
            # 动态生成超过100层的配置
            dungeon_config = config._generate_dungeon_level_config(
                player.dungeon_level, config.map_config.get("dungeon_generation_rules", {})
            )
        mp_cost = dungeon_config.get("mp_cost", 1)  # 默认消耗1点理智

        if player.mp < mp_cost:
            # 移动失败，恢复原坐标
            player.dungeon_x, player.dungeon_y = old_x, old_y
            player.x, player.y = old_x, old_y
            await move_cmd.finish(f"⛔ 理智不足以在此诡域移动，需要 {mp_cost} 点理智，当前 {player.mp}")

        player.mp = max(0, player.mp - mp_cost)
        if player.mp == 0 and player.hp > 0:
            player.hp = 0  # 理智耗尽即"疯狂身亡"

        # 获取当前位置事件格
        tile = await get_or_create_tile(session, player.get_current_region(), new_x, new_y, player.server_id)

        # 清除全视之眼预览标记（玩家已实际到达此格子）
        if (tile.state or {}).get("preview"):
            state = tile.state or {}
            state.pop("preview", None)
            tile.state = state

        # 检查月卡权限是否支持自动采集
        benefits = await get_player_card_benefits(session, player.id)
        auto_collect = benefits.get("auto_collect", False)

        auto_collect_msg = ""

        # 如果有月卡自动采集权限，自动触发收集
        if auto_collect:
            if tile.event_type == "MATERIAL":
                # 自动采集材料
                if player.id not in tile.state.get("looted_by", []) and not tile.state.get("looted"):
                    collect_result = await _handle_material(session, tile, player)
                    auto_collect_msg = f"\n💳 月卡自动采集：\n{collect_result}"
            elif tile.event_type == "TREASURE":
                # 自动收集宝藏
                if not tile.state.get("looted"):
                    collect_result = await _handle_treasure(session, tile, player)
                    auto_collect_msg = f"\n💳 月卡自动收集：\n{collect_result}"

        session.add_all([player, tile])
        await session.commit()  # 提交数据库事务

        # 构造事件描述
        def describe_tile(t: WorldTile) -> str:
            """根据 tile 类型生成可读描述，在移动后提示玩家下一步操作。"""
            if t.event_type == "MATERIAL":
                item_cfg = config.items_config["by_id"].get(t.state.get("item_id"))
                item_name = item_cfg.get_display_name() if item_cfg else "未知材料"
                qty = t.state.get("quantity", "?")
                looted_by = t.state.get("looted_by", [])
                if player.id in looted_by or t.state.get("looted"):
                    return f"🪨 这里曾经散落着 {item_name} ✖️{qty}，但已被搜刮一空。"
                return f"✨ 你发现了材料 {item_name} ✖️{qty}，可输入 【收集】 获取。"
            elif t.event_type == "TREASURE":
                if t.state.get("looted"):
                    return "🪨 破碎的宝箱静静躺在尘埃中，没有任何价值。"
                return "🎁 你注意到一个尘封宝箱，输入 【探索】 能打开它。"
            elif t.event_type == "EMPTY":
                if player.id in t.state.get("defeated_by", []):
                    return "🪨 这里只剩下诡异的残骸，散发着淡淡的血腥味。"
                monster = t.state.get("name")
                monster_level = t.state.get("level", 1)

                # 为200级以后的诡异显示特殊属性提示
                special_info = ""
                if monster_level >= 200:
                    special_attrs = []
                    if t.state.get("crit_rate", 0) > 0:
                        special_attrs.append(f"💥暴击{t.state['crit_rate']:.1f}%")
                    if t.state.get("combo_rate", 0) > 0:
                        special_attrs.append(f"🔄连击{t.state['combo_rate']:.1f}%")
                    if t.state.get("counter_rate", 0) > 0:
                        special_attrs.append(f"⚡反击{t.state['counter_rate']:.1f}%")
                    if t.state.get("anti_crit_rate", 0) > 0:
                        special_attrs.append(f"🛡️抗暴{t.state['anti_crit_rate']:.1f}%")
                    if t.state.get("defense", 0) > 0:
                        special_attrs.append(f"🪨防{t.state['defense']}")
                    if t.state.get("true_damage_rate", 0) > 0:
                        special_attrs.append(f"🗡️真伤{t.state['true_damage_rate']:.1f}%")

                    if special_attrs:
                        special_info = f"\n🔥 特殊能力：{' '.join(special_attrs)}"

                return f"🌫️ 空间扭曲中传来异响，似乎有 {monster}(Lv{monster_level}) 在此游荡。{special_info}\n若想挑战，可输入 【探索】 进行调查。"
            elif t.event_type == "REST":
                return "🌫️ 你发现了一家驿站，可输入 【探索】 恢复生命。"
            elif t.event_type == "MERCHANT":
                if player.id in t.state.get("visited_by", []):
                    return "🏪 卖货郎已经离开了，只留下空荡荡的摊位。"
                return "🏪 你遇到了神秘卖货郎，输入 【探索】 查看他的商品。"
            elif t.event_type == "ELITE":
                if player.id in t.state.get("defeated_by", []):
                    return "⚰️ 精英诡异的残骸散落一地，散发着不祥的气息。"
                monster_name = t.state.get("name", "精英诡异")
                monster_level = t.state.get("level", 1)

                # 为200级以后的精英诡异显示特殊属性提示
                special_info = ""
                if monster_level >= 200:
                    special_attrs = []
                    if t.state.get("crit_rate", 0) > 0:
                        special_attrs.append(f"💥暴击{t.state['crit_rate']:.1f}%")
                    if t.state.get("combo_rate", 0) > 0:
                        special_attrs.append(f"🔄连击{t.state['combo_rate']:.1f}%")
                    if t.state.get("counter_rate", 0) > 0:
                        special_attrs.append(f"⚡反击{t.state['counter_rate']:.1f}%")
                    if t.state.get("anti_crit_rate", 0) > 0:
                        special_attrs.append(f"🛡️抗暴{t.state['anti_crit_rate']:.1f}%")
                    if t.state.get("defense", 0) > 0:
                        special_attrs.append(f"🪨防{t.state['defense']}")
                    if t.state.get("true_damage_rate", 0) > 0:
                        special_attrs.append(f"🗡️真伤{t.state['true_damage_rate']:.1f}%")

                    if special_attrs:
                        special_info = f"\n🔥 特殊能力：{' '.join(special_attrs)}"

                return f"⚔️ 空间深处传来恶意的窥视，{monster_name}(Lv{monster_level}) 作为这重诡域的诡异存在正盯着你！{special_info}\n输入 【探索】 迎战。"
            return "⁉️ 未知事件。"

        event_desc = describe_tile(tile)

        # 获取含buff/宠物的有效属性，保持与面板一致
        effective_attrs = await player.get_effective_attributes(session)
        eff_max_hp = effective_attrs.get("max_hp", player.max_hp)
        eff_max_mp = effective_attrs.get("max_mp", player.max_mp)

        status_line = (
            f"🧭 **{player.get_current_region()}** ({new_x},{new_y})　"
            f"❤️ **{player.hp}**/{eff_max_hp}　"
            f"🧠 **{player.mp}**/{eff_max_mp}"
        )

        lines = [
            "# 🚶 诡域移动",
            status_line,
            "***",
            event_desc,
        ]
        if auto_collect_msg:
            lines.append(auto_collect_msg)
        lines += [
            "***",
            f"{cmd('↑上', '上')} | {cmd('↓下', '下')} | {cmd('←左', '左')} | {cmd('→右', '右')} | {cmd('🗡️探索', '探索')}",
            f"{cmd('上一层')} | {cmd('下一层')} | {cmd('一键嗑药')} | {cmd('俯瞰')}",
        ]

        await move_cmd.finish(build_markdown("\n".join(lines)))

# ----------------- 指令：战斗 -----------------
explore_cmd = on_command("探索", aliases={"战斗", "收集"}, block=True, priority=5)

# 事件处理器映射
async def _handle_material(session, tile: WorldTile, player: Player) -> str:
    # 个人事件：仅当当前玩家已拾取时才视为已搜刮
    if player.id in tile.state.get("looted_by", []) or tile.state.get("looted"):
        return "🪨 这的材料已经被拿了，起码在你的视角是这样。"

    # 获取物品配置
    item_id = tile.state.get("item_id")
    item_cfg = config.items_config["by_id"].get(item_id)
    if not item_cfg:
        return "⚠️ 错误：未知的物品。"

    quantity = tile.state.get("quantity", 1)

    # Luck: 采集加成判定
    luck_bonus = 0
    if random.random() < luck_prob(player.luck):
        luck_bonus = quantity  # 翻倍
        quantity *= 2

    # 更新或创建物品记录
    try:
        await ItemInstance.add_item(session, player.id, item_id, quantity)
    except ValueError as e:
        return f"⚠️ 错误：{e}"

    # 标记为已拾取（个人事件）
    tile.state.setdefault("looted_by", []).append(player.id)
    session.add(tile)
    await session.flush()

    base_msg = f"✨ 你采集到了 {item_cfg.get_display_name()} ✖️{quantity}!"
    if luck_bonus:
        base_msg += "\n🍀 幸运闪现！材料翻倍。"
    base_msg += "\n⬇️ 【图鉴 物品名】 查看描述"
    return base_msg


async def _handle_treasure(session, tile: WorldTile, player: Player) -> str:
    if tile.state.get("looted"):
        return "🪨 雕塑的暗格已被掏空，徒留潮湿指印。"
    # 添加时间戳确保每次开启宝箱都有不同的奖励
    import time
    treasure_timestamp = int(time.time() * 1000)
    rng = random.Random(hash(f"{tile.seed}:{player.id}:{treasure_timestamp}"))
    base_gold = rng.randint(2000, 8000)
    from ..utils import luck_prob
    multiplier = 1 + luck_prob(player.luck)  # 1~2 倍区间
    gold_gain = int(base_gold * multiplier)
    player.gold += gold_gain
    # 更新财富成就统计
    from ..achievement.achievement_service import AchievementService
    await AchievementService.update_stat(session, player.id, "gold_earned_total", increment=gold_gain, auto_commit=False)
    tile.state["looted"] = True
    session.add_all([player, tile])
    await session.flush()
    msg = f"🔑 你在龟裂神像内抠出 {base_gold}💰！"
    if multiplier > 1.01:
        msg += f"\n🍀幸运改写中...金币变为{gold_gain}！"
    # 极低概率掉落稀有诡兽（0.5%，鼓励手动探索）
    if rng.random() < 0.005:
        beast_id = rng.choice(["guardian_void_serpent", "guardian_nightmare_wolf"])
        try:
            await ItemInstance.add_item(session, player.id, beast_id, 1)
            beast_cfg = config.items_config["by_id"].get(beast_id)
            if beast_cfg:
                msg += f"\n\n🎊 奇迹降临！宝箱深处竟藏着一只【{beast_cfg.name}】！"
                msg += f"\n✨ {beast_cfg.description}"
                msg += f"\n⚠️ 此诡兽极为罕见，请妥善保管！"
        except ValueError:
            pass
    # 低概率掉落诡兽精魄（0.5%，与稀有诡兽相同概率）
    if rng.random() < 0.005:
        try:
            await ItemInstance.add_item(session, player.id, "pet_evolution_stone", 1)
            msg += "\n\n✨ 宝箱角落闪烁着幽光...你获得了【诡兽精魄】×1！"
        except ValueError:
            pass
    return msg


async def _handle_empty(session, tile: WorldTile, player: Player):
    # 检查玩家是否已经击败过这个小怪
    if player.id in tile.state.get("defeated_by", []):
        return "🪨 这里只剩下诡异的残骸，散发着淡淡的血腥味。"
    # empty格有遇到个人的诡异，但不会影响公共事件
    return await _handle_personal_monster(session, tile, player)


async def _handle_personal_monster(session, tile: WorldTile, player: Player) -> "BattleResult":
    """诡异属于个人事件，使用新战斗系统进行战斗。"""
    # 获取诡异信息
    monster_stats = {
        "hp": tile.state.get("hp", 0),
        "attack": tile.state.get("attack", 0),
        "agility": tile.state.get("agility", 0),
        "defense": tile.state.get("defense", 0),
    }

    # 为200级以后的诡异添加特殊属性
    monster_level = tile.state.get("level", 1)
    if monster_level >= 200:
        monster_stats.update({
            "crit_rate": tile.state.get("crit_rate", 0),
            "combo_rate": tile.state.get("combo_rate", 0),
            "counter_rate": tile.state.get("counter_rate", 0),
            "anti_crit_rate": tile.state.get("anti_crit_rate", 0),
            "true_damage_rate": tile.state.get("true_damage_rate", 0),
        })

    monster_name = tile.state.get("name", "未知诡影")
    monster_base_display = f"{monster_name}(Lv{monster_level})"
    monster_full_display = monster_base_display

    # 为200级以后的诡异显示特殊属性信息
    if monster_level >= 200:
        special_attrs = []
        if monster_stats.get("crit_rate", 0) > 0:
            special_attrs.append(f"💥{monster_stats['crit_rate']:.1f}%")
        if monster_stats.get("combo_rate", 0) > 0:
            special_attrs.append(f"🔄{monster_stats['combo_rate']:.1f}%")
        if monster_stats.get("counter_rate", 0) > 0:
            special_attrs.append(f"⚡{monster_stats['counter_rate']:.1f}%")
        if monster_stats.get("anti_crit_rate", 0) > 0:
            special_attrs.append(f"🛡️{monster_stats['anti_crit_rate']:.1f}%")
        if monster_stats.get("defense", 0) > 0:
            special_attrs.append(f"🪨防{monster_stats['defense']}")
        if monster_stats.get("true_damage_rate", 0) > 0:
            special_attrs.append(f"🗡️真伤{monster_stats['true_damage_rate']:.1f}%")

        if special_attrs:
            monster_full_display += f" [{' '.join(special_attrs)}]"

    # 使用新战斗系统
    from ..battle.integration_helper import BattleIntegrationHelper

    # 创建战斗种子 - 添加时间戳确保每次战斗都有不同的随机序列
    import time
    battle_timestamp = int(time.time() * 1000)  # 毫秒级时间戳
    seed = f"P_{tile.seed}:{player.id}:{battle_timestamp}"

    # 执行增强战斗V2 - 支持装备特殊效果
    victory, battle_log, damage_taken, post_effects = await BattleIntegrationHelper.enhanced_player_vs_monster_battle_v2(
        player, monster_stats, monster_base_display, session, seed=seed, max_rounds=100,
        monster_full_display=monster_full_display
    )

    # 更新玩家血量
    player.hp = max(0, player.hp - damage_taken)

    # 根据玩家偏好过滤战斗日志，再添加额外信息
    dungeon_log_mode = get_player_log_mode(player)
    battle_summary = filter_battle_log(battle_log, dungeon_log_mode)

    # 处理战斗结果
    if victory:
        # 胜利处理 - 使用新的时间戳确保每次掉落都不同
        import random
        drop_timestamp = int(time.time() * 1000)  # 毫秒级时间戳
        rng = random.Random(hash(f"P_{tile.seed}:{player.id}:{drop_timestamp}"))
        exp_gain = rng.randint(1, 4) * monster_level
        player.exp += exp_gain
        battle_summary.append(f"🎉 你击杀了 {monster_full_display}，获得 {exp_gain} EXP")

        # 诡异掉落材料机制
        is_elite = tile.state.get("is_elite", False)
        drop_result = await handle_monster_drops(
            session, player, monster_level, player.region, rng, is_elite
        )
        if drop_result:
            battle_summary.append(drop_result)

        # 更新战斗胜利统计（用于公会任务）
        if player.guild_id:
            from ..guild.guild_task_service_new import GuildTaskService as GuildTaskServiceNew
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.guild_repository import GuildRepository
            from ..infrastructure.repositories.player_task_stats_repository import PlayerTaskStatsRepository
            from ..infrastructure.repositories.guild_task_record_repository import GuildTaskRecordRepository
            from ..infrastructure.repositories.player_donation_log_repository import PlayerDonationLogRepository
            from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository

            task_service = GuildTaskServiceNew(
                player_repo=PlayerRepository(session),
                guild_repo=GuildRepository(session),
                player_task_stats_repo=PlayerTaskStatsRepository(session),
                guild_task_record_repo=GuildTaskRecordRepository(session),
                player_donation_log_repo=PlayerDonationLogRepository(session),
                guild_building_repo=GuildBuildingRepository(session),
            )
            await task_service.update_combat_victory_stats(player.id)

        # 更新成就统计（诡域战斗胜利）
        from ..achievement.achievement_service import AchievementService
        await AchievementService.update_stat(session, player.id, "total_battles", auto_commit=False)
        await AchievementService.update_stat(session, player.id, "total_wins", auto_commit=False)
        await AchievementService.update_stat(session, player.id, "total_kills", auto_commit=False)

        # 检查并解锁成就
        achievement_msgs = await AchievementService.check_achievements(session, player)
        if achievement_msgs:
            battle_summary.extend([""] + achievement_msgs)

        # 慧海心元珠「胜负归元」：击杀永久+30理智上限（每日8次）—— 不依赖 post_effects
        from ..item.vip_huihai_xinyuan_skill import apply_kill_max_mp
        _hh_msg = await apply_kill_max_mp(session, player)
        if _hh_msg:
            battle_summary.append(_hh_msg)
            await session.commit()

        # 结算"斩龙闪"的战后效果，保持与战斗日志一致（修复 Bug3/1）
        try:
            if post_effects:
                from sqlalchemy import select as _select
                from ..models.inventory import ItemInstance as _ItemInstance
                from ..models.vip_equipment_bonus import VIPEquipmentBonus as _VIPBonus
                from datetime import datetime as _dt

                def _today_key() -> str:
                    return _dt.now().strftime("%Y%m%d")

                # 找到已穿戴的斩龙闪
                stmt = _select(_ItemInstance).where(
                    _ItemInstance.player_id == player.id,
                    _ItemInstance.equipped == True,
                    _ItemInstance.item_id == "vip_blade_zhanlongshan",
                )
                inst = (await session.execute(stmt)).scalars().first()
                if inst:
                    extra = dict(inst.extra_attrs or {})
                    vip_bonus = await _VIPBonus.get_or_create(session, player.id)
                    day = _today_key()

                    cn_map = {
                        "attack": "攻击",
                        "defense": "防御",
                        "agility": "敏捷",
                        "luck": "幸运",
                        "max_hp": "生命上限",
                        "max_mp": "理智上限",
                    }

                    for eff in post_effects:
                        et = eff.get("type")
                        if et == "gain_random_attr":
                            if extra.get("blade_rand_day") != day:
                                attr = eff.get("attr")
                                val = int(eff.get("value", 0) or 0)
                                # 持久化并立即生效
                                vip_bonus.add_bonus(attr, val)
                                setattr(player, attr, getattr(player, attr) + val)
                                extra["blade_rand_day"] = day
                                battle_summary.append(f"✨ 刃之魔灵：今日首战恩赐，{cn_map.get(attr, attr)}+{val}（永久）")
                        elif et == "gain_max_hp":
                            # 击杀永久+2属性点（每日最多20次），1属性点=3生命值，所以实际+6生命值
                            if extra.get("blade_kill_day") != day:
                                extra["blade_kill_day"] = day
                                extra["blade_kill_cnt"] = 0
                            cnt = int(extra.get("blade_kill_cnt", 0))
                            if cnt < 20:
                                attr_points = int(eff.get("value", 0) or 0)  # 属性点数
                                actual_hp = attr_points * 3  # 1属性点=3生命值
                                vip_bonus.add_bonus("max_hp", actual_hp)
                                player.max_hp = player.max_hp + actual_hp
                                extra["blade_kill_cnt"] = cnt + 1
                                battle_summary.append(
                                    f"🩸 噬灵者：击杀吞噬，生命上限+{actual_hp}（今日{extra['blade_kill_cnt']}/20）"
                                )

                    inst.extra_attrs = extra
                    session.add(inst)
                    session.add(player)
                    await session.commit()

                # 归雨「夺伞步」：击杀永久+2敏捷（每日20次）
                gui_yu_effects = [e for e in post_effects if e.get("type") == "gain_agility"]
                if gui_yu_effects:
                    stmt_gy = _select(_ItemInstance).where(
                        _ItemInstance.player_id == player.id,
                        _ItemInstance.equipped == True,
                        _ItemInstance.item_id == "vip_gui_yu",
                    )
                    gy_inst = (await session.execute(stmt_gy)).scalars().first()
                    if gy_inst:
                        gy_extra = dict(gy_inst.extra_attrs or {})
                        gy_day = _today_key()
                        if gy_extra.get("gy_kill_day") != gy_day:
                            gy_extra["gy_kill_day"] = gy_day
                            gy_extra["gy_kill_cnt"] = 0
                        gy_cnt = int(gy_extra.get("gy_kill_cnt", 0))
                        gy_bonus = await _VIPBonus.get_or_create(session, player.id)
                        total_agility = gy_bonus.get_total_bonus().get("agility", 0)
                        for eff_gy in gui_yu_effects:
                            if gy_cnt >= 20:
                                battle_summary.append(f"👣 夺伞步：今日已达上限（+40/40）")
                                break
                            val = int(eff_gy.get("value", 2) or 2)
                            gy_bonus.add_bonus("agility", val)
                            player.agility = player.agility + val
                            gy_cnt += 1
                            total_agility += val
                            gy_extra["gy_kill_cnt"] = gy_cnt
                            battle_summary.append(
                                f"👣 夺伞步：脚步更轻，敏捷+{val}（今日+{gy_cnt * 2}/40）"
                            )
                        gy_inst.extra_attrs = gy_extra
                        session.add(gy_inst)
                        session.add(player)
                        await session.commit()

                # 折光年「时间掠夺」+「终焉铭刻」：击杀永久+2体质/+2攻击（每日各20次）
                # 区分折光年(终焉铭刻)和诡面骰(骰相·噬)的gain_attack
                chrono_effects = [e for e in post_effects if e.get("type") in ("gain_max_hp",) or
                                  (e.get("type") == "gain_attack" and "骰相" not in e.get("description", ""))]
                if chrono_effects:
                    stmt_cw = _select(_ItemInstance).where(
                        _ItemInstance.player_id == player.id,
                        _ItemInstance.equipped == True,
                        _ItemInstance.item_id == "vip_chrono_watch",
                    )
                    cw_inst = (await session.execute(stmt_cw)).scalars().first()
                    if cw_inst:
                        cw_extra = dict(cw_inst.extra_attrs or {})
                        cw_day = _today_key()
                        cw_bonus = await _VIPBonus.get_or_create(session, player.id)

                        # 时间掠夺（gain_max_hp）：每日20次，每次+2体质(+6生命值)
                        if cw_extra.get("cw_hp_day") != cw_day:
                            cw_extra["cw_hp_day"] = cw_day
                            cw_extra["cw_hp_cnt"] = 0
                        cw_hp_cnt = int(cw_extra.get("cw_hp_cnt", 0))

                        # 终焉铭刻（gain_attack）：每日20次，每次+2攻击
                        if cw_extra.get("cw_atk_day") != cw_day:
                            cw_extra["cw_atk_day"] = cw_day
                            cw_extra["cw_atk_cnt"] = 0
                        cw_atk_cnt = int(cw_extra.get("cw_atk_cnt", 0))

                        for eff_cw in chrono_effects:
                            cw_type = eff_cw.get("type")
                            val = int(eff_cw.get("value", 2) or 2)

                            if cw_type == "gain_max_hp" and cw_hp_cnt < 20:
                                actual_hp = val * 3  # 1属性点=3生命值
                                cw_bonus.add_bonus("max_hp", actual_hp)
                                player.max_hp = player.max_hp + actual_hp
                                cw_hp_cnt += 1
                                cw_extra["cw_hp_cnt"] = cw_hp_cnt
                                battle_summary.append(
                                    f"⏱️ 时间掠夺：夺取寿命，生命上限+{actual_hp}（今日{cw_hp_cnt}/20）"
                                )
                            elif cw_type == "gain_max_hp" and cw_hp_cnt >= 20:
                                battle_summary.append("⏱️ 时间掠夺：今日已达上限（+120/120）")

                            elif cw_type == "gain_attack" and cw_atk_cnt < 20:
                                cw_bonus.add_bonus("attack", val)
                                player.attack = player.attack + val
                                cw_atk_cnt += 1
                                cw_extra["cw_atk_cnt"] = cw_atk_cnt
                                battle_summary.append(
                                    f"⏱️ 终焉铭刻：铭刻终结，攻击力+{val}（今日{cw_atk_cnt}/20）"
                                )
                            elif cw_type == "gain_attack" and cw_atk_cnt >= 20:
                                battle_summary.append("⏱️ 终焉铭刻：今日已达上限（+40/40）")

                        cw_inst.extra_attrs = cw_extra
                        session.add(cw_inst)
                        session.add(player)
                        await session.commit()

                # 诡面骰「骰相·噬」：击杀永久+2攻击（每日20次，独立计数）
                dice_atk_effects = [e for e in post_effects if e.get("type") == "gain_attack" and "骰相" in e.get("description", "")]
                if dice_atk_effects:
                    stmt_dice = _select(_ItemInstance).where(
                        _ItemInstance.player_id == player.id,
                        _ItemInstance.equipped == True,
                        _ItemInstance.item_id == "vip_ghost_dice",
                    )
                    dice_inst = (await session.execute(stmt_dice)).scalars().first()
                    if dice_inst:
                        dice_extra = dict(dice_inst.extra_attrs or {})
                        dice_day = _today_key()
                        dice_bonus = await _VIPBonus.get_or_create(session, player.id)

                        if dice_extra.get("dice_atk_day") != dice_day:
                            dice_extra["dice_atk_day"] = dice_day
                            dice_extra["dice_atk_cnt"] = 0
                        dice_atk_cnt = int(dice_extra.get("dice_atk_cnt", 0))

                        for eff_dice in dice_atk_effects:
                            val = int(eff_dice.get("value", 2) or 2)
                            if dice_atk_cnt < 20:
                                dice_bonus.add_bonus("attack", val)
                                player.attack = player.attack + val
                                dice_atk_cnt += 1
                                dice_extra["dice_atk_cnt"] = dice_atk_cnt
                                battle_summary.append(
                                    f"🎲 骰相·噬：骰纹加深，攻击力+{val}（今日{dice_atk_cnt}/20）"
                                )
                            else:
                                battle_summary.append("🎲 骰相·噬：今日已达上限（+40/40）")

                        dice_inst.extra_attrs = dice_extra
                        session.add(dice_inst)
                        session.add(player)
                        await session.commit()
        except Exception:
            # 不影响战斗主流程
            pass

        # 标记为已击败（玩家胜利后）
        tile.state.setdefault("defeated_by", []).append(player.id)

        # 爬塔系统：击败诡异后解锁下一层
        if player.is_in_dungeon():
            old_max_level = player.max_dungeon_level or 0
            player.unlock_next_dungeon_level()
            new_max_level = player.max_dungeon_level or 0

            # 如果解锁了新的诡域，给予提示
            if new_max_level > old_max_level:
                battle_summary.append(f"🎉 恭喜！解锁了第{new_max_level + 1}重诡域")
                battle_summary.append(f"🔓 现在可以探索更深层的诡域了！")

                # 检查是否可以领取深渊探索者宝箱
                if new_max_level % 10 == 0:
                    from ..models.dungeon_chest_record import DungeonChestRecord

                    stmt = select(DungeonChestRecord).where(
                        DungeonChestRecord.player_id == player.id,
                        DungeonChestRecord.dungeon_level == new_max_level
                    )
                    existing_record = (await session.execute(stmt)).scalar_one_or_none()

                    if not existing_record:
                        battle_summary.append("***")
                        battle_summary.append("🎁 恭喜！你可以领取深渊探索者宝箱了！")
                        battle_summary.append(f"💎 {cmd('领取宝箱')} 一键领取所有可领取的宝箱")

    else:
        # PVE失败（玩家死亡）：应用镜怨自噬与每日随机属性
        from sqlalchemy import select as _select
        from datetime import datetime as _dt
        from ..models.inventory import ItemInstance as _ItemInstance
        from ..models.vip_equipment_bonus import VIPEquipmentBonus as _VIPBonus
        def _today_key() -> str:
            return _dt.now().strftime("%Y%m%d")
        async def _apply_blade_daily_random_on_death(_player):
            stmt = _select(_ItemInstance).where(
                _ItemInstance.player_id == _player.id,
                _ItemInstance.equipped == True,
                _ItemInstance.item_id == "vip_blade_zhanlongshan"
            )
            inst = (await session.execute(stmt)).scalars().first()
            if not inst:
                return None
            extra = inst.extra_attrs or {}
            day = _today_key()
            if extra.get("blade_rand_day") == day:
                return None
            import random as _r
            attr_map = {
                "attack": "攻击", "defense": "防御", "agility": "敏捷",
                "luck": "幸运", "max_hp": "生命上限", "max_mp": "理智上限"
            }
            attrs = list(attr_map.keys())
            chosen = _r.choice(attrs)
            # 使用VIPEquipmentBonus表持久化，确保冥返后不会丢失
            vip_bonus = await _VIPBonus.get_or_create(session, _player.id)
            vip_bonus.add_bonus(chosen, 40)
            setattr(_player, chosen, getattr(_player, chosen) + 40)
            extra["blade_rand_day"] = day
            inst.extra_attrs = extra
            return f"✨ 刃之魔灵：今日首战恩赐，{attr_map[chosen]}+40（永久）"
        async def _apply_robe_self_siphon(_dead_player):
            stmt = _select(_ItemInstance).where(
                _ItemInstance.player_id == _dead_player.id,
                _ItemInstance.equipped == True,
                _ItemInstance.item_id.in_(("vip_robe_jingyuanzhiyi", "vip_robe_jingyuan_legacy"))
            )
            inst = (await session.execute(stmt)).scalars().first()
            if not inst:
                return None
            extra = inst.extra_attrs or {}
            day = _today_key()
            if extra.get("robe_die_day") != day:
                extra["robe_die_day"] = day
                extra["robe_die_cnt"] = 0
            current_cnt = int(extra.get("robe_die_cnt", 0))
            if current_cnt >= 20:
                return f"🪞 镜怨自噬：今日已达上限（{current_cnt}/20）"
            # 使用VIPEquipmentBonus表持久化，确保冥返后不会丢失
            vip_bonus = await _VIPBonus.get_or_create(session, _dead_player.id)
            vip_bonus.add_bonus("attack", 2)
            _dead_player.attack = _dead_player.attack + 2
            extra["robe_die_cnt"] = current_cnt + 1
            inst.extra_attrs = extra
            return f"🪞 镜怨自噬：死亡化怨，攻击+2（今日{extra['robe_die_cnt']}/20）"
        async def _apply_blade_kill_mp_on_death(_player):
            """同归于尽时，玩家击杀怪物也触发噬灵者效果"""
            stmt = _select(_ItemInstance).where(
                _ItemInstance.player_id == _player.id,
                _ItemInstance.equipped == True,
                _ItemInstance.item_id == "vip_blade_zhanlongshan"
            )
            inst = (await session.execute(stmt)).scalars().first()
            if not inst:
                return None
            extra = inst.extra_attrs or {}
            day = _today_key()
            if extra.get("blade_kill_day") != day:
                extra["blade_kill_day"] = day
                extra["blade_kill_cnt"] = 0
            if int(extra.get("blade_kill_cnt", 0)) >= 20:
                return "(噬灵者今日上限已满)"
            # 使用VIPEquipmentBonus表持久化，确保冥返后不会丢失
            # 击杀永久+2属性点，1属性点=3生命值，所以实际+6生命值
            vip_bonus = await _VIPBonus.get_or_create(session, _player.id)
            actual_hp = 2 * 3  # 2属性点 × 3生命值/属性点 = 6生命值
            vip_bonus.add_bonus("max_hp", actual_hp)
            _player.max_hp = _player.max_hp + actual_hp
            extra["blade_kill_cnt"] = int(extra.get("blade_kill_cnt", 0)) + 1
            inst.extra_attrs = extra
            return f"🩸 噬灵者：击杀吞噬，生命上限+{actual_hp}（今日{extra['blade_kill_cnt']}/20）"

        _msg_rand = await _apply_blade_daily_random_on_death(player)
        if _msg_rand:
            battle_summary.append(_msg_rand)
        _msg_die = await _apply_robe_self_siphon(player)
        if _msg_die:
            battle_summary.append(_msg_die)
        # 同归于尽时也触发噬灵者（击杀怪物）
        _msg_kill2 = await _apply_blade_kill_mp_on_death(player)
        if _msg_kill2:
            battle_summary.append(_msg_kill2)

        if player.hp <= 0:
            battle_summary.append(f"💀 你被 {monster_full_display} 击败，很遗憾，你已死亡")

    # ---------------- 扣除装备耐久 ----------------
    result_eq = await session.execute(
        select(ItemInstance).where(
            ItemInstance.player_id == player.id, ItemInstance.equipped == True,
            ItemInstance.item_id.in_(config.items_config["by_type"]["EQUIPMENT"])
        )
    )
    equipped_items = result_eq.scalars().all()
    broken_msgs = []
    hp_loss_from_equipment = 0  # 记录因装备损坏导致的HP损失
    mp_loss_from_equipment = 0  # 记录因装备损坏导致的MP损失

    for eq in equipped_items:
        if eq.lose_durability(1):
            # 耐久耗尽：自动卸下且不可穿戴，保留物品
            delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
            for k, v in delta.items():
                current_value = getattr(player, k, 0)
                setattr(player, k, max(0, current_value - v))
            # 清除 _persist_bonus，防止修复后重穿时 recalc 重复扣减属性
            if "_persist_bonus" in (eq.extra_attrs or {}):
                eq.extra_attrs = {k: v for k, v in eq.extra_attrs.items() if k != "_persist_bonus"}
            eq.equipped = False
            broken_msgs.append(
                f"***\n"
                f"💔 **{eq.config.name}** 耐久耗尽已自动卸下\n"
                f"⚠️ 需修理后才能再次穿戴"
            )
            # 不再删除装备实例，遵循“耐久归零自动卸下且无法穿戴”的规则

            # 记录因装备损坏导致的属性损失，并在战报中显示
            if "max_hp" in delta and player.hp > player.max_hp:
                hp_before_adjust = player.hp
                player.hp = player.max_hp
                hp_loss = hp_before_adjust - player.hp
                hp_loss_from_equipment += hp_loss

            if "max_mp" in delta and player.mp > player.max_mp:
                mp_before_adjust = player.mp
                player.mp = player.max_mp
                mp_loss = mp_before_adjust - player.mp
                mp_loss_from_equipment += mp_loss

    # 如果有装备损坏，添加到战报中
    if broken_msgs:
        battle_summary.extend(broken_msgs)

        # 如果有因装备损坏导致的HP/MP损失，在战报中显示
        if hp_loss_from_equipment > 0:
            battle_summary.append(f"   ⚡ 体质下降，失去 {hp_loss_from_equipment} 生命值")
        if mp_loss_from_equipment > 0:
            battle_summary.append(f"   ⚡ 智力下降，失去 {mp_loss_from_equipment} 理智值")

        # 重新计算剩余装备的属性加成（确保百分比加成正确）
        await recalc_equipment_attributes(session, player)

    # ---------------- 检查装备耐久度并提醒 ----------------
    durability_warning = await check_equipment_durability(session, player.id)
    if durability_warning:
        battle_summary.append(durability_warning)

    session.add_all([player, tile])
    await session.flush()
    return BattleResult(battle_summary, victory, monster_full_display)

async def _handle_rest(session, tile: WorldTile, player: Player) -> str:
    effective_attrs = await player.get_effective_attributes(session)
    effective_max_hp = effective_attrs.get('max_hp', player.max_hp)
    player.hp = effective_max_hp
    session.add(player)
    await session.flush()
    return "🌫️ 你在这里休息了一晚，恢复了体力，生命++。"

async def _handle_merchant(session, tile: WorldTile, player: Player) -> str:
    """处理卖货郎事件"""
    if player.id in tile.state.get("visited_by", []):
        return "🏪 卖货郎已经离开了，只留下空荡荡的摊位。"

    goods = tile.state.get("goods", [])
    if not goods:
        return "🏪 卖货郎的货物已经售罄。"

    # 显示商品列表
    goods_display = []
    for i, good in enumerate(goods, 1):
        item_config = config.items_config["by_id"].get(good["item_id"])
        if item_config:
            goods_display.append(
                f"{i}. {item_config.get_display_name()} ✖️{good['quantity']} - {good['price']}💰"
            )

    if not goods_display:
        return "🏪 卖货郎的货物已经售罄。"

    goods_display_md = []
    for i, good in enumerate(goods, 1):
        item_config_md = config.items_config["by_id"].get(good["item_id"])
        if item_config_md:
            goods_display_md.append(
                f"{i}. {cmd(item_config_md.get_display_name(), f'购买 {i}')} ×{good['quantity']}　💰{good['price']}"
            )

    msg = (
        "🏪 **神秘卖货郎**\n"
        "「旅者，需要些稀有材料吗？」\n"
        + "\n".join(goods_display_md if goods_display_md else goods_display) +
        "\n💡 点击物品名直接购买　⚠️ 每人只能访问一次"
    )

    # 标记玩家已访问
    tile.state.setdefault("visited_by", []).append(player.id)
    session.add(tile)
    await session.flush()

    return msg

async def _handle_elite(session, tile: WorldTile, player: Player):
    """处理精英怪事件"""
    if player.id in tile.state.get("defeated_by", []):
        return "⚰️ 精英诡异的残骸散落一地，散发着不祥的气息。"

    # 使用与普通诡异相同的战斗逻辑，但精英诡异更强
    return await _handle_personal_monster(session, tile, player)


EVENT_HANDLERS = {
    "MATERIAL": _handle_material,
    "TREASURE": _handle_treasure,
    "EMPTY": _handle_empty,
    "REST": _handle_rest,
    "MERCHANT": _handle_merchant,
    "ELITE": _handle_elite,
}

@explore_cmd.handle()
async def _(event: MessageEvent):
    user_id = event.get_user_id()

    async with safe_session() as session:
        player: Player | None = await get_unified_player(session, event)
        if not player:
            await explore_cmd.finish("⛔ 请先创建角色")

        if not player.is_in_dungeon():
            await explore_cmd.finish("⛔ 你已经返回现实\n⬇️ 【传送 N层诡域】进入诡域探索")

        if player.hp <= 0:
            await explore_cmd.finish("💀 你已死亡，返回现实吧，或者你有复活道具..."
                                     "\n⬇️ 【返回】 退出副本"
                                     "\n⬇️ 【使用 还魂丹】 原地复活，继续副本")

        # 使用新的坐标系统获取当前位置
        current_x, current_y = player.get_current_coordinates()
        current_region = player.get_current_region()
        tile = await get_or_create_tile(session, current_region, current_x, current_y, player.server_id)

        # 清除全视之眼预览标记（玩家已实际探索此格子）
        if (tile.state or {}).get("preview"):
            state = tile.state or {}
            state.pop("preview", None)
            tile.state = state

        log = await EVENT_HANDLERS[tile.event_type](session, tile, player)

        # 更新探索统计（用于公会任务）
        if player.guild_id:
            from ..guild.guild_task_service_new import GuildTaskService as GuildTaskServiceNew
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.guild_repository import GuildRepository
            from ..infrastructure.repositories.player_task_stats_repository import PlayerTaskStatsRepository
            from ..infrastructure.repositories.guild_task_record_repository import GuildTaskRecordRepository
            from ..infrastructure.repositories.player_donation_log_repository import PlayerDonationLogRepository
            from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository

            task_service = GuildTaskServiceNew(
                player_repo=PlayerRepository(session),
                guild_repo=GuildRepository(session),
                player_task_stats_repo=PlayerTaskStatsRepository(session),
                guild_task_record_repo=GuildTaskRecordRepository(session),
                player_donation_log_repo=PlayerDonationLogRepository(session),
                guild_building_repo=GuildBuildingRepository(session),
            )
            await task_service.update_exploration_stats(player.id)

            # 尝试自动完成任务
            completed_tasks = await task_service.try_auto_complete_tasks(player.id)
            if completed_tasks:
                if isinstance(log, BattleResult):
                    log.log_lines.append("")
                    log.log_lines.append("🎉 公会任务完成：")
                    log.log_lines.extend(completed_tasks)
                else:
                    log += "\n\n🎉 公会任务完成：\n" + "\n".join(completed_tasks)
        # 获取含buff/宠物的有效属性，保持与面板一致
        effective_attrs = await player.get_effective_attributes(session)
        eff_max_hp = effective_attrs.get("max_hp", player.max_hp)
        eff_max_mp = effective_attrs.get("max_mp", player.max_mp)

        # 查询已探索坐标（用于战斗后的小地图）
        explored_coords: set[tuple[int, int]] = set()
        if isinstance(log, BattleResult):
            explored_coords = await _query_explored_coords(session, current_region, player.server_id)

        await session.commit()

    status_line = (
        f"🧭 **{current_region}** ({current_x},{current_y})　"
        f"❤️ **{player.hp}**/{eff_max_hp}　"
        f"🧠 **{player.mp}**/{eff_max_mp}"
    )

    nav_row1 = f"{cmd('↑上', '上')} | {cmd('↓下', '下')} | {cmd('←左', '左')} | {cmd('→右', '右')} | {cmd('🗡️探索', '探索')}"
    nav_row2 = f"{cmd('上一层')} | {cmd('下一层')} | {cmd('一键嗑药')} | {cmd('俯瞰')}"

    if isinstance(log, BattleResult):
        # 战斗日志用 bash 代码块包裹；小地图放在代码块外面
        mini_map = _build_dungeon_minimap(current_x, current_y, explored_coords)
        battle_title = f"⚔️ **击杀 {log.monster_display}**" if log.victory else f"⚔️ **对战 {log.monster_display}**"
        battle_text = "\n".join(str(l) for l in log.log_lines)
        lines = [
            "# 🌀 诡域探索",
            status_line,
            "***",
            "🗺️ **小地图**　🟨你　🟩已探索　⬜未探索",
            mini_map,
            "***",
            battle_title,
            "```bash",
            battle_text,
            "```",
            "***",
            nav_row1,
            nav_row2,
        ]
    else:
        lines = [
            "# 🌀 诡域探索",
            status_line,
            "***",
            log,
            "***",
            nav_row1,
            nav_row2,
        ]

    await explore_cmd.finish(build_markdown("\n".join(lines)))

# ==================== 购买指令 ====================
dungeon_buy_cmd = on_command("购买", block=False, priority=5)

@dungeon_buy_cmd.handle()
async def handle_buy(matcher: Matcher, event: MessageEvent, args: Message = CommandArg()):
    """从卖货郎处购买商品（仅副本内生效，参数为纯数字序号）"""
    arg_text = args.extract_plain_text().strip()
    # 仅处理纯数字参数（副本卖货郎用序号），其他格式放行给跑商购买
    if not arg_text or not arg_text.isdigit():
        return
    item_index = int(arg_text)

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await dungeon_buy_cmd.finish("⛔ 请先创建角色")

        # 大都会玩家不处理，放行给跑商购买命令
        if player.region == "大都会":
            return
        # 非大都会且参数为纯数字时，视为诡域卖货郎购买，阻断后续「购买」命令
        matcher.stop_propagation()

        # 获取当前位置的格子 - 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        tile = await get_or_create_tile(session, player.region, current_x, current_y, player.server_id)

        if tile.event_type != "MERCHANT":
            await dungeon_buy_cmd.finish("⛔ 这里没有卖货郎")

        if player.id not in tile.state.get("visited_by", []):
            await dungeon_buy_cmd.finish("⛔ 你还没有与卖货郎交谈，请先【探索】")

        # 检查玩家是否已经购买过商品
        purchased_by = tile.state.get("purchased_by", [])
        if player.id in purchased_by:
            await dungeon_buy_cmd.finish("⛔ 你已经从这个卖货郎处购买过商品了，每人只能购买一次")

        goods = tile.state.get("goods", [])
        if not goods or item_index < 1 or item_index > len(goods):
            await dungeon_buy_cmd.finish("⛔ 商品序号无效")

        good = goods[item_index - 1]
        item_config = config.items_config["by_id"].get(good["item_id"])
        if not item_config:
            await dungeon_buy_cmd.finish("⛔ 商品不存在")

        # 检查金币是否足够
        if player.gold < good["price"]:
            await dungeon_buy_cmd.finish(f"⛔ 金币不足，需要 {good['price']}💰，当前 {player.gold}💰")

        # 购买商品
        try:
            from ..models.inventory import ItemInstance
            await ItemInstance.add_item(session, player.id, good["item_id"], good["quantity"])
            player.gold -= good["price"]

            # 移除已购买的商品
            goods.pop(item_index - 1)
            tile.state["goods"] = goods

            # 标记玩家已购买，防止重复购买
            tile.state.setdefault("purchased_by", []).append(player.id)

            session.add_all([player, tile])
            await session.commit()

            msg = (
                f"💰 购买成功！\n"
                f"▫️ 获得：{item_config.get_display_name()} ✖️{good['quantity']}\n"
                f"▫️ 花费：{good['price']}💰\n"
                f"▫️ 剩余金币：{player.gold}💰\n"
                f"⚠️ 你已经从这个卖货郎处购买过商品，无法再次购买"
            )
            await dungeon_buy_cmd.finish(message_add_head(msg, event))

        except ValueError as e:
            await dungeon_buy_cmd.finish(f"⛔ 购买失败：{e}")


teleport_list = on_command("诡域", aliases={"副本列表"}, block=True, priority=5)
@teleport_list.handle()
async def handle_teleport_list(event: MessageEvent):
    """显示无限层诡域爬塔进度"""
    async with safe_session() as session:
        # 检查玩家是否存在
        player = await get_unified_player(session, event)
        if not player:
            await teleport_list.finish("⛔ 请先创建角色")

        # 获取玩家爬塔进度
        max_level = player.max_dungeon_level or 0
        accessible_levels = player.get_accessible_dungeon_levels()
        current_level = player.dungeon_level if player.is_in_dungeon() else 0

        # 显示当前可访问的层级（最多显示5层）
        display_levels = accessible_levels[-5:] if len(accessible_levels) > 5 else accessible_levels

        locations = []
        for level in display_levels:
            # 动态生成层级配置
            dungeon_config = config._generate_dungeon_level_config(
                level, config.map_config.get("dungeon_generation_rules", {})
            )

            mp_cost = dungeon_config.get("mp_cost", 1)
            level_range = dungeon_config.get("level_range", [level*5-2, level*5+2])

            # 状态标识
            if level <= max_level:
                status = "✅"  # 已通过
            elif level == max_level + 1:
                status = "🎯"  # 下一个挑战
            else:
                status = "🔒"  # 未解锁

            # 当前所在层级
            current_marker = " 📍**当前**" if level == current_level else ""
            level_name = f"{level}层诡域"

            if level <= max_level + 1:
                # 可进入的层：点击直接传送
                locations.append(
                    f"{status} {cmd(level_name, f'传送 {level_name}')}　"
                    f"⚡理智-{mp_cost}　👹诡异Lv.{level_range[0]}-{level_range[1]}{current_marker}"
                )
            else:
                locations.append(
                    f"{status} **{level_name}**　"
                    f"⚡理智-{mp_cost}　👹诡异Lv.{level_range[0]}-{level_range[1]}"
                )

        # 格式化消息
        msg_lines = [
            "# 🌀 无限重诡域探索系统",
            "***",
            f"🏆 最深探索：**第{max_level}重**诡域",
            f"🎯 下一目标：**第{max_level + 1}重**诡域",
            f"📊 总可访问：**{len(accessible_levels)}重**",
        ]

        if current_level > 0:
            msg_lines.append(f"📍 当前位置：**第{current_level}重**诡域")

        msg_lines.extend([
            "***",
            "💡 每重诡域都是独立的10x10空间",
            "⚔️ 诡异等级 = 诡域深度 × 5（±2波动）",
            "🔓 击败诡异解锁更深的诡域",
            "***",
        ])

        if locations:
            msg_lines.append("**📋 可访问深度（最近5重）：**")
            msg_lines.extend(locations)

        msg_lines.extend([
            "***",
            "✅已探索　🎯下一目标　🔒未解锁",
            f"{cmd('俯瞰')} | {cmd('返回')} | {cmd('帮助')}",
        ])

        await teleport_list.finish(build_markdown("\n".join(msg_lines)))


# ==================== 诡域探索概览图片生成 ====================
region_overview_cmd = on_command("俯瞰", aliases={"感知"}, block=True, priority=5)


def _render_dungeon_overview(tile_data: list[tuple[int, int, str, bool]],
                            min_x: int, max_x: int, min_y: int, max_y: int,
                            player_x: int | None, player_y: int | None) -> bytes:
    """纯CPU渲染诡域俯瞰图（在线程池中执行，不阻塞事件循环）
    tile_data: [(x, y, event_type, is_preview), ...]
    """
    margin = 40
    img_width = 1000
    img_height = 1000
    img = Image.new('RGB', (img_width, img_height), color='#1a1a1a')
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    grid_width = max(max_x - min_x + 1, 1)
    grid_height = max(max_y - min_y + 1, 1)
    available_width = img_width - 2 * margin
    available_height = img_height - 2 * margin

    cell_width = max(available_width // grid_width, 2)
    cell_height = max(available_height // grid_height, 2)

    event_colors = {
        'MATERIAL': (76, 175, 80),
        'TREASURE': (255, 215, 0),
        'EMPTY': (244, 67, 54),
        'REST': (33, 150, 243),
        'MERCHANT': (156, 39, 176),
        'ELITE': (255, 87, 34),
    }

    tile_map = {(x, y): (evt, preview) for x, y, evt, preview in tile_data}

    # 绘制格子
    for grid_x in range(grid_width):
        for grid_y in range(grid_height):
            world_x = min_x + grid_x
            world_y = max_y - grid_y

            pixel_x = margin + grid_x * cell_width
            pixel_y = margin + grid_y * cell_height

            tile_info = tile_map.get((world_x, world_y))
            if tile_info:
                evt_type, is_preview = tile_info
                base_color = event_colors.get(evt_type, (102, 102, 102))
                if is_preview:
                    color = (base_color[0] // 3, base_color[1] // 3, base_color[2] // 3)
                else:
                    color = base_color
            else:
                color = (51, 51, 51)

            x1, y1 = pixel_x, pixel_y
            x2, y2 = pixel_x + cell_width, pixel_y + cell_height
            if x2 > x1 and y2 > y1:
                draw.rectangle([x1, y1, x2, y2], fill=color, outline=(85, 85, 85))

    # 绘制玩家位置标记
    if player_x is not None and player_y is not None:
        if min_x <= player_x <= max_x and min_y <= player_y <= max_y:
            pg_x = player_x - min_x
            pg_y = max_y - player_y
            pp_x = margin + pg_x * cell_width
            pp_y = margin + pg_y * cell_height

            cx = pp_x + cell_width // 2
            cy = pp_y + cell_height // 2
            radius = min(cell_width, cell_height) // 3

            draw.ellipse([cx - radius - 2, cy - radius - 2,
                         cx + radius + 2, cy + radius + 2],
                        fill=(255, 255, 255), outline=(255, 255, 255))
            draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                        fill=(255, 255, 0), outline=(255, 215, 0))

    # 绘制坐标轴十字线
    if min_x <= 0 <= max_x and min_y <= 0 <= max_y:
        og_x = 0 - min_x
        og_y = max_y - 0
        op_x = margin + og_x * cell_width
        op_y = margin + og_y * cell_height
        draw.line([(op_x + cell_width // 2, margin),
                   (op_x + cell_width // 2, img_height - margin)], fill=(128, 128, 128), width=1)
        draw.line([(margin, op_y + cell_height // 2),
                   (img_width - margin, op_y + cell_height // 2)], fill=(128, 128, 128), width=1)

    # 绘制坐标轴数字
    if font:
        step_x = max(1, grid_width // 10)
        for i in range(0, grid_width, step_x):
            wx = min_x + i
            px = margin + i * cell_width + cell_width // 2
            draw.text((px, 5), str(wx), fill=(255, 255, 255), font=font, anchor='mt')
            draw.text((px, img_height - 20), str(wx), fill=(255, 255, 255), font=font, anchor='mb')

        step_y = max(1, grid_height // 10)
        for i in range(0, grid_height, step_y):
            wy = max_y - i
            py = margin + i * cell_height + cell_height // 2
            draw.text((5, py), str(wy), fill=(255, 255, 255), font=font, anchor='lm')
            draw.text((img_width - 5, py), str(wy), fill=(255, 255, 255), font=font, anchor='rm')

    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    return img_buffer.getvalue()


async def generate_player_centered_overview_image(region: str, session, center_x: int, center_y: int, width: int, height: int, player_x: int = None, player_y: int = None, server_id: int = 1) -> tuple[bytes, tuple[int, int, int, int]]:
    """生成以玩家为中心的固定大小俯瞰图片，只显示今日刷新的格子"""
    half_width = width // 2
    half_height = height // 2
    min_x = center_x - half_width
    max_x = center_x + half_width
    min_y = center_y - half_height
    max_y = center_y + half_height

    from sqlalchemy import and_
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    tomorrow_start = today_start + timedelta(days=1)

    stmt = select(WorldTile).where(
        and_(
            WorldTile.region == region,
            WorldTile.server_id == server_id,
            WorldTile.x >= min_x, WorldTile.x <= max_x,
            WorldTile.y >= min_y, WorldTile.y <= max_y,
            WorldTile.refreshed_at >= today_start,
            WorldTile.refreshed_at < tomorrow_start
        )
    )
    result = await session.execute(stmt)
    tiles = result.scalars().all()

    # 提取纯数据，脱离ORM session
    tile_data = [(t.x, t.y, t.event_type, bool((t.state or {}).get("preview"))) for t in tiles]

    if player_x is None or player_y is None:
        player_x, player_y = center_x, center_y

    # 线程池渲染
    img_bytes = await asyncio.to_thread(
        _render_dungeon_overview, tile_data, min_x, max_x, min_y, max_y, player_x, player_y
    )
    return img_bytes, (min_x, max_x, min_y, max_y)


async def generate_region_overview_image(region: str, session, player_x: int = None, player_y: int = None, server_id: int = 1) -> tuple[bytes, tuple[int, int, int, int]]:
    """生成指定诡域的今日探索概览图片"""
    today = date.today()
    from sqlalchemy import and_

    today_start = datetime.combine(today, datetime.min.time())
    tomorrow_start = today_start + timedelta(days=1)

    stmt = select(WorldTile).where(
        and_(
            WorldTile.region == region,
            WorldTile.server_id == server_id,
            WorldTile.refreshed_at >= today_start,
            WorldTile.refreshed_at < tomorrow_start
        )
    )
    result = await session.execute(stmt)
    today_tiles = result.scalars().all()

    # 过滤掉x或y绝对值大于500的格子
    today_tiles = [tile for tile in today_tiles if abs(tile.x) <= 500 and abs(tile.y) <= 500]

    if not today_tiles:
        center_x, center_y = 0, 0
        if player_x is not None and player_y is not None:
            center_x, center_y = player_x, player_y
        min_x, max_x = center_x - 2, center_x + 2
        min_y, max_y = center_y - 2, center_y + 2
        tile_data = []
    else:
        # 提取纯数据
        tile_data = [(t.x, t.y, t.event_type, bool((t.state or {}).get("preview"))) for t in today_tiles]
        min_x = min(t[0] for t in tile_data)
        max_x = max(t[0] for t in tile_data)
        min_y = min(t[1] for t in tile_data)
        max_y = max(t[1] for t in tile_data)

    if min_x > max_x:
        min_x, max_x = max_x, min_x
    if min_y > max_y:
        min_y, max_y = max_y, min_y

    if tile_data:
        if max_x - min_x + 1 < 20:
            cx = (min_x + max_x) // 2
            min_x, max_x = cx - 10, cx + 10
        if max_y - min_y + 1 < 20:
            cy = (min_y + max_y) // 2
            min_y, max_y = cy - 10, cy + 10

    if min_x >= max_x:
        max_x = min_x + 20
    if min_y >= max_y:
        max_y = min_y + 20

    # 线程池渲染（复用共享渲染函数）
    img_bytes = await asyncio.to_thread(
        _render_dungeon_overview, tile_data, min_x, max_x, min_y, max_y, player_x, player_y
    )
    return img_bytes, (min_x, max_x, min_y, max_y)


@region_overview_cmd.handle()
async def handle_region_overview(event: MessageEvent, args: Message = CommandArg()):
    """生成诡域探索概览图片"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await region_overview_cmd.finish("⛔ 请先创建角色")

        # 获取参数
        arg_text = args.extract_plain_text().strip()

        # 如果没有指定诡域，俯瞰当前区域
        if not arg_text:
            try:
                current_x, current_y = player.get_current_coordinates()
                current_region = player.get_current_region()

                # 检查当前区域是否为诡域（层级制诡域）
                if current_region.endswith("层诡域"):
                    # 全视之眼赞助特权：预生成所有格子
                    from ..sponsor.service import SponsorShopService
                    if SponsorShopService.is_privilege_active(player, "premium_vision_until"):
                        # 记录已存在的格子坐标（玩家实际探索过的）
                        from sqlalchemy import and_
                        today = date.today()
                        today_start = datetime.combine(today, datetime.min.time())
                        tomorrow_start = today_start + timedelta(days=1)
                        existing_stmt = select(WorldTile.x, WorldTile.y).where(
                            and_(
                                WorldTile.region == current_region,
                                WorldTile.server_id == player.server_id,
                                WorldTile.refreshed_at >= today_start,
                                WorldTile.refreshed_at < tomorrow_start
                            )
                        )
                        existing_result = await session.execute(existing_stmt)
                        existing_coords = {(r[0], r[1]) for r in existing_result}
                        # 预生成所有格子，新格子标记为预览
                        for tx in range(-5, 6):
                            for ty in range(-5, 6):
                                if (tx, ty) not in existing_coords:
                                    tile = await get_or_create_tile(session, current_region, tx, ty, player.server_id)
                                    # 标记为预览格子
                                    state = tile.state or {}
                                    state["preview"] = True
                                    tile.state = state
                        await session.flush()
                    # 诡域内：生成固定的10x10地图（-5到5的范围），以(0,0)为中心但显示玩家实际位置
                    img_data, (min_x, max_x, min_y, max_y) = await generate_player_centered_overview_image(
                        current_region, session, 0, 0, 11, 11, current_x, current_y, player.server_id  # 以(0,0)为中心的11x11地图，但显示玩家在(current_x,current_y)的位置
                    )
                    map_desc = f"🗺️ {current_region} 今日探索情况"
                    coord_desc = f"📍 你的位置：({current_x},{current_y})"
                    range_desc = f"📍 诡域范围：(-5,-5) 到 (5,5)"
                else:
                    # 现实世界：生成以玩家为中心的大范围俯瞰图
                    img_data, (min_x, max_x, min_y, max_y) = await generate_player_centered_overview_image(
                        current_region, session, current_x, current_y, 500, 500, current_x, current_y, player.server_id
                    )
                    map_desc = f"🗺️ {current_region} 以你为中心的俯瞰图"
                    coord_desc = f"📍 中心位置：({current_x},{current_y})"
                    range_desc = f"📍 坐标范围：X({min_x}~{max_x}) Y({min_y}~{max_y})"

                # 转换为base64
                img_b64 = base64.b64encode(img_data).decode('utf-8')

                # 构建说明文字
                msg_lines = [
                    map_desc,
                    "━━━━━━━━━━━━━",
                    coord_desc,
                    range_desc,
                    "━━━━━━━━━━━━━",
                    "🟢 绿色：材料格子",
                    "🟡 金色：宝藏格子",
                    "🔴 红色：诡异格子",
                    "🔵 蓝色：休息格子",
                    "🟣 紫色：商人格子",
                    "🟠 橙色：精英怪格子",
                    "⬛ 灰色：未探索区域",
                    "🔲 暗色：全视之眼揭示（未探索）",
                    f"🟡 亮黄圆圈：你的位置 ({current_x},{current_y})",
                ]

                msg_text = "\n".join(msg_lines)

                # 发送图片和文字
                img_segment = MessageSegment.file_image(img_b64)
                message = Message(msg_text).append(img_segment)

                await region_overview_cmd.finish(message_add_head(message, event))

            except ValueError as e:
                await region_overview_cmd.finish(f"⛔ 生成俯瞰图失败：{str(e)}")
        else:
            # 指定了诡域名称，支持层级制诡域
            region = arg_text

            # 检查是否为层级诡域格式
            if region.endswith("层诡域"):
                try:
                    level_str = region.replace("层诡域", "")
                    # 兼容"第N层诡域"格式，移除开头的"第"字
                    if level_str.startswith("第"):
                        level_str = level_str[1:]
                    dungeon_level = int(level_str)
                    # 优先从预生成配置获取，如果不存在则动态生成（支持无限层）
                    dungeon_config = config.map_config.get("dungeon_levels", {}).get(dungeon_level)
                    if not dungeon_config:
                        # 动态生成超过100层的配置
                        dungeon_config = config._generate_dungeon_level_config(
                            dungeon_level, config.map_config.get("dungeon_generation_rules", {})
                        )
                except ValueError:
                    await region_overview_cmd.finish("⛔ 诡域层级格式错误，请使用：俯瞰 1层诡域 或 俯瞰 第1层诡域")
            else:
                # 兼容旧的命名诡域
                if region not in config.map_config.get("regions", {}):
                    await region_overview_cmd.finish("⛔ 未知的诡域名称，请使用：俯瞰 N层诡域")
                dungeon_config = config.map_config["regions"].get(region, {})

            try:
                # 生成概览图片，传入玩家坐标（如果玩家在当前诡域）
                player_x, player_y = None, None
                current_region = player.get_current_region()
                if current_region == region:
                    player_x, player_y = player.get_current_coordinates()

                # 检查是否为诡域，如果是则使用固定范围
                if region.endswith("层诡域"):
                    # 全视之眼赞助特权：预生成所有格子
                    from ..sponsor.service import SponsorShopService
                    if SponsorShopService.is_privilege_active(player, "premium_vision_until"):
                        # 记录已存在的格子坐标（玩家实际探索过的）
                        from sqlalchemy import and_
                        today = date.today()
                        today_start = datetime.combine(today, datetime.min.time())
                        tomorrow_start = today_start + timedelta(days=1)
                        existing_stmt = select(WorldTile.x, WorldTile.y).where(
                            and_(
                                WorldTile.region == region,
                                WorldTile.server_id == player.server_id,
                                WorldTile.refreshed_at >= today_start,
                                WorldTile.refreshed_at < tomorrow_start
                            )
                        )
                        existing_result = await session.execute(existing_stmt)
                        existing_coords = {(r[0], r[1]) for r in existing_result}
                        # 预生成所有格子，新格子标记为预览
                        for tx in range(-5, 6):
                            for ty in range(-5, 6):
                                if (tx, ty) not in existing_coords:
                                    tile = await get_or_create_tile(session, region, tx, ty, player.server_id)
                                    # 标记为预览格子
                                    state = tile.state or {}
                                    state["preview"] = True
                                    tile.state = state
                        await session.flush()
                    # 诡域使用固定的10x10范围（-5到5），如果玩家在当前诡域则以玩家为中心
                    center_x, center_y = 0, 0  # 默认以(0,0)为中心
                    if current_region == region and player_x is not None and player_y is not None:
                        center_x, center_y = player_x, player_y  # 如果玩家在当前诡域，以玩家位置为中心
                    img_data, (min_x, max_x, min_y, max_y) = await generate_player_centered_overview_image(
                        region, session, center_x, center_y, 11, 11, player_x, player_y, player.server_id  # 以计算出的中心位置生成11x11地图，显示玩家实际位置
                    )
                else:
                    # 其他区域使用原有的今日探索逻辑
                    img_data, (min_x, max_x, min_y, max_y) = await generate_region_overview_image(region, session, player_x, player_y, player.server_id)

                # 转换为base64
                img_b64 = base64.b64encode(img_data).decode('utf-8')

                # 构建消息
                tier = dungeon_config.get("tier", 1)
                level_range = dungeon_config.get("level_range", [1, 1])

                # 构建说明文字
                if region.endswith("层诡域"):
                    msg_lines = [
                        f"🗺️ {region} 今日探索小地图",
                        "━━━━━━━━━━━━━",
                        f"📊 诡域等级：Tier {tier}",
                        f"⚔️ 诡异等级：{level_range[0]}-{level_range[1]}级",
                        "📍 诡域范围：(-5,-5) 到 (5,5)"
                    ]
                else:
                    msg_lines = [
                        f"🗺️ {region} 今日探索小地图",
                        "━━━━━━━━━━━━━",
                        f"📊 诡域等级：Tier {tier}",
                        f"⚔️ 诡异等级：{level_range[0]}-{level_range[1]}级",
                        f"📍 坐标范围：X({min_x}~{max_x}) Y({min_y}~{max_y})"
                    ]

                msg_lines.extend([
                    "━━━━━━━━━━━━━",
                    "🟢 绿色：材料格子",
                    "🟡 金色：宝藏格子",
                    "🔴 红色：诡异格子",
                    "🔵 蓝色：休息格子",
                    "🟣 紫色：商人格子",
                    "🟠 橙色：精英怪格子",
                    "⬛ 灰色：未探索区域",
                    "🔲 暗色：全视之眼揭示（未探索）"
                ])

                # 如果玩家在当前诡域，添加位置说明
                if current_region == region:
                    current_x, current_y = player.get_current_coordinates()
                    msg_lines.append(f"🟡 亮黄圆圈：你的位置 ({current_x},{current_y})")

                msg_lines.append("🔢 图片边缘显示坐标数字")

                msg_text = "\n".join(msg_lines)

                # 发送图片和文字
                img_segment = MessageSegment.file_image(img_b64)
                message = Message(msg_text).append(img_segment)

                await region_overview_cmd.finish(message_add_head(message, event))

            except ValueError as e:
                await region_overview_cmd.finish(f"⛔ 生成概览图片失败：{str(e)}")
