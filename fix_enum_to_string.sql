-- ==========================================
-- 终极解决方案：将ENUM改为VARCHAR
-- ==========================================
-- 问题：SQLAlchemy的ENUM映射有大小写问题
-- 解决：改用VARCHAR类型，更灵活且不会有映射问题
-- ==========================================

-- 删除旧的ENUM列
ALTER TABLE daily_task DROP COLUMN IF EXISTS task_type;
ALTER TABLE daily_task DROP COLUMN IF EXISTS status;

-- 创建VARCHAR列（不再使用ENUM）
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
