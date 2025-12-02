# 修复 daily_task.task_type ENUM 列

## 问题描述
数据库中的 `task_type` ENUM 列缺少新的 `tutorial` 值，导致新手注册时插入新手任务失败。

## 错误信息
```
sqlalchemy.exc.DataError: (pymysql.err.DataError) (1265, "Data truncated for column 'task_type' at row 1")
```

## 修复步骤

### 1. 登录数据库
```bash
mysql -u root -p guixiuxian_db
```

### 2. 执行修复SQL
```sql
ALTER TABLE daily_task 
MODIFY COLUMN task_type ENUM(
    'ghost_elimination',
    'pen_spirit_case', 
    'fake_immortal_cult',
    'shape_shifter_hunt',
    'stone_curse_break',
    'torture_cult_raid',
    'tutorial'
) NOT NULL COMMENT '任务类型';
```

### 3. 验证修复
```sql
SHOW COLUMNS FROM daily_task WHERE Field='task_type';
```

应该看到 ENUM 包含所有7个值。

### 4. 重启机器人
修复完成后重启机器人即可。

## 自动执行（Linux服务器）
```bash
mysql -u root -p123456 guixiuxian_db < fix_task_type_enum.sql
```
