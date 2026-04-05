from datetime import datetime
import random

from nonebot import on_command
from nonebot.adapters.qq import Message
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from ..platform_utils import get_unified_player

# ──────────────────────────────────────────────
# 猜拳鬼：镜中的同步者
# 每次与玩家出相同手势（平局），同步计数 +1
# 连续平局 2 次 → 替换事件触发，玩家被困入镜中
# 任意胜负 → 连续计数归零
# ──────────────────────────────────────────────

# {user_id: 连续平局次数}
_ghost_sync: dict[str, int] = {}

# ── 开场/游戏说明 ──────────────────────────────
_FLAVOR_INTRO = "【猜拳鬼】住在每一面镜子里，它正透过玻璃盯着你……"

# ── 平局恐怖文案（按同步层级）──────────────────
_TIE_TEXTS = [
    # 同步第1次（下一次即触发替换）
    (
        "你出了 {hand}——镜子里的影子也出了 {hand}。\n"
        "这很正常……应该是。\n"
        "「镜中鬼同步度：▓░」\n"
        "——平局，金币未变。镜面开始温热，再来一次……"
    ),
]

# ── 替换事件（第2次平局）──────────────────────
_REPLACE_EVENT = """\
▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
         镜 中 鬼 — 附 身
▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓

你出了 {hand}。
它……也出了 {hand}。

第二次。

镜面发出一声闷响。
你的影子不再随你移动——
它伸出手，穿过玻璃，
抓住了你的手腕。

冰冷。

下一刻，你已经在镜子里了。
猜拳鬼走了出来。

▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
【替换惩罚】它带走了你 30% 的金币——
  损失金币：{penalty}💰
  当前金币：{gold_left}💰
▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
（同步重置，你挣扎着爬回了镜外……）"""

# ── 胜利文案 ──────────────────────────────────
_WIN_TEXTS = [
    "你出了 {hand}，它出了 {ghost_hand}。\n"
    "镜中鬼怒拍玻璃，碎裂的纹路瞬间消失——\n"
    "🎉 你打破了同步！同步计数归零。\n"
    "💰 获得金币：+{gold_change}",

    "你出了 {hand}，它出了 {ghost_hand}。\n"
    "影子猛地向后踉跄，发出低沉的嘶鸣……\n"
    "✨ 胜利！镜面恢复平静。\n"
    "💰 获得金币：+{gold_change}",
]

# ── 失败文案 ──────────────────────────────────
_LOSE_TEXTS = [
    "你出了 {hand}，它出了 {ghost_hand}。\n"
    "「早就猜到了。」镜中传来低语——\n"
    "💸 失败。金币随着倒影沉入镜底。\n"
    "💰 损失金币：{gold_change}",

    "你出了 {hand}，它出了 {ghost_hand}。\n"
    "镜面泛起涟漪，像是在嘲弄你的选择……\n"
    "💀 失败。同步计数归零。\n"
    "💰 损失金币：{gold_change}",
]


# ──────────────────────────────────────────────
# 命令注册
# ──────────────────────────────────────────────
guess_fist = on_command("猜拳", priority=13, block=True)

@guess_fist.handle()
async def handle_fist_game(event: MessageEvent, args: Message = CommandArg()):
    """处理猜拳游戏（猜拳鬼版本）"""
    group_id = getattr(event, "group_id", None)
    if group_id is None:
        await guess_fist.finish("⛔ 猜拳指令只能在群聊中使用")

    if datetime.now().weekday() != 5:
        await guess_fist.finish("⛔ 猜拳小游戏仅限周六开放，请周六再来玩~")

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await guess_fist.finish("⛔ 请先创建角色")

        args_text = args.extract_plain_text().strip()
        parts = args_text.split()

        if len(parts) != 2:
            await guess_fist.finish(
                f"{_FLAVOR_INTRO}\n\n"
                "⚠️ 格式：猜拳 [石头/剪刀/布] [金币数]\n"
                "例：猜拳 石头 100\n\n"
                "⚠️ 警告：连续2次平局将触发镜鬼替换事件，损失30%金币。"
            )

        player_choice, bet_str = parts
        if player_choice not in ["石头", "剪刀", "布"]:
            await guess_fist.finish("⚠️ 请选择：石头、剪刀 或 布")

        try:
            bet = int(bet_str)
            if bet < 1000 or bet > 99999999:
                raise ValueError
        except ValueError:
            await guess_fist.finish("⚠️ 金币数必须为1000-99999999之间的整数")

        if player.gold < bet:
            await guess_fist.finish(f"❌ 金币不足 | 需要 {bet}💰 当前 {player.gold}💰")

        # 猜拳鬼出手
        ghost_choice = random.choice(["石头", "剪刀", "布"])
        win_map = {"石头": "剪刀", "剪刀": "布", "布": "石头"}

        user_id = event.get_user_id()
        current_sync = _ghost_sync.get(user_id, 0)

        # ── 平局：同步事件 ────────────────────────
        if player_choice == ghost_choice:
            current_sync += 1

            # 第2次平局 → 替换事件
            if current_sync >= 2:
                penalty = max(1000, int(player.gold * 0.3))
                penalty = min(penalty, player.gold)
                player.gold -= penalty
                gold_left = player.gold
                _ghost_sync[user_id] = 0

                session.add(player)
                await session.commit()

                msg = _REPLACE_EVENT.format(
                    hand=player_choice,
                    penalty=penalty,
                    gold_left=gold_left,
                )
                await guess_fist.finish(message_add_head(msg, event))

            else:
                _ghost_sync[user_id] = current_sync
                # 平局金币不变
                session.add(player)
                await session.commit()

                tier = current_sync - 1  # 0 or 1
                text = _TIE_TEXTS[tier].format(hand=player_choice)
                msg = (
                    f"🪞 猜拳鬼\n"
                    f"━━━━━━━━━━━━━\n"
                    f"{text}\n"
                    f"━━━━━━━━━━━━━\n"
                    f"💰 当前金币：{player.gold}"
                )
                await guess_fist.finish(message_add_head(msg, event))

        # ── 胜利 ─────────────────────────────────
        elif win_map[player_choice] == ghost_choice:
            player.gold += bet
            gold_change = bet
            _ghost_sync[user_id] = 0

            session.add(player)
            await session.commit()

            text = random.choice(_WIN_TEXTS).format(
                hand=player_choice,
                ghost_hand=ghost_choice,
                gold_change=gold_change,
            )
            msg = (
                f"🪞 猜拳鬼\n"
                f"━━━━━━━━━━━━━\n"
                f"{text}\n"
                f"━━━━━━━━━━━━━\n"
                f"💰 当前金币：{player.gold}"
            )
            await guess_fist.finish(message_add_head(msg, event))

        # ── 失败 ─────────────────────────────────
        else:
            player.gold -= bet
            gold_change = bet
            _ghost_sync[user_id] = 0

            session.add(player)
            await session.commit()

            text = random.choice(_LOSE_TEXTS).format(
                hand=player_choice,
                ghost_hand=ghost_choice,
                gold_change=gold_change,
            )
            msg = (
                f"🪞 猜拳鬼\n"
                f"━━━━━━━━━━━━━\n"
                f"{text}\n"
                f"━━━━━━━━━━━━━\n"
                f"💰 当前金币：{player.gold}"
            )
            await guess_fist.finish(message_add_head(msg, event))
