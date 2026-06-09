from __future__ import annotations

import asyncio
import base64
import io
import json

from nonebot import on_command
from nonebot.adapters.qq import Message, MessageEvent, MessageSegment
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.animal_chess import AnimalChessRoomStatus
from ..models.db import safe_session
from ..models.player import Player
from ..platform_utils import get_unified_player, require_player
from ..utils import message_add_head
from ..utils_markdown import build_markdown, cmd
from .animal_chess_service import ANIMAL_ORDER, DEN, DIRECTION_DELTAS, RIVER, TRAPS, AnimalChessService


animal_chess_cmd = on_command("斗兽棋", aliases={"斗兽棋帮助"}, block=True, priority=13)
animal_chess_bet_cmd = on_command("斗兽棋下注", aliases={"下注斗兽棋"}, block=True, priority=13)
animal_chess_view_bets_cmd = on_command("查看斗兽棋下注", aliases={"斗兽棋下注情况"}, block=True, priority=13)


@animal_chess_cmd.handle()
async def handle_animal_chess(event: MessageEvent, args: Message = CommandArg()):
    session_id = event.get_session_id()
    if not session_id.startswith("group_"):
        await animal_chess_cmd.finish("⛔ 斗兽棋只能在群聊中进行")

    group_id = session_id.split("_")[1]
    args_text = args.extract_plain_text().strip()
    if not args_text or args_text == "帮助":
        await animal_chess_cmd.finish(_animal_markdown(_help_text()))
    if args_text in ("规则", "游戏规则", "玩法"):
        await _send_rules_image(animal_chess_cmd)
        await animal_chess_cmd.finish(
            _animal_markdown(
                f"{cmd('创建房间', '斗兽棋 创建')}  "
                f"{cmd('加入房间', '斗兽棋 加入')}  "
                f"{cmd('查看棋盘', '斗兽棋 棋盘')}"
            )
        )

    async with safe_session() as session:
        player = await require_player(session, event, animal_chess_cmd)

        service = AnimalChessService(session)

        if args_text == "创建":
            success, msg, room = await service.create_room(player.id, group_id)
            if not success or not room:
                await animal_chess_cmd.finish(message_add_head(f"❌ {msg}", event))
            await animal_chess_cmd.finish(
                _animal_markdown(
                    "🐾 斗兽棋房间创建成功！\n"
                    "━━━━━━━━━━━━━\n"
                    f"房间ID：{room.room_id}\n"
                    f"蓝方：{player.nickname}[UID:{player.uid}]\n"
                    "红方：等待加入\n"
                    "━━━━━━━━━━━━━\n"
                    f"{cmd('加入房间', '斗兽棋 加入')}  "
                    f"{cmd('查看规则', '斗兽棋 规则')}  "
                    f"{cmd('查看状态', '斗兽棋 状态')}  "
                    f"{cmd('退出房间', '斗兽棋 退出')}\n"
                    "双方入场后设置主押注。",
                )
            )

        if args_text == "加入":
            success, msg, room = await service.join_group_room(player.id, group_id)
            if not success or not room:
                await animal_chess_cmd.finish(message_add_head(f"❌ {msg}", event))
            p1 = await session.get(Player, room.player1_id)
            await animal_chess_cmd.finish(
                _animal_markdown(
                    "✅ 成功加入斗兽棋房间！\n"
                    "━━━━━━━━━━━━━\n"
                    f"蓝方：{_player_label(p1)}\n"
                    f"红方：{_player_label(player)}\n"
                    "━━━━━━━━━━━━━\n"
                    f"{_bet_amount_links()}\n"
                    f"{cmd('查看下注', '查看斗兽棋下注')}  "
                    f"{cmd('查看规则', '斗兽棋 规则')}  "
                    f"{cmd('查看状态', '斗兽棋 状态')}",
                )
            )

        if args_text.startswith("筹码 "):
            amount_text = args_text[3:].strip()
            try:
                gold = int(amount_text)
            except ValueError:
                await animal_chess_cmd.finish("⛔ 金币数必须是数字，例如：斗兽棋 筹码 1000")

            success, msg, details = await service.set_bet(player.id, gold)
            if not success:
                await animal_chess_cmd.finish(message_add_head(f"❌ {msg}", event))

            lines = [
                "💰 斗兽棋筹码设置成功！",
                "━━━━━━━━━━━━━",
                f"你的投注：{gold}金币",
                f"对手投注：{details.get('opponent_gold', 0)}金币" if details.get("opponent_gold") else "对手投注：尚未设置",
            ]
            if details.get("both_ready"):
                lines.extend(
                    [
                        "━━━━━━━━━━━━━",
                        f"奖池总额：{details['total_pool']}金币",
                        f"系统税收：{details['tax_amount']}金币（3%）",
                        f"获胜可得：{details['final_reward']}金币起",
                        f"{cmd('开始棋局', '斗兽棋 开始')}  {cmd('查看规则', '斗兽棋 规则')}  {cmd('查看下注', '查看斗兽棋下注')}",
                    ]
                )
            else:
                lines.append("等待对手设置筹码...")
                lines.append(_bet_amount_links())
                lines.append(cmd("查看规则", "斗兽棋 规则"))
            await animal_chess_cmd.finish(_animal_markdown("\n".join(lines)))

        if args_text == "开始":
            success, msg, room, game = await service.start_game(player.id)
            if not success or not room or not game:
                await animal_chess_cmd.finish(message_add_head(f"❌ {msg}", event))
            players = await _players_by_id(session, [room.player1_id, room.player2_id])
            current = players.get(game.current_player_id)
            current_side = AnimalChessService.get_player_side(room, game.current_player_id)
            board = json.loads(game.board_state)
            await _send_board_image(
                animal_chess_cmd,
                "🐾 斗兽棋开始！",
                board,
                room,
                players,
                current,
                game.turn_count,
                None,
            )
            await animal_chess_cmd.finish(
                _animal_markdown(
                    f"先手：{_player_label(current)}\n"
                    "━━━━━━━━━━━━━\n"
                    f"{_move_links(board, current_side)}\n"
                    f"{cmd('刷新棋盘', '斗兽棋 棋盘')}  {cmd('查看规则', '斗兽棋 规则')}  {cmd('查看下注', '查看斗兽棋下注')}  {cmd('投降', '斗兽棋 投降')}"
                )
            )

        if args_text in ("状态", "棋盘"):
            room = await service.find_player_active_room(player.id) or await service.find_group_active_room(group_id)
            if not room:
                await animal_chess_cmd.finish("⛔ 本群暂无斗兽棋房间")
            players = await _players_by_id(session, [room.player1_id, room.player2_id])
            game = await service.find_active_game(room.room_id)
            lines = [
                f"🐾 斗兽棋房间 {room.room_id}",
                "━━━━━━━━━━━━━",
                f"状态：{room.status}",
                _format_room_players(room, players),
                f"蓝方押注：{room.player1_gold_bet}金币",
                f"红方押注：{room.player2_gold_bet}金币",
            ]
            if game:
                current = players.get(game.current_player_id)
                current_side = AnimalChessService.get_player_side(room, game.current_player_id)
                board = json.loads(game.board_state)
                lines.extend(
                    [
                        "━━━━━━━━━━━━━",
                        f"回合：{game.turn_count}",
                        f"当前行动：{_player_label(current)}",
                    ]
                )
                last_move_text = AnimalChessService.describe_move(json.loads(game.last_move)) if game.last_move else None
                if last_move_text:
                    lines.append(f"最近一步：{last_move_text}")
                await _send_board_image(
                    animal_chess_cmd,
                    "🐾 斗兽棋棋盘",
                    board,
                    room,
                    players,
                    current,
                    game.turn_count,
                    last_move_text,
                )
                lines.extend(["━━━━━━━━━━━━━", _move_links(board, current_side)])
            lines.append(f"{cmd('刷新棋盘', '斗兽棋 棋盘')}  {cmd('查看规则', '斗兽棋 规则')}  {cmd('查看下注', '查看斗兽棋下注')}  {cmd('投降', '斗兽棋 投降')}")
            await animal_chess_cmd.finish(_animal_markdown("\n".join(lines)))

        if args_text.startswith("走 "):
            parts = args_text.split()
            if len(parts) != 3:
                await animal_chess_cmd.finish("⛔ 格式：斗兽棋 走 棋子 方向，例如：斗兽棋 走 虎 上")
            result = await service.move_piece(player.id, parts[1], parts[2])
            if not result.success:
                await animal_chess_cmd.finish(message_add_head(f"❌ {result.message}", event))

            room = await service.find_player_active_room(player.id)
            game = await service.find_active_game(room.room_id) if room else None
            if game:
                players = await _players_by_id(session, [room.player1_id, room.player2_id])
                current = players.get(game.current_player_id)
                current_side = AnimalChessService.get_player_side(room, game.current_player_id)
                board = json.loads(game.board_state)
                await _send_board_image(
                    animal_chess_cmd,
                    "✅ 斗兽棋走子成功",
                    board,
                    room,
                    players,
                    current,
                    game.turn_count,
                    result.message,
                )
                await animal_chess_cmd.finish(
                    _animal_markdown(
                        f"✅ {result.message}\n"
                        "━━━━━━━━━━━━━\n"
                        f"轮到：{_player_label(current)}\n"
                        f"{_move_links(board, current_side)}\n"
                        f"{cmd('刷新棋盘', '斗兽棋 棋盘')}  {cmd('查看规则', '斗兽棋 规则')}  {cmd('投降', '斗兽棋 投降')}"
                    )
                )
            await animal_chess_cmd.finish(message_add_head(f"✅ {result.message}", event))

        if args_text == "投降":
            room = await service.find_player_active_room(player.id)
            if not room or room.status != AnimalChessRoomStatus.PLAYING.value:
                await animal_chess_cmd.finish("⛔ 你不在进行中的斗兽棋房间中")
            game = await service.find_active_game(room.room_id)
            if not game:
                await animal_chess_cmd.finish("⛔ 游戏状态异常")
            winner_id = room.get_opponent_id(player.id)
            if not winner_id:
                await animal_chess_cmd.finish("⛔ 找不到对手，无法投降")
            game.status = "finished"
            game.winner_id = winner_id
            room.status = AnimalChessRoomStatus.FINISHED.value
            session.add_all([room, game])
            success, reward_msg = await service.finish_game(room, winner_id)
            if not success:
                await animal_chess_cmd.finish(message_add_head(f"❌ {reward_msg}", event))
            await animal_chess_cmd.finish(_animal_markdown(f"🏳️ {_player_label(player)}投降\n{reward_msg}"))

        if args_text in ("退出", "离开"):
            success, msg = await service.leave_room(player.id)
            await animal_chess_cmd.finish(_animal_markdown(("✅ " if success else "❌ ") + msg + f"\n{cmd('创建新房', '斗兽棋 创建')}"))

    await animal_chess_cmd.finish("⚠️ 未知指令，发送【斗兽棋】查看帮助")


@animal_chess_bet_cmd.handle()
async def handle_animal_chess_bet(event: MessageEvent, args: Message = CommandArg()):
    session_id = event.get_session_id()
    if not session_id.startswith("group_"):
        await animal_chess_bet_cmd.finish("⛔ 斗兽棋下注只能在群聊中使用")

    group_id = session_id.split("_")[1]
    parts = args.extract_plain_text().strip().split()
    if len(parts) < 2:
        await animal_chess_bet_cmd.finish(_animal_markdown("📝 用法：斗兽棋下注 玩家昵称/UID 金币数\n示例：斗兽棋下注 张三 500\n" + cmd("查看房间", "斗兽棋 状态")))

    target_text = " ".join(parts[:-1])
    try:
        gold_amount = int(parts[-1])
    except ValueError:
        await animal_chess_bet_cmd.finish("⛔ 金币数必须是数字")

    async with safe_session() as session:
        bettor = await get_unified_player(session, event)
        if not bettor:
            await animal_chess_bet_cmd.finish("⛔ 请先创建角色")

        service = AnimalChessService(session)
        room = await service.find_group_active_room(group_id)
        if not room:
            await animal_chess_bet_cmd.finish("⛔ 本群暂无活跃斗兽棋房间")

        players = await _players_by_id(session, [room.player1_id, room.player2_id])
        target = _match_player(target_text, players.values())
        if not target:
            await animal_chess_bet_cmd.finish(
                _animal_markdown(
                "⛔ 找不到可下注玩家\n"
                "━━━━━━━━━━━━━\n"
                f"{_format_room_players(room, players)}"
                )
            )

        success, msg = await service.place_bet(bettor.id, room, target.id, gold_amount)
        if not success:
            await animal_chess_bet_cmd.finish(message_add_head(f"❌ {msg}", event))
        await animal_chess_bet_cmd.finish(
            _animal_markdown(
                "🎲 斗兽棋下注成功！\n"
                "━━━━━━━━━━━━━\n"
                f"支持玩家：{target.nickname}[UID:{target.uid}]\n"
                f"下注金额：{gold_amount}金币\n"
                "游戏结束后自动结算\n"
                f"{cmd('查看下注', '查看斗兽棋下注')}  {cmd('查看规则', '斗兽棋 规则')}  {cmd('查看棋盘', '斗兽棋 棋盘')}",
            )
        )


@animal_chess_view_bets_cmd.handle()
async def handle_animal_chess_view_bets(event: MessageEvent):
    session_id = event.get_session_id()
    if not session_id.startswith("group_"):
        await animal_chess_view_bets_cmd.finish("⛔ 此指令只能在群聊中使用")

    group_id = session_id.split("_")[1]
    async with safe_session() as session:
        service = AnimalChessService(session)
        room = await service.find_group_active_room(group_id)
        if not room:
            await animal_chess_view_bets_cmd.finish("⛔ 本群暂无活跃斗兽棋房间")
        bets = await service.get_room_bets(room.room_id)
        players = await _players_by_id(session, [room.player1_id, room.player2_id])
        p1_total = sum(bet.gold_amount for bet in bets if bet.target_player_id == room.player1_id)
        p2_total = sum(bet.gold_amount for bet in bets if bet.target_player_id == room.player2_id)
        p1_count = sum(1 for bet in bets if bet.target_player_id == room.player1_id)
        p2_count = sum(1 for bet in bets if bet.target_player_id == room.player2_id)
        await animal_chess_view_bets_cmd.finish(
            _animal_markdown(
                "🎲 斗兽棋旁观下注情况\n"
                "━━━━━━━━━━━━━\n"
                f"蓝方 {_player_label(players.get(room.player1_id))}：{p1_count}人，共{p1_total}金币\n"
                f"红方 {_player_label(players.get(room.player2_id))}：{p2_count}人，共{p2_total}金币\n"
                "━━━━━━━━━━━━━\n"
                "赢家支持者按投入比例瓜分输家支持者与输家主押注的金币\n"
                f"{cmd('查看棋盘', '斗兽棋 棋盘')}  {cmd('查看规则', '斗兽棋 规则')}  {cmd('开始棋局', '斗兽棋 开始')}",
            )
        )


def _help_text() -> str:
    return (
        "🐾 斗兽棋 PvP\n"
        "━━━━━━━━━━━━━\n"
        "规则：象>狮>虎>豹>狼>狗>猫>鼠；鼠可吃象，象不可吃鼠。\n"
        "鼠可入河，狮虎可跳河，河中有鼠时不能跳过。\n"
        "己方陷阱内的敌子可被任意己方棋子吃掉；进入对方兽穴或吃光对方棋子获胜。\n"
        "━━━━━━━━━━━━━\n"
        f"房间：{cmd('创建', '斗兽棋 创建')} / {cmd('加入', '斗兽棋 加入')} / {cmd('退出', '斗兽棋 退出')}\n"
        f"筹码：{_bet_amount_links()} / {cmd('开始', '斗兽棋 开始')}\n"
        "行动：斗兽棋 走 虎 上（方向：上/下/左/右）\n"
        f"查看：{cmd('规则', '斗兽棋 规则')} / {cmd('状态', '斗兽棋 状态')} / {cmd('棋盘', '斗兽棋 棋盘')}\n"
        f"认输：{cmd('投降', '斗兽棋 投降')}\n"
        f"旁观：斗兽棋下注 玩家名 金币数 / {cmd('查看下注', '查看斗兽棋下注')}\n"
        "━━━━━━━━━━━━━\n"
        "结算沿用恶魔轮盘：主押注+旁观支持者按赢方投入比例分配输方资产，系统税收3%。"
    )


def _animal_markdown(content: str):
    return build_markdown(f"# 诡修仙 · 斗兽棋\n***\n{content}")


def _bet_amount_links() -> str:
    return (
        f"{cmd('押1000', '斗兽棋 筹码 1000')}  "
        f"{cmd('押5000', '斗兽棋 筹码 5000')}  "
        f"{cmd('押10000', '斗兽棋 筹码 10000')}"
    )


async def _players_by_id(session, player_ids: list[str | None]) -> dict[str, Player]:
    ids = [player_id for player_id in dict.fromkeys(player_ids) if player_id]
    if not ids:
        return {}
    stmt = select(Player).where(Player.id.in_(ids))
    players = (await session.execute(stmt)).scalars().all()
    return {player.id: player for player in players}


def _player_label(player: Player | None) -> str:
    if not player:
        return "等待加入"
    return f"{player.nickname}[UID:{player.uid}]"


def _format_room_players(room, players: dict[str, Player]) -> str:
    return (
        f"蓝方：{_player_label(players.get(room.player1_id))}\n"
        f"红方：{_player_label(players.get(room.player2_id))}"
    )


def _match_player(text: str, players) -> Player | None:
    for player in players:
        if player and (player.nickname == text or str(player.uid) == text):
            return player
    return None


async def _send_board_image(matcher, title: str, board: list[dict], room, players: dict[str, Player], current: Player | None, turn_count: int, note: str | None):
    image_b64 = await asyncio.to_thread(_render_board_image_b64, board, room, players, current, turn_count, note)
    text = (
        f"{title}\n"
        "━━━━━━━━━━━━━\n"
        f"{_format_room_players(room, players)}\n"
        f"回合：{turn_count}\n"
        f"当前行动：{_player_label(current)}"
    )
    if note:
        text += f"\n最近一步：{note}"

    if image_b64:
        await matcher.send(Message(text).append(MessageSegment.file_image(image_b64)))
        return

    await matcher.send(message_add_head(text + "\n" + _render_board(board)))


async def _send_rules_image(matcher) -> None:
    image_b64 = await asyncio.to_thread(_render_rules_image_b64)
    text = (
        "📖 斗兽棋游戏规则\n"
        "━━━━━━━━━━━━━\n"
        "目标：进入对方兽穴，或吃光对方所有棋子。\n"
        "常用：鼠吃象，象不能吃鼠；狮虎可跳河；敌方进己方陷阱后任意子可吃。"
    )
    if image_b64:
        await matcher.send(Message(text).append(MessageSegment.file_image(image_b64)))
        return

    await matcher.send(message_add_head(text + "\n" + _rules_fallback_text()))


def _render_rules_image_b64() -> str | None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    img_w, img_h = 1220, 720
    img = Image.new("RGB", (img_w, img_h), (250, 247, 238))
    draw = ImageDraw.Draw(img)
    title_font = _load_font(ImageFont, 30)
    header_font = _load_font(ImageFont, 20)
    body_font = _load_font(ImageFont, 16)
    small_font = _load_font(ImageFont, 13)
    piece_font = _load_font(ImageFont, 22)

    draw.text((img_w // 2, 30), "📖 斗兽棋游戏规则", fill=(139, 72, 22), font=title_font, anchor="mm")

    left_x, right_x = 18, 625
    y = 64
    _draw_rule_card(draw, (left_x, y, 592, 176), "🎯 游戏目标", [
        "斗兽棋是两人策略棋。目标是让己方棋子进入对方兽穴，",
        "或者吃掉对方所有棋子。自己的棋子不能进入自己的兽穴。",
    ], header_font, body_font, (255, 251, 230), (244, 199, 61))

    y = 200
    _draw_rule_card(draw, (left_x, y, 592, 480), "🦁 动物等级", [
        "棋子按战力从高到低排列，高等级可吃低等级，同等级可互吃：",
    ], header_font, body_font, (255, 251, 230), (244, 199, 61))
    pieces = [("象", 8), ("狮", 7), ("虎", 6), ("豹", 5), ("狼", 4), ("狗", 3), ("猫", 2), ("鼠", 1)]
    for idx, (animal, rank) in enumerate(pieces):
        px = left_x + 18 + (idx % 4) * 136
        py = y + 86 + (idx // 4) * 92
        draw.rounded_rectangle((px, py, px + 128, py + 78), radius=8, fill=(255, 255, 249), outline=(244, 199, 61), width=1)
        draw.ellipse((px + 42, py + 9, px + 86, py + 53), fill=(255, 244, 239), outline=(205, 65, 56), width=2)
        draw.text((px + 64, py + 31), animal, fill=(185, 54, 48), font=piece_font, anchor="mm")
        draw.text((px + 64, py + 62), f"等级 {rank}", fill=(69, 77, 91), font=small_font, anchor="mm")

    y = 504
    _draw_rule_card(draw, (left_x, y, 592, 662), "🎮 移动规则", [
        "• 每次只能上下左右移动一格，不能斜走。",
        "• 不能移动到已有己方棋子的格子。",
        "• 除狮虎跳河外，不能越过其他棋子。",
        "• 进入对方兽穴立即获胜。",
    ], header_font, body_font, (255, 251, 230), (244, 199, 61))

    _draw_rule_card(draw, (right_x, 64, 1200, 172), "🐭 鼠吃象", [
        "鼠是唯一可以吃象的棋子，象不能吃鼠。",
        "注意：河里的鼠不能直接吃陆地上的象。",
    ], header_font, body_font, (238, 245, 255), (156, 190, 242))

    _draw_rule_card(draw, (right_x, 184, 1200, 272), "💧 河流", [
        "只有鼠可以进入河流。水中鼠只能吃水中鼠，不能吃岸上的棋子。",
    ], header_font, body_font, (233, 251, 252), (105, 211, 224))

    _draw_rule_card(draw, (right_x, 284, 1200, 352), "🦁🐯 跳跃", [
        "狮子和老虎可以横向或纵向跳过整条河。河中有任意鼠时，不能跳过。",
    ], header_font, body_font, (255, 246, 235), (247, 181, 105))

    _draw_rule_card(draw, (right_x, 364, 1200, 432), "🕳 陷阱", [
        "进入己方陷阱的敌方棋子战力归零，可被任意己方棋子吃掉。",
    ], header_font, body_font, (249, 241, 255), (210, 171, 245))

    _draw_rule_card(draw, (right_x, 444, 1200, 512), "🏠 兽穴", [
        "进入对方兽穴立即获胜；自己的棋子不能进入自己的兽穴。",
    ], header_font, body_font, (255, 240, 240), (245, 167, 167))

    _draw_rule_card(draw, (right_x, 528, 1200, 662), "🏆 胜负判定", [
        "• 己方棋子进入对方兽穴，获胜。",
        "• 吃掉对方所有棋子，获胜。",
        "• 对方主动投降，己方获胜。",
        "• 结算沿用恶魔轮盘：输方资金扣 3% 税后按赢方投入比例分配。",
    ], header_font, body_font, (237, 253, 243), (141, 224, 166))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _draw_rule_card(draw, box: tuple[int, int, int, int], title: str, lines: list[str], header_font, body_font, fill, outline) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=12, fill=fill, outline=outline, width=1)
    draw.text((x1 + 18, y1 + 18), title, fill=(124, 68, 24), font=header_font)
    text_y = y1 + 56
    for line in lines:
        draw.text((x1 + 18, text_y), line, fill=(54, 65, 82), font=body_font)
        text_y += 26


def _rules_fallback_text() -> str:
    return (
        "游戏目标：进入对方兽穴，或吃光对方棋子。\n"
        "等级：象>狮>虎>豹>狼>狗>猫>鼠，同级互吃。\n"
        "鼠：可吃象，象不可吃鼠；鼠可入河，河中鼠不能吃岸上象。\n"
        "河流：只有鼠能入河；狮虎可跳河，河中有鼠则不能跳。\n"
        "陷阱：敌方棋子进入己方陷阱后，可被任意己方棋子吃掉。\n"
        "兽穴：不能进自己的兽穴，进入对方兽穴立即获胜。"
    )


def _render_board_image_b64(board: list[dict], room, players: dict[str, Player], current: Player | None, turn_count: int, note: str | None) -> str | None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return None

    cell = 74
    margin_x = 44
    margin_top = 172
    footer_h = 72
    board_w = cell * 7
    board_h = cell * 9
    img_w = board_w + margin_x * 2
    img_h = margin_top + board_h + footer_h

    img = Image.new("RGB", (img_w, img_h), (248, 241, 222))
    draw = ImageDraw.Draw(img)

    title_font = _load_font(ImageFont, 30)
    info_font = _load_font(ImageFont, 18)
    small_font = _load_font(ImageFont, 14)
    piece_font = _load_font(ImageFont, 25)
    coord_font = _load_font(ImageFont, 15)

    # Background and title
    draw.rectangle((0, 0, img_w, img_h), fill=(250, 244, 228))
    draw.rounded_rectangle((22, 22, img_w - 22, img_h - 22), radius=18, fill=(150, 84, 28), outline=(102, 52, 16), width=4)
    draw.rounded_rectangle((34, 34, img_w - 34, img_h - 34), radius=14, fill=(246, 226, 163), outline=(188, 112, 28), width=3)

    draw.text((img_w // 2, 52), "斗 兽 棋", fill=(111, 56, 12), font=title_font, anchor="mm")
    draw.text((img_w // 2, 88), f"第 {turn_count} 回合 · 当前行动：{_player_label(current)}", fill=(84, 66, 45), font=info_font, anchor="mm")

    blue_name = _player_label(players.get(room.player1_id))
    red_name = _player_label(players.get(room.player2_id))
    badge_y1, badge_y2 = 108, 150
    draw.rounded_rectangle((margin_x, badge_y1, margin_x + 230, badge_y2), radius=10, fill=(232, 240, 255), outline=(153, 183, 244), width=1)
    draw.rounded_rectangle((img_w - margin_x - 230, badge_y1, img_w - margin_x, badge_y2), radius=10, fill=(255, 237, 234), outline=(242, 162, 154), width=1)
    draw.text((margin_x + 14, badge_y1 + 21), _fit_text(f"蓝方 {blue_name}", 16), fill=(40, 91, 197), font=small_font, anchor="lm")
    draw.text((img_w - margin_x - 14, badge_y1 + 21), _fit_text(f"红方 {red_name}", 16), fill=(190, 58, 52), font=small_font, anchor="rm")

    # Board cells
    board_x = margin_x
    board_y = margin_top
    draw.rounded_rectangle((board_x - 10, board_y - 10, board_x + board_w + 10, board_y + board_h + 10), radius=10, fill=(120, 64, 20))
    for row in range(9):
        for col in range(7):
            x1 = board_x + col * cell
            y1 = board_y + row * cell
            x2 = x1 + cell
            y2 = y1 + cell
            pos = (row, col)
            fill = (247, 219, 112)
            outline = (221, 171, 28)
            label = ""
            label_fill = (155, 118, 26)
            if pos in RIVER:
                fill = (102, 183, 197)
                outline = (57, 144, 170)
                label = "河"
                label_fill = (231, 252, 255)
            elif pos in (DEN["red"], DEN["blue"]):
                fill = (217, 54, 54) if pos == DEN["blue"] else (102, 79, 208)
                outline = (255, 218, 39)
                label = "穴"
                label_fill = (255, 245, 210)
            elif pos in TRAPS["red"] or pos in TRAPS["blue"]:
                fill = (238, 128, 93) if pos in TRAPS["blue"] else (124, 163, 188)
                outline = (255, 218, 39)
                label = "陷"
                label_fill = (255, 243, 216)

            draw.rounded_rectangle((x1 + 3, y1 + 3, x2 - 3, y2 - 3), radius=7, fill=fill, outline=outline, width=2)
            if pos in RIVER:
                for wave_y in range(y1 + 16, y2 - 8, 16):
                    draw.arc((x1 + 9, wave_y - 7, x1 + 35, wave_y + 7), 0, 180, fill=(183, 230, 236), width=2)
                    draw.arc((x1 + 35, wave_y - 7, x1 + 61, wave_y + 7), 180, 360, fill=(183, 230, 236), width=2)
            if label:
                draw.text((x1 + cell // 2, y1 + cell // 2), label, fill=label_fill, font=piece_font, anchor="mm")

    # Coordinates
    for col in range(7):
        draw.text((board_x + col * cell + cell // 2, board_y - 18), chr(ord("A") + col), fill=(95, 59, 23), font=coord_font, anchor="mm")
    for row in range(9):
        draw.text((board_x - 18, board_y + row * cell + cell // 2), str(row + 1), fill=(95, 59, 23), font=coord_font, anchor="mm")

    # Pieces
    for piece in board:
        if not piece["alive"]:
            continue
        row, col = piece["pos"]
        cx = board_x + col * cell + cell // 2
        cy = board_y + row * cell + cell // 2
        is_blue = piece["side"] == "blue"
        outer = (72, 116, 225) if is_blue else (211, 74, 66)
        inner = (238, 246, 255) if is_blue else (255, 241, 236)
        text_fill = (44, 91, 203) if is_blue else (184, 52, 47)
        draw.ellipse((cx - 28, cy - 28, cx + 28, cy + 28), fill=outer, outline=(255, 247, 205), width=3)
        draw.ellipse((cx - 22, cy - 22, cx + 22, cy + 22), fill=inner, outline=outer, width=2)
        draw.text((cx, cy), piece["animal"], fill=text_fill, font=piece_font, anchor="mm")

    footer = note or "进对方兽穴或吃光对方棋子获胜"
    draw.text((img_w // 2, img_h - 38), footer[:42], fill=(91, 58, 28), font=info_font, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _load_font(image_font_module, size: int):
    for path in (
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    ):
        try:
            return image_font_module.truetype(path, size)
        except OSError:
            continue
    return image_font_module.load_default()


def _fit_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


def _render_board(board: list[dict]) -> str:
    cells = [["  " for _ in range(7)] for _ in range(9)]
    for row in range(9):
        for col in range(7):
            pos = (row, col)
            if pos in RIVER:
                cells[row][col] = "河"
            elif pos in (DEN["red"], DEN["blue"]):
                cells[row][col] = "穴"
            elif pos in TRAPS["red"] or pos in TRAPS["blue"]:
                cells[row][col] = "陷"
            else:
                cells[row][col] = "· "

    for piece in board:
        if not piece["alive"]:
            continue
        prefix = "蓝" if piece["side"] == "blue" else "红"
        row, col = piece["pos"]
        cells[row][col] = prefix + piece["animal"]

    lines = ["```text", "    A  B  C  D  E  F  G"]
    for index, row in enumerate(cells, start=1):
        lines.append(f"{index:>2}  " + " ".join(row))
    lines.append("```")
    return "\n".join(lines)


def _move_links(board: list[dict], side: str | None) -> str:
    if not side:
        return "等待棋局开始。"

    service = AnimalChessService(None)
    links = []
    for animal in ANIMAL_ORDER:
        piece = service.find_piece(board, side, animal)
        if not piece:
            continue
        for direction in DIRECTION_DELTAS:
            if direction not in ("上", "下", "左", "右"):
                continue
            destination = service.resolve_destination(board, piece, direction)
            if destination is None:
                continue
            ok, _ = service.can_land(board, piece, destination)
            if ok:
                side_name = "蓝" if side == "blue" else "红"
                links.append(cmd(f"{side_name}{animal}{direction}", f"斗兽棋 走 {animal} {direction}"))

    if not links:
        return "当前没有可生成的合法走法，可检查是否已被困住。"
    return "可走步：\n" + "  ".join(links)
