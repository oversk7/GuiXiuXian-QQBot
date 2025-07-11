from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from datetime import datetime, timedelta
from sqlalchemy import select
from ..models import Player, Inventory
from ..models.db import get_session
import random
from ..utils import luck_prob

sign = on_command("签到", block=True, priority=5)

@sign.handle()
async def handle_sign(event: MessageEvent):
    user_id = event.get_user_id()
    now = datetime.now()
    group_id = event.group_id
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
            lucky_msg = "🍀 幸运加成！奖励翻倍！"
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

        player.stamina = 10  # 可改为配置或与等级相关
        stamina_msg = "\n💪 体力已恢复至 10/10"

        await sign.send(
            f"✅ 连续签到 {streak} 天！获得 {gold_reward} 金币！{lucky_msg}{bonus_msg}{stamina_msg}")
        
        # 检查是否为创建账号的同一天
        if player.created_at.date() == today:
            # 赠送新手大礼包
            starter_pack = Inventory(
                player_id=player.id,
                item_id="heal_potion",
                quantity=3
            )
            session.add(starter_pack)
        await session.commit()