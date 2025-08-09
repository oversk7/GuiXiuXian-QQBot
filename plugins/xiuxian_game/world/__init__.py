from __future__ import annotations

"""世界与坐标系统
1. 传送 <区域名> 切换区域，但坐标与现实世界相同
2. 前往 <上|下|左|右|x,y> 改变坐标（同区域内移动）
3. get_or_create_tile: 按天刷新、确定性种子生成事件
"""

from nonebot import on_command, on_regex
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.params import CommandArg
from typing import Tuple, Dict
from datetime import datetime, date, timedelta
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
from ..utils import message_add_head, luck_prob, check_action_limit, record_action


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
from . import nearby_players, message_board, navigation, map_locations

# ----------------- 常量 -----------------
DIRECTIONS: Dict[str, Tuple[int, int]] = {
    "上": (0, 1),
    "下": (0, -1),
    "左": (-1, 0),
    "右": (1, 0),
}



# -------- 材料掉落权重配置 --------
RARITY_WEIGHTS = {
    "white": 50,    # 白色材料权重
    "green": 25,    # 绿色材料权重
    "blue": 15,     # 蓝色材料权重
    "purple": 8,    # 紫色材料权重
    "orange": 2     # 橙色材料权重
}

def get_materials_by_rarity(rarity: str) -> list:
    """获取指定稀有度的所有材料"""
    materials = []
    for item_id in config.items_config["by_type"]["MATERIAL"]:
        item_config = config.items_config["by_id"].get(item_id)
        if item_config and item_config.rarity == rarity:
            materials.append(item_id)
    return materials

def get_region_materials(region: str) -> dict:
    """获取区域材料配置"""
    region_config = config.map_config["regions"].get(region, {})
    return {
        "merchant": region_config.get("merchant_materials", []),  # 商人材料（高价值）
        "basic": region_config.get("basic_materials", [])         # 基础材料（材料格子）
    }

def calculate_monster_attributes(monster_level: int, is_elite: bool = False) -> dict:
    """
    计算怪物属性，适配实际玩家水平
    目标：同等级玩家能连续刷5个同等级小怪而不需要治疗药

    基于196级玩家反馈调整：
    - 生命2125，攻击1256，防御854（60%免伤）
    - 目标：怪物攻击造成约100-150伤害，玩家能连续打5个不死
    """
    import random

    # 基础属性计算 - 平衡调整，确保5个同级怪物的挑战度
    if monster_level <= 50:
        # 前期线性增长（1-50级）
        base_hp = 1.2 * monster_level + 15
        base_attack = 0.6 * monster_level + 10
        base_agility = 0.5 * monster_level + 8
    elif monster_level <= 100:
        # 中期增长（51-100级）
        base_hp = 1.5 * monster_level + 40
        base_attack = 0.7 * monster_level + 25
        base_agility = 0.5 * monster_level + 20
    elif monster_level <= 150:
        # 高期增长（101-150级）
        base_hp = 1.7 * monster_level + 80
        base_attack = 0.9 * monster_level + 40
        base_agility = 0.8 * monster_level + 30
    else:
        # 终极期适度增长（151+级）
        base_hp = 2.1 * monster_level + 100
        base_attack = 2.7 * monster_level + 250
        base_agility = 1.1 * monster_level + 50

    # 添加随机波动（±10%，减少波动范围）
    rng = random.Random()
    hp_variation = rng.uniform(0.9, 1.1)
    attack_variation = rng.uniform(0.9, 1.1)
    agility_variation = rng.uniform(0.9, 1.1)

    hp = int(base_hp * hp_variation)
    attack = int(base_attack * attack_variation)
    agility = int(base_agility * agility_variation)

    # 精英怪属性提升 - 保持现有倍率
    if is_elite:
        if monster_level <= 50:
            elite_multiplier = 1.8  # 前期精英怪1.8倍属性
        elif monster_level <= 100:
            elite_multiplier = 2.0  # 中期精英怪2倍属性
        else:
            elite_multiplier = 2.2  # 高期精英怪2.2倍属性

        hp = int(hp * elite_multiplier)
        attack = int(attack * elite_multiplier)
        agility = int(agility * elite_multiplier)

    return {
        "hp": hp,
        "attack": attack,
        "agility": agility
    }

def generate_merchant_goods(region: str, tier: int, rng) -> list:
    """生成商人商品列表 - 专门出售高价值材料"""
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

    return goods

async def handle_monster_drops(session, player: Player, monster_level: int, region: str, rng, is_elite: bool = False) -> str:
    """处理怪物掉落材料"""
    from ..models.inventory import ItemInstance
    from ..utils import luck_prob

    # 根据怪物等级确定掉落概率和稀有度
    if monster_level <= 20:
        # 低级怪物：30%掉落白色，10%绿色
        drop_rates = {"white": 0.30, "green": 0.10}
    elif monster_level <= 60:
        # 中级怪物：40%白色，20%绿色，5%蓝色
        drop_rates = {"white": 0.40, "green": 0.20, "blue": 0.05}
    elif monster_level <= 100:
        # 高级怪物：30%白色，25%绿色，15%蓝色，3%紫色
        drop_rates = {"white": 0.30, "green": 0.25, "blue": 0.15, "purple": 0.03}
    else:
        # 顶级怪物：20%白色，20%绿色，20%蓝色，8%紫色，1%橙色
        drop_rates = {"white": 0.20, "green": 0.20, "blue": 0.20, "purple": 0.08, "orange": 0.01}

    # 精英怪掉落率翻倍，并且有更高概率掉落稀有材料
    if is_elite:
        enhanced_rates = {}
        for rarity, rate in drop_rates.items():
            if rarity in ["purple", "orange"]:
                enhanced_rates[rarity] = min(rate * 3, 0.5)  # 紫橙材料3倍概率
            else:
                enhanced_rates[rarity] = min(rate * 2, 0.8)  # 其他材料2倍概率
        drop_rates = enhanced_rates

    drops = []
    region_materials = get_region_materials(region)

    # 检查每个稀有度的掉落
    for rarity, base_rate in drop_rates.items():
        # 幸运值影响掉落率
        final_rate = base_rate * (1 + luck_prob(player.luck))

        if rng.random() < final_rate:
            # 选择掉落的材料
            candidate_materials = []

            # 怪物掉落优先从商人材料中选择（更有价值）
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
                        drops.append(f"{item_config.get_display_name()} ✖️{quantity}")
                except ValueError:
                    # 背包满了，跳过这个掉落
                    pass

    if drops:
        return f"💎 战利品：{', '.join(drops)}"
    else:
        return "💔 这次没有获得任何材料"

# ----------------- 工具函数 -----------------
async def get_or_create_tile(session, region: str, x: int, y: int) -> WorldTile:
    """获取或创建今日坐标格，并在创建时生成事件"""
    today = date.today()

    # 先尝试简单查询，避免使用 with_for_update() 造成锁定
    result = await session.execute(
        select(WorldTile)
        .where(WorldTile.region == region, WorldTile.x == x, WorldTile.y == y)
    )
    tile = result.scalars().first()

    # 若不存在或已过期（日期变化）则重新生成
    if (not tile) or (tile.refreshed_at.date() != today):
        if not tile:
            # 创建新的tile
            tile = WorldTile(region=region, x=x, y=y)
            session.add(tile)

        # 更新tile信息
        tile.refreshed_at = datetime.now()

        # 生成事件 - 增加新的事件类型
        tile.seed = f"{region}:{x}:{y}:{today.isoformat()}"
        rng = random.Random(hash(tile.seed))

        # 根据诡域等级调整事件权重
        region_config = config.map_config["regions"].get(region, {})
        tier = region_config.get("tier", 1)

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
            map_info = config.map_config["regions"][region]
            monster = rng.choice(map_info["monsters"])
            monster_level = random.randint(map_info["level_range"][0], map_info["level_range"][1])

            # 使用新的怪物属性计算函数
            monster_attrs = calculate_monster_attributes(monster_level, is_elite=False)
            tile.state = {
                "name": monster,
                "level": monster_level,
                "hp": monster_attrs["hp"],
                "attack": monster_attrs["attack"],
                "agility": monster_attrs["agility"],
                "defeated_by": []  # 记录击败过的玩家，避免原地无限刷
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
            # 精英怪：强化版怪物
            map_info = config.map_config["regions"][region]
            monster = rng.choice(map_info["monsters"])
            monster_level = rng.randint(map_info["level_range"][0], map_info["level_range"][1])

            # 使用新的怪物属性计算函数（精英版）
            monster_attrs = calculate_monster_attributes(monster_level, is_elite=True)
            tile.state = {
                "name": f"精英·{monster}",
                "level": monster_level,
                "hp": monster_attrs["hp"],
                "attack": monster_attrs["attack"],
                "agility": monster_attrs["agility"],
                "is_elite": True,
                "defeated_by": []  # 记录击败过的玩家
            }

        # 使用 merge 来处理可能的并发冲突
        try:
            await session.flush()
        except Exception:
            # 如果出现冲突，重新查询最新的tile
            await session.rollback()
            result = await session.execute(
                select(WorldTile)
                .where(WorldTile.region == region, WorldTile.x == x, WorldTile.y == y)
            )
            tile = result.scalars().first()
            if not tile:
                # 如果还是没有，说明出现了异常情况，创建一个基本的tile
                tile = WorldTile(region=region, x=x, y=y, refreshed_at=datetime.now())
                tile.event_type = "EMPTY"
                tile.state = {}
                session.add(tile)
                await session.flush()

    return tile


# ----------------- 指令：移动 -----------------
move_cmd = on_regex(r"^(上|下|左|右)$", block=True, priority=5)

@move_cmd.handle()
async def _(event: MessageEvent):
    direction = event.get_plaintext().strip()
    user_id = event.get_user_id()

    # 频率限制检查
    allowed, error_msg = check_action_limit(user_id, "move")
    if not allowed:
        await move_cmd.finish(error_msg)

    # 记录操作
    record_action(user_id, "move")

    async with retry_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player or player.region == "大都会":
            await move_cmd.finish("⛔ 单格移动只能在诡域使用")

        # 解析方向
        if direction not in DIRECTIONS:
            await move_cmd.finish("⛔ 无效的方向")
        dx, dy = DIRECTIONS[direction]
        new_x, new_y = player.x + dx, player.y + dy
        player.x, player.y = new_x, new_y

        # 根据诡域等级扣除理智
        region_config = config.map_config["regions"].get(player.region, {})
        mp_cost = region_config.get("mp_cost", 1)  # 默认消耗1点理智

        if player.mp < mp_cost:
            await move_cmd.finish(f"⛔ 理智不足以在此诡域移动，需要 {mp_cost} 点理智，当前 {player.mp}")

        player.mp = max(0, player.mp - mp_cost)
        if player.mp == 0 and player.hp > 0:
            player.hp = 0  # 理智耗尽即"疯狂身亡"

        # 获取当前位置事件格
        tile = await get_or_create_tile(session, player.region, player.x, player.y)

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
                return f"✨ 你发现了材料 {item_name} ✖️{qty}，可输入 [收集] 获取。"
            elif t.event_type == "TREASURE":
                if t.state.get("looted"):
                    return "🪨 破碎的宝箱静静躺在尘埃中，没有任何价值。"
                return "🎁 你注意到一个尘封宝箱，输入 [探索] 能打开它。"
            elif t.event_type == "EMPTY":
                if player.id in t.state.get("defeated_by", []):
                    return "🪨 这里只剩下怪物的残骸，散发着淡淡的血腥味。"
                monster = t.state.get("name")
                return f"🌫️ 四周弥漫着诡异的静谧，似乎潜伏着 {monster} 的气息。若想冒险，可输入 [探索] 进行调查。"
            elif t.event_type == "REST":
                return "🌫️ 你发现了一家驿站，可输入 [探索] 恢复生命。"
            elif t.event_type == "MERCHANT":
                if player.id in t.state.get("visited_by", []):
                    return "🏪 卖货郎已经离开了，只留下空荡荡的摊位。"
                return "🏪 你遇到了神秘卖货郎，输入 [探索] 查看他的商品。"
            elif t.event_type == "ELITE":
                if player.id in t.state.get("defeated_by", []):
                    return "⚰️ 精英怪的残骸散落一地，散发着不祥的气息。"
                monster_name = t.state.get("name", "精英怪物")
                return f"⚔️ 你感受到强大的威压，{monster_name} 正虎视眈眈地盯着你！输入 [探索] 迎战。"
            return "⁉️ 未知事件。"

        event_desc = describe_tile(tile)
        header = f"🚶 已移动至 ({new_x},{new_y})"
        await move_cmd.finish(message_add_head(f"{header}\n{event_desc}{auto_collect_msg}", event))

# ----------------- 指令：战斗 -----------------
explore_cmd = on_command("探索", aliases={"战斗", "收集", "休息"}, block=True, priority=5)

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
    base_msg += "\n⬇️ 【图鉴 <物品名>】 查看描述"
    return base_msg


async def _handle_treasure(session, tile: WorldTile, player: Player) -> str:
    if tile.state.get("looted"):
        return "🪨 雕塑的暗格已被掏空，徒留潮湿指印。"
    # 添加时间戳确保每次开启宝箱都有不同的奖励
    import time
    treasure_timestamp = int(time.time() * 1000)
    rng = random.Random(hash(f"{tile.seed}:{player.id}:{treasure_timestamp}"))
    base_gold = rng.randint(100, 1000)
    from ..utils import luck_prob
    multiplier = 1 + luck_prob(player.luck)  # 1~2 倍区间
    gold_gain = int(base_gold * multiplier)
    player.gold += gold_gain
    tile.state["looted"] = True
    session.add_all([player, tile])
    await session.flush()
    msg = f"🔑 你在龟裂神像内抠出 {base_gold}💰！"
    if multiplier > 1.01:
        msg += f"\n🍀幸运改写中...金币变为{gold_gain}！"
    return msg


async def _handle_empty(session, tile: WorldTile, player: Player) -> str:
    # 检查玩家是否已经击败过这个小怪
    if player.id in tile.state.get("defeated_by", []):
        return "🪨 这里只剩下怪物的残骸，散发着淡淡的血腥味。"
    # empty格有遇到个人的怪物，但不会影响公共事件
    return await _handle_personal_monster(session, tile, player)


async def _handle_personal_monster(session, tile: WorldTile, player: Player) -> str:
    """小怪属于个人事件，使用新战斗系统进行战斗。"""
    # 获取怪物信息
    monster_stats = {
        "hp": tile.state.get("hp", 0),
        "attack": tile.state.get("attack", 0),
        "agility": tile.state.get("agility", 0),
        "defense": 0  # 怪物默认无防御
    }
    monster_name = tile.state.get("name", "未知诡影")
    monster_level = tile.state.get("level", 1)
    monster_display = f"{monster_name}(Lv{monster_level})"

    # 使用新战斗系统
    from ..battle.integration_helper import BattleIntegrationHelper

    # 创建战斗种子 - 添加时间戳确保每次战斗都有不同的随机序列
    import time
    battle_timestamp = int(time.time() * 1000)  # 毫秒级时间戳
    seed = f"P_{tile.seed}:{player.id}:{battle_timestamp}"

    # 执行增强战斗
    victory, battle_log, damage_taken = BattleIntegrationHelper.enhanced_player_vs_monster_battle(
        player, monster_stats, monster_display, seed=seed, max_rounds=100
    )

    # 更新玩家血量
    player.hp = max(0, player.hp - damage_taken)

    # 使用战斗日志作为基础，添加额外信息
    battle_summary = battle_log.copy()

    # 处理战斗结果
    if victory:
        # 胜利处理 - 使用新的时间戳确保每次掉落都不同
        import random
        drop_timestamp = int(time.time() * 1000)  # 毫秒级时间戳
        rng = random.Random(hash(f"P_{tile.seed}:{player.id}:{drop_timestamp}"))
        exp_gain = rng.randint(1, 4) * monster_level
        player.exp += exp_gain
        battle_summary.append(f"🎉 你击杀了 {monster_display}，获得 {exp_gain} EXP")

        # 更新战斗胜利统计（用于公会任务）
        if player.guild_id:
            from ..guild.guild_task_service import GuildTaskService
            await GuildTaskService.update_combat_victory_stats(session, player.id)

        # 怪物掉落材料机制
        is_elite = tile.state.get("is_elite", False)
        drop_result = await handle_monster_drops(session, player, monster_level, player.region, rng, is_elite)
        if drop_result:
            battle_summary.append(drop_result)

        # 标记为已击败（无论是精英怪还是普通小怪）
        tile.state.setdefault("defeated_by", []).append(player.id)

    elif player.hp <= 0:
        battle_summary.append(f"💀 你被 {monster_display} 击败，很遗憾，你已死亡")

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
            # 还原玩家属性
            delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
            for k, v in delta.items():
                setattr(player, k, getattr(player, k) - v)
            broken_msgs.append(f"💔 {eq.config.name} 耐久耗尽，化为尘埃！")
            await session.delete(eq)

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
            battle_summary.append(f"💔 装备损坏导致体质下降，失去 {hp_loss_from_equipment} HP")
        if mp_loss_from_equipment > 0:
            battle_summary.append(f"💔 装备损坏导致智力下降，失去 {mp_loss_from_equipment} MP")

    log = "\n".join(battle_summary)

    # ---------------- 检查装备耐久度并提醒 ----------------
    durability_warning = await check_equipment_durability(session, player.id)
    if durability_warning:
        log += f"\n{durability_warning}"

    session.add_all([player, tile])
    await session.flush()
    return log

async def _handle_rest(session, tile: WorldTile, player: Player) -> str:
    player.hp = player.max_hp
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

    msg = (
        "🏪 神秘卖货郎：\n"
        "━━━━━━━━━━━━━\n"
        "「旅者，需要些稀有材料吗？」\n"
        + "\n".join(goods_display) +
        "\n━━━━━━━━━━━━━\n"
        "💡 使用【购买 序号】购买商品\n"
        "⚠️ 每人只能访问一次"
    )

    # 标记玩家已访问
    tile.state.setdefault("visited_by", []).append(player.id)
    session.add(tile)
    await session.flush()

    return msg

async def _handle_elite(session, tile: WorldTile, player: Player) -> str:
    """处理精英怪事件"""
    if player.id in tile.state.get("defeated_by", []):
        return "⚰️ 精英怪的残骸散落一地，散发着不祥的气息。"

    # 使用与普通怪物相同的战斗逻辑，但精英怪更强
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

    # 频率限制检查
    allowed, error_msg = check_action_limit(user_id, "explore")
    if not allowed:
        await explore_cmd.finish(error_msg)

    # 记录操作
    record_action(user_id, "explore")

    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await explore_cmd.finish("⛔ 请先创建角色")
        if player.region == "大都会":
            await explore_cmd.finish("⛔ 你已经返回现实")
        if player.hp <= 0:
            await explore_cmd.finish("💀 你已死亡，返回现实吧，或者你有复活道具..."
                                     "\n⬇️ 【返回】 退出副本"
                                     "\n⬇️ 【使用 还魂丹】 原地复活，继续副本")

        tile = await get_or_create_tile(session, player.region, player.x, player.y)
        log = await EVENT_HANDLERS[tile.event_type](session, tile, player)

        # 更新探索统计（用于公会任务）
        if player.guild_id:
            from ..guild.guild_task_service import GuildTaskService
            await GuildTaskService.update_exploration_stats(session, player.id)

            # 尝试自动完成任务
            completed_tasks = await GuildTaskService.try_auto_complete_tasks(session, player.id)
            if completed_tasks:
                log += "\n\n🎉 公会任务完成：\n" + "\n".join(completed_tasks)

        await session.commit()

    header = f"🧭位置 {player.region} ({player.x},{player.y})"
    await explore_cmd.finish(f"{header}\n{log}")

# ==================== 购买指令 ====================
buy_cmd = on_command("购买", block=True, priority=5)

@buy_cmd.handle()
async def handle_buy(event: MessageEvent, args: Message = CommandArg()):
    """从卖货郎处购买商品"""
    try:
        item_index = int(args.extract_plain_text().strip())
    except ValueError:
        return

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await buy_cmd.finish("⛔ 请先创建角色")

        if player.region == "大都会":
            await buy_cmd.finish("⛔ 现实世界没有卖货郎")

        # 获取当前位置的格子
        tile = await get_or_create_tile(session, player.region, player.x, player.y)

        if tile.event_type != "MERCHANT":
            await buy_cmd.finish("⛔ 这里没有卖货郎")

        if player.id not in tile.state.get("visited_by", []):
            await buy_cmd.finish("⛔ 你还没有与卖货郎交谈，请先【探索】")

        # 检查玩家是否已经购买过商品
        purchased_by = tile.state.get("purchased_by", [])
        if player.id in purchased_by:
            await buy_cmd.finish("⛔ 你已经从这个卖货郎处购买过商品了，每人只能购买一次")

        goods = tile.state.get("goods", [])
        if not goods or item_index < 1 or item_index > len(goods):
            await buy_cmd.finish("⛔ 商品序号无效")

        good = goods[item_index - 1]
        item_config = config.items_config["by_id"].get(good["item_id"])
        if not item_config:
            await buy_cmd.finish("⛔ 商品不存在")

        # 检查金币是否足够
        if player.gold < good["price"]:
            await buy_cmd.finish(f"⛔ 金币不足，需要 {good['price']}💰，当前 {player.gold}💰")

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
            await buy_cmd.finish(message_add_head(msg, event))

        except ValueError as e:
            await buy_cmd.finish(f"⛔ 购买失败：{e}")


teleport_list = on_command("诡域", aliases={"副本列表"}, block=True, priority=5)
@teleport_list.handle()
async def handle_teleport_list(event: MessageEvent):
    """显示所有可传送的地点"""
    async with safe_session() as session:
        # 检查玩家是否存在
        player = await session.get(Player, event.get_user_id())
        if not player:
            await teleport_list.finish("⛔ 请先创建角色")

        # 获取所有可传送地点，按等级要求排序
        regions = config.map_config["regions"]
        sorted_regions = sorted(regions.items(), key=lambda x: x[1].get("required_level", 1))

        locations = []
        for name, region_config in sorted_regions:
            required_level = region_config.get("required_level", 1)
            tier = region_config.get("tier", 1)
            mp_cost = region_config.get("mp_cost", 1)

            # 检查玩家是否满足等级要求
            if player.level >= required_level:
                status = "✅"
            else:
                status = "🔒"

            locations.append(f"{status} {name} (Lv.{required_level}+ 理智-{mp_cost})")

        # 格式化消息
        msg = (
            "🪐 诡域传送列表：\n"
            "━━━━━━━━━━━━━\n"
            + "\n".join(locations)
            + "\n━━━━━━━━━━━━━\n"
            "📌 使用方式：传送 <诡域名>\n"
            "📦 需要消耗咒抗1点\n"
            "✅可进入 🔒等级不足"
        )

        await teleport_list.finish(message_add_head(msg, event))


# ==================== 诡域探索概览图片生成 ====================
region_overview_cmd = on_command("俯瞰", aliases={"感知"}, block=True, priority=5)


async def generate_region_overview_image(region: str, session, player_x: int = None, player_y: int = None) -> tuple[bytes, tuple[int, int, int, int]]:
    """生成指定诡域的今日探索概览图片"""
    today = date.today()

    # 获取今日该诡域的所有格子数据
    from sqlalchemy import and_

    # 计算今日的开始和结束时间
    today_start = datetime.combine(today, datetime.min.time())
    tomorrow_start = today_start + timedelta(days=1)

    stmt = select(WorldTile).where(
        and_(
            WorldTile.region == region,
            WorldTile.refreshed_at >= today_start,
            WorldTile.refreshed_at < tomorrow_start
        )
    )
    result = await session.execute(stmt)
    today_tiles = result.scalars().all()

    # 如果今天没有格子数据，查询历史格子数据作为参考来确定地图范围
    if not today_tiles:
        # 查询该区域的所有历史格子
        stmt_all = select(WorldTile).where(WorldTile.region == region)
        result_all = await session.execute(stmt_all)
        all_tiles = result_all.scalars().all()

        if all_tiles:
            # 使用历史格子的坐标范围，但不生成新格子
            # 只是为了确定地图显示范围
            min_x = min(tile.x for tile in all_tiles)
            max_x = max(tile.x for tile in all_tiles)
            min_y = min(tile.y for tile in all_tiles)
            max_y = max(tile.y for tile in all_tiles)
            tiles = today_tiles  # 保持为空列表，表示今天没有格子
        else:
            # 如果完全没有历史数据，使用玩家位置作为中心生成小范围
            center_x, center_y = 0, 0  # 默认中心点
            if player_x is not None and player_y is not None:
                center_x, center_y = player_x, player_y

            # 设置一个小范围的坐标
            min_x, max_x = center_x - 2, center_x + 2
            min_y, max_y = center_y - 2, center_y + 2
            tiles = today_tiles  # 保持为空列表
    else:
        tiles = today_tiles
        # 计算坐标范围
        min_x = min(tile.x for tile in tiles)
        max_x = max(tile.x for tile in tiles)
        min_y = min(tile.y for tile in tiles)
        max_y = max(tile.y for tile in tiles)

    # 验证和修正坐标范围
    if min_x > max_x:
        min_x, max_x = max_x, min_x
    if min_y > max_y:
        min_y, max_y = max_y, min_y

    # 扩展范围以显示更多区域（如果有格子的话）
    if tiles:
        range_x = max_x - min_x + 1
        range_y = max_y - min_y + 1

        # 确保最小显示范围
        if range_x < 20:
            center_x = (min_x + max_x) // 2
            min_x = center_x - 10
            max_x = center_x + 10
        if range_y < 20:
            center_y = (min_y + max_y) // 2
            min_y = center_y - 10
            max_y = center_y + 10

    # 最终验证坐标范围的有效性
    if min_x >= max_x:
        max_x = min_x + 20
    if min_y >= max_y:
        max_y = min_y + 20

    # 创建图片 - 为坐标轴预留空间
    margin = 40  # 边缘留白用于显示坐标
    img_width = 1000
    img_height = 1000
    img = Image.new('RGB', (img_width, img_height), color='#1a1a1a')  # 深色背景
    draw = ImageDraw.Draw(img)

    # 尝试加载字体，如果失败则使用默认字体
    try:
        # 使用系统默认字体
        font = ImageFont.load_default()
    except Exception:
        font = None

    # 计算格子大小 - 减去边缘空间
    grid_width = max_x - min_x + 1
    grid_height = max_y - min_y + 1
    available_width = img_width - 2 * margin
    available_height = img_height - 2 * margin

    # 防止除零错误
    if grid_width <= 0:
        grid_width = 1
    if grid_height <= 0:
        grid_height = 1

    cell_width = available_width // grid_width
    cell_height = available_height // grid_height

    # 确保格子大小至少为1像素
    if cell_width <= 0:
        cell_width = 1
    if cell_height <= 0:
        cell_height = 1

    # 事件类型颜色映射
    event_colors = {
        'MATERIAL': '#4CAF50',    # 绿色 - 材料
        'TREASURE': '#FFD700',    # 金色 - 宝藏
        'EMPTY': '#F44336',       # 红色 - 怪物
        'REST': '#2196F3',        # 蓝色 - 休息点
        'MERCHANT': '#9C27B0',    # 紫色 - 商人
        'ELITE': '#FF5722',       # 深橙色 - 精英怪
    }

    # 创建格子坐标到tile的映射
    tile_map = {(tile.x, tile.y): tile for tile in tiles}

    # 绘制格子
    for grid_x in range(grid_width):
        for grid_y in range(grid_height):
            world_x = min_x + grid_x
            world_y = min_y + grid_y

            # 计算像素坐标 - 加上边距偏移
            pixel_x = margin + grid_x * cell_width
            pixel_y = margin + grid_y * cell_height

            tile = tile_map.get((world_x, world_y))

            if tile:
                # 根据事件类型选择颜色，不区分消耗状态
                color = event_colors.get(tile.event_type, '#666666')
            else:
                # 未探索的区域使用深灰色
                color = '#333333'

            # 绘制格子 - 确保坐标正确
            x1 = pixel_x
            y1 = pixel_y
            x2 = pixel_x + cell_width - 1
            y2 = pixel_y + cell_height - 1

            # 确保 x2 >= x1 和 y2 >= y1
            if x2 < x1:
                x1, x2 = x2, x1
            if y2 < y1:
                y1, y2 = y2, y1

            draw.rectangle([x1, y1, x2, y2], fill=color, outline='#555555')

    # 绘制玩家位置标记
    if player_x is not None and player_y is not None:
        # 检查玩家位置是否在当前显示范围内
        if min_x <= player_x <= max_x and min_y <= player_y <= max_y:
            # 计算玩家位置的像素坐标
            player_grid_x = player_x - min_x
            player_grid_y = player_y - min_y
            player_pixel_x = margin + player_grid_x * cell_width
            player_pixel_y = margin + player_grid_y * cell_height

            # 绘制玩家位置标记 - 使用亮黄色圆形
            center_x = player_pixel_x + cell_width // 2
            center_y = player_pixel_y + cell_height // 2
            radius = min(cell_width, cell_height) // 3

            # 绘制外圈（白色边框）
            draw.ellipse([
                center_x - radius - 2, center_y - radius - 2,
                center_x + radius + 2, center_y + radius + 2
            ], fill='#FFFFFF', outline='#FFFFFF')

            # 绘制内圈（亮黄色）
            draw.ellipse([
                center_x - radius, center_y - radius,
                center_x + radius, center_y + radius
            ], fill='#FFFF00', outline='#FFD700')

    # 绘制坐标轴数字
    if font:
        # 绘制X轴坐标（顶部和底部）
        step_x = max(1, grid_width // 10)  # 最多显示10个X坐标
        for i in range(0, grid_width, step_x):
            world_x = min_x + i
            pixel_x = margin + i * cell_width + cell_width // 2

            # 顶部X坐标
            draw.text((pixel_x, 5), str(world_x), fill='#FFFFFF', font=font, anchor='mt')
            # 底部X坐标
            draw.text((pixel_x, img_height - 20), str(world_x), fill='#FFFFFF', font=font, anchor='mb')

        # 绘制Y轴坐标（左侧和右侧）
        step_y = max(1, grid_height // 10)  # 最多显示10个Y坐标
        for i in range(0, grid_height, step_y):
            world_y = min_y + i
            pixel_y = margin + i * cell_height + cell_height // 2

            # 左侧Y坐标
            draw.text((5, pixel_y), str(world_y), fill='#FFFFFF', font=font, anchor='lm')
            # 右侧Y坐标
            draw.text((img_width - 5, pixel_y), str(world_y), fill='#FFFFFF', font=font, anchor='rm')

    # 将图片转换为字节流
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    return img_buffer.getvalue(), (min_x, max_x, min_y, max_y)


@region_overview_cmd.handle()
async def handle_region_overview(event: MessageEvent, args: Message = CommandArg()):
    """生成诡域探索概览图片"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await region_overview_cmd.finish("⛔ 请先创建角色")

        # 获取参数
        arg_text = args.extract_plain_text().strip()

        # 如果没有指定诡域，使用当前诡域
        if not arg_text:
            if player.region == "大都会":
                await region_overview_cmd.finish("⛔ 请指定要查看的诡域名称，或先传送到诡域中")
            region = player.region
        else:
            region = arg_text
            # 检查诡域是否存在
            if region not in config.map_config["regions"]:
                await region_overview_cmd.finish("⛔ 未知的诡域名称")

        try:
            # 生成概览图片，传入玩家坐标（如果玩家在当前诡域）
            player_x, player_y = None, None
            if player.region == region:
                player_x, player_y = player.x, player.y

            img_data, (min_x, max_x, min_y, max_y) = await generate_region_overview_image(region, session, player_x, player_y)

            # 转换为base64
            img_b64 = base64.b64encode(img_data).decode('utf-8')

            # 构建消息
            region_config = config.map_config["regions"].get(region, {})
            tier = region_config.get("tier", 1)
            level_range = region_config.get("level_range", [1, 1])

            # 构建说明文字
            msg_lines = [
                f"🗺️ {region} 今日探索小地图",
                "━━━━━━━━━━━━━",
                f"📊 诡域等级：Tier {tier}",
                f"⚔️ 怪物等级：{level_range[0]}-{level_range[1]}级",
                f"📍 坐标范围：X({min_x}~{max_x}) Y({min_y}~{max_y})",
                "━━━━━━━━━━━━━",
                "🟢 绿色：材料格子",
                "🟡 金色：宝藏格子",
                "🔴 红色：怪物格子",
                "🔵 蓝色：休息格子",
                "🟣 紫色：商人格子",
                "🟠 橙色：精英怪格子",
                "⬛ 灰色：未探索区域"
            ]

            # 如果玩家在当前诡域，添加位置说明
            if player.region == region:
                msg_lines.append(f"🟡 亮黄圆圈：你的位置 ({player.x},{player.y})")

            msg_lines.append("🔢 图片边缘显示坐标数字")

            msg_text = "\n".join(msg_lines)

            # 发送图片和文字
            img_segment = MessageSegment.file_image(img_b64)
            message = Message(msg_text).append(img_segment)

            await region_overview_cmd.finish(message_add_head(message, event))

        except ValueError as e:
            await region_overview_cmd.finish(f"⛔ 生成概览图片失败：{str(e)}")