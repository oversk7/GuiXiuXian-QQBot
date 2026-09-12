import asyncio
from contextlib import asynccontextmanager, nullcontext
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.exception import FinishedException
from nonebot.adapters.qq import Message
from sqlalchemy import func, select
from sqlalchemy.dialects import mysql
from sqlalchemy.orm.exc import StaleDataError

from plugins.xiuxian_game.achievement.achievement_service import AchievementService
from plugins.xiuxian_game.economy import market
from plugins.xiuxian_game.economy.equipment_trade_service import EquipmentTradeService
from plugins.xiuxian_game.infrastructure.repositories.item_repository import ItemRepository
from plugins.xiuxian_game.infrastructure.repositories.market_order_repository import MatchingCandidate, MarketOrderRepository
from plugins.xiuxian_game.models import db
from plugins.xiuxian_game.models.inventory import ItemInstance
from plugins.xiuxian_game.models.market_order import MarketOrder, OrderSide
from plugins.xiuxian_game.models.player import Player
from tests.mysql_helpers import mysql_session_factory


class StatementSession:
    def __init__(self, rows):
        self.rows = rows
        self.identity_map = {}
        self.autoflush = True
        self.flush = AsyncMock()
        self.statements = []
        self.no_autoflush = nullcontext()

    async def execute(self, statement):
        self.statements.append(statement)
        return self

    def scalars(self):
        return self

    def all(self):
        return self.rows


def make_order(player_id="buyer", **kwargs):
    values = dict(server_id=1, player_id=player_id, side=OrderSide.BUY,
                  item_id="yin_grass", price=10, quantity=6, is_instance_trade=False)
    values.update(kwargs)
    return MarketOrder(**values)


async def test_candidate_lock_uses_pk_order_and_current_quantities():
    current = make_order("seller", id=9, side=OrderSide.SELL, quantity=4, created_at=datetime.now())
    session = StatementSession([current])
    result = await MarketOrderRepository(session).lock_candidates(
        make_order(), [MatchingCandidate(9, "seller", 6), MatchingCandidate(3, "gone", 6)], False
    )
    assert result == [current]
    assert result[0].quantity == 4
    statement = session.statements[0]
    sql = str(statement.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "market_orders.id IN (3, 9)" in sql
    assert "ORDER BY market_orders.id FOR UPDATE" in sql
    assert statement.get_execution_options()["populate_existing"] is True


async def test_cancel_lookup_uses_the_same_current_row_lock():
    session = StatementSession([])
    assert await MarketOrderRepository(session).lock_by_id(9) is None
    statement = session.statements[0]
    assert "FOR UPDATE" in str(statement.compile(dialect=mysql.dialect()))
    assert statement.get_execution_options()["populate_existing"] is True


async def test_locked_candidates_keep_price_time_priority_and_drop_invalid_rows():
    now = datetime.now()
    rows = [make_order("seller", id=pk, price=price, side=OrderSide.SELL,
                       quantity=quantity, created_at=now)
            for pk, price, quantity in [(1, 10, 2), (2, 8, 2), (3, 7, 0), (4, 11, 3)]]
    repo = MarketOrderRepository(StatementSession(rows))
    result = await repo.lock_candidates(make_order(), [MatchingCandidate(r.id, r.player_id, r.quantity) for r in rows], False)
    assert [row.id for row in result] == [2, 1]


@pytest.mark.parametrize("changes", [
    {"player_id": "new-owner"}, {"equipped": True},
    {"extra_attrs": {"_frozen_for_trade": True}},
    {"extra_attrs": {"_frozen_for_auction": True}},
    {"extra_attrs": {"_frozen_for_other": True}},
    {"extra_attrs": {"_player_locked": True}},
])
async def test_freeze_rechecks_locked_owner_equipped_and_freeze_flags(changes):
    old = SimpleNamespace(id=1, player_id="seller", equipped=False, extra_attrs={})
    values = dict(vars(old))
    values.update(changes)
    current = SimpleNamespace(**values)
    session = StatementSession([current])
    service = EquipmentTradeService(ItemRepository(session), SimpleNamespace())
    assert await service.freeze_equipment(old, "seller") is False
    assert vars(current) == values


async def test_market_transfer_cannot_take_item_back_from_previous_buyer():
    stale = SimpleNamespace(id=1, player_id="seller")
    current = SimpleNamespace(id=1, player_id="first-buyer", equipped=False, extra_attrs={})
    service = EquipmentTradeService(ItemRepository(StatementSession([current])), SimpleNamespace())
    assert await service.transfer_equipment(stale, "second-buyer", "seller") is False
    assert current.player_id == "first-buyer"


async def test_market_transfer_updates_owner_and_unfreezes_together():
    item = SimpleNamespace(id=1, player_id="seller", equipped=False,
                           extra_attrs={"_frozen_for_trade": True, "quality": 5})
    service = EquipmentTradeService(ItemRepository(StatementSession([item])), SimpleNamespace())
    assert await service.transfer_equipment(item, "buyer", "seller") is True
    assert item.player_id == "buyer"
    assert item.extra_attrs == {"quality": 5}


async def test_direct_gift_still_works_but_cannot_unfreeze_market_item():
    item = SimpleNamespace(id=1, player_id="seller", equipped=False,
                           extra_attrs={"_frozen_for_trade": True})
    service = EquipmentTradeService(ItemRepository(StatementSession([item])), SimpleNamespace())
    assert await service.transfer_equipment(item, "buyer") is False
    item.extra_attrs = {}
    assert await service.transfer_equipment(item, "buyer") is True


async def test_rejected_equipment_price_never_freezes(monkeypatch):
    freeze = AsyncMock()
    monkeypatch.setattr(EquipmentTradeService, "freeze_equipment", freeze)
    monkeypatch.setattr(EquipmentTradeService, "generate_instance_summary", lambda item: "equipment")
    monkeypatch.setattr(market, "_compute_equipment_floor_price", AsyncMock(return_value=10))
    monkeypatch.setattr(market, "message_add_head", lambda message, event: message)
    monkeypatch.setattr(market.list_cmd, "finish", AsyncMock(side_effect=FinishedException))
    item = SimpleNamespace(is_equipment=True, extra_attrs={})
    with pytest.raises(FinishedException):
        await market._create_instance_order(object(), SimpleNamespace(server_id=1), item, 81, object())
    freeze.assert_not_awaited()
    assert item.extra_attrs == {}


async def test_reservation_waits_for_all_participants_and_current_orders(monkeypatch):
    player = SimpleNamespace(id="buyer", gold=1000)
    seller = SimpleNamespace(id="seller", gold=1000)
    order = make_order()
    calls = []
    session = StatementSession([])

    @asynccontextmanager
    async def savepoint():
        yield

    session.begin_nested = savepoint
    session.add = lambda value: calls.append("reserve")
    session.flush = AsyncMock()

    async def candidates(repo, new_order, same_price_only):
        calls.append("candidates")
        return [MatchingCandidate(3, "seller", 6)]

    async def participants(session, model, ids):
        assert model is Player and set(ids) == {"buyer", "seller"}
        assert player.gold == 1000
        calls.append("players")
        return [player, seller]

    async def orders(repo, new_order, candidates, same_price_only):
        assert player.gold == 1000
        calls.append("orders")
        return []

    monkeypatch.setattr(MarketOrderRepository, "matching_candidates", candidates)
    monkeypatch.setattr(MarketOrderRepository, "lock_candidates", orders)
    monkeypatch.setattr(market, "lock_rows", participants)
    monkeypatch.setattr(market, "_try_auto_match", AsyncMock(return_value=""))
    await market._place_market_order(session, order)
    assert calls == ["candidates", "players", "orders", "reserve"]
    assert player.gold == 940


@pytest.mark.parametrize("entry", ["list", "instance", "selection", "cancel"])
async def test_transaction_entries_disable_autoflush_before_identity_queries(monkeypatch, entry):
    player = SimpleNamespace(id="buyer", server_id=1, gold=1000, last_active_at=None)
    item = SimpleNamespace(id=7, player_id=player.id, extra_attrs={}, equipped=False)
    session = StatementSession([item])
    session.scalar = lambda: 0

    @asynccontextmanager
    async def safe_session():
        yield session

    async def identity(session, *args):
        assert session.autoflush is False
        player.last_active_at = datetime.now()
        return player

    async def get(model, key):
        assert session.autoflush is False
        return player if model is Player else item

    async def stop(*args, **kwargs):
        assert session.autoflush is False
        session.flush.assert_not_awaited()
        raise FinishedException

    async def floor(session, *args):
        assert session.autoflush is False
        return 10

    session.get = get
    monkeypatch.setattr(market, "safe_session", safe_session)
    monkeypatch.setattr(market, "get_unified_player", identity)
    monkeypatch.setattr(market, "require_player", identity)
    monkeypatch.setattr(market, "_place_market_order", stop)
    monkeypatch.setattr(market, "_create_instance_order", stop)
    monkeypatch.setattr(market, "_cancel_market_order", stop)
    monkeypatch.setattr(market, "_compute_item_floor_price", floor)
    monkeypatch.setattr(EquipmentTradeService, "is_instance_trade", lambda _: False)
    cfg = SimpleNamespace(item_id="test_material", name="测试材料", type=market.ItemType.MATERIAL)
    monkeypatch.setitem(market.config.items_config["by_name"], cfg.name, cfg)
    event = SimpleNamespace(get_message=lambda: Message("1"))
    with pytest.raises(FinishedException):
        if entry == "list":
            await market.list_cmd.handlers[0].call(event, Message("收购 测试材料 10 1"))
        elif entry == "instance":
            await market._handle_instance_listing(event, cfg, 10)
        elif entry == "selection":
            monkeypatch.setattr(market, "_cleanup_expired_states", lambda: None)
            monkeypatch.setitem(market.equipment_selection_state, player.id,
                                {"equipment_ids": [item.id], "price": 10})
            await market.equipment_selection_handler.handlers[0].call(event)
        else:
            await market.cancel_cmd.handlers[0].call(event, Message("7"))


@pytest.mark.parametrize("entry", ["list", "instance", "cancel"])
async def test_failure_rolls_back_before_finish(monkeypatch, entry):
    player = SimpleNamespace(id="buyer", server_id=1, gold=1000)
    session = StatementSession([])
    session.rollback = AsyncMock()
    session.scalar = lambda: 0

    @asynccontextmanager
    async def safe_session():
        yield session

    async def finish(*args):
        session.rollback.assert_awaited_once()
        raise FinishedException

    monkeypatch.setattr(market, "safe_session", safe_session)
    monkeypatch.setattr(market, "get_unified_player", AsyncMock(return_value=player))
    monkeypatch.setattr(market, "require_player", AsyncMock(return_value=player))
    monkeypatch.setattr(market, "_place_market_order", AsyncMock(side_effect=ValueError("冲突")))
    monkeypatch.setattr(market, "_cancel_market_order", AsyncMock(side_effect=ValueError("冲突")))
    monkeypatch.setattr(market, "_compute_item_floor_price", AsyncMock(return_value=10))
    monkeypatch.setattr(market, "_compute_equipment_floor_price", AsyncMock(return_value=10))
    monkeypatch.setattr(EquipmentTradeService, "is_instance_trade", lambda _: False)
    monkeypatch.setattr(EquipmentTradeService, "generate_instance_summary", lambda _: "equipment")
    monkeypatch.setattr(market.list_cmd, "finish", finish)
    monkeypatch.setattr(market.cancel_cmd, "finish", finish)
    cfg = SimpleNamespace(item_id="test_material", name="测试材料", type=market.ItemType.MATERIAL)
    monkeypatch.setitem(market.config.items_config["by_name"], cfg.name, cfg)
    with pytest.raises(FinishedException):
        if entry == "list":
            await market.list_cmd.handlers[0].call(object(), Message("收购 测试材料 10 1"))
        elif entry == "instance":
            item = SimpleNamespace(id=7, item_id=cfg.item_id, is_equipment=True)
            await market._create_instance_order(session, player, item, 10, object())
        else:
            await market.cancel_cmd.handlers[0].call(object(), Message("7"))


@pytest.mark.parametrize("is_instance", [False, True])
async def test_listing_cap_uses_current_locked_count_before_reserving(monkeypatch, is_instance):
    player = SimpleNamespace(id="buyer", gold=1000)
    session = StatementSession([(i,) for i in range(6)])
    reserve = AsyncMock()
    monkeypatch.setattr(market, "lock_rows", AsyncMock(return_value=[player]))
    monkeypatch.setattr(MarketOrderRepository, "matching_candidates", AsyncMock(return_value=[]))
    monkeypatch.setattr(MarketOrderRepository, "lock_candidates", AsyncMock(return_value=[]))
    monkeypatch.setattr(EquipmentTradeService, "freeze_equipment", reserve)
    monkeypatch.setattr(ItemInstance, "consume_item", reserve)
    order = make_order(is_instance_trade=is_instance,
                       side=OrderSide.SELL if is_instance else OrderSide.BUY)
    with pytest.raises(ValueError, match="挂满 6"):
        await market._place_market_order(session, order, instance=SimpleNamespace(id=7))
    assert player.gold == 1000
    reserve.assert_not_awaited()
    statement = session.statements[-1]
    sql = str(statement.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "market_orders.player_id = 'buyer'" in sql
    assert "ORDER BY market_orders.id FOR UPDATE" in sql
    session.flush.assert_not_awaited()


async def test_transfer_flushes_pending_freeze_and_owner_before_current_read():
    item = SimpleNamespace(id=1, player_id="seller", equipped=False,
                           extra_attrs={"_frozen_for_trade": True})
    stored = SimpleNamespace(player_id="seller", extra_attrs={})
    session = StatementSession([item])
    session.autoflush = False

    async def flush():
        stored.player_id = item.player_id
        stored.extra_attrs = dict(item.extra_attrs)

    async def current_read(statement):
        item.player_id = stored.player_id
        item.extra_attrs = dict(stored.extra_attrs)
        return session

    session.flush = AsyncMock(side_effect=flush)
    session.execute = current_read
    service = EquipmentTradeService(ItemRepository(session), SimpleNamespace())
    assert await service.transfer_equipment(item, "first-buyer", "seller") is True
    assert await service.transfer_equipment(item, "second-buyer", "seller") is False
    assert item.player_id == "first-buyer"
    assert item.extra_attrs == {}
    assert session.flush.await_count == 2


@pytest.mark.parametrize("side, price_order", [(OrderSide.BUY, "ASC"), (OrderSide.SELL, "DESC")])
async def test_candidate_discovery_is_ordered_mvcc_without_autoflush(side, price_order):
    session = StatementSession([(3, "seller", 8)])
    rows = await MarketOrderRepository(session).matching_candidates(make_order(side=side), False)
    assert rows == [MatchingCandidate(3, "seller", 8)]
    sql = str(session.statements[0].compile(dialect=mysql.dialect()))
    assert f"ORDER BY market_orders.price {price_order}, market_orders.created_at, market_orders.id" in sql
    assert "FOR UPDATE" not in sql
    session.flush.assert_not_awaited()


@pytest.mark.parametrize("current_quantity", [0, 1])
async def test_shrunken_prefix_with_tail_fails_before_reservation(monkeypatch, current_quantity):
    session = StatementSession([])
    player = SimpleNamespace(id="buyer", gold=1000)
    prefix = MatchingCandidate(9, "seller", 2)
    tail = MatchingCandidate(3, "tail", 4)
    monkeypatch.setattr(MarketOrderRepository, "matching_candidates", AsyncMock(return_value=[prefix, tail]))
    players = AsyncMock(return_value=[player, SimpleNamespace(id="seller")])
    monkeypatch.setattr(market, "lock_rows", players)
    locked = AsyncMock(return_value=[make_order("seller", quantity=current_quantity)] if current_quantity else [])
    monkeypatch.setattr(MarketOrderRepository, "lock_candidates", locked)
    with pytest.raises(StaleDataError):
        await market._place_market_order(session, make_order(quantity=2))
    assert players.call_args.args[2] == ["buyer", "seller"]
    assert locked.call_args.args[1] == [prefix]
    assert player.gold == 1000
    session.flush.assert_not_awaited()


async def seed_market(monkeypatch, factory):
    monkeypatch.setattr(db, "AsyncSessionLocal", factory)
    monkeypatch.setattr(AchievementService, "update_stat", AsyncMock())
    async with db.safe_session() as session:
        session.add_all([
            Player(id=name, uid=index, nickname=name, gold=1000)
            for index, name in enumerate(["seller", "buyer-a", "buyer-b"], 1)
        ])
        await session.flush()
        order = make_order("seller", side=OrderSide.SELL, quantity=10)
        session.add(order)
        await session.flush()
        return order.id


async def test_mysql_unselected_tail_seller_lock_does_not_block_one_item(mysql_session_factory, monkeypatch):
    order_id = await seed_market(monkeypatch, mysql_session_factory)
    async with db.safe_session() as session:
        (await session.get(MarketOrder, order_id)).created_at = datetime(2020, 1, 1)
        tail = make_order("buyer-b", side=OrderSide.SELL, quantity=10)
        session.add(tail)
        await session.flush()
        tail_id = tail.id
    async with db.safe_session() as blocker:
        await market.lock_row(blocker, Player, "buyer-b")
        await market.lock_row(blocker, MarketOrder, tail_id)

        async def buy():
            async with db.safe_session() as session:
                await market._place_market_order(session, make_order("buyer-a", quantity=1))

        await asyncio.wait_for(buy(), 10)
    async with db.safe_session() as session:
        assert (await session.get(MarketOrder, order_id)).quantity == 9
        assert (await session.get(MarketOrder, tail_id)).quantity == 10
        assert (await session.get(Player, "buyer-a")).gold == 990
        assert await session.scalar(select(func.sum(ItemInstance.quantity)).where(
            ItemInstance.player_id == "buyer-a")) == 1


@pytest.mark.parametrize("cancel_prefix", [False, True])
async def test_mysql_shrunken_prefix_with_tail_rolls_back_entire_order(mysql_session_factory, monkeypatch, cancel_prefix):
    order_id = await seed_market(monkeypatch, mysql_session_factory)
    async with db.safe_session() as session:
        prefix = await session.get(MarketOrder, order_id)
        prefix.quantity = 2
        prefix.created_at = datetime(2020, 1, 1)
        tail = make_order("buyer-b", side=OrderSide.SELL, quantity=10)
        session.add(tail)
        await session.flush()
        tail_id = tail.id
    original = MarketOrderRepository.matching_candidates

    async def shrink_after_discovery(repo, order, same_price_only):
        rows = await original(repo, order, same_price_only)
        async with db.safe_session() as session:
            if cancel_prefix:
                await market._cancel_market_order(session, "seller", order_id)
            else:
                await market.lock_row(session, Player, "seller")
                prefix = await market.lock_row(session, MarketOrder, order_id)
                prefix.quantity = 1
        return rows

    monkeypatch.setattr(MarketOrderRepository, "matching_candidates", shrink_after_discovery)
    with pytest.raises(StaleDataError):
        async with db.safe_session() as session:
            buyer = await session.get(Player, "buyer-a")
            buyer.nickname = "must-rollback"
            await market._place_market_order(session, make_order("buyer-a", quantity=2))
    async with db.safe_session() as session:
        buyer = await session.get(Player, "buyer-a")
        assert buyer.gold == 1000 and buyer.nickname == "buyer-a"
        assert (await session.get(Player, "seller")).gold == 1000
        assert (await session.get(Player, "buyer-b")).gold == 1000
        assert (await session.get(MarketOrder, tail_id)).quantity == 10
        assert await session.scalar(select(func.count()).select_from(MarketOrder).where(
            MarketOrder.player_id == "buyer-a")) == 0
        assert await session.scalar(select(func.count()).select_from(ItemInstance).where(
            ItemInstance.player_id == "buyer-a")) == 0
        prefix = await session.get(MarketOrder, order_id)
        assert prefix is None if cancel_prefix else prefix.quantity == 1


async def test_mysql_two_buyers_cannot_oversell_ten_items(mysql_session_factory, monkeypatch):
    order_id = await seed_market(monkeypatch, mysql_session_factory)
    original = MarketOrderRepository.matching_candidates
    ready = asyncio.Event()
    arrivals = 0

    async def synchronized_candidates(repo, order, same_price_only):
        nonlocal arrivals
        rows = await original(repo, order, same_price_only)
        arrivals += 1
        if arrivals == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), 10)
        return rows

    monkeypatch.setattr(MarketOrderRepository, "matching_candidates", synchronized_candidates)

    async def buy(player_id):
        async with db.safe_session() as session:
            # 两个会话都保留卖单数量为10的旧ORM对象。
            stale = await session.get(MarketOrder, order_id)
            assert stale.quantity == 10
            await market._place_market_order(session, make_order(player_id))

    await asyncio.wait_for(asyncio.gather(buy("buyer-a"), buy("buyer-b")), 30)
    async with db.safe_session() as session:
        quantity = await session.scalar(select(func.sum(ItemInstance.quantity)).where(
            ItemInstance.player_id.in_(["buyer-a", "buyer-b"]), ItemInstance.item_id == "yin_grass"))
        assert quantity == 10
        assert await session.get(MarketOrder, order_id) is None
        remaining = (await session.execute(select(MarketOrder))).scalars().all()
        assert len(remaining) == 1 and remaining[0].quantity == 2
        players = (await session.execute(select(Player))).scalars().all()
        assert sum(player.gold for player in players) + 20 == 3000
        assert next(player.gold for player in players if player.id == "seller") == 1100


async def test_mysql_cancel_before_match_does_not_deliver_cancelled_stock(mysql_session_factory, monkeypatch):
    order_id = await seed_market(monkeypatch, mysql_session_factory)
    discovered = asyncio.Event()
    cancelled = asyncio.Event()
    original = MarketOrderRepository.matching_candidates

    async def candidates_then_cancel(repo, order, same_price_only):
        rows = await original(repo, order, same_price_only)
        discovered.set()
        await asyncio.wait_for(cancelled.wait(), 10)
        return rows

    monkeypatch.setattr(MarketOrderRepository, "matching_candidates", candidates_then_cancel)

    async def buy():
        async with db.safe_session() as session:
            await market._place_market_order(session, make_order("buyer-a"))

    async def cancel():
        await asyncio.wait_for(discovered.wait(), 10)
        async with db.safe_session() as session:
            await market._cancel_market_order(session, "seller", order_id)
        cancelled.set()

    await asyncio.wait_for(asyncio.gather(buy(), cancel()), 30)
    async with db.safe_session() as session:
        stock = (await session.execute(select(ItemInstance))).scalars().all()
        assert sum(item.quantity for item in stock if item.player_id == "seller") == 10
        assert not [item for item in stock if item.player_id == "buyer-a"]
        assert (await session.get(Player, "buyer-a")).gold == 940


@pytest.mark.parametrize("side", [OrderSide.SELL, OrderSide.BUY])
async def test_mysql_duplicate_cancel_refunds_once(mysql_session_factory, monkeypatch, side):
    order_id = await seed_market(monkeypatch, mysql_session_factory)
    if side == OrderSide.BUY:
        async with db.safe_session() as session:
            (await session.get(MarketOrder, order_id)).side = side
            (await session.get(Player, "seller")).gold = 900

    async def cancel():
        try:
            async with db.safe_session() as session:
                await market._cancel_market_order(session, "seller", order_id)
            return True
        except ValueError:
            return False

    results = await asyncio.wait_for(asyncio.gather(cancel(), cancel()), 30)
    assert sorted(results) == [False, True]
    async with db.safe_session() as session:
        if side == OrderSide.SELL:
            assert await session.scalar(select(func.sum(ItemInstance.quantity))) == 10
        else:
            assert (await session.get(Player, "seller")).gold == 1000
        assert await session.get(MarketOrder, order_id) is None


async def test_mysql_stale_equipment_rolls_back_reservation_and_previous_fill(mysql_session_factory, monkeypatch):
    order_id = await seed_market(monkeypatch, mysql_session_factory)
    async with db.safe_session() as session:
        item = ItemInstance(player_id="buyer-b", item_id="yin_grass", quantity=1)
        session.add(item)
        await session.flush()
        item_id = item.id
        order = await session.get(MarketOrder, order_id)
        order.quantity = 1
        order.created_at = datetime(2020, 1, 1)
        session.add(make_order("seller", side=OrderSide.SELL, quantity=1,
                               is_instance_trade=True, item_instance_id=item.id))
    async with db.safe_session() as session:
        with pytest.raises(ValueError, match="状态已变化"):
            await market._place_market_order(session, make_order("buyer-a", quantity=2))
        # 正常离开safe_session，仍不得提交买家的预扣金币或新订单。
    async with db.safe_session() as session:
        assert (await session.get(Player, "buyer-a")).gold == 1000
        assert (await session.get(ItemInstance, item_id)).player_id == "buyer-b"
        assert (await session.get(Player, "seller")).gold == 1000
        assert (await session.get(MarketOrder, order_id)).quantity == 1
        assert await session.scalar(select(func.count()).select_from(MarketOrder)) == 2
        assert await session.scalar(select(func.count()).select_from(ItemInstance).where(
            ItemInstance.player_id == "buyer-a")) == 0
