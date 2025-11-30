"""
手动运行账号所有权表迁移脚本

由于Alembic环境问题，这个脚本直接执行SQL来创建表和迁移数据
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from models.db import engine, Base
from models.account_ownership import AccountOwnership
from models.account_transfer_log import AccountTransferLog
from sqlalchemy import text


async def create_tables():
    """创建账号所有权相关的表"""
    print("开始创建账号所有权表...")

    async with engine.begin() as conn:
        # 创建 account_ownership 表
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS account_ownership (
                id INTEGER PRIMARY KEY AUTO_INCREMENT,
                owner_platform_id VARCHAR(64) NOT NULL COMMENT '拥有者的平台ID（真实玩家）',
                player_id VARCHAR(64) NOT NULL COMMENT '拥有的游戏账号ID',
                is_active BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否是当前激活使用的账号',
                display_name VARCHAR(32) NULL COMMENT '账号备注名',
                transfer_key VARCHAR(16) NULL COMMENT '账号转让密钥',
                transfer_key_created_at DATETIME NULL COMMENT '转让密钥生成时间',
                acquired_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '获得此账号的时间',
                acquired_type VARCHAR(16) NOT NULL DEFAULT 'created' COMMENT '获得方式',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
                UNIQUE KEY uq_account_ownership_player_id (player_id),
                KEY idx_account_ownership_owner (owner_platform_id),
                KEY idx_account_ownership_active (owner_platform_id, is_active),
                FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        print("✅ account_ownership 表创建成功")

        # 创建 account_transfer_logs 表
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS account_transfer_logs (
                id INTEGER PRIMARY KEY AUTO_INCREMENT,
                player_id VARCHAR(64) NOT NULL COMMENT '被转让的游戏账号ID',
                from_platform_id VARCHAR(64) NOT NULL COMMENT '原拥有者的平台ID',
                to_platform_id VARCHAR(64) NOT NULL COMMENT '新拥有者的平台ID',
                transfer_type VARCHAR(16) NOT NULL COMMENT '转让类型',
                transfer_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '转让完成时间',
                transfer_key_used VARCHAR(16) NULL COMMENT '使用的转让密钥',
                notes VARCHAR(256) NULL COMMENT '转让备注',
                KEY idx_transfer_log_player (player_id, transfer_time),
                KEY idx_transfer_log_from (from_platform_id, transfer_time),
                KEY idx_transfer_log_to (to_platform_id, transfer_time),
                FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """))
        print("✅ account_transfer_logs 表创建成功")


async def migrate_existing_data():
    """迁移现有玩家数据"""
    print("\n开始迁移现有玩家数据...")

    async with engine.begin() as conn:
        # 检查是否有现有玩家
        result = await conn.execute(text("SELECT COUNT(*) as cnt FROM players"))
        row = result.fetchone()
        player_count = row[0] if row else 0

        print(f"发现 {player_count} 个现有玩家")

        if player_count > 0:
            # 为每个现有Player创建AccountOwnership记录
            await conn.execute(text("""
                INSERT INTO account_ownership (
                    owner_platform_id,
                    player_id,
                    is_active,
                    display_name,
                    acquired_type,
                    acquired_at
                )
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
                )
            """))
            print(f"✅ 已为所有现有玩家创建所有权记录")

    print("\n✅ 数据迁移完成")


async def main():
    """主函数"""
    print("=" * 60)
    print("账号所有权系统迁移脚本")
    print("=" * 60)

    try:
        # 创建表
        await create_tables()

        # 迁移现有数据
        await migrate_existing_data()

        print("\n" + "=" * 60)
        print("✅ 迁移成功完成!")
        print("=" * 60)
        print("\n现在可以使用以下命令：")
        print("  - 我的账号 - 查看拥有的所有游戏账号")
        print("  - 切换账号 <账号ID> - 切换到指定的游戏账号")
        print("  - 生成转让密钥 <账号ID> - 生成账号转让密钥")
        print("  - 接收账号 <转让密钥> - 使用转让密钥接收账号")

    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
