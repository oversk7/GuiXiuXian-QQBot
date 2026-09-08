import asyncio
import importlib.util
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def service():
    root = "plugins.xiuxian_game"
    modules = {}
    for name in ("plugins", root, f"{root}.economy", f"{root}.models",
                 f"{root}.infrastructure", f"{root}.infrastructure.repositories"):
        module = types.ModuleType(name)
        module.__path__ = []
        modules[name] = module
    for filename, classname in (
        ("bank_fund_repository", "BankFundRepository"),
        ("fund_holding_repository", "FundHoldingRepository"),
        ("bank_account_repository", "BankAccountRepository"),
        ("player_repository", "PlayerRepository"),
    ):
        modules[f"{root}.infrastructure.repositories.{filename}"] = SimpleNamespace(
            **{classname: object}
        )
    modules[f"{root}.models.bank_fund"] = SimpleNamespace(
        BankFund=SimpleNamespace, FundHolding=SimpleNamespace
    )
    modules[f"{root}.models.bank_account"] = SimpleNamespace(BankAccount=SimpleNamespace)
    modules[f"{root}.models.player"] = SimpleNamespace(Player=SimpleNamespace)
    path = Path(__file__).resolve().parents[1] / "plugins/xiuxian_game/economy/bank_fund_service.py"
    spec = importlib.util.spec_from_file_location(f"{root}.economy.bank_fund_service", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module.BankFundService(AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock())


def holding(maturity_date):
    return SimpleNamespace(
        id=1, player_id="player", fund_id=2, principal=10_000_000,
        current_value=10_000_000, accumulated_profit=0, is_active=True,
        maturity_date=maturity_date, last_settlement=datetime.now(),
    )


@pytest.mark.parametrize("days", [-1, 7])
@pytest.mark.parametrize("to_bank", [False, True])
def test_lively_redemption_rejects_fixed_without_changes(service, days, to_bank):
    item = holding(datetime.now() + timedelta(days=days))
    player = SimpleNamespace(id="player", gold=123)
    before = vars(item).copy()
    service._holding_repo.get_by_id.return_value = item

    success, message = asyncio.run(service.sell_fund(player, item.id, to_bank))

    assert not success
    assert "赎回定期" in message
    assert vars(item) == before
    assert player.gold == 123
    service._fund_repo.get_by_id.assert_not_awaited()
    service._holding_repo.update.assert_not_awaited()
    service._bank_account_repo.get_or_create.assert_not_awaited()
    service._player_repo.update.assert_not_awaited()


def test_holdings_lists_separate_fixed_and_lively(service):
    fixed = holding(datetime.now() + timedelta(days=7))
    lively = holding(None)
    service._holding_repo.get_player_holdings.return_value = [fixed, lively]

    assert asyncio.run(service.get_player_holdings("player")) == [lively]
    assert asyncio.run(service.get_player_fixed_holdings("player")) == [fixed]


def test_fixed_redemption_rejects_before_maturity(service):
    item = holding(datetime.now() + timedelta(days=7))
    player = SimpleNamespace(id="player", gold=123)
    service._holding_repo.get_by_id.return_value = item

    success, message = asyncio.run(service.redeem_fixed_weekly(player, item.id, False))

    assert not success
    assert "尚未到期" in message
    assert item.is_active
    assert player.gold == 123
    service._holding_repo.update.assert_not_awaited()
    service._fund_repo.get_by_id.assert_not_awaited()


@pytest.mark.parametrize("to_bank", [False, True])
def test_fixed_redemption_pays_once_and_removes_only_principal(service, to_bank):
    item = holding(datetime.now() - timedelta(seconds=1))
    player = SimpleNamespace(id="player", gold=123)
    bank = SimpleNamespace(balance=456)
    fund = SimpleNamespace(total_scale=10_050_000, participant_count=2)
    service._holding_repo.get_by_id.return_value = item
    service._fund_repo.get_by_id.return_value = fund
    service._bank_account_repo.get_or_create.return_value = bank

    success, _ = asyncio.run(service.redeem_fixed_weekly(player, item.id, to_bank))

    assert success
    assert not item.is_active
    assert item.accumulated_profit == 450_000
    assert item.current_value == 10_450_000
    assert fund.total_scale == 50_000
    assert fund.participant_count == 1
    assert player.gold == (123 if to_bank else 10_450_123)
    assert bank.balance == (10_450_456 if to_bank else 456)
    success, _ = asyncio.run(service.redeem_fixed_weekly(player, item.id, to_bank))
    assert not success
    assert fund.total_scale == 50_000
    service._holding_repo.update.assert_awaited_once()


def test_lively_redemption_still_works(service):
    item = holding(None)
    player = SimpleNamespace(id="player", gold=123)
    fund = SimpleNamespace(daily_return=0, total_scale=10_000_000, participant_count=1)
    service._holding_repo.get_by_id.return_value = item
    service._fund_repo.get_by_id.return_value = fund

    success, _ = asyncio.run(service.sell_fund(player, item.id, False))

    assert success
    assert not item.is_active
    assert player.gold == 9_990_123
    assert item.accumulated_profit == -10_000
