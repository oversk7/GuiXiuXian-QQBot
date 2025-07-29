from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from datetime import datetime, timedelta
from sqlalchemy import select
from ..models import Player, ItemInstance
from ..models.db import get_session
import random
from ..utils import luck_prob

sign = on_command("签到", block=True, priority=5)

@sign.handle()
async def handle_sign(event: MessageEvent):
    user_id = event.get_user_id()
    now = datetime.now()
    group_id = getattr(event, "group_id", None)
    async with get_session() as session:
        stmt = select(Player).where(Player.id == user_id)
        result = await session.execute(stmt)
        player = result.scalar_one_or_none()
        
        if not player:
            await sign.send("您还没有创建角色，请先注册。")
            return
        
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

        gold_reward = min(2000, base_gold * streak)

        # Luck 翻倍判定
        if random.random() < luck_prob(player.luck):
            gold_reward *= 2
            lucky_msg = f"🍀 幸运加成！奖励翻倍，改写为{gold_reward}金币"
        else:
            lucky_msg = ""

        bonus_msg = ""
        # 官群额外奖励
        if group_id == 'A147FA35C340F858A66260FB4ADBB46D':
            bonus_msg = "\n🎁 官群额外奖励 怨念值+10 ↑"
            # 发放怨念值
            player.resentment += 10
        else:
            bonus_msg = "\n官群签到送大量怨念！发送/帮助 查看群号~"

        # 发放奖励
        player.gold += gold_reward

        # 更新签到日期
        player.last_sign = now

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

        # 月卡权利：签到时发放扫荡令
        monthly_card_msg = ""
        sweep_tokens = benefits["sign_sweep_tokens"]
        if sweep_tokens > 0:
            try:
                await ItemInstance.add_item(session, user_id, "sweep_token", quantity=sweep_tokens)
                monthly_card_msg = f"\n🎫 月卡权利：获得扫荡令*{sweep_tokens}"
            except ValueError as e:
                # 如果添加物品失败，记录错误但不影响签到
                monthly_card_msg = f"\n⚠️ 月卡扫荡令发放失败：{e}"

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
            from ..guild.guild_economy_service import GuildEconomyService
            from ..guild.guild_task_service import GuildTaskService

            # 获取公会签到任务配置
            task_config = GuildTaskService.DAILY_TASKS["daily_sign"]
            points_reward = task_config["points_reward"]
            base_exp = task_config["base_exp"]

            # 发放公会积分和贡献
            player.gold2 += points_reward
            player.guild_contribution += points_reward

            # 添加公会经验（会根据公会建筑倍率动态计算）
            guild_exp_gained = await GuildEconomyService.add_guild_experience(
                session, player.guild_id, base_exp
            )

            guild_msg = f"\n🏰 公会奖励：积分+{points_reward} 公会经验+{guild_exp_gained}"

        # 先提交数据库事务，确保数据保存成功
        await session.commit()

        # 然后发送响应消息
        await sign.send(
            f"✅ 连续签到 {streak} 天！获得 {gold_reward} 金币！\n{lucky_msg}{bonus_msg}{stamina_msg}{monthly_card_msg}{new_msg}{guild_msg}")