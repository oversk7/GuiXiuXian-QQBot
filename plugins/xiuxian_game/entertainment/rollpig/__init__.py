"""今天是什么小猪 - 移植自 nonebot-plugin-rollpig"""

import base64
import hashlib
from datetime import datetime
from pathlib import Path

from nonebot import on_command
from nonebot.adapters.qq import Message, MessageEvent, MessageSegment

from ...utils import message_add_head
from .pig_data import PIG_POOL, Pigsonality

IMAGE_DIR = Path(__file__).parent / "images"


def _get_today_pig(user_id: str) -> Pigsonality:
    """根据用户ID和日期确定性地分配今日猪格（同一天同一人结果固定）"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    seed = hashlib.md5(f"{user_id}:{date_str}".encode()).hexdigest()
    idx = int(seed, 16) % len(PIG_POOL)
    return PIG_POOL[idx]


def _get_pig_image_b64(pig: Pigsonality) -> str | None:
    """读取猪格配图并返回 base64"""
    for pid in (pig.id, pig.id.replace("-", "_"), pig.id.replace("_", "-")):
        for ext in ("png", "jpg", "jpeg", "gif", "webp"):
            path = IMAGE_DIR / f"{pid}.{ext}"
            if path.exists():
                return base64.b64encode(path.read_bytes()).decode()
    return None


today_pig_cmd = on_command(
    "今日小猪", aliases={"今天小猪", "今天是什么小猪", "今日猪猪", "什么小猪"},
    priority=5, block=True
)


@today_pig_cmd.handle()
async def handle_today_pig(event: MessageEvent):
    user_id = event.get_user_id()
    pig = _get_today_pig(user_id)

    text = message_add_head(
        f"今天你是——{pig.name}！\n"
        f"━━━━━━━━━━━━━\n"
        f"{pig.description}\n"
        f"━━━━━━━━━━━━━\n"
        f"{pig.analysis}",
        event,
    )

    img_b64 = _get_pig_image_b64(pig)
    if img_b64:
        msg = Message(text).append(MessageSegment.file_image(img_b64))
        await today_pig_cmd.finish(msg)
    else:
        await today_pig_cmd.finish(text)
