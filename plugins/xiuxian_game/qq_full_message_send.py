"""Compatibility patch for replying to QQ full group messages.

The QQ adapter can receive ``GROUP_MESSAGE_CREATE`` events, but upstream
``Bot.send(event=...)`` does not treat them as replyable. Existing command
handlers use ``matcher.send()/finish()``, so route those sends to active group
messages when the source event is a full group message.
"""

from __future__ import annotations

from typing import Any

from nonebot.adapters.qq import Bot, MessageSegment


_PATCH_ATTR = "_xiuxian_full_group_send_patched"
_ORIGINAL_ATTR = "_xiuxian_original_send"


def _event_type(event: Any) -> str:
    event_type = getattr(event, "__type__", "")
    return str(getattr(event_type, "value", event_type))


def _get_sender_nickname(event: Any) -> str | None:
    nickname = getattr(event, "_xiuxian_nickname", None)
    if nickname:
        return nickname
    author = getattr(event, "author", None)
    return getattr(author, "username", None)


def _with_sender_mention(event: Any, message: Any) -> Any:
    nickname = _get_sender_nickname(event)
    if not nickname:
        return message
    return MessageSegment.text(f"@{nickname}\n") + message


def patch_full_group_message_send() -> None:
    if getattr(Bot, _PATCH_ATTR, False):
        return

    original_send = Bot.send

    async def send(self: Bot, event: Any, message: Any, **kwargs: Any) -> Any:
        if _event_type(event) == "GROUP_MESSAGE_CREATE":
            group_openid = getattr(event, "group_openid", None)
            if group_openid:
                return await self.send_to_group(
                    group_openid=group_openid,
                    message=_with_sender_mention(event, message),
                )

        return await original_send(self, event, message, **kwargs)

    setattr(Bot, _ORIGINAL_ATTR, original_send)
    Bot.send = send  # type: ignore[method-assign]
    setattr(Bot, _PATCH_ATTR, True)


patch_full_group_message_send()
