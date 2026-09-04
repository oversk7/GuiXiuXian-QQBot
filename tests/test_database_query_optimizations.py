from datetime import datetime
from types import SimpleNamespace

from plugins.xiuxian_game.fishing.service import FishingService
from plugins.xiuxian_game.infrastructure.repositories.fishing_record_repository import (
    FishingRecordRepository,
)
from plugins.xiuxian_game.models.auto_migrate import REQUIRED_INDEXES
from plugins.xiuxian_game.models.fishing_record import FishingRecord
from plugins.xiuxian_game.models.inventory import ItemInstance


class _Scalars:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)


class _Result:
    def __init__(self, *, scalar=None, row=None, values=()):
        self._scalar = scalar
        self._row = row
        self._values = values

    def scalar(self):
        return self._scalar

    def one(self):
        return self._row

    def scalars(self):
        return _Scalars(self._values)


class _QuerySession:
    def __init__(self, result):
        self.result = result
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return self.result


class _FishingRecordRepo:
    def __init__(self, last_time, today_count):
        self.last_time = last_time
        self.today_count = today_count
        self.last_time_calls = 0
        self.today_count_calls = 0

    async def get_last_fishing_time(self, player_id):
        self.last_time_calls += 1
        return self.last_time

    async def get_today_fishing_count(self, player_id):
        self.today_count_calls += 1
        return self.today_count

    async def get_player_fishing_stats(self, player_id):
        raise AssertionError("资格检查不应读取完整历史统计")


class _InventoryPlayer:
    def __init__(self, capacity=100):
        self.capacity = capacity
        self.capacity_calls = 0

    async def get_effective_inventory_capacity(self, session):
        self.capacity_calls += 1
        return self.capacity


class _InventorySession:
    def __init__(self, player, stacks):
        self.player = player
        self.stacks = stacks
        self.statements = []
        self.added = []
        self.deleted = []
        self.flush_calls = 0

    async def get(self, model, entity_id):
        return self.player

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(values=self.stacks)

    def add(self, entity):
        self.added.append(entity)

    async def delete(self, entity):
        self.deleted.append(entity)

    async def flush(self):
        self.flush_calls += 1


async def test_fishing_repository_stats_use_one_aggregate_query():
    session = _QuerySession(_Result(row=(12, 34, 5)))

    stats = await FishingRecordRepository(session).get_player_fishing_stats("player-1")

    assert stats == {
        "today_fishing_count": 5,
        "total_fishing_count": 12,
        "total_fish_caught": 34,
    }
    assert len(session.statements) == 1


async def test_today_fishing_count_uses_one_range_query():
    session = _QuerySession(_Result(scalar=5))

    count = await FishingRecordRepository(session).get_today_fishing_count("player-1")

    assert count == 5
    assert len(session.statements) == 1
    sql = str(session.statements[0])
    assert "fishing_record.player_id" in sql
    assert "fishing_record.fishing_time" in sql


async def test_legacy_fishing_stats_use_one_aggregate_query():
    session = _QuerySession(_Result(row=(12, 34, 5)))

    stats = await FishingRecord.get_player_fishing_stats(session, "player-1")

    assert stats == {
        "today_fishing_count": 5,
        "total_fishing_count": 12,
        "total_fish_caught": 34,
    }
    assert len(session.statements) == 1


async def test_fishing_cooldown_reuses_last_record_query():
    repo = _FishingRecordRepo(datetime.now(), today_count=0)
    service = FishingService(repo, SimpleNamespace(), SimpleNamespace())

    can_fish, reason = await service.can_fishing(SimpleNamespace(id="player-1"))

    assert can_fish is False
    assert reason.startswith("钓鱼冷却中")
    assert repo.last_time_calls == 1
    assert repo.today_count_calls == 0


async def test_fishing_daily_limit_uses_today_count_only():
    repo = _FishingRecordRepo(last_time=None, today_count=FishingService.DAILY_FISHING_LIMIT)
    service = FishingService(repo, SimpleNamespace(), SimpleNamespace())

    can_fish, reason = await service.can_fishing(SimpleNamespace(id="player-1"))

    assert can_fish is False
    assert reason.startswith("今日钓鱼次数已达上限")
    assert repo.last_time_calls == 1
    assert repo.today_count_calls == 1


async def test_add_fish_queries_only_target_stacks_once():
    player = _InventoryPlayer()
    stack = ItemInstance(id=1, player_id="player-1", item_id="arowana", quantity=90)
    session = _InventorySession(player, [stack])

    added = await ItemInstance.add_item(session, "player-1", "arowana", 15)

    assert added is True
    assert len(session.statements) == 1
    sql = str(session.statements[0])
    assert "inventory.item_id" in sql
    assert "inventory.extra_attrs" not in sql
    assert "inventory.gem_slots_data" not in sql
    assert player.capacity_calls == 0
    assert stack.quantity == 100
    assert any(item.item_id == "arowana" and item.quantity == 5 for item in session.added)


async def test_add_regular_item_reuses_inventory_query():
    player = _InventoryPlayer(capacity=100)
    stack = ItemInstance(id=1, player_id="player-1", item_id="heal_potion", quantity=90)
    session = _InventorySession(player, [stack])

    added = await ItemInstance.add_item(session, "player-1", "heal_potion", 15)

    assert added is True
    assert len(session.statements) == 1
    sql = str(session.statements[0])
    assert "inventory.extra_attrs" not in sql
    assert "inventory.gem_slots_data" not in sql
    assert player.capacity_calls == 1
    assert stack.quantity == 100
    assert any(item.item_id == "heal_potion" and item.quantity == 5 for item in session.added)


def test_hot_path_indexes_are_declared_and_migrated():
    inventory_indexes = {index.name for index in ItemInstance.__table__.indexes}
    fishing_indexes = {index.name for index in FishingRecord.__table__.indexes}
    migration_indexes = {
        (table_name, index_name, columns)
        for table_name, index_name, columns in REQUIRED_INDEXES
    }

    assert "ix_inventory_player_item" in inventory_indexes
    assert "ix_fishing_record_player_time" in fishing_indexes
    assert (
        "inventory",
        "ix_inventory_player_item",
        "player_id, item_id",
    ) in migration_indexes
    assert (
        "fishing_record",
        "ix_fishing_record_player_time",
        "player_id, fishing_time",
    ) in migration_indexes
