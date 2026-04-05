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

# ─── 天赋稀有度 emoji ────────────────────────────────

_GRADE_EMOJI = {3: "⭐", 2: "💜", 1: "💙", 0: ""}


def _talent_display(t: Talent) -> str:
    e = _GRADE_EMOJI.get(t.grade, "")
    return f"{e}{t.name}" if e else t.name


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
    combos = []
    base = total // 4
    remainder = total - base * 4
    balanced = [base] * 4
    for i in range(remainder):
        balanced[i] += 1
    combos.append(balanced)
    for focus_idx in range(4):
        if total >= 10:
            rest = total - 10
            r = rest // 3
            rem = rest - r * 3
            c = [r] * 4
            c[focus_idx] = 10
            j = 0
            for k in range(4):
                if k != focus_idx and j < rem:
                    c[k] += 1
                    j += 1
            combos.append(c)
    return [c for c in combos if max(c) <= 10]


def _generate_life_image(
    talents: list[Talent],
    init_prop: PerAgeProperty,
    results: list[PerAgeResult],
    summary: Summary,
) -> BytesIO:
    return save_jpg(draw_life(talents, init_prop, results, summary))


async def _send_life_result(matcher, selected, init_prop, results, summary):
    """生成图片并发送结果（图片 + markdown 按钮分两条消息）"""
    try:
        img_bytes: BytesIO = await asyncio.to_thread(
            _generate_life_image, selected, init_prop, results, summary
        )
    except (OSError, ValueError) as e:
        logger.error(f"人生重开图片生成失败: {e}")
        await matcher.finish("❌ 人生重开失败，请稍后再试")

    # 第一条：图片
    img_b64 = base64.b64encode(img_bytes.getvalue()).decode()
    await matcher.send(MessageSegment.file_image(img_b64))

    # 第二条：摘要 + 操作按钮（markdown）
    age = summary.AGE
    sum_s = summary.SUM
    content = (
        f"# 🎴 人生重开模拟器\n"
        f"享年 **{age.value}岁**（{age.judge}）| 总评 **{sum_s.value}**（{sum_s.judge}）\n"
        "***\n"
        f"> {cmd('随机人生')} 再来一次 | {cmd('人生选择')} 自选天赋 | {cmd('福利娱乐')} 返回"
    )
    await matcher.finish(build_markdown(content))


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

    await _send_life_result(random_life_cmd, selected, init_prop, results, summary)


# ─── 交互模式（手动选天赋+分属性） ──────────────────────

interactive_life_cmd = on_command("人生选择", priority=5, block=True)


def _build_talent_list_md(all_talents: list[Talent], selected_indices: list[int], warning: str = ""):
    lines = []
    for i, t in enumerate(all_talents):
        emoji = _GRADE_EMOJI.get(t.grade, "")
        prefix = f"{emoji}" if emoji else ""
        if i in selected_indices:
            lines.append(f"✅ **{i}. {prefix}{t.name}** {t.description}")
        else:
            lines.append(f"{cmd(str(i))} {prefix}**{t.name}** {t.description}")
    talent_text = "\n".join(lines)

    count = len(selected_indices)
    warn_line = f"**{warning}**\n" if warning else ""

    content = (
        f"# 🎲 人生重开 · 选择天赋（{count}/3）\n"
        f"{warn_line}"
        "点击序号选择，再点已选序号可取消\n"
        "***\n"
        f"{talent_text}\n"
        "***\n"
        f"> {cmd('随机')} 随机选择 | {cmd('取消')} 退出"
    )
    return build_markdown(content)


@interactive_life_cmd.handle()
async def handle_interactive_start(event: MessageEvent, state: T_State):
    life = Life()
    life.load()
    all_talents = life.rand_talents(10)

    state["life"] = life
    state["all_talents"] = all_talents
    state["selected_indices"] = []

    await interactive_life_cmd.send(_build_talent_list_md(all_talents, []))


@interactive_life_cmd.got("talent_input")
async def handle_talent_select(event: MessageEvent, state: T_State):
    text = state["talent_input"].extract_plain_text().strip()
    all_talents: list[Talent] = state["all_talents"]
    life: Life = state["life"]
    selected_indices: list[int] = state["selected_indices"]

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
        _proceed_to_attr(life, selected, state)
        await interactive_life_cmd.send(_build_attr_prompt(selected, state))
        return

    matched = re.fullmatch(r"\s*(\d)\s+(\d)\s+(\d)\s*", text)
    if matched:
        nums = sorted(set(int(n) for n in matched.groups()))
        if len(nums) != 3 or any(n >= len(all_talents) for n in nums):
            await interactive_life_cmd.reject(
                _build_talent_list_md(all_talents, selected_indices, "⚠️ 编号不正确，请选0~9之间的3个不同编号")
            )
        selected = [all_talents[n] for n in nums]
        for t1, t2 in itertools.combinations(selected, 2):
            if t1.exclusive_with(t2):
                await interactive_life_cmd.reject(
                    _build_talent_list_md(all_talents, selected_indices, f"⚠️ 「{t1.name}」和「{t2.name}」冲突")
                )
        _proceed_to_attr(life, selected, state)
        await interactive_life_cmd.send(_build_attr_prompt(selected, state))
        return

    if text.isdigit() and 0 <= int(text) < len(all_talents):
        idx = int(text)
        if idx in selected_indices:
            selected_indices.remove(idx)
            await interactive_life_cmd.reject(
                _build_talent_list_md(all_talents, selected_indices)
            )
        else:
            if len(selected_indices) >= 3:
                await interactive_life_cmd.reject(
                    _build_talent_list_md(all_talents, selected_indices, "⚠️ 已选满3个，点已选序号可取消")
                )
            selected_indices.append(idx)

            if len(selected_indices) == 3:
                selected = [all_talents[n] for n in sorted(selected_indices)]
                for t1, t2 in itertools.combinations(selected, 2):
                    if t1.exclusive_with(t2):
                        selected_indices.pop()
                        await interactive_life_cmd.reject(
                            _build_talent_list_md(
                                all_talents, selected_indices,
                                f"⚠️ 「{t1.name}」和「{t2.name}」冲突，已撤回"
                            )
                        )
                _proceed_to_attr(life, selected, state)
                await interactive_life_cmd.send(_build_attr_prompt(selected, state))
                return
            else:
                await interactive_life_cmd.reject(
                    _build_talent_list_md(all_talents, selected_indices)
                )

    await interactive_life_cmd.reject(
        _build_talent_list_md(all_talents, selected_indices, "⚠️ 请点击序号或发送「随机」")
    )


def _proceed_to_attr(life: Life, selected: list[Talent], state: T_State):
    life.set_talents(selected)
    state["selected_talents"] = selected
    state["total_prop"] = life.total_property()


def _build_attr_prompt(selected: list[Talent], state: T_State):
    total = state["total_prop"]
    talent_names = "、".join(f"**{_talent_display(t)}**" for t in selected)

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
    return build_markdown(content)


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

    init_prop = life.get_property()
    results = list(life.run())
    summary = life.gen_summary()

    await _send_life_result(interactive_life_cmd, selected, init_prop, results, summary)
