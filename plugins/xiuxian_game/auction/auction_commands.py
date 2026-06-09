"""
拍卖行命令处理器

命令列表：
- 【上架拍卖 物品名 起拍价 时长(h) [一口价]】 - 发起拍卖（装备会弹出选择列表）
- 【出价 拍卖ID 金额】                          - 参与竞价
- 【拍卖行 [页码]】                              - 查看当前拍卖列表
- 【我的拍卖】                                   - 查看自己的拍卖
- 【撤拍 拍卖ID】                               - 撤回拍卖（无人出价时）
- 【拍卖详情 拍卖ID】                            - 查看竞价历史（出价人、金额、时间）
"""

import time
from datetime import datetime
from typing import Optional

from nonebot import on_command, on_message
from nonebot.adapters.qq import Message, MessageEvent
from nonebot.params import CommandArg
from sqlalchemy import select

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.db import AsyncSessionLocal
from ..models.inventory import ItemInstance, ItemType
from ..economy.equipment_trade_service import EquipmentTradeService
from ..platform_utils import get_unified_player, is_guild_message, require_player
from ..utils import message_add_head
from ..utils_markdown import cmd, build_markdown
from ..config import config
from . import auction_service

# ==================== 命令定义 ====================

list_auction_cmd = on_command(
    "上架拍卖",
    aliases={"拍卖上架", "发起拍卖"},
    block=True,
    priority=13,
)
bid_cmd = on_command(
    "出价",
    aliases={"竞价", "拍卖出价"},
    block=True,
    priority=13,
)
auction_hall_cmd = on_command(
    "拍卖行",
    aliases={"查看拍卖", "拍卖列表", "拍卖大厅"},
    block=True,
    priority=13,
)
my_auction_cmd = on_command(
    "我的拍卖",
    aliases={"我的拍卖品", "查看我的拍卖"},
    block=True,
    priority=13,
)
cancel_auction_cmd = on_command(
    "撤拍",
    aliases={"取消拍卖", "拍卖撤回"},
    block=True,
    priority=13,
)
auction_detail_cmd = on_command(
    "拍卖详情",
    aliases={"竞价记录", "拍卖记录"},
    block=True,
    priority=13,
)

# ==================== 装备选择状态管理 ====================

# {player_id: {"equipment_ids": [...], "equipment_summaries": [...],
#              "item_name": str, "start_price": int, "duration_hours": int,
#              "buyout_price": int|None, "timestamp": float}}
_auction_equipment_selection_state: dict = {}
_AUCTION_SELECTION_EXPIRE = 120  # 秒，超时自动清理


def _cleanup_expired_auction_states():
    now = time.time()
    expired = [
        uid for uid, s in _auction_equipment_selection_state.items()
        if now - s.get("timestamp", 0) > _AUCTION_SELECTION_EXPIRE
    ]
    for uid in expired:
        del _auction_equipment_selection_state[uid]


# 用于捕获玩家回复序号的消息处理器（低优先级，不阻断其他命令）
auction_equipment_selection_handler = on_message(priority=6, block=False)

# ==================== 上架拍卖 ====================

@list_auction_cmd.handle()
async def handle_list_auction(event: MessageEvent, args: Message = CommandArg()):
    """
    格式：上架拍卖 物品名 起拍价 时长(h) [一口价]
    例如：上架拍卖 棺材钉 50000 12
         上架拍卖 碎颅制服 50000 24 200000
    """
    raw = args.extract_plain_text().strip()
    parts = raw.split()

    if len(parts) < 3:
        await list_auction_cmd.finish(message_add_head(
            "📋 上架拍卖格式：\n"
            "【上架拍卖 物品名 起拍价 时长(小时) [一口价] [宣传语]】\n"
            "━━━━━━━━━━━━━\n"
            "示例：\n"
            "• 上架拍卖 棺材钉 50000 12\n"
            "• 上架拍卖 碎颅制服 50000 24 200000（带一口价）\n"
            "• 上架拍卖 碎颅制服 50000 24 200000 全服最强武器\n"
            f"⏰ 时长范围：{auction_service.MIN_DURATION_HOURS}~{auction_service.MAX_DURATION_HOURS}小时\n"
            "💰 起拍价最低：物品系统估价\n"
            "⚠️ 跑商商品不可拍卖",
            event
        ))

    item_name = parts[0]
    description = None

    try:
        start_price = int(parts[1])
        duration_hours = int(parts[2])
        # parts[3] 如果是数字则为一口价，否则当作宣传语开头
        if len(parts) >= 4:
            try:
                buyout_price = int(parts[3])
                # 一口价后面的全部文字作为宣传语
                if len(parts) >= 5:
                    description = " ".join(parts[4:])
            except ValueError:
                buyout_price = None
                description = " ".join(parts[3:])
        else:
            buyout_price = None
    except ValueError:
        await list_auction_cmd.finish(message_add_head("⛔ 价格和时长必须是整数", event))

    if description and len(description) > 32:
        await list_auction_cmd.finish(message_add_head("⛔ 宣传语最多32个字", event))

    # 提前识别物品配置，装备走选择流程
    item_cfg = config.items_config["by_name"].get(item_name)
    if not item_cfg:
        await list_auction_cmd.finish(message_add_head(f"⛔ 未找到物品「{item_name}」", event))

    if item_cfg.type in (ItemType.EQUIPMENT, ItemType.INSCRIPTION):
        await _handle_instance_auction_listing(event, item_cfg, start_price, duration_hours, buyout_price, description)
        return  # finish() 已在内部调用，此行不会执行

    # 普通物品：直接上架
    result_msg = ""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            if is_guild_message(event):
                result_msg = "⛔ 你还没有创建角色或绑定账号"
            else:
                result_msg = "⛔ 请先创建角色"
        else:
            success, msg = await auction_service.list_auction(
                uow, player, item_name, start_price, duration_hours, buyout_price,
                description=description,
            )
            if success:
                await uow.commit()
            result_msg = msg

    await list_auction_cmd.finish(message_add_head(result_msg, event))


async def _handle_instance_auction_listing(
    event: MessageEvent,
    item_cfg,
    start_price: int,
    duration_hours: int,
    buyout_price: Optional[int],
    description: Optional[str] = None,
):
    """装备/铭文拍卖：查询可用实例，单件直接上架，多件让玩家选择"""
    is_inscription = item_cfg.type == ItemType.INSCRIPTION
    type_name = "铭文" if is_inscription else "装备"

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await require_player(uow.session, event, list_auction_cmd)

        # 提前检查上架数量限制
        active_auctions = await uow.auction_items.find_seller_active_auctions(player.id, player.server_id)
        if len(active_auctions) >= auction_service.MAX_AUCTION_LISTINGS:
            await list_auction_cmd.finish(message_add_head(
                f"⛔ 你已有 {auction_service.MAX_AUCTION_LISTINGS} 件物品正在拍卖，无法继续上架", event
            ))

        # 查询背包中所有该物品的可用实例
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
        ]

        if not available:
            await list_auction_cmd.finish(message_add_head(
                f"⛔ 背包中没有可拍卖的「{item_cfg.name}」", event
            ))

        if len(available) == 1:
            # 只有一件，直接上架
            success, msg = await auction_service.list_auction(
                uow, player, item_cfg.name, start_price, duration_hours, buyout_price,
                equipment_instance_id=available[0].id,
                description=description,
            )
            if success:
                await uow.commit()
            await list_auction_cmd.finish(message_add_head(msg, event))

        # 多件：生成摘要，保存选择状态，展示列表
        from ..economy.equipment_trade_service_new import EquipmentTradeService as ETSNew
        summaries = [ETSNew.generate_instance_summary(e) for e in available]
        equipment_ids = [e.id for e in available]

        _cleanup_expired_auction_states()
        _auction_equipment_selection_state[player.id] = {
            "equipment_ids": equipment_ids,
            "equipment_summaries": summaries,
            "item_name": item_cfg.name,
            "start_price": start_price,
            "duration_hours": duration_hours,
            "buyout_price": buyout_price,
            "description": description,
            "timestamp": time.time(),
        }

        lines = [
            f"📋 选择要上架拍卖的「{item_cfg.name}」：",
            "━━━━━━━━━━━━━",
        ]
        for i, (eq_id, summary) in enumerate(zip(equipment_ids, summaries), 1):
            lines.append(f"{i}. 🆔{eq_id} {summary}")
        lines.extend(["━━━━━━━━━━━━━", "💡 回复序号选择（如：1），或回复 取消"])

        await list_auction_cmd.finish(message_add_head("\n".join(lines), event))


@auction_equipment_selection_handler.handle()
async def handle_auction_equipment_selection(event: MessageEvent):
    """捕获玩家回复的装备序号，完成装备拍卖上架"""
    _cleanup_expired_auction_states()

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            return
        if player.id not in _auction_equipment_selection_state:
            return

        message_text = event.get_message().extract_plain_text().strip()

        # 取消
        if message_text in ["取消", "cancel", "0"]:
            del _auction_equipment_selection_state[player.id]
            await auction_equipment_selection_handler.finish(
                message_add_head("❌ 已取消装备拍卖", event)
            )

        # 非数字直接放行，不处理
        if not message_text.isdigit():
            return

        try:
            index = int(message_text) - 1
            if index < 0:
                raise ValueError
        except ValueError:
            return

        state = _auction_equipment_selection_state[player.id]
        equipment_ids = state["equipment_ids"]

        if index >= len(equipment_ids):
            await auction_equipment_selection_handler.finish(
                message_add_head("⛔ 无效的序号，请重新选择或回复 取消", event)
            )

        equipment_id = equipment_ids[index]
        item_name = state["item_name"]
        start_price = state["start_price"]
        duration_hours = state["duration_hours"]
        buyout_price = state["buyout_price"]
        sel_description = state.get("description")

        del _auction_equipment_selection_state[player.id]

        success, msg = await auction_service.list_auction(
            uow, player, item_name, start_price, duration_hours, buyout_price,
            equipment_instance_id=equipment_id,
            description=sel_description,
        )
        if success:
            await uow.commit()
        await auction_equipment_selection_handler.finish(message_add_head(msg, event))




# ==================== 出价竞拍 ====================

@bid_cmd.handle()
async def handle_bid(event: MessageEvent, args: Message = CommandArg()):
    """
    格式：出价 拍卖ID 金额
    例如：出价 5 88000
    """
    raw = args.extract_plain_text().strip()
    parts = raw.split()

    if len(parts) < 2:
        await bid_cmd.finish(message_add_head(
            "📋 出价格式：\n"
            "【出价 拍卖编号 金额】\n"
            "━━━━━━━━━━━━━\n"
            "示例：出价 5 88000\n"
            "💡 使用【拍卖行】查看当前拍卖编号",
            event
        ))

    result_msg = ""

    try:
        auction_id = int(parts[0])
        bid_amount = int(parts[1])
    except ValueError:
        await bid_cmd.finish(message_add_head("⛔ 拍卖编号和金额必须是整数", event))

    if bid_amount <= 0:
        await bid_cmd.finish(message_add_head("⛔ 出价金额必须大于0", event))

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            if is_guild_message(event):
                result_msg = "⛔ 你还没有创建角色或绑定账号"
            else:
                result_msg = "⛔ 请先创建角色"
        else:
            success, msg = await auction_service.place_bid(uow, player, auction_id, bid_amount)
            if success:
                await uow.commit()
            result_msg = msg

    await bid_cmd.finish(message_add_head(result_msg, event))


# ==================== 查看拍卖行 ====================

@auction_hall_cmd.handle()
async def handle_auction_hall(event: MessageEvent, args: Message = CommandArg()):
    """
    格式：拍卖行 [页码]
    """
    raw = args.extract_plain_text().strip()
    try:
        page = max(1, int(raw)) if raw else 1
    except ValueError:
        page = 1

    page_size = 8
    result_msg = ""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        from ..platform_utils import get_event_server_id
        server_id = await get_event_server_id(uow.session, event)
        total = await uow.auction_items.count_active_auctions(server_id)
        if total == 0:
            result_msg = "🏛️ 拍卖行\n━━━━━━━━━━━━━\n当前暂无任何拍卖，快去上架稀有物品吧！"
        else:
            import math
            total_pages = math.ceil(total / page_size)
            page = min(page, total_pages)
            auctions = await uow.auction_items.find_active_auctions(page, page_size, server_id)

            lines = [
                "# 🏛️ 拍卖行",
                f"第**{page}**/{total_pages}页　共**{total}**件",
                "***",
            ]
            now = datetime.now()
            for a in auctions:
                item_cfg = config.items_config["by_id"].get(a.item_id)
                item_name = item_cfg.get_display_name() if item_cfg else a.item_id
                if a.equipment_summary:
                    item_name += f"（{a.equipment_summary}）"
                elif a.quantity > 1:
                    item_name += f" ×{a.quantity}"

                remaining = a.end_at - now
                remain_h = int(remaining.total_seconds() // 3600)
                remain_m = int((remaining.total_seconds() % 3600) // 60)
                remain_str = f"{remain_h}h{remain_m}m" if remain_h > 0 else f"{remain_m}m"

                bid_info = f"{a.current_price:,}💰（{a.current_bidder_name} [UID:{a.current_bidder_uid}] 领先）" if a.has_bidder else f"起拍 {a.current_price:,}💰"
                buyout_str = f"\n   🎯 一口价：{a.buyout_price:,}💰" if a.buyout_price else ""
                seller_str = f"{a.seller_name or '未知'} [UID:{a.seller_uid}]"

                aid = a.id
                desc_str = f"\n   💬 {a.description}" if a.description else ""
                lines.append(
                    f"**#{aid}** {item_name}\n"
                    f"👤 {seller_str}　💰 {bid_info}{buyout_str}{desc_str}\n"
                    f"⏰ {remain_str}　📊{a.bid_count}次　"
                    f"{cmd('详情', f'拍卖详情 {aid}')}"
                )
                lines.append("")

            lines.append("***")
            nav = []
            if page > 1:
                nav.append(cmd("上一页", f"拍卖行 {page - 1}"))
            if page < total_pages:
                nav.append(cmd("下一页", f"拍卖行 {page + 1}"))
            if nav:
                lines.append(" | ".join(nav))
            lines.append(cmd("拍卖行") + " | " + cmd("我的拍卖") + " | " + cmd("帮助"))
            result_msg = "\n".join(lines)

    await auction_hall_cmd.finish(build_markdown(result_msg))


# ==================== 我的拍卖 ====================

@my_auction_cmd.handle()
async def handle_my_auction(event: MessageEvent):
    """查看自己发起的拍卖"""
    result_msg = ""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            if is_guild_message(event):
                result_msg = "⛔ 你还没有创建角色或绑定账号"
            else:
                result_msg = "⛔ 请先创建角色"
        else:
            auctions = await uow.auction_items.find_seller_active_auctions(player.id, player.server_id)
            if not auctions:
                result_msg = "📋 你当前没有进行中的拍卖\n💡 使用【上架拍卖 物品名 起拍价 时长】发起拍卖"
            else:
                lines = [
                    "# 📋 我的拍卖",
                    f"进行中　共**{len(auctions)}**件",
                    "***",
                ]
                now = datetime.now()
                for a in auctions:
                    item_cfg = config.items_config["by_id"].get(a.item_id)
                    item_name = item_cfg.get_display_name() if item_cfg else a.item_id
                    if a.equipment_summary:
                        item_name += f"（{a.equipment_summary}）"

                    remaining = a.end_at - now
                    remain_h = int(remaining.total_seconds() // 3600)
                    remain_m = int((remaining.total_seconds() % 3600) // 60)
                    remain_str = f"{remain_h}h{remain_m}m" if remain_h > 0 else f"{remain_m}m"

                    if a.has_bidder:
                        bid_info = f"当前价：{a.current_price:,}💰\n   📌 领先者：{a.current_bidder_name} [UID:{a.current_bidder_uid}]（{a.bid_count}次出价）"
                    else:
                        bid_info = "暂无人出价"

                    cancel_btn = cmd("撤拍", f"撤拍 {a.id}") if not a.has_bidder else ""
                    lines.append(
                        f"**#{a.id}** {item_name}\n"
                        f"💰 {bid_info}\n"
                        f"⏰ 剩余：{remain_str}　{cancel_btn}"
                    )
                    lines.append("")
                lines.append("***")
                lines.append(cmd("拍卖行") + " | " + cmd("我的拍卖") + " | " + cmd("帮助"))
                result_msg = "\n".join(lines)

    await my_auction_cmd.finish(build_markdown(result_msg))


# ==================== 撤拍 ====================

@cancel_auction_cmd.handle()
async def handle_cancel_auction(event: MessageEvent, args: Message = CommandArg()):
    """
    格式：撤拍 拍卖ID
    """
    raw = args.extract_plain_text().strip()
    result_msg = ""

    if not raw:
        await cancel_auction_cmd.finish(message_add_head(
            "📋 撤拍格式：【撤拍 拍卖编号】\n"
            "⚠️ 仅在无人出价时可以撤拍",
            event
        ))

    try:
        auction_id = int(raw)
    except ValueError:
        await cancel_auction_cmd.finish(message_add_head("⛔ 拍卖编号必须是整数", event))

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            if is_guild_message(event):
                result_msg = "⛔ 你还没有创建角色或绑定账号"
            else:
                result_msg = "⛔ 请先创建角色"
        else:
            success, msg = await auction_service.cancel_auction(uow, player, auction_id)
            if success:
                await uow.commit()
            result_msg = msg

    await cancel_auction_cmd.finish(message_add_head(result_msg, event))


# ==================== 拍卖详情 ====================

@auction_detail_cmd.handle()
async def handle_auction_detail(event: MessageEvent, args: Message = CommandArg()):
    """
    格式：拍卖详情 拍卖ID
    查看拍卖品详情及完整竞价历史（出价人、金额、时间）
    """
    raw = args.extract_plain_text().strip()
    result_msg = ""

    if not raw:
        await auction_detail_cmd.finish(message_add_head(
            "📋 格式：【拍卖详情 拍卖编号】\n"
            "💡 使用【拍卖行】查看当前拍卖编号",
            event
        ))

    try:
        auction_id = int(raw)
    except ValueError:
        await auction_detail_cmd.finish(message_add_head("⛔ 拍卖编号必须是整数", event))

    async with UnitOfWork(AsyncSessionLocal) as uow:
        from ..platform_utils import get_event_server_id
        server_id = await get_event_server_id(uow.session, event)
        auction = await uow.auction_items.get_by_id(auction_id)
        if not auction:
            result_msg = f"⛔ 拍卖 #{auction_id} 不存在"
        elif auction.server_id != server_id:
            result_msg = f"⛔ 拍卖 #{auction_id} 不存在"
        else:
            item_cfg = config.items_config["by_id"].get(auction.item_id)
            item_name = item_cfg.get_display_name() if item_cfg else auction.item_id
            if auction.equipment_summary:
                item_name += f"（{auction.equipment_summary}）"
            elif auction.quantity > 1:
                item_name += f" ×{auction.quantity}"

            status_map = {
                "active": "进行中",
                "sold": "已成交",
                "cancelled": "已撤拍",
                "expired": "流拍",
            }
            status_str = status_map.get(auction.status, auction.status)

            lines = [
                f"# 🏛️ 拍卖详情 #{auction.id}",
                f"📦 **{item_name}**",
                f"👤 卖家：{auction.seller_name or '未知'} [UID:{auction.seller_uid}]",
            ]
            if auction.description:
                lines.append(f"💬 {auction.description}")

            # 装备实例：展示完整属性详情
            if auction.is_instance_trade and auction.item_instance_id:
                equip = await uow.session.get(ItemInstance, auction.item_instance_id)
                if equip and equip.is_equipment:
                    tpl = equip.config
                    rarity_map = {
                        "white": "白色", "green": "绿色", "blue": "蓝色",
                        "purple": "紫色", "orange": "橙色", "red": "红色"
                    }
                    rarity_name = rarity_map.get(tpl.rarity, tpl.rarity)

                    lines.append(f"🎨 品质：{tpl.get_rarity_display()}{rarity_name}")
                    lines.append(f"⭐ 升阶：+{equip.upgrade_level}阶")
                    lines.append(f"🛠️ 耐久：{equip.durability}/{tpl.durability}")
                    lines.append("")

                    # 基础属性
                    upgrade_multiplier = equip.get_upgrade_bonus_multiplier()
                    if tpl.attr_bonus or tpl.attr_ratio:
                        lines.append("📈 基础属性：")
                        attr_name_map = {
                            "attack": "攻击力", "defense": "防御力", "agility": "敏捷",
                            "luck": "运气", "hp": "生命值", "mp": "理智值",
                            "max_hp": "最大生命值", "max_mp": "最大理智值"
                        }
                        if tpl.attr_bonus:
                            for k, v in tpl.attr_bonus.items():
                                current_value = int(v * upgrade_multiplier)
                                lines.append(f"  • {attr_name_map.get(k, k)}+{current_value}")
                        if tpl.attr_ratio:
                            for k, r in tpl.attr_ratio.items():
                                current_ratio = float(r) * upgrade_multiplier * 100
                                lines.append(f"  • {attr_name_map.get(k, k)}+{current_ratio:.1f}%")
                        lines.append("")

                    # 词缀详情
                    from ..item.affix_service import get_affixes_from_equipment, format_affixes_display
                    affixes = get_affixes_from_equipment(equip.extra_attrs)
                    if affixes:
                        lines.append("🔮 词缀：")
                        lines.extend(format_affixes_display(affixes))
                        lines.append("")

                    # 宝石/铭文镶嵌详情
                    if equip.available_gem_slots > 0:
                        lines.append("💎 镶嵌孔位：")
                        lines.append(f"  • 孔位：{equip.used_gem_slots}/{equip.available_gem_slots}")
                        if equip.used_gem_slots > 0:
                            from ..item.gem_socket_service_new import GemSocketService
                            from ..item.inscription_service import get_inscription_display
                            gem_info = GemSocketService.get_equipment_gem_info(equip)
                            for slot_info in gem_info:
                                if not slot_info["is_empty"]:
                                    slot_num = slot_info["slot_number"]
                                    if slot_info.get("is_inscription"):
                                        display = get_inscription_display(slot_info["inscription_data"])
                                        lines.append(f"  • 孔位{slot_num}：📜 {display}")
                                    else:
                                        gem_name = slot_info["gem_name"]
                                        gem_type = slot_info["gem_type"]
                                        lines.append(f"  • 孔位{slot_num}：{gem_type} - {gem_name}")
                        lines.append("")

                    # 特殊效果
                    if hasattr(tpl, 'special_effects') and tpl.special_effects:
                        lines.append("✨ 特殊效果：")
                        VIP_EQUIPMENT_IDS = {"vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi", "vip_robe_jingyuan_legacy", "heaven_retreat_star_blade", "vip_gui_yu", "vip_chrono_watch", "vip_longying_flash", "vip_ghost_dice", "vip_shoes_longren", "vip_pendant_fuze", "vip_huihai_xinyuan", "vip_jade_xuanxu_shuangyan"}
                        is_vip = equip.item_id in VIP_EQUIPMENT_IDS
                        unlocked_count = equip.upgrade_level // 2

                        for idx, effect in enumerate(tpl.special_effects, start=1):
                            desc = effect.get('description', '')
                            if not desc:
                                continue
                            if is_vip or idx <= unlocked_count:
                                lines.append(f"  ✅ [{idx}] {desc}")
                            else:
                                lines.append(f"  🔒 [{idx}] {desc} (需+{idx * 2}阶)")
                        lines.append("")

            lines.append(f"💰 起拍价：{auction.start_price:,}💰")
            if auction.buyout_price:
                lines.append(f"🎯 一口价：{auction.buyout_price:,}💰")
            if auction.has_bidder:
                lines.append(f"📈 当前价：{auction.current_price:,}💰（{auction.current_bidder_name} [UID:{auction.current_bidder_uid}]，共{auction.bid_count}次出价）")
            else:
                lines.append("📊 暂无人出价")

            if auction.status == "active":
                now = datetime.now()
                remaining = auction.end_at - now
                remain_h = int(remaining.total_seconds() // 3600)
                remain_m = int((remaining.total_seconds() % 3600) // 60)
                remain_str = f"{remain_h}h{remain_m}m" if remain_h > 0 else f"{remain_m}m"
                lines.append(f"⏰ 截止：{auction.end_at.strftime('%m-%d %H:%M')}（剩余{remain_str}）")
            else:
                lines.append(f"🏷️ 状态：{status_str}")

            lines.append("━━━━━━━━━━━━━")

            # 查询竞价历史
            bids = await uow.auction_bid_histories.find_by_auction(auction.id, limit=10)
            if not bids:
                lines.append("📋 竞价历史：暂无记录")
            else:
                lines.append(f"📋 竞价历史（最近{len(bids)}条）")
                for i, bid in enumerate(bids, 1):
                    bid_time = bid.bid_at.strftime("%m-%d %H:%M")
                    crown = "🥇" if i == 1 else f"{i}."
                    lines.append(f"  {crown} {bid.bidder_name} [UID:{bid.bidder_uid}]  {bid.amount:,}💰  {bid_time}")

            lines.append("***")
            if auction.status == "active":
                lines.append(cmd("拍卖行") + " | " + cmd("我的拍卖") + " | " + cmd("帮助"))
            else:
                lines.append(cmd("拍卖行") + " | " + cmd("帮助"))

            result_msg = "\n".join(lines)

    await auction_detail_cmd.finish(build_markdown(result_msg))
