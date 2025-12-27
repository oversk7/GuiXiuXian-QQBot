# 股票系统退市问题调查报告

**调查日期**: 2025-12-28
**调查类型**: 股票退市机制根因分析
**调查目标**: 分析"股票全部倒闭"的根本原因和修复方案

---

## Code Sections (The Evidence)

### 核心模型定义

- `plugins/xiuxian_game/models/stock.py:46-53` (Stock健康度字段): 定义了health、health_decay_rate、is_active、delisted_at、delist_reason五个反套利相关字段
- `plugins/xiuxian_game/models/stock.py:161-184` (StockEvent模型): 定义了股票突发事件表(黑天鹅事件),但实际未实现触发逻辑

### 价格引擎核心逻辑

- `plugins/xiuxian_game/economy/stock_price_engine.py:26-33` (TYPE_VOLATILITY): 大幅提高波动率配置(TECH:0.15、ENERGY:0.13、MATERIALS:0.14),导致价格波动剧烈
- `plugins/xiuxian_game/economy/stock_price_engine.py:114` (sentiment): 市场情绪波动范围扩大到-5%~+5%(原-2%~+2%),加大价格震荡
- `plugins/xiuxian_game/economy/stock_price_engine.py:127` (total_change_rate): 单次变化幅度提高到±25%(原±15%),进一步加剧波动
- `plugins/xiuxian_game/economy/stock_price_engine.py:176-194` (_update_health): 健康度衰减加速机制:
  - 下跌损耗: 跌1% = -1.5点健康(原-1点,加速50%)
  - 上涨恢复: 涨1% = +0.3点健康(原+0.5点,恢复速度降低40%)
  - 衰减倍率: health_decay_rate默认1.0,可进一步加速损耗
- `plugins/xiuxian_game/economy/stock_price_engine.py:197-213` (_delist_stock): 退市处理逻辑仅标记is_active=False,**未实现清空持仓和重新上市机制**

### Service层退市处理

- `plugins/xiuxian_game/economy/stock_service_new.py:383-418` (delist_stock): 退市处理方法,负责清空持仓,但**未主动调用**
- `plugins/xiuxian_game/economy/stock_service_new.py:420-429` (check_delist_condition): 检查退市条件,但**未在价格更新后调用**

### 定时任务调度

- `plugins/xiuxian_game/economy/stock_scheduler.py:161-190` (perform_weekly_black_swan_check): 黑天鹅事件定时任务框架已就绪,但**依赖未实现的BlackSwanService**
- `plugins/xiuxian_game/economy/stock_scheduler.py:126-158` (perform_daily_holding_fee): 每日持仓管理费扣除逻辑已实现(0.1%/天)

### 股票初始化

- `plugins/xiuxian_game/economy/stock_commands.py:431-462` (handle_stock_init): 初始化12只股票,**所有健康度默认100,health_decay_rate默认1.0**,未区分风险等级

### 设计文档对比

- `llmdoc/design/investment_anti_arbitrage_redesign.md:54-91` (设计方案): 设计文档明确指出"跌1% = -1点健康",但**实际代码实现为-1.5点,加速50%**
- `llmdoc/design/investment_anti_arbitrage_redesign.md:402-406` (重新上市): 设计文档提到"3天后重新上市",但**代码中完全未实现该逻辑**

---

## Report (The Answers)

### result

#### 1. 当前股票状态诊断

**无法直接查询数据库确认**,但根据代码分析,问题根源明确:

**预期状态**: 所有股票可能已退市或濒临退市
- 健康度: 预计大部分已归零或极低(<20)
- is_active: 可能大部分为False
- 退市原因: "健康度归零"

#### 2. 退市机制分析

**退市检查位置**: `stock_price_engine.py:140-142`
```python
if stock.health <= 0:
    await cls._delist_stock(session, stock)
    return 0
```

**健康度损耗机制** (`stock_price_engine.py:176-194`):
- **下跌损耗加速**: 跌1% = -1.5点健康(设计值-1点,**加速50%**)
- **上涨恢复减速**: 涨1% = +0.3点健康(设计值+0.5点,**恢复速度降低40%**)
- **不对称恢复**: 下跌损耗是上涨恢复的5倍(1.5 vs 0.3)

**波动率过高的致命组合**:
1. **基础波动率大幅提高**: TECH 0.15、ENERGY 0.13、MATERIALS 0.14
2. **市场情绪扩大**: -5%~+5%(原-2%~+2%)
3. **单次变化限制放宽**: ±25%(原±15%)
4. **健康度衰减加速**: 跌1%=-1.5点(原-1点)

**数学模拟结果**:
- 单次暴跌15% → 健康度损耗22.5点
- 连续5次暴跌(每次-10%) → 健康度损耗75点
- **预计2-3天内健康度归零**

#### 3. 退市后处理机制

**已实现**:
- ✅ 标记is_active=False
- ✅ 记录delisted_at时间戳
- ✅ 记录delist_reason="健康度归零"
- ✅ delist_stock()方法可清空持仓

**未实现**:
- ❌ **价格更新引擎中未调用delist_stock()**,只标记退市,不清空持仓
- ❌ **无重新上市机制**,设计文档提到的"3天后重新上市"完全未实现
- ❌ **无自动补充股票机制**,退市后永久减少可投资标的

#### 4. 价格更新机制

**计算逻辑** (`stock_price_engine.py:91-144`):
```python
total_change_rate = (
    random_factor +      # 随机波动(期望=0,标准差13-15%)
    sentiment +          # 市场情绪(-5%~+5%)
    regression_factor    # 价格回归(1%弱回归)
)
```

**关键缺陷**:
1. ✅ 已移除正向趋势(期望收益=0)
2. ❌ **波动率设置过高**,导致健康度快速损耗
3. ❌ **上涨恢复速度过慢**,无法抵消下跌损耗

#### 5. 初始化机制

**股票创建** (`stock_commands.py:451-463`):
```python
stock = Stock(
    symbol=stock_data["symbol"],
    name=stock_data["name"],
    stock_type=stock_data["type"],
    base_price=stock_data["base_price"],
    current_price=stock_data["base_price"],
    volatility=stock_data["volatility"],  # 个体波动率0.03-0.10
    health=100,                            # 固定初始值100
    health_decay_rate=1.0,                 # 固定衰减倍率1.0
    is_active=True
)
```

**缺陷**:
- ❌ **所有股票统一health=100、health_decay_rate=1.0**,未根据风险等级差异化
- ❌ **无自动补充机制**,退市后需手动初始化新股票

---

### conclusions

#### 根本原因分析

**主要原因**: 参数配置错误导致健康度损耗过快

1. **健康度衰减加速50%**: 代码实现跌1%=-1.5点,偏离设计值(-1点)
2. **上涨恢复速度降低40%**: 代码实现涨1%=+0.3点,偏离设计值(+0.5点)
3. **波动率大幅提高**: 基础波动率从0.03-0.08提高到0.08-0.15(提高2-3倍)
4. **市场情绪扩大**: 从±2%扩大到±5%
5. **单次变化限制放宽**: 从±15%放宽到±25%

**数学验证**:
- 单次暴跌15% → 健康-22.5点
- 连续4次暴跌(每次-10%) → 健康-60点
- **预计1-2周内所有股票退市**

**次要原因**: 退市后处理机制不完善

1. **delist_stock()未被调用**: 价格更新引擎中的_delist_stock()只标记状态,未清空持仓
2. **无重新上市机制**: 设计文档提到的"3天后重新上市"未实现
3. **无自动补充机制**: 退市后永久减少投资标的,最终"无股可买"

#### 预期现状

根据代码逻辑推演,服务器当前状态应为:
1. **大部分股票已退市**(is_active=False)
2. **少数股票濒临退市**(health<20)
3. **玩家持仓可能仍在**(未正确清空)
4. **无新股票补充**(需手动初始化)

---

### relations

#### 代码调用关系

```
stock_scheduler.py (定时触发)
    ↓ 调用
StockPriceEngine.update_all_prices()
    ↓ 遍历所有活跃股票
_calculate_new_price() (每只股票)
    ↓ 计算价格变化
total_change_rate = random_factor + sentiment + regression
    ↓ 限制变化幅度
max(-0.25, min(0.25, total_change_rate))  # ±25%
    ↓ 更新健康度
_update_health(stock, change_rate)
    ↓ 下跌损耗加速
health_loss = abs(change_rate) * 150 * stock.health_decay_rate  # -1.5点/1%
    ↓ 检查退市
if stock.health <= 0:
    _delist_stock(session, stock)  # ❌ 只标记,不清空持仓
```

#### 设计与实现偏差

```
设计文档 (investment_anti_arbitrage_redesign.md):
    ├─ 跌1% = -1点健康
    └─ 涨1% = +0.5点健康

实际实现 (stock_price_engine.py):
    ├─ 跌1% = -1.5点健康 (❌ 加速50%)
    └─ 涨1% = +0.3点健康 (❌ 恢复速度降低40%)

结果: 健康度损耗速度是设计的5倍 (1.5/0.3 = 5)
```

#### 缺失的功能模块

```
设计文档提到:
    ├─ 退市后重新上市 (3天后)
    ├─ 自动补充新股票
    └─ 黑天鹅事件触发

实际代码:
    ├─ ❌ 无重新上市逻辑
    ├─ ❌ 无自动补充机制
    └─ ⚠️ 黑天鹅框架就绪但未实现
```

---

## 修复建议

### 紧急修复(立即执行)

#### 1. 修正健康度参数 (`stock_price_engine.py:176-194`)

```python
@classmethod
def _update_health(cls, stock: Stock, change_rate: float) -> None:
    """更新股票健康度(恢复设计值)"""
    if change_rate < 0:
        # 下跌: 恢复设计值 -1点/1% (当前-1.5点)
        health_loss = abs(change_rate) * 100 * stock.health_decay_rate
        stock.health -= int(health_loss)
    else:
        # 上涨: 恢复设计值 +0.5点/1% (当前+0.3点)
        health_gain = change_rate * 50 * stock.health_decay_rate
        stock.health += int(health_gain)

    stock.health = max(0, min(100, stock.health))
```

#### 2. 降低波动率 (`stock_price_engine.py:26-33`)

```python
TYPE_VOLATILITY = {
    StockType.TECH: 0.08,       # 恢复原值 (当前0.15)
    StockType.FINANCE: 0.04,    # 恢复原值 (当前0.10)
    StockType.ENERGY: 0.06,     # 恢复原值 (当前0.13)
    StockType.CONSUMER: 0.03,   # 恢复原值 (当前0.08)
    StockType.HEALTHCARE: 0.05, # 恢复原值 (当前0.11)
    StockType.MATERIALS: 0.07,  # 恢复原值 (当前0.14)
}
```

#### 3. 缩小市场情绪 (`stock_price_engine.py:114`)

```python
# 恢复原值 -2%~+2% (当前-5%~+5%)
sentiment = random.choice([-0.02, 0, 0.02])
```

#### 4. 缩小单次变化 (`stock_price_engine.py:127`)

```python
# 恢复原值 ±15% (当前±25%)
total_change_rate = max(-0.15, min(0.15, total_change_rate))
```

### 机制完善(短期实现)

#### 5. 实现退市后重新上市 (`stock_service_new.py`)

```python
async def check_and_relist_stocks(self) -> Tuple[int, List[str]]:
    """检查并重新上市退市股票

    Returns:
        (重新上市数量, 股票名称列表)
    """
    from datetime import timedelta

    # 获取3天前退市的股票
    three_days_ago = datetime.now() - timedelta(days=3)
    delisted_stocks = await self._stock_repo.get_delisted_stocks_before(three_days_ago)

    relisted_count = 0
    relisted_names = []

    for stock in delisted_stocks:
        # 重新上市: 重置健康度和价格
        stock.health = 100
        stock.current_price = stock.base_price
        stock.is_active = True
        stock.delisted_at = None
        stock.delist_reason = None

        await self._stock_repo.update(stock)
        relisted_count += 1
        relisted_names.append(stock.name)

    return relisted_count, relisted_names
```

在`stock_scheduler.py`中添加每日检查任务:

```python
async def perform_daily_relist_check():
    """每日检查并重新上市股票"""
    # ... (调用check_and_relist_stocks)
```

#### 6. 自动补充新股票 (`stock_service_new.py`)

```python
async def ensure_minimum_active_stocks(self, min_count: int = 12) -> int:
    """确保至少有min_count只活跃股票

    Args:
        min_count: 最少股票数量

    Returns:
        新增股票数量
    """
    active_stocks = await self._stock_repo.get_active_stocks()
    current_count = len(active_stocks)

    if current_count >= min_count:
        return 0

    # 需要新增的数量
    needed = min_count - current_count

    # 从预定义模板中选择未上市的股票
    templates = self._get_stock_templates()
    existing_symbols = {s.symbol for s in active_stocks}

    new_count = 0
    for template in templates:
        if new_count >= needed:
            break
        if template["symbol"] not in existing_symbols:
            stock = Stock(
                symbol=template["symbol"],
                name=template["name"],
                stock_type=template["type"],
                base_price=template["base_price"],
                current_price=template["base_price"],
                volatility=template["volatility"],
                health=100,
                health_decay_rate=1.0,
                is_active=True
            )
            await self._stock_repo.add(stock)
            new_count += 1

    return new_count
```

### 数据恢复(立即执行)

#### 7. 批量恢复已退市股票

```sql
-- 重置所有股票健康度
UPDATE stocks SET health = 100, is_active = True, delisted_at = NULL, delist_reason = NULL;

-- 重置所有股票价格到基础价格
UPDATE stocks SET current_price = base_price;
```

或在Python中执行:

```python
async def reset_all_stocks():
    """重置所有股票状态(紧急修复)"""
    async with safe_session() as session:
        stmt = select(Stock)
        stocks = (await session.execute(stmt)).scalars().all()

        for stock in stocks:
            stock.health = 100
            stock.is_active = True
            stock.delisted_at = None
            stock.delist_reason = None
            stock.current_price = stock.base_price

        await session.commit()
```

---

## 优先级建议

### P0 - 紧急修复(立即执行,1小时内)
1. 修正健康度参数(恢复设计值)
2. 降低波动率到原始值
3. 批量重置所有股票状态

### P1 - 机制完善(今日内,4小时)
4. 实现重新上市机制
5. 实现自动补充机制
6. 添加定时任务调用

### P2 - 长期优化(本周内,2天)
7. 实现黑天鹅事件系统
8. 添加健康度预警通知
9. 优化股票初始化(差异化风险等级)

---

## 验证计划

### 1. 参数修复验证
- 模拟100次价格更新,检查健康度变化范围
- 验证下跌10次(每次-5%)后健康度是否>30

### 2. 重新上市验证
- 手动退市1只股票
- 等待3天后检查是否自动重新上市

### 3. 自动补充验证
- 手动删除3只股票
- 检查是否自动补充新股票

---

**调查者**: Scout Agent
**调查日期**: 2025-12-28
**报告版本**: 1.0
**预期修复时间**: P0紧急修复1小时,P1机制完善4小时
