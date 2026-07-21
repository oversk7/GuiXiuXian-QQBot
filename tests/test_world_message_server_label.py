from datetime import datetime

from plugins.xiuxian_game.economy.merchants import _headquarters_location_hint
from plugins.xiuxian_game.economy.merchant_service import HEADQUARTERS_COORD
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.models.world_message import WorldMessage
from plugins.xiuxian_game.world.message_board import MessageScope, _format_message_lines


def _player(player_id: str, uid: int, nickname: str, server_id: int) -> Player:
    return Player(
        id=player_id,
        uid=uid,
        nickname=nickname,
        server_id=server_id,
    )


def _message(player_id: str, scope: str) -> WorldMessage:
    return WorldMessage(
        player_id=player_id,
        scope=scope,
        content="测试消息",
        created_at=datetime(2026, 1, 2, 3, 4),
    )


def test_world_channel_shows_sender_server_label():
    players = {
        "p1": _player("p1", 10001, "甲", 1),
        "p2": _player("p2", 10002, "乙", 2),
    }
    records = [_message("p1", "world"), _message("p2", "world")]

    result = _format_message_lines(
        MessageScope.WORLD, 1, 1, records, players, viewer_id="viewer"
    )

    assert "❶ **甲** [UID:10001]" in result
    assert "❷ **乙** [UID:10002]" in result


def test_guild_channel_keeps_existing_sender_format():
    player = _player("p1", 10001, "甲", 2)

    result = _format_message_lines(
        MessageScope.GUILD,
        1,
        1,
        [_message("p1", "guild")],
        {"p1": player},
        viewer_id="viewer",
    )

    assert "**甲** [UID:10001]" in result
    assert "❷" not in result


def test_headquarters_exchange_hint_uses_current_headquarters_coordinate():
    x, y = HEADQUARTERS_COORD

    assert _headquarters_location_hint() == f"风雪镇({x},{y})缉邪司总部"
    assert "(-5,390)" not in _headquarters_location_hint()
