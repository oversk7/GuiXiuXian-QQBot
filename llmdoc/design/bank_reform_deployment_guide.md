# 银行系统改革部署指南

**创建日期**: 2025-12-03
**改革版本**: v1.0 (简化版)
**预计影响**: 所有玩家

---

## 📋 改革概要

### 核心变化

1. **✅ 已完成: 一步到位取消存款利息**
   - 直接删除所有利息计算代码,不分阶段
   - 原因: 利息是纯货币创造,导致严重通货膨胀(最高金币34.4亿)
   - 实施方式: 立即生效,不逐步降低

2. **✅ 已完成: 新增活期理财产品**
   - 最低投资: 1万金币
   - 最高投资: 100万金币
   - 日收益: ±5% (随机波动)
   - 管理费: 0.1%/天 (货币Sink)
   - 期望收益: 0 (防止套利)

3. **⏸️ 暂缓实施: 贷款/保险/VIP**
   - 实施难度较高
   - 等活期理财稳定后再考虑

---

## 🗂️ 修改的文件清单

### 核心修改 (必看)

| 文件 | 修改内容 | 影响 |
|-----|---------|------|
| `economy/bank.py` | 删除所有利息计算逻辑 | **破坏性变更** |
| `models/bank_fund.py` | 新增理财产品数据模型 | 新功能 |
| `models/auto_migrate.py` | 新增理财表自动创建 | 数据库变更 |

### 新增文件

| 文件 | 作用 |
|-----|------|
| `economy/bank_fund_service.py` | 理财产品核心业务逻辑 |
| `economy/bank_fund_commands.py` | 理财命令处理器 |
| `economy/bank_fund_scheduler.py` | 每日结算定时任务 |
| `infrastructure/repositories/bank_fund_repository.py` | 理财基金仓储 |
| `infrastructure/repositories/fund_holding_repository.py` | 理财持仓仓储 |

---

## 🚀 部署步骤

### Step 1: 数据备份 (必做!)

```bash
# 备份银行账户数据
mysqldump xiuxian_db bank_account > backup_bank_account_20251203.sql

# 备份玩家金币数据
mysqldump xiuxian_db players --where="gold > 0" > backup_player_gold_20251203.sql
```

### Step 2: 停止Bot

```bash
# 停止运行中的Bot
# (根据你的部署方式,可能是Ctrl+C或systemctl stop)
```

### Step 3: 更新代码

```bash
cd D:\QQbot\GuiXiuXian2

# 拉取最新代码 (如果使用git)
git pull

# 或者直接替换修改的文件
```

### Step 4: 启动Bot (自动迁移数据库)

```bash
python bot.py
```

**观察日志输出**,应该看到:

```
🔍 [自动迁移] 检查数据库结构...
  📊 创建表: bank_fund
  📊 创建表: fund_holding
✅ [自动迁移] 完成！创建了 2 个表，添加了 0 个字段，0 个索引
```

### Step 5: 验证功能

在QQ群测试以下命令:

```
1. 余额          # 应该看到"已取消存款利息"的公告
2. 理财产品      # 应该看到冥界活期理财基金
3. 购买理财 10000  # 测试购买功能
4. 我的理财      # 查看持仓
```

---

## 📢 玩家公告模板

建议在群里发布以下公告:

```
📢 银行系统重大改革公告
━━━━━━━━━━━━━

⚠️ 改革原因:
旧银行利息导致严重通货膨胀,
最高金币已达34.4亿,
物价飞涨,新手无法生存。

🎯 核心变化:
1️⃣ 立即取消存款利息 (一步到位)
   • 银行不再提供躺赚收益
   • 存款仍然安全,随时存取
   • 不分阶段,立即生效

2️⃣ 新增活期理财产品
   • 最低投资1万,最高100万
   • 每日收益波动±5%
   • 每日扣除0.1%管理费
   • 期望收益为0,需要技巧

3️⃣ 转账手续费不变
   • 仍为3%
   • 未来可能降低至1%

💡 为什么必须改革?
老玩家囤积数十亿金币,
新手买不起装备,
游戏经济濒临崩溃。

🎮 新玩法:
理财产品不是躺赚,而是博弈:
• 高手可以择时赎回,赚取差价
• 菜鸟可能亏损,需要学习

⏱️ 生效时间: 立即生效
📖 详细说明: 使用【理财产品】查看
```

---

## ⚠️ 风险评估与应对

### 预期玩家反馈

| 反馈类型 | 概率 | 应对措施 |
|---------|------|---------|
| **"凭什么取消利息"** | 🔴 高 | 解释通胀危害,强调是为了游戏健康 |
| **"理财亏钱了"** | 🟠 中 | 强调期望收益为0,需要技巧 |
| **"不会玩理财"** | 🟡 中低 | 提供新手教程,限制投资金额 |

### 回滚方案 (紧急情况)

如果玩家反馈极差,需要回滚:

```bash
# 1. 停止Bot
# 2. 恢复数据库
mysql xiuxian_db < backup_bank_account_20251203.sql

# 3. 回退代码
git revert HEAD

# 4. 重启Bot
python bot.py
```

---

## 📊 监控指标

部署后需要观察以下数据:

### 每日监控

```sql
-- 1. 理财参与人数
SELECT COUNT(DISTINCT player_id) FROM fund_holding WHERE is_active = 1;

-- 2. 理财总规模
SELECT SUM(current_value) FROM fund_holding WHERE is_active = 1;

-- 3. 昨日收益率
SELECT daily_return FROM bank_fund WHERE fund_type = 'lively';

-- 4. 管理费销毁量
SELECT SUM(current_value * 0.001) FROM fund_holding WHERE is_active = 1;
```

### 每周监控

- 玩家投诉数量
- 理财参与率 (参与人数/活跃玩家)
- 货币总量变化
- 物价水平变化

---

## 🔧 常见问题处理

### Q1: 数据库表没有自动创建

**解决方案**:
```bash
# 手动执行SQL
mysql xiuxian_db < create_bank_fund_tables.sql
```

### Q2: 定时任务没有执行

**检查步骤**:
1. 查看 `bot.py` 是否导入了 `bank_fund_scheduler`
2. 查看日志是否有错误
3. 手动触发一次结算测试:
   ```python
   # 在Python shell中
   from plugins.xiuxian_game.economy.bank_fund_scheduler import daily_fund_settlement
   await daily_fund_settlement()
   ```

### Q3: 玩家无法购买理财

**排查步骤**:
1. 检查玩家金币是否足够
2. 检查投资金额是否在1万-100万范围内
3. 查看数据库日志是否有报错

---

## 📝 后续迭代计划

### Phase 2 (3个月后)
- 新增定期理财产品 (7天/30天)
- 收益率更高,但锁定期

### Phase 3 (6个月后)
- 新增VIP服务
- 付费获得游戏增益,月费作为货币Sink

### Phase 4 (12个月后)
- 新增贷款系统
- 利息作为货币Sink

---

## ✅ 部署检查清单

部署前确认:

- [ ] 已备份 `bank_account` 表
- [ ] 已备份 `players` 表
- [ ] 已测试 `余额` 命令
- [ ] 已测试 `理财产品` 命令
- [ ] 已测试 `购买理财` 命令
- [ ] 已测试 `我的理财` 命令
- [ ] 已准备玩家公告文案
- [ ] 已准备回滚方案

部署后确认:

- [ ] 数据库表自动创建成功
- [ ] 所有命令正常响应
- [ ] 定时任务正常执行 (次日确认)
- [ ] 玩家反馈收集
- [ ] 货币总量监控

---

## 📞 联系支持

如遇到问题,请:
1. 查看Bot日志
2. 查看数据库日志
3. 检查 `llmdoc/design/bank_system_redesign_2025_12_03.md` 设计文档
4. 在GitHub Issues提问

---

**部署责任人**: (填写)
**部署日期**: 2025-12-03
**回滚责任人**: (填写)
**监控负责人**: (填写)
