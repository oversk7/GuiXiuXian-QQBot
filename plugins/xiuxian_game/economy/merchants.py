from __future__ import annotations

"""跑商系统

规则：
1. 仅限现实世界（region == "大都会"）。
2. 市场坐标固定；列表见 MARKETS。
3. 价格：每天 09:00 刷新，基于日期+市场ID+item_id 生成哈希随机数。
4. 必须玩家坐标与市场坐标一致才可交易。
"""

from datetime import datetime, time, timedelta, date
import random
import hashlib
from typing import Dict, Tuple, List

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..models.market_state import MarketState
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
    "lux_perfume", "red_wine","gold_watch", "diamond_ring", "silk_scarf",
    "dslr_camera", "smartphone", "gaming_console", "designer_bag", "luxury_chocolate",
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


async def _price_for(session, market: Market, item_id: str) -> Tuple[int, int]:
    """返回 (sell_price, buy_price) - 新的动态价格系统

    价格计算逻辑：
    1. 基础价格 × 随机波动(±20%) × 供需因子
    2. 收购价 = 售价 × 0.88 (降低利润率从15%到12%)
    """
    item_cfg = config.items_config["by_id"].get(item_id)
    base_price = item_cfg.price or 1

    # 获取或创建市场状态
    market_state = await MarketState.get_or_create(session, market.id, item_id)

    # 检查是否需要每日刷新
    await market_state.check_daily_refresh(session)

    # -------- 基础随机波动（适度扩大到±25%） --------
    seed_str = f"{market.id}:{item_id}:{_current_seed_day().isoformat()}"
    seed_int = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
    rng_local = random.Random(seed_int)
    random_factor = rng_local.uniform(0.75, 1.25)  # ±25% 浮动

    # -------- 动态供需因子 --------
    supply_demand_factor = market_state.get_price_multiplier()

    # -------- 最终价格计算 --------
    final_factor = random_factor * supply_demand_factor
    sell_price = max(1, int(base_price * final_factor))

    # 收购价：进一步降低利润率到约8-10%
    buy_price_ratio = rng_local.uniform(0.90, 0.92)  # 90%-92%，平均91%
    buy_price = max(1, int(sell_price * buy_price_ratio))

    return sell_price, buy_price

# ------------------- 指令 -------------------
market_cmd = on_command("市集", aliases={"商店", "市场"}, block=True, priority=5)

list_market_cmd = on_command("市集列表", aliases={"市场列表", "全部市集"}, block=True, priority=5)
# 查看指定市集商品
detail_market_cmd = on_command("市集详情", aliases={"市集价格", "市场报价"}, block=True, priority=5)

# 查看某物品在各市集的买/卖价
price_compare_cmd = on_command("市价", block=True, priority=5)

# 跑商推荐：列出可获利的买卖路线
trade_advise_cmd = on_command("跑商推荐", aliases={"套利", "赚差价"}, block=True, priority=5)

@market_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await market_cmd.finish("⛔ 请先创建角色")
        if player.region != "大都会":
            await market_cmd.finish(message_add_head(
                "💀 诡域之中皆不可信\n"
                "━━━━━━━━━━━━━\n"
                "此地没有安全商人。\n"
                "━━━━━━━━━━━━━\n"
                "⬇️ 【返回】脱离诡域，返回现实", event))

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
            sell_p, buy_p = await _price_for(session, market, iid)

            # 获取库存状态
            market_state = await MarketState.get_or_create(session, market.id, iid)
            stock_status = market_state.get_stock_status()
            stock_info = f"({market_state.current_stock})"

            lines.append(f"{item_cfg.name}│售 {sell_p}│收 {buy_p}│库存{stock_info}{stock_status}")
        lines.append("━━━━━━━━━━━━━\n� 购买和出售功能已恢复！\n💡 价格受供需影响，库存有限先到先得")
        await market_cmd.finish(message_add_head("\n".join(lines), event))

buy_cmd = on_command("购买", block=True, priority=5)

@buy_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    parts = arg_text.split()
    if len(parts) != 2:
        return
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
            await buy_cmd.finish(message_add_head(
                "💀 诡域之中皆不可信\n"
                "━━━━━━━━━━━━━\n"
                "此地没有安全商人。\n"
                "━━━━━━━━━━━━━\n"
                "⬇️ 【返回】脱离诡域，返回现实", event))

        # 检查是否为市集购买
        market = MARKET_BY_COORD.get((player.x, player.y))
        item_cfg = config.items_config["by_name"].get(item_name)
        if not item_cfg:
            await buy_cmd.finish("⛔ 不存在该物品")

        # 市集购买逻辑
        if market and item_cfg.item_id in market.items:
            # 获取市场状态
            market_state = await MarketState.get_or_create(session, market.id, item_cfg.item_id)
            await market_state.check_daily_refresh(session)

            # 检查库存
            if not market_state.can_purchase(qty):
                await buy_cmd.finish(f"❌ 库存不足！当前库存：{market_state.current_stock}，需要：{qty}")

            # 获取当前价格
            sell_price, _ = await _price_for(session, market, item_cfg.item_id)
            total_cost = sell_price * qty

            if player.gold < total_cost:
                await buy_cmd.finish(f"❌ 金币不足，需要 {total_cost} (当前 {player.gold})")

            # 先检查背包空间，再扣款
            try:
                await ItemInstance.add_item(session, player.id, item_cfg.item_id, qty)
            except ValueError as e:
                await buy_cmd.finish(f"❌ {e}")

            # 扣款并更新市场状态
            player.gold -= total_cost
            market_state.apply_purchase(qty)

            session.add_all([player, market_state])
            await session.commit()

            await buy_cmd.finish(message_add_head(
                f"✅ 购买 {item_cfg.name}×{qty} 成功！\n💸 花费 {total_cost} 金币\n"
                f"📦 剩余库存：{market_state.current_stock}", event))

        # 万事屋购买逻辑（保持不变）
        elif item_cfg.item_id in SHOP_ITEMS:
            total_cost = item_cfg.price * qty

            if player.gold < total_cost:
                await buy_cmd.finish(f"💰 金币不足，需要 {total_cost} (当前 {player.gold})")

            try:
                await ItemInstance.add_item(session, player.id, item_cfg.item_id, qty)
            except ValueError as e:
                await buy_cmd.finish(f"❌ {e}")

            player.gold -= total_cost
            await session.commit()
            await buy_cmd.finish(message_add_head(
                f"✅ 购买 {item_cfg.name}×{qty} 成功！\n💸 花费 {total_cost} 金币", event))
        else:
            await buy_cmd.finish("⛔ 此处无法购买该物品")

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
            await sell_cmd.finish(message_add_head(
                "💀 诡域之中皆不可信\n"
                "━━━━━━━━━━━━━\n"
                "此地没有安全商人。\n"
                "━━━━━━━━━━━━━\n"
                "⬇️ 【返回】脱离诡域，返回现实", event))

        # 检查是否在市集
        market = MARKET_BY_COORD.get((player.x, player.y))
        if not market:
            await sell_cmd.finish("⛔ 这里只有风～没有商人")

        item_cfg = config.items_config["by_name"].get(item_name)
        if not item_cfg or item_cfg.item_id not in market.items:
            await sell_cmd.finish("⛔ 商人不收购该物品")

        # 检查库存（聚合数量）
        inv_rows = (await session.execute(
            select(ItemInstance).where(ItemInstance.player_id == player.id, ItemInstance.item_id == item_cfg.item_id)
        )).scalars().all()
        total_qty = sum(r.quantity for r in inv_rows)
        if total_qty < qty:
            await sell_cmd.finish("❌ 背包数量不足")

        # 获取市场状态和当前价格
        market_state = await MarketState.get_or_create(session, market.id, item_cfg.item_id)
        await market_state.check_daily_refresh(session)

        _, buy_price = await _price_for(session, market, item_cfg.item_id)
        total_gain = buy_price * qty

        # 更新：优先扣未满堆叠
        success_consume = await ItemInstance.consume_item(session, player.id, item_cfg.item_id, qty)
        if not success_consume:
            await session.rollback()
            await sell_cmd.finish("❌ 扣除物品失败")

        # 更新玩家金币和市场状态
        player.gold += total_gain
        market_state.apply_sale(qty)

        session.add_all([player, market_state])
        await session.commit()

        await sell_cmd.finish(message_add_head(
            f"💰 卖出 {item_cfg.name}×{qty} 成功！\n🪙 获得 {total_gain} 金币\n"
            f"📦 市场库存：{market_state.current_stock}", event))

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

    async with safe_session() as session:
        lines = [f"🏪 {market.name} ({market.x},{market.y})", "━━━━━━━━━━━━━"]
        for iid in market.items:
            item_cfg = config.items_config["by_id"].get(iid)
            sell_p, buy_p = await _price_for(session, market, iid)

            # 获取库存状态
            market_state = await MarketState.get_or_create(session, market.id, iid)
            stock_status = market_state.get_stock_status()
            stock_info = f"({market_state.current_stock})"

            lines.append(f"{item_cfg.name}│售 {sell_p}│收 {buy_p}│库存{stock_info}{stock_status}")
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

    async with safe_session() as session:
        lines = [f"💹 {item_cfg.name} 各市集价格", "━━━━━━━━━━━━━"]
        found = False
        for m in MARKETS:
            if item_cfg.item_id not in m.items:
                continue
            sell_p, buy_p = await _price_for(session, m, item_cfg.item_id)

            # 获取库存状态
            market_state = await MarketState.get_or_create(session, m.id, item_cfg.item_id)
            stock_info = f"({market_state.current_stock})"

            lines.append(f"{m.name}│售 {sell_p}│收 {buy_p}│库存{stock_info}")
            found = True

        if not found:
            await price_compare_cmd.finish("ℹ️ 暂无市集出售该物品")

        await price_compare_cmd.finish(message_add_head("\n".join(lines), event))

# -------- 跑商推荐 --------

@trade_advise_cmd.handle()
async def _(event: MessageEvent):
    """遍历市集与商品，列出正利润路线（购买→售出）。"""
    async with safe_session() as session:
        opportunities = []
        for src in MARKETS:
            for iid in src.items:
                # 检查源市场库存
                src_state = await MarketState.get_or_create(session, src.id, iid)
                if not src_state.can_purchase(1):  # 至少要有1个库存
                    continue

                sell_p_src, _ = await _price_for(session, src, iid)
                for dst in MARKETS:
                    if dst is src or iid not in dst.items:
                        continue
                    _, buy_p_dst = await _price_for(session, dst, iid)
                    profit = buy_p_dst - sell_p_src
                    if profit > 0:
                        item_cfg = config.items_config["by_id"].get(iid)
                        margin = profit / sell_p_src if sell_p_src else 0
                        opportunities.append({
                            "item": item_cfg.name,
                            "from": src.name,
                            "to": dst.name,
                            "buy": sell_p_src,
                            "sell": buy_p_dst,
                            "profit": profit,
                            "margin": margin,
                            "src_stock": src_state.current_stock,
                        })

        if not opportunities:
            await trade_advise_cmd.finish("ℹ️ 今日暂无明显差价或库存不足，明天再来看看吧！")

        # 按利润降序排序，随机挑选前10条中的5条进行推荐
        opportunities.sort(key=lambda d: d["profit"], reverse=True)

        # 从前10条中随机选择5条，如果不足10条则全部选择
        import random as _rnd
        top_opportunities = opportunities[:10]  # 取前10条
        sample = _rnd.sample(top_opportunities, min(5, len(top_opportunities)))

        lines = ["💹 跑商盈利机会 (优质推荐)", "━━━━━━━━━━━━━"]
        for op in sample:
            lines.append(
                f"📦 {op['item']} (库存:{op['src_stock']})\n🛒 {op['from']} → {op['to']}  "+
                f"💸 {op['buy']} → 💰 {op['sell']}  "+
                f"📈 +{op['profit']} ({op['margin']*100:.0f}%)"
            )
            lines.append("──────────")

        await trade_advise_cmd.finish(message_add_head("\n".join(lines), event))

# 普通商店商品（只卖不收的特殊消耗品）
SHOP_ITEMS = [
    "revive_potion", "rename_card", "president_letter", "territory_expansion_scroll","spirit_herb","blood_pact"
]

# 普通商店指令
shop_cmd = on_command("万事屋", aliases={"特殊商店"}, block=True, priority=5)

@shop_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await shop_cmd.finish("⛔ 请先创建角色")
        if player.region != "大都会":
            await shop_cmd.finish(message_add_head(
                "💀 诡域之中皆不可信\n"
                "━━━━━━━━━━━━━\n"
                "此地没有安全商人。\n"
                "━━━━━━━━━━━━━\n"
                "⬇️ 【返回】脱离诡域，返回现实", event))

        lines = ["🏬 万事屋", "━━━━━━━━━━━━━"]
        for item_id in SHOP_ITEMS:
            item_cfg = config.items_config["by_id"].get(item_id)
            lines.append(f"{item_cfg.name}│{item_cfg.price} 金币")
        lines.append("━━━━━━━━━━━━━\n⬇️【购买 [物品] [数量]】")
        await shop_cmd.finish(message_add_head("\n".join(lines), event)) 
