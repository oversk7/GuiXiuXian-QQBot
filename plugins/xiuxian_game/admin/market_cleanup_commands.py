"""管理员市场清理指令。"""

from typing import Dict, List

from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from sqlalchemy import select

from ..ai_guide import is_admin
from ..economy.equipment_trade_service import EquipmentTradeService
from ..economy.market import (
    MIN_UNIT_PRICE,
    PRICE_CAP_MULT,
    _compute_equipment_floor_price,
    _compute_item_floor_price,
)
from ..models.db import safe_session
from ..models.inventory import ItemInstance
from ..models.market_order import MarketOrder, OrderSide
from ..utils import message_add_head


cleanup_cmd = on_command("清理异常挂牌", block=True, priority=1)


@cleanup_cmd.handle()
async def handle_cleanup(event: MessageEvent, args: Message = CommandArg()):
    """管理员指令：清理高于建议上限的异常挂牌。"""

    user_id = event.get_user_id()
    if not is_admin(user_id):
        await cleanup_cmd.finish("⛔ 只有管理员可以执行该指令")

    multiplier_text = args.extract_plain_text().strip()
    multiplier = PRICE_CAP_MULT

    if multiplier_text:
        try:
            multiplier = float(multiplier_text)
            if multiplier < 1:
                raise ValueError
        except ValueError:
            await cleanup_cmd.finish("⛔ 倍数参数必须是不小于 1 的数字，如：清理异常挂牌 6")

    async with safe_session() as session:
        stmt = select(MarketOrder)
        orders = (await session.execute(stmt)).scalars().all()

        if not orders:
            await cleanup_cmd.finish(message_add_head("📭 市场目前没有任何挂牌", event))

        item_floor_cache: Dict[str, int] = {}
        item_base_cache: Dict[str, int] = {}
        removed: List[str] = []
        auto_removed_missing: List[str] = []

        for order in orders:
            # 对于普通物品，底价可被缓存；装备需要逐件计算
            floor_price: int | None = None
            cap_price: int | None = None
            base_price: int | None = None

            if order.is_instance_trade:
                equipment = None
                if order.item_instance_id:
                    equipment = await session.get(ItemInstance, order.item_instance_id)

                if equipment is None:
                    auto_removed_missing.append(
                        f"🆔{order.id}┃装备实例缺失，直接清理"
                    )
                    await session.delete(order)
                    continue

                floor_price = await _compute_equipment_floor_price(session, equipment)
                cap_price = max(int(floor_price * multiplier), floor_price)
                base_price = max(
                    int(EquipmentTradeService.calculate_equipment_value_range(equipment)[0]),
                    MIN_UNIT_PRICE,
                )
            else:
                item_id = order.item_id
                if item_id not in item_floor_cache:
                    item_cfg = order.item
                    if not item_cfg:
                        auto_removed_missing.append(
                            f"🆔{order.id}┃物品配置缺失，直接清理"
                        )
                        await session.delete(order)
                        continue
                    item_floor_cache[item_id] = await _compute_item_floor_price(
                        session, item_cfg
                    )
                    base_price_val = max(
                        int(getattr(item_cfg, "price", 0) or 0),
                        MIN_UNIT_PRICE,
                    )
                    item_base_cache[item_id] = base_price_val
                floor_price = item_floor_cache[item_id]
                cap_price = max(int(floor_price * multiplier), floor_price)
                base_price = item_base_cache.get(item_id, MIN_UNIT_PRICE)

            if cap_price is None or floor_price is None or base_price is None:
                continue

            hard_cap = base_price * 100

            reasons: List[str] = []
            if order.side == OrderSide.SELL and order.price > cap_price:
                reasons.append(f"超过建议上限 {cap_price}💰")
            if order.price > hard_cap:
                reasons.append(f"超过基础价百倍 {hard_cap}💰")

            if reasons:
                item_name = order.item.name if order.item else order.item_id
                removed.append(
                    f"🆔{order.id}┃{item_name}┃{order.price}💰 ＞ {'、'.join(reasons)}"
                )
                await session.delete(order)

        if not removed and not auto_removed_missing:
            await cleanup_cmd.finish(
                message_add_head("✅ 未发现超过上限的异常挂牌", event)
            )

        await session.commit()

    lines = ["🧹 异常挂牌清理完成"]
    if removed:
        lines.append(f"✅ 清理高价挂牌 {len(removed)} 条：")
        lines.extend(removed[:10])
        if len(removed) > 10:
            lines.append(f"…… 共 {len(removed)} 条，已截取前 10 条展示")
    if auto_removed_missing:
        lines.append(f"⚠️ 因缺失数据自动清理 {len(auto_removed_missing)} 条：")
        lines.extend(auto_removed_missing[:5])
        if len(auto_removed_missing) > 5:
            lines.append("…… 其余已省略")
    lines.append(f"📊 使用倍数：{multiplier:g}× 建议底价上限")

    await cleanup_cmd.finish(message_add_head("\n".join(lines), event))
