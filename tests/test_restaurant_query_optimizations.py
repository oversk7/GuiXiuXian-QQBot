import asyncio
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import event, select
from sqlalchemy.dialects import mysql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plugins.xiuxian_game.cooking import scheduler as restaurant_scheduler
from plugins.xiuxian_game.cooking.settlement_service import SettlementService, DishQuality
from plugins.xiuxian_game.infrastructure.repositories.restaurant_log_repository import RestaurantLogRepository
from plugins.xiuxian_game.infrastructure.repositories.restaurant_menu_repository import RestaurantMenuRepository
from plugins.xiuxian_game.infrastructure.repositories.restaurant_storage_repository import RestaurantStorageRepository
from plugins.xiuxian_game.models import db
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.models.restaurant import Restaurant, RestaurantMenu, RestaurantStorage
from plugins.xiuxian_game.models.restaurant_log import RestaurantLog
from tests.mysql_helpers import mysql_session_factory


@pytest.fixture
async def restaurant_sessions():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for table in (RestaurantMenu.__table__, RestaurantStorage.__table__, RestaurantLog.__table__):
            await connection.run_sync(table.create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def chef(name, speed):
    return SimpleNamespace(name=name, speed=speed, skill=50, specialty=None,
                           personality="diligent", tier="apprentice", experience=0, salary=5)


def settlement_uow(session, chefs):
    restaurant = SimpleNamespace(id=1, player_id="owner", is_open=True, area=10,
                                 reputation=0, level=1, total_income=0, total_expense=0)
    player = SimpleNamespace(gold=1000)
    return SimpleNamespace(
        restaurants=SimpleNamespace(get_by_id=AsyncMock(return_value=restaurant), update=AsyncMock()),
        chefs=SimpleNamespace(get_by_restaurant_id=AsyncMock(return_value=chefs), update=AsyncMock()),
        players=SimpleNamespace(get_by_id=AsyncMock(return_value=player), update=AsyncMock()),
        restaurant_menus=RestaurantMenuRepository(session),
        restaurant_storage=RestaurantStorageRepository(session),
        restaurant_logs=RestaurantLogRepository(session), commit=session.commit,
    )


def fixed_service(monkeypatch):
    service = SettlementService()
    recipe = SimpleNamespace(recipe_id="soup", name="汤", ingredients={"vegetable": 3, "salt": 1},
                             category="soup", base_price=100, tier="white", buff={"attack": 1})
    service.recipe_manager = SimpleNamespace(get_recipe=lambda recipe_id: recipe if recipe_id == "soup" else None)
    monkeypatch.setattr(service, "_calculate_customer_count", lambda *args: 7)
    monkeypatch.setattr(service, "_roll_random_event", lambda *args: None)
    monkeypatch.setattr(service.cooking_service, "_calculate_success_rate", lambda *args: 50)
    monkeypatch.setattr(service.cooking_service, "_determine_quality", lambda *args: DishQuality.NORMAL)
    monkeypatch.setattr("plugins.xiuxian_game.cooking.settlement_service.random.choice", lambda choices: choices[0])
    monkeypatch.setattr("plugins.xiuxian_game.cooking.settlement_service.random.random", lambda: 0)
    return service


async def seed_stock(session, vegetable, salt):
    session.add_all([
        RestaurantMenu(restaurant_id=1, recipe_id="soup", is_active=True),
        RestaurantMenu(restaurant_id=1, recipe_id="inactive", is_active=False),
        RestaurantStorage(restaurant_id=1, item_id="vegetable", quantity=vegetable),
        RestaurantStorage(restaurant_id=1, item_id="salt", quantity=salt),
    ])
    await session.commit()


async def test_settlement_preserves_success_failure_consumption_and_chef_order(restaurant_sessions, monkeypatch):
    service = fixed_service(monkeypatch)
    rolls = Mock(side_effect=[0, 0.99, 0])
    monkeypatch.setattr("plugins.xiuxian_game.cooking.settlement_service.random.random", rolls)
    monkeypatch.setattr(service.cooking_service, "_determine_quality",
                        Mock(side_effect=[DishQuality.PERFECT, DishQuality.NORMAL]))
    chefs = [chef("甲", 2), chef("乙", 3)]
    async with restaurant_sessions() as session:
        await seed_stock(session, 7, 3)
        uow = settlement_uow(session, chefs)
        await service._settle_restaurant(uow, 1)
        assert list((await session.scalars(select(RestaurantStorage))).all()) == []
        log = (await session.scalars(select(RestaurantLog))).one()
        details = json.loads(log.details_json)
        assert [(d["quality"], d["price"], d["buff"]) for d in details["dishes_made"]] == [
            ("perfect", 250, {"attack": 1}), ("dark", 10, None), ("normal", 100, None),
        ]
        assert [c["chef_name"] for c in details["chef_details"]] == ["甲", "乙"]
        assert [c["exp_gained"] for c in details["chef_details"]] == [28, 10]
        assert [c.experience for c in chefs] == [28, 10]
        assert log.dishes_made == 3 and log.dishes_failed == 1
        assert log.income == 360 and log.expense == 10
        assert details["dishes_sold"] == 3 and details["unsold_dishes"] == 0
        assert log.reputation_change == -8
        assert uow.players.get_by_id.return_value.gold == 1350
        assert rolls.call_count == 3


@pytest.mark.parametrize("speed", [1, 30])
async def test_sql_counts_do_not_grow_with_dishes(restaurant_sessions, monkeypatch, speed):
    service = fixed_service(monkeypatch)
    statements = []
    async with restaurant_sessions() as session:
        await seed_stock(session, 1000, 1000)
        engine = session.bind.sync_engine
        def record(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement.lower())
        event.listen(engine, "before_cursor_execute", record)
        try:
            await service._settle_restaurant(settlement_uow(session, [chef("甲", speed), chef("乙", speed)]), 1)
        finally:
            event.remove(engine, "before_cursor_execute", record)
        assert sum(s.startswith("select") and "restaurant_menu" in s for s in statements) == 1
        assert sum(s.startswith("select") and "restaurant_storage" in s for s in statements) == 1
        assert sum(s.startswith("update restaurant_storage") for s in statements) == 1
        stock = {row.item_id: row.quantity for row in (await session.scalars(select(RestaurantStorage))).all()}
        assert stock == {"vegetable": 1000 - 6 * speed, "salt": 1000 - 2 * speed}


async def test_missing_recipe_and_missing_ingredient_preserve_failure_rules(monkeypatch):
    service = fixed_service(monkeypatch)
    chosen = Mock(side_effect=["missing", "soup"])
    monkeypatch.setattr("plugins.xiuxian_game.cooking.settlement_service.random.choice", chosen)
    uow = SimpleNamespace(chefs=SimpleNamespace(update=AsyncMock()))
    result = await service._chef_cook_dishes(uow, chef("甲", 2), [SimpleNamespace(recipe_id="soup")], {"vegetable": 20})
    assert result["failed"] == 1 and result["dishes"] == [] and result["exp_gained"] == 0
    uow.chefs.update.assert_not_awaited()


async def test_global_log_cleanup_runs_one_delete_for_all_restaurants(restaurant_sessions, monkeypatch):
    now = datetime.now()
    async with restaurant_sessions() as session:
        for restaurant_id in (1, 2):
            for age in (1, 8, 20):
                session.add(RestaurantLog(restaurant_id=restaurant_id, period_start=now, period_end=now,
                                          created_at=now - timedelta(days=age), details_json="{}"))
        await session.commit()
    statements = []
    engine = restaurant_sessions.kw["bind"].sync_engine
    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())
    event.listen(engine, "before_cursor_execute", record)
    monkeypatch.setattr(restaurant_scheduler, "AsyncSessionLocal", restaurant_sessions)
    try:
        await restaurant_scheduler.clear_old_restaurant_logs()
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert sum(s.startswith("delete from restaurant_log") for s in statements) == 1
    assert not any(s.startswith("select") for s in statements)
    async with restaurant_sessions() as session:
        logs = list((await session.scalars(select(RestaurantLog))).all())
        assert sorted(log.restaurant_id for log in logs) == [1, 2]
        assert all(log.created_at > now - timedelta(days=7) for log in logs)


async def test_inventory_reads_lock_current_values_in_pk_order():
    session = SimpleNamespace(execute=AsyncMock())
    session.execute.return_value = Mock()
    session.execute.return_value.scalars.return_value.all.return_value = []
    repo = RestaurantStorageRepository(session)
    await repo.get_for_settlement(1)
    statement = session.execute.call_args.args[0]
    sql = str(statement.compile(dialect=mysql.dialect()))
    assert "ORDER BY restaurant_storage.id FOR UPDATE" in sql
    assert statement.get_execution_options()["populate_existing"] is True
    await repo.get_by_restaurant_and_item(1, "salt")
    statement = session.execute.call_args.args[0]
    assert "FOR UPDATE" in str(statement.compile(dialect=mysql.dialect()))
    assert statement.get_execution_options()["populate_existing"] is True


async def test_failed_restaurant_rolls_back_before_next_settlement(monkeypatch):
    service = SettlementService()
    calls = []
    async def settle(uow, restaurant_id):
        calls.append(restaurant_id)
        if restaurant_id == 1:
            raise ValueError("invalid recipe")
        assert calls == [1, "rollback", 2]
    async def rollback():
        calls.append("rollback")
    monkeypatch.setattr(service, "_settle_restaurant", settle)
    uow = SimpleNamespace(restaurants=SimpleNamespace(get_open_restaurants=AsyncMock(
        return_value=[SimpleNamespace(id=1), SimpleNamespace(id=2)])), rollback=rollback)
    assert await service.settle_all_restaurants(uow) == 1


@pytest.mark.parametrize("remaining", [0, 4])
async def test_mysql_restock_waits_for_settlement_and_refreshes_old_snapshot(mysql_session_factory, monkeypatch, remaining):
    monkeypatch.setattr(db, "AsyncSessionLocal", mysql_session_factory)
    async with db.safe_session() as session:
        session.add(Player(id="restaurant-owner", uid=1, nickname="店主"))
        await session.flush()
        restaurant = Restaurant(player_id="restaurant-owner")
        session.add(restaurant)
        await session.flush()
        restaurant_id = restaurant.id
        session.add(RestaurantStorage(restaurant_id=restaurant_id, item_id="salt", quantity=10))
    restock_started = asyncio.Event()
    async with db.safe_session() as settlement, db.safe_session() as restock:
        old = (await restock.scalars(select(RestaurantStorage))).one()
        assert old.quantity == 10
        repo = RestaurantStorageRepository(settlement)
        rows = await repo.get_for_settlement(restaurant_id)
        balances = {"salt": remaining} if remaining else {}
        await repo.apply_settlement_balances(rows, balances)
        async def replenish():
            restock_started.set()
            target = await RestaurantStorageRepository(restock).get_by_restaurant_and_item(restaurant_id, "salt")
            if target is None:
                restock.add(RestaurantStorage(restaurant_id=restaurant_id, item_id="salt", quantity=5))
            else:
                assert target.quantity == remaining
                target.quantity += 5
            await restock.commit()
        task = asyncio.create_task(replenish())
        try:
            await asyncio.wait_for(restock_started.wait(), 5)
            assert not task.done()
            await settlement.commit()
            await asyncio.wait_for(task, 10)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    async with db.safe_session() as session:
        stock = (await session.scalars(select(RestaurantStorage))).one()
        assert stock.quantity == remaining + 5


async def test_mysql_settlement_refreshes_stock_after_restock_commit(mysql_session_factory, monkeypatch):
    monkeypatch.setattr(db, "AsyncSessionLocal", mysql_session_factory)
    async with db.safe_session() as session:
        session.add(Player(id="restaurant-owner", uid=1, nickname="店主"))
        await session.flush()
        restaurant = Restaurant(player_id="restaurant-owner")
        session.add(restaurant)
        await session.flush()
        restaurant_id = restaurant.id
        session.add(RestaurantStorage(restaurant_id=restaurant_id, item_id="salt", quantity=10))
    async with db.safe_session() as settlement:
        old = (await settlement.scalars(select(RestaurantStorage))).one()
        async with db.safe_session() as restock:
            stock = await RestaurantStorageRepository(restock).get_by_restaurant_and_item(restaurant_id, "salt")
            stock.quantity += 5
        assert old.quantity == 10
        repo = RestaurantStorageRepository(settlement)
        rows = await repo.get_for_settlement(restaurant_id)
        assert rows[0].quantity == 15
        await repo.apply_settlement_balances(rows, {"salt": 11})
    async with db.safe_session() as session:
        assert (await session.scalars(select(RestaurantStorage))).one().quantity == 11
