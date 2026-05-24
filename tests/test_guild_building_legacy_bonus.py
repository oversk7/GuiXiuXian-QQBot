import asyncio
import importlib.util
import sys
import types
from enum import Enum
from pathlib import Path


def _package(name):
    module = types.ModuleType(name)
    module.__path__ = []
    return module


class _BuildingType(str, Enum):
    EXPERIENCE_SHRINE = "EXPERIENCE_SHRINE"
    TREASURY_VAULT = "TREASURY_VAULT"
    TRAINING_GROUND = "TRAINING_GROUND"
    TELEPORT_ARRAY = "TELEPORT_ARRAY"
    ALCHEMY_ROOM = "ALCHEMY_ROOM"
    GUILD_WAREHOUSE = "GUILD_WAREHOUSE"
    SPIRIT_TOWER = "SPIRIT_TOWER"
    ARTIFACT_FORGE = "ARTIFACT_FORGE"
    REFINING_PAVILION = "REFINING_PAVILION"
    DEFENSE_WALL = "DEFENSE_WALL"


class _DummyModel:
    pass


class _DummyNewBuildingService:
    created_with = None

    def __init__(self, **kwargs):
        self.__class__.created_with = kwargs

    async def get_guild_bonuses(self, guild_id):
        return {
            "cultivation_bonus": 0.07,
            "adjacency_descriptions": ["聚灵阵邻接训练场：修为加成 +2%"],
        }


def _load_legacy_guild_building_service():
    module_name = "plugins.xiuxian_game.guild.guild_building_service"
    project_root = Path(__file__).resolve().parents[1]
    module_path = (
        project_root
        / "plugins"
        / "xiuxian_game"
        / "guild"
        / "guild_building_service.py"
    )

    stubs = {
        "plugins": _package("plugins"),
        "plugins.xiuxian_game": _package("plugins.xiuxian_game"),
        "plugins.xiuxian_game.guild": _package("plugins.xiuxian_game.guild"),
        "plugins.xiuxian_game.models": _package("plugins.xiuxian_game.models"),
        "plugins.xiuxian_game.models.guild": types.SimpleNamespace(
            Guild=_DummyModel,
            GuildBuilding=_DummyModel,
            BuildingType=_BuildingType,
        ),
        "plugins.xiuxian_game.models.inventory": types.SimpleNamespace(
            ItemInstance=_DummyModel
        ),
        "sqlalchemy": types.SimpleNamespace(
            select=lambda *args, **kwargs: None,
            and_=lambda *args, **kwargs: None,
        ),
        "sqlalchemy.ext": _package("sqlalchemy.ext"),
        "sqlalchemy.ext.asyncio": types.SimpleNamespace(AsyncSession=_DummyModel),
        "plugins.xiuxian_game.guild.guild_permission": types.SimpleNamespace(
            GuildPermission=_DummyModel
        ),
        "plugins.xiuxian_game.infrastructure": _package(
            "plugins.xiuxian_game.infrastructure"
        ),
        "plugins.xiuxian_game.infrastructure.repositories": _package(
            "plugins.xiuxian_game.infrastructure.repositories"
        ),
        "plugins.xiuxian_game.infrastructure.repositories.guild_repository": types.SimpleNamespace(
            GuildRepository=lambda session: ("guild_repo", session)
        ),
        "plugins.xiuxian_game.infrastructure.repositories.guild_building_repository": types.SimpleNamespace(
            GuildBuildingRepository=lambda session: ("building_repo", session)
        ),
        "plugins.xiuxian_game.guild.guild_building_service_new": types.SimpleNamespace(
            GuildBuildingService=_DummyNewBuildingService
        ),
    }

    created = []
    for name, module in stubs.items():
        if name not in sys.modules:
            sys.modules[name] = module
            created.append(name)

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module.GuildBuildingService, [module_name, *reversed(created)]


def test_legacy_guild_bonuses_delegate_to_new_layout_service():
    service, cleanup_modules = _load_legacy_guild_building_service()
    session = object()

    try:
        bonuses = asyncio.run(service.get_guild_bonuses(session, 123))
    finally:
        for name in cleanup_modules:
            sys.modules.pop(name, None)

    assert bonuses["cultivation_bonus"] == 0.07
    assert bonuses["adjacency_descriptions"] == ["聚灵阵邻接训练场：修为加成 +2%"]
    assert _DummyNewBuildingService.created_with == {
        "guild_repo": ("guild_repo", session),
        "building_repo": ("building_repo", session),
        "item_repo": None,
    }
