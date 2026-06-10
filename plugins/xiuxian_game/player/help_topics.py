"""知识库驱动的帮助页 — data/knowledge/*.yaml 是帮助内容的唯一来源。

yaml 新增两个可选字段（没有这两个字段的 yaml 仅供 AI 检索，不注册命令）：
  help_command: "钓鱼系统"      # 注册的帮助命令名
  help_aliases: ["钓鱼帮助"]    # 命令别名（可选）

body 渲染规则（纯文本 → QQ 原生 Markdown）：
  - 页首插入 "# {title}"，body 内不要再写标题行
  - 整行 ━/─/= 分隔线 → ***
  - 【命令】 → 可点击蓝字；【命令 参数】 → 点击预填 "命令 " 让玩家补参数
  - 其余行原样保留（body 内可直接写 **加粗** 等 Markdown）
"""
import re
from pathlib import Path

import yaml
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent

from ..utils_markdown import cmd, build_markdown

KNOWLEDGE_DIR = Path(__file__).parent.parent / "data" / "knowledge"

_CMD_TAG = re.compile(r"【([^】\n]+)】")
_SEPARATOR = re.compile(r"^[━─—=\-]{3,}$")


def _cmd_tag_to_button(match: re.Match) -> str:
    label = match.group(1).strip()
    if not label:
        return match.group(0)
    first_word = label.split()[0]
    if first_word != label:
        # 带参数示例的命令，点击后预填命令名等待补参数
        return cmd(label, first_word + " ")
    return cmd(label)


def render_topic(title: str, body: str) -> str:
    """把知识库 body 渲染成帮助页 Markdown"""
    lines = [f"# {title}"]
    for line in body.rstrip().splitlines():
        if _SEPARATOR.match(line.strip()):
            lines.append("***")
        else:
            lines.append(_CMD_TAG.sub(_cmd_tag_to_button, line))
    return "\n".join(lines)


def _register_topic(name: str, aliases: list, content: str) -> None:
    matcher = on_command(name, aliases=set(aliases), block=True, priority=5)

    @matcher.handle()
    async def _(event: MessageEvent):
        await matcher.finish(build_markdown(content))


def _load_all_topics() -> int:
    count = 0
    for path in sorted(KNOWLEDGE_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not data or not data.get("help_command"):
            continue
        title = data.get("title") or data["help_command"]
        content = render_topic(title, data.get("body", ""))
        _register_topic(data["help_command"], data.get("help_aliases") or [], content)
        count += 1
    return count


TOPIC_COUNT = _load_all_topics()
