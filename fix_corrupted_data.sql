-- ==========================================
-- 修复损坏的 task_type 数据
-- ==========================================
-- 问题：数据中可能有截断或损坏的值
-- 解决：重新规范化所有数据
-- ==========================================

-- 查看当前数据分布
SELECT '=== 修复前数据分布 ===' as status;
SELECT task_type, COUNT(*) as count
FROM daily_task
GROUP BY task_type
ORDER BY task_type;

-- 创建临时备份列
ALTER TABLE daily_task ADD COLUMN task_type_fixed VARCHAR(100);

-- 使用CASE语句规范化所有数据
UPDATE daily_task
SET task_type_fixed = CASE
    WHEN task_type = 'ghost_elimination' THEN 'ghost_elimination'
    WHEN task_type = 'pen_spirit_case' THEN 'pen_spirit_case'
    WHEN task_type = 'fake_immortal_cult' THEN 'fake_immortal_cult'
    WHEN task_type = 'shape_shifter_hunt' THEN 'shape_shifter_hunt'
    WHEN task_type = 'stone_curse_break' THEN 'stone_curse_break'
    WHEN task_type = 'torture_cult_raid' THEN 'torture_cult_raid'
    WHEN task_type = 'tutorial' THEN 'tutorial'
    ELSE 'tutorial'  -- 默认值，处理任何异常情况
END;

-- 检查是否有NULL值
SELECT '=== 检查修复后的数据 ===' as status;
SELECT
    task_type_fixed,
    COUNT(*) as count
FROM daily_task
GROUP BY task_type_fixed
ORDER BY task_type_fixed;

-- 检查是否有未修复的记录
SELECT '=== 检查未修复的记录 ===' as status;
SELECT COUNT(*) as unfixed_count
FROM daily_task
WHERE task_type_fixed IS NULL OR task_type_fixed = '';

-- 删除旧列
ALTER TABLE daily_task DROP COLUMN task_type;

-- 重命名新列
ALTER TABLE daily_task CHANGE task_type_fixed task_type ENUM(
    'ghost_elimination',
    'pen_spirit_case',
    'fake_immortal_cult',
    'shape_shifter_hunt',
    'stone_curse_break',
    'torture_cult_raid',
    'tutorial'
) NOT NULL DEFAULT 'tutorial' COMMENT '任务类型';

-- 验证最终结果
SELECT '=== 修复完成，最终数据分布 ===' as status;
SELECT task_type, COUNT(*) as count
FROM daily_task
GROUP BY task_type
ORDER BY task_type;

-- 验证ENUM定义
SELECT '=== 验证ENUM定义 ===' as status;
SHOW COLUMNS FROM daily_task LIKE 'task_type';

SELECT '=== ✅ 修复完成 ===' as status;
