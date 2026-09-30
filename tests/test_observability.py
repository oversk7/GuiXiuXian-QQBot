"""Performance traces survive NoneBot's sibling-task preprocessors."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from nonebot.adapters.qq import Bot
from nonebot.adapters.qq.event import GroupAtMessageCreateEvent
from nonebot.matcher import Matcher, current_matcher
from nonebot import message as dispatch
from sqlalchemy import event as sql_event, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from plugins.xiuxian_game import observability as perf


class FakeEvent:
    event_id = "event-1"
    id = "message-1"
    def get_user_id(self):
        return "user-1"
    def get_plaintext(self):
        return "sign"


async def test_trace_survives_sibling_tasks_and_shallow_state_copy(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(perf.time, "perf_counter", lambda: now[0])
    event_state = {}
    # NoneBot launches event/run preprocessors in separate tasks.
    await asyncio.create_task(perf._start_perf_trace_event(FakeEvent(), event_state))
    matcher = Matcher()
    now[0] = 1.0
    await asyncio.create_task(perf._start_perf_trace(
        matcher, None, FakeEvent(), event_state.copy()
    ))
    matcher.state.update(event_state.copy())
    trace = matcher.state[perf._TRACE_KEY]
    assert trace is event_state[perf._TRACE_KEY]
    assert trace.event_id == "event-1"
    token = current_matcher.set(matcher)
    try:
        context = SimpleNamespace()
        perf._before_cursor_execute(None, None, "SELECT 1", None, context, False)
        now[0] = 1.25
        perf._after_cursor_execute(None, None, "SELECT 1", None, context, False)
    finally:
        current_matcher.reset(token)
    assert trace.db_count == 1
    assert trace.db_ms == 250.0
    assert trace.slow_queries == [250.0]
    messages = []
    monkeypatch.setattr(perf.logger, "warning", messages.append)
    now[0] = 1.5
    await asyncio.create_task(perf._log_perf_trace(matcher, None))
    await asyncio.create_task(perf._log_event_perf(event_state))
    assert "event=event-1" in messages[0]
    assert "dispatch=1000.0ms" in messages[0]
    assert "handler=500.0ms" in messages[0]
    assert "db=1/250.0ms" in messages[0]
    assert messages[1].startswith("[PerfEvent] elapsed=1500.0ms")


async def test_interleaved_events_do_not_share_query_metrics():
    matchers = []
    for event_id in ("event-a", "event-b"):
        event = FakeEvent()
        event.event_id = event_id
        state = {}
        await perf._start_perf_trace_event(event, state)
        matcher = Matcher()
        await perf._start_perf_trace(matcher, None, event, state)
        matchers.append(matcher)
    async def query(matcher):
        token = current_matcher.set(matcher)
        try:
            context = SimpleNamespace()
            perf._before_cursor_execute(None, None, "SELECT 1", None, context, False)
            await asyncio.sleep(0)
            perf._after_cursor_execute(None, None, "SELECT 1", None, context, False)
        finally:
            current_matcher.reset(token)
    await asyncio.gather(query(matchers[0]), query(matchers[1]))
    assert [m.state[perf._TRACE_KEY].db_count for m in matchers] == [1, 1]


def test_background_database_query_without_matcher_is_ignored():
    context = SimpleNamespace()
    perf._before_cursor_execute(None, None, "SELECT 1", None, context, False)
    perf._after_cursor_execute(None, None, "SELECT 1", None, context, False)
    assert context._xiuxian_perf_trace is None


async def test_real_nonebot_pipeline_records_handler_database_query(monkeypatch):
    event = GroupAtMessageCreateEvent.model_validate({
        "event_id": "perf-pipeline-event",
        "id": "perf-pipeline-message",
        "timestamp": "2026-09-30T20:00:00+08:00",
        "content": "sign",
        "author": {
            "id": "user-1", "member_openid": "user-1",
            "bot": False, "member_role": "member",
        },
        "group_id": "group-1",
        "group_openid": "group-1",
    })
    bot = Bot(MagicMock(), "bot-1", MagicMock())
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = sessionmaker(engine, class_=AsyncSession)
    sql_event.listen(engine.sync_engine, "before_cursor_execute", perf._before_cursor_execute)
    sql_event.listen(engine.sync_engine, "after_cursor_execute", perf._after_cursor_execute)
    from plugins.xiuxian_game.models.db import safe_session
    async def handler():
        async with safe_session(factory) as session:
            await session.execute(text("SELECT 1"))
    matcher = Matcher.new(type_="message", handlers=[handler])
    for attr, calls in (
        ("_event_preprocessors", {perf._start_perf_trace_event}),
        ("_run_preprocessors", {perf._start_perf_trace}),
        ("_run_postprocessors", {perf._log_perf_trace}),
    ):
        monkeypatch.setattr(dispatch, attr, {
            dependent for dependent in getattr(dispatch, attr)
            if dependent.call in calls
        })
    state = {}
    try:
        assert await dispatch._apply_event_preprocessors(bot, event, state)
        await dispatch._run_matcher(matcher, bot, event, state)
        assert state[perf._TRACE_KEY].db_count == 1
    finally:
        matcher.destroy()
        await engine.dispose()


async def test_loop_monitor_lifecycle():
    await perf._start_loop_monitor()
    task = perf._lag_task
    await perf._start_loop_monitor()
    assert perf._lag_task is task
    await perf._stop_loop_monitor()
    assert task.cancelled()
    assert perf._lag_task is None
