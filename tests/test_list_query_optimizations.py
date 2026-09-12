from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.qq import Message
from nonebot.exception import FinishedException
from sqlalchemy import event, inspect
from sqlalchemy.dialects import mysql

from plugins.xiuxian_game.config import config
from plugins.xiuxian_game.guild import guild, guild_activity
from plugins.xiuxian_game.infrastructure.repositories.item_repository import ItemRepository
from plugins.xiuxian_game.item import equipment_commands as equipment
from plugins.xiuxian_game.item import inventory
from plugins.xiuxian_game.models.guild import Guild, GuildMember
from plugins.xiuxian_game.models.inventory import ItemInstance, ItemType
from plugins.xiuxian_game.models.player import Player
from tests.mysql_helpers import mysql_session_factory


class Result:
    def __init__(self, rows=(), total=0):
        self.rows = rows
        self.total = total

    def all(self):
        return list(self.rows)

    def scalars(self):
        return self

    def scalar_one(self):
        return self.total


class QuerySession:
    def __init__(self, *results):
        self.results = iter(results)
        self.statements = []
        self.active = False

    async def execute(self, statement):
        self.statements.append(statement)
        return next(self.results)

    @asynccontextmanager
    async def scope(self):
        self.active = True
        try:
            yield self
        finally:
            self.active = False


def sql(statement):
    return str(statement.compile(dialect=mysql.dialect(), compile_kwargs={"literal_binds": True}))


def capture_finish(monkeypatch, module, matcher, session):
    async def finish(message):
        assert not session.active
        raise FinishedException

    mock = AsyncMock(side_effect=finish)
    monkeypatch.setattr(matcher, "finish", mock)
    monkeypatch.setattr(module, "build_markdown", lambda text: text)
    monkeypatch.setattr(module, "cmd", lambda label, command=None: f"{label} [{command or label}]")
    return mock


async def test_equipment_display_queries_are_bounded_and_narrow():
    session = QuerySession(Result(total=47), Result(), Result())
    repo = ItemRepository(session)
    assert await repo.count_equipment_for_numbering("p", ["furnace"]) == 47
    await repo.get_equipment_page_for_numbering("p", ["furnace"], offset=20, limit=20)
    await repo.get_equipped_for_slot_display("p", ["furnace"])
    count_sql, page_sql, equipped_sql = map(sql, session.statements)
    assert len(session.statements) == 3
    assert "count(*)" in count_sql
    assert "ORDER BY inventory.id ASC" in page_sql
    assert "LIMIT 20, 20" in page_sql
    assert "inventory.extra_attrs" in page_sql
    assert "inventory.version_id" not in page_sql
    assert "inventory.quantity" not in page_sql
    assert "inventory.equipped = true" in equipped_sql
    assert "inventory.extra_attrs" not in equipped_sql
    assert "inventory.gem_slots_data" not in equipped_sql
    assert "inventory.version_id" not in equipped_sql


@pytest.mark.parametrize("page,total,expected_numbers", [(1, 5, [1, 2]), (2, 5, [3, 4]), (99, 5, [5]), (1, 0, [])])
async def test_equipment_handler_preserves_global_numbers_and_releases_session(
    monkeypatch, page, total, expected_numbers,
):
    items = [ItemInstance(
        id=number * 100, item_id="furnace", equipped=False,
        upgrade_level=0, durability=number, extra_attrs={}, gem_slots_data={},
    ) for number in expected_numbers]
    session = QuerySession(Result(total=total), Result(items), Result())
    monkeypatch.setattr(equipment, "safe_session", session.scope)
    monkeypatch.setattr(equipment, "require_player", AsyncMock(return_value=SimpleNamespace(id="p")))
    monkeypatch.setitem(config.game_config["game"], "inventory_page_size", 2)
    finish = capture_finish(monkeypatch, equipment, equipment.list_equipment, session)
    with pytest.raises(FinishedException):
        await equipment.list_equipment.handlers[0].call(event=SimpleNamespace(), args=Message(str(page)))
    text = finish.call_args.args[0]
    lines = [line for line in text.splitlines() if "[装备详情 " in line]
    assert len(lines) == len(expected_numbers)
    for line, number in zip(lines, expected_numbers):
        assert f"[装备详情 {number}]" in line
    if not total:
        assert text == "🎒 你的装备栏空空如也"
    assert len(session.statements) == 3
    expected_offset = expected_numbers[0] - 1 if expected_numbers else 0
    assert f"LIMIT {expected_offset}, 2" in sql(session.statements[1])


async def test_inventory_aggregate_query_preserves_row_usage_without_json():
    session = QuerySession(Result([
        SimpleNamespace(item_id="heal_potion", quantity=210, used_slots=3),
        SimpleNamespace(item_id="affix_reroll_stone", quantity=8, used_slots=2),
    ]))
    items, usage = await inventory._query_inventory_totals(session, "p")
    assert [(item.item_id, item.quantity) for item in items] == [("heal_potion", 210), ("affix_reroll_stone", 8)]
    assert usage == 5
    assert len(session.statements) == 1
    statement = sql(session.statements[0])
    assert "sum(inventory.quantity)" in statement
    assert "count(*)" in statement
    assert "GROUP BY inventory.item_id" in statement
    assert "inventory.quantity > 0" in statement
    assert "NOT IN" in statement
    assert "inventory.extra_attrs" not in statement
    assert "inventory.gem_slots_data" not in statement
    assert "inventory.version_id" not in statement


@pytest.mark.parametrize("compact,quantities", [(True, [210, 8]), (False, [100, 100, 10, 8])])
async def test_inventory_handler_keeps_sort_stacks_and_capacity(monkeypatch, compact, quantities):
    from plugins.xiuxian_game import platform_utils, queries

    session = QuerySession(Result([
        SimpleNamespace(item_id="affix_reroll_stone", quantity=8, used_slots=2),
        SimpleNamespace(item_id="heal_potion", quantity=210, used_slots=3),
    ]))
    player = SimpleNamespace(
        id="p", inventory_capacity=100, inventory_compact=compact,
        get_effective_inventory_capacity=AsyncMock(return_value=120),
    )
    monkeypatch.setattr(inventory, "safe_session", session.scope)
    monkeypatch.setattr(queries, "readonly_session", session.scope)
    monkeypatch.setattr(platform_utils, "require_player", AsyncMock(return_value=player))
    finish = capture_finish(monkeypatch, inventory, inventory.inventory_cmd, session)
    captured = []

    def formatter(items, page, page_size, capacity_info, **kwargs):
        captured.append((items, page, capacity_info, kwargs))
        return "inventory"

    monkeypatch.setattr(inventory, "_format_inventory_md", formatter)
    with pytest.raises(FinishedException):
        await inventory.handle_inventory(SimpleNamespace(), Message("99"))
    items, page, capacity, kwargs = captured[0]
    assert [item.quantity for item in items] == quantities
    assert items[0].item_id == "heal_potion"
    assert capacity == "📦 容量：5/120 (💳+20)"
    assert kwargs["compact"] == compact
    assert page == 1
    assert len(session.statements) == 1
    finish.assert_called_once()


async def test_guild_page_joins_display_data_in_one_query():
    session = QuerySession(Result())
    await guild_activity.get_guilds_sorted_by_activity(session, server_id=2, page=3)
    assert len(session.statements) == 1
    statement = sql(session.statements[0])
    assert "LIMIT 40, 20" in statement
    assert "guild.server_id = 2" in statement
    assert "count(guild_member.id)" in statement
    assert "player.nickname AS president_name" in statement
    assert "player.uid AS president_uid" in statement
    assert "greatest(" in statement
    assert "guild.level DESC, guild.id" in statement
    assert "guild.notice" not in statement
    assert "player.version_id" not in statement


async def test_guild_handler_clamps_page_and_keeps_daily_check(monkeypatch):
    row = SimpleNamespace(id=21, name="测试公会", level=2, treasury=1000,
                          member_count=3, president_name="会长", president_uid=123)
    session = QuerySession(Result(total=21), Result([row]))
    monkeypatch.setattr(guild, "safe_session", session.scope)
    monkeypatch.setattr(guild, "get_unified_player", AsyncMock(return_value=SimpleNamespace(server_id=2)))
    check = AsyncMock(return_value=["活跃度检查记录"])
    monkeypatch.setattr(guild_activity, "maybe_run_activity_check", check)
    finish = capture_finish(monkeypatch, guild, guild.list_guilds_cmd, session)
    with pytest.raises(FinishedException):
        await guild.handle_list_guilds(SimpleNamespace(), Message("99"))
    text = finish.call_args.args[0]
    assert "第**2**/2页 | 共**21**个公会" in text
    assert "3/15人" in text
    assert "[面板 123]" in text
    assert "活跃度检查记录" in text
    assert len(session.statements) == 2
    assert "LIMIT 20, 20" in sql(session.statements[1])
    check.assert_awaited_once_with(session, server_id=2)


async def test_mysql_equipment_pages_and_inventory_aggregation(mysql_session_factory):
    factory = mysql_session_factory
    async with factory() as session, session.begin():
        session.add(Player(id="list-player", uid=990001, nickname="列表测试"))
        await session.flush()
        session.add_all([
            ItemInstance(id=i, player_id="list-player", item_id="furnace" if i % 2 else "black_envelope",
                         quantity=1, equipped=i == 41, extra_attrs={"_player_locked": i == 21},
                         gem_slots_data={})
            for i in range(1, 46)
        ])
        for index, quantity in enumerate([100, 100, 10, 0], 100):
            session.add(ItemInstance(id=index, player_id="list-player", item_id="heal_potion", quantity=quantity))
        inscription_id = next(iid for iid, tpl in config.items_config["by_id"].items() if tpl.type == ItemType.INSCRIPTION)
        session.add_all([
            ItemInstance(id=110, player_id="list-player", item_id="arowana", quantity=20),
            ItemInstance(id=111, player_id="list-player", item_id=inscription_id, quantity=1),
        ])
    statements = []
    async with factory() as session:
        def record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        engine = session.bind.sync_engine
        event.listen(engine, "before_cursor_execute", record)
        try:
            repo = ItemRepository(session)
            assert await repo.count_equipment_for_numbering("list-player", equipment.EQUIP_ITEM_IDS) == 45
            page = await repo.get_equipment_page_for_numbering("list-player", equipment.EQUIP_ITEM_IDS, offset=20, limit=20)
            assert [item.id for item in page] == list(range(21, 41))
            assert "quantity" in inspect(page[0]).unloaded
            equipped = await repo.get_equipped_for_slot_display("list-player", equipment.EQUIP_ITEM_IDS)
            assert [item.id for item in equipped] == [41]
            assert "extra_attrs" in inspect(equipped[0]).unloaded
            assert len(statements) == 3
            items, usage = await inventory._query_inventory_totals(session, "list-player")
            assert [(item.item_id, item.quantity) for item in items] == [("heal_potion", 210)]
            assert usage == 3
            assert len(statements) == 4
            assert "extra_attrs" not in statements[-1]
        finally:
            event.remove(engine, "before_cursor_execute", record)


async def test_mysql_guild_activity_pages_counts_and_presidents(mysql_session_factory):
    factory = mysql_session_factory
    now = datetime(2026, 7, 1)
    async with factory() as session, session.begin():
        for i in range(1, 24):
            session.add(Player(id=f"guild-player-{i}", uid=991000 + i, nickname=f"会长{i}",
                               created_at=now - timedelta(days=100), last_sign=now + timedelta(days=i),
                               last_active_at=now))
            session.add(Guild(id=i, name=f"公会{i}", president_id=f"guild-player-{i}",
                              server_id=1 if i <= 22 else 2, level=1, treasury=i))
        session.add(Guild(id=24, name="空公会", president_id="missing", server_id=1, level=99))
        await session.flush()
        session.add_all([GuildMember(guild_id=i, player_id=f"guild-player-{i}") for i in range(1, 24)])
        session.add(GuildMember(guild_id=22, player_id="missing-member"))
    async with factory() as session:
        rows = await guild_activity.get_guilds_sorted_by_activity(session, page=1)
        assert len(rows) == 20
        assert [row.id for row in rows] == list(range(22, 2, -1))
        assert rows[0].member_count == 2
        assert rows[0].president_name == "会长22"
        assert rows[0].president_uid == 991022
        rows = await guild_activity.get_guilds_sorted_by_activity(session, page=2)
        assert [row.id for row in rows] == [2, 1, 24]
        assert rows[-1].member_count == 0
        assert rows[-1].president_uid is None
        assert rows[-1].latest_active is None
