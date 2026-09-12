import importlib
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.exception import FinishedException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm.exc import StaleDataError

from plugins.xiuxian_game import platform_utils
from plugins.xiuxian_game.achievement.achievement_service import AchievementService
from plugins.xiuxian_game.cultivate import core
from plugins.xiuxian_game.models import db, monthly_card
from plugins.xiuxian_game.models.achievement import PlayerAchievement, PlayerStats
from plugins.xiuxian_game.models.inventory import ItemInstance
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.quest.novice_quest_service import NoviceQuestService

sign_module = importlib.import_module("plugins.xiuxian_game.entertainment.sign")


@pytest.fixture
async def feedback_store(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'feedback.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: db.Base.metadata.create_all(
            conn, tables=[Player.__table__, ItemInstance.__table__, PlayerStats.__table__, PlayerAchievement.__table__],
        ))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(AchievementService, "_achievement_config", {
        "basic_achievements": {"first_login": {"condition_type": "login_streak", "condition_value": 1,
                                               "title": "首次登录", "rewards": {"gold": 10}}},
    })
    monkeypatch.setattr(Player, "get_effective_inventory_capacity", AsyncMock(return_value=80))
    monkeypatch.setattr(monthly_card, "get_player_card_benefits", AsyncMock(return_value={
        "sign_stamina_bonus": 0, "sign_monthly_card_boxes": 0,
        "seclusion_efficiency": 0, "seclusion_time_limit": 7200,
    }))
    monkeypatch.setattr(core, "get_coffin_nail_count", AsyncMock(return_value=0))
    from plugins.xiuxian_game.cultivate.mansion_service import MansionService
    from plugins.xiuxian_game.social.mentorship_system_service import MentorshipSystemService
    monkeypatch.setattr(MansionService, "find_mansion_owner_at_location", AsyncMock(return_value=None))
    monkeypatch.setattr(MentorshipSystemService, "get_cultivation_penalty", AsyncMock(return_value=0))
    monkeypatch.setattr(sign_module.random, "randint", lambda *args: 100)
    monkeypatch.setattr(sign_module, "luck_prob", lambda luck: 0)

    async def identity(session, event, *args):
        player = await session.get(Player, "p")
        player.last_active_at = datetime.now()
        return player

    monkeypatch.setattr(platform_utils, "get_unified_player", identity)
    monkeypatch.setattr(platform_utils, "require_player", identity)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.parametrize("command", ["sign", "sign_again", "seclusion"])
@pytest.mark.parametrize("failure", [None, "quest", "commit"])
async def test_rewards_and_feedback_share_one_commit(feedback_store, monkeypatch, command, failure):
    factory = feedback_store
    now = datetime.now()
    original_sign = now if command == "sign_again" else None
    async with db.safe_session(factory) as session:
        session.add(Player(id="p", uid=1, nickname="玩家", gold=100, exp=0, last_sign=original_sign,
                           created_at=now - timedelta(days=10)))

    @asynccontextmanager
    async def command_session():
        async with factory() as session:
            if failure == "commit":
                session.commit = AsyncMock(side_effect=StaleDataError("commit conflict"))
            yield session

    monkeypatch.setattr(db, "AsyncSessionLocal", command_session)

    async def quest(session, player, *args):
        player.exp += 100
        await session.flush()
        if failure == "quest":
            raise StaleDataError("quest conflict")
        return True, "任务完成"

    monkeypatch.setattr(NoviceQuestService, "check_and_advance_quest", quest)

    async def check_success():
        async with db.safe_session(factory) as session:
            player = await session.get(Player, "p")
            assert player.exp == 100
            assert player.is_secluded == (command == "seclusion")
            assert player.gold == (210 if command == "sign" else 100)
            if command == "sign":
                assert player.last_sign.date() == now.date()
                assert (await session.execute(select(PlayerAchievement))).scalars().one().is_completed
                assert (await session.execute(select(PlayerStats))).scalars().one().total_login_days == 1

    async def send(message):
        await check_success()
        if command == "seclusion":
            raise FinishedException

    reply = AsyncMock(side_effect=send)
    if command == "seclusion":
        monkeypatch.setattr(core.seclusion, "finish", reply)
        handler = core.handle_seclusion
    else:
        monkeypatch.setattr(sign_module.sign, "send", reply)
        handler = sign_module.handle_sign
    event = SimpleNamespace(get_user_id=lambda: "platform")
    if failure:
        with pytest.raises(StaleDataError):
            await handler(event)
        reply.assert_not_awaited()
        async with db.safe_session(factory) as session:
            player = await session.get(Player, "p")
            assert player.gold == 100 and player.exp == 0 and not player.is_secluded
            assert player.last_sign == original_sign
            for model in (ItemInstance, PlayerStats, PlayerAchievement):
                assert not (await session.execute(select(model))).scalars().all()
    else:
        if command == "seclusion":
            with pytest.raises(FinishedException):
                await handler(event)
        else:
            await handler(event)
        reply.assert_awaited_once()
        await check_success()
