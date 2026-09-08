"""AI 引导的 QQ 原生 Markdown 展示。"""
import re

from .utils_markdown import build_markdown, cmd


_COMMAND_PATTERN = re.compile(r"【([^】]+)】")


def build_guide_reply(content: str):
    def link_command(match: re.Match) -> str:
        label = match.group(1).strip()
        return cmd(label) if label else match.group(0)

    return build_markdown("\n".join([
        "# 🤖 游戏助手",
        _COMMAND_PATTERN.sub(link_command, content),
        "***",
        f"{cmd('继续问', '问 ')} | {cmd('帮助')}",
    ]))


def build_guide_usage():
    return build_markdown("\n".join([
        "# 🤖 游戏助手",
        "> 为你解答《诡修仙》的游戏玩法和机制。",
        "***",
        f"用法：@机器人 {cmd('问 你的问题', '问 ')}",
        f"例如：{cmd('如何升级', '问 如何升级')} | "
        f"{cmd('怎么赚钱', '请问 怎么赚钱')} | "
        f"{cmd('装备升阶', '怎么 装备升阶')}",
        "***",
        cmd('帮助'),
    ]))


def build_guide_thinking():
    return build_markdown("# 🤖 游戏助手正在思考\n> 正在查阅游戏资料，请稍候……")
