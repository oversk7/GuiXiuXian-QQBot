"""
账号所有权系统数据库迁移脚本

功能：
1. 创建 account_ownership 表（账号所有权记录）
2. 创建 account_transfer_logs 表（账号转让历史）
3. 为所有现有玩家创建所有权记录

使用方法：
    python migrate_account_ownership.py
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径到sys.path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from plugins.xiuxian_game.models.db import engine
from sqlalchemy import text


async def check_tables_exist():
    """检查表是否已存在"""
    async with engine.begin() as conn:
        # 检查 account_ownership 表
        result = await conn.execute(text("""
            SELECT COUNT(*) as cnt
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'account_ownership'
        """))
        ownership_exists = result.fetchone()[0] > 0

        # 检查 account_transfer_logs 表
        result = await conn.execute(text("""
            SELECT COUNT(*) as cnt
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
            AND table_name = 'account_transfer_logs'
        """))
        logs_exists = result.fetchone()[0] > 0

        return ownership_exists, logs_exists


async def create_account_ownership_table():
    """创建账号所有权表"""
    print("📝 创建 account_ownership 表...")

    async with engine.begin() as conn:
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
                acquired_type VARCHAR(16) NOT NULL DEFAULT 'created' COMMENT '获得方式: created/transferred/admin',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
                UNIQUE KEY uq_account_ownership_player_id (player_id),
                KEY idx_account_ownership_owner (owner_platform_id),
                KEY idx_account_ownership_active (owner_platform_id, is_active),
                KEY idx_account_ownership_transfer_key (transfer_key),
                FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='账号所有权记录表'
        """))

    print("✅ account_ownership 表创建成功")


async def create_account_transfer_logs_table():
    """创建账号转让历史表"""
    print("📝 创建 account_transfer_logs 表...")

    async with engine.begin() as conn:
        await conn.execute(text("""
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
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='账号转让历史记录表'
        """))

    print("✅ account_transfer_logs 表创建成功")


async def migrate_existing_players():
    """为现有玩家创建所有权记录"""
    print("\n📊 检查现有玩家...")

    async with engine.begin() as conn:
        # 统计现有玩家数量
        result = await conn.execute(text("SELECT COUNT(*) as cnt FROM players"))
        player_count = result.fetchone()[0]

        print(f"🎮 发现 {player_count} 个现有玩家账号")

        if player_count == 0:
            print("ℹ️  没有需要迁移的玩家数据")
            return

        # 为每个现有玩家创建所有权记录
        print("📝 为现有玩家创建所有权记录...")
        result = await conn.execute(text("""
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
                SELECT 1 FROM account_ownership
                WHERE account_ownership.player_id = players.id
            )
        """))

        migrated_count = result.rowcount
        print(f"✅ 成功为 {migrated_count} 个玩家创建所有权记录")


async def verify_migration():
    """验证迁移结果"""
    print("\n🔍 验证迁移结果...")

    async with engine.begin() as conn:
        # 检查account_ownership表记录数
        result = await conn.execute(text("SELECT COUNT(*) as cnt FROM account_ownership"))
        ownership_count = result.fetchone()[0]

        # 检查players表记录数
        result = await conn.execute(text("SELECT COUNT(*) as cnt FROM players"))
        player_count = result.fetchone()[0]

        print(f"📊 players表: {player_count} 条记录")
        print(f"📊 account_ownership表: {ownership_count} 条记录")

        if ownership_count == player_count:
            print("✅ 验证通过：所有玩家都有对应的所有权记录")
            return True
        else:
            print(f"⚠️  警告：记录数不匹配 (玩家:{player_count}, 所有权:{ownership_count})")
            return False


async def main():
    """主函数"""
    print("=" * 70)
    print("🚀 账号所有权系统 - 数据库迁移脚本")
    print("=" * 70)
    print()

    try:
        # 1. 检查表是否已存在
        ownership_exists, logs_exists = await check_tables_exist()

        if ownership_exists and logs_exists:
            print("ℹ️  检测到表已存在，跳过创建步骤")
            print(f"   - account_ownership: ✅ 已存在")
            print(f"   - account_transfer_logs: ✅ 已存在")
        else:
            # 2. 创建表
            if not ownership_exists:
                await create_account_ownership_table()
            else:
                print("ℹ️  account_ownership 表已存在，跳过创建")

            if not logs_exists:
                await create_account_transfer_logs_table()
            else:
                print("ℹ️  account_transfer_logs 表已存在，跳过创建")

        # 3. 迁移现有玩家数据
        await migrate_existing_players()

        # 4. 验证迁移结果
        await verify_migration()

        # 5. 显示成功信息
        print("\n" + "=" * 70)
        print("🎉 数据库迁移成功完成！")
        print("=" * 70)
        print("\n📖 现在可以使用以下账号切换系统命令：")
        print()
        print("  📋 我的账号               - 查看你拥有的所有游戏账号")
        print("  🔄 切换账号 <UID>         - 切换到指定的游戏账号")
        print("  ✏️  重命名账号 <UID> <名称> - 给账号设置备注名")
        print("  🔑 生成转让密钥 <UID>     - 生成账号转让密钥（6位数字）")
        print("  📥 接收账号 <密钥>        - 使用转让密钥接收账号")
        print("  ❌ 取消转让 <UID>         - 取消账号转让")
        print("  📜 转让历史 <UID>         - 查看账号转让历史")
        print()
        print("💡 提示：每个玩家可以拥有多个游戏账号，同时只能激活一个账号进行游戏")
        print()

        return 0

    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ 数据库迁移失败！")
        print("=" * 70)
        print(f"\n错误信息：{e}")
        print("\n详细错误追踪：")
        import traceback
        traceback.print_exc()
        print()
        print("💡 可能的解决方案：")
        print("  1. 检查数据库连接配置是否正确")
        print("  2. 确认MySQL服务正在运行")
        print("  3. 确认数据库用户有足够的权限")
        print("  4. 检查players表是否存在")
        print()
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断操作")
        sys.exit(1)
