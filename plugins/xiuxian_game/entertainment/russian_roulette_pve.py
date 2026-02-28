"""
恶魔轮盘 PvE 人机模式
仅限私聊，玩家与 AI 对战
游戏状态持久化到数据库，支持重启恢复
"""
import json
import asyncio
import random
from collections import Counter
from nonebot import on_command
from nonebot.adapters.qq import Bot, MessageEvent, Message
from nonebot.params import CommandArg

from ..models.db import safe_session
from ..models.player import Player
from ..models.russian_roulette import RussianRoulettePvEGame
from ..infrastructure.repositories.russian_roulette_pve_repository import RussianRoulettePvERepository
from ..utils import message_add_head
from ..platform_utils import get_unified_player, is_private_message
from .russian_roulette_core import RussianRouletteCore, ItemType
from .russian_roulette_ai import execute_ai_turn

# 道具名称映射
ITEM_NAME_MAP = {
    "手锯": ItemType.KNIFE,
    "手铐": ItemType.HANDCUFFS,
    "香烟": ItemType.CIGARETTE,
    "放大镜": ItemType.MAGNIFIER,
    "啤酒": ItemType.BEER,
    "肾上腺素": ItemType.ADRENALINE,
    "过期药": ItemType.EXPIRED_MEDICINE,
    "逆转器": ItemType.INVERTER,
    "电话": ItemType.PHONE,
    "骰子": ItemType.DICE,
}

# 肾上腺素可偷取的道具
ADRENALINE_STEAL_MAP = {k: v for k, v in ITEM_NAME_MAP.items() if v != ItemType.ADRENALINE}

BET_MIN = 100
BET_MAX = 500000
DEFAULT_HP = 4
MIN_HP = 3
MAX_HP = 6


# ==================== DB ↔ session_data 转换 ====================

def _db_to_session(pve_game: RussianRoulettePvEGame) -> dict:
    """从数据库记录还原 session_data dict"""
    return {
        "player_id": pve_game.player_id,
        "initial_bet": pve_game.initial_bet,
        "pot": pve_game.pot,
        "double_count": pve_game.double_count,
        "max_hp": pve_game.max_hp,
        "game_state": json.loads(pve_game.game_state),
        "current_turn": pve_game.current_turn,
        "status": pve_game.status,
        "ai_known_bullet": pve_game.ai_known_bullet,
        "ai_known_phone": json.loads(pve_game.ai_known_phone) if pve_game.ai_known_phone else None,
        "bullet_counts": json.loads(pve_game.bullet_counts),
    }


def _session_to_db(sd: dict, pve_game: RussianRoulettePvEGame):
    """将 session_data 写回数据库记录（不修改 player_id / initial_bet）"""
    pve_game.pot = sd["pot"]
    pve_game.double_count = sd["double_count"]
    pve_game.max_hp = sd["max_hp"]
    pve_game.game_state = json.dumps(sd["game_state"])
    pve_game.current_turn = sd["current_turn"]
    pve_game.status = sd["status"]
    pve_game.ai_known_bullet = sd.get("ai_known_bullet")
    pve_game.ai_known_phone = json.dumps(sd["ai_known_phone"]) if sd.get("ai_known_phone") is not None else None
    pve_game.bullet_counts = json.dumps(sd["bullet_counts"])


# ==================== 游戏逻辑（纯函数，不涉及 DB） ====================

def _create_pve_session(player_id: str, bet: int, max_hp: int = DEFAULT_HP) -> dict:
    """创建一个新的 PvE 游戏 session"""
    bullets = RussianRouletteCore.generate_bullets()
    player_items = RussianRouletteCore.generate_items(4)
    ai_items = RussianRouletteCore.generate_items(4)

    live_count = sum(1 for b in bullets if b)
    blank_count = sum(1 for b in bullets if not b)

    # 随机决定先手
    first_turn = random.choice(["player", "ai"])

    session_data = {
        "player_id": player_id,
        "initial_bet": bet,
        "pot": bet * 2,
        "double_count": 0,
        "max_hp": max_hp,
        "game_state": {
            "bullets": json.dumps(bullets),
            "current_bullet_index": 0,
            "player_hp": max_hp,
            "ai_hp": max_hp,
            "player_items": json.dumps([item.value for item in player_items]),
            "ai_items": json.dumps([item.value for item in ai_items]),
            "is_sawed_off": False,
            "handcuffed_player_id": None,
            "magnifier_info": None,
            "phone_info": None,
            "handcuffs_cooldown_player_id": None,
        },
        "current_turn": first_turn,
        "status": "playing",
        "ai_known_bullet": None,
        "ai_known_phone": None,
        "bullet_counts": {
            "total_live": live_count,
            "total_blank": blank_count,
            "fired_live": 0,
            "fired_blank": 0,
        },
    }
    return session_data


def _get_pve_display(session_data: dict) -> str:
    """获取 PvE 游戏状态显示"""
    gs = session_data["game_state"]
    bullets = json.loads(gs["bullets"])
    current_index = gs["current_bullet_index"]

    remaining = bullets[current_index:]
    total_remaining = len(remaining)

    fired = bullets[:current_index]
    fired_live = sum(1 for b in fired if b)
    fired_blank = sum(1 for b in fired if not b)

    player_hp = gs["player_hp"]
    ai_hp = gs["ai_hp"]
    max_hp = session_data["max_hp"]

    display = [
        "🎮 恶魔轮盘 · 人机模式",
        f"💰 当前奖池：{session_data['pot']}金币",
        "━━━━━━━━━━━━━",
        f"🔫 剩余弹药：{total_remaining}发",
    ]

    if fired_live > 0 or fired_blank > 0:
        display.append(f"📊 已打出：{fired_live}发实弹 + {fired_blank}发空包弹")

    display.extend([
        "❤️ 血量状态：",
        f"  玩家: {'❤️' * player_hp}{'🖤' * (max_hp - player_hp)}",
        f"  花花: {'❤️' * ai_hp}{'🖤' * (max_hp - ai_hp)}",
    ])

    # 道具
    player_items_inline = _format_items_inline(gs.get("player_items", "[]"))
    ai_items_inline = _format_items_inline(gs.get("ai_items", "[]"))
    display.extend([
        "━━━━━━━━━━━━━",
        f"🎒 你的道具：{player_items_inline}",
        f"🤖 花花道具：{ai_items_inline}",
    ])

    # 特殊状态
    effects = []
    if gs.get("is_sawed_off"):
        effects.append("🪚 手锯效果：下一发实弹伤害+1")
    handcuffed = gs.get("handcuffed_player_id")
    if handcuffed:
        name = "玩家" if handcuffed == "player" else "花花"
        effects.append(f"⛓️ 手铐效果：{name}下回合被限制")
    if effects:
        display.extend(["━━━━━━━━━━━━━"] + effects)

    return "\n".join(display)


def _format_items_list(items_json: str) -> str:
    """格式化道具列表（详细格式，含描述）"""
    items = json.loads(items_json or "[]")
    if not items:
        return "无道具"
    item_counts = Counter(items)
    lines = []
    for item_str, count in item_counts.items():
        try:
            item_type = ItemType(item_str)
            cfg = RussianRouletteCore.ITEM_CONFIGS[item_type]
            if count > 1:
                lines.append(f"{cfg['name']} x{count}")
            else:
                lines.append(f"{cfg['name']}")
            lines.append(f"  └ {cfg['description']}")
        except (ValueError, KeyError):
            lines.append(f"❓ 未知: {item_str} x{count}")
    return "\n".join(lines)


def _format_items_inline(items_json: str) -> str:
    """格式化道具列表（简短内联格式，用于状态显示）"""
    items = json.loads(items_json or "[]")
    if not items:
        return "无"
    item_counts = Counter(items)
    parts = []
    for item_str, count in item_counts.items():
        try:
            item_type = ItemType(item_str)
            cfg = RussianRouletteCore.ITEM_CONFIGS[item_type]
            if count > 1:
                parts.append(f"{cfg['name']}x{count}")
            else:
                parts.append(cfg['name'])
        except (ValueError, KeyError):
            parts.append(f"❓{item_str}")
    return " ".join(parts)


def _reset_round(session_data: dict):
    """加倍时重置游戏状态（新一轮）"""
    bullets = RussianRouletteCore.generate_bullets()
    player_items = RussianRouletteCore.generate_items(4)
    ai_items = RussianRouletteCore.generate_items(4)

    live_count = sum(1 for b in bullets if b)
    blank_count = sum(1 for b in bullets if not b)

    max_hp = session_data["max_hp"]
    session_data["game_state"] = {
        "bullets": json.dumps(bullets),
        "current_bullet_index": 0,
        "player_hp": max_hp,
        "ai_hp": max_hp,
        "player_items": json.dumps([item.value for item in player_items]),
        "ai_items": json.dumps([item.value for item in ai_items]),
        "is_sawed_off": False,
        "handcuffed_player_id": None,
        "magnifier_info": None,
        "phone_info": None,
        "handcuffs_cooldown_player_id": None,
    }
    session_data["current_turn"] = random.choice(["player", "ai"])
    session_data["status"] = "playing"
    session_data["ai_known_bullet"] = None
    session_data["ai_known_phone"] = None
    session_data["bullet_counts"] = {
        "total_live": live_count,
        "total_blank": blank_count,
        "fired_live": 0,
        "fired_blank": 0,
    }


# ==================== AI 回合（操作 DB） ====================

async def _do_ai_turn(
    bot: Bot, event: MessageEvent,
    sd: dict, pve_game: RussianRoulettePvEGame, repo: RussianRoulettePvERepository
):
    """执行 AI 回合，更新 DB，发送消息"""
    ai_messages, game_over = execute_ai_turn(sd)
    gs = sd["game_state"]

    # 合并 AI 消息
    ai_text = "\n".join(ai_messages)

    if game_over:
        # 判断谁赢
        if gs["player_hp"] <= 0:
            result = (
                f"{ai_text}\n"
                f"━━━━━━━━━━━━━\n"
                f"💀 你被击败了！\n"
                f"💰 失去了奖池中的 {sd['pot']} 金币"
            )
            await repo.delete_entity(pve_game)
            await bot.send(event, message_add_head(result, event))
        else:
            sd["status"] = "won"
            _session_to_db(sd, pve_game)
            pot = sd["pot"]
            result = (
                f"{ai_text}\n"
                f"━━━━━━━━━━━━━\n"
                f"🎉 你击败了花花！\n"
                f"💰 当前奖池：{pot}金币\n"
                f"━━━━━━━━━━━━━\n"
                f"📝 选择：\n"
                f"▫️【人机轮盘 加倍】奖池翻倍再战\n"
                f"▫️【人机轮盘 收手】拿走 {pot} 金币"
            )
            await bot.send(event, message_add_head(result, event))
        return

    # AI 回合结束，轮到玩家 - 保存状态
    _session_to_db(sd, pve_game)
    status = _get_pve_display(sd)
    full_msg = f"{ai_text}\n━━━━━━━━━━━━━\n🔄 轮到你行动\n\n{status}"
    await bot.send(event, message_add_head(full_msg, event))


# ==================== 道具使用公共逻辑 ====================

def _update_after_item(sd: dict, stolen_type: ItemType):
    """肾上腺素使用后根据偷到的道具类型更新统计"""
    if stolen_type == ItemType.DICE:
        sd["ai_known_bullet"] = None
        sd["ai_known_phone"] = None


async def _finish_item_use(
    bot: Bot, event: MessageEvent,
    sd: dict, item_name: str, result_msg: str,
    pve_game: RussianRoulettePvEGame, repo: RussianRoulettePvERepository
):
    """处理道具使用后的公共逻辑"""
    gs = sd["game_state"]

    # 检查道具使用后是否有人死亡
    game_over = gs.get("player_hp", 1) <= 0 or gs.get("ai_hp", 1) <= 0

    # 检查弹药重装
    reloaded = False
    reload_msg = ""
    if not game_over:
        reloaded, reload_msg = RussianRouletteCore.check_and_reload(gs, "player", "ai")
        if reloaded:
            bullets = json.loads(gs["bullets"])
            sd["bullet_counts"] = {
                "total_live": sum(1 for b in bullets if b),
                "total_blank": sum(1 for b in bullets if not b),
                "fired_live": 0,
                "fired_blank": 0,
            }
            sd["ai_known_bullet"] = None
            sd["ai_known_phone"] = None

    final_msg = f"🎒 使用了{item_name}\n{result_msg}"
    if reload_msg:
        final_msg += f"\n{reload_msg}"

    if game_over:
        if gs.get("ai_hp", 0) <= 0:
            sd["status"] = "won"
            _session_to_db(sd, pve_game)
            pot = sd["pot"]
            final_msg += (
                f"\n━━━━━━━━━━━━━\n"
                f"🎉 你击败了花花！\n"
                f"💰 当前奖池：{pot}金币\n"
                f"━━━━━━━━━━━━━\n"
                f"📝 选择：\n"
                f"▫️【人机轮盘 加倍】奖池翻倍再战\n"
                f"▫️【人机轮盘 收手】拿走 {pot} 金币"
            )
            await bot.send(event, message_add_head(final_msg, event))
        elif gs.get("player_hp", 0) <= 0:
            final_msg += (
                f"\n━━━━━━━━━━━━━\n"
                f"💀 你被击败了！\n"
                f"💰 失去了 {sd['pot']} 金币"
            )
            await repo.delete_entity(pve_game)
            await bot.send(event, message_add_head(final_msg, event))
        return

    # 道具使用后继续行动（不切换回合），保存并刷新显示
    _session_to_db(sd, pve_game)
    status_display = _get_pve_display(sd)
    final_msg += f"\n🔄 你可以继续行动\n\n{status_display}"
    await bot.send(event, message_add_head(final_msg, event))


# ==================== 命令注册 ====================

pve_cmd = on_command("人机轮盘", block=True, priority=4)


@pve_cmd.handle()
async def handle_pve(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    """人机轮盘主命令"""
    if not is_private_message(event):
        await pve_cmd.finish("⛔ 人机轮盘仅限私聊使用")

    args_text = args.extract_plain_text().strip()

    if not args_text or args_text == "帮助":
        help_msg = (
            "🎮 恶魔轮盘 · 人机模式\n"
            "━━━━━━━━━━━━━\n"
            "🎯 规则：\n"
            "▫️ 私聊对战花花，默认4血（可选3-6）\n"
            "▫️ 将花花血量降为0即获胜\n"
            "▫️ 赢后可选择加倍续战或收手\n"
            "━━━━━━━━━━━━━\n"
            "📝 指令：\n"
            f"▫️【人机轮盘 <金额>】开始（{BET_MIN}~{BET_MAX}）\n"
            f"▫️【人机轮盘 <金额> <血量>】自定义血量（{MIN_HP}~{MAX_HP}）\n"
            "▫️ 示例：人机轮盘 1000 4（四命房）\n"
            "▫️【pve开枪 自己/对手】射击\n"
            "▫️【pve道具 <道具名>】使用道具\n"
            "▫️【pve道具 肾上腺素 <道具名>】偷取道具\n"
            "▫️【pve状态】查看当前状态和道具详情\n"
            "▫️【pve预知】查看预知结果\n"
            "━━━━━━━━━━━━━\n"
            "💰 经济：\n"
            "▫️ 开局扣除赌注金额\n"
            "▫️ 赢后可加倍（奖池翻倍）或收手\n"
            "▫️ 输了失去奖池中的金额\n"
            "━━━━━━━━━━━━━\n"
            "🎒 道具与PVP相同，详见【恶魔轮盘帮助】"
        )
        await pve_cmd.finish(message_add_head(help_msg, event))

    # 加倍
    if args_text == "加倍":
        await _handle_double(bot, event)
        return

    # 收手
    if args_text == "收手":
        await _handle_cash_out(bot, event)
        return

    # 开始新游戏（金额参数 + 可选血量参数）
    parts = args_text.split()
    try:
        bet = int(parts[0])
    except ValueError:
        await pve_cmd.finish("⛔ 请输入正确的金额数字\n📝 示例：人机轮盘 1000\n📝 自定义血量：人机轮盘 1000 4")

    max_hp = DEFAULT_HP
    if len(parts) >= 2:
        try:
            max_hp = int(parts[1])
        except ValueError:
            await pve_cmd.finish(f"⛔ 血量参数无效，请填入 {MIN_HP}-{MAX_HP} 的数字\n📝 示例：人机轮盘 1000 4")
        if max_hp < MIN_HP or max_hp > MAX_HP:
            await pve_cmd.finish(f"⛔ 血量范围：{MIN_HP} ~ {MAX_HP}\n📝 示例：人机轮盘 1000 4（四命）")

    if bet < BET_MIN or bet > BET_MAX:
        await pve_cmd.finish(f"⛔ 赌注范围：{BET_MIN} ~ {BET_MAX} 金币")

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await pve_cmd.finish("⛔ 请先创建角色")

        repo = RussianRoulettePvERepository(session)

        # 检查是否已有 PvE 游戏
        existing = await repo.find_active_by_player_id(player.id)
        if existing:
            if existing.status == "playing":
                await pve_cmd.finish("⛔ 你已有进行中的人机轮盘，请先完成当前游戏\n📝 发送【pve状态】查看状态")
            elif existing.status == "won":
                await pve_cmd.finish("⛔ 你还有未结算的人机轮盘\n📝 请先选择【人机轮盘 加倍】或【人机轮盘 收手】")

        # 检查是否在 PvP 房间中
        from .russian_roulette_service_new import RussianRouletteService as RussianRouletteServiceNew
        from ..infrastructure.repositories.russian_roulette_room_repository import RussianRouletteRoomRepository
        from ..infrastructure.repositories.russian_roulette_game_repository import RussianRouletteGameRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository

        service = RussianRouletteServiceNew(
            room_repo=RussianRouletteRoomRepository(session),
            game_repo=RussianRouletteGameRepository(session),
            player_repo=PlayerRepository(session)
        )
        pvp_room = await service.get_player_active_room(player.id)
        if pvp_room:
            await pve_cmd.finish("⛔ 你正在PVP轮盘房间中，不能同时进行人机轮盘")

        # 检查金币
        if player.gold < bet:
            await pve_cmd.finish(f"⛔ 金币不足，你当前有 {player.gold} 金币")

        # 扣除金币
        player.gold -= bet

        # 创建游戏
        session_data = _create_pve_session(player.id, bet, max_hp)
        pve_game = RussianRoulettePvEGame(
            player_id=player.id,
            initial_bet=bet,
        )
        _session_to_db(session_data, pve_game)
        await repo.add(pve_game)

        gs = session_data["game_state"]
        bc = session_data["bullet_counts"]

        # 显示开局信息
        player_items_text = _format_items_list(gs["player_items"])
        ai_items_text = _format_items_list(gs["ai_items"])

        first_turn = session_data["current_turn"]
        first_text = "你先手！" if first_turn == "player" else "花花先手！"

        start_msg = (
            f"🎮 恶魔轮盘 · 人机模式 开始！\n"
            f"━━━━━━━━━━━━━\n"
            f"💰 赌注：{bet}金币（庄家跟注，初始奖池：{session_data['pot']}金币）\n"
            f"💥 弹药配置：{bc['total_live']}发实弹 + {bc['total_blank']}发空包弹\n"
            f"❤️ 双方血量：{max_hp}\n"
            f"🎯 {first_text}\n"
            f"━━━━━━━━━━━━━\n"
            f"🎒 你的道具：\n{player_items_text}\n"
            f"━━━━━━━━━━━━━\n"
            f"🤖 花花的道具：\n{ai_items_text}\n"
            f"━━━━━━━━━━━━━\n"
            f"📝 操作：【pve开枪 自己/对手】或【pve道具 <道具名>】\n"
            f"📝 查看道具：【pve状态】"
        )

        if first_turn == "ai":
            # AI 先手，先发送开局信息，然后执行 AI 回合
            await bot.send(event, message_add_head(start_msg, event))
            await asyncio.sleep(1)
            await _do_ai_turn(bot, event, session_data, pve_game, repo)
        else:
            await pve_cmd.finish(message_add_head(start_msg, event))


async def _handle_double(bot: Bot, event: MessageEvent):
    """处理加倍"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await pve_cmd.finish("⛔ 请先创建角色")

        repo = RussianRoulettePvERepository(session)
        pve_game = await repo.find_active_by_player_id(player.id)
        if not pve_game:
            await pve_cmd.finish("⛔ 你没有进行中的人机轮盘")

        if pve_game.status != "won":
            await pve_cmd.finish("⛔ 只有赢了之后才能加倍")

        sd = _db_to_session(pve_game)

        # 奖池翻倍（不额外扣金币）
        sd["pot"] *= 2
        sd["double_count"] += 1

        # 重置游戏
        _reset_round(sd)
        _session_to_db(sd, pve_game)

        gs = sd["game_state"]
        bc = sd["bullet_counts"]
        player_items_text = _format_items_list(gs["player_items"])
        ai_items_text = _format_items_list(gs["ai_items"])

        first_turn = sd["current_turn"]
        first_text = "你先手！" if first_turn == "player" else "花花先手！"

        msg = (
            f"🔥 加倍续战！第 {sd['double_count']} 次加倍\n"
            f"━━━━━━━━━━━━━\n"
            f"💰 当前奖池：{sd['pot']}金币\n"
            f"💥 弹药配置：{bc['total_live']}发实弹 + {bc['total_blank']}发空包弹\n"
            f"❤️ 双方血量已重置\n"
            f"🎯 {first_text}\n"
            f"━━━━━━━━━━━━━\n"
            f"🎒 你的道具：\n{player_items_text}\n"
            f"━━━━━━━━━━━━━\n"
            f"🤖 花花的道具：\n{ai_items_text}\n"
            f"━━━━━━━━━━━━━\n"
            f"📝 操作：【pve开枪 自己/对手】或【pve道具 <道具名>】\n"
            f"📝 查看道具：【pve状态】"
        )

        if first_turn == "ai":
            # AI 先手，先发送信息，然后执行 AI 回合
            await bot.send(event, message_add_head(msg, event))
            await asyncio.sleep(1)
            await _do_ai_turn(bot, event, sd, pve_game, repo)
        else:
            await pve_cmd.finish(message_add_head(msg, event))


async def _handle_cash_out(bot: Bot, event: MessageEvent):
    """处理收手"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await pve_cmd.finish("⛔ 请先创建角色")

        repo = RussianRoulettePvERepository(session)
        pve_game = await repo.find_active_by_player_id(player.id)
        if not pve_game:
            await pve_cmd.finish("⛔ 你没有进行中的人机轮盘")

        if pve_game.status != "won":
            await pve_cmd.finish("⛔ 只有赢了之后才能收手")

        pot = pve_game.pot
        double_count = pve_game.double_count

        # 发放奖励
        player.gold += pot
        # 积分：基础1分 + 每次加倍额外1分
        score_gain = 1 + double_count
        player.mini_game_score += score_gain

        # 删除游戏记录
        await repo.delete_entity(pve_game)

        msg = (
            f"💰 收手成功！\n"
            f"━━━━━━━━━━━━━\n"
            f"🏆 获得 {pot} 金币\n"
            f"🎮 加倍次数：{double_count}\n"
            f"⭐ 小游戏积分 +{score_gain}\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 再来一局？发送【人机轮盘 <金额>】"
        )
        await pve_cmd.finish(message_add_head(msg, event))


# ==================== PvE 开枪 ====================

pve_shoot_cmd = on_command("pve开枪", block=True, priority=4)


@pve_shoot_cmd.handle()
async def handle_pve_shoot(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    """PvE 射击"""
    if not is_private_message(event):
        await pve_shoot_cmd.finish("⛔ 人机轮盘指令仅限私聊使用")

    target = args.extract_plain_text().strip()
    if target not in ["自己", "对手"]:
        await pve_shoot_cmd.finish("⛔ 请指定目标：pve开枪 自己/对手")

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await pve_shoot_cmd.finish("⛔ 请先创建角色")

        repo = RussianRoulettePvERepository(session)
        pve_game = await repo.find_active_by_player_id(player.id)
        if not pve_game:
            await pve_shoot_cmd.finish("⛔ 你没有进行中的人机轮盘\n📝 发送【人机轮盘 <金额>】开始")

        sd = _db_to_session(pve_game)

        if sd["status"] != "playing":
            if sd["status"] == "won":
                await pve_shoot_cmd.finish("⛔ 游戏已结束，请选择【人机轮盘 加倍】或【人机轮盘 收手】")
            await pve_shoot_cmd.finish("⛔ 当前没有进行中的游戏")

        if sd["current_turn"] != "player":
            await pve_shoot_cmd.finish("⛔ 还没轮到你行动")

        gs = sd["game_state"]

        # 检查手铐
        if gs.get("handcuffed_player_id") == "player":
            gs["handcuffed_player_id"] = None
            sd["current_turn"] = "ai"
            _session_to_db(sd, pve_game)
            await bot.send(event, message_add_head("⛓️ 你被手铐限制，跳过本回合\n🔄 轮到花花行动", event))
            await asyncio.sleep(1)
            await _do_ai_turn(bot, event, sd, pve_game, repo)
            return

        # 执行射击
        shooter_id = "player"
        target_id = "player" if target == "自己" else "ai"
        hit, shoot_msg, game_over = RussianRouletteCore.shoot(gs, shooter_id, target_id)

        # 更新弹药统计
        if hit:
            sd["bullet_counts"]["fired_live"] += 1
        else:
            sd["bullet_counts"]["fired_blank"] += 1

        target_text = "自己" if target == "自己" else "花花"
        result_msg = f"🎯 你对{target_text}开枪\n{shoot_msg}"

        if game_over:
            if gs["ai_hp"] <= 0:
                # 玩家赢了
                sd["status"] = "won"
                _session_to_db(sd, pve_game)
                pot = sd["pot"]
                result_msg += (
                    f"\n━━━━━━━━━━━━━\n"
                    f"🎉 你击败了花花！\n"
                    f"💰 当前奖池：{pot}金币\n"
                    f"━━━━━━━━━━━━━\n"
                    f"📝 选择：\n"
                    f"▫️【人机轮盘 加倍】奖池翻倍再战\n"
                    f"▫️【人机轮盘 收手】拿走 {pot} 金币"
                )
                await pve_shoot_cmd.finish(message_add_head(result_msg, event))
            else:
                # 玩家输了
                result_msg += (
                    f"\n━━━━━━━━━━━━━\n"
                    f"💀 你被击败了！\n"
                    f"💰 失去了 {sd['pot']} 金币"
                )
                await repo.delete_entity(pve_game)
                await pve_shoot_cmd.finish(message_add_head(result_msg, event))

        # 游戏继续
        # 检查弹药重装
        reloaded, reload_msg = RussianRouletteCore.check_and_reload(gs, "player", "ai")
        if reloaded:
            result_msg += f"\n{reload_msg}"
            bullets = json.loads(gs["bullets"])
            sd["bullet_counts"] = {
                "total_live": sum(1 for b in bullets if b),
                "total_blank": sum(1 for b in bullets if not b),
                "fired_live": 0,
                "fired_blank": 0,
            }
            sd["ai_known_bullet"] = None
            sd["ai_known_phone"] = None

        if target == "自己" and not hit:
            # 对自己开空包弹，继续行动
            _session_to_db(sd, pve_game)
            status_display = _get_pve_display(sd)
            result_msg += f"\n🔄 你继续行动\n\n{status_display}"
            await pve_shoot_cmd.finish(message_add_head(result_msg, event))
        else:
            # 检查对手被手铐
            if gs.get("handcuffed_player_id") == "ai":
                gs["handcuffed_player_id"] = None
                result_msg += "\n⛓️ 花花被手铐限制，跳过回合\n🔄 你继续行动"
                _session_to_db(sd, pve_game)
                status_display = _get_pve_display(sd)
                result_msg += f"\n\n{status_display}"
                await pve_shoot_cmd.finish(message_add_head(result_msg, event))

            # 切换到 AI 回合
            sd["current_turn"] = "ai"
            _session_to_db(sd, pve_game)
            result_msg += "\n🔄 轮到花花行动..."
            await bot.send(event, message_add_head(result_msg, event))
            await asyncio.sleep(1)
            await _do_ai_turn(bot, event, sd, pve_game, repo)


# ==================== PvE 道具 ====================

pve_item_cmd = on_command("pve道具", block=True, priority=4)


@pve_item_cmd.handle()
async def handle_pve_item(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    """PvE 使用道具"""
    if not is_private_message(event):
        await pve_item_cmd.finish("⛔ 人机轮盘指令仅限私聊使用")

    args_text = args.extract_plain_text().strip()
    if not args_text:
        await pve_item_cmd.finish("⛔ 请指定道具名称\n📝 示例：pve道具 放大镜")

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await pve_item_cmd.finish("⛔ 请先创建角色")

        repo = RussianRoulettePvERepository(session)
        pve_game = await repo.find_active_by_player_id(player.id)
        if not pve_game:
            await pve_item_cmd.finish("⛔ 你没有进行中的人机轮盘")

        sd = _db_to_session(pve_game)

        if sd["status"] != "playing":
            if sd["status"] == "won":
                await pve_item_cmd.finish("⛔ 游戏已结束，请选择【人机轮盘 加倍】或【人机轮盘 收手】")
            await pve_item_cmd.finish("⛔ 当前没有进行中的游戏")

        if sd["current_turn"] != "player":
            await pve_item_cmd.finish("⛔ 还没轮到你行动")

        gs = sd["game_state"]

        # 检查手铐
        if gs.get("handcuffed_player_id") == "player":
            gs["handcuffed_player_id"] = None
            sd["current_turn"] = "ai"
            _session_to_db(sd, pve_game)
            await bot.send(event, message_add_head("⛓️ 你被手铐限制，跳过本回合\n🔄 轮到花花行动", event))
            await asyncio.sleep(1)
            await _do_ai_turn(bot, event, sd, pve_game, repo)
            return

        # 解析肾上腺素特殊格式: pve道具 肾上腺素 <目标道具>
        parts = args_text.split(maxsplit=1)
        if parts[0] == "肾上腺素":
            if len(parts) < 2:
                await pve_item_cmd.finish("⛔ 肾上腺素需要指定偷取的道具\n📝 示例：pve道具 肾上腺素 手锯")
            steal_name = parts[1].strip()
            if steal_name not in ADRENALINE_STEAL_MAP:
                available = "、".join(ADRENALINE_STEAL_MAP.keys())
                await pve_item_cmd.finish(f"⛔ 不可偷取该道具。可选：{available}")

            player_items = json.loads(gs.get("player_items", "[]"))
            if ItemType.ADRENALINE.value not in player_items:
                await pve_item_cmd.finish("⛔ 你没有肾上腺素")

            stolen_type = ADRENALINE_STEAL_MAP[steal_name]
            success, result_msg = RussianRouletteCore.use_adrenaline(
                gs, "player", "ai", stolen_type, sd["max_hp"]
            )
            if not success:
                await pve_item_cmd.finish(message_add_head(f"❌ {result_msg}", event))

            # 私聊模式下直接显示放大镜/电话预知结果（无需再发送【预知】指令）
            if stolen_type == ItemType.MAGNIFIER:
                mag_data = json.loads(gs.get("magnifier_info") or "{}")
                if mag_data.get("player_id") == "player":
                    bullet_type = mag_data["bullet_type"]
                    result_msg = f"💉 肾上腺素已使用！偷取了花花的🔍放大镜并立刻使用\n🔍 放大镜结果：当前弹药是 {bullet_type}"
            elif stolen_type == ItemType.PHONE:
                phone_data = json.loads(gs.get("phone_info") or "{}")
                if phone_data.get("player_id") == "player":
                    pos = phone_data["bullet_position"]
                    bt = phone_data["bullet_type"]
                    result_msg = f"💉 肾上腺素已使用！偷取了花花的📞电话并立刻使用\n📞 电话结果：第{pos}发弹药是 {bt}"
            elif stolen_type == ItemType.BEER:
                # 更新弹药统计（啤酒退膛）
                if "实弹" in result_msg:
                    sd["bullet_counts"]["fired_live"] += 1
                else:
                    sd["bullet_counts"]["fired_blank"] += 1

            # 检查肾上腺素使用后的状态变化
            _update_after_item(sd, stolen_type)

            await _finish_item_use(bot, event, sd, "肾上腺素", result_msg, pve_game, repo)
            return

        # 普通道具
        item_name = args_text
        if item_name not in ITEM_NAME_MAP:
            available = "、".join(ITEM_NAME_MAP.keys())
            await pve_item_cmd.finish(f"⛔ 未知道具。可用道具：{available}")

        item_type = ITEM_NAME_MAP[item_name]

        if item_type == ItemType.ADRENALINE:
            await pve_item_cmd.finish("⛔ 肾上腺素需要指定偷取的道具\n📝 示例：pve道具 肾上腺素 手锯")

        # 检查是否拥有道具
        player_items = json.loads(gs.get("player_items", "[]"))
        if item_type.value not in player_items:
            await pve_item_cmd.finish(f"⛔ 你没有{item_name}")

        # 手铐额外检查
        if item_type == ItemType.HANDCUFFS:
            if gs.get("handcuffed_player_id") == "ai":
                await pve_item_cmd.finish("⛔ 花花已被手铐限制")
            cooldown = gs.get("handcuffs_cooldown_player_id")
            if cooldown == "ai":
                await pve_item_cmd.finish("⛔ 花花刚刚被手铐限制，需其行动一次后才能再次使用")

        # 使用道具
        success = False
        result_msg = ""

        if item_type == ItemType.KNIFE:
            success, result_msg = RussianRouletteCore.use_knife(gs)
        elif item_type == ItemType.HANDCUFFS:
            success, result_msg = RussianRouletteCore.use_handcuffs(gs, "ai")
        elif item_type == ItemType.CIGARETTE:
            success, result_msg = RussianRouletteCore.use_cigarette(gs, "player", sd["max_hp"])
        elif item_type == ItemType.MAGNIFIER:
            success, result_msg = RussianRouletteCore.use_magnifier(gs, "player")
            if success:
                # 直接显示预知结果（私聊模式）
                mag_data = json.loads(gs.get("magnifier_info", "{}"))
                if mag_data.get("player_id") == "player":
                    bullet_type = mag_data["bullet_type"]
                    result_msg = f"🔍 放大镜结果：当前弹药是 {bullet_type}"
        elif item_type == ItemType.BEER:
            success, result_msg = RussianRouletteCore.use_beer(gs)
            if success:
                # 更新弹药统计
                if "实弹" in result_msg:
                    sd["bullet_counts"]["fired_live"] += 1
                else:
                    sd["bullet_counts"]["fired_blank"] += 1
        elif item_type == ItemType.EXPIRED_MEDICINE:
            success, result_msg = RussianRouletteCore.use_expired_medicine(gs, "player", sd["max_hp"])
        elif item_type == ItemType.INVERTER:
            success, result_msg = RussianRouletteCore.use_inverter(gs)
        elif item_type == ItemType.PHONE:
            success, result_msg = RussianRouletteCore.use_phone(gs, "player")
            if success:
                # 直接显示预知结果
                phone_data = json.loads(gs.get("phone_info", "{}"))
                if phone_data.get("player_id") == "player":
                    pos = phone_data["bullet_position"]
                    bt = phone_data["bullet_type"]
                    result_msg = f"📞 电话结果：第{pos}发弹药是 {bt}"
        elif item_type == ItemType.DICE:
            success, result_msg = RussianRouletteCore.use_dice(gs)
            if success:
                sd["ai_known_bullet"] = None
                sd["ai_known_phone"] = None

        if not success:
            await pve_item_cmd.finish(message_add_head(f"❌ {result_msg}", event))

        # 消耗道具
        player_items.remove(item_type.value)
        gs["player_items"] = json.dumps(player_items)

        await _finish_item_use(bot, event, sd, item_name, result_msg, pve_game, repo)


# ==================== PvE 状态 ====================

pve_status_cmd = on_command("pve状态", block=True, priority=4)


@pve_status_cmd.handle()
async def handle_pve_status(event: MessageEvent):
    """查看 PvE 游戏状态"""
    if not is_private_message(event):
        await pve_status_cmd.finish("⛔ 人机轮盘指令仅限私聊使用")

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await pve_status_cmd.finish("⛔ 请先创建角色")

        repo = RussianRoulettePvERepository(session)
        pve_game = await repo.find_active_by_player_id(player.id)
        if not pve_game:
            await pve_status_cmd.finish("⛔ 你没有进行中的人机轮盘")

        sd = _db_to_session(pve_game)

        if sd["status"] == "won":
            pot = sd["pot"]
            msg = (
                f"🎮 人机轮盘 - 已胜利\n"
                f"━━━━━━━━━━━━━\n"
                f"💰 当前奖池：{pot}金币\n"
                f"🎮 加倍次数：{sd['double_count']}\n"
                f"━━━━━━━━━━━━━\n"
                f"📝 选择：\n"
                f"▫️【人机轮盘 加倍】奖池翻倍再战\n"
                f"▫️【人机轮盘 收手】拿走 {pot} 金币"
            )
            await pve_status_cmd.finish(message_add_head(msg, event))

        # 正在进行的游戏
        gs = sd["game_state"]
        display = _get_pve_display(sd)

        # 显示玩家道具详情
        player_items_text = _format_items_list(gs["player_items"])
        ai_items_text = _format_items_list(gs["ai_items"])

        turn_text = "你的回合" if sd["current_turn"] == "player" else "花花的回合"
        msg = (
            f"{display}\n"
            f"━━━━━━━━━━━━━\n"
            f"🔄 当前：{turn_text}\n"
            f"━━━━━━━━━━━━━\n"
            f"🎒 你的道具详情：\n{player_items_text}\n"
            f"━━━━━━━━━━━━━\n"
            f"🤖 花花道具详情：\n{ai_items_text}\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 使用肾上腺素：【pve道具 肾上腺素 <花花道具名>】"
        )
        await pve_status_cmd.finish(message_add_head(msg, event))


# ==================== PvE 预知 ====================

pve_predict_cmd = on_command("pve预知", block=True, priority=4)


@pve_predict_cmd.handle()
async def handle_pve_predict(event: MessageEvent):
    """查看预知结果"""
    if not is_private_message(event):
        await pve_predict_cmd.finish("⛔ 人机轮盘指令仅限私聊使用")

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await pve_predict_cmd.finish("⛔ 请先创建角色")

        repo = RussianRoulettePvERepository(session)
        pve_game = await repo.find_active_by_player_id(player.id)
        if not pve_game:
            await pve_predict_cmd.finish("⛔ 你没有进行中的人机轮盘")

        sd = _db_to_session(pve_game)
        gs = sd["game_state"]

        results = []

        # 放大镜
        if gs.get("magnifier_info"):
            mag_data = json.loads(gs["magnifier_info"])
            if mag_data.get("player_id") == "player":
                results.append(f"🔍 放大镜：当前弹药是 {mag_data['bullet_type']}")

        # 电话
        if gs.get("phone_info"):
            phone_data = json.loads(gs["phone_info"])
            if phone_data.get("player_id") == "player":
                results.append(f"📞 电话：第{phone_data['bullet_position']}发弹药是 {phone_data['bullet_type']}")

        if not results:
            await pve_predict_cmd.finish("⛔ 暂无预知结果")

        msg = "🔮 预知结果\n━━━━━━━━━━━━━\n" + "\n".join(results)
        await pve_predict_cmd.finish(message_add_head(msg, event))
