"""
个人摊位命令处理器

命令列表：
- 【摆摊】              - 在当前城镇开摊（消耗摊位令）
- 【收摊】              - 手动收摊，物品退回背包
- 【上摊 物品名 单价 [数量]】 - 上架物品
- 【下摊 序号】          - 下架物品
- 【我的摊位】           - 查看自己的摊位
- 【摊位名 名称】        - 设置摊位名
- 【吆喝 内容】          - 设置吆喝语
- 【买摊 摊主UID 序号 [数量]】 - 购买（需在同一城镇）
- 【摊位 UID】           - 查看某人摊位（需在同一城镇）

摊位信息通过【观察】命令在城镇中自动显示，无需单独逛摊/搜摊。
"""

import time
from datetime import datetime

from nonebot import on_command, on_message
from nonebot.adapters.qq import Message, MessageEvent
from nonebot.params import CommandArg
from sqlalchemy import select

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.db import AsyncSessionLocal
from ..models.inventory import ItemInstance, ItemType
from ..platform_utils import get_unified_player, is_guild_message
from ..utils import message_add_head
from ..utils_markdown import cmd, build_markdown
from ..config import config
from . import stall_service

# ==================== 命令定义 ====================

open_stall_cmd = on_command("摆摊", aliases={"开摊"}, block=True, priority=13)
close_stall_cmd = on_command("收摊", aliases={"关摊"}, block=True, priority=13)
list_item_cmd = on_command("上摊", aliases={"摊位上架"}, block=True, priority=13)
unlist_item_cmd = on_command("下摊", aliases={"摊位下架"}, block=True, priority=13)
my_stall_cmd = on_command("我的摊位", block=True, priority=13)
set_name_cmd = on_command("摊位名", aliases={"摊位改名"}, block=True, priority=13)
set_shout_cmd = on_command("吆喝", block=True, priority=13)
buy_cmd = on_command("买摊", aliases={"摊位购买"}, block=True, priority=13)
view_stall_cmd = on_command("摊位", block=True, priority=13, force_whitespace=True)


# ==================== 装备选择状态管理 ====================

_stall_equipment_selection_state: dict = {}
_STALL_SELECTION_EXPIRE = 120  # 秒


def _cleanup_expired_stall_states():
    now = time.time()
    expired = [
        uid for uid, s in _stall_equipment_selection_state.items()
        if now - s.get("timestamp", 0) > _STALL_SELECTION_EXPIRE
    ]
    for uid in expired:
        del _stall_equipment_selection_state[uid]


stall_equipment_selection_handler = on_message(priority=6, block=False)


# ==================== 摆摊 ====================

@open_stall_cmd.handle()
async def handle_open_stall(event: MessageEvent):
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await open_stall_cmd.finish(message_add_head("⛔ 请先创建角色", event))

        success, msg = await stall_service.open_stall(uow, player)
        if success:
            await uow.commit()

    await open_stall_cmd.finish(message_add_head(msg, event))


# ==================== 收摊 ====================

@close_stall_cmd.handle()
async def handle_close_stall(event: MessageEvent):
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await close_stall_cmd.finish(message_add_head("⛔ 请先创建角色", event))

        success, msg = await stall_service.close_stall(uow, player)
        if success:
            await uow.commit()

    await close_stall_cmd.finish(message_add_head(msg, event))


# ==================== 上摊 ====================

@list_item_cmd.handle()
async def handle_list_item(event: MessageEvent, args: Message = CommandArg()):
    """格式：上摊 物品名 单价 [数量]"""
    raw = args.extract_plain_text().strip()
    parts = raw.split()

    if len(parts) < 2:
        await list_item_cmd.finish(message_add_head(
            "📋 上摊格式：\n"
            "【上摊 物品名 单价 [数量]】\n"
            "━━━━━━━━━━━━━\n"
            "示例：\n"
            "• 上摊 棺材钉 50000\n"
            "• 上摊 墓土 100 10\n"
            "• 上摊 碎颅制服 200000\n"
            "━━━━━━━━━━━━━\n"
            "💡 价格完全自由，无系统限制\n"
            "⚠️ 跑商商品不可上摊",
            event
        ))

    item_name = parts[0]

    try:
        unit_price = int(parts[1])
    except ValueError:
        await list_item_cmd.finish(message_add_head("⛔ 价格必须是整数", event))

    quantity = 1
    if len(parts) >= 3:
        try:
            quantity = int(parts[2])
            if quantity < 1:
                raise ValueError
        except ValueError:
            await list_item_cmd.finish(message_add_head("⛔ 数量必须是正整数", event))

    # 检查是否装备/铭文 → 走选择流程
    item_cfg = config.items_config["by_name"].get(item_name)
    if not item_cfg:
        await list_item_cmd.finish(message_add_head(f"⛔ 未找到物品「{item_name}」", event))

    if item_cfg.type in (ItemType.EQUIPMENT, ItemType.INSCRIPTION):
        await _handle_stall_equipment_listing(event, item_cfg, unit_price)
        return

    # 普通物品直接上架
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await list_item_cmd.finish(message_add_head("⛔ 请先创建角色", event))

        success, msg = await stall_service.list_item(
            uow, player, item_name, unit_price, quantity
        )
        if success:
            await uow.commit()

    await list_item_cmd.finish(message_add_head(msg, event))


async def _handle_stall_equipment_listing(event, item_cfg, unit_price):
    """装备/铭文上摊：多件时弹出选择列表"""
    is_inscription = item_cfg.type == ItemType.INSCRIPTION

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await list_item_cmd.finish(message_add_head("⛔ 请先创建角色", event))

        # 检查摊位存在
        stall = await uow.player_stalls.get_active_by_player(player.id)
        if not stall:
            await list_item_cmd.finish(message_add_head("⛔ 你当前没有摊位\n💡 请先【摆摊】", event))

        # 查询可用实例
        conditions = [
            ItemInstance.player_id == player.id,
            ItemInstance.item_id == item_cfg.item_id,
        ]
        if not is_inscription:
            conditions.append(ItemInstance.equipped == False)
        stmt = select(ItemInstance).where(*conditions)
        res = await uow.session.execute(stmt)
        candidates = res.scalars().all()
        available = [
            e for e in candidates
            if not (e.extra_attrs or {}).get("_frozen_for_trade")
            and not (e.extra_attrs or {}).get("_frozen_for_auction")
            and not (e.extra_attrs or {}).get("_frozen_for_stall")
        ]

        if not available:
            await list_item_cmd.finish(message_add_head(
                f"⛔ 背包中没有可上架的「{item_cfg.name}」", event
            ))

        if len(available) == 1:
            # 单件直接上架
            success, msg = await stall_service.list_item(
                uow, player, item_cfg.name, unit_price,
                equipment_instance_id=available[0].id,
            )
            if success:
                await uow.commit()
            await list_item_cmd.finish(message_add_head(msg, event))

        # 多件：保存选择状态
        from ..economy.equipment_trade_service_new import EquipmentTradeService as ETSNew
        summaries = [ETSNew.generate_instance_summary(e) for e in available]
        equipment_ids = [e.id for e in available]

        _cleanup_expired_stall_states()
        _stall_equipment_selection_state[player.id] = {
            "equipment_ids": equipment_ids,
            "equipment_summaries": summaries,
            "item_name": item_cfg.name,
            "unit_price": unit_price,
            "timestamp": time.time(),
        }

        lines = [
            f"📋 选择要上摊的「{item_cfg.name}」：",
            "━━━━━━━━━━━━━",
        ]
        for i, (eq_id, summary) in enumerate(zip(equipment_ids, summaries), 1):
            lines.append(f"{i}. 🆔{eq_id} {summary}")
        lines.extend(["━━━━━━━━━━━━━", "💡 回复序号选择（如：1），或回复 取消"])

        await list_item_cmd.finish(message_add_head("\n".join(lines), event))


@stall_equipment_selection_handler.handle()
async def handle_stall_equipment_selection(event: MessageEvent):
    """捕获玩家回复的装备序号，完成装备上摊"""
    _cleanup_expired_stall_states()

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            return
        if player.id not in _stall_equipment_selection_state:
            return

        message_text = event.get_message().extract_plain_text().strip()

        if message_text in ["取消", "cancel", "0"]:
            del _stall_equipment_selection_state[player.id]
            await stall_equipment_selection_handler.finish(
                message_add_head("❌ 已取消上摊", event)
            )

        if not message_text.isdigit():
            return

        try:
            index = int(message_text) - 1
            if index < 0:
                raise ValueError
        except ValueError:
            return

        state = _stall_equipment_selection_state[player.id]
        equipment_ids = state["equipment_ids"]

        if index >= len(equipment_ids):
            await stall_equipment_selection_handler.finish(
                message_add_head("⛔ 无效的序号，请重新选择或回复 取消", event)
            )

        equipment_id = equipment_ids[index]
        item_name = state["item_name"]
        unit_price = state["unit_price"]

        del _stall_equipment_selection_state[player.id]

        success, msg = await stall_service.list_item(
            uow, player, item_name, unit_price,
            equipment_instance_id=equipment_id,
        )
        if success:
            await uow.commit()
        await stall_equipment_selection_handler.finish(message_add_head(msg, event))


# ==================== 下摊 ====================

@unlist_item_cmd.handle()
async def handle_unlist_item(event: MessageEvent, args: Message = CommandArg()):
    """格式：下摊 序号"""
    raw = args.extract_plain_text().strip()

    if not raw:
        await unlist_item_cmd.finish(message_add_head(
            "📋 下摊格式：【下摊 序号】\n"
            "💡 使用【我的摊位】查看商品序号",
            event
        ))

    try:
        slot_index = int(raw)
    except ValueError:
        await unlist_item_cmd.finish(message_add_head("⛔ 序号必须是整数", event))

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await unlist_item_cmd.finish(message_add_head("⛔ 请先创建角色", event))

        success, msg = await stall_service.unlist_item(uow, player, slot_index)
        if success:
            await uow.commit()

    await unlist_item_cmd.finish(message_add_head(msg, event))


# ==================== 我的摊位 ====================

@my_stall_cmd.handle()
async def handle_my_stall(event: MessageEvent):
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await my_stall_cmd.finish(message_add_head("⛔ 请先创建角色", event))

        stall = await uow.player_stalls.get_active_by_player(player.id)
        if not stall:
            await my_stall_cmd.finish(build_markdown(
                "# 🏪 我的摊位\n***\n当前没有摊位\n"
                f"💡 使用{cmd('摆摊')}在城镇开摊"
            ))

        items = await uow.stall_items.find_by_stall(stall.id)
        max_slots = await stall_service.get_max_stall_slots(uow.session, player.id)

        now = datetime.now()
        remaining = stall.expires_at - now
        remain_h = int(remaining.total_seconds() // 3600)
        remain_m = int((remaining.total_seconds() % 3600) // 60)
        remain_str = f"{remain_h}h{remain_m}m" if remain_h > 0 else f"{remain_m}m"

        stall_display = stall.stall_name or f"{player.nickname}的摊位"

        lines = [
            f"# 🏪 {stall_display}",
            f"📍 {stall.city_name}　⏰ 剩余{remain_str}　📦 {len(items)}/{max_slots}",
        ]
        if stall.shout_text:
            lines.append(f"📢 {stall.shout_text}")
        lines.append("***")

        if not items:
            lines.append("摊位空空如也，快来上架商品吧！")
            lines.append(f"💡 {cmd('上摊 物品名 单价 数量', '上摊 ')}")
        else:
            for i, si in enumerate(items, 1):
                item_cfg = config.items_config["by_id"].get(si.item_id)
                item_name = item_cfg.get_display_name() if item_cfg else si.item_id
                equip_info = f"（{si.equipment_summary}）" if si.equipment_summary else ""
                qty_str = f" ×{si.quantity}" if si.quantity > 1 else ""
                lines.append(
                    f"**{i}.** {item_name}{equip_info}{qty_str}\n"
                    f"   💰 {si.unit_price:,}💰　{cmd('下架', f'下摊 {i}')}"
                )

        lines.append("***")
        lines.append(
            f"{cmd('上摊 物品名 单价', '上摊 ')} | {cmd('收摊')} | "
            f"{cmd('摊位名 名称', '摊位名 ')} | {cmd('吆喝 内容', '吆喝 ')}"
        )

    await my_stall_cmd.finish(build_markdown("\n".join(lines)))


# ==================== 摊位名 / 吆喝 ====================

@set_name_cmd.handle()
async def handle_set_name(event: MessageEvent, args: Message = CommandArg()):
    raw = args.extract_plain_text().strip()
    if not raw:
        await set_name_cmd.finish(message_add_head("📋 格式：【摊位名 名称】", event))

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await set_name_cmd.finish(message_add_head("⛔ 请先创建角色", event))

        success, msg = await stall_service.set_stall_name(uow, player, raw)
        if success:
            await uow.commit()

    await set_name_cmd.finish(message_add_head(msg, event))


@set_shout_cmd.handle()
async def handle_set_shout(event: MessageEvent, args: Message = CommandArg()):
    raw = args.extract_plain_text().strip()
    if not raw:
        await set_shout_cmd.finish(message_add_head("📋 格式：【吆喝 内容】", event))

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await set_shout_cmd.finish(message_add_head("⛔ 请先创建角色", event))

        success, msg = await stall_service.set_shout(uow, player, raw)
        if success:
            await uow.commit()

    await set_shout_cmd.finish(message_add_head(msg, event))


# ==================== 买摊 ====================

@buy_cmd.handle()
async def handle_buy(event: MessageEvent, args: Message = CommandArg()):
    """格式：买摊 摊主UID 序号 [数量]"""
    raw = args.extract_plain_text().strip()
    parts = raw.split()

    if len(parts) < 2:
        await buy_cmd.finish(message_add_head(
            "📋 购买格式：\n"
            "【买摊 摊主UID 序号 [数量]】\n"
            "━━━━━━━━━━━━━\n"
            "示例：买摊 123 1\n"
            "💡 在城镇【观察】可查看当地摊位",
            event
        ))

    try:
        seller_uid = int(parts[0])
        slot_index = int(parts[1])
    except ValueError:
        await buy_cmd.finish(message_add_head("⛔ UID和序号必须是整数", event))

    quantity = 1
    if len(parts) >= 3:
        try:
            quantity = int(parts[2])
            if quantity < 1:
                raise ValueError
        except ValueError:
            await buy_cmd.finish(message_add_head("⛔ 数量必须是正整数", event))

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await buy_cmd.finish(message_add_head("⛔ 请先创建角色", event))

        # 检查买家必须在城镇
        region = player.get_current_region() if hasattr(player, 'get_current_region') else "大都会"
        buyer_town = stall_service.get_town_name(player.x, player.y, region)
        if not buyer_town:
            await buy_cmd.finish(message_add_head("⛔ 必须在城镇才能购买摊位商品", event))

        success, msg = await stall_service.buy_item(uow, player, seller_uid, slot_index, quantity)
        if success:
            await uow.commit()

    await buy_cmd.finish(message_add_head(msg, event))


# ==================== 摊位 UID ====================

@view_stall_cmd.handle()
async def handle_view_stall(event: MessageEvent, args: Message = CommandArg()):
    """格式：摊位 UID（需在同一城镇）"""
    raw = args.extract_plain_text().strip()

    if not raw:
        await view_stall_cmd.finish(message_add_head(
            "📋 格式：【摊位 UID】\n"
            "💡 在城镇【观察】可查看当地摊位",
            event
        ))

    try:
        target_uid = int(raw)
    except ValueError:
        await view_stall_cmd.finish(message_add_head("⛔ UID必须是整数", event))

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await view_stall_cmd.finish(message_add_head("⛔ 请先创建角色", event))

        # 检查玩家必须在城镇
        region = player.get_current_region() if hasattr(player, 'get_current_region') else "大都会"
        my_town = stall_service.get_town_name(player.x, player.y, region)
        if not my_town:
            await view_stall_cmd.finish(message_add_head("⛔ 必须在城镇才能查看摊位", event))

        # 查找摊主
        from ..models.player import Player
        stmt = select(Player).where(Player.uid == target_uid, Player.server_id == player.server_id)
        result = await uow.session.execute(stmt)
        target = result.scalars().first()
        if not target:
            await view_stall_cmd.finish(message_add_head(f"⛔ 未找到UID为{target_uid}的玩家", event))

        stall = await uow.player_stalls.get_active_by_player(target.id)
        if not stall:
            await view_stall_cmd.finish(message_add_head("⛔ 该玩家没有摆摊", event))
        if stall.server_id != player.server_id:
            await view_stall_cmd.finish(message_add_head("⛔ 该玩家没有摆摊", event))

        # 检查是否同城镇
        if stall.city_name != my_town:
            await view_stall_cmd.finish(message_add_head(
                f"⛔ 该摊位在「{stall.city_name}」，你在「{my_town}」\n"
                f"💡 请先导航到对应城镇", event
            ))

        items = await uow.stall_items.find_by_stall(stall.id)

        now = datetime.now()
        remaining = stall.expires_at - now
        remain_h = max(0, int(remaining.total_seconds() // 3600))
        remain_m = max(0, int((remaining.total_seconds() % 3600) // 60))
        remain_str = f"{remain_h}h{remain_m}m" if remain_h > 0 else f"{remain_m}m"

        stall_display = stall.stall_name or f"{stall.player_name}的摊位"

        lines = [
            f"# 🏪 {stall_display}",
            f"👤 {stall.player_name} [UID:{stall.player_uid}]",
            f"📍 {stall.city_name}　⏰ 剩余{remain_str}",
        ]
        if stall.shout_text:
            lines.append(f"📢 {stall.shout_text}")
        lines.append("***")

        if not items:
            lines.append("摊位上没有商品")
        else:
            for i, si in enumerate(items, 1):
                item_cfg_i = config.items_config["by_id"].get(si.item_id)
                item_name = item_cfg_i.get_display_name() if item_cfg_i else si.item_id
                equip_info = f"（{si.equipment_summary}）" if si.equipment_summary else ""
                qty_str = f" ×{si.quantity}" if si.quantity > 1 else ""
                lines.append(
                    f"**{i}.** {item_name}{equip_info}{qty_str}\n"
                    f"   💰 **{si.unit_price:,}**💰　"
                    f"{cmd('购买', f'买摊 {stall.player_uid} {i}')}"
                )

        lines.append("***")
        lines.append(f"{cmd('观察')} | {cmd('帮助')}")

    await view_stall_cmd.finish(build_markdown("\n".join(lines)))
