from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from ..utils import format_hp_bar, create_rich_message
from ..data.db import get_session
from ..models.player import Player
from sqlalchemy import select

profile = on_command("角色", block=True, priority=5)

@profile.handle()
async def _(event: MessageEvent):
    async with get_session() as session:
        result = await session.execute(
            select(Player).where(Player.uid == event.get_user_id())
        )
        player = result.scalars().first()
    
    if not player:
        await profile.finish("⛔ 你还没有创建角色")
    
    content = f"""
    🧬 境界：{player.level}重天
    {format_hp_bar(player.hp, 100)}
    💠 真气：{player.mp}/100
    🕒 最后活跃：{player.last_active.strftime('%Y-%m-%d %H:%M')}
    """
    await profile.finish(create_rich_message(player.name, content))