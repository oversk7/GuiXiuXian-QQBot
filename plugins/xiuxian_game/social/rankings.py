from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from sqlalchemy import select, func

from ..models.db import safe_session
from ..models.player import Player
from ..models.marriage import Marriage
from ..models.mentorship import Mentorship
from ..utils import message_add_head
from .mentorship_service import MentorshipService


# ==================== 恩爱榜 ====================
love_ranking_cmd = on_command("恩爱榜", aliases={"夫妻榜", "恩爱排行榜"}, block=True, priority=5)

@love_ranking_cmd.handle()
async def handle_love_ranking(event: MessageEvent):
    async with safe_session() as session:
        # 按礼物总价值排序获取前10对夫妻
        stmt = select(Marriage).order_by(Marriage.total_gift_value.desc()).limit(10)
        marriages = (await session.execute(stmt)).scalars().all()
        
        if not marriages:
            await love_ranking_cmd.finish("暂无恩爱榜数据")
        
        lines = ["💕 恩爱排行榜", "▃▃▃▃▃▃▃▃▃▃"]
        
        for idx, marriage in enumerate(marriages, 1):
            player1 = await session.get(Player, marriage.player1_id)
            player2 = await session.get(Player, marriage.player2_id)
            
            if not player1 or not player2:
                continue
            
            # 使用emoji装饰
            rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            
            lines.append(
                f"{rank_emoji} {player1.nickname}[UID:{player1.uid}] ❤️ {player2.nickname}[UID:{player2.uid}]"
            )
            lines.append(f"   💝 恩爱值：{marriage.total_gift_value}")
            lines.append(f"   💒 结婚时间：{marriage.married_at.strftime('%Y-%m-%d')}")
            lines.append("")  # 空行分隔
        
        # 移除最后的空行
        if lines and lines[-1] == "":
            lines.pop()
        
        await love_ranking_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 恩师榜 ====================
mentor_ranking_cmd = on_command("恩师榜", aliases={"师父榜", "恩师排行榜"}, block=True, priority=5)

@mentor_ranking_cmd.handle()
async def handle_mentor_ranking(event: MessageEvent):
    async with safe_session() as session:
        # 获取恩师点排行榜
        rankings = await MentorshipService.get_mentor_points_ranking(session, 10)
        
        if not rankings:
            await mentor_ranking_cmd.finish("暂无恩师榜数据")
        
        # 导入境界映射函数
        from ..player.info import realm_by_level_and_reincarnation

        lines = ["🎓 恩师排行榜", "▃▃▃▃▃▃▃▃▃▃"]

        for idx, (master, total_points) in enumerate(rankings, 1):
            # 获取该师父的徒弟数量
            disciples = await MentorshipService.get_disciples(session, master.id)
            disciple_count = len(disciples)

            # 使用emoji装饰
            rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."

            realm_name = realm_by_level_and_reincarnation(master.level, master.reincarnation_level)
            lines.append(f"{rank_emoji} {master.nickname}[UID:{master.uid}] Lv.{master.level} {realm_name}")
            lines.append(f"   ⭐ 恩师点：{total_points}")
            lines.append(f"   👥 徒弟数：{disciple_count}")
            lines.append("")  # 空行分隔
        
        # 移除最后的空行
        if lines and lines[-1] == "":
            lines.pop()
        
        await mentor_ranking_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 社交统计 ====================
social_stats_cmd = on_command("社交统计", aliases={"社交信息"}, block=True, priority=5)

@social_stats_cmd.handle()
async def handle_social_stats(event: MessageEvent):
    async with safe_session() as session:
        # 统计总的婚姻数量
        marriage_count = (await session.execute(select(func.count(Marriage.id)))).scalar_one()
        
        # 统计总的师徒关系数量
        mentorship_count = (await session.execute(select(func.count(Mentorship.id)))).scalar_one()
        
        # 统计最高恩爱值
        max_love_stmt = select(func.max(Marriage.total_gift_value))
        max_love_value = (await session.execute(max_love_stmt)).scalar_one() or 0
        
        # 统计最高恩师点
        max_mentor_stmt = select(func.max(Mentorship.mentor_points))
        max_mentor_points = (await session.execute(max_mentor_stmt)).scalar_one() or 0
        
        lines = [
            "📊 社交系统统计",
            "━━━━━━━━━━━━━━",
            f"💒 总夫妻对数：{marriage_count}",
            f"🎓 总师徒对数：{mentorship_count}",
            f"💝 最高恩爱值：{max_love_value}",
            f"⭐ 最高恩师点：{max_mentor_points}",
            "",
            "💡 使用「恩爱榜」查看夫妻排行",
            "💡 使用「恩师榜」查看师父排行"
        ]
        
        await social_stats_cmd.finish(message_add_head("\n".join(lines), event))
