from __future__ import annotations

"""跑商系统

规则：
1. 仅限现实世界（region == "大都会"）。
2. 市场坐标固定；列表见 MARKETS。
3. 价格：每天 09:00 刷新，基于日期+市场ID+item_id 生成哈希随机数。
   - 出售价 = base_price * rand(0.8,1.2)
   - 收购价 = 出售价 * 0.7（向上取整）
4. 指令：
   • 商店            查看当前坐标市场价格表
   • 购买 物品 数量   消耗金币购买
   • 出售 物品 数量   将背包物品卖给市场
5. 必须玩家坐标与市场坐标一致才可交易。
"""

from datetime import datetime, time, timedelta, date
import random
from typing import Dict, Tuple, List

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import Inventory
from ..utils import message_add_head
from ..config import config

# ------------------- 市场配置 -------------------
class Market:
    def __init__(self, mid: str, name: str, coord: Tuple[int, int], items: List[str]):
        self.id = mid
        self.name = name
        self.x, self.y = coord
        self.items = items

goods_ids = [
    "lux_perfume", "red_wine", "yin_grass","gold_watch", "diamond_ring", "silk_scarf",
    "dslr_camera", "smartphone", "blood_pact", "gaming_console", "designer_bag", "luxury_chocolate",
    "art_book", "concert_ticket", "fountain_pen", "sneakers", "noise_headphones",
    "heal_potion", "spirit_herb"
]

# 生成重叠商品列表：每个市场拥有 5 个商品，起始索引按 3 步进，形成交叠
def _goods_for_merchant(idx: int, slice_size: int = 5) -> List[str]:
    start = (idx * 3) % len(goods_ids)  # 步进 3，产生重叠
    return [goods_ids[(start + j) % len(goods_ids)] for j in range(slice_size)]


# 市场基础信息（id, 显示名, 坐标）
_PROFILE_DATA = [
    ("merchant1", "上京", (0, 0)),
    ("merchant2", "北郊", (100, 460)),
    ("merchant3", "东郊", (390, 50)),
    ("merchant4", "西郊", (-420, 140)),
    ("merchant5", "南郊", (-100, -480)),
    ("merchant6", "金陵", (220, -350)),
    ("merchant7", "云岭", (-250, 490)),
    ("merchant8", "郸城", (120, 120)),
    ("merchant9", "荔湾镇", (120, 200)),
    ("merchant10", "摩配镇", (80, 140)),
    ("merchant11", "风雪镇", (-5, 390)),
]


# 创建市场实例，自动分配重叠商品
MARKETS: List[Market] = []
for idx, (mid, name, coord) in enumerate(_PROFILE_DATA):
    MARKETS.append(Market(mid, name, coord, _goods_for_merchant(idx)))

MARKET_BY_COORD: Dict[Tuple[int, int], Market] = {(m.x, m.y): m for m in MARKETS}

# ------------------- 工具函数 -------------------
_DEF_TIME = time(hour=9)


def _current_seed_day() -> date:
    """返回当前价格所属日期：若当前时间 <09:00 视为前一天。"""
    now = datetime.now()
    day = now.date()
    if now.time() < _DEF_TIME:
        day -= timedelta(days=1)
    return day


def _get_rng(merchant_id: str, item_id: str) -> random.Random:
    seed_str = f"{merchant_id}:{item_id}:{_current_seed_day().isoformat()}"
    return random.Random(hash(seed_str))


def _price_for(market: Market, item_id: str) -> Tuple[int, int]:
    """返回 (sell_price,buy_price) 整数金币"""
    item_cfg = config.items_config["by_id"].get(item_id)
    base_price = item_cfg.price or 1
    rng = _get_rng(market.id, item_id)
    factor = rng.uniform(0.8, 1.2)
    sell_price = max(1, int(base_price * factor))
    buy_price = max(1, int(sell_price * 0.7))
    return sell_price, buy_price

# ------------------- 指令 -------------------
market_cmd = on_command("市集", aliases={"商店", "市场"}, block=True, priority=5)

list_market_cmd = on_command("市集列表", aliases={"市场列表", "全部市集"}, block=True, priority=5)

# 查看指定市集商品
detail_market_cmd = on_command("市集详情", aliases={"市集价格", "市场报价"}, block=True, priority=5)

# 查看某物品在各市集的买/卖价
price_compare_cmd = on_command("市价", aliases={"物价", "比价"}, block=True, priority=5)

@market_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await market_cmd.finish("⛔ 请先创建角色")
        if player.region != "大都会":
            await market_cmd.finish("⛔ 诡域中没有安全商人！")

        market = MARKET_BY_COORD.get((player.x, player.y))
        if not market:
            # 展示所有市场坐标
            lines = ["🏪 可交易地点一览", "━━━━━━━━━━━━━"]
            for m in MARKETS:
                lines.append(f"• {m.name} ({m.x},{m.y})")
            lines.append("━━━━━━━━━━━━━\n🧭 前往对应坐标后输入【市集】联系当地商人")
            await market_cmd.finish(message_add_head("\n".join(lines), event))

        lines = [f"🏪 {market.name} ({market.x},{market.y})", "━━━━━━━━━━━━━"]
        for iid in market.items:
            item_cfg = config.items_config["by_id"].get(iid)
            sell_p, buy_p = _price_for(market, iid)
            lines.append(f"{item_cfg.name}│售 {sell_p}│收 {buy_p}")
        lines.append("━━━━━━━━━━━━━\n⬇️【购买 [物品] [数量]】\n⬇️【出售 [物品] [数量]】")
        await market_cmd.finish(message_add_head("\n".join(lines), event))

# -------- 购买 --------
buy_cmd = on_command("购买",aliases={"买"}, block=True, priority=5)

@buy_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    parts = arg_text.split()
    if len(parts) != 2:
        await buy_cmd.finish("📦 格式：购买 物品名 数量")
    item_name, qty_str = parts
    if not qty_str.isdigit():
        await buy_cmd.finish("❌ 数量需为正整数")
    qty = int(qty_str)
    if qty <= 0:
        await buy_cmd.finish("❌ 数量需大于0")

    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await buy_cmd.finish("⛔ 请先创建角色")
        if player.region != "大都会":
            await buy_cmd.finish("⛔ 诡域中无法与商人交易")
        market = MARKET_BY_COORD.get((player.x, player.y))
        if not market:
            await buy_cmd.finish("⛔ 这里没有商人")
        item_cfg = config.items_config["by_name"].get(item_name)
        if not item_cfg or item_cfg.item_id not in market.items:
            await buy_cmd.finish("⛔ 商人不出售该物品")

        sell_p, _ = _price_for(market, item_cfg.item_id)
        total_cost = sell_p * qty
        if player.gold < total_cost:
            await buy_cmd.finish(f"💰 金币不足，需要 {total_cost} (当前 {player.gold})")

        # 背包容量检查（考虑单格上限）
        from ..models.inventory import STACK_SIZE
        inv_rows = (await session.execute(
            select(Inventory).where(Inventory.player_id == player.id)
        )).scalars().all()
        current_slots = sum(r.slot_count for r in inv_rows)

        inv_item = next((r for r in inv_rows if r.item_id == item_cfg.item_id), None)

        import math
        if inv_item:
            added_slots = math.ceil((inv_item.quantity + qty) / STACK_SIZE) - inv_item.slot_count
        else:
            added_slots = math.ceil(qty / STACK_SIZE)

        if current_slots + added_slots > player.inventory_capacity:
            await buy_cmd.finish("🎒 背包已满，无法购买新物品！")

        # 扣款 & 添物
        player.gold -= total_cost
        await Inventory.add_item(session, player.id, item_cfg.item_id, qty)
        await session.commit()
        await buy_cmd.finish(message_add_head(
            f"✅ 购买 {item_cfg.name}×{qty} 成功！\n💸 花费 {total_cost} 金币", event))

# -------- 卖出 --------
sell_cmd = on_command("出售", aliases={"卖"}, block=True, priority=5)

@sell_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    parts = arg_text.split()
    if len(parts) != 2:
        await sell_cmd.finish("📦 格式：出售 物品名 数量")
    item_name, qty_str = parts
    if not qty_str.isdigit():
        await sell_cmd.finish("❌ 数量需为正整数")
    qty = int(qty_str)
    if qty <= 0:
        await sell_cmd.finish("❌ 数量必须大于0")

    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await sell_cmd.finish("⛔ 请先创建角色")
        if player.region != "大都会":
            await sell_cmd.finish("⛔ 诡域中无法与商人交易！")
        market = MARKET_BY_COORD.get((player.x, player.y))
        if not market:
            await sell_cmd.finish("⛔ 这里只有风～没有商人")
        item_cfg = config.items_config["by_name"].get(item_name)
        if not item_cfg or item_cfg.item_id not in market.items:
            await sell_cmd.finish("⛔ 商人不收购该物品")

        # 检查库存（聚合数量）
        inv_rows = (await session.execute(
            select(Inventory).where(Inventory.player_id == player.id, Inventory.item_id == item_cfg.item_id)
        )).scalars().all()
        total_qty = sum(r.quantity for r in inv_rows)
        if total_qty < qty:
            await sell_cmd.finish("❌ 背包数量不足")

        _, buy_price = _price_for(market, item_cfg.item_id)
        total_gain = buy_price * qty

        # 更新：优先扣未满堆叠
        success_consume = await Inventory.consume_item(session, player.id, item_cfg.item_id, qty)
        if not success_consume:
            await session.rollback()
            await sell_cmd.finish("❌ 扣除物品失败")

        player.gold += total_gain
        await session.commit()
        await sell_cmd.finish(message_add_head(
            f"💰 卖出 {item_cfg.name}×{qty} 成功！\n🪙 获得 {total_gain} 金币", event))

# -------- 市集列表 --------

@list_market_cmd.handle()
async def _(event: MessageEvent):
    """显示所有市集坐标列表（无论玩家当前位置）。"""
    lines = ["🏪 全部市集坐标", "━━━━━━━━━━━━━"]
    for m in MARKETS:
        lines.append(f"• {m.name} ({m.x},{m.y})")
    lines.append("━━━━━━━━━━━━━\n🧭 到达坐标后发送【市集】进行交易")
    await list_market_cmd.finish(message_add_head("\n".join(lines), event))

# -------- 市集详情 --------

@detail_market_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    market_name = args.extract_plain_text().strip()
    if not market_name:
        await detail_market_cmd.finish("⛔ 格式：市集详情 市集名称  （示例：市集详情 荔湾镇）")

    market = next((m for m in MARKETS if m.name == market_name), None)
    if not market:
        names = "、".join(m.name for m in MARKETS)
        await detail_market_cmd.finish(f"⛔ 未找到市集：{market_name}。可选：{names}")

    lines = [f"🏪 {market.name} ({market.x},{market.y})", "━━━━━━━━━━━━━"]
    for iid in market.items:
        item_cfg = config.items_config["by_id"].get(iid)
        sell_p, buy_p = _price_for(market, iid)
        lines.append(f"{item_cfg.name}│售 {sell_p}│收 {buy_p}")
    lines.append("━━━━━━━━━━━━━\n🧭 到达坐标后发送【市集】进行交易")

    await detail_market_cmd.finish(message_add_head("\n".join(lines), event))

# -------- 市价 --------

@price_compare_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    item_name = args.extract_plain_text().strip()
    if not item_name:
        await price_compare_cmd.finish("⛔ 格式：市价 物品名称  （示例：市价 回春散）")

    item_cfg = config.items_config["by_name"].get(item_name)
    if not item_cfg:
        await price_compare_cmd.finish(f"⛔ 未找到物品：{item_name}")

    lines = [f"💹 {item_cfg.name} 各市集价格", "━━━━━━━━━━━━━"]
    found = False
    for m in MARKETS:
        if item_cfg.item_id not in m.items:
            continue
        sell_p, buy_p = _price_for(m, item_cfg.item_id)
        lines.append(f"{m.name}│售 {sell_p}│收 {buy_p}")
        found = True

    if not found:
        await price_compare_cmd.finish("ℹ️ 暂无市集出售该物品")

    await price_compare_cmd.finish(message_add_head("\n".join(lines), event)) 