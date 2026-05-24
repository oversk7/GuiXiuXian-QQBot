"""NoneBot handlers for text-only group persona replies."""

from __future__ import annotations

from nonebot import on_message
from nonebot.adapters.qq import MessageEvent

from .service import PersonaIncomingMessage, group_persona_service


group_persona_message = on_message(priority=90, block=False)


def _author_name(event: MessageEvent) -> str:
    author = getattr(event, "author", None)
    username = getattr(author, "username", None)
    if isinstance(username, str) and username.strip():
        return username.strip()[:24]
    return event.get_user_id()


@group_persona_message.handle()
async def handle_group_persona_message(event: MessageEvent) -> None:
    group_id = getattr(event, "group_openid", None)
    if not group_id:
        return

    text = event.get_plaintext().strip()
    incoming = PersonaIncomingMessage(
        group_id=str(group_id),
        user_id=event.get_user_id(),
        username=_author_name(event),
        text=text,
        to_me=bool(getattr(event, "to_me", False)),
    )
    response = await group_persona_service.maybe_reply(incoming)
    if response:
        await group_persona_message.send(response)
