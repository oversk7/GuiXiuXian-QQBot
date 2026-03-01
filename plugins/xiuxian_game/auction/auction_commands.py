"""
拍卖行命令处理器

命令列表：
- 【上架拍卖 物品名 起拍价 时长(h) [一口价]】 - 发起拍卖
- 【出价 拍卖ID 金额】                          - 参与竞价
- 【拍卖行 [页码]】                              - 查看当前拍卖列表
- 【我的拍卖】                                   - 查看自己的拍卖
- 【撤拍 拍卖ID】                               - 撤回拍卖（无人出价时）
"""

from datetime import datetime
from typing import Optional

from nonebot import on_command
from nonebot.adapters.qq import Message, MessageEvent
from nonebot.params import CommandArg

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.db import AsyncSessionLocal
from ..platform_utils import get_unified_player, is_guild_message
from ..utils import message_add_head
from ..config import config
from . import auction_service

# ==================== 命令定义 ====================

list_auction_cmd = on_command(
    "上架拍卖",
    aliases={"拍卖上架", "发起拍卖"},
    block=True,
    priority=5,
)
bid_cmd = on_command(
    "出价",
    aliases={"竞价", "拍卖出价"},
    block=True,
    priority=5,
)
auction_hall_cmd = on_command(
    "拍卖行",
    aliases={"查看拍卖", "拍卖列表", "拍卖大厅"},
    block=True,
    priority=5,
)
my_auction_cmd = on_command(
    "我的拍卖",
    aliases={"我的拍卖品", "查看我的拍卖"},
    block=True,
    priority=5,
)
cancel_auction_cmd = on_command(
    "撤拍",
    aliases={"取消拍卖", "拍卖撤回"},
    block=True,
    priority=5,
)


# ==================== 上架拍卖 ====================

@list_auction_cmd.handle()
async def handle_list_auction(event: MessageEvent, args: Message = CommandArg()):
    """
    格式：上架拍卖 物品名 起拍价 时长(h) [一口价]
    例如：上架拍卖 玄铁剑 50000 12
         上架拍卖 玄铁剑 50000 24 200000
    """
    raw = args.extract_plain_text().strip()
    parts = raw.split()

    if len(parts) < 3:
        await list_auction_cmd.finish(message_add_head(
            "📋 上架拍卖格式：\n"
            "【上架拍卖 物品名 起拍价 时长(小时) [一口价]】\n"
            "━━━━━━━━━━━━━\n"
            "示例：\n"
            "• 上架拍卖 玄铁剑 50000 12\n"
            "• 上架拍卖 玄铁剑 50000 24 200000（带一口价）\n"
            f"⏰ 时长范围：{auction_service.MIN_DURATION_HOURS}~{auction_service.MAX_DURATION_HOURS}小时\n"
            f"💰 起拍价最低：{auction_service.MIN_START_PRICE}💰\n"
            "⚠️ 跑商商品不可拍卖",
            event
        ))

    item_name = parts[0]
    result_msg = ""

    try:
        start_price = int(parts[1])
        duration_hours = int(parts[2])
        buyout_price = int(parts[3]) if len(parts) >= 4 else None
    except ValueError:
        await list_auction_cmd.finish(message_add_head("⛔ 价格和时长必须是整数", event))

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            if is_guild_message(event):
                result_msg = "⛔ 你还没有创建角色或绑定账号"
            else:
                result_msg = "⛔ 请先创建角色"
        else:
            success, msg = await auction_service.list_auction(
                uow, player, item_name, start_price, duration_hours, buyout_price
            )
            if success:
                await uow.commit()
            result_msg = msg

    await list_auction_cmd.finish(message_add_head(result_msg, event))


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
        total = await uow.auction_items.count_active_auctions()
        if total == 0:
            result_msg = "🏛️ 拍卖行\n━━━━━━━━━━━━━\n当前暂无任何拍卖，快去上架稀有物品吧！"
        else:
            import math
            total_pages = math.ceil(total / page_size)
            page = min(page, total_pages)
            auctions = await uow.auction_items.find_active_auctions(page, page_size)

            lines = [
                f"🏛️ 拍卖行（第{page}/{total_pages}页，共{total}件）",
                "━━━━━━━━━━━━━",
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

                bid_info = f"{a.current_price:,}💰" if a.has_bidder else f"起拍{a.current_price:,}💰"
                buyout_str = f" | 一口价{a.buyout_price:,}💰" if a.buyout_price else ""

                lines.append(
                    f"#{a.id} {item_name}\n"
                    f"   💰{bid_info}{buyout_str} | ⏰{remain_str}剩余 | 📊{a.bid_count}次出价"
                )

            lines.append("━━━━━━━━━━━━━")
            lines.append("💡【出价 编号 金额】参与竞价")
            if total_pages > 1:
                lines.append(f"💡【拍卖行 页码】查看更多")
            result_msg = "\n".join(lines)

    await auction_hall_cmd.finish(message_add_head(result_msg, event))


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
            auctions = await uow.auction_items.find_seller_active_auctions(player.id)
            if not auctions:
                result_msg = "📋 你当前没有进行中的拍卖\n💡 使用【上架拍卖 物品名 起拍价 时长】发起拍卖"
            else:
                lines = [f"📋 我的拍卖（进行中，共{len(auctions)}件）", "━━━━━━━━━━━━━"]
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
                        bid_info = f"当前价：{a.current_price:,}💰（{a.bid_count}次出价）"
                    else:
                        bid_info = "暂无人出价"

                    lines.append(
                        f"#{a.id} {item_name}\n"
                        f"   💰{bid_info}\n"
                        f"   ⏰剩余：{remain_str}"
                    )
                lines.append("━━━━━━━━━━━━━")
                lines.append("💡 无人出价时可使用【撤拍 编号】撤回")
                result_msg = "\n".join(lines)

    await my_auction_cmd.finish(message_add_head(result_msg, event))


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
