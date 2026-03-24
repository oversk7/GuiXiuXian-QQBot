"""
里界系统命令处理器 -- 场景节点版

⚠️ 测试阶段：仅管理员可用，测试完成后移除 permission=SUPERUSER
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from ..platform_utils import get_unified_player
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.db import AsyncSessionLocal
from .service import InnerRealmService
from .config import InnerRealmConfig
import json


# ==================== 规则定义 ====================
async def in_inner_realm_rule(event: MessageEvent) -> bool:
    """检查玩家是否在里界中"""
    def session_factory():
        return AsyncSessionLocal()

    try:
        async with UnitOfWork(session_factory) as uow:
            player = await get_unified_player(uow.session, event)
            return player is not None and player.inner_realm is not None
    except (ValueError, AttributeError, KeyError):
        return False


# ==================== 命令注册 ====================

realms_list_cmd = on_command("里界", aliases={"里界列表"}, block=True, priority=5, permission=SUPERUSER)

# 里界传送命令优先级为4（高于诡域的5），使用智能识别
# block=False 允许在不匹配里界时继续传递给诡域系统
enter_realm_cmd = on_command("传送", aliases={"进入里界"}, block=False, priority=4, permission=SUPERUSER)

realm_info_cmd = on_command("里界信息", block=True, priority=5, permission=SUPERUSER)

# 里界的返回命令优先级更高（4），在诡域返回命令（5）之前处理
# 使用 Rule 确保只有在里界时才匹配此命令
exit_realm_cmd = on_command(
    "返回",
    aliases={"离开里界"},
    rule=in_inner_realm_rule,
    block=True,
    priority=4,
    permission=SUPERUSER,
)

# 场景移动
goto_cmd = on_command("前往", rule=in_inner_realm_rule, block=True, priority=4, permission=SUPERUSER)

# 交互命令
search_cmd = on_command("搜刮", block=True, priority=4, permission=SUPERUSER)
intimidate_cmd = on_command("威吓", block=True, priority=4, permission=SUPERUSER)
assassination_cmd = on_command("处决", block=True, priority=4, permission=SUPERUSER)
talk_cmd = on_command("交谈", block=True, priority=4, permission=SUPERUSER)
observe_cmd = on_command("观察", aliases={"环顾", "查看环境"},
                         rule=in_inner_realm_rule, block=True, priority=4, permission=SUPERUSER)

# 道具
use_item_cmd = on_command("使用", rule=in_inner_realm_rule, block=True, priority=4, permission=SUPERUSER)
inventory_cmd = on_command("道具", rule=in_inner_realm_rule, block=True, priority=4, permission=SUPERUSER)

# 线索 & 事件
view_clues_cmd = on_command("查看线索", aliases={"线索列表", "已收集线索"}, block=True, priority=4, permission=SUPERUSER)
choose_cmd = on_command("选择", rule=in_inner_realm_rule, block=True, priority=4, permission=SUPERUSER)


# ==================== 【里界】查看列表 ====================

@realms_list_cmd.handle()
async def handle_realms_list(event: MessageEvent):
    """查看可进入的里界列表"""
    def session_factory():
        return AsyncSessionLocal()

    result_msg = None
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            result_msg = "⛔ 请先创建角色"
        else:
            service = InnerRealmService(uow)
            realms = await service.get_available_realms(player)

            if not realms:
                result_msg = "⛔ 暂无可进入的里界"
            else:
                lines = [
                    "🌌 里界列表",
                    "━━━━━━━━━━━━━"
                ]
                for realm in realms:
                    status = "✅" if realm["can_enter"] else "🔒"
                    level_req = f"Lv.{realm['level_requirement']}"
                    lines.append(
                        f"{status} {realm['display_name']} ({level_req})\n"
                        f"   {realm['description']}"
                    )
                lines.extend([
                    "━━━━━━━━━━━━━",
                    "💡 使用【传送 里界名】进入里界"
                ])
                result_msg = "\n".join(lines)

    await realms_list_cmd.finish(result_msg)


# ==================== 【传送】进入里界 ====================

@enter_realm_cmd.handle()
async def handle_enter_realm(event: MessageEvent, args: Message = CommandArg()):
    """传送到指定里界（智能识别，不匹配则传递给诡域系统）"""
    arg_text = args.extract_plain_text().strip()

    # 如果没有参数，交给诡域系统处理
    if not arg_text:
        return

    # 检查是否是诡域格式（包含"层诡域"），如果是则交给诡域系统
    if "层诡域" in arg_text or arg_text == "诡域":
        return

    realm_display_name = arg_text

    def session_factory():
        return AsyncSessionLocal()

    result_msg = None
    should_finish = False

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            # 未找到玩家，也可能是诡域命令，不finish，继续传递
            return

        # 根据显示名称找到里界配置key
        all_realms = InnerRealmConfig.get_all_realms()
        realm_key = None

        for key, config in all_realms.items():
            if config.get("display_name") == realm_display_name:
                realm_key = key
                break

        # 如果不是里界名称，交给诡域系统处理
        if not realm_key:
            return

        # 确认是里界命令，开始处理
        should_finish = True
        service = InnerRealmService(uow)
        success, message, session = await service.enter_realm(player, realm_key)

        if success:
            result_msg = (
                f"{message}\n"
                f"━━━━━━━━━━━━━\n"
                f"💡 使用【里界信息】查看探索进度\n"
                f"💡 使用【前往 场景名】移动\n"
                f"💡 使用【返回】离开并结算"
            )
        else:
            result_msg = message

    # 只有确认是里界命令时才finish（阻断后续处理）
    if should_finish:
        await enter_realm_cmd.finish(result_msg)


# ==================== 【里界信息】 ====================

@realm_info_cmd.handle()
async def handle_realm_info(event: MessageEvent):
    """查看当前里界信息"""
    def session_factory():
        return AsyncSessionLocal()

    result_msg = None
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            result_msg = "⛔ 请先创建角色"
        elif not player.inner_realm:
            result_msg = "⛔ 你不在任何里界中\n💡 使用【里界】查看可进入的里界列表"
        else:
            service = InnerRealmService(uow)
            realm_config = InnerRealmConfig.get_realm_config(player.inner_realm)
            if not realm_config:
                result_msg = "⛔ 里界配置错误"
            else:
                active_session = await service.get_active_session(player.id, player.inner_realm)
                if not active_session:
                    result_msg = "⛔ 会话数据错误"
                else:
                    # 解析状态
                    state = json.loads(active_session.state) if active_session.state else {}
                    clue_ids = json.loads(active_session.clue_collected) if active_session.clue_collected else []
                    visited = json.loads(active_session.visited_scenes) if active_session.visited_scenes else []
                    phase = state.get("phase", "dusk")
                    phase_label = "黄昏" if phase == "dusk" else "入夜"

                    # 理智状态指示器
                    sanity_icon = "🟢"
                    if active_session.sanity <= 10:
                        sanity_icon = "💀"
                    elif active_session.sanity <= 30:
                        sanity_icon = "🔴"
                    elif active_session.sanity <= 50:
                        sanity_icon = "🟡"

                    # 当前场景名
                    current_scene_name = active_session.current_scene or "未知"
                    engine = service._get_scene_engine(active_session.realm_name)
                    scene = engine.get_current_scene(active_session)
                    if scene:
                        current_scene_name = scene.display_name

                    lines = [
                        f"🌌 {realm_config['display_name']}",
                        "━━━━━━━━━━━━━",
                        f"📍 当前场景: {current_scene_name}",
                        f"{sanity_icon} 理智值: {active_session.sanity}/100",
                        f"⚔️ 击杀数: {active_session.killed_count}",
                        f"📖 线索数: {len(clue_ids)}",
                        f"🌗 阶段: {phase_label}",
                        f"🗺️ 已访问: {len(visited)} 个场景",
                    ]

                    lines.extend([
                        "━━━━━━━━━━━━━",
                        "💡 使用【前往 场景名】移动",
                        "💡 使用【返回】结算并离开里界"
                    ])

                    result_msg = "\n".join(lines)

    await realm_info_cmd.finish(result_msg)


# ==================== 【返回】离开并结算 ====================

@exit_realm_cmd.handle()
async def handle_exit_realm(event: MessageEvent):
    """离开里界并结算"""
    def session_factory():
        return AsyncSessionLocal()

    result_msg = None
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            result_msg = "⛔ 请先创建角色"
        elif not player.inner_realm:
            result_msg = "⛔ 你不在任何里界中"
        else:
            service = InnerRealmService(uow)
            realm_config = InnerRealmConfig.get_realm_config(player.inner_realm)
            if not realm_config:
                result_msg = "⛔ 里界配置错误"
            else:
                active_session = await service.get_active_session(player.id, player.inner_realm)
                if not active_session:
                    result_msg = "⛔ 会话数据错误"
                else:
                    # 结算结局（会清空 player.inner_realm）
                    ending_info = await service.settle_ending(player, active_session, realm_config)

                    lines = [
                        f"🌌 离开 {realm_config['display_name']}",
                        "━━━━━━━━━━━━━",
                        f"🎬 结局: {ending_info['display_name']}",
                        "",
                        ending_info["description"],
                        "━━━━━━━━━━━━━",
                        "📊 本次探索统计:",
                        f"⚔️ 击杀数: {active_session.killed_count}",
                        f"📖 线索数: {len(json.loads(active_session.clue_collected) if active_session.clue_collected else '[]')}",
                        f"🧠 最终理智: {active_session.sanity}/100",
                    ]

                    # 显示实际发放的奖励
                    reward_desc = ending_info.get("reward_desc", "")
                    if reward_desc and reward_desc != "无" and reward_desc != "什么也没得到...":
                        lines.append("━━━━━━━━━━━━━")
                        lines.append("🎁 获得奖励:")
                        lines.append(reward_desc)

                    result_msg = "\n".join(lines)

    await exit_realm_cmd.finish(result_msg)


# ==================== 【前往】场景移动 ====================

@goto_cmd.handle()
async def handle_goto(event: MessageEvent, args: Message = CommandArg()):
    """前往指定场景，无参数时显示可前往列表"""
    arg_text = args.extract_plain_text().strip()

    def session_factory():
        return AsyncSessionLocal()

    result_msg = None
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            result_msg = "⛔ 请先创建角色"
        elif not player.inner_realm:
            result_msg = "⛔ 你不在任何里界中"
        else:
            service = InnerRealmService(uow)
            active_session = await service.get_active_session(player.id, player.inner_realm)
            if not active_session:
                result_msg = "⛔ 会话数据错误"
            else:
                # 检查理智归零
                if await service.check_sanity_zero(player, active_session):
                    result_msg = service._sanity_collapse_text()
                else:
                    if not arg_text:
                        # 无参数 -- 显示可前往地点列表
                        engine = service._get_scene_engine(active_session.realm_name)
                        dests = engine.get_available_destinations(active_session)
                        if not dests:
                            result_msg = "⛔ 当前没有可前往的地点"
                        else:
                            lines = [
                                "🚪 可前往地点",
                                "━━━━━━━━━━━━━",
                            ]
                            for dest in dests:
                                lines.append(f"  📍 {dest.display_name}")
                            lines.extend([
                                "━━━━━━━━━━━━━",
                                "💡 使用【前往 场景名】移动",
                            ])
                            result_msg = "\n".join(lines)
                    else:
                        # 有参数 -- 移动到目标场景
                        success, message = await service.move_to_scene(
                            player, active_session, arg_text
                        )
                        result_msg = message

    await goto_cmd.finish(result_msg)


# ==================== 【搜刮】 ====================

@search_cmd.handle()
async def handle_search(event: MessageEvent):
    """搜刮当前场景"""
    def session_factory():
        return AsyncSessionLocal()

    result_msg = None
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            result_msg = "⛔ 请先创建角色"
        elif not player.inner_realm:
            result_msg = "⛔ 你不在任何里界中"
        else:
            service = InnerRealmService(uow)
            active_session = await service.get_active_session(player.id, player.inner_realm)
            if not active_session:
                result_msg = "⛔ 会话数据错误"
            else:
                if await service.check_sanity_zero(player, active_session):
                    result_msg = service._sanity_collapse_text()
                else:
                    success, message = await service.perform_search(player, active_session)
                    result_msg = message

    await search_cmd.finish(result_msg)


# ==================== 【威吓】 ====================

@intimidate_cmd.handle()
async def handle_intimidate(event: MessageEvent, args: Message = CommandArg()):
    """威吓当前场景的NPC"""
    arg_text = args.extract_plain_text().strip()

    def session_factory():
        return AsyncSessionLocal()

    result_msg = None
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            result_msg = "⛔ 请先创建角色"
        elif not player.inner_realm:
            result_msg = "⛔ 你不在任何里界中"
        else:
            service = InnerRealmService(uow)
            active_session = await service.get_active_session(player.id, player.inner_realm)
            if not active_session:
                result_msg = "⛔ 会话数据错误"
            else:
                if await service.check_sanity_zero(player, active_session):
                    result_msg = service._sanity_collapse_text()
                else:
                    success, message = await service.perform_intimidation(
                        player, active_session, arg_text if arg_text else None
                    )
                    result_msg = message

    await intimidate_cmd.finish(result_msg)


# ==================== 【处决】 ====================

@assassination_cmd.handle()
async def handle_assassination(event: MessageEvent, args: Message = CommandArg()):
    """处决当前场景的NPC"""
    arg_text = args.extract_plain_text().strip()

    def session_factory():
        return AsyncSessionLocal()

    result_msg = None
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            result_msg = "⛔ 请先创建角色"
        elif not player.inner_realm:
            result_msg = "⛔ 你不在任何里界中"
        else:
            service = InnerRealmService(uow)
            active_session = await service.get_active_session(player.id, player.inner_realm)
            if not active_session:
                result_msg = "⛔ 会话数据错误"
            else:
                if await service.check_sanity_zero(player, active_session):
                    result_msg = service._sanity_collapse_text()
                else:
                    success, message = await service.perform_assassination(
                        player, active_session, arg_text if arg_text else None
                    )
                    result_msg = message

    await assassination_cmd.finish(result_msg)


# ==================== 【交谈】 ====================

@talk_cmd.handle()
async def handle_talk(event: MessageEvent, args: Message = CommandArg()):
    """与NPC交谈"""
    arg_text = args.extract_plain_text().strip()

    def session_factory():
        return AsyncSessionLocal()

    result_msg = None
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            result_msg = "⛔ 请先创建角色"
        elif not player.inner_realm:
            result_msg = "⛔ 你不在任何里界中"
        else:
            service = InnerRealmService(uow)
            active_session = await service.get_active_session(player.id, player.inner_realm)
            if not active_session:
                result_msg = "⛔ 会话数据错误"
            else:
                if await service.check_sanity_zero(player, active_session):
                    result_msg = service._sanity_collapse_text()
                else:
                    success, message = await service.talk_to_npc(
                        player, active_session, arg_text if arg_text else None
                    )
                    result_msg = message

    await talk_cmd.finish(result_msg)


# ==================== 【观察】 ====================

@observe_cmd.handle()
async def handle_observe(event: MessageEvent):
    """仔细观察当前场景"""
    def session_factory():
        return AsyncSessionLocal()

    result_msg = None
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            result_msg = "⛔ 请先创建角色"
        elif not player.inner_realm:
            result_msg = "⛔ 你不在任何里界中"
        else:
            service = InnerRealmService(uow)
            active_session = await service.get_active_session(player.id, player.inner_realm)
            if not active_session:
                result_msg = "⛔ 会话数据错误"
            else:
                if await service.check_sanity_zero(player, active_session):
                    result_msg = service._sanity_collapse_text()
                else:
                    result_msg = await service.observe_scene(player, active_session)

    await observe_cmd.finish(result_msg)


# ==================== 【查看线索】 ====================

@view_clues_cmd.handle()
async def handle_view_clues(event: MessageEvent):
    """查看已收集的线索（从玩家全局记录读取）"""
    def session_factory():
        return AsyncSessionLocal()

    result_msg = None
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            result_msg = "⛔ 请先创建角色"
        elif not player.inner_realm:
            result_msg = "⛔ 你不在任何里界中"
        else:
            realm_name = player.inner_realm
            realm_config = InnerRealmConfig.get_realm_config(realm_name)
            if not realm_config:
                result_msg = "⛔ 里界配置错误"
            else:
                # 从玩家全局记录读取线索
                clears = {}
                if hasattr(player, 'inner_realm_clears') and player.inner_realm_clears:
                    try:
                        clears = json.loads(player.inner_realm_clears)
                    except (json.JSONDecodeError, TypeError):
                        clears = {}

                realm_clears = clears.get(realm_name, {})
                clue_ids = realm_clears.get("clues_found", [])

                if not clue_ids:
                    result_msg = "⛔ 你还没有收集任何线索\n💡 观察场景或搜刮可发现线索"
                else:
                    all_clues = {c["id"]: c for c in realm_config.get("clues", [])}

                    lines = [
                        "📖 已收集线索",
                        "━━━━━━━━━━━━━",
                        f"已收集: {len(clue_ids)} / {len(all_clues)}",
                        ""
                    ]

                    for clue_id in clue_ids:
                        clue = all_clues.get(clue_id, {})
                        lines.append(f"📝 {clue.get('name', clue_id)}")
                        lines.append(f"   {clue.get('description', '...')}")
                        if clue.get("reveal"):
                            lines.append(f"   💡 {clue.get('reveal')}")
                        lines.append("")

                    lines.append("━━━━━━━━━━━━━")
                    lines.append("💡 收集全部线索可以触发【真相】结局")

                    result_msg = "\n".join(lines)

    await view_clues_cmd.finish(result_msg)


# ==================== 【使用】里界内道具 ====================

@use_item_cmd.handle()
async def handle_use_item(event: MessageEvent, args: Message = CommandArg()):
    """使用里界内道具"""
    arg_text = args.extract_plain_text().strip()

    def session_factory():
        return AsyncSessionLocal()

    result_msg = None
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            result_msg = "⛔ 请先创建角色"
        elif not player.inner_realm:
            result_msg = "⛔ 你不在任何里界中"
        else:
            service = InnerRealmService(uow)
            active_session = await service.get_active_session(player.id, player.inner_realm)
            if not active_session:
                result_msg = "⛔ 会话数据错误"
            else:
                if await service.check_sanity_zero(player, active_session):
                    result_msg = service._sanity_collapse_text()
                elif not arg_text:
                    result_msg = "⛔ 请指定道具名称\n正确格式: 使用 <道具名>\n💡 使用【道具】查看背包"
                else:
                    success, message = await service.use_item(
                        player, active_session, arg_text
                    )
                    result_msg = message

    await use_item_cmd.finish(result_msg)


# ==================== 【道具】查看里界内道具 ====================

@inventory_cmd.handle()
async def handle_inventory(event: MessageEvent):
    """查看里界内道具"""
    def session_factory():
        return AsyncSessionLocal()

    result_msg = None
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            result_msg = "⛔ 请先创建角色"
        elif not player.inner_realm:
            result_msg = "⛔ 你不在任何里界中"
        else:
            service = InnerRealmService(uow)
            active_session = await service.get_active_session(player.id, player.inner_realm)
            if not active_session:
                result_msg = "⛔ 会话数据错误"
            else:
                result_msg = await service.get_inventory_display(active_session)

    await inventory_cmd.finish(result_msg)


# ==================== 【选择】特殊事件选项 ====================

@choose_cmd.handle()
async def handle_choose(event: MessageEvent, args: Message = CommandArg()):
    """处理特殊事件中的选择"""
    arg_text = args.extract_plain_text().strip()

    if not arg_text:
        await choose_cmd.finish("⛔ 格式错误\n正确格式: 选择 <选项名>")

    def session_factory():
        return AsyncSessionLocal()

    result_msg = None
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            result_msg = "⛔ 请先创建角色"
        elif not player.inner_realm:
            result_msg = "⛔ 你不在任何里界中"
        else:
            service = InnerRealmService(uow)
            active_session = await service.get_active_session(player.id, player.inner_realm)
            if not active_session:
                result_msg = "⛔ 会话数据错误"
            else:
                if await service.check_sanity_zero(player, active_session):
                    result_msg = service._sanity_collapse_text()
                else:
                    success, result = await service.resolve_special_event(
                        player, active_session, arg_text
                    )
                    result_msg = result

    await choose_cmd.finish(result_msg)
