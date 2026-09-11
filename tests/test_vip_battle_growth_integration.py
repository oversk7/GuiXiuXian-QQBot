"""真实战斗入口调用公共成长结算，并保留胜败边界。"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from nonebot.exception import FinishedException

from plugins.xiuxian_game.achievement.achievement_service import AchievementService
from plugins.xiuxian_game.battle.integration_helper import BattleIntegrationHelper
from plugins.xiuxian_game.event.knocker_event import KnockerEventService
from plugins.xiuxian_game.models.npc import NPCType
from plugins.xiuxian_game.quest.novice_quest_service import NoviceQuestService
from plugins.xiuxian_game.world import attack_command as attack
from plugins.xiuxian_game.world import dungeon_battle_service as dungeon


@pytest.fixture
def battle_context(monkeypatch):
    player = SimpleNamespace(
        id="P1", nickname="测试", uid=1, hp=20, level=1, exp=0, gold=0,
        guild_id=None, dungeon_kill_streak=0, dungeon_level=0, region="大都会",
        is_in_dungeon=lambda: False,
    )
    session = Mock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    query = Mock()
    query.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=query)
    monkeypatch.setattr(AchievementService, "update_stat", AsyncMock())
    monkeypatch.setattr(AchievementService, "check_achievements", AsyncMock(return_value=[]))
    monkeypatch.setattr(NoviceQuestService, "check_and_advance_quest", AsyncMock(return_value=(False, None)))
    monkeypatch.setattr(attack, "get_player_log_mode", lambda player: "detailed")
    monkeypatch.setattr(dungeon, "get_player_log_mode", lambda player: "detailed")
    return session, player


@pytest.mark.parametrize("victory", [True, False])
async def test_npc_growth_only_runs_on_victory(monkeypatch, battle_context, victory):
    session, player = battle_context
    npc = SimpleNamespace(
        extra_data={}, npc_id="N1", name="木桩", level=1, hp=10, attack=1,
        defense=0, agility=0, npc_type=NPCType.GHOST, is_killable=True,
        respawn_duration_minutes=0, is_dead=lambda: False, is_respawning=lambda: False,
        kill=Mock(),
    )
    effects = [{"type": "gain_attack", "source_item_id": "vip_ghost_dice", "value": 2}]
    monkeypatch.setattr(KnockerEventService, "is_knocker_npc", lambda npc: False)
    monkeypatch.setattr(BattleIntegrationHelper, "enhanced_player_vs_monster_battle_v2",
                        AsyncMock(return_value=(victory, ["战斗结束"], 1, effects)))
    settle = AsyncMock(return_value=["成长已结算"])
    monkeypatch.setattr(attack, "settle_pve_victory", settle)
    monkeypatch.setattr(attack.attack_cmd, "finish", AsyncMock(side_effect=FinishedException))

    with pytest.raises(FinishedException):
        await attack.handle_npc_attack(session, player, npc, None)

    if victory:
        settle.assert_awaited_once_with(session, player, effects)
    else:
        settle.assert_not_awaited()


@pytest.mark.parametrize("victory", [True, False])
async def test_dungeon_dispatches_existing_growth_context(monkeypatch, battle_context, victory):
    session, player = battle_context
    tile = SimpleNamespace(seed="test", state={"name": "木桩", "level": 1})
    effects = [{"type": "gain_attack", "source_item_id": "vip_ghost_dice", "value": 2}]
    monkeypatch.setattr(BattleIntegrationHelper, "enhanced_player_vs_monster_battle_v2",
                        AsyncMock(return_value=(victory, ["战斗结束"], 1, effects)))
    monkeypatch.setattr(dungeon, "handle_monster_drops", AsyncMock(return_value=""))
    monkeypatch.setattr(dungeon, "check_equipment_durability", AsyncMock(return_value=""))
    win_growth = AsyncMock(return_value=["胜利成长"])
    defeat_growth = AsyncMock(return_value=["失败成长"])
    monkeypatch.setattr(dungeon, "settle_pve_victory", win_growth)
    monkeypatch.setattr(dungeon, "settle_dungeon_defeat", defeat_growth)

    result = await dungeon._handle_personal_monster(session, tile, player)

    if victory:
        win_growth.assert_awaited_once_with(session, player, effects)
        defeat_growth.assert_not_awaited()
        assert "胜利成长" in result.result_lines
    else:
        defeat_growth.assert_awaited_once_with(session, player)
        win_growth.assert_not_awaited()
        assert "失败成长" in result.result_lines


async def test_dungeon_does_not_swallow_growth_failure(monkeypatch, battle_context):
    session, player = battle_context
    tile = SimpleNamespace(seed="test", state={"name": "木桩", "level": 1})
    monkeypatch.setattr(BattleIntegrationHelper, "enhanced_player_vs_monster_battle_v2",
                        AsyncMock(return_value=(True, ["战斗结束"], 1, [])))
    monkeypatch.setattr(dungeon, "handle_monster_drops", AsyncMock(return_value=""))
    monkeypatch.setattr(dungeon, "settle_pve_victory", AsyncMock(side_effect=RuntimeError("成长失败")))

    with pytest.raises(RuntimeError, match="成长失败"):
        await dungeon._handle_personal_monster(session, tile, player)

    assert "defeated_by" not in tile.state
    session.flush.assert_not_awaited()
