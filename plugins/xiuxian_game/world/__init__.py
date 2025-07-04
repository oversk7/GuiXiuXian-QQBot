from __future__ import annotations

"""世界与坐标系统
1. 传送 <区域名> 切换区域并把坐标重置为 (0,0)
2. 前往 <上|下|左|右|x,y> 改变坐标（同区域内移动）
3. get_or_create_tile: 按天刷新、确定性种子生成事件（暂占位）
"""

from nonebot import on_command, on_regex
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.params import CommandArg
from typing import Tuple, Dict
from datetime import datetime, date
import random
from sqlalchemy import select, func
from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import Inventory
from ..models.world_tile import WorldTile
from ..config import config
from ..utils import message_add_head, luck_prob
from io import BytesIO
import base64
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import os
from sqlalchemy import select as _select
from ..models.equipment import EquipmentInstance as _Equip
from . import nearby_players  # 注册附近玩家指令

# ----------------- 常量 -----------------
DIRECTIONS: Dict[str, Tuple[int, int]] = {
    "上": (0, 1),
    "下": (0, -1),
    "左": (-1, 0),
    "右": (1, 0),
}

# -------- 预计算通用材料列表 --------
_all_materials = set(config.items_config["by_type"]["MATERIAL"])
_special_mats = set()
for _reg_info in config.map_config.get("regions", {}).values():
    _special_mats.update(_reg_info.get("materials", []) or [])

# 不在任何区域作为特产出现的材料视为通用材料
COMMON_MATERIALS = list(_all_materials - _special_mats)

# ----------------- 工具函数 -----------------
async def get_or_create_tile(session, region: str, x: int, y: int) -> WorldTile:
    """获取或创建今日坐标格，并在创建时生成事件"""
    today = date.today()
    # 查询并锁行，防止并发写
    result = await session.execute(
        select(WorldTile)
        .where(WorldTile.region == region, WorldTile.x == x, WorldTile.y == y)
        .with_for_update()
    )
    tile = result.scalars().first()

    # 若不存在或已过期（日期变化）则重新生成
    if (not tile) or (tile.refreshed_at.date() != today):
        if not tile:
            # 再查一次，防止并发唯一冲突
            result2 = await session.execute(
                select(WorldTile)
                .where(WorldTile.region == region, WorldTile.x == x, WorldTile.y == y)
            )
            tile = result2.scalars().first()
            if tile:
                return tile
            tile = WorldTile(region=region, x=x, y=y)
        tile.refreshed_at = datetime.now()
        # 生成事件
        tile.seed = f"{region}:{x}:{y}:{today.isoformat()}"
        rng = random.Random(hash(tile.seed))
        tile.event_type = rng.choices(
            ["MATERIAL", "TREASURE", "EMPTY", "REST"],
            weights=[15, 5, 75, 5],
            k=1
        )[0]
        tile.state = {}
        if tile.event_type == "EMPTY":
            map_info = config.map_config["regions"][region]
            monster = rng.choice(map_info["monsters"])
            monster_level = random.randint(map_info["level_range"][0], map_info["level_range"][1])
            tile.state = {
                "name": monster,
                "level": monster_level,
                "hp": rng.randint(10, 20) * monster_level,
                "attack": rng.randint(1, 5) * monster_level,
                "agility": rng.randint(1, 5) * monster_level,
            }
        elif tile.event_type == "TREASURE":
            tile.state = {"looted": False}
        elif tile.event_type == "MATERIAL":
            # 优先选择当前区域的特产材料，如无则回退到全局材料列表
            region_cfg = config.map_config["regions"].get(region, {})
            region_materials = region_cfg.get("materials") or []
            # 仅使用通用材料 + 本区域特产材料
            candidate_materials = COMMON_MATERIALS + region_materials
            # 若配置中写的是 ItemConfig 列表，需要转为 id；此处假设直接存放 item_id 字符串
            candidate_materials = list(dict.fromkeys(candidate_materials))
            item_id = rng.choice(candidate_materials)
            tile.state = {
                "item_id": item_id,
                "quantity": rng.randint(1, 3),
                "looted": False,
            }
        tile = await session.merge(tile)
        await session.flush()
    return tile


# ----------------- 指令：移动 -----------------
move_cmd = on_regex(r"^(上|下|左|右)$", block=True, priority=5)

@move_cmd.handle()
async def _(event: MessageEvent):
    direction = event.get_plaintext().strip()
    
    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await move_cmd.finish("⛔ 请先创建角色")

        # 解析方向
        if direction not in DIRECTIONS:
            await move_cmd.finish("⛔ 无效的方向")
        if player.stamina <= 0:
            await move_cmd.finish("⛔ 体力不足，无法移动")
        dx, dy = DIRECTIONS[direction]
        new_x, new_y = player.x + dx, player.y + dy
        player.x, player.y = new_x, new_y

        # 扣体力暂定
        # player.stamina -= 1
        # player.mp -= random.randint(0, 2)
        # player.mp = max(0, player.mp)

        # 获取当前位置事件格
        tile = await get_or_create_tile(session, player.region, player.x, player.y)

        session.add_all([player, tile])
        await session.commit()

        # 构造事件描述
        def describe_tile(t: WorldTile) -> str:
            """根据 tile 类型生成可读描述，在移动后提示玩家下一步操作。"""
            if t.event_type == "MATERIAL":
                item_cfg = config.items_config["by_id"].get(t.state.get("item_id"))
                item_name = item_cfg.name if item_cfg else "未知材料"
                qty = t.state.get("quantity", "?")
                if t.state.get("looted"):
                    return f"🪨 这里曾经散落着 {item_name} ✖️{qty}，但已被搜刮一空。"
                return f"✨ 你发现了材料 {item_name} ✖️{qty}，可输入 [收集] 获取。"
            elif t.event_type == "TREASURE":
                if t.state.get("looted"):
                    return "🪨 破碎的宝箱静静躺在尘埃中，没有任何价值。"
                return "🎁 你注意到一个尘封宝箱，也许输入 [探索] 能打开它。"
            elif t.event_type == "EMPTY":
                monster = t.state.get("name")
                return f"🌫️ 四周弥漫着诡异的静谧，似乎潜伏着 {monster} 的气息。若想冒险，可输入 [探索] 进行调查。"
            elif t.event_type == "REST":
                return "🌫️ 你发现了一家驿站，也许输入 [休息] 能恢复状态。"
            return "⁉️ 未知事件。"

        event_desc = describe_tile(tile)

    header = f"🚶 已移动至 ({new_x},{new_y})"
    await move_cmd.finish(message_add_head(f"{header}\n{event_desc}", event))

# ----------------- 指令：战斗 -----------------
explore_cmd = on_command("探索", aliases={"战斗", "收集", "休息"}, block=True, priority=5)

# 事件处理器映射
async def _handle_material(session, tile: WorldTile, player: Player) -> str:
    if tile.state.get("looted"):
        return "🪨 这里什么都没有了。"
    
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
    
    # 检查背包容量
    result = await session.execute(
        select(func.count(Inventory.id)).where(Inventory.player_id == player.id)
    )
    current_items = result.scalar() or 0
    
    # 检查是否已有该物品
    result = await session.execute(
        select(Inventory).where(
            Inventory.player_id == player.id,
            Inventory.item_id == item_id
        )
    )
    existing_item = result.scalars().first()
    
    # 如果是新物品且背包已满，则无法拾取
    if not existing_item and current_items >= player.inventory_capacity:
        return f"⚠️ 你的背包已满（{current_items}/{player.inventory_capacity}），无法拾取 {item_cfg.name}。"
    
    # 更新或创建物品记录
    if existing_item:
        existing_item.quantity += quantity
        session.add(existing_item)
    else:
        new_item = Inventory(
            player_id=player.id,
            item_id=item_id,
            quantity=quantity
        )
        session.add(new_item)
    
    # 标记为已拾取
    tile.state["looted"] = True
    session.add(tile)
    await session.flush()
    
    base_msg = f"✨ 你采集到了 {item_cfg.name} ✖️{quantity}!"
    if luck_bonus:
        base_msg += "\n🍀 幸运闪现！材料翻倍。"
    return base_msg


async def _handle_treasure(session, tile: WorldTile, player: Player) -> str:
    if tile.state.get("looted"):
        return "🪨 雕塑的暗格已被掏空，徒留潮湿指印。"
    rng = random.Random(hash(tile.seed))
    base_gold = rng.randint(100, 1000)
    from ..utils import luck_prob
    multiplier = 1 + luck_prob(player.luck)  # 1~2 倍区间
    gold_gain = int(base_gold * multiplier)
    player.gold += gold_gain
    tile.state["looted"] = True
    session.add_all([player, tile])
    await session.flush()
    msg = f"🔑 你在龟裂神像内抠出 {gold_gain}💰！"
    if multiplier > 1.01:
        msg += "\n🍀 幸运加成！宝箱更丰厚。"
    return msg


async def _handle_empty(session, tile: WorldTile, player: Player) -> str:
    # empty格有70%可能遇到个人的怪物，但不会影响公共事件
    if random.random() < 0.7:
        return await _handle_personal_monster(session, tile, player)
    return "🌫️ 什么都没有发现，除了回声……"


async def _handle_personal_monster(session, tile: WorldTile, player: Player) -> str:
    """小怪属于个人事件，自动战斗直至一方死亡，输出完整战报。"""
    rng = random.Random(hash(f"P_{tile.seed}:{player.id}"))
    monster_hp = tile.state.get("hp", 0)
    monster_name = tile.state.get("name", "未知诡影")
    monster_level = tile.state.get("level", 1)
    monster_attack = tile.state.get("attack", 0)
    monster_agility = tile.state.get("agility", 0)
    monster_display = f"{monster_name}(Lv{monster_level})"

    player_hp = player.hp
    max_round = 100
    battle_log = []
    dodge_count = 0  # 记录成功闪避次数

    def record_p(r_idx, text, force=False):
        if force or r_idx == 1 or r_idx % 5 == 0:
            battle_log.append(text)

    for round_num in range(1, max_round + 1):
        if monster_hp <= 0 or player_hp <= 0:
            break
        player_first = rng.random() < (player.agility / (player.agility + monster_agility))

        def p_atk(r_idx):
            nonlocal monster_hp
            dmg = max(1, int(player.attack * rng.uniform(0.8, 1.1)))
            crit = False
            from ..utils import luck_prob
            if rng.random() < luck_prob(player.luck):
                dmg = int(dmg*1.5)
                crit = True
            monster_hp = max(0, monster_hp - dmg)
            record_p(r_idx, f"[回合{r_idx}] {'💥 暴击！' if crit else ''}你斩击 {monster_display}，造成 {dmg} 伤害。", force=(crit or monster_hp==0))

        def m_atk(r_idx):
            nonlocal player_hp
            # 计算闪避：概率基于敏捷
            dodge_chance = player.agility / (player.agility + monster_agility + 20)  # +20 抑制极端
            if rng.random() < dodge_chance:
                nonlocal dodge_count
                dodge_count += 1
                record_p(r_idx, f"[回合{r_idx}] ⚡ 你敏捷地闪避了 {monster_display} 的攻击！")
                return

            dmg_raw = rng.randint(int(monster_attack*0.8), int(monster_attack*1.2))
            # 防御减伤：效果递减，且至少造成1点伤害
            dmg_after = max(1, int(dmg_raw * 100 / (100 + player.defense)))
            blocked = dmg_raw - dmg_after
            player_hp = max(0, player_hp - dmg_after)
            if blocked > 0:
                record_p(r_idx, f"[回合{r_idx}] {monster_display} 反击你，造成 {dmg_after} 伤害！（格挡 {blocked}）", force=(player_hp==0))
            else:
                record_p(r_idx, f"[回合{r_idx}] {monster_display} 反击你，造成 {dmg_after} 伤害！", force=(player_hp==0))

        if player_first:
            p_atk(round_num)
            if monster_hp>0:
                m_atk(round_num)
        else:
            m_atk(round_num)
            if player_hp>0:
                p_atk(round_num)

    battle_log.append(f"📊 总计 {round_num} 回合，你剩余HP {player_hp}/{player.max_hp}，{monster_display} HP {monster_hp}/{tile.state.get('hp', 0)}。")
    if dodge_count:
        battle_log.append(f"🌀 其中你成功闪避 {dodge_count} 次攻击！")
    log = "\n".join(battle_log)

    # 更新
    player.hp = player_hp

    # 结算
    if monster_hp <= 0:
        exp_gain = rng.randint(20, 30) * monster_level
        player.exp += exp_gain
        log += f"\n🎉 你击杀了 {monster_display}，获得 {exp_gain} EXP"
    elif player_hp <= 0:
        log += f"\n💀 你被 {monster_display} 击败，快去恢复吧！"
    else:
        log += f"\n👁️ {monster_display} 剩余 {monster_hp} HP"

    # ---------------- 扣除装备耐久 ----------------
    result_eq = await session.execute(
        _select(_Equip).where(_Equip.player_id == player.id, _Equip.equipped == True)
    )
    equipped_items = result_eq.scalars().all()
    broken_msgs = []
    for eq in equipped_items:
        if eq.lose_durability(1):
            # 还原玩家属性
            delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
            for k, v in delta.items():
                setattr(player, k, getattr(player, k) - v)
            broken_msgs.append(f"💔 {eq.template.name} 耐久耗尽，化为尘埃！")
            await session.delete(eq)
            # 修正HP/MP不超过上限
            if player.hp > player.max_hp:
                player.hp = player.max_hp
            if player.mp > player.max_mp:
                player.mp = player.max_mp
    if broken_msgs:
        log += "\n" + "\n".join(broken_msgs)

    session.add_all([player, tile])
    await session.flush()
    return log

async def _handle_rest(session, tile: WorldTile, player: Player) -> str:
    player.hp = player.max_hp
    session.add(player)
    await session.flush()
    return "🌫️ 你在这里休息了一晚，恢复了体力。"


EVENT_HANDLERS = {
    "MATERIAL": _handle_material,
    "TREASURE": _handle_treasure,
    "EMPTY": _handle_empty,
    "REST": _handle_rest,
}

@explore_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await explore_cmd.finish("⛔ 请先创建角色")

        tile = await get_or_create_tile(session, player.region, player.x, player.y)
        log = await EVENT_HANDLERS[tile.event_type](session, tile, player)
        await session.commit()

    header = f"🧭位置 {player.region} ({player.x},{player.y})"
    await explore_cmd.finish(f"{header}\n{log}")


teleport_list = on_command("地图", block=True, priority=5)
@teleport_list.handle()
async def handle_teleport_list(event: MessageEvent):
    """显示所有可传送的地点"""
    async with safe_session() as session:
        # 检查玩家是否存在
        player = await session.get(Player, event.get_user_id())
        if not player:
            await teleport_list.finish("⛔ 请先创建角色")

        # 获取所有可传送地点
        locations = [f"• {name} 🌐" for name in config.map_config["regions"].keys()]
        
        # 格式化消息
        msg = (
            "🪐 可传送区域列表：\n"
            + "\n".join(locations)
            + "\n\n📌 使用方式：传送 [区域]\n"
            "📦 需要消耗：传送符 ✖1"
        )
        
        await teleport_list.finish(message_add_head(msg, event))
        
# ----------------- 指令：跳跃（驿站快速移动） -----------------

# 仅在当前坐标为 REST(驿站) 时可使用。格式：跳跃 x y   或 跳跃 x,y

jump_cmd = on_command("跳跃", aliases={"瞬移", "传送坐标"}, block=True, priority=5)


@jump_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip().replace(",", " ")
    parts = [p for p in arg_text.split() if p]
    if len(parts) != 2 or not all(p.lstrip("-+ ").isdigit() for p in parts):
        await jump_cmd.finish("⛔ 格式：跳跃 x y  （示例：跳跃 3 -2）")

    target_x, target_y = map(int, parts)

    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await jump_cmd.finish("⛔ 请先创建角色")

        # 确认当前格子为驿站
        current_tile = await get_or_create_tile(session, player.region, player.x, player.y)
        if current_tile.event_type != "REST":
            await jump_cmd.finish("⛔ 只有在驿站才能使用 [跳跃] 指令！")

        # 执行跳跃
        player.x = target_x
        player.y = target_y

        # 获取目标格事件，若首次则生成
        target_tile = await get_or_create_tile(session, player.region, player.x, player.y)

        # 构造描述复用 describe_tile 内部逻辑
        def _desc_tile(t: WorldTile) -> str:
            if t.event_type == "MATERIAL":
                item_cfg = config.items_config["by_id"].get(t.state.get("item_id"))
                item_name = item_cfg.name if item_cfg else "未知材料"
                qty = t.state.get("quantity", "?")
                return f"✨ 你抵达后发现 {item_name} ✖️{qty} 的微光。输入 [收集] 获取。"
            elif t.event_type == "TREASURE":
                return "🎁 你抵达后看见一个尘封宝箱，输入 [探索] 调查。"
            elif t.event_type == "EMPTY":
                monster = t.state.get("name", "未知")
                return f"🌫️ 周围寂静，似乎潜伏着 {monster}。"
            elif t.event_type == "REST":
                return "🏠 你抵达另一家驿站，可输入 [休息] 恢复。"
            return "⁉️ 未知事件。"

        session.add(player)
        await session.commit()

        await jump_cmd.finish(message_add_head(f"🚀 已跳跃至 ({target_x},{target_y})\n{_desc_tile(target_tile)}", event)) 