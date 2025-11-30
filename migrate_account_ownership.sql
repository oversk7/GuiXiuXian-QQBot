-- 账号所有权系统数据库迁移SQL脚本
-- 执行方法：mysql -u root -p guixiuxian_db < migrate_account_ownership.sql

-- 1. 创建账号所有权表
CREATE TABLE IF NOT EXISTS account_ownership (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    owner_platform_id VARCHAR(64) NOT NULL COMMENT '拥有者的平台ID（真实玩家）',
    player_id VARCHAR(64) NOT NULL COMMENT '拥有的游戏账号ID',
    is_active BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否是当前激活使用的账号',
    display_name VARCHAR(32) NULL COMMENT '账号备注名',
    transfer_key VARCHAR(16) NULL COMMENT '账号转让密钥',
    transfer_key_created_at DATETIME NULL COMMENT '转让密钥生成时间',
    acquired_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '获得此账号的时间',
    acquired_type VARCHAR(16) NOT NULL DEFAULT 'created' COMMENT '获得方式: created/transferred/admin',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
    UNIQUE KEY uq_account_ownership_player_id (player_id),
    KEY idx_account_ownership_owner (owner_platform_id),
    KEY idx_account_ownership_active (owner_platform_id, is_active),
    KEY idx_account_ownership_transfer_key (transfer_key),
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='账号所有权记录表';

-- 2. 创建账号转让历史表
CREATE TABLE IF NOT EXISTS account_transfer_logs (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    player_id VARCHAR(64) NOT NULL COMMENT '被转让的游戏账号ID',
    from_platform_id VARCHAR(64) NOT NULL COMMENT '原拥有者的平台ID',
    to_platform_id VARCHAR(64) NOT NULL COMMENT '新拥有者的平台ID',
    transfer_type VARCHAR(16) NOT NULL COMMENT '转让类型: normal/admin_force',
    transfer_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '转让完成时间',
    transfer_key_used VARCHAR(16) NULL COMMENT '使用的转让密钥',
    notes VARCHAR(256) NULL COMMENT '转让备注',
    KEY idx_transfer_log_player (player_id, transfer_time),
    KEY idx_transfer_log_from (from_platform_id, transfer_time),
    KEY idx_transfer_log_to (to_platform_id, transfer_time),
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='账号转让历史记录表';

-- 3. 为现有玩家创建所有权记录
INSERT INTO account_ownership (owner_platform_id, player_id, is_active, display_name, acquired_type, acquired_at)
SELECT
    id as owner_platform_id,
    id as player_id,
    TRUE as is_active,
    '主号' as display_name,
    'created' as acquired_type,
    created_at as acquired_at
FROM players
WHERE NOT EXISTS (
    SELECT 1 FROM account_ownership WHERE account_ownership.player_id = players.id
);

-- 4. 显示迁移结果统计
SELECT
    '迁移结果统计' as info,
    (SELECT COUNT(*) FROM players) as players_count,
    (SELECT COUNT(*) FROM account_ownership) as ownership_count,
    (SELECT COUNT(*) FROM account_ownership WHERE is_active = TRUE) as active_count;
