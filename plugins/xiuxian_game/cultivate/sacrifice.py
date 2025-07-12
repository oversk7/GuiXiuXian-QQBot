from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..utils import message_add_head
from ..config import config

sacrifice_cmd = on_command("献祭", block=True, priority=5)

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

    if item_cfg.type.value != "MATERIAL":
        await sacrifice_cmd.finish("⛔ 只能献祭材料类物品！")

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