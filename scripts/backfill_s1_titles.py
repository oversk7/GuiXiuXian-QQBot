"""一次性脚本：补发第1赛季天梯称号"""
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from sqlalchemy.orm.attributes import flag_modified

from plugins.xiuxian_game.models.db import async_engine, async_session_factory
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.models.ladder import LadderRating


SEASON_ID = 1
SEASON_NUMBER = 1

REWARDS = [
    (1, "诡道煞君"),
    (3, "斗煞尊"),
    (10, "煞道名宿"),
    (50, "斗煞新秀"),
]


def get_title_for_rank(rank: int) -> str:
    for limit, base_title in REWARDS:
        if rank <= limit:
            return f"{base_title}·第{SEASON_NUMBER}赛季"
    return ""


async def main():
    async with async_session_factory() as session:
        stmt = (
            select(LadderRating, Player)
            .join(Player, Player.id == LadderRating.player_id)
            .where(LadderRating.season_id == SEASON_ID, LadderRating.best_rating > 0)
            .order_by(LadderRating.best_rating.desc())
        )
        rows = (await session.execute(stmt)).all()

        count = 0
        for rank, row in enumerate(rows, start=1):
            player = row.Player
            title = get_title_for_rank(rank)
            if not title:
                continue

            extra = player.extra_attrs if player.extra_attrs else {}
            pdata = extra.get("knocker_event", {})
            owned_titles = pdata.get("owned_titles", [])

            if title in owned_titles:
                print(f"  #{rank} {player.nickname} — 已有「{title}」，跳过")
                continue

            owned_titles.append(title)
            pdata["owned_titles"] = owned_titles
            extra = dict(extra)
            extra["knocker_event"] = pdata
            player.extra_attrs = extra
            flag_modified(player, "extra_attrs")
            count += 1
            print(f"  #{rank} {player.nickname} — 补发「{title}」")

        await session.commit()
        print(f"\n补发完成，共 {count} 人获得称号")


if __name__ == "__main__":
    asyncio.run(main())
