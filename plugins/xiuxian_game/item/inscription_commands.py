"""
铭文合成命令

指令：
- 【合成铭文】 - 消耗5个铭文碎片，60%概率合成1个随机基础铭文
- 【合成铭文 稳定水晶】 - 消耗5个碎片+1个稳定水晶，100%合成
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
from ..platform_utils import require_player
from ..utils_markdown import cmd, build_markdown
from .inscription_service import (
    generate_synthesis_inscription,
    get_inscription_display_from_item,
)

FRAGMENT_COST = 5
FRAGMENT_ITEM_ID = "inscription_fragment"
STABILIZER_ITEM_ID = "stabilizer_crystal"
SUCCESS_RATE = 0.60

synthesize_cmd = on_command("合成铭文", priority=9, block=True)


@synthesize_cmd.handle()
async def handle_synthesize(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    use_protection = arg_text in ("稳定水晶", "保护")

    async with safe_session() as session:
        player = await require_player(session, event, synthesize_cmd)

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

        # 检查稳定水晶
        if use_protection:
            crystal_stmt = select(ItemInstance).where(
                ItemInstance.player_id == player.id,
                ItemInstance.item_id == STABILIZER_ITEM_ID,
            )
            crystal = (await session.execute(crystal_stmt)).scalars().first()
            if not crystal or crystal.quantity < 1:
                await synthesize_cmd.finish("稳定水晶不足！需要1个")

            # 扣除稳定水晶
            crystal.quantity -= 1
            if crystal.quantity <= 0:
                await session.delete(crystal)

        # 扣除碎片
        fragments.quantity -= FRAGMENT_COST
        if fragments.quantity <= 0:
            await session.delete(fragments)

        # 判定成功率
        rng = random.Random()
        if not use_protection and rng.random() >= SUCCESS_RATE:
            # 合成失败，碎片已消耗
            rate_display = int(SUCCESS_RATE * 100)
            await synthesize_cmd.finish(
                f"合成失败！铭文碎片 x{FRAGMENT_COST} 已消耗\n"
                f"当前成功率：{rate_display}%\n"
                f"提示：使用【合成铭文 稳定水晶】可保证100%成功"
            )

        # 随机选择基础铭文（排除高级铭文）
        basic_ids = [
            iid for iid in config.items_config["by_type"].get("INSCRIPTION", [])
            if not getattr(config.items_config["by_id"].get(iid), 'inscription_type', None)
            and not iid.startswith("adv_")
        ]
        if not basic_ids:
            await synthesize_cmd.finish("系统错误：无可用铭文模板")

        chosen_id = rng.choice(basic_ids)
        drop_attrs = generate_synthesis_inscription(chosen_id, rng, player.luck)

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
        protection_hint = "（稳定水晶保护）" if use_protection else ""
        msg = (
            f"# ✅ 合成成功！{protection_hint}\n"
            f"消耗铭文碎片 x{FRAGMENT_COST}\n"
            f"获得：**{display}**\n"
            f"***\n"
            f"{cmd('铭文列表')} | {cmd('装备栏')}"
        )

    await synthesize_cmd.finish(build_markdown(msg))
