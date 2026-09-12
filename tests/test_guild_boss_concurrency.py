import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError

from plugins.xiuxian_game import guild_boss
from plugins.xiuxian_game.guild_boss import _finish_committed, _finish_rolled_back
from plugins.xiuxian_game.guild_boss.config import BLOOD_TIERS, GUILD_EXP_BASE, POINTS_PARTICIPANT, POINTS_TOP3
from plugins.xiuxian_game.guild_boss.service import GuildBossService
from plugins.xiuxian_game.models import db
from plugins.xiuxian_game.models.guild import Guild, GuildMember
from plugins.xiuxian_game.models.guild_boss import GuildBossDamage, GuildBossInstance
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.world_boss.service import WorldBossService
from tests.mysql_helpers import mysql_session_factory


@pytest.fixture
async def boss_db(mysql_session_factory, monkeypatch):
    monkeypatch.setattr(db, "AsyncSessionLocal", mysql_session_factory)

    async def attributes(player, session):
        return {"attack": 10}

    async def battle(self, *args, **kwargs):
        return False, [], 7, 300

    monkeypatch.setattr(Player, "get_effective_attributes", attributes)
    monkeypatch.setattr(WorldBossService, "_execute_sanity_battle_v2", battle)
    monkeypatch.setattr(GuildBossService, "_pick_boss", staticmethod(
        lambda *args: {"name": "测试诡异", "title": "测试", "intro": "测试"}
    ))
    async with db.safe_session() as session:
        players = [Player(
            id=key, uid=index, nickname=key, resentment=1000, gold2=0,
            hp=100, max_hp=100, mp=100, max_mp=100, last_active_at=datetime.now(),
        ) for index, key in enumerate(("a", "z"), 1)]
        session.add_all(players)
        guild = Guild(name="并发镇诡测试", president_id="a", treasury=100000, resentment_pool=300000)
        session.add(guild)
        await session.flush()
        for player in players:
            player.guild_id = guild.id
            session.add(GuildMember(guild_id=guild.id, player_id=player.id))
        return guild.id


async def seed_instance(guild_id, *, hp_left=1000, expired=False, existing_damage=False):
    async with db.safe_session() as session:
        instance = GuildBossInstance(
            guild_id=guild_id, boss_name="测试诡异", boss_title="测试", boss_level=1,
            hp_max=1000, hp_left=hp_left, summoned_by="a",
            expires_at=datetime.now() + timedelta(hours=-1 if expired else 1),
        )
        session.add(instance)
        await session.flush()
        if existing_damage:
            session.add(GuildBossDamage(
                instance_id=instance.id, player_id="a", total_damage=1000 - hp_left, attacks_used=1,
            ))
        return instance.id


async def race(guild_id, instance_id, operations):
    barrier = asyncio.Barrier(len(operations))

    async def run(operation):
        async with db.safe_session() as session:
            guild = await session.get(Guild, guild_id)
            instance = await session.get(GuildBossInstance, instance_id) if instance_id else None
            players = {p.id: p for p in (await session.execute(select(Player))).scalars()}
            # 两边先建立 RR 快照和旧 identity map；后到者必须看到先到者提交的伤害。
            damage_rows = list((await session.execute(select(GuildBossDamage))).scalars())
            await barrier.wait()
            result = await operation(GuildBossService(session), guild, instance, players)
            assert all(row in session for row in damage_rows)
            return result

    return await asyncio.wait_for(asyncio.gather(*(run(op) for op in operations)), timeout=20)


@pytest.mark.parametrize("blood_tier", ["", "中坛"])
async def test_double_summon_creates_one_instance_and_pays_once(boss_db, blood_tier):
    results = await race(boss_db, None, [
        lambda service, guild, instance, players: service.summon(guild, players["a"], blood_tier),
        lambda service, guild, instance, players: service.summon(guild, players["z"], blood_tier),
    ])
    assert sum(ok for ok, _ in results) == 1
    cost = BLOOD_TIERS[blood_tier]["cost"] if blood_tier else GuildBossService.summon_cost(1)
    async with db.safe_session() as session:
        guild = await session.get(Guild, boss_db)
        instances = list((await session.execute(select(GuildBossInstance))).scalars())
        assert len(instances) == 1
        assert instances[0].status == "active"
        assert guild.boss_week_summons == 1
        assert guild.treasury == 100000 - (0 if blood_tier else cost)
        assert guild.resentment_pool == 300000 - (cost if blood_tier else 0)


async def test_two_donations_are_fully_credited(boss_db):
    results = await race(boss_db, None, [
        lambda service, guild, instance, players: service.donate_resentment(guild, players["a"], 120),
        lambda service, guild, instance, players: service.donate_resentment(guild, players["z"], 230),
    ])
    assert all(ok for ok, _ in results)
    async with db.safe_session() as session:
        assert (await session.get(Guild, boss_db)).resentment_pool == 300350
        assert (await session.get(Player, "a")).resentment == 880
        assert (await session.get(Player, "z")).resentment == 770


async def test_two_attacks_preserve_total_damage_and_hp(boss_db):
    instance_id = await seed_instance(boss_db)
    results = await race(boss_db, instance_id, [
        lambda service, guild, instance, players: service.attack(guild, instance, players["a"]),
        lambda service, guild, instance, players: service.attack(guild, instance, players["z"]),
    ])
    assert all(ok and result["applied"] == 300 for ok, result in results)
    async with db.safe_session() as session:
        instance = await session.get(GuildBossInstance, instance_id)
        rows = await GuildBossService(session).get_damage_rows(instance_id)
        assert instance.status == "active"
        assert instance.hp_left == 400
        assert len(rows) == 2
        assert sum(row.total_damage for row in rows) == instance.hp_max - instance.hp_left == 600
        assert all(row.attacks_used == 1 for row in rows)
        players = [await session.get(Player, key) for key in ("a", "z")]
        assert all(player.mp == 93 for player in players)


async def test_killing_attacks_settle_and_award_every_participant_once(boss_db):
    instance_id = await seed_instance(boss_db, hp_left=400, existing_damage=True)
    results = await race(boss_db, instance_id, [
        lambda service, guild, instance, players: service.attack(guild, instance, players["a"]),
        lambda service, guild, instance, players: service.attack(guild, instance, players["z"]),
    ])
    assert all(ok for ok, _ in results)
    assert sum(result["killed"] for _, result in results) == 1
    settlement = next(result["settlement"] for _, result in results if result["killed"])
    assert {p["player_id"] for p in settlement["participants"]} == {"a", "z"}
    assert sum(p["damage"] for p in settlement["participants"]) == 1000
    async with db.safe_session() as session:
        instance = await session.get(GuildBossInstance, instance_id)
        guild = await session.get(Guild, boss_db)
        assert (instance.status, instance.settled, instance.hp_left) == ("subdued", 1, 0)
        assert (guild.boss_level, guild.exp) == (2, GUILD_EXP_BASE)
        assert (await session.get(Player, "a")).gold2 == POINTS_PARTICIPANT + POINTS_TOP3[0]
        assert (await session.get(Player, "z")).gold2 == POINTS_PARTICIPANT + POINTS_TOP3[1]
        assert (await session.get(Player, "a")).mp == 93
        assert (await session.get(Player, "z")).mp == 93
        assert await GuildBossService(session)._settle(instance, guild, killed=True) is None
        assert await GuildBossService(session)._settle(instance, guild, killed=False) is None


async def test_two_lethal_attacks_only_one_can_kill_and_award(boss_db):
    instance_id = await seed_instance(boss_db, hp_left=200, existing_damage=True)
    results = await race(boss_db, instance_id, [
        lambda service, guild, instance, players: service.attack(guild, instance, players["a"]),
        lambda service, guild, instance, players: service.attack(guild, instance, players["z"]),
    ])
    assert sum(ok for ok, _ in results) == 1
    result = next(result for ok, result in results if ok)
    assert result["killed"] and result["applied"] == 200
    awards = {p["player_id"]: p["points"] for p in result["settlement"]["participants"]}
    async with db.safe_session() as session:
        guild = await session.get(Guild, boss_db)
        instance = await session.get(GuildBossInstance, instance_id)
        assert (instance.status, instance.hp_left, instance.settled) == ("subdued", 0, 1)
        assert (guild.boss_level, guild.exp) == (2, GUILD_EXP_BASE)
        rows = await GuildBossService(session).get_damage_rows(instance_id)
        assert sum(row.total_damage for row in rows) == 1000
        assert sum(row.attacks_used for row in rows) == 2
        for key in ("a", "z"):
            player = await session.get(Player, key)
            assert player.gold2 == awards.get(key, 0)
            assert player.mp == (93 if key == instance.final_blow_by else 100)


async def test_expiration_entries_settle_only_once(boss_db):
    instance_id = await seed_instance(boss_db, hp_left=400, expired=True, existing_damage=True)
    results = await race(boss_db, instance_id, [
        lambda service, guild, instance, players: service.settle_if_expired(guild, instance),
        lambda service, guild, instance, players: service._settle(instance, guild, killed=False),
    ])
    assert sum(result is not None for result in results) == 1
    async with db.safe_session() as session:
        guild = await session.get(Guild, boss_db)
        instance = await session.get(GuildBossInstance, instance_id)
        assert (instance.status, instance.settled, instance.hp_left) == ("expired", 1, 400)
        assert guild.exp == int(GUILD_EXP_BASE * 0.6 / 2)
        assert (await session.get(Player, "a")).gold2 == int((POINTS_PARTICIPANT + POINTS_TOP3[0]) * 0.6)
        assert (await session.get(Player, "z")).gold2 == 0
        assert await GuildBossService(session)._settle(instance, guild, killed=True) is None


async def test_attack_racing_expiration_cannot_damage_or_award_twice(boss_db):
    instance_id = await seed_instance(boss_db, hp_left=400, expired=True, existing_damage=True)
    results = await race(boss_db, instance_id, [
        lambda service, guild, instance, players: service.attack(guild, instance, players["z"]),
        lambda service, guild, instance, players: service.settle_if_expired(guild, instance),
    ])
    attack_ok, attack_result = results[0]
    assert int(attack_ok and attack_result.get("expired", False)) + int(results[1] is not None) == 1
    async with db.safe_session() as session:
        instance = await session.get(GuildBossInstance, instance_id)
        assert (instance.status, instance.hp_left) == ("expired", 400)
        assert (await session.get(Player, "z")).mp == 100
        assert (await session.get(Player, "a")).gold2 == int((POINTS_PARTICIPANT + POINTS_TOP3[0]) * 0.6)
        assert (await session.get(Guild, boss_db)).exp == int(GUILD_EXP_BASE * 0.6 / 2)


async def test_reentry_keeps_pending_donations_and_summon_cost(boss_db):
    async with db.safe_session() as session:
        guild = await session.get(Guild, boss_db)
        player = await session.get(Player, "a")
        service = GuildBossService(session)
        assert (await service.donate_resentment(guild, player, 100))[0]
        assert (await service.donate_resentment(guild, player, 200))[0]
        assert (await service.summon(guild, player))[0]
        assert not (await GuildBossService(session).summon(guild, player))[0]
    async with db.safe_session() as session:
        guild = await session.get(Guild, boss_db)
        assert guild.resentment_pool == 300300
        assert (await session.get(Player, "a")).resentment == 700
        assert guild.treasury == 100000 - GuildBossService.summon_cost(1)
        assert guild.boss_week_summons == 1


async def test_reentrant_settlement_keeps_unflushed_rewards(boss_db):
    instance_id = await seed_instance(boss_db, hp_left=400, expired=True, existing_damage=True)
    async with db.safe_session() as session:
        guild = await session.get(Guild, boss_db)
        instance = await session.get(GuildBossInstance, instance_id)
        assert await GuildBossService(session).settle_if_expired(guild, instance) is not None
        assert await GuildBossService(session)._settle(instance, guild, killed=False) is None
    async with db.safe_session() as session:
        assert (await session.get(Guild, boss_db)).exp == int(GUILD_EXP_BASE * 0.6 / 2)
        assert (await session.get(Player, "a")).gold2 == int((POINTS_PARTICIPANT + POINTS_TOP3[0]) * 0.6)
        assert (await session.get(GuildBossInstance, instance_id)).status == "expired"


async def test_success_message_is_sent_after_commit():
    calls = []

    async def commit():
        calls.append("commit")

    async def finish(message):
        calls.append(message)

    await _finish_committed(SimpleNamespace(commit=commit), SimpleNamespace(finish=finish), "成功")
    assert calls == ["commit", "成功"]


async def test_commit_failure_does_not_send_success_message():
    session = SimpleNamespace(commit=AsyncMock(side_effect=SQLAlchemyError("commit failed")))
    matcher = SimpleNamespace(finish=AsyncMock())
    with pytest.raises(SQLAlchemyError, match="commit failed"):
        await _finish_committed(session, matcher, "成功")
    matcher.finish.assert_not_awaited()


async def test_failure_message_is_sent_after_rollback():
    calls = []

    async def rollback():
        calls.append("rollback")

    async def finish(message):
        calls.append(message)

    await _finish_rolled_back(SimpleNamespace(rollback=rollback), SimpleNamespace(finish=finish), "失败")
    assert calls == ["rollback", "失败"]


async def test_nonlethal_attack_does_not_wait_for_other_participant(boss_db):
    instance_id = await seed_instance(boss_db, hp_left=900, existing_damage=True)

    async def attack():
        async with db.safe_session() as session:
            guild = await session.get(Guild, boss_db)
            instance = await session.get(GuildBossInstance, instance_id)
            player = await session.get(Player, "z")
            ok, result = await GuildBossService(session).attack(guild, instance, player)
            assert ok and not result["killed"]

    async with db.safe_session() as blocker:
        await blocker.execute(select(Player).where(Player.id == "a").with_for_update())
        await asyncio.wait_for(attack(), timeout=3)
    async with db.safe_session() as session:
        assert (await session.get(GuildBossInstance, instance_id)).hp_left == 600
        assert (await session.get(Player, "z")).mp == 93


@pytest.mark.parametrize("page", ["view", "report"])
@pytest.mark.parametrize("has_instance", [False, True])
async def test_readonly_page_does_not_wait_for_guild_or_player_locks(boss_db, monkeypatch, page, has_instance):
    if has_instance:
        await seed_instance(boss_db, hp_left=900, existing_damage=True)

    async def identify(session, event):
        player = await session.get(Player, "a")
        player.last_active_at = datetime.now()
        return player

    class PageFinished(Exception):
        pass

    async def finish(message):
        raise PageFinished

    monkeypatch.setattr(guild_boss, "get_unified_player", identify)
    monkeypatch.setattr(getattr(guild_boss, f"{page}_cmd"), "finish", finish)
    async with db.safe_session() as blocker:
        await blocker.execute(select(Guild).where(Guild.id == boss_db).with_for_update())
        await blocker.execute(select(Player).order_by(Player.id).with_for_update())
        with pytest.raises(PageFinished):
            await asyncio.wait_for(getattr(guild_boss, f"handle_{page}")(SimpleNamespace()), timeout=3)


@pytest.mark.parametrize("page", ["view", "report"])
async def test_boss_pages_commit_lazy_settlement_once(boss_db, monkeypatch, page):
    instance_id = await seed_instance(boss_db, hp_left=400, expired=True, existing_damage=True)

    async def identify(session, event):
        return await session.get(Player, "z")

    class PageFinished(Exception):
        pass

    async def finish(message):
        raise PageFinished

    monkeypatch.setattr(guild_boss, "get_unified_player", identify)
    monkeypatch.setattr(getattr(guild_boss, f"{page}_cmd"), "finish", finish)
    for _ in range(2):
        with pytest.raises(PageFinished):
            await getattr(guild_boss, f"handle_{page}")(SimpleNamespace())
    async with db.safe_session() as session:
        guild = await session.get(Guild, boss_db)
        instance = await session.get(GuildBossInstance, instance_id)
        assert (instance.status, instance.settled) == ("expired", 1)
        assert guild.exp == int(GUILD_EXP_BASE * 0.6 / 2)
        assert (await session.get(Player, "a")).gold2 == int((POINTS_PARTICIPANT + POINTS_TOP3[0]) * 0.6)


@pytest.mark.parametrize("lethal", [False, True])
async def test_actor_version_change_rolls_back_entire_attack(boss_db, monkeypatch, lethal):
    hp_left = 200 if lethal else 900
    instance_id = await seed_instance(boss_db, hp_left=hp_left, existing_damage=True)

    async def battle(self, player, *args, **kwargs):
        player.hp = 80
        # 即使引擎修改 ORM 字段后继续查询，也不能提前写出玩家。
        await self._session.execute(select(Player.id))
        async with db.safe_session() as other:
            current = await other.get(Player, player.id)
            current.gold2 += 11
        return False, [], 7, 300

    monkeypatch.setattr(WorldBossService, "_execute_sanity_battle_v2", battle)

    async def attack():
        async with db.safe_session() as session:
            guild = await session.get(Guild, boss_db)
            instance = await session.get(GuildBossInstance, instance_id)
            player = await session.get(Player, "z")
            player.last_active_at = datetime.now()
            await GuildBossService(session).attack(guild, instance, player)

    with pytest.raises(StaleDataError):
        await asyncio.wait_for(attack(), timeout=3)
    async with db.safe_session() as session:
        guild = await session.get(Guild, boss_db)
        instance = await session.get(GuildBossInstance, instance_id)
        player = await session.get(Player, "z")
        rows = await GuildBossService(session).get_damage_rows(instance_id)
        all_rows = list((await session.execute(select(GuildBossDamage))).scalars())
        assert (instance.hp_left, instance.status, instance.settled) == (hp_left, "active", 0)
        assert (player.hp, player.mp, player.gold2) == (100, 100, 11)
        assert (guild.exp, guild.boss_level) == (0, 1)
        assert len(rows) == len(all_rows) == 1
        assert (rows[0].player_id, rows[0].total_damage, rows[0].attacks_used) == ("a", 1000 - hp_left, 1)


async def test_attack_preserves_engine_player_changes(boss_db, monkeypatch):
    instance_id = await seed_instance(boss_db)

    async def battle(self, player, *args, **kwargs):
        player.hp = 80
        await self._session.execute(select(Player.id))
        return False, [], 7, 300

    monkeypatch.setattr(WorldBossService, "_execute_sanity_battle_v2", battle)
    async with db.safe_session() as session:
        guild = await session.get(Guild, boss_db)
        instance = await session.get(GuildBossInstance, instance_id)
        player = await session.get(Player, "z")
        assert (await GuildBossService(session).attack(guild, instance, player))[0]
    async with db.safe_session() as session:
        player = await session.get(Player, "z")
        assert (player.hp, player.mp) == (80, 93)

