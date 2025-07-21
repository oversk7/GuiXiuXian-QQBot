"""每日鬼怪入侵刷新机制"""
import random
from datetime import date, datetime, time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.ghost_invasion import GhostInvasion
from ..config import config


class DailyGhostRefresh:
    """每日鬼怪刷新服务"""

    @staticmethod
    def should_refresh_today(target_date: date = None) -> bool:
        """检查今天是否应该刷新鬼怪（18点后）"""
        if target_date is None:
            target_date = date.today()

        now = datetime.now()
        today = now.date()

        # 如果不是今天，直接返回False
        if target_date != today:
            return False

        # 检查是否已过18点
        refresh_time = time(17, 0)  # 18:00
        current_time = now.time()

        return current_time >= refresh_time

    @staticmethod
    async def refresh_daily_invasions(session: AsyncSession, target_date: date = None) -> int:
        """刷新每日鬼怪入侵事件"""
        if target_date is None:
            target_date = date.today()

        # 检查今日是否已经刷新过
        result = await session.execute(
            select(GhostInvasion).where(GhostInvasion.invasion_date == target_date)
        )
        existing_invasions = result.scalars().all()

        if existing_invasions:
            return len(existing_invasions)  # 已经刷新过，返回现有数量

        # 如果是今天，检查是否已过18点
        if target_date == date.today() and not DailyGhostRefresh.should_refresh_today(target_date):
            return 0  # 还没到18点，不刷新

        # 生成1-3只鬼怪入侵
        invasion_count = random.randint(1, 3)
        ghost_configs = config.ghosts_config["all"]

        if not ghost_configs:
            return 0  # 没有鬼怪配置

        created_count = 0
        for _ in range(invasion_count):
            # 随机选择鬼怪类型
            ghost_config = random.choice(ghost_configs)

            # 随机生成坐标（在现实世界大都会的合理范围内）
            x = random.randint(-50, 50)
            y = random.randint(-50, 50)

            # 创建入侵事件
            invasion = GhostInvasion(
                ghost_id=ghost_config["ghost_id"],
                region="大都会",
                x=x,
                y=y,
                invasion_date=target_date
            )

            session.add(invasion)
            created_count += 1

        await session.commit()
        return created_count
    
    @staticmethod
    async def get_invasion_summary(session: AsyncSession, target_date: date = None) -> str:
        """获取入侵事件摘要"""
        if target_date is None:
            target_date = date.today()

        # 如果是今天且还没到18点，显示等待提示
        if target_date == date.today() and not DailyGhostRefresh.should_refresh_today(target_date):
            now = datetime.now()
            current_time_str = now.strftime("%H:%M")
            return (
                f"📰 今日鬼怪入侵报告 ({target_date})\n"
                "━━━━━━━━━━━━━\n"
                f"🕐 当前时间: {current_time_str}\n"
                "⏰ 鬼怪将在18:00后开始入侵现实世界\n"
                "💡 请耐心等待，18点后再次查看入侵情况"
            )

        result = await session.execute(
            select(GhostInvasion).where(GhostInvasion.invasion_date == target_date)
        )
        invasions = result.scalars().all()

        if not invasions:
            return "📰 今日暂无鬼怪入侵报告"

        summary_lines = [f"📰 今日鬼怪入侵报告 ({target_date})"]
        summary_lines.append("━━━━━━━━━━━━━")

        for i, invasion in enumerate(invasions, 1):
            ghost_config = config.ghosts_config["by_id"].get(invasion.ghost_id, {})
            ghost_name = ghost_config.get("name", invasion.ghost_id)
            status = "已镇压" if invasion.is_suppressed else "待镇压"
            status_emoji = "✅" if invasion.is_suppressed else "🔥"

            summary_lines.append(
                f"{status_emoji} {i}. {ghost_name} - {invasion.location_str} ({status})"
            )

            if invasion.is_suppressed and invasion.suppressed_by:
                # 这里可以添加镇压者信息，但需要查询玩家表
                summary_lines.append(f"   镇压者: UID-{invasion.suppressed_by}")

        summary_lines.append("━━━━━━━━━━━━━")
        active_count = sum(1 for inv in invasions if not inv.is_suppressed)
        summary_lines.append(f"📊 总计: {len(invasions)}只 | 待镇压: {active_count}只")

        return "\n".join(summary_lines)
