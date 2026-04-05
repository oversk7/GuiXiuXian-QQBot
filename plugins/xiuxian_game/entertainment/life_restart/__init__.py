"""人生重开模拟器 - 集成自 nonebot-plugin-remake"""

import asyncio
import base64
import itertools
import random
import re
import traceback
import logging
from io import BytesIO

from nonebot import on_command
from nonebot.adapters.qq import Message, MessageEvent, MessageSegment
from nonebot.params import CommandArg
from nonebot.typing import T_State

from ...utils import message_add_head
from .drawer import draw_life, save_jpg
from .life import Life, PerAgeProperty, PerAgeResult
from .property import Summary
from .talent import Talent

logger = logging.getLogger(__name__)


def _generate_life_image(
    talents: list[Talent],
    init_prop: PerAgeProperty,
    results: list[PerAgeResult],
    summary: Summary,
) -> BytesIO:
    """在线程池中执行的图片生成（CPU密集型）"""
    return save_jpg(draw_life(talents, init_prop, results, summary))


def _random_talents_no_conflict(talents: list[Talent], count: int = 3) -> list[Talent]:
    """随机选择不冲突的天赋"""
    while True:
        nums = random.sample(range(len(talents)), count)
        nums.sort()
        selected = [talents[n] for n in nums]
        has_conflict = False
        for t1, t2 in itertools.combinations(selected, 2):
            if t1.exclusive_with(t2):
                has_conflict = True
                break
        if not has_conflict:
            return selected


def _random_attributes(total: int) -> list[int]:
    """随机分配属性点"""
    half1 = int(total / 2)
    half2 = total - half1
    n1 = random.randint(0, half1)
    n2 = random.randint(0, half2)
    nums = [n1, n2, half1 - n1, half2 - n2]
    random.shuffle(nums)
    return nums


# ─── 随机人生（一键随机，最常用） ───────────────────────

random_life_cmd = on_command(
    "随机人生", aliases={"人生重开", "人生重来", "liferestart", "remake"},
    priority=5, block=True
)


@random_life_cmd.handle()
async def handle_random_life(event: MessageEvent, args: Message = CommandArg()):
    args_text = args.extract_plain_text().strip()

    # "人生重开 选择" 进入交互模式的提示
    if args_text == "选择":
        await random_life_cmd.finish(
            message_add_head(
                "📋 交互模式请使用指令：人生选择\n"
                "可自行挑选天赋和分配属性点",
                event,
            )
        )

    await random_life_cmd.send(message_add_head("🔄 你的人生正在重开...", event))

    try:
        life = Life()
        life.load()

        # 随机选天赋
        all_talents = life.rand_talents(10)
        selected = _random_talents_no_conflict(all_talents, 3)
        life.set_talents(selected)

        # 随机分配属性
        total = life.total_property()
        nums = _random_attributes(total)
        prop = {"CHR": nums[0], "INT": nums[1], "STR": nums[2], "MNY": nums[3]}
        life.apply_property(prop)

        # 模拟人生
        init_prop = life.get_property()
        results = list(life.run())
        summary = life.gen_summary()

        # 生成图片（线程池避免阻塞）
        img_bytes: BytesIO = await asyncio.to_thread(
            _generate_life_image, selected, init_prop, results, summary
        )
        img_b64 = base64.b64encode(img_bytes.getvalue()).decode()

        img_seg = MessageSegment.file_image(img_b64)
        text_msg = message_add_head("🎴 人生重开模拟器", event)
        msg = Message(text_msg).append(img_seg)
        await random_life_cmd.finish(msg)

    except Exception:
        logger.error(f"人生重开失败:\n{traceback.format_exc()}")
        await random_life_cmd.finish(
            message_add_head("❌ 人生重开失败，请稍后再试", event)
        )


# ─── 交互模式（手动选天赋+分属性） ──────────────────────

interactive_life_cmd = on_command("人生选择", priority=5, block=True)


@interactive_life_cmd.handle()
async def handle_interactive_start(event: MessageEvent, state: T_State):
    life = Life()
    life.load()
    all_talents = life.rand_talents(10)

    state["life"] = life
    state["all_talents"] = all_talents

    talent_list = "\n".join(
        f"  {i}. {t.name}（{t.description}）" for i, t in enumerate(all_talents)
    )
    await interactive_life_cmd.send(
        message_add_head(
            f"🎲 人生重开 · 选择天赋\n"
            f"━━━━━━━━━━━━━\n"
            f"{talent_list}\n"
            f"━━━━━━━━━━━━━\n"
            f"请发送3个编号选择天赋（如：0 1 2）\n"
            f"发送「随机」随机选择 | 发送「取消」退出",
            event,
        )
    )


@interactive_life_cmd.got("talent_input")
async def handle_talent_select(event: MessageEvent, state: T_State):
    text = state["talent_input"].extract_plain_text().strip()
    all_talents: list[Talent] = state["all_talents"]
    life: Life = state["life"]

    if text == "取消":
        await interactive_life_cmd.finish(
            message_add_head("已取消人生重开", event)
        )

    if text == "随机":
        selected = _random_talents_no_conflict(all_talents, 3)
    else:
        matched = re.fullmatch(r"\s*(\d)\s*(\d)\s*(\d)\s*", text)
        if not matched:
            await interactive_life_cmd.reject(
                message_add_head("⚠️ 请发送3个编号，如「0 1 2」", event)
            )

        nums = sorted(set(int(n) for n in matched.groups()))
        if len(nums) != 3 or any(n >= len(all_talents) for n in nums):
            await interactive_life_cmd.reject(
                message_add_head("⚠️ 编号不正确，请重新选择", event)
            )

        selected = [all_talents[n] for n in nums]

        # 检查互斥
        for t1, t2 in itertools.combinations(selected, 2):
            if t1.exclusive_with(t2):
                await interactive_life_cmd.reject(
                    message_add_head(
                        f"⚠️ 「{t1.name}」和「{t2.name}」不能同时选择，请重新选",
                        event,
                    )
                )

    life.set_talents(selected)
    state["selected_talents"] = selected
    total = life.total_property()
    state["total_prop"] = total

    talent_names = "、".join(t.name for t in selected)
    await interactive_life_cmd.send(
        message_add_head(
            f"✅ 已选天赋：{talent_names}\n"
            f"━━━━━━━━━━━━━\n"
            f"请分配属性点（共 {total} 点）\n"
            f"依次为：颜值 智力 体质 家境（每项≤10）\n"
            f"如：5 5 5 5\n"
            f"发送「随机」随机分配",
            event,
        )
    )


@interactive_life_cmd.got("attr_input")
async def handle_attr_select(event: MessageEvent, state: T_State):
    text = state["attr_input"].extract_plain_text().strip()
    life: Life = state["life"]
    selected: list[Talent] = state["selected_talents"]
    total: int = state["total_prop"]

    if text == "取消":
        await interactive_life_cmd.finish(
            message_add_head("已取消人生重开", event)
        )

    if text == "随机":
        nums = _random_attributes(total)
    else:
        matched = re.fullmatch(
            r"\s*(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s*", text
        )
        if not matched:
            await interactive_life_cmd.reject(
                message_add_head("⚠️ 请发送4个数字，如「5 5 5 5」", event)
            )

        nums = [int(n) for n in matched.groups()]
        if sum(nums) != total:
            await interactive_life_cmd.reject(
                message_add_head(
                    f"⚠️ 属性之和需为 {total}，当前为 {sum(nums)}，请重新分配",
                    event,
                )
            )
        if max(nums) > 10:
            await interactive_life_cmd.reject(
                message_add_head("⚠️ 每个属性不能超过10，请重新分配", event)
            )

    prop = {"CHR": nums[0], "INT": nums[1], "STR": nums[2], "MNY": nums[3]}
    life.apply_property(prop)

    await interactive_life_cmd.send(message_add_head("🔄 你的人生正在重开...", event))

    try:
        init_prop = life.get_property()
        results = list(life.run())
        summary = life.gen_summary()

        img_bytes: BytesIO = await asyncio.to_thread(
            _generate_life_image, selected, init_prop, results, summary
        )
        img_b64 = base64.b64encode(img_bytes.getvalue()).decode()

        img_seg = MessageSegment.file_image(img_b64)
        text_msg = message_add_head("🎴 人生重开模拟器", event)
        msg = Message(text_msg).append(img_seg)
        await interactive_life_cmd.finish(msg)

    except Exception:
        logger.error(f"人生重开失败:\n{traceback.format_exc()}")
        await interactive_life_cmd.finish(
            message_add_head("❌ 人生重开失败，请稍后再试", event)
        )
