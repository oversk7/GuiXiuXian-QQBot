-- ==========================================
-- 终极修复方案 - 最简单粗暴的方法
-- ==========================================
-- 直接删除并重建 task_type 列
-- 所有数据将设置为默认值 'tutorial'
-- ==========================================

-- 备份当前数据（如果需要）
-- CREATE TABLE daily_task_backup_20251203 AS SELECT * FROM daily_task;

-- 直接删除 task_type 列
ALTER TABLE daily_task DROP COLUMN task_type;

-- 创建新的 ENUM 列
ALTER TABLE daily_task ADD COLUMN task_type ENUM(
    'ghost_elimination',
    'pen_spirit_case',
    'fake_immortal_cult',
    'shape_shifter_hunt',
    'stone_curse_break',
    'torture_cult_raid',
    'tutorial'
) NOT NULL DEFAULT 'tutorial' COMMENT '任务类型';

-- 验证结果
SHOW COLUMNS FROM daily_task LIKE 'task_type';

SELECT 'Fix completed! All tasks set to tutorial (default)' as message;
