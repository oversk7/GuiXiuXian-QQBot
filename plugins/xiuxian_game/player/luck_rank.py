from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select
import random
from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head

luck_rank_cmd = on_command("幸运榜", aliases={"运气榜", "幸运排行榜"}, block=True, priority=5)

@luck_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """显示幸运值最高的前10名玩家"""
    async with safe_session() as session:
        stmt = select(Player).order_by(Player.luck.desc()).limit(10)
        players = (await session.execute(stmt)).scalars().all()

    if not players:
        await luck_rank_cmd.finish("暂无排行榜数据")

    wishes = random.choice(["你信任那些微小的可能性，于是，世界便以暴击的星火与翻倍的惊喜回应这份信任。",
                            "这份加点，不是侥幸，是宣言：你相信，那1%的闪光，足以点亮100%的征程。",
                            "凡俗眼中的偶然，是你掌中的必然。",
    ])
    lines = ["🍀 幸运排行榜", wishes,"▃▃▃▃▃▃▃▃▃▃"]
    for idx, p in enumerate(players, 1):
        # 使用emoji装饰前三名
        rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        lines.append(f"{rank_emoji} {p.nickname}[UID:{p.uid}] - 🍀{p.luck}")

    await luck_rank_cmd.finish(message_add_head("\n".join(lines), event))
