from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError

from plugins.xiuxian_game.infrastructure.locking import lock_row
from plugins.xiuxian_game.models.auto_migrate import REQUIRED_FIELDS
from plugins.xiuxian_game.models.bank_account import BankAccount
from plugins.xiuxian_game.models.guild import Guild
from plugins.xiuxian_game.models.inventory import ItemInstance
from plugins.xiuxian_game.models.player import Player
from tests.mysql_helpers import mysql_session_factory


@pytest.mark.parametrize("model,field,values", [
    (Player, "gold", {"id": "p", "uid": 1, "nickname": "甲", "gold": 100}),
    (BankAccount, "balance", {"player_id": "p", "balance": 100}),
    (Guild, "treasury", {"name": "测试公会", "president_id": "p", "treasury": 100}),
    (ItemInstance, "quantity", {"player_id": "p", "item_id": "yin_grass", "quantity": 100}),
])
async def test_stale_asset_write_cannot_overwrite_committed_change(mysql_session_factory, model, field, values):
    factory = mysql_session_factory
    async with factory() as setup:
        if model is not Player:
            setup.add(Player(id="p", uid=1, nickname="甲"))
            await setup.flush()
        entity = model(**values)
        setup.add(entity)
        await setup.commit()
        key = entity.player_id if model is BankAccount else entity.id

    async with factory() as first, factory() as second:
        current = await first.get(model, key)
        stale = await second.get(model, key)
        setattr(current, field, 80)
        await first.commit()
        setattr(stale, field, 110)
        with pytest.raises(StaleDataError):
            await second.commit()
        await second.rollback()

    async with factory() as check:
        assert getattr(await check.get(model, key), field) == 80


async def test_conflict_rolls_back_already_flushed_reward(mysql_session_factory):
    factory = mysql_session_factory
    async with factory() as setup:
        setup.add(Player(id="p", uid=1, nickname="甲", gold=100))
        await setup.commit()
    async with factory() as first, factory() as second:
        current = await first.get(Player, "p")
        stale = await second.get(Player, "p")
        current.gold = 80
        await first.commit()
        second.add(ItemInstance(player_id="p", item_id="yin_grass", quantity=1))
        await second.flush()
        stale.gold = 110
        with pytest.raises(StaleDataError):
            await second.commit()
        await second.rollback()
    async with factory() as check:
        assert (await check.get(Player, "p")).gold == 80
        assert not (await check.execute(select(ItemInstance))).scalars().all()


async def test_lock_refreshes_existing_repeatable_read_snapshot(mysql_session_factory):
    factory = mysql_session_factory
    async with factory() as setup:
        setup.add(Player(id="p", uid=1, nickname="甲", gold=100))
        await setup.commit()
    async with factory() as first, factory() as second:
        stale = await second.get(Player, "p")
        activity_time = datetime.now()
        stale.last_active_at = activity_time
        stale.last_group_openid = "current-group"
        current = await first.get(Player, "p")
        current.gold = 80
        await first.commit()
        locked = await lock_row(second, Player, "p")
        assert locked is stale
        assert locked.gold == 80
        assert locked.last_active_at == activity_time
        assert locked.last_group_openid == "current-group"
        locked.gold -= 30
        await second.commit()
    async with factory() as check:
        assert (await check.get(Player, "p")).gold == 50


def test_version_columns_are_in_automatic_migration():
    for table in ("player", "bank_account", "inventory", "guild"):
        assert "NOT NULL DEFAULT 1" in REQUIRED_FIELDS[table]["version_id"]
