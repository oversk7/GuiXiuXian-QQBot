# 每日任务（委托）统计异常调查报告

**调查日期**: 2025-12-06
**调查人员**: Scout Agent
**报告版本**: 1.0
**严重级别**: 🔴 高 - 统计数据完全错误，影响玩家体验和成就系统

---

## 代码位置总览 (Code Sections)

### 核心文件清单
- `plugins/xiuxian_game/models/daily_task.py:1-144` - DailyTask数据模型和TaskStatus枚举
- `plugins/xiuxian_game/infrastructure/repositories/daily_task_repository.py:109-151` - 统计查询实现
- `plugins/xiuxian_game/daily_task/commands.py:24-434` - 统计命令处理
- `plugins/xiuxian_game/daily_task/service_new.py:269-290` - 汇总统计服务

---

## 问题描述

### 现象
玩家使用【任务统计】和【委托统计】命令时，显示的"本周完成"和"总计完成"统计数字**永远为0**，即使玩家已完成多个任务。

### 根本原因

#### 问题1：数据模型层的类型不一致（P0 Critical）

**文件**: `plugins/xiuxian_game/models/daily_task.py:49`

```python
status: Mapped[str] = mapped_column(String(20), default="available", comment="任务状态")
```

**问题分析**:
- `status`字段定义为`String(20)`，即字符串类型
- 模型中定义了`TaskStatus`枚举（第20-25行），但**未被应用到字段映射**
- 任务完成时（第100行），状态被设置为字符串字面量`"completed"`

#### 问题2：Repository统计查询使用了Enum对象而非字符串（P0 Critical）

**文件**: `plugins/xiuxian_game/infrastructure/repositories/daily_task_repository.py:124-127`和`144-147`

```python
# count_weekly_completed方法
stmt = select(func.count(DailyTask.id)).where(
    and_(
        DailyTask.player_id == player_id,
        DailyTask.status == TaskStatus.COMPLETED,  # ❌ 使用Enum对象而非字符串值
        DailyTask.task_date >= week_start
    )
)

# count_total_completed方法
stmt = select(func.count(DailyTask.id)).where(
    and_(
        DailyTask.player_id == player_id,
        DailyTask.status == TaskStatus.COMPLETED  # ❌ 同样的问题
    )
)
```

**问题分析**:
- SQLAlchemy在构建SQL WHERE子句时，会将`TaskStatus.COMPLETED`（Enum对象）转换为其字符串表示
- 但由于`status`字段是`String(20)`而不是`Enum`类型，SQLAlchemy无法进行自动类型转换
- 最终SQL查询变成: `WHERE status == '<enum 'TaskStatus'>'` 或类似的非预期值
- 数据库中存储的是`"completed"`，永远无法匹配查询条件

#### 问题3：过期任务查询同样使用了Enum对象（P1 高）

**文件**: `plugins/xiuxian_game/infrastructure/repositories/daily_task_repository.py:166`

```python
DailyTask.status.in_([TaskStatus.AVAILABLE, TaskStatus.ACCEPTED])  # ❌ 使用Enum列表
```

虽然这个查询的影响可能被掩盖（因为字符串比较可能有部分匹配），但原理上同样存在问题。

---

## 统计路径分析

### 调用链路

```
命令处理:
┌─ handle_task_stats (commands.py:385-434)
│  └─ task_service.get_task_summary(player.id) (service_new.py:269)
│     └─ self._daily_task_repo.count_weekly_completed(player.id, week_start)
│     │  └─ DailyTaskRepository.count_weekly_completed() (repository.py:109-132)
│     │     └─ SQL: SELECT COUNT(*) FROM daily_task
│     │           WHERE player_id = ?
│     │           AND status = TaskStatus.COMPLETED  ❌ 类型错误
│     │           AND task_date >= ?
│     │
│     └─ self._daily_task_repo.count_total_completed(player.id)
│        └─ DailyTaskRepository.count_total_completed() (repository.py:134-151)
│           └─ SQL: SELECT COUNT(*) FROM daily_task
│                 WHERE player_id = ?
│                 AND status = TaskStatus.COMPLETED  ❌ 类型错误
```

### 影响范围

| 影响点 | 位置 | 显示效果 | 严重度 |
|--------|------|----------|--------|
| 【任务统计】命令 | commands.py:383-434 | 本周完成、总计完成永远为0 | 🔴 高 |
| 【每日委托】汇总 | commands.py:67, 105-108 | 统计信息错误 | 🔴 高 |
| 成就系统 | achievement_integration_fix报告显示的财富成就检查 | 可能导致基于任务完成数的成就无法触发 | 🔴 高 |
| 公会任务统计 | guild_task_service_new.py | 委托完成数统计异常 | 🟠 中 |

---

## 技术根本原因

### SQLAlchemy ORM类型系统不匹配

当SQLAlchemy遇到以下情况时会产生类型转换错误：

```python
# 模型定义
status: Mapped[str] = mapped_column(String(20))

# 查询条件
DailyTask.status == TaskStatus.COMPLETED  # Enum对象与String字段

# SQLAlchemy的处理过程
1. 识别TaskStatus.COMPLETED是Python Enum对象
2. 尝试将其转换为SQL表达式
3. 由于status是String字段（而非Enum字段），转换结果不可预测
4. 可能生成: "status = '<TaskStatus.COMPLETED: 'completed'>'" 或其他错误
5. 数据库比较: "completed" != "<TaskStatus.COMPLETED: 'completed'>" ❌ 不匹配
```

### 为什么状态检查方法能工作

**在内存对象检查中**（daily_task.py:79-106）:
```python
def is_completed(self) -> bool:
    return self.status == "completed"  # ✅ 字符串字面量，能正确匹配
```

这些方法能正确工作，因为：
1. 在Python代码中，`self.status`已是从数据库读取的字符串`"completed"`
2. 直接与字符串字面量比较，不涉及SQLAlchemy类型转换

但Repository统计查询无法工作，因为：
1. 查询条件在构建SQL时需要进行类型转换
2. Enum对象无法正确转换为String字段的WHERE条件

---

## 修复方案

### 方案对比

| 方案 | 成本 | 影响 | 推荐度 |
|------|------|------|--------|
| A: 修改Repository使用字符串值 | 低 | 最小 | ⭐⭐⭐⭐⭐ |
| B: 将字段改为Enum类型 | 中 | 需数据库迁移 | ⭐⭐⭐⭐ |
| C: 同时实施A和B | 中 | 完整优化 | ⭐⭐⭐⭐⭐ |

### 推荐修复（方案A - 快速修复）

**文件**: `plugins/xiuxian_game/infrastructure/repositories/daily_task_repository.py`

**第127行**:
```python
# 修改前
DailyTask.status == TaskStatus.COMPLETED

# 修改后
DailyTask.status == TaskStatus.COMPLETED.value
# 或直接使用
DailyTask.status == "completed"
```

**第147行**:
```python
# 修改前
DailyTask.status == TaskStatus.COMPLETED

# 修改后
DailyTask.status == TaskStatus.COMPLETED.value
```

**第166行** (过期任务查询):
```python
# 修改前
DailyTask.status.in_([TaskStatus.AVAILABLE, TaskStatus.ACCEPTED])

# 修改后
DailyTask.status.in_([TaskStatus.AVAILABLE.value, TaskStatus.ACCEPTED.value])
# 或
DailyTask.status.in_(["available", "accepted"])
```

### 长期优化（方案B - 模型改进）

**文件**: `plugins/xiuxian_game/models/daily_task.py:49`

```python
# 改进前
status: Mapped[str] = mapped_column(String(20), default="available", comment="任务状态")

# 改进后
status: Mapped[str] = mapped_column(
    SQLEnum(TaskStatus, values_callable=lambda x: [e.value for e in x]),
    default=TaskStatus.AVAILABLE.value,
    comment="任务状态"
)
```

这样做的好处：
- SQLAlchemy会自动处理Enum和字符串的转换
- 提供类型安全性
- Repository中可以使用`TaskStatus.COMPLETED`而无需`.value`

---

## 测试验证建议

### 单元测试
1. 创建测试任务，标记为"completed"状态
2. 调用Repository的count_weekly_completed()，验证返回值>0
3. 调用Repository的count_total_completed()，验证返回值>0
4. 验证统计结果与实际数据库记录数相符

### 集成测试
1. 模拟玩家完成3个任务的全流程
2. 使用【任务统计】命令，验证"本周完成"、"总计完成"显示正确数字
3. 使用【每日委托】命令，验证任务统计汇总信息正确
4. 验证成就系统中基于任务完成数的成就能正确触发

---

## 关键影响评估

### 对玩家体验的影响

| 系统 | 影响 | 用户感受 |
|------|------|----------|
| 任务统计显示 | 永远显示0 | "我完成了那么多任务，为什么统计是0？" |
| 周任务追踪 | 无法追踪周完成进度 | 无法了解每周完成情况 |
| 成就系统 | 基于任务完成数的成就无法触发 | 成就无法获得，觉得系统有bug |
| 公会任务 | 委托完成统计错误 | 公会活跃度统计不准 |

### 数据一致性风险
- 玩家完成的任务数量与显示的统计数字严重不符
- 无法审计玩家真实的任务完成历史
- 影响经济平衡计算（完成任务获得经验金币的分析）

---

## 其他发现

### 相关的编码规范问题

1. **TaskStatus枚举定义完整但未充分使用**
   - 模型中定义了完整的TaskStatus枚举
   - 但字段映射和Repository查询中的使用不一致
   - 建议：在代码审查中加入"Enum与数据库字段映射检查"

2. **缺少类型检查**
   - 没有明确要求Repository方法使用`.value`获取枚举值
   - 建议：在Service层或Repository层添加类型检查

---

## 修复优先级

**立即修复（P0）**:
- daily_task_repository.py 第127、147行：修改统计查询条件

**本周修复（P1）**:
- daily_task_repository.py 第166行：修改过期任务查询条件
- daily_task.py 第49行：改进status字段的Enum映射
- 添加单元测试验证统计查询正确性

**长期优化（P2）**:
- 代码审查规范中加入ORM类型映射检查
- 为所有Enum字段添加类型检查

---

## 总结

**问题根本原因**:
数据模型层将`status`字段定义为`String`类型，但Repository统计查询使用了`Enum`对象进行比较，导致SQLAlchemy无法正确转换WHERE条件，最终数据库查询无法匹配任何记录。

**影响范围**:
所有任务统计功能失效，包括【任务统计】命令、【每日委托】汇总信息、成就系统中基于任务完成数的检查等。

**修复方案**:
修改Repository查询条件，使用`TaskStatus.COMPLETED.value`或直接使用字符串`"completed"`替代Enum对象。同时改进模型定义，使status字段正确映射Enum类型。

