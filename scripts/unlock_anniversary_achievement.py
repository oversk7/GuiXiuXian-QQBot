"""
一次性脚本：为所有老玩家解锁"元老见证者"周年成就

使用方法：
    python scripts/unlock_anniversary_achievement.py

功能：
    - 查询所有在2025-10-04之前创建的玩家
    - 为符合条件且未解锁的玩家自动解锁first_anniversary成就
    - 发放周年庆典奖励（金币50000、经验10000、属性点30）
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime
import yaml

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 在导入插件模块之前，设置环境变量避免 NoneBot 初始化检查
os.environ.setdefault('NONEBOT_SKIP_INIT_CHECK', '1')

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


# ==================== 独立数据库配置 ====================

def load_database_config() -> dict:
    """加载数据库配置"""
    config_path = project_root / "plugins" / "xiuxian_game" / "config" / "database.yaml"

    if not config_path.exists():
        print(f"⚠️ 使用默认 SQLite 配置")
        return {
            "database": {
                "type": "sqlite",
                "sqlite": {
                    "path": "data/game.db",
                    "timeout": 30
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

# 导入模型类（必须在数据库引擎创建之后）
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.models.achievement import PlayerAchievement, PlayerStats


async def unlock_anniversary_for_old_players():
    """为老玩家解锁周年成就"""

    # 设置截止日期
    cutoff_date = datetime(2025, 10, 4)
    achievement_id = "first_anniversary"

    # 成就奖励配置
    rewards = {
        "gold": 50000,
        "exp": 10000,
        "attribute_points": 30
    }

    print("=" * 60)
    print("🎂 诡修仙一周年成就解锁脚本")
    print("=" * 60)
    print(f"截止日期: {cutoff_date.strftime('%Y-%m-%d')}")
    print(f"成就ID: {achievement_id}")
    print(f"奖励: 金币{rewards['gold']} 经验{rewards['exp']} 属性点{rewards['attribute_points']}")
    print()

    async with AsyncSessionLocal() as session:
        try:
            # 1. 查询所有符合条件的老玩家
            print("📊 正在查询符合条件的玩家...")
            result = await session.execute(
                select(Player).where(Player.created_at < cutoff_date)
            )
            old_players = result.scalars().all()

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
                try:
                    # 检查是否已解锁
                    existing_result = await session.execute(
                        select(PlayerAchievement).where(
                            and_(
                                PlayerAchievement.player_id == player.id,
                                PlayerAchievement.achievement_id == achievement_id,
                                PlayerAchievement.is_completed == True
                            )
                        )
                    )
                    existing = existing_result.scalar_one_or_none()

                    if existing:
                        print(f"⏭️  跳过 {player.nickname} (UID:{player.uid}) - 已解锁")
                        skipped_count += 1
                        continue

                    # 初始化PlayerStats（如果不存在）
                    stats_result = await session.execute(
                        select(PlayerStats).where(PlayerStats.player_id == player.id)
                    )
                    stats = stats_result.scalar_one_or_none()

                    if not stats:
                        stats = PlayerStats(player_id=player.id)
                        session.add(stats)

                    # 创建成就记录
                    achievement_record = PlayerAchievement(
                        player_id=player.id,
                        achievement_id=achievement_id,
                        is_completed=True,
                        reward_claimed=True,
                        unlocked_at=datetime.now()
                    )
                    session.add(achievement_record)

                    # 发放奖励
                    player.gold += rewards["gold"]
                    player.exp += rewards["exp"]
                    player.attribute_points += rewards["attribute_points"]
                    session.add(player)

                    print(f"✅ 解锁成功: {player.nickname} (UID:{player.uid})")
                    print(f"   创建时间: {player.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
                    unlocked_count += 1

                except Exception as e:
                    print(f"❌ 错误: {player.nickname} (UID:{player.uid}) - {str(e)}")
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
