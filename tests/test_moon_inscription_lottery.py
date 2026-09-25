"""月华抽奖概率边界、仙品数值与事务回滚。"""

import random
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plugins.xiuxian_game.config import config
from plugins.xiuxian_game.event import moon_festival as festival
from plugins.xiuxian_game.item.inscription_service import (
    generate_celestial_inscription, generate_inscription_drop,
    get_inscription_effect_configs,
)
from plugins.xiuxian_game.models.inventory import ItemInstance
from plugins.xiuxian_game.models.player import Player


@pytest.fixture
async def lottery(tmp_path, monkeypatch):
    monkeypatch.setattr(festival, "STATE_FILE", tmp_path / "moon.json")
    service = festival.MoonFestivalService
    service.start()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Player.__table__.create)
        await connection.run_sync(ItemInstance.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(Player, "get_effective_inventory_capacity", AsyncMock(return_value=30))
    try:
        async with factory() as session:
            member = Player(id="lottery", uid=1, nickname="抽奖者", extra_attrs={})
            session.add(member)
            progress = service._progress(member)
            progress.update(total=200, balance=200)
            service._store(member, progress)
            await session.commit()
            yield service, session, member
    finally:
        await engine.dispose()


def fixed_rolls(monkeypatch, values):
    rng = random.Random(42)
    rolls = iter(values)
    rng.randrange = lambda *args: next(rolls)
    monkeypatch.setattr(festival.random, "Random", lambda: rng)


@pytest.mark.parametrize("roll,expected,count", [
    (0, "celestial", 1), (39, "celestial", 1),
    (40, "inscription_fragment", 3), (59, "inscription_fragment", 3),
    (60, "moon_festival_cake", 1), (79, "moon_festival_cake", 1),
    (80, "moon_festival_dew", 1), (99, "moon_festival_dew", 1),
])
async def test_lottery_prize_boundaries(lottery, monkeypatch, roll, expected, count):
    service, session, member = lottery
    fixed_rolls(monkeypatch, [roll])
    result = await service.buy(session, member, "仙品铭文抽奖", 1)
    assert "月华开奖" in result
    await session.commit()
    items = (await session.scalars(select(ItemInstance))).all()
    assert len(items) == 1
    item = items[0]
    assert item.quantity == count
    if expected == "celestial":
        assert item.is_inscription
        assert item.extra_attrs["_inscription_grade"] == "仙品"
        assert "{仙品}" in result
        assert "仙光破匣" in result
        assert "本轮揭出仙品铭文 ×1" in result
    else:
        assert item.item_id == expected
        assert "月下得赏" in result
        assert "仙光破匣" not in result
    data = service._progress(member)
    assert data["balance"] == 160
    assert data["bought"] == {festival.LOTTERY_ID: 1}


async def test_five_draws_and_limit(lottery, monkeypatch):
    service, session, member = lottery
    fixed_rolls(monkeypatch, [0, 39, 40, 60, 80])
    result = await service.buy(session, member, "仙品铭文抽奖", 5)
    assert "第5抽" in result
    assert "本轮揭出仙品铭文 ×2" in result
    assert 'text="月华商店 兑换 仙品铭文抽奖"' not in result
    assert service._progress(member)["balance"] == 0
    assert service._progress(member)["bought"][festival.LOTTERY_ID] == 5
    await session.commit()
    assert "个人限购" in await service.buy(session, member, "仙品铭文抽奖", 1)
    assert 'text="月华商店 兑换 仙品铭文抽奖"' not in service.shop(member)
    items = (await session.scalars(select(ItemInstance))).all()
    assert len(items) == 5
    assert sum(item.is_inscription for item in items) == 2


async def test_failed_batch_rolls_back_all_prizes(lottery, monkeypatch):
    service, session, member = lottery
    fixed_rolls(monkeypatch, [0, 60])

    async def fail_after_flush(*args, **kwargs):
        await session.flush()
        raise ValueError("背包空间不足")

    monkeypatch.setattr(ItemInstance, "add_item", fail_after_flush)
    result = await service.buy(session, member, "仙品铭文抽奖", 2)
    assert "兑换失败" in result
    await session.commit()
    assert not (await session.scalars(select(ItemInstance))).all()
    data = service._progress(member)
    assert data["balance"] == 200
    assert data["bought"] == {}


async def test_insufficient_balance_does_not_draw(lottery, monkeypatch):
    service, session, member = lottery
    data = service._progress(member)
    data["balance"] = 39
    service._store(member, data)
    await session.commit()
    draw = AsyncMock()
    monkeypatch.setattr(service, "_draw_inscriptions", draw)
    assert "月华不足" in await service.buy(session, member, "仙品铭文抽奖", 1)
    draw.assert_not_awaited()
    assert service._progress(member)["bought"] == {}


@pytest.mark.parametrize("balance,bought,batch", [
    (200, 0, 5), (80, 1, 2), (200, 4, 1), (39, 0, 0), (200, 5, 0),
])
def test_lottery_controls_only_offer_affordable_draws(balance, bought, batch):
    lines = festival.MoonFestivalService._lottery_controls({
        "balance": balance, "bought": {festival.LOTTERY_ID: bought},
    })
    content = "\n".join(lines)
    single = 'text="月华商店 兑换 仙品铭文抽奖"'
    assert (single in content) is (batch > 0)
    if batch > 1:
        assert f'text="月华商店 兑换 仙品铭文抽奖 {batch}"' in content
        assert f"{batch * 40}月华" in content
    else:
        assert 'text="月华商店 兑换 仙品铭文抽奖 ' not in content


def test_all_celestial_inscriptions_have_high_rolls():
    pool = config.items_config["by_type"]["INSCRIPTION"]
    assert any(config.items_config["by_id"][key].inscription_type == "advanced" for key in pool)
    for item_id in pool:
        effects = get_inscription_effect_configs(item_id)
        if not effects:
            continue
        attrs = generate_celestial_inscription(item_id, random.Random(42))
        assert attrs["_inscription_grade"] == "仙品"
        assert len(attrs["_inscription_values"]) == len(effects)
        for values, effect in zip(attrs["_inscription_values"], effects):
            for key in ("chance", "value"):
                if f"{key}_range" in effect:
                    low, high = effect[f"{key}_range"]
                    assert round(low + (high - low) * 0.95, 1) <= values[key] <= high


@pytest.mark.parametrize("level,roll,celestial", [
    (2999, 0.0, False), (3000, 0.0199, True), (3000, 0.02, False),
])
def test_drop_celestial_level_and_two_percent_boundary(level, roll, celestial):
    rng = random.Random(42)
    rng.random = lambda: roll
    attrs = generate_inscription_drop("inscription_fear", rng, level)
    assert (attrs["_inscription_grade"] == "仙品") is celestial
