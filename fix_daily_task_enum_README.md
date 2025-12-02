# 修复 daily_task.task_type ENUM 列错误

## 问题描述

错误信息：
```
LookupError: 'tutorial' is not among the defined enum values. Enum name: tasktype.
Possible values: GHOST_ELIMI.., PEN_SPIRIT_.., FAKE_IMMORT.., ...,
```

**原因**：数据库中 `daily_task` 表的 `task_type` ENUM 列缺少 `'tutorial'` 值，但代码中已经使用了该值。

## 解决方案

### 方法1：执行 SQL 脚本（推荐）

```bash
# 1. 备份数据库
mysqldump -u用户名 -p数据库名 > backup_$(date +%Y%m%d).sql

# 2. 执行修复脚本
mysql -u用户名 -p数据库名 < fix_daily_task_enum.sql

# 3. 重启bot
python bot.py
```

### 方法2：手动执行 SQL

登录 MySQL 后执行 `fix_daily_task_enum.sql` 中的 SQL 语句。

## 验证

执行以下 SQL 确认修复成功：

```sql
-- 查看 task_type 列定义
SHOW COLUMNS FROM daily_task LIKE 'task_type';

-- 应该看到 ENUM 包含 'tutorial'
-- Type 列应该显示：enum('ghost_elimination','pen_spirit_case',...,'tutorial')
```

## 注意事项

1. **务必先备份数据库**
2. 此脚本会临时删除并重建 `task_type` 列
3. 数据不会丢失（通过临时列保存）
4. 修复后需要重启 bot

## 为什么会出现这个问题？

这是因为：
1. 代码中的 `TaskType` 枚举添加了新值 `TUTORIAL = "tutorial"`
2. 但数据库中的 ENUM 类型定义没有同步更新
3. MySQL 的 ENUM 类型需要手动修改列定义才能添加新值

## 防止未来出现类似问题

建议：
- 不要使用 MySQL ENUM 类型，改用 VARCHAR
- 或者在代码中添加数据库迁移脚本

---

**修复时间**：2025-12-02
**影响模块**：新手教程系统、每日任务系统
