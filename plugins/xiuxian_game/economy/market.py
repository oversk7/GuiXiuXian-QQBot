from nonebot import on_command, on_message
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.rule import to_me
from sqlalchemy import select, func, asc, desc, and_
from sqlalchemy.orm import selectinload
from ..models.db import safe_session
from ..models.market_order import MarketOrder, OrderSide
from ..models.trade_record import TradeRecord, TradeType
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..config import config
from ..utils import message_add_head
from ..utils_markdown import cmd, build_markdown
from .equipment_trade_service import EquipmentTradeService
from ..item.equipment_commands import find_equipment_by_input
from ..platform_utils import get_unified_player

from datetime import date, datetime, timedelta

# 导入新版DI架构EquipmentTradeService
from .equipment_trade_service_new import EquipmentTradeService as EquipmentTradeServiceNew
from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.repositories.market_order_repository import MarketOrderRepository

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
    计算分段累进交易税率（仅对超出部分征税，消除断崖效应）
    ≤5,000: 免税 (0%)
    5,001-20,000: 超出部分 5%
    20,001-50,000: 超出部分 10%
    50,001-100,000: 超出部分 15%
    >100,000: 超出部分 20%

    示例：交易额 25,000 → 0 + 15000*5% + 5000*10% = 1,250（而非旧版 25000*10%=2,500）
    """
    if amount <= 5000:
        return 0

    tax = 0
    brackets = [
        (5000, 20000, 0.05),      # 5,001-20,000: 5%
        (20000, 50000, 0.10),     # 20,001-50,000: 10%
        (50000, 100000, 0.15),    # 50,001-100,000: 15%
        (100000, float('inf'), 0.20),  # >100,000: 20%
    ]

    remaining = amount - 5000  # 5,000以下免税

    for lower, upper, rate in brackets:
        if remaining <= 0:
            break
        bracket_size = upper - lower
        taxable = min(remaining, bracket_size)
        tax += int(taxable * rate)
        remaining -= taxable

    return tax

# ====== 商店基础倍率（抗通胀） ======
SHOP_BASE_MULT = 3  # 系统商店/黑市/礼物商店的固定基础倍率


async def get_shop_adjusted_price(session, base_price: int) -> int:
    """计算商店调整后价格：基础价 × 固定倍率 × 财富指数。
    用于系统商店、黑市、礼物商店等所有金币定价的NPC商店。"""
    scale = await _get_wealth_scale(session)
    return max(1, int(base_price * SHOP_BASE_MULT * scale))

# ====== 价格基础与底价吸附（调低整体物价与门槛） ======
PRICE_FLOOR_ALPHA = 0.6   # 参考价折扣系数（底价≈参考价*alpha 与 经济基础价 取最大）
MIN_UNIT_PRICE = 10       # 系统绝对最小单价下限（如需进一步降低门槛可改为 5）
PRICE_CAP_MULT = 8        # 建议价倍数上限，防止恶意拉高挂牌价格

# 成交价采样窗口及阈值（用于底价估计，详见 _compute_item_floor_price）
TRADE_REF_LOOKBACK_DAYS = 7       # 最近 N 天的成交价作为参考样本
TRADE_REF_MIN_SAMPLES = 5         # 至少需要的成交样本数，低于该值将回退到挂牌价/经济基础价

# 全局经济倍率（更温和的倍率，避免底价被放大过头）
ECONOMY_MULT_BY_TYPE = {
    "MATERIAL": 0.7,
    "GOODS": 0.9,
    "CONSUMABLE": 1.2,
    "GEM": 2.0,
    "EQUIPMENT": 4.0,
    "FISH": 0.9,
}
ECONOMY_MULT_BY_RARITY = {
    "white": 1.0,
    "green": 1.05,
    "blue": 1.10,
    "purple": 1.20,
    "orange": 1.30,
}

# ====== 财富指数联动（自动经济倍率） ======
WEALTH_TOP_N = 100
WEALTH_BASELINE = 5_000_000_000  # 50亿作为基线（提高基线以降低放大效果）
WEALTH_GAMMA = 0.3               # 更平缓的增长（降低高端玩家对全服物价的拉动）
WEALTH_SMIN = 1.0                # 不低于1，避免低谷期进一步打压物价
WEALTH_SMAX = 3.0                # 限制上限，避免土豪时代通胀
WEALTH_EMA_ALPHA = 0.15          # 降低敏感度，收敛更平滑

_wealth_cache_day: int | None = None
_wealth_prev_scale: float = 1.0

async def _get_wealth_scale(session) -> float:
    """按TopN玩家金币中位数计算当日财富指数S，并进行EMA平滑与上下限夹持。"""
    global _wealth_cache_day, _wealth_prev_scale
    today_ord = date.today().toordinal()
    if _wealth_cache_day == today_ord and _wealth_prev_scale:
        return _wealth_prev_scale

    stmt = select(Player.gold).order_by(desc(Player.gold)).limit(WEALTH_TOP_N)
    rows = (await session.execute(stmt)).all()
    vals = [int(v) for (v,) in rows if v is not None]
    if not vals:
        _wealth_cache_day = today_ord
        _wealth_prev_scale = 1.0
        return 1.0

    vals.sort()
    n = len(vals)
    if n % 2 == 1:
        median_v = vals[n // 2]
    else:
        median_v = (vals[n // 2 - 1] + vals[n // 2]) / 2

    ratio = max(median_v, 1) / WEALTH_BASELINE
    raw = pow(ratio, WEALTH_GAMMA)
    raw = max(WEALTH_SMIN, min(raw, WEALTH_SMAX))

    scale = WEALTH_EMA_ALPHA * raw + (1.0 - WEALTH_EMA_ALPHA) * (_wealth_prev_scale or 1.0)
    _wealth_prev_scale = scale
    _wealth_cache_day = today_ord
    return scale

EQUIPMENT_FLOOR_MULT = 6.0   # 降低装备底价放大，缓解高价壁垒

async def _compute_item_floor_price(session, item_cfg) -> int:
    """计算普通物品的底价：综合物品基础价(含经济倍率)与近期市场参考价。
    参考价使用最近若干卖单价格的截尾均值，剔除过低异常值。
    """
    base = int(getattr(item_cfg, "price", 0) or 0)
    base = max(base, MIN_UNIT_PRICE)

    # 按类别/稀有度放大基础价（动态经济时代调整）
    type_val = getattr(item_cfg.type, "value", str(item_cfg.type))
    rarity = getattr(item_cfg, "rarity", None) or "white"
    t_mult = ECONOMY_MULT_BY_TYPE.get(str(type_val), 1.0)
    r_mult = ECONOMY_MULT_BY_RARITY.get(str(rarity), ECONOMY_MULT_BY_RARITY["white"])
    scale = await _get_wealth_scale(session)
    econ_base = int(base * t_mult * r_mult * scale)

    lookback_since = datetime.now() - timedelta(days=TRADE_REF_LOOKBACK_DAYS)
    trade_stmt = (
        select(TradeRecord.unit_price)
        .where(
            TradeRecord.item_id == item_cfg.item_id,
            TradeRecord.trade_type == TradeType.SELL,
            TradeRecord.trade_time >= lookback_since,
        )
        .order_by(desc(TradeRecord.trade_time))
        .limit(200)
    )
    trade_prices = [int(p) for (p,) in (await session.execute(trade_stmt)).all()]

    # 剔除过低异常值（小于基础价的60%或小于最小单价）
    lo_cut = max(int(base * 0.6), MIN_UNIT_PRICE)
    trade_prices = [p for p in trade_prices if p >= lo_cut]

    ref_floor = 0
    if len(trade_prices) >= TRADE_REF_MIN_SAMPLES:
        trade_prices.sort()
        n = len(trade_prices)
        trim = max(1, n // 10) if n >= 10 else 0
        core = trade_prices[trim:n - trim] if trim and n - trim > trim else trade_prices
        ref = sum(core) / len(core)
        ref_floor = int(ref * PRICE_FLOOR_ALPHA)
    else:
        # 回退：若成交样本不足，混合最近的挂牌价，避免底价回落为 0
        order_stmt = (
            select(MarketOrder.price)
            .where(
                MarketOrder.item_id == item_cfg.item_id,
                MarketOrder.side == OrderSide.SELL,
                MarketOrder.is_instance_trade == False,
            )
            .order_by(desc(MarketOrder.created_at))
            .limit(20)
        )
        order_prices = [int(p) for (p,) in (await session.execute(order_stmt)).all()]
        order_prices = [p for p in order_prices if p >= lo_cut]
        combined = trade_prices + order_prices
        if combined:
            combined.sort()
            n = len(combined)
            trim = max(1, n // 10) if n >= 10 else 0
            core = combined[trim:n - trim] if trim and n - trim > trim else combined
            ref = sum(core) / len(core)
            ref_floor = int(ref * PRICE_FLOOR_ALPHA)

    floor_price = max(econ_base, ref_floor, MIN_UNIT_PRICE)
    return floor_price

async def _compute_equipment_floor_price(session, equipment) -> int:
    """计算装备实例底价：使用装备估价下界，并按财富指数放大。"""
    min_price, _ = EquipmentTradeService.calculate_equipment_value_range(equipment)
    scale = await _get_wealth_scale(session)
    return max(int(min_price * EQUIPMENT_FLOOR_MULT * scale), MIN_UNIT_PRICE)


async def _get_market_reference(session, item_cfg) -> str | None:
    """查询近7日市场参考数据，返回格式化的信息行。无数据时返回 None。"""
    is_equipment = EquipmentTradeService.is_equipment_trade(item_cfg.item_id)
    lookback_since = datetime.now() - timedelta(days=TRADE_REF_LOOKBACK_DAYS)

    # 查询近7日成交记录（跑商系统的交易数据）
    trade_stmt = (
        select(
            func.count().label("cnt"),
            func.avg(TradeRecord.unit_price).label("avg_price"),
        )
        .where(
            TradeRecord.item_id == item_cfg.item_id,
            TradeRecord.trade_time >= lookback_since,
        )
    )
    row = (await session.execute(trade_stmt)).one()
    trade_count = int(row.cnt or 0)
    avg_price = int(row.avg_price) if row.avg_price else None

    parts: list[str] = []

    # 底价（仅非装备物品展示，装备因实例而异）
    if not is_equipment:
        floor_price = await _compute_item_floor_price(session, item_cfg)
        parts.append(f"底价:{floor_price:,}💰")

    # 近7日均价和成交量
    if avg_price is not None and trade_count > 0:
        parts.append(f"7日均价:{avg_price:,}💰({trade_count}笔)")
    else:
        parts.append("7日无成交记录")

    if not parts:
        return None
    return "📊 " + " ┃ ".join(parts)


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
        await list_cmd.finish(
            f"⛔ 单价不能低于10，数量必须为正整数，且挂牌价格需在建议底价的 {PRICE_CAP_MULT} 倍以内"
        )

    # 物品模板
    item_cfg = config.items_config["by_name"].get(item_name)
    if not item_cfg:
        await list_cmd.finish(f"⛔ 不存在物品：{item_name}")

    # VIP定制装备禁止交易
    VIP_EQUIPMENT_IDS = {"vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi", "heaven_retreat_star_blade", "vip_gui_yu", "vip_chrono_watch", "vip_longying_flash", "vip_ghost_dice", "vip_shoes_longren"}
    if item_cfg.item_id in VIP_EQUIPMENT_IDS:
        await list_cmd.finish("⛔ VIP定制装备为专属装备，不可交易")

    # 装备交易特殊处理
    is_equipment = EquipmentTradeService.is_equipment_trade(item_cfg.item_id)
    if is_equipment and side == OrderSide.SELL:
        if quantity != 1:
            await list_cmd.finish("⛔ 装备只能单件出售")
        # 装备出售需要选择具体实例，转到装备选择流程
        await _handle_equipment_listing(event, item_cfg, price)
        return

    async with safe_session() as session:
        player: Player | None = await get_unified_player(session, event)
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

        # 底价吸附与价格上限（普通物品）
        snap_hint = ""
        cap_hint = ""
        if not is_equipment:
            floor_price = await _compute_item_floor_price(session, item_cfg)
            price_cap = max(int(floor_price * PRICE_CAP_MULT), floor_price)
            if price > price_cap:
                await list_cmd.finish(
                    message_add_head(
                        (
                            f"⛔ {item_cfg.name} 的挂牌价格不得超过建议底价 {floor_price}💰 的 {PRICE_CAP_MULT} 倍\n"
                            f"💡 该物品当前上限为 {price_cap}💰，请调整价格后再试"
                        ),
                        event,
                    )
                )
            if side == OrderSide.SELL and price < floor_price:
                price = floor_price
                snap_hint = f"（已自动吸附到底价{floor_price}💰）"
            cap_hint = f"💡 建议底价{floor_price}💰，挂牌上限{price_cap}💰（{PRICE_CAP_MULT}倍）"

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

    lines = [
        f"# 📈 成功挂牌",
        f"***",
        f"🆔 **{new_order.id}** | {mode_str} {cmd(item_cfg.name, '查牌 ' + item_cfg.name)} | 💰 **{price}** | 📦 **{quantity}**",
    ]
    if snap_hint:
        lines.append(snap_hint)
    if cap_hint:
        lines.append(cap_hint)
    if fill_msg:
        lines.append(fill_msg)
    lines.append("***")
    lines.append(f"{cmd('我的挂牌')} | {cmd('撤牌 ' + str(new_order.id), '撤牌 ' + str(new_order.id))} | {cmd('查牌 ' + item_cfg.name, '查牌 ' + item_cfg.name)}")
    await list_cmd.finish(build_markdown("\n".join(lines)))


async def _handle_equipment_listing(event: MessageEvent, item_cfg, price: int):
    """处理装备挂牌选择"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await list_cmd.finish("⛔ 请先创建角色")

        # 获取玩家的装备列表
        item_repo = ItemRepository(session)
        market_order_repo = MarketOrderRepository(session)
        service = EquipmentTradeServiceNew(item_repo, market_order_repo)
        equipment_list = await service.get_player_equipment_list(player.id, item_cfg.item_id)

        if not equipment_list:
            await list_cmd.finish(f"⛔ 你没有可挂牌的 {item_cfg.name}")

        if len(equipment_list) == 1:
            # 只有一件装备，直接挂牌
            await _create_equipment_order(session, player, equipment_list[0], price, event)
            return

        # 多件装备，保存状态并让玩家选择
        import time

        # 只保存装备ID列表和基本信息，避免数据库会话问题
        equipment_ids = [eq.id for eq in equipment_list]
        equipment_summaries = [EquipmentTradeService.generate_equipment_summary(eq) for eq in equipment_list]

        equipment_selection_state[player.id] = {
            "equipment_ids": equipment_ids,
            "equipment_summaries": equipment_summaries,
            "item_id": item_cfg.item_id,
            "item_name": item_cfg.name,
            "price": price,
            "timestamp": time.time()  # 添加时间戳，用于状态过期
        }

        lines = [
            f"# 📋 选择要挂牌的 {item_cfg.name}",
            "***",
            f"💡 挂牌价格需在建议底价的 **{PRICE_CAP_MULT}** 倍以内"
        ]

        # 使用保存的摘要信息显示装备列表
        for i, (eq_id, summary) in enumerate(zip(equipment_ids, equipment_summaries), 1):
            lines.append(f"{i}. 🆔**{eq_id}** {summary}")

        lines.extend([
            "",
            "💡 请直接回复序号选择装备（如：1），或回复 取消"
        ])

        await list_cmd.finish(build_markdown("\n".join(lines)))


async def _create_equipment_order(session, player, equipment: ItemInstance, price: int, event: MessageEvent):
    """创建装备订单"""
    # 冻结装备
    item_repo = ItemRepository(session)
    market_order_repo = MarketOrderRepository(session)
    service = EquipmentTradeServiceNew(item_repo, market_order_repo)
    if not await service.freeze_equipment(equipment):
        await list_cmd.finish("⛔ 该装备无法挂牌（可能已在交易中或已装备）")

    # 生成装备摘要
    summary = EquipmentTradeService.generate_equipment_summary(equipment)

    # 底价吸附（装备）
    snap_hint = ""
    floor_price = await _compute_equipment_floor_price(session, equipment)
    price_cap = max(int(floor_price * PRICE_CAP_MULT), floor_price)
    if price > price_cap:
        await list_cmd.finish(
            message_add_head(
                (
                    f"⛔ 装备挂牌价格不得超过建议底价 {floor_price}💰 的 {PRICE_CAP_MULT} 倍\n"
                    f"💡 该装备当前上限为 {price_cap}💰，请调整价格后再试"
                ),
                event,
            )
        )
    if price < floor_price:
        price = floor_price
        snap_hint = f"（已自动吸附到底价{floor_price}💰）"

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

    lines = [
        f"# 📈 成功挂牌装备",
        "***",
        f"🆔 **{new_order.id}** | {summary} | 💰 **{price:,}**",
    ]
    if snap_hint:
        lines.append(snap_hint)
    if fill_msg:
        lines.append(fill_msg)
    lines.append("***")
    lines.append(f"{cmd('我的挂牌')} | {cmd('撤牌 ' + str(new_order.id), '撤牌 ' + str(new_order.id))}")
    await list_cmd.finish(build_markdown("\n".join(lines)))

# ---------------- 装备选择消息处理器 ----------------
equipment_selection_handler = on_message(priority=10, block=False)

@equipment_selection_handler.handle()
async def _(event: MessageEvent):
    """处理装备选择的数字回复"""
    # 清理过期状态
    _cleanup_expired_states()

    # 使用跨平台工具获取玩家ID
    player_id = None
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            return
        player_id = player.id

        # 检查是否有待处理的装备选择状态
        if player_id not in equipment_selection_state:
            return

    message_text = event.get_message().extract_plain_text().strip()

    # 处理取消操作
    if message_text in ["取消", "cancel", "0"]:
        del equipment_selection_state[player_id]
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
    state = equipment_selection_state[player_id]
    equipment_ids = state["equipment_ids"]
    price = state["price"]

    # 检查序号有效性
    if index >= len(equipment_ids):
        await equipment_selection_handler.finish("⛔ 无效的装备序号，请重新选择")

    # 获取选中装备的ID
    equipment_id = equipment_ids[index]

    # 清除状态
    del equipment_selection_state[player_id]

    async with safe_session() as session:
        player = await session.get(Player, player_id)
        if not player:
            await equipment_selection_handler.finish("⛔ 请先创建角色")

        # 在新会话中重新获取装备对象
        equipment = await session.get(ItemInstance, equipment_id)
        if not equipment or equipment.player_id != player_id:
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
        # 使用跨平台工具获取玩家数据
        player = await get_unified_player(session, event)
        if not player:
            await cancel_cmd.finish("⛔ 请先创建角色")

        order: MarketOrder | None = await session.get(MarketOrder, oid)
        if not order or order.player_id != player.id:
            await cancel_cmd.finish("⛔ 无效牌子")

        if order.side == OrderSide.SELL:
            if order.is_equipment_trade:
                # 装备交易：解冻装备
                item_repo = ItemRepository(session)
                market_order_repo = MarketOrderRepository(session)
                service = EquipmentTradeServiceNew(item_repo, market_order_repo)

                equipment = await service.get_equipment_by_instance_id(order.item_instance_id)
                if equipment:
                    await service.unfreeze_equipment(equipment)
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

    content = (
        f"🗑️ 已撤回牌子 #**{oid}**\n"
        f"***\n"
        f"{cmd('我的挂牌')} | {cmd('交易清单')}"
    )
    await cancel_cmd.finish(build_markdown(content))

# ---------------- 指令：查牌主（查看订单归属） ----------------
order_owner_cmd = on_command("挂牌详情", aliases={"查牌主", "牌主", "牌子详情"}, block=True, priority=5)

@order_owner_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    oid_str = args.extract_plain_text().strip()
    if not oid_str.isdigit():
        await order_owner_cmd.finish("⛔ 格式：挂牌详情 订单ID")
    oid = int(oid_str)

    async with safe_session() as session:
        stmt = select(MarketOrder).options(selectinload(MarketOrder.player)).where(
            MarketOrder.id == oid
        )
        order: MarketOrder | None = (await session.execute(stmt)).scalar_one_or_none()
        if not order:
            await order_owner_cmd.finish("⛔ 未找到该订单，可能已撤牌或成交")

        item_cfg = config.items_config["by_id"].get(order.item_id)
        item_name = item_cfg.get_display_name() if item_cfg else order.item_id
        side_text = "📤 出售" if order.side == OrderSide.SELL else "📥 求购"
        player_name = order.player.nickname if order.player else "未知"
        player_uid = order.player.uid if order.player else "?"

        lines = [
            f"# 📋 订单 #{order.id} 详情",
            "***",
            f"{side_text} {cmd(item_name, '查牌 ' + item_name)}",
            f"💰 单价: **{order.price:,}**",
        ]

        if order.is_equipment_trade and order.item_instance_id:
            # 装备交易：实时读取装备实例展示完整详情
            equip = await session.get(ItemInstance, order.item_instance_id)
            if equip and equip.is_equipment:
                tpl = equip.config
                rarity_map = {
                    "white": "白色", "green": "绿色", "blue": "蓝色",
                    "purple": "紫色", "orange": "橙色", "red": "红色"
                }
                rarity_name = rarity_map.get(tpl.rarity, tpl.rarity)

                lines.append(f"🎨 品质：{tpl.get_rarity_display()}{rarity_name}")
                lines.append(f"⭐ 升阶：+{equip.upgrade_level}阶")
                lines.append(f"🛠️ 耐久：{equip.durability}/{tpl.durability}")
                lines.append("")

                # 基础属性
                upgrade_multiplier = equip.get_upgrade_bonus_multiplier()
                if tpl.attr_bonus or tpl.attr_ratio:
                    lines.append("📈 基础属性：")
                    attr_name_map = {
                        "attack": "攻击力", "defense": "防御力", "agility": "敏捷",
                        "luck": "运气", "hp": "生命值", "mp": "理智值",
                        "max_hp": "最大生命值", "max_mp": "最大理智值"
                    }
                    if tpl.attr_bonus:
                        for k, v in tpl.attr_bonus.items():
                            current_value = int(v * upgrade_multiplier)
                            lines.append(f"  • {attr_name_map.get(k, k)}+{current_value}")
                    if tpl.attr_ratio:
                        for k, r in tpl.attr_ratio.items():
                            current_ratio = float(r) * upgrade_multiplier * 100
                            lines.append(f"  • {attr_name_map.get(k, k)}+{current_ratio:.1f}%")
                    lines.append("")

                # 词缀详情
                from ..item.affix_service import get_affixes_from_equipment, format_affixes_display
                affixes = get_affixes_from_equipment(equip.extra_attrs)
                if affixes:
                    lines.append("🔮 词缀：")
                    lines.extend(format_affixes_display(affixes))
                    lines.append("")

                # 宝石/铭文镶嵌详情
                if equip.available_gem_slots > 0:
                    lines.append("💎 镶嵌孔位：")
                    lines.append(f"  • 孔位：{equip.used_gem_slots}/{equip.available_gem_slots}")
                    if equip.used_gem_slots > 0:
                        from ..item.gem_socket_service_new import GemSocketService
                        from ..item.inscription_service import get_inscription_display
                        gem_info = GemSocketService.get_equipment_gem_info(equip)
                        for slot_info in gem_info:
                            if not slot_info["is_empty"]:
                                slot_num = slot_info["slot_number"]
                                if slot_info.get("is_inscription"):
                                    display = get_inscription_display(slot_info["inscription_data"])
                                    lines.append(f"  • 孔位{slot_num}：📜 {display}")
                                else:
                                    gem_name = slot_info["gem_name"]
                                    gem_type = slot_info["gem_type"]
                                    lines.append(f"  • 孔位{slot_num}：{gem_type} - {gem_name}")
                    lines.append("")

                # 特殊效果
                if hasattr(tpl, 'special_effects') and tpl.special_effects:
                    lines.append("✨ 特殊效果：")
                    VIP_EQUIPMENT_IDS = {"vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi", "heaven_retreat_star_blade", "vip_gui_yu", "vip_chrono_watch", "vip_longying_flash", "vip_ghost_dice", "vip_shoes_longren"}
                    is_vip = equip.item_id in VIP_EQUIPMENT_IDS
                    unlocked_count = equip.upgrade_level // 2

                    for idx, effect in enumerate(tpl.special_effects, start=1):
                        desc = effect.get('description', '')
                        if not desc:
                            continue
                        if is_vip or idx <= unlocked_count:
                            lines.append(f"  ✅ [{idx}] {desc}")
                        else:
                            lines.append(f"  🔒 [{idx}] {desc} (需+{idx * 2}阶)")
                    lines.append("")
            else:
                # 装备实例不存在，回退到摘要
                lines.append(f"⭐ {order.equipment_summary}")
        else:
            lines.append(f"📦 数量: {order.quantity}")

        lines.append(f"👤 挂牌人: {player_name} (UID: {player_uid})")
        lines.append(f"🕐 挂牌时间: {order.created_at.strftime('%Y-%m-%d %H:%M')}")
        lines.append("***")
        lines.append(f"{cmd('查牌 ' + item_name, '查牌 ' + item_name)} | {cmd('交易清单')}")

        await order_owner_cmd.finish(build_markdown("\n".join(lines)))

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

        # ---- 查询近7日市场参考数据 ----
        ref_info = await _get_market_reference(session, item_cfg)

        def _fmt(order: MarketOrder):
            oid_cmd = cmd(f"#{order.id}", f"挂牌详情 {order.id}")
            if order.is_equipment_trade:
                return f"{oid_cmd} 💰**{order.price:,}** | {order.equipment_summary}"
            else:
                return f"{oid_cmd} 💰**{order.price:,}** 📦**{order.quantity}**"

        PAGE_SIZE = 10
        def _paginate(lst: list[MarketOrder]):
            total_pages = (len(lst) - 1) // PAGE_SIZE + 1 if lst else 1
            p = max(1, min(page, total_pages))
            start = (p - 1) * PAGE_SIZE
            end = start + PAGE_SIZE
            return lst[start:end], total_pages, p

        sell_page, sell_total, cur_page = _paginate(sells)
        buy_page, _, _ = _paginate(buys)

        lines = [f"# 📋 {cmd(item_cfg.name, '查牌 ' + item_cfg.name)} 市场牌子 第{cur_page}/{sell_total}页"]
        # 插入市场参考信息行
        if ref_info:
            lines.append(ref_info)
        lines.append(f"***")
        lines.append(f"{EMOJI_SELL} **出售**")
        if sell_page:
            lines.extend(_fmt(o) for o in sell_page)
        else:
            lines.append("(空)")
        lines.append(f"***")
        lines.append(f"{EMOJI_BUY} **求购**")
        if buy_page:
            lines.extend(_fmt(o) for o in buy_page)
        else:
            lines.append("(空)")
        lines.append("***")
        if sell_total > 1:
            nav = []
            if cur_page > 1:
                nav.append(cmd(f'上一页', f'查牌 {item_cfg.name} {cur_page - 1}'))
            if cur_page < sell_total:
                nav.append(cmd(f'下一页', f'查牌 {item_cfg.name} {cur_page + 1}'))
            lines.append(" | ".join(nav))
        lines.append(f"{cmd('挂牌 出售 ' + item_cfg.name, '挂牌 出售 ' + item_cfg.name + ' ')} | {cmd('挂牌 收购 ' + item_cfg.name, '挂牌 收购 ' + item_cfg.name + ' ')} | {cmd('交易清单')}")

        await view_cmd.finish(build_markdown("\n".join(lines)))

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
            return f"{EMOJI_SELL} {cmd(item_cfg.name, '查牌 ' + item_cfg.name)} 💰**{row.min_price}** 📦**{row.qty}**"

        def _fmt_buy(row):
            item_cfg = config.items_config["by_id"].get(row.item_id)
            if not item_cfg:
                return None
            return f"{EMOJI_BUY} {cmd(item_cfg.name, '查牌 ' + item_cfg.name)} 💰**{row.max_price}** 📦**{row.qty}**"

        sell_lines_raw: list[str] = list(filter(None, (_fmt_sell(r) for r in sells)))
        buy_lines_raw: list[str] = list(filter(None, (_fmt_buy(r) for r in buys)))

        PAGE_SIZE = 10

        total_pages_sell = (len(sell_lines_raw) - 1) // PAGE_SIZE + 1 if sell_lines_raw else 1
        total_pages_buy = (len(buy_lines_raw) - 1) // PAGE_SIZE + 1 if buy_lines_raw else 1
        total_pages = max(total_pages_sell, total_pages_buy)
        cur_page = max(1, min(page, total_pages))

        start = (cur_page - 1) * PAGE_SIZE
        end = start + PAGE_SIZE
        sell_page = sell_lines_raw[start:end]
        buy_page = buy_lines_raw[start:end]

        lines: list[str] = [f"# 📊 市场总览 第{cur_page}/{total_pages}页"]
        lines.append("***")
        lines.append(f"{EMOJI_SELL} **在售**")
        if sell_page:
            lines.extend(sell_page)
        else:
            lines.append("(空)")
        lines.append("***")
        lines.append(f"{EMOJI_BUY} **收购**")
        if buy_page:
            lines.extend(buy_page)
        else:
            lines.append("(空)")
        lines.append("***")
        if total_pages > 1:
            nav = []
            if cur_page > 1:
                nav.append(cmd(f'上一页', f'交易清单 {cur_page - 1}'))
            if cur_page < total_pages:
                nav.append(cmd(f'下一页', f'交易清单 {cur_page + 1}'))
            lines.append(" | ".join(nav))
        lines.append(f"{cmd('我的挂牌')} | {cmd('税率')} | {cmd('估价', '估价 ')}")
        await overview_cmd.finish(build_markdown("\n".join(lines)))

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
        player: Player | None = await get_unified_player(session, event)
        if not player:
            await my_orders_cmd.finish("⛔ 请先创建角色")

        # 查询玩家的所有挂牌订单
        stmt = select(MarketOrder).where(
            MarketOrder.player_id == player.id
        ).order_by(desc(MarketOrder.created_at))

        orders = (await session.execute(stmt)).scalars().all()

        if not orders:
            content = (
                f"📋 你还没有挂牌任何物品\n"
                f"***\n"
                f"{cmd('交易清单')} | {cmd('挂牌', '挂牌 ')}"
            )
            await my_orders_cmd.finish(build_markdown(content))

        PAGE_SIZE = 8
        total_pages = (len(orders) - 1) // PAGE_SIZE + 1 if orders else 1
        page = max(1, min(page, total_pages))
        start = (page - 1) * PAGE_SIZE
        end = start + PAGE_SIZE
        page_orders = orders[start:end]

        lines = [f"# 📋 我的挂牌 第{page}/{total_pages}页 ({len(orders)}个)"]
        lines.append("***")
        lines.append(f"📤 **出售订单**")

        sell_orders = [o for o in page_orders if o.side == OrderSide.SELL]
        if sell_orders:
            for order in sell_orders:
                item_cfg = config.items_config["by_id"].get(order.item_id)
                if item_cfg:
                    lines.append(f"🆔**{order.id}** | {cmd(item_cfg.name, '查牌 ' + item_cfg.name)} | 💰**{order.price}** 📦**{order.quantity}** | {cmd('撤牌', '撤牌 ' + str(order.id))}")
        else:
            lines.append("(空)")

        lines.append("***")
        lines.append(f"📥 **求购订单**")

        buy_orders = [o for o in page_orders if o.side == OrderSide.BUY]
        if buy_orders:
            for order in buy_orders:
                item_cfg = config.items_config["by_id"].get(order.item_id)
                if item_cfg:
                    lines.append(f"🆔**{order.id}** | {cmd(item_cfg.name, '查牌 ' + item_cfg.name)} | 💰**{order.price}** 📦**{order.quantity}** | {cmd('撤牌', '撤牌 ' + str(order.id))}")
        else:
            lines.append("(空)")

        lines.append("***")
        if total_pages > 1:
            nav = []
            if page > 1:
                nav.append(cmd(f'上一页', f'我的挂牌 {page - 1}'))
            if page < total_pages:
                nav.append(cmd(f'下一页', f'我的挂牌 {page + 1}'))
            lines.append(" | ".join(nav))
        lines.append(f"{cmd('交易清单')} | {cmd('挂牌', '挂牌 ')}")
        await my_orders_cmd.finish(build_markdown("\n".join(lines)))

# ---------------- 指令：查看税率 ----------------
tax_info_cmd = on_command("税率", aliases={"交易税率", "查看税率"}, block=True, priority=5)

@tax_info_cmd.handle()
async def _(event: MessageEvent):
    """查看当前的分段累进交易税率"""
    content = (
        f"# 💰 交易税率表（分段累进）\n"
        f"***\n"
        f"💚 ≤**5,000**金币：免税 (**0%**)\n"
        f"💛 **5,001**~**20,000**金币：超出部分 **5%**\n"
        f"🧡 **20,001**~**50,000**金币：超出部分 **10%**\n"
        f"❤️ **50,001**~**100,000**金币：超出部分 **15%**\n"
        f"💜 >**100,000**金币：超出部分 **20%**\n\n"
        f"📝 仅对超出部分征税，不会因多挂1金币多交一大笔\n"
        f"💡 举例：交易额 25,000 → 税收 **{calculate_transaction_tax(25000):,}**（而非2,500）\n"
        f"⚠️ 税收从卖家收入中扣除，直接销毁\n"
        f"***\n"
        f"{cmd('交易清单')} | {cmd('我的挂牌')} | {cmd('挂牌', '挂牌 ')}"
    )
    await tax_info_cmd.finish(build_markdown(content))


# ---------------- 指令：装备估价 ----------------
equipment_appraise_cmd = on_command("估价", aliases={"装备估价"}, block=True, priority=5)

@equipment_appraise_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """估价 装备编号/名称"""
    arg = args.extract_plain_text().strip()
    if not arg:
        await equipment_appraise_cmd.finish("⛔ 格式：估价 装备编号/名称")

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await equipment_appraise_cmd.finish("⛔ 请先创建角色")

        # 查找装备
        equipment = await find_equipment_by_input(session, player.id, arg)
        if not equipment:
            await equipment_appraise_cmd.finish("⛔ 未找到指定装备，请使用装备栏中显示的编号或装备名称")

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
            f"# 💰 装备估价报告",
            f"***",
            f"🎯 装备：{summary}",
            f"🆔 ID：**{equipment.id}**",
            "",
            f"📊 估价分析",
            f"▫️ 基础价值：**{equipment.config.price:,}** 金币",
        ]

        if equipment.upgrade_level > 0:
            upgrade_bonus = (equipment.get_upgrade_bonus_multiplier() - 1) * 100
            lines.append(f"▫️ 升阶加成：**+{upgrade_bonus:.0f}%** ({equipment.upgrade_level}阶)")

        if equipment.used_gem_slots > 0:
            gem_value = 0
            for gem_item_id in equipment.gem_slots_data.values():
                gem_config = config.items_config["by_id"].get(gem_item_id)
                if gem_config:
                    gem_value += gem_config.price
            lines.append(f"▫️ 宝石价值：**{gem_value:,}** 金币")

        durability_ratio = equipment.durability / equipment.config.durability if equipment.config.durability > 0 else 1.0
        if durability_ratio < 1.0:
            lines.append(f"▫️ 耐久影响：**{durability_ratio:.1%}**")

        lines.extend([
            "",
            f"💎 建议售价：**{min_price:,}** - **{max_price:,}** 金币",
            ""
        ])

        if market_orders:
            lines.append("📈 市场参考")
            for order in market_orders:
                lines.append(f"▫️ {order.equipment_summary} - **{order.price:,}** 金币")
        else:
            lines.append("📈 市场参考：暂无同类装备在售")

        eq_name = equipment.config.name if equipment.config else equipment.item_id
        lines.append("***")
        lines.append(f"{cmd('挂牌 出售 ' + eq_name, '挂牌 出售 ' + eq_name + ' ')} | {cmd('查牌 ' + eq_name, '查牌 ' + eq_name)} | {cmd('交易清单')}")

        await equipment_appraise_cmd.finish(build_markdown("\n".join(lines)))

# ======= 辅助函数 =======
async def _try_auto_match(session, new_order: MarketOrder, player: Player, same_price_only: bool = False) -> str:
    """自动撮合逻辑，返回描述信息（可能为空）。"""
    # 初始化新版service
    item_repo = ItemRepository(session)
    market_order_repo = MarketOrderRepository(session)
    equipment_service = EquipmentTradeServiceNew(item_repo, market_order_repo)

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

    halt_reason: str | None = None

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
            equipment = await equipment_service.get_equipment_by_instance_id(new_order.item_instance_id)
            if not equipment or not await equipment_service.transfer_equipment(equipment, buyer.id):
                break  # 装备转移失败，停止撮合
        elif opp.side == OrderSide.SELL and opp.is_equipment_trade:
            # 对手方是装备，转移装备实例
            equipment = await equipment_service.get_equipment_by_instance_id(opp.item_instance_id)
            if not equipment or not await equipment_service.transfer_equipment(equipment, buyer.id):
                break  # 装备转移失败，停止撮合
        else:
            # 普通物品交易，检查背包空间
            try:
                await ItemInstance.add_item(session, buyer.id, item_cfg.item_id, trade_qty)
            except ValueError:
                # 买家背包空间不足，停止撮合
                if buyer_id == player.id:
                    halt_reason = "⚠️ 成交中断：你的背包空间不足，未能继续自动撮合"
                else:
                    halt_reason = "⚠️ 成交中断：买家背包空间不足，未能继续自动撮合"
                break

        # 计算交易金额和阶梯税收
        trade_amount = trade_price * trade_qty
        tax = calculate_transaction_tax(trade_amount)

        # 金币给卖家（扣除税收）
        seller.gold += trade_amount - tax
        # 更新财富成就统计
        from ..achievement.achievement_service import AchievementService
        await AchievementService.update_stat(session, seller.id, "gold_earned_total", increment=trade_amount - tax, auto_commit=False)

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

    if halt_reason:
        trade_lines.append(halt_reason)

    return "\n".join(trade_lines)