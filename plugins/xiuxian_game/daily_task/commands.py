"""每日任务系统指令处理"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..models.db import AsyncSessionLocal
from ..models.player import Player
from ..models.daily_task import DailyTask, TaskStatus
from ..utils_markdown import cmd, build_markdown
from ..platform_utils import require_player
from .service import DailyTaskService
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..world.location_service import LocationService
from ..world.npc_service import NPCService
from ..guild.guild_economy_service_new import GuildEconomyService
import random
from datetime import date


# ==================== 查看每日任务 ====================
daily_task_cmd = on_command("每日委托", aliases={"任务", "每日任务"}, block=True, priority=7)

@daily_task_cmd.handle()
async def handle_daily_task(event: MessageEvent):
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await require_player(uow.session, event, daily_task_cmd)
        if player.level < 30:
            await daily_task_cmd.finish("⛔ 该功能仅对Lv.30以上角色开放")

        # 实例化依赖Service
        location_service = LocationService(uow.locations)
        npc_service = NPCService(uow.session, uow.npcs)
        guild_economy_service = GuildEconomyService(
            guild_repo=uow.guilds,
            player_repo=uow.players,
            donation_log_repo=uow.player_donation_logs,
            building_repo=uow.guild_buildings
        ) if player.guild_id else None

        # 实例化DailyTaskService
        task_service = DailyTaskService(
            daily_task_repo=uow.daily_tasks,
            location_service=location_service,
            npc_service=npc_service,
            guild_economy_service=guild_economy_service
        )

        # 获取今日所有任务
        today = date.today()
        tasks = await task_service.get_player_daily_tasks(player.id, today)

        # 如果没有任务，生成新任务
        if not tasks:
            task = await task_service.generate_daily_task(player)
            tasks = [task] if task else []
            await uow.commit()

        # 获取任务汇总信息
        summary = await task_service.get_task_summary(player.id)

        # 构建消息
        lines = ["# 🏛️ 缉邪司 · 每日委托", "***"]

        if not tasks:
            lines.append("⚠️ 今日暂无委托任务")
        else:
            for i, task in enumerate(tasks, 1):
                if task.is_available():
                    status_emoji = "📋"
                    status_text = "可接取"
                elif task.is_accepted():
                    status_emoji = "⚔️"
                    status_text = "进行中"
                elif task.is_completed():
                    status_emoji = "✅"
                    status_text = "已完成"
                else:
                    status_emoji = "❌"
                    status_text = "已过期"

                lines.append(f"**{status_emoji} 委托{i} · {task.title}**")
                lines.append(f"📝 {task.description}")
                lines.append(f"📍 {cmd(task.location_str, f'导航 {task.target_x} {task.target_y}')} | 👹 {task.enemy_name} Lv.**{task.enemy_level}**")
                lines.append(f"💰 {task.get_reward_summary(bool(player.guild_id))} | 状态：{status_text}")

                if task.is_available():
                    lines.append(f"→ {cmd(f'接取委托 {i}')} | {cmd(f'接取并导航', f'接取委托 {i} 导航')}")
                elif task.is_accepted():
                    lines.append(f"→ {cmd(task.location_str, f'导航 {task.target_x} {task.target_y}')} 前往 | {cmd('完成任务')} 到达后提交")

                lines.append("***")

        # 统计信息
        lines.append(f"📈 本周完成：**{summary['weekly_completed']}**次 | 总计：**{summary['total_completed']}**次")

        # 操作提示
        available_count = sum(1 for task in tasks if task.is_available())
        accepted_count = sum(1 for task in tasks if task.is_accepted())
        completed_count = sum(1 for task in tasks if task.is_completed())

        nav_cmds = []
        if completed_count == len(tasks) and len(tasks) >= 3:
            lines.append("🎉 今日所有委托已完成，明日再来！")
        if len(tasks) < 3:
            nav_cmds.append(cmd('刷新委托'))
        nav_cmds.append(cmd('任务统计'))
        nav_cmds.append(cmd('帮助'))
        lines.append(" | ".join(nav_cmds))

        # 检查新手任务
        from ..quest.novice_quest_service import NoviceQuestService
        quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(
            uow.session, player, "command", {"command": "任务"}
        )

        if quest_completed and quest_msg:
            lines.append("")
            lines.append(quest_msg)

        await daily_task_cmd.finish(build_markdown("\n".join(lines)))


# ==================== 接取任务 ====================
accept_task_cmd = on_command("接取委托", aliases={"接取任务", "接收委托"}, block=True, priority=7)

@accept_task_cmd.handle()
async def handle_accept_task(event: MessageEvent, args: Message = CommandArg()):
    # 使用跨平台工具获取玩家数据
    from ..platform_utils import require_player

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await require_player(uow.session, event, accept_task_cmd)

        # 解析参数
        args_text = args.extract_plain_text().strip()
        task_index = 1  # 默认接取第一个任务
        auto_nav = False  # 是否自动设置导航

        if args_text:
            # 检查是否包含导航参数
            auto_nav = "--导航" in args_text or "导航" in args_text

            # 移除导航参数后解析任务编号
            task_number_text = args_text.replace("--导航", "").replace("导航", "").strip()

            if task_number_text:
                try:
                    task_index = int(task_number_text)
                    if task_index < 1:
                        await accept_task_cmd.finish("⛔ 委托编号必须是正整数")
                except ValueError:
                    await accept_task_cmd.finish("⛔ 请输入正确的委托编号")

        # 实例化依赖Service
        location_service = LocationService(uow.locations)
        npc_service = NPCService(uow.session, uow.npcs)
        guild_economy_service = GuildEconomyService(
            guild_repo=uow.guilds,
            player_repo=uow.players,
            donation_log_repo=uow.player_donation_logs,
            building_repo=uow.guild_buildings
        ) if player.guild_id else None

        # 实例化DailyTaskService
        task_service = DailyTaskService(
            daily_task_repo=uow.daily_tasks,
            location_service=location_service,
            npc_service=npc_service,
            guild_economy_service=guild_economy_service
        )

        # 获取今日任务
        today = date.today()
        tasks = await task_service.get_player_daily_tasks(player.id, today)

        # 如果没有足够的任务，生成新任务
        while len(tasks) < task_index:
            new_task = await task_service.force_generate_new_task(player)
            if new_task:
                tasks.append(new_task)
            else:
                break

        if len(tasks) < task_index:
            await accept_task_cmd.finish(f"⛔ 委托{task_index}不存在")

        task = tasks[task_index - 1]

        # 接取任务
        success, message = await task_service.accept_task(task)

        if success:
            # 如果需要自动导航
            if auto_nav:
                from ..world.navigation import NavigationTask, _euclidean_distance
                from datetime import datetime

                # 计算初始距离
                player_x = player.real_world_x if player.real_world_x is not None else (player.x or 0)
                player_y = player.real_world_y if player.real_world_y is not None else (player.y or 0)
                initial_distance = _euclidean_distance(
                    player_x, player_y, task.target_x, task.target_y
                )

                # 创建或更新导航任务
                nav_task = await uow.session.get(NavigationTask, player.id)
                if nav_task:
                    nav_task.target_x = task.target_x
                    nav_task.target_y = task.target_y
                    nav_task.last_update = datetime.now()
                    nav_task.initial_distance = initial_distance
                else:
                    nav_task = NavigationTask(
                        player_id=player.id,
                        target_x=task.target_x,
                        target_y=task.target_y,
                        last_update=datetime.now(),
                        initial_distance=initial_distance
                    )
                    uow.session.add(nav_task)

            await uow.commit()

            msg = (
                f"# ✅ 委托接取成功\n"
                f"***\n"
                f"**📋 委托{task_index} · {task.title}**\n"
                f"📝 {task.description}\n"
                f"📍 {cmd(task.location_str, f'导航 {task.target_x} {task.target_y}')} | 👹 {task.enemy_name} Lv.**{task.enemy_level}**\n"
                f"💰 {task.get_reward_summary(bool(player.guild_id))}\n"
                f"***\n"
            )

            if auto_nav:
                msg += f"🧭 已自动导航至任务位置\n"
                msg += f"{cmd('导航')} 查看进度 | {cmd('中断导航')} 停止"
            else:
                msg += f"🧭 {cmd('前往任务点', f'导航 {task.target_x} {task.target_y}')} | {cmd('观察')} 到达后查看鬼怪 | {cmd('完成任务')}"
        else:
            msg = f"⛔ {message}"

    await accept_task_cmd.finish(build_markdown(msg))


# ==================== 完成任务 ====================
complete_task_cmd = on_command("完成任务", aliases={"完成委托", "退邪"}, block=True, priority=7)

@complete_task_cmd.handle()
async def handle_complete_task(event: MessageEvent):
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await require_player(uow.session, event, complete_task_cmd)

        # 实例化依赖Service
        location_service = LocationService(uow.locations)
        npc_service = NPCService(uow.session, uow.npcs)
        guild_economy_service = GuildEconomyService(
            guild_repo=uow.guilds,
            player_repo=uow.players,
            donation_log_repo=uow.player_donation_logs,
            building_repo=uow.guild_buildings
        ) if player.guild_id else None

        # 实例化DailyTaskService
        task_service = DailyTaskService(
            daily_task_repo=uow.daily_tasks,
            location_service=location_service,
            npc_service=npc_service,
            guild_economy_service=guild_economy_service
        )

        # 获取今日已接取的任务
        today = date.today()
        tasks = await task_service.get_player_daily_tasks(player.id, today)
        accepted_tasks = [task for task in tasks if task.is_accepted()]

        if not accepted_tasks:
            await complete_task_cmd.finish("⛔ 你没有已接取的任务")

        # 检查当前位置是否有可完成的任务
        current_x, current_y = player.x, player.y
        completable_tasks = [
            task for task in accepted_tasks
            if task.target_x == current_x and task.target_y == current_y
        ]

        if not completable_tasks:
            task_locations = [f"{task.location_str}" for task in accepted_tasks]
            await complete_task_cmd.finish(
                f"⛔ 当前位置没有可完成的任务\n"
                f"💡 请前往以下任务位置：\n" + "\n".join(task_locations)
            )

        # 选择第一个可完成的任务
        task = completable_tasks[0]

        # 位置检查已在上面完成

        # 完成任务（检测NPC是否死亡）
        success, message, rewards = await task_service.complete_task(player, task)

        if success:
            # 更新委托完成统计（用于公会任务）
            if player.guild_id:
                from ..guild.guild_task_service_new import GuildTaskService as GuildTaskServiceNew

                guild_task_service = GuildTaskServiceNew(
                    player_repo=uow.players,
                    guild_repo=uow.guilds,
                    player_task_stats_repo=uow.player_task_stats,
                    guild_task_record_repo=uow.guild_task_records,
                    player_donation_log_repo=uow.player_donation_logs,
                    guild_building_repo=uow.guild_buildings,
                )
                await guild_task_service.update_commission_stats(player.id)
            await uow.commit()

            # 构建完成消息
            reward_lines = []
            if "exp" in rewards:
                reward_lines.append(f"经验+{rewards['exp']}")
            if "gold" in rewards:
                reward_lines.append(f"金币+{rewards['gold']}")
            if "guild_points" in rewards:
                reward_lines.append(f"积分+{rewards['guild_points']}")
            if "guild_exp" in rewards:
                reward_lines.append(f"公会经验+{rewards['guild_exp']}")

            reward_text = " ".join(reward_lines) if reward_lines else "无奖励"

            # 生成任务完成描述
            completion_descriptions = [
                f"恶鬼{task.enemy_name}已被成功诛杀，其怨气消散，化为青烟。城中阴霾尽散，百姓重获安宁。",
                f"厉鬼{task.enemy_name}伏诛，其魂魄被超度，不再作祟。城中恢复生机，百姓感激不尽。",
                f"邪鬼{task.enemy_name}已被除去，其邪法破除，城中百姓从噩梦中苏醒，重获自由。",
                f"恶灵{task.enemy_name}魂飞魄散，其作祟之力彻底消失。城中重现祥和，百姓安居乐业。"
            ]
            completion_desc = random.choice(completion_descriptions)

            msg = (
                f"# 🎉 任务完成！\n"
                f"***\n"
                f"👻 {completion_desc}\n"
                f"💰 获得奖励：**{reward_text}**\n"
                f"🏛️ 缉邪司对你的英勇表示赞赏！\n"
                f"***\n"
                f"{cmd('每日委托')} | {cmd('刷新委托')} | {cmd('任务统计')} | {cmd('帮助')}"
            )
        else:
            msg = f"⛔ {message}"

    await complete_task_cmd.finish(build_markdown(msg))


# ==================== 任务统计 ====================
task_stats_cmd = on_command("任务统计", aliases={"委托统计"}, block=True, priority=7)

@task_stats_cmd.handle()
async def handle_task_stats(event: MessageEvent):
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await require_player(uow.session, event, task_stats_cmd)

        # 实例化依赖Service
        location_service = LocationService(uow.locations)
        npc_service = NPCService(uow.session, uow.npcs)
        guild_economy_service = GuildEconomyService(
            guild_repo=uow.guilds,
            player_repo=uow.players,
            donation_log_repo=uow.player_donation_logs,
            building_repo=uow.guild_buildings
        ) if player.guild_id else None

        # 实例化DailyTaskService
        task_service = DailyTaskService(
            daily_task_repo=uow.daily_tasks,
            location_service=location_service,
            npc_service=npc_service,
            guild_economy_service=guild_economy_service
        )

        summary = await task_service.get_task_summary(player.id)

        lines = ["# 📊 缉邪司委托统计", "***"]
        lines.append(f"📅 本周完成：**{summary['weekly_completed']}** 次")
        lines.append(f"🏆 总计完成：**{summary['total_completed']}** 次")

        today_task = summary['today_task']
        if today_task:
            if today_task.is_completed():
                lines.append("✅ 今日任务：已完成")
            elif today_task.is_accepted():
                lines.append(f"⚔️ 今日任务：进行中 → {cmd('完成任务')}")
            else:
                lines.append(f"📋 今日任务：可接取 → {cmd('接取委托 1')}")
        else:
            lines.append(f"📋 今日任务：尚未生成 → {cmd('每日委托')} 查看")

        lines.append("***")
        lines.append(f"{cmd('每日委托')} | {cmd('刷新委托')} | {cmd('帮助')}")

    await task_stats_cmd.finish(build_markdown("\n".join(lines)))


# ==================== 刷新委托 ====================
refresh_task_cmd = on_command("刷新委托", aliases={"刷新任务", "更多委托"}, block=True, priority=7)

@refresh_task_cmd.handle()
async def handle_refresh_task(event: MessageEvent):
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await require_player(uow.session, event, refresh_task_cmd)
        if player.level < 30:
            await refresh_task_cmd.finish("⛔ 该功能仅对Lv.30以上角色开放")

        # 实例化依赖Service
        location_service = LocationService(uow.locations)
        npc_service = NPCService(uow.session, uow.npcs)
        guild_economy_service = GuildEconomyService(
            guild_repo=uow.guilds,
            player_repo=uow.players,
            donation_log_repo=uow.player_donation_logs,
            building_repo=uow.guild_buildings
        ) if player.guild_id else None

        # 实例化DailyTaskService
        task_service = DailyTaskService(
            daily_task_repo=uow.daily_tasks,
            location_service=location_service,
            npc_service=npc_service,
            guild_economy_service=guild_economy_service
        )

        # 获取今日任务
        today = date.today()
        tasks = await task_service.get_player_daily_tasks(player.id, today)

        if len(tasks) >= 3:
            await refresh_task_cmd.finish("⛔ 今日委托已达上限（3个），请完成后再来")

        # 生成新任务
        new_task = await task_service.force_generate_new_task(player)
        if not new_task:
            await refresh_task_cmd.finish("⛔ 生成委托失败，请稍后重试")

        await uow.commit()

        task_num = len(tasks) + 1
        msg = (
            f"# 🏛️ 新委托生成！\n"
            f"***\n"
            f"**📋 委托{task_num} · {new_task.title}**\n"
            f"📝 {new_task.description}\n"
            f"📍 {cmd(new_task.location_str, f'导航 {new_task.target_x} {new_task.target_y}')} | 👹 {new_task.enemy_name} Lv.**{new_task.enemy_level}**\n"
            f"💰 {new_task.get_reward_summary(bool(player.guild_id))}\n"
            f"***\n"
            f"{cmd(f'接取委托 {task_num}')} | {cmd(f'接取并导航', f'接取委托 {task_num} 导航')} | {cmd('每日委托')}"
        )

    await refresh_task_cmd.finish(build_markdown(msg))
