"""
除夕叩门活动 — 命令注册 + 手动刷新

玩家命令: 除夕活动 / 刷新诡事 / 鬼域瞬移 / 叩门排行 / 活动商店
管理命令: 开启活动 / 关闭活动
"""

from nonebot import on_command, get_bot, get_driver, logger
from nonebot.permission import SUPERUSER
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from nonebot_plugin_apscheduler import scheduler

from ..models.db import safe_session, AsyncSessionLocal
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..platform_utils import get_unified_player, is_guild_message
from ..utils import message_add_head

from .knocker_event import KnockerEventService


# ==================== 玩家命令 ====================

event_status_cmd = on_command(
    "除夕活动", aliases={"叩门活动", "新年活动"}, block=True, priority=5
)

refresh_cmd = on_command("刷新诡事", aliases={"刷新鬼怪", "刷新活动"}, block=True, priority=5)

teleport_cmd = on_command("鬼域瞬移",aliases={"诡域瞬移"}, block=True, priority=5)

ranking_cmd = on_command("叩门排行", block=True, priority=5)

shop_cmd = on_command("活动商店", aliases={"叩门商店"}, block=True, priority=5)

title_switch_cmd = on_command("切换称号", block=True, priority=5)

title_remove_cmd = on_command("卸下称号", block=True, priority=5)


# ==================== 管理命令 ====================

start_event_cmd = on_command("开启活动", block=True, priority=4, permission=SUPERUSER)

stop_event_cmd = on_command("关闭活动", block=True, priority=4, permission=SUPERUSER)


# ==================== 活动状态查询 ====================

@event_status_cmd.handle()
async def handle_event_status(event: MessageEvent):
    """查看活动状态 + 个人进度 + 个人鬼怪列表（不自动刷新）"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await event_status_cmd.finish(
                    "你还没有创建角色或绑定账号\n请先在群聊注册角色，然后使用绑定功能"
                )
            else:
                await event_status_cmd.finish("请先创建角色")

        # 仅查看，不触发刷新
        result = await KnockerEventService.get_event_status(session, player)

    await event_status_cmd.finish(message_add_head(result, event))


# ==================== 手动刷新诡事 ====================

@refresh_cmd.handle()
async def handle_refresh(event: MessageEvent):
    """手动刷新诡事点，CD 10分钟"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await refresh_cmd.finish(
                    "你还没有创建角色或绑定账号\n请先在群聊注册角色，然后使用绑定功能"
                )
            else:
                await refresh_cmd.finish("请先创建角色")

        if not KnockerEventService.is_active():
            await refresh_cmd.finish("除夕叩门活动当前未开启")

        # 检查CD
        cd_remaining = KnockerEventService.get_refresh_cooldown(player)
        if cd_remaining > 0:
            minutes = int(cd_remaining // 60)
            seconds = int(cd_remaining % 60)
            await refresh_cmd.finish(f"刷新冷却中，还需 {minutes}分{seconds}秒")

        # 执行刷新
        new_count = await KnockerEventService.refresh_player_events(session, player)

    if new_count > 0:
        await refresh_cmd.finish(message_add_head(f"刷新成功！生成了 {new_count} 个新诡事\n使用【除夕活动】查看详情", event))
    else:
        await refresh_cmd.finish(message_add_head("当前鬼怪数量已达上限，无法刷新更多\n击杀现有鬼怪后再来刷新吧", event))


# ==================== 鬼域瞬移 ====================

@teleport_cmd.handle()
async def handle_teleport(event: MessageEvent, args: Message = CommandArg()):
    """鬼域瞬移 x y"""
    args_text = args.extract_plain_text().strip()

    if not args_text:
        await teleport_cmd.finish(
            "鬼域瞬移\n"
            "━━━━━━━━━━━━━\n"
            "用法: 【鬼域瞬移 x y】\n"
            "曼哈顿距离上限: 200格\n"
            "冷却时间: 3分钟\n"
            "━━━━━━━━━━━━━\n"
            "示例: 鬼域瞬移 120 -50"
        )

    # 解析坐标
    parts = args_text.split()
    if len(parts) < 2:
        await teleport_cmd.finish("格式错误，请输入: 鬼域瞬移 x y")

    try:
        target_x = int(parts[0])
        target_y = int(parts[1])
    except ValueError:
        await teleport_cmd.finish("坐标必须是整数，请输入: 鬼域瞬移 x y")

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await teleport_cmd.finish(
                    "你还没有创建角色或绑定账号\n请先在群聊注册角色，然后使用绑定功能"
                )
            else:
                await teleport_cmd.finish("请先创建角色")

        success, msg = KnockerEventService.handle_teleport(session, player, target_x, target_y)

    await teleport_cmd.finish(message_add_head(msg, event))


# ==================== 叩门排行 ====================

@ranking_cmd.handle()
async def handle_ranking(event: MessageEvent):
    """查看叩门排行榜"""
    async with safe_session() as session:
        result = await KnockerEventService.get_ranking(session)

    await ranking_cmd.finish(message_add_head(result, event))


# ==================== 活动商店 ====================

@shop_cmd.handle()
async def handle_shop(event: MessageEvent, args: Message = CommandArg()):
    """活动商店 / 活动商店 兑换 物品名 [数量]"""
    args_text = args.extract_plain_text().strip()

    # 判断是查看还是兑换
    if args_text.startswith("兑换"):
        # 解析兑换参数
        buy_args = args_text[2:].strip()
        if not buy_args:
            await shop_cmd.finish("请输入: 活动商店 兑换 物品名 [数量]")

        parts = buy_args.rsplit(" ", 1)
        if len(parts) == 2 and parts[1].isdigit():
            item_name = parts[0].strip()
            quantity = int(parts[1])
        else:
            item_name = buy_args.strip()
            quantity = 1

        if quantity <= 0:
            await shop_cmd.finish("数量必须大于0")

        async with safe_session() as session:
            player = await get_unified_player(session, event)
            if not player:
                if is_guild_message(event):
                    await shop_cmd.finish(
                        "你还没有创建角色或绑定账号\n请先在群聊注册角色，然后使用绑定功能"
                    )
                else:
                    await shop_cmd.finish("请先创建角色")

            success, msg = await KnockerEventService.handle_shop_buy(
                session, player, item_name, quantity
            )

        await shop_cmd.finish(message_add_head(msg, event))
    else:
        # 查看商店
        async with safe_session() as session:
            player = await get_unified_player(session, event)
            if not player:
                if is_guild_message(event):
                    await shop_cmd.finish(
                        "你还没有创建角色或绑定账号\n请先在群聊注册角色，然后使用绑定功能"
                    )
                else:
                    await shop_cmd.finish("请先创建角色")

            result = await KnockerEventService.handle_shop_view(player)

        await shop_cmd.finish(message_add_head(result, event))


# ==================== 切换称号 ====================

@title_switch_cmd.handle()
async def handle_title_switch(event: MessageEvent, args: Message = CommandArg()):
    """切换称号 [称号名]"""
    args_text = args.extract_plain_text().strip()

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await title_switch_cmd.finish(
                    "你还没有创建角色或绑定账号\n请先在群聊注册角色，然后使用绑定功能"
                )
            else:
                await title_switch_cmd.finish("请先创建角色")

        if not args_text:
            # 无参数：显示称号列表
            result = KnockerEventService.handle_title_list(player)
            await title_switch_cmd.finish(message_add_head(result, event))

        # 有参数：切换到指定称号
        success, msg = KnockerEventService.handle_title_switch(player, args_text)

    await title_switch_cmd.finish(message_add_head(msg, event))


@title_remove_cmd.handle()
async def handle_title_remove(event: MessageEvent):
    """卸下称号"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await title_remove_cmd.finish(
                    "你还没有创建角色或绑定账号\n请先在群聊注册角色，然后使用绑定功能"
                )
            else:
                await title_remove_cmd.finish("请先创建角色")

        success, msg = KnockerEventService.handle_title_switch(player, "")

    await title_remove_cmd.finish(message_add_head(msg, event))


# ==================== 管理员: 开启活动 ====================

@start_event_cmd.handle()
async def handle_start_event(event: MessageEvent, args: Message = CommandArg()):
    """开启活动 [持续小时数]"""
    args_text = args.extract_plain_text().strip()

    duration = 48  # 默认48小时
    if args_text:
        try:
            duration = int(args_text)
            if duration <= 0:
                await start_event_cmd.finish("持续时间必须大于0")
        except ValueError:
            await start_event_cmd.finish("格式: 开启活动 [小时数]，如: 开启活动 72")

    # 使用UnitOfWork提供session,立即刷新诡事点
    async with UnitOfWork(AsyncSessionLocal) as uow:
        broadcast = await KnockerEventService.start_event(duration, uow.session)
        # UnitOfWork会自动commit

    await start_event_cmd.finish(broadcast)


# ==================== 管理员: 关闭活动 ====================

@stop_event_cmd.handle()
async def handle_stop_event(event: MessageEvent):
    """关闭活动"""
    if not KnockerEventService.is_active():
        await stop_event_cmd.finish("活动当前未开启")

    broadcast = KnockerEventService.stop_event()
    await stop_event_cmd.finish(broadcast)


# ==================== 定时任务: 已废弃 ====================
# 手动刷新模式，玩家使用【刷新诡事】命令主动刷新，无需定时任务


# ==================== 启动日志 ====================

driver = get_driver()


@driver.on_startup
async def on_knocker_startup():
    """Bot启动时记录活动系统状态"""
    status = "开启" if KnockerEventService.is_active() else "关闭"
    logger.info(f"[叩门活动] 活动系统已加载, 当前状态: {status}")
    logger.info("  - 手动刷新: 玩家使用【刷新诡事】命令触发, CD 10分钟")
    logger.info("  - 玩家命令: 除夕活动/刷新诡事/鬼域瞬移/叩门排行/活动商店")
    logger.info("  - 管理命令: 开启活动/关闭活动")
