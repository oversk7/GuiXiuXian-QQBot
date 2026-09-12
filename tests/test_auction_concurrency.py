import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from plugins.xiuxian_game.auction import auction_service as service
from plugins.xiuxian_game.infrastructure.uow.unit_of_work import UnitOfWork
from plugins.xiuxian_game.models import db
from plugins.xiuxian_game.models.auction import AuctionBidHistory, AuctionItem
from plugins.xiuxian_game.models.inventory import ItemConfig, ItemInstance
from plugins.xiuxian_game.models.player import Player
from tests.mysql_helpers import mysql_session_factory


def make_uow(session):
    uow = UnitOfWork(db.AsyncSessionLocal)
    uow._session = session
    return uow


@pytest.fixture
async def auction_db(mysql_session_factory, monkeypatch):
    monkeypatch.setattr(db, "AsyncSessionLocal", mysql_session_factory)
    from plugins.xiuxian_game import notification_service
    monkeypatch.setattr(notification_service, "notify_player", AsyncMock(return_value=False))
    item = ItemConfig({
        "item_id": "auction_test_inscription", "name": "并发测试铭文",
        "type": "INSCRIPTION", "description": "测试", "price": 100,
    })
    monkeypatch.setitem(service.config.items_config["by_id"], item.item_id, item)
    monkeypatch.setitem(service.config.items_config["by_name"], item.name, item)
    monkeypatch.setattr(service.EquipmentTradeService, "generate_instance_summary", lambda equipment: "测试铭文")
    async with db.safe_session() as session:
        session.add_all([
            Player(id="seller", uid=1, nickname="卖家", gold=1000),
            Player(id="buyer1", uid=2, nickname="买家一", gold=1000),
            Player(id="buyer2", uid=3, nickname="买家二", gold=1000),
        ])
    return item


async def seed_auction(item, *, expired=False, has_bidder=False, buyout_price=None):
    async with db.safe_session() as session:
        equipment = ItemInstance(
            player_id="seller", item_id=item.item_id, quantity=1,
            extra_attrs={"_frozen_for_auction": True},
        )
        session.add(equipment)
        await session.flush()
        auction = AuctionItem(
            seller_id="seller", seller_uid=1, seller_name="卖家", server_id=1,
            item_id=item.item_id, item_instance_id=equipment.id, is_instance_trade=True,
            quantity=1, start_price=100, current_price=100, buyout_price=buyout_price,
            current_bidder_id="buyer1" if has_bidder else None,
            bid_count=1 if has_bidder else 0,
            status="active", end_at=datetime.now() + timedelta(hours=-1 if expired else 1),
        )
        session.add(auction)
        if has_bidder:
            buyer = await session.get(Player, "buyer1")
            buyer.gold -= 100
        await session.flush()
        return auction.id, equipment.id


async def race_stale_requests(auction_id, operations):
    barrier = asyncio.Barrier(len(operations))

    async def run(operation):
        async with db.safe_session() as session:
            stale = await session.get(AuctionItem, auction_id)
            players = {p.id: p for p in (await session.execute(select(Player))).scalars()}
            await barrier.wait()
            return await operation(make_uow(session), stale, players)

    return await asyncio.wait_for(asyncio.gather(*(run(op) for op in operations)), timeout=15)


async def test_mysql_concurrent_bids_refund_previous_escrow(auction_db):
    auction_id, _ = await seed_auction(auction_db)
    results = await race_stale_requests(auction_id, [
        lambda uow, auction, players: service.place_bid(uow, players["buyer1"], auction_id, 100),
        lambda uow, auction, players: service.place_bid(uow, players["buyer2"], auction_id, 110),
    ])
    async with db.safe_session() as session:
        auction = await session.get(AuctionItem, auction_id)
        buyers = [(await session.get(Player, key)) for key in ("buyer1", "buyer2")]
        assert auction.current_bidder_id == "buyer2"
        assert auction.current_price == 110
        assert sum(p.gold for p in buyers) + auction.current_price == 2000
        assert buyers[0].gold == 1000
        assert auction.bid_count == sum(success for success, _ in results)
        assert (await session.execute(select(func.count()).select_from(AuctionBidHistory))).scalar_one() == auction.bid_count


@pytest.mark.parametrize('buyout_price', [None, 200])
async def test_mysql_regular_bid_does_not_wait_for_seller_wallet(auction_db, buyout_price):
    from plugins.xiuxian_game.infrastructure.locking import lock_row

    auction_id, _ = await seed_auction(auction_db, buyout_price=buyout_price)
    async with db.safe_session() as seller_session:
        await lock_row(seller_session, Player, 'seller')
        async with db.safe_session() as bidder_session:
            bidder = await bidder_session.get(Player, 'buyer1')
            success, _ = await asyncio.wait_for(
                service.place_bid(make_uow(bidder_session), bidder, auction_id, 100), timeout=2,
            )
            assert success
    async with db.safe_session() as session:
        assert (await session.get(Player, 'buyer1')).gold == 900
        assert (await session.get(Player, 'seller')).gold == 1000
        assert (await session.get(AuctionItem, auction_id)).status == 'active'


async def test_mysql_invalid_bid_does_not_lock_any_wallet(auction_db):
    from plugins.xiuxian_game.infrastructure.locking import lock_rows

    auction_id, _ = await seed_auction(auction_db)
    async with db.safe_session() as writer:
        await lock_rows(writer, Player, ['buyer1', 'buyer2', 'seller'])
        async with db.safe_session() as reader:
            bidder = await reader.get(Player, 'buyer1')
            success, _ = await asyncio.wait_for(
                service.place_bid(make_uow(reader), bidder, auction_id, 50), timeout=2,
            )
            assert not success


async def test_mysql_bid_rechecks_deadline_after_waiting_for_wallet(auction_db, monkeypatch):
    auction_id, _ = await seed_auction(auction_db)
    now = datetime.now()
    monkeypatch.setattr(service, 'datetime', SimpleNamespace(now=Mock(side_effect=[now, now + timedelta(hours=2)])))
    async with db.safe_session() as session:
        buyer = await session.get(Player, 'buyer1')
        success, message = await service.place_bid(make_uow(session), buyer, auction_id, 100)
        assert not success and '截止' in message
    async with db.safe_session() as session:
        assert (await session.get(Player, 'buyer1')).gold == 1000
        assert (await session.get(AuctionItem, auction_id)).current_bidder_id is None


async def test_mysql_same_buyer_cannot_overspend_across_auctions(auction_db):
    first_id, _ = await seed_auction(auction_db)
    second_id, _ = await seed_auction(auction_db)
    results = await race_stale_requests(first_id, [
        lambda uow, auction, players: service.place_bid(uow, players["buyer1"], first_id, 600),
        lambda uow, auction, players: service.place_bid(uow, players["buyer1"], second_id, 600),
    ])
    assert sum(success for success, _ in results) == 1
    async with db.safe_session() as session:
        assert (await session.get(Player, "buyer1")).gold == 400
        auctions = (await session.execute(select(AuctionItem))).scalars().all()
        assert sum(a.current_price for a in auctions if a.has_bidder) == 600


async def test_mysql_cancel_and_bid_share_root_lock(auction_db):
    auction_id, equipment_id = await seed_auction(auction_db)
    results = await race_stale_requests(auction_id, [
        lambda uow, auction, players: service.cancel_auction(uow, players["seller"], auction_id),
        lambda uow, auction, players: service.place_bid(uow, players["buyer1"], auction_id, 100),
    ])
    assert sum(success for success, _ in results) == 1
    async with db.safe_session() as session:
        auction = await session.get(AuctionItem, auction_id)
        equipment = await session.get(ItemInstance, equipment_id)
        buyer = await session.get(Player, "buyer1")
        if auction.status == "cancelled":
            assert auction.current_bidder_id is None
            assert buyer.gold == 1000
            assert not equipment.extra_attrs.get("_frozen_for_auction")
        else:
            assert auction.status == "active"
            assert auction.current_bidder_id == buyer.id
            assert buyer.gold == 900
            assert equipment.extra_attrs["_frozen_for_auction"]
        assert equipment.player_id == "seller"


async def test_mysql_double_settlement_pays_and_transfers_once(auction_db):
    auction_id, equipment_id = await seed_auction(auction_db, expired=True, has_bidder=True)
    results = await race_stale_requests(auction_id, [
        lambda uow, auction, players: service._settle_auction(uow, auction),
        lambda uow, auction, players: service._settle_auction(uow, auction),
    ])
    assert sum(success for success, _ in results) == 1
    async with db.safe_session() as session:
        assert (await session.get(AuctionItem, auction_id)).status == "sold"
        assert (await session.get(Player, "seller")).gold == 1100 - service.calculate_transaction_tax(100)
        assert (await session.get(Player, "buyer1")).gold == 900
        equipment = await session.get(ItemInstance, equipment_id)
        assert equipment.player_id == "buyer1"
        assert not equipment.extra_attrs.get("_frozen_for_auction")


async def test_mysql_buyout_keeps_debit_and_refunds_previous_bidder(auction_db):
    auction_id, equipment_id = await seed_auction(auction_db, has_bidder=True, buyout_price=200)
    async with db.safe_session() as session:
        buyer = await session.get(Player, "buyer2")
        success, _ = await service.place_bid(make_uow(session), buyer, auction_id, 200)
        assert success
    async with db.safe_session() as session:
        assert (await session.get(Player, "buyer1")).gold == 1000
        assert (await session.get(Player, "buyer2")).gold == 800
        assert (await session.get(Player, "seller")).gold == 1200 - service.calculate_transaction_tax(200)
        assert (await session.get(AuctionItem, auction_id)).status == "sold"
        assert (await session.get(ItemInstance, equipment_id)).player_id == "buyer2"


async def test_mysql_failed_buyout_rolls_back_all_assets(auction_db, monkeypatch):
    auction_id, equipment_id = await seed_auction(auction_db, has_bidder=True, buyout_price=200)
    monkeypatch.setattr(service, "_broadcast", AsyncMock(side_effect=SQLAlchemyError("forced failure")))
    with pytest.raises(SQLAlchemyError, match="forced failure"):
        async with db.safe_session() as session:
            buyer = await session.get(Player, "buyer2")
            await service.place_bid(make_uow(session), buyer, auction_id, 200)
    async with db.safe_session() as session:
        auction = await session.get(AuctionItem, auction_id)
        assert (auction.status, auction.current_bidder_id, auction.current_price) == ("active", "buyer1", 100)
        assert (await session.get(Player, "seller")).gold == 1000
        assert (await session.get(Player, "buyer1")).gold == 900
        assert (await session.get(Player, "buyer2")).gold == 1000
        equipment = await session.get(ItemInstance, equipment_id)
        assert equipment.player_id == "seller"
        assert equipment.extra_attrs["_frozen_for_auction"]
        assert (await session.execute(select(func.count()).select_from(AuctionBidHistory))).scalar_one() == 0


@pytest.mark.parametrize("same_instance", [True, False])
@pytest.mark.parametrize("automatic", [True, False])
async def test_mysql_listing_serializes_instance_and_seller_limit(auction_db, same_instance, automatic):
    if not same_instance:
        await seed_auction(auction_db)
        await seed_auction(auction_db)
    async with db.safe_session() as session:
        equipment = [
            ItemInstance(player_id="seller", item_id=auction_db.item_id)
            for _ in range(1 if same_instance else 2)
        ]
        session.add_all(equipment)
        await session.flush()
        ids = [equipment[0].id, equipment[0 if same_instance else 1].id]
    barrier = asyncio.Barrier(2)

    async def listing(equipment_id):
        async with db.safe_session() as session:
            seller = await session.get(Player, "seller")
            stale = await session.get(ItemInstance, equipment_id)
            await session.execute(select(AuctionItem))
            await barrier.wait()
            return await service.list_auction(
                make_uow(session), seller, auction_db.name, 100, 1,
                equipment_instance_id=None if automatic else stale.id,
            )

    results = await asyncio.wait_for(asyncio.gather(*(listing(key) for key in ids)), 15)
    assert sum(success for success, _ in results) == 1
    async with db.safe_session() as session:
        auctions = (await session.execute(select(AuctionItem))).scalars().all()
        assert len(auctions) == (1 if same_instance else 3)
        assert len({a.item_instance_id for a in auctions}) == len(auctions)


async def test_mysql_listing_does_not_wait_on_root_held_by_settlement(auction_db):
    auction_id, _ = await seed_auction(auction_db)
    from plugins.xiuxian_game.infrastructure.locking import lock_row

    async with db.safe_session() as root_session:
        await lock_row(root_session, AuctionItem, auction_id)
        with pytest.raises(SQLAlchemyError):
            async with db.safe_session() as listing_session:
                seller = await listing_session.get(Player, "seller")
                await asyncio.wait_for(service.list_auction(
                    make_uow(listing_session), seller, auction_db.name, 100, 1,
                ), timeout=5)
        assert await lock_row(root_session, Player, "seller") is not None


async def test_mysql_stale_reminder_cannot_mark_sold_auction(auction_db):
    auction_id, _ = await seed_auction(auction_db, buyout_price=200)
    async with db.safe_session() as stale_session:
        stale = await stale_session.get(AuctionItem, auction_id)
        async with db.safe_session() as session:
            buyer = await session.get(Player, "buyer1")
            assert (await service.place_bid(make_uow(session), buyer, auction_id, 200))[0]
        assert not await service.send_30min_reminder(make_uow(stale_session), auction_id)
        assert stale.status == "sold"
        assert not stale.reminded_30min


@pytest.mark.parametrize("commit_failure", [False, True])
async def test_scheduler_commits_each_auction_and_reports_failed_transaction(monkeypatch, commit_failure):
    from plugins.xiuxian_game.auction import auction_scheduler as scheduler_module

    events = []
    session_count = 0

    @asynccontextmanager
    async def uow_factory(factory):
        nonlocal session_count
        session_count += 1
        number = session_count
        session = SimpleNamespace(number=number, get=AsyncMock(side_effect=lambda model, key: SimpleNamespace(id=key)))
        uow = SimpleNamespace(session=session, auction_items=SimpleNamespace(
            find_near_ending_unreminded=AsyncMock(return_value=[]),
            find_expired_unsettled=AsyncMock(return_value=[SimpleNamespace(id=1), SimpleNamespace(id=2)]),
        ))
        events.append(("open", number))
        try:
            yield uow
            if number == 2 and commit_failure:
                raise SQLAlchemyError("failed auction")
        except SQLAlchemyError:
            events.append(("rollback", number))
            raise
        else:
            events.append(("commit", number))

    async def settle(uow, auction):
        events.append(("settle", auction.id))
        if auction.id == 1 and not commit_failure:
            raise SQLAlchemyError("failed auction")
        return True, "成交"

    async def notify(auction_id):
        events.append(("notify", auction_id))

    monkeypatch.setattr(scheduler_module, "UnitOfWork", uow_factory)
    monkeypatch.setattr(service, "_settle_auction", settle)
    monkeypatch.setattr(service, "notify_settlement", notify)
    with pytest.raises(SQLAlchemyError, match="failed auction"):
        await scheduler_module.auction_settlement_check()
    assert events == [
        ("open", 1), ("commit", 1),
        ("open", 2), ("settle", 1), ("rollback", 2),
        ("open", 3), ("settle", 2), ("commit", 3), ("notify", 2),
    ]


@pytest.mark.parametrize("commit_failure", [False, True])
async def test_bid_command_notifies_only_after_commit(monkeypatch, commit_failure):
    from plugins.xiuxian_game.auction import auction_commands as commands

    events = []
    player = SimpleNamespace(id="buyer")
    auction = SimpleNamespace(status="sold")

    @asynccontextmanager
    async def uow_factory(factory):
        yield SimpleNamespace(
            session=object(),
            auction_items=SimpleNamespace(get_by_id=AsyncMock(return_value=auction)),
        )
        if commit_failure:
            raise SQLAlchemyError("commit failed")
        events.append("commit")

    async def notify(auction_id):
        assert auction_id == 1
        events.append("notify")

    monkeypatch.setattr(commands, "UnitOfWork", uow_factory)
    monkeypatch.setattr(commands, "get_unified_player", AsyncMock(return_value=player))
    monkeypatch.setattr(commands, "message_add_head", lambda text, event: text)
    monkeypatch.setattr(commands.bid_cmd, "finish", AsyncMock())
    monkeypatch.setattr(service, "place_bid", AsyncMock(return_value=(True, "成交")))
    monkeypatch.setattr(service, "notify_settlement", notify)
    args = SimpleNamespace(extract_plain_text=lambda: "1 200")
    if commit_failure:
        with pytest.raises(SQLAlchemyError, match="commit failed"):
            await commands.handle_bid(object(), args)
        assert events == []
        commands.bid_cmd.finish.assert_not_awaited()
    else:
        await commands.handle_bid(object(), args)
        assert events == ["commit", "notify"]
        commands.bid_cmd.finish.assert_awaited_once()


@pytest.mark.parametrize("has_bidder", [False, True])
async def test_settlement_does_not_send_external_notification(monkeypatch, has_bidder):
    from plugins.xiuxian_game import notification_service

    notify = AsyncMock()
    monkeypatch.setattr(notification_service, "notify_player", notify)
    monkeypatch.setattr(service, "_transfer_auction_item", AsyncMock(return_value=True))
    monkeypatch.setattr(service, "_return_item_to_seller", AsyncMock())
    monkeypatch.setattr(service, "_broadcast", AsyncMock())
    auction = AuctionItem(
        id=1, seller_id="seller", current_bidder_id="buyer" if has_bidder else None,
        item_id="test", quantity=1, current_price=100, status="active",
    )
    players = {key: Player(id=key, nickname=key, gold=1000) for key in ("buyer", "seller")}
    session = SimpleNamespace(add=Mock(), flush=AsyncMock())
    assert (await service._settle_locked_auction(SimpleNamespace(session=session), auction, players))[0]
    assert auction.status == ("sold" if has_bidder else "expired")
    notify.assert_not_awaited()


async def test_notification_target_query_failure_propagates_before_sending(monkeypatch):
    from plugins.xiuxian_game import notification_service

    auction = SimpleNamespace(status="sold", seller_id="seller", current_bidder_id="buyer")

    @asynccontextmanager
    async def uow_factory(factory):
        yield SimpleNamespace(
            auction_items=SimpleNamespace(get_by_id=AsyncMock(return_value=auction)),
            session=SimpleNamespace(get=AsyncMock(side_effect=SQLAlchemyError("target query failed"))),
        )

    notify = AsyncMock()
    monkeypatch.setattr(service, "UnitOfWork", uow_factory)
    monkeypatch.setattr(notification_service, "notify_player", notify)
    with pytest.raises(SQLAlchemyError, match="target query failed"):
        await service.notify_settlement(1)
    notify.assert_not_awaited()


async def test_broadcast_propagates_database_failure():
    session = SimpleNamespace(add=Mock(), flush=AsyncMock(side_effect=SQLAlchemyError("failed")))
    with pytest.raises(SQLAlchemyError, match="failed"):
        await service._broadcast(session, "test")


async def test_buyout_uses_locked_players_without_refreshing_dirty_rows(monkeypatch):
    auction = AuctionItem(
        id=1, server_id=1, seller_id="seller", item_id="test", quantity=1,
        start_price=100, current_price=100, current_bidder_id="buyer1", bid_count=1,
        status="active", end_at=datetime.now() + timedelta(hours=1), buyout_price=200,
    )
    players = {
        key: Player(id=key, uid=index, nickname=key, gold=900 if key == "buyer1" else 1000, server_id=1)
        for index, key in enumerate(("seller", "buyer1", "buyer2"), 1)
    }
    calls = []

    async def lock_root(session, model, key):
        calls.append(("root", key))
        return auction

    async def lock_players(session, model, keys):
        assert model is Player
        assert set(keys) == set(players)
        assert players["buyer2"].gold == 1000
        calls.append(("players",))
        return list(players.values())

    async def settle(uow, current, locked_players, buyout):
        assert current.current_bidder_id == "buyer2"
        assert locked_players["buyer1"].gold == 1000
        assert locked_players["buyer2"].gold == 800
        assert buyout
        return True, "成交"

    monkeypatch.setattr(service, "lock_row", lock_root)
    monkeypatch.setattr(service, "lock_rows", lock_players)
    monkeypatch.setattr(service, "_settle_locked_auction", settle)
    session = SimpleNamespace(add=Mock(), flush=AsyncMock())
    uow = SimpleNamespace(session=session, auction_bid_histories=SimpleNamespace(add=AsyncMock()))
    assert (await service.place_bid(uow, players["buyer2"], 1, 200))[0]
    assert calls == [("root", 1), ("players",)]
