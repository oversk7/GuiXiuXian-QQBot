from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from ..utils import format_hp_bar, create_rich_message
from ..data.db import get_session
from ..models.player import Player
from sqlmodel import select

profile = on_command("角色", block=True, priority=5)

@profile.handle()
async def _(event: MessageEvent):
    session = next(get_session())
    player = session.exec(
        select(Player).where(Player.uid == event.get_user_id())
    ).first()
    
    if not player:
        await profile.finish("⛔ 你还没有创建角色")
    
    content = f"""
    🧬 境界：{player.cultivation}
    ⚡ 等级：Lv.{player.level}
    {format_hp_bar(player.hp, 100)}
    💠 真气：{player.mp}/100
    """
    await profile.finish(create_rich_message(player.name, content))