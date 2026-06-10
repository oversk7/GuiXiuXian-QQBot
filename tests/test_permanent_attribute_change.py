"""永久属性写入口（apply_permanent_change）原子性测试

写入口必须一次完成四件事：改字段、记账、装备重算、hp/mp 收口。
任何一步缺失都会导致账实漂移（见 scripts/check_attribute_consistency.py）。
"""
import asyncio
from types import SimpleNamespace

import plugins.xiuxian_game.domain.attributes.permanent_change as pc
from plugins.xiuxian_game.item.equipment_service import EquipmentService
from plugins.xiuxian_game.models.elixir_usage import ElixirUsageLog


class _FakeLog:
    def __init__(self):
        self.quantity = 0
        self.changes = []

    def record_changes(self, changes):
        self.changes.append(dict(changes))


def _make_player():
    return SimpleNamespace(
        id="P1", attack=100, max_hp=200, max_mp=50,
        hp=200, mp=50, defense=10,
    )


def _patch(monkeypatch, fake_log, recalc_calls):
    async def fake_recalc(self, player, equipped_items=None):
        recalc_calls.append(player)

    async def fake_get_or_create(cls, session, player_id, item_id, use_date=None):
        fake_log.item_id = item_id
        return fake_log

    monkeypatch.setattr(EquipmentService, "recalc_equipment_attributes", fake_recalc)
    monkeypatch.setattr(
        ElixirUsageLog, "get_or_create_log", classmethod(fake_get_or_create)
    )


def test_apply_change_mutates_records_recalcs_and_clamps(monkeypatch):
    fake_log, recalc_calls = _FakeLog(), []
    _patch(monkeypatch, fake_log, recalc_calls)
    player = _make_player()

    actual = asyncio.run(pc.apply_permanent_change(
        object(), player, {"attack": 10, "max_hp": -50, "unknown_attr": 5, "defense": 0},
        ledger_item_id="test_elixir", quantity=2,
    ))

    # 改字段：0 值与未知字段被忽略
    assert actual == {"attack": 10, "max_hp": -50}
    assert player.attack == 110
    assert player.max_hp == 150
    # hp 收口到新上限
    assert player.hp == 150
    # 装备重算恰好一次
    assert recalc_calls == [player]
    # 记账：数量与变更都进了账本
    assert fake_log.item_id == "test_elixir"
    assert fake_log.quantity == 2
    assert fake_log.changes == [{"attack": 10, "max_hp": -50}]


def test_noop_change_skips_recalc_and_ledger(monkeypatch):
    fake_log, recalc_calls = _FakeLog(), []
    _patch(monkeypatch, fake_log, recalc_calls)
    player = _make_player()

    actual = asyncio.run(pc.apply_permanent_change(
        object(), player, {"unknown_attr": 5, "attack": 0},
        ledger_item_id="test_elixir",
    ))

    assert actual == {}
    assert player.attack == 100
    assert recalc_calls == []
    assert fake_log.quantity == 0
