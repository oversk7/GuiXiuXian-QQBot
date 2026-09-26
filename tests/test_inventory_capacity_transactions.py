from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plugins.xiuxian_game.achievement.achievement_service import AchievementService
from plugins.xiuxian_game.economy.part_time_job_service import PartTimeJobService
from plugins.xiuxian_game.infrastructure.exceptions import InventoryCapacityError
from plugins.xiuxian_game.infrastructure.uow.unit_of_work import UnitOfWork
from plugins.xiuxian_game.models.db import Base, safe_session
from plugins.xiuxian_game.models.inventory import ItemInstance
from plugins.xiuxian_game.models.part_time_job import PartTimeJob, PlayerJobStats
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.models.spirit_field import SpiritField, SpiritFieldPlot
from plugins.xiuxian_game.spirit_field.spirit_field_service import SpiritFieldService
from tests.mysql_helpers import mysql_session_factory


@pytest.fixture
async def inventory_store(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'inventory.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=[
            Player.__table__, ItemInstance.__table__, PartTimeJob.__table__, PlayerJobStats.__table__,
            SpiritField.__table__, SpiritFieldPlot.__table__,
        ]))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
def capacity(monkeypatch):
    capacity = AsyncMock(return_value=1)
    monkeypatch.setattr(Player, "get_effective_inventory_capacity", capacity)
    monkeypatch.setattr(AchievementService, "update_stat", AsyncMock())
    return capacity


async def test_full_bag_can_stack_but_overflow_does_not_change_items(inventory_store, capacity):
    async with safe_session(inventory_store) as session:
        session.add(Player(id="p", uid=1, nickname="测试"))
        await session.flush()
        await ItemInstance.add_item(session, "p", "heal_potion", 99)
    with pytest.raises(InventoryCapacityError):
        async with safe_session(inventory_store) as session:
            await ItemInstance.add_item(session, "p", "heal_potion", 2)
    async with safe_session(inventory_store) as session:
        assert await session.scalar(select(func.sum(ItemInstance.quantity))) == 99
        assert await ItemInstance.add_item(session, "p", "heal_potion", 1)
    async with safe_session(inventory_store) as session:
        assert await session.scalar(select(func.sum(ItemInstance.quantity))) == 100
        with pytest.raises(ValueError) as error:
            await ItemInstance.add_item(session, "p", "not_a_real_item", 1)
        assert not isinstance(error.value, InventoryCapacityError)


async def test_second_reward_failure_rolls_back_payment_and_first_reward(inventory_store, capacity):
    async with safe_session(inventory_store) as session:
        session.add(Player(id="p", uid=1, nickname="测试", gold=100))
    with pytest.raises(InventoryCapacityError):
        async with safe_session(inventory_store) as session:
            player = await session.get(Player, "p")
            player.gold -= 50
            await ItemInstance.add_item(session, "p", "heal_potion", 100)
            await ItemInstance.add_item(session, "p", "spirit_herb", 1)
    async with safe_session(inventory_store) as session:
        assert (await session.get(Player, "p")).gold == 100
        assert await session.scalar(select(func.count()).select_from(ItemInstance)) == 0


async def _check_job_retry(factory, monkeypatch):
    async with safe_session(factory) as session:
        session.add(Player(id="p", uid=1, nickname="测试", gold=100))
        await session.flush()
        session.add(ItemInstance(player_id="p", item_id="spirit_herb", quantity=100))
        session.add(PartTimeJob(
            player_id="p", job_location_id="shop", job_type="cashier", is_working=True,
            end_time=datetime.now() - timedelta(minutes=1),
        ))
        session.add(PlayerJobStats(player_id="p"))
    monkeypatch.setattr(PartTimeJobService, "roll_item_drop", lambda *args: {
        "item_id": "heal_potion", "name": "回春散", "quantity": 1,
    })

    async def complete():
        async with UnitOfWork(factory) as uow:
            player = await uow.players.get_by_id("p")
            service = PartTimeJobService(uow.players, uow.part_time_jobs, uow.job_locations, uow.player_job_stats)
            return await service.complete_job(player)

    for _ in range(2):
        with pytest.raises(InventoryCapacityError):
            await complete()
        async with safe_session(factory) as session:
            job = (await session.execute(select(PartTimeJob))).scalar_one()
            stats = (await session.execute(select(PlayerJobStats))).scalar_one()
            assert job.is_working and job.completed_time is None
            assert job.total_reward == 0
            assert stats.job_proficiency == {}
            assert stats.total_jobs_completed == stats.total_earnings == 0
            assert (await session.get(Player, "p")).gold == 100
            assert await session.scalar(select(func.sum(ItemInstance.quantity))) == 100

    # 腾出背包后领取，再次点击不得重复付钱或发放物品。
    async with safe_session(factory) as session:
        await session.execute(delete(ItemInstance))
    success, _, result = await complete()
    assert success
    assert not (await complete())[0]
    async with safe_session(factory) as session:
        assert (await session.get(Player, "p")).gold == 100 + result["total_reward"]
        stats = (await session.execute(select(PlayerJobStats))).scalar_one()
        assert stats.total_jobs_completed == 1
        assert stats.job_proficiency["cashier"]["count"] == 1
        assert not (await session.execute(select(PartTimeJob))).scalar_one().is_working
        assert await session.scalar(select(func.sum(ItemInstance.quantity))) == 1


async def test_job_full_bag_rolls_back_then_retries_once(inventory_store, capacity, monkeypatch):
    await _check_job_retry(inventory_store, monkeypatch)


async def test_mysql_job_full_bag_rolls_back_then_retries_once(mysql_session_factory, capacity, monkeypatch):
    await _check_job_retry(mysql_session_factory, monkeypatch)


@pytest.mark.parametrize("seed_drop", [False, True])
async def test_harvest_full_bag_preserves_crops_and_partial_rewards(inventory_store, capacity, monkeypatch, seed_drop):
    import plugins.xiuxian_game.spirit_field.spirit_field_service as field_module

    service = SpiritFieldService()
    crop = SimpleNamespace(name="测试作物", harvest_item_id="heal_potion", seed_id="spirit_herb")
    monkeypatch.setattr(service.crop_manager, "get_crop", lambda crop_id: crop)
    monkeypatch.setattr(field_module.random, "random", lambda: 0 if seed_drop else 1)
    async with safe_session(inventory_store) as session:
        session.add(Player(id="p", uid=1, nickname="测试"))
        await session.flush()
        field = SpiritField(player_id="p")
        session.add(field)
        await session.flush()
        # 第一块装满唯一格子，第二块或返还的种子入包失败。
        for index in (1, 2):
            session.add(SpiritFieldPlot(
                field_id=field.id, plot_index=index, crop_id="test_crop", is_mature=True,
                yield_quantity=100, mature_at=datetime.now() - timedelta(minutes=1),
            ))
    with pytest.raises(InventoryCapacityError):
        async with UnitOfWork(inventory_store) as uow:
            await service.harvest(uow, "p")
    async with safe_session(inventory_store) as session:
        plots = (await session.execute(select(SpiritFieldPlot))).scalars().all()
        assert all(plot.crop_id == "test_crop" and plot.is_mature and plot.yield_quantity == 100 for plot in plots)
        assert (await session.execute(select(SpiritField))).scalar_one().total_harvested == 0
        assert await session.scalar(select(func.count()).select_from(ItemInstance)) == 0
    capacity.return_value = 4
    async with UnitOfWork(inventory_store) as uow:
        assert (await service.harvest(uow, "p"))[0]
    async with safe_session(inventory_store) as session:
        assert (await session.execute(select(SpiritField))).scalar_one().total_harvested == 200
        assert all(plot.crop_id is None for plot in (await session.execute(select(SpiritFieldPlot))).scalars())
        assert await session.scalar(select(func.sum(ItemInstance.quantity))) == (202 if seed_drop else 200)
