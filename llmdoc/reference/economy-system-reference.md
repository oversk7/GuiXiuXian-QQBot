# 经济系统配置参考

## 1. 核心摘要

经济系统的关键配置参数分布在市场交易、跑商系统、财富调控和税收控制四个模块。核心参数包括财富指数基线(50亿)、阶梯税率门槛(5k-100k)、13个市集配置、经济倍率(材料0.7/宝石2.0/装备4.0)、交易限制(4小时同地点/8小时挂牌/最多6单)、供需因子范围(0.6-1.6)等。所有参数直接在代码中定义,可通过修改常量快速调整经济平衡。

## 2. 真实来源

### 2.1 市场交易配置
- **主文件**: `plugins/xiuxian_game/economy/market.py` - 交易市场核心逻辑,包含挂牌、撮合、税收、财富指数
- **关键参数**:
  - `MAX_LISTINGS = 6` (Line 25): 每位玩家最大挂牌数
  - `PRICE_FLOOR_ALPHA = 0.6` (Line 77): 参考价折扣系数,底价 = 参考价 × alpha
  - `MIN_UNIT_PRICE = 10` (Line 78): 系统绝对最小单价下限
  - `PRICE_CAP_MULT = 8` (Line 79): 建议价倍数上限,防止恶意拉高价格
  - `TRADE_REF_LOOKBACK_DAYS = 7` (Line 82): 成交价采样窗口(最近7天)
  - `TRADE_REF_MIN_SAMPLES = 5` (Line 83): 最小成交样本数
  - `ECONOMY_MULT_BY_TYPE` (Line 86-93): 类型倍率,如MATERIAL=0.7, GEM=2.0, EQUIPMENT=4.0
  - `ECONOMY_MULT_BY_RARITY` (Line 94-100): 稀有度倍率,white=1.0, orange=1.3
  - `WEALTH_TOP_N = 100` (Line 103): 财富统计样本数(前100名)
  - `WEALTH_BASELINE = 5_000_000_000` (Line 104): 财富基线(50亿)
  - `WEALTH_GAMMA = 0.3` (Line 105): 财富增长指数(0.3次方)
  - `WEALTH_SMIN = 1.0` (Line 106): 财富指数下限
  - `WEALTH_SMAX = 3.0` (Line 107): 财富指数上限
  - `WEALTH_EMA_ALPHA = 0.15` (Line 108): EMA平滑系数
  - `EQUIPMENT_FLOOR_MULT = 6.0` (Line 144): 装备底价放大倍数
  - `TAX_BRACKETS = [5000, 20000, 50000, 100000]` (Line 419-428): 阶梯税收门槛
  - `TAX_RATES = [0, 0.05, 0.10, 0.15, 0.20]` (Line 419-428): 阶梯税率

### 2.2 跑商系统配置
- **主文件**: `plugins/xiuxian_game/economy/merchants.py` - 跑商系统,13个市集、动态定价、交易限制
- **关键参数**:
  - `MARKET_CONFIGS` (Line 88-192): 13个市集配置,包含坐标、可售商品、可收商品
  - `LIMITED_GOODS` (Line 65-69): 受携带限制的商品(500件上限,不包含血契丹、阴冥草、鱼类)
  - `ALL_FISH` (Line 71-83): 所有鱼类列表(20种,白色到橙色品质)
  - `_DEF_TIME = time(hour=9)` (Line 262): 每日刷新时间(09:00)
  - 同地点交易限制: 4小时(Line 633)
  - 携带上限: 500件(Line 458)
  - 跨市场奖励: 5%(Line 667)
  - 收购价利润率: 75-85%(Line 316),即利润率15-25%
  - 价格波动范围: ±30%(Line 301)
  - 供需因子范围: 0.5-2.0倍(Line 304-311)
  - 库存恢复: 每日50个或补满(Line 91)
  - 供需因子回归: 每日20%(Line 95-96)

### 2.3 数据模型定义
- **MarketOrder**: `plugins/xiuxian_game/models/market_order.py` - 市场订单模型
  - `id`: 订单ID(主键)
  - `player_id`: 玩家ID(外键)
  - `side`: 订单类型(BUY/SELL枚举)
  - `item_id`: 物品ID
  - `price`: 单价
  - `quantity`: 数量
  - `is_instance_trade`: 是否装备实例交易
  - `item_instance_id`: 装备实例ID(装备交易专用)
  - `equipment_summary`: 装备摘要(显示用)

- **MarketState**: `plugins/xiuxian_game/models/market_state.py` - 市场状态模型
  - `current_stock`: 当前库存(500-1000随机)
  - `max_stock`: 最大库存
  - `daily_sold/daily_bought`: 今日交易量
  - `demand_factor`: 需求因子(0.6-1.6)
  - `supply_factor`: 供给因子(0.6-1.6)
  - `last_refresh_date`: 上次刷新日期

- **TradeRecord**: `plugins/xiuxian_game/models/trade_record.py` - 交易记录模型
  - `player_id`: 玩家ID
  - `trade_type`: 交易类型(BUY/SELL枚举)
  - `market_id`: 市场ID
  - `item_id`: 物品ID
  - `quantity`: 数量
  - `unit_price`: 单价
  - `total_amount`: 总额
  - `trade_time`: 交易时间

### 2.4 银行与投资系统
- **银行转账**: `plugins/xiuxian_game/economy/bank.py`
  - 转账手续费: 3%(Line 568)
  - 不可透支: 余额检查
  - 记录转账日志

- **气运投资**: `plugins/xiuxian_game/economy/stock_service.py`
  - 手续费: 3%(Line 617), 最低30金币,最高30000金币
  - 持仓管理费: 每日持仓价值的0.1%(Line 624)
  - 价格保护: 基础价格的0.2-3.0倍(Line 610)
  - 波动率: TECH=8%, FINANCE=4%, ENERGY=6%, CONSUMER=3%, HEALTHCARE=5%, MATERIALS=7%

### 2.5 黑市与缉邪司总部
- **黑市配置**: `plugins/xiuxian_game/economy/merchants.py`
  - `BLACK_MARKET_OVERPRICE = 10` (Line 1122): 黑市溢价倍数(10倍价格)
  - `BLACK_MARKET_MIN_ITEMS = 3`, `MAX_ITEMS = 6` (Line 1123-1124): 每日上架数量
  - `BLACK_MARKET_STOCK_MIN = 10`, `MAX = 20` (Line 1125-1126): 库存范围
  - `BLACK_MARKET_DAILY_LIMIT_PER_PLAYER = 50` (Line 1127): 每人每日限购(不含基础物品)
  - `BLACK_MARKET_CANDIDATES` (Line 1130-1132): 黑市候选池(升阶石、稳定水晶等)

- **缉邪司总部**: `plugins/xiuxian_game/economy/merchants.py`
  - `HEADQUARTERS_COORD = (-5, 390)` (Line 1282): 风雪镇坐标
  - `HEADQUARTERS_ITEMS` (Line 1285-1298): 积分兑换物品配置
    - 初级升阶石: 300积分
    - 中级升阶石: 2000积分
    - 稳定水晶: 10000积分
    - 抗暴符文1-5级: 600-9600积分

### 2.6 打工系统
- **频率限制**: `plugins/xiuxian_game/utils.py`
  - 每小时最多10次(Line 640)
  - 每次间隔1分钟(Line 641)
  - 奖励范围: 80-180金币

### 2.7 送礼系统
- **限制条件**: `plugins/xiuxian_game/social/gift_service_new.py`
  - 关系限制: 仅配偶、师徒
  - 每日限额: 10次
  - 单次限额: 100件或10000金币价值

### 2.8 相关架构文档
- `/llmdoc/architecture/economy-system-architecture.md` - 经济系统整体架构
- `/llmdoc/architecture/market-trading-architecture.md` - 市场交易详细架构

### 2.9 外部文档
- SQLAlchemy ORM: https://docs.sqlalchemy.org/en/14/orm/ - 数据模型定义和查询
- Python Decimal: https://docs.python.org/3/library/decimal.html - 金币精确计算建议

## 3. 关键计算公式

### 3.1 财富指数计算
```python
# plugins/xiuxian_game/economy/market.py:135-139
median_wealth = top_100_players_gold.median()  # 前100名金币中位数
ratio = median_wealth / 5_000_000_000  # 与50亿基线比较
raw_scale = 1.0 + ratio^0.3 * 0.3  # 0.3次方降低敏感度
scale = clamp(raw_scale, 1.0, 3.0)  # 限制在1.0-3.0倍
scale = EMA平滑: prev_scale * 0.85 + raw_scale * 0.15  # 降低波动
```

### 3.2 物品底价计算
```python
# plugins/xiuxian_game/economy/market.py:158-159
base_price = item_config.price
type_mult = ECONOMY_MULT_BY_TYPE[item_type]  # MATERIAL=0.7, GEM=2.0...
rarity_mult = ECONOMY_MULT_BY_RARITY[rarity]  # white=1.0, orange=1.3...
wealth_scale = _get_wealth_scale(session)  # 1.0-3.0动态指数
floor_price = base_price * type_mult * rarity_mult * wealth_scale
```

### 3.3 跑商价格计算
```python
# plugins/xiuxian_game/economy/merchants.py:298-318
seed = f"{market_id}:{item_id}:{date}"
rng = Random(hash_md5(seed))
random_factor = rng.uniform(0.7, 1.3)  # ±30%随机波动
supply_demand_factor = market_state.get_price_multiplier()  # 0.5-2.0
sell_price = base_price * random_factor * supply_demand_factor
sell_price = clamp(sell_price, base_price * 0.5, base_price * 2.0)  # 限制倍率
buy_price = sell_price * rng.uniform(0.75, 0.85)  # 利润率15-25%
```

### 3.4 阶梯税收计算
```python
# plugins/xiuxian_game/economy/market.py:419-428
if amount <= 5000: tax = 0
elif amount <= 20000: tax = amount * 0.05
elif amount <= 50000: tax = amount * 0.10
elif amount <= 100000: tax = amount * 0.15
else: tax = amount * 0.20
```

### 3.5 供需因子更新
```python
# plugins/xiuxian_game/models/market_state.py:114-120
# 购买操作
demand_factor = min(1.6, demand_factor + quantity * 0.01)
if current_stock < max_stock * 0.3:
    supply_factor = max(0.6, supply_factor - quantity * 0.008)

# plugins/xiuxian_game/models/market_state.py:135-150
# 出售操作
demand_factor = max(0.6, demand_factor - quantity * 0.008)
if current_stock > max_stock * 0.7:
    supply_factor = min(1.6, supply_factor + effective_qty * 0.005)

# 每日回归
demand_factor = demand_factor * 0.8 + 1.0 * 0.2  # 20%回归正常
```

## 4. 常用SQL查询示例

```sql
-- 查看全服金币总量和分布
SELECT
    COUNT(*) as player_count,
    SUM(gold) as total_gold,
    AVG(gold) as avg_gold,
    MAX(gold) as max_gold,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY gold) as median_gold
FROM player;

-- 查看前100名玩家财富(用于财富指数计算)
SELECT gold FROM player ORDER BY gold DESC LIMIT 100;

-- 查看市场订单统计
SELECT
    side,
    COUNT(*) as order_count,
    SUM(quantity) as total_quantity,
    AVG(price) as avg_price
FROM market_orders
GROUP BY side;

-- 查看跑商交易记录统计
SELECT
    market_id,
    trade_type,
    COUNT(*) as trade_count,
    SUM(quantity) as total_quantity,
    SUM(total_amount) as total_amount
FROM trade_record
WHERE trade_time >= NOW() - INTERVAL '7 days'
GROUP BY market_id, trade_type;

-- 查看市场状态和供需因子
SELECT
    m.name as market_name,
    i.name as item_name,
    ms.demand_factor,
    ms.supply_factor,
    ms.current_stock,
    ms.max_stock,
    ms.daily_sold,
    ms.daily_bought
FROM market_state ms
JOIN markets m ON ms.market_id = m.id
JOIN item_config i ON ms.item_id = i.item_id
WHERE ms.demand_factor > 1.3 OR ms.supply_factor < 0.7;
```
