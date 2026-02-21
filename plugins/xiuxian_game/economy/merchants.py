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
class MarketConfig:
    """市场配置类，支持独立的买入和卖出商品列表"""
    def __init__(self, mid: str, name: str, coord: Tuple[int, int],
                 sellable_items: List[str], buyable_items: List[str] = None):
        self.id = mid
        self.name = name
        self.x, self.y = coord
        self.sellable_items = sellable_items  # 市场出售的商品（玩家可购买）
        self.buyable_items = buyable_items or sellable_items  # 市场收购的商品（玩家可出售）
        # 为了兼容现有代码，保留items属性
        self.items = list(set(sellable_items + self.buyable_items))

    def can_sell_to_player(self, item_id: str) -> bool:
        """检查市场是否向玩家出售此商品"""
        return item_id in self.sellable_items

    def can_buy_from_player(self, item_id: str) -> bool:
        """检查市场是否从玩家收购此商品"""
        return item_id in self.buyable_items

# 所有跑商商品列表（包含血契丹和阴冥草，用于市场配置和分析）
ALL_GOODS = [
    "lux_perfume", "red_wine", "gold_watch", "jade_bracelet", "silk_scarf",
    "dslr_camera", "smartphone", "gaming_console", "designer_bag", "luxury_chocolate",
    "art_book", "concert_ticket", "fountain_pen", "sneakers", "noise_headphones",
    "yin_grass", "blood_pact"
]

# 受携带限制的商品列表（不包含血契丹、阴冥草和鱼类）
LIMITED_GOODS = [
    "lux_perfume", "red_wine", "gold_watch", "jade_bracelet", "silk_scarf",
    "dslr_camera", "smartphone", "gaming_console", "designer_bag", "luxury_chocolate",
    "art_book", "concert_ticket", "fountain_pen", "sneakers", "noise_headphones"
]

# 所有鱼类列表（钓鱼系统专用）
ALL_FISH = [
    # 普通鱼类（白色品质）
    "common_carp", "crucian_carp", "grass_carp", "silver_carp", "catfish",
    # 绿色品质鱼类
    "bass", "mandarin_fish", "yellow_croaker", "pomfret", "snapper",
    # 蓝色品质鱼类
    "salmon", "tuna", "grouper", "eel", "turbot",
    # 紫色品质稀有鱼类
    "chinese_sturgeon", "arowana", "giant_catfish", "bluefin_tuna",
    # 橙色品质传说鱼类
    "golden_dragon_fish", "phoenix_fish", "void_fish"
]

# ================= 硬编码市集配置 =================
# 基于地理位置和经济特色进行商品分配，确保跑商路线的多样性和盈利性

MARKET_CONFIGS = {
    # 上京 (0,0) - 政治中心，奢侈品集散地
    "merchant1": {
        "name": "上京",
        "coord": (0, 0),
        "sellable": ["gold_watch", "jade_bracelet", "lux_perfume", "designer_bag", "red_wine", "spice", "secret_sauce", "immortal_oil"],
        "buyable": ["gold_watch", "jade_bracelet", "lux_perfume", "designer_bag", "red_wine", "art_book"]
    },

    # 北郊 (100,460) - 工业区，电子产品集中
    "merchant2": {
        "name": "北郊",
        "coord": (100, 460),
        "sellable": ["smartphone", "gaming_console", "noise_headphones", "dslr_camera", "lux_perfume"],
        "buyable": ["smartphone", "gaming_console", "noise_headphones", "dslr_camera", "fountain_pen"]
    },

    # 东郊 (390,50) - 制造业基地，日用品丰富
    "merchant3": {
        "name": "东郊",
        "coord": (390, 50),
        "sellable": ["sneakers", "silk_scarf", "fountain_pen", "concert_ticket", "luxury_chocolate"],
        "buyable": ["sneakers", "silk_scarf", "fountain_pen", "concert_ticket", "smartphone", "gaming_console"]
    },

    # 西郊 (-420,140) - 文化区，艺术品交易
    "merchant4": {
        "name": "西郊",
        "coord": (-420, 140),
        "sellable": ["art_book", "concert_ticket", "fountain_pen", "luxury_chocolate", "blood_pact"],
        "buyable": ["art_book", "concert_ticket", "fountain_pen", "luxury_chocolate", "lux_perfume", "designer_bag"]
    },

    # 南郊 (-100,-480) - 港口，进口商品多
    "merchant5": {
        "name": "南郊",
        "coord": (-100, -480),
        "sellable": ["red_wine", "luxury_chocolate", "designer_bag", "dslr_camera", "gold_watch"],
        "buyable": ["red_wine", "luxury_chocolate", "dslr_camera", "gold_watch", "jade_bracelet", "gaming_console"]
    },

    # 金陵 (220,-350) - 古都，传统与现代结合
    "merchant6": {
        "name": "金陵",
        "coord": (220, -350),
        "sellable": ["gold_watch", "art_book", "fountain_pen", "silk_scarf", "yin_grass"],
        "buyable": ["gold_watch", "art_book", "silk_scarf", "yin_grass", "sneakers", "concert_ticket", "jade_bracelet"]
    },

    # 云岭 (-250,490) - 山区，药材丰富
    "merchant7": {
        "name": "云岭",
        "coord": (-250, 490),
        "sellable": ["yin_grass", "blood_pact", "luxury_chocolate", "art_book", "gaming_console", "lingzhi_powder"],
        "buyable": ["yin_grass", "blood_pact", "luxury_chocolate", "silk_scarf", "fountain_pen"]
    },

    # 郸城 (120,120) - 商业重镇，各类商品齐全
    "merchant8": {
        "name": "郸城",
        "coord": (120, 120),
        "sellable": ["smartphone", "sneakers", "noise_headphones", "designer_bag", "concert_ticket"],
        "buyable": ["smartphone", "sneakers", "noise_headphones", "designer_bag", "gaming_console", "lux_perfume"]
    },

    # 荔湾镇 (120,200) - 小镇，特色商品
    "merchant9": {
        "name": "荔湾镇",
        "coord": (120, 200),
        "sellable": ["silk_scarf", "luxury_chocolate", "fountain_pen", "sneakers", "spice"],
        "buyable": ["silk_scarf", "luxury_chocolate", "fountain_pen", "sneakers", "art_book", "noise_headphones"]
    },

    # 摩配镇 (80,140) - 机械城，电子设备专业
    "merchant10": {
        "name": "摩配镇",
        "coord": (80, 140),
        "sellable": ["gaming_console", "dslr_camera", "noise_headphones", "smartphone"],
        "buyable": ["gaming_console", "dslr_camera", "noise_headphones", "red_wine", "lux_perfume"]
    },

    # 风雪镇 (-5,390) - 边境小镇，药材和特殊商品
    "merchant11": {
        "name": "风雪镇",
        "coord": (-5, 390),
        "sellable": ["blood_pact", "yin_grass", "concert_ticket", "art_book", "lingzhi_powder"],
        "buyable": ["blood_pact", "yin_grass", "concert_ticket", "jade_bracelet", "gold_watch"]
    },

    # 舟山 (200,-200) - 海岛城市，海外商品 + 鱼类收购
    "merchant12": {
        "name": "舟山",
        "coord": (200, -200),
        "sellable": ["jade_bracelet", "red_wine", "dslr_camera", "designer_bag", "wasabi"],
        "buyable": ["jade_bracelet", "red_wine", "dslr_camera", "designer_bag", "gaming_console", "smartphone"] + ALL_FISH
    },

    # 大昌市 (-400,-240) - 西南商埠，综合贸易
    "merchant13": {
        "name": "大昌市",
        "coord": (-400, -240),
        "sellable": ["smartphone", "sneakers", "noise_headphones", "designer_bag", "concert_ticket", "spice"],
        "buyable": ["smartphone", "sneakers", "noise_headphones", "designer_bag", "gaming_console", "lux_perfume"]
    }
}

# 创建市场实例
MARKETS: List[MarketConfig] = []
for mid, config_data in MARKET_CONFIGS.items():
    market = MarketConfig(
        mid=mid,
        name=config_data["name"],
        coord=config_data["coord"],
        sellable_items=config_data["sellable"],
        buyable_items=config_data["buyable"]
    )
    MARKETS.append(market)

MARKET_BY_COORD: Dict[Tuple[int, int], MarketConfig] = {(m.x, m.y): m for m in MARKETS}

# ================= 配置验证和分析工具 =================
def analyze_market_configuration():
    """分析市场配置的合理性"""
    print("=== 市集货物分配分析报告 ===")

    # 统计每种商品的分布
    item_distribution = {}
    for item_id in ALL_GOODS:
        sellable_markets = [m.name for m in MARKETS if m.can_sell_to_player(item_id)]
        buyable_markets = [m.name for m in MARKETS if m.can_buy_from_player(item_id)]
        item_distribution[item_id] = {
            'sellable_count': len(sellable_markets),
            'buyable_count': len(buyable_markets),
            'sellable_markets': sellable_markets,
            'buyable_markets': buyable_markets
        }

    print("\n📊 商品分布统计：")
    for item_id, dist in item_distribution.items():
        from ..config import config
        item_cfg = config.items_config["by_id"].get(item_id)
        item_name = item_cfg.name if item_cfg else item_id
        print(f"  {item_name}: 出售{dist['sellable_count']}个市集, 收购{dist['buyable_count']}个市集")

    # 统计市集商品数量
    print("\n🏪 市集商品数量：")
    for market in MARKETS:
        print(f"  {market.name}: 出售{len(market.sellable_items)}种, 收购{len(market.buyable_items)}种")

    # 分析跑商路线数量
    route_count = 0
    for src in MARKETS:
        for dst in MARKETS:
            if src == dst:
                continue
            common_items = set(src.sellable_items) & set(dst.buyable_items)
            if common_items:
                route_count += len(common_items)

    print(f"\n🚚 理论跑商路线数量: {route_count}")
    print(f"📍 平均每个市集间距: {sum(abs(m1.x-m2.x)+abs(m1.y-m2.y) for m1 in MARKETS for m2 in MARKETS if m1!=m2) // (len(MARKETS)*(len(MARKETS)-1))}")

    # 检查是否有孤立商品
    isolated_items = [item_id for item_id, dist in item_distribution.items()
                     if dist['sellable_count'] < 3 or dist['buyable_count'] < 3]
    if isolated_items:
        print(f"\n⚠️ 交易机会较少的商品: {isolated_items}")

    print("=== 分析完成 ===\n")

# 在模块加载时进行配置分析（仅在开发环境）
# analyze_market_configuration()

# ------------------- 工具函数 -------------------
_DEF_TIME = time(hour=9)


def _current_seed_day() -> date:
    """返回当前价格所属日期：若当前时间 <09:00 视为前一天。"""
    now = datetime.now()
    day = now.date()
    if now.time() < _DEF_TIME:
        day -= timedelta(days=1)
    return day



async def _price_for(session, market: MarketConfig, item_id: str) -> Tuple[int, int]:
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

# 交易限制查询：查看玩家当前的交易限制情况
trade_restrictions_cmd = on_command("交易限制", aliases={"限制查询", "交易状态"}, block=True, priority=5)

@market_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await market_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
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
            lines.append("━━━━━━━━━━━━━\n🧭 前往对应坐标后输入【市集】联系当地商人\n🧭 使用【导航 x y】前往")
            await market_cmd.finish(message_add_head("\n".join(lines), event))

        lines = [f"🏪 {market.name} ({market.x},{market.y})", "━━━━━━━━━━━━━"]

        # 显示可购买的商品
        if market.sellable_items:
            lines.append("📦 可购买商品：")
            for iid in market.sellable_items:
                item_cfg = config.items_config["by_id"].get(iid)
                sell_p, _ = await _price_for(session, market, iid)

                # 获取库存状态
                market_state = await MarketState.get_or_create(session, market.id, iid)
                stock_status = market_state.get_stock_status()
                stock_info = f"({market_state.current_stock})"

                lines.append(f"  {item_cfg.name}│售价 {sell_p}│库存{stock_info}{stock_status}")

        # 显示可出售的商品（如果与可购买不同）
        buyable_only = set(market.buyable_items) - set(market.sellable_items)
        if buyable_only:
            lines.append("💰 额外收购商品：")
            for iid in buyable_only:
                item_cfg = config.items_config["by_id"].get(iid)
                _, buy_p = await _price_for(session, market, iid)
                lines.append(f"  {item_cfg.name}│收价 {buy_p}")

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
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await buy_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
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

        # 市集购买逻辑 - 检查市场是否出售此商品
        if market and market.can_sell_to_player(item_cfg.item_id):
            # 获取市场状态
            market_state = await MarketState.get_or_create(session, market.id, item_cfg.item_id)
            await market_state.check_daily_refresh(session)

            # 检查库存
            if not market_state.can_purchase(qty):
                await buy_cmd.finish(f"❌ 库存不足！当前库存：{market_state.current_stock}，需要：{qty}")

            # 检查背包商品总量限制（防止高等级玩家垄断库存）
            # 注意：血契丹、阴冥草、鱼类和调味料(SEASONING)不占用携带上限
            if item_cfg.item_id in LIMITED_GOODS:
                result_inv = await session.execute(
                    select(ItemInstance).where(
                        ItemInstance.player_id == player.id,
                        ItemInstance.item_id.in_(LIMITED_GOODS)  # 仅统计受限商品
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

        # 黑市/基础商店逻辑
        else:
            # 今日黑市上架（非基础物品）
            today_items = await _pick_black_market_today_items(session)
            if item_cfg.item_id in SHOP_ITEMS:
                # 基础物品原价
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

            elif item_cfg.item_id in today_items:
                # 黑市高溢价 + 限购
                # 确保今日库存已初始化
                await _ensure_black_market_stock(session, [item_cfg.item_id])
                mstate = await MarketState.get_or_create(session, BLACK_MARKET_ID, item_cfg.item_id)

                if not mstate.can_purchase(qty):
                    await buy_cmd.finish(f"❌ 黑市库存不足！当前库存：{mstate.current_stock}，需要：{qty}")

                # 每人每天总限购（不含基础物品）
                bought = await _black_market_daily_purchased_qty(session, player.id)
                remaining = max(0, BLACK_MARKET_DAILY_LIMIT_PER_PLAYER - bought)
                if qty > remaining:
                    await buy_cmd.finish(
                        f"⛔ 超出今日限购！已购 {bought}/{BLACK_MARKET_DAILY_LIMIT_PER_PLAYER}，还可购买 {remaining} 件")

                unit_price = max(1, int((item_cfg.price or 1) * BLACK_MARKET_OVERPRICE))
                total_cost = unit_price * qty
                if player.gold < total_cost:
                    await buy_cmd.finish(f"💰 金币不足，需要 {total_cost} (当前 {player.gold})")

                # 先加物，再扣款，避免金额不足卡死库存
                try:
                    await ItemInstance.add_item(session, player.id, item_cfg.item_id, qty)
                except ValueError as e:
                    await buy_cmd.finish(f"❌ {e}")

                player.gold -= total_cost
                mstate.apply_purchase(qty)

                # 记录交易
                await TradeRecord.record_trade(
                    session=session,
                    player_id=player.id,
                    trade_type=TradeType.BUY,
                    market_id=BLACK_MARKET_ID,
                    item_id=item_cfg.item_id,
                    quantity=qty,
                    unit_price=unit_price,
                    total_amount=total_cost
                )

                session.add_all([player, mstate])
                await session.commit()

                await buy_cmd.finish(message_add_head(
                    f"✅ 黑市购买 {item_cfg.name}×{qty} 成功！\n💸 花费 {total_cost} 金币\n"
                    f"📦 黑市剩余库存：{mstate.current_stock}", event))

            else:
                await buy_cmd.finish("⛔ 此处无法购买该物品")

# -------- 卖出 --------
sell_cmd = on_command("出售", aliases={"卖"}, block=True, priority=5)

# -------- 自动出售 --------
auto_sell_cmd = on_command("自动出售", aliases={"一键出售", "批量出售"}, block=True, priority=5)

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
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await sell_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
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
        if not item_cfg:
            await sell_cmd.finish("⛔ 不存在该物品")

        # 检查市场是否收购此商品
        if not market.can_buy_from_player(item_cfg.item_id):
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
        # 更新财富成就统计
        from ..achievement.achievement_service import AchievementService
        await AchievementService.update_stat(session, player.id, "gold_earned_total", increment=total_gain + bonus, auto_commit=False)
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

@auto_sell_cmd.handle()
async def _(event: MessageEvent):
    """自动出售背包中所有可出售的商品"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await auto_sell_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await auto_sell_cmd.finish("⛔ 请先创建角色")

        # 获取当前位置的市场
        current_x, current_y = player.get_current_coordinates()
        market = MARKET_BY_COORD.get((current_x, current_y))
        if not market:
            await auto_sell_cmd.finish("⛔ 当前位置没有市集，请先前往市集")

        # 获取背包中的所有商品（排除装备）
        result = await session.execute(
            select(ItemInstance)
            .where(ItemInstance.player_id == player.id)
            .where(ItemInstance.quantity > 0)
        )
        all_items = result.scalars().all()

        # 过滤出可出售的商品，并按物品ID聚合数量
        aggregated_items: dict[str, int] = {}
        blocked_items: set[str] = set()

        for item in all_items:
            if item.is_equipment:
                continue  # 跳过装备

            if not market.can_buy_from_player(item.item_id):
                continue

            if item.item_id in blocked_items:
                continue

            if item.item_id not in aggregated_items:
                can_sell = await TradeRecord.can_sell_at_market(
                    session, player.id, market.id, item.item_id, hours=4
                )
                if not can_sell:
                    blocked_items.add(item.item_id)
                    continue
                aggregated_items[item.item_id] = 0

            aggregated_items[item.item_id] += item.quantity

        if not aggregated_items:
            await auto_sell_cmd.finish(message_add_head(
                "📦 背包中没有可在当前市集出售的商品\n"
                "💡 可能原因：\n"
                "• 背包中没有商品\n"
                "• 当前市集不收购你的商品\n"
                "• 4小时内在此地购买的商品不能出售", event))

        # 计算总收益和详细信息
        total_gain = 0
        total_bonus = 0
        sold_items = []

        for item_id, quantity in aggregated_items.items():
            if quantity <= 0:
                continue

            item_cfg = config.items_config["by_id"].get(item_id)
            if not item_cfg:
                continue

            # 获取市场状态和价格
            market_state = await MarketState.get_or_create(session, market.id, item_id)
            await market_state.check_daily_refresh(session)

            _, buy_price = await _price_for(session, market, item_id)
            item_gain = buy_price * quantity

            # 计算跑商奖励
            bonus = 0
            recent_purchases = await TradeRecord.get_recent_purchases_at_market(
                session, player.id, market.id, item_id, hours=24
            )
            if not recent_purchases:
                bonus = int(item_gain * 0.05)

            # 扣除物品
            try:
                success_consume = await ItemInstance.consume_item(
                    session, player.id, item_id, quantity
                )
            except ValueError:
                continue

            if not success_consume:
                continue

            # 更新市场状态
            market_state.apply_sale(quantity)

            # 记录交易
            await TradeRecord.record_trade(
                session=session,
                player_id=player.id,
                trade_type=TradeType.SELL,
                market_id=market.id,
                item_id=item_id,
                quantity=quantity,
                unit_price=buy_price,
                total_amount=item_gain
            )

            total_gain += item_gain
            total_bonus += bonus
            sold_items.append({
                "name": item_cfg.name,
                "quantity": quantity,
                "unit_price": buy_price,
                "total": item_gain,
                "bonus": bonus
            })

            session.add(market_state)

        if not sold_items:
            await auto_sell_cmd.finish(message_add_head("❌ 没有成功出售任何商品", event))

        # 更新玩家金币
        player.gold += total_gain + total_bonus
        # 更新财富成就统计
        from ..achievement.achievement_service import AchievementService
        await AchievementService.update_stat(session, player.id, "gold_earned_total", increment=total_gain + total_bonus, auto_commit=False)
        session.add(player)
        await session.commit()

        # 生成结果消息
        lines = [
            f"💰 自动出售完成！共出售 {len(sold_items)} 种商品",
            "━━━━━━━━━━━━━"
        ]

        for item in sold_items:
            bonus_text = f" (+{item['bonus']}跑商奖励)" if item['bonus'] > 0 else ""
            lines.append(f"• {item['name']} ×{item['quantity']} = {item['total']}金币{bonus_text}")

        lines.extend([
            "━━━━━━━━━━━━━",
            f"🪙 总收益：{total_gain + total_bonus} 金币",
            f"💰 当前金币：{player.gold}"
        ])

        if total_bonus > 0:
            lines.append(f"🎁 跨市场交易奖励：{total_bonus} 金币")

        await auto_sell_cmd.finish(message_add_head("\n".join(lines), event))

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

        # 显示可购买的商品
        if market.sellable_items:
            lines.append("📦 可购买商品：")
            for iid in market.sellable_items:
                item_cfg = config.items_config["by_id"].get(iid)
                sell_p, _ = await _price_for(session, market, iid)

                # 获取库存状态
                market_state = await MarketState.get_or_create(session, market.id, iid)
                stock_status = market_state.get_stock_status()
                stock_info = f"({market_state.current_stock})"

                lines.append(f"  {item_cfg.name}│售价 {sell_p}│库存{stock_info}{stock_status}")

        # 显示可出售的商品（如果与可购买不同）
        buyable_only = set(market.buyable_items) - set(market.sellable_items)
        if buyable_only:
            lines.append("💰 额外收购商品：")
            for iid in buyable_only:
                item_cfg = config.items_config["by_id"].get(iid)
                _, buy_p = await _price_for(session, market, iid)
                lines.append(f"  {item_cfg.name}│收价 {buy_p}")

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
            can_sell = m.can_sell_to_player(item_cfg.item_id)
            can_buy = m.can_buy_from_player(item_cfg.item_id)

            if not can_sell and not can_buy:
                continue

            found = True
            price_info = []

            if can_sell:
                sell_p, _ = await _price_for(session, m, item_cfg.item_id)
                # 获取库存状态
                market_state = await MarketState.get_or_create(session, m.id, item_cfg.item_id)
                stock_info = f"({market_state.current_stock})"
                price_info.append(f"售 {sell_p}│库存{stock_info}")

            if can_buy:
                _, buy_p = await _price_for(session, m, item_cfg.item_id)
                price_info.append(f"收 {buy_p}")

            lines.append(f"{m.name}│{' '.join(price_info)}")

        if not found:
            await price_compare_cmd.finish("ℹ️ 暂无市集交易该物品")

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
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await trade_history_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
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
    """遍历市集与商品，列出正利润路线（购买→售出），考虑玩家个人交易限制。"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await trade_advise_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await trade_advise_cmd.finish("⛔ 请先创建角色")

        opportunities = []
        filtered_count = 0  # 被过滤掉的机会数量

        for src in MARKETS:
            for iid in src.sellable_items:  # 只考虑源市场出售的商品
                # 检查源市场库存
                src_state = await MarketState.get_or_create(session, src.id, iid)
                if not src_state.can_purchase(1):  # 至少要有1个库存
                    continue

                sell_p_src, _ = await _price_for(session, src, iid)
                for dst in MARKETS:
                    if dst is src or not dst.can_buy_from_player(iid):  # 检查目标市场是否收购此商品
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

                        # 检查玩家是否可以在目标市场出售该商品（考虑原地交易限制）
                        can_sell_at_dst = await TradeRecord.can_sell_at_market(
                            session, player.id, dst.id, iid, hours=4
                        )

                        if not can_sell_at_dst:
                            filtered_count += 1
                            continue  # 跳过这个机会，因为玩家在目标市场有交易限制

                        opportunities.append({
                            "item": item_cfg.name,
                            "from": src.name,
                            "to": dst.name,
                            "buy": sell_p_src,
                            "sell": buy_p_dst,
                            "profit": profit,
                            "margin": margin,
                            "src_stock": src_state.current_stock,
                            "src_id": src.id,
                            "dst_id": dst.id,
                            "item_id": iid,
                        })

        if not opportunities:
            filter_msg = ""
            if filtered_count > 0:
                filter_msg = f"\n💡 已过滤 {filtered_count} 个受交易限制影响的机会"
            await trade_advise_cmd.finish(f"ℹ️ 今日暂无可用的盈利机会，明天再来看看吧！{filter_msg}")

        # 按利润降序排序，随机挑选前10条中的5条进行推荐
        opportunities.sort(key=lambda d: d["profit"], reverse=True)

        # 从前10条中随机选择5条，如果不足10条则全部选择
        import random as _rnd
        top_opportunities = opportunities[:10]  # 取前10条
        sample = _rnd.sample(top_opportunities, min(5, len(top_opportunities)))

        lines = ["💹 跑商盈利机会 (个性化推荐)", "━━━━━━━━━━━━━"]

        # 添加个人情况说明
        if filtered_count > 0:
            lines.append(f"🔍 已为您过滤 {filtered_count} 个受交易限制的机会")
            lines.append("━━━━━━━━━━━━━")

        for op in sample:
            lines.append(
                f"📦 {op['item']} (库存:{op['src_stock']})\n🛒 {op['from']} → {op['to']}  "+
                f"💸 {op['buy']} → 💰 {op['sell']}  "+
                f"📈 +{op['profit']} ({op['margin']*100:.0f}%)"
            )
            lines.append("──────────")

        # 添加提示信息
        lines.append("💡 推荐已考虑您的交易记录，避免原地交易限制")
        if filtered_count > 0:
            lines.append("💡 4小时后可能有更多机会解锁")

        await trade_advise_cmd.finish(message_add_head("\n".join(lines), event))

# 系统商店基础物品（保留原价）
SHOP_ITEMS = [
    "revive_potion", "president_letter", "territory_expansion_scroll", "heal_potion", "spirit_herb",
    # 基础调料（烹饪系统）
    "salt", "soy_sauce", "vinegar", "sugar"
]

# 黑市配置
BLACK_MARKET_ID = "black_market"
BLACK_MARKET_OVERPRICE = 10
BLACK_MARKET_MIN_ITEMS = 3
BLACK_MARKET_MAX_ITEMS = 6
BLACK_MARKET_STOCK_MIN = 10
BLACK_MARKET_STOCK_MAX = 20
BLACK_MARKET_DAILY_LIMIT_PER_PLAYER = 50  # 除基础物品外，每人每日总限购

# 黑市候选池（不含装备）——以消耗品为主，如升阶石/稳定水晶
BLACK_MARKET_CANDIDATES = [
    "upgrade_stone_low", "upgrade_stone_mid", "upgrade_stone_high", "upgrade_stone_supreme", "stabilizer_crystal"
]

from datetime import datetime as _dt, time as _time


def _black_market_seed_day() -> str:
    """与市集一致的日切：09:00 前算前一天。返回形如 'YYYY-MM-DD' 的字符串。"""
    day = _current_seed_day()  # 复用市集的日切逻辑
    return day.isoformat()


def _black_market_day_start_dt() -> _dt:
    """返回本'黑市日'的起始时间点(datetime)，用于统计每日限购。"""
    day = _current_seed_day()
    return _dt.combine(day, _DEF_TIME)


async def _pick_black_market_today_items(session) -> list[str]:
    """确定今日黑市上架道具（按固定种子随机），不含基础物品与装备。"""
    seed_str = f"{BLACK_MARKET_ID}:{_black_market_seed_day()}"
    seed_int = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
    rng_local = random.Random(seed_int)

    # 过滤候选中不存在或为装备的条目
    valid = []
    for iid in BLACK_MARKET_CANDIDATES:
        cfg = config.items_config["by_id"].get(iid)
        if not cfg:
            continue
        if getattr(cfg, "type", "") == "EQUIPMENT":
            continue
        # 排除基础物品
        if iid in SHOP_ITEMS:
            continue
        valid.append(iid)

    if not valid:
        return []

    count = rng_local.randint(BLACK_MARKET_MIN_ITEMS, min(BLACK_MARKET_MAX_ITEMS, len(valid)))
    rng_local.shuffle(valid)
    return valid[:count]


async def _ensure_black_market_stock(session, items: list[str]):
    """为今日上架的黑市物品设置库存（每日刷新为10-20随机），使用 MarketState 持久化。"""
    if not items:
        return
    today = _current_seed_day()
    seed_str = f"{BLACK_MARKET_ID}:{today.isoformat()}:stock"
    seed_int = int(hashlib.md5(seed_str.encode()).hexdigest(), 16)
    rng_local = random.Random(seed_int)

    for iid in items:
        market_state = await MarketState.get_or_create(session, BLACK_MARKET_ID, iid)
        # 若跨日，则重置库存到当日随机值
        last_date = market_state.last_refresh_date
        if isinstance(last_date, _dt):
            last_date = last_date.date()
        if last_date < today:
            stock = rng_local.randint(BLACK_MARKET_STOCK_MIN, BLACK_MARKET_STOCK_MAX)
            market_state.current_stock = stock
            market_state.max_stock = stock
            market_state.daily_sold = 0
            market_state.daily_bought = 0
            market_state.last_refresh_date = today
            market_state.updated_at = _dt.now()
            session.add(market_state)


async def _black_market_daily_purchased_qty(session, player_id: str) -> int:
    """统计玩家今日在黑市（非基础物品）的已购数量（用于50件总限购）。"""
    from sqlalchemy import select, and_
    day_start = _black_market_day_start_dt()
    stmt = select(TradeRecord).where(and_(
        TradeRecord.player_id == player_id,
        TradeRecord.market_id == BLACK_MARKET_ID,
        TradeRecord.trade_type == TradeType.BUY,
        TradeRecord.trade_time > day_start,
    ))
    result = await session.execute(stmt)
    records = result.scalars().all()
    total = 0
    # 仅统计非基础物品
    for r in records:
        if r.item_id in SHOP_ITEMS:
            continue
        total += r.quantity
    return total


# 黑市指令（替代原“系统商店”）
black_market_cmd = on_command("黑市", aliases={"系统商店", "特殊商店"}, block=True, priority=5)

@black_market_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await black_market_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await black_market_cmd.finish("⛔ 请先创建角色")
        if player.region != "大都会":
            await black_market_cmd.finish(message_add_head(
                "💀 诡域之中皆不可信\n"
                "━━━━━━━━━━━━━\n"
                "此地没有安全商人。\n"
                "━━━━━━━━━━━━━\n"
                "⬇️ 【返回】脱离诡域，返回现实", event))

        # 今日上架与库存
        today_items = await _pick_black_market_today_items(session)
        await _ensure_black_market_stock(session, today_items)

        lines = ["🕳️ 黑市", "━━━━━━━━━━━━━"]
        # 今日黑市·高溢价限量
        if today_items:
            lines.append("🖤 黑市商人：这可都是我从诡域坟墓里偷出来的好东西~".format(BLACK_MARKET_OVERPRICE))
            for iid in today_items:
                cfg = config.items_config["by_id"].get(iid)
                if not cfg:
                    continue
                mstate = await MarketState.get_or_create(session, BLACK_MARKET_ID, iid)
                unit_price = max(1, int((cfg.price or 1) * BLACK_MARKET_OVERPRICE))
                lines.append(f"• {cfg.name}│{unit_price} 金币│库存({mstate.current_stock})")
            lines.append("━━━━━━━━━━━━━")

        # 基础物品·原价
        lines.append("📦 基础物品（原价）:")
        for item_id in SHOP_ITEMS:
            cfg = config.items_config["by_id"].get(item_id)
            if cfg:
                lines.append(f"• {cfg.name}│{cfg.price} 金币")

        # 限购说明
        bought = await _black_market_daily_purchased_qty(session, player.id)
        lines.extend([
            "━━━━━━━━━━━━━",
            f"📏 限购：除基础物品外，每人每日总计≤{BLACK_MARKET_DAILY_LIMIT_PER_PLAYER} 件",
            f"🧮 今日已购（不含基础物品）：{bought}/{BLACK_MARKET_DAILY_LIMIT_PER_PLAYER}",
            "⬇️【购买 物品名称 数量】"
        ])
        await black_market_cmd.finish(message_add_head("\n".join(lines), event))


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
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await headquarters_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
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
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await headquarters_exchange_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
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


# -------- 交易限制查询 --------

@trade_restrictions_cmd.handle()
async def _(event: MessageEvent):
    """查看玩家当前的交易限制情况"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player | None = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await trade_restrictions_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await trade_restrictions_cmd.finish("⛔ 请先创建角色")

        from datetime import timedelta
        from sqlalchemy import select, and_

        # 查询最近4小时内的购买记录
        time_limit = datetime.now() - timedelta(hours=4)
        stmt = select(TradeRecord).where(
            and_(
                TradeRecord.player_id == player.id,
                TradeRecord.trade_type == TradeType.BUY,
                TradeRecord.trade_time > time_limit
            )
        ).order_by(TradeRecord.trade_time.desc())

        result = await session.execute(stmt)
        recent_purchases = result.scalars().all()

        if not recent_purchases:
            await trade_restrictions_cmd.finish(message_add_head(
                "✅ 当前无交易限制\n"
                "━━━━━━━━━━━━━\n"
                "🎯 所有市集均可自由交易\n"
                "💡 可使用【跑商推荐】查看盈利机会", event))

        lines = ["⚠️ 当前交易限制情况", "━━━━━━━━━━━━━"]

        # 按市场分组统计限制
        restrictions_by_market = {}
        for purchase in recent_purchases:
            market_id = purchase.market_id
            item_id = purchase.item_id

            if market_id not in restrictions_by_market:
                restrictions_by_market[market_id] = []

            # 计算解锁时间
            unlock_time = purchase.trade_time + timedelta(hours=4)
            time_remaining = unlock_time - datetime.now()

            if time_remaining.total_seconds() > 0:
                hours = int(time_remaining.total_seconds() // 3600)
                minutes = int((time_remaining.total_seconds() % 3600) // 60)
                time_str = f"{hours}小时{minutes}分钟" if hours > 0 else f"{minutes}分钟"

                item_cfg = config.items_config["by_id"].get(item_id)
                item_name = item_cfg.name if item_cfg else item_id

                restrictions_by_market[market_id].append({
                    "item": item_name,
                    "time_remaining": time_str,
                    "unlock_time": unlock_time
                })

        # 显示限制信息
        for market_id, restrictions in restrictions_by_market.items():
            if not restrictions:  # 跳过已过期的限制
                continue

            market = next((m for m in MARKETS if m.id == market_id), None)
            market_name = market.name if market else market_id

            lines.append(f"📍 {market_name}")
            for restriction in restrictions:
                lines.append(f"  🚫 {restriction['item']} - 还需 {restriction['time_remaining']}")
            lines.append("")

        if len(lines) == 2:  # 只有标题，说明所有限制都已过期
            await trade_restrictions_cmd.finish(message_add_head(
                "✅ 当前无交易限制\n"
                "━━━━━━━━━━━━━\n"
                "🎯 所有市集均可自由交易\n"
                "💡 可使用【跑商推荐】查看盈利机会", event))

        lines.extend([
            "━━━━━━━━━━━━━",
            "💡 在限制时间内无法在对应市集出售相应商品",
            "💡 可前往其他市集出售或等待限制解除",
            "💡 使用【跑商推荐】获取个性化建议"
        ])

        await trade_restrictions_cmd.finish(message_add_head("\n".join(lines), event))