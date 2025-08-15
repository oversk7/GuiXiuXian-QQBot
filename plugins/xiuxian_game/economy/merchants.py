from __future__ import annotations

"""跑商系统 & 缉邪司总部商店

跑商系统规则：
1. 仅限现实世界（region == "大都会"）。
2. 市场坐标固定；列表见 MARKETS。
3. 价格：每天 09:00 刷新，基于日期+市场ID+item_id 生成哈希随机数。
4. 必须玩家坐标与市场坐标一致才可交易。

缉邪司总部规则：
1. 位于风雪镇(-5,390)
2. 使用公会积分兑换装备升阶相关特殊物品
3. 即使没有所属公会也可以使用（如果有积分）
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
from ..models.trade_record import TradeRecord, TradeType
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
    "art_book", "concert_ticket", "fountain_pen", "sneakers", "noise_headphones","yin_grass","blood_pact"
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



async def _price_for(session, market: Market, item_id: str) -> Tuple[int, int]:
    """返回 (sell_price, buy_price) - 优化的动态价格系统

    价格计算逻辑：
    1. 基础价格 × 随机波动(±30%) × 供需因子(0.5-2.0倍)
    2. 收购价 = 售价 × 75%-85% (利润率15%-25%)
    3. 限制最大利润率不超过100%

    改进内容：
    - 适度价格波动范围，平衡套利机会与游戏平衡
    - 合理利润率，增加跑商收益但不过度
    - 增强供需因子影响，让市场更动态
    """
    item_cfg = config.items_config["by_id"].get(item_id)
    base_price = item_cfg.price or 1

    # 获取或创建市场状态
    market_state = await MarketState.get_or_create(session, market.id, item_id)

    # 检查是否需要每日刷新
    await market_state.check_daily_refresh(session)

    # -------- 基础随机波动（调整到±30%，平衡价格差异与游戏平衡） --------
    seed_str = f"{market.id}:{item_id}:{_current_seed_day().isoformat()}"
    seed_int = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
    rng_local = random.Random(seed_int)
    random_factor = rng_local.uniform(0.7, 1.3)  # ±30% 浮动，适度价格差异

    # -------- 动态供需因子 --------
    supply_demand_factor = market_state.get_price_multiplier()

    # -------- 最终价格计算 --------
    final_factor = random_factor * supply_demand_factor

    # 限制最终因子，确保价格不会过于极端
    final_factor = min(final_factor, 2.0)  # 最大不超过基础价格的2倍
    final_factor = max(final_factor, 0.5)  # 最小不低于基础价格的0.5倍

    sell_price = max(1, int(base_price * final_factor))

    # 收购价：保持利润率在15-25%
    buy_price_ratio = rng_local.uniform(0.75, 0.85)  # 75%-85%，平均80%，利润率15-25%
    buy_price = max(1, int(sell_price * buy_price_ratio))

    return sell_price, buy_price

# ------------------- 指令 -------------------
market_cmd = on_command("市集", aliases={"商店", "市场"}, block=True, priority=5)

list_market_cmd = on_command("市集列表", aliases={"市场列表", "全部市集"}, block=True, priority=5)
# 查看指定市集商品
detail_market_cmd = on_command("市集详情", aliases={"市集价格", "市场报价"}, block=True, priority=5)

# 查看某物品在各市集的买/卖价
price_compare_cmd = on_command("市价", block=True, priority=5)

# 跑商记录：查看玩家的交易历史
trade_history_cmd = on_command("跑商记录", block=True, priority=5)

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

        # 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        market = MARKET_BY_COORD.get((current_x, current_y))
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
        lines.append("━━━━━━━━━━━━━\n💡 价格受供需影响，库存有限先到先得")
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

        # 检查是否为市集购买 - 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        market = MARKET_BY_COORD.get((current_x, current_y))
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

            # 检查背包商品总量限制（防止高等级玩家垄断库存）
            result_inv = await session.execute(
                select(ItemInstance).where(
                    ItemInstance.player_id == player.id,
                    ItemInstance.item_id.in_(goods_ids)  # 只统计跑商商品
                )
            )
            current_goods = result_inv.scalars().all()
            current_goods_total = sum(item.quantity for item in current_goods)

            if current_goods_total + qty > 500:
                await buy_cmd.finish(message_add_head(
                    f"❌ 商品携带量限制！\n"
                    f"━━━━━━━━━━━━━\n"
                    f"📦 当前商品总量：{current_goods_total}\n"
                    f"🛒 尝试购买：{qty}\n"
                    f"⚖️ 携带上限：500\n"
                    f"━━━━━━━━━━━━━\n"
                    f"💡 请先出售部分商品再购买", event))

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

            # 记录交易
            await TradeRecord.record_trade(
                session=session,
                player_id=player.id,
                trade_type=TradeType.BUY,
                market_id=market.id,
                item_id=item_cfg.item_id,
                quantity=qty,
                unit_price=sell_price,
                total_amount=total_cost
            )

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

        # 检查是否在市集 - 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        market = MARKET_BY_COORD.get((current_x, current_y))
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

        # 检查是否违反同地点交易限制（减少到4小时）
        can_sell = await TradeRecord.can_sell_at_market(session, player.id, market.id, item_cfg.item_id, hours=4)
        if not can_sell:
            # 获取最近的购买记录用于提示
            recent_purchases = await TradeRecord.get_recent_purchases_at_market(session, player.id, market.id, item_cfg.item_id, hours=4)
            if recent_purchases:
                latest_purchase = recent_purchases[0]
                from datetime import timedelta
                unlock_time = latest_purchase.trade_time + timedelta(hours=4)
                await sell_cmd.finish(message_add_head(
                    f"⛔ 同地点交易限制！\n"
                    f"你在 {latest_purchase.trade_time.strftime('%H:%M')} 于此地购买了 {item_cfg.name}\n"
                    f"需要等到 {unlock_time.strftime('%H:%M')} 才能在此地出售\n"
                    f"💡 建议：前往其他市集出售该商品", event))

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

        # 计算跑商奖励（异地出售奖励）
        bonus = 0
        bonus_msg = ""
        # 检查是否为跨市场交易（在不同市场出售）
        recent_purchases = await TradeRecord.get_recent_purchases_at_market(session, player.id, market.id, item_cfg.item_id, hours=24)
        if not recent_purchases:  # 没有在本地购买记录，说明是从其他地方运来的
            # 给予5%的跑商奖励
            bonus = int(total_gain * 0.05)
            if bonus > 0:
                bonus_msg = f"\n🎁 跨市场交易奖励：+{bonus} 金币"

        # 更新玩家金币和市场状态
        player.gold += total_gain + bonus
        market_state.apply_sale(qty)

        # 记录交易
        await TradeRecord.record_trade(
            session=session,
            player_id=player.id,
            trade_type=TradeType.SELL,
            market_id=market.id,
            item_id=item_cfg.item_id,
            quantity=qty,
            unit_price=buy_price,
            total_amount=total_gain
        )

        session.add_all([player, market_state])
        await session.commit()

        await sell_cmd.finish(message_add_head(
            f"💰 卖出 {item_cfg.name}×{qty} 成功！\n🪙 获得 {total_gain + bonus} 金币{bonus_msg}\n"
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

# -------- 交易记录 --------

@trade_history_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """查看玩家的交易记录"""
    args_text = args.extract_plain_text().strip()
    page = 1
    if args_text:
        try:
            page = int(args_text)
            if page < 1:
                page = 1
        except ValueError:
            pass

    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await trade_history_cmd.finish("⛔ 请先创建角色")

        # 查询交易记录
        from sqlalchemy import select, desc
        stmt = select(TradeRecord).where(
            TradeRecord.player_id == player.id
        ).order_by(desc(TradeRecord.trade_time)).limit(10).offset((page - 1) * 10)

        result = await session.execute(stmt)
        records = result.scalars().all()

        if not records:
            await trade_history_cmd.finish("📋 暂无交易记录")

        lines = [f"📋 交易记录 (第{page}页)", "━━━━━━━━━━━━━"]

        for record in records:
            # 获取商品和市场信息
            item_cfg = config.items_config["by_id"].get(record.item_id)
            market = next((m for m in MARKETS if m.id == record.market_id), None)

            trade_type_emoji = "🛒" if record.trade_type == TradeType.BUY else "💰"
            trade_type_text = "购买" if record.trade_type == TradeType.BUY else "出售"

            item_name = item_cfg.name if item_cfg else record.item_id
            market_name = market.name if market else record.market_id

            lines.append(
                f"{trade_type_emoji} {trade_type_text} {item_name}×{record.quantity}\n"
                f"   📍 {market_name} | 💰 {record.total_amount}金币\n"
                f"   🕐 {record.trade_time.strftime('%m-%d %H:%M')}"
            )

        lines.append("━━━━━━━━━━━━━")
        lines.append("💡 使用【交易记录 页数】查看更多")

        await trade_history_cmd.finish(message_add_head("\n".join(lines), event))

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

                        # 限制利润率不超过100%
                        if margin > 1.0:  # 利润率超过100%
                            # 调整收购价，使利润率刚好为100%
                            buy_p_dst = sell_p_src * 2  # 100%利润率
                            profit = buy_p_dst - sell_p_src
                            margin = 1.0

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

# 系统商店商品
SHOP_ITEMS = [
    "revive_potion", "rename_card", "president_letter", "territory_expansion_scroll","heal_potion","spirit_herb"
]

# 普通商店指令
shop_cmd = on_command("系统商店", aliases={"特殊商店"}, block=True, priority=5)

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

        lines = ["🏬 系统商店", "━━━━━━━━━━━━━"]
        for item_id in SHOP_ITEMS:
            item_cfg = config.items_config["by_id"].get(item_id)
            lines.append(f"{item_cfg.name}│{item_cfg.price} 金币")
        lines.append("━━━━━━━━━━━━━\n⬇️【购买 [物品] [数量]】")
        await shop_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 缉邪司总部商店系统 ====================

# 缉邪司总部坐标
HEADQUARTERS_COORD = (-5, 390)

# 缉邪司总部商品配置（物品ID: 积分价格）
HEADQUARTERS_ITEMS = {
    "upgrade_stone_low": 300,        # 初级升阶石
    "upgrade_stone_mid": 2000,       # 中级升阶石
    "stabilizer_crystal": 10000,      # 稳定水晶
    "gem_hammer": 300,               # 镶嵌锤
    "gem_chisel": 300,               # 拆卸凿
    "accuracy_bead_1": 500,          # 一级命中佛珠
    # 抗暴符文系列
    "anti_crit_rune_1": 600,         # 一级抗暴符文
    "anti_crit_rune_2": 1200,        # 二级抗暴符文
    "anti_crit_rune_3": 2400,        # 三级抗暴符文
    "anti_crit_rune_4": 4800,        # 四级抗暴符文
    "anti_crit_rune_5": 9600         # 五级抗暴符文
}

# 缉邪司总部商店指令
headquarters_cmd = on_command("缉邪司总部", aliases={"总部商店", "总部"}, block=True, priority=5)

@headquarters_cmd.handle()
async def _(event: MessageEvent):
    """缉邪司总部商店"""
    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await headquarters_cmd.finish("⛔ 请先创建角色")

        if player.region != "大都会":
            await headquarters_cmd.finish(message_add_head(
                "💀 诡域之中皆不可信\n"
                "━━━━━━━━━━━━━\n"
                "此地没有安全商人。\n"
                "━━━━━━━━━━━━━\n"
                "⬇️ 【返回】脱离诡域，返回现实", event))

        # 检查是否在缉邪司总部坐标 - 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        if (current_x, current_y) != HEADQUARTERS_COORD:
            await headquarters_cmd.finish(message_add_head(
                "🏛️ 缉邪司总部商店\n"
                "━━━━━━━━━━━━━\n"
                f"📍 总部位置：风雪镇 {HEADQUARTERS_COORD}\n"
                f"📍 当前位置：({current_x},{current_y})\n"
                "━━━━━━━━━━━━━\n"
                "🧭 请前往风雪镇缉邪司总部", event))

        # 显示商店界面
        lines = [
            "🏛️ 缉邪司总部商店",
            "━━━━━━━━━━━━━",
            f"💎 当前积分：{player.gold2}",
            "━━━━━━━━━━━━━",
            "📦 装备升阶专用物品："
        ]

        # 分类显示商品
        upgrade_items = ["upgrade_stone_low", "upgrade_stone_mid", "stabilizer_crystal"]
        tool_items = ["gem_hammer", "gem_chisel"]
        gem_items = ["accuracy_bead_1"]
        anti_crit_items = ["anti_crit_rune_1", "anti_crit_rune_2", "anti_crit_rune_3",
                          "anti_crit_rune_4", "anti_crit_rune_5"]

        # 升阶材料
        for item_id in upgrade_items:
            if item_id in HEADQUARTERS_ITEMS:
                item_cfg = config.items_config["by_id"].get(item_id)
                if item_cfg:
                    lines.append(f"• {item_cfg.name} - {HEADQUARTERS_ITEMS[item_id]}✨积分")

        lines.append("")
        lines.append("🔨 镶嵌工具：")

        # 镶嵌工具
        for item_id in tool_items:
            if item_id in HEADQUARTERS_ITEMS:
                item_cfg = config.items_config["by_id"].get(item_id)
                if item_cfg:
                    lines.append(f"• {item_cfg.name} - {HEADQUARTERS_ITEMS[item_id]}✨积分")

        lines.append("")
        lines.append("💎 镶嵌物品：")

        # 普通镶嵌物
        for item_id in gem_items:
            if item_id in HEADQUARTERS_ITEMS:
                item_cfg = config.items_config["by_id"].get(item_id)
                if item_cfg:
                    lines.append(f"• {item_cfg.name} - {HEADQUARTERS_ITEMS[item_id]}✨积分")

        # 抗暴符文
        for item_id in anti_crit_items:
            if item_id in HEADQUARTERS_ITEMS:
                item_cfg = config.items_config["by_id"].get(item_id)
                if item_cfg:
                    lines.append(f"• {item_cfg.name} - {HEADQUARTERS_ITEMS[item_id]}✨积分")

        lines.extend([
            "━━━━━━━━━━━━━",
            "💡 使用方法：【总部兑换 物品名称 数量】",
            "💡 即使没有公会也可以使用积分兑换",
            "💡 积分可通过公会捐献、签到等方式获得"
        ])

        await headquarters_cmd.finish(message_add_head("\n".join(lines), event))


# 缉邪司总部兑换指令
headquarters_exchange_cmd = on_command("总部兑换", aliases={"缉邪司兑换"}, block=True, priority=5)

@headquarters_exchange_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """缉邪司总部兑换物品"""
    arg_text = args.extract_plain_text().strip()
    if not arg_text:
        await headquarters_exchange_cmd.finish("⛔ 格式：总部兑换 物品名称 [数量]")

    parts = arg_text.split()
    item_name = parts[0]
    quantity = 1

    if len(parts) > 1:
        try:
            quantity = int(parts[1])
            if quantity <= 0:
                await headquarters_exchange_cmd.finish("⛔ 数量必须大于0")
        except ValueError:
            await headquarters_exchange_cmd.finish("⛔ 数量必须是正整数")

    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await headquarters_exchange_cmd.finish("⛔ 请先创建角色")

        if player.region != "大都会":
            await headquarters_exchange_cmd.finish("⛔ 诡域中无法使用缉邪司服务")

        # 检查是否在缉邪司总部坐标 - 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        if (current_x, current_y) != HEADQUARTERS_COORD:
            await headquarters_exchange_cmd.finish("⛔ 请前往风雪镇(-5,390)缉邪司总部")

        # 查找物品配置
        item_cfg = config.items_config["by_name"].get(item_name)
        if not item_cfg:
            await headquarters_exchange_cmd.finish(f"⛔ 未找到物品：{item_name}")

        # 检查是否为总部商品
        if item_cfg.item_id not in HEADQUARTERS_ITEMS:
            available_items = "、".join([
                config.items_config["by_id"][iid].name
                for iid in HEADQUARTERS_ITEMS.keys()
                if iid in config.items_config["by_id"]
            ])
            await headquarters_exchange_cmd.finish(
                f"⛔ 缉邪司总部不出售该物品\n"
                f"📦 可兑换物品：{available_items}")

        # 计算总积分消耗
        unit_cost = HEADQUARTERS_ITEMS[item_cfg.item_id]
        total_cost = unit_cost * quantity

        # 检查积分是否足够
        if player.gold2 < total_cost:
            await headquarters_exchange_cmd.finish(
                f"⛔ 积分不足\n"
                f"💎 需要：{total_cost}积分\n"
                f"💎 拥有：{player.gold2}积分\n"
                f"💎 缺少：{total_cost - player.gold2}积分")

        # 检查背包空间并添加物品
        try:
            await ItemInstance.add_item(session, player.id, item_cfg.item_id, quantity)
        except ValueError as e:
            await headquarters_exchange_cmd.finish(f"⛔ {e}")

        # 扣除积分
        player.gold2 -= total_cost
        await session.commit()

        await headquarters_exchange_cmd.finish(message_add_head(
            f"✅ 兑换成功！\n"
            f"📦 获得：{item_cfg.name} ×{quantity}\n"
            f"💎 消耗：{total_cost}积分\n"
            f"💎 剩余：{player.gold2}积分", event))
