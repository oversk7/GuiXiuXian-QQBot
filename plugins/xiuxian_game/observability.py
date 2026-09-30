"""Lightweight per-event performance observability."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import time
from dataclasses import dataclass, field
from typing import Any

from nonebot import get_driver, logger
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher, current_matcher
from nonebot.message import (
    event_postprocessor,
    event_preprocessor,
    run_postprocessor,
    run_preprocessor,
)
from nonebot.typing import T_State
from sqlalchemy import event as sqlalchemy_event

from .models.db import engine


SLOW_EVENT_MS = 800.0
MANY_DB_QUERIES = 8
SLOW_DB_MS = 300.0
_TRACE_KEY = "_xiuxian_perf_trace"
_MATCHER_START_KEY = "_xiuxian_perf_matcher_start"
_lag_task: asyncio.Task | None = None


@dataclass
class PerfTrace:
    event_id: str
    user_id: str
    text: str
    start: float
    db_count: int = 0
    db_ms: float = 0.0
    slow_queries: list[float] = field(default_factory=list)


def _short_text(text: str, limit: int = 80) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _event_id(event: Event) -> str:
    for attr in ("event_id", "id", "message_id"):
        value = getattr(event, attr, None)
        if value:
            return str(value)
    return f"{event.__class__.__name__}:{id(event)}"


def _event_user_id(event: Event) -> str:
    try:
        return str(event.get_user_id())
    except (AttributeError, TypeError, ValueError, NotImplementedError):
        return "-"


def _event_text(event: Event) -> str:
    try:
        return _short_text(event.get_plaintext())
    except (AttributeError, TypeError, ValueError, NotImplementedError):
        return ""


def _matcher_name(matcher: Matcher) -> str:
    return matcher.module_name or matcher.__class__.__module__


def _new_trace(event: Event) -> PerfTrace:
    return PerfTrace(
        event_id=_event_id(event),
        user_id=_event_user_id(event),
        text=_event_text(event),
        start=time.perf_counter(),
    )


def _trace_fields(trace: PerfTrace) -> str:
    slow_db = ",".join(f"{ms:.1f}" for ms in trace.slow_queries[-3:]) or "-"
    return (
        f"event={trace.event_id} user={trace.user_id} text={trace.text!r} "
        f"db={trace.db_count}/{trace.db_ms:.1f}ms slow_db={slow_db}"
    )


@event_preprocessor
async def _start_perf_trace_event(event: Event, state: T_State) -> None:
    # Preprocessors run in sibling tasks, so ContextVar writes do not reach
    # handlers. A nested state value survives NoneBot's per-matcher shallow copy.
    state[_TRACE_KEY] = _new_trace(event)


@run_preprocessor
async def _start_perf_trace(
    matcher: Matcher, bot: Bot, event: Event, state: T_State
) -> None:
    trace = state.get(_TRACE_KEY)
    if trace is None:
        trace = state[_TRACE_KEY] = _new_trace(event)
    matcher.state[_TRACE_KEY] = trace
    matcher.state[_MATCHER_START_KEY] = time.perf_counter()


@run_postprocessor
async def _log_perf_trace(matcher: Matcher, exception: Exception | None) -> None:
    trace = matcher.state.get(_TRACE_KEY)
    started = matcher.state.get(_MATCHER_START_KEY)
    if trace is None or started is None:
        return

    elapsed_ms = (time.perf_counter() - trace.start) * 1000
    handler_ms = (time.perf_counter() - started) * 1000
    if not (
        exception is not None
        or elapsed_ms >= SLOW_EVENT_MS
        or trace.db_count >= MANY_DB_QUERIES
        or trace.db_ms >= SLOW_DB_MS
    ):
        return

    level = logger.warning if exception is not None or elapsed_ms >= SLOW_EVENT_MS else logger.info
    exc_name = type(exception).__name__ if exception else "-"
    level(
        f"[Perf] elapsed={elapsed_ms:.1f}ms "
        f"dispatch={(started - trace.start) * 1000:.1f}ms "
        f"handler={handler_ms:.1f}ms matcher={_matcher_name(matcher)} "
        f"{_trace_fields(trace)} exc={exc_name}"
    )


@event_postprocessor
async def _log_event_perf(state: T_State) -> None:
    trace = state.get(_TRACE_KEY)
    if trace is None:
        return
    elapsed_ms = (time.perf_counter() - trace.start) * 1000
    if elapsed_ms >= SLOW_EVENT_MS:
        logger.warning(f"[PerfEvent] elapsed={elapsed_ms:.1f}ms {_trace_fields(trace)}")


@sqlalchemy_event.listens_for(engine.sync_engine, "before_cursor_execute")
def _before_cursor_execute(
    conn: Any,
    cursor: Any,
    statement: str,
    parameters: Any,
    context: Any,
    executemany: bool,
) -> None:
    context._xiuxian_query_start = time.perf_counter()
    matcher = current_matcher.get(None)
    context._xiuxian_perf_trace = matcher.state.get(_TRACE_KEY) if matcher else None


@sqlalchemy_event.listens_for(engine.sync_engine, "after_cursor_execute")
def _after_cursor_execute(
    conn: Any,
    cursor: Any,
    statement: str,
    parameters: Any,
    context: Any,
    executemany: bool,
) -> None:
    trace = getattr(context, "_xiuxian_perf_trace", None)
    query_start = getattr(context, "_xiuxian_query_start", None)
    if trace is None or query_start is None:
        return

    elapsed_ms = (time.perf_counter() - query_start) * 1000
    trace.db_count += 1
    trace.db_ms += elapsed_ms
    if elapsed_ms >= 100.0:
        trace.slow_queries.append(elapsed_ms)


async def _monitor_loop_lag() -> None:
    while True:
        expected = time.perf_counter() + 1.0
        await asyncio.sleep(1.0)
        lag_ms = (time.perf_counter() - expected) * 1000
        if lag_ms >= SLOW_DB_MS:
            logger.warning(f"[PerfLoop] lag={lag_ms:.1f}ms")


@get_driver().on_startup
async def _start_loop_monitor() -> None:
    global _lag_task
    if _lag_task is None or _lag_task.done():
        _lag_task = asyncio.create_task(_monitor_loop_lag())


@get_driver().on_shutdown
async def _stop_loop_monitor() -> None:
    global _lag_task
    task, _lag_task = _lag_task, None
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
