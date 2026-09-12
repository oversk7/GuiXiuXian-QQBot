from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError

from plugins.xiuxian_game.models.db import safe_session
from plugins.xiuxian_game.models.inventory import ItemInstance
from plugins.xiuxian_game.models.player import Player
from tests.mysql_helpers import mysql_session_factory


async def seed(factory):
    async with safe_session(factory) as session:
        session.add(Player(id="p", uid=1, nickname="玩家", gold=100))


@pytest.mark.parametrize("context_first", [True, False])
async def test_context_and_asset_updates_do_not_conflict(mysql_session_factory, context_first):
    factory = mysql_session_factory
    await seed(factory)
    now = datetime.now().replace(microsecond=0)
    async with safe_session(factory) as context, safe_session(factory) as business:
        observer = await context.get(Player, "p")
        actor = await business.get(Player, "p")
        observer.last_active_at = now
        observer.last_group_openid = "group"
        observer.last_group_member_id = "member"
        observer.last_group_username = "群昵称"
        actor.gold -= 20
        first, second = (context, business) if context_first else (business, context)
        await first.commit()
        await second.commit()
    async with safe_session(factory) as check:
        player = await check.get(Player, "p")
        assert player.gold == 80 and player.version_id == 2
        assert player.last_active_at == now
        assert (player.last_group_openid, player.last_group_member_id, player.last_group_username) == ("group", "member", "群昵称")


async def test_late_context_update_keeps_newer_activity_time(mysql_session_factory):
    factory = mysql_session_factory
    await seed(factory)
    now = datetime.now().replace(microsecond=0)
    async with safe_session(factory) as first, safe_session(factory) as delayed:
        current = await first.get(Player, "p")
        stale = await delayed.get(Player, "p")
        current.last_active_at = now
        stale.last_active_at = now - timedelta(minutes=1)
        await first.commit()
        await delayed.commit()
    async with safe_session(factory) as check:
        player = await check.get(Player, "p")
        assert player.last_active_at == now and player.version_id == 1


async def test_context_after_committed_success_does_not_report_business_failure(mysql_session_factory):
    factory = mysql_session_factory
    await seed(factory)
    async with safe_session(factory) as operation:
        player = await operation.get(Player, "p")
        player.gold += 50
        await operation.commit()
        async with safe_session(factory) as other:
            current = await other.get(Player, "p")
            current.gold -= 20
        player.last_group_openid = "reply-group"
    async with safe_session(factory) as check:
        player = await check.get(Player, "p")
        assert player.gold == 130 and player.version_id == 3
        assert player.last_group_openid == "reply-group"


async def test_mixed_asset_and_context_conflict_still_rolls_back_rewards(mysql_session_factory):
    factory = mysql_session_factory
    await seed(factory)
    with pytest.raises(StaleDataError):
        async with safe_session(factory) as stale_session:
            stale = await stale_session.get(Player, "p")
            async with safe_session(factory) as writer:
                current = await writer.get(Player, "p")
                current.gold -= 20
            stale_session.add(ItemInstance(player_id="p", item_id="bone_fragment", quantity=1))
            await stale_session.flush()
            stale.gold += 50
            stale.last_group_openid = "must-rollback"
    async with safe_session(factory) as check:
        player = await check.get(Player, "p")
        assert player.gold == 80 and player.last_group_openid is None
        assert not (await check.execute(select(ItemInstance))).scalars().all()


async def test_context_update_remains_part_of_transaction(mysql_session_factory):
    factory = mysql_session_factory
    await seed(factory)
    with pytest.raises(ValueError, match="abort"):
        async with safe_session(factory) as session:
            player = await session.get(Player, "p")
            player.last_group_openid = "must-rollback"
            await session.flush()
            raise ValueError("abort")
    async with safe_session(factory) as check:
        player = await check.get(Player, "p")
        assert player.last_group_openid is None and player.version_id == 1


async def test_context_cannot_update_a_deleted_player(mysql_session_factory):
    factory = mysql_session_factory
    await seed(factory)
    with pytest.raises(StaleDataError):
        async with safe_session(factory) as stale_session:
            stale = await stale_session.get(Player, "p")
            async with safe_session(factory) as other:
                current = await other.get(Player, "p")
                await other.delete(current)
            stale.last_group_openid = "missing"


async def test_lottery_join_sends_success_after_concurrent_player_update(mysql_session_factory, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from nonebot.adapters.qq import Message
    from nonebot.exception import FinishedException
    from plugins.xiuxian_game.admin import lottery_commands
    from plugins.xiuxian_game.models import db
    from plugins.xiuxian_game.models.lottery import Lottery, LotteryParticipant, LotteryType

    factory = mysql_session_factory
    await seed(factory)
    monkeypatch.setattr(db, "AsyncSessionLocal", factory)
    async with safe_session(factory) as session:
        lottery = Lottery(creator_id="host", creator_uid=2, creator_name="发起人", lottery_type=LotteryType.GOLD,
                          item_name="金币", winner_count=1, prize_per_winner=100, total_prize=100)
        session.add(lottery)
        await session.flush()
        lottery_id = lottery.id

    async def identity(session, event, matcher):
        player = await session.get(Player, "p")
        player.last_active_at = datetime.now()
        async with safe_session(factory) as writer:
            current = await writer.get(Player, "p")
            current.gold -= 20
        return player

    async def finish(message):
        assert "参与成功" in message
        async with safe_session(factory) as check:
            participant = (await check.execute(select(LotteryParticipant))).scalar_one()
            assert participant.player_id == "p" and participant.lottery_id == lottery_id
            player = await check.get(Player, "p")
            assert player.gold == 80 and player.version_id == 2
        raise FinishedException

    reply = AsyncMock(side_effect=finish)
    monkeypatch.setattr(lottery_commands, "require_player", identity)
    monkeypatch.setattr(lottery_commands, "message_add_head", lambda text, event: text)
    monkeypatch.setattr(lottery_commands.join_lottery_cmd, "finish", reply)
    with pytest.raises(FinishedException):
        await lottery_commands.handle_join_lottery(SimpleNamespace(get_user_id=lambda: "platform"), Message(str(lottery_id)))
    reply.assert_awaited_once()
