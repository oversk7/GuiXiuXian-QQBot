"""
排行榜查询模块 (CQRS Query Side)

将 5 种排行榜统一为通用查询函数，并加入进程内缓存。
财富榜从 7 次查询优化为 1 次 SQL。
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from sqlalchemy import select, func, case, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from . import readonly_session, cached
from ..models.player import Player
from ..models.bank_account import BankAccount
from ..models.stock import StockHolding, Stock


@dataclass
class RankedPlayer:
    """排行榜条目 DTO"""
    rank: int
    player_id: str
    uid: int
    nickname: str
    value: int | float  # 排序依据的值
    extra: dict = field(default_factory=dict)  # 额外展示数据


# ==================== 通用单字段排行查询 ====================

@cached(ttl_seconds=300)
async def query_level_ranking(limit: int = 30) -> list[RankedPlayer]:
    """修为排行榜：按 reincarnation_level DESC, level DESC, exp DESC"""
    async with readonly_session() as session:
        stmt = (
            select(
                Player.id,
                Player.uid,
                Player.nickname,
                Player.level,
                Player.exp,
                Player.reincarnation_level,
            )
            .order_by(
                Player.reincarnation_level.desc(),
                Player.level.desc(),
                Player.exp.desc(),
            )
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()

    result = []
    for rank, row in enumerate(rows, start=1):
        result.append(RankedPlayer(
            rank=rank,
            player_id=row.id,
            uid=row.uid,
            nickname=row.nickname,
            value=row.level,
            extra={
                "exp": row.exp,
                "reincarnation_level": row.reincarnation_level,
            },
        ))
    return result


@cached(ttl_seconds=300)
async def query_luck_ranking(limit: int = 30) -> list[RankedPlayer]:
    """幸运排行榜：按 luck DESC"""
    async with readonly_session() as session:
        stmt = (
            select(Player.id, Player.uid, Player.nickname, Player.luck)
            .order_by(Player.luck.desc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()

    return [
        RankedPlayer(
            rank=i,
            player_id=row.id,
            uid=row.uid,
            nickname=row.nickname,
            value=row.luck,
        )
        for i, row in enumerate(rows, start=1)
    ]


@cached(ttl_seconds=300)
async def query_exploration_ranking(limit: int = 30) -> list[RankedPlayer]:
    """探索排行榜：按 max_dungeon_level DESC"""
    async with readonly_session() as session:
        stmt = (
            select(Player.id, Player.uid, Player.nickname, Player.max_dungeon_level)
            .order_by(Player.max_dungeon_level.desc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()

    return [
        RankedPlayer(
            rank=i,
            player_id=row.id,
            uid=row.uid,
            nickname=row.nickname,
            value=row.max_dungeon_level,
        )
        for i, row in enumerate(rows, start=1)
    ]


@cached(ttl_seconds=300)
async def query_agility_ranking(limit: int = 30) -> list[RankedPlayer]:
    """敏捷排行榜：按 agility DESC"""
    async with readonly_session() as session:
        stmt = (
            select(Player.id, Player.uid, Player.nickname, Player.agility)
            .order_by(Player.agility.desc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()

    return [
        RankedPlayer(
            rank=i,
            player_id=row.id,
            uid=row.uid,
            nickname=row.nickname,
            value=row.agility,
        )
        for i, row in enumerate(rows, start=1)
    ]


@cached(ttl_seconds=300)
async def query_mini_game_ranking(limit: int = 30) -> list[RankedPlayer]:
    """小游戏排行榜：按 mini_game_score DESC"""
    async with readonly_session() as session:
        stmt = (
            select(Player.id, Player.uid, Player.nickname, Player.mini_game_score)
            .order_by(Player.mini_game_score.desc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()

    return [
        RankedPlayer(
            rank=i,
            player_id=row.id,
            uid=row.uid,
            nickname=row.nickname,
            value=row.mini_game_score,
        )
        for i, row in enumerate(rows, start=1)
    ]


@cached(ttl_seconds=300)
async def query_demon_coins_ranking(limit: int = 30) -> list[RankedPlayer]:
    """恶魔币排行榜：按 demon_coins DESC"""
    async with readonly_session() as session:
        stmt = (
            select(Player.id, Player.uid, Player.nickname, Player.demon_coins)
            .where(Player.demon_coins > 0)
            .order_by(Player.demon_coins.desc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()

    return [
        RankedPlayer(
            rank=i,
            player_id=row.id,
            uid=row.uid,
            nickname=row.nickname,
            value=row.demon_coins,
        )
        for i, row in enumerate(rows, start=1)
    ]


# ==================== 财富榜专用查询 ====================

@cached(ttl_seconds=300)
async def query_wealth_ranking(limit: int = 50) -> list[RankedPlayer]:
    """财富排行：一次查询合并 金币 + 存款 + 投资市值

    当前实现 7 次查询 → 优化为 1 次 SQL：
    - LEFT JOIN BankAccount 获取存款
    - LEFT JOIN (子查询) 获取投资市值
    - ORDER BY 总财富 DESC
    """
    async with readonly_session() as session:
        # 子查询：每个玩家的投资市值
        invest_subq = (
            select(
                StockHolding.player_id,
                func.sum(StockHolding.shares * Stock.current_price).label("invest_value"),
            )
            .join(Stock, Stock.id == StockHolding.stock_id)
            .where(StockHolding.shares > 0)
            .group_by(StockHolding.player_id)
            .subquery()
        )

        # 主查询：金币 + 存款 + 投资
        total_wealth = (
            Player.gold
            + func.coalesce(BankAccount.balance, 0)
            + func.coalesce(invest_subq.c.invest_value, 0)
        ).label("total_wealth")

        stmt = (
            select(
                Player.id,
                Player.uid,
                Player.nickname,
                Player.gold,
                func.coalesce(BankAccount.balance, 0).label("bank_balance"),
                func.coalesce(invest_subq.c.invest_value, 0).label("invest_value"),
                total_wealth,
            )
            .outerjoin(BankAccount, BankAccount.player_id == Player.id)
            .outerjoin(invest_subq, invest_subq.c.player_id == Player.id)
            .order_by(total_wealth.desc())
            .limit(limit)
        )

        rows = (await session.execute(stmt)).all()

    return [
        RankedPlayer(
            rank=i,
            player_id=row.id,
            uid=row.uid,
            nickname=row.nickname,
            value=row.total_wealth,
            extra={
                "gold": row.gold,
                "bank_balance": row.bank_balance,
                "invest_value": row.invest_value,
            },
        )
        for i, row in enumerate(rows, start=1)
    ]


# ==================== 玩家排名查询 ====================

async def query_player_rank(
    player_id: str,
    ranking_type: str,
) -> int | None:
    """从已缓存的排行数据中查找指定玩家的排名

    Args:
        player_id: 玩家 ID
        ranking_type: "level" | "luck" | "wealth" | "exploration" | "agility" | "mini_game"

    Returns:
        排名（1-indexed），如果不在榜单中返回 None
    """
    query_map = {
        "level": query_level_ranking,
        "luck": query_luck_ranking,
        "wealth": query_wealth_ranking,
        "exploration": query_exploration_ranking,
        "agility": query_agility_ranking,
        "mini_game": query_mini_game_ranking,
        "demon_coins": query_demon_coins_ranking,
    }

    query_fn = query_map.get(ranking_type)
    if not query_fn:
        return None

    ranked_list = await query_fn()
    for entry in ranked_list:
        if entry.player_id == player_id:
            return entry.rank
    return None


async def query_player_rank_by_counting(
    player_id: str,
    ranking_type: str,
) -> int | None:
    """通过 COUNT 查询获取精确排名（当玩家不在缓存的 TOP N 中时使用）

    Args:
        player_id: 玩家 ID
        ranking_type: 排行类型

    Returns:
        排名（1-indexed），如果玩家不存在返回 None
    """
    async with readonly_session() as session:
        # 先获取玩家数据
        player = await session.get(Player, player_id)
        if not player:
            return None

        if ranking_type == "level":
            count_stmt = select(func.count()).select_from(Player).where(
                (Player.reincarnation_level > player.reincarnation_level) |
                (
                    (Player.reincarnation_level == player.reincarnation_level) &
                    (Player.level > player.level)
                ) |
                (
                    (Player.reincarnation_level == player.reincarnation_level) &
                    (Player.level == player.level) &
                    (Player.exp > player.exp)
                )
            )
        elif ranking_type == "luck":
            count_stmt = select(func.count()).select_from(Player).where(
                Player.luck > player.luck
            )
        elif ranking_type == "exploration":
            count_stmt = select(func.count()).select_from(Player).where(
                Player.max_dungeon_level > player.max_dungeon_level
            )
        elif ranking_type == "agility":
            count_stmt = select(func.count()).select_from(Player).where(
                Player.agility > player.agility
            )
        elif ranking_type == "mini_game":
            count_stmt = select(func.count()).select_from(Player).where(
                Player.mini_game_score > player.mini_game_score
            )
        elif ranking_type == "demon_coins":
            count_stmt = select(func.count()).select_from(Player).where(
                Player.demon_coins > player.demon_coins
            )
        elif ranking_type == "wealth":
            # 财富排名需要特殊处理，先计算该玩家的总财富
            bank_row = await session.get(BankAccount, player_id)
            bank_balance = bank_row.balance if bank_row else 0

            invest_stmt = (
                select(func.sum(StockHolding.shares * Stock.current_price))
                .join(Stock, Stock.id == StockHolding.stock_id)
                .where(StockHolding.player_id == player_id, StockHolding.shares > 0)
            )
            invest_value = (await session.execute(invest_stmt)).scalar() or 0
            my_wealth = player.gold + bank_balance + invest_value

            # 计算比我富的人数
            invest_subq = (
                select(
                    StockHolding.player_id,
                    func.sum(StockHolding.shares * Stock.current_price).label("iv"),
                )
                .join(Stock, Stock.id == StockHolding.stock_id)
                .where(StockHolding.shares > 0)
                .group_by(StockHolding.player_id)
                .subquery()
            )
            wealth_expr = (
                Player.gold
                + func.coalesce(BankAccount.balance, 0)
                + func.coalesce(invest_subq.c.iv, 0)
            )
            count_stmt = (
                select(func.count())
                .select_from(Player)
                .outerjoin(BankAccount, BankAccount.player_id == Player.id)
                .outerjoin(invest_subq, invest_subq.c.player_id == Player.id)
                .where(wealth_expr > my_wealth)
            )
        else:
            return None

        above_count = (await session.execute(count_stmt)).scalar_one()
        return above_count + 1
