# 修复 daily_task.task_type ENUM 列（v2）

## 问题描述

启动 bot 时报错：
```
LookupError: 'torture_cult_raid' is not among the defined enum values.
Enum name: tasktype.
Possible values: GHOST_ELIMI.., PEN_SPIRIT_.., FAKE_IMMORT.., ..., TUTORIAL
```

## 根本原因

**MySQL ENUM 类型的局限性**：

1. 代码中的 Python 枚举定义了 **7 个任务类型**：
   ```python
   # plugins/xiuxian_game/models/daily_task.py
   class TaskType(Enum):
       GHOST_ELIMINATION = "ghost_elimination"
       PEN_SPIRIT_CASE = "pen_spirit_case"
       FAKE_IMMORTAL_CULT = "fake_immortal_cult"
       SHAPE_SHIFTER_HUNT = "shape_shifter_hunt"
       STONE_CURSE_BREAK = "stone_curse_break"
       TORTURE_CULT_RAID = "torture_cult_raid"   # ⚠️ 数据库缺失
       TUTORIAL = "tutorial"
   ```

2. 数据库的 ENUM 列**缺少部分值**，导致 SQLAlchemy 无法正确映射

3. MySQL ENUM 的限制：
   - 不能直接 `ALTER ENUM ADD VALUE`
   - 必须重建整个列

## 解决方案

### 方案1：执行 SQL 脚本（推荐）

**执行前请备份数据库！**

```bash
# 连接数据库执行
mysql -u用户名 -p数据库名 < fix_daily_task_enum_v2.sql

# 或者在 MySQL 命令行中
mysql> source /path/to/fix_daily_task_enum_v2.sql;
```

脚本会：
1. 创建临时 VARCHAR 列保存数据
2. 删除旧的 ENUM 列
3. 创建包含所有 7 个值的新 ENUM 列
4. 恢复数据
5. 删除临时列

### 方案2：使用 auto_migrate.py（未来推荐）

⚠️ **注意**：当前的 `auto_migrate.py` 不支持修改 ENUM 类型。

如果要支持，需要扩展 `auto_migrate.py`：
- 检测 ENUM 值差异
- 自动重建 ENUM 列

## 执行验证

执行后检查：

```sql
-- 1. 查看表结构
SHOW CREATE TABLE daily_task;

-- 应该看到：
-- task_type enum('ghost_elimination','pen_spirit_case','fake_immortal_cult',
--               'shape_shifter_hunt','stone_curse_break','torture_cult_raid',
--               'tutorial') NOT NULL COMMENT '任务类型'

-- 2. 查看现有数据
SELECT DISTINCT task_type FROM daily_task;

-- 3. 测试插入新类型
INSERT INTO daily_task (player_id, task_type, title, description, ...)
VALUES ('test', 'torture_cult_raid', '测试', '测试');
```

## 历史问题

### v1 脚本的问题

之前的 `fix_daily_task_enum.sql` 包含了一个**不存在的任务类型** `cursed_painting`，导致：
- 数据库包含无用的枚举值
- 可能导致混淆

### 修复历史

1. **第一次错误**：缺少 `tutorial`
   - 提交：`0dab22c` 和 `6755f0b`
   - 但脚本包含了错误的 `cursed_painting`

2. **第二次错误**：缺少 `torture_cult_raid`（当前问题）
   - v2 脚本修复：移除 `cursed_painting`，确保所有 7 个类型都存在

## 预防措施

### 1. 代码规范

在 `models/daily_task.py` 添加注释：
```python
class TaskType(Enum):
    """任务类型枚举

    ⚠️ 修改此枚举后，必须更新数据库 ENUM 列！
    执行：fix_daily_task_enum_v2.sql
    """
```

### 2. 单元测试

创建测试检查 ENUM 一致性：
```python
def test_task_type_enum_matches_database():
    """确保代码中的 TaskType 枚举与数据库 ENUM 列一致"""
    code_values = {e.value for e in TaskType}
    db_values = get_enum_values_from_db("daily_task", "task_type")
    assert code_values == db_values
```

### 3. 迁移工具改进

扩展 `auto_migrate.py` 支持 ENUM 类型检测和自动修复。

## 相关文件

- `plugins/xiuxian_game/models/daily_task.py` - TaskType 枚举定义
- `plugins/xiuxian_game/models/auto_migrate.py` - 自动迁移系统
- `fix_daily_task_enum_v2.sql` - 本次修复脚本
- `fix_daily_task_enum.sql` (已废弃) - v1 脚本，包含错误的 cursed_painting

## 技术细节

### 为什么 SQLAlchemy 不能自动处理？

SQLAlchemy ORM 会在启动时验证：
1. Python 枚举的值
2. 数据库 ENUM 列的允许值

如果不匹配，会抛出 `LookupError`，防止数据不一致。

### 为什么不用 Alembic？

1. 项目使用 `auto_migrate.py` 自动迁移系统
2. Alembic 对 ENUM 类型的支持也需要手动处理
3. 直接 SQL 更简单、更可控

## 总结

✅ **立即执行**：`fix_daily_task_enum_v2.sql`
✅ **确保包含**：所有 7 个任务类型
✅ **验证成功**：bot 启动无错误
🔜 **未来改进**：扩展 auto_migrate 支持 ENUM 检测
