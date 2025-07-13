from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from sqlalchemy import select, func, asc, desc
from sqlalchemy.orm import selectinload
from ..models.db import safe_session
from ..models.market_order import MarketOrder, OrderSide
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..config import config
from ..utils import message_add_head

MAX_LISTINGS = 6  # 每位玩家最大挂牌数
AUTO_MATCH = True

# ---------------- 指令：挂牌 ----------------
list_cmd = on_command("挂牌", block=True, priority=5)

@list_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """挂牌 出售/收购 物品名 单价 数量"""
    params = args.extract_plain_text().strip().split()
    if len(params) != 4:
        await list_cmd.finish("⛔ 格式错误：挂牌 出售/收购 物品名 单价 数量")

    mode_str, item_name, price_str, qty_str = params
    if mode_str not in ("出售", "收购"):
        await list_cmd.finish("⛔ 挂牌类型必须为 出售 或 收购")

    side = OrderSide.SELL if mode_str == "出售" else OrderSide.BUY
    # 参数校验
    try:
        price = int(price_str)
        quantity = int(qty_str)
        if price < 10 or quantity <= 0:
            raise ValueError
    except ValueError:
        await list_cmd.finish("⛔ 单价不能低于10，数量必须为正整数")

    # 物品模板
    item_cfg = config.items_config["by_name"].get(item_name)
    if not item_cfg:
        await list_cmd.finish(f"⛔ 不存在物品：{item_name}")

    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await list_cmd.finish("⛔ 请先创建角色")

        # 开仓数检查
        open_cnt_stmt = select(func.count()).select_from(MarketOrder).where(
            MarketOrder.player_id == player.id
        )
        open_cnt = (await session.execute(open_cnt_stmt)).scalar()
        if open_cnt >= MAX_LISTINGS:
            await list_cmd.finish(f"⛔ 你已挂满 {MAX_LISTINGS} 个牌子，请先撤回后再挂牌\n"
                                  f"⬇️ 【撤牌 <牌子ID>】\n"
                                  f"⬇️ 【查牌 <物品名> [页数]】")

        # 资源冻结
        if side == OrderSide.SELL:
            try:
                await ItemInstance.consume_item(session, player.id, item_cfg.item_id, quantity)
            except ValueError as e:
                await list_cmd.finish(f"⛔ 挂牌失败：{e}")
        else:  # BUY: 冻结金币
            cost = price * quantity
            if player.gold < cost:
                await list_cmd.finish("⛔ 金币不足")
            player.gold -= cost
            session.add(player)

        # 创建新订单
        new_order = MarketOrder(
            player_id=player.id,
            side=side,
            item_id=item_cfg.item_id,
            price=price,
            quantity=quantity,
        )
        session.add(new_order)

        await session.flush()  # 获取 new_order.id

        # 自动撮合（规则取决于 auto_match 配置）
        fill_msg = await _try_auto_match(session, new_order, player, same_price_only=not AUTO_MATCH)

        await session.commit()

    result_msg = f"📈 成功挂牌 #{new_order.id} {mode_str}{item_cfg.name} ✖️{quantity} @{price}💰" + ("\n" + fill_msg if fill_msg else "")
    await list_cmd.finish(message_add_head(result_msg, event))

# ---------------- 指令：撤牌 ----------------
cancel_cmd = on_command("撤牌", block=True, priority=5)

@cancel_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    oid_str = args.extract_plain_text().strip()
    if not oid_str.isdigit():
        await cancel_cmd.finish("⛔ 格式：撤牌 牌子ID")
    oid = int(oid_str)

    async with safe_session() as session:
        order: MarketOrder | None = await session.get(MarketOrder, oid)
        if not order or order.player_id != event.get_user_id():
            await cancel_cmd.finish("⛔ 无效牌子")

        player = await session.get(Player, event.get_user_id())

        if order.side == OrderSide.SELL:
            # 退回剩余物品
            await ItemInstance.add_item(session, player.id, order.item_id, order.quantity)
        else:
            # 退回剩余金币
            player.gold += order.price * order.quantity
            session.add(player)

        await session.delete(order)
        await session.commit()

    await cancel_cmd.finish(message_add_head(f"🗑️ 已撤回牌子 #{oid}", event))

# ---------------- 指令：查看牌子 ----------------
view_cmd = on_command("查牌",aliases={"比价"}, block=True, priority=5)

@view_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    params = args.extract_plain_text().strip().split()
    if not params:
        await view_cmd.finish("⛔ 格式：查牌 物品名 [页数]")

    item_name = params[0]
    page = 1
    if len(params) == 2:
        try:
            page = int(params[1])
            if page < 1:
                raise ValueError
        except ValueError:
            await view_cmd.finish("⛔ 页数必须为正整数")

    item_cfg = config.items_config["by_name"].get(item_name)
    if not item_cfg:
        await view_cmd.finish(f"⛔ 不存在物品：{item_name}")

    async with safe_session() as session:
        stmt_sell = select(MarketOrder).options(selectinload(MarketOrder.player)).where(
            MarketOrder.item_id == item_cfg.item_id,
            MarketOrder.side == OrderSide.SELL,
        ).order_by(asc(MarketOrder.price), asc(MarketOrder.created_at))
        stmt_buy = select(MarketOrder).options(selectinload(MarketOrder.player)).where(
            MarketOrder.item_id == item_cfg.item_id,
            MarketOrder.side == OrderSide.BUY,
        ).order_by(desc(MarketOrder.price), asc(MarketOrder.created_at))
        sells = (await session.execute(stmt_sell)).scalars().all()
        buys = (await session.execute(stmt_buy)).scalars().all()

        def _fmt(order: MarketOrder):
            return f"#{order.id} {order.price}💰 ✖️{order.quantity} (UID {order.player.uid})"

        PAGE_SIZE = 10
        def _paginate(lst: list[MarketOrder]):
            total_pages = (len(lst) - 1) // PAGE_SIZE + 1 if lst else 1
            p = max(1, min(page, total_pages))
            start = (p - 1) * PAGE_SIZE
            end = start + PAGE_SIZE
            return lst[start:end], total_pages, p

        sell_page, sell_total, cur_page = _paginate(sells)
        buy_page, _, _ = _paginate(buys)

        lines = [f"💰 市场牌子 · {item_cfg.name} 第{cur_page}/{sell_total}页"]
        lines.append("━━ 出售 ━━")
        if sell_page:
            lines.extend(_fmt(o) for o in sell_page)
        else:
            lines.append("(空)")
        lines.append("━━ 收购 ━━")
        if buy_page:
            lines.extend(_fmt(o) for o in buy_page)
        else:
            lines.append("(空)")

        await view_cmd.finish(message_add_head("\n".join(lines), event))

# ======= 辅助函数 =======
async def _try_auto_match(session, new_order: MarketOrder, player: Player, same_price_only: bool = False) -> str:
    """自动撮合逻辑，返回描述信息（可能为空）。"""
    if new_order.side == OrderSide.BUY:
        # 买单 → 查找卖单
        price_cond = (MarketOrder.price == new_order.price) if same_price_only else (MarketOrder.price <= new_order.price)
        stmt = select(MarketOrder).where(
            MarketOrder.item_id == new_order.item_id,
            MarketOrder.side == OrderSide.SELL,
            price_cond,
        ).order_by(asc(MarketOrder.price), asc(MarketOrder.created_at))
        opposite_orders = (await session.execute(stmt)).scalars().all()
    else:
        # 卖单 → 查找买单
        price_cond = (MarketOrder.price == new_order.price) if same_price_only else (MarketOrder.price >= new_order.price)
        stmt = select(MarketOrder).where(
            MarketOrder.item_id == new_order.item_id,
            MarketOrder.side == OrderSide.BUY,
            price_cond,
        ).order_by(desc(MarketOrder.price), asc(MarketOrder.created_at))
        opposite_orders = (await session.execute(stmt)).scalars().all()

    remaining = new_order.quantity
    trade_lines: list[str] = []
    original_qty = new_order.quantity
    total_spent = 0  # BUY 单实际花费

    for opp in opposite_orders:
        if remaining == 0:
            break
        trade_qty = min(remaining, opp.quantity)
        trade_price = opp.price  # 成交价按对手价
        buyer_id = new_order.player_id if new_order.side == OrderSide.BUY else opp.player_id
        seller_id = opp.player_id if new_order.side == OrderSide.BUY else new_order.player_id

        # 资金与物品处理
        buyer: Player = await session.get(Player, buyer_id)
        seller: Player = await session.get(Player, seller_id)
        item_cfg = new_order.item

        # 物品给买家
        await ItemInstance.add_item(session, buyer.id, item_cfg.item_id, trade_qty)
        # 金币给卖家
        seller.gold += trade_price * trade_qty

        # 更新对手单
        opp.quantity -= trade_qty
        if opp.quantity == 0:
            await session.delete(opp)

        remaining -= trade_qty
        if new_order.side == OrderSide.BUY:
            total_spent += trade_price * trade_qty
        trade_lines.append(f"⚖️ 成交 {trade_qty} 个 @{trade_price}💰")

    # 更新当前单剩余
    new_order.quantity = remaining
    if remaining == 0:
        await session.delete(new_order)

    # 退款处理（仅买单）
    if new_order.side == OrderSide.BUY:
        frozen_total = original_qty * new_order.price
        refund = frozen_total - total_spent - remaining * new_order.price
        if refund > 0:
            player.gold += refund

    return "\n".join(trade_lines) 