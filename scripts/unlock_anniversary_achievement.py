"""
一次性脚本：为所有老玩家解锁"元老见证者"周年成就

使用方法：
    python scripts/unlock_anniversary_achievement.py

功能：
    - 查询所有在2025-10-04之前创建的玩家
    - 为符合条件且未解锁的玩家自动解锁first_anniversary成就
    - 发放周年庆典奖励（金币50000、经验10000、属性点30）

注意：
    此脚本完全独立运行，不依赖NoneBot和插件模块
    使用原始SQL查询避免导入插件代码
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
import yaml

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text


# ==================== 配置 ====================

# 截止日期（2025-10-04之前创建的账号）
CUTOFF_DATE = "2025-10-04"

# 成就ID
ACHIEVEMENT_ID = "first_anniversary"

# 奖励配置
REWARDS = {
    "gold": 50000,
    "exp": 10000,
    "attribute_points": 30
}


# ==================== 数据库连接 ====================

def load_database_config() -> dict:
    """加载数据库配置"""
    config_path = project_root / "plugins" / "xiuxian_game" / "config" / "database.yaml"

    if not config_path.exists():
        print(f"⚠️ 使用默认 SQLite 配置")
        return {
            "database": {
                "type": "sqlite",
                "sqlite": {
                    "path": "data/game.db"
                }
            }
        }

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_database_url(config: dict) -> str:
    """构建数据库连接 URL"""
    db_config = config["database"]
    db_type = db_config.get("type", "sqlite")

    if db_type == "sqlite":
        sqlite_config = db_config["sqlite"]
        db_path = project_root / "plugins" / "xiuxian_game" / sqlite_config["path"]
        return f"sqlite+aiosqlite:///{db_path}"

    elif db_type == "mysql":
        mysql_config = db_config["mysql"]
        host = mysql_config["host"]
        port = mysql_config["port"]
        user = mysql_config["user"]
        password = mysql_config["password"]
        database = mysql_config["database"]
        charset = mysql_config.get("charset", "utf8mb4")
        return f"mysql+aiomysql://{user}:{password}@{host}:{port}/{database}?charset={charset}"

    else:
        raise ValueError(f"不支持的数据库类型: {db_type}")


# 初始化数据库连接
db_config = load_database_config()
database_url = build_database_url(db_config)
engine = create_async_engine(database_url, echo=False)
AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


# ==================== 核心逻辑 ====================

async def unlock_anniversary_for_old_players():
    """为老玩家解锁周年成就"""

    print("=" * 60)
    print("🎂 诡修仙一周年成就解锁脚本")
    print("=" * 60)
    print(f"截止日期: {CUTOFF_DATE}")
    print(f"成就ID: {ACHIEVEMENT_ID}")
    print(f"奖励: 金币{REWARDS['gold']} 经验{REWARDS['exp']} 属性点{REWARDS['attribute_points']}")
    print()

    async with AsyncSessionLocal() as session:
        try:
            # 1. 查询所有符合条件的老玩家
            print("📊 正在查询符合条件的玩家...")

            query = text("""
                SELECT id, uid, nickname, created_at
                FROM player
                WHERE created_at < :cutoff_date
                ORDER BY created_at ASC
            """)

            result = await session.execute(query, {"cutoff_date": CUTOFF_DATE})
            old_players = result.fetchall()

            if not old_players:
                print("❌ 未找到符合条件的玩家")
                return

            print(f"✅ 找到 {len(old_players)} 位老玩家")
            print()

            # 2. 为每位老玩家解锁成就
            unlocked_count = 0
            skipped_count = 0
            error_count = 0

            for player in old_players:
                player_id = player[0]
                player_uid = player[1]
                player_nickname = player[2]
                player_created_at = player[3]

                try:
                    # 检查是否已解锁
                    check_query = text("""
                        SELECT id FROM player_achievement
                        WHERE player_id = :player_id
                        AND achievement_id = :achievement_id
                        AND is_completed = 1
                    """)

                    check_result = await session.execute(
                        check_query,
                        {"player_id": player_id, "achievement_id": ACHIEVEMENT_ID}
                    )
                    existing = check_result.fetchone()

                    if existing:
                        print(f"⏭️  跳过 {player_nickname} (UID:{player_uid}) - 已解锁")
                        skipped_count += 1
                        continue

                    # 确保 player_stats 存在
                    stats_check = text("""
                        SELECT player_id FROM player_stats
                        WHERE player_id = :player_id
                    """)
                    stats_result = await session.execute(stats_check, {"player_id": player_id})
                    stats_exists = stats_result.fetchone()

                    if not stats_exists:
                        # 创建 player_stats 记录
                        create_stats = text("""
                            INSERT INTO player_stats (player_id, cultivation_count, total_battles, total_wins, total_kills, equipment_obtained)
                            VALUES (:player_id, 0, 0, 0, 0, 0)
                        """)
                        await session.execute(create_stats, {"player_id": player_id})

                    # 创建成就记录
                    insert_achievement = text("""
                        INSERT INTO player_achievement (player_id, achievement_id, is_completed, reward_claimed, unlocked_at)
                        VALUES (:player_id, :achievement_id, 1, 1, :unlocked_at)
                    """)

                    await session.execute(
                        insert_achievement,
                        {
                            "player_id": player_id,
                            "achievement_id": ACHIEVEMENT_ID,
                            "unlocked_at": datetime.now()
                        }
                    )

                    # 发放奖励
                    update_player = text("""
                        UPDATE player
                        SET gold = gold + :gold,
                            exp = exp + :exp,
                            attribute_points = attribute_points + :attribute_points
                        WHERE id = :player_id
                    """)

                    await session.execute(
                        update_player,
                        {
                            "player_id": player_id,
                            "gold": REWARDS["gold"],
                            "exp": REWARDS["exp"],
                            "attribute_points": REWARDS["attribute_points"]
                        }
                    )

                    print(f"✅ 解锁成功: {player_nickname} (UID:{player_uid})")
                    if isinstance(player_created_at, str):
                        print(f"   创建时间: {player_created_at}")
                    else:
                        print(f"   创建时间: {player_created_at.strftime('%Y-%m-%d %H:%M:%S')}")
                    unlocked_count += 1

                except Exception as e:
                    print(f"❌ 错误: {player_nickname} (UID:{player_uid}) - {str(e)}")
                    error_count += 1
                    continue

            # 提交所有更改
            await session.commit()

            # 3. 输出统计结果
            print()
            print("=" * 60)
            print("📋 执行完成统计")
            print("=" * 60)
            print(f"总玩家数: {len(old_players)}")
            print(f"✅ 成功解锁: {unlocked_count}")
            print(f"⏭️  已经解锁: {skipped_count}")
            print(f"❌ 失败/错误: {error_count}")
            print()
            print("🎉 周年成就解锁完成！")
            print("=" * 60)

        except Exception as e:
            await session.rollback()
            raise e
        finally:
            await session.close()


def main():
    """主函数"""
    try:
        asyncio.run(unlock_anniversary_for_old_players())
    except KeyboardInterrupt:
        print("\n⚠️  操作已取消")
    except Exception as e:
        print(f"\n❌ 发生错误: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
