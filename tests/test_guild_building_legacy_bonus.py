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

    # 强制替换（真模块可能已被其他测试加载），用完通过 restore() 完整还原，
    # 保证与运行顺序无关。get_guild_bonuses 内部是运行时相对导入，
    # 因此 stub 必须保留到调用结束后再还原。
    saved = {}
    for name, module in stubs.items():
        saved[name] = sys.modules.get(name)
        sys.modules[name] = module

    def restore():
        sys.modules.pop(module_name, None)
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except BaseException:
        restore()
        raise
    return module.GuildBuildingService, restore


def test_legacy_guild_bonuses_delegate_to_new_layout_service():
    service, restore = _load_legacy_guild_building_service()
    session = object()

    try:
        bonuses = asyncio.run(service.get_guild_bonuses(session, 123))
    finally:
        restore()

    assert bonuses["cultivation_bonus"] == 0.07
    assert bonuses["adjacency_descriptions"] == ["聚灵阵邻接训练场：修为加成 +2%"]
    assert _DummyNewBuildingService.created_with == {
        "guild_repo": ("guild_repo", session),
        "building_repo": ("building_repo", session),
        "item_repo": None,
    }
