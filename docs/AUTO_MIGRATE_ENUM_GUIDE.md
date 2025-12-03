# auto_migrate ENUM 自动修复指南

## 概述

`auto_migrate.py` 现在支持自动检测和修复 MySQL ENUM 类型不匹配的问题，无需手动执行 SQL 脚本。

## 问题背景

### MySQL ENUM 的限制

MySQL ENUM 类型有以下限制：
1. **不能直接添加值**：不支持 `ALTER ENUM ADD VALUE`
2. **必须重建列**：修改 ENUM 值需要删除并重新创建列
3. **容易不同步**：代码中的 Python Enum 和数据库 ENUM 容易不一致

### 历史问题

之前两次遇到 ENUM 同步问题：
```
LookupError: 'tutorial' is not among the defined enum values
LookupError: 'torture_cult_raid' is not among the defined enum values
```

每次都需要：
1. 手动创建 SQL 脚本
2. 执行迁移
3. 验证结果

现在这个过程完全自动化了！

## 工作原理

### 1. 配置定义（`auto_migrate.py`）

在 `REQUIRED_ENUMS` 中定义期望的 ENUM 值：

```python
REQUIRED_ENUMS: Dict[str, Dict[str, List[str]]] = {
    "daily_task": {
        "task_type": [
            "ghost_elimination",
            "pen_spirit_case",
            "fake_immortal_cult",
            "shape_shifter_hunt",
            "stone_curse_break",
            "torture_cult_raid",
            "tutorial",
        ],
    },
}
```

### 2. 自动检测

Bot 启动时，`auto_migrate()` 会：
1. 读取数据库中 ENUM 列的实际值
2. 与 `REQUIRED_ENUMS` 中的期望值对比
3. 检测缺失值和多余值

### 3. 自动修复

如果发现不匹配，执行安全的6步重建流程：

```sql
-- 1. 创建临时列备份数据
ALTER TABLE daily_task ADD COLUMN task_type_temp_migration VARCHAR(100);

-- 2. 复制现有数据
UPDATE daily_task SET task_type_temp_migration = task_type;

-- 3. 删除旧 ENUM 列
ALTER TABLE daily_task DROP COLUMN task_type;

-- 4. 创建新 ENUM 列（包含所有期望值）
ALTER TABLE daily_task ADD COLUMN task_type ENUM(
    'ghost_elimination','pen_spirit_case','fake_immortal_cult',
    'shape_shifter_hunt','stone_curse_break','torture_cult_raid','tutorial'
) NOT NULL COMMENT '任务类型';

-- 5. 恢复数据
UPDATE daily_task SET task_type = task_type_temp_migration;

-- 6. 删除临时列
ALTER TABLE daily_task DROP COLUMN task_type_temp_migration;
```

## 使用方法

### 场景1：添加新的任务类型

假设你要添加一个新任务类型 `treasure_hunt`：

1. **在 Python 代码中添加枚举值**（`models/daily_task.py`）：
```python
class TaskType(Enum):
    GHOST_ELIMINATION = "ghost_elimination"
    PEN_SPIRIT_CASE = "pen_spirit_case"
    # ... 其他类型 ...
    TREASURE_HUNT = "treasure_hunt"  # 新增
```

2. **在 auto_migrate.py 中添加配置**：
```python
REQUIRED_ENUMS = {
    "daily_task": {
        "task_type": [
            "ghost_elimination",
            "pen_spirit_case",
            "fake_immortal_cult",
            "shape_shifter_hunt",
            "stone_curse_break",
            "torture_cult_raid",
            "tutorial",
            "treasure_hunt",  # 新增
        ],
    },
}
```

3. **重启 Bot**

Bot 启动时会自动检测并添加新值！

### 场景2：添加新的 ENUM 列

假设你在另一个表中添加了 ENUM 列：

```python
REQUIRED_ENUMS = {
    "daily_task": {
        "task_type": [...],
        "difficulty": ["easy", "normal", "hard", "nightmare"],  # 新列
    },
    "player": {
        "vip_level": ["bronze", "silver", "gold", "platinum"],  # 新表
    },
}
```

### 场景3：查看自动迁移日志

Bot 启动时会输出详细日志：

```
🔍 [自动迁移] 检查数据库结构...
  🔧 修复 ENUM 列: daily_task.task_type
     缺失值: treasure_hunt
     ✅ 修复完成
✅ [自动迁移] 完成！创建了 0 个表，添加了 0 个字段，0 个索引，修复了 1 个 ENUM 列
```

如果没有需要修复的：
```
🔍 [自动迁移] 检查数据库结构...
✓ [自动迁移] 数据库结构已是最新
```

## 安全保障

### 1. 事务保护

所有操作在一个事务中执行：
```python
async with engine.begin() as conn:
    await _fix_enum_columns(conn, verbose)
```

发生错误时自动回滚。

### 2. 数据备份

使用临时列保存数据：
- 重建前：数据复制到 `{column_name}_temp_migration`
- 重建后：数据恢复到新列
- 完成后：删除临时列

### 3. 属性保留

重建时保留列的所有属性：
- `NOT NULL` / `NULL`
- `DEFAULT` 值
- `COMMENT` 注释

### 4. 错误处理

发生错误时：
1. 记录详细错误日志
2. 自动清理临时列
3. 回滚事务
4. Bot 继续启动（不会因 ENUM 问题而崩溃）

## 性能影响

### 检测开销
- **时间**：每个 ENUM 列约 10-50ms（执行 SHOW COLUMNS）
- **锁**：无锁，不影响其他操作

### 修复开销
- **时间**：每个列约 100-500ms（取决于表大小）
- **锁**：需要表锁（ALTER TABLE），但通常很快
- **触发**：仅在发现不匹配时才执行

### 优化建议
- ENUM 值发生变化时，Bot 首次启动会较慢（需要重建）
- 后续启动会快速跳过（检测到已匹配）
- 避免频繁修改 ENUM 定义

## 技术细节

### 代码结构

```
auto_migrate.py
├── REQUIRED_ENUMS          # 配置：期望的 ENUM 值
├── auto_migrate()          # 主入口：执行所有迁移
├── _fix_enum_columns()     # ENUM 修复入口
├── _get_enum_values()      # 获取数据库中的实际值
└── _rebuild_enum_column()  # 重建 ENUM 列
```

### 正则解析 ENUM

从 `SHOW COLUMNS` 结果中提取值：
```python
column_type = "enum('value1','value2','value3')"
enum_values = re.findall(r"'([^']*)'", column_type)
# => ['value1', 'value2', 'value3']
```

### 集合对比

使用 Python 集合高效对比：
```python
expected_set = set(expected_values)
actual_set = set(actual_values)

missing_values = expected_set - actual_set   # 缺失的值
extra_values = actual_set - expected_set     # 多余的值
```

## 故障排查

### 问题1：Bot 启动时报 ENUM 错误

**症状**：
```
LookupError: 'xxx' is not among the defined enum values
```

**原因**：
- `REQUIRED_ENUMS` 配置缺失或不完整
- 代码中的 Enum 定义与配置不一致

**解决**：
1. 检查 `auto_migrate.py` 中的 `REQUIRED_ENUMS`
2. 确保包含所有 Python Enum 中定义的值
3. 重启 Bot

### 问题2：ENUM 值没有自动添加

**症状**：
Bot 启动日志显示 "数据库结构已是最新"，但实际缺少值

**原因**：
- `REQUIRED_ENUMS` 配置错误
- 表名或列名拼写错误

**解决**：
```python
# 检查配置是否正确
REQUIRED_ENUMS = {
    "daily_task": {  # 表名必须正确
        "task_type": [...]  # 列名必须正确
    }
}
```

### 问题3：重建失败，临时列未清理

**症状**：
数据库中存在 `{column_name}_temp_migration` 列

**原因**：
- 重建过程中断（如数据库重启）
- 权限不足

**解决**：
手动删除临时列：
```sql
ALTER TABLE daily_task DROP COLUMN task_type_temp_migration;
```

然后重启 Bot。

## 最佳实践

### 1. 保持代码和配置同步

**每次修改 Python Enum 时，同步更新 `REQUIRED_ENUMS`：**

```python
# ❌ 错误：只修改了代码
class TaskType(Enum):
    NEW_TYPE = "new_type"  # 添加了新值

# ✅ 正确：同步修改配置
REQUIRED_ENUMS = {
    "daily_task": {
        "task_type": [..., "new_type"]  # 同步添加
    }
}
```

### 2. 添加注释

在配置中添加注释，方便维护：

```python
REQUIRED_ENUMS = {
    "daily_task": {
        "task_type": [
            # 常规任务（v1.0）
            "ghost_elimination",
            "pen_spirit_case",
            "fake_immortal_cult",
            "shape_shifter_hunt",
            "stone_curse_break",

            # 扩展任务（v1.1）
            "torture_cult_raid",

            # 新手任务（v1.2）
            "tutorial",
        ],
    },
}
```

### 3. 测试前备份

虽然有事务保护，但大规模修改前建议备份：

```bash
mysqldump -u root -p guixiuxian_db > backup_$(date +%Y%m%d).sql
```

### 4. 查看变更历史

使用 Git 跟踪 `auto_migrate.py` 的修改：

```bash
git log -p -- plugins/xiuxian_game/models/auto_migrate.py
```

## 与手动 SQL 脚本对比

| 特性 | 手动 SQL 脚本 | auto_migrate |
|------|--------------|--------------|
| **执行方式** | 手动连接数据库执行 | Bot 启动自动执行 |
| **易用性** | 需要创建脚本 | 只需修改配置 |
| **出错率** | 容易遗漏值 | 自动对比，不会遗漏 |
| **可追溯** | 需要保存脚本文件 | Git 记录配置变更 |
| **环境迁移** | 每个环境都要执行 | 新环境首次启动自动执行 |
| **数据安全** | 手动控制 | 事务保护 |

## 未来改进方向

### 1. 自动从 Enum 类提取值

目前需要手动维护 `REQUIRED_ENUMS`，未来可以自动扫描：

```python
# 自动从 TaskType 类提取值
from .daily_task import TaskType

REQUIRED_ENUMS = {
    "daily_task": {
        "task_type": [e.value for e in TaskType],  # 自动提取
    },
}
```

### 2. ENUM 值使用统计

检测数据库中未使用的 ENUM 值，建议清理：

```sql
SELECT task_type, COUNT(*) FROM daily_task GROUP BY task_type;
```

如果某个值从未使用，可能已废弃。

### 3. 支持 PostgreSQL

PostgreSQL 的 ENUM 类型支持 `ALTER TYPE ADD VALUE`，实现更简单：

```sql
ALTER TYPE task_type_enum ADD VALUE 'new_value';
```

## 参考资料

- [MySQL ENUM 文档](https://dev.mysql.com/doc/refman/8.0/en/enum.html)
- [SQLAlchemy Enum 类型](https://docs.sqlalchemy.org/en/20/core/type_basics.html#sqlalchemy.types.Enum)
- [项目 auto_migrate 源码](../plugins/xiuxian_game/models/auto_migrate.py)

## 总结

`auto_migrate` 的 ENUM 支持让数据库迁移更加简单：

✅ **无需手动 SQL**：配置即可
✅ **自动检测**：启动时自动对比
✅ **安全可靠**：事务保护，数据备份
✅ **易于维护**：Git 跟踪变更历史

遇到 ENUM 问题时，只需：
1. 更新 `REQUIRED_ENUMS` 配置
2. 重启 Bot
3. 验证日志

就这么简单！🎉
