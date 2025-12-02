"""每日任务系统指令处理"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select, and_

from ..models.db import AsyncSessionLocal
from ..models.player import Player
from ..models.daily_task import DailyTask, TaskStatus
from ..utils import message_add_head
from ..platform_utils import get_unified_player
from .service_new import DailyTaskService
from ..battle.integration_helper import BattleIntegrationHelper
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..world.location_service_new import LocationService
from ..world.npc_service_new import NPCService
from ..guild.guild_economy_service_new import GuildEconomyService
import time
import random
from datetime import date


# ==================== 查看每日任务 ====================
daily_task_cmd = on_command("每日委托", aliases={"任务", "每日任务"}, block=True, priority=5)

@daily_task_cmd.handle()
async def handle_daily_task(event: MessageEvent):
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await daily_task_cmd.finish("⛔ 请先创建角色")
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
        lines = ["🏛️ 大都会缉邪司 - 每日委托", "━━━━━━━━━━━━━"]

        if not tasks:
            lines.append("⚠️ 今日暂无委托任务")
        else:
            # 显示所有任务
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

                lines.append(f"{status_emoji} 【委托{i}】{task.title}")
                lines.append(f"🔳 任务描述：{task.description}")
                lines.append(f"📍 目标位置：{task.location_str}")
                lines.append(f"👹 目标敌人：{task.enemy_name} Lv.{task.enemy_level}")
                lines.append(f"💰 任务奖励：{task.get_reward_summary(bool(player.guild_id))}")
                lines.append(f"📊 任务状态：{status_text}")
                lines.append("")

        lines.append("━━━━━━━━━━━━━")
        
        # 统计信息
        lines.append("📈 完成统计：")
        lines.append(f"本周完成：{summary['weekly_completed']} 次")
        lines.append(f"总计完成：{summary['total_completed']} 次")
        lines.append("")
        
        # 操作提示
        available_count = sum(1 for task in tasks if task.is_available())
        accepted_count = sum(1 for task in tasks if task.is_accepted())
        completed_count = sum(1 for task in tasks if task.is_completed())

        if available_count > 0:
            lines.append(f"💡 使用【接取任务 <委托编号>】接取委托（如：接取任务 1）")
        if accepted_count > 0:
            lines.append("💡 前往目标位置，使用【观察】查看鬼怪，击杀后使用【完成任务】")
        if completed_count == len(tasks) and len(tasks) >= 3:
            lines.append("🎉 今日所有委托已完成，明日再来！")
        elif len(tasks) < 3:
            lines.append("💡 使用【刷新委托】获取更多委托任务")
        
        await daily_task_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 接取任务 ====================
accept_task_cmd = on_command("接取委托", aliases={"接取任务", "接收委托"}, block=True, priority=5)

@accept_task_cmd.handle()
async def handle_accept_task(event: MessageEvent, args: Message = CommandArg()):
    # 使用跨平台工具获取玩家数据
    from ..platform_utils import get_unified_player, is_guild_message

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            if is_guild_message(event):
                await accept_task_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await accept_task_cmd.finish("⛔ 请先创建角色")

        # 解析参数
        args_text = args.extract_plain_text().strip()
        task_index = 1  # 默认接取第一个任务

        if args_text:
            try:
                task_index = int(args_text)
                if task_index < 1 or task_index > 3:
                    await accept_task_cmd.finish("⛔ 委托编号必须是1-3之间的数字")
            except ValueError:
                await accept_task_cmd.finish("⛔ 请输入正确的委托编号（1-3）")

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
            await uow.commit()
            msg = (
                f"🏛️ 缉邪司委托接取成功！\n"
                f"━━━━━━━━━━━━━\n"
                f"📋 委托{task_index}：{task.title}\n"
                f"🔳 任务描述：{task.description}\n"
                f"📍 目标：{task.location_str}\n"
                f"👹 敌人：{task.enemy_name} Lv.{task.enemy_level}\n"
                f"💰 奖励：{task.get_reward_summary(bool(player.guild_id))}\n"
                f"━━━━━━━━━━━━━\n"
                f"💡 请前往目标位置，使用【观察】查看鬼怪，击杀后使用【完成任务】"
            )
        else:
            msg = f"⛔ {message}"

    await accept_task_cmd.finish(message_add_head(msg, event))


# ==================== 完成任务 ====================
complete_task_cmd = on_command("完成任务", aliases={"完成委托", "退邪"}, block=True, priority=5)

@complete_task_cmd.handle()
async def handle_complete_task(event: MessageEvent):
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await complete_task_cmd.finish("⛔ 请先创建角色")

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
                from ..infrastructure.repositories.player_task_stats_repository import PlayerTaskStatsRepository
                from ..infrastructure.repositories.guild_task_record_repository import GuildTaskRecordRepository
                from ..infrastructure.repositories.player_donation_log_repository import PlayerDonationLogRepository
                from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository

                guild_task_service = GuildTaskServiceNew(
                    player_repo=uow.players,
                    guild_repo=uow.guilds,
                    player_task_stats_repo=PlayerTaskStatsRepository(uow.session),
                    guild_task_record_repo=GuildTaskRecordRepository(uow.session),
                    player_donation_log_repo=PlayerDonationLogRepository(uow.session),
                    guild_building_repo=GuildBuildingRepository(uow.session),
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
                f"🎉 任务完成！\n"
                f"━━━━━━━━━━━━━\n"
                f"👻 {completion_desc}\n"
                f"💰 获得奖励：{reward_text}\n"
                f"🏛️ 缉邪司对你的英勇表示赞赏！"
            )
        else:
            msg = f"⛔ {message}"

    await complete_task_cmd.finish(message_add_head(msg, event))


# ==================== 任务统计 ====================
task_stats_cmd = on_command("任务统计", aliases={"委托统计"}, block=True, priority=5)

@task_stats_cmd.handle()
async def handle_task_stats(event: MessageEvent):
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await task_stats_cmd.finish("⛔ 请先创建角色")

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

        lines = ["📊 缉邪司委托统计", "━━━━━━━━━━━━━"]
        lines.append(f"📅 本周完成：{summary['weekly_completed']} 次")
        lines.append(f"🏆 总计完成：{summary['total_completed']} 次")

        # 今日任务状态
        today_task = summary['today_task']
        if today_task:
            if today_task.is_completed():
                lines.append("✅ 今日任务：已完成")
            elif today_task.is_accepted():
                lines.append("⚔️ 今日任务：进行中")
            else:
                lines.append("📋 今日任务：可接取")
        else:
            lines.append("📋 今日任务：尚未生成")

        lines.append("")
        lines.append("💡 每日完成委托可获得经验、金币和积分奖励，有公会还可获得公会经验")

    await task_stats_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 刷新委托 ====================
refresh_task_cmd = on_command("刷新委托", aliases={"刷新任务", "更多委托"}, block=True, priority=5)

@refresh_task_cmd.handle()
async def handle_refresh_task(event: MessageEvent):
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await refresh_task_cmd.finish("⛔ 请先创建角色")
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

        msg = (
            f"🏛️ 缉邪司新委托生成！\n"
            f"━━━━━━━━━━━━━\n"
            f"📋 委托{len(tasks) + 1}：{new_task.title}\n"
            f"🔳 任务描述：{new_task.description}\n"
            f"📍 目标：{new_task.location_str}\n"
            f"👹 敌人：{new_task.enemy_name} Lv.{new_task.enemy_level}\n"
            f"💰 奖励：{new_task.get_reward_summary(bool(player.guild_id))}\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 使用【接取任务 {len(tasks) + 1}】接取此委托"
        )

    await refresh_task_cmd.finish(message_add_head(msg, event))
