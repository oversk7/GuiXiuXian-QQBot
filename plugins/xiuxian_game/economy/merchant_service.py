from __future__ import annotations

"""跑商系统服务层（纯业务逻辑）

市集/集群配置、地理与动态定价、阶梯加价、跑商多元奖励与跑商税、
黑市与基础商店配置、缉邪司总部商品配置。
"""

from datetime import datetime, date
import random
import hashlib
from typing import Dict, Tuple, List

from ..models.market_state import MarketState
from ..models.trade_record import TradeRecord, TradeType
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
# 八大集群 · 35城 — 参见 llmdoc/design/specs/2026-04-04-world-map-expansion-design.md

MARKET_CONFIGS = {
    # ==================== 集群一：京畿（5城）====================
    "merchant_shangjing": {
        "name": "上京",
        "coord": (0, 0),
        "sellable": ["gold_watch", "jade_bracelet", "lux_perfume", "designer_bag", "red_wine", "spice", "secret_sauce", "immortal_oil"],
        "buyable": ["gold_watch", "jade_bracelet", "lux_perfume", "designer_bag", "red_wine", "art_book"]
    },
    "merchant_dancheng": {
        "name": "郸城",
        "coord": (150, -130),
        "sellable": ["gold_watch", "designer_bag", "lux_perfume", "smartphone", "concert_ticket"],
        "buyable": ["gold_watch", "designer_bag", "lux_perfume", "smartphone", "sneakers", "art_book"]
    },
    "merchant_mopeizhen": {
        "name": "摩配镇",
        "coord": (80, 160),
        "sellable": ["gaming_console", "dslr_camera", "noise_headphones", "smartphone"],
        "buyable": ["gaming_console", "dslr_camera", "noise_headphones", "red_wine", "lux_perfume"]
    },
    "merchant_tianhaiwei": {
        "name": "天海卫",
        "coord": (250, -50),
        "sellable": ["jade_bracelet", "designer_bag", "red_wine", "gold_watch", "noise_headphones"],
        "buyable": ["jade_bracelet", "designer_bag", "red_wine", "sneakers", "art_book", "fountain_pen"]
    },
    "merchant_shiguan": {
        "name": "石关",
        "coord": (-200, -150),
        "sellable": ["lux_perfume", "gold_watch", "concert_ticket", "noise_headphones"],
        "buyable": ["lux_perfume", "gold_watch", "sneakers", "art_book", "silk_scarf"]
    },

    # ==================== 集群二：江南（5城）====================
    "merchant_jinling": {
        "name": "金陵",
        "coord": (450, -480),
        "sellable": ["silk_scarf", "art_book", "fountain_pen", "luxury_chocolate", "yin_grass", "spice"],
        "buyable": ["silk_scarf", "art_book", "yin_grass", "sneakers", "concert_ticket", "jade_bracelet"]
    },
    "merchant_gusu": {
        "name": "姑苏",
        "coord": (600, -520),
        "sellable": ["silk_scarf", "art_book", "luxury_chocolate", "fountain_pen"],
        "buyable": ["silk_scarf", "art_book", "smartphone", "gaming_console", "dslr_camera"]
    },
    "merchant_linan": {
        "name": "临安",
        "coord": (580, -650),
        "sellable": ["luxury_chocolate", "fountain_pen", "art_book", "silk_scarf"],
        "buyable": ["luxury_chocolate", "fountain_pen", "gaming_console", "smartphone", "noise_headphones"]
    },
    "merchant_haimen": {
        "name": "海门",
        "coord": (720, -480),
        "sellable": ["silk_scarf", "designer_bag", "dslr_camera", "red_wine"],
        "buyable": ["silk_scarf", "designer_bag", "dslr_camera", "smartphone", "gaming_console"] + ALL_FISH
    },
    "merchant_zhoushan": {
        "name": "舟山",
        "coord": (700, -600),
        "sellable": ["jade_bracelet", "red_wine", "dslr_camera", "designer_bag", "wasabi"],
        "buyable": ["jade_bracelet", "red_wine", "dslr_camera", "designer_bag", "gaming_console", "smartphone"] + ALL_FISH
    },

    # ==================== 集群三：南海（4城）====================
    "merchant_liwanzhen": {
        "name": "荔湾镇",
        "coord": (250, -1350),
        "sellable": ["red_wine", "dslr_camera", "designer_bag", "luxury_chocolate", "spice"],
        "buyable": ["red_wine", "dslr_camera", "silk_scarf", "fountain_pen", "art_book"] + ALL_FISH
    },
    "merchant_pengcheng": {
        "name": "鹏城",
        "coord": (350, -1450),
        "sellable": ["red_wine", "dslr_camera", "designer_bag", "noise_headphones"],
        "buyable": ["red_wine", "dslr_camera", "silk_scarf", "art_book", "fountain_pen"] + ALL_FISH
    },
    "merchant_ludao": {
        "name": "鹭岛",
        "coord": (550, -1200),
        "sellable": ["red_wine", "designer_bag", "dslr_camera", "luxury_chocolate"],
        "buyable": ["red_wine", "designer_bag", "silk_scarf", "fountain_pen", "art_book", "sneakers"] + ALL_FISH
    },
    "merchant_qiongya": {
        "name": "琼崖",
        "coord": (200, -1650),
        "sellable": ["red_wine", "luxury_chocolate", "dslr_camera", "lux_perfume"],
        "buyable": ["red_wine", "luxury_chocolate", "silk_scarf", "fountain_pen", "art_book"] + ALL_FISH
    },

    # ==================== 集群四：蜀地（5城）====================
    "merchant_jinguancheng": {
        "name": "锦官城",
        "coord": (-780, -750),
        "sellable": ["yin_grass", "blood_pact", "luxury_chocolate", "art_book", "spice"],
        "buyable": ["yin_grass", "blood_pact", "smartphone", "noise_headphones", "designer_bag"]
    },
    "merchant_dachangshi": {
        "name": "大昌市",
        "coord": (-600, -800),
        "sellable": ["yin_grass", "luxury_chocolate", "concert_ticket", "sneakers", "spice"],
        "buyable": ["yin_grass", "smartphone", "noise_headphones", "designer_bag", "gaming_console", "lux_perfume"]
    },
    "merchant_jiange": {
        "name": "剑阁",
        "coord": (-650, -650),
        "sellable": ["blood_pact", "concert_ticket", "luxury_chocolate", "art_book"],
        "buyable": ["blood_pact", "smartphone", "noise_headphones", "designer_bag"]
    },
    "merchant_yelang": {
        "name": "夜郎",
        "coord": (-900, -950),
        "sellable": ["yin_grass", "blood_pact", "luxury_chocolate"],
        "buyable": ["yin_grass", "blood_pact", "smartphone", "noise_headphones", "designer_bag"]
    },
    "merchant_yunling": {
        "name": "云岭",
        "coord": (-850, -1150),
        "sellable": ["yin_grass", "blood_pact", "luxury_chocolate", "art_book", "gaming_console", "lingzhi_powder"],
        "buyable": ["yin_grass", "blood_pact", "luxury_chocolate", "silk_scarf", "fountain_pen"]
    },

    # ==================== 集群五：关中（4城）====================
    "merchant_changan": {
        "name": "长安",
        "coord": (-500, -280),
        "sellable": ["concert_ticket", "art_book", "fountain_pen", "luxury_chocolate"],
        "buyable": ["concert_ticket", "gold_watch", "jade_bracelet", "red_wine", "designer_bag"]
    },
    "merchant_shendu": {
        "name": "神都",
        "coord": (-350, -320),
        "sellable": ["art_book", "fountain_pen", "concert_ticket", "luxury_chocolate"],
        "buyable": ["art_book", "gold_watch", "jade_bracelet", "red_wine"]
    },
    "merchant_chencang": {
        "name": "陈仓",
        "coord": (-650, -350),
        "sellable": ["concert_ticket", "fountain_pen", "art_book"],
        "buyable": ["concert_ticket", "gold_watch", "jade_bracelet", "red_wine", "designer_bag"]
    },
    "merchant_jincheng": {
        "name": "金城",
        "coord": (-900, -180),
        "sellable": ["jade_bracelet", "concert_ticket", "art_book", "fountain_pen"],
        "buyable": ["jade_bracelet", "smartphone", "gaming_console", "sneakers", "noise_headphones"]
    },

    # ==================== 集群六：中原（4城）====================
    "merchant_bianliang": {
        "name": "汴梁",
        "coord": (-100, -450),
        "sellable": ["sneakers", "smartphone", "noise_headphones", "gaming_console", "concert_ticket"],
        "buyable": ["sneakers", "smartphone", "lux_perfume", "jade_bracelet", "designer_bag"]
    },
    "merchant_yingchuan": {
        "name": "颍川",
        "coord": (-200, -380),
        "sellable": ["sneakers", "smartphone", "gaming_console", "fountain_pen"],
        "buyable": ["sneakers", "smartphone", "lux_perfume", "jade_bracelet"]
    },
    "merchant_jiangxia": {
        "name": "江夏",
        "coord": (-30, -680),
        "sellable": ["smartphone", "gaming_console", "noise_headphones", "sneakers", "dslr_camera"],
        "buyable": ["smartphone", "gaming_console", "lux_perfume", "jade_bracelet", "silk_scarf"]
    },
    "merchant_tanzhou": {
        "name": "潭州",
        "coord": (-80, -900),
        "sellable": ["sneakers", "noise_headphones", "gaming_console", "luxury_chocolate"],
        "buyable": ["sneakers", "noise_headphones", "lux_perfume", "jade_bracelet", "silk_scarf"]
    },

    # ==================== 集群七：北境（4城）====================
    "merchant_liaoyang": {
        "name": "辽阳",
        "coord": (350, 650),
        "sellable": ["blood_pact", "yin_grass", "concert_ticket", "noise_headphones"],
        "buyable": ["blood_pact", "yin_grass", "luxury_chocolate", "red_wine", "silk_scarf"]
    },
    "merchant_longcheng": {
        "name": "龙城",
        "coord": (280, 900),
        "sellable": ["blood_pact", "yin_grass", "concert_ticket", "art_book"],
        "buyable": ["blood_pact", "yin_grass", "luxury_chocolate", "red_wine", "silk_scarf", "designer_bag"]
    },
    "merchant_fengxuezhen": {
        "name": "风雪镇",
        "coord": (150, 1200),
        "sellable": ["blood_pact", "yin_grass", "concert_ticket", "art_book", "lingzhi_powder"],
        "buyable": ["blood_pact", "yin_grass", "concert_ticket", "jade_bracelet", "gold_watch"]
    },
    "merchant_bingyuanbao": {
        "name": "冰原堡",
        "coord": (200, 1400),
        "sellable": ["blood_pact", "yin_grass", "concert_ticket"],
        "buyable": ["blood_pact", "yin_grass", "luxury_chocolate", "red_wine", "silk_scarf"]
    },

    # ==================== 集群八：西域（4城）====================
    "merchant_yumen": {
        "name": "玉门",
        "coord": (-1200, 100),
        "sellable": ["jade_bracelet", "lux_perfume", "concert_ticket", "art_book"],
        "buyable": ["jade_bracelet", "lux_perfume", "smartphone", "gaming_console", "sneakers"]
    },
    "merchant_loulan": {
        "name": "楼兰",
        "coord": (-1400, 250),
        "sellable": ["jade_bracelet", "lux_perfume", "gold_watch"],
        "buyable": ["jade_bracelet", "lux_perfume", "smartphone", "gaming_console", "sneakers", "noise_headphones"]
    },
    "merchant_qiuci": {
        "name": "龟兹",
        "coord": (-1550, 300),
        "sellable": ["lux_perfume", "jade_bracelet", "luxury_chocolate"],
        "buyable": ["lux_perfume", "jade_bracelet", "smartphone", "gaming_console", "sneakers"]
    },
    "merchant_luntai": {
        "name": "轮台",
        "coord": (-1700, 350),
        "sellable": ["lux_perfume", "jade_bracelet", "concert_ticket"],
        "buyable": ["lux_perfume", "jade_bracelet", "smartphone", "gaming_console", "sneakers", "noise_headphones"]
    },
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
MARKET_BY_NAME: Dict[str, MarketConfig] = {m.name: m for m in MARKETS}

# ================= 集群配置 =================
CITY_CLUSTERS: Dict[str, List[str]] = {
    "京畿": ["上京", "郸城", "摩配镇", "天海卫", "石关"],
    "江南": ["金陵", "姑苏", "临安", "海门", "舟山"],
    "南海": ["荔湾镇", "鹏城", "鹭岛", "琼崖"],
    "蜀地": ["锦官城", "大昌市", "剑阁", "夜郎", "云岭"],
    "关中": ["长安", "神都", "陈仓", "金城"],
    "中原": ["汴梁", "颍川", "江夏", "潭州"],
    "北境": ["辽阳", "龙城", "风雪镇", "冰原堡"],
    "西域": ["玉门", "楼兰", "龟兹", "轮台"],
}

# ================= 集群与地理定价 =================
# 城市 → 集群
CITY_TO_CLUSTER: Dict[str, str] = {
    "上京": "京畿", "郸城": "京畿", "摩配镇": "京畿", "天海卫": "京畿", "石关": "京畿",
    "金陵": "江南", "姑苏": "江南", "临安": "江南", "海门": "江南", "舟山": "江南",
    "荔湾镇": "南海", "鹏城": "南海", "鹭岛": "南海", "琼崖": "南海",
    "锦官城": "蜀地", "大昌市": "蜀地", "剑阁": "蜀地", "夜郎": "蜀地", "云岭": "蜀地",
    "长安": "关中", "神都": "关中", "陈仓": "关中", "金城": "关中",
    "汴梁": "中原", "颍川": "中原", "江夏": "中原", "潭州": "中原",
    "辽阳": "北境", "龙城": "北境", "风雪镇": "北境", "冰原堡": "北境",
    "玉门": "西域", "楼兰": "西域", "龟兹": "西域", "轮台": "西域",
}

# 集群邻接关系（BFS 用）
CLUSTER_NEIGHBORS: Dict[str, List[str]] = {
    "京畿": ["中原", "江南", "关中", "北境"],
    "江南": ["京畿", "中原", "南海"],
    "南海": ["江南", "蜀地", "中原"],
    "蜀地": ["关中", "中原", "南海"],
    "关中": ["京畿", "蜀地", "中原", "西域"],
    "中原": ["京畿", "江南", "蜀地", "关中", "南海"],
    "北境": ["京畿"],
    "西域": ["关中"],
}

# 商品 → 产地集群（该集群生产此商品，价格最低）
ITEM_HOME_CLUSTER: Dict[str, str] = {
    "gold_watch": "京畿", "jade_bracelet": "京畿", "lux_perfume": "京畿", "designer_bag": "京畿",
    "silk_scarf": "江南", "art_book": "江南", "fountain_pen": "江南", "luxury_chocolate": "江南",
    "red_wine": "南海", "dslr_camera": "南海",
    "yin_grass": "蜀地", "blood_pact": "蜀地",
    "concert_ticket": "关中",
    "smartphone": "中原", "gaming_console": "中原", "noise_headphones": "中原", "sneakers": "中原",
}

# 集群距离 → 收购价加成（卖出时远离产地越远，价格越高）
DISTANCE_BUY_BONUS = {0: 1.00, 1: 1.08, 2: 1.18, 3: 1.30}


def _cluster_distance(a: str, b: str) -> int:
    """BFS 计算两个集群间最短距离（0~4）"""
    if not a or not b or a == b:
        return 0
    visited = {a}
    queue = [(a, 0)]
    while queue:
        cur, d = queue.pop(0)
        for nb in CLUSTER_NEIGHBORS.get(cur, []):
            if nb == b:
                return d + 1
            if nb not in visited:
                visited.add(nb)
                queue.append((nb, d + 1))
    return 4  # 不连通（理论上不会发生）


def _geo_modifiers(market_name: str, item_id: str) -> Tuple[float, float]:
    """返回 (sell_modifier, buy_modifier) 地理定价修正
    sell_modifier: 市集卖给玩家时的价格修正（<1 = 产地便宜）
    buy_modifier: 市集从玩家收购时的价格修正（>1 = 远离产地加价）
    """
    item_home = ITEM_HOME_CLUSTER.get(item_id)
    market_cluster = CITY_TO_CLUSTER.get(market_name)
    if not item_home or not market_cluster:
        return 1.0, 1.0
    dist = _cluster_distance(item_home, market_cluster)
    # 产地折扣：在产地集群购买更便宜
    sell_mod = 0.85 if dist == 0 else 1.0 + dist * 0.03  # 0.85 / 1.03 / 1.06 / 1.09
    # 收购加成：远离产地时市集愿意出更高价
    buy_mod = DISTANCE_BUY_BONUS.get(min(dist, 3), 1.60)
    return sell_mod, buy_mod


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
def _current_seed_day() -> date:
    """返回当前价格所属日期（0点日切）。"""
    return datetime.now().date()



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
    # 分时补货
    await market_state.check_restock(session)

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

    # 收购价基础比率
    buy_price_ratio = rng_local.uniform(0.72, 0.82)  # 72%-82%

    # -------- 地理定价修正（集群特产/距离加成）--------
    sell_mod, buy_mod = _geo_modifiers(market.name, item_id)
    sell_price = max(1, int(sell_price * sell_mod))
    buy_price = max(1, int(sell_price * buy_price_ratio * buy_mod))

    return sell_price, buy_price


# ------------------- 阶梯加价系统 -------------------
TIERED_PRICE_BRACKETS = [
    (30,     1.00),   # 1-30: 原价
    (80,     1.12),   # 31-80: 1.12x
    (150,    1.28),   # 81-150: 1.28x
    (999999, 1.48),   # 150+: 1.48x
]


def _calculate_tiered_multiplier(already_bought: int, qty: int) -> float:
    """按档位拆分购买量，加权平均计算阶梯加价倍率

    Args:
        already_bought: 今日已购买数量
        qty: 本次购买数量

    Returns:
        float: 加权平均价格倍率
    """
    if qty <= 0:
        return 1.0

    total_cost_weight = 0.0
    remaining = qty
    current_pos = int(already_bought)

    for bracket_end, multiplier in TIERED_PRICE_BRACKETS:
        if remaining <= 0:
            break
        # 当前档位可容纳的数量
        available_in_bracket = max(0, bracket_end - current_pos)
        if available_in_bracket <= 0:
            continue
        # 本档位实际使用的数量
        use = min(remaining, available_in_bracket)
        total_cost_weight += use * multiplier
        remaining -= use
        current_pos += use

    return total_cost_weight / qty


# ------------------- 跑商多元奖励系统 -------------------
# 多种小额奖励并存，看起来丰富但总额可控（最高约18%，日常约6-8%）

async def _calculate_trade_bonuses(
    session, player_id: str, market: MarketConfig, item_id: str, total_gain: int
) -> list[tuple[str, float, int]]:
    """计算跑商交易的各项奖励

    Returns:
        list of (奖励名称, 奖励比例, 奖励金额)
    """
    bonuses = []

    market_cluster = CITY_TO_CLUSTER.get(market.name)
    item_home = ITEM_HOME_CLUSTER.get(item_id)
    dist = _cluster_distance(item_home, market_cluster) if item_home and market_cluster else 0

    # 1. 跨域贸易 —— 在非产地集群出售即可获得
    if dist > 0:
        rate = 0.03
        bonuses.append(("🌍跨域贸易", rate, int(total_gain * rate)))

    # 2. 远途补贴 —— 距离越远补贴越高
    if dist >= 2:
        rate = 0.02 if dist == 2 else 0.04  # 中途2% / 远途4%
        bonuses.append(("🚀远途补贴", rate, int(total_gain * rate)))

    # 3. 稀缺供应 —— 目标市场该商品库存紧张时触发
    ms = await MarketState.get_or_create(session, market.id, item_id)
    stock_ratio = ms.current_stock / max(1, ms.max_stock)
    if stock_ratio < 0.3:
        rate = 0.02
        bonuses.append(("📦稀缺供应", rate, int(total_gain * rate)))

    # 4. 首单加成 —— 当日首笔跨市场交易
    daily_sell_count = await TradeRecord.get_daily_cross_market_sell_count(session, player_id)
    if daily_sell_count == 0:
        rate = 0.05
        bonuses.append(("⭐首单加成", rate, int(total_gain * rate)))

    # 5. 行情红利 —— 市场需求旺盛时出售
    if ms.demand_factor > 1.2:
        rate = 0.02
        bonuses.append(("📈行情红利", rate, int(total_gain * rate)))

    # 6. 连续跑商 —— 连续多天进行跑商活动
    streak = await TradeRecord.get_trade_streak_days(session, player_id)
    if streak > 0:
        rate = min(0.01 * streak, 0.03)  # 每天+1%，最高3%
        bonuses.append((f"🔥连续跑商({streak}天)", rate, int(total_gain * rate)))

    return bonuses


# ------------------- 跑商税（累进制）-------------------
# 档位与选档逻辑提取至 formulas/trade_tax.py（便于单元测试）
from ..formulas.trade_tax import TRADE_TAX_BRACKETS, pick_trade_tax_rate


async def _calculate_trade_tax(session, player_id: str, revenue: int,
                               daily_revenue_override: int | None = None) -> tuple[float, int]:
    """根据当日累计跑商收入计算本笔交易的税额

    Args:
        session: 数据库会话
        player_id: 玩家ID
        revenue: 本次交易收入
        daily_revenue_override: 预查询的当日累计收入（用于批量出售场景，
            避免 flush 后重查导致税率虚高）

    Returns:
        (适用税率, 税额)
    """
    if daily_revenue_override is not None:
        daily_revenue = daily_revenue_override
    else:
        daily_revenue = await TradeRecord.get_daily_cross_market_revenue(session, player_id)

    # 根据累计日收入确定税率档位
    tax_rate = pick_trade_tax_rate(daily_revenue)

    tax_amount = int(revenue * tax_rate)
    return tax_rate, tax_amount


# 系统商店基础物品（价格 = 基础价 × SHOP_BASE_MULT × 财富指数）
SHOP_ITEMS = [
    "revive_potion", "president_letter", "territory_expansion_scroll", "heal_potion", "spirit_herb",
]

# 食材铺：基础调料（烹饪系统，与黑市分开）
SEASONING_SHOP_ITEMS = [
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
    """返回当日日期字符串，形如 'YYYY-MM-DD'（0点日切）。"""
    return _current_seed_day().isoformat()


def _black_market_day_start_dt() -> _dt:
    """返回今日起始时间点(datetime)，用于统计每日限购（0点日切）。"""
    return _dt.combine(_current_seed_day(), _time(hour=0))


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


# 缉邪司总部坐标
HEADQUARTERS_COORD = (150, 1200)  # 风雪镇

# 缉邪司总部商品配置（物品ID: 积分价格）
HEADQUARTERS_ITEMS = {
    "upgrade_stone_low": 300,        # 初级升阶石
    "upgrade_stone_mid": 2000,       # 中级升阶石
    "upgrade_stone_high": 6000,      # 高级升阶石
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
