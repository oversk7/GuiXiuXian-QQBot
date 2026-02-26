"""
恶魔轮盘 PvE 人机模式
仅限私聊，玩家与 AI 对战
"""
import json
import asyncio
import random
from collections import Counter
from typing import Dict
from nonebot import on_command
from nonebot.adapters.qq import Bot, MessageEvent, Message
from nonebot.params import CommandArg

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from ..platform_utils import get_unified_player, is_private_message
from .russian_roulette_core import RussianRouletteCore, ItemType
from .russian_roulette_ai import execute_ai_turn

# ==================== PvE 会话管理 ====================
# key = player_id, value = session dict
_pve_sessions: Dict[str, dict] = {}

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
MAX_HP = 3


def _create_pve_session(player_id: str, bet: int) -> dict:
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
        "pot": bet,
        "double_count": 0,
        "max_hp": MAX_HP,
        "game_state": {
            "bullets": json.dumps(bullets),
            "current_bullet_index": 0,
            "player_hp": MAX_HP,
            "ai_hp": MAX_HP,
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
        f"  AI: {'❤️' * ai_hp}{'🖤' * (max_hp - ai_hp)}",
    ])

    # 道具
    player_items = json.loads(gs.get("player_items", "[]"))
    ai_items = json.loads(gs.get("ai_items", "[]"))
    display.extend([
        "━━━━━━━━━━━━━",
        f"🎒 你的道具：{len(player_items)}个",
        f"🤖 AI道具：{len(ai_items)}个",
    ])

    # 特殊状态
    effects = []
    if gs.get("is_sawed_off"):
        effects.append("🪚 手锯效果：下一发实弹伤害+1")
    handcuffed = gs.get("handcuffed_player_id")
    if handcuffed:
        name = "玩家" if handcuffed == "player" else "AI"
        effects.append(f"⛓️ 手铐效果：{name}下回合被限制")
    if effects:
        display.extend(["━━━━━━━━━━━━━"] + effects)

    return "\n".join(display)


def _format_items_list(items_json: str) -> str:
    """格式化道具列表"""
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


def _reset_round(session_data: dict):
    """加倍时重置游戏状态（新一轮）"""
    bullets = RussianRouletteCore.generate_bullets()
    player_items = RussianRouletteCore.generate_items(4)
    ai_items = RussianRouletteCore.generate_items(4)

    live_count = sum(1 for b in bullets if b)
    blank_count = sum(1 for b in bullets if not b)

    session_data["game_state"] = {
        "bullets": json.dumps(bullets),
        "current_bullet_index": 0,
        "player_hp": MAX_HP,
        "ai_hp": MAX_HP,
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


async def _do_ai_turn(bot: Bot, event: MessageEvent, session_data: dict):
    """执行 AI 回合并发送消息，返回是否游戏结束"""
    ai_messages, game_over = execute_ai_turn(session_data)
    player_id = session_data["player_id"]
    gs = session_data["game_state"]

    # 合并 AI 消息
    ai_text = "\n".join(ai_messages)

    if game_over:
        # 判断谁赢
        if gs["player_hp"] <= 0:
            session_data["status"] = "lost"
            result = (
                f"{ai_text}\n"
                f"━━━━━━━━━━━━━\n"
                f"💀 你被击败了！\n"
                f"💰 失去了奖池中的 {session_data['pot']} 金币"
            )
            del _pve_sessions[player_id]
            await bot.send(event, message_add_head(result, event))
        else:
            session_data["status"] = "won"
            pot = session_data["pot"]
            result = (
                f"{ai_text}\n"
                f"━━━━━━━━━━━━━\n"
                f"🎉 你击败了 AI！\n"
                f"💰 当前奖池：{pot}金币\n"
                f"━━━━━━━━━━━━━\n"
                f"📝 选择：\n"
                f"▫️【人机轮盘 加倍】奖池翻倍再战\n"
                f"▫️【人机轮盘 收手】拿走 {pot} 金币"
            )
            await bot.send(event, message_add_head(result, event))
        return

    # AI 回合结束，轮到玩家
    status = _get_pve_display(session_data)
    full_msg = f"{ai_text}\n━━━━━━━━━━━━━\n🔄 轮到你行动\n\n{status}"
    await bot.send(event, message_add_head(full_msg, event))


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
            "▫️ 私聊对战 AI，固定3血\n"
            "▫️ 将 AI 血量降为0即获胜\n"
            "▫️ 赢后可选择加倍续战或收手\n"
            "━━━━━━━━━━━━━\n"
            "📝 指令：\n"
            f"▫️【人机轮盘 <金额>】开始（{BET_MIN}~{BET_MAX}）\n"
            "▫️【pve开枪 自己/对手】射击\n"
            "▫️【pve道具 <道具名>】使用道具\n"
            "▫️【pve道具 肾上腺素 <道具名>】偷取道具\n"
            "▫️【pve状态】查看当前状态\n"
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

    # 开始新游戏（金额参数）
    try:
        bet = int(args_text)
    except ValueError:
        await pve_cmd.finish("⛔ 请输入正确的金额数字\n📝 示例：人机轮盘 1000")

    if bet < BET_MIN or bet > BET_MAX:
        await pve_cmd.finish(f"⛔ 赌注范围：{BET_MIN} ~ {BET_MAX} 金币")

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await pve_cmd.finish("⛔ 请先创建角色")

        # 检查是否已有 PvE 游戏
        if player.id in _pve_sessions:
            s = _pve_sessions[player.id]
            if s["status"] == "playing":
                await pve_cmd.finish("⛔ 你已有进行中的人机轮盘，请先完成当前游戏\n📝 发送【pve状态】查看状态")
            elif s["status"] == "won":
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
        await session.commit()

    # 创建游戏
    session_data = _create_pve_session(player.id, bet)
    _pve_sessions[player.id] = session_data

    gs = session_data["game_state"]
    bc = session_data["bullet_counts"]

    # 显示开局信息
    player_items_text = _format_items_list(gs["player_items"])
    ai_items_text = _format_items_list(gs["ai_items"])

    first_turn = session_data["current_turn"]
    first_text = "你先手！" if first_turn == "player" else "AI 先手！"

    start_msg = (
        f"🎮 恶魔轮盘 · 人机模式 开始！\n"
        f"━━━━━━━━━━━━━\n"
        f"💰 赌注：{bet}金币\n"
        f"💥 弹药配置：{bc['total_live']}发实弹 + {bc['total_blank']}发空包弹\n"
        f"❤️ 双方血量：{MAX_HP}\n"
        f"🎯 {first_text}\n"
        f"━━━━━━━━━━━━━\n"
        f"🎒 你的道具：\n{player_items_text}\n"
        f"━━━━━━━━━━━━━\n"
        f"🤖 AI的道具：\n{ai_items_text}\n"
        f"━━━━━━━━━━━━━\n"
        f"📝 操作：【pve开枪 自己/对手】或【pve道具 <道具名>】"
    )

    if first_turn == "ai":
        # AI 先手，先发送开局信息，然后执行 AI 回合
        await bot.send(event, message_add_head(start_msg, event))
        await asyncio.sleep(1)
        await _do_ai_turn(bot, event, session_data)
    else:
        await pve_cmd.finish(message_add_head(start_msg, event))


async def _handle_double(bot: Bot, event: MessageEvent):
    """处理加倍"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await pve_cmd.finish("⛔ 请先创建角色")

        if player.id not in _pve_sessions:
            await pve_cmd.finish("⛔ 你没有进行中的人机轮盘")

        sd = _pve_sessions[player.id]
        if sd["status"] != "won":
            await pve_cmd.finish("⛔ 只有赢了之后才能加倍")

        # 奖池翻倍（不额外扣金币）
        sd["pot"] *= 2
        sd["double_count"] += 1

        # 重置游戏
        _reset_round(sd)

        gs = sd["game_state"]
        bc = sd["bullet_counts"]
        player_items_text = _format_items_list(gs["player_items"])
        ai_items_text = _format_items_list(gs["ai_items"])

        first_turn = sd["current_turn"]
        first_text = "你先手！" if first_turn == "player" else "AI 先手！"

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
            f"🤖 AI的道具：\n{ai_items_text}\n"
            f"━━━━━━━━━━━━━\n"
            f"📝 操作：【pve开枪 自己/对手】或【pve道具 <道具名>】"
        )

        if first_turn == "ai":
            # AI 先手，先发送信息，然后执行 AI 回合
            await bot.send(event, message_add_head(msg, event))
            await asyncio.sleep(1)
            await _do_ai_turn(bot, event, sd)
        else:
            await pve_cmd.finish(message_add_head(msg, event))


async def _handle_cash_out(bot: Bot, event: MessageEvent):
    """处理收手"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await pve_cmd.finish("⛔ 请先创建角色")

        if player.id not in _pve_sessions:
            await pve_cmd.finish("⛔ 你没有进行中的人机轮盘")

        sd = _pve_sessions[player.id]
        if sd["status"] != "won":
            await pve_cmd.finish("⛔ 只有赢了之后才能收手")

        pot = sd["pot"]
        double_count = sd["double_count"]

        # 发放奖励
        player.gold += pot
        # 积分：基础1分 + 每次加倍额外1分
        score_gain = 1 + double_count
        player.mini_game_score += score_gain
        await session.commit()

        # 清理 session
        del _pve_sessions[player.id]

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

        if player.id not in _pve_sessions:
            await pve_shoot_cmd.finish("⛔ 你没有进行中的人机轮盘\n📝 发送【人机轮盘 <金额>】开始")

        sd = _pve_sessions[player.id]
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
            await bot.send(event, message_add_head("⛓️ 你被手铐限制，跳过本回合\n🔄 轮到 AI 行动", event))
            await asyncio.sleep(1)
            await _do_ai_turn(bot, event, sd)
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

        target_text = "自己" if target == "自己" else "AI"
        result_msg = f"🎯 你对{target_text}开枪\n{shoot_msg}"

        if game_over:
            if gs["ai_hp"] <= 0:
                # 玩家赢了
                sd["status"] = "won"
                pot = sd["pot"]
                result_msg += (
                    f"\n━━━━━━━━━━━━━\n"
                    f"🎉 你击败了 AI！\n"
                    f"💰 当前奖池：{pot}金币\n"
                    f"━━━━━━━━━━━━━\n"
                    f"📝 选择：\n"
                    f"▫️【人机轮盘 加倍】奖池翻倍再战\n"
                    f"▫️【人机轮盘 收手】拿走 {pot} 金币"
                )
                await pve_shoot_cmd.finish(message_add_head(result_msg, event))
            else:
                # 玩家输了
                sd["status"] = "lost"
                result_msg += (
                    f"\n━━━━━━━━━━━━━\n"
                    f"💀 你被击败了！\n"
                    f"💰 失去了 {sd['pot']} 金币"
                )
                del _pve_sessions[player.id]
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
            status_display = _get_pve_display(sd)
            result_msg += f"\n🔄 你继续行动\n\n{status_display}"
            await pve_shoot_cmd.finish(message_add_head(result_msg, event))
        else:
            # 检查对手被手铐
            if gs.get("handcuffed_player_id") == "ai":
                gs["handcuffed_player_id"] = None
                result_msg += "\n⛓️ AI 被手铐限制，跳过回合\n🔄 你继续行动"
                status_display = _get_pve_display(sd)
                result_msg += f"\n\n{status_display}"
                await pve_shoot_cmd.finish(message_add_head(result_msg, event))

            # 切换到 AI 回合
            sd["current_turn"] = "ai"
            result_msg += "\n🔄 轮到 AI 行动..."
            await bot.send(event, message_add_head(result_msg, event))
            await asyncio.sleep(1)
            await _do_ai_turn(bot, event, sd)


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

        if player.id not in _pve_sessions:
            await pve_item_cmd.finish("⛔ 你没有进行中的人机轮盘")

        sd = _pve_sessions[player.id]
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
            await bot.send(event, message_add_head("⛓️ 你被手铐限制，跳过本回合\n🔄 轮到 AI 行动", event))
            await asyncio.sleep(1)
            await _do_ai_turn(bot, event, sd)
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

            # 检查肾上腺素使用后的状态变化
            _update_after_item(sd, stolen_type)

            await _finish_item_use(bot, event, sd, "肾上腺素", result_msg, player)
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
                await pve_item_cmd.finish("⛔ AI 已被手铐限制")
            cooldown = gs.get("handcuffs_cooldown_player_id")
            if cooldown == "ai":
                await pve_item_cmd.finish("⛔ AI 刚刚被手铐限制，需其行动一次后才能再次使用")

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

        await _finish_item_use(bot, event, sd, item_name, result_msg, player)


def _update_after_item(sd: dict, stolen_type: ItemType):
    """肾上腺素使用后根据偷到的道具类型更新统计"""
    gs = sd["game_state"]
    if stolen_type == ItemType.BEER:
        # 检查 beer result in magnifier_info (not applicable here)
        # beer 的退膛结果已经在 result_msg 中了，但我们无法直接从这里获取
        # 由 Core.use_adrenaline -> use_beer 处理，统计在 check_and_reload 中自动处理
        pass
    elif stolen_type == ItemType.DICE:
        sd["ai_known_bullet"] = None
        sd["ai_known_phone"] = None


async def _finish_item_use(bot: Bot, event: MessageEvent, sd: dict, item_name: str, result_msg: str, player):
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
            pot = sd["pot"]
            final_msg += (
                f"\n━━━━━━━━━━━━━\n"
                f"🎉 你击败了 AI！\n"
                f"💰 当前奖池：{pot}金币\n"
                f"━━━━━━━━━━━━━\n"
                f"📝 选择：\n"
                f"▫️【人机轮盘 加倍】奖池翻倍再战\n"
                f"▫️【人机轮盘 收手】拿走 {pot} 金币"
            )
            await bot.send(event, message_add_head(final_msg, event))
        elif gs.get("player_hp", 0) <= 0:
            sd["status"] = "lost"
            final_msg += (
                f"\n━━━━━━━━━━━━━\n"
                f"💀 你被击败了！\n"
                f"💰 失去了 {sd['pot']} 金币"
            )
            del _pve_sessions[player.id]
            await bot.send(event, message_add_head(final_msg, event))
        return

    # 道具使用后继续行动（不切换回合），刷新显示
    status_display = _get_pve_display(sd)
    final_msg += f"\n🔄 你可以继续行动\n\n{status_display}"
    await bot.send(event, message_add_head(final_msg, event))


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

        if player.id not in _pve_sessions:
            await pve_status_cmd.finish("⛔ 你没有进行中的人机轮盘")

        sd = _pve_sessions[player.id]

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

        turn_text = "你的回合" if sd["current_turn"] == "player" else "AI 的回合"
        msg = (
            f"{display}\n"
            f"━━━━━━━━━━━━━\n"
            f"🔄 当前：{turn_text}\n"
            f"━━━━━━━━━━━━━\n"
            f"🎒 你的道具详情：\n{player_items_text}"
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

        if player.id not in _pve_sessions:
            await pve_predict_cmd.finish("⛔ 你没有进行中的人机轮盘")

        sd = _pve_sessions[player.id]
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
