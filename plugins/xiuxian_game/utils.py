from nonebot.adapters.onebot.v11 import Message, MessageSegment, MessageEvent
from typing import Optional

def create_rich_message(content: str, event: Optional[MessageEvent] = None) -> Message:
    """
    创建带格式的富文本消息，自动添加@用户
    """
    msg = Message()
    if event:
        msg.append(MessageSegment.at(event.get_user_id()))
    msg.append(MessageSegment.text(content.strip()))
    return msg
