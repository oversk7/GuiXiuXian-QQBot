import ast
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.qq.exception import ActionFailed
from nonebot.adapters.qq.models.common import MessageMarkdown
from nonebot.drivers import Response
from nonebot.exception import FinishedException, PausedException, RejectedException


ROOT = Path(__file__).resolve().parents[1] / "plugins" / "xiuxian_game"
SPEC = importlib.util.spec_from_file_location("catalog_markdown_under_test", ROOT / "utils_markdown.py")
markdown = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(markdown)

# 隔离指令注册和数据库依赖，执行源文件中的实际发送函数。
TREE = ast.parse((ROOT / "item" / "catalog.py").read_text(encoding="utf-8"))
HELPER = next(node for node in TREE.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "_send_catalog_detail")
CONTENT = "## Item\n***\nDetails\n***\nActions"
IMAGE = "![Item #300px #163px](https://example.com/item.png)"


def action_failed(code, message="failure"):
    return ActionFailed(Response(400, content=json.dumps({"code": code, "message": message})))


def make_sender(side_effect=None):
    matcher = SimpleNamespace(
        send=AsyncMock(side_effect=side_effect),
        finish=AsyncMock(side_effect=FinishedException()),
    )
    namespace = {"catalog_cmd": matcher, "ActionFailed": ActionFailed, "build_markdown": markdown.build_markdown}
    exec(compile(ast.Module(body=[HELPER], type_ignores=[]), str(ROOT / "item" / "catalog.py"), "exec"), namespace)
    return matcher, namespace["_send_catalog_detail"]


def payload(call):
    return call.args[0].data["markdown"].dict(exclude_none=True)


def test_real_model_serialization_and_default_compatibility():
    default = markdown.build_markdown("a\nb").data["markdown"]
    disabled = markdown.build_markdown("a\nb", force_verify_image_resource=False).data["markdown"]
    verified = markdown.build_markdown("a\nb", buttons=[["Action"]], force_verify_image_resource=True)[0].data["markdown"]
    assert type(default) is MessageMarkdown
    assert default.dict(exclude_none=True) == disabled.dict(exclude_none=True) == {"content": "a\rb"}
    assert isinstance(verified, MessageMarkdown)
    assert verified.dict(exclude_none=True) == {"content": "a\rb", "force_verify_image_resource": True}


@pytest.mark.parametrize("image", [None, IMAGE])
def test_success_sends_once_then_finishes(image):
    matcher, send = make_sender()
    with pytest.raises(FinishedException):
        asyncio.run(send(CONTENT, image))
    assert matcher.send.await_count == 1
    matcher.finish.assert_awaited_once_with()
    expected = CONTENT.replace("\n", "\r")
    result = payload(matcher.send.call_args)
    if image:
        expected = expected.replace("\r", f"\r{image}\r", 1)
        assert result["force_verify_image_resource"] is True
    else:
        assert "force_verify_image_resource" not in result
    assert result["content"] == expected


def test_image_error_falls_back_once_with_identical_details():
    matcher, send = make_sender([action_failed(304010), None])
    with pytest.raises(FinishedException):
        asyncio.run(send(CONTENT, IMAGE))
    assert matcher.send.await_count == 2
    first, second = map(payload, matcher.send.call_args_list)
    assert first["force_verify_image_resource"] is True
    assert first["content"].replace(f"\r{IMAGE}", "", 1) == second["content"]
    assert second == {"content": CONTENT.replace("\n", "\r")}
    matcher.finish.assert_awaited_once_with()


@pytest.mark.parametrize("code", [304003, 304016, None])
def test_other_errors_propagate_even_with_image_error_text(code):
    error = action_failed(code, "CHANGE_IMAGE_URL 图片转存错误")
    matcher, send = make_sender(error)
    with pytest.raises(ActionFailed) as caught:
        asyncio.run(send(CONTENT, IMAGE))
    assert caught.value is error
    assert matcher.send.await_count == 1
    matcher.finish.assert_not_awaited()


@pytest.mark.parametrize("error_type", [FinishedException, PausedException, RejectedException])
def test_flow_control_exceptions_propagate(error_type):
    error = error_type()
    matcher, send = make_sender(error)
    with pytest.raises(error_type) as caught:
        asyncio.run(send(CONTENT, IMAGE))
    assert caught.value is error
    assert matcher.send.await_count == 1
    matcher.finish.assert_not_awaited()


def test_fallback_failure_is_not_retried():
    error = action_failed(304010)
    matcher, send = make_sender([action_failed(304010), error])
    with pytest.raises(ActionFailed) as caught:
        asyncio.run(send(CONTENT, IMAGE))
    assert caught.value is error
    assert matcher.send.await_count == 2
    matcher.finish.assert_not_awaited()


def test_no_image_error_is_not_retried():
    error = action_failed(304010)
    matcher, send = make_sender(error)
    with pytest.raises(ActionFailed) as caught:
        asyncio.run(send(CONTENT))
    assert caught.value is error
    assert matcher.send.await_count == 1
    matcher.finish.assert_not_awaited()
