import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.qq.exception import ActionFailed as QQActionFailed
from nonebot.drivers import Response
from nonebot.exception import ActionFailed, FinishedException, PausedException, RejectedException
from nonebot.message import _run_postprocessors
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from plugins.xiuxian_game.command_errors import (
    CONTENT_REJECTED_MESSAGE,
    DB_CONFLICT_MESSAGE,
    INVENTORY_CAPACITY_MESSAGE,
    _failure_message,
    handle_command_error,
)
from plugins.xiuxian_game.infrastructure.exceptions import InventoryCapacityError
from plugins.xiuxian_game.infrastructure.uow.unit_of_work import UnitOfWork
from plugins.xiuxian_game.models.db import safe_session


def test_handler_is_registered_once():
    assert sum(proc.call is handle_command_error for proc in _run_postprocessors) == 1


@pytest.mark.parametrize("exception", [
    None, ValueError("背包空间不足"), ValueError("物品模板不存在"), RuntimeError("bug"),
    FinishedException(), PausedException(), RejectedException(),
    OperationalError("sql", {}, ValueError(9999)),
])
async def test_unknown_and_handled_failures_do_not_send_capacity_notice(exception):
    matcher = SimpleNamespace(send=AsyncMock())
    await handle_command_error(matcher, exception)
    matcher.send.assert_not_awaited()


@pytest.mark.parametrize("wrapped", ["direct", "cause", "context"])
async def test_capacity_error_sends_exactly_one_notice(wrapped):
    error = InventoryCapacityError()
    assert isinstance(error, ValueError)
    assert str(error) == "背包空间不足"
    if wrapped != "direct":
        wrapper = RuntimeError("业务包装")
        setattr(wrapper, f"__{wrapped}__", error)
        error = wrapper
    matcher = SimpleNamespace(send=AsyncMock())
    await handle_command_error(matcher, error)
    matcher.send.assert_awaited_once_with(INVENTORY_CAPACITY_MESSAGE)


@pytest.mark.parametrize("wrapped", [False, True])
async def test_qq_content_rejection_sends_plain_notice(wrapped):
    error = QQActionFailed(Response(400, content=json.dumps({"code": 40034006})))
    if wrapped:
        wrapper = RuntimeError("send failed")
        wrapper.__cause__ = error
        error = wrapper
    matcher = SimpleNamespace(send=AsyncMock())
    await handle_command_error(matcher, error)
    matcher.send.assert_awaited_once_with(CONTENT_REJECTED_MESSAGE)


@pytest.mark.parametrize("code", [304003, 304016, None])
async def test_other_qq_errors_are_not_reported_as_content_rejection(code):
    error = QQActionFailed(Response(400, content=json.dumps({"code": code})))
    matcher = SimpleNamespace(send=AsyncMock())
    await handle_command_error(matcher, error)
    matcher.send.assert_not_awaited()


async def test_rejected_notice_is_not_retried():
    error = QQActionFailed(Response(400, content=json.dumps({"code": 40034006})))
    matcher = SimpleNamespace(send=AsyncMock(side_effect=error))
    await handle_command_error(matcher, error)
    matcher.send.assert_awaited_once_with(CONTENT_REJECTED_MESSAGE)


def test_suppressed_and_cyclic_exception_contexts_are_safe():
    error = RuntimeError("unknown")
    error.__context__ = InventoryCapacityError()
    error.__suppress_context__ = True
    assert _failure_message(error) is None
    error.__cause__ = error
    assert _failure_message(error) is None


@pytest.mark.parametrize("error", [
    StaleDataError(),
    *(OperationalError("sql", {}, ValueError(code)) for code in (1205, 1213, 3572)),
])
async def test_existing_database_conflict_notice_is_preserved(error):
    matcher = SimpleNamespace(send=AsyncMock())
    await handle_command_error(matcher, error)
    matcher.send.assert_awaited_once_with(DB_CONFLICT_MESSAGE)


async def test_notice_delivery_failure_is_logged(monkeypatch):
    from plugins.xiuxian_game import command_errors

    warning = SimpleNamespace(warning=lambda message: messages.append(message))
    messages = []
    monkeypatch.setattr(command_errors, "logger", warning)
    matcher = SimpleNamespace(send=AsyncMock(side_effect=ActionFailed("QQ")))
    await handle_command_error(matcher, InventoryCapacityError())
    matcher.send.assert_awaited_once()
    assert len(messages) == 1 and "失败提示发送失败" in messages[0]


@pytest.mark.parametrize("manager", [safe_session, UnitOfWork])
async def test_capacity_notice_is_sent_after_rollback_and_close(manager):
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.__aexit__.return_value = False

    async def send(message):
        session.rollback.assert_awaited_once()
        session.close.assert_awaited_once()
        session.commit.assert_not_awaited()
        assert message == INVENTORY_CAPACITY_MESSAGE

    matcher = SimpleNamespace(send=AsyncMock(side_effect=send))
    try:
        async with manager(lambda: session):
            raise InventoryCapacityError()
    except InventoryCapacityError as error:
        await handle_command_error(matcher, error)
    matcher.send.assert_awaited_once()


async def test_nonebot_dispatcher_provides_reply_context(monkeypatch):
    from nonebot.adapters.qq import Bot
    from nonebot.matcher import Matcher
    from nonebot.message import _apply_run_postprocessors
    from tests.test_message_guard import _qq_bot, _qq_event

    send = AsyncMock()
    monkeypatch.setattr(Bot, "send", send)
    event = _qq_event(text="收工")
    await _apply_run_postprocessors(
        bot=_qq_bot(), event=event, matcher=Matcher(), exception=InventoryCapacityError(),
    )
    send.assert_awaited_once_with(event=event, message=INVENTORY_CAPACITY_MESSAGE)


async def test_qq_rejection_notice_uses_original_event_context(monkeypatch):
    from nonebot.adapters.qq import Bot
    from nonebot.matcher import Matcher
    from nonebot.message import _apply_run_postprocessors
    from tests.test_message_guard import _qq_bot, _qq_event

    send = AsyncMock()
    monkeypatch.setattr(Bot, "send", send)
    event = _qq_event(text="观察")
    error = QQActionFailed(Response(400, content=json.dumps({"code": 40034006})))
    await _apply_run_postprocessors(
        bot=_qq_bot(), event=event, matcher=Matcher(), exception=error,
    )
    send.assert_awaited_once_with(event=event, message=CONTENT_REJECTED_MESSAGE)
