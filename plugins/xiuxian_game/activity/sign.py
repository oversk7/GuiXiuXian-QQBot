from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from datetime import datetime
from sqlalchemy import select
from ..models import Player, Inventory
from ..data.db import get_session
import random
from ..quest.core import check_daily_quests

sign = on_command("签到", block=True, priority=5)

@sign.handle()
async def handle_sign(event: MessageEvent):
    user_id = event.get_user_id()
    now = datetime.now()
    
    async with get_session() as session:
        stmt = select(Player).where(Player.id == user_id)
        result = await session.execute(stmt)
        player = result.scalar_one_or_none()
        
        if not player:
            await sign.send("您还没有创建角色，请先注册。")
            return
        
        last_sign_date = player.last_sign.date() if player.last_sign else None
        today = now.date()
        
        if last_sign_date == today:
            await sign.send("您今天已经签到过了，请勿重复签到！")
            return
        
        # 签到奖励
        gold_reward = random.randint(100, 500)
        player.gold += gold_reward
        player.last_sign = now
        
        # 检查是否为创建账号的同一天
        if player.created_at.date() == today:
            # 赠送新手大礼包
            starter_pack = Inventory(
                player_id=player.id,
                item_id="heal_potion",
                quantity=3
            )
            session.add(starter_pack)
            await sign.send(f"签到成功！获得 {gold_reward} 金币，并领取了 回春散x3！🎁")
        else:
            await sign.send(f"签到成功！获得 {gold_reward} 金币！✨")
        
        await session.commit()
        await check_daily_quests(str(user_id))  # 检查每日任务