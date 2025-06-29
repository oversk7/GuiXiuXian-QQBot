from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from datetime import datetime
from sqlalchemy import select
from ..models import Player, Inventory
from ..models.db import get_session
import random

sign = on_command("签到", block=True, priority=5)

@sign.handle()
async def handle_sign(event: MessageEvent):
    user_id = event.get_user_id()
    now = datetime.now()
    group_id = event.group_id
    await sign.send(f"group_id: {group_id}")
    return
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
        
        player.last_sign = now
        await session.flush()
        
        # 签到奖励
        gold_reward = random.randint(100, 500)
        player.gold += gold_reward
        
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