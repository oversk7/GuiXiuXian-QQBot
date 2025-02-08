from nonebot.adapters.qq import MessageSegment, Message

def format_hp_bar(current: int, max: int, length: int = 10) -> str:
    filled = int(round(current / max * length))
    return f"🩸 [{'█'*filled}{'░'*(length-filled)}] {current}/{max}"

def create_rich_message(title: str, content: str) -> Message:
    return Message([
        MessageSegment.text(f"✨ {title} ✨\n"),
        MessageSegment.text("▰"*20 + "\n"),
        MessageSegment.text(content),
        MessageSegment.text("\n" + "▰"*20),
        MessageSegment.embed(
            title="状态面板",
            description="修炼进度 | 气血循环",
            color=0x00ff00
        )
    ]) 