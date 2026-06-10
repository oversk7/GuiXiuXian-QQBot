"""全量真源（Player.get_effective_attributes）的加成键直通测试

历史教训：旧 v2 读取框架因 buff 字段名错位（critical_rate vs crit_rate），
战斗属性的临时 buff 加成被静默丢弃。真源必须按 Player 字段名直通累加，
任何中间映射层都禁止再引入（读取规范见 coding-conventions.md §6.3）。
"""
import asyncio
from types import SimpleNamespace

from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.models.temporary_buff import TemporaryBuff
import plugins.xiuxian_game.domain.attributes.attribute_sources.pet_source as pet_source_module


def _make_player():
    fields = dict(Player.INIT_ATTRS)
    fields.update(id="P1", hp=20, mp=20)
    return SimpleNamespace(**fields)


def _patch(monkeypatch, buff_bonuses, pet_bonuses):
    async def fake_buffs(cls, session, player_id):
        return dict(buff_bonuses)

    class _FakePetSource:
        async def calculate_full_bonus(self, player, session):
            return dict(pet_bonuses)

    monkeypatch.setattr(
        TemporaryBuff, "get_total_attribute_bonuses", classmethod(fake_buffs)
    )
    monkeypatch.setattr(pet_source_module, "_instance", _FakePetSource())


def test_buff_and_pet_battle_attrs_pass_through(monkeypatch):
    _patch(
        monkeypatch,
        buff_bonuses={"critical_rate": 10, "combo_rate": 7, "max_hp": 50, "attack": 3},
        pet_bonuses={"penetration_rate": 4, "attack": 2},
    )
    player = _make_player()

    attrs = asyncio.run(Player.get_effective_attributes(player, session=object()))

    init = Player.INIT_ATTRS
    # 战斗属性的 buff/宠物加成必须直通（v2 框架曾在这里丢失）
    assert attrs["critical_rate"] == init["critical_rate"] + 10
    assert attrs["combo_rate"] == init["combo_rate"] + 7
    assert attrs["penetration_rate"] == init["penetration_rate"] + 4
    # 六维与多来源叠加
    assert attrs["max_hp"] == init["max_hp"] + 50
    assert attrs["attack"] == init["attack"] + 3 + 2
    # 未被加成的字段保持原值
    assert attrs["dodge_rate"] == init["dodge_rate"]


def test_no_session_returns_raw_fields(monkeypatch):
    _patch(monkeypatch, buff_bonuses={"attack": 99}, pet_bonuses={"attack": 99})
    player = _make_player()

    attrs = asyncio.run(Player.get_effective_attributes(player, session=None))

    # 无 session 时不查 buff/宠物，返回存储值
    assert attrs["attack"] == Player.INIT_ATTRS["attack"]
