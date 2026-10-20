from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from ..utils_markdown import build_markdown, cmd, plain_command_text
from datetime import datetime, timedelta
from sqlalchemy import select
from ..models import Player, ItemInstance
import random
from ..utils import luck_prob
from .sign_calendar import record_sign

# Feature Flag（在文件顶部靠近其他导入的位置）
sign = on_command("签到", block=True, priority=13)

@sign.handle()
async def handle_sign(event: MessageEvent):
    from ..platform_utils import get_unified_player, is_guild_message
    from ..models.db import safe_session

    now = datetime.now()
    group_id = getattr(event, "group_id", None)
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        player = await get_unified_player(session, event)

        if not player:
            if is_guild_message(event):
                await sign.send("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await sign.send("您还没有创建角色，请先注册。")
            return

        from ..event.moon_festival import MoonFestivalService
        player = await MoonFestivalService.lock_for_action(session, player)

        # 获取用户ID用于物品发放
        user_id = player.id
        
        last_sign_date = player.last_sign.date() if player.last_sign else None
        today = now.date()

        # 记录是否为首次签到
        is_first_sign = player.last_sign is None

        # 已签到检查
        if last_sign_date == today:
            from ..quest.novice_quest_service import NoviceQuestService
            _, quest_msg = await NoviceQuestService.check_and_advance_quest(
                session, player, "state"
            )
            message = "今日已签到，明日再来。"
            if quest_msg:
                message += f"\n\n{quest_msg}"
            await session.commit()
            await sign.send(build_markdown(message))
            return

        # 计算连续签到
        # 检查是否为「拨针·签到」重置的二次签到，是则不增加streak
        vip_data = player.vip_equipment_data or {}
        is_dial_reset = vip_data.get("dial_sign_reset", False)

        if is_dial_reset:
            # 拨针重置的签到：保持streak不变，清除标记
            data = dict(vip_data)
            data.pop("dial_sign_reset", None)
            player.vip_equipment_data = data
        elif last_sign_date == (today - timedelta(days=1)):
            player.sign_streak += 1
        else:
            player.sign_streak = 1

        streak = player.sign_streak

        # 基础奖励
        if group_id == 'A147FA35C340F858A66260FB4ADBB46D':
            base_gold = random.randint(100, 300)
        else:
            base_gold = random.randint(50, 150)

        gold_reward = min(3000, base_gold * streak)
        base_reward = gold_reward

        # Luck 翻倍判定
        if random.random() < luck_prob(player.luck):
            gold_reward *= 2
            lucky_msg = f"🍀 触发幸运判定！奖励翻倍，改写为{gold_reward}金币"
        else:
            lucky_msg = ""

        bonus_msg = ""
        resentment_reward = random.randint(10, 50)
        # 官群额外奖励
        if group_id == 'A147FA35C340F858A66260FB4ADBB46D':
            bonus_msg = f"\n🎁 官群额外奖励 怨念值+{resentment_reward} ↑"
            # 发放怨念值
            player.resentment += resentment_reward
        else:
            bonus_msg = "\n官群签到送怨念！发送/帮助 查看群号~"

        # 发放奖励
        player.gold += gold_reward

        # 更新财富成就统计
        from ..achievement.achievement_service import AchievementService
        await AchievementService.update_stat(session, player.id, "gold_earned_total", increment=gold_reward, auto_commit=False)

        # 更新签到日期
        player.last_sign = now

        # 更新连续登录成就统计
        await AchievementService.update_login_streak(session, player.id, auto_commit=False)

        # 获取月卡权益
        from ..models.monthly_card import get_player_card_benefits
        benefits = await get_player_card_benefits(session, player.id)

        # 计算咒抗上限（基础10 + 月卡加成）
        base_stamina = 10
        stamina_limit = base_stamina + benefits["sign_stamina_bonus"]
        player.stamina = stamina_limit

        # 构建咒抗恢复消息
        if benefits["sign_stamina_bonus"] > 0:
            stamina_msg = f"\n💪 咒抗已恢复至 {stamina_limit}/{stamina_limit} (月卡+{benefits['sign_stamina_bonus']})"
        else:
            stamina_msg = f"\n💪 咒抗已恢复至 {stamina_limit}/{stamina_limit}"

        # 月卡权利：签到时发放月卡宝箱
        monthly_card_msg = ""
        monthly_card_boxes = benefits["sign_monthly_card_boxes"]
        if monthly_card_boxes > 0:
            try:
                await ItemInstance.add_item(session, user_id, "monthly_card_box", quantity=monthly_card_boxes)
                monthly_card_msg = f"\n💎 月卡权利：获得月卡宝箱*{monthly_card_boxes}"
            except ValueError as e:
                # 如果添加物品失败，记录错误但不影响签到
                monthly_card_msg = f"\n⚠️ 月卡宝箱发放失败：{e}"

        # 所有玩家签到都获得扫荡令
        sweep_token_msg = ""
        base_sweep_tokens = 5  # 基础扫荡令数量
        total_sweep_tokens = base_sweep_tokens  # 月卡不再额外提供扫荡令

        try:
            await ItemInstance.add_item(session, user_id, "sweep_token", quantity=total_sweep_tokens)
            sweep_token_msg = f"\n⚡ 每日奖励：获得扫荡令*{base_sweep_tokens}"
        except ValueError as e:
            # 如果添加物品失败，记录错误但不影响签到
            sweep_token_msg = f"\n⚠️ 扫荡令发放失败：{e}"

        # 首次签到赠改名卡
        first_sign_msg = ""
        if is_first_sign:
            try:
                await ItemInstance.add_item(session, user_id, "rename_card", 1)
                first_sign_msg = "\n🎁 首次签到奖励：改名卡 ×1（使用【改名 新名字】修改道号）"
            except ValueError as e:
                first_sign_msg = f"\n⚠️ 改名卡发放失败：{e}"

        vip_medal_msg = ""
        stmt_medal = select(ItemInstance).where(
            ItemInstance.player_id == user_id,
            ItemInstance.item_id == "vip_medal_tiandi"
        )
        medal_instance = (await session.execute(stmt_medal)).scalars().first()
        if medal_instance:
            from ..models.vip_equipment_bonus import VIPEquipmentBonus

            vip_record = await VIPEquipmentBonus.get_or_create(session, player.id)
            vip_record.add_bonus("attack", 15)
            vip_record.add_bonus("luck", 15)
            player.attack += 15
            player.luck += 15
            # 基础属性变化后重算装备百分比加成
            from ..item.equipment_service import recalc_equipment_attributes
            await recalc_equipment_attributes(session, player)
            vip_medal_msg = "\n👑 天帝祝福：筋骨更盛，鸿运加身（力+15 运+15·基础闪避率30%）"

        new_msg = ""
        # 检查是否为创建账号的同一天
        if player.created_at.date() == today:
            # 赠送新手大礼包
            try:
                await ItemInstance.add_item(session, user_id, "spirit_herb", quantity=5)
                await ItemInstance.add_item(session, user_id, "heal_potion", quantity=5)
                new_msg = "\n🎁 获得新手大礼包：回春散*5 凝神草*5"
            except ValueError as e:
                # 如果添加物品失败，记录错误但不影响签到
                new_msg = f"\n⚠️ 新手大礼包发放失败：{e}"

        # 公会签到奖励
        guild_msg = ""
        if player.guild_id:
            # 导入公会相关服务
            from ..models.guild_task_record import GuildTaskType

            from ..guild.guild_task_service import GuildTaskService
            from ..guild.guild_economy_service import GuildEconomyService
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.guild_repository import GuildRepository
            from ..infrastructure.repositories.player_task_stats_repository import PlayerTaskStatsRepository
            from ..infrastructure.repositories.guild_task_record_repository import GuildTaskRecordRepository
            from ..infrastructure.repositories.player_donation_log_repository import PlayerDonationLogRepository
            from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository

            # 获取公会签到任务配置
            task_config = GuildTaskService.DAILY_TASKS["daily_sign"]
            points_reward = task_config["points_reward"]
            base_exp = task_config["base_exp"]

            # 发放公会积分和贡献
            player.gold2 += points_reward
            player.guild_contribution += points_reward

            # 添加公会经验（会根据公会建筑倍率动态计算）
            guild_economy_service = GuildEconomyService(
                guild_repo=GuildRepository(session),
                player_repo=PlayerRepository(session),
                donation_log_repo=PlayerDonationLogRepository(session),
                building_repo=GuildBuildingRepository(session),
            )
            guild_exp_gained = await guild_economy_service.add_guild_experience(
                player.guild_id, base_exp
            )

            # 记录签到任务完成
            task_service = GuildTaskService(
                player_repo=PlayerRepository(session),
                guild_repo=GuildRepository(session),
                player_task_stats_repo=PlayerTaskStatsRepository(session),
                guild_task_record_repo=GuildTaskRecordRepository(session),
                player_donation_log_repo=PlayerDonationLogRepository(session),
                guild_building_repo=GuildBuildingRepository(session),
            )
            await task_service.record_task_completion(
                player.id, player.guild_id, GuildTaskType.DAILY_SIGN,
                points_reward, guild_exp_gained
            )

            # 更新日常任务完成统计
            await task_service.update_daily_task_completion_stats(player.id)
            guild_msg = f"\n🏰 公会奖励：积分+{points_reward} 公会经验+{guild_exp_gained}"

        # 检查并解锁成就
        achievement_msgs = await AchievementService.check_achievements(session, player, auto_commit=False)

        # 新手任务钩子
        from ..quest.novice_quest_service import NoviceQuestService
        quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(session, player, "command", {"command": "签到"})
        moon_msg = MoonFestivalService.record_action(player, "sign")
        await session.commit()
        # 提交后再写签到日历（Redis BitMap），写失败只影响日历展示
        await record_sign(player.id, today, streak)

        # 尝试使用原生Markdown卡片展示签到结果（仅在QQ平台）
        if hasattr(event, 'get_user_id'):
            try:
                # 获取玩家QQ官方ID（用于头像）
                qq_openid = event.get_user_id()

                # 玩家头像URL（32x32小头像）
                avatar_url = f"https://thirdqq.qlogo.cn/qqapp/102499345/{qq_openid}/0"

                lines = [
                    f"# 🎉 签到成功 · 连续 {streak} 天",
                    f"![头像 #32px #32px]({avatar_url})",
                    f"👤 **{player.nickname}** `UID:{player.uid}`",
                    "***",
                    f"💰 金币奖励 **+{base_reward}**",
                ]

                # 幸运翻倍
                if lucky_msg:
                    lines.append(f"🍀 触发幸运判定！奖励翻倍，改写为 **{gold_reward}** 金币")

                # 官群额外奖励
                if "官群额外奖励" in bonus_msg:
                    lines.append(f"🎁 官群额外奖励 怨念值 **+{resentment_reward}** ↑")

                # 其余奖励逐行展示
                for extra_msg in (stamina_msg, monthly_card_msg, sweep_token_msg,
                                  first_sign_msg, vip_medal_msg, new_msg, guild_msg, moon_msg):
                    if extra_msg:
                        lines.append(extra_msg.strip())

                # 成就解锁
                if achievement_msgs:
                    lines.append("***")
                    lines.append("**🏆 成就解锁**")
                    for ach_msg in achievement_msgs:
                        lines.append(ach_msg.strip())

                # 新手任务消息
                if quest_completed and quest_msg:
                    lines.append("***")
                    lines.append(quest_msg.strip())

                # 非官群提示
                if "官群额外奖励" not in bonus_msg:
                    lines.append(f"> 官群签到送怨念！发送 {cmd('帮助')} 查看群号~")

                lines.append("***")
                lines.append(" | ".join([cmd("面板"), cmd("背包"), cmd("修炼"), cmd("打工"), cmd("签到日历")]))

                await sign.send(build_markdown("\n".join(lines)))
            except Exception as e:
                # 如果Markdown模板发送失败，回退到文字版本
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"[签到MD] 发送失败，回退到文本版本: {e}", exc_info=True)

                # 构建纯文本响应消息
                response_msg = f"🛞{player.nickname}[{player.uid}] 连续签到 {streak} 天！获得 {base_reward} 金币！\n{lucky_msg}{bonus_msg}{stamina_msg}{monthly_card_msg}{sweep_token_msg}{first_sign_msg}{vip_medal_msg}{new_msg}{guild_msg}\n{moon_msg}"

                # 附加成就解锁消息
                if achievement_msgs:
                    response_msg += "\n\n" + "\n".join(achievement_msgs)

                # 附加新手任务消息
                if quest_completed and quest_msg:
                    response_msg += "\n\n" + quest_msg

                # 发送纯文本消息
                await sign.send(plain_command_text(response_msg))
        else:
            # 非QQ平台，使用纯文本版本
            response_msg = f"🛞{player.nickname}[{player.uid}] 连续签到 {streak} 天！获得 {base_reward} 金币！\n{lucky_msg}{bonus_msg}{stamina_msg}{monthly_card_msg}{sweep_token_msg}{first_sign_msg}{vip_medal_msg}{new_msg}{guild_msg}\n{moon_msg}"

            # 附加成就解锁消息
            if achievement_msgs:
                response_msg += "\n\n" + "\n".join(achievement_msgs)

            # 附加新手任务消息
            if quest_completed and quest_msg:
                response_msg += "\n\n" + quest_msg

            # 发送纯文本消息
            await sign.send(plain_command_text(response_msg))