# _apply_interest 函数调查报告

**调查日期**: 2025-12-06
**调查范围**: 银行系统利息计算相关代码
**问题类型**: 已废弃函数的悬空导入
**严重程度**: 🟡 中（代码已注释，无实际风险，但存在导入不匹配）

---

## 执行摘要

项目中存在一个被废弃的函数 `_apply_interest()`：
- **银行系统改革时间**: 2025-12-03 (commit 7ac4f4c)
- **改革原因**: 利息是纯货币创造，导致严重通货膨胀（最高金币34.4亿）
- **当前状态**: 函数已被注释移除，但 `rankings.py` 仍在导入和调用它（第206-208行）
- **影响**: 财富榜排行命令在结息阶段会失败（ImportError）

---

## 代码证据

### 1. 银行系统中_apply_interest的定义和废弃过程

**历史版本** (commit 7ac4f4c^，改革前):
```
plugins/xiuxian_game/economy/bank.py - 第1-30行

_TIERS = [
    (10_000, 0.001),      # 0-1w 0.1%/小时
    (50_000, 0.0005),     # 1w-5w 0.05%/小时
    (100_000, 0.0002),    # 5w-10w 0.02%/小时
    (500_000, 0.0001),    # 10w-50w 0.01%/小时
    (1_000_000, 0.0001),  # 50w-100w 0.01%
    (float("inf"), 0.0)   # 100w 以上无利息
]

def _tier_rate(balance: int) -> float:
    for limit, rate in _TIERS:
        if balance <= limit:
            return rate
    return 0.0

def _apply_interest(acc: BankAccount):
    now = datetime.now()
    delta_hours = (now - acc.last_interest).total_seconds() / 3600
    if delta_hours <= 0 or acc.balance <= 0:
        acc.last_interest = now
        return 0
    gain = int(acc.balance * _tier_rate(acc.balance) * delta_hours)
    # 单次结息上限 1w
    cap = 10_000
    if gain > cap:
        gain = cap
    if gain > 0:
        acc.balance += gain
    acc.last_interest = now
    return gain
```

**当前版本** (commit 7ac4f4c，改革后):
`plugins/xiuxian_game/economy/bank.py:28-31`
```python
# 旧利息计算函数已废弃
# def _apply_interest(acc: BankAccount):
#     """已于2025-12-03废弃，不再计算利息"""
#     pass
```

### 2. rankings.py中的悬空导入和调用

**文件**: `plugins/xiuxian_game/player/rankings.py:202-212`

```python
# 批量查询银行余额并结息以确保余额最新
bank_stmt = select(BankAccount).where(BankAccount.player_id.in_(player_ids))
bank_accounts = (await session.execute(bank_stmt)).scalars().all()
# 结息，保持与【存款榜】一致的口径
from ..economy.bank import _apply_interest  # ← 第206行：导入不存在的函数
for acc in bank_accounts:
    _apply_interest(acc)  # ← 第208行：调用不存在的函数
if bank_accounts:
    session.add_all(bank_accounts)
    await session.commit()
bank_map = {acc.player_id: acc.balance for acc in bank_accounts}
```

**调用位置**: `wealth_rank_cmd.handle()` 函数（财富榜排行命令）

---

## 问题分析

### 问题1：函数存在状态不一致

| 文件 | 状态 | 详情 |
|-----|------|------|
| `bank.py` | ❌ 已移除 | 函数被注释掉，不再存在 |
| `rankings.py` | ❌ 仍在使用 | 第206行导入，第208行调用 |

### 问题2：ImportError风险

当用户执行 `【财富榜】` 命令时，会触发以下错误：
```
ImportError: cannot import name '_apply_interest' from 'plugins.xiuxian_game.economy.bank'
```

**触发路径**:
```
用户命令【财富榜】
    ↓
wealth_rank_cmd.handle() (rankings.py:165)
    ↓
从bank导入_apply_interest (rankings.py:206)
    ↓
ImportError: 函数不存在
    ↓
命令失败
```

### 问题3：逻辑不匹配

**改革内容**:
- 取消了存款利息机制
- 删除了_tier_rate()函数（利息等级计算）
- 删除了_apply_interest()函数（利息应用）

**当前代码**:
- `bank.py` 完全移除了利息相关代码 ✅
- `bank.py:248` 注释: "已取消利息计算，直接排序"
- `rankings.py` 仍在调用利息结算 ❌

**gap**:
- 两个文件的改革不同步
- rankings.py注释(205行)说"结息，保持与【存款榜】一致的口径"
- 但存款榜(bank.py:248)已取消利息，不再结息

---

## 修复方案

### 方案A：完全移除利息结算（推荐）

**原因**：
1. 银行改革已取消利息，不需要结息
2. 存款榜已不再结息（bank.py:248）
3. 财富榜应保持一致的口径

**修改**:
`plugins/xiuxian_game/player/rankings.py:202-212`

从:
```python
# 批量查询银行余额并结息以确保余额最新
bank_stmt = select(BankAccount).where(BankAccount.player_id.in_(player_ids))
bank_accounts = (await session.execute(bank_stmt)).scalars().all()
# 结息，保持与【存款榜】一致的口径
from ..economy.bank import _apply_interest
for acc in bank_accounts:
    _apply_interest(acc)
if bank_accounts:
    session.add_all(bank_accounts)
    await session.commit()
bank_map = {acc.player_id: acc.balance for acc in bank_accounts}
```

改为:
```python
# 批量查询银行余额（已取消利息结算）
bank_stmt = select(BankAccount).where(BankAccount.player_id.in_(player_ids))
bank_accounts = (await session.execute(bank_stmt)).scalars().all()
# 已取消利息机制（参见bank.py:13-16），直接使用现有余额
bank_map = {acc.player_id: acc.balance for acc in bank_accounts}
```

**优势**:
- 简化代码，移除废弃函数调用
- 与存款榜实现一致
- 符合银行改革的设计意图

### 方案B：在bank.py中保留_apply_interest函数（不推荐）

**缺点**:
1. 与银行改革的设计意图相悖
2. 会重新引入通货膨胀机制
3. 只有财富榜结息，存款榜不结息，逻辑不一致

---

## 影响范围

### 受影响的用户交互路径

| 命令 | 文件 | 行号 | 影响等级 |
|-----|-----|-----|--------|
| 【财富榜】 | rankings.py | 165-278 | 🔴 高（命令失败） |
| 【财富榜 页码】 | rankings.py | 165-278 | 🔴 高（命令失败） |
| 【排行榜】 | rankings.py | 449-476 | 🟡 中（入口正常，但财富榜失败） |

### 风险评估

- **当前状态**: 代码可以导入但会在运行时失败
- **发现时机**: 需要用户实际执行财富榜命令才会显现
- **影响范围**: 仅限财富榜排行命令，其他命令无关

---

## 相关文档和提交

### 银行系统改革文档

**投资系统反套利实施** (2025-12-02):
- `/design/investment_anti_arbitrage_redesign.md` - 反套利设计方案
- `/design/investment_implementation_summary.md` - 实施总结

**银行系统改革说明**:
- `bank.py:12-16` - 改革公告注释
- commit 7ac4f4c - "feature: 银行系统更新"

### 相关改革内容

**来源**: commit 7ac4f4c (2025-12-03)
```
feature: 银行系统更新

修改内容:
- 取消存款利息机制
- 新增银行投资理财（理财产品）
- 将利息改为零和博弈的管理费
- 原因：防止通货膨胀
```

---

## BankAccount模型字段分析

**文件**: `plugins/xiuxian_game/models/bank_account.py`

```python
class BankAccount(Base):
    player_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    balance: Mapped[int] = mapped_column(BigInteger, default=0)
    last_interest: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())
    player: Mapped["Player"] = relationship(...)
```

**字段说明**:
- `balance` - 存款余额
- `last_interest` - 上次结息时间

**字段废弃说明**:
- `last_interest` 字段仍然存在于数据库中
- 但已不再使用（改革后不再计算利息）
- 保留原因：数据库迁移成本与向后兼容

---

## 建议的完整修复步骤

### 第1步：修改rankings.py
修改 `plugins/xiuxian_game/player/rankings.py:202-212`，移除_apply_interest导入和调用。

### 第2步：验证功能
测试【财富榜】命令是否正常工作，验证：
1. 命令无ImportError
2. 财富值计算正确（面板金币 + 银行余额 + 投资价值）
3. 排行榜排序符合预期

### 第3步：可选清理
未来数据库迁移时，可考虑：
- 在bank_account表中移除last_interest字段（已无业务用途）
- 或保留以备将来功能扩展

---

## 总结

| 项目 | 详情 |
|-----|------|
| **问题类型** | 已废弃函数的悬空导入 |
| **严重程度** | 🟡 中 |
| **影响命令** | 【财富榜】排行命令 |
| **根本原因** | 银行改革时未同步更新rankings.py |
| **修复难度** | 🟢 低（仅需删除3行代码） |
| **建议方案** | 方案A：完全移除利息结算（与存款榜保持一致） |
| **估计工作量** | 5分钟 |

---

## 相关命令行证据

### Git提交信息
```bash
commit 7ac4f4c1ecfb40c97781c9761cbc10fe1011db86
Author: OverSky <seuoversky@qq.com>
Date:   Wed Dec 3 14:06:31 2025 +0800

    feature: 银行系统更新
    - 取消存款利息
    - 新增理财产品系统
    - 修改费用模式为管理费
```

### 代码搜索结果
```bash
$ grep -r "_apply_interest" plugins/
plugins/xiuxian_game/economy/bank.py:28:# def _apply_interest(acc: BankAccount):
plugins/xiuxian_game/player/rankings.py:206:from ..economy.bank import _apply_interest
plugins/xiuxian_game/player/rankings.py:208:_apply_interest(acc)
```

---

## 建议下一步行动

1. ✅ **立即修复**: 删除rankings.py中的_apply_interest导入和调用（5分钟）
2. ✅ **验证**: 执行【财富榜】命令进行功能测试
3. 📋 **未来优化**: 考虑在数据库迁移中移除last_interest字段
4. 📚 **文档更新**: 在architecture/economic-system.md中说明利息机制的移除
