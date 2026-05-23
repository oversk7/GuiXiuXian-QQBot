"""Normalize QQ group messages before command matching.

Full group messages and @ group messages can represent the bot mention in
slightly different segment shapes. Keep command handlers simple by stripping
only the bot mention at the edges of the message before NoneBot command parsing.
"""

from __future__ import annotations

import re
from typing import Any

from nonebot.adapters.qq import Bot, MessageEvent, MessageSegment
from nonebot.message import event_preprocessor


_MENTION_RE = re.compile(r"^\s*<@!?(?P<id>[\w-]+)>\s*|\s*<@!?(?P<tail_id>[\w-]+)>\s*$")


def _event_type(event: MessageEvent) -> str:
    event_type = getattr(event, "__type__", "")
    return str(getattr(event_type, "value", event_type))


def _is_full_group_message(event: MessageEvent) -> bool:
    return _event_type(event) == "GROUP_MESSAGE_CREATE"


def _is_confirmed_other_group_mention(segment: MessageSegment, message) -> bool:
    if segment.type != "mention_user":
        return False

    mention_id = segment.data.get("user_id")
    if not mention_id:
        return False

    for other in message[1:]:
        if other.type != "group_mention_user":
            continue
        data: dict[str, Any] = other.data
        if str(data.get("id")) == str(mention_id) and not data.get("is_you"):
            return True

    return False


def _bot_id(bot: Bot) -> str | None:
    try:
        return str(bot.self_info.id)
    except Exception:
        return str(getattr(bot, "self_id", "")) or None


def _is_bot_mention(
    segment: MessageSegment,
    bot_id: str | None,
    *,
    assume_full_group_leading_mention: bool = False,
) -> bool:
    if assume_full_group_leading_mention and segment.type == "mention_user":
        return True

    if segment.type in {"group_mention_user", "mention_user", "mention_robot"}:
        data: dict[str, Any] = segment.data
        mention_id = data.get("id") or data.get("user_id") or data.get("target_id")
        return bool(data.get("is_you")) or bool(bot_id and mention_id and str(mention_id) == bot_id)

    return False


def _strip_bot_mention_text(text: str, bot_id: str | None) -> tuple[str, bool]:
    if not bot_id:
        return text, False

    changed = False

    def replace(match: re.Match[str]) -> str:
        nonlocal changed
        mentioned_id = match.group("id") or match.group("tail_id")
        if mentioned_id == bot_id:
            changed = True
            return ""
        return match.group(0)

    stripped = _MENTION_RE.sub(replace, text)
    return stripped, changed


def _lstrip_first_text(message) -> None:
    if message and message[0].type == "text":
        message[0].data["text"] = message[0].data["text"].lstrip("\xa0").lstrip()
        if not message[0].data["text"]:
            del message[0]


def _rstrip_last_text(message) -> None:
    if message and message[-1].type == "text":
        message[-1].data["text"] = message[-1].data["text"].rstrip()
        if not message[-1].data["text"]:
            del message[-1]


@event_preprocessor
async def normalize_qq_group_command_message(bot: Bot, event: MessageEvent) -> None:
    """Make both full group messages and @ messages feed the same command text."""
    group_openid = getattr(event, "group_openid", None)
    if not group_openid:
        return

    bot_id = _bot_id(bot)
    message = event.get_message()
    removed_at_me = False
    mentions_other_user = bool(
        _is_full_group_message(event)
        and message
        and _is_confirmed_other_group_mention(message[0], message)
    )

    while message and _is_bot_mention(
        message[0],
        bot_id,
        assume_full_group_leading_mention=(
            _is_full_group_message(event)
            and not mentions_other_user
        ),
    ):
        del message[0]
        removed_at_me = True
        _lstrip_first_text(message)

    while message and _is_bot_mention(message[-1], bot_id):
        del message[-1]
        removed_at_me = True
        _rstrip_last_text(message)

    for segment in message:
        if segment.type != "text":
            continue
        text, changed = _strip_bot_mention_text(segment.data["text"], bot_id)
        if changed:
            segment.data["text"] = text.strip()
            removed_at_me = True

    if not message:
        message.append(MessageSegment.text(""))

    if removed_at_me:
        event.to_me = True
        setattr(event, "_message", message)
    elif mentions_other_user:
        event.to_me = False
