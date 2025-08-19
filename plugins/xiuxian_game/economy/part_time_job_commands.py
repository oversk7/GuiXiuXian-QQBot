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
from .part_time_job_service import PartTimeJobService


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
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await work_cmd.finish("⛔ 请先创建角色")

        args_text = args.extract_plain_text().strip()

        if not args_text:
            # 查看当前位置的工作机会
            success, msg, jobs = await PartTimeJobService.get_available_jobs_at_location(session, player)

            if not success:
                await work_cmd.finish(message_add_head(f"❌ {msg}", event))

            if not jobs:
                await work_cmd.finish(message_add_head("📍 当前位置没有工作机会\n💡 使用【工作地点】查看所有工作地点", event))

            # 构建工作列表消息
            lines = [f"💼 {msg}", "━━━━━━━━━━━━━"]
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

                lines.append(f"{job['emoji']} {i}. {job['name']}")
                lines.append(f"   💰 基础收入：{job['base_reward']}金币")
                lines.append(f"   ⏰ 工作时长：{time_str}")
                lines.append(f"   📝 {job['description']}")
                if i < len(jobs):
                    lines.append("")

            lines.extend([
                "━━━━━━━━━━━━━",
                "💡 使用【打工 工作名称】开始工作",
                "💡 例如：打工 便利店收银员"
            ])

            await work_cmd.finish(message_add_head("\n".join(lines), event))

        else:
            # 开始指定工作
            # 检查频率限制
            can_work, limit_msg = check_action_limit(event.get_user_id(), "start_work")
            if not can_work:
                await work_cmd.finish(message_add_head(f"❌ {limit_msg}", event))

            # 先尝试通过工作名称匹配
            job_type = None
            for jtype, jconfig in PartTimeJobService.JOB_TYPES.items():
                if args_text in jconfig["name"] or args_text == jconfig["name"]:
                    job_type = jtype
                    break

            if not job_type:
                await work_cmd.finish(message_add_head(f"❌ 找不到工作：{args_text}\n💡 使用【打工】查看可用工作", event))

            success, msg, job = await PartTimeJobService.start_job(session, player, job_type)

            if not success:
                await work_cmd.finish(message_add_head(f"❌ {msg}", event))

            # 记录操作
            record_action(event.get_user_id(), "start_work")

            job_config = PartTimeJobService.JOB_TYPES[job_type]
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

            result_msg = (
                f"✅ {msg}\n"
                f"━━━━━━━━━━━━━\n"
                f"{job_config['emoji']} 工作：{job_config['name']}\n"
                f"💰 预期收入：{job_config['base_reward']}+ 金币\n"
                f"⏰ 工作时长：{duration_str}\n"
                f"🕐 完成时间：{end_time_str}\n"
                f"━━━━━━━━━━━━━\n"
                f"💡 使用【收工】完成工作并获得奖励"
            )

            await work_cmd.finish(message_add_head(result_msg, event))


@finish_work_cmd.handle()
async def handle_finish_work(event: MessageEvent):
    """处理收工命令"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await finish_work_cmd.finish("⛔ 请先创建角色")

        success, msg, result = await PartTimeJobService.complete_job(session, player)

        if not success:
            await finish_work_cmd.finish(message_add_head(f"❌ {msg}", event))

        # 构建奖励消息
        lines = [
            f"🎉 {result['job_name']} 工作完成！",
            "━━━━━━━━━━━━━",
            f"💰 基础收入：{result['base_reward']} 金币"
        ]

        if result['bonus_reward'] != 0:
            if result['special_event']:
                lines.append(f"🎁 特殊事件：{result['special_event']['description']}")
                if result['bonus_reward'] > 0:
                    lines.append(f"✨ 额外奖励：+{result['bonus_reward']} 金币")
                else:
                    lines.append(f"💔 收入减少：{result['bonus_reward']} 金币")

        lines.extend([
            f"💎 总收入：{result['total_reward']} 金币",
            f"🔥 连续工作：{result['current_streak']} 天",
            "━━━━━━━━━━━━━",
            f"💰 当前金币：{player.gold}"
        ])

        await finish_work_cmd.finish(message_add_head("\n".join(lines), event))


@work_status_cmd.handle()
async def handle_work_status(event: MessageEvent):
    """处理工作状态命令"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await work_status_cmd.finish("⛔ 请先创建角色")

        success, msg, status = await PartTimeJobService.get_current_job_status(session, player)

        if not success:
            await work_status_cmd.finish(message_add_head(f"ℹ️ {msg}", event))

        if status['is_completed']:
            result_msg = (
                f"✅ 工作已完成！\n"
                f"━━━━━━━━━━━━━\n"
                f"{status['job_emoji']} {status['job_name']}\n"
                f"⏰ 完成时间：{status['end_time'].strftime('%H:%M')}\n"
                f"━━━━━━━━━━━━━\n"
                f"💡 使用【收工】获得奖励"
            )
        else:
            remaining = status['remaining_time']
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)

            result_msg = (
                f"⏳ 工作进行中...\n"
                f"━━━━━━━━━━━━━\n"
                f"{status['job_emoji']} {status['job_name']}\n"
                f"⏰ 开始时间：{status['start_time'].strftime('%H:%M')}\n"
                f"🕐 完成时间：{status['end_time'].strftime('%H:%M')}\n"
                f"⏱️ 剩余时间：{hours}小时{minutes}分钟\n"
                f"━━━━━━━━━━━━━\n"
                f"💡 完成后使用【收工】获得奖励"
            )

        await work_status_cmd.finish(message_add_head(result_msg, event))


@work_locations_cmd.handle()
async def handle_work_locations(event: MessageEvent):
    """处理工作地点命令"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await work_locations_cmd.finish("⛔ 请先创建角色")

        locations = await PartTimeJobService.get_job_locations_list(session)

        if not locations:
            await work_locations_cmd.finish(message_add_head("❌ 暂无工作地点", event))

        lines = ["🏢 工作地点一览", "━━━━━━━━━━━━━"]

        for location in locations:
            lines.append(f"📍 {location['name']} ({location['x']}, {location['y']})")
            lines.append(f"   💼 工作数量：{location['job_count']}个")
            lines.append(f"   🎯 等级要求：{location['required_level']}级")
            lines.append(f"   📝 {location['description']}")
            lines.append("")

        lines.extend([
            "━━━━━━━━━━━━━",
            "💡 前往对应坐标后使用【打工】查看工作",
            "💡 使用【导航 x y】快速前往"
        ])

        await work_locations_cmd.finish(message_add_head("\n".join(lines), event))


@work_history_cmd.handle()
async def handle_work_history(event: MessageEvent):
    """处理打工记录命令"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await work_history_cmd.finish("⛔ 请先创建角色")

        history = await PartTimeJobService.get_player_job_history(session, player.id, 5)

        if not history:
            await work_history_cmd.finish(message_add_head("📝 暂无打工记录", event))

        lines = ["📋 最近打工记录", "━━━━━━━━━━━━━"]

        for i, job in enumerate(history, 1):
            completed_time = job['completed_time'].strftime("%m-%d %H:%M")
            lines.append(f"{job['job_emoji']} {i}. {job['job_name']}")
            lines.append(f"   💰 收入：{job['total_reward']} 金币")
            lines.append(f"   ⏰ 完成：{completed_time}")

            if job['special_event']:
                lines.append(f"   🎁 {job['special_event']}")

            if i < len(history):
                lines.append("")

        await work_history_cmd.finish(message_add_head("\n".join(lines), event))


@work_stats_cmd.handle()
async def handle_work_stats(event: MessageEvent):
    """处理打工统计命令"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await work_stats_cmd.finish("⛔ 请先创建角色")

        stats = await PartTimeJobService.get_or_create_player_stats(session, player.id)

        # 计算平均收入
        avg_income = stats.total_earnings // max(stats.total_jobs_completed, 1)

        lines = [
            f"📊 {player.nickname} 的打工统计",
            "━━━━━━━━━━━━━",
            f"💼 完成工作：{stats.total_jobs_completed} 次",
            f"💰 总收入：{stats.total_earnings} 金币",
            f"📈 平均收入：{avg_income} 金币/次",
            f"⏰ 总工时：{stats.total_work_hours} 小时",
            f"🔥 当前连击：{stats.current_streak} 天",
            f"🏆 最高连击：{stats.max_streak} 天"
        ]

        if stats.favorite_job_type and stats.favorite_job_type in PartTimeJobService.JOB_TYPES:
            fav_job = PartTimeJobService.JOB_TYPES[stats.favorite_job_type]
            lines.append(f"❤️ 偏好工作：{fav_job['name']}")

        await work_stats_cmd.finish(message_add_head("\n".join(lines), event))


# 帮助命令
work_help_cmd = on_command("打工帮助", aliases={"工作帮助"}, block=True, priority=5)


@work_help_cmd.handle()
async def handle_work_help(event: MessageEvent):
    """处理打工帮助命令"""
    help_msg = (
        "💼 打工系统使用指南 (年轻玩家专属优化)\n"
        "━━━━━━━━━━━━━\n"
        "📍 基本流程：\n"
        "1. 前往工作地点坐标\n"
        "2. 使用【打工】查看可用工作\n"
        "3. 使用【打工 工作名称】开始工作\n"
        "4. 等待工作完成后使用【收工】获得奖励\n"
        "\n"
        "🏢 工作地点：\n"
        "• 上京商业中心 (0,0) - 服务业工作\n"
        "• 荔湾镇工业区 (120,200) - 体力工作\n"
        "• 郸城娱乐街区 (120,120) - 轻松工作\n"
        "• 东郊物流中心 (390,50) - 物流工作\n"
        "\n"
        "⚡ 超快节奏体验：\n"
        "• 工作时长：2-3分钟 (极速完成!)\n"
        "• 高工资：60-180金币/次 + 特殊事件奖励\n"
        "• 特殊事件奖励丰厚，最高300金币!\n"
        "• 频率限制：每小时最多10次，每次间隔1分钟\n"
        "\n"
        "💰 收入计算：\n"
        "基础收入 + 等级加成 + 运气加成 + 连续奖励 + 特殊事件\n"
        "\n"
        "📋 相关命令：\n"
        "• 打工 - 查看当前位置工作\n"
        "• 打工 [工作名] - 开始工作\n"
        "• 收工 - 完成工作获得奖励\n"
        "• 工作状态 - 查看当前工作状态\n"
        "• 工作地点 - 查看所有工作地点\n"
        "• 打工记录 - 查看打工历史\n"
        "• 打工统计 - 查看打工数据\n"
        "\n"
        "💡 小贴士：\n"
        "• 连续打工可获得额外奖励\n"
        "• 运气值影响收入和特殊事件\n"
        "• 不同工作有不同的等级要求\n"
        "• 特殊事件可能带来额外收入\n"
        "• 适合碎片化时间，随时开始!"
    )

    await work_help_cmd.finish(message_add_head(help_msg, event))