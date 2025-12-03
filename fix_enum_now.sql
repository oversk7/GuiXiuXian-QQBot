-- ==========================================
-- 立即修复 daily_task.task_type ENUM 问题
-- ==========================================
-- 执行方法: mysql -u用户名 -p数据库名 < fix_enum_now.sql
-- ==========================================

-- 步骤 1: 添加临时列
ALTER TABLE daily_task ADD COLUMN task_type_temp VARCHAR(100);

-- 步骤 2: 复制现有数据到临时列
UPDATE daily_task SET task_type_temp = task_type;

-- 步骤 3: 删除旧的 ENUM 列
ALTER TABLE daily_task DROP COLUMN task_type;

-- 步骤 4: 创建新的 ENUM 列（包含所有7个值）
ALTER TABLE daily_task ADD COLUMN task_type ENUM(
    'ghost_elimination',
    'pen_spirit_case',
    'fake_immortal_cult',
    'shape_shifter_hunt',
    'stone_curse_break',
    'torture_cult_raid',
    'tutorial'
) NOT NULL COMMENT '任务类型';

-- 步骤 5: 从临时列恢复数据
UPDATE daily_task SET task_type = task_type_temp;

-- 步骤 6: 验证数据恢复（检查是否有未恢复的数据）
SELECT COUNT(*) AS orphaned_rows
FROM daily_task
WHERE task_type IS NULL AND task_type_temp IS NOT NULL;

-- 步骤 7: 删除临时列
ALTER TABLE daily_task DROP COLUMN task_type_temp;

-- 步骤 8: 验证修复结果
SHOW COLUMNS FROM daily_task LIKE 'task_type';

-- 步骤 9: 检查数据完整性
SELECT task_type, COUNT(*) as count
FROM daily_task
GROUP BY task_type
ORDER BY task_type;
