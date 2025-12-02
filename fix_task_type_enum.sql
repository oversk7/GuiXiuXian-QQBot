-- 修复 daily_task 表的 task_type ENUM 列
-- 添加缺失的 'tutorial' 枚举值

-- 方案1: 直接ALTER TABLE修改ENUM（推荐）
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

-- 如果上面的命令失败，使用方案2: 临时列方法
-- ALTER TABLE daily_task ADD COLUMN task_type_new ENUM('ghost_elimination','pen_spirit_case','fake_immortal_cult','shape_shifter_hunt','stone_curse_break','torture_cult_raid','tutorial') NOT NULL COMMENT '任务类型';
-- UPDATE daily_task SET task_type_new = task_type;
-- ALTER TABLE daily_task DROP COLUMN task_type;
-- ALTER TABLE daily_task CHANGE COLUMN task_type_new task_type ENUM('ghost_elimination','pen_spirit_case','fake_immortal_cult','shape_shifter_hunt','stone_curse_break','torture_cult_raid','tutorial') NOT NULL COMMENT '任务类型';
