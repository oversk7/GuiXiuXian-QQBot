-- ==========================================
-- 强制修复 daily_task.task_type ENUM
-- ==========================================
-- 这个脚本会彻底删除并重建列
-- ⚠️ 执行前请确保已备份数据库！
-- ==========================================

-- 显示当前状态
SELECT '=== 修复前状态 ===' as status;
SHOW COLUMNS FROM daily_task LIKE 'task_type';

-- 清理可能存在的临时列
ALTER TABLE daily_task DROP COLUMN IF EXISTS task_type_temp;
ALTER TABLE daily_task DROP COLUMN IF EXISTS task_type_temp_migration;
ALTER TABLE daily_task DROP COLUMN IF EXISTS task_type_backup;

-- 方案：彻底重建列
-- 步骤 1: 创建备份列
ALTER TABLE daily_task ADD COLUMN task_type_backup VARCHAR(100);

-- 步骤 2: 尝试复制数据（可能会失败，但没关系）
UPDATE daily_task
SET task_type_backup = CASE task_type
    WHEN 'ghost_elimination' THEN 'ghost_elimination'
    WHEN 'pen_spirit_case' THEN 'pen_spirit_case'
    WHEN 'fake_immortal_cult' THEN 'fake_immortal_cult'
    WHEN 'shape_shifter_hunt' THEN 'shape_shifter_hunt'
    WHEN 'stone_curse_break' THEN 'stone_curse_break'
    WHEN 'torture_cult_raid' THEN 'torture_cult_raid'
    WHEN 'tutorial' THEN 'tutorial'
    ELSE 'tutorial'  -- 默认值
END;

-- 步骤 3: 删除旧列
ALTER TABLE daily_task DROP COLUMN task_type;

-- 步骤 4: 创建新 ENUM 列（包含所有7个值）
ALTER TABLE daily_task ADD COLUMN task_type ENUM(
    'ghost_elimination',
    'pen_spirit_case',
    'fake_immortal_cult',
    'shape_shifter_hunt',
    'stone_curse_break',
    'torture_cult_raid',
    'tutorial'
) NOT NULL DEFAULT 'tutorial' COMMENT '任务类型';

-- 步骤 5: 从备份列恢复数据
UPDATE daily_task
SET task_type = task_type_backup
WHERE task_type_backup IS NOT NULL;

-- 步骤 6: 检查恢复情况
SELECT '=== 数据恢复检查 ===' as status;
SELECT task_type, COUNT(*) as count
FROM daily_task
GROUP BY task_type;

-- 步骤 7: 删除备份列
ALTER TABLE daily_task DROP COLUMN task_type_backup;

-- 显示最终状态
SELECT '=== 修复后状态 ===' as status;
SHOW COLUMNS FROM daily_task LIKE 'task_type';

SELECT '=== 修复完成 ===' as status;
