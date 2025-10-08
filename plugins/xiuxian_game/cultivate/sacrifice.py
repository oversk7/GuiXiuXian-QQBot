from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..models.monthly_card import MonthlyCard
from ..utils import message_add_head
from ..config import config

sacrifice_cmd = on_command("献祭", block=True, priority=5)
batch_sacrifice_cmd = on_command("一键献祭", block=True, priority=5)

@sacrifice_cmd.handle()
async def handle_sacrifice(event: MessageEvent, args: Message = CommandArg()):
    """献祭材料以获取怨念值"""
    params = args.extract_plain_text().strip().split()
    if len(params) != 2:
        await sacrifice_cmd.finish("⛔ 格式错误，正确格式：献祭 [材料名称] [数量]")

    item_name, qty = params
    try:
        qty = int(qty)
        if qty <= 0:
            raise ValueError
    except ValueError:
        await sacrifice_cmd.finish("⛔ 数量必须为正整数")

    item_cfg = config.items_config["by_name"].get(item_name)
    if not item_cfg:
        await sacrifice_cmd.finish(f"⛔ 未找到物品：{item_name}")

    # 允许材料类物品和有怨念值的消耗品献祭
    if item_cfg.type.value not in ["MATERIAL", "CONSUMABLE"]:
        await sacrifice_cmd.finish("⛔ 只能献祭材料类或特殊消耗品！")

    if item_cfg.grudge_value <= 0:
        await sacrifice_cmd.finish("⛔ 该材料未蕴含怨念，无法献祭")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await sacrifice_cmd.finish("⛔ 请先创建角色")

        # 查询背包 (聚合)
        inv_rows = (await session.execute(
            select(ItemInstance).where(
                ItemInstance.player_id == player.id,
                ItemInstance.item_id == item_cfg.item_id
            )
        )).scalars().all()
        total_have = sum(r.quantity for r in inv_rows)
        if total_have < qty:
            await sacrifice_cmd.finish("⛔ 背包数量不足！")

        gained = item_cfg.grudge_value * qty
        player.resentment += gained

        # 扣除物品（优先小堆）
        success_consume = await ItemInstance.consume_item(session, player.id, item_cfg.item_id, qty)
        if not success_consume:
            await session.rollback()
            await sacrifice_cmd.finish("⛔ 扣除物品失败")

        session.add(player)
        await session.commit()

        msg = (
            f"⚙️ 祭品坠入幽冥，磷火噬啮骨肉。\n"
            "━━━━━━━━━━━━━\n"
            f"✧ 怨念值 + {gained}↑\n"
            f"✧ 当前怨念值 {player.resentment}\n"
            "━━━━━━━━━━━━━\n"
            "⬇️ 【献祭】继续投喂祭坛\n"
            "⬇️ 【突破 [镇厄]】以怨念护体突破"
        )
        await sacrifice_cmd.finish(message_add_head(msg, event))


@batch_sacrifice_cmd.handle()
async def handle_batch_sacrifice(event: MessageEvent, args: Message = CommandArg()):
    """一键献祭指定稀有度的全部材料（月卡用户专属）"""
    # 检查月卡权限
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await batch_sacrifice_cmd.finish("⛔ 请先创建角色")

        # 检查是否有有效月卡
        active_cards = await MonthlyCard.get_all_active_cards(session, player.id)
        if not active_cards:
            await batch_sacrifice_cmd.finish(
                "⛔ 一键献祭是月卡用户专属功能\n"
                "💡 发送【赞助】了解月卡权益"
            )

        # 解析参数，默认为白色
        rarity_input = args.extract_plain_text().strip().lower()
        if not rarity_input:
            rarity = "white"
        else:
            # 支持中文和英文输入
            rarity_map = {
                "白": "white", "白色": "white", "white": "white",
                "绿": "green", "绿色": "green", "green": "green",
                "蓝": "blue", "蓝色": "blue", "blue": "blue",
                "紫": "purple", "紫色": "purple", "purple": "purple",
                "橙": "orange", "橙色": "orange", "orange": "orange"
            }
            rarity = rarity_map.get(rarity_input)
            if not rarity:
                await batch_sacrifice_cmd.finish(
                    "⛔ 稀有度格式错误\n"
                    "💡 支持：白/绿/蓝/紫/橙\n"
                    "💡 示例：一键献祭 白色"
                )

        # 获取背包中所有指定稀有度的材料
        inv_rows = (await session.execute(
            select(ItemInstance).where(
                ItemInstance.player_id == player.id,
                ItemInstance.quantity > 0
            )
        )).scalars().all()

        # 筛选出可献祭的材料
        sacrificable_items = []
        for item_inst in inv_rows:
            item_cfg = config.items_config["by_id"].get(item_inst.item_id)
            if not item_cfg:
                continue

            # 检查是否是材料或消耗品，且有怨念值，且稀有度匹配
            if (item_cfg.type.value in ["MATERIAL", "CONSUMABLE"] and
                item_cfg.grudge_value > 0 and
                item_cfg.rarity == rarity):
                sacrificable_items.append((item_inst, item_cfg))

        if not sacrificable_items:
            rarity_emoji = {
                "white": "⚪", "green": "🟢", "blue": "🔵",
                "purple": "🟣", "orange": "🟠"
            }
            await batch_sacrifice_cmd.finish(
                f"⛔ 背包中没有可献祭的{rarity_emoji.get(rarity, '⚪')}{rarity.upper()}材料"
            )

        # 批量献祭
        total_gained = 0
        sacrifice_details = []

        for item_inst, item_cfg in sacrificable_items:
            qty = item_inst.quantity
            gained = item_cfg.grudge_value * qty
            total_gained += gained

            # 扣除物品
            success_consume = await ItemInstance.consume_item(
                session, player.id, item_cfg.item_id, qty
            )
            if not success_consume:
                await session.rollback()
                await batch_sacrifice_cmd.finish("⛔ 扣除物品失败，献祭已取消")

            sacrifice_details.append(f"  • {item_cfg.get_display_name()} x{qty} → {gained}怨念")

        # 更新玩家怨念值
        player.resentment += total_gained
        session.add(player)
        await session.commit()

        # 构建消息
        rarity_emoji = {
            "white": "⚪", "green": "🟢", "blue": "🔵",
            "purple": "🟣", "orange": "🟠"
        }
        rarity_name = {
            "white": "白色", "green": "绿色", "blue": "蓝色",
            "purple": "紫色", "orange": "橙色"
        }

        msg_lines = [
            f"💳 月卡特权：一键献祭",
            "━━━━━━━━━━━━━",
            f"🎯 稀有度：{rarity_emoji.get(rarity, '⚪')}{rarity_name.get(rarity, rarity.upper())}",
            f"📦 献祭数量：{len(sacrifice_details)}种材料",
            "━━━━━━━━━━━━━",
            "📋 献祭明细："
        ]

        # 限制显示前10条，避免消息过长
        display_details = sacrifice_details[:10]
        msg_lines.extend(display_details)

        if len(sacrifice_details) > 10:
            msg_lines.append(f"  ... 还有{len(sacrifice_details) - 10}种材料")

        msg_lines.extend([
            "━━━━━━━━━━━━━",
            f"✧ 怨念值 + {total_gained}↑",
            f"✧ 当前怨念值 {player.resentment}",
            "━━━━━━━━━━━━━",
            "⬇️ 【一键献祭 [稀有度]】继续献祭",
            "⬇️ 【突破 [镇厄]】以怨念护体突破"
        ])

        await batch_sacrifice_cmd.finish(message_add_head("\n".join(msg_lines), event))