# 经济系统架构

## 1. 身份标识

- **定义**: 经济系统包含货币管理、价格计算、交易撮合和税收控制四大核心模块
- **目的**: 实现游戏内经济的稳定运行、资源公平分配和通胀自动调控

## 2. 核心组件

- `plugins/xiuxian_game/economy/market.py` (MarketOrder, calculate_transaction_tax, _get_wealth_scale): 交易市场核心逻辑,包括订单挂牌、自动撮合、阶梯税收、财富指数计算
- `plugins/xiuxian_game/economy/merchants.py` (MarketConfig, _price_for, MARKETS): 跑商系统实现,包含13个市集配置、动态定价、供需因子更新
- `plugins/xiuxian_game/economy/stock_service_new.py` (StockService): 气运投资系统,实现股票交易、价格波动、手续费计算
- `plugins/xiuxian_game/economy/equipment_trade_service_new.py` (EquipmentTradeService): 装备交易专用服务,处理装备估价、冻结、转移
- `plugins/xiuxian_game/models/market_order.py` (MarketOrder, OrderSide): 市场订单数据模型,支持买单/卖单、装备实例交易
- `plugins/xiuxian_game/models/market_state.py` (MarketState): 市场状态模型,存储库存、供需因子、价格倍率
- `plugins/xiuxian_game/models/trade_record.py` (TradeRecord, TradeType): 跑商交易记录模型,追踪玩家买卖历史
- `plugins/xiuxian_game/infrastructure/repositories/market_order_repository.py` (MarketOrderRepository): 市场订单仓储层,提供数据访问抽象

## 3. 执行流程 (LLM检索地图)

### 3.1 玩家间交易流程

- **1. 订单创建**: `plugins/xiuxian_game/economy/market.py:222-345` - 玩家使用【挂牌】命令创建买单或卖单,系统检查挂牌数量限制(最多6个)
- **2. 底价计算**: `plugins/xiuxian_game/economy/market.py:146-217` - 根据物品基础价格、类型倍率、稀有度倍率和财富指数计算底价,自动吸附过低价格
- **3. 资源冻结**: `plugins/xiuxian_game/economy/market.py:299-316` - 卖单冻结物品或装备,买单冻结相应金币
- **4. 自动撮合**: `plugins/xiuxian_game/economy/market.py:886-995` - 系统查找对手方订单,按价格优先、时间优先撮合,执行物品/装备转移
- **5. 税收计算**: `plugins/xiuxian_game/economy/market.py:57-75` - 根据交易金额应用阶梯税率(0-20%),直接销毁税收金币
- **6. 订单更新**: `plugins/xiuxian_game/economy/market.py:966-983` - 更新剩余数量,完全成交后删除订单

### 3.2 跑商系统流程

- **1. 市场选择**: `plugins/xiuxian_game/economy/merchants.py:340-368` - 玩家到达指定坐标,使用【市集】命令查看商品价格和库存
- **2. 价格计算**: `plugins/xiuxian_game/economy/merchants.py:275-318` - 基于日期+市场+商品的哈希随机数生成基础价格,叠加供需因子得到最终售价
- **3. 购买商品**: `plugins/xiuxian_game/economy/merchants.py:400-502` - 检查库存和携带上限(500件),扣除金币,记录交易,更新需求因子
- **4. 跨市场交易**: `plugins/xiuxian_game/economy/merchants.py:580-695` - 前往其他市集出售商品,检查4小时同地点限制,获得5%跨市场奖励
- **5. 出售商品**: `plugins/xiuxian_game/economy/merchants.py:620-695` - 检查交易限制,按当前市价收购,更新供给因子,记录交易
- **6. 每日刷新**: `plugins/xiuxian_game/models/market_state.py:82-102` - 每天09:00重置供需因子向1.0回归,恢复库存,记录日交易量

### 3.3 财富指数调控流程

- **1. 财富统计**: `plugins/xiuxian_game/economy/market.py:113-142` - 计算全服前100名玩家的金币中位数
- **2. 指数计算**: `plugins/xiuxian_game/economy/market.py:135-139` - 使用公式 scale = 1.0 + (median_wealth / 5_000_000_000)^0.3 * 0.3
- **3. 平滑处理**: `plugins/xiuxian_game/economy/market.py:139` - 应用EMA平滑: current_scale = prev_scale * 0.85 + new_scale * 0.15
- **4. 限制范围**: `plugins/xiuxian_game/economy/market.py:137` - 夹持在1.0-3.0倍之间
- **5. 底价联动**: `plugins/xiuxian_game/economy/market.py:158-159` - 物品底价 = 基础价 × 类型倍率 × 稀有度倍率 × 财富指数

## 4. 设计原理

**财富指数联动机制**: 通过动态调整物品底价响应全服财富水平。当高玩财富增长时,自动提升物价避免通胀;当财富下降时,保持底价稳定防止通缩。指数使用0.3次方函数降低敏感度,避免土豪玩家过度影响全服经济。

**阶梯税收设计**: 采用累进税率(免税→5%→10%→15%→20%),小额交易鼓励新手,大额交易重税抑制通胀。税收直接销毁而非转移,实现真正的货币回收。

**供需因子系统**: 每个市集的每个商品有独立的需求因子(0.6-1.6)和供给因子(0.6-1.6)。玩家购买推高需求因子→价格上涨,出售推高供给因子→价格下跌。每日20%回归正常,保持价格动态平衡。

**时间窗口防刷**: 4小时同地点限制强制玩家跨市场交易,8小时挂牌限制防止通过挂牌给小号转移商品。结合交易记录全追踪,有效遏制刷钱行为。

**装备交易特殊性**: 装备使用实例交易模式,挂牌时冻结(extra_attrs["_frozen_for_trade"]=True),防止同时装备/强化/销毁。成交后转移所有权,保留所有属性(升阶、宝石、耐久)。
