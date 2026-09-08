from contextlib import asynccontextmanager
import sqlite3
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import sqlite

from plugins.xiuxian_game import queries
from plugins.xiuxian_game.queries import ranking_queries


@pytest.fixture
def wealth_db(monkeypatch):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE player (
            id TEXT PRIMARY KEY, uid INTEGER, nickname TEXT,
            gold INTEGER, server_id INTEGER
        );
        CREATE TABLE bank_account (player_id TEXT PRIMARY KEY, balance INTEGER);
        CREATE TABLE stocks (id INTEGER PRIMARY KEY, current_price INTEGER);
        CREATE TABLE stock_holdings (player_id TEXT, stock_id INTEGER, shares INTEGER);
    """)
    connection.executemany(
        "INSERT INTO player VALUES (?, ?, ?, ?, ?)",
        [(f"p{i}", i, f"Player {i}", 1000 - i, 1) for i in range(1, 61)],
    )
    statements = []

    class Session:
        async def execute(self, statement):
            statements.append(statement)
            sql = str(statement.compile(
                dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}
            ))
            rows = [SimpleNamespace(**dict(row)) for row in connection.execute(sql)]
            return SimpleNamespace(all=lambda: rows)

    @asynccontextmanager
    async def readonly_session():
        yield Session()

    monkeypatch.setattr(ranking_queries, "readonly_session", readonly_session)
    monkeypatch.setattr(queries, "_cache", {})
    yield connection, statements
    connection.close()


async def test_rank_beyond_top_50_uses_same_snapshot_after_wealth_changes(wealth_db):
    connection, statements = wealth_db
    initial = await ranking_queries.query_wealth_ranking(server_id=1)
    assert len(initial) == 50

    connection.execute("UPDATE player SET gold = 10000 WHERE id = 'p60'")
    rank = await ranking_queries.query_player_rank("p60", "wealth", server_id=1)
    expanded = await ranking_queries.query_wealth_ranking(limit=rank + 10, server_id=1)

    assert rank == 60
    assert expanded[rank - 1].player_id == "p60"
    assert expanded[rank - 1].rank == rank
    assert expanded[:50] == initial
    assert len(statements) == 1


async def test_snapshot_expiration_refreshes_rank_and_list_together(wealth_db, monkeypatch):
    connection, statements = wealth_db
    clock = SimpleNamespace(now=1000)
    monkeypatch.setattr(queries, "time", SimpleNamespace(time=lambda: clock.now))
    assert await ranking_queries.query_player_rank("p60", "wealth", server_id=1) == 60

    connection.execute("UPDATE player SET gold = 10000 WHERE id = 'p60'")
    clock.now += 301
    rank = await ranking_queries.query_player_rank("p60", "wealth", server_id=1)
    ranked = await ranking_queries.query_wealth_ranking(server_id=1)

    assert rank == 1
    assert ranked[0].player_id == "p60"
    assert ranked[0].rank == rank
    assert len(statements) == 2


async def test_wealth_components_ties_and_server_isolation(wealth_db):
    connection, _ = wealth_db
    connection.executescript("""
        INSERT INTO bank_account VALUES ('p60', 59);
        INSERT INTO stocks VALUES (1, 10);
        INSERT INTO stock_holdings VALUES ('p59', 1, 6);
        INSERT INTO player VALUES ('other', 61, 'Other server', 999999, 2);
    """)
    ranked = await ranking_queries.query_wealth_ranking(limit=70, server_id=1)
    assert [entry.player_id for entry in ranked[:3]] == ["p59", "p1", "p60"]
    assert ranked[0].value == 1001
    assert ranked[1].value == ranked[2].value == 999
    assert await ranking_queries.query_player_rank("p60", "wealth", server_id=1) == 3
    assert await ranking_queries.query_player_rank("other", "wealth", server_id=1) is None
    other_server = await ranking_queries.query_wealth_ranking(server_id=2)
    assert [entry.player_id for entry in other_server] == ["other"]
