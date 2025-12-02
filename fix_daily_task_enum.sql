-- 修复 daily_task.task_type ENUM 列，添加 'tutorial' 值
-- 执行此脚本前请备份数据库

-- 步骤1：添加一个临时列
ALTER TABLE daily_task ADD COLUMN task_type_new VARCHAR(50);

-- 步骤2：复制现有数据到临时列
UPDATE daily_task SET task_type_new = task_type;

-- 步骤3：删除旧的 ENUM 列
ALTER TABLE daily_task DROP COLUMN task_type;

-- 步骤4：创建新的 ENUM 列（包含所有值，包括 tutorial）
ALTER TABLE daily_task ADD COLUMN task_type ENUM(
    'ghost_elimination',
    'pen_spirit_case',
    'fake_immortal_cult',
    'shape_shifter_hunt',
    'stone_curse_break',
    'torture_cult_raid',
    'cursed_painting',
    'tutorial'
) NOT NULL COMMENT '任务类型';

-- 步骤5：从临时列恢复数据
UPDATE daily_task SET task_type = task_type_new;

-- 步骤6：删除临时列
ALTER TABLE daily_task DROP COLUMN task_type_new;

-- 验证
SELECT DISTINCT task_type FROM daily_task;
