import importlib.util
import sys
import types
from decimal import Decimal
from pathlib import Path


def _package(name):
    module = types.ModuleType(name)
    module.__path__ = []
    return module


class _DummyModel:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _DummyGuildBuildingService:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    async def get_guild_bonuses(self, guild_id):
        return {"exp_multiplier": 1.0, "treasury_limit": 100000}


def _load_guild_economy_service_new():
    module_name = "plugins.xiuxian_game.guild.guild_economy_service_new"
    project_root = Path(__file__).resolve().parents[1]
    module_path = (
        project_root
        / "plugins"
        / "xiuxian_game"
        / "guild"
        / "guild_economy_service_new.py"
    )

    stubs = {
        "plugins": _package("plugins"),
        "plugins.xiuxian_game": _package("plugins.xiuxian_game"),
        "plugins.xiuxian_game.guild": _package("plugins.xiuxian_game.guild"),
        "plugins.xiuxian_game.models": _package("plugins.xiuxian_game.models"),
        "plugins.xiuxian_game.infrastructure": _package("plugins.xiuxian_game.infrastructure"),
        "plugins.xiuxian_game.infrastructure.repositories": _package(
            "plugins.xiuxian_game.infrastructure.repositories"
        ),
        "plugins.xiuxian_game.models.guild": types.SimpleNamespace(Guild=_DummyModel),
        "plugins.xiuxian_game.models.player": types.SimpleNamespace(Player=_DummyModel),
        "plugins.xiuxian_game.models.donation_log": types.SimpleNamespace(
            PlayerDonationLog=_DummyModel
        ),
        "plugins.xiuxian_game.infrastructure.repositories.guild_repository": types.SimpleNamespace(
            GuildRepository=object
        ),
        "plugins.xiuxian_game.infrastructure.repositories.player_repository": types.SimpleNamespace(
            PlayerRepository=object
        ),
        "plugins.xiuxian_game.infrastructure.repositories.guild_building_repository": types.SimpleNamespace(
            GuildBuildingRepository=object
        ),
        "plugins.xiuxian_game.infrastructure.repositories.player_donation_log_repository": types.SimpleNamespace(
            PlayerDonationLogRepository=object
        ),
        "plugins.xiuxian_game.guild.guild_building_service_new": types.SimpleNamespace(
            GuildBuildingService=_DummyGuildBuildingService
        ),
    }

    created = []
    for name, module in stubs.items():
        if name not in sys.modules:
            sys.modules[name] = module
            created.append(name)

    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module.GuildEconomyService
    finally:
        sys.modules.pop(module_name, None)
        for name in reversed(created):
            sys.modules.pop(name, None)


def test_decimal_donation_total_still_returns_int_points():
    service = _load_guild_economy_service_new()

    points = service.calculate_donation_points(Decimal("99000"), 1000)

    assert points == 1
    assert type(points) is int


def test_decimal_donation_limit_check():
    service = _load_guild_economy_service_new()

    assert service.is_donation_points_limit_reached(Decimal("100000"))
