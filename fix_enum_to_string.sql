-- ==========================================
-- 终极解决方案：将ENUM改为VARCHAR
-- ==========================================
-- 问题：SQLAlchemy的ENUM映射有大小写问题
-- 解决：改用VARCHAR类型，更灵活且不会有映射问题
-- ==========================================

-- 删除旧的ENUM列（兼容旧版MySQL）
-- 步骤1: 检查并删除task_type
SET @sql1 = (SELECT IF(
    COUNT(*) > 0,
    'ALTER TABLE daily_task DROP COLUMN task_type',
    'SELECT "Column task_type does not exist"'
) FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
AND TABLE_NAME = 'daily_task'
AND COLUMN_NAME = 'task_type');

PREPARE stmt1 FROM @sql1;
EXECUTE stmt1;
DEALLOCATE PREPARE stmt1;

-- 步骤2: 检查并删除status
SET @sql2 = (SELECT IF(
    COUNT(*) > 0,
    'ALTER TABLE daily_task DROP COLUMN status',
    'SELECT "Column status does not exist"'
) FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
AND TABLE_NAME = 'daily_task'
AND COLUMN_NAME = 'status');

PREPARE stmt2 FROM @sql2;
EXECUTE stmt2;
DEALLOCATE PREPARE stmt2;

-- 步骤3: 创建VARCHAR列（不再使用ENUM）
ALTER TABLE daily_task ADD COLUMN task_type VARCHAR(50) NOT NULL DEFAULT 'tutorial' COMMENT '任务类型';
ALTER TABLE daily_task ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'available' COMMENT '任务状态';

-- 添加CHECK约束确保数据有效（可选，MySQL 8.0.16+支持）
-- ALTER TABLE daily_task ADD CONSTRAINT chk_task_type CHECK (
--     task_type IN (
--         'ghost_elimination',
--         'pen_spirit_case',
--         'fake_immortal_cult',
--         'shape_shifter_hunt',
--         'stone_curse_break',
--         'torture_cult_raid',
--         'tutorial'
--     )
-- );

-- 验证
SHOW COLUMNS FROM daily_task LIKE 'task_type';
SELECT COUNT(*) FROM daily_task;

SELECT '✅ 修复完成！task_type 已改为 VARCHAR 类型' as message;
