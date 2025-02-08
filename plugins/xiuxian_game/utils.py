from nonebot.adapters.qq import MessageSegment, Message

def format_hp_bar(current: int, max: int, length: int = 10) -> str:
    filled = int(round(current / max * length))
    return f"🩸 [{'█'*filled}{'░'*(length-filled)}] {current}/{max}"

def create_rich_message(title: str, content: str, msg_type: str = "info") -> Message:
    colors = {
        "info": 0x00ff00,
        "warning": 0xff9900,
        "error": 0xff0000
    }
    return Message([
        MessageSegment.text(f"▰▰▰ {title} ▰▰▰\n"),
        MessageSegment.text(content),
        MessageSegment.embed(
            title="状态变化",
            color=colors.get(msg_type, 0x666666)
        )
    ]) 