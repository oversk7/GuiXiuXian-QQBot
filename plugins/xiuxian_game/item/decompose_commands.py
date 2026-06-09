"""
分解系统命令处理

指令：
- 【分解 装备编号/名称】 - 分解装备获得洗词石+铭文碎片
"""

import time
import random

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..config import config
from ..platform_utils import require_player
from ..utils_markdown import build_markdown, cmd
from .decompose_service import validate_decompose, calculate_decompose_yields, FRAGMENT_ITEM_ID

# 分解选择状态：{player_id: {"ids": [...], "summaries": [...], "timestamp": float}}
_decompose_selection_state: dict = {}
SELECTION_TIMEOUT = 120  # 选择超时秒数

decompose_cmd = on_command("分解", priority=9, block=True)
decompose_select_cmd = on_command("分解选择", priority=4, block=True)


@decompose_cmd.handle()
async def handle_decompose(event: MessageEvent, args: Message = CommandArg()):
    raw_args = args.extract_plain_text().strip()
    if not raw_args:
        await decompose_cmd.finish("用法：【分解 装备编号/名称】\n分解装备获得洗词石，带T2词缀的装备可获得铭文碎片")

    async with safe_session() as session:
        player = await require_player(session, event, decompose_cmd)

        # 按编号精确查找
        if raw_args.isdigit():
            equipment = await _find_equipment_by_index(session, player.id, int(raw_args))
            if not equipment:
                await decompose_cmd.finish(f"未找到装备编号：{raw_args}")
            await _do_decompose(session, player, equipment)
            return

        # 按名称查找——可能匹配多件
        matches = await _find_equipments_by_name(session, player.id, raw_args)
        if not matches:
            await decompose_cmd.finish(f"未找到装备：{raw_args}")

        if len(matches) == 1:
            # 只有一件，直接分解
            await _do_decompose(session, player, matches[0])
            return

        # 多件同名装备，显示选择列表
        from ..economy.equipment_trade_service_new import EquipmentTradeService as ETSNew
        ids = [eq.id for eq in matches]
        summaries = [ETSNew.generate_instance_summary(eq) for eq in matches]

        _decompose_selection_state[player.id] = {
            "ids": ids,
            "summaries": summaries,
            "timestamp": time.time(),
        }

        lines = ["# 🔨 选择要分解的装备", "***"]
        for i, (eid, summary) in enumerate(zip(ids, summaries), 1):
            lines.append(f"{i}. 🆔**{eid}** {summary}")
        lines.append("***")
        lines.append("💡 回复 " + cmd("分解选择 序号", "分解选择 1") + " 选择装备")

        await decompose_cmd.finish(build_markdown("\n".join(lines)))


@decompose_select_cmd.handle()
async def handle_decompose_select(event: MessageEvent, args: Message = CommandArg()):
    """处理分解选择回调"""
    raw = args.extract_plain_text().strip()

    async with safe_session() as session:
        player = await require_player(session, event, decompose_select_cmd)

        state = _decompose_selection_state.get(player.id)
        if not state or time.time() - state["timestamp"] > SELECTION_TIMEOUT:
            _decompose_selection_state.pop(player.id, None)
            await decompose_select_cmd.finish("⛔ 选择已过期，请重新输入【分解 装备名称】")

        if not raw.isdigit():
            await decompose_select_cmd.finish("⛔ 请输入序号（如：分解选择 1）")

        idx = int(raw)
        ids = state["ids"]
        if idx < 1 or idx > len(ids):
            await decompose_select_cmd.finish(f"⛔ 请输入 1~{len(ids)} 之间的序号")

        instance_id = ids[idx - 1]
        _decompose_selection_state.pop(player.id, None)

        equipment = await session.get(ItemInstance, instance_id)
        if not equipment or equipment.player_id != player.id:
            await decompose_select_cmd.finish("⛔ 装备不存在或不属于你")

        await _do_decompose(session, player, equipment)


async def _do_decompose(session, player: Player, equipment: ItemInstance):
    """执行分解逻辑"""
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


async def _find_equipment_by_index(session, player_id: str, idx: int):
    """按装备栏编号查找"""
    stmt = select(ItemInstance).where(
        ItemInstance.player_id == player_id,
    ).order_by(ItemInstance.id)
    all_items = (await session.execute(stmt)).scalars().all()
    equips = [i for i in all_items if i.is_equipment]
    if 1 <= idx <= len(equips):
        return equips[idx - 1]
    return None


async def _find_equipments_by_name(session, player_id: str, keyword: str):
    """按名称查找所有匹配的装备"""
    stmt = select(ItemInstance).where(
        ItemInstance.player_id == player_id,
    )
    all_items = (await session.execute(stmt)).scalars().all()
    return [
        item for item in all_items
        if item.is_equipment and item.config and keyword in item.config.name
    ]
