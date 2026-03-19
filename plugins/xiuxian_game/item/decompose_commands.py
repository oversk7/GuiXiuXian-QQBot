"""
分解系统命令处理

指令：
- 【分解 装备编号/名称】 - 分解装备获得洗词石+铭文碎片
"""

import random

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..config import config
from .decompose_service import validate_decompose, calculate_decompose_yields, FRAGMENT_ITEM_ID


decompose_cmd = on_command("分解", priority=5, block=True)


@decompose_cmd.handle()
async def handle_decompose(event: MessageEvent, args: Message = CommandArg()):
    raw_args = args.extract_plain_text().strip()
    if not raw_args:
        await decompose_cmd.finish("用法：【分解 装备编号/名称】\n分解装备获得洗词石，带T2词缀的装备可获得铭文碎片")

    msg = ""
    async with safe_session() as session:
        player = await Player.get_player_by_event(event, session)
        if not player:
            await decompose_cmd.finish("你还没有创建角色")

        equipment = await _find_equipment(session, player.id, raw_args)
        if not equipment:
            await decompose_cmd.finish(f"未找到装备：{raw_args}")

        can_decompose, reason = validate_decompose(equipment)
        if not can_decompose:
            await decompose_cmd.finish(reason)

        equip_name = equipment.config.name if equipment.config else equipment.item_id

        rng = random.Random()
        result = calculate_decompose_yields(equipment, rng)

        # 回收孔位中的宝石/铭文
        recovered_items = []
        if equipment.gem_slots_data:
            for slot_val in list(equipment.gem_slots_data.values()):
                if not slot_val:
                    continue
                if isinstance(slot_val, dict):
                    insc_id = slot_val.get("item_id", "")
                    insc_values = slot_val.get("values", {})
                    if not isinstance(insc_values, list):
                        insc_values = [insc_values]
                    inst = ItemInstance(
                        player_id=player.id,
                        item_id=insc_id,
                        quantity=1,
                        extra_attrs={"_inscription_values": insc_values},
                    )
                    session.add(inst)
                    insc_cfg = config.items_config["by_id"].get(insc_id)
                    recovered_items.append(insc_cfg.name if insc_cfg else insc_id)
                else:
                    try:
                        await ItemInstance.add_item(session, player.id, slot_val, 1)
                        gem_cfg = config.items_config["by_id"].get(slot_val)
                        recovered_items.append(gem_cfg.name if gem_cfg else slot_val)
                    except ValueError:
                        gem_cfg = config.items_config["by_id"].get(slot_val)
                        gold_value = gem_cfg.price if gem_cfg else 1000
                        player.gold += gold_value
                        recovered_items.append(f"{gem_cfg.name if gem_cfg else slot_val}(转为{gold_value}金币)")

        # 发放洗词石
        if result.reroll_stones > 0:
            await ItemInstance.add_item(session, player.id, "affix_reroll_stone", result.reroll_stones)

        # 发放铭文碎片
        if result.fragment_count > 0:
            await ItemInstance.add_item(session, player.id, FRAGMENT_ITEM_ID, result.fragment_count)

        # 删除装备
        await session.delete(equipment)

        # 构建消息
        lines = [f"分解成功：{equip_name}"]
        lines.append(f"  获得洗词石 x{result.reroll_stones}")
        if result.fragment_count > 0:
            lines.append(f"  获得铭文碎片 x{result.fragment_count}")
        if recovered_items:
            lines.append(f"  回收镶嵌物：{'、'.join(recovered_items)}")
        msg = "\n".join(lines)

    await decompose_cmd.finish(Message(msg))


async def _find_equipment(session, player_id: str, keyword: str):
    """按编号或名称查找装备"""
    try:
        idx = int(keyword)
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player_id,
        ).order_by(ItemInstance.id)
        all_items = (await session.execute(stmt)).scalars().all()
        equips = [i for i in all_items if i.is_equipment]
        if 1 <= idx <= len(equips):
            return equips[idx - 1]
    except ValueError:
        pass

    stmt = select(ItemInstance).where(
        ItemInstance.player_id == player_id,
    )
    all_items = (await session.execute(stmt)).scalars().all()
    for item in all_items:
        if item.is_equipment and item.config and keyword in item.config.name:
            return item

    return None
