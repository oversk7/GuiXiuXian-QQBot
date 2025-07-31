from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from .info import REALM_NAMES  # 复用境界名称映射
from .info import realm_by_level, number_to_chinese

level_rank_cmd = on_command("修为榜", aliases={"等级榜"}, block=True, priority=5)

@level_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """按等级 (level) 及经验排序的前 10 名玩家排行榜"""
    async with safe_session() as session:
        stmt = select(Player).order_by(Player.reincarnation_level.desc(), Player.level.desc(), Player.exp.desc()).limit(10)
        players = (await session.execute(stmt)).scalars().all()

    if not players:
        await level_rank_cmd.finish("暂无排行榜数据")

    lines = ["📈 修为排行榜", "▃▃▃▃▃▃▃▃▃▃"]
    for idx, p in enumerate(players, 1):
        realm_name = realm_by_level(p.level)
        # 使用emoji装饰前三名
        rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        # 转数信息（只有冥返过才显示）
        reincarnation_text = ""
        if p.reincarnation_level > 0:
            chinese_reincarnation = number_to_chinese(p.reincarnation_level)
            reincarnation_text = f"{chinese_reincarnation}转 "
        lines.append(f"{rank_emoji} {p.nickname}[UID:{p.uid}] - {reincarnation_text}Lv.{p.level}『{realm_name}』 ({p.exp} EXP)")

    await level_rank_cmd.finish(message_add_head("\n".join(lines), event)) 