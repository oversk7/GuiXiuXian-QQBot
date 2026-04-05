"""今天是什么小猪 - 移植自 nonebot-plugin-rollpig"""

import base64
import hashlib
import random
from datetime import datetime
from pathlib import Path

from nonebot import on_command
from nonebot.adapters.qq import Message, MessageEvent, MessageSegment
from nonebot.params import CommandArg

from ...utils_markdown import cmd, build_markdown
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
    # 尝试多种文件名格式（原始id可能有下划线或连字符）
    for pid in (pig.id, pig.id.replace("-", "_"), pig.id.replace("_", "-")):
        for ext in ("png", "jpg", "jpeg", "gif", "webp"):
            path = IMAGE_DIR / f"{pid}.{ext}"
            if path.exists():
                return base64.b64encode(path.read_bytes()).decode()
    return None


# ─── 今日小猪 ──────────────────────────────────────────

today_pig_cmd = on_command(
    "今日小猪", aliases={"今天小猪", "今天是什么小猪", "今日猪猪", "什么小猪"},
    priority=5, block=True
)


@today_pig_cmd.handle()
async def handle_today_pig(event: MessageEvent):
    user_id = event.get_user_id()
    pig = _get_today_pig(user_id)

    content = (
        f"# 今天你是——{pig.name}！\n"
        f"*{pig.description}*\n"
        "***\n"
        f"{pig.analysis}\n"
        "***\n"
        f"> {cmd('随机小猪')} 再抽一只 | {cmd('福利娱乐')} 返回"
    )

    img_b64 = _get_pig_image_b64(pig)
    if img_b64:
        msg = Message(build_markdown(content)).append(
            MessageSegment.file_image(img_b64)
        )
        await today_pig_cmd.finish(msg)
    else:
        await today_pig_cmd.finish(build_markdown(content))


# ─── 随机小猪 ──────────────────────────────────────────

random_pig_cmd = on_command("随机小猪", aliases={"随机猪猪"}, priority=5, block=True)


@random_pig_cmd.handle()
async def handle_random_pig(event: MessageEvent, args: Message = CommandArg()):
    args_text = args.extract_plain_text().strip()

    count = 1
    if args_text:
        try:
            count = int(args_text)
            count = max(1, min(count, 5))
        except ValueError:
            pass

    pigs = random.sample(PIG_POOL, min(count, len(PIG_POOL)))

    if count == 1:
        pig = pigs[0]
        content = (
            f"# {pig.name}\n"
            f"*{pig.description}*\n"
            "***\n"
            f"{pig.analysis}\n"
            "***\n"
            f"> {cmd('随机小猪')} 再来一只 | {cmd('今日小猪')} 今日猪格 | {cmd('福利娱乐')} 返回"
        )
        img_b64 = _get_pig_image_b64(pig)
        if img_b64:
            msg = Message(build_markdown(content)).append(
                MessageSegment.file_image(img_b64)
            )
            await random_pig_cmd.finish(msg)
        else:
            await random_pig_cmd.finish(build_markdown(content))
    else:
        # 多只猪，文字列表
        lines = []
        for i, pig in enumerate(pigs, 1):
            lines.append(f"**{i}. {pig.name}** — {pig.description}")
        content = (
            f"# 随机 {len(pigs)} 只小猪\n"
            + "\n".join(lines)
            + "\n***\n"
            + f"> {cmd('随机小猪')} 再来 | {cmd('今日小猪')} 今日猪格"
        )
        await random_pig_cmd.finish(build_markdown(content))
