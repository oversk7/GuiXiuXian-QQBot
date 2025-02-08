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
            select(Player).where(Player.id == event.get_user_id())
        )
        player = result.scalars().first()
    
    if not player:
        await profile.finish("⛔ 你还没有创建角色")
    
    content = f"""
    🌌 修士档案·{player.nickname}（UID：{player.uid}）🌌
    ▰▰▰▰▰▰▰▰▰
    🧬 境界：{player.level}重天
    {format_hp_bar(player.hp, player.max_hp)}
    💠 真气：{player.mp}/{player.max_mp}
    ⏳ 最后修炼：{player.last_cultivation.strftime('%m-%d %H:%M') if player.last_cultivation else '从未'}
    ▰▰▰▰▰▰▰▰▰
    """
    await profile.finish(create_rich_message("诡道修士", content, "warning"))