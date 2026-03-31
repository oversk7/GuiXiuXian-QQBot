"""
洗炼系统命令处理

指令：
- 【洗炼 装备编号/名称 词缀序号】 — 预览洗炼信息
- 【确认洗炼】 — 执行洗炼
"""

import random

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..platform_utils import get_unified_player
from ..utils_markdown import cmd, build_markdown
from .affix_service import (
    get_affixes_from_equipment, get_affix_display_name,
    get_affix_value_range_display, reroll_single_affix,
    VIP_EQUIPMENT_IDS,
)


# 洗炼待确认缓存: {user_id: {"equipment_id": int, "affix_index": int}}
_pending_rerolls: dict = {}


reroll_cmd = on_command("洗炼", priority=5, block=True)


@reroll_cmd.handle()
async def handle_reroll(event: MessageEvent, args: Message = CommandArg()):
    raw_args = args.extract_plain_text().strip().split()
    if len(raw_args) < 2:
        await reroll_cmd.finish("用法：【洗炼 装备编号/名称 词缀序号】\n消耗洗词石重新随机指定词缀的数值")

    equip_keyword = raw_args[0]
    try:
        affix_index = int(raw_args[1]) - 1
    except ValueError:
        await reroll_cmd.finish("词缀序号必须是数字")
        return

    user_id = event.get_user_id()
    msg = ""

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await reroll_cmd.finish("你还没有创建角色")

        from .decompose_commands import _find_equipment_by_index, _find_equipments_by_name
        if equip_keyword.isdigit():
            equipment = await _find_equipment_by_index(session, player.id, int(equip_keyword))
        else:
            matches = await _find_equipments_by_name(session, player.id, equip_keyword)
            equipment = matches[0] if matches else None
        if not equipment:
            await reroll_cmd.finish(f"未找到装备：{equip_keyword}")

        if equipment.item_id in VIP_EQUIPMENT_IDS:
            await reroll_cmd.finish("VIP定制装备不可洗炼")

        affixes = get_affixes_from_equipment(getattr(equipment, 'extra_attrs', None))
        if not affixes:
            await reroll_cmd.finish("该装备没有词缀，无法洗炼")

        if affix_index < 0 or affix_index >= len(affixes):
            await reroll_cmd.finish(f"词缀序号无效，该装备有 {len(affixes)} 条词缀")

        # 检查洗词石
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.item_id == "affix_reroll_stone",
        )
        stone_items = (await session.execute(stmt)).scalars().all()
        stone_count = sum(s.quantity for s in stone_items)
        if stone_count < 1:
            await reroll_cmd.finish("洗词石不足，需要洗词石×1\n💡 分解装备可获得洗词石")

        equip_name = equipment.config.name if equipment.config else equipment.item_id
        rarity = equipment.config.rarity if equipment.config else "white"
        target_affix = affixes[affix_index]
        current_display = get_affix_display_name(target_affix)
        range_display = get_affix_value_range_display(target_affix, rarity)

        _pending_rerolls[user_id] = {
            "equipment_id": equipment.id,
            "affix_index": affix_index,
        }

        lines = [
            f"🔄 洗炼预览 — {equip_name}",
            f"  当前词缀：{current_display}",
            f"  {range_display}",
            f"  消耗：洗词石×1（当前持有：{stone_count}）",
            "",
            "⚠️ 洗炼后数值直接覆盖，不可保留旧值",
            "发送【确认洗炼】执行",
        ]
        lines.append("")
        lines.append(f"{cmd('确认洗炼')} | {cmd('装备栏')}")
        msg = "\n".join(lines)

    await reroll_cmd.finish(build_markdown(msg))


confirm_reroll_cmd = on_command("确认洗炼", priority=5, block=True)


@confirm_reroll_cmd.handle()
async def handle_confirm_reroll(event: MessageEvent):
    user_id = event.get_user_id()
    pending = _pending_rerolls.pop(user_id, None)
    if not pending:
        await confirm_reroll_cmd.finish("没有待确认的洗炼操作，请先使用【洗炼 装备编号 词缀序号】")

    equipment_id = pending["equipment_id"]
    affix_index = pending["affix_index"]
    msg = ""

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await confirm_reroll_cmd.finish("你还没有创建角色")

        equipment = await session.get(ItemInstance, equipment_id)
        if not equipment or equipment.player_id != player.id:
            await confirm_reroll_cmd.finish("装备不存在或已不属于你")

        # 消耗洗词石
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.item_id == "affix_reroll_stone",
        )
        stone_items = (await session.execute(stmt)).scalars().all()
        stone_count = sum(s.quantity for s in stone_items)
        if stone_count < 1:
            await confirm_reroll_cmd.finish("洗词石不足")

        for s in stone_items:
            if s.quantity >= 1:
                s.quantity -= 1
                if s.quantity <= 0:
                    await session.delete(s)
                break

        affixes = get_affixes_from_equipment(getattr(equipment, 'extra_attrs', None))
        if affix_index >= len(affixes):
            await confirm_reroll_cmd.finish("词缀序号已失效")

        rarity = equipment.config.rarity if equipment.config else "white"
        old_affix = affixes[affix_index]
        old_display = get_affix_display_name(old_affix)

        rng = random.Random()
        new_affix = reroll_single_affix(old_affix, rarity, rng)

        # 写入
        extra = dict(equipment.extra_attrs or {})
        affix_list = list(extra.get("_affixes", []))
        affix_list[affix_index] = new_affix
        extra["_affixes"] = affix_list
        equipment.extra_attrs = extra

        new_display = get_affix_display_name(new_affix)

        old_val = old_affix.get("value", 0)
        new_val = new_affix.get("value", 0)
        if new_val > old_val:
            trend = "⬆️ 上升"
        elif new_val < old_val:
            trend = "⬇️ 下降"
        else:
            trend = "➡️ 不变"

        equip_name = equipment.config.name if equipment.config else equipment.item_id
        lines = [
            f"# 🔄 洗炼完成 — {equip_name}",
            f"旧词缀：{old_display}",
            f"新词缀：**{new_display}**",
            f"变化：{trend}",
            f"***",
            f"{cmd('装备栏')} | {cmd(f'装备详情 {equip_name}', f'装备详情 {equip_name}')}",
        ]
        msg = "\n".join(lines)

    await confirm_reroll_cmd.finish(build_markdown(msg))
