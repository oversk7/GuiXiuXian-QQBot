"""Markdown 卡片格式化：替代图片渲染的文本输出。

原先由 image_generator 渲染成长图的内容改为 QQ 原生 Markdown 卡片：
标题用一级标题，长正文放代码块，省去图片渲染与上传的等待。
"""
from __future__ import annotations

import random
import re
from collections.abc import Mapping, Sequence

from ...common.models import JsonValue, RuleDict
from .image_generator import AsyncImageGenerator

_truncate = AsyncImageGenerator._truncate_display_text

_RULE_NORM_RE = re.compile(r"[\s，,。.!！？?；;:“”\"'‘’《》【】\[\]（）()\-—…·]")


def _code_block(text: str) -> str:
    """长正文放代码块展示；防止正文里的反引号破坏围栏。"""
    body = str(text or "").replace("```", "'''").strip()
    return f"```text\n{body}\n```"


def _distort(text: str, sanity: int) -> str:
    """理智低于 30 时对文本做字符侵蚀（与原图片渲染同款效果）。"""
    if sanity >= 30 or not text:
        return text
    level = (30 - sanity) / 30.0
    if random.random() >= level * 0.3:
        return text
    chars = list(text)
    for _ in range(int(len(chars) * level * 0.2)):
        idx = random.randint(0, len(chars) - 1)
        chars[idx] = random.choice(["█", "▓", "▒", "░", "?", "!", "#"])
    return "".join(chars)


def _dedup_rule_texts(rules: Sequence[RuleDict | Mapping[str, JsonValue] | str] | None) -> list[str]:
    """提取规则文案并按“同一句话”去重（忽略空白与标点差异）。"""
    seen: set[str] = set()
    texts: list[str] = []
    for rule in rules or []:
        if isinstance(rule, Mapping):
            text = str(rule.get("text", rule.get("content", "")) or "").strip()
            if not text:
                text = str(rule or "").strip()
        else:
            text = str(rule or "").strip()
        if not text:
            continue
        key = _RULE_NORM_RE.sub("", text)
        if not key or key in seen:
            continue
        seen.add(key)
        texts.append(text)
    return texts


def scene_card(
    scene_name: str,
    background: str,
    arrival_reason: str,
    entrance_description: str = "",
) -> str:
    """剧情导入卡：背景 + 到来原因，可附开场叙事。"""
    title = str(scene_name or "").strip() or "故事开始"
    body_parts = [part for part in (str(background or "").strip(), str(arrival_reason or "").strip()) if part]
    narrative = _truncate("\n\n".join(body_parts), max_chars=360)
    entrance = str(entrance_description or "").strip()
    if entrance:
        entrance = _truncate(entrance, max_chars=360)
        narrative = f"{narrative}\n\n{'─' * 16}\n\n{entrance}" if narrative else entrance
    return f"# {title}\n{_code_block(narrative)}"


def rules_card(rules_title: str, rules: Sequence[RuleDict | Mapping[str, JsonValue] | str] | None, win_condition: str) -> str:
    """规则卡：纸面规则 + 目标。"""
    texts = _dedup_rule_texts(rules)
    lines = [f"# {str(rules_title or '').strip() or '规则'}"]
    if texts:
        lines.append(_code_block("\n\n".join(f"“{text}”" for text in texts)))
    goal = str(win_condition or "").strip()
    if goal:
        goal_line = f"最后别忘了，{goal}" if texts else goal
        lines.append(f"**{goal_line}**")
    return "\n".join(lines)


def action_result_card(
    *,
    scene_description: str,
    action_feedback: str,
    sanity: int,
    is_dead: bool,
    found_items: Sequence[str] | None = None,
    found_clues: Sequence[str] | None = None,
    new_location: str | None = None,
    random_event: str | None = None,
) -> str:
    """行动结果卡：统一叙事正文（理智 0 进入崩坏展示）。"""
    is_insane_mode = sanity == 0
    if is_insane_mode:
        parts = [
            _truncate(scene_description, max_chars=280),
            _truncate(action_feedback, max_chars=180),
        ]
        narrative_parts = [part for part in parts if part] or ["……"]
    else:
        extra_parts: list[str] = []
        items = [str(item).strip() for item in (found_items or []) if str(item).strip()]
        if items:
            extra_parts.append("你顺手带走了" + "、".join(items) + "。")
        clues = [str(item).strip() for item in (found_clues or []) if str(item).strip()]
        if clues:
            extra_parts.append("你记下了" + "、".join(clues) + "。")
        if new_location:
            extra_parts.append(f"等你停下来时，人已经到了{_truncate(new_location, max_chars=80)}。")
        if random_event:
            extra_parts.append(str(random_event).strip())
        if is_dead:
            extra_parts.append("你没能从这一回合里全身而退，怪谈已经把你吞了进去。")

        parts = [
            _truncate(scene_description, max_chars=320),
            _truncate(action_feedback, max_chars=180),
            _truncate(" ".join(part for part in extra_parts if part), max_chars=180),
        ]
        narrative_parts = [part for part in parts if part] or ["四周暂时安静下来，但事情还没有结束。"]

    narrative = "\n\n".join(_distort(part, sanity) for part in narrative_parts)
    return _code_block(narrative)


def ending_card(
    *,
    ending_title: str,
    ending_description: str,
    reasoning_analysis: str = "",
    truth_revealed: bool = False,
    hidden_truth: str | None = None,
) -> str:
    """结局卡：结局描述 + 复盘 + 隐藏真相。"""
    sections = [str(ending_description or "").strip()]
    reasoning = str(reasoning_analysis or "").strip()
    if reasoning:
        sections.append(f"── 复盘 ──\n{reasoning}")
    if truth_revealed and hidden_truth:
        sections.append(f"── 隐藏真相 ──\n{str(hidden_truth).strip()}")
    body = "\n\n".join(section for section in sections if section)
    return f"# 结局：{str(ending_title or '').strip()}\n{_code_block(body)}"


def inventory_card(
    inventory_data: Sequence[Mapping[str, JsonValue]] | Sequence[object],
    player_name: str = "玩家",
    title: str = "随身物品",
) -> str:
    """物品栏卡。"""
    lines = [f"# {player_name} 的{title}"]
    if not inventory_data:
        lines.append("（空）")
    else:
        for item in inventory_data:
            if isinstance(item, Mapping):
                name = str(item.get("name", "未知物品"))
                description = str(item.get("description", "") or "").strip()
                key_marker = "（关键）" if bool(item.get("is_key_item", False)) else ""
                lines.append(f"- **{name}**{key_marker}" + (f"：{description}" if description else ""))
            else:
                lines.append(f"- {item}")
    lines.append("***")
    lines.append("想把某件东西单独拿出来看清楚，用 `/rg 道具 <名称>`。")
    return "\n".join(lines)


def overview_card(overview_title: str, overview_text: str) -> str:
    """场景概览卡。"""
    title = str(overview_title or "").strip() or "此刻你能确认的情况"
    return f"# {title}\n{_code_block(_truncate(overview_text, max_chars=520))}"
