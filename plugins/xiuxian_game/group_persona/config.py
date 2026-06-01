"""Configuration helpers for the group persona feature."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import config


@dataclass(frozen=True)
class GroupPersonaConfig:
    enabled: bool = False
    group_whitelist: frozenset[str] = field(default_factory=frozenset)
    persona_name: str = "小诡"
    aliases: tuple[str, ...] = ("小诡",)
    reply_probability: float = 0.08
    mention_reply_probability: float = 1.0
    min_interval_seconds: float = 90.0
    ambient_max_wait_messages: int = 6
    ambient_window_seconds: float = 120.0
    max_history_messages: int = 30
    max_response_length: int = 120
    ignore_commands: bool = True
    timing_gate_enabled: bool = False


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def load_group_persona_config() -> GroupPersonaConfig:
    raw = config.game_config.get("group_persona", {}) or {}
    persona_name = str(raw.get("persona_name") or "小诡").strip() or "小诡"
    aliases = _as_str_list(raw.get("aliases"))
    if persona_name not in aliases:
        aliases.insert(0, persona_name)

    return GroupPersonaConfig(
        enabled=bool(raw.get("enabled", False)),
        group_whitelist=frozenset(_as_str_list(raw.get("group_whitelist"))),
        persona_name=persona_name,
        aliases=tuple(aliases),
        reply_probability=max(0.0, min(1.0, float(raw.get("reply_probability", 0.08)))),
        mention_reply_probability=max(0.0, min(1.0, float(raw.get("mention_reply_probability", 1.0)))),
        min_interval_seconds=max(0.0, float(raw.get("min_interval_seconds", 90.0))),
        ambient_max_wait_messages=max(1, int(raw.get("ambient_max_wait_messages", 6))),
        ambient_window_seconds=max(15.0, float(raw.get("ambient_window_seconds", 120.0))),
        max_history_messages=max(5, int(raw.get("max_history_messages", 30))),
        max_response_length=max(20, int(raw.get("max_response_length", 120))),
        ignore_commands=bool(raw.get("ignore_commands", True)),
        timing_gate_enabled=bool(raw.get("timing_gate_enabled", False)),
    )
