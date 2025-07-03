from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg
from nonebot.adapters.qq import Message
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head

wealth_rank_cmd = on_command("财富榜", aliases={"财富排行榜"}, block=True, priority=5)

@wealth_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """显示金币最多的前10名玩家"""
    async with safe_session() as session:
        stmt = select(Player).order_by(Player.gold.desc()).limit(10)
        players = (await session.execute(stmt)).scalars().all()

    if not players:
        await wealth_rank_cmd.finish("暂无排行榜数据")

    lines = ["💰 财富排行榜", "▃▃▃▃▃▃▃▃▃▃"]
    for idx, p in enumerate(players, 1):
        lines.append(f"{idx}. {p.nickname}[UID:{p.uid}] - {p.gold}💰")

    await wealth_rank_cmd.finish(message_add_head("\n".join(lines), event)) 