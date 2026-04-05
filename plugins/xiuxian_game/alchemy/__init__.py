from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head

# 使用新版DI架构AlchemyService
from .service_new import AlchemyService as AlchemyServiceNew
from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.repositories.alchemy_record_repository import AlchemyRecordRepository
from ..platform_utils import get_unified_player

# ---------------- 指令 ----------------

recipe_cmd = on_command("丹方", aliases={"炼丹配方"}, block=True, priority=13)
start_cmd = on_command("炼丹", block=True, priority=13)
status_cmd = on_command("炼丹状态", block=True, priority=13)
claim_cmd = on_command("收获丹药", aliases={"领取丹药"}, block=True, priority=13)


@recipe_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()

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
            player.id, best_furnace.id, recipe_key, recipe, qty, player_luck=player.luck
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
        # 新版：使用DI架构Service
        alchemy_record_repo = AlchemyRecordRepository(session)
        service = AlchemyServiceNew(
            item_repo=ItemRepository(session),
            alchemy_record_repo=alchemy_record_repo
        )
        records = await service.get_player_records(event.get_user_id())
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

        # 新版：使用DI架构Service
        alchemy_record_repo = AlchemyRecordRepository(session)
        service = AlchemyServiceNew(
            item_repo=ItemRepository(session),
            alchemy_record_repo=alchemy_record_repo
        )

        # 【关键修复】使用带锁的方法获取可领取记录
        # 这会锁定记录，防止并发领取
        claimable_records = await alchemy_record_repo.get_claimable_by_player_id(player.id)

        if not claimable_records:
            await claim_cmd.finish("📭 没有可领取的炼丹奖励")

        # 批量领取所有可领取的奖励
        messages = []
        for record in claimable_records:
            # 重新使用带锁的查询，确保原子性
            locked_record = await alchemy_record_repo.get_by_id_with_lock(record.id)
            if not locked_record or locked_record.claimed:
                # 如果记录已被其他并发请求领取，跳过
                continue

            success, msg = await service.claim_reward(locked_record)
            if success:
                messages.append(msg)

        if messages:
            await session.commit()
            await claim_cmd.finish(message_add_head("\n".join(messages), event))
        else:
            await claim_cmd.finish("⛔ 领取失败或已被领取")
