"""每日任务系统指令处理"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select, and_

from ..models.db import safe_session
from ..models.player import Player
from ..models.daily_task import DailyTask, TaskStatus
from ..utils import message_add_head
from .service import DailyTaskService
from ..battle.integration_helper import BattleIntegrationHelper
import time
import random


# ==================== 查看每日任务 ====================
daily_task_cmd = on_command("每日任务", aliases={"任务", "日常任务"}, block=True, priority=5)

@daily_task_cmd.handle()
async def handle_daily_task(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await daily_task_cmd.finish("⛔ 请先创建角色")
        if player.level < 30:
            await daily_task_cmd.finish("⛔ 该功能仅对Lv.30以上角色开放")
        # 获取或生成今日任务（会自动被动清理过期任务）
        task = await DailyTaskService.generate_daily_task(session, player)
        await session.commit()
        
        # 获取任务汇总信息
        summary = await DailyTaskService.get_task_summary(session, player.id)
        
        # 构建消息
        lines = ["🏛️ 大都会缉邪司 - 每日委托", "━━━━━━━━━━━━━"]
        
        # 今日任务信息
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
        
        lines.append(f"{status_emoji} 【{task.title}】")
        lines.append(f"📍 目标位置：{task.location_str}")
        lines.append(f"👹 目标敌人：{task.enemy_name} Lv.{task.enemy_level}")
        lines.append(f"💰 任务奖励：{task.get_reward_summary()}")
        lines.append(f"📊 任务状态：{status_text}")
        lines.append("")
        
        # 任务描述
        lines.append("📜 任务详情：")
        lines.append(task.description)
        lines.append("")
        
        # 统计信息
        lines.append("📈 完成统计：")
        lines.append(f"本周完成：{summary['weekly_completed']} 次")
        lines.append(f"总计完成：{summary['total_completed']} 次")
        lines.append("")
        
        # 操作提示
        if task.is_available():
            lines.append("💡 使用【接取任务】接取今日委托")
        elif task.is_accepted():
            lines.append("💡 前往目标位置后使用【完成任务】")
        elif task.is_completed():
            lines.append("🎉 今日任务已完成，明日再来！")
        
        await daily_task_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 接取任务 ====================
accept_task_cmd = on_command("接取任务", aliases={"接取委托", "接任务"}, block=True, priority=5)

@accept_task_cmd.handle()
async def handle_accept_task(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await accept_task_cmd.finish("⛔ 请先创建角色")
        
        # 获取今日任务
        task = await DailyTaskService.get_player_daily_task(session, player.id)
        if not task:
            # 生成新任务
            task = await DailyTaskService.generate_daily_task(session, player)
        
        # 接取任务
        success, message = await DailyTaskService.accept_task(session, task)
        
        if success:
            await session.commit()
            msg = (
                f"🏛️ 缉邪司委托接取成功！\n"
                f"━━━━━━━━━━━━━\n"
                f"📋 任务：{task.title}\n"
                f"📍 目标：{task.location_str}\n"
                f"👹 敌人：{task.enemy_name} Lv.{task.enemy_level}\n"
                f"💰 奖励：{task.get_reward_summary()}\n"
                f"━━━━━━━━━━━━━\n"
                f"💡 请前往目标位置，使用【完成任务】与敌人战斗"
            )
        else:
            msg = f"⛔ {message}"
        
        await accept_task_cmd.finish(message_add_head(msg, event))


# ==================== 完成任务 ====================
complete_task_cmd = on_command("完成任务", aliases={"完成委托", "退邪"}, block=True, priority=5)

@complete_task_cmd.handle()
async def handle_complete_task(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await complete_task_cmd.finish("⛔ 请先创建角色")
        
        # 获取今日已接取的任务
        task = await DailyTaskService.get_player_daily_task(session, player.id)
        if not task or not task.is_accepted():
            await complete_task_cmd.finish("⛔ 你没有已接取的任务")
        
        # 检查位置
        if player.x != task.target_x or player.y != task.target_y:
            await complete_task_cmd.finish(
                f"⛔ 请先前往任务目标位置：{task.location_str}\n"
                f"💡 当前位置：{player.region}({player.x},{player.y})"
            )
        
        # 开始战斗
        await complete_task_cmd.send(message_add_head(
            f"⚔️ 遭遇{task.enemy_name}！\n"
            f"👹 敌人等级：Lv.{task.enemy_level}\n"
            f"🩸 敌人血量：{task.enemy_hp}\n"
            f"⚡ 战斗开始！", event
        ))
        
        # 使用战斗系统
        battle_timestamp = int(time.time() * 1000)
        seed = f"DailyTask_{task.id}:{player.id}:{battle_timestamp}"
        
        victory, battle_log, damage_taken = BattleIntegrationHelper.enhanced_player_vs_monster_battle(
            player, task.enemy_stats, task.enemy_name, seed=seed, max_rounds=50
        )
        
        # 更新玩家血量
        player.hp = max(0, player.hp - damage_taken)
        
        if victory:
            # 战斗胜利，完成任务
            success, message, rewards = await DailyTaskService.complete_task(session, player, task)
            
            if success:
                await session.commit()
                
                # 构建胜利消息
                battle_summary = "\n".join(battle_log)
                reward_lines = []
                if "exp" in rewards:
                    reward_lines.append(f"经验+{rewards['exp']}")
                if "gold" in rewards:
                    reward_lines.append(f"金币+{rewards['gold']}")
                if "guild_points" in rewards:
                    reward_lines.append(f"公会积分+{rewards['guild_points']}")
                if "guild_exp" in rewards:
                    reward_lines.append(f"公会经验+{rewards['guild_exp']}")
                
                reward_text = " ".join(reward_lines) if reward_lines else "无奖励"
                
                # 生成诡异的胜利描述
                victory_descriptions = [
                    f"伪仙面具破碎，露出狰狞鬼面，发出凄厉惨叫后化为青烟散去。城中被蛊惑的百姓渐渐清醒，双目重现神采。",
                    f"邪法破除，{task.enemy_name}现出原形，乃一厉鬼也！随着鬼物消散，城中阴气尽散，百姓从噩梦中苏醒。",
                    f"伪仙道袍化为灰烬，鬼魅真身暴露无遗。随着此鬼伏诛，城中被控制的民众纷纷倒地，片刻后醒来，已不记邪法之事。",
                    f"道坛崩塌，邪符自燃，{task.enemy_name}发出不甘怒吼后魂飞魄散。城中恢复生机，百姓重获自由意志。"
                ]
                victory_desc = random.choice(victory_descriptions)

                msg = (
                    f"{battle_summary}\n"
                    f"━━━━━━━━━━━━━\n"
                    f"🎉 任务完成！\n"
                    f"👻 {victory_desc}\n"
                    f"💰 获得奖励：{reward_text}\n"
                    f"🏛️ 缉邪司对你的英勇表示赞赏！"
                )
            else:
                msg = f"⛔ {message}"
        else:
            # 战斗失败
            await session.commit()  # 保存血量变化

            # 生成诡异的失败描述
            defeat_descriptions = [
                f"伪仙{task.enemy_name}邪笑连连，邪法愈发强盛。你身受重伤，只得暂时退却。城中百姓仍在其蛊惑之下，如行尸走肉。",
                f"邪法太过诡异，{task.enemy_name}的幻术让你陷入迷障。你勉强逃脱，但伪仙仍在城中传播邪道，民众深陷其中。",
                f"道坛邪光大盛，{task.enemy_name}实力超乎想象。你败退而归，城中百姓仍被邪法控制，面无血色，目光呆滞。",
                f"伪仙之力诡异莫测，你一时不敌。{task.enemy_name}狂笑不止，继续在城中蛊惑人心，传授邪道。"
            ]
            defeat_desc = random.choice(defeat_descriptions)

            battle_summary = "\n".join(battle_log)
            msg = (
                f"{battle_summary}\n"
                f"━━━━━━━━━━━━━\n"
                f"💀 战斗失败！\n"
                f"👻 {defeat_desc}\n"
                f"💡 建议：提升等级、更换装备或使用丹药增强属性后再来挑战"
            )
        
        await complete_task_cmd.finish(message_add_head(msg, event))


# ==================== 任务统计 ====================
task_stats_cmd = on_command("任务统计", aliases={"委托统计"}, block=True, priority=5)

@task_stats_cmd.handle()
async def handle_task_stats(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await task_stats_cmd.finish("⛔ 请先创建角色")
        
        summary = await DailyTaskService.get_task_summary(session, player.id)
        
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
        lines.append("💡 每日完成委托可获得经验、金币和公会积分奖励")
        
        await task_stats_cmd.finish(message_add_head("\n".join(lines), event))
