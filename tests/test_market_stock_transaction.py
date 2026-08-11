from datetime import date
from types import SimpleNamespace

from plugins.xiuxian_game.achievement.achievement_service import AchievementService
from plugins.xiuxian_game.economy import merchant_service
from plugins.xiuxian_game.economy.merchant_service import _lock_trade_player
from plugins.xiuxian_game.models.market_state import MarketState


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value


class _StatementSession:
    def __init__(self, result):
        self.result = result
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _ScalarResult(self.result)


async def test_trade_player_lock_refreshes_existing_player_snapshot():
    player = SimpleNamespace(id="player-1")
    session = _StatementSession(player)

    actual = await _lock_trade_player(session, player.id)

    assert actual is player
    assert session.statement._for_update_arg is not None
    assert session.statement.get_execution_options()["populate_existing"] is True


async def test_market_state_lock_refreshes_existing_inventory_snapshot():
    market_state = SimpleNamespace()
    session = _StatementSession(market_state)

    actual = await MarketState.get_or_create(
        session,
        "merchant_fengxuezhen",
        "yin_grass",
        lock_for_update=True,
    )

    assert actual is market_state
    assert session.statement._for_update_arg is not None
    assert session.statement.get_execution_options()["populate_existing"] is True


class _FakeMarketState:
    last_refresh_date = date.today()

    async def check_daily_refresh(self, session):
        return None

    async def check_restock(self, session):
        return None

    def get_price_multiplier(self):
        return 1.0


async def test_price_lookup_locks_stock_before_restock(monkeypatch):
    calls = []

    async def fake_get_or_create(
        cls, session, market_id, item_id, lock_for_update=False
    ):
        calls.append((market_id, item_id, lock_for_update))
        return _FakeMarketState()

    monkeypatch.setattr(
        MarketState, "get_or_create", classmethod(fake_get_or_create)
    )
    market = SimpleNamespace(id="merchant_fengxuezhen", name="风雪镇")

    await merchant_service._price_for(object(), market, "yin_grass")

    assert calls == [("merchant_fengxuezhen", "yin_grass", True)]


async def test_black_market_refresh_locks_rows_in_stable_order(monkeypatch):
    calls = []

    async def fake_get_or_create(
        cls, session, market_id, item_id, lock_for_update=False
    ):
        calls.append((market_id, item_id, lock_for_update))
        return _FakeMarketState()

    monkeypatch.setattr(
        MarketState, "get_or_create", classmethod(fake_get_or_create)
    )

    await merchant_service._ensure_black_market_stock(
        object(), ["upgrade_stone_mid", "upgrade_stone_low"]
    )

    assert calls == [
        ("black_market", "upgrade_stone_low", True),
        ("black_market", "upgrade_stone_mid", True),
    ]


class _AchievementSession:
    def __init__(self):
        self.results = iter([_ScalarResult(None), _ScalarResult(None)])
        self.added = []
        self.commit_count = 0
        self.flush_count = 0

    async def execute(self, statement):
        return next(self.results)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commit_count += 1

    async def flush(self):
        self.flush_count += 1


async def test_player_stats_init_preserves_outer_transaction():
    session = _AchievementSession()

    await AchievementService.init_player_stats(
        session,
        "missing-player",
        auto_commit=False,
    )

    assert len(session.added) == 1
    assert session.commit_count == 0
    assert session.flush_count == 1
