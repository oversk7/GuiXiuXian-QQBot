"""
个人摊位核心服务

功能：
1. 开摊     - 消耗摊位令，在城镇开设摊位
2. 收摊     - 手动/自动关闭摊位，退回所有物品
3. 上架     - 上架物品到摊位（自由定价）
4. 下架     - 从摊位移除物品
5. 购买     - 其他玩家直接购买摊位商品
6. 过期处理 - 定时任务自动收摊过期摊位
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Tuple

from nonebot import logger
from sqlalchemy import select

from ..config import config
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.inventory import ItemInstance, ItemType
from ..models.player import Player
from ..models.stall import PlayerStall, StallItem

# ==================== 常量 ====================

MAX_STALL_SLOTS = 5              # 基础摊位格数
BASIC_CARD_BONUS_SLOTS = 2       # 基础月卡额外格数
PREMIUM_CARD_BONUS_SLOTS = 5     # 高级月卡额外格数
STALL_DURATION_HOURS = 24        # 摊位令持续时间（小时）
STALL_TAX_RATE = 0.03            # 基础税率 3%
PREMIUM_TAX_THRESHOLD_5X = 5     # 溢价5倍阈值
PREMIUM_TAX_RATE_5X = 0.15       # 超5倍附加税率 15%
PREMIUM_TAX_THRESHOLD_20X = 20   # 溢价20倍阈值
PREMIUM_TAX_RATE_20X = 0.30      # 超20倍附加税率 30%
STALL_NAME_MAX_LEN = 16          # 摊位名最大长度
SHOUT_MAX_LEN = 32               # 吆喝语最大长度
STALL_PERMIT_ITEM_ID = "stall_permit"


# ==================== 工具函数 ====================

def get_town_name(x: int, y: int, region: str = "大都会") -> Optional[str]:
    """获取玩家所在城镇名称，不在城镇则返回None"""
    if region != "大都会":
        return None

    from ..economy.merchants import MARKETS, HEADQUARTERS_COORD

    # 市集
    for market in MARKETS:
        distance = abs(x - market.x) + abs(y - market.y)
        if distance <= 5:
            return market.name

    # 缉邪司总部
    hq_distance = abs(x - HEADQUARTERS_COORD[0]) + abs(y - HEADQUARTERS_COORD[1])
    if hq_distance <= 5:
        return "风雪镇"

    # 打工地点
    try:
        from ..economy.part_time_job_service import PartTimeJobService
        for loc_name, loc_data in PartTimeJobService.JOB_LOCATIONS.items():
            distance = abs(x - loc_data['x']) + abs(y - loc_data['y'])
            if distance <= 5:
                return loc_name
    except ImportError:
        pass

    return None


async def get_max_stall_slots(session, player_id: str) -> int:
    """计算玩家最大摊位格数"""
    from ..models.monthly_card import get_player_card_benefits
    benefits = await get_player_card_benefits(session, player_id)

    slots = MAX_STALL_SLOTS
    if benefits["premium_active"]:
        slots += PREMIUM_CARD_BONUS_SLOTS
    elif benefits["basic_active"]:
        slots += BASIC_CARD_BONUS_SLOTS
    return slots


def calculate_stall_tax(unit_price: int, quantity: int, system_estimate: int) -> int:
    """计算摊位交易税

    基础税 = 成交额 × 3%
    超估价5倍部分 +15%
    超估价20倍部分 +30%
    """
    total = unit_price * quantity
    base_tax = int(total * STALL_TAX_RATE)

    surcharge = 0
    if system_estimate > 0:
        threshold_5x = system_estimate * PREMIUM_TAX_THRESHOLD_5X
        threshold_20x = system_estimate * PREMIUM_TAX_THRESHOLD_20X

        if unit_price > threshold_20x:
            surcharge += int((unit_price - threshold_20x) * quantity * PREMIUM_TAX_RATE_20X)
            surcharge += int((threshold_20x - threshold_5x) * quantity * PREMIUM_TAX_RATE_5X)
        elif unit_price > threshold_5x:
            surcharge += int((unit_price - threshold_5x) * quantity * PREMIUM_TAX_RATE_5X)

    return base_tax + surcharge


def _get_system_estimate(item_cfg, equipment: Optional[ItemInstance] = None) -> int:
    """获取物品的系统估价"""
    base = getattr(item_cfg, "price", 0) or 0
    if equipment:
        try:
            from ..economy.equipment_trade_service import EquipmentTradeService
            min_val, _ = EquipmentTradeService.calculate_equipment_value_range(equipment)
            return max(base, min_val)
        except Exception:
            pass
    return base


# ==================== 核心业务 ====================

async def open_stall(uow: UnitOfWork, player: Player) -> Tuple[bool, str]:
    """开摊"""
    session = uow.session

    # 1. 检查是否在城镇
    region = player.get_current_region() if hasattr(player, 'get_current_region') else "大都会"
    town = get_town_name(player.x, player.y, region)
    if not town:
        return False, "⛔ 只能在城镇安全区摆摊\n💡 请先导航到一个城镇"

    # 2. 检查是否已有活跃摊位
    existing = await uow.player_stalls.get_active_by_player(player.id)
    if existing:
        return False, f"⛔ 你已在「{existing.city_name}」有一个摊位\n💡 先【收摊】再重新开"

    # 3. 消耗摊位令
    try:
        await ItemInstance.consume_item(session, player.id, STALL_PERMIT_ITEM_ID, 1)
    except ValueError:
        return False, "⛔ 你没有摊位令\n💡 可通过打工掉落或商店购买获取"

    # 4. 创建摊位
    now = datetime.now()
    stall = PlayerStall(
        server_id=player.server_id,
        player_id=player.id,
        player_uid=player.uid,
        player_name=player.nickname,
        city_name=town,
        opened_at=now,
        expires_at=now + timedelta(hours=STALL_DURATION_HOURS),
        status="active",
    )
    await uow.player_stalls.add(stall)

    max_slots = await get_max_stall_slots(session, player.id)
    expire_str = stall.expires_at.strftime("%m-%d %H:%M")
    return True, (
        f"✅ 摊位已在「{town}」开张！\n"
        f"📦 可上架 {max_slots} 件商品\n"
        f"⏰ 有效期至 {expire_str}\n"
        f"💡 使用【上摊 物品名 单价 数量】上架商品"
    )


async def close_stall(uow: UnitOfWork, player: Player) -> Tuple[bool, str]:
    """收摊"""
    session = uow.session

    stall = await uow.player_stalls.get_active_by_player(player.id)
    if not stall:
        return False, "⛔ 你当前没有摊位"

    # 退回所有商品
    returned = await _return_all_stall_items(uow, stall)

    stall.status = "closed"
    session.add(stall)
    await session.flush()

    return True, f"✅ 已收摊，退回 {returned} 件商品到背包"


async def _return_all_stall_items(uow: UnitOfWork, stall: PlayerStall) -> int:
    """退回摊位上所有商品给摊主"""
    session = uow.session
    items = await uow.stall_items.delete_all_by_stall(stall.id)
    count = 0
    for si in items:
        if si.is_instance_trade and si.item_instance_id:
            # 装备：解冻
            equipment = await session.get(ItemInstance, si.item_instance_id)
            if equipment:
                extra = equipment.extra_attrs or {}
                extra.pop("_frozen_for_stall", None)
                equipment.extra_attrs = extra
                session.add(equipment)
        else:
            # 普通物品：退回背包
            try:
                await ItemInstance.add_item(session, stall.player_id, si.item_id, si.quantity)
            except ValueError as e:
                logger.error(f"[摊位] 退回物品失败: {e}")
        count += 1
    return count


# ==================== 上架 / 下架 ====================

async def list_item(
    uow: UnitOfWork,
    player: Player,
    item_name: str,
    unit_price: int,
    quantity: int = 1,
    equipment_instance_id: Optional[int] = None,
) -> Tuple[bool, str]:
    """上架物品到摊位"""
    session = uow.session

    # 1. 检查摊位
    stall = await uow.player_stalls.get_active_by_player(player.id)
    if not stall:
        return False, "⛔ 你当前没有摊位\n💡 请先【摆摊】"

    # 2. 检查过期
    if datetime.now() >= stall.expires_at:
        return False, "⛔ 摊位已过期，请重新开摊"

    # 3. 检查格数
    current_count = await uow.stall_items.count_by_stall(stall.id)
    max_slots = await get_max_stall_slots(session, player.id)
    if current_count >= max_slots:
        return False, f"⛔ 摊位已满（{current_count}/{max_slots}）\n💡 先【下摊】腾出位置"

    # 4. 查找物品配置
    item_cfg = config.items_config["by_name"].get(item_name)
    if not item_cfg:
        return False, f"⛔ 未找到物品「{item_name}」"

    # 5. 禁止GOODS
    if item_cfg.type == ItemType.GOODS:
        return False, "⛔ 跑商商品不能上摊"

    # 6. 价格校验
    if unit_price < 1:
        return False, "⛔ 单价至少1金币"

    # 7. 根据物品类型处理
    if item_cfg.type in (ItemType.EQUIPMENT, ItemType.INSCRIPTION):
        return await _list_equipment_item(uow, stall, player, item_cfg, unit_price, equipment_instance_id)
    else:
        return await _list_normal_item(uow, stall, player, item_cfg, unit_price, quantity)


async def _list_normal_item(uow, stall, player, item_cfg, unit_price, quantity):
    """上架普通物品"""
    session = uow.session

    # 从背包扣除
    try:
        await ItemInstance.consume_item(session, player.id, item_cfg.item_id, quantity)
    except ValueError as e:
        return False, f"⛔ 背包物品不足：{e}"

    si = StallItem(
        server_id=player.server_id,
        stall_id=stall.id,
        seller_id=player.id,
        item_id=item_cfg.item_id,
        quantity=quantity,
        unit_price=unit_price,
        is_instance_trade=False,
    )
    await uow.stall_items.add(si)

    item_display = item_cfg.get_display_name()
    return True, (
        f"✅ 已上架到摊位\n"
        f"📦 {item_display} ×{quantity}\n"
        f"💰 单价：{unit_price:,}💰"
    )


async def _list_equipment_item(uow, stall, player, item_cfg, unit_price, equipment_instance_id):
    """上架装备/铭文"""
    session = uow.session
    is_inscription = item_cfg.type == ItemType.INSCRIPTION

    if equipment_instance_id:
        equipment = await session.get(ItemInstance, equipment_instance_id)
        if not equipment or equipment.player_id != player.id:
            return False, "⛔ 物品不存在或不属于你"
        if not is_inscription and equipment.equipped:
            return False, "⛔ 该装备正在穿戴中"
        extra = equipment.extra_attrs or {}
        if extra.get("_frozen_for_trade") or extra.get("_frozen_for_auction") or extra.get("_frozen_for_stall"):
            return False, "⛔ 该物品已在交易中"
    else:
        # 自动选择第一件
        conditions = [
            ItemInstance.player_id == player.id,
            ItemInstance.item_id == item_cfg.item_id,
        ]
        if not is_inscription:
            conditions.append(ItemInstance.equipped == False)
        stmt = select(ItemInstance).where(*conditions)
        result = await session.execute(stmt)
        candidates = result.scalars().all()
        available = [
            e for e in candidates
            if not (e.extra_attrs or {}).get("_frozen_for_trade")
            and not (e.extra_attrs or {}).get("_frozen_for_auction")
            and not (e.extra_attrs or {}).get("_frozen_for_stall")
        ]
        if not available:
            return False, f"⛔ 背包中没有可上架的「{item_cfg.name}」"
        equipment = available[0]

    # 冻结
    extra_attrs = equipment.extra_attrs or {}
    extra_attrs["_frozen_for_stall"] = True
    equipment.extra_attrs = extra_attrs
    session.add(equipment)
    await session.flush()

    # 生成摘要
    from ..economy.equipment_trade_service import EquipmentTradeService
    summary = EquipmentTradeService.generate_instance_summary(equipment)

    si = StallItem(
        server_id=player.server_id,
        stall_id=stall.id,
        seller_id=player.id,
        item_id=item_cfg.item_id,
        quantity=1,
        unit_price=unit_price,
        is_instance_trade=True,
        item_instance_id=equipment.id,
        equipment_summary=summary,
    )
    await uow.stall_items.add(si)

    item_display = item_cfg.get_display_name()
    return True, (
        f"✅ 已上架到摊位\n"
        f"📦 {item_display}（{summary}）\n"
        f"💰 单价：{unit_price:,}💰"
    )


async def unlist_item(uow: UnitOfWork, player: Player, slot_index: int) -> Tuple[bool, str]:
    """下架指定序号的商品"""
    session = uow.session

    stall = await uow.player_stalls.get_active_by_player(player.id)
    if not stall:
        return False, "⛔ 你当前没有摊位"

    items = await uow.stall_items.find_by_stall(stall.id)
    if slot_index < 1 or slot_index > len(items):
        return False, f"⛔ 无效序号，当前摊位有 {len(items)} 件商品"

    si = items[slot_index - 1]
    item_cfg = config.items_config["by_id"].get(si.item_id)
    item_name = item_cfg.get_display_name() if item_cfg else si.item_id

    # 退回物品
    if si.is_instance_trade and si.item_instance_id:
        equipment = await session.get(ItemInstance, si.item_instance_id)
        if equipment:
            extra = equipment.extra_attrs or {}
            extra.pop("_frozen_for_stall", None)
            equipment.extra_attrs = extra
            session.add(equipment)
    else:
        try:
            await ItemInstance.add_item(session, player.id, si.item_id, si.quantity)
        except ValueError as e:
            return False, f"⛔ 退回物品失败：{e}"

    await uow.stall_items.delete(si)

    return True, f"✅ 已下架「{item_name}」，物品已退回背包"


# ==================== 购买 ====================

async def buy_item(
    uow: UnitOfWork,
    buyer: Player,
    seller_uid: int,
    slot_index: int,
    quantity: int = 1,
) -> Tuple[bool, str]:
    """购买摊位商品"""
    session = uow.session

    # 1. 查找摊主
    stmt = select(Player).where(Player.uid == seller_uid, Player.server_id == buyer.server_id)
    result = await session.execute(stmt)
    seller = result.scalars().first()
    if not seller:
        return False, f"⛔ 未找到UID为{seller_uid}的玩家"

    if buyer.id == seller.id:
        return False, "⛔ 不能购买自己摊位的商品"

    # 2. 查找摊位
    stall = await uow.player_stalls.get_active_by_player(seller.id)
    if not stall:
        return False, "⛔ 该玩家没有摆摊"
    if stall.server_id != buyer.server_id:
        return False, "⛔ 该玩家没有摆摊"

    # 3. 查找商品
    items = await uow.stall_items.find_by_stall(stall.id)
    if slot_index < 1 or slot_index > len(items):
        return False, f"⛔ 无效序号（该摊位有{len(items)}件商品）"

    si = items[slot_index - 1]
    item_cfg = config.items_config["by_id"].get(si.item_id)
    item_name = item_cfg.get_display_name() if item_cfg else si.item_id

    # 4. 数量校验
    if si.is_instance_trade:
        quantity = 1  # 装备固定1件
    if quantity > si.quantity:
        return False, f"⛔ 库存不足（剩余{si.quantity}件）"
    if quantity < 1:
        return False, "⛔ 购买数量至少1"

    # 5. 计算费用
    total_cost = si.unit_price * quantity
    if buyer.gold < total_cost:
        return False, f"⛔ 金币不足（需要{total_cost:,}💰，你有{buyer.gold:,}💰）"

    # 6. 计算税
    equipment_for_estimate = None
    if si.is_instance_trade and si.item_instance_id:
        equipment_for_estimate = await session.get(ItemInstance, si.item_instance_id)
    system_estimate = _get_system_estimate(item_cfg, equipment_for_estimate)
    tax = calculate_stall_tax(si.unit_price, quantity, system_estimate)
    seller_income = total_cost - tax

    # 7. 扣款 & 卖家到账
    buyer.gold -= total_cost
    seller.gold += seller_income
    session.add(buyer)
    session.add(seller)

    # 8. 转移物品
    if si.is_instance_trade and si.item_instance_id:
        equipment = await session.get(ItemInstance, si.item_instance_id)
        if not equipment:
            return False, "⛔ 物品数据异常"
        extra = equipment.extra_attrs or {}
        extra.pop("_frozen_for_stall", None)
        equipment.extra_attrs = extra
        equipment.player_id = buyer.id
        session.add(equipment)
    else:
        try:
            await ItemInstance.add_item(session, buyer.id, si.item_id, quantity)
        except ValueError as e:
            return False, f"⛔ 背包空间不足：{e}"

    # 9. 更新或删除商品条目
    if quantity >= si.quantity:
        await uow.stall_items.delete(si)
    else:
        si.quantity -= quantity
        session.add(si)

    # 10. 记录交易
    from ..models.trade_record import TradeRecord, TradeType
    for pid, ttype in [(buyer.id, TradeType.BUY), (seller.id, TradeType.SELL)]:
        record = TradeRecord(
            player_id=pid,
            trade_type=ttype,
            market_id=f"stall_{stall.id}",
            item_id=si.item_id,
            quantity=quantity,
            unit_price=si.unit_price,
            total_amount=total_cost,
            trade_time=datetime.now(),
            is_cross_market=False,
        )
        session.add(record)

    await session.flush()

    tax_str = f"（税{tax:,}💰）" if tax > 0 else ""
    equip_info = f"（{si.equipment_summary}）" if si.equipment_summary else ""
    return True, (
        f"✅ 购买成功！\n"
        f"📦 {item_name}{equip_info} ×{quantity}\n"
        f"💰 支付：{total_cost:,}💰{tax_str}\n"
        f"👤 卖家{seller.nickname}到手：{seller_income:,}💰"
    )


# ==================== 摊位设置 ====================

async def set_stall_name(uow: UnitOfWork, player: Player, name: str) -> Tuple[bool, str]:
    """设置摊位名"""
    stall = await uow.player_stalls.get_active_by_player(player.id)
    if not stall:
        return False, "⛔ 你当前没有摊位"
    if len(name) > STALL_NAME_MAX_LEN:
        return False, f"⛔ 摊位名最多{STALL_NAME_MAX_LEN}个字"
    stall.stall_name = name
    uow.session.add(stall)
    return True, f"✅ 摊位名已设为「{name}」"


async def set_shout(uow: UnitOfWork, player: Player, text: str) -> Tuple[bool, str]:
    """设置吆喝语"""
    stall = await uow.player_stalls.get_active_by_player(player.id)
    if not stall:
        return False, "⛔ 你当前没有摊位"
    if len(text) > SHOUT_MAX_LEN:
        return False, f"⛔ 吆喝语最多{SHOUT_MAX_LEN}个字"
    stall.shout_text = text
    uow.session.add(stall)
    return True, f"✅ 吆喝语已设为：{text}"


# ==================== 过期处理 ====================

async def expire_stalls(uow: UnitOfWork) -> int:
    """批量过期处理（定时任务调用）"""
    expired = await uow.player_stalls.find_expired_active()
    count = 0
    for stall in expired:
        try:
            await _return_all_stall_items(uow, stall)
            stall.status = "expired"
            uow.session.add(stall)
            count += 1
        except Exception as e:
            logger.error(f"[摊位] 过期处理失败 stall_id={stall.id}: {e}")
    return count
