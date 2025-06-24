from __future__ import annotations

"""世界与坐标系统
1. 传送 <区域名> 切换区域并把坐标重置为 (0,0)
2. 前往 <上|下|左|右|x,y> 改变坐标（同区域内移动）
3. get_or_create_tile: 按天刷新、确定性种子生成事件（暂占位）
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from typing import Tuple, Dict
from datetime import datetime, date
import random
from sqlalchemy import select
from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import Inventory
from ..models.world_tile import WorldTile
from ..config import config
from ..utils import create_rich_message

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
            ["ELITE", "TREASURE", "EMPTY"],
            weights=[20, 5, 75],
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
        elif tile.event_type == "ELITE":
            tile.state = {
                "name": "精英怪",
                "level": monster_level,
                "hp": rng.randint(10, 20) * monster_level,
                "attack": rng.randint(1, 5) * monster_level,
                "agility": rng.randint(1, 5) * monster_level + 10,
            }
        await session.merge(tile)
        await session.flush()
    return tile

travel_cmd = on_command("传送", block=True, priority=5)

@travel_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    target_region = args.extract_plain_text().strip()
    if not target_region:
        await travel_cmd.finish("⛔ 请指定目标区域，例如：传送 旧港雾巢")

    # 验证区域
    valid_regions = list(config.map_config["regions"].keys())
    if target_region not in valid_regions:
        await travel_cmd.finish("⛔ 目的地不存在，可发送 /地图 查看全部区域")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await travel_cmd.finish("⛔ 请先创建角色")

        # 检查传说券
        legend_ticket_cfg = config.items_config["by_name"].get("传说券")
        if not legend_ticket_cfg:
            await travel_cmd.finish("⚠️ 配置缺少 传送券")
        result = await session.execute(
            select(Inventory)
            .where(Inventory.player_id == player.id)
            .where(Inventory.item_id == legend_ticket_cfg.item_id)
        )
        ticket = result.scalars().first()
        if not ticket or ticket.quantity < 1:
            await travel_cmd.finish("⛔ 传送券不足，无法启程")

        # 扣除并移动
        ticket.quantity -= 1
        if ticket.quantity <= 0:
            await session.delete(ticket)
        player.region = target_region
        player.x = 0
        player.y = 0
        session.add_all([player])
        await session.commit()

    msg = (
        f"🪄 你使用了一张传送券，穿过层层迷雾抵达『{target_region}』！\n"
        f"当前位置：({player.x},{player.y})"
    )
    await travel_cmd.finish(create_rich_message(msg, event))

# ----------------- 指令：前往 -----------------
move_cmd = on_command("前往", block=True, priority=5)

@move_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    if not arg:
        await move_cmd.finish("⛔ 请输入方向（上/下/左/右）或目标坐标 x,y")

    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await move_cmd.finish("⛔ 请先创建角色")

        # 解析
        if arg in DIRECTIONS:
            dx, dy = DIRECTIONS[arg]
            new_x, new_y = player.x + dx, player.y + dy
        else:
            try:
                parts = arg.split(",")
                new_x, new_y = int(parts[0]), int(parts[1])
            except Exception:
                await move_cmd.finish("⛔ 格式错误，示例：前往 上  或  前往 3,5")

        # 可加入边界检查 / 体力消耗
        player.x, player.y = new_x, new_y
        session.add(player)
        await session.commit()

    await move_cmd.finish(create_rich_message(f"🚶 已移动至 ({new_x},{new_y})", event))

# ----------------- 指令：探索 -----------------
explore_cmd = on_command("探索", block=True, priority=5)

# 事件处理器映射
async def _handle_elite(session, tile: WorldTile, player: Player) -> str:
    """精英怪属于公共事件，自动战斗，直到一方死亡，输出完整战报"""
    rng = random.Random(hash(f"{tile.seed}:{player.id}:{datetime.utcnow().timestamp()}"))
    monster_hp = tile.state.get("hp", 0)
    monster_name = tile.state.get("name", "未知诡影")
    if monster_hp <= 0:
        return f"⚠️ 这里残留着 {monster_name} 的破碎尸壳…已经被人捷足先登。"

    # 玩家属性
    attack_score = player.attack * 0.7 + player.agility * 0.3
    defense_score = player.defense * 0.7 + player.agility * 0.2 + player.luck * 0.1
    player_hp = player.hp
    max_round = 100  # 上限 100 回合
    battle_log = []
    contributors: dict = tile.state.setdefault("contributors", {})
    uid = str(player.uid)
    total_dmg = 0

    # 怪物属性（若无则默认）
    monster_attack_stat = tile.state.get("attack", rng.randint(10, 30))
    monster_agility = tile.state.get("agility", rng.randint(5, 20))
    monster_level = tile.state.get("level", 1)
    monster_display = f"{monster_name}(Lv{monster_level})"

    def record(round_idx: int, text: str, force: bool=False):
        """根据需求选择性记录日志"""
        if force or round_idx == 1 or round_idx % 10 == 0:
            battle_log.append(text)

    for round_num in range(1, max_round + 1):
        if monster_hp <= 0 or player_hp <= 0:
            break

        # 计算先手：概率由敏捷决定
        player_first = rng.random() < (player.agility / (player.agility + monster_agility))

        def player_attack(r_idx):
            nonlocal monster_hp, total_dmg
            hit_rate = max(0.3, min(0.95, attack_score / (attack_score + defense_score + 1)))
            if rng.random() > hit_rate:
                record(r_idx, f"[回合{r_idx}] 你挥舞兵刃，未命中 {monster_display}。")
                return
            base_dmg = attack_score * rng.uniform(0.8, 1.2)
            dmg = max(1, int(base_dmg))
            crit = False
            if rng.random() < player.luck / 1000:
                dmg = int(dmg * 1.5)
                crit = True
            monster_hp = max(0, monster_hp - dmg)
            total_dmg += dmg
            record(r_idx, f"[回合{r_idx}] {'💥 暴击！' if crit else ''}你对 {monster_display} 造成 {dmg} 伤害！", force=(crit or monster_hp==0))

        def monster_attack_fn(r_idx):
            nonlocal player_hp
            dmg = rng.randint(int(monster_attack_stat*0.8), int(monster_attack_stat*1.2))
            player_hp = max(0, player_hp - dmg)
            record(r_idx, f"[回合{r_idx}] {monster_display} 攻击你，造成 {dmg} 伤害！", force=(player_hp==0))

        if player_first:
            player_attack(round_num)
            if monster_hp > 0:
                monster_attack_fn(round_num)
        else:
            monster_attack_fn(round_num)
            if player_hp > 0:
                player_attack(round_num)

    # 更新贡献
    contributors[uid] = contributors.get(uid, 0) + total_dmg
    tile.state["hp"] = monster_hp
    player.hp = player_hp

    # 添加总结行
    battle_log.append(f"📊 总计 {round_num} 回合，你造成 {total_dmg} 伤害，剩余HP {player_hp}/{player.max_hp}，{monster_display} HP {monster_hp}/{monster_hp + total_dmg}。")

    # 结算
    if monster_hp == 0:
        exp_gain = 100
        player.exp += exp_gain
        reward_text = f"🎉 你终结了 {monster_display}！获得 {exp_gain} EXP"
        tile.event_type = "EMPTY"
        tile.state = {}
        session.add(player)
        await session.flush()
        return "\n".join(battle_log) + "\n" + reward_text
    elif player_hp == 0:
        tile.state["hp"] = monster_hp
        session.add_all([player, tile])
        await session.flush()
        return "\n".join(battle_log)
    else:
        session.add_all([player, tile])
        await session.flush()
        return "\n".join(battle_log)


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
    return "🌫️ 除了回声，只有潮湿气味……"


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
            if rng.random() < player.luck / 1000:
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

    session.add_all([player, tile])
    await session.flush()
    return log


EVENT_HANDLERS = {
    "ELITE": _handle_elite,
    "TREASURE": _handle_treasure,
    "EMPTY": _handle_empty,
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
    await explore_cmd.finish(f"{header}\n{log}", event) 