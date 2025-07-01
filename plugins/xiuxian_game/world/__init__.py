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
from ..utils import message_add_head
from io import BytesIO
import base64
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import os
from sqlalchemy import select as _select
from ..models.equipment import EquipmentInstance as _Equip

# ----------------- 常量 -----------------
DIRECTIONS: Dict[str, Tuple[int, int]] = {
    "上": (0, 1),
    "下": (0, -1),
    "左": (-1, 0),
    "右": (1, 0),
}

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
            item_id = rng.choice(config.items_config["by_type"]["MATERIAL"])
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
                return f"✨ 你发现地面闪烁着 {item_name} ✖️{qty} 的微光，可输入 [收集] 获取。"
            elif t.event_type == "TREASURE":
                if t.state.get("looted"):
                    return "🪨 破碎的宝箱静静躺在尘埃中，没有任何价值。"
                return "🎁 你注意到一个尘封宝箱，也许输入 [探索] 能打开它。"
            elif t.event_type == "EMPTY":
                monster = t.state.get("name")
                return f"🌫️ 四周弥漫着诡异的静谧，似乎潜伏着 {monster} 的气息。若想冒险，可输入 [探索] 进行调查。"
            elif t.event_type == "REST":
                return "🌫️ 你发现这里有一张床，也许输入 [休息] 能恢复状态。"
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
    
    return f"✨ 你采集到了 {item_cfg.name} ✖️{quantity}！"


async def _handle_treasure(session, tile: WorldTile, player: Player) -> str:
    if tile.state.get("looted"):
        return "🪨 雕塑的暗格已被掏空，徒留潮湿指印。"
    rng = random.Random(hash(tile.seed))
    gold_gain = rng.randint(50, 150)
    player.gold += gold_gain
    tile.state["looted"] = True
    session.add_all([player, tile])
    await session.flush()
    return f"🔑 你在龟裂神像内抠出 {gold_gain}💰！"


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
            if rng.random() < player.luck / 100:
                dmg = int(dmg*1.5)
                crit = True
            monster_hp = max(0, monster_hp - dmg)
            record_p(r_idx, f"[回合{r_idx}] {'💥 暴击！' if crit else ''}你斩击 {monster_display}，造成 {dmg} 伤害。", force=(crit or monster_hp==0))

        def m_atk(r_idx):
            nonlocal player_hp
            dmg = rng.randint(int(monster_attack*0.8), int(monster_attack*1.2))
            player_hp = max(0, player_hp - dmg)
            record_p(r_idx, f"[回合{r_idx}] {monster_display} 反击你，造成 {dmg} 伤害！", force=(player_hp==0))

        if player_first:
            p_atk(round_num)
            if monster_hp>0:
                m_atk(round_num)
        else:
            m_atk(round_num)
            if player_hp>0:
                p_atk(round_num)

    battle_log.append(f"📊 总计 {round_num} 回合，你剩余HP {player_hp}/{player.max_hp}，{monster_display} HP {monster_hp}/{tile.state.get('hp', 0)}。")
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
            broken_msgs.append(f"💔 {eq.template.name} 耐久耗尽，化为尘埃！")
            await session.delete(eq)
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

# ----------------- 指令：区域小地图 -----------------
region_map_cmd = on_command("区域图", aliases={"小地图", "区域地图"}, block=True, priority=5)

# 小地图颜色配置
_TILE_COLORS = {
    "MATERIAL": (76, 175, 80),   # 绿色
    "TREASURE": (255, 193, 7),   # 黄色
    "EMPTY": (158, 158, 158),    # 灰色
}
_PLAYER_COLOR = (244, 67, 54)    # 红色

# ----------------- 内部工具：字体加载 -----------------

def _load_font(size: int = 24) -> ImageFont.ImageFont:
    """尝试加载支持中文的系统字体，若失败则回退默认字体。"""
    candidates = [
        # Windows 常见中文字体
        Path("C:/Windows/Fonts/msyh.ttc"),  # 微软雅黑
        Path("C:/Windows/Fonts/simhei.ttf"),  # 黑体
        Path("C:/Windows/Fonts/simsun.ttc"),  # 宋体

        # Linux 常见中文字体
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK.ttc"),

        # 通用 sans 字体
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]

    # 若用户自定义字体路径，可通过环境变量 FONT_PATH 指定
    env_font = os.getenv("FONT_PATH")
    if env_font:
        candidates.insert(0, Path(env_font))

    for p in candidates:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size=size)
            except Exception:
                continue
    return ImageFont.load_default()

@region_map_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await region_map_cmd.finish("⛔ 请先创建角色")

        # 获取当前区域已生成的所有格子
        result = await session.execute(
            select(WorldTile).where(WorldTile.region == player.region)
        )
        tiles = result.scalars().all()

        # 若尚无任何格子，则确保包含玩家当前所在格
        if not tiles:
            tile = await get_or_create_tile(session, player.region, player.x, player.y)
            tiles.append(tile)

        # 统计边界范围
        xs = [t.x for t in tiles] + [player.x]
        ys = [t.y for t in tiles] + [player.y]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        # 绘图参数
        cell_size = 60
        padding = 6
        cols = max_x - min_x + 1
        rows = max_y - min_y + 1
        legend_height = 80  # 图例区域高度
        title_height = 40   # 标题区域高度

        img_w = cols * cell_size + (cols + 1) * padding
        img_h = rows * cell_size + (rows + 1) * padding + legend_height + title_height

        bg_color = (245, 245, 245)
        img = Image.new("RGBA", (img_w, img_h), bg_color)
        draw = ImageDraw.Draw(img)
        font = _load_font(24)
        small_font = _load_font(20)

        # 绘制标题
        title_text = f"『{player.region}』区域小地图"
        bbox = draw.textbbox((0, 0), title_text, font=font)
        draw.text(((img_w - (bbox[2] - bbox[0])) / 2, 10), title_text, fill=(33, 33, 33), font=font)

        # 起始 y 偏移（跳过标题区域）
        origin_y = title_height + padding
        origin_x = padding

        tile_map = {(t.x, t.y): t for t in tiles}

        for x in range(min_x, max_x + 1):
            for y in range(min_y, max_y + 1):
                # 将游戏坐标转换为图像坐标（y 轴向上为正）
                left = origin_x + (x - min_x) * (cell_size + padding)
                top = origin_y + (max_y - y) * (cell_size + padding)
                right = left + cell_size
                bottom = top + cell_size

                if (x, y) == (player.x, player.y):
                    fill_color = _PLAYER_COLOR
                    text = "你"
                elif (x, y) in tile_map:
                    event_type = tile_map[(x, y)].event_type
                    fill_color = _TILE_COLORS.get(event_type, (200, 200, 200))
                    text = {
                        "MATERIAL": "材",
                        "TREASURE": "宝",
                        "EMPTY": "",
                    }.get(event_type, "")
                else:
                    fill_color = (230, 230, 230)
                    text = ""

                # 绘制圆角矩形
                try:
                    draw.rounded_rectangle([left, top, right, bottom], radius=8, fill=fill_color, outline=(120, 120, 120))
                except AttributeError:
                    # Pillow 9 及以下无 rounded_rectangle
                    draw.rectangle([left, top, right, bottom], fill=fill_color, outline=(120, 120, 120))

                if text:
                    # Pillow>=10 移除 textsize，改用 textbbox 计算文本尺寸
                    bbox = draw.textbbox((0, 0), text, font=font)
                    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
                    draw.text(
                        (left + (cell_size - w) / 2, top + (cell_size - h) / 2),
                        text,
                        fill=(255, 255, 255) if (x, y) == (player.x, player.y) else (33, 33, 33),
                        font=font,
                    )

        # 绘制图例
        legend_top = img_h - legend_height + 15
        legend_items = [
            ("你", _PLAYER_COLOR, "玩家位置"),
            ("材", _TILE_COLORS["MATERIAL"], "材料"),
            ("宝", _TILE_COLORS["TREASURE"], "宝箱"),
        ]
        legend_padding = 20
        cur_x = legend_padding
        for symbol, color, label in legend_items:
            rect_w = rect_h = 30
            draw.rounded_rectangle([cur_x, legend_top, cur_x + rect_w, legend_top + rect_h], radius=6, fill=color, outline=(120, 120, 120))
            # 符号
            bbox = draw.textbbox((0, 0), symbol, font=small_font)
            sx = cur_x + (rect_w - (bbox[2] - bbox[0])) / 2
            sy = legend_top + (rect_h - (bbox[3] - bbox[1])) / 2
            draw.text((sx, sy), symbol, fill=(255, 255, 255) if symbol == "你" else (33, 33, 33), font=small_font)
            # 文字
            draw.text((cur_x + rect_w + 8, legend_top + 5), label, fill=(33, 33, 33), font=small_font)
            cur_x += rect_w + 8 + draw.textlength(label, font=small_font) + 32

        buf = BytesIO()
        img.save(buf, format="PNG")
        base64_img = base64.b64encode(buf.getvalue()).decode("utf-8")

    msg = Message()
    msg += MessageSegment.text(f"🗺️ 当前区域：{player.region}\n")
    msg += MessageSegment.file_image(base64_img)
    await region_map_cmd.finish(msg) 