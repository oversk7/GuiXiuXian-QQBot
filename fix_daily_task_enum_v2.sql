-- 修复 daily_task.task_type ENUM 列
-- 问题：代码中定义了7个TaskType，但数据库ENUM列缺少部分值
-- 解决：重建ENUM列，包含所有7个任务类型
--
-- 执行此脚本前请备份数据库！
-- 执行命令：mysql -u用户名 -p数据库名 < fix_daily_task_enum_v2.sql

-- 步骤1：添加一个临时VARCHAR列
ALTER TABLE daily_task ADD COLUMN task_type_new VARCHAR(50);

-- 步骤2：复制现有数据到临时列
UPDATE daily_task SET task_type_new = task_type;

-- 步骤3：删除旧的 ENUM 列
ALTER TABLE daily_task DROP COLUMN task_type;

-- 步骤4：创建新的 ENUM 列（包含所有7个任务类型）
-- 对应 models/daily_task.py 中的 TaskType 枚举定义：
--   1. GHOST_ELIMINATION = "ghost_elimination"
--   2. PEN_SPIRIT_CASE = "pen_spirit_case"
--   3. FAKE_IMMORTAL_CULT = "fake_immortal_cult"
--   4. SHAPE_SHIFTER_HUNT = "shape_shifter_hunt"
--   5. STONE_CURSE_BREAK = "stone_curse_break"
--   6. TORTURE_CULT_RAID = "torture_cult_raid"
--   7. TUTORIAL = "tutorial"
ALTER TABLE daily_task ADD COLUMN task_type ENUM(
    'ghost_elimination',
    'pen_spirit_case',
    'fake_immortal_cult',
    'shape_shifter_hunt',
    'stone_curse_break',
    'torture_cult_raid',
    'tutorial'
) NOT NULL COMMENT '任务类型';

-- 步骤5：从临时列恢复数据
UPDATE daily_task SET task_type = task_type_new;

-- 步骤6：删除临时列
ALTER TABLE daily_task DROP COLUMN task_type_new;

-- 验证：显示所有不同的任务类型
SELECT DISTINCT task_type FROM daily_task;

-- 验证：显示表结构
SHOW CREATE TABLE daily_task;
