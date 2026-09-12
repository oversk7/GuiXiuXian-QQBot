import ast
import asyncio
import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from nonebot.exception import FinishedException


ROOT = Path(__file__).resolve().parents[1] / "plugins" / "xiuxian_game"
PACKAGE = "ai_guide_render_test"
package = ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]

sys.modules[PACKAGE] = package
try:
    spec = importlib.util.spec_from_file_location(
        f"{PACKAGE}.ai_guide_markdown", ROOT / "ai_guide_markdown.py"
    )
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
finally:
    # 原生扩展不能二次初始化，只清理本测试创建的模块别名。
    for name in list(sys.modules):
        if name == PACKAGE or name.startswith(f"{PACKAGE}."):
            del sys.modules[name]


def content(message):
    return message.data["markdown"].content


class GuideMarkdownTests(unittest.TestCase):
    def test_answer_preserves_markdown_and_links_full_command(self):
        result = content(renderer.build_guide_reply("**重点**\n- 【图鉴 铁剑】说明"))
        self.assertIn("**重点**\r- ", result)
        self.assertIn('text="图鉴 铁剑" show="图鉴 铁剑"', result)
        self.assertIn('text="问 " show="继续问"', result)
        self.assertNotIn("【图鉴 铁剑】", result)
        self.assertNotIn("\n", result)

    def test_parameter_placeholders_quotes_and_empty_brackets(self):
        result = content(renderer.build_guide_reply('【送礼 <UID> [数量]】 【查找 "名字"】 【 】'))
        self.assertIn('text="送礼 <UID> [数量]"', result)
        self.assertIn('text="查找 &quot;名字&quot;"', result)
        self.assertIn("【 】", result)

    def test_usage_and_thinking(self):
        usage = content(renderer.build_guide_usage())
        for command in ("问 ", "问 如何升级", "请问 怎么赚钱", "怎么 装备升阶", "帮助"):
            self.assertIn(f'text="{command}"', usage)
        thinking = content(renderer.build_guide_thinking())
        self.assertTrue(thinking.startswith("# "))
        self.assertIn("\r> ", thinking)

    def test_handler_sends_markdown_and_preserves_finish_control_flow(self):
        tree = ast.parse((ROOT / "ai_guide.py").read_text(encoding="utf-8"))
        handler = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                       and node.name == "handle_ai_guide")
        handler.decorator_list = []
        handler.args.defaults = []
        for arg in handler.args.args:
            arg.annotation = None
        llm_usage = ModuleType(f"{PACKAGE}.llm_usage")
        llm_usage.set_llm_usage_context = Mock()
        platform = ModuleType(f"{PACKAGE}.platform_utils")
        platform.get_unified_player = AsyncMock(return_value=SimpleNamespace(uid=1))
        session = SimpleNamespace()
        session_context = unittest.mock.MagicMock()
        session_context.__aenter__ = AsyncMock(return_value=session)
        session_context.__aexit__ = AsyncMock(return_value=False)
        matcher = SimpleNamespace(send=AsyncMock(), finish=AsyncMock(side_effect=FinishedException))
        namespace = {
            "__package__": PACKAGE,
            "ai_guide": matcher,
            "safe_session": Mock(return_value=session_context),
            "get_ai_guidance": AsyncMock(return_value="**回答**\n【帮助】"),
            "build_guide_reply": renderer.build_guide_reply,
            "build_guide_usage": renderer.build_guide_usage,
            "build_guide_thinking": renderer.build_guide_thinking,
            "aiohttp": __import__("aiohttp"),
            "asyncio": asyncio,
            "logger": Mock(),
        }
        exec(compile(ast.Module(body=[handler], type_ignores=[]), str(ROOT / "ai_guide.py"), "exec"), namespace)
        modules = {PACKAGE: package, llm_usage.__name__: llm_usage, platform.__name__: platform}
        with patch.dict(sys.modules, modules):
            with self.assertRaises(FinishedException):
                asyncio.run(namespace["handle_ai_guide"](
                    SimpleNamespace(), SimpleNamespace(extract_plain_text=lambda: "如何升级")
                ))
        matcher.send.assert_awaited_once()
        matcher.finish.assert_awaited_once()
        self.assertIn("正在思考", content(matcher.send.call_args.args[0]))
        self.assertIn("**回答**", content(matcher.finish.call_args.args[0]))
        namespace["logger"].error.assert_not_called()


if __name__ == "__main__":
    unittest.main()
