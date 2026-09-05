from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.qq import Message
from nonebot.exception import FinishedException
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from plugins.xiuxian_game.config import config
from plugins.xiuxian_game.infrastructure.repositories.item_repository import ItemRepository
from plugins.xiuxian_game.item import decompose_commands as decompose
from plugins.xiuxian_game.item import equipment_commands as equipment
from plugins.xiuxian_game.item import equipment_upgrade_commands as upgrade
from plugins.xiuxian_game.item.equipment_service import EQUIP_ITEM_IDS
from plugins.xiuxian_game.models import db
from plugins.xiuxian_game.models.inventory import ItemInstance
from plugins.xiuxian_game.models.player import Player


EXPECTED_IDS = [100, 200, 300, 400, 500]


@pytest.fixture
async def numbering_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    statements = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute", retval=True)
    def force_composite_index(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and "FROM inventory" in statement:
            statement = statement.replace(
                "FROM inventory", "FROM inventory INDEXED BY ix_inventory_player_item"
            )
            statements.append(statement)
        return statement, parameters

    try:
        async with engine.begin() as conn:
            await conn.run_sync(db.Base.metadata.create_all)
        monkeypatch.setattr(
            db,
            "AsyncSessionLocal",
            sessionmaker(engine, class_=AsyncSession, expire_on_commit=False),
        )
        async with db.safe_session() as session:
            session.add_all([
                Player(id="numbering-player", uid=99001, nickname="Numbering"),
                Player(id="other-player", uid=99002, nickname="Other"),
            ])
            for item_id, template, equipped, level, extra in [
                (500, "black_envelope", False, 0, {}),
                (300, "furnace", True, 0, {}),
                (100, "furnace", False, 0, {}),
                (400, "black_envelope", False, 10, {}),
                (200, "black_envelope", False, 0, {"_player_locked": True}),
            ]:
                session.add(ItemInstance(
                    id=item_id,
                    player_id="numbering-player",
                    item_id=template,
                    quantity=1,
                    durability=item_id // 10,
                    equipped=equipped,
                    upgrade_level=level,
                    extra_attrs=extra,
                    gem_slots_data={},
                ))
            session.add_all([
                ItemInstance(id=50, player_id="other-player", item_id="black_envelope", quantity=1),
                ItemInstance(id=150, player_id="numbering-player", item_id="heal_potion", quantity=10),
                ItemInstance(id=160, player_id="numbering-player", item_id="unknown-template", quantity=1),
            ])
        yield statements
    finally:
        await engine.dispose()


def _capture_command(monkeypatch, module, matcher):
    async def require_player(session, event, command):
        return await session.get(Player, "numbering-player")

    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(module, "require_player", require_player)
    monkeypatch.setattr(matcher, "finish", finish)
    monkeypatch.setattr(module, "build_markdown", lambda text: text)
    monkeypatch.setattr(module, "cmd", lambda label, command=None: f"{label} [{command or label}]")
    return finish


async def test_numbering_does_not_follow_composite_index_order(numbering_db):
    async with db.safe_session() as session:
        unordered = (await session.execute(
            select(ItemInstance).where(
                ItemInstance.player_id == "numbering-player",
                ItemInstance.item_id.in_(EQUIP_ITEM_IDS),
            )
        )).scalars().all()
        assert [item.id for item in unordered] != EXPECTED_IDS

        ordered = await ItemRepository(session).get_equipment_for_numbering(
            "numbering-player", EQUIP_ITEM_IDS
        )
        assert [item.id for item in ordered] == EXPECTED_IDS
        assert "ORDER BY inventory.id ASC" in numbering_db[-1]
        assert "INDEXED BY ix_inventory_player_item" in numbering_db[-1]


@pytest.mark.parametrize("page,expected_ids", [(1, [100, 200]), (2, [300, 400]), (3, [500])])
async def test_equipment_pages_match_general_and_decompose_targets(
    numbering_db, monkeypatch, page, expected_ids
):
    monkeypatch.setitem(config.game_config["game"], "inventory_page_size", 2)
    finish = _capture_command(monkeypatch, equipment, equipment.list_equipment)

    with pytest.raises(FinishedException):
        await equipment.list_equipment.handlers[0].call(
            event=SimpleNamespace(), args=Message(str(page))
        )

    text = str(finish.call_args.args[0])
    lines = [line for line in text.splitlines() if "[装备详情 " in line]
    assert len(lines) == len(expected_ids)
    async with db.safe_session() as session:
        for offset, (line, instance_id) in enumerate(zip(lines, expected_ids), 1):
            short_id = (page - 1) * 2 + offset
            assert f"[装备详情 {short_id}]" in line
            assert f"🛠️{instance_id // 10}/" in line
            general = await equipment.find_equipment_by_input(
                session, "numbering-player", str(short_id)
            )
            destructive = await decompose._find_equipment_by_index(
                session, "numbering-player", short_id
            )
            assert general.id == destructive.id == instance_id


async def test_upgrade_list_keeps_full_equipment_numbering(numbering_db, monkeypatch):
    finish = _capture_command(monkeypatch, upgrade, upgrade.upgrade_list_cmd)

    with pytest.raises(FinishedException):
        await upgrade.upgrade_list_cmd.handlers[0].call(event=SimpleNamespace())

    text = str(finish.call_args.args[0])
    numbers = [int(line.split(" │ ")[0][1:]) for line in text.splitlines() if line.startswith("🆔")]
    assert numbers == [1, 2, 5]
    assert len(numbering_db) == 1


@pytest.mark.parametrize("short_id,instance_id", [(1, 100), (5, 500)])
async def test_decompose_deletes_only_the_displayed_equipment(
    numbering_db, monkeypatch, short_id, instance_id
):
    _capture_command(monkeypatch, decompose, decompose.decompose_cmd)
    monkeypatch.setattr(
        decompose,
        "calculate_decompose_yields",
        lambda item, rng: SimpleNamespace(reroll_stones=0, fragment_count=0),
    )

    with pytest.raises(FinishedException):
        await decompose.handle_decompose(event=SimpleNamespace(), args=Message(str(short_id)))

    async with db.safe_session() as session:
        all_ids = set((await session.execute(select(ItemInstance.id))).scalars().all())
        assert all_ids == (set(EXPECTED_IDS) | {50, 150, 160}) - {instance_id}
        refreshed = await ItemRepository(session).get_equipment_for_numbering(
            "numbering-player", EQUIP_ITEM_IDS
        )
        for number, item in enumerate(refreshed, 1):
            found = await decompose._find_equipment_by_index(session, "numbering-player", number)
            assert found.id == item.id


@pytest.mark.parametrize("short_id", [0, -1, 6, 100])
async def test_decompose_rejects_invalid_short_ids(numbering_db, short_id):
    async with db.safe_session() as session:
        assert await decompose._find_equipment_by_index(session, "numbering-player", short_id) is None


async def test_general_lookup_preserves_raw_id_and_owner_checks(numbering_db):
    async with db.safe_session() as session:
        own = await equipment.find_equipment_by_input(session, "numbering-player", "100")
        assert own.id == 100
        assert await equipment.find_equipment_by_input(session, "numbering-player", "50") is None
        assert await equipment.find_equipment_by_input(session, "numbering-player", "150") is None
