from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from datetime import datetime, timedelta
from sqlalchemy import select
from ..models import Player, ItemInstance
from ..models.db import get_session
import random
from ..utils import luck_prob

# Feature Flag（在文件顶部靠近其他导入的位置）
sign = on_command("签到", block=True, priority=5)

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

        # 获取用户ID用于物品发放
        user_id = player.id
        
        last_sign_date = player.last_sign.date() if player.last_sign else None
        today = now.date()

        # 已签到检查
        if last_sign_date == today:
            await sign.send("您今天已经签到过了，请勿重复签到！")
            return

        # 计算连续签到
        if last_sign_date == (today - timedelta(days=1)):
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
        await AchievementService.update_login_streak(session, player.id)

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

            from ..guild.guild_task_service_new import GuildTaskService as GuildTaskServiceNew
            from ..guild.guild_economy_service_new import GuildEconomyService as GuildEconomyServiceNew
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.guild_repository import GuildRepository
            from ..infrastructure.repositories.player_task_stats_repository import PlayerTaskStatsRepository
            from ..infrastructure.repositories.guild_task_record_repository import GuildTaskRecordRepository
            from ..infrastructure.repositories.player_donation_log_repository import PlayerDonationLogRepository
            from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository

            # 获取公会签到任务配置
            task_config = GuildTaskServiceNew.DAILY_TASKS["daily_sign"]
            points_reward = task_config["points_reward"]
            base_exp = task_config["base_exp"]

            # 发放公会积分和贡献
            player.gold2 += points_reward
            player.guild_contribution += points_reward

            # 添加公会经验（会根据公会建筑倍率动态计算）
            guild_economy_service = GuildEconomyServiceNew(
                guild_repo=GuildRepository(session),
                player_repo=PlayerRepository(session),
                donation_log_repo=PlayerDonationLogRepository(session),
                building_repo=GuildBuildingRepository(session),
            )
            guild_exp_gained = await guild_economy_service.add_guild_experience(
                player.guild_id, base_exp
            )

            # 记录签到任务完成
            task_service = GuildTaskServiceNew(
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
        achievement_msgs = await AchievementService.check_achievements(session, player)

        # 先提交数据库事务，确保数据保存成功
        await session.commit()

        # 构建响应消息
        response_msg = f"🛞{player.nickname}[{player.uid}] 连续签到 {streak} 天！获得 {base_reward} 金币！\n{lucky_msg}{bonus_msg}{stamina_msg}{monthly_card_msg}{sweep_token_msg}{vip_medal_msg}{new_msg}{guild_msg}"

        # 附加成就解锁消息
        if achievement_msgs:
            response_msg += "\n\n" + "\n".join(achievement_msgs)

        # 发送响应消息
        await sign.send(response_msg)