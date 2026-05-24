"""Lightweight per-event performance observability."""

from __future__ import annotations

import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot.message import event_preprocessor, run_postprocessor, run_preprocessor
from nonebot.typing import T_State
from sqlalchemy import event as sqlalchemy_event

from .models.db import engine


SLOW_EVENT_MS = 800.0
MANY_DB_QUERIES = 8
SLOW_DB_MS = 300.0


@dataclass
class PerfTrace:
    event_id: str
    user_id: str
    text: str
    start: float
    db_count: int = 0
    db_ms: float = 0.0
    slow_queries: list[float] = field(default_factory=list)
    logged: bool = False


_current_trace: ContextVar[PerfTrace | None] = ContextVar("xiuxian_perf_trace", default=None)


def _short_text(text: str, limit: int = 80) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _event_id(event: Event) -> str:
    for attr in ("id", "event_id", "message_id"):
        value = getattr(event, attr, None)
        if value:
            return str(value)
    return f"{event.__class__.__name__}:{id(event)}"


def _event_user_id(event: Event) -> str:
    try:
        return str(event.get_user_id())
    except Exception:
        return "-"


def _event_text(event: Event) -> str:
    try:
        return _short_text(event.get_plaintext())
    except Exception:
        return ""


def _matcher_name(matcher: Matcher) -> str:
    module = matcher.__class__.__module__
    name = matcher.__class__.__name__
    return f"{module}.{name}"


def _new_trace(event: Event) -> PerfTrace:
    return PerfTrace(
        event_id=_event_id(event),
        user_id=_event_user_id(event),
        text=_event_text(event),
        start=time.perf_counter(),
    )


@event_preprocessor
async def _start_perf_trace_event(event: Event) -> None:
    _current_trace.set(_new_trace(event))


@run_preprocessor
async def _start_perf_trace(bot: Bot, event: Event, state: T_State) -> None:
    if _current_trace.get() is None:
        _current_trace.set(_new_trace(event))


@run_postprocessor
async def _log_perf_trace(matcher: Matcher, exception: Exception | None) -> None:
    trace = _current_trace.get()
    if trace is None:
        return

    elapsed_ms = (time.perf_counter() - trace.start) * 1000
    should_log = (
        not trace.logged
        and (
            exception is not None
            or elapsed_ms >= SLOW_EVENT_MS
            or trace.db_count >= MANY_DB_QUERIES
            or trace.db_ms >= SLOW_DB_MS
        )
    )
    if not should_log:
        return

    trace.logged = True
    level = logger.warning if exception is not None or elapsed_ms >= SLOW_EVENT_MS else logger.info
    slow_db = ",".join(f"{ms:.1f}" for ms in trace.slow_queries[-3:]) or "-"
    exc_name = type(exception).__name__ if exception else "-"
    level(
        f"[Perf] elapsed={elapsed_ms:.1f}ms "
        f"db={trace.db_count}/{trace.db_ms:.1f}ms "
        f"slow_db={slow_db} "
        f"matcher={_matcher_name(matcher)} "
        f"user={trace.user_id} "
        f"text={trace.text!r} "
        f"exc={exc_name}"
    )


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


@sqlalchemy_event.listens_for(engine.sync_engine, "after_cursor_execute")
def _after_cursor_execute(
    conn: Any,
    cursor: Any,
    statement: str,
    parameters: Any,
    context: Any,
    executemany: bool,
) -> None:
    trace = _current_trace.get()
    query_start = getattr(context, "_xiuxian_query_start", None)
    if trace is None or query_start is None:
        return

    elapsed_ms = (time.perf_counter() - query_start) * 1000
    trace.db_count += 1
    trace.db_ms += elapsed_ms
    if elapsed_ms >= 100.0:
        trace.slow_queries.append(elapsed_ms)
