"""
拍卖行核心服务

功能：
1. 上架拍卖 - 验证物品类型、冻结物品、创建拍卖条目
2. 出价竞拍 - 验证出价、退还旧出价人金币、冻结新出价金币
3. 撤拍     - 仅允许无人出价时撤拍，退还物品
4. 结算     - 有人竞得时转移物品+结算金币；流拍时退还物品
5. 留言板广播 - 上架、30分钟提醒、结束时系统广播
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Tuple

from nonebot import logger
from sqlalchemy import select

from ..economy.market import calculate_transaction_tax
from ..economy.equipment_trade_service_new import EquipmentTradeService as EquipmentTradeServiceNew
from ..economy.equipment_trade_service import EquipmentTradeService
from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.repositories.market_order_repository import MarketOrderRepository
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.auction import AuctionItem, AuctionBidHistory
from ..models.inventory import ItemInstance, ItemType
from ..models.player import Player
from ..models.world_message import WorldMessage
from ..config import config

# ==================== 常量 ====================

MAX_AUCTION_LISTINGS = 3         # 每人最多同时上架拍卖品数量
MIN_DURATION_HOURS = 1           # 最短拍卖时长（小时）
MAX_DURATION_HOURS = 72          # 最长拍卖时长（小时）
MIN_BID_RATIO = 1.05             # 每次出价至少高于当前价的比例


def _make_item_display(auction: AuctionItem) -> str:
    """生成物品展示文本"""
    item_cfg = config.items_config["by_id"].get(auction.item_id)
    item_name = item_cfg.get_display_name() if item_cfg else auction.item_id
    if auction.is_instance_trade and auction.equipment_summary:
        return f"{item_name}（{auction.equipment_summary}）"
    if auction.quantity > 1:
        return f"{item_name} ×{auction.quantity}"
    return item_name


async def _broadcast(session, content: str):
    """向世界留言板发送系统广播"""
    try:
        msg = WorldMessage(
            player_id="SYSTEM",
            recipient_id=None,
            content=content,
            created_at=datetime.now(),
        )
        session.add(msg)
        await session.flush()
    except Exception as e:
        logger.error(f"[拍卖行] 广播失败: {e}")


# ==================== 上架拍卖 ====================

async def list_auction(
    uow: UnitOfWork,
    seller: Player,
    item_name: str,
    start_price: int,
    duration_hours: int,
    buyout_price: Optional[int] = None,
    equipment_instance_id: Optional[int] = None,
) -> Tuple[bool, str]:
    """
    上架拍卖

    支持：
    - 普通物品（1件）：从背包扣除
    - 装备实例：冻结装备

    Args:
        uow: 工作单元
        seller: 卖家玩家对象
        item_name: 物品名称
        start_price: 起拍价
        duration_hours: 拍卖时长（小时）
        buyout_price: 一口价（None表示不设置）
        equipment_instance_id: 装备实例ID（仅装备拍卖时使用，None则自动选择）

    Returns:
        (success, message)
    """
    # 1. 参数验证
    if not (MIN_DURATION_HOURS <= duration_hours <= MAX_DURATION_HOURS):
        return False, f"⛔ 拍卖时长必须在 {MIN_DURATION_HOURS}~{MAX_DURATION_HOURS} 小时之间"

    if buyout_price is not None and buyout_price <= start_price:
        return False, "⛔ 一口价必须高于起拍价"

    # 2. 查找物品配置
    item_cfg = config.items_config["by_name"].get(item_name)
    if not item_cfg:
        return False, f"⛔ 未找到物品「{item_name}」"

    # 3. 禁止拍卖跑商商品（GOODS类型）
    if item_cfg.type == ItemType.GOODS:
        return False, "⛔ 跑商商品不能上架拍卖行，请前往市集交易"

    # 4. 检查卖家活跃拍卖数量
    active_auctions = await uow.auction_items.find_seller_active_auctions(seller.id)
    if len(active_auctions) >= MAX_AUCTION_LISTINGS:
        return False, f"⛔ 你已有 {MAX_AUCTION_LISTINGS} 件物品正在拍卖，无法继续上架"

    # 5. 根据物品类型分支处理
    if item_cfg.type == ItemType.EQUIPMENT:
        return await _list_equipment_auction(
            uow, seller, item_cfg, start_price, duration_hours, buyout_price,
            equipment_instance_id=equipment_instance_id,
        )
    else:
        return await _list_normal_auction(
            uow, seller, item_cfg, start_price, duration_hours, buyout_price
        )


async def _list_equipment_auction(
    uow, seller, item_cfg, start_price, duration_hours, buyout_price,
    equipment_instance_id: Optional[int] = None,
) -> Tuple[bool, str]:
    """上架装备拍卖"""
    session = uow.session

    if equipment_instance_id is not None:
        # 命令层已选好具体实例，直接使用
        equipment = await session.get(ItemInstance, equipment_instance_id)
        if not equipment or equipment.player_id != seller.id:
            return False, "⛔ 装备实例不存在或不属于你"
        if equipment.equipped:
            return False, "⛔ 该装备正在装备中，无法上架"
        extra = equipment.extra_attrs or {}
        if extra.get("_frozen_for_trade") or extra.get("_frozen_for_auction"):
            return False, "⛔ 该装备已在交易中，无法上架"
    else:
        # 兜底：自动选择第一件可用装备（背包只有一件时命令层也会走这里）
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == seller.id,
            ItemInstance.item_id == item_cfg.item_id,
            ItemInstance.equipped == False,
        )
        result = await session.execute(stmt)
        candidates = result.scalars().all()
        available = [
            e for e in candidates
            if not (e.extra_attrs or {}).get("_frozen_for_trade")
            and not (e.extra_attrs or {}).get("_frozen_for_auction")
        ]
        if not available:
            return False, f"⛔ 背包中没有可拍卖的「{item_cfg.name}」（请确认未装备且未在市场挂牌）"
        equipment = available[0]

    # 检查起拍价不低于系统估价下界
    min_price, _ = EquipmentTradeService.calculate_equipment_value_range(equipment)
    if min_price > 0 and start_price < min_price:
        return False, f"⛔ 起拍价不能低于系统估价 {min_price:,}💰\n💡 使用【估价 装备名/编号】查看详细估价"

    # 检查是否已在市场挂牌
    existing_order = await uow.auction_items.find_by_equipment_instance(equipment.id)
    if existing_order:
        return False, "⛔ 该装备已在拍卖行中"

    # 冻结装备（拍卖专用标记）
    extra_attrs = equipment.extra_attrs or {}
    extra_attrs["_frozen_for_auction"] = True
    equipment.extra_attrs = extra_attrs
    session.add(equipment)
    await session.flush()

    # 生成装备摘要
    summary = EquipmentTradeService.generate_equipment_summary(equipment)

    # 创建拍卖条目
    end_at = datetime.now() + timedelta(hours=duration_hours)
    auction = AuctionItem(
        seller_id=seller.id,
        seller_name=seller.nickname,
        item_id=item_cfg.item_id,
        quantity=1,
        is_instance_trade=True,
        item_instance_id=equipment.id,
        equipment_summary=summary,
        start_price=start_price,
        current_price=start_price,
        buyout_price=buyout_price,
        current_bidder_id=None,
        bid_count=0,
        end_at=end_at,
        status="active",
    )
    await uow.auction_items.add(auction)

    # 广播
    item_display = _make_item_display(auction)
    end_str = end_at.strftime("%m-%d %H:%M")
    await _broadcast(
        session,
        f"🔨 [拍卖行] {seller.nickname} 发起拍卖！\n"
        f"📦 {item_display}\n"
        f"💰 起拍价：{start_price:,}💰"
        + (f"  一口价：{buyout_price:,}💰" if buyout_price else "")
        + f"\n⏰ 截止：{end_str}  编号：#{auction.id}\n"
        f"📣 发送【出价 {auction.id} 金额】参与竞价"
    )

    return True, (
        f"✅ 装备已上架拍卖！\n"
        f"📦 {item_display}\n"
        f"💰 起拍价：{start_price:,}💰"
        + (f"  一口价：{buyout_price:,}💰" if buyout_price else "")
        + f"\n⏰ 截止：{end_str}\n"
        f"🆔 拍卖编号：#{auction.id}"
    )


async def _list_normal_auction(
    uow, seller, item_cfg, start_price, duration_hours, buyout_price
) -> Tuple[bool, str]:
    """上架普通物品拍卖（固定1件）"""
    session = uow.session
    quantity = 1

    # 检查起拍价不低于物品基础价格（系统估价）
    base_price = getattr(item_cfg, "price", 0) or 0
    if base_price > 0 and start_price < base_price:
        return False, f"⛔ 起拍价不能低于系统估价 {base_price:,}💰\n💡 使用【图鉴 {item_cfg.name}】查看物品基础价值"

    # 检查背包中是否有该物品
    stmt = select(ItemInstance).where(
        ItemInstance.player_id == seller.id,
        ItemInstance.item_id == item_cfg.item_id,
    )
    result = await session.execute(stmt)
    stacks = result.scalars().all()
    total_qty = sum(s.quantity for s in stacks)
    if total_qty < quantity:
        return False, f"⛔ 背包中没有「{item_cfg.name}」"

    # 从背包扣除
    try:
        await ItemInstance.consume_item(session, seller.id, item_cfg.item_id, quantity)
    except ValueError as e:
        return False, f"⛔ 扣除物品失败：{e}"

    # 创建拍卖条目
    end_at = datetime.now() + timedelta(hours=duration_hours)
    auction = AuctionItem(
        seller_id=seller.id,
        seller_name=seller.nickname,
        item_id=item_cfg.item_id,
        quantity=quantity,
        is_instance_trade=False,
        item_instance_id=None,
        equipment_summary=None,
        start_price=start_price,
        current_price=start_price,
        buyout_price=buyout_price,
        current_bidder_id=None,
        bid_count=0,
        end_at=end_at,
        status="active",
    )
    await uow.auction_items.add(auction)

    # 广播
    item_display = _make_item_display(auction)
    end_str = end_at.strftime("%m-%d %H:%M")
    await _broadcast(
        session,
        f"🔨 [拍卖行] {seller.nickname} 发起拍卖！\n"
        f"📦 {item_display}\n"
        f"💰 起拍价：{start_price:,}💰"
        + (f"  一口价：{buyout_price:,}💰" if buyout_price else "")
        + f"\n⏰ 截止：{end_str}  编号：#{auction.id}\n"
        f"📣 发送【出价 {auction.id} 金额】参与竞价"
    )

    return True, (
        f"✅ 物品已上架拍卖！\n"
        f"📦 {item_display}\n"
        f"💰 起拍价：{start_price:,}💰"
        + (f"  一口价：{buyout_price:,}💰" if buyout_price else "")
        + f"\n⏰ 截止：{end_str}\n"
        f"🆔 拍卖编号：#{auction.id}"
    )


# ==================== 出价竞拍 ====================

async def place_bid(
    uow: UnitOfWork,
    bidder: Player,
    auction_id: int,
    bid_amount: int,
) -> Tuple[bool, str]:
    """
    出价竞拍

    Args:
        uow: 工作单元
        bidder: 出价人玩家对象
        auction_id: 拍卖编号
        bid_amount: 出价金额

    Returns:
        (success, message)
    """
    session = uow.session

    # 1. 查找拍卖条目
    auction = await uow.auction_items.get_by_id(auction_id)
    if not auction or not auction.is_active:
        return False, f"⛔ 拍卖 #{auction_id} 不存在或已结束"

    # 2. 检查是否已过期
    if datetime.now() >= auction.end_at:
        return False, "⛔ 该拍卖已截止"

    # 3. 卖家不能自己出价
    if bidder.id == auction.seller_id:
        return False, "⛔ 不能对自己上架的物品出价"

    # 4. 出价不能与当前最高出价人相同（防止重复出价）
    if bidder.id == auction.current_bidder_id:
        return False, "⛔ 你已是当前最高出价人，无需重复出价"

    # 5. 验证出价金额
    min_bid = auction.min_next_bid
    if bid_amount < min_bid:
        if not auction.has_bidder:
            return False, f"⛔ 出价不能低于起拍价 {min_bid:,}💰"
        return False, (
            f"⛔ 出价不足，至少需要出 {min_bid:,}💰\n"
            f"（当前价 {auction.current_price:,}💰 × {int(MIN_BID_RATIO*100)}%）"
        )

    # 6. 检查出价人金币是否充足
    if bidder.gold < bid_amount:
        return False, f"⛔ 金币不足，你有 {bidder.gold:,}💰，需要 {bid_amount:,}💰"

    # 7. 退还前一位竞价者的金币
    if auction.current_bidder_id:
        prev_bidder = await session.get(Player, auction.current_bidder_id)
        if prev_bidder:
            prev_bidder.gold += auction.current_price
            session.add(prev_bidder)

    # 8. 冻结新竞价者金币
    bidder.gold -= bid_amount
    session.add(bidder)

    # 9. 更新拍卖条目
    auction.current_price = bid_amount
    auction.current_bidder_id = bidder.id
    auction.current_bidder_name = bidder.nickname
    auction.bid_count += 1
    session.add(auction)
    await session.flush()

    # 10. 记录竞价历史
    bid_record = AuctionBidHistory(
        auction_id=auction.id,
        bidder_id=bidder.id,
        bidder_name=bidder.nickname,
        amount=bid_amount,
        bid_at=datetime.now(),
    )
    await uow.auction_bid_histories.add(bid_record)

    item_display = _make_item_display(auction)

    # 11. 检查是否触发一口价
    if auction.buyout_price and bid_amount >= auction.buyout_price:
        success, settle_msg = await _settle_auction(uow, auction, buyout=True)
        if success:
            return True, (
                f"🎯 以一口价 {auction.buyout_price:,}💰 竞得！\n"
                f"📦 {item_display}\n"
                f"✅ 物品已转入你的背包"
            )
        return False, settle_msg

    end_str = auction.end_at.strftime("%m-%d %H:%M")
    return True, (
        f"✅ 出价成功！\n"
        f"📦 {item_display}\n"
        f"💰 你的出价：{bid_amount:,}💰\n"
        f"⏰ 截止：{end_str}\n"
        f"💡 如被超价，金币将自动退还"
    )


# ==================== 撤拍 ====================

async def cancel_auction(
    uow: UnitOfWork,
    seller: Player,
    auction_id: int,
) -> Tuple[bool, str]:
    """
    撤拍（仅允许无人出价时撤拍）

    Args:
        uow: 工作单元
        seller: 卖家玩家对象
        auction_id: 拍卖编号

    Returns:
        (success, message)
    """
    session = uow.session

    auction = await uow.auction_items.get_by_id(auction_id)
    if not auction or not auction.is_active:
        return False, f"⛔ 拍卖 #{auction_id} 不存在或已结束"

    if auction.seller_id != seller.id:
        return False, "⛔ 该拍卖不属于你"

    if auction.has_bidder:
        return False, "⛔ 已有人出价，无法撤拍"

    # 退还物品
    await _return_item_to_seller(uow, auction, seller)

    auction.status = "cancelled"
    session.add(auction)
    await session.flush()

    item_display = _make_item_display(auction)
    return True, f"✅ 已撤拍「{item_display}」，物品已退回背包"


# ==================== 结算 ====================

async def _settle_auction(
    uow: UnitOfWork,
    auction: AuctionItem,
    buyout: bool = False,
) -> Tuple[bool, str]:
    """
    结算单个拍卖

    有人出价 → 转移物品给买家，金币（扣税）给卖家，广播结果
    无人出价 → 退还物品给卖家，标记为流拍，广播结果

    Args:
        uow: 工作单元
        auction: 拍卖条目
        buyout: 是否为一口价触发

    Returns:
        (success, message)
    """
    session = uow.session

    item_display = _make_item_display(auction)

    if not auction.has_bidder:
        # 流拍：退还物品给卖家
        seller = await session.get(Player, auction.seller_id)
        if seller:
            await _return_item_to_seller(uow, auction, seller)

        auction.status = "expired"
        session.add(auction)
        await session.flush()

        await _broadcast(
            session,
            f"📋 [拍卖行] 拍卖结束，无人竞价\n"
            f"📦 {item_display}（#{auction.id}）\n"
            f"↩️ 物品已退回卖家"
        )
        return True, "流拍"

    # 有人成交：转移物品给买家
    buyer = await session.get(Player, auction.current_bidder_id)
    seller = await session.get(Player, auction.seller_id)

    if not buyer or not seller:
        logger.error(f"[拍卖行] 结算失败：买家或卖家不存在 auction_id={auction.id}")
        return False, "内部错误：玩家数据异常"

    # 转移物品
    transfer_ok = await _transfer_auction_item(uow, auction, buyer)
    if not transfer_ok:
        logger.error(f"[拍卖行] 结算失败：物品转移失败 auction_id={auction.id}")
        return False, "内部错误：物品转移失败"

    # 结算金币（税收直接销毁）
    final_price = auction.current_price
    tax = calculate_transaction_tax(final_price)
    seller_income = final_price - tax
    seller.gold += seller_income
    session.add(seller)

    auction.status = "sold"
    session.add(auction)
    await session.flush()

    # 广播结果
    buyer_name = buyer.nickname
    seller_name = seller.nickname
    trigger = "（一口价）" if buyout else ""
    await _broadcast(
        session,
        f"🎉 [拍卖行] 拍卖成交！{trigger}\n"
        f"📦 {item_display}（#{auction.id}）\n"
        f"🏆 竞得者：{buyer_name}\n"
        f"💰 成交价：{final_price:,}💰"
        + (f"（税：{tax:,}）" if tax > 0 else "")
        + f"\n💸 卖家到手：{seller_income:,}💰"
    )

    return True, "成交"


async def _transfer_auction_item(
    uow: UnitOfWork,
    auction: AuctionItem,
    buyer: Player,
) -> bool:
    """将拍卖物品转移给买家"""
    session = uow.session

    if auction.is_instance_trade:
        # 装备：解冻并转移所有权
        equipment = await session.get(ItemInstance, auction.item_instance_id)
        if not equipment:
            return False
        # 解冻拍卖标记
        extra_attrs = equipment.extra_attrs or {}
        extra_attrs.pop("_frozen_for_auction", None)
        equipment.extra_attrs = extra_attrs
        equipment.player_id = buyer.id
        session.add(equipment)
        await session.flush()
        return True
    else:
        # 普通物品：添加到买家背包
        try:
            await ItemInstance.add_item(session, buyer.id, auction.item_id, auction.quantity)
            return True
        except ValueError as e:
            logger.error(f"[拍卖行] 添加物品到买家背包失败: {e}")
            return False


async def _return_item_to_seller(
    uow: UnitOfWork,
    auction: AuctionItem,
    seller: Player,
):
    """退还拍卖物品给卖家（流拍/撤拍时）"""
    session = uow.session

    if auction.is_instance_trade:
        # 装备：仅解冻，不需要转移（player_id不变）
        equipment = await session.get(ItemInstance, auction.item_instance_id)
        if equipment:
            extra_attrs = equipment.extra_attrs or {}
            extra_attrs.pop("_frozen_for_auction", None)
            equipment.extra_attrs = extra_attrs
            session.add(equipment)
            await session.flush()
    else:
        # 普通物品：退回背包
        try:
            await ItemInstance.add_item(session, seller.id, auction.item_id, auction.quantity)
        except ValueError as e:
            logger.error(f"[拍卖行] 退还物品失败: {e}")


# ==================== 批量结算（定时任务调用） ====================

async def settle_expired_auctions(uow: UnitOfWork) -> int:
    """
    结算所有已到期的拍卖

    Returns:
        结算数量
    """
    expired = await uow.auction_items.find_expired_unsettled()
    count = 0
    for auction in expired:
        try:
            success, _ = await _settle_auction(uow, auction)
            if success:
                count += 1
        except Exception as e:
            logger.error(f"[拍卖行] 结算拍卖 #{auction.id} 失败: {e}")
    return count


async def send_30min_reminders(uow: UnitOfWork) -> int:
    """
    发送即将结束（30分钟内）的拍卖提醒

    Returns:
        发送数量
    """
    session = uow.session
    near_ending = await uow.auction_items.find_near_ending_unreminded()
    count = 0
    for auction in near_ending:
        try:
            item_display = _make_item_display(auction)
            end_str = auction.end_at.strftime("%H:%M")
            buyer_info = f"当前最高：{auction.current_price:,}💰" if auction.has_bidder else "暂无人出价"
            await _broadcast(
                session,
                f"⏳ [拍卖行] 即将结束提醒！\n"
                f"📦 {item_display}（#{auction.id}）\n"
                f"💰 {buyer_info}\n"
                f"⏰ 截止时间：{end_str}\n"
                f"📣 发送【出价 {auction.id} 金额】参与竞价"
            )
            auction.reminded_30min = True
            session.add(auction)
            count += 1
        except Exception as e:
            logger.error(f"[拍卖行] 发送提醒 #{auction.id} 失败: {e}")
    return count
