from nonebot.adapters.qq import MessageSegment

def format_hp_bar(current: int, max: int, length: int = 10) -> str:
    filled = int(round(current / max * length))
    return f"🩸 [{'█'*filled}{'░'*(length-filled)}] {current}/{max}"

def create_rich_message(title: str, content: str) -> Message:
    return Message([
        MessageSegment.text(f"🌀 {title}\n"),
        MessageSegment.text("="*20 + "\n"),
        MessageSegment.text(content)
    ]) 