# 诡修仙投资系统调查报告

**调查日期**: 2025-12-02
**调查类型**: 经济系统平衡性分析
**调查目标**: 分析投资系统的运作机制、资源流动和平衡性问题

---

## Code Sections (The Evidence)

### 银行系统

- `plugins/xiuxian_game/economy/bank.py` (handle_balance): 查看银行余额、自动结息逻辑
- `plugins/xiuxian_game/economy/bank.py` (handle_deposit): 存款功能
- `plugins/xiuxian_game/economy/bank.py` (handle_withdraw): 取款功能
- `plugins/xiuxian_game/economy/bank.py` (handle_transfer): 转账功能，3%手续费
- `plugins/xiuxian_game/economy/bank.py` (handle_bank_invest): 投资理财中心入口
- `plugins/xiuxian_game/economy/bank.py:12-25` (_tier_rate, _TIERS): 阶梯利率配置
- `plugins/xiuxian_game/economy/bank.py:37-51` (_apply_interest): 利息计算逻辑，单次结息上限10,000金币
- `plugins/xiuxian_game/models/bank_account.py` (BankAccount): 银行账户数据模型

### 股票系统（气运投资）

- `plugins/xiuxian_game/economy/stock_commands.py` (handle_stock_list): 查看气运行情
- `plugins/xiuxian_game/economy/stock_commands.py` (handle_stock_buy): 买入气运
- `plugins/xiuxian_game/economy/stock_commands.py` (handle_stock_sell): 卖出气运
- `plugins/xiuxian_game/economy/stock_commands.py` (handle_stock_holdings): 查看持仓
- `plugins/xiuxian_game/economy/stock_service_new.py:30-374` (StockService): DI架构的股票交易服务
- `plugins/xiuxian_game/economy/stock_service_new.py:36-45` (手续费配置): 3%手续费，最低1、最高1,000,000
- `plugins/xiuxian_game/economy/stock_service_new.py:42` (持仓限制): 每种股票最多持有100万份
- `plugins/xiuxian_game/economy/stock_service_new.py:45` (价格刷新): 1小时刷新间隔
- `plugins/xiuxian_game/economy/stock_service_new.py:106-191` (buy_stock): 买入逻辑，支持银行账户或现金
- `plugins/xiuxian_game/economy/stock_service_new.py:192-258` (sell_stock): 卖出逻辑，支持存入银行或现金
- `plugins/xiuxian_game/economy/stock_price_engine.py:22-230` (StockPriceEngine): 价格波动引擎
- `plugins/xiuxian_game/economy/stock_price_engine.py:25-33` (TYPE_VOLATILITY): 不同股票类型的波动率
- `plugins/xiuxian_game/economy/stock_price_engine.py:36-40` (MARKET_SENTIMENT): 市场情绪配置
- `plugins/xiuxian_game/economy/stock_price_engine.py:91-134` (_calculate_new_price): 价格计算公式
- `plugins/xiuxian_game/models/stock.py:8-152` (Stock/StockHolding/StockTransaction/StockPriceHistory): 股票相关数据模型
- `plugins/xiuxian_game/economy/stock_commands.py:397-432` (handle_stock_init): 初始化12个股票项目

### 打工系统

- `plugins/xiuxian_game/economy/part_time_job_commands.py` (handle_work): 打工命令处理
- `plugins/xiuxian_game/economy/part_time_job_commands.py` (handle_finish_work): 收工命令处理
- `plugins/xiuxian_game/economy/part_time_job_service_new.py:29-509` (PartTimeJobService): DI架构的打工服务
- `plugins/xiuxian_game/economy/part_time_job_service_new.py:36-173` (JOB_TYPES): 11种工作类型配置
- `plugins/xiuxian_game/economy/part_time_job_service_new.py:176-213` (JOB_LOCATIONS): 4个工作地点配置
- `plugins/xiuxian_game/economy/part_time_job_service_new.py:359-440` (complete_job): 工作完成奖励计算
- `plugins/xiuxian_game/models/part_time_job.py` (PartTimeJob/JobLocation/PlayerJobStats): 打工相关数据模型

### 修炼系统（对比参照）

- `plugins/xiuxian_game/cultivate/core.py:80-234` (handle_cultivate): 修炼主逻辑
- `plugins/xiuxian_game/cultivate/core.py:112-191` (经验计算): 基础经验+多层加成
- `plugins/xiuxian_game/data/config.yaml:38-62` (cultivate配置): 冷却300秒、基础经验50
- `plugins/xiuxian_game/utils.py:20-35` (calculate_level_up_exp): 升级所需经验计算
- `llmdoc/agent/cultivation_and_quest_investigation.md`: 修炼系统详细调研

### 经济系统概览

- `llmdoc/overview/project-overview.md:18` (经济系统): 市场、银行、股票、打工
- `llmdoc/agent/game_balance_analysis_2025_12_01.md`: 游戏平衡分析报告
- `llmdoc/reference/data-models.md:125-129` (经济系统模型): BankAccount、MarketOrder、Stock

---

## Report (The Answers)

### 1. 投资系统的核心机制

诡修仙项目中的"投资系统"包含两个主要子系统：

#### 1.1 银行存款利息系统

**运作机制**:
- 玩家可将金币存入银行账户
- 每次查看余额时自动结算利息
- 利息基于存款余额和时长计算

**阶梯利率** (`bank.py:14-18`):
```python
_TIERS = [
    (100_000, 0.001),   # 10w以内 0.1%/小时
    (500_000, 0.0005),  # 10w-50w 0.05%/小时
    (1_000_000, 0.0001),# 50w-100w 0.01%/小时
    (float("inf"), 0.0) # 100w以上无利息
]
```

**利息计算公式** (`bank.py:37-51`):
- `利息 = 存款余额 × 阶梯利率 × 时长(小时)`
- 单次结息上限: 10,000金币
- 自动更新last_interest时间戳

**关键特性**:
- 被动触发（查看余额时结息）
- 单次结息上限防止无限累积
- 大额存款利率为0，鼓励消费

#### 1.2 股票投资系统（气运投资）

**运作机制**:
- 玩家可买入/卖出12种"气运"（股票）
- 价格每小时更新一次（被动触发）
- 支持现金或银行账户交易

**股票类型** (`stock_commands.py:397-432`):
- 法宝气运（科技股）：3只，波动率0.08-0.10
- 金融气运：2只，波动率0.04-0.05
- 灵气气运（能源股）：2只，波动率0.06-0.07
- 丹药气运（消费股）：2只，波动率0.03-0.04
- 医道气运：1只，波动率0.05
- 材料气运：2只，波动率0.07-0.08

**价格波动机制** (`stock_price_engine.py:91-134`):
```python
综合变化率 = 随机因子 + 趋势因子 + 市场情绪 + 回归因子
新价格 = 当前价格 × (1 + 综合变化率)
```

**关键参数**:
- 随机因子：正态分布，标准差=综合波动率
- 综合波动率 = (类型波动率 + 个股波动率) / 2
- 市场情绪：牛市+2%、熊市-2%、中性0%（随机）
- 回归因子：防止偏离基础价格太远（-偏离度 × 2%）
- 单次变化限制：±20%
- 价格下限：基础价格的20%

**手续费**:
- 买入/卖出均收取3%手续费
- 最低1金币、最高1,000,000金币

**持仓限制**:
- 每种股票最多持有1,000,000份

### 2. 资源流动分析

#### 2.1 银行存款系统

**投入成本**:
- 存款本金（金币）
- 机会成本（金币无法用于其他投资）

**收益类型**:
- 固定收益（阶梯利率）
- 0.1%/小时（10万以内）→ 2.4%/天 → 73%/月
- 0.05%/小时（10-50万）→ 1.2%/天 → 36%/月
- 0.01%/小时（50-100万）→ 0.24%/天 → 7.2%/月
- 0%/小时（100万以上）

**时间周期**:
- 无固定周期
- 随时存取
- 利息实时累积、查看时结算

**风险**:
- 无风险（保本保息）

#### 2.2 股票投资系统

**投入成本**:
- 买入资金 = 股票价格 × 数量 + 3%手续费
- 资金来源：现金或银行账户

**收益类型**:
- 浮动收益（价格波动）
- 正收益：价格上涨
- 负收益：价格下跌

**时间周期**:
- 无固定周期
- 随时买卖
- 价格每小时更新（被动触发）

**风险**:
- 价格波动风险（单次±20%）
- 手续费成本（买入+卖出=6%）
- 最大损失：价格跌至基础价格的20%

#### 2.3 打工系统（对比参照）

**投入成本**:
- 时间成本（2-3分钟）
- 机会成本（无法同时修炼或战斗）

**收益类型**:
- 固定基础收入（60-180金币）
- 等级加成（每级+2%）
- 运气加成（最多50%）
- 连续工作奖励（每天+5金币，最多100）
- 特殊事件奖励（概率触发，-20到+300金币）

**时间周期**:
- 2-3分钟/次
- 频率限制：每小时最多10次、间隔1分钟

**效率** (`part_time_job_commands.py:414-433`):
- 基础工资：60-180金币/次
- 时间：2-3分钟
- 理论效率：1200-5400金币/小时（不计加成）
- 实际效率：考虑加成和特殊事件，约1500-7000金币/小时

#### 2.4 修炼系统（对比参照）

**投入成本**:
- 时间成本（冷却5分钟）
- 阴宅使用费（如使用他人阴宅）

**收益类型**:
- 经验（怨炁）
- 基础经验：50 × (1 + 等级/k) × [0.8-1.2]
- 月卡加成：基础 × 20%-50%
- 转数加成：基础 × 50% × 转数
- 公会加成：基础 × 公会建筑加成
- 阴宅加成：基础 × 阴宅等级加成

**时间周期**:
- 5分钟冷却/次
- 理论效率：12次/小时

**效率** (`cultivation_and_quest_investigation.md:114-149`):
- 基础经验：50 × (1 + 等级/7) × 1.0（平均）
- 10级新手：约71经验/次 → 852经验/小时
- 50级玩家：约407经验/次 → 4884经验/小时
- 考虑加成（月卡+公会+阴宅），实际可达2-5倍

### 3. 平衡性问题分析

#### 3.1 投资收益率对比

**银行存款收益率**:

| 存款额度 | 利率/小时 | 日收益率 | 月收益率 | 年收益率 |
|---------|----------|---------|---------|---------|
| 10万以内 | 0.1% | 2.4% | 73% | 876% |
| 10-50万 | 0.05% | 1.2% | 36% | 438% |
| 50-100万 | 0.01% | 0.24% | 7.2% | 87.6% |
| 100万以上 | 0% | 0% | 0% | 0% |

**关键发现**:
- **10万以内存款收益极高**：年化876%
- **10万是关键分界点**，之后收益腰斩
- 单次结息上限10,000金币有效抑制大额存款收益

**股票投资收益率**:
- **手续费成本**：买入+卖出=6%（盈亏平衡点）
- **价格波动范围**：单次±20%，长期围绕基础价格波动
- **理论收益率**：
  - 短期持有（1天）：-20%至+20%（扣除6%手续费）
  - 中期持有（7天）：受随机游走影响，期望值≈0
  - 长期持有（30天）：受回归因子拉回，期望值≈0

**关键发现**:
- **6%手续费极高**，普通股票交易手续费通常<0.1%
- **随机游走+回归因子**设计意味着长期期望收益为0
- **价格波动是零和游戏**，玩家之间互相转移财富
- **不存在套利机会**，价格完全随机且回归基础价格

**打工系统效率**:
- 理论效率：1200-5400金币/小时（基础）
- 实际效率：1500-7000金币/小时（含加成）
- 时间投入：每小时最多10次，实际约20-30分钟

#### 3.2 与其他经济活动对比

**修炼 vs 投资**:
- 修炼产出：经验（升级、属性提升）
- 投资产出：金币
- **不直接竞争**，资源类型不同

**打工 vs 银行存款**:

假设玩家有10万金币：
- 银行存款：100,000 × 0.1%/小时 = 100金币/小时（被动）
- 打工收入：约1500-7000金币/小时（主动）

**收益比**: 打工效率是银行存款的**15-70倍**

**打工 vs 股票投资**:

假设玩家有10万金币投资股票：
- 股票期望收益：0%（长期）
- 手续费成本：6%
- 时间成本：需关注价格波动、择时买卖
- 风险：价格波动最大可亏80%

**结论**: **打工无风险且效率远高于股票投资**

**银行存款 vs 股票投资**:

假设玩家有10万金币：
- 银行存款：年化876%，无风险
- 股票投资：期望收益0%，6%手续费成本，高风险

**结论**: **银行存款完全优于股票投资**

#### 3.3 无风险套利机会

**发现1：银行存款无风险高收益**
- 10万以内存款年化876%，完全无风险
- 远超任何现实金融产品
- **套利策略**：存满10万，定期领取利息

**发现2：单次结息上限的漏洞**
- 单次结息上限10,000金币
- 但可以通过**频繁查看余额**绕过上限
- **套利策略**：
  1. 存入10万金币
  2. 每100小时查看一次余额（10,000金币利息）
  3. 年化收益：10,000 × (8760/100) = 876,000金币（876%）

**发现3：打工系统效率失衡**
- 打工效率15-70倍于银行存款
- 2-3分钟即可完成，频率限制宽松
- **套利策略**：优先打工积累本金

**发现4：股票投资无吸引力**
- 期望收益0%，6%手续费，高风险
- 无任何理性玩家会选择股票投资
- **设计缺陷**：股票系统形同虚设

#### 3.4 通货膨胀风险

**货币创造速度**:
- 银行存款：10万 × 0.1%/小时 = 100金币/小时（被动）
- 打工：1500-7000金币/小时（主动）
- 修炼：无金币产出
- 战斗：金币产出（数据未调研）

**货币销毁渠道**:
- 物品购买：消耗金币
- 装备修理：消耗金币
- 公会建设：消耗金币
- 转账手续费：3%（销毁）
- 股票交易手续费：6%（销毁）

**关键发现**:
- **银行利息是纯货币创造**，无对应资源消耗
- **单次结息上限10,000金币**有效限制通胀
- **100万以上无利息**鼓励消费，抑制通胀
- **打工系统是主要货币来源**，效率远高于银行

**通胀风险评估**:
- 🟡 中等风险
- 打工系统创造大量货币
- 银行利息创造少量货币（受上限限制）
- 需观察游戏中金币销毁渠道是否充足

**来自游戏平衡分析报告的证据** (`game_balance_analysis_2025_12_01.md:33-42`):
- 最高金币：34.4亿
- 金币中位数：未披露
- **已存在严重通胀**

#### 3.5 平衡性问题总结

| 问题类型 | 严重程度 | 关键指标 | 影响范围 |
|---------|---------|---------|---------|
| 银行存款收益过高 | 🟠 中 | 10万以内年化876% | 货币系统 |
| 股票投资无吸引力 | 🔴 高 | 期望收益0%、手续费6% | 投资系统 |
| 打工效率过高 | 🟡 中低 | 15-70倍银行存款 | 经济平衡 |
| 通货膨胀 | 🔴 高 | 最高金币34.4亿 | 整体经济 |
| 股票系统设计缺陷 | 🔴 高 | 零和游戏+高手续费 | 投资玩法 |

### 4. 相关代码文件清单

#### 银行系统
- `plugins/xiuxian_game/economy/bank.py` - 银行命令处理
- `plugins/xiuxian_game/models/bank_account.py` - 银行账户模型

#### 股票系统
- `plugins/xiuxian_game/economy/stock_commands.py` - 股票命令处理
- `plugins/xiuxian_game/economy/stock_service_new.py` - 股票交易服务（DI架构）
- `plugins/xiuxian_game/economy/stock_service_legacy.py` - 股票交易服务（旧版）
- `plugins/xiuxian_game/economy/stock_price_engine.py` - 价格波动引擎
- `plugins/xiuxian_game/economy/stock_scheduler.py` - 定时任务调度
- `plugins/xiuxian_game/models/stock.py` - 股票数据模型
- `plugins/xiuxian_game/infrastructure/repositories/stock_repository.py` - 股票仓储
- `plugins/xiuxian_game/infrastructure/repositories/stock_holding_repository.py` - 持仓仓储
- `plugins/xiuxian_game/infrastructure/repositories/stock_transaction_repository.py` - 交易记录仓储
- `plugins/xiuxian_game/infrastructure/repositories/bank_account_repository.py` - 银行账户仓储

#### 打工系统
- `plugins/xiuxian_game/economy/part_time_job_commands.py` - 打工命令处理
- `plugins/xiuxian_game/economy/part_time_job_service_new.py` - 打工服务（DI架构）
- `plugins/xiuxian_game/economy/part_time_job_service_legacy.py` - 打工服务（旧版）
- `plugins/xiuxian_game/economy/part_time_job_init.py` - 打工系统初始化
- `plugins/xiuxian_game/models/part_time_job.py` - 打工数据模型
- `plugins/xiuxian_game/infrastructure/repositories/part_time_job_repository.py` - 打工记录仓储
- `plugins/xiuxian_game/infrastructure/repositories/job_location_repository.py` - 工作地点仓储
- `plugins/xiuxian_game/infrastructure/repositories/player_job_stats_repository.py` - 打工统计仓储

#### 其他经济系统
- `plugins/xiuxian_game/economy/market.py` - 市场系统
- `plugins/xiuxian_game/economy/merchants.py` - 商人系统
- `plugins/xiuxian_game/economy/equipment_trade_service_new.py` - 装备交易服务

---

## Conclusions (Key Takeaways)

### 投资系统核心机制

1. **银行存款是阶梯利率系统**，10万以内年化876%，100万以上无利息
2. **股票投资是随机波动系统**，价格每小时更新，长期期望收益为0
3. **手续费高昂**，转账3%、股票交易6%
4. **单次结息上限10,000金币**限制银行利息累积
5. **股票持仓限制100万份**防止垄断

### 资源流动特征

1. **银行存款是被动收益**，无风险但受上限限制
2. **股票投资是零和游戏**，玩家间财富转移，系统收取6%手续费
3. **打工是主动收益**，效率远高于投资（15-70倍银行存款）
4. **修炼产出经验**，与投资系统资源类型不同，不直接竞争
5. **转账手续费3%销毁货币**，抑制通胀

### 平衡性关键问题

1. **银行存款10万以内收益过高**，年化876%远超合理范围
2. **股票投资完全无吸引力**，期望收益0%+6%手续费+高风险，理性玩家不会选择
3. **打工效率远超投资**，导致投资系统形同虚设
4. **通货膨胀严重**，最高金币34.4亿，银行+打工是主要货币来源
5. **股票系统设计缺陷**，随机游走+回归因子+高手续费=无吸引力

### 无风险套利机会

1. **存满10万金币定期领取利息**，年化876%无风险收益
2. **优先打工积累本金**，效率15-70倍于银行存款
3. **完全不投资股票**，期望收益为负（手续费）
4. **频繁查看余额绕过单次结息上限**（设计漏洞）
5. **大额存款分散到多账号**，规避100万无利息限制（如果支持多账号）

### 与其他经济活动对比

1. **打工 > 银行存款 > 股票投资**（收益率排序）
2. **修炼与投资不冲突**，资源类型不同（经验 vs 金币）
3. **战斗产出未调研**，可能是另一主要金币来源
4. **市场交易未调研**，可能是货币销毁渠道
5. **装备修理、公会建设是货币销毁渠道**，需评估是否充足

---

## Relations (Code Relationships)

### 银行系统代码关系

```
economy/bank.py (命令处理)
    ↓ 使用
models/bank_account.py (BankAccount模型)
    ↓ 通过
models/db.py (safe_session)
    ↓ 关联
models/player.py (Player.gold)
```

### 股票系统代码关系

```
economy/stock_commands.py (命令处理)
    ↓ 调用
economy/stock_service_new.py (StockService)
    ↓ 使用
infrastructure/repositories/stock_repository.py (StockRepository)
infrastructure/repositories/stock_holding_repository.py (StockHoldingRepository)
infrastructure/repositories/stock_transaction_repository.py (StockTransactionRepository)
infrastructure/repositories/bank_account_repository.py (BankAccountRepository)
    ↓ 操作
models/stock.py (Stock/StockHolding/StockTransaction/StockPriceHistory)
    ↓ 价格更新
economy/stock_price_engine.py (StockPriceEngine)
    ↓ 定时调度
economy/stock_scheduler.py (StockMarketScheduler)
```

### 打工系统代码关系

```
economy/part_time_job_commands.py (命令处理)
    ↓ 调用
economy/part_time_job_service_new.py (PartTimeJobService)
    ↓ 使用
infrastructure/repositories/part_time_job_repository.py (PartTimeJobRepository)
infrastructure/repositories/job_location_repository.py (JobLocationRepository)
infrastructure/repositories/player_job_stats_repository.py (PlayerJobStatsRepository)
    ↓ 操作
models/part_time_job.py (PartTimeJob/JobLocation/PlayerJobStats)
    ↓ 奖励发放
models/player.py (Player.gold)
```

### DI架构集成关系

```
infrastructure/uow/unit_of_work.py (UnitOfWork)
    ↓ 提供
infrastructure/repositories/* (各Repository)
    ↓ 注入到
economy/*_service_new.py (各Service)
    ↓ 被调用
economy/*_commands.py (各命令处理器)
```

---

**调查者**: Scout Agent
**调查日期**: 2025-12-02
**报告版本**: 1.0
