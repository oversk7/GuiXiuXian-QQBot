from __future__ import annotations

"""打工系统命令处理器

命令：
1. 打工 - 查看当前位置的工作机会
2. 打工 <工作类型> - 开始指定工作
3. 收工 - 完成当前工作并获得奖励
4. 工作状态 - 查看当前工作状态
5. 工作地点 - 查看所有工作地点
6. 打工记录 - 查看打工历史
7. 打工统计 - 查看打工统计信息
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from datetime import datetime, timedelta

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head, check_action_limit, record_action
from ..utils_markdown import cmd, build_markdown
from .part_time_job_service import PartTimeJobService
from ..platform_utils import get_unified_player

# ==================== Feature Flag ====================
# 设置为True使用新版DI架构的PartTimeJobService，False使用旧版本
# =====================================================


# ==================== 命令定义 ====================

work_cmd = on_command("打工", block=True, priority=5)
finish_work_cmd = on_command("收工", aliases={"完成工作", "结束工作"}, block=True, priority=5)
work_status_cmd = on_command("工作状态", aliases={"打工状态"}, block=True, priority=5)
work_locations_cmd = on_command("工作地点", aliases={"打工地点"}, block=True, priority=5)
work_history_cmd = on_command("打工记录", aliases={"工作记录"}, block=True, priority=5)
work_stats_cmd = on_command("打工统计", aliases={"工作统计"}, block=True, priority=5)


# ==================== 命令处理器 ====================

@work_cmd.handle()
async def handle_work(event: MessageEvent, args: Message = CommandArg()):
    """处理打工命令"""
    # 新版本: 使用DI架构
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal
    from .part_time_job_service_new import PartTimeJobService as PartTimeJobServiceNew

    quest_completed, quest_msg = False, None

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await work_cmd.finish("⛔ 请先创建角色")

        args_text = args.extract_plain_text().strip()

        part_time_job_service = PartTimeJobServiceNew(
            player_repo=uow.players,
            part_time_job_repo=uow.part_time_jobs,
            job_location_repo=uow.job_locations,
            player_job_stats_repo=uow.player_job_stats
        )

        if not args_text:
            # 查看当前位置的工作机会
            success, msg, jobs = await part_time_job_service.get_available_jobs_at_location(player)
        else:
            # 开始指定工作
            # 检查频率限制
            can_work, limit_msg = check_action_limit(event.get_user_id(), "start_work")
            if not can_work:
                await work_cmd.finish(message_add_head(f"❌ {limit_msg}", event))

            # 先尝试通过工作名称匹配
            job_type = None
            for jtype, jconfig in PartTimeJobServiceNew.JOB_TYPES.items():
                if args_text in jconfig["name"] or args_text == jconfig["name"]:
                    job_type = jtype
                    break

            if not job_type:
                await work_cmd.finish(message_add_head(f"❌ 找不到工作：{args_text}\n💡 使用【打工】查看可用工作", event))

            success, msg, job = await part_time_job_service.start_job(player, job_type)

            # 新手任务钩子（打工成功时）
            if success:
                from ..quest.novice_quest_service import NoviceQuestService
                quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(uow.session, player, "command", {"command": "打工"})

    # 共享的消息构建逻辑
    if not args_text:
        # 查看工作机会的消息
        if not success:
            await work_cmd.finish(message_add_head(f"❌ {msg}", event))

        if not jobs:
            content = (
                f"📍 当前位置没有工作机会\n"
                f"***\n"
                f"{cmd('工作地点')}"
            )
            await work_cmd.finish(build_markdown(content))

        # 构建工作列表消息
        lines = [f"# 💼 {msg}", "***"]
        for i, job in enumerate(jobs, 1):
            # 格式化时间显示
            duration = job['duration_hours']
            if duration < 1:
                minutes = round(duration * 60, 1)
                if minutes == int(minutes):
                    time_str = f"{int(minutes)}分钟"
                else:
                    time_str = f"{minutes}分钟"
            else:
                time_str = f"{duration}小时"

            lines.append(f"{job['emoji']} {i}. {cmd(job['name'], '打工 ' + job['name'])}")
            lines.append(f"💰 基础收入：**{job['base_reward']}** 金币 | ⏰ 时长：**{time_str}**")
            lines.append(f"📝 {job['description']}")
            if i < len(jobs):
                lines.append("")

        lines.append("***")
        lines.append(f"{cmd('工作地点')} | {cmd('工作状态')} | {cmd('打工统计')}")

        await work_cmd.finish(build_markdown("\n".join(lines)))
    else:
        # 开始工作的消息
        if not success:
            await work_cmd.finish(message_add_head(f"❌ {msg}", event))

        # 记录操作
        record_action(event.get_user_id(), "start_work")

        # 获取job_config（新旧版本都有JOB_TYPES）
        from .part_time_job_service_new import PartTimeJobService as PartTimeJobServiceNew
        job_config = PartTimeJobServiceNew.JOB_TYPES[job_type]
        end_time_str = job.end_time.strftime("%H:%M")

        # 格式化工作时长显示
        duration = job_config['duration_hours']
        if duration < 1:
            minutes = round(duration * 60, 1)
            if minutes == int(minutes):
                duration_str = f"{int(minutes)}分钟"
            else:
                duration_str = f"{minutes}分钟"
        else:
            duration_str = f"{duration}小时"

        content = (
            f"# ✅ {msg}\n"
            f"***\n"
            f"{job_config['emoji']} 工作：**{job_config['name']}**\n"
            f"💰 预期收入：**{job_config['base_reward']}+** 金币\n"
            f"⏰ 工作时长：**{duration_str}**\n"
            f"🕐 完成时间：**{end_time_str}**\n"
            f"***\n"
            f"{cmd('收工')} | {cmd('工作状态')}"
        )

        # 附加新手任务消息
        if quest_completed and quest_msg:
            content += "\n\n" + quest_msg

        await work_cmd.finish(build_markdown(content))


@finish_work_cmd.handle()
async def handle_finish_work(event: MessageEvent):
    """处理收工命令"""
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal
    from .part_time_job_service_new import PartTimeJobService as PartTimeJobServiceNew

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await finish_work_cmd.finish("⛔ 请先创建角色")

        part_time_job_service = PartTimeJobServiceNew(
            player_repo=uow.players,
            part_time_job_repo=uow.part_time_jobs,
            job_location_repo=uow.job_locations,
            player_job_stats_repo=uow.player_job_stats
        )

        success, msg, result = await part_time_job_service.complete_job(player)
    if not success:
        await finish_work_cmd.finish(message_add_head(f"❌ {msg}", event))

    # 构建奖励消息
    lines = [
        f"# 🎉 {result['job_name']} 工作完成",
        "***",
        f"💰 基础收入：**{result['base_reward']}** 金币"
    ]

    if result['bonus_reward'] != 0:
        if result['special_event']:
            lines.append(f"🎁 特殊事件：{result['special_event']['description']}")
            if result['bonus_reward'] > 0:
                lines.append(f"✨ 额外奖励：**+{result['bonus_reward']}** 金币")
            else:
                lines.append(f"💔 收入减少：**{result['bonus_reward']}** 金币")

    lines.extend([
        f"💎 总收入：**{result['total_reward']}** 金币",
        f"🔥 连续工作：**{result['current_streak']}** 天",
        "***",
        f"💰 当前金币：**{player.gold}**",
        "",
        f"{cmd('打工')} | {cmd('打工统计')} | {cmd('工作状态')}"
    ])

    await finish_work_cmd.finish(build_markdown("\n".join(lines)))


@work_status_cmd.handle()
async def handle_work_status(event: MessageEvent):
    """处理工作状态命令"""
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal
    from .part_time_job_service_new import PartTimeJobService as PartTimeJobServiceNew
    from ..platform_utils import get_unified_player, is_guild_message

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            if is_guild_message(event):
                await work_status_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await work_status_cmd.finish("⛔ 请先创建角色")

        part_time_job_service = PartTimeJobServiceNew(
            player_repo=uow.players,
            part_time_job_repo=uow.part_time_jobs,
            job_location_repo=uow.job_locations,
            player_job_stats_repo=uow.player_job_stats
        )

        success, msg, status = await part_time_job_service.get_current_job_status(player)
    if not success:
        content = (
            f"ℹ️ {msg}\n"
            f"***\n"
            f"{cmd('打工')} | {cmd('工作地点')}"
        )
        await work_status_cmd.finish(build_markdown(content))

    if status['is_completed']:
        content = (
            f"# ✅ 工作已完成\n"
            f"***\n"
            f"{status['job_emoji']} **{status['job_name']}**\n"
            f"⏰ 完成时间：**{status['end_time'].strftime('%H:%M')}**\n"
            f"***\n"
            f"{cmd('收工')}"
        )
    else:
        remaining = status['remaining_time']
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)

        content = (
            f"# ⏳ 工作进行中\n"
            f"***\n"
            f"{status['job_emoji']} **{status['job_name']}**\n"
            f"⏰ 开始时间：**{status['start_time'].strftime('%H:%M')}**\n"
            f"🕐 完成时间：**{status['end_time'].strftime('%H:%M')}**\n"
            f"⏱️ 剩余时间：**{hours}小时{minutes}分钟**\n"
            f"***\n"
            f"{cmd('收工')} | {cmd('工作状态')}"
        )

    await work_status_cmd.finish(build_markdown(content))


@work_locations_cmd.handle()
async def handle_work_locations(event: MessageEvent):
    """处理工作地点命令"""
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal
    from .part_time_job_service_new import PartTimeJobService as PartTimeJobServiceNew

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await work_locations_cmd.finish("⛔ 请先创建角色")

        part_time_job_service = PartTimeJobServiceNew(
            player_repo=uow.players,
            part_time_job_repo=uow.part_time_jobs,
            job_location_repo=uow.job_locations,
            player_job_stats_repo=uow.player_job_stats
        )

        locations = await part_time_job_service.get_job_locations_list()
    if not locations:
        await work_locations_cmd.finish(message_add_head("❌ 暂无工作地点", event))

    lines = ["# 🏢 工作地点一览", "***"]

    for location in locations:
        lines.append(f"📍 {cmd(location['name'], '导航 ' + location['name'])} ({location['x']}, {location['y']})")
        lines.append(f"💼 工作数量：**{location['job_count']}** 个 | 🎯 等级要求：**{location['required_level']}** 级")
        lines.append(f"📝 {location['description']}")
        lines.append("")

    lines.append("***")
    lines.append(f"{cmd('打工')} | {cmd('工作状态')}")

    await work_locations_cmd.finish(build_markdown("\n".join(lines)))


@work_history_cmd.handle()
async def handle_work_history(event: MessageEvent):
    """处理打工记录命令"""
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal
    from .part_time_job_service_new import PartTimeJobService as PartTimeJobServiceNew

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await work_history_cmd.finish("⛔ 请先创建角色")

        part_time_job_service = PartTimeJobServiceNew(
            player_repo=uow.players,
            part_time_job_repo=uow.part_time_jobs,
            job_location_repo=uow.job_locations,
            player_job_stats_repo=uow.player_job_stats
        )

        history = await part_time_job_service.get_player_job_history(player.id, 5)
    if not history:
        content = (
            f"📝 暂无打工记录\n"
            f"***\n"
            f"{cmd('打工')} | {cmd('工作地点')}"
        )
        await work_history_cmd.finish(build_markdown(content))

    lines = ["# 📋 最近打工记录", "***"]

    for i, job in enumerate(history, 1):
        completed_time = job['completed_time'].strftime("%m-%d %H:%M")
        lines.append(f"{job['job_emoji']} {i}. **{job['job_name']}**")
        lines.append(f"💰 收入：**{job['total_reward']}** 金币 | ⏰ 完成：{completed_time}")

        if job['special_event']:
            lines.append(f"🎁 {job['special_event']}")

        if i < len(history):
            lines.append("")

    lines.append("***")
    lines.append(f"{cmd('打工')} | {cmd('打工统计')}")

    await work_history_cmd.finish(build_markdown("\n".join(lines)))


@work_stats_cmd.handle()
async def handle_work_stats(event: MessageEvent):
    """处理打工统计命令"""
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal
    from .part_time_job_service_new import PartTimeJobService as PartTimeJobServiceNew

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await work_stats_cmd.finish("⛔ 请先创建角色")

        part_time_job_service = PartTimeJobServiceNew(
            player_repo=uow.players,
            part_time_job_repo=uow.part_time_jobs,
            job_location_repo=uow.job_locations,
            player_job_stats_repo=uow.player_job_stats
        )

        stats = await part_time_job_service._player_job_stats_repo.get_or_create(player.id)
    # 计算平均收入
    avg_income = stats.total_earnings // max(stats.total_jobs_completed, 1)

    lines = [
        f"# 📊 {player.nickname} 的打工统计",
        "***",
        f"💼 完成工作：**{stats.total_jobs_completed}** 次",
        f"💰 总收入：**{stats.total_earnings}** 金币",
        f"📈 平均收入：**{avg_income}** 金币/次",
        f"⏰ 总工时：**{stats.total_work_hours}** 小时",
        f"🔥 当前连击：**{stats.current_streak}** 天",
        f"🏆 最高连击：**{stats.max_streak}** 天"
    ]

    # 获取JOB_TYPES（新旧版本都有）
    from .part_time_job_service_new import PartTimeJobService as PartTimeJobServiceNew
    job_types = PartTimeJobServiceNew.JOB_TYPES
    if stats.favorite_job_type and stats.favorite_job_type in job_types:
        fav_job = job_types[stats.favorite_job_type]
        lines.append(f"❤️ 偏好工作：**{fav_job['name']}**")

    lines.append("***")
    lines.append(f"{cmd('打工')} | {cmd('打工记录')} | {cmd('工作地点')}")

    await work_stats_cmd.finish(build_markdown("\n".join(lines)))


# 帮助命令
work_help_cmd = on_command("打工帮助", aliases={"工作帮助"}, block=True, priority=5)


@work_help_cmd.handle()
async def handle_work_help(event: MessageEvent):
    """处理打工帮助命令"""
    content = (
        f"# 💼 打工系统使用指南\n"
        f"***\n"
        f"📍 基本流程\n"
        f"1. 前往工作地点坐标\n"
        f"2. 使用 {cmd('打工')} 查看可用工作\n"
        f"3. 使用 {cmd('打工 工作名称', '打工 ')} 开始工作\n"
        f"4. 等待完成后使用 {cmd('收工')} 获得奖励\n\n"
        f"🏢 工作地点\n"
        f"▫️ {cmd('上京商业中心', '导航 上京商业中心')} (0,0) - 服务业\n"
        f"▫️ {cmd('荔湾镇工业区', '导航 荔湾镇工业区')} (120,200) - 体力\n"
        f"▫️ {cmd('郸城娱乐街区', '导航 郸城娱乐街区')} (120,120) - 轻松\n"
        f"▫️ {cmd('东郊物流中心', '导航 东郊物流中心')} (390,50) - 物流\n\n"
        f"⚡ 超快节奏体验\n"
        f"▫️ 工作时长：**2-3**分钟 | 工资：**60-180**金币/次\n"
        f"▫️ 特殊事件最高**300**金币 | 每小时最多**10**次\n\n"
        f"💰 收入 = 基础 + 等级加成 + 运气加成 + 连续奖励 + 特殊事件\n"
        f"***\n"
        f"{cmd('打工')} | {cmd('收工')} | {cmd('工作状态')}\n"
        f"{cmd('工作地点')} | {cmd('打工记录')} | {cmd('打工统计')}"
    )

    await work_help_cmd.finish(build_markdown(content))