"""人生重开模拟器 - 集成自 nonebot-plugin-remake"""

import asyncio
import base64
import itertools
import random
import re
import logging
from io import BytesIO

from nonebot import on_command
from nonebot.adapters.qq import Message, MessageEvent, MessageSegment
from nonebot.params import CommandArg
from nonebot.typing import T_State

from ...utils_markdown import cmd, build_markdown
from .drawer import draw_life, save_jpg
from .life import Life, PerAgeProperty, PerAgeResult
from .property import Summary
from .talent import Talent

logger = logging.getLogger(__name__)

# ─── 天赋稀有度标识 ───────────────────────────────────

_GRADE_TAG = {3: "【金】", 2: "【紫】", 1: "【蓝】", 0: ""}


def _generate_life_image(
    talents: list[Talent],
    init_prop: PerAgeProperty,
    results: list[PerAgeResult],
    summary: Summary,
) -> BytesIO:
    return save_jpg(draw_life(talents, init_prop, results, summary))


def _random_talents_no_conflict(talents: list[Talent], count: int = 3) -> list[Talent]:
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
    half1 = int(total / 2)
    half2 = total - half1
    n1 = random.randint(0, half1)
    n2 = random.randint(0, half2)
    nums = [n1, n2, half1 - n1, half2 - n2]
    random.shuffle(nums)
    return nums


def _suggest_attr_combos(total: int) -> list[list[int]]:
    """根据总点数生成几组推荐属性分配"""
    combos = []
    # 均衡型
    base = total // 4
    remainder = total - base * 4
    balanced = [base] * 4
    for i in range(remainder):
        balanced[i] += 1
    combos.append(balanced)
    # 颜值型
    if total >= 10:
        rest = total - 10
        r = rest // 3
        rem = rest - r * 3
        c = [10, r, r, r]
        for i in range(1, 1 + rem):
            c[i] += 1
        combos.append(c)
    # 智力型
    if total >= 10:
        rest = total - 10
        r = rest // 3
        rem = rest - r * 3
        c = [r, 10, r, r]
        for i in [0, 2, 3][:rem]:
            c[i] += 1
        combos.append(c)
    # 体质型
    if total >= 10:
        rest = total - 10
        r = rest // 3
        rem = rest - r * 3
        c = [r, r, 10, r]
        for i in [0, 1, 3][:rem]:
            c[i] += 1
        combos.append(c)
    # 过滤掉超过10的
    return [c for c in combos if max(c) <= 10]


# ─── 随机人生（一键随机） ────────────────────────────────

random_life_cmd = on_command(
    "随机人生", aliases={"人生重开", "人生重来", "liferestart", "remake"},
    priority=5, block=True
)


@random_life_cmd.handle()
async def handle_random_life(event: MessageEvent, args: Message = CommandArg()):
    args_text = args.extract_plain_text().strip()

    if args_text == "选择":
        content = (
            "# 人生重开 · 交互模式\n"
            "自选天赋和分配属性点\n"
            "***\n"
            f"> {cmd('人生选择')} 开始选择"
        )
        await random_life_cmd.finish(build_markdown(content))

    await random_life_cmd.send(build_markdown("# 🔄 你的人生正在重开..."))

    life = Life()
    life.load()

    all_talents = life.rand_talents(10)
    selected = _random_talents_no_conflict(all_talents, 3)
    life.set_talents(selected)

    total = life.total_property()
    nums = _random_attributes(total)
    prop = {"CHR": nums[0], "INT": nums[1], "STR": nums[2], "MNY": nums[3]}
    life.apply_property(prop)

    init_prop = life.get_property()
    results = list(life.run())
    summary = life.gen_summary()

    try:
        img_bytes: BytesIO = await asyncio.to_thread(
            _generate_life_image, selected, init_prop, results, summary
        )
    except (OSError, ValueError) as e:
        logger.error(f"人生重开图片生成失败: {e}")
        await random_life_cmd.finish(build_markdown("# ❌ 人生重开失败\n请稍后再试"))

    img_b64 = base64.b64encode(img_bytes.getvalue()).decode()
    img_seg = MessageSegment.file_image(img_b64)

    # 结果文字摘要 + 操作按钮
    age = summary.AGE
    sum_s = summary.SUM
    content = (
        f"# 🎴 人生重开模拟器\n"
        f"享年 **{age.value}岁**（{age.judge}）| 总评 **{sum_s.value}**（{sum_s.judge}）\n"
        "***\n"
        f"> {cmd('随机人生')} 再来一次 | {cmd('人生选择')} 自选天赋 | {cmd('福利娱乐')} 返回"
    )
    msg = Message(build_markdown(content)).append(img_seg)
    await random_life_cmd.finish(msg)


# ─── 交互模式（手动选天赋+分属性） ──────────────────────

interactive_life_cmd = on_command("人生选择", priority=5, block=True)


@interactive_life_cmd.handle()
async def handle_interactive_start(event: MessageEvent, state: T_State):
    life = Life()
    life.load()
    all_talents = life.rand_talents(10)

    state["life"] = life
    state["all_talents"] = all_talents

    # 构建天赋列表 markdown
    talent_lines = []
    for i, t in enumerate(all_talents):
        tag = _GRADE_TAG.get(t.grade, "")
        talent_lines.append(f"{i}. {tag}**{t.name}** {t.description}")
    talent_text = "\n".join(talent_lines)

    # 生成几组随机推荐组合作为快捷按钮
    suggestions = []
    for _ in range(3):
        combo = _random_talents_no_conflict(all_talents, 3)
        idxs = sorted(all_talents.index(t) for t in combo)
        suggestions.append(f"{idxs[0]} {idxs[1]} {idxs[2]}")
    # 去重
    suggestions = list(dict.fromkeys(suggestions))

    btn_row = " | ".join(cmd(s) for s in suggestions)

    content = (
        "# 🎲 人生重开 · 选择天赋\n"
        "选择 **3个** 天赋编号（如 0 1 2）\n"
        "***\n"
        f"{talent_text}\n"
        "***\n"
        f"> 推荐 {btn_row}\n"
        f"> {cmd('随机')} 随机选择 | {cmd('取消')} 退出"
    )
    await interactive_life_cmd.send(build_markdown(content))


@interactive_life_cmd.got("talent_input")
async def handle_talent_select(event: MessageEvent, state: T_State):
    text = state["talent_input"].extract_plain_text().strip()
    all_talents: list[Talent] = state["all_talents"]
    life: Life = state["life"]

    if text == "取消":
        await interactive_life_cmd.finish(
            build_markdown(
                "# 已取消人生重开\n"
                "***\n"
                f"> {cmd('随机人生')} 快速开始 | {cmd('人生选择')} 重新选择"
            )
        )

    if text == "随机":
        selected = _random_talents_no_conflict(all_talents, 3)
    else:
        matched = re.fullmatch(r"\s*(\d)\s*(\d)\s*(\d)\s*", text)
        if not matched:
            await interactive_life_cmd.reject(
                build_markdown(
                    "**⚠️ 格式不对** — 请发送3个编号\n"
                    f"> 例如 {cmd('0 1 2')} 或 {cmd('随机')}"
                )
            )

        nums = sorted(set(int(n) for n in matched.groups()))
        if len(nums) != 3 or any(n >= len(all_talents) for n in nums):
            await interactive_life_cmd.reject(
                build_markdown(
                    "**⚠️ 编号不正确** — 请选择0~9之间的3个不同编号\n"
                    f"> 例如 {cmd('0 1 2')} 或 {cmd('随机')}"
                )
            )

        selected = [all_talents[n] for n in nums]

        for t1, t2 in itertools.combinations(selected, 2):
            if t1.exclusive_with(t2):
                await interactive_life_cmd.reject(
                    build_markdown(
                        f"**⚠️ 天赋冲突** — 「{t1.name}」和「{t2.name}」不能同时选择\n"
                        f"> {cmd('随机')} 随机选择 | 请重新发送编号"
                    )
                )

    life.set_talents(selected)
    state["selected_talents"] = selected
    total = life.total_property()
    state["total_prop"] = total

    talent_names = "、".join(f"**{t.name}**" for t in selected)

    # 属性分配推荐按钮
    combos = _suggest_attr_combos(total)
    labels = ["均衡", "颜值", "智力", "体质"]
    combo_btns = []
    for i, c in enumerate(combos):
        text_val = f"{c[0]} {c[1]} {c[2]} {c[3]}"
        label = labels[i] if i < len(labels) else text_val
        combo_btns.append(cmd(label, text_val))
    combo_row = " | ".join(combo_btns)

    content = (
        f"# ✅ 已选天赋\n"
        f"{talent_names}\n"
        "***\n"
        f"分配 **{total}** 点到 颜值/智力/体质/家境（每项≤10）\n"
        f"> {combo_row}\n"
        f"> {cmd('随机')} 随机分配"
    )
    await interactive_life_cmd.send(build_markdown(content))


@interactive_life_cmd.got("attr_input")
async def handle_attr_select(event: MessageEvent, state: T_State):
    text = state["attr_input"].extract_plain_text().strip()
    life: Life = state["life"]
    selected: list[Talent] = state["selected_talents"]
    total: int = state["total_prop"]

    if text == "取消":
        await interactive_life_cmd.finish(
            build_markdown(
                "# 已取消人生重开\n"
                "***\n"
                f"> {cmd('随机人生')} 快速开始 | {cmd('人生选择')} 重新选择"
            )
        )

    if text == "随机":
        nums = _random_attributes(total)
    else:
        matched = re.fullmatch(
            r"\s*(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s*", text
        )
        if not matched:
            await interactive_life_cmd.reject(
                build_markdown(
                    f"**⚠️ 格式不对** — 请发送4个数字\n"
                    f"> 例如 {cmd('5 5 5 5')} 或 {cmd('随机')}"
                )
            )

        nums = [int(n) for n in matched.groups()]
        if sum(nums) != total:
            await interactive_life_cmd.reject(
                build_markdown(
                    f"**⚠️ 点数不对** — 总和需为 {total}，当前 {sum(nums)}\n"
                    f"> {cmd('随机')} 随机分配"
                )
            )
        if max(nums) > 10:
            await interactive_life_cmd.reject(
                build_markdown(
                    f"**⚠️ 单项超限** — 每个属性不能超过10\n"
                    f"> {cmd('随机')} 随机分配"
                )
            )

    prop = {"CHR": nums[0], "INT": nums[1], "STR": nums[2], "MNY": nums[3]}
    life.apply_property(prop)

    await interactive_life_cmd.send(build_markdown("# 🔄 你的人生正在重开..."))

    init_prop = life.get_property()
    results = list(life.run())
    summary = life.gen_summary()

    try:
        img_bytes: BytesIO = await asyncio.to_thread(
            _generate_life_image, selected, init_prop, results, summary
        )
    except (OSError, ValueError) as e:
        logger.error(f"人生重开图片生成失败: {e}")
        await interactive_life_cmd.finish(
            build_markdown("# ❌ 人生重开失败\n请稍后再试")
        )

    img_b64 = base64.b64encode(img_bytes.getvalue()).decode()
    img_seg = MessageSegment.file_image(img_b64)

    age = summary.AGE
    sum_s = summary.SUM
    content = (
        f"# 🎴 人生重开模拟器\n"
        f"享年 **{age.value}岁**（{age.judge}）| 总评 **{sum_s.value}**（{sum_s.judge}）\n"
        "***\n"
        f"> {cmd('随机人生')} 再来一次 | {cmd('人生选择')} 自选天赋 | {cmd('福利娱乐')} 返回"
    )
    msg = Message(build_markdown(content)).append(img_seg)
    await interactive_life_cmd.finish(msg)
