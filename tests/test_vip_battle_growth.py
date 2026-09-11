"""VIP 成长的来源、场景差异、每日额度和事务一致性。"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plugins.xiuxian_game.item import vip_battle_growth_service as growth
from plugins.xiuxian_game.item import vip_huihai_xinyuan_skill as huihai
from plugins.xiuxian_game.models import db
from plugins.xiuxian_game.models.inventory import ItemInstance
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.models.vip_equipment_bonus import VIPEquipmentBonus


class Clock:
    today = datetime(2026, 9, 11, 12)

    @classmethod
    def now(cls):
        return cls.today


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(Clock, "today", datetime(2026, 9, 11, 12))
    monkeypatch.setattr(growth, "datetime", Clock)
    monkeypatch.setattr(growth.random, "choice", lambda values: "defense")


def player(player_id="P1"):
    return SimpleNamespace(
        **dict(Player.INIT_ATTRS, id=player_id, nickname=player_id, hp=10, mp=10),
    )


def item(item_id, player_id="P1", **extra):
    return ItemInstance(
        item_id=item_id, player_id=player_id, equipped=True, upgrade_level=3,
        durability=99, gem_slots_data={"0": "ruby_lv1"},
        extra_attrs={"_persist_bonus": {"attack": 37}, "_player_locked": True, **extra},
    )


def effect(item_id, effect_type, value=2, **extra):
    return dict(source_item_id=item_id, type=effect_type, value=value, **extra)


def make_service(items):
    records = {}

    async def add_bonus(player_id, attribute, value):
        record = records.setdefault(player_id, VIPEquipmentBonus(player_id=player_id, bonus_attrs={}))
        record.add_bonus(attribute, value)
        return record

    item_repo = SimpleNamespace(
        get_equipped_items=AsyncMock(side_effect=lambda pid: [
            entry for entry in items if entry.player_id == pid and entry.equipped
        ]),
        update=AsyncMock(),
    )
    service = growth.VIPBattleGrowthService(
        item_repo, SimpleNamespace(update=AsyncMock()),
        SimpleNamespace(add_bonus=AsyncMock(side_effect=add_bonus)),
    )
    return service, records


async def test_simultaneous_equipment_keeps_independent_growth_and_snapshots():
    owner = player()
    items = [item(key) for key in (
        growth.BLADE_ID, "vip_gui_yu", "vip_chrono_watch", "vip_ghost_dice",
    )]
    service, records = make_service(items)
    before = vars(owner).copy()
    messages = await service.apply_pve_effects(owner, [
        effect(growth.BLADE_ID, "gain_random_attr", 40, attr="attack"),
        effect(growth.BLADE_ID, "gain_max_hp"),
        effect("vip_gui_yu", "gain_agility"),
        effect("vip_chrono_watch", "gain_max_hp"),
        effect("vip_chrono_watch", "gain_attack", description="骰相"),
        effect("vip_ghost_dice", "gain_attack", description="另一个技能名"),
    ])

    expected = {"attack": 44, "max_hp": 12, "agility": 2}
    assert records[owner.id].get_total_bonus() == expected
    for attribute in Player.INIT_ATTRS:
        assert getattr(owner, attribute) == before[attribute] + expected.get(attribute, 0)
    assert (owner.hp, owner.mp) == (10, 10)
    assert len(messages) == 6
    assert items[0].extra_attrs["blade_kill_cnt"] == 1
    assert items[1].extra_attrs["gy_kill_cnt"] == 1
    assert items[2].extra_attrs["cw_hp_cnt"] == 1
    assert items[2].extra_attrs["cw_atk_cnt"] == 1
    assert items[3].extra_attrs["dice_atk_cnt"] == 1
    for entry in items:
        assert entry.extra_attrs["_persist_bonus"] == {"attack": 37}
        assert entry.extra_attrs["_player_locked"] is True
        assert entry.gem_slots_data == {"0": "ruby_lv1"}
        assert (entry.upgrade_level, entry.durability, entry.equipped) == (3, 99, True)


@pytest.mark.parametrize("source", [growth.BLADE_ID, "vip_chrono_watch"])
async def test_same_effect_type_only_credits_its_source(source):
    owner = player()
    blade, watch = item(growth.BLADE_ID), item("vip_chrono_watch")
    service, records = make_service([blade, watch])
    await service.apply_pve_effects(owner, [effect(source, "gain_max_hp")])

    assert records[owner.id].get_total_bonus() == {"max_hp": 6}
    credited, untouched = (blade, watch) if source == growth.BLADE_ID else (watch, blade)
    prefix = "blade_kill" if source == growth.BLADE_ID else "cw_hp"
    assert credited.extra_attrs[f"{prefix}_cnt"] == 1
    assert untouched.extra_attrs == {"_persist_bonus": {"attack": 37}, "_player_locked": True}


async def test_unequipped_or_foreign_effect_does_not_grant():
    owner = player()
    dice = item("vip_ghost_dice")
    dice.equipped = False
    service, records = make_service([dice, item("vip_chrono_watch")])
    assert await service.apply_pve_effects(owner, [
        effect("vip_ghost_dice", "gain_attack"),
        effect("other_item", "gain_attack", description="骰相"),
    ]) == []
    assert not records


async def test_daily_limits_reset_independently_and_random_awards_once():
    owner = player()
    blade = item(growth.BLADE_ID, blade_rand_day="20260910")
    watch = item("vip_chrono_watch", cw_hp_day="20260911", cw_hp_cnt=19,
                 cw_atk_day="20260911", cw_atk_cnt=20)
    service, records = make_service([blade, watch])
    effects = [
        effect(growth.BLADE_ID, "gain_random_attr", 40, attr="luck"),
        effect("vip_chrono_watch", "gain_max_hp"),
        effect("vip_chrono_watch", "gain_attack"),
    ]
    await service.apply_pve_effects(owner, effects)
    await service.apply_pve_effects(owner, effects)
    assert records[owner.id].get_total_bonus() == {"luck": 40, "max_hp": 6}
    assert watch.extra_attrs["cw_hp_cnt"] == watch.extra_attrs["cw_atk_cnt"] == 20

    Clock.today = datetime(2026, 9, 12)
    await service.apply_pve_effects(owner, effects)
    assert records[owner.id].get_total_bonus() == {"luck": 80, "max_hp": 12, "attack": 2}
    assert watch.extra_attrs["cw_hp_cnt"] == watch.extra_attrs["cw_atk_cnt"] == 1
    assert blade.extra_attrs["blade_rand_day"] == "20260912"


@pytest.mark.parametrize("victory", [True, False])
async def test_pvp_preserves_both_daily_rewards_and_winner_loser_rules(monkeypatch, victory):
    attacker, target = player("A"), player("B")
    items = [item(key, pid) for pid in ("A", "B") for key in (
        growth.BLADE_ID, "vip_gui_yu", "vip_robe_jingyuan_legacy",
    )]
    service, records = make_service(items)
    monkeypatch.setattr(growth, "_service", lambda session: service)
    hh_kill = AsyncMock(return_value="慧海成长")
    monkeypatch.setattr(huihai, "apply_kill_max_mp", hh_kill)

    messages = await growth.settle_pvp_growth(object(), attacker, target, victory=victory)

    winner, loser = (attacker, target) if victory else (target, attacker)
    assert records[winner.id].get_total_bonus() == {"defense": 40, "max_mp": 2, "agility": 2}
    assert records[loser.id].get_total_bonus() == {"defense": 40, "attack": 2}
    assert winner.max_hp == loser.max_hp == Player.INIT_ATTRS["max_hp"]
    assert "A 今日首战恩赐" in messages[0]
    assert "B 今日首战恩赐" in messages[1]
    assert "慧海成长" == messages[-2]
    hh_kill.assert_awaited_once()
    assert hh_kill.call_args.args[1] is winner


async def test_pve_and_pvp_share_blade_daily_limit():
    owner = player()
    blade = item(growth.BLADE_ID, blade_kill_day="20260911", blade_kill_cnt=19)
    service, records = make_service([blade])
    await service.apply_pve_effects(owner, [effect(growth.BLADE_ID, "gain_max_hp")])
    messages = await service.apply_pvp_kill(owner)
    assert records[owner.id].get_total_bonus() == {"max_hp": 6}
    assert blade.extra_attrs["blade_kill_cnt"] == 20
    assert "今日已达上限" in messages[0]


async def test_dungeon_defeat_preserves_existing_growth_branch():
    owner = player()
    blade = item(growth.BLADE_ID)
    robe = item("vip_robe_jingyuanzhiyi")
    service, records = make_service([blade, robe])
    await service.apply_dungeon_defeat(owner)
    assert records[owner.id].get_total_bonus() == {"defense": 40, "attack": 2, "max_hp": 6}
    assert robe.extra_attrs["robe_die_cnt"] == blade.extra_attrs["blade_kill_cnt"] == 1


async def test_pve_huihai_hook_runs_without_triggered_effects(monkeypatch):
    service, _ = make_service([])
    monkeypatch.setattr(growth, "_service", lambda session: service)
    hh_kill = AsyncMock(return_value="慧海成长")
    monkeypatch.setattr(huihai, "apply_kill_max_mp", hh_kill)
    assert await growth.settle_pve_victory(object(), player(), []) == ["慧海成长"]
    hh_kill.assert_awaited_once()


@pytest.fixture
async def growth_database(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: db.Base.metadata.create_all(conn, tables=[
            Player.__table__, ItemInstance.__table__, VIPEquipmentBonus.__table__,
        ]))
    monkeypatch.setattr(db, "AsyncSessionLocal", async_sessionmaker(engine, expire_on_commit=False))
    async with db.safe_session() as session:
        session.add(Player(id="P1", uid=1, nickname="测试", attack=100))
        session.add(item("vip_chrono_watch"))
    try:
        yield
    finally:
        await engine.dispose()


async def test_growth_persists_player_counter_and_vip_ledger_together(growth_database):
    async with db.safe_session() as session:
        owner = await session.get(Player, "P1")
        await growth.settle_pve_victory(session, owner, [effect("vip_chrono_watch", "gain_attack")])
    async with db.safe_session() as session:
        owner = await session.get(Player, "P1")
        watch = (await growth.ItemRepository(session).get_equipped_items(owner.id))[0]
        record = await growth.VIPEquipmentBonusRepository(session).get_by_player_id(owner.id)
        assert owner.attack == 102
        assert record.get_total_bonus() == {"attack": 2}
        assert watch.extra_attrs["cw_atk_cnt"] == 1
        assert watch.extra_attrs["cw_atk_day"] == "20260911"
        assert watch.extra_attrs["_persist_bonus"] == {"attack": 37}


async def test_growth_failure_propagates_and_rolls_back(growth_database, monkeypatch):
    monkeypatch.setattr(growth.PlayerRepository, "update", AsyncMock(side_effect=RuntimeError("写入失败")))
    with pytest.raises(RuntimeError, match="写入失败"):
        async with db.safe_session() as session:
            owner = await session.get(Player, "P1")
            await growth.settle_pve_victory(session, owner, [effect("vip_chrono_watch", "gain_attack")])
    async with db.safe_session() as session:
        owner = await session.get(Player, "P1")
        watch = (await growth.ItemRepository(session).get_equipped_items(owner.id))[0]
        record = await growth.VIPEquipmentBonusRepository(session).get_by_player_id(owner.id)
        assert owner.attack == 100
        assert record is None
        assert "cw_atk_cnt" not in watch.extra_attrs
