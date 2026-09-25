"""月蚀祭个人进度、奖励和限购边界。"""

import time
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.qq import Message
from nonebot.exception import FinishedException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plugins.xiuxian_game.config import config
from plugins.xiuxian_game.event import moon_commands, moon_festival as festival
from plugins.xiuxian_game.models.player import Player


@pytest.fixture
def moon_event(tmp_path, monkeypatch):
    monkeypatch.setattr(festival, "STATE_FILE", tmp_path / "state.json")
    festival.MoonFestivalService.start()
    return festival.MoonFestivalService


def player():
    member = Player(
        id="p", uid=1, nickname="甲", hp=100, max_hp=100, attack=30, defense=10, agility=10,
        extra_attrs={},
    )
    member.get_effective_attributes = AsyncMock(return_value={
        "max_hp": 100, "attack": 30, "defense": 10, "agility": 10
    })
    return member


def test_event_items_are_registered():
    items = config.items_config["by_id"]
    assert items["moon_festival_cake"].effect_params["percent"] == 0.15
    dew = items["moon_festival_dew"]
    assert dew.effect_params == {"hp_percent": 0.3, "mp_percent": 0.3}
    assert "event_only" in dew.tags
    assert festival.SHOP["moon_festival_dew"] == ("桂月露", 20, 2)
    talisman = items["moon_festival_talisman"]
    assert talisman.effect_params["accuracy_rate"] == 10
    assert talisman.effect_params["critical_rate"] == 5
    assert "event_only" in talisman.tags
    assert festival.SHOP["moon_festival_talisman"] == ("望月符", 15, 2)
    assert items["moon_festival_keepsake"].name == "月轮残片"


async def test_status_sends_actionable_markdown_for_each_phase(moon_event, monkeypatch):
    member = player()

    @asynccontextmanager
    async def fake_session():
        yield object()

    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(moon_commands, "safe_session", fake_session)
    monkeypatch.setattr(moon_commands, "require_player", AsyncMock(return_value=member))
    monkeypatch.setattr(moon_commands.status_cmd, "finish", finish)

    async def content():
        with pytest.raises(FinishedException):
            await moon_commands.show_status(object())
        segments = Message(finish.await_args.args[0])
        assert [segment.type for segment in segments] == ["markdown"]
        return segments[0].data["markdown"].content

    first = await content()
    assert "# 🌘 月蚀祭 · 守月" in first
    assert "今日采月 · 0/2" in first
    assert '<qqbot-cmd-input text="签到"' in first
    assert '<qqbot-cmd-input text="守月"' not in first

    moon_event.record_action(member, "sign")
    moon_event.record_action(member, "cultivate")
    ready = await content()
    assert "今日采月 · 2/2" in ready
    assert "⚔️ 缺月 · 可挑战" in ready
    assert '<qqbot-cmd-input text="守月"' in ready
    assert '<qqbot-cmd-input text="探索"' not in ready

    progress = moon_event._progress(member)
    progress["cleared"] = len(festival.CHAPTERS)
    moon_event._store(member, progress)
    completed = await content()
    assert "# 🌕 月蚀祭 · 月轮已圆" in completed
    assert '<qqbot-cmd-input text="守月"' not in completed

    state = moon_event.state()
    state["end"] = time.time() - 10
    moon_event._save_state(state)
    exchange = await content()
    assert "兑换期" in exchange
    assert "今日采月" not in exchange
    assert '<qqbot-cmd-input text="守月"' not in exchange
    assert '<qqbot-cmd-input text="月华商店"' in exchange


def test_two_distinct_actions_per_day_and_new_run(moon_event, monkeypatch):
    current = [datetime(2026, 9, 25)]

    class FakeDatetime(datetime):
        @classmethod
        def now(cls):
            return current[0]

    monkeypatch.setattr(festival, "datetime", FakeDatetime)
    member = player()
    assert moon_event.record_action(member, "sign")
    assert not moon_event.record_action(member, "sign")
    assert moon_event.record_action(member, "cultivate")
    assert not moon_event.record_action(member, "cook")
    assert moon_event._progress(member)["total"] == 40
    current[0] = datetime(2026, 9, 26)
    assert moon_event.record_action(member, "sign")
    assert moon_event._progress(member)["total"] == 60
    moon_event.stop()
    moon_event.start()
    assert moon_event._progress(member)["total"] == 0


async def test_exchange_grace_without_new_progress(moon_event):
    member = player()
    state = moon_event.state()
    state["end"] = time.time() - 10
    moon_event._save_state(state)
    assert not moon_event.record_action(member, "sign")
    assert "当前未开放" in await moon_event.challenge(object(), member)
    assert "团圆月饼" in moon_event.shop(member)
    state["end"] = time.time() - festival.EXCHANGE_GRACE - 10
    moon_event._save_state(state)
    assert "当前未开放" in moon_event.shop(member)


async def test_challenges_retry_and_issue_title_once(moon_event, monkeypatch):
    member = player()
    data = moon_event._progress(member)
    data.update(total=120, balance=120)
    moon_event._store(member, data)
    monkeypatch.setattr(moon_event, "_lock_player", AsyncMock(side_effect=lambda session, p: p))
    battle = AsyncMock(side_effect=[(False, [], 7, []), *((True, [], 2, [{"effect": "growth"}]) for _ in range(3))])
    add_item = AsyncMock(return_value=True)
    growth = AsyncMock(return_value=["战后成长已结算"])
    monkeypatch.setattr(festival.BattleIntegrationHelper, "enhanced_player_vs_monster_battle_v2", battle)
    monkeypatch.setattr(festival.ItemInstance, "add_item", add_item)
    monkeypatch.setattr(festival, "settle_pve_victory", growth)

    assert "进度不会损失" in await moon_event.challenge(object(), member)
    assert member.hp == 93
    assert moon_event._progress(member)["cleared"] == 0
    growth.assert_not_awaited()
    for stage in range(1, 4):
        assert f"（{stage}/3）" in await moon_event.challenge(object(), member)
    assert moon_event._progress(member)["cleared"] == 3
    assert "守月人" in member.extra_attrs["knocker_event"]["owned_titles"]
    assert member.hp == 87
    assert add_item.await_count == 3
    assert growth.await_count == 3
    assert growth.await_args_list[0].args[2] == [{"effect": "growth"}]
    assert add_item.await_args_list[1].args[2] == "moon_festival_dew"
    assert "已经修补完成" in await moon_event.challenge(object(), member)
    assert add_item.await_count == 3


async def test_full_bag_keeps_challenge_and_shop_balance(moon_event, monkeypatch):
    member = player()
    data = moon_event._progress(member)
    data.update(total=40, balance=40)
    moon_event._store(member, data)
    monkeypatch.setattr(moon_event, "_lock_player", AsyncMock(side_effect=lambda session, p: p))
    monkeypatch.setattr(festival.BattleIntegrationHelper, "enhanced_player_vs_monster_battle_v2", AsyncMock(return_value=(True, [], 0, [])))
    item = AsyncMock(side_effect=ValueError("背包空间不足"))
    monkeypatch.setattr(festival.ItemInstance, "add_item", item)
    assert "整理背包" in await moon_event.challenge(object(), member)
    assert moon_event._progress(member)["cleared"] == 0
    assert "兑换失败" in await moon_event.buy(object(), member, "团圆月饼", 1)
    assert moon_event._progress(member)["balance"] == 40
    item.side_effect = None
    assert "兑换成功" in await moon_event.buy(object(), member, "团圆月饼", 3)
    assert "个人限购" in await moon_event.buy(object(), member, "团圆月饼", 1)
    assert moon_event._progress(member)["balance"] == 10


async def test_progress_persists_with_other_player_data(moon_event, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Player.__table__.create)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            session.add(Player(id="p", uid=1, nickname="甲", extra_attrs={"another_event": {"key": 1}}))
            await session.commit()

        async with factory() as session:
            member = await session.get(Player, "p")
            assert moon_event.record_action(member, "sign")
            await session.commit()
        async with factory() as session:
            member = await session.get(Player, "p")
            assert member.extra_attrs["another_event"] == {"key": 1}
            assert moon_event._progress(member)["balance"] == 20
            monkeypatch.setattr(festival.ItemInstance, "add_item", AsyncMock(return_value=True))
            assert "兑换成功" in await moon_event.buy(session, member, "团圆月饼", 1)
            await session.commit()
        async with factory() as session:
            member = await session.get(Player, "p")
            assert moon_event._progress(member)["balance"] == 10
            assert moon_event._progress(member)["bought"]["moon_festival_cake"] == 1
    finally:
        await engine.dispose()
