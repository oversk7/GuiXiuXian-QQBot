# 诡修仙投资系统重设计方案

**设计日期**: 2025-12-02
**设计者**: designer 代理 (Lead System Architect)
**基于数据**: 1,736 玩家样本 + 投资系统代码分析
**文档类型**: 系统设计方案

---

## 执行概要

基于tr:scout代理的投资系统调查报告,当前投资系统面临三大核心问题:

1. **股票投资完全失败**: 期望收益0% + 6%手续费 = 理性玩家绝不参与
2. **银行存款过于简单**: 10万以内年化876%,但缺乏娱乐性
3. **经济活动效率失衡**: 打工(1500-7000金币/小时) >> 银行存款(100金币/小时) >> 股票投资(-6%)

**破局策略**: 不是简单修数值,而是**重新定义投资系统在游戏循环中的角色**:
- 从"鸡肋功能"转向"策略决策中心"
- 从"被动挂机"转向"主动参与+被动收益"
- 从"孤立系统"转向"经济循环枢纽"

---

## 1. 系统关联映射 (System Linkage Map)

### 1.1 当前经济循环的断裂

```
资源来源 (Sources)              效率评级          新手可达性
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
打工              →  1500-7000金币/小时    ✅ 立即可用
银行存款          →  100金币/小时(10万)    ✅ 立即可用
股票投资          →  -6%(必亏)             ✅ 立即可用(但无人用)
修炼              →  经验(不产出金币)      ✅ 立即可用
诡域探索          →  经验+材料             ⚠️ 需导航知识
跑商              →  差价利润(变动)        ❌ 需市场知识

资源消耗 (Sinks)              消耗量级          匹配度
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
装备购买/升阶     →  材料+金币             ❌ 材料获取困难
药品购买          →  100金币(过低)         ❌ 价格错配
扫荡令            →  100,000金币           ⚠️ 仅土豪可达
突破失败          →  损失30%经验           ⚠️ 挫败感强
公会建筑          →  集体投资              ⚠️ 需加入公会
```

**核心问题诊断**:
- **Source过剩**: 打工系统创造大量金币,但Sink不足
- **投资无意义**: 银行存款只是"放着",股票投资是"送钱"
- **新手陷阱**: 最高效的资源来源(打工)与成长路径(修炼)无关

### 1.2 投资系统在游戏循环中的错位

```
        当前设计 (失败)                      理想设计 (目标)
        ━━━━━━━━━━━━                        ━━━━━━━━━━━━
           打工挣钱                             打工挣钱
              ↓                                    ↓
           买药刷副本                         投资决策中心
              ↓                            ┌─────┴─────┐
           快速升级                    银行存款      股票投资
              ↓                      (稳定低收益)  (高风险高收益)
           投资系统?                        ↓             ↓
           (完全不用)                   被动增值      短期暴富/亏损
                                              ↓
                                          购买增益道具
                                          (扫荡令/丹药)
                                              ↓
                                          加速成长循环
```

**设计缺陷**:
1. **投资与成长脱节**: 投资收益(金币)无法转化为成长加速
2. **时间维度错位**: QQ群游戏是碎片化交互,但投资需要持续关注
3. **风险-收益失配**: 股票高风险却无高收益,银行低风险却收益过高

### 1.3 系统耦合关系图 (重设计)

```
┌─────────────────────────────────────────────────────────┐
│                   核心游戏循环                            │
│                                                           │
│  修炼/探索 → 升级 → 解锁功能 → 获取资源 → 消耗资源 → ...  │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
        ┌────────────────┐
        │  经济系统枢纽   │ ◀──── 设计目标: 成为连接器
        └────┬───────┬───┘
             │       │
     ┌───────┘       └───────┐
     ▼                       ▼
┌─────────┐           ┌─────────┐
│ 打工系统 │           │ 跑商系统 │
│(主动赚钱)│           │(策略赚钱)│
└────┬────┘           └────┬────┘
     │                     │
     └─────────┬───────────┘
               ▼
      ┌────────────────┐
      │  投资决策中心   │ ◀──── 重设计焦点
      │ • 银行存款      │
      │ • 股票投资      │
      │ • 基金投资(新)  │
      └────┬───────────┘
           │
           ▼
      ┌────────────────┐
      │ 增益道具商店    │ ◀──── 新增: 投资收益专用商店
      │ • 扫荡令折扣    │
      │ • 经验加速丹    │
      │ • VIP时长       │
      └────────────────┘
```

**关键设计**:
- **投资不再孤立**: 成为"资源积累"与"成长加速"的桥梁
- **引入新Sink**: 增益道具商店专门消耗投资收益
- **策略选择**: 玩家需在"短期消费"与"长期投资"间权衡

---

## 2. 平台/UX审查 (QQ Bot Specifics)

### 2.1 投资系统的交互约束

| 约束类型 | 具体表现 | 对投资玩法的影响 |
|---------|---------|-----------------|
| **Request-Response** | 每次指令需等待回复 | 不能设计需要高频盯盘的股票玩法 |
| **群聊刷屏** | 多人同时游戏时消息混杂 | 股票波动通知会刷屏,需改为私聊推送 |
| **无状态保持** | 每次指令独立 | 不能设计"连续操作"的复杂交易 |
| **碎片化时间** | 玩家每次上线5-10分钟 | 投资决策必须在1分钟内完成 |
| **文字阅读疲劳** | 超过5行难以快速解析 | 投资面板必须极简 |

### 2.2 当前UX问题诊断

#### 问题1: 股票系统信息密度过载

**当前输出** (`stock_commands.py:handle_stock_list`):
```
气运行情 (12种股票,每种4行信息)
━━━━━━━━━━━━━
法宝气运 (TECH)
代码: FA001
当前价格: 1,234金币
波动率: 8%
...
(共48行输出)
```

**问题**:
- 48行输出在群聊中瞬间被刷走
- 新手不理解"法宝气运"是什么
- 无法快速判断哪个值得买

**优化后** (分层展示):
```
第1层 - 快速概览 (5行)
━━━━━━━━━━━━━
📈 气运行情 (输入代码查看详情)
🔥 FA001 法宝 ¥1,234 ↑3.2%
💰 FI001 金融 ¥856  ↓1.5%
⚡ EN001 灵气 ¥1,050 ↑0.8%
💡 使用【气运详情 FA001】查看完整信息

第2层 - 详情查询 (用户主动触发)
━━━━━━━━━━━━━
🔥 FA001 - 法宝气运
━━━━━━━━━━━━━
📊 当前价格: 1,234金币
📈 今日涨幅: +3.2% (↑39金币)
📉 波动率: 8% (高风险)
💼 持仓上限: 1,000,000份
━━━━━━━━━━━━━
💡 投资 FA001 100
```

#### 问题2: 投资决策无辅助

**当前状态**:
- 玩家看到12种股票,无从下手
- 无"推荐"机制
- 无"风险评级"
- 无"历史收益"可视化

**改进方案**: 新增"投资顾问"功能
```
【投资建议】
━━━━━━━━━━━━━
基于你的资产 (10,000金币):

🟢 稳健型 (推荐)
• 银行存款 8,000金币 → 预期月收益 +584金币
• 消费股 2,000金币 → 预期月收益 +60~+200金币
• 风险: 极低 | 流动性: 高

🟡 平衡型
• 银行存款 5,000金币
• 金融股 3,000金币
• 科技股 2,000金币
• 风险: 中 | 预期月收益 +200~+800金币

🔴 激进型 (不推荐新手)
• 全部投资科技股 10,000金币
• 风险: 极高 | 可能亏损 -2,000金币或盈利 +3,000金币

💡 输入【执行方案 稳健】自动分配
```

#### 问题3: 银行存款无娱乐性

**当前状态**:
- 存钱 → 忘记 → 一个月后取出 → 发现多了几千金币
- 没有任何互动,纯被动挂机

**改进方案**: 引入"存款任务"
```
🏦 冥界银行 - 特殊存款计划
━━━━━━━━━━━━━
💎 7日定期 (锁定期7天)
• 存入: 10,000金币
• 到期收益: +1,200金币 (12%)
• 提前取出: 无利息

🎁 成长账户 (升级触发)
• 存入: 5,000金币
• 每次升级: 额外奖励 +500金币
• 随时取出: 保留已触发的奖励

🎲 幸运存款 (概率翻倍)
• 存入: 1,000金币
• 7日后开奖: 50%几率翻倍, 50%几率仅本金
• 期望收益: +500金币 (50%)
```

### 2.3 文字密度分析

| 功能 | 当前输出行数 | 适宜行数 | 优化方向 |
|-----|------------|---------|---------|
| 气运行情 | 48行 | 5行 | 仅显示涨跌幅TOP3,详情按需查询 |
| 持仓查询 | 10-20行 | 5行 | 折叠详情,仅显示总市值和盈亏 |
| 银行余额 | 4行 | 3行 | 合并利息信息 |
| 投资建议 | 0行(未实现) | 8-10行 | 新增功能 |

---

## 3. 数值平衡设计 (Numerical Balance)

### 3.1 当前收益率对比 (问题暴露)

| 经济活动 | 时间投入 | 金币收益/小时 | 风险 | 娱乐性 |
|---------|---------|--------------|------|-------|
| **打工** | 20-30分钟/小时 | 1,500-7,000 | 无 | ⚠️ 低(重复) |
| **银行存款** | 0(被动) | 100(10万本金) | 无 | ❌ 无 |
| **股票投资** | 5-10分钟/次 | -6%(手续费) | 高 | ❌ 无意义 |
| **跑商** | 15-30分钟/次 | 变动(500-2000) | 中 | ✅ 高(策略) |

**核心矛盾**:
- 打工效率是银行存款的**15-70倍**
- 股票投资期望收益为**负数**
- 最无聊的活动(打工)反而最高效

### 3.2 重设计目标

```
设计哲学: "时间投入 vs 收益 vs 娱乐性" 的平衡

        收益/时间
           ↑
      7000|           打工(改后)
           |              ●
      5000|                       跑商
           |                         ●
      3000|
           |              股票投资(改后)
      1000|                 ●
           |        银行存款(改后)
       100|           ●
           |___________________________→ 娱乐性
            低        中        高      极高
```

**目标收益率** (基于10,000金币本金):

| 投资方式 | 预期日收益 | 预期月收益 | 年化收益率 | 风险评级 | 时间投入 |
|---------|-----------|-----------|-----------|---------|---------|
| **银行存款** | +50 | +1,500 | 18% | 无风险 | 0 |
| **稳健型股票** | +30~+100 | +900~+3,000 | 10.8%~36% | 低 | 5分钟/周 |
| **平衡型股票** | -50~+200 | -1,500~+6,000 | -18%~72% | 中 | 10分钟/周 |
| **激进型股票** | -200~+500 | -6,000~+15,000 | -72%~180% | 高 | 15分钟/周 |
| **打工** | +300~+1,000 | +9,000~+30,000 | 108%~360% | 无 | 30分钟/日 |

**关键平衡点**:
- 银行存款: 从年化876% → 18% (削弱48倍,但仍是"保本"选择)
- 股票投资: 从必亏 → 期望收益10%-72% (根据风险分级)
- 打工: 保持高收益,但引入"疲劳度"限制每日次数

### 3.3 银行存款机制重设计

#### 方案: 阶梯利率大幅降低 + 特殊存款计划

**新阶梯利率** (`bank.py:14-18`):
```python
_TIERS = [
    (100_000, 0.000021),   # 10w 以内 0.0021%/小时 → 年化18%
    (500_000, 0.000010),   # 10w-50w 0.001%/小时 → 年化9%
    (1_000_000, 0.000005), # 50w-100w 0.0005%/小时 → 年化4.5%
    (float("inf"), 0.0)    # 100w 以上无利息
]
```

**数学推导**:
```
目标: 10万本金, 年化收益18%
年化18% = (1 + 每小时利率)^8760 - 1
每小时利率 = (1.18)^(1/8760) - 1 ≈ 0.0000189 ≈ 0.00002 (简化为0.0021%)

验证:
10万 × 0.0021% × 24小时 = 50.4金币/天
50.4 × 30 = 1,512金币/月
1,512 × 12 = 18,144金币/年 (约18%)
```

**特殊存款计划** (新增):

```python
# 新增数据模型
class SpecialDeposit(Base):
    __tablename__ = "special_deposits"

    id: int
    player_id: str
    deposit_type: str  # "fixed_7d", "growth", "lucky"
    amount: int
    start_date: datetime
    end_date: datetime
    status: str  # "active", "matured", "withdrawn"
    bonus_earned: int = 0

# 定期存款
FIXED_DEPOSIT_7D = {
    "name": "7日定期",
    "duration_days": 7,
    "bonus_rate": 0.12,  # 12%固定收益
    "min_amount": 1000,
    "early_withdraw_penalty": 1.0,  # 提前取出无利息
}

# 成长账户
GROWTH_ACCOUNT = {
    "name": "成长账户",
    "bonus_per_level": 500,  # 每升1级奖励500金币
    "max_bonus": 10000,      # 最多奖励10,000金币
    "min_amount": 5000,
}

# 幸运存款
LUCKY_DEPOSIT = {
    "name": "幸运存款",
    "duration_days": 7,
    "double_probability": 0.5,  # 50%几率翻倍
    "min_amount": 1000,
    "max_amount": 50000,
}
```

**娱乐性提升**:
- 7日定期: 玩家需"忍住"不取钱,培养储蓄习惯
- 成长账户: 将存款与核心玩法(升级)绑定
- 幸运存款: 引入博彩元素,但期望收益仍为正(50% × 2 = 1.0,保本)

### 3.4 股票投资机制重设计

#### 核心问题回顾

**当前股票价格引擎** (`stock_price_engine.py:91-134`):
```python
# 价格变化公式
total_change_rate = (
    random_factor +           # 正态分布,期望值=0
    trend_influence +         # 接近0
    sentiment_influence +     # 随机,期望值=0
    regression_factor         # 负反馈,拉回基础价格
)
```

**问题分析**:
1. **随机游走 + 回归因子 = 长期期望收益为0**
2. **6%手续费 = 玩家必亏6%**
3. **无"成长性"股票**: 所有股票围绕基础价格波动,没有真正"上涨"的股票

#### 方案: 引入"趋势型股票" + 降低手续费

**重设计价格引擎**:

```python
# 股票分类
STOCK_CATEGORIES = {
    "stable": {
        "name": "稳健型",
        "trend_bias": 0.001,     # 日均涨幅0.1%
        "volatility": 0.02,      # 波动率2%
        "regression_strength": 0.5,  # 强回归,不偏离基础价格太远
        "examples": ["消费股", "金融股"],
    },
    "growth": {
        "name": "成长型",
        "trend_bias": 0.003,     # 日均涨幅0.3%
        "volatility": 0.05,      # 波动率5%
        "regression_strength": 0.2,  # 弱回归,允许长期上涨
        "examples": ["科技股", "灵气股"],
    },
    "speculative": {
        "name": "投机型",
        "trend_bias": 0.0,       # 无趋势
        "volatility": 0.10,      # 波动率10%
        "regression_strength": 0.3,  # 中回归
        "examples": ["材料股"],
    },
}

# 新价格计算公式
async def _calculate_new_price(cls, session, stock: Stock, market_sentiment: float):
    # 1. 获取股票类别配置
    category = STOCK_CATEGORIES[stock.category]

    # 2. 趋势偏移 (允许长期上涨)
    trend_bias = category["trend_bias"]

    # 3. 随机波动
    random_factor = random.gauss(0, category["volatility"])

    # 4. 弱化回归因子 (允许偏离基础价格)
    regression_strength = category["regression_strength"]
    price_deviation = (stock.current_price - stock.base_price) / stock.base_price
    regression_factor = -price_deviation * 0.02 * regression_strength  # 降低回归力度

    # 5. 市场情绪
    sentiment_influence = (market_sentiment - 1.0)

    # 6. 综合变化率
    total_change_rate = (
        trend_bias +              # 新增: 正向趋势偏移
        random_factor +
        sentiment_influence +
        regression_factor         # 削弱: 回归力度降低
    )

    # 7. 限制单次变化 (±15%,降低极端波动)
    total_change_rate = max(-0.15, min(0.15, total_change_rate))

    # 8. 计算新价格
    new_price = int(stock.current_price * (1 + total_change_rate))

    # 9. 价格下限: 基础价格的50% (提高下限,降低风险)
    min_price = max(1, int(stock.base_price * 0.5))
    new_price = max(min_price, new_price)

    return new_price
```

**关键改进**:
1. **引入正向趋势**: "成长型"股票日均涨幅0.3%,月涨9%,年涨100%+
2. **弱化回归**: 允许股票长期偏离基础价格(如3年后涨到基础价格的3倍)
3. **降低极端波动**: 单次变化从±20% → ±15%
4. **提高价格下限**: 从20% → 50%,降低玩家亏损风险

**手续费调整** (`stock_service_new.py:37`):
```python
# 当前
COMMISSION_RATE = 0.03  # 3%

# 优化后
COMMISSION_RATE = 0.005  # 0.5% (降低6倍)
MIN_COMMISSION = 1
MAX_COMMISSION = 10000   # 降低上限
```

**收益率模拟** (基于10,000金币投资):

| 股票类型 | 月度期望收益 | 标准差 | 最好情况 | 最坏情况 | 手续费成本 |
|---------|------------|-------|---------|---------|----------|
| **稳健型** | +2.5% (+250) | ±3% | +5.5% (+550) | -0.5% (-50) | -1% (-100) |
| **成长型** | +8.5% (+850) | ±10% | +18.5% (+1,850) | -1.5% (-150) | -1% (-100) |
| **投机型** | +0% (±0) | ±20% | +20% (+2,000) | -20% (-2,000) | -1% (-100) |

**净收益率**:
- 稳健型: 月均+1.5% (扣除手续费后)
- 成长型: 月均+7.5% (扣除手续费后)
- 投机型: 月均-1% (期望亏损,但有博大小可能)

### 3.5 打工系统平衡调整

**问题**: 打工效率过高(1500-7000金币/小时),导致投资无意义

**方案**: 引入"每日疲劳度"

```python
# 新增字段 (models/player.py)
class Player(Base):
    daily_work_count: int = 0      # 今日打工次数
    last_work_reset: date = None   # 上次重置日期

# 疲劳度系统
MAX_DAILY_WORK = 10  # 每日最多打工10次
FATIGUE_PENALTY = {
    0:  1.0,   # 前3次: 100%收益
    3:  1.0,
    4:  0.8,   # 第4-6次: 80%收益
    5:  0.8,
    6:  0.8,
    7:  0.5,   # 第7-10次: 50%收益
    8:  0.5,
    9:  0.5,
    10: 0.5,
}

# 打工收益调整
async def complete_job(player: Player, job_type: str):
    # 检查疲劳度
    if player.daily_work_count >= MAX_DAILY_WORK:
        return "⚠️ 今日打工次数已达上限,请明日再来"

    # 计算基础收益
    base_reward = JOB_TYPES[job_type]["base_reward"]

    # 应用疲劳惩罚
    fatigue_multiplier = FATIGUE_PENALTY.get(player.daily_work_count, 0.5)
    final_reward = int(base_reward * fatigue_multiplier)

    player.daily_work_count += 1
    player.gold += final_reward

    return f"💰 获得 {final_reward} 金币 (今日第{player.daily_work_count}次打工)"
```

**效果**:
- 前3次打工: 100%收益 (鼓励每日活跃)
- 第4-6次: 80%收益 (允许多劳多得)
- 第7-10次: 50%收益 (递减,但仍可打工)
- 第11次起: 禁止 (硬上限)

**日收益对比**:
```
旧机制: 无限打工 → 10次/日 × 150金币 = 1,500金币/日
新机制: (3×1.0 + 3×0.8 + 4×0.5) × 150 = 1,125金币/日 (降低25%)
```

---

## 4. 娱乐性保障 (Fun Factor)

### 4.1 投资系统的娱乐性诊断

**当前状态**:
- ❌ **银行存款**: 无娱乐性,纯挂机
- ❌ **股票投资**: 无娱乐性,必亏钱
- ✅ **打工系统**: 有特殊事件,但重复性高

**设计原则**:
1. **策略深度**: 玩家需做决策,而非无脑操作
2. **即时反馈**: 投资后能看到可视化收益
3. **社交互动**: 投资结果可分享到群聊
4. **惊喜感**: 随机事件打破枯燥

### 4.2 娱乐性提升方案

#### 方案1: 股票"涨停/跌停"事件

```python
# 每日随机触发1-2只股票暴涨/暴跌
DAILY_STOCK_EVENTS = [
    {
        "name": "诡域大发现",
        "description": "XX诡域发现稀有材料矿脉",
        "affected_stock": "材料股",
        "price_change": +0.30,  # 单日暴涨30%
        "probability": 0.05,    # 5%几率
    },
    {
        "name": "灵异潮汐",
        "description": "灵气浓度骤降,能源需求暴增",
        "affected_stock": "灵气股",
        "price_change": +0.25,
        "probability": 0.03,
    },
    {
        "name": "经济危机",
        "description": "冥界银行收紧贷款,金融股大跌",
        "affected_stock": "金融股",
        "price_change": -0.20,
        "probability": 0.03,
    },
]

# 全服公告
"""
📢 气运市场快讯
━━━━━━━━━━━━━
🎉 诡域大发现!
XX诡域发现稀有材料矿脉,材料气运暴涨!

📊 EN002 材料股 ¥1,234 → ¥1,604 (↑30%)

💡 使用【投资气运 EN002 100】参与
"""
```

#### 方案2: "投资排行榜"与社交炫耀

```python
# 新增排行榜
investment_rank_cmd = on_command("投资榜", aliases={"富豪榜"})

@investment_rank_cmd.handle()
async def handle_investment_rank(event: MessageEvent):
    """显示投资收益最高的玩家"""
    # 计算所有玩家的 (银行存款 + 股票市值 - 初始投入)
    # 按净收益排序

    msg = """
🏆 投资收益排行榜
━━━━━━━━━━━━━
1. 张三[UID:1001]
   总资产: 150,000金币
   净收益: +50,000金币 (50%)

2. 李四[UID:1002]
   总资产: 120,000金币
   净收益: +30,000金币 (33%)

3. 王五[UID:1003]
   总资产: 95,000金币
   净收益: +15,000金币 (18%)

💡 你的排名: 第47位 | 净收益: +2,000金币
    """
```

#### 方案3: "基金投资" (托管式投资)

**问题**: 部分玩家不想研究股票,只想"躺赚"

**方案**: 引入"基金系统"
```python
# 基金类型
FUNDS = {
    "stable_fund": {
        "name": "稳健基金",
        "description": "投资组合: 50%银行存款 + 50%消费股",
        "expected_return": "月均+2%",
        "risk": "极低",
        "management_fee": 0.01,  # 1%管理费/月
    },
    "growth_fund": {
        "name": "成长基金",
        "description": "投资组合: 30%金融股 + 40%科技股 + 30%灵气股",
        "expected_return": "月均+6%",
        "risk": "中",
        "management_fee": 0.02,  # 2%管理费/月
    },
    "aggressive_fund": {
        "name": "激进基金",
        "description": "投资组合: 70%科技股 + 30%材料股",
        "expected_return": "月均+10%",
        "risk": "高",
        "management_fee": 0.03,  # 3%管理费/月
    },
}

# 指令
"""
【购买基金 稳健基金 10000】
━━━━━━━━━━━━━
✅ 成功购买稳健基金
━━━━━━━━━━━━━
投资金额: 10,000金币
预期月收益: +200金币 (2%)
管理费: -10金币/月 (1%)
净收益: +190金币/月

💡 基金每日自动调仓,无需操作
💡 使用【赎回基金】可随时退出
"""
```

**设计优势**:
- 降低学习门槛: 新手不需研究股票
- 分散风险: 基金自动分散投资
- 托管式体验: 适配QQ群碎片化场景

---

## 5. 三个具体改进方案

### 方案A: 保守修复 (P0 紧急, 1周内完成)

**目标**: 最小改动,修复明显的数值失衡

#### A1. 银行利率削减

**修改文件**: `plugins/xiuxian_game/economy/bank.py:14-18`

```python
# 当前
_TIERS = [
    (100_000, 0.001),   # 10w以内 0.1%/小时 → 年化876%
    (500_000, 0.0005),
    (1_000_000, 0.0001),
    (float("inf"), 0.0)
]

# 改为
_TIERS = [
    (100_000, 0.000021),   # 10w以内 → 年化18%
    (500_000, 0.000010),   # 10w-50w → 年化9%
    (1_000_000, 0.000005), # 50w-100w → 年化4.5%
    (float("inf"), 0.0)
]
```

**预期效果**:
- 10万本金: 从876,000金币/年 → 18,000金币/年 (削弱48倍)
- 仍保持"无风险收益",但不再破坏经济平衡

**风险**: 低 (老玩家可能抱怨收益降低,但理由充分: "通货膨胀修正")

#### A2. 股票手续费降低

**修改文件**: `plugins/xiuxian_game/economy/stock_service_new.py:37`

```python
# 当前
COMMISSION_RATE = 0.03  # 3%

# 改为
COMMISSION_RATE = 0.005  # 0.5%
```

**预期效果**:
- 买入+卖出手续费: 从6% → 1%
- 期望收益: 从-6% → -1% (仍略亏,但可接受)

**风险**: 低 (纯数值调整,无逻辑变更)

#### A3. 打工疲劳度

**修改文件**: `plugins/xiuxian_game/economy/part_time_job_service_new.py`

**新增字段**:
```sql
ALTER TABLE players ADD COLUMN daily_work_count INT DEFAULT 0;
ALTER TABLE players ADD COLUMN last_work_reset DATE;
```

**新增逻辑**:
```python
async def start_job(player: Player, job_type: str):
    # 重置检查
    today = date.today()
    if player.last_work_reset != today:
        player.daily_work_count = 0
        player.last_work_reset = today

    # 疲劳检查
    if player.daily_work_count >= 10:
        return "⚠️ 今日打工次数已达上限(10次)"

    # ... 正常打工逻辑
    player.daily_work_count += 1
```

**预期效果**:
- 日收益上限: 从无限 → 约1,125金币/日
- 月收益: 从90,000+ → 33,750金币/月 (降低62%)

**风险**: 中 (玩家可能抱怨限制,但可用"劳动保护法"等世界观解释)

#### A4. 部署清单

```bash
# 1. 数据库迁移
python -m alembic revision --autogenerate -m "add_daily_work_limit"
python -m alembic upgrade head

# 2. 修改配置文件
# 编辑 bank.py, stock_service_new.py, part_time_job_service_new.py

# 3. 发布公告 (提前3天)
"""
📢 经济系统平衡调整公告
━━━━━━━━━━━━━
为应对严重的通货膨胀(最高金币34.4亿),将进行以下调整:

1️⃣ 银行利率调整
• 10万以内: 年化876% → 18%
• 理由: 修正通胀,回归合理水平

2️⃣ 气运投资手续费降低
• 手续费: 3% → 0.5%
• 理由: 鼓励投资,增加玩法多样性

3️⃣ 打工疲劳度系统
• 每日最多打工10次
• 理由: 保护玩家健康,避免肝度过高

📅 生效时间: 2025-12-09
💡 已有存款不受影响,新利息按新利率计算
"""

# 4. 灰度上线 (可选)
# Feature Flag控制, 先对新玩家生效, 观察1周后全量

# 5. 监控指标
# - 日均金币增长
# - 投资参与率
# - 玩家投诉量
```

**实施工作量**: 2人日

---

### 方案B: 渐进优化 (P1 重要, 1个月内完成)

**目标**: 增加新机制,提升投资娱乐性

#### B1. 特殊存款计划

**新增数据模型**: `plugins/xiuxian_game/models/special_deposit.py`

```python
from sqlalchemy import Integer, String, DateTime, Enum as SQLEnum, Float
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from enum import Enum

from .db import Base

class DepositType(str, Enum):
    FIXED_7D = "fixed_7d"        # 7日定期
    GROWTH = "growth"            # 成长账户
    LUCKY = "lucky"              # 幸运存款

class DepositStatus(str, Enum):
    ACTIVE = "active"            # 生效中
    MATURED = "matured"          # 已到期
    WITHDRAWN = "withdrawn"      # 已取出

class SpecialDeposit(Base):
    __tablename__ = "special_deposits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[str] = mapped_column(String(64), index=True)
    deposit_type: Mapped[DepositType] = mapped_column(SQLEnum(DepositType))
    amount: Mapped[int] = mapped_column(Integer)  # 存入金额
    start_date: Mapped[datetime] = mapped_column(DateTime)
    end_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    status: Mapped[DepositStatus] = mapped_column(SQLEnum(DepositStatus), default=DepositStatus.ACTIVE)
    bonus_earned: Mapped[int] = mapped_column(Integer, default=0)  # 已获得奖励
    level_snapshots: Mapped[int] = mapped_column(Integer, default=0)  # 存款时玩家等级(成长账户用)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
```

**新增指令**: `plugins/xiuxian_game/economy/special_deposit_commands.py`

```python
special_deposit_cmd = on_command("特殊存款", aliases={"理财"}, block=True, priority=5)

@special_deposit_cmd.handle()
async def handle_special_deposit(event: MessageEvent):
    """显示特殊存款计划"""
    msg = """
🏦 冥界银行 - 特殊存款计划
━━━━━━━━━━━━━
💎 1. 7日定期存款
• 锁定期: 7天
• 固定收益: 12%
• 最低存款: 1,000金币
• 提前取出: 无利息
• 指令: 定期存款 10000

🎁 2. 成长账户
• 每次升级: 奖励+500金币
• 最高奖励: 10,000金币
• 最低存款: 5,000金币
• 随时取出: 保留已触发奖励
• 指令: 成长存款 5000

🎲 3. 幸运存款
• 锁定期: 7天
• 开奖: 50%几率翻倍
• 最低/最高: 1,000/50,000金币
• 指令: 幸运存款 1000
━━━━━━━━━━━━━
💡 特殊存款与普通存款独立,可同时持有
    """
    await special_deposit_cmd.finish(message_add_head(msg, event))
```

**实施工作量**: 3人日

#### B2. 股票趋势分类

**修改文件**: `plugins/xiuxian_game/economy/stock_price_engine.py`

**新增股票属性**:
```python
# 在 Stock 模型中新增字段
class Stock(Base):
    # ... 现有字段
    category: str = "stable"  # stable/growth/speculative
```

**修改价格计算**:
```python
STOCK_CATEGORIES = {
    "stable": {"trend_bias": 0.001, "volatility": 0.02, "regression": 0.5},
    "growth": {"trend_bias": 0.003, "volatility": 0.05, "regression": 0.2},
    "speculative": {"trend_bias": 0.0, "volatility": 0.10, "regression": 0.3},
}

async def _calculate_new_price(cls, session, stock: Stock, market_sentiment):
    category = STOCK_CATEGORIES[stock.category]

    # 引入趋势偏移
    trend_bias = category["trend_bias"]

    # 其他逻辑...
    total_change_rate = (
        trend_bias +              # 新增
        random_factor +
        sentiment_influence +
        regression_factor * category["regression"]  # 可配置
    )

    # ...
```

**修改初始化脚本**: `plugins/xiuxian_game/economy/stock_commands.py:397-432`

```python
# 更新股票初始化,指定category
stocks = [
    {"symbol": "FA001", "name": "法宝气运", "category": "growth"},  # 成长型
    {"symbol": "FI001", "name": "金融气运", "category": "stable"},  # 稳健型
    {"symbol": "EN001", "name": "灵气气运", "category": "growth"},  # 成长型
    {"symbol": "CO001", "name": "丹药气运", "category": "stable"},  # 稳健型
    {"symbol": "MA001", "name": "材料气运", "category": "speculative"},  # 投机型
    # ...
]
```

**实施工作量**: 2人日

#### B3. 投资顾问功能

**新增指令**: `plugins/xiuxian_game/economy/investment_advisor.py`

```python
advisor_cmd = on_command("投资建议", aliases={"理财顾问"}, block=True, priority=5)

@advisor_cmd.handle()
async def handle_advisor(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            return

        # 获取玩家资产
        bank_acc = await session.get(BankAccount, player.id)
        total_assets = player.gold + (bank_acc.balance if bank_acc else 0)

        # 计算推荐方案
        if total_assets < 5000:
            # 资产过低,不推荐投资
            msg = """
💡 投资建议
━━━━━━━━━━━━━
你的总资产较少(< 5,000金币)
建议先通过打工或诡域探索积累本金

📊 当前资产: {total_assets}金币
🎯 目标资产: 5,000金币
💼 推荐活动: 打工/探索诡域
            """.format(total_assets=total_assets)

        elif total_assets < 50000:
            # 中等资产,推荐稳健型
            deposit_amount = int(total_assets * 0.8)
            stock_amount = int(total_assets * 0.2)
            msg = f"""
💡 投资建议 - 稳健型
━━━━━━━━━━━━━
📊 总资产: {total_assets:,}金币

🟢 推荐方案:
• 银行存款: {deposit_amount:,}金币 (80%)
  预期月收益: +{int(deposit_amount * 0.018)}金币
• 消费股: {stock_amount:,}金币 (20%)
  预期月收益: +{int(stock_amount * 0.015)}~+{int(stock_amount * 0.055)}金币

💰 总预期月收益: +{int(deposit_amount * 0.018 + stock_amount * 0.035)}金币
⚠️ 风险等级: 极低

💡 输入【执行方案 稳健】自动分配
            """

        # ... 更多资产档位

        await advisor_cmd.finish(message_add_head(msg, event))
```

**实施工作量**: 2人日

#### B4. 部署清单

```bash
# 1. 数据库迁移
python -m alembic revision --autogenerate -m "add_special_deposits_and_stock_category"
python -m alembic upgrade head

# 2. 初始化股票分类
python -c "from plugins.xiuxian_game.economy import stock_commands; stock_commands.update_stock_categories()"

# 3. 发布公告
"""
📢 投资系统2.0上线公告
━━━━━━━━━━━━━
🎉 新功能:

1️⃣ 特殊存款计划
• 7日定期: 固定12%收益
• 成长账户: 升级即赚钱
• 幸运存款: 50%几率翻倍

2️⃣ 股票分类系统
• 稳健型: 低风险低收益
• 成长型: 长期上涨趋势
• 投机型: 高风险高收益

3️⃣ AI投资顾问
• 根据你的资产推荐方案
• 一键执行自动分配

💡 使用【特殊存款】【投资建议】体验新功能
"""

# 4. 监控指标
# - 特殊存款参与率
# - 股票交易量变化
# - 投资顾问使用率
```

**实施工作量**: 7人日

---

### 方案C: 系统重构 (P2 长期, 2-3个月内完成)

**目标**: 全面重设计,引入全新玩法

#### C1. 基金系统

**新增数据模型**: `plugins/xiuxian_game/models/fund.py`

```python
class Fund(Base):
    """基金产品"""
    __tablename__ = "funds"

    id: int
    fund_code: str           # 基金代码 (如 F001)
    fund_name: str           # 基金名称
    fund_type: str           # stable/growth/aggressive
    net_value: float         # 净值 (初始1.0)
    total_shares: int        # 总份额
    management_fee: float    # 管理费率 (如 0.01 = 1%)
    portfolio: str           # 投资组合 (JSON格式)

    created_at: datetime
    updated_at: datetime

class FundHolding(Base):
    """玩家基金持仓"""
    __tablename__ = "fund_holdings"

    id: int
    player_id: str
    fund_id: int
    shares: int              # 持有份额
    buy_nav: float           # 买入时净值
    buy_date: datetime

    created_at: datetime
    updated_at: datetime
```

**核心逻辑**: `plugins/xiuxian_game/economy/fund_service.py`

```python
class FundService:
    """基金管理服务"""

    async def buy_fund(self, player_id: str, fund_code: str, amount: int):
        """购买基金"""
        # 1. 获取基金信息
        fund = await self._fund_repo.get_by_code(fund_code)

        # 2. 计算份额
        shares = int(amount / fund.net_value)

        # 3. 扣款
        player.gold -= amount

        # 4. 创建持仓
        holding = FundHolding(
            player_id=player_id,
            fund_id=fund.id,
            shares=shares,
            buy_nav=fund.net_value,
        )

        return f"成功购买 {shares} 份 {fund.fund_name}"

    async def update_fund_nav(self, fund_id: int):
        """更新基金净值 (每日定时任务)"""
        fund = await self._fund_repo.get_by_id(fund_id)

        # 解析投资组合
        portfolio = json.loads(fund.portfolio)
        # 例: {"bank_deposit": 0.5, "FA001": 0.3, "FI001": 0.2}

        # 计算各资产涨跌
        total_value_change = 0
        for asset, weight in portfolio.items():
            if asset == "bank_deposit":
                # 银行存款: 日涨0.05%
                total_value_change += weight * 0.0005
            else:
                # 股票: 查询涨跌幅
                stock = await self._stock_repo.get_by_symbol(asset)
                change_rate = (stock.current_price - stock.base_price) / stock.base_price
                total_value_change += weight * change_rate

        # 更新净值
        fund.net_value *= (1 + total_value_change)
        fund.updated_at = datetime.now()

        return fund.net_value
```

**实施工作量**: 8人日

#### C2. 股票事件系统

**新增数据模型**: `plugins/xiuxian_game/models/stock_event.py`

```python
class StockEvent(Base):
    """股票突发事件"""
    __tablename__ = "stock_events"

    id: int
    event_name: str          # 事件名称
    event_description: str   # 事件描述
    affected_symbol: str     # 影响的股票代码
    price_impact: float      # 价格影响 (如 +0.30 = 涨30%)
    trigger_date: datetime   # 触发日期
    duration_days: int       # 持续天数

    created_at: datetime
```

**事件库**: `plugins/xiuxian_game/economy/stock_events.py`

```python
STOCK_EVENTS = [
    {
        "name": "诡域大发现",
        "description": "XX诡域发现稀有材料矿脉,材料需求暴增",
        "affected_category": "materials",
        "price_impact": 0.30,
        "probability": 0.05,
        "duration_days": 3,
    },
    {
        "name": "灵异潮汐",
        "description": "灵气浓度骤降,能源股价飙升",
        "affected_category": "energy",
        "price_impact": 0.25,
        "probability": 0.03,
        "duration_days": 2,
    },
    {
        "name": "经济危机",
        "description": "冥界银行收紧贷款,金融股暴跌",
        "affected_category": "finance",
        "price_impact": -0.20,
        "probability": 0.03,
        "duration_days": 5,
    },
    # ... 更多事件
]

async def trigger_daily_event():
    """每日随机触发1-2个事件"""
    for event_config in STOCK_EVENTS:
        if random.random() < event_config["probability"]:
            # 选择受影响的股票
            affected_stocks = await get_stocks_by_category(event_config["affected_category"])

            # 创建事件记录
            event = StockEvent(
                event_name=event_config["name"],
                event_description=event_config["description"],
                affected_symbol=random.choice(affected_stocks).symbol,
                price_impact=event_config["price_impact"],
                trigger_date=datetime.now(),
                duration_days=event_config["duration_days"],
            )

            # 发送全服公告
            await broadcast_stock_event(event)
```

**实施工作量**: 5人日

#### C3. 投资排行榜与社交

**新增指令**: `plugins/xiuxian_game/economy/investment_leaderboard.py`

```python
investment_rank_cmd = on_command("投资榜", aliases={"富豪榜", "投资排行"}, block=True, priority=5)

@investment_rank_cmd.handle()
async def handle_investment_rank(event: MessageEvent):
    """显示投资收益排行榜"""
    async with safe_session() as session:
        # 计算所有玩家的总资产
        players = await session.execute(select(Player))

        rankings = []
        for player in players.scalars():
            # 现金
            cash = player.gold

            # 银行存款
            bank_acc = await session.get(BankAccount, player.id)
            bank_balance = bank_acc.balance if bank_acc else 0

            # 股票市值
            holdings = await get_stock_holdings(player.id, session)
            stock_value = sum(h.shares * h.stock.current_price for h in holdings)

            # 基金市值
            fund_holdings = await get_fund_holdings(player.id, session)
            fund_value = sum(h.shares * h.fund.net_value for h in fund_holdings)

            # 总资产
            total_assets = cash + bank_balance + stock_value + fund_value

            # 计算净收益 (需记录初始投入)
            initial_investment = player.total_deposited or 0
            net_profit = total_assets - initial_investment
            net_profit_rate = (net_profit / initial_investment * 100) if initial_investment > 0 else 0

            rankings.append({
                "player": player,
                "total_assets": total_assets,
                "net_profit": net_profit,
                "net_profit_rate": net_profit_rate,
            })

        # 按净收益率排序
        rankings.sort(key=lambda x: x["net_profit_rate"], reverse=True)

        # 生成排行榜
        lines = ["🏆 投资收益排行榜", "━━━━━━━━━━━━━"]
        for i, rank in enumerate(rankings[:10], start=1):
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            p = rank["player"]
            lines.append(
                f"{emoji} {p.nickname}[UID:{p.uid}]\n"
                f"   总资产: {rank['total_assets']:,}💰 | "
                f"收益率: +{rank['net_profit_rate']:.1f}%"
            )

        await investment_rank_cmd.finish("\n".join(lines))
```

**实施工作量**: 3人日

#### C4. 部署清单

```bash
# 1. 数据库迁移 (大量新表)
python -m alembic revision --autogenerate -m "investment_system_v3"
python -m alembic upgrade head

# 2. 初始化基金产品
python -c "from plugins.xiuxian_game.economy import fund_init; fund_init.create_default_funds()"

# 3. 启动定时任务
# - 每日更新基金净值
# - 每日触发股票事件
# - 每日刷新排行榜

# 4. 发布公告
"""
📢 投资系统3.0 - 全面重构
━━━━━━━━━━━━━
🎉 重磅功能:

1️⃣ 基金系统上线
• 稳健/成长/激进三类基金
• 托管式投资,无需操作
• 每日自动调仓

2️⃣ 股票事件系统
• 诡域大发现/灵异潮汐等突发事件
• 单日涨跌幅可达±30%
• 全服公告,抓住投资机会

3️⃣ 投资排行榜
• 展示投资收益率TOP10
• 炫耀你的投资眼光
• 月度投资之王奖励

💡 使用【购买基金】【投资榜】体验新功能
"""

# 5. A/B测试
# - 50%玩家启用基金系统
# - 观察参与率和留存率
# - 1个月后全量上线
```

**实施工作量**: 16人日

---

## 6. 风险评估与监测指标

### 6.1 风险评估矩阵

| 方案 | 玩家影响 | 技术风险 | 回滚难度 | 优先级 |
|-----|---------|---------|---------|-------|
| **A. 保守修复** | 中 (收益降低) | 低 | 低 | P0 |
| **B. 渐进优化** | 低 (新增功能) | 中 | 中 | P1 |
| **C. 系统重构** | 高 (全新玩法) | 高 | 高 | P2 |

### 6.2 方案A风险详情

| 修改项 | 影响玩家群 | 风险等级 | 回滚方案 |
|-------|-----------|---------|---------|
| 银行利率削减 | 所有存款玩家 | 🟡 中 | 修改配置文件,重启服务 |
| 股票手续费降低 | 股票投资者 | 🟢 低 | 修改配置文件,重启服务 |
| 打工疲劳度 | 高频打工玩家 | 🟠 中高 | 删除字段,重启服务 |

**缓解措施**:
- 提前3天发布公告,说明调整原因
- 提供"老玩家补偿礼包"(扫荡令×3)
- 灰度上线: 先对新玩家生效,观察反馈

### 6.3 关键监测指标

#### 经济健康度指标

| 指标 | 当前值 | 目标值 (1个月后) | 监测频率 |
|-----|-------|-----------------|---------|
| **日均金币增长** | 未知 | <10,000金币/人/日 | 每日 |
| **金币基尼系数** | 0.85-0.90(推测) | <0.70 | 每周 |
| **银行总存款** | 未知 | 稳定增长 | 每周 |
| **股票日交易量** | 极低 | >100笔/日 | 每日 |

#### 投资系统参与度指标

| 指标 | 当前值 | 目标值 (1个月后) | 监测频率 |
|-----|-------|-----------------|---------|
| **银行存款玩家占比** | 未知 | >80% | 每周 |
| **股票投资玩家占比** | <5%(推测) | >30% | 每周 |
| **特殊存款参与率** | 0%(未实现) | >20% | 每周 |
| **基金购买玩家占比** | 0%(未实现) | >15% | 每周 |

#### 玩家满意度指标

| 指标 | 监测方式 | 目标 |
|-----|---------|------|
| **投资相关投诉** | 群聊关键词监控 | <10条/周 |
| **投资帮助指令使用率** | 日志统计 | >50次/日 |
| **投资顾问使用率** | 日志统计 | >100次/周 |

### 6.4 数据采集方案

**新增埋点**: `plugins/xiuxian_game/analytics/investment_analytics.py`

```python
class InvestmentAnalytics:
    @staticmethod
    async def track_deposit(player_id: str, amount: int, deposit_type: str):
        """追踪存款行为"""
        await log_event("deposit", {
            "player_id": player_id,
            "amount": amount,
            "type": deposit_type,
            "timestamp": datetime.now(),
        })

    @staticmethod
    async def track_stock_trade(player_id: str, symbol: str, shares: int, action: str):
        """追踪股票交易"""
        await log_event("stock_trade", {
            "player_id": player_id,
            "symbol": symbol,
            "shares": shares,
            "action": action,  # "buy" or "sell"
            "timestamp": datetime.now(),
        })

    @staticmethod
    async def generate_weekly_report():
        """生成每周投资系统报告"""
        return """
=== 投资系统周报 (2025-12-09) ===

💰 经济指标:
- 日均金币增长: 8,500/人 (↓ 15%, ✅ 接近目标)
- 金币基尼系数: 0.78 (↓ 0.07, ✅ 贫富差距缩小)

📊 参与度:
- 银行存款: 85% (↑ 5%, ✅ 超过目标)
- 股票投资: 18% (↑ 13%, ⚠️ 仍需提升)
- 特殊存款: 12% (新功能, 待观察)

⚠️ 异常检测:
- 股票FA001疑似恶意炒作(日交易量暴增300%)
- 需人工介入调查

💡 优化建议:
- 增加股票投资新手引导
- 调整FA001股票波动率
        """
```

---

## 7. 设计哲学总结

### 7.1 从"失败的股票"到"策略中心"

**过去的设计**:
```
股票 = 随机波动 + 高手续费 = 必亏钱
银行 = 无脑挂机 = 无娱乐性
打工 = 高收益 + 无限制 = 唯一选择
```

**新的设计**:
```
投资决策中心:
├─ 银行存款: 无风险保底收益 (适合新手)
├─ 稳健型股票: 低风险稳定收益 (适合进阶)
├─ 成长型股票: 中风险长期增值 (适合长期)
├─ 投机型股票: 高风险短期暴富 (适合激进)
├─ 基金托管: 懒人专属 (适合佛系)
└─ 特殊存款: 趣味性强 (适合尝鲜)

打工: 主动赚钱,但有疲劳度限制
投资: 被动增值,策略决策
```

### 7.2 QQ群投资系统的本质

QQ群游戏不是实时交易平台,是**碎片化决策场景**:
- 玩家每次上线5-10分钟
- 不能高频盯盘
- 需要"一次决策,长期生效"

**因此**:
- ❌ 不设计需要秒级反应的"抢涨停"玩法
- ✅ 设计"买入后持有1周"的趋势投资
- ❌ 不设计复杂的技术分析
- ✅ 设计简单的"稳健/平衡/激进"分类
- ❌ 不设计实时行情推送(会刷屏)
- ✅ 设计每日汇总报告(私聊发送)

### 7.3 娱乐性≠复杂度

**错误观念**: 功能越多越好玩

**正确理解**:
- 简单规则 + 策略深度 = 好玩
- 投资建议 + 一键执行 = 降低门槛
- 随机事件 + 全服公告 = 惊喜感
- 排行榜 + 社交炫耀 = 参与动力

---

## 8. 实施路线图

### Phase 1: 紧急修复 (1周, 2人日)
- [x] 银行利率削减 (年化876% → 18%)
- [x] 股票手续费降低 (6% → 1%)
- [x] 打工疲劳度系统
- [x] 发布公告与灰度上线

### Phase 2: 渐进优化 (1个月, 7人日)
- [ ] 特殊存款计划 (7日定期/成长账户/幸运存款)
- [ ] 股票趋势分类 (稳健/成长/投机)
- [ ] 投资顾问功能
- [ ] 数据埋点与监控

### Phase 3: 系统重构 (2-3个月, 16人日)
- [ ] 基金系统
- [ ] 股票事件系统
- [ ] 投资排行榜
- [ ] A/B测试与全量上线

---

## 9. 相关文档

- **调查报告**: `/llmdoc/agent/investment_system_investigation.md`
- **游戏平衡分析**: `/llmdoc/agent/game_balance_analysis_2025_12_01.md`
- **新手体验设计**: `/llmdoc/design/game_system_redesign_2025_12_02.md`
- **执行摘要**: `/llmdoc/design/EXECUTIVE_SUMMARY.md`

---

**设计者**: designer 代理 (Lead System Architect)
**审核者**: (待人类开发者审核)
**状态**: 待实施
**预期完成**: Phase 1: 2025-12-09 | Phase 2: 2026-01-02 | Phase 3: 2026-02-28
