from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

import random
from typing import List

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head

# ----------------------------
# 配置常量
# ----------------------------
MAX_ROD_LEVEL = 5  # 鱼竿最高等级
MAX_TRIES = 10     # 单次最多钓鱼次数
BASE_COST = 30     # 等级1的每次费用
COST_PER_LEVEL = 10  # 额外费用

# 鱼池设置：[(名称, 基础权重, 售价)]
FISH_POOL = [
    ("咸鱼🐟", 50, 5),
    ("鲫鱼🐠", 30, 20),
    ("锦鲤🎏", 15, 80),
    ("鲲🦈", 5, 300),
]

fishing_cmd = on_command("钓鱼", aliases={"fishing"}, block=True, priority=5)


def _parse_args(arg_str: str) -> tuple[int, int]:
    """解析参数，返回 (rod_level, tries)"""
    parts = arg_str.split()
    # 默认值
    rod_level = 1
    tries = 1
    if not parts:
        return rod_level, tries

    # 将参数中 <=MAX_ROD_LEVEL 识别为竿等级，其余当作次数
    digits = [p for p in parts if p.isdigit()]
    if not digits:
        return rod_level, tries
    if len(digits) == 1:
        val = int(digits[0])
        if val <= MAX_ROD_LEVEL:
            rod_level = val
        else:
            tries = val
    else:
        # 两个数字，第一个做竿等级，第二个做次数
        rod_level = int(digits[0])
        tries = int(digits[1])
    return rod_level, tries


def _random_fish(rod_level: int) -> tuple[str, int]:
    """根据竿等级随机一条鱼，返回 (名称, 售价)"""
    # 提升竿等级提高稀有鱼概率：权重调整公式
    weights: List[float] = []
    for name, base_w, price in FISH_POOL:
        # 权重 = 基础权重 / (1 + (price/100) * lvl_factor)
        # 简化为：稀有鱼价高 → 权重下降，但竿等级提升会减少抑制
        lvl_factor = 0.1 * rod_level
        adjusted = base_w / (1 + (price / 100) * (1 - lvl_factor))
        weights.append(adjusted)
    # 随机选择
    choice = random.choices(FISH_POOL, weights=weights, k=1)[0]
    return choice[0], choice[2]


@fishing_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_str = args.extract_plain_text().strip()
    rod_level, tries = _parse_args(arg_str)

    # 参数检查
    if rod_level < 1 or rod_level > MAX_ROD_LEVEL:
        await fishing_cmd.finish(f"⚠️ 鱼竿等级范围 1-{MAX_ROD_LEVEL}")
    if tries < 1 or tries > MAX_TRIES:
        await fishing_cmd.finish(f"⚠️ 钓鱼次数范围 1-{MAX_TRIES}")

    cost_per_try = BASE_COST + (rod_level - 1) * COST_PER_LEVEL
    total_cost = cost_per_try * tries

    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await fishing_cmd.finish("⛔ 请先创建角色")

        if player.gold < total_cost:
            await fishing_cmd.finish(
                f"💸 金币不足，需要 {total_cost}，当前 {player.gold}"
            )

        # 扣费
        player.gold -= total_cost

        catch_results: List[str] = []
        total_income = 0
        for _ in range(tries):
            fish_name, fish_price = _random_fish(rod_level)
            catch_results.append(f"{fish_name}（{fish_price}💰）")
            total_income += fish_price

        # 更新金币
        player.gold += total_income
        await session.commit()

        net = total_income - total_cost
        net_text = (
            f"📈 盈利 {net} 💰" if net >= 0 else f"📉 亏损 {abs(net)} 💰"
        )

        msg_lines = [
            "🎣 钓鱼结算",
            "━━━━━━━━━━",
            f"🪝 鱼竿等级：{rod_level}  |  尝试：{tries} 次",
            f"💸 花费：{total_cost} 金币",
            "🐟 收获：" + (", ".join(catch_results) if catch_results else "空军"),
            f"💰 卖出可得：{total_income} 金币",
            net_text,
            f"📦 当前金币：{player.gold}",
        ]

        await fishing_cmd.finish(message_add_head("\n".join(msg_lines), event)) 