import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from nonebot.exception import FinishedException
from sqlalchemy import select

from plugins.xiuxian_game.economy.bank_fund_service import BankFundService
from plugins.xiuxian_game.economy.stock_service import StockService
from plugins.xiuxian_game.infrastructure.repositories.bank_account_repository import BankAccountRepository
from plugins.xiuxian_game.infrastructure.repositories.bank_fund_repository import BankFundRepository
from plugins.xiuxian_game.infrastructure.repositories.fund_holding_repository import FundHoldingRepository
from plugins.xiuxian_game.infrastructure.repositories.player_repository import PlayerRepository
from plugins.xiuxian_game.infrastructure.repositories.stock_repository import StockRepository
from plugins.xiuxian_game.infrastructure.repositories.stock_holding_repository import StockHoldingRepository
from plugins.xiuxian_game.infrastructure.repositories.stock_transaction_repository import StockTransactionRepository
from plugins.xiuxian_game.models.bank_account import BankAccount
from plugins.xiuxian_game.models.bank_fund import BankFund, FundHolding
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.models.stock import Stock, StockHolding, StockTransaction
from tests.mysql_helpers import mysql_session_factory


def fund_service(session):
    return BankFundService(BankFundRepository(session), FundHoldingRepository(session),
                           BankAccountRepository(session), PlayerRepository(session))


async def seed_players(factory, gold=100_000, balance=100_000):
    async with factory() as session:
        session.add_all([Player(id=key, uid=i, nickname=key, gold=gold)
                         for i, key in enumerate(('sender', 'receiver', 'third'), 1)])
        await session.flush()
        session.add_all([BankAccount(player_id=key, balance=balance if key == 'sender' else 0)
                         for key in ('sender', 'receiver', 'third')])
        await session.commit()


async def race(factory, *operations):
    barrier = asyncio.Barrier(len(operations))

    async def run(operation):
        async with factory() as session:
            # 两个事务都先建立 RR 快照，并保留旧对象，覆盖 identity map 复用。
            cached = []
            for model in (Player, BankAccount, FundHolding, StockHolding):
                cached.extend((await session.scalars(select(model))).all())
            await barrier.wait()
            result = await operation(session)
            await session.commit()
            return result

    return await asyncio.wait_for(asyncio.gather(*(run(op) for op in operations)), timeout=20)


@pytest.mark.parametrize('different_receivers', [False, True])
async def test_mysql_concurrent_transfers_cannot_overdraw(mysql_session_factory, different_receivers):
    factory = mysql_session_factory
    await seed_players(factory, balance=100)

    def transfer(target):
        return lambda session: BankAccountRepository(session).transfer('sender', target, 80)

    results = await race(factory, transfer('receiver'), transfer('third' if different_receivers else 'receiver'))
    assert sorted(results) == [False, True]
    async with factory() as session:
        accounts = {a.player_id: a.balance for a in (await session.scalars(select(BankAccount))).all()}
        assert accounts['sender'] == 20
        assert accounts['receiver'] + accounts['third'] == 78


async def test_mysql_two_receivers_both_get_funded_transfers(mysql_session_factory):
    factory = mysql_session_factory
    await seed_players(factory, balance=200)
    results = await race(factory,
                         lambda s: BankAccountRepository(s).transfer('sender', 'receiver', 80),
                         lambda s: BankAccountRepository(s).transfer('sender', 'third', 80))
    assert results == [True, True]
    async with factory() as session:
        accounts = {a.player_id: a.balance for a in (await session.scalars(select(BankAccount))).all()}
        assert accounts == {'sender': 40, 'receiver': 78, 'third': 78}


@pytest.mark.parametrize('fixed', [False, True])
async def test_mysql_cash_and_bank_redemption_pay_only_once(mysql_session_factory, fixed):
    factory = mysql_session_factory
    await seed_players(factory, gold=0, balance=0)
    async with factory() as session:
        fund = BankFund(fund_name='test', fund_type='fixed_weekly' if fixed else 'lively',
                        daily_return=0, total_scale=50_000, participant_count=1)
        session.add(fund)
        await session.flush()
        holding = FundHolding(player_id='sender', fund_id=fund.id, principal=50_000,
                              current_value=50_000, accumulated_profit=0, is_active=True,
                              maturity_date=datetime.now() - timedelta(days=1) if fixed else None)
        session.add(holding)
        await session.commit()
        holding_id = holding.id

    def redeem(to_bank):
        async def operation(session):
            player = await session.get(Player, 'sender')
            service = fund_service(session)
            method = service.redeem_fixed_weekly if fixed else service.sell_fund
            return (await method(player, holding_id, to_bank))[0]
        return operation

    results = await race(factory, redeem(False), redeem(True))
    assert sorted(results) == [False, True]
    async with factory() as session:
        player = await session.get(Player, 'sender')
        account = await session.get(BankAccount, 'sender')
        assert player.gold + account.balance == (52_250 if fixed else 49_950)
        holding = await session.get(FundHolding, holding_id)
        assert not holding.is_active
        fund = await session.get(BankFund, holding.fund_id)
        assert fund.participant_count == 0
        assert fund.total_scale == (0 if fixed else 50)


@pytest.mark.parametrize('fixed', [False, True])
@pytest.mark.parametrize('use_bank', [False, True])
async def test_mysql_concurrent_fund_buys_charge_each_holding(mysql_session_factory, fixed, use_bank):
    factory = mysql_session_factory
    await seed_players(factory)
    async with factory() as session:
        session.add(BankFund(fund_name='test', fund_type='fixed_weekly' if fixed else 'lively',
                             daily_return=0, total_scale=0, participant_count=0))
        await session.commit()

    async def buy(session):
        service = fund_service(session)
        method = service.buy_fixed_weekly if fixed else service.buy_fund
        return (await method(await session.get(Player, 'sender'), 50_000, use_bank))[0]

    results = await race(factory, buy, buy)
    count = 1 if fixed else 2
    assert sum(results) == count
    async with factory() as session:
        holdings = (await session.scalars(select(FundHolding))).all()
        assert len(holdings) == count
        player = await session.get(Player, 'sender')
        account = await session.get(BankAccount, 'sender')
        assert player.gold == 100_000 - (0 if use_bank else 50_000 * count)
        assert account.balance == 100_000 - (50_000 * count if use_bank else 0)
        fund = (await session.scalars(select(BankFund))).one()
        assert fund.total_scale == 50_000 * count
        assert fund.participant_count == count


async def test_mysql_transfer_commands_keep_lock_order_with_pending_activity(mysql_session_factory, monkeypatch):
    from plugins.xiuxian_game import platform_utils
    from plugins.xiuxian_game.economy import bank
    from plugins.xiuxian_game.models import db

    factory = mysql_session_factory
    await seed_players(factory, balance=200)
    async with factory() as session:
        (await session.get(BankAccount, 'receiver')).balance = 200
        await session.commit()
    barrier = asyncio.Barrier(2)

    async def get_player(session, event):
        player = await session.get(Player, event.player_id)
        player.last_active_at = datetime.now()
        await barrier.wait()
        return player

    async def finish(message):
        raise FinishedException

    monkeypatch.setattr(db, 'AsyncSessionLocal', factory)
    monkeypatch.setattr(platform_utils, 'get_unified_player', get_player)
    monkeypatch.setattr(bank.bank_transfer_cmd, 'finish', finish)
    results = await asyncio.wait_for(asyncio.gather(
        bank.handle_transfer(SimpleNamespace(player_id='sender'), SimpleNamespace(extract_plain_text=lambda: '2 80')),
        bank.handle_transfer(SimpleNamespace(player_id='receiver'), SimpleNamespace(extract_plain_text=lambda: '1 80')),
        return_exceptions=True,
    ), timeout=15)
    assert all(isinstance(result, FinishedException) for result in results), results
    async with factory() as session:
        assert (await session.get(BankAccount, 'sender')).balance == 198
        assert (await session.get(BankAccount, 'receiver')).balance == 198


async def test_mysql_daily_fund_settlement_locks_and_updates_live_holdings(mysql_session_factory, monkeypatch):
    factory = mysql_session_factory
    await seed_players(factory)
    async with factory() as session:
        fund = BankFund(fund_name='test', fund_type='lively', daily_return=0, total_scale=50_000, participant_count=1)
        session.add(fund)
        await session.flush()
        holding = FundHolding(player_id='sender', fund_id=fund.id, principal=50_000, current_value=50_000, accumulated_profit=0, is_active=True)
        session.add(holding)
        await session.commit()
        holding_id = holding.id
    monkeypatch.setattr(BankFundService, '_calculate_daily_return', lambda self: 0.02)
    async with factory() as session:
        assert await fund_service(session).daily_settlement() == (0.02, 1)
        await session.commit()
    async with factory() as session:
        assert (await session.get(FundHolding, holding_id)).current_value == 50_950


@pytest.mark.parametrize('fixed', [False, True])
async def test_mysql_fund_display_does_not_wait_for_fund_writer(mysql_session_factory, fixed):
    from plugins.xiuxian_game.infrastructure.locking import lock_row

    factory = mysql_session_factory
    async with factory() as session:
        fund = BankFund(fund_name='test', fund_type='fixed_weekly' if fixed else 'lively', total_scale=100)
        session.add(fund)
        await session.commit()
        fund_id = fund.id
    async with factory() as writer, factory() as reader:
        await lock_row(writer, BankFund, fund_id)
        service = fund_service(reader)
        lookup = service.get_or_create_fixed_weekly_fund if fixed else service.get_or_create_lively_fund
        result = await asyncio.wait_for(lookup(), timeout=2)
        assert result.id == fund_id and result.total_scale == 100


async def test_mysql_fund_writes_by_different_players_still_serialize(mysql_session_factory):
    factory = mysql_session_factory
    await seed_players(factory)
    async with factory() as session:
        session.add(BankFund(fund_name='test', fund_type='lively', total_scale=0, participant_count=0))
        await session.commit()

    async def buy(session, player_id):
        player = await session.get(Player, player_id)
        return await fund_service(session).buy_fund(player, 50_000, use_bank=False)

    results = await race(factory, lambda s: buy(s, 'sender'), lambda s: buy(s, 'receiver'))
    assert all(success for success, _ in results)
    async with factory() as session:
        fund = (await session.scalars(select(BankFund))).one()
        assert (fund.total_scale, fund.participant_count) == (100_000, 2)
        assert len((await session.scalars(select(FundHolding))).all()) == 2
        assert (await session.get(Player, 'sender')).gold == 50_000
        assert (await session.get(Player, 'receiver')).gold == 50_000


async def test_mysql_first_bank_display_creates_only_one_account(mysql_session_factory):
    from plugins.xiuxian_game.economy.bank import _get_display_account

    factory = mysql_session_factory
    async with factory() as session:
        session.add(Player(id='sender', uid=1, nickname='sender'))
        await session.commit()
    barrier = asyncio.Barrier(2)

    async def display():
        async with factory() as session:
            player = await session.get(Player, 'sender')
            await barrier.wait()
            account = await _get_display_account(session, player.id)
            await session.commit()
            return account.balance

    assert await asyncio.wait_for(asyncio.gather(display(), display()), timeout=10) == [0, 0]
    async with factory() as session:
        assert len((await session.scalars(select(BankAccount))).all()) == 1


async def test_mysql_existing_bank_display_does_not_wait_for_balance_writer(mysql_session_factory):
    from plugins.xiuxian_game.economy.bank import _get_display_account
    from plugins.xiuxian_game.infrastructure.locking import lock_row

    factory = mysql_session_factory
    await seed_players(factory)
    async with factory() as writer, factory() as reader:
        await lock_row(writer, BankAccount, 'sender')
        account = await asyncio.wait_for(_get_display_account(reader, 'sender'), timeout=2)
        assert account.balance == 100_000


async def test_mysql_failed_withdrawal_releases_locks_before_reply(mysql_session_factory, monkeypatch):
    from plugins.xiuxian_game import platform_utils
    from plugins.xiuxian_game.economy import bank
    from plugins.xiuxian_game.infrastructure.locking import lock_row
    from plugins.xiuxian_game.models import db

    factory = mysql_session_factory
    await seed_players(factory, balance=10)
    replied = []

    async def require_player(session, event, matcher):
        return await session.get(Player, 'sender')

    async def finish(message):
        async with factory() as other:
            await asyncio.wait_for(lock_row(other, Player, 'sender'), timeout=2)
            await asyncio.wait_for(lock_row(other, BankAccount, 'sender'), timeout=2)
        replied.append(message)
        raise FinishedException

    monkeypatch.setattr(db, 'AsyncSessionLocal', factory)
    monkeypatch.setattr(platform_utils, 'require_player', require_player)
    monkeypatch.setattr(bank.bank_withdraw_cmd, 'finish', finish)
    with pytest.raises(FinishedException):
        await bank.handle_withdraw(SimpleNamespace(), SimpleNamespace(extract_plain_text=lambda: '80'))
    assert replied == ['⛔ 取款金额超过存款']
    async with factory() as session:
        assert (await session.get(BankAccount, 'sender')).balance == 10


async def test_mysql_two_stock_buys_use_current_cash(mysql_session_factory):
    factory = mysql_session_factory
    await seed_players(factory, gold=10_000)
    async with factory() as session:
        session.add_all([Stock(symbol=symbol, name=symbol, stock_type='TECH',
                               base_price=100, current_price=100) for symbol in ('A', 'B')])
        await session.commit()

    def buy(symbol):
        async def operation(session):
            service = StockService(PlayerRepository(session), StockRepository(session),
                                   StockHoldingRepository(session), StockTransactionRepository(session),
                                   BankAccountRepository(session))
            return (await service.buy_stock('sender', symbol, 10))[0]
        return operation

    assert await race(factory, buy('A'), buy('B')) == [True, True]
    async with factory() as session:
        assert (await session.get(Player, 'sender')).gold == 7990
        holdings = (await session.scalars(select(StockHolding))).all()
        assert len(holdings) == 2
        assert all(h.shares == 10 and h.total_cost == 1000 for h in holdings)
        transactions = (await session.scalars(select(StockTransaction))).all()
        assert len(transactions) == 2
        assert sum(t.commission for t in transactions) == 10
