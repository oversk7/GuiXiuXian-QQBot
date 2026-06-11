-- =============================================
-- 挂牌市场货架化迁移（2026-06-11）
-- 1. 退还所有求购(BUY)挂单冻结的金币，删除求购单
--    （求购挂牌已下线，历史上撮合从未成交，63 张买单的钱被冻结最长 10 个月）
-- 2. 摊位系统下线：回收玩家持有的摊位令，按商店基准价 15000/张 退款
-- 部署时执行一次：mysql -uroot -p guixiuxian_db < shelf_market_migration.sql
-- =============================================

-- ========== 第一步：查看影响范围 ==========

SELECT side, COUNT(*) AS orders, COUNT(DISTINCT player_id) AS players,
       SUM(price * quantity) AS frozen_gold
FROM market_orders WHERE side = 'BUY' GROUP BY side;

SELECT SUM(quantity) AS permits, COUNT(DISTINCT player_id) AS holders
FROM inventory WHERE item_id = 'stall_permit';

-- ========== 第二步：退款 ==========

-- 求购单冻结金币退还
UPDATE player p
JOIN (
    SELECT player_id, SUM(price * quantity) AS refund
    FROM market_orders
    WHERE side = 'BUY'
    GROUP BY player_id
) r ON p.id = r.player_id
SET p.gold = p.gold + r.refund;

-- 摊位令退款（15000/张 = 基础价5000 × 商店倍率3）
UPDATE player p
JOIN (
    SELECT player_id, SUM(quantity) * 15000 AS refund
    FROM inventory
    WHERE item_id = 'stall_permit'
    GROUP BY player_id
) r ON p.id = r.player_id
SET p.gold = p.gold + r.refund;

-- ========== 第三步：清理 ==========

DELETE FROM market_orders WHERE side = 'BUY';
DELETE FROM inventory WHERE item_id = 'stall_permit';

-- ========== 第四步：验证（均应返回 0） ==========

SELECT COUNT(*) AS remaining_buy_orders FROM market_orders WHERE side = 'BUY';
SELECT COUNT(*) AS remaining_permits FROM inventory WHERE item_id = 'stall_permit';
