"""Compatibility patch for QQ adapter full group message events.

QQ full group messages may arrive as ``GROUP_MESSAGE_CREATE`` while carrying
the same payload as ``GroupAtMessageCreateEvent``. Registering a matching event
class makes upstream ``Bot.send(event=...)`` work without send monkey patches.
"""

from nonebot.adapters.qq.event import (
    EventType,
    GroupAtMessageCreateEvent,
    register_event_class,
)


@register_event_class
class GroupMsgEvent(GroupAtMessageCreateEvent):
    __type__ = EventType.GROUP_MESSAGE_CREATE
