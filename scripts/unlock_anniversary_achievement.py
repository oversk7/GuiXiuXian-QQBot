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
from pathlib import Path
from datetime import datetime

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from plugins.xiuxian_game.models.db import async_session_maker
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.achievement.achievement_service import AchievementService


async def unlock_anniversary_for_old_players():
    """为老玩家解锁周年成就"""

    # 设置截止日期
    cutoff_date = datetime(2025, 10, 4)
    achievement_id = "first_anniversary"

    print("=" * 60)
    print("🎂 诡修仙一周年成就解锁脚本")
    print("=" * 60)
    print(f"截止日期: {cutoff_date.strftime('%Y-%m-%d')}")
    print(f"成就ID: {achievement_id}")
    print()

    async with async_session_maker() as session:
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
                # 初始化玩家统计数据（如果不存在）
                await AchievementService.init_player_stats(session, player.id)

                # 尝试解锁成就
                from plugins.xiuxian_game.models.achievement import PlayerAchievement
                from sqlalchemy import and_

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

                # 解锁成就
                unlock_msg = await AchievementService.unlock_achievement(
                    session, player, achievement_id
                )

                if unlock_msg:
                    print(f"✅ 解锁成功: {player.nickname} (UID:{player.uid})")
                    print(f"   创建时间: {player.created_at.strftime('%Y-%m-%d')}")
                    unlocked_count += 1
                else:
                    print(f"⚠️  解锁失败: {player.nickname} (UID:{player.uid}) - 成就不存在")
                    error_count += 1

            except Exception as e:
                print(f"❌ 错误: {player.nickname} (UID:{player.uid}) - {str(e)}")
                error_count += 1
                continue

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
