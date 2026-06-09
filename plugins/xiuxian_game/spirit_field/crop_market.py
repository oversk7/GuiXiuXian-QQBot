"""
灵蔬市场 - 动态收购价格系统

价格机制:
- 每小时更新，以 hash(crop_id + YYYYMMDDHHH) 作为确定性种子，同一小时内全服价格一致
- 两层因子叠加：稀有度波动因子 + 时段加成因子
- 最终价格 = base_sell_price × 稀有度因子 × 时段因子
"""

import hashlib
from datetime import datetime, timedelta

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select, func

from ..models.db import AsyncSessionLocal
from ..models.inventory import ItemInstance
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..platform_utils import require_player
from .config import CropManager

# ==================== 服务实例 ====================

crop_manager = CropManager()

# ==================== 稀有度与时段配置 ====================

RARITY_NAMES = {
    "white": "白色",
    "green": "绿色",
    "blue": "蓝色",
    "purple": "紫色",
    "orange": "橙色",
}

RARITY_ICONS = {
    "white": "⚪",
    "green": "🟢",
    "blue": "🔵",
    "purple": "🟣",
    "orange": "🟠",
}

# 稀有度波动范围：(最小因子, 最大因子)
RARITY_FACTOR_RANGE = {
    "white":  (0.80, 1.25),  # ±22%
    "green":  (0.75, 1.40),  # ±33%
    "blue":   (0.65, 1.55),  # ±45%
    "purple": (0.55, 1.70),  # ±55%
    "orange": (0.45, 1.90),  # ±72%
}

# 时段加成：((开始小时, 结束小时), 加成因子, 时段描述)
TIME_SEGMENTS = [
    ((0,  6),  0.90, "深夜滞销"),
    ((6,  9),  1.05, "早市开市"),
    ((9,  12), 1.00, "平时段"),
    ((12, 15), 1.08, "午市旺盛"),
    ((15, 18), 1.00, "平时段"),
    ((18, 22), 1.12, "晚市高峰"),
    ((22, 24), 0.92, "收市前"),
]


# ==================== 价格计算函数 ====================

def _get_time_factor(hour: int) -> float:
    """根据小时获取时段加成因子"""
    for (start, end), factor, _ in TIME_SEGMENTS:
        if start <= hour < end:
            return factor
    return 1.0


def _get_time_name(hour: int) -> str:
    """根据小时获取时段名称"""
    for (start, end), _, name in TIME_SEGMENTS:
        if start <= hour < end:
            return name
    return "平时段"


def _get_rarity_factor(crop_id: str, rarity: str, hour_seed: str) -> float:
    """根据稀有度和小时种子计算稀有度波动因子（确定性）"""
    hash_input = f"{crop_id}_{hour_seed}"
    hash_bytes = hashlib.md5(hash_input.encode()).digest()
    # 取前4字节归一化到 [0, 1)
    hash_int = int.from_bytes(hash_bytes[:4], "big")
    ratio = hash_int / 0xFFFFFFFF
    min_factor, max_factor = RARITY_FACTOR_RANGE.get(rarity, (0.80, 1.25))
    return min_factor + ratio * (max_factor - min_factor)


def _get_hourly_price(crop_id: str, base_price: int, rarity: str, dt: datetime = None) -> int:
    """计算指定时间的市场收购价"""
    if dt is None:
        dt = datetime.now()
    hour_seed = dt.strftime("%Y%m%d%H")
    rarity_factor = _get_rarity_factor(crop_id, rarity, hour_seed)
    time_factor = _get_time_factor(dt.hour)
    price = round(base_price * rarity_factor * time_factor)
    return max(1, price)


def _get_last_hour_price(crop_id: str, base_price: int, rarity: str) -> int:
    """计算上一小时的市场收购价（用于趋势对比）"""
    last_hour = datetime.now() - timedelta(hours=1)
    return _get_hourly_price(crop_id, base_price, rarity, last_hour)


def _get_trend_arrow(current: int, last: int) -> str:
    """根据价格变化返回趋势箭头"""
    if last == 0:
        return "→"
    change_ratio = (current - last) / last
    if change_ratio > 0.10:
        return "↑↑"
    elif change_ratio > 0:
        return "↑"
    elif change_ratio == 0:
        return "→"
    elif change_ratio > -0.10:
        return "↓"
    else:
        return "↓↓"


# ==================== 菜市场指令 ====================

crop_market_cmd = on_command("菜市场", aliases={"灵蔬市场", "卖菜价格"}, priority=13, block=True)


@crop_market_cmd.handle()
async def handle_crop_market(event: MessageEvent):
    """【菜市场】- 查看当前灵蔬/诡药收购价（每小时变化）"""
    now = datetime.now()
    all_crops = crop_manager.get_all_crops()

    if not all_crops:
        await crop_market_cmd.finish("作物配置未加载，请联系管理员")

    # 计算距离下次整点刷新的时间
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    remaining = next_hour - now
    remaining_minutes = remaining.seconds // 60
    remaining_secs = remaining.seconds % 60

    time_name = _get_time_name(now.hour)

    msg = "灵蔬市场 - 今日行情\n"
    msg += "━━━━━━━━━━━━━\n"
    msg += f"时段: {now.strftime('%H:%M')} ({time_name})\n"
    msg += f"刷新倒计时: {remaining_minutes}分{remaining_secs}秒\n"
    msg += "━━━━━━━━━━━━━"

    # 按稀有度分组展示
    for rarity in ["white", "green", "blue", "purple", "orange"]:
        crops = [c for c in all_crops if c.rarity == rarity]
        if not crops:
            continue

        icon = RARITY_ICONS.get(rarity, "⚪")
        label = RARITY_NAMES.get(rarity, rarity)
        msg += f"\n{icon} {label}:\n"

        for crop in crops:
            current_price = _get_hourly_price(crop.crop_id, crop.sell_price, crop.rarity, now)
            last_price = _get_last_hour_price(crop.crop_id, crop.sell_price, crop.rarity)
            arrow = _get_trend_arrow(current_price, last_price)
            type_tag = "蔬" if crop.type == "VEGETABLE" else "药"
            msg += f"  {crop.name}[{type_tag}] {current_price}金 {arrow}\n"

    msg += "━━━━━━━━━━━━━\n"
    msg += "【卖菜 作物名 数量】出售作物"

    await crop_market_cmd.finish(msg)


# ==================== 卖菜指令 ====================

sell_crop_cmd = on_command("卖菜", aliases={"出售灵蔬"}, priority=13, block=True)


@sell_crop_cmd.handle()
async def handle_sell_crop(event: MessageEvent, args: Message = CommandArg()):
    """【卖菜 作物名 数量】- 按当前市场价出售作物"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await sell_crop_cmd.finish("用法: 卖菜 <作物名> <数量>\n例如: 卖菜 碧冥芹 10")

    parts = args_text.split()
    if len(parts) < 2:
        await sell_crop_cmd.finish("用法: 卖菜 <作物名> <数量>\n例如: 卖菜 碧冥芹 10")

    crop_name = parts[0]
    quantity_str = parts[1]

    try:
        quantity = int(quantity_str)
        if quantity <= 0:
            await sell_crop_cmd.finish("数量必须大于0")
    except ValueError:
        await sell_crop_cmd.finish("数量必须是数字")

    # 查找作物配置
    crop = crop_manager.get_crop_by_name(crop_name)
    if not crop:
        await sell_crop_cmd.finish(
            f"未找到作物【{crop_name}】\n使用【菜市场】查看可出售列表"
        )

    # 计算当前单价和总价
    now = datetime.now()
    unit_price = _get_hourly_price(crop.crop_id, crop.sell_price, crop.rarity, now)
    total_gold = unit_price * quantity

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await require_player(uow.session, event, sell_crop_cmd)

        # 检查背包库存
        result = await uow.session.execute(
            select(func.sum(ItemInstance.quantity)).where(
                ItemInstance.player_id == player.id,
                ItemInstance.item_id == crop.harvest_item_id,
            )
        )
        total_qty = result.scalar() or 0

        if total_qty < quantity:
            if total_qty == 0:
                await sell_crop_cmd.finish(f"背包中没有【{crop.name}】")
            else:
                await sell_crop_cmd.finish(
                    f"【{crop.name}】库存不足\n"
                    f"当前持有: {total_qty}个\n"
                    f"需要: {quantity}个"
                )

        # 扣除物品
        success = await ItemInstance.consume_item(
            uow.session, player.id, crop.harvest_item_id, quantity
        )
        if not success:
            await sell_crop_cmd.finish("扣除物品失败，请重试")

        # 增加金币
        player.gold += total_gold
        await uow.players.update(player)

        await sell_crop_cmd.finish(
            f"出售成功!\n"
            f"{crop.name} ×{quantity}\n"
            f"单价: {unit_price}金\n"
            f"收入: {total_gold:,}金\n"
            f"当前金币: {player.gold:,}"
        )
