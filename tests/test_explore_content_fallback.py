import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from nonebot.adapters.qq.exception import ActionFailed
from nonebot.drivers import Response
from nonebot.exception import FinishedException, PausedException, RejectedException

from plugins.xiuxian_game.utils_markdown import build_markdown


SOURCE = Path(__file__).resolve().parents[1] / "plugins/xiuxian_game/world/real_world_explore.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
HELPER = next(node for node in TREE.body if isinstance(node, ast.AsyncFunctionDef)
              and node.name == "_finish_explore")


def failure(code):
    return ActionFailed(Response(400, content=json.dumps({"code": code})))


def sender(side_effect=None):
    matcher = SimpleNamespace(send=AsyncMock(side_effect=side_effect),
                              finish=AsyncMock(side_effect=FinishedException()))
    namespace = {"real_explore_cmd": matcher, "ActionFailed": ActionFailed,
                 "build_markdown": build_markdown, "logger": Mock()}
    exec(compile(ast.Module(body=[HELPER], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return matcher, namespace["_finish_explore"]


async def test_success_preserves_full_detail_and_finishes_once():
    matcher, send = sender()
    with pytest.raises(FinishedException):
        await send("# Location\nNearby nickname", 12, -5)
    matcher.send.assert_awaited_once()
    assert matcher.send.call_args.args[0].data["markdown"].content == "# Location\rNearby nickname"
    matcher.finish.assert_awaited_once_with()


async def test_content_rejection_sends_coordinates_without_dynamic_content():
    matcher, send = sender([failure(40034006), None])
    with pytest.raises(FinishedException):
        await send("Rejected nickname and mansion", 12, -5)
    assert matcher.send.await_count == 2
    fallback = matcher.send.call_args.args[0]
    assert isinstance(fallback, str)
    assert "(12,-5)" in fallback
    assert "QQ" in fallback
    assert "Rejected nickname" not in fallback
    matcher.finish.assert_awaited_once_with()


@pytest.mark.parametrize("code", [304003, 304016, None])
async def test_unrelated_send_errors_propagate(code):
    error = failure(code)
    matcher, send = sender(error)
    with pytest.raises(ActionFailed) as caught:
        await send("details", 12, -5)
    assert caught.value is error
    matcher.send.assert_awaited_once()
    matcher.finish.assert_not_awaited()


@pytest.mark.parametrize("error_type", [FinishedException, PausedException, RejectedException])
async def test_flow_control_is_preserved(error_type):
    matcher, send = sender(error_type())
    with pytest.raises(error_type):
        await send("details", 12, -5)
    matcher.send.assert_awaited_once()
    matcher.finish.assert_not_awaited()


async def test_fallback_failure_propagates_without_loop():
    error = failure(40034006)
    matcher, send = sender([failure(40034006), error])
    with pytest.raises(ActionFailed) as caught:
        await send("details", 12, -5)
    assert caught.value is error
    assert matcher.send.await_count == 2
    matcher.finish.assert_not_awaited()


def test_both_location_views_use_fallback_sender():
    for name in ("show_location_info", "show_basic_location_info"):
        node = next(node for node in TREE.body if isinstance(node, ast.AsyncFunctionDef)
                    and node.name == name)
        assert any(isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                   and call.func.id == "_finish_explore" for call in ast.walk(node))
