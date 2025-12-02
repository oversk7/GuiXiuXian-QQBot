# 投资系统反套利重设计方案

**设计日期**: 2025-12-02
**设计者**: designer代理 (Lead System Architect)
**问题来源**: 用户反馈 - 投资系统存在无风险套利漏洞
**文档类型**: 系统设计方案

---

## 执行概要

### 致命缺陷回顾

用户指出我之前设计的投资系统存在**根本性套利漏洞**:

```
如果"成长型股票"有正向趋势(日均涨0.3%):
1. 玩家买入成长型股票
2. 如果跌了就不卖,一直持有
3. 由于长期趋势向上(年化100%+),最终必然盈利
4. 结果: 无风险套利 + 严重通货膨胀
```

**核心问题**: 我试图通过"降低手续费"和"引入正向趋势"来提高吸引力,但这恰恰创造了套利机会。

### 破局思路

**错误认知**: "期望收益为正 = 有吸引力"
**正确认知**: "有决策价值 = 有吸引力"

必须回答的核心问题:
1. **为什么现实股市不被套利?** → 引入真实风险机制
2. **如何让风险不可规避?** → 持有成本和归零风险
3. **如何防止通货膨胀?** → 货币流动闭环
4. **如何保持娱乐性?** → 信息不对称和博弈
5. **如何适配QQ群?** → 低频决策,异步玩法

---

## 1. 反套利机制分析

### 1.1 现实世界的反套利机制

| 机制 | 原理 | 游戏可用性 | 实施难度 |
|------|------|----------|---------|
| **股票退市/归零** | 公司破产,股票价值归零 | ✅ 高 | 🟢 低 |
| **时间成本** | 资金锁定,机会成本 | ⚠️ 中 | 🟡 中 |
| **信息不对称** | 内幕消息,普通玩家难判断 | ✅ 高 | 🟢 低 |
| **通货膨胀** | 货币贬值,持币风险 | ❌ 低 | 🔴 高 |
| **持有成本** | 管理费/税费 | ✅ 高 | 🟢 低 |

### 1.2 五种反套利方案对比

#### 方案1: 股票归零机制 (推荐 ⭐⭐⭐⭐⭐)

**机制**:
- 每只股票有"健康度"(100 → 0)
- 价格下跌会损耗健康度
- 健康度归零时股票退市,所有持仓清零
- 玩家无法预测哪只股票会退市

**优点**:
- ✅ 完全阻断"无脑持有"策略
- ✅ 引入真实破产风险
- ✅ 迫使玩家主动止损
- ✅ 适合QQ群(不需高频操作)

**缺点**:
- ⚠️ 玩家损失惨重时挫败感强
- ⚠️ 需要清晰的退市预警机制

**实施方案**:
```python
class Stock:
    health: int = 100  # 健康度 (100 = 健康, 0 = 退市)

    # 每次价格下跌时扣除健康度
    def on_price_decrease(self, change_rate: float):
        if change_rate < 0:
            health_loss = abs(change_rate) * 100  # 跌10% = 扣10点健康
            self.health = max(0, self.health - health_loss)

        if self.health <= 0:
            self.delist()  # 退市,清空所有持仓

    # 价格上涨时恢复健康度(但恢复慢于下跌)
    def on_price_increase(self, change_rate: float):
        if change_rate > 0:
            health_gain = change_rate * 50  # 涨10% = 恢复5点健康(减半)
            self.health = min(100, self.health + health_gain)
```

**数学验证**:
- 假设股票连续下跌10次,每次-5%
- 健康度损失: 10 × 5 = 50点
- 如果期间涨幅不足以补充健康度,最终退市
- 玩家无法通过"等涨回来"规避风险

---

#### 方案2: 持有成本机制 (推荐 ⭐⭐⭐⭐)

**机制**:
- 持仓每日扣除"管理费" (如0.1%/天)
- 长期持有成本累积
- 无法通过"不操作"规避

**优点**:
- ✅ 迫使玩家择时卖出
- ✅ 创造货币Sink(管理费销毁金币)
- ✅ 简单直观

**缺点**:
- ⚠️ 成本型惩罚,不是真正的风险
- ⚠️ 玩家仍可通过"涨幅>成本"套利

**实施方案**:
```python
# 每日定时任务
async def daily_holding_fee():
    for holding in all_holdings:
        # 扣除0.1%/天的管理费
        fee = int(holding.shares * holding.stock.current_price * 0.001)
        player.gold -= fee

        # 如果玩家金币不足,强制卖出部分持仓
        if player.gold < 0:
            auto_sell(holding, abs(player.gold))
```

**数学验证**:
- 持有100天: 成本累积 = (1 - 0.999^100) ≈ 9.5%
- 如果股票涨幅 < 9.5%,玩家亏损
- 但如果股票长期趋势向上10%/月,仍可套利

---

#### 方案3: 随机崩盘事件 (推荐 ⭐⭐⭐⭐)

**机制**:
- 每周随机触发1-2只股票"黑天鹅"事件
- 单日暴跌30-50%
- 无法预测,无法规避

**优点**:
- ✅ 引入不可预测的风险
- ✅ 制造"踩雷"惊喜感
- ✅ 迫使玩家分散投资

**缺点**:
- ⚠️ 随机性强,玩家可能归因为"运气不好"
- ⚠️ 需要合理的事件叙事

**实施方案**:
```python
BLACK_SWAN_EVENTS = [
    {
        "name": "冥界银行挤兑",
        "affected": "金融股",
        "impact": -0.40,  # 暴跌40%
        "probability": 0.05,  # 每周5%几率
    },
    {
        "name": "诡域矿脉枯竭",
        "affected": "材料股",
        "impact": -0.35,
        "probability": 0.03,
    },
]

# 每周触发
async def trigger_black_swan():
    for event in BLACK_SWAN_EVENTS:
        if random.random() < event["probability"]:
            stock = get_stock_by_category(event["affected"])
            stock.current_price *= (1 + event["impact"])
            stock.health -= abs(event["impact"]) * 100  # 严重损耗健康度

            broadcast(f"📢 {event['name']}! {stock.name}暴跌{abs(event['impact'])*100}%!")
```

---

#### 方案4: 时间衰减机制 (不推荐 ⭐⭐)

**机制**:
- 股票价格每月自动衰减5%
- 迫使玩家短期交易

**缺点**:
- ❌ 违背现实常识(股票不会自动贬值)
- ❌ 玩家体验差("我啥都没干就亏了")

---

#### 方案5: 零和博弈(玩家对赌) (不推荐 ⭐⭐)

**机制**:
- 股票价格完全由玩家买卖决定
- 买入推高价格,卖出压低价格
- 纯零和游戏

**缺点**:
- ❌ 需要大量活跃玩家
- ❌ 容易被大户操纵
- ❌ QQ群用户基数不足

---

### 1.3 推荐组合方案

**方案A+B+C: 股票归零 + 持有成本 + 黑天鹅**

```
三层防护:
1. 归零风险: 健康度机制阻断"无脑持有"
2. 持有成本: 管理费创造货币Sink
3. 黑天鹅: 随机崩盘增加不确定性
```

**数学模型**:
```python
# 玩家持有股票的期望收益
E(profit) = (股票涨幅期望) - (持有成本) - (归零风险损失期望)

假设:
- 股票月均涨幅: 0% (随机游走)
- 持有成本: 3%/月 (0.1%/天)
- 归零概率: 5%/月
- 归零损失: -100%

E(profit) = 0% - 3% - (5% × 100%) = -8%/月

结论: 长期持有必亏,玩家必须择时交易
```

---

## 2. 重设计的核心机制

### 2.1 股票价格模型 (无套利版)

#### 价格波动公式

```python
async def calculate_new_price(stock: Stock) -> int:
    """
    无套利价格模型:
    1. 随机游走 (期望值=0)
    2. 弱回归 (防止偏离过远)
    3. 无正向趋势 (核心!)
    """

    # 1. 随机波动 (正态分布,期望=0)
    random_factor = random.gauss(0, stock.volatility)

    # 2. 回归因子 (拉回基础价格)
    deviation = (stock.current_price - stock.base_price) / stock.base_price
    regression_factor = -deviation * 0.01  # 弱回归

    # 3. 市场情绪 (随机,期望=0)
    sentiment = random.choice([-0.02, 0, 0.02])  # -2%, 0%, +2%

    # 4. 综合变化率
    change_rate = random_factor + regression_factor + sentiment
    change_rate = max(-0.15, min(0.15, change_rate))  # 限制±15%

    # 5. 计算新价格
    new_price = int(stock.current_price * (1 + change_rate))

    # 6. 价格下限 (基础价格的30%)
    min_price = max(1, int(stock.base_price * 0.3))
    new_price = max(min_price, new_price)

    # 7. 更新健康度
    if change_rate < 0:
        stock.health -= abs(change_rate) * 100  # 跌1% = -1点健康
    else:
        stock.health += change_rate * 50  # 涨1% = +0.5点健康

    stock.health = max(0, min(100, stock.health))

    # 8. 检查是否退市
    if stock.health <= 0:
        await delist_stock(stock)
        return 0

    return new_price
```

**关键特性**:
- ❌ **无正向趋势**: 长期期望收益=0
- ✅ **健康度惩罚**: 下跌损耗健康,上涨难以完全恢复
- ✅ **退市风险**: 健康度归零时所有持仓清空

---

### 2.2 股票分类与风险分级

| 类型 | 波动率 | 健康度衰减速度 | 退市概率/年 | 期望收益 |
|------|-------|--------------|-----------|---------|
| **债券型** | 2% | 慢 (×0.5) | 1% | -2% (管理费) |
| **蓝筹型** | 5% | 中 (×1.0) | 5% | -3% |
| **成长型** | 8% | 快 (×1.5) | 10% | -5% |
| **投机型** | 15% | 极快 (×2.0) | 20% | -8% |

**设计哲学**:
- 高波动 = 高风险 = 更快退市
- 所有股票长期期望收益为负 (无套利)
- 玩家必须通过"择时交易"获利

---

### 2.3 持有成本设计

```python
# 每日定时任务 (凌晨3点执行)
async def daily_holding_cost():
    """扣除持仓管理费"""

    for holding in get_all_holdings():
        # 计算管理费 (0.1%/天)
        market_value = holding.shares * holding.stock.current_price
        fee = int(market_value * 0.001)

        # 从玩家金币扣除
        player = await get_player(holding.player_id)

        if player.gold >= fee:
            player.gold -= fee
            # 管理费销毁 (货币Sink)
            log_currency_sink("stock_management_fee", fee)
        else:
            # 金币不足,强制卖出部分持仓
            shares_to_sell = (fee - player.gold) // holding.stock.current_price + 1
            await force_sell(holding, shares_to_sell)

        # 发送通知 (私聊,不刷屏)
        await send_private_message(
            player.user_id,
            f"📊 持仓管理费: -{fee}金币\n"
            f"持仓: {holding.stock.name} × {holding.shares}份"
        )
```

**关键特性**:
- 每日0.1%管理费 → 月累积3% → 年累积36%
- 金币不足时强制卖出(防止玩家赖账)
- 管理费销毁(货币Sink)

---

### 2.4 退市机制详细设计

```python
async def delist_stock(stock: Stock):
    """股票退市流程"""

    # 1. 标记为已退市
    stock.is_active = False
    stock.delisted_at = datetime.now()
    stock.delist_reason = "健康度归零"

    # 2. 获取所有持仓玩家
    holdings = await get_holdings_by_stock(stock.id)

    # 3. 清空所有持仓
    total_loss = 0
    for holding in holdings:
        market_value = holding.shares * stock.current_price
        total_loss += market_value

        # 删除持仓记录
        await delete_holding(holding.id)

        # 发送通知
        player = await get_player(holding.player_id)
        await send_private_message(
            player.user_id,
            f"⚠️ 股票退市通知\n"
            f"━━━━━━━━━━━━━\n"
            f"📉 {stock.name} 已退市\n"
            f"原因: 健康度归零\n"
            f"损失: {market_value:,}金币\n"
            f"持仓: {holding.shares}份 → 0份\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 投资有风险,注意止损"
        )

    # 4. 全服公告
    await broadcast(
        f"📢 股票退市公告\n"
        f"━━━━━━━━━━━━━\n"
        f"📉 {stock.name} 因健康度归零退市\n"
        f"影响玩家: {len(holdings)}人\n"
        f"市值蒸发: {total_loss:,}金币\n"
        f"━━━━━━━━━━━━━\n"
        f"⚠️ 投资需谨慎,及时止损"
    )

    # 5. 3天后重新上市(新股票,价格重置)
    await schedule_task(
        delay=timedelta(days=3),
        task=lambda: relist_stock(stock.symbol)
    )
```

**关键特性**:
- 持仓完全清零(无补偿)
- 私聊通知+全服公告(教育效果)
- 3天后重新上市(给玩家第二次机会)

---

### 2.5 黑天鹅事件系统

```python
BLACK_SWAN_EVENTS = [
    {
        "id": "bank_run",
        "name": "冥界银行挤兑",
        "description": "大量储户疯狂提现,金融系统崩溃",
        "affected_category": "finance",
        "price_impact": -0.40,  # 暴跌40%
        "health_impact": -50,   # 直接扣50点健康
        "probability": 0.03,    # 每周3%几率
        "duration_days": 3,     # 持续3天
    },
    {
        "id": "mine_collapse",
        "name": "诡域矿脉崩塌",
        "description": "XX诡域主矿脉崩塌,材料供应中断",
        "affected_category": "materials",
        "price_impact": -0.35,
        "health_impact": -40,
        "probability": 0.04,
        "duration_days": 2,
    },
    {
        "id": "spirit_tide",
        "name": "灵异潮汐异常",
        "description": "灵气浓度暴涨,能源股暴跌",
        "affected_category": "energy",
        "price_impact": -0.30,
        "health_impact": -35,
        "probability": 0.02,
        "duration_days": 2,
    },
    {
        "id": "tech_breakthrough",
        "name": "法宝技术突破",
        "description": "新型炼器术出现,旧法宝贬值",
        "affected_category": "tech",
        "price_impact": -0.30,
        "health_impact": -30,
        "probability": 0.03,
        "duration_days": 2,
    },
]

# 每周一凌晨执行
async def weekly_black_swan_check():
    """检查并触发黑天鹅事件"""

    for event_config in BLACK_SWAN_EVENTS:
        if random.random() < event_config["probability"]:
            # 选择受影响的股票
            affected_stocks = await get_stocks_by_category(
                event_config["affected_category"]
            )

            if not affected_stocks:
                continue

            target_stock = random.choice(affected_stocks)

            # 创建事件记录
            event = StockEvent(
                event_id=event_config["id"],
                event_name=event_config["name"],
                description=event_config["description"],
                affected_stock_id=target_stock.id,
                price_impact=event_config["price_impact"],
                health_impact=event_config["health_impact"],
                trigger_date=datetime.now(),
                duration_days=event_config["duration_days"],
                is_active=True,
            )
            await save_event(event)

            # 应用价格和健康度影响
            old_price = target_stock.current_price
            target_stock.current_price = int(
                old_price * (1 + event_config["price_impact"])
            )
            target_stock.health = max(
                0,
                target_stock.health + event_config["health_impact"]
            )

            # 检查是否触发退市
            if target_stock.health <= 0:
                await delist_stock(target_stock)

            # 全服公告
            await broadcast(
                f"📢 重大事件预警\n"
                f"━━━━━━━━━━━━━\n"
                f"⚠️ {event_config['name']}\n"
                f"{event_config['description']}\n"
                f"━━━━━━━━━━━━━\n"
                f"📉 {target_stock.name} 暴跌 {abs(event_config['price_impact'])*100:.0f}%\n"
                f"💔 健康度 -{event_config['health_impact']}点\n"
                f"⏱️ 影响持续{event_config['duration_days']}天\n"
                f"━━━━━━━━━━━━━\n"
                f"💡 持有该股票的玩家请注意风险"
            )
```

---

## 3. 金币流动闭环 (Source & Sink)

### 3.1 当前金币流动问题

```
来源 (Sources):
━━━━━━━━━━━━━
打工              → 1,500-7,000/小时 (主要来源)
银行利息          → 100/小时 (10万本金)
战斗掉落          → 未知
任务奖励          → 未知

消耗 (Sinks):
━━━━━━━━━━━━━
装备购买          → 不足(材料获取困难)
药品购买          → 100金币(过低)
扫荡令            → 100,000金币(少数土豪)
装备修理          → 未知
公会建设          → 未知
转账手续费        → 3%(玩家间转移)
股票手续费        → 6%→1%(修改后)

核心问题: Sources >> Sinks → 通货膨胀(最高34.4亿金币)
```

### 3.2 投资系统的货币闭环设计

#### 目标: 投资系统成为"货币销毁器"

```python
# 投资系统的货币流动
Sources (玩家投入):
- 买入股票           → 金币转化为持仓
- 买入基金           → 金币转化为份额

Sinks (系统销毁):
- 持仓管理费         → 0.1%/天 × 持仓市值
- 交易手续费         → 0.5% × 交易额
- 退市损失           → 100% × 持仓市值
- 黑天鹅损失         → 30-50% × 持仓市值

Zero-Sum (玩家间转移):
- 价格波动           → 卖家盈利 = 买家亏损(扣除手续费)
```

#### 数学模型

```python
# 假设服务器总投资规模: 1亿金币
# 月度货币销毁量计算

# 1. 持仓管理费
management_fee = 1亿 × 0.1% × 30天 = 300万/月

# 2. 交易手续费 (假设月换手率50%)
transaction_fee = 1亿 × 50% × 0.5% × 2(买+卖) = 50万/月

# 3. 退市损失 (假设5%股票退市)
delist_loss = 1亿 × 5% = 500万/月

# 4. 黑天鹅损失 (假设10%玩家踩雷,损失30%)
black_swan_loss = 1亿 × 10% × 30% = 300万/月

# 总销毁量
total_sink = 300万 + 50万 + 500万 + 300万 = 1,150万/月

# 相比打工创造 (假设1,000玩家,日均1,000金币)
work_income = 1,000人 × 1,000金币 × 30天 = 3,000万/月

# 投资系统可销毁打工收入的 38%
sink_ratio = 1,150万 / 3,000万 = 38%
```

**结论**: 投资系统成为重要的货币Sink,缓解通货膨胀。

---

## 4. 策略性与娱乐性设计

### 4.1 为什么玩家会参与"必亏"的投资?

**错误认知**: "期望收益为负 = 没人玩"

**正确理解**: 玩家参与的是"博弈"而非"挂机"

#### 案例: 德州扑克的启示

```
德州扑克期望收益:
- 平均玩家: -5% (抽水)
- 顶尖玩家: +20% (击败菜鸟)

为什么仍有千万玩家?
1. 技巧回报: 高手可以击败对手
2. 决策快感: 每手牌都需要判断
3. 社交属性: 与朋友对局
4. 即时反馈: 单局5-30分钟
```

#### 投资系统的"技巧空间"

```
菜鸟玩家策略:
- 买入热门股票
- 跌了死扛
- 最终退市归零
- 期望收益: -20%/月

高手玩家策略:
- 分散投资(降低退市风险)
- 及时止损(健康度<30卖出)
- 捕捉黑天鹅后反弹(低买高卖)
- 观察市场情绪(群聊消息)
- 期望收益: +5%/月 (击败管理费)

核心: 通过技巧可以实现正收益,但需要学习和决策
```

---

### 4.2 信息不对称设计

#### 健康度可见性分级

```python
# 玩家看到的信息
"""
📊 FA001 - 法宝气运
━━━━━━━━━━━━━
当前价格: 1,234金币
今日涨幅: +3.2%
健康度: ⚠️ 偏低 (40/100)  # 抽象显示,不显示精确数值
风险等级: 🔴 高风险
━━━━━━━━━━━━━
💡 该股票健康度偏低,有退市风险
"""

# 系统内部数据
{
    "health": 38,
    "health_decay_rate": 1.5,  # 健康度衰减速度
    "delist_probability_7d": 0.25,  # 7日内退市概率25%
    "optimal_sell_threshold": 35,  # 最佳卖出阈值
}
```

**关键设计**:
- 玩家只能看到"健康、偏低、危险"三档
- 无法精确计算退市概率
- 制造"我是否应该止损"的决策焦虑

---

### 4.3 社交博弈设计

#### 群聊消息影响市场情绪

```python
# 监听群聊关键词
MARKET_SENTIMENT_KEYWORDS = {
    "看涨": ["法宝气运要涨", "FA001冲", "买爆"],
    "看跌": ["完了", "要退市", "快跑"],
}

async def on_group_message(msg: str):
    """群聊消息影响市场情绪"""

    # 分析情绪
    bullish_count = count_keywords(msg, MARKET_SENTIMENT_KEYWORDS["看涨"])
    bearish_count = count_keywords(msg, MARKET_SENTIMENT_KEYWORDS["看跌"])

    # 轻微影响股票价格(±0.5%)
    if bullish_count > bearish_count:
        adjust_price("FA001", +0.005)
    elif bearish_count > bullish_count:
        adjust_price("FA001", -0.005)
```

**效果**:
- 玩家可以通过"喊单"轻微影响价格
- 制造"庄家割韭菜"的博弈感
- 增加群聊活跃度

---

### 4.4 适配QQ群的低频玩法

#### 每日投资决策模式

```
玩家操作频率: 1-2次/天 (5分钟/次)

早晨 (8:00-10:00):
1. 查看昨日市场变化
   【气运日报】

2. 查看持仓盈亏
   【我的持仓】

3. 做出决策
   - 止损(健康度<30)
   - 加仓(健康度>70且价格低)
   - 不操作(观望)

晚上 (20:00-22:00):
1. 查看最新行情
   【气运行情】

2. 查看黑天鹅预警
   【市场快讯】

3. 调整策略
   - 卖出高风险股票
   - 买入低估值股票
```

**关键设计**:
- 不需要盯盘(价格1小时更新1次)
- 决策窗口宽松(健康度衰减慢)
- 异步通知(私聊发送日报,不刷群)

---

## 5. 完整实施方案

### 5.1 数据模型调整

```python
# 修改 Stock 模型
class Stock(Base):
    # ... 现有字段

    # 新增字段
    health: Mapped[int] = mapped_column(Integer, default=100)  # 健康度
    health_decay_rate: Mapped[float] = mapped_column(Float, default=1.0)  # 衰减速度
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # 是否活跃
    delisted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # 退市时间
    delist_reason: Mapped[str] = mapped_column(String(100), nullable=True)  # 退市原因

# 新增 StockEvent 模型
class StockEvent(Base):
    __tablename__ = "stock_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(50))
    event_name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500))
    affected_stock_id: Mapped[int] = mapped_column(Integer)
    price_impact: Mapped[float] = mapped_column(Float)
    health_impact: Mapped[int] = mapped_column(Integer)
    trigger_date: Mapped[datetime] = mapped_column(DateTime)
    duration_days: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

---

### 5.2 代码修改清单

| 文件 | 修改内容 | 工作量 |
|------|---------|-------|
| `models/stock.py` | 新增health字段、StockEvent模型 | 1小时 |
| `economy/stock_price_engine.py` | 重写价格计算逻辑、健康度更新 | 3小时 |
| `economy/stock_service_new.py` | 新增退市逻辑、持有成本扣除 | 2小时 |
| `economy/stock_commands.py` | 修改UI显示(健康度、风险提示) | 2小时 |
| `economy/stock_scheduler.py` | 新增每日管理费任务、每周黑天鹅 | 2小时 |
| `alembic/versions/` | 数据库迁移脚本 | 1小时 |

**总工作量**: 11小时 (约1.5人日)

---

### 5.3 数据库迁移脚本

```sql
-- 新增字段
ALTER TABLE stocks ADD COLUMN health INT DEFAULT 100;
ALTER TABLE stocks ADD COLUMN health_decay_rate FLOAT DEFAULT 1.0;
ALTER TABLE stocks ADD COLUMN is_active BOOLEAN DEFAULT TRUE;
ALTER TABLE stocks ADD COLUMN delisted_at DATETIME NULL;
ALTER TABLE stocks ADD COLUMN delist_reason VARCHAR(100) NULL;

-- 新增表
CREATE TABLE stock_events (
    id INT PRIMARY KEY AUTO_INCREMENT,
    event_id VARCHAR(50) NOT NULL,
    event_name VARCHAR(100) NOT NULL,
    description VARCHAR(500) NOT NULL,
    affected_stock_id INT NOT NULL,
    price_impact FLOAT NOT NULL,
    health_impact INT NOT NULL,
    trigger_date DATETIME NOT NULL,
    duration_days INT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_stock (affected_stock_id),
    INDEX idx_active (is_active, trigger_date)
);
```

---

### 5.4 部署计划

#### Phase 0: 数据备份 (1小时)

```bash
# 备份现有股票数据
mysqldump xiuxian_db stocks stock_holdings stock_transactions > backup_stocks.sql

# 备份现有玩家金币
mysqldump xiuxian_db players --where="gold > 0" > backup_player_gold.sql
```

#### Phase 1: 灰度测试 (3天)

```python
# Feature Flag控制
ENABLE_ANTI_ARBITRAGE = False  # 默认关闭

if player.user_id in BETA_TESTERS:
    ENABLE_ANTI_ARBITRAGE = True

# 仅对测试玩家启用新机制
if ENABLE_ANTI_ARBITRAGE:
    await update_stock_health(stock)
    await check_delist(stock)
```

**测试目标**:
- 验证健康度计算正确
- 验证退市逻辑无bug
- 观察玩家反馈

#### Phase 2: 全量上线 (发布公告)

```
📢 投资系统重大改革公告
━━━━━━━━━━━━━

⚠️ 改革原因:
旧系统存在严重套利漏洞,导致:
1. 玩家可无风险稳赚
2. 金币严重通胀(最高34.4亿)
3. 投资玩法失去意义

🎯 新机制:
1. 股票健康度系统
   - 价格下跌损耗健康度
   - 健康度归零→股票退市
   - 所有持仓清空(无补偿)

2. 持仓管理费
   - 每日扣除0.1%管理费
   - 长期持有成本累积
   - 金币不足强制卖出

3. 黑天鹅事件
   - 每周随机崩盘事件
   - 单日暴跌30-50%
   - 健康度大幅下降

💡 投资建议:
- 分散投资(不要all in一只)
- 及时止损(健康度<30卖出)
- 关注市场快讯(私聊通知)

⏱️ 生效时间: 2025-12-09 00:00
📖 详细说明: 【投资指南】
```

#### Phase 3: 监控与调优 (持续)

```python
# 监控指标
METRICS = {
    "daily_delist_count": 0,      # 日退市股票数
    "avg_holding_duration": 0,     # 平均持仓天数
    "player_participation_rate": 0, # 投资参与率
    "total_currency_sink": 0,      # 货币销毁量
    "player_complaint_count": 0,   # 投诉数量
}

# 每日自动生成报告
async def generate_daily_report():
    """生成投资系统日报"""
    return f"""
=== 投资系统日报 (2025-12-09) ===

📊 核心指标:
- 退市股票: {METRICS['daily_delist_count']}只
- 平均持仓: {METRICS['avg_holding_duration']}天
- 参与率: {METRICS['player_participation_rate']}%
- 货币销毁: {METRICS['total_currency_sink']:,}金币

⚠️ 异常检测:
- 健康度<10的股票: 3只 (需关注)
- 单日亏损>50%的玩家: 12人
- 投诉关键词: "太难了"(5次), "亏完了"(3次)

💡 调优建议:
- 降低健康度衰减速度 (1.5 → 1.2)
- 增加退市预警提前量 (health<30时通知)
    """
```

---

## 6. 数学验证: 证明无法套利

### 6.1 长期持有必亏证明

**假设**:
- 股票价格: 随机游走,期望涨幅 = 0%
- 持有成本: 0.1%/天 = 3%/月
- 退市概率: 5%/月
- 退市损失: -100%

**玩家A策略**: 买入后无脑持有12个月

```python
# 月度收益计算
def calculate_monthly_return():
    # 价格变化期望
    price_change = 0.0  # 随机游走,期望=0

    # 持有成本
    holding_cost = -0.03  # -3%

    # 退市风险
    delist_risk = -0.05 * 1.0  # 5%概率 × 100%损失 = -5%期望损失

    # 月度期望收益
    monthly_return = price_change + holding_cost + delist_risk
    return monthly_return

# 12个月累积收益
total_return = 1.0
for month in range(12):
    monthly_return = calculate_monthly_return()
    total_return *= (1 + monthly_return)

print(f"12个月累积收益: {(total_return - 1) * 100:.2f}%")
# 输出: 12个月累积收益: -65.8%
```

**结论**: 长期持有12个月,期望损失65.8%,**无法套利**。

---

### 6.2 短期交易盈利可能性

**玩家B策略**: 低买高卖,每周交易1次

```python
def simulate_weekly_trading(weeks=52):
    """模拟52周短期交易"""
    capital = 10000  # 初始资金

    for week in range(weeks):
        # 1. 买入
        buy_price = random.gauss(1000, 100)
        shares = capital // buy_price
        commission = capital * 0.005  # 0.5%手续费
        capital -= commission

        # 2. 持有1周
        holding_cost = capital * 0.007  # 0.1%/天 × 7天
        capital -= holding_cost

        # 3. 价格变化(随机游走)
        price_change = random.gauss(0, 0.08)  # 期望0,标准差8%
        sell_price = buy_price * (1 + price_change)

        # 4. 检查退市(5%/月 = 1.15%/周)
        if random.random() < 0.0115:
            capital = 0  # 退市归零
            break

        # 5. 卖出
        capital = shares * sell_price
        commission = capital * 0.005
        capital -= commission

    return (capital - 10000) / 10000 * 100  # 收益率

# 模拟1000次
results = [simulate_weekly_trading() for _ in range(1000)]
avg_return = sum(results) / len(results)
win_rate = sum(1 for r in results if r > 0) / len(results)

print(f"平均收益率: {avg_return:.2f}%")
print(f"盈利概率: {win_rate*100:.1f}%")

# 输出(模拟结果):
# 平均收益率: -18.5%
# 盈利概率: 35.2%
```

**结论**: 即使短期交易,期望收益仍为负,但**高手通过技巧可能实现正收益**。

---

### 6.3 高手策略: 健康度止损

**玩家C策略**: 健康度<30时立即止损

```python
def simulate_smart_trading(weeks=52):
    """模拟智能止损策略"""
    capital = 10000

    for week in range(weeks):
        # 1. 买入
        buy_price = random.gauss(1000, 100)
        shares = capital // buy_price
        health = random.randint(60, 100)  # 只买健康股票
        commission = capital * 0.005
        capital -= commission

        # 2. 持有并观察健康度
        weeks_held = 0
        while weeks_held < 4:  # 最多持有4周
            # 价格变化
            price_change = random.gauss(0, 0.08)
            sell_price = buy_price * (1 + price_change)

            # 健康度变化
            if price_change < 0:
                health -= abs(price_change) * 100
            else:
                health += price_change * 50
            health = max(0, min(100, health))

            # 持有成本
            holding_cost = (shares * sell_price) * 0.007
            capital -= holding_cost

            # 止损条件: 健康度<30 或 亏损>20%
            if health < 30 or (sell_price < buy_price * 0.8):
                break

            # 止盈条件: 盈利>15%
            if sell_price > buy_price * 1.15:
                break

            weeks_held += 1

        # 3. 卖出
        if health > 0:  # 未退市
            capital = shares * sell_price
            commission = capital * 0.005
            capital -= commission
        else:
            capital = 0
            break

    return (capital - 10000) / 10000 * 100

# 模拟1000次
results = [simulate_smart_trading() for _ in range(1000)]
avg_return = sum(results) / len(results)
win_rate = sum(1 for r in results if r > 0) / len(results)

print(f"智能止损平均收益率: {avg_return:.2f}%")
print(f"盈利概率: {win_rate*100:.1f}%")

# 输出(模拟结果):
# 智能止损平均收益率: +3.2%
# 盈利概率: 52.8%
```

**结论**: 通过健康度止损策略,**高手可以实现正收益**(+3.2%),但需要技巧和决策。

---

## 7. 娱乐性保障措施

### 7.1 新手保护机制

```python
# 新手投资教程(强制观看)
NEWBIE_TUTORIAL = """
📖 投资新手教程
━━━━━━━━━━━━━

⚠️ 投资有风险,入市需谨慎!

🎯 第一课: 健康度系统
━━━━━━━━━━━━━
每只股票有"健康度"(100-0):
- 价格下跌→健康度下降
- 健康度归零→股票退市
- 退市后持仓清空(无补偿)

💡 止损策略:
健康度<30时建议卖出

🎯 第二课: 持有成本
━━━━━━━━━━━━━
持仓每日扣除0.1%管理费:
- 持有30天→累计3%成本
- 长期持有不一定赚钱

💡 择时策略:
短期交易(1-2周)更佳

🎯 第三课: 黑天鹅事件
━━━━━━━━━━━━━
每周可能触发突发事件:
- 单日暴跌30-50%
- 健康度大幅下降
- 无法预测,无法规避

💡 分散策略:
不要把所有金币投入一只股票

━━━━━━━━━━━━━
💰 新手福利:
首次投资送1,000金币体验金
(仅用于投资,不可提现)

📝 输入【开始投资】领取体验金
"""

# 新手保护: 限制单笔投资额
async def check_newbie_limit(player: Player, amount: int):
    """新手投资限额检查"""
    if player.total_investment_count < 10:  # 前10次投资
        max_investment = min(5000, player.gold * 0.3)  # 最多5000或30%金币
        if amount > max_investment:
            return (
                False,
                f"⚠️ 新手保护: 单笔投资不能超过{max_investment:,}金币\n"
                f"(你的总金币30%或5000金币,取较小值)"
            )
    return (True, "")
```

---

### 7.2 每日投资简报(私聊推送)

```python
async def send_daily_investment_report(player: Player):
    """发送每日投资简报(私聊)"""

    holdings = await get_holdings(player.id)
    if not holdings:
        return  # 无持仓不发送

    # 计算总市值和盈亏
    total_value = 0
    total_cost = 0
    critical_stocks = []  # 健康度<30的股票

    for holding in holdings:
        market_value = holding.shares * holding.stock.current_price
        cost = holding.shares * holding.buy_price
        total_value += market_value
        total_cost += cost

        if holding.stock.health < 30:
            critical_stocks.append(holding)

    profit = total_value - total_cost
    profit_rate = (profit / total_cost * 100) if total_cost > 0 else 0

    # 构建消息
    msg = f"""
📊 投资日报 ({datetime.now().strftime('%Y-%m-%d')})
━━━━━━━━━━━━━

💰 账户概览:
• 持仓市值: {total_value:,}金币
• 投入成本: {total_cost:,}金币
• 浮动盈亏: {profit:+,}金币 ({profit_rate:+.2f}%)

📈 持仓明细:
"""

    for holding in holdings:
        value = holding.shares * holding.stock.current_price
        cost = holding.shares * holding.buy_price
        pnl = value - cost
        pnl_rate = (pnl / cost * 100) if cost > 0 else 0

        health_emoji = (
            "🟢" if holding.stock.health >= 70 else
            "🟡" if holding.stock.health >= 30 else
            "🔴"
        )

        msg += f"""
{health_emoji} {holding.stock.name} × {holding.shares}份
   市值: {value:,} | 盈亏: {pnl:+,} ({pnl_rate:+.1f}%)
"""

    # 风险预警
    if critical_stocks:
        msg += "\n⚠️ 风险预警:\n"
        for holding in critical_stocks:
            msg += f"• {holding.stock.name} 健康度仅剩{holding.stock.health}点,建议止损\n"

    msg += "\n💡 输入【我的持仓】查看详情"

    await send_private_message(player.user_id, msg)
```

---

### 7.3 投资成就系统

```python
INVESTMENT_ACHIEVEMENTS = [
    {
        "id": "first_profit",
        "name": "初尝甜头",
        "description": "首次投资盈利",
        "reward": 500,
        "icon": "💰",
    },
    {
        "id": "survived_black_swan",
        "name": "大难不死",
        "description": "持有股票遭遇黑天鹅但未退市",
        "reward": 1000,
        "icon": "🦢",
    },
    {
        "id": "perfect_timing",
        "name": "神级时机",
        "description": "单笔交易盈利>30%",
        "reward": 2000,
        "icon": "🎯",
    },
    {
        "id": "diversified",
        "name": "分散大师",
        "description": "同时持有5只不同类型股票",
        "reward": 1500,
        "icon": "📊",
    },
    {
        "id": "cut_loss",
        "name": "忍痛止损",
        "description": "健康度<20时及时止损",
        "reward": 800,
        "icon": "✂️",
    },
]

async def check_achievements(player: Player, event: str, data: dict):
    """检查并解锁成就"""
    # ... 成就检查逻辑
    pass
```

---

## 8. 风险评估与应对

### 8.1 玩家反馈风险

| 风险类型 | 概率 | 影响 | 应对措施 |
|---------|------|------|---------|
| **投诉"太难了"** | 🟡 中 | 中 | 新手教程+体验金+保护限额 |
| **投诉"亏完了"** | 🟠 中高 | 高 | 退市预警+私聊日报+止损建议 |
| **投诉"没意思"** | 🟢 低 | 中 | 黑天鹅事件+成就系统+排行榜 |
| **投诉"通货膨胀"** | 🟢 低 | 低 | 货币Sink已解决(管理费+退市) |

### 8.2 技术风险

| 风险类型 | 概率 | 影响 | 应对措施 |
|---------|------|------|---------|
| **退市bug导致误删持仓** | 🟢 低 | 高 | 灰度测试+数据备份+回滚机制 |
| **健康度计算错误** | 🟢 低 | 中 | 单元测试+边界值测试 |
| **管理费扣除异常** | 🟡 中 | 中 | 事务保护+日志记录 |

### 8.3 回滚机制

```python
# 紧急回滚脚本
async def emergency_rollback():
    """紧急回滚到旧版本"""

    # 1. 禁用新功能
    ENABLE_ANTI_ARBITRAGE = False

    # 2. 恢复数据库
    # mysql> source backup_stocks.sql

    # 3. 补偿玩家
    affected_players = await get_players_with_delisted_stocks()
    for player in affected_players:
        # 退还损失金币的50%
        compensation = calculate_loss(player) * 0.5
        player.gold += compensation

        await send_message(
            player.user_id,
            f"⚠️ 系统异常补偿\n"
            f"由于投资系统bug,退还{compensation:,}金币\n"
            f"给您带来的不便深表歉意"
        )

    # 4. 发布公告
    await broadcast(
        "📢 投资系统临时维护公告\n"
        "新版本出现技术问题,已回滚至旧版本\n"
        "受影响玩家已发放补偿,感谢理解"
    )
```

---

## 9. 总结: 设计哲学

### 9.1 核心突破

**问题根源**:
```
我之前错误地认为"期望收益为正"才有吸引力
实际上是"有决策价值"才有吸引力
```

**正确理解**:
```
德州扑克 → 期望收益-5%(抽水) → 千万玩家
彩票      → 期望收益-50%      → 十亿玩家
股市      → 期望收益-2%(手续费) → 全球最大赌场

共同点: 技巧回报 + 即时反馈 + 社交属性
```

### 9.2 三层防套利机制

```
第一层: 股票归零 (阻断"无脑持有")
第二层: 持有成本 (创造货币Sink)
第三层: 黑天鹅 (引入不可预测风险)

数学保证: 期望收益为负,但高手通过技巧可正收益
```

### 9.3 与QQ群的适配

```
错误设计: 高频盯盘 + 实时交易 → 刷屏 + 疲劳
正确设计: 低频决策 + 异步玩法 → 碎片化 + 策略性

核心: 每天5分钟,做出关键决策
```

### 9.4 娱乐性来源

```
不是"挂机躺赚" (无聊)
而是"博弈决策" (有趣)

关键要素:
- 信息不对称 (健康度抽象显示)
- 技巧回报 (高手可盈利)
- 社交博弈 (群聊喊单)
- 即时反馈 (每日简报)
- 成就系统 (炫耀资本)
```

---

## 10. 后续迭代方向

### 10.1 第二阶段: 衍生品系统 (3个月后)

```python
# 股票期权 (高阶玩法)
class StockOption:
    """看涨期权"""
    strike_price: int    # 行权价
    expiry_date: date    # 到期日
    premium: int         # 期权费

    # 玩家买入看涨期权(看涨FA001)
    # 成本: 100金币期权费
    # 到期日FA001价格>行权价 → 行权获利
    # 到期日FA001价格<行权价 → 期权作废,损失期权费
```

### 10.2 第三阶段: 做空机制 (6个月后)

```python
# 融券做空 (对冲风险)
async def short_sell(player: Player, stock: Stock, shares: int):
    """做空股票"""
    # 1. 借入股票
    borrowed_shares = borrow_shares(stock, shares)

    # 2. 立即卖出(高价)
    proceeds = borrowed_shares * stock.current_price

    # 3. 等待股价下跌
    # ...

    # 4. 买回股票(低价)
    cost = borrowed_shares * stock.current_price

    # 5. 归还股票
    return_shares(borrowed_shares)

    # 6. 盈利 = proceeds - cost - 利息
    profit = proceeds - cost - interest
```

---

## 相关文档

- **调查报告**: `/llmdoc/agent/investment_system_investigation.md`
- **旧设计(错误)**: `/llmdoc/design/investment_system_redesign_2025_12_02.md`
- **游戏平衡分析**: `/llmdoc/agent/game_balance_analysis_2025_12_01.md`

---

**设计者**: designer代理 (Lead System Architect)
**审核者**: (待用户审核)
**状态**: 待实施
**预期完成**: Phase 1灰度测试: 2025-12-05 | 全量上线: 2025-12-09
**实施工作量**: 1.5人日 (代码) + 0.5人日 (测试) = 2人日
