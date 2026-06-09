import re

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
from ..platform_utils import require_player
from ..utils_markdown import cmd, build_markdown

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
        player = await require_player(session, event, sacrifice_cmd)

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
            f"⚙️ 祭品坠入幽冥，磷火噬啮骨肉。\n\n"
            f"**━━ 献祭结果 ━━**\n"
            f"✧ 怨念值 **+{gained}**↑\n"
            f"✧ 当前怨念值 **{player.resentment}**\n\n"
            + cmd("继续献祭", "献祭 ") + " | "
            + cmd("突破", "突破 ") + " | "
            + cmd("突破 镇厄")
        )
        await sacrifice_cmd.finish(build_markdown(msg))


@batch_sacrifice_cmd.handle()
async def handle_batch_sacrifice(event: MessageEvent, args: Message = CommandArg()):
    """一键献祭指定的材料（月卡用户专属）"""
    # 检查月卡权限
    async with safe_session() as session:
        player = await require_player(session, event, batch_sacrifice_cmd)

        # 检查是否有有效月卡
        active_cards = await MonthlyCard.get_all_active_cards(session, player.id)
        if not active_cards:
            await batch_sacrifice_cmd.finish(
                "⛔ 一键献祭是月卡用户专属功能\n"
                "💡 发送【赞助】了解月卡权益"
            )

        # 解析参数
        raw_text = args.extract_plain_text().strip()
        if not raw_text:
            await batch_sacrifice_cmd.finish(
                "⛔ 请指定要献祭的材料\n"
                "💡 示例：一键献祭 病历单 寻人启事"
            )

        # 支持空格、顿号、逗号分隔
        raw_names = re.split(r"[\s,，、]+", raw_text)
        unique_names = []
        seen = set()
        for name in raw_names:
            if not name:
                continue
            if name in seen:
                continue
            seen.add(name)
            unique_names.append(name)

        if not unique_names:
            await batch_sacrifice_cmd.finish("⛔ 未识别到有效的材料名称")

        # 校验材料配置
        item_cfgs = []
        invalid_names = []
        unsacrificable_names = []
        for name in unique_names:
            cfg = config.items_config["by_name"].get(name)
            if not cfg:
                invalid_names.append(name)
                continue

            if cfg.type.value not in ["MATERIAL", "CONSUMABLE"] or cfg.grudge_value <= 0:
                unsacrificable_names.append(name)
                continue

            item_cfgs.append(cfg)

        if invalid_names:
            await batch_sacrifice_cmd.finish(
                "⛔ 未找到以下材料：" + "、".join(invalid_names)
            )

        if unsacrificable_names:
            await batch_sacrifice_cmd.finish(
                "⛔ 以下材料无法献祭：" + "、".join(unsacrificable_names)
            )

        # 获取背包中所有指定材料
        item_ids = [cfg.item_id for cfg in item_cfgs]

        inv_rows = (await session.execute(
            select(ItemInstance).where(
                ItemInstance.player_id == player.id,
                ItemInstance.quantity > 0,
                ItemInstance.item_id.in_(item_ids)
            )
        )).scalars().all()

        quantity_map = {}
        for item_inst in inv_rows:
            quantity_map[item_inst.item_id] = (
                quantity_map.get(item_inst.item_id, 0) + item_inst.quantity
            )

        sacrificable_items = []
        missing_items = []
        for cfg in item_cfgs:
            total_qty = quantity_map.get(cfg.item_id, 0)
            if total_qty <= 0:
                missing_items.append(cfg.get_display_name())
                continue
            sacrificable_items.append((cfg, total_qty))

        if not sacrificable_items:
            await batch_sacrifice_cmd.finish("⛔ 指定的材料在背包中不存在或数量为0")

        # 批量献祭
        total_gained = 0
        sacrifice_details = []

        for item_cfg, qty in sacrificable_items:
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
        msg_lines = [
            f"💳 **月卡特权：一键献祭**",
            "",
            f"**━━ 献祭明细 ━━**",
        ]

        # 限制显示前10条，避免消息过长
        display_details = sacrifice_details[:10]
        msg_lines.extend(display_details)

        if len(sacrifice_details) > 10:
            msg_lines.append(f"  ... 还有{len(sacrifice_details) - 10}种材料")

        if missing_items:
            msg_lines.extend([
                "",
                "⚠️ 未献祭：" + "、".join(missing_items)
            ])

        msg_lines.extend([
            "",
            f"**━━ 结果 ━━**",
            f"✧ 怨念值 **+{total_gained}**↑",
            f"✧ 当前怨念值 **{player.resentment}**",
            "",
            cmd("继续献祭", "一键献祭 ") + " | "
            + cmd("突破", "突破 ") + " | "
            + cmd("突破 镇厄")
        ])

        await batch_sacrifice_cmd.finish(build_markdown("\n".join(msg_lines)))