import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from plugins.xiuxian_game.world import location_init, npc_definitions
from plugins.xiuxian_game.item import codex_world


def test_social_initializer_uses_same_definitions_as_codex(monkeypatch):
    definitions = [{
        'npc_id': 'test_mentor', 'city': '测试城', 'function': 'mentorship',
        'name': '测试师者', 'description': '测试公开介绍',
    }]
    monkeypatch.setattr(location_init, 'SOCIAL_NPCS', definitions)
    monkeypatch.setattr(codex_world, 'SOCIAL_NPCS', definitions)
    monkeypatch.setattr(location_init, 'SOCIAL_AGENT_CITIES', {})
    service = SimpleNamespace(get_npc_by_id=AsyncMock(return_value=None))
    monkeypatch.setattr(location_init, 'NPCService', lambda session: service)
    location = SimpleNamespace(id=1, has_function=lambda name: True)
    query_result = Mock()
    query_result.scalars.return_value.first.return_value = location
    session = SimpleNamespace(execute=AsyncMock(return_value=query_result), add=Mock(), delete=AsyncMock())
    assert asyncio.run(location_init.init_social_npcs(session)) == 1
    npc = session.add.call_args.args[0]
    assert npc.name == '测试师者' and npc.npc_id == 'test_mentor'
    assert npc.has_function('mentorship')
    entry = next(e for e in codex_world.get_entries() if e['name'] == npc.name)
    assert '测试城' in entry['description']


def test_shared_station_names_are_read_by_codex(monkeypatch):
    monkeypatch.setitem(npc_definitions.STATION_MASTER_NAMES, '风雪镇', '驿丞·测试变更')
    assert location_init.STATION_MASTER_NAMES['风雪镇'] == '驿丞·测试变更'
    assert any(e['name'] == '驿丞·测试变更' for e in codex_world.get_entries())
