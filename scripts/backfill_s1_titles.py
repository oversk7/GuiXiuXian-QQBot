"""一次性脚本：补发第1赛季天梯称号（独立运行，不依赖 NoneBot）"""
import asyncio
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

DB_URL = "mysql+aiomysql://root:***REMOVED***@localhost:3306/guixiuxian_db?charset=utf8mb4"

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
    engine = create_async_engine(DB_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await session.execute(text("""
            SELECT lr.player_id, p.nickname, lr.best_rating, p.extra_attrs
            FROM ladder_rating lr
            JOIN player p ON p.id = lr.player_id
            WHERE lr.season_id = :season_id AND lr.best_rating > 0
            ORDER BY lr.best_rating DESC
        """), {"season_id": SEASON_ID})
        rows = result.fetchall()

        count = 0
        for rank, row in enumerate(rows, start=1):
            player_id, nickname, best_rating, extra_attrs_raw = row
            title = get_title_for_rank(rank)
            if not title:
                continue

            extra = json.loads(extra_attrs_raw) if extra_attrs_raw else {}
            pdata = extra.get("knocker_event", {})
            owned_titles = pdata.get("owned_titles", [])

            if title in owned_titles:
                print(f"  #{rank} {nickname} — 已有「{title}」，跳过")
                continue

            owned_titles.append(title)
            pdata["owned_titles"] = owned_titles
            extra["knocker_event"] = pdata

            await session.execute(text("""
                UPDATE player SET extra_attrs = :extra WHERE id = :pid
            """), {"extra": json.dumps(extra, ensure_ascii=False), "pid": player_id})

            count += 1
            print(f"  #{rank} {nickname} — 补发「{title}」")

        await session.commit()
        print(f"\n补发完成，共 {count} 人获得称号")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
