"""
铭文合成命令

指令：
- 【合成铭文】 - 消耗5个铭文碎片，合成1个随机基础铭文
"""

import random

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..config import config
from ..platform_utils import get_unified_player
from .inscription_service import (
    generate_inscription_drop,
    get_inscription_display_from_item,
)

FRAGMENT_COST = 5
FRAGMENT_ITEM_ID = "inscription_fragment"

synthesize_cmd = on_command("合成铭文", priority=5, block=True)


@synthesize_cmd.handle()
async def handle_synthesize(event: MessageEvent, args: Message = CommandArg()):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await synthesize_cmd.finish("你还没有创建角色")

        # 检查碎片数量
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.item_id == FRAGMENT_ITEM_ID,
        )
        fragments = (await session.execute(stmt)).scalars().first()
        current = fragments.quantity if fragments else 0
        if current < FRAGMENT_COST:
            await synthesize_cmd.finish(
                f"铭文碎片不足！需要{FRAGMENT_COST}个，当前{current}个\n"
                f"碎片来源：分解T2词缀装备、击杀精英怪"
            )

        # 扣除碎片
        fragments.quantity -= FRAGMENT_COST
        if fragments.quantity <= 0:
            await session.delete(fragments)

        # 随机选择基础铭文（排除高级铭文）
        rng = random.Random()
        basic_ids = [
            iid for iid in config.items_config["by_type"].get("INSCRIPTION", [])
            if not getattr(config.items_config["by_id"].get(iid), 'inscription_type', None)
            and not iid.startswith("adv_")
        ]
        if not basic_ids:
            await synthesize_cmd.finish("系统错误：无可用铭文模板")

        chosen_id = rng.choice(basic_ids)
        drop_attrs = generate_inscription_drop(chosen_id, rng)

        # 创建铭文实例
        inst = ItemInstance(
            player_id=player.id,
            item_id=chosen_id,
            quantity=1,
            extra_attrs=drop_attrs,
        )
        session.add(inst)

        # 显示结果
        display = get_inscription_display_from_item(inst)
        msg = f"合成成功！消耗铭文碎片 x{FRAGMENT_COST}\n  获得：{display}"

    await synthesize_cmd.finish(Message(msg))
