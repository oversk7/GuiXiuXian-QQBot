"""
公会任务系统命令
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from ..models.db import safe_session
from ..models.player import Player
from ..utils_markdown import cmd, build_markdown
from .guild_task_service import GuildTaskService
from .guild_task_service_new import GuildTaskService as GuildTaskServiceNew  # DI版本
from ..platform_utils import get_unified_player

# Feature Flag（在文件顶部靠近其他常量的位置）
# ==================== 公会任务 ====================
guild_task_cmd = on_command("公会任务", aliases={"公会日常", "公会周常"}, block=True, priority=5)

@guild_task_cmd.handle()
async def handle_guild_task(event: MessageEvent):
    """查看公会任务列表"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await guild_task_cmd.finish("请先创建角色")

        if not player.guild_id:
            await guild_task_cmd.finish("你未加入任何公会")

        # 获取可用任务列表
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.player_task_stats_repository import PlayerTaskStatsRepository
        from ..infrastructure.repositories.guild_task_record_repository import GuildTaskRecordRepository
        from ..infrastructure.repositories.player_donation_log_repository import PlayerDonationLogRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository

        task_service = GuildTaskServiceNew(
            player_repo=PlayerRepository(session),
            guild_repo=GuildRepository(session),
            player_task_stats_repo=PlayerTaskStatsRepository(session),
            guild_task_record_repo=GuildTaskRecordRepository(session),
            player_donation_log_repo=PlayerDonationLogRepository(session),
            guild_building_repo=GuildBuildingRepository(session),
        )
        tasks = await task_service.get_available_tasks(player.id)
        if not tasks:
            await guild_task_cmd.finish("暂无可用的公会任务")

        # 构建任务列表消息
        msg_lines = [
            "# 公会任务系统",
            "***",
            "**可用任务:**"
        ]

        daily_tasks = [t for t in tasks if t["type"] == "daily"]
        weekly_tasks = [t for t in tasks if t["type"] == "weekly"]

        if daily_tasks:
            msg_lines.append("\n**日常任务:**")
            for task in daily_tasks:
                status = "✅" if task["completed"] else "⏳"
                progress_text = f"(**{task['progress']}**/{task['requirement']})" if task.get('requirement', 1) > 1 else ""
                msg_lines.append(
                    f"{status} {task['name']} {progress_text}\n"
                    f"   {task['description']}\n"
                    f"   奖励: 积分+**{task['points_reward']}** 公会经验+**{task['base_exp']}**"
                )

        if weekly_tasks:
            msg_lines.append("\n**周常任务:**")
            for task in weekly_tasks:
                status = "✅" if task["completed"] else "⏳"
                progress_text = f"(**{task['progress']}**/{task['requirement']})" if task.get('requirement', 1) > 1 else ""
                msg_lines.append(
                    f"{status} {task['name']} {progress_text}\n"
                    f"   {task['description']}\n"
                    f"   奖励: 积分+**{task['points_reward']}** 公会经验+**{task['base_exp']}**"
                )

        msg_lines.extend([
            "\n***",
            "提示:",
            f"- 使用{cmd('完成公会任务')}手动领取奖励",
            "- 签到和捐献任务会自动完成",
            "***",
            f"{cmd('完成公会任务')} | {cmd('公会任务统计')} | {cmd('我的公会')}",
        ])

        await guild_task_cmd.finish(build_markdown("\n".join(msg_lines)))


# ==================== 完成公会任务 ====================
complete_guild_task_cmd = on_command("完成公会任务", aliases={"领取公会任务", "公会任务奖励"}, block=True, priority=5)

@complete_guild_task_cmd.handle()
async def handle_complete_guild_task(event: MessageEvent):
    """尝试完成所有满足条件的公会任务"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await complete_guild_task_cmd.finish("请先创建角色")

        if not player.guild_id:
            await complete_guild_task_cmd.finish("你未加入任何公会")

        # 尝试自动完成任务
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.player_task_stats_repository import PlayerTaskStatsRepository
        from ..infrastructure.repositories.guild_task_record_repository import GuildTaskRecordRepository
        from ..infrastructure.repositories.player_donation_log_repository import PlayerDonationLogRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository

        task_service = GuildTaskServiceNew(
            player_repo=PlayerRepository(session),
            guild_repo=GuildRepository(session),
            player_task_stats_repo=PlayerTaskStatsRepository(session),
            guild_task_record_repo=GuildTaskRecordRepository(session),
            player_donation_log_repo=PlayerDonationLogRepository(session),
            guild_building_repo=GuildBuildingRepository(session),
        )
        completed_tasks = await task_service.try_auto_complete_tasks(player.id)
        await session.commit()

        if completed_tasks:
            msg_lines = [
                "# 公会任务完成!",
                "***"
            ]
            msg_lines.extend(completed_tasks)
            msg_lines.extend([
                "***",
                f"{cmd('公会任务')} | {cmd('我的公会')}",
            ])
            await complete_guild_task_cmd.finish(build_markdown("\n".join(msg_lines)))
        else:
            await complete_guild_task_cmd.finish("暂无可完成的公会任务")


# ==================== 公会任务统计 ====================
guild_task_stats_cmd = on_command("公会任务统计", aliases={"公会活跃度"}, block=True, priority=5)

@guild_task_stats_cmd.handle()
async def handle_guild_task_stats(event: MessageEvent):
    """查看公会任务完成统计"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await guild_task_stats_cmd.finish("请先创建角色")

        if not player.guild_id:
            await guild_task_stats_cmd.finish("你未加入任何公会")

        # 获取个人统计和公会整体统计
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.player_task_stats_repository import PlayerTaskStatsRepository
        from ..infrastructure.repositories.guild_task_record_repository import GuildTaskRecordRepository
        from ..infrastructure.repositories.player_donation_log_repository import PlayerDonationLogRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository

        task_service = GuildTaskServiceNew(
            player_repo=PlayerRepository(session),
            guild_repo=GuildRepository(session),
            player_task_stats_repo=PlayerTaskStatsRepository(session),
            guild_task_record_repo=GuildTaskRecordRepository(session),
            player_donation_log_repo=PlayerDonationLogRepository(session),
            guild_building_repo=GuildBuildingRepository(session),
        )
        stats = await task_service.get_or_create_player_stats(player.id)
        guild_summary = await task_service.get_guild_task_summary(player.guild_id)
        msg_lines = [
            "# 公会任务统计",
            "***",
            "**个人统计:**",
            f"今日探索: **{stats.today_explorations}**次",
            f"今日战斗胜利: **{stats.today_combat_victories}**次",
            f"今日委托: **{stats.today_commissions}**次",
            f"本周委托: **{stats.week_commissions}**次",
            f"本周日常任务: **{stats.week_daily_tasks}**次",
            "",
            "**公会统计:**",
            f"公会成员: **{guild_summary['member_count']}**人",
            f"今日签到: **{guild_summary['signed_today']}**人",
            f"签到率: **{guild_summary['sign_rate']:.1%}**",
            f"活跃度: **{guild_summary['active_level']}**",
            "***",
            f"{cmd('公会任务')} | {cmd('我的公会')}",
        ]

        await guild_task_stats_cmd.finish(build_markdown("\n".join(msg_lines)))
