"""
除夕叩门活动 — 命令注册 + 定时刷新

玩家命令: 除夕活动 / 鬼域瞬移 / 叩门排行 / 活动商店
管理命令: 开启活动 / 关闭活动
定时任务: 每5分钟检测是否需要刷新诡事点
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

teleport_cmd = on_command("鬼域瞬移",aliases={"诡域瞬移"}, block=True, priority=5)

ranking_cmd = on_command("叩门排行", block=True, priority=5)

shop_cmd = on_command("活动商店", aliases={"叩门商店"}, block=True, priority=5)


# ==================== 管理命令 ====================

start_event_cmd = on_command("开启活动", block=True, priority=4, permission=SUPERUSER)

stop_event_cmd = on_command("关闭活动", block=True, priority=4, permission=SUPERUSER)


# ==================== 活动状态查询 ====================

@event_status_cmd.handle()
async def handle_event_status(event: MessageEvent):
    """查看活动状态 + 个人进度 + 附近诡事点 + 完整帮助"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await event_status_cmd.finish(
                    "你还没有创建角色或绑定账号\n请先在群聊注册角色，然后使用绑定功能"
                )
            else:
                await event_status_cmd.finish("请先创建角色")

        result = KnockerEventService.get_event_status(player)

    # 在结果末尾添加完整的指令帮助
    help_section = (
        "\n"
        "━━━━━━━━━━━━━\n"
        "🎆 除夕叩门活动指令\n"
        "━━━━━━━━━━━━━\n"
        "【除夕活动】查看活动状态、进度、附近诡事点\n"
        "【鬼域瞬移 x y】快速移动到目标坐标（冷却3分钟）\n"
        "【叩门排行】查看击杀排行榜\n"
        "【活动商店】查看碎片商店\n"
        "【活动商店 兑换 物品名 [数量]】兑换商品\n"
        "【攻击 鬼怪名】击杀活动鬼怪获取碎片\n"
        "━━━━━━━━━━━━━\n"
        "💡 碎片可用于兑换稀有道具和食谱\n"
        "💡 击杀Boss级鬼怪可获得全服播报\n"
        "💡 瞬移距离上限200格（曼哈顿距离）"
    )

    await event_status_cmd.finish(message_add_head(result + help_section, event))


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


# ==================== 定时任务: 诡事刷新 ====================

@scheduler.scheduled_job("interval", minutes=5, id="knocker_event_refresh")
async def knocker_event_refresh():
    """每5分钟检查并刷新诡事点"""
    if not KnockerEventService.is_active():
        return

    if not KnockerEventService.should_refresh():
        return

    try:
        async with UnitOfWork(AsyncSessionLocal) as uow:
            broadcast = await KnockerEventService.refresh_events(uow.session)
            if broadcast:
                logger.info(f"[叩门活动] 刷新诡事点, 播报: {broadcast[:50]}...")
                # 尝试广播到所有群
                try:
                    bot = get_bot()
                    # QQ适配器发送群消息
                    # 此处依赖具体适配器实现; 如果无法广播则仅记录日志
                    logger.info(f"[叩门活动] 诡事刷新播报已生成(需手动/自动分发)")
                except Exception as e:
                    logger.debug(f"[叩门活动] 广播跳过: {e}")
    except Exception as e:
        logger.error(f"[叩门活动] 刷新任务失败: {e}")


# ==================== 启动日志 ====================

driver = get_driver()


@driver.on_startup
async def on_knocker_startup():
    """Bot启动时记录活动系统状态"""
    status = "开启" if KnockerEventService.is_active() else "关闭"
    logger.info(f"[叩门活动] 活动系统已加载, 当前状态: {status}")
    logger.info("  - 定时刷新: 每5分钟检查")
    logger.info("  - 玩家命令: 除夕活动/鬼域瞬移/叩门排行/活动商店")
    logger.info("  - 管理命令: 开启活动/关闭活动")
