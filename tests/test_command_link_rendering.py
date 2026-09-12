from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.qq import Message
from nonebot.exception import FinishedException

from plugins.xiuxian_game.battle.battle_markdown import build_battle_markdown
from plugins.xiuxian_game.battle.ladder import commands as ladder
from plugins.xiuxian_game.utils_markdown import cmd


def markdown_content(message):
    segments = Message(message)
    assert [segment.type for segment in segments] == ["markdown"]
    return segments[0].data["markdown"].content


@pytest.mark.parametrize("arguments", ["", "不存在的商品"])
async def test_ladder_redemption_help_renders_shop_link(monkeypatch, arguments):
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(ladder.redeem_cmd, "finish", finish)

    with pytest.raises(FinishedException):
        await ladder.handle_redeem(SimpleNamespace(), Message(arguments))

    content = markdown_content(finish.await_args.args[0])
    assert '<qqbot-cmd-input text="斗法商店"' in content


async def test_empty_ladder_history_renders_match_link(monkeypatch):
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(ladder.ladder_main_cmd, "finish", finish)
    monkeypatch.setattr(ladder, "_append_pending_notifications", AsyncMock())
    service = SimpleNamespace(get_recent_matches=AsyncMock(return_value=[]))

    with pytest.raises(FinishedException):
        await ladder._show_history(SimpleNamespace(), None, SimpleNamespace(id="newbie"), service)

    content = markdown_content(finish.await_args.args[0])
    assert '<qqbot-cmd-input text="斗法天梯 匹配"' in content


def test_battle_card_renders_tutorial_links_outside_log_code_block():
    guide = f"🎯 **谋生之道**\n下一步：{cmd('打工')}\n{cmd('新手任务')}"
    message = build_battle_markdown(
        title="战斗结束", battle_log=["第一回合：造成10点伤害"],
        hint=f"获得战斗奖励\n{guide}", btn1="探索", btn2="面板", btn3="背包",
    )
    content = markdown_content(message)
    _, log, details = content.split("```")
    assert "第一回合" in log
    assert "<qqbot-cmd-input" not in log
    assert '<qqbot-cmd-input text="打工"' in details
    assert '<qqbot-cmd-input text="新手任务"' in details
