from nonebot import on_command, on_message
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.rule import to_me
from sqlalchemy import select, func, asc, desc, and_
from sqlalchemy.orm import selectinload
from ..models.db import safe_session
from ..models.market_order import MarketOrder, OrderSide
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..config import config
from ..utils import message_add_head
from .equipment_trade_service import EquipmentTradeService

MAX_LISTINGS = 6  # 每位玩家最大挂牌数
AUTO_MATCH = True
# === 输出格式辅助 ===
EMOJI_SELL = "📤"  # 出售标识
EMOJI_BUY = "📥"   # 求购标识

# === 装备选择状态管理 ===
equipment_selection_state = {}  # {user_id: {"equipment_list": [...], "item_cfg": ..., "price": ...}}

def _cleanup_expired_states():
    """清理过期的装备选择状态（超过5分钟）"""
    import time
    current_time = time.time()
    expired_users = []

    for user_id, state in equipment_selection_state.items():
        if current_time - state.get("timestamp", 0) > 300:  # 5分钟过期
            expired_users.append(user_id)

    for user_id in expired_users:
        del equipment_selection_state[user_id]

def format_order_line(order_id: int, price: int, qty: int, uid: int) -> str:
    """统一的市场订单行格式，便于排版对齐"""
    return f"🆔{str(order_id).rjust(3)}┃💰{str(price).rjust(8)}┃📦{qty}"


def heavy_divider(title: str) -> str:
    """返回带有粗线分隔符的标题"""
    return f"━━ {title} ━━"


def calculate_transaction_tax(amount: int) -> int:
    """
    计算阶梯交易税率
    5000以下免税
    5000-20000: 5%
    20000-50000: 10%
    50000-100000: 15%
    100000以上: 20%
    """
    if amount <= 5000:
        return 0
    elif amount <= 20000:
        return int(amount * 0.05)
    elif amount <= 50000:
        return int(amount * 0.10)
    elif amount <= 100000:
        return int(amount * 0.15)
    else:
        return int(amount * 0.20)

# ---------------- 指令：挂牌 ----------------
list_cmd = on_command("挂牌", block=True, priority=5)

@list_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """挂牌 出售/收购 物品名 单价 [数量]"""
    params = args.extract_plain_text().strip().split()
    if len(params) < 3:
        await list_cmd.finish("⛔ 格式错误：挂牌 出售/收购 物品名 单价 [数量]")

    mode_str, item_name, price_str = params[:3]
    qty_str = params[3] if len(params) > 3 else "1"

    if mode_str not in ("出售","购买", "收购", "求购"):
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

    # 装备交易特殊处理
    is_equipment = EquipmentTradeService.is_equipment_trade(item_cfg.item_id)
    if is_equipment and side == OrderSide.SELL:
        if quantity != 1:
            await list_cmd.finish("⛔ 装备只能单件出售")
        # 装备出售需要选择具体实例，转到装备选择流程
        await _handle_equipment_listing(event, item_cfg, price)
        return

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
            # 检查是否可以挂牌（8小时内购买的商品不能挂牌）
            from ..models.trade_record import TradeRecord
            can_list, error_msg = await TradeRecord.can_list_item(session, player.id, item_cfg.item_id, hours=8)
            if not can_list:
                await list_cmd.finish(error_msg)

            # 非装备物品按原有逻辑处理
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

        # 创建新订单（非装备）
        new_order = MarketOrder(
            player_id=player.id,
            side=side,
            item_id=item_cfg.item_id,
            price=price,
            quantity=quantity,
            is_instance_trade=False
        )
        session.add(new_order)

        await session.flush()  # 获取 new_order.id

        # 自动撮合（规则取决于 auto_match 配置）
        fill_msg = await _try_auto_match(session, new_order, player, same_price_only=not AUTO_MATCH)

        await session.commit()

    result_msg = (
        f"📈 成功挂牌 🆔{new_order.id}┃{mode_str}{item_cfg.name}┃💰{price}┃📦{quantity}"
        + ("\n" + fill_msg if fill_msg else "")
    )
    await list_cmd.finish(message_add_head(result_msg, event))


async def _handle_equipment_listing(event: MessageEvent, item_cfg, price: int):
    """处理装备挂牌选择"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await list_cmd.finish("⛔ 请先创建角色")

        # 获取玩家的装备列表
        equipment_list = await EquipmentTradeService.get_player_equipment_list(
            session, player.id, item_cfg.item_id
        )

        if not equipment_list:
            await list_cmd.finish(f"⛔ 你没有可挂牌的 {item_cfg.name}")

        if len(equipment_list) == 1:
            # 只有一件装备，直接挂牌
            await _create_equipment_order(session, player, equipment_list[0], price, event)
            return

        # 多件装备，保存状态并让玩家选择
        import time
        user_id = event.get_user_id()

        # 只保存装备ID列表和基本信息，避免数据库会话问题
        equipment_ids = [eq.id for eq in equipment_list]
        equipment_summaries = [EquipmentTradeService.generate_equipment_summary(eq) for eq in equipment_list]

        equipment_selection_state[user_id] = {
            "equipment_ids": equipment_ids,
            "equipment_summaries": equipment_summaries,
            "item_id": item_cfg.item_id,
            "item_name": item_cfg.name,
            "price": price,
            "timestamp": time.time()  # 添加时间戳，用于状态过期
        }

        lines = [
            f"📋 选择要挂牌的 {item_cfg.name}：",
            "━━━━━━━━━━━━━"
        ]

        # 使用保存的摘要信息显示装备列表
        for i, (eq_id, summary) in enumerate(zip(equipment_ids, equipment_summaries), 1):
            lines.append(f"{i}. 🆔{eq_id} {summary}")

        lines.extend([
            "",
            "💡 请直接回复序号选择装备（如：1），或回复 取消"
        ])

        await list_cmd.finish(message_add_head("\n".join(lines), event))


async def _create_equipment_order(session, player, equipment: ItemInstance, price: int, event: MessageEvent):
    """创建装备订单"""
    # 冻结装备
    if not await EquipmentTradeService.freeze_equipment(session, equipment):
        await list_cmd.finish("⛔ 该装备无法挂牌（可能已在交易中或已装备）")

    # 生成装备摘要
    summary = EquipmentTradeService.generate_equipment_summary(equipment)

    # 创建装备订单
    new_order = MarketOrder(
        player_id=player.id,
        side=OrderSide.SELL,
        item_id=equipment.item_id,
        price=price,
        quantity=1,
        is_instance_trade=True,
        item_instance_id=equipment.id,
        equipment_summary=summary
    )
    session.add(new_order)

    await session.flush()  # 获取订单ID

    # 自动撮合
    fill_msg = await _try_auto_match(session, new_order, player, same_price_only=not AUTO_MATCH)

    await session.commit()

    result_msg = f"📈 成功挂牌装备 🆔{new_order.id}┃{summary}┃💰{price:,}"
    if fill_msg:
        result_msg += "\n" + fill_msg

    await list_cmd.finish(message_add_head(result_msg, event))

# ---------------- 装备选择消息处理器 ----------------
equipment_selection_handler = on_message(priority=10, block=False)

@equipment_selection_handler.handle()
async def _(event: MessageEvent):
    """处理装备选择的数字回复"""
    # 清理过期状态
    _cleanup_expired_states()

    user_id = event.get_user_id()

    # 检查是否有待处理的装备选择状态
    if user_id not in equipment_selection_state:
        return

    message_text = event.get_message().extract_plain_text().strip()

    # 处理取消操作
    if message_text in ["取消", "cancel", "0"]:
        del equipment_selection_state[user_id]
        await equipment_selection_handler.finish("❌ 已取消装备挂牌")

    # 检查是否为数字
    if not message_text.isdigit():
        return  # 不是数字，不处理

    try:
        index = int(message_text) - 1  # 转换为0基索引
        if index < 0:
            raise ValueError
    except ValueError:
        return  # 无效数字，不处理

    # 获取状态信息
    state = equipment_selection_state[user_id]
    equipment_ids = state["equipment_ids"]
    price = state["price"]

    # 检查序号有效性
    if index >= len(equipment_ids):
        await equipment_selection_handler.finish("⛔ 无效的装备序号，请重新选择")

    # 获取选中装备的ID
    equipment_id = equipment_ids[index]

    # 清除状态
    del equipment_selection_state[user_id]

    async with safe_session() as session:
        player = await session.get(Player, user_id)
        if not player:
            await equipment_selection_handler.finish("⛔ 请先创建角色")

        # 在新会话中重新获取装备对象
        equipment = await session.get(ItemInstance, equipment_id)
        if not equipment or equipment.player_id != user_id:
            await equipment_selection_handler.finish("⛔ 装备不存在或不属于你")

        await _create_equipment_order(session, player, equipment, price, event)


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
            if order.is_equipment_trade:
                # 装备交易：解冻装备
                equipment = await EquipmentTradeService.get_equipment_by_instance_id(
                    session, order.item_instance_id
                )
                if equipment:
                    await EquipmentTradeService.unfreeze_equipment(session, equipment)
            else:
                # 普通物品：退回剩余物品
                try:
                    await ItemInstance.add_item(session, player.id, order.item_id, order.quantity)
                except ValueError as e:
                    await cancel_cmd.finish(f"⛔ 撤牌失败：{e}")
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
            if order.is_equipment_trade:
                # 装备显示格式：🆔001┃💰50,000┃⭐+5阶 [💎2/3] 耐久160/160
                return f"🆔{str(order.id).rjust(3)}┃💰{str(order.price).rjust(8)}┃{order.equipment_summary}"
            else:
                # 普通物品显示格式
                return format_order_line(order.id, order.price, order.quantity, order.player.uid)

        PAGE_SIZE = 10
        def _paginate(lst: list[MarketOrder]):
            total_pages = (len(lst) - 1) // PAGE_SIZE + 1 if lst else 1
            p = max(1, min(page, total_pages))
            start = (p - 1) * PAGE_SIZE
            end = start + PAGE_SIZE
            return lst[start:end], total_pages, p

        sell_page, sell_total, cur_page = _paginate(sells)
        buy_page, _, _ = _paginate(buys)

        lines = [f"📋 {item_cfg.name} 市场牌子 · 第{cur_page}/{sell_total}页"]
        lines.append(heavy_divider(f"{EMOJI_SELL} 出售"))
        if sell_page:
            lines.extend(_fmt(o) for o in sell_page)
        else:
            lines.append("(空)")
        lines.append(heavy_divider(f"{EMOJI_BUY} 求购"))
        if buy_page:
            lines.extend(_fmt(o) for o in buy_page)
        else:
            lines.append("(空)")

        await view_cmd.finish(message_add_head("\n".join(lines), event))

overview_cmd = on_command("交易清单", aliases={"交易市场"}, block=True, priority=5)

@overview_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """交易清单 [页数] - 展示当前所有在售与求购物品总览"""
    page_str = args.extract_plain_text().strip()
    page = 1
    if page_str:
        try:
            page = int(page_str)
            if page < 1:
                raise ValueError
        except ValueError:
            await overview_cmd.finish("⛔ 页数必须为正整数")

    async with safe_session() as session:
        # 聚合在售（SELL）信息：最低价与总数量
        stmt_sell = (
            select(
                MarketOrder.item_id,
                func.sum(MarketOrder.quantity).label("qty"),
                func.min(MarketOrder.price).label("min_price"),
            )
            .where(MarketOrder.side == OrderSide.SELL)
            .group_by(MarketOrder.item_id)
        )
        # 聚合求购（BUY）信息：最高价与总数量
        stmt_buy = (
            select(
                MarketOrder.item_id,
                func.sum(MarketOrder.quantity).label("qty"),
                func.max(MarketOrder.price).label("max_price"),
            )
            .where(MarketOrder.side == OrderSide.BUY)
            .group_by(MarketOrder.item_id)
        )

        sells = (await session.execute(stmt_sell)).all()
        buys = (await session.execute(stmt_buy)).all()

        def _fmt_sell(row):
            item_cfg = config.items_config["by_id"].get(row.item_id)
            if not item_cfg:
                return None
            return f"{EMOJI_SELL} {item_cfg.name} 💰{row.min_price} 📦{row.qty}"

        def _fmt_buy(row):
            item_cfg = config.items_config["by_id"].get(row.item_id)
            if not item_cfg:
                return None
            return f"{EMOJI_BUY} {item_cfg.name} 💰{row.max_price} 📦{row.qty}"

        sell_lines_raw: list[str] = list(filter(None, (_fmt_sell(r) for r in sells)))
        buy_lines_raw: list[str] = list(filter(None, (_fmt_buy(r) for r in buys)))

        PAGE_SIZE = 10

        def _paginate(lst: list[str]):
            total_pages = (len(lst) - 1) // PAGE_SIZE + 1 if lst else 1
            p = max(1, min(page, total_pages))
            start = (p - 1) * PAGE_SIZE
            end = start + PAGE_SIZE
            return lst[start:end], total_pages, p

        sell_page, total_pages_sell, cur_page = _paginate(sell_lines_raw)
        buy_page, total_pages_buy, _ = _paginate(buy_lines_raw)
        total_pages = max(total_pages_sell, total_pages_buy)

        lines: list[str] = [f"📊 市场总览 第{cur_page}/{total_pages}页"]
        lines.append(heavy_divider(f"{EMOJI_SELL} 在售"))
        if sell_page:
            lines.extend(sell_page)
        else:
            lines.append("(空)")
        lines.append(heavy_divider(f"{EMOJI_BUY} 收购"))
        if buy_page:
            lines.extend(buy_page)
        else:
            lines.append("(空)")
        lines.append("⬇️ 【查牌 <物品名> [页数]】 查看物品买卖行情")
        await overview_cmd.finish(message_add_head("\n".join(lines), event))

# ---------------- 指令：我的挂牌 ----------------
my_orders_cmd = on_command("我的挂牌", aliases={"查看我的挂牌", "我的牌子"}, block=True, priority=5)

@my_orders_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """我的挂牌 [页数] - 查看玩家自己的所有挂牌订单"""
    page_str = args.extract_plain_text().strip()
    page = 1
    if page_str:
        try:
            page = int(page_str)
            if page < 1:
                raise ValueError
        except ValueError:
            await my_orders_cmd.finish("⛔ 页数必须为正整数")

    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await my_orders_cmd.finish("⛔ 请先创建角色")

        # 查询玩家的所有挂牌订单
        stmt = select(MarketOrder).where(
            MarketOrder.player_id == player.id
        ).order_by(desc(MarketOrder.created_at))

        orders = (await session.execute(stmt)).scalars().all()

        if not orders:
            await my_orders_cmd.finish(message_add_head("📋 你还没有挂牌任何物品", event))

        PAGE_SIZE = 8
        total_pages = (len(orders) - 1) // PAGE_SIZE + 1 if orders else 1
        page = max(1, min(page, total_pages))
        start = (page - 1) * PAGE_SIZE
        end = start + PAGE_SIZE
        page_orders = orders[start:end]

        lines = [f"📋 我的挂牌 · 第{page}/{total_pages}页 ({len(orders)}个)"]
        lines.append(heavy_divider("📤 出售订单"))

        sell_orders = [o for o in page_orders if o.side == OrderSide.SELL]
        if sell_orders:
            for order in sell_orders:
                item_cfg = config.items_config["by_id"].get(order.item_id)
                if item_cfg:
                    lines.append(f"🆔{str(order.id).rjust(3)}┃{item_cfg.name}┃💰{order.price}┃📦{order.quantity}")
        else:
            lines.append("(空)")

        lines.append(heavy_divider("📥 求购订单"))

        buy_orders = [o for o in page_orders if o.side == OrderSide.BUY]
        if buy_orders:
            for order in buy_orders:
                item_cfg = config.items_config["by_id"].get(order.item_id)
                if item_cfg:
                    lines.append(f"🆔{str(order.id).rjust(3)}┃{item_cfg.name}┃💰{order.price}┃📦{order.quantity}")
        else:
            lines.append("(空)")

        lines.append("⬇️ 【撤牌 <牌子ID>】 撤回指定牌子")
        await my_orders_cmd.finish(message_add_head("\n".join(lines), event))

# ---------------- 指令：查看税率 ----------------
tax_info_cmd = on_command("税率", aliases={"交易税率", "查看税率"}, block=True, priority=5)

@tax_info_cmd.handle()
async def _(event: MessageEvent):
    """查看当前的阶梯交易税率"""
    lines = [
        "💰 交易税率表",
        heavy_divider("阶梯税率"),
        "💚 5,000金币以下：免税 (0%)",
        "💛 5,001-20,000金币：5%",
        "🧡 20,001-50,000金币：10%",
        "❤️ 50,001-100,000金币：15%",
        "💜 100,001金币以上：20%",
        "",
        "📝 说明：税收从卖家收入中扣除",
        "⚠️ 高价交易将产生大量税收损失"
    ]
    await tax_info_cmd.finish(message_add_head("\n".join(lines), event))


# ---------------- 指令：装备估价 ----------------
equipment_appraise_cmd = on_command("估价", aliases={"装备估价"}, block=True, priority=5)

@equipment_appraise_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """估价 装备ID"""
    arg = args.extract_plain_text().strip()
    if not arg.isdigit():
        await equipment_appraise_cmd.finish("⛔ 格式：估价 装备ID")

    equipment_id = int(arg)

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await equipment_appraise_cmd.finish("⛔ 请先创建角色")

        # 获取装备
        equipment = await session.get(ItemInstance, equipment_id)
        if not equipment or equipment.player_id != player.id or not equipment.is_equipment:
            await equipment_appraise_cmd.finish("⛔ 无效装备ID或非本人所有")

        # 计算估价
        min_price, max_price = EquipmentTradeService.calculate_equipment_value_range(equipment)
        summary = EquipmentTradeService.generate_equipment_summary(equipment)

        # 获取市场参考价格
        stmt = select(MarketOrder).where(
            and_(
                MarketOrder.item_id == equipment.item_id,
                MarketOrder.side == OrderSide.SELL,
                MarketOrder.is_instance_trade == True
            )
        ).order_by(MarketOrder.price.asc()).limit(5)

        market_orders = (await session.execute(stmt)).scalars().all()

        lines = [
            f"💰 装备估价报告",
            f"━━━━━━━━━━━━━",
            f"🎯 装备：{summary}",
            f"🆔 ID：{equipment.id}",
            "",
            f"📊 估价分析：",
            f"• 基础价值：{equipment.config.price:,} 金币",
        ]

        if equipment.upgrade_level > 0:
            upgrade_bonus = (equipment.get_upgrade_bonus_multiplier() - 1) * 100
            lines.append(f"• 升阶加成：+{upgrade_bonus:.0f}% ({equipment.upgrade_level}阶)")

        if equipment.used_gem_slots > 0:
            gem_value = 0
            for gem_item_id in equipment.gem_slots_data.values():
                gem_config = config.items_config["by_id"].get(gem_item_id)
                if gem_config:
                    gem_value += gem_config.price
            lines.append(f"• 宝石价值：{gem_value:,} 金币")

        durability_ratio = equipment.durability / equipment.config.durability if equipment.config.durability > 0 else 1.0
        if durability_ratio < 1.0:
            lines.append(f"• 耐久影响：{durability_ratio:.1%}")

        lines.extend([
            "",
            f"💎 建议售价：{min_price:,} - {max_price:,} 金币",
            ""
        ])

        if market_orders:
            lines.append("📈 市场参考：")
            for order in market_orders:
                lines.append(f"• {order.equipment_summary} - {order.price:,} 金币")
        else:
            lines.append("📈 市场参考：暂无同类装备在售")

        await equipment_appraise_cmd.finish(message_add_head("\n".join(lines), event))

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

        # 处理物品转移
        if new_order.side == OrderSide.SELL and new_order.is_equipment_trade:
            # 卖方是装备，转移装备实例
            equipment = await EquipmentTradeService.get_equipment_by_instance_id(
                session, new_order.item_instance_id
            )
            if not equipment or not await EquipmentTradeService.transfer_equipment(session, equipment, buyer.id):
                break  # 装备转移失败，停止撮合
        elif opp.side == OrderSide.SELL and opp.is_equipment_trade:
            # 对手方是装备，转移装备实例
            equipment = await EquipmentTradeService.get_equipment_by_instance_id(
                session, opp.item_instance_id
            )
            if not equipment or not await EquipmentTradeService.transfer_equipment(session, equipment, buyer.id):
                break  # 装备转移失败，停止撮合
        else:
            # 普通物品交易，检查背包空间
            try:
                await ItemInstance.add_item(session, buyer.id, item_cfg.item_id, trade_qty)
            except ValueError:
                # 买家背包空间不足，停止撮合
                break

        # 计算交易金额和阶梯税收
        trade_amount = trade_price * trade_qty
        tax = calculate_transaction_tax(trade_amount)

        # 金币给卖家（扣除税收）
        seller.gold += trade_amount - tax

        # 更新对手单
        opp.quantity -= trade_qty
        if opp.quantity == 0:
            await session.delete(opp)

        remaining -= trade_qty
        if new_order.side == OrderSide.BUY:
            total_spent += trade_price * trade_qty

        # 生成交易消息（包含税收信息）
        trade_msg = f"✅ 成交 📦{trade_qty} @{trade_price}💰"
        if tax > 0:
            trade_msg += f"（税收：{tax}💰）"
        trade_lines.append(trade_msg)

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