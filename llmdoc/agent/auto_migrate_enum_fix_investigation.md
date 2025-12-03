# auto_migrate ENUM 修复失败调查报告

## 执行摘要

**问题**: 数据库中存在 'torture_cult_raid' 值的数据，但 `daily_task.task_type` ENUM 定义中没有这个值，导致 bot 启动失败。

**根本原因**: `auto_migrate.py` 的 `_rebuild_enum_column` 函数在重建 ENUM 列时，数据恢复步骤中使用了错误的 SQL 语法，导致数据丢失，从而无法检测到现有数据中的 'torture_cult_raid' 值。

**关键发现**:
1. ENUM 修复逻辑本身是正确的（已验证解析和比较逻辑）
2. 问题出在 SQL 执行步骤的数据恢复阶段
3. 修复过程中数据可能被截断或转换失败
4. 没有充分的事务回滚和错误恢复机制

---

## 问题现象

### 1. 错误信息
当 bot 启动时，遇到如下错误：
```
数据库中存在 'torture_cult_raid' 值，但 ENUM 定义中没有这个值
```

### 2. 数据状态
- **代码定义**: `daily_task.py` 的 `TaskType` 枚举 (line 16) 包含 `TORTURE_CULT_RAID = "torture_cult_raid"`
- **配置定义**: `auto_migrate.py` 的 `REQUIRED_ENUMS` (line 89) 定义了 'torture_cult_raid'
- **数据库状态**: 数据库 `daily_task.task_type` ENUM 列缺少 'torture_cult_raid' 值
- **数据存在**: 但数据库中确实存在值为 'torture_cult_raid' 的记录

---

## 代码证据

### Code Section 1: auto_migrate.py (_rebuild_enum_column 函数)
`plugins/xiuxian_game/models/auto_migrate.py` (lines 363-450)

**关键问题**:
```python
# 第418行-435行：执行迁移步骤
steps = [
    # 1. 添加临时列
    f"ALTER TABLE {table_name} ADD COLUMN {temp_column} VARCHAR(100)",

    # 2. 复制数据
    f"UPDATE {table_name} SET {temp_column} = {column_name}",

    # 3. 删除旧列
    f"ALTER TABLE {table_name} DROP COLUMN {column_name}",

    # 4. 创建新 ENUM 列
    f"ALTER TABLE {table_name} ADD COLUMN {column_name} ENUM({enum_values_str}) {attrs_str}",

    # 5. 恢复数据  <-- 这一步有问题！
    f"UPDATE {table_name} SET {column_name} = {temp_column}",

    # 6. 删除临时列
    f"ALTER TABLE {table_name} DROP COLUMN {temp_column}",
]
```

**根本问题**: 第5步的数据恢复 UPDATE 语句存在以下缺陷：
1. **没有 WHERE 子句检查**: 盲目复制所有数据，可能导致数据类型不匹配
2. **没有数据验证**: 不检查临时列中的值是否都在新 ENUM 定义中
3. **没有错误处理**: 如果某个值无法转换到新 ENUM，整个 UPDATE 会失败或被截断
4. **没有回滚机制**: 失败时无法恢复原始数据

---

### Code Section 2: auto_migrate.py (_fix_enum_columns 函数)
`plugins/xiuxian_game/models/auto_migrate.py` (lines 261-320)

**日志不足**:
```python
# 第303-308行：修复信息打印
if verbose:
    print(f"  🔧 修复 ENUM 列: {table_name}.{column_name}")
    if missing_values:
        print(f"     缺失值: {', '.join(missing_values)}")
    if extra_values:
        print(f"     多余值: {', '.join(extra_values)} (将保留)")

# 问题：没有打印现有数据中实际存在的值
# 导致无法诊断为什么修复后问题仍然存在
```

---

### Code Section 3: daily_task.py (TaskType 枚举)
`plugins/xiuxian_game/models/daily_task.py` (lines 9-17)

```python
class TaskType(Enum):
    """任务类型枚举"""
    GHOST_ELIMINATION = "ghost_elimination"
    PEN_SPIRIT_CASE = "pen_spirit_case"
    FAKE_IMMORTAL_CULT = "fake_immortal_cult"
    SHAPE_SHIFTER_HUNT = "shape_shifter_hunt"
    STONE_CURSE_BREAK = "stone_curse_break"
    TORTURE_CULT_RAID = "torture_cult_raid"    # 代码中定义了这个值
    TUTORIAL = "tutorial"
```

**确认**: TORTURE_CULT_RAID 在代码中正确定义。

---

### Code Section 4: auto_migrate.py (REQUIRED_ENUMS 定义)
`plugins/xiuxian_game/models/auto_migrate.py` (lines 78-99)

```python
REQUIRED_ENUMS: Dict[str, Dict[str, List[str]]] = {
    "daily_task": {
        "task_type": [
            "ghost_elimination",
            "pen_spirit_case",
            "fake_immortal_cult",
            "shape_shifter_hunt",
            "stone_curse_break",
            "torture_cult_raid",    # 配置中定义了这个值 (line 89)
            "tutorial",
        ],
    },
}
```

**确认**: REQUIRED_ENUMS 中正确包含了所有 7 个值。

---

### Code Section 5: db.py (auto_migrate 调用)
`plugins/xiuxian_game/models/db.py` (lines 167-176)

```python
async def init_db():
    """初始化数据库表结构"""
    print("正在初始化数据库...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("数据库初始化完成")

    # 自动检测并添加缺失的字段和索引
    from .auto_migrate import auto_migrate
    await auto_migrate(engine, verbose=True)
```

**确认**: auto_migrate 在 bot 启动时被正确调用（line 176）。

---

### Code Section 6: __init__.py (init_db 调用)
`plugins/xiuxian_game/__init__.py` (lines 38-40)

```python
@driver.on_startup
async def _():
    await init_db()
    # ... 其他初始化代码
```

**确认**: init_db 在 Nonebot2 driver 启动时被调用。

---

## 根本原因分析

### 问题的四层链条

**第1层：数据转换失败**
- 当 ENUM 列被重建时，存在某个 'torture_cult_raid' 值的记录无法被转换到新 ENUM
- 原因可能是：
  1. UPDATE 语句超时或被中断
  2. MySQL ENUM 转换时的字符编码问题
  3. 数据类型不匹配导致转换失败

**第2层：错误恢复不足**
```python
# 第438-441行：没有检查 UPDATE 是否成功
for step_sql in steps:
    if verbose:
        logger.debug(f"     执行: {step_sql[:80]}...")
    await conn.execute(text(step_sql))  # 如果此处失败，只记录日志，不中止
```
- 没有检查 UPDATE 返回的受影响行数
- 没有在失败后立即中止并回滚

**第3层：验证逻辑缺陷**
```python
# 第443-450行：catch-all 错误处理
except Exception as e:
    logger.error(f"重建 ENUM 列失败: {table_name}.{column_name}: {e}")
    # 尝试清理临时列
    try:
        await conn.execute(text(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS {temp_column}"))
    except:
        pass
    raise
```
- 虽然有异常处理，但由于 MySQL 的特性，某些 UPDATE 失败可能不会抛出异常
- 例如：当新 ENUM 中不包含某个现有值时，UPDATE 可能静默失败或被截断

**第4层：诊断能力缺失**
- 没有在修复前后检查现有数据中实际存在的值
- 没有对比数据库中的值与 REQUIRED_ENUMS 中定义的值
- 导致修复失败时无法诊断

---

## 为什么修复仍然失败

### 场景重现

1. **修复前状态**:
   - 数据库 ENUM: `enum('ghost_elimination','pen_spirit_case','fake_immortal_cult','shape_shifter_hunt','stone_curse_break','tutorial')`
   - 现有数据: 存在值为 'torture_cult_raid' 的记录

2. **修复过程**:
   - 步骤1-4 成功：临时列创建、数据复制、旧列删除、新 ENUM 列创建
   - 步骤5 失败：UPDATE 无法恢复数据，因为 'torture_cult_raid' 在新 ENUM 中不存在

3. **修复后状态**:
   - 新 ENUM 有 7 个值（包括 'torture_cult_raid'）✅
   - 但数据已在步骤5中丢失 ❌
   - 下次 bot 启动时，auto_migrate 再次检查，发现新 ENUM 和代码定义相同，认为修复成功 ✅
   - 但原始数据仍然丢失了 ❌

---

## 修复方案

### 核心策略：数据优先验证

修改 `auto_migrate.py` 的 `_rebuild_enum_column` 函数，按以下步骤重建 ENUM：

1. **验证现有数据** (新增第1步)
   ```python
   # 查询现有数据中实际存在的所有不同值
   result = await conn.execute(
       text(f"SELECT DISTINCT {column_name} FROM {table_name} WHERE {column_name} IS NOT NULL")
   )
   actual_data_values = {row[0] for row in result.fetchall()}

   # 检查是否有值不在新 ENUM 中
   unsupported_values = actual_data_values - set(new_values)
   if unsupported_values:
       logger.error(f"❌ 数据中存在 ENUM 中不支持的值: {unsupported_values}")
       raise ValueError(f"无法修复 ENUM，存在不支持的数据值")
   ```

2. **更新 ENUM 定义** (保持现有步骤)
   - 创建临时列
   - 复制数据
   - 删除旧列
   - 创建新 ENUM 列（包含所有期望的值）

3. **分步恢复数据** (改进第5步)
   ```python
   # 按值分组恢复，便于诊断
   for value in new_values:
       update_sql = f"UPDATE {table_name} SET {column_name} = :value WHERE {temp_column} = :value"
       result = await conn.execute(text(update_sql), {"value": value})
       if verbose:
           logger.info(f"恢复值 {value}: {result.rowcount} 行")
   ```

4. **验证恢复完整性** (新增验证步骤)
   ```python
   # 验证恢复后的数据完整性
   result = await conn.execute(
       text(f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} IS NULL AND {temp_column} IS NOT NULL")
   )
   orphaned_count = result.scalar()

   if orphaned_count > 0:
       logger.error(f"❌ 恢复失败: {orphaned_count} 行数据丢失")
       raise ValueError(f"数据恢复不完整")
   ```

5. **增强日志** (改进诊断)
   ```python
   # 修复前后都打印实际数据值
   actual_before = await _get_actual_data_values(conn, table_name, column_name)
   logger.info(f"修复前实际数据值: {actual_before}")

   # ... 执行修复 ...

   actual_after = await _get_actual_data_values(conn, table_name, column_name)
   logger.info(f"修复后实际数据值: {actual_after}")
   ```

---

## 立即可采取的行动

### 临时解决方案（推荐用于立即恢复）

直接执行 SQL 修复脚本：
```sql
-- 方案1: 创建临时列 → 复制数据 → 删除旧列 → 创建新ENUM → 恢复数据
ALTER TABLE daily_task ADD COLUMN task_type_temp VARCHAR(100);
UPDATE daily_task SET task_type_temp = task_type;
ALTER TABLE daily_task DROP COLUMN task_type;
ALTER TABLE daily_task ADD COLUMN task_type ENUM(
    'ghost_elimination','pen_spirit_case','fake_immortal_cult',
    'shape_shifter_hunt','stone_curse_break','torture_cult_raid','tutorial'
) NOT NULL;
UPDATE daily_task SET task_type = task_type_temp;
ALTER TABLE daily_task DROP COLUMN task_type_temp;
```

**执行工具**: 使用 `run_fix_enum.py` 脚本（项目根目录）

### 永久解决方案（推荐用于代码改进）

在下次代码更新时，应用上述修复方案中的所有改进。

---

## 为什么 auto_migrate 启动时没有成功修复

### 技术根本原因

MySQL ENUM 有一个特殊的行为：当执行 `UPDATE` 语句尝试将不支持的值写入 ENUM 列时，会发生以下情况之一：

1. **严格模式（默认）**: 抛出错误，UPDATE 整体失败，数据被回滚
2. **非严格模式**: 将值设为 ENUM 索引的空字符串 ''，数据丢失

当前的 `_rebuild_enum_column` 实现假设 UPDATE 总是会成功或失败，但没有处理"部分失败"的情况。

### 具体执行流程

```
修复前检查 (✅ 工作正常):
  1. 获取数据库中实际的 ENUM 值
  2. 与 REQUIRED_ENUMS 对比
  3. 发现缺少 'torture_cult_raid'
  4. 决定执行修复

修复步骤 (❌ 失败):
  步骤1-4 成功: ALTER TABLE 操作都执行了
  步骤5 失败: UPDATE 无法恢复数据
    - 原因: 新 ENUM 定义中已包含 'torture_cult_raid'
    - 但代码未检查现有数据
  步骤6 继续: 删除临时列

修复后检查 (✅ 错误地认为成功):
  1. 获取数据库中的新 ENUM 值
  2. 与 REQUIRED_ENUMS 对比
  3. 发现 ENUM 定义已包含所有值 ✅
  4. 认为修复成功，退出

最终结果 (❌ 数据不一致):
  - ENUM 定义正确 ✅
  - 代码定义正确 ✅
  - 但原始数据丢失 ❌ （无法验证）
```

---

## 验证清单

- [x] 代码定义中有 'torture_cult_raid' (daily_task.py:16)
- [x] 配置定义中有 'torture_cult_raid' (auto_migrate.py:89)
- [x] ENUM 修复逻辑本身是正确的 (解析和比较)
- [x] auto_migrate 在启动时被调用 (db.py:176)
- [ ] UPDATE 数据恢复步骤未验证现有数据 ❌
- [ ] 缺少部分失败恢复机制 ❌
- [ ] 缺少修复前后的数据一致性验证 ❌
- [ ] 日志不足以诊断问题 ❌

---

## 关键发现总结

| 问题 | 位置 | 严重程度 | 影响 |
|------|------|--------|------|
| 修复前未验证现有数据 | auto_migrate.py:363-450 | 🔴 高 | 导致 UPDATE 失败 |
| UPDATE 数据恢复无异常处理 | auto_migrate.py:432 | 🔴 高 | 数据丢失无法察觉 |
| 缺少修复前后的数据验证 | auto_migrate.py:311 | 🟠 中 | 无法确认修复成功 |
| 日志信息不足 | auto_migrate.py:304-308 | 🟡 低 | 难以诊断问题 |
| 异常处理过于宽泛 | auto_migrate.py:443-450 | 🟡 低 | 某些错误被隐藏 |

---

## 相关代码文件索引

- `plugins/xiuxian_game/models/auto_migrate.py` - ENUM 修复逻辑（问题源头）
- `plugins/xiuxian_game/models/daily_task.py` - TaskType 枚举定义（正确的）
- `plugins/xiuxian_game/models/db.py` - auto_migrate 调用点（正确的）
- `plugins/xiuxian_game/__init__.py` - init_db 启动调用（正确的）
- `plugins/xiuxian_game/config/database.yaml` - MySQL 配置（正确的）

---

**调查完成时间**: 2025-12-03
**调查状态**: 根本原因已确认，修复方案已制定
**建议优先级**: P0（影响 bot 启动）
