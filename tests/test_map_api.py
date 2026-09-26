"""Exercise map and tower HTTP routes with isolated query and rate limit fakes."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.exc import OperationalError

from plugins.xiuxian_game.web import map_api, map_cache, tower_api


class FakeSession:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error
        self.queries = 0

    async def execute(self, stmt):
        self.queries += 1
        await asyncio.sleep(0)
        if self.error:
            raise self.error
        return SimpleNamespace(all=lambda: self.rows[self.queries - 1])


class AllowAll:
    def __init__(self):
        self.calls = []

    async def allow(self, key, limit, window_seconds):
        self.calls.append((key, limit, window_seconds))
        return True


@pytest.mark.parametrize("question", ["问 网页地图位置不更新", "问 网页地图刷新延迟怎么办"])
def test_map_refresh_question_retrieves_player_explanation(question):
    from plugins.xiuxian_game.ai_knowledge_retriever import KnowledgeRetriever

    retriever = KnowledgeRetriever()
    retriever.load(Path(map_api.__file__).parents[1] / "data" / "knowledge")
    hits = retriever.search(question, top_k=5)
    assert any(chunk.id in {"explore_detail", "explore_system_help"}
               and "定时刷新" in chunk.body and "【观察】" in chunk.body
               for chunk, _ in hits)


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(map_api.router)
    app.include_router(tower_api.router)
    return app


async def _get(app, path, *, headers=None):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path, headers=headers)


async def test_map_http_cache_refresh_and_navigation_fields(monkeypatch, app):
    now = [0.0]
    wall = [100.0]
    monkeypatch.setattr(map_cache, "get_redis_backend", lambda: None)
    monkeypatch.setattr(map_api, "_map_cache", map_cache.MapSnapshotCache(ttl_seconds=5, clock=lambda: now[0]))
    monkeypatch.setattr(map_api, "time", SimpleNamespace(time=lambda: wall[0]))
    monkeypatch.setattr(map_api, "_tiles_per_second", lambda agility: 1)
    limiter = AllowAll()
    monkeypatch.setattr(map_api, "_limiter", limiter)
    sessions = []
    last_update = datetime.now() - timedelta(seconds=2)
    rows = [
        [
            (7, "Traveler", 4, 10, 0, 0, 0, 10, 0, last_update),
            (8, None, None, 0, 5, 2, 3, 9, 2, last_update),
        ],
        [("Keeper", 2, 3, 1)],
        [("Guild", 4, 5, 2)],
    ]

    @asynccontextmanager
    async def session_scope():
        session = FakeSession(rows)
        sessions.append(session)
        yield session

    monkeypatch.setattr(map_api, "safe_session", session_scope)
    responses = await asyncio.gather(*(_get(app, "/api/map/data") for _ in range(12)))
    assert all(response.status_code == 200 for response in responses)
    assert len(sessions) == 1
    assert sessions[0].queries == 3
    payload = responses[0].json()
    assert payload["ts"] == 100
    assert set(payload) == {"ts", "cities", "players", "mansions", "guilds"}
    assert payload["cities"] == map_api.CITIES
    assert payload["mansions"] == [{"owner": "Keeper", "x": 2, "y": 3, "lv": 1}]
    assert payload["guilds"] == [{"name": "Guild", "x": 4, "y": 5, "lv": 2}]
    assert 1 <= payload["players"][0]["x"] <= 4
    assert payload["players"][0]["nav"] == {"tx": 10, "ty": 0}
    dungeon_player = payload["players"][1].copy()
    assert 6 <= dungeon_player.pop("x") <= 9
    assert dungeon_player == {"uid": 8, "name": "修仙者#8", "y": 2, "lv": 1, "dg": 3}
    assert all(response.json() == payload for response in responses)
    assert responses[0].headers["x-frame-options"] == "DENY"
    assert responses[0].headers["cache-control"] == "no-store"
    assert responses[0].headers["x-content-type-options"] == "nosniff"
    assert limiter.calls == [("127.0.0.1", 30, 60)] * 12

    now[0] = 5
    wall[0] = 105
    refreshed = await _get(app, "/api/map/data")
    assert refreshed.json()["ts"] == 105
    assert len(sessions) == 2
    assert sessions[1].queries == 3


async def test_map_db_error_returns_503_and_is_not_cached(monkeypatch, app):
    monkeypatch.setattr(map_cache, "get_redis_backend", lambda: None)
    monkeypatch.setattr(map_api, "_map_cache", map_cache.MapSnapshotCache(ttl_seconds=5))
    monkeypatch.setattr(map_api, "_limiter", AllowAll())
    sessions = []

    @asynccontextmanager
    async def session_scope():
        session = FakeSession(error=OperationalError("SELECT", {}, Exception("offline")))
        sessions.append(session)
        yield session

    monkeypatch.setattr(map_api, "safe_session", session_scope)
    for _ in range(2):
        response = await _get(app, "/api/map/data")
        assert response.status_code == 503
        assert response.json() == {"error": "服务暂时不可用"}
        assert response.headers["cache-control"] == "no-store"
    assert len(sessions) == 2
    assert [s.queries for s in sessions] == [1, 1]


async def test_shared_ip_limit_precedes_map_cache_and_tower_query(monkeypatch, app):
    class Limiter:
        def __init__(self):
            self.calls = []

        async def allow(self, key, limit, window_seconds):
            self.calls.append((key, limit, window_seconds))
            return len(self.calls) == 1

    limiter = Limiter()
    monkeypatch.setattr(map_api, "_limiter", limiter)
    monkeypatch.setattr(tower_api, "_limiter", limiter)

    class Cache:
        calls = 0

        async def get_or_load(self, loader):
            self.calls += 1
            return {"ts": 1, "cities": [], "players": [], "mansions": [], "guilds": []}

    cache = Cache()
    monkeypatch.setattr(map_api, "_map_cache", cache)
    monkeypatch.setattr(tower_api, "AsyncSessionLocal", lambda: pytest.fail("tower queried DB"))
    assert (await _get(app, "/api/map/data", headers={"X-Forwarded-For": "8.8.8.8"})).status_code == 200
    blocked_map = await _get(app, "/api/map/data")
    blocked_tower = await _get(app, "/api/tower/data")
    assert blocked_map.status_code == blocked_tower.status_code == 429
    assert cache.calls == 1
    assert blocked_map.headers["x-frame-options"] == blocked_tower.headers["x-frame-options"] == "DENY"
    assert blocked_map.headers["cache-control"] == blocked_tower.headers["cache-control"] == "no-store"
    assert limiter.calls == [("127.0.0.1", 30, 60)] * 3
