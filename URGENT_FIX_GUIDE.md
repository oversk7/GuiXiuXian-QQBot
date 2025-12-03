# 🚨 紧急修复指南 - ENUM 问题

## 当前问题

即使执行了SQL脚本和重启bot，仍然报错：
```
LookupError: 'torture_cult_raid' is not among the defined enum values
```

## 🔍 诊断步骤

### 第 1 步：诊断当前状态

在 MySQL 客户端中执行：

```bash
mysql -u用户名 -p数据库名
```

然后运行诊断SQL：

```sql
source D:/QQbot/GuiXiuXian2/diagnose_enum.sql
```

**或者逐条执行**：

```sql
-- 查看ENUM定义
SHOW COLUMNS FROM daily_task LIKE 'task_type';

-- 查看表记录数
SELECT COUNT(*) FROM daily_task;

-- 用十六进制查看数据（绕过ENUM检查）
SELECT HEX(task_type) as hex_value, COUNT(*) as count
FROM daily_task
GROUP BY hex_value;
```

---

## 🛠️ 修复方案

### 方案 A：强制重建列（推荐）

这个方案会彻底删除并重建 task_type 列：

```bash
mysql -u用户名 -p数据库名 < force_fix_enum.sql
```

**或者在MySQL客户端中**：

```sql
source D:/QQbot/GuiXiuXian2/force_fix_enum.sql
```

### 方案 B：手动逐步修复

如果方案A失败，手动执行以下步骤：

#### 1. 清理临时列

```sql
ALTER TABLE daily_task DROP COLUMN IF EXISTS task_type_temp;
ALTER TABLE daily_task DROP COLUMN IF EXISTS task_type_temp_migration;
ALTER TABLE daily_task DROP COLUMN IF EXISTS task_type_backup;
```

#### 2. 检查当前ENUM定义

```sql
SHOW COLUMNS FROM daily_task LIKE 'task_type';
```

**预期看到**：包含7个值的ENUM，包括 'torture_cult_raid'

#### 3. 如果ENUM定义正确但仍报错

这说明数据中有**无效值**，需要清理：

```sql
-- 创建备份表
CREATE TABLE daily_task_backup AS SELECT * FROM daily_task;

-- 删除有问题的列
ALTER TABLE daily_task DROP COLUMN task_type;

-- 创建新列
ALTER TABLE daily_task ADD COLUMN task_type ENUM(
    'ghost_elimination',
    'pen_spirit_case',
    'fake_immortal_cult',
    'shape_shifter_hunt',
    'stone_curse_break',
    'torture_cult_raid',
    'tutorial'
) NOT NULL DEFAULT 'tutorial' COMMENT '任务类型';

-- 从备份表恢复合法数据
UPDATE daily_task d
INNER JOIN daily_task_backup b ON d.id = b.id
SET d.task_type = b.task_type
WHERE b.task_type IN (
    'ghost_elimination',
    'pen_spirit_case',
    'fake_immortal_cult',
    'shape_shifter_hunt',
    'stone_curse_break',
    'torture_cult_raid',
    'tutorial'
);
```

---

## 🔄 修复后验证

### 1. 在 MySQL 中验证

```sql
-- 验证ENUM定义
SHOW COLUMNS FROM daily_task LIKE 'task_type';

-- 验证数据
SELECT task_type, COUNT(*) as count
FROM daily_task
GROUP BY task_type;
```

### 2. 重启 Bot

```bash
# 停止bot
pkill -f bot.py

# 启动bot
python bot.py
```

### 3. 查看启动日志

确认没有 ENUM 相关错误。

---

## 🚨 如果仍然失败

### 可能的原因

1. **数据库连接池缓存了旧的表结构**
   - 解决：重启 MySQL 服务
   ```bash
   # Linux
   sudo systemctl restart mysql

   # Windows
   # 在服务管理器中重启 MySQL 服务
   ```

2. **SQLAlchemy 缓存了表结构**
   - 解决：清理 Python 缓存
   ```bash
   find . -type d -name __pycache__ -exec rm -rf {} +
   find . -name "*.pyc" -delete
   ```

3. **数据库中真的有无效数据**
   - 解决：直接删除或更新这些记录
   ```sql
   -- 查找无效记录
   SELECT id, HEX(task_type) as hex_value
   FROM daily_task
   WHERE task_type NOT IN (
       'ghost_elimination',
       'pen_spirit_case',
       'fake_immortal_cult',
       'shape_shifter_hunt',
       'stone_curse_break',
       'torture_cult_raid',
       'tutorial'
   );

   -- 删除无效记录（如果可以接受丢失数据）
   DELETE FROM daily_task
   WHERE task_type NOT IN (
       'ghost_elimination',
       'pen_spirit_case',
       'fake_immortal_cult',
       'shape_shifter_hunt',
       'stone_curse_break',
       'torture_cult_raid',
       'tutorial'
   );
   ```

---

## 🆘 终极方案

如果以上所有方案都失败，考虑：

### 选项 1：删除所有 daily_task 数据

```sql
-- 备份
CREATE TABLE daily_task_backup_20251203 AS SELECT * FROM daily_task;

-- 清空表
TRUNCATE TABLE daily_task;

-- 重建ENUM
ALTER TABLE daily_task MODIFY COLUMN task_type ENUM(
    'ghost_elimination',
    'pen_spirit_case',
    'fake_immortal_cult',
    'shape_shifter_hunt',
    'stone_curse_break',
    'torture_cult_raid',
    'tutorial'
) NOT NULL DEFAULT 'tutorial' COMMENT '任务类型';
```

### 选项 2：将 ENUM 改为 VARCHAR

修改 `plugins/xiuxian_game/models/daily_task.py`:

```python
# 将第39行的 ENUM 改为 String
task_type: Mapped[str] = mapped_column(String(50), comment="任务类型")
```

然后在数据库中：

```sql
ALTER TABLE daily_task MODIFY COLUMN task_type VARCHAR(50) NOT NULL;
```

---

## 📞 需要帮助

请提供以下信息：

1. **诊断SQL的输出**（`diagnose_enum.sql`的结果）
2. **MySQL版本**：`SELECT VERSION();`
3. **表中记录数**：`SELECT COUNT(*) FROM daily_task;`
4. **Bot启动日志**中关于auto_migrate的输出

---

**创建时间**: 2025-12-03
**优先级**: 🔴 P0 - 阻塞bot启动
