"""斗法天梯赛季奖励分发

按本月最终排名发放奖励，包括：
- 称号（写入 Player.titles JSON 字段，若不存在则跳过称号部分）
- 香火（直接累加 Player.incense）
- 稳定水晶（通过 ItemInstance.add_item 加入背包）

奖励等级：
| 排名 | 称号 | 香火 | 稳定水晶 |
|------|------|------|---------|
| 1 | 诡道煞君 | 1000 | 5 |
| 2-3 | 斗煞尊 | 500 | 3 |
| 4-10 | 煞道名宿 | 300 | 2 |
| 11-50 | 斗煞新秀 | 100 | 1 |
| 51-100 | - | 50 | 0 |
| 100+ | - | 20 | 0 |
"""
from __future__ import annotations

import logging
from typing import List, Tuple

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ...models.player import Player
from ...models.inventory import ItemInstance
from ...models.ladder import LadderRating, LadderSeason
from ...models.world_message import WorldMessage

logger = logging.getLogger(__name__)


# 奖励配置（排名上限, 称号, 香火, 稳定水晶数）
SEASON_REWARDS: List[Tuple[int, str, int, int]] = [
    (1, "诡道煞君", 1000, 5),
    (3, "斗煞尊", 500, 3),
    (10, "煞道名宿", 300, 2),
    (50, "斗煞新秀", 100, 1),
    (100, "", 50, 0),
]
PARTICIPATION_INCENSE = 20
STABLE_CRYSTAL_ITEM_ID = "stabilizer_crystal"


def _get_reward_for_rank(rank: int) -> Tuple[str, int, int]:
    """根据排名返回 (称号, 香火, 稳定水晶) 三元组"""
    for limit, title, incense, crystal in SEASON_REWARDS:
        if rank <= limit:
            return title, incense, crystal
    return "", PARTICIPATION_INCENSE, 0


async def distribute_season_rewards(session: AsyncSession, season: LadderSeason) -> dict:
    """为指定赛季分发奖励

    Returns:
        dict: {"reward_count": int, "errors": List[str]}
    """
    if season.rewards_distributed:
        return {"reward_count": 0, "errors": ["already_distributed"]}

    # 拉取所有有战绩的玩家，按积分降序
    stmt = (
        select(LadderRating, Player)
        .join(Player, Player.id == LadderRating.player_id)
        .where(
            LadderRating.season_id == season.id,
            LadderRating.matches_played > 0,
        )
        .order_by(LadderRating.rating.desc())
    )
    rows = (await session.execute(stmt)).all()

    if not rows:
        logger.info(f"赛季 #{season.season_number} 无玩家参赛，跳过奖励发放")
        return {"reward_count": 0, "errors": []}

    reward_count = 0
    errors: List[str] = []

    # 按区服分组，各区独立排名发奖（rows 已按积分降序，组内顺序不变）
    server_groups: dict = {}
    for row in rows:
        server_groups.setdefault(row.Player.server_id or 1, []).append(row)

    ranked_rows = [
        (rank, row)
        for group in server_groups.values()
        for rank, row in enumerate(group, start=1)
    ]

    for rank, row in ranked_rows:
        rating: LadderRating = row.LadderRating
        player: Player = row.Player

        base_title, incense, crystal = _get_reward_for_rank(rank)
        title = f"{base_title}·第{season.season_number}赛季" if base_title else ""

        try:
            # 香火奖励（直接加 Player.incense）
            if incense > 0:
                player.incense = (player.incense or 0) + incense

            # 稳定水晶（背包物品）
            if crystal > 0:
                ok = await ItemInstance.add_item(session, player.id, STABLE_CRYSTAL_ITEM_ID, crystal)
                if not ok:
                    errors.append(f"player {player.id} 背包已满，稳定水晶发放失败")

            # 称号（写入 extra_attrs.knocker_event.owned_titles）
            if title:
                extra = player.extra_attrs if player.extra_attrs else {}
                pdata = extra.get("knocker_event", {})
                owned_titles = pdata.get("owned_titles", [])
                if title not in owned_titles:
                    owned_titles.append(title)
                    pdata["owned_titles"] = owned_titles
                    extra = dict(extra)
                    extra["knocker_event"] = pdata
                    player.extra_attrs = extra
                    flag_modified(player, "extra_attrs")

            # 私信通知
            parts = [f"⚔️ 斗法天梯第{season.season_number}赛季结算 — 排名#{rank}"]
            if title:
                parts.append(f"🏅 称号「{title}」")
            if incense > 0:
                parts.append(f"🔥 香火+{incense}")
            if crystal > 0:
                parts.append(f"💎 稳定水晶×{crystal}")
            session.add(WorldMessage(
                player_id="SYSTEM",
                recipient_id=player.id,
                scope="private",
                content=" | ".join(parts),
            ))

            reward_count += 1
        except (SQLAlchemyError, ValueError, AttributeError) as e:  # pragma: no cover
            logger.error(f"赛季奖励发放失败 player={player.id} rank={rank}: {e}", exc_info=True)
            errors.append(f"player {player.id} rank {rank}: {e}")

    await session.flush()
    logger.info(f"✅ 赛季 #{season.season_number} 奖励发放: {reward_count} 人")
    return {"reward_count": reward_count, "errors": errors}
