# daily_task.task_type ENUM 修复指南

## 问题描述

Bot 启动时遇到错误：
```
LookupError: 'torture_cult_raid' is not among the defined enum values
```

**根本原因**: 数据库中 `daily_task.task_type` ENUM 列缺少 `torture_cult_raid` 值，但数据表中存在该值的记录，导致 SQLAlchemy 无法读取数据。

---

## 🚀 快速修复方案（推荐）

### 方案 1: 使用 Python 验证脚本

```bash
# 1. 检查当前状态
python verify_and_fix_enum.py

# 2. 根据输出决定后续操作
```

### 方案 2: 直接执行 SQL 修复

```bash
# Windows (使用 MySQL 客户端)
mysql -u your_user -p your_database < fix_enum_immediate.sql

# 或在 MySQL Workbench 中打开 fix_enum_immediate.sql 并执行
```

### 方案 3: 重启 Bot（已改进 auto_migrate）

```bash
# auto_migrate 已改进，现在可以安全地修复 ENUM 问题
python bot.py
```

---

## 📋 修复步骤详解

### 步骤 1: 验证当前状态

运行验证脚本查看详细信息：

```bash
python verify_and_fix_enum.py
```

**预期输出**：
```
============================================================
检查 daily_task.task_type ENUM 状态
============================================================

1️⃣ 获取 ENUM 定义...
   当前 ENUM 定义: enum('ghost_elimination','pen_spirit_case',...)
   包含的值: ['ghost_elimination', 'pen_spirit_case', ...]

2️⃣ 检查数据中实际存在的值...
   数据中的值:
     - ghost_elimination: 10 条记录 ✅
     - torture_cult_raid: 5 条记录 ❌ 不在ENUM中

3️⃣ 与代码定义对比...
   ❌ ENUM 中缺少的值: {'torture_cult_raid'}

4️⃣ 修复建议:
   需要在 ENUM 中添加: {'torture_cult_raid'}
```

### 步骤 2: 执行修复（选择一种方法）

#### 方法 A: SQL 脚本修复（最安全）

1. 打开 `fix_enum_immediate.sql`
2. 检查数据库名称（默认是 `guixiuxian2`）
3. 执行 SQL 脚本：

```bash
# 命令行
mysql -u root -p guixiuxian2 < fix_enum_immediate.sql

# 或使用 MySQL Workbench
# File -> Open SQL Script -> fix_enum_immediate.sql -> Execute
```

**脚本执行内容**：
- 创建临时列
- 复制数据
- 删除旧 ENUM 列
- 创建新 ENUM 列（包含所有 7 个值）
- 恢复数据
- 验证完整性
- 删除临时列

#### 方法 B: 重启 Bot（依赖改进的 auto_migrate）

```bash
# 改进后的 auto_migrate 会自动检测并修复 ENUM 问题
python bot.py
```

**改进内容**：
- ✅ 修复前验证现有数据
- ✅ 分步恢复数据，便于诊断
- ✅ 修复后验证数据完整性
- ✅ 增强日志输出

### 步骤 3: 验证修复结果

再次运行验证脚本：

```bash
python verify_and_fix_enum.py
```

**预期输出**：
```
============================================================
检查 daily_task.task_type ENUM 状态
============================================================

...

3️⃣ 与代码定义对比...
   ✅ ENUM 定义与代码完全一致

============================================================
✅ ENUM 状态正常，无需修复
============================================================
```

### 步骤 4: 启动 Bot

```bash
python bot.py
```

---

## 🔍 问题根因分析

详细调查报告：`llmdoc/agent/auto_migrate_enum_fix_investigation.md`

### 核心问题

原 `auto_migrate.py` 的 `_rebuild_enum_column` 函数存在以下缺陷：

| 问题 | 影响 | 状态 |
|------|------|------|
| 修复前未验证现有数据 | 数据恢复失败 | ✅ 已修复 |
| UPDATE 无异常处理 | 数据丢失无法察觉 | ✅ 已修复 |
| 缺少完整性验证 | 无法确认修复成功 | ✅ 已修复 |
| 日志信息不足 | 难以诊断问题 | ✅ 已修复 |

### 改进内容

**新增步骤**：
1. **步骤 0**: 验证现有数据中的所有值都在新 ENUM 中
2. **步骤 5**: 分步恢复数据（按值分组，便于诊断）
3. **步骤 6**: 验证数据恢复完整性
4. **增强日志**: 打印现有数据值、新 ENUM 值、恢复进度

**代码位置**: `plugins/xiuxian_game/models/auto_migrate.py:363-500`

---

## 📊 修复前后对比

### 修复前（问题版本）

```python
# 原代码：直接 UPDATE，无验证
steps = [
    ...,
    f"UPDATE {table_name} SET {column_name} = {temp_column}",  # 可能失败
    ...
]

for step_sql in steps:
    await conn.execute(text(step_sql))  # 无返回值检查
```

### 修复后（当前版本）

```python
# 新代码：验证 + 分步恢复 + 完整性检查

# 1. 验证现有数据
actual_data_values = {row[0] for row in result.fetchall()}
unsupported_values = actual_data_values - set(new_values)
if unsupported_values:
    raise ValueError(f"数据中存在新 ENUM 不支持的值: {unsupported_values}")

# 2. 分步恢复数据
total_restored = 0
for value in actual_data_values:
    result = await conn.execute(text(update_sql), {"value": value})
    total_restored += result.rowcount
    print(f"恢复值 '{value}': {result.rowcount} 行")

# 3. 验证完整性
orphaned_count = (await conn.execute(text(verify_sql))).scalar()
if orphaned_count > 0:
    raise ValueError(f"数据恢复不完整: {orphaned_count} 行数据未能恢复")
```

---

## 🔧 文件清单

### 新增文件

| 文件 | 用途 | 说明 |
|------|------|------|
| `fix_enum_immediate.sql` | SQL 修复脚本 | 手动执行修复，最安全 |
| `verify_and_fix_enum.py` | 验证脚本 | 检查 ENUM 状态，提供诊断 |
| `ENUM_FIX_GUIDE.md` | 使用指南 | 本文档 |

### 修改文件

| 文件 | 修改内容 | 代码行 |
|------|---------|--------|
| `plugins/xiuxian_game/models/auto_migrate.py` | 改进 `_rebuild_enum_column` 函数 | 363-500 |

### 相关文件（未修改）

| 文件 | 说明 |
|------|------|
| `plugins/xiuxian_game/models/daily_task.py` | TaskType 枚举定义（正确） |
| `plugins/xiuxian_game/models/auto_migrate.py` | REQUIRED_ENUMS 配置（正确） |

---

## ⚠️ 注意事项

### 执行 SQL 脚本前

1. **备份数据库**（强烈推荐）：
   ```bash
   mysqldump -u root -p guixiuxian2 > backup_before_enum_fix.sql
   ```

2. **检查数据库名称**：
   - 修改 `fix_enum_immediate.sql` 第 13 行的数据库名称

3. **确保有足够权限**：
   - 需要 ALTER TABLE 权限

### 重启 Bot 前

1. **确认改进的 auto_migrate 已部署**：
   - 检查 `auto_migrate.py` 是否包含新的验证逻辑

2. **查看启动日志**：
   - 观察 ENUM 修复的详细输出
   - 确认 "✓ 数据恢复完整" 消息

---

## 🆘 常见问题

### Q1: 执行 SQL 脚本后仍然报错

**可能原因**：
- SQL 脚本执行失败（中途中断）
- 数据库名称不匹配

**解决方法**：
1. 检查 SQL 执行日志，查看哪一步失败
2. 运行 `verify_and_fix_enum.py` 查看当前状态
3. 手动执行失败的步骤

### Q2: auto_migrate 启动时没有修复

**可能原因**：
- auto_migrate 代码未更新
- 启动时遇到其他错误提前退出

**解决方法**：
1. 确认 `auto_migrate.py` 已更新（检查 line 393-415）
2. 查看启动日志，搜索 "验证现有数据"
3. 使用方案 2（SQL 脚本）手动修复

### Q3: 验证脚本无法运行

**可能原因**：
- 数据库连接配置问题
- Python 环境问题

**解决方法**：
1. 检查 `plugins/xiuxian_game/models/db.py` 的数据库配置
2. 确认虚拟环境已激活
3. 直接使用 SQL 脚本（方案 2）

---

## 📚 相关文档

- **调查报告**: `llmdoc/agent/auto_migrate_enum_fix_investigation.md`
- **auto_migrate 使用指南**: `docs/AUTO_MIGRATE_ENUM_GUIDE.md`
- **数据库迁移最佳实践**: System Reminder 中的说明

---

## ✅ 修复验证清单

完成修复后，请确认以下所有项：

- [ ] `verify_and_fix_enum.py` 输出 "✅ ENUM 状态正常"
- [ ] SQL 查询 `SHOW COLUMNS FROM daily_task LIKE 'task_type'` 显示所有 7 个值
- [ ] SQL 查询 `SELECT DISTINCT task_type FROM daily_task` 成功返回所有值
- [ ] Bot 成功启动，无 ENUM 相关错误
- [ ] 日常任务功能正常（可接取、完成任务）

---

**修复完成时间**: 2025-12-03
**文档版本**: 1.0
**维护者**: Claude Code (tr:scout agent)
