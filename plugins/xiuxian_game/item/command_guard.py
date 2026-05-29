from __future__ import annotations

from typing import Any


def event_type(event: Any) -> str:
    raw_event_type = getattr(event, "__type__", "")
    return str(getattr(raw_event_type, "value", raw_event_type))


def should_silence_unknown_inventory_item(event: Any) -> bool:
    return (
        event_type(event) == "GROUP_MESSAGE_CREATE"
        and not bool(getattr(event, "to_me", False))
        and not bool(getattr(event, "_mentioned_bot", False))
    )
