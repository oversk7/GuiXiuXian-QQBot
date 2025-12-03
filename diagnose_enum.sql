-- ==========================================
-- 诊断 daily_task.task_type ENUM 问题
-- ==========================================
-- 使用方法: 在 MySQL 客户端中逐条执行
-- ==========================================

-- 1. 查看当前 ENUM 定义
SHOW COLUMNS FROM daily_task LIKE 'task_type';

-- 2. 查看表中有多少条记录
SELECT COUNT(*) as total_rows FROM daily_task;

-- 3. 尝试查看数据中的值（可能会报错）
SELECT task_type, COUNT(*) as count
FROM daily_task
GROUP BY task_type;

-- 4. 用十六进制方式读取（绕过 ENUM 检查）
SELECT HEX(task_type) as hex_value, COUNT(*) as count
FROM daily_task
GROUP BY hex_value;

-- 5. 检查是否有临时列
SHOW COLUMNS FROM daily_task LIKE '%temp%';

-- ==========================================
-- 根据上述查询结果：
--
-- 如果第3步报错 LookupError，说明数据中有 ENUM 不支持的值
-- 如果第4步能看到数据，可以把十六进制转换成字符串
--
-- 转换方法（在线工具）：
-- https://www.rapidtables.com/convert/number/hex-to-ascii.html
-- ==========================================
