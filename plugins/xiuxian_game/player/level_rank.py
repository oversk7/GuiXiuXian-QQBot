from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head

level_rank_cmd = on_command("修为榜", aliases={"等级榜"}, block=True, priority=5)

@level_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """按等级 (level) 及经验排序的前 10 名玩家排行榜"""
    async with safe_session() as session:
        stmt = select(Player).order_by(Player.level.desc(), Player.exp.desc()).limit(10)
        players = (await session.execute(stmt)).scalars().all()

    if not players:
        await level_rank_cmd.finish("暂无排行榜数据")

    lines = ["📈 修为排行榜", "▃▃▃▃▃▃▃▃▃▃"]
    for idx, p in enumerate(players, 1):
        lines.append(f"{idx}. {p.nickname}[UID:{p.uid}] - Lv.{p.level} ({p.exp} EXP)")

    await level_rank_cmd.finish(message_add_head("\n".join(lines), event)) 