from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head

import random

# 🎲 骰子比大小：/押大小 金币数 大/小
dice_cmd = on_command(
    "押大小",
    aliases={"押大", "押小", "dice"},
    block=True,
    priority=5,
)


@dice_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """处理骰子押大小指令"""
    arg_str = args.extract_plain_text().strip()
    parts = arg_str.split()

    # 基本参数校验
    if len(parts) != 2:
        await dice_cmd.finish(
            "⚠️ 格式：/押大小 金币数 大/小\n示例：/押大小 100 大"
        )

    # 提取押注与大小
    if parts[0].isdigit():
        bet = int(parts[0])
        guess = parts[1]
    elif parts[1].isdigit():
        bet = int(parts[1])
        guess = parts[0]
    else:
        await dice_cmd.finish("⚠️ 必须包含金币数，例如：/押大小 200 小")

    if guess not in {"大", "小", "big", "small"}:
        await dice_cmd.finish("⚠️ 请选择 大 或 小 进行押注")

    try:
        if bet < 1 or bet > 1_000_000:
            raise ValueError
    except ValueError:
        await dice_cmd.finish("❌ 金币数必须为 1-1000000 之间的整数")

    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await dice_cmd.finish("⛔ 请先创建角色")

        # 金币检查
        if player.gold < bet:
            await dice_cmd.finish(f"💸 金币不足，需要 {bet}，当前 {player.gold}")

        # 扣除押注
        player.gold -= bet
        session.add(player)

        # 掷骰子
        die1 = random.randint(1, 6)
        die2 = random.randint(1, 6)
        total = die1 + die2

        outcome = "大" if total >= 8 else "小" if total <= 6 else "7"

        win = False
        jackpot = False  # 爆点 2 或 12

        if total in {2, 12}:
            jackpot = True

        # 判断胜负
        if outcome in {"大", "小"} and outcome == ("大" if guess in {"大", "big"} else "小"):
            win = True

        # 结算
        if total == 7:
            # 幸运 7：无论押大押小都算玩家获胜，给予 3 倍奖励
            multiplier = 3
            reward = bet * multiplier
            player.gold += reward
            result_text = f"🍀 幸运数字 7！奖励 ×{multiplier}，获得 {reward} 金币"
            icon = "🍀"
        elif win:
            multiplier = 5 if jackpot else 2
            reward = bet * multiplier
            player.gold += reward
            result_text = (
                "🎉 胜利！" + ("🎁 爆点 ×5！" if jackpot else "") + f" 获得 {reward} 金币"
            )
            icon = "✨"
        else:
            # 玩家失败
            result_text = "💔 押注失败，金币已被庄家收走"
            icon = "💸"

        await session.commit()

        # 构造消息
        msg_lines = [
            f"{icon} 骰子比大小结果",
            "━━━━━━━━━━",
            f"🎲 骰子：{die1} + {die2} = {total} ➡️ {outcome}",
            f"📝 你的选择：{ '大' if guess in {'大', 'big'} else '小' }  | 押注：{bet} 金币",
            f"📣 {result_text}",
            f"💰 当前金币：{player.gold}",
        ]

        await dice_cmd.finish(message_add_head("\n".join(msg_lines), event)) 