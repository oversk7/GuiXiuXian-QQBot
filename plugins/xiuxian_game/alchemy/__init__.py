from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head

# Feature Flag: 启用新版DI架构AlchemyService
USE_NEW_ALCHEMY_SERVICE = True

if USE_NEW_ALCHEMY_SERVICE:
    from .service_new import AlchemyService as AlchemyServiceNew
    from ..infrastructure.repositories.item_repository import ItemRepository
    from ..infrastructure.repositories.alchemy_record_repository import AlchemyRecordRepository
else:
    from .service import AlchemyService

# 保持向后兼容：旧版Service（仅用于常量引用）
from .service import AlchemyService as AlchemyServiceLegacy
from ..platform_utils import get_unified_player

# ---------------- 指令 ----------------

recipe_cmd = on_command("丹方", aliases={"炼丹配方"}, block=True, priority=5)
start_cmd = on_command("炼丹", block=True, priority=5)
status_cmd = on_command("炼丹状态", block=True, priority=5)
claim_cmd = on_command("收获丹药", aliases={"领取丹药"}, block=True, priority=5)


@recipe_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()

    if USE_NEW_ALCHEMY_SERVICE:
        # 新版：使用DI架构Service（无需Repository的纯配置操作）
        # 创建临时实例用于配置查询（不涉及数据库操作）
        async with safe_session() as session:
            service = AlchemyServiceNew(
                item_repo=ItemRepository(session),
                alchemy_record_repo=AlchemyRecordRepository(session)
            )

            if not arg:
                page = 1
                content = service.format_recipes(page)
                content += ("\n⬇️ 【丹方 [页数]】")
            elif arg.isdigit():
                page = int(arg)
                content = service.format_recipes(page)
                content += ("\n⬇️ 【丹方 [页数]】")
            else:
                matches = service.search_recipes(arg)
                content = service.format_recipe_search(arg, matches)
    else:
        # 旧版：使用@classmethod静态方法
        if not arg:
            page = 1
            content = AlchemyServiceLegacy.format_recipes(page)
            content += ("\n⬇️ 【丹方 [页数]】")
        elif arg.isdigit():
            page = int(arg)
            content = AlchemyServiceLegacy.format_recipes(page)
            content += ("\n⬇️ 【丹方 [页数]】")
        else:
            matches = AlchemyServiceLegacy.search_recipes(arg)
            content = AlchemyServiceLegacy.format_recipe_search(arg, matches)

    await recipe_cmd.finish(message_add_head(content, event))


@start_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """炼丹 配方序号|名称 [数量]"""
    params = args.extract_plain_text().strip().split()
    if len(params) < 1 or len(params) > 2:
        await start_cmd.finish("⛔ 格式：炼丹 配方序号|名称 [数量]")

    # 解析参数
    target = params[0]

    qty = 1
    if len(params) == 2:
        try:
            qty = int(params[1])
            if qty < 1:
                raise ValueError
        except ValueError:
            await start_cmd.finish("⛔ 数量必须为正整数")

    if USE_NEW_ALCHEMY_SERVICE:
        # 新版：使用DI架构Service
        async with safe_session() as session:
            # 创建Repository和Service实例
            item_repo = ItemRepository(session)
            alchemy_record_repo = AlchemyRecordRepository(session)
            service = AlchemyServiceNew(
                item_repo=item_repo,
                alchemy_record_repo=alchemy_record_repo
            )

            # 查找丹方
            recipe_result = service.find_recipe(target)
            if not recipe_result:
                await start_cmd.finish("⛔ 未找到该丹方")

            recipe_key, recipe = recipe_result

            player = await get_unified_player(session, event)
            if not player:
                await start_cmd.finish("⛔ 请先创建角色")

            # 自动选择最高阶的炼丹炉
            furnaces = await service.get_player_furnaces(player.id)
            if not furnaces:
                await start_cmd.finish("⛔ 你没有炼丹炉，请先获得炼丹炉")

            # 选择第一个（已按升阶等级排序）
            best_furnace = furnaces[0]

            # 开始炼丹
            success, msg, record = await service.start_alchemy(
                player.id, best_furnace.id, recipe_key, recipe, qty
            )

            if success:
                await session.commit()
                # 添加炼丹炉信息到消息中
                furnace_info = f"🏺 使用炼丹炉+{best_furnace.upgrade_level}阶 (ID:{best_furnace.id})\n"
                await start_cmd.finish(message_add_head(furnace_info + msg, event))
            else:
                await session.rollback()
                await start_cmd.finish(msg)
    else:
        # 旧版：使用@classmethod静态方法
        # 查找丹方
        recipe_result = AlchemyServiceLegacy.find_recipe(target)
        if not recipe_result:
            await start_cmd.finish("⛔ 未找到该丹方")

        recipe_key, recipe = recipe_result

        async with safe_session() as session:
            player = await get_unified_player(session, event)
            if not player:
                await start_cmd.finish("⛔ 请先创建角色")

            # 自动选择最高阶的炼丹炉
            furnaces = await AlchemyServiceLegacy.get_player_furnaces(session, player.id)
            if not furnaces:
                await start_cmd.finish("⛔ 你没有炼丹炉，请先获得炼丹炉")

            # 选择第一个（已按升阶等级排序）
            best_furnace = furnaces[0]

            # 开始炼丹
            success, msg, record = await AlchemyServiceLegacy.start_alchemy(
                session, player.id, best_furnace.id, recipe_key, recipe, qty
            )

            if success:
                await session.commit()
                # 添加炼丹炉信息到消息中
                furnace_info = f"🏺 使用炼丹炉+{best_furnace.upgrade_level}阶 (ID:{best_furnace.id})\n"
                await start_cmd.finish(message_add_head(furnace_info + msg, event))
            else:
                await session.rollback()
                await start_cmd.finish(msg)


@status_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        if USE_NEW_ALCHEMY_SERVICE:
            # 新版：使用DI架构Service
            alchemy_record_repo = AlchemyRecordRepository(session)
            service = AlchemyServiceNew(
                item_repo=ItemRepository(session),
                alchemy_record_repo=alchemy_record_repo
            )
            records = await service.get_player_records(event.get_user_id())
        else:
            # 旧版：使用@classmethod静态方法
            records = await AlchemyServiceLegacy.get_player_records(session, event.get_user_id())

        if not records:
            await status_cmd.finish("📭 当前没有炼丹记录")

        lines = ["📋 炼丹状态", "━"*10]

        for record in records:
            from ..config import config
            prod_cfg = config.items_config["by_id"][record.produce_item_id]

            if record.claimed:
                result_msg = "✅ 已领取"
            elif record.is_finished():
                success_count, total_produce = record.calculate_result()
                result_msg = f"🎉 已完成！成功 {success_count}/{record.qty} 炉，共得 {total_produce} 颗 (输入'收获丹药'领取)"
            else:
                remain = record.get_remaining_seconds()
                result_msg = f"⏳ 剩余 {remain//60}分{remain%60}秒"

            lines.append(f"• {prod_cfg.name} ✖️{record.qty} 炉  {result_msg}")

        await status_cmd.finish(message_add_head("\n".join(lines), event))


@claim_cmd.handle()
async def _(event: MessageEvent):
    """领取炼丹奖励"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await claim_cmd.finish("⛔ 请先创建角色")

        if USE_NEW_ALCHEMY_SERVICE:
            # 新版：使用DI架构Service
            service = AlchemyServiceNew(
                item_repo=ItemRepository(session),
                alchemy_record_repo=AlchemyRecordRepository(session)
            )
            records = await service.get_player_records(player.id)

            # 找到所有已完成但未领取的记录
            claimable_records = [r for r in records if r.is_finished() and not r.claimed]

            if not claimable_records:
                await claim_cmd.finish("📭 没有可领取的炼丹奖励")

            # 批量领取所有可领取的奖励
            messages = []
            for record in claimable_records:
                success, msg = await service.claim_reward(record)
                if success:
                    messages.append(msg)

            if messages:
                await session.commit()
                await claim_cmd.finish(message_add_head("\n".join(messages), event))
            else:
                await claim_cmd.finish("⛔ 领取失败")
        else:
            # 旧版：使用@classmethod静态方法
            records = await AlchemyServiceLegacy.get_player_records(session, player.id)

            # 找到所有已完成但未领取的记录
            claimable_records = [r for r in records if r.is_finished() and not r.claimed]

            if not claimable_records:
                await claim_cmd.finish("📭 没有可领取的炼丹奖励")

            # 批量领取所有可领取的奖励
            messages = []
            for record in claimable_records:
                success, msg = await AlchemyServiceLegacy.claim_reward(session, record)
                if success:
                    messages.append(msg)

            if messages:
                await session.commit()
                await claim_cmd.finish(message_add_head("\n".join(messages), event))
            else:
                await claim_cmd.finish("⛔ 领取失败")