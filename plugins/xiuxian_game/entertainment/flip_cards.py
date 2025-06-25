from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

import random
from typing import List, Tuple

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head

# ----------------------------
# 配置常量
# ----------------------------
MAX_FLIPS = 3         # 单次最多翻牌次数
COST_PER_FLIP = 50    # 每次翻牌成本

# 概率设置（按翻牌序号 1~3）
# (宝箱概率, 怪物概率) 其余为传送门
PROB_TABLE: List[Tuple[int, int]] = [
    (60, 25),  # 第一次 60% 宝 25% 怪 15% 门
    (50, 35),  # 第二次
    (40, 45),  # 第三次
]

# 宝箱奖励区间 (min,max)
REWARD_RANGE = (80, 200)
# 怪物罚金区间
PENALTY_RANGE = (40, 120)

flip_cmd = on_command("翻牌", aliases={"flip", "flipcards"}, block=True, priority=5)


def _parse_times(arg_str: str) -> int:
    """解析次数"""
    if not arg_str:
        return 1
    if not arg_str.isdigit():
        raise ValueError
    return int(arg_str)


@flip_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_str = args.extract_plain_text().strip()
    try:
        times = _parse_times(arg_str)
    except ValueError:
        await flip_cmd.finish("⚠️ 格式：/翻牌 [1-3]")

    if times < 1 or times > MAX_FLIPS:
        await flip_cmd.finish(f"⚠️ 翻牌次数需为 1-{MAX_FLIPS}")

    total_cost = times * COST_PER_FLIP

    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await flip_cmd.finish("⛔ 请先创建角色")

        if player.gold < total_cost:
            await flip_cmd.finish(f"💸 金币不足，需要 {total_cost}，当前 {player.gold}")

        # 扣除费用
        player.gold -= total_cost

        step_results = []
        accumulated_reward = 0
        triggered_monster = False
        triggered_portal = False

        for step in range(times):
            chest_p, monster_p = PROB_TABLE[step]
            portal_p = 100 - chest_p - monster_p
            roll = random.randint(1, 100)
            if roll <= chest_p:
                reward = random.randint(*REWARD_RANGE)
                accumulated_reward += reward
                step_results.append(f"第 {step+1} 张 → 🎁 宝箱 +{reward}💰")
            elif roll <= chest_p + monster_p:
                penalty = random.randint(*PENALTY_RANGE)
                player.gold = max(0, player.gold - penalty)  # 怪物附加罚金
                step_results.append(f"第 {step+1} 张 → 👾 怪物 -{penalty}💰 & 失去全部宝藏！")
                accumulated_reward = 0
                triggered_monster = True
                break
            else:
                step_results.append(f"第 {step+1} 张 → 🚪 传送门 | 立即结算！")
                triggered_portal = True
                break

        # 发放奖励（若有）
        if accumulated_reward > 0:
            player.gold += accumulated_reward

        await session.commit()

        # 结果汇总
        header_icon = "✨" if accumulated_reward else ("💥" if triggered_monster else "🔄")
        msg_lines = [
            f"{header_icon} 翻牌探险结果",
            "━━━━━━━━━━",
            f"🎲 本次翻牌：{times} 次 (花费 {total_cost}💰)",
            *step_results,
            f"📦 共获得：{accumulated_reward} 💰" if accumulated_reward else "💸 本次无收益！",
            f"💰 当前金币：{player.gold}",
        ]

        await flip_cmd.finish(message_add_head("\n".join(msg_lines), event)) 