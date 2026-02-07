"""
里界系统命令处理器
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..platform_utils import get_unified_player
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.db import AsyncSessionLocal
from .service import InnerRealmService
from .config import InnerRealmConfig
import json

# 注册命令
realms_list_cmd = on_command("里界", aliases={"里界列表"}, block=True, priority=5)
enter_realm_cmd = on_command("传送", block=True, priority=5)
realm_info_cmd = on_command("里界信息", block=True, priority=5)
# 里界的返回命令优先级更高（4），在诡域返回命令（5）之前处理
exit_realm_cmd = on_command("返回", aliases={"离开里界"}, block=True, priority=4)


@realms_list_cmd.handle()
async def handle_realms_list(event: MessageEvent):
    """查看可进入的里界列表"""

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            error_msg = "⛔ 请先创建角色"
        else:
            error_msg = None

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

    if error_msg:
        await realms_list_cmd.finish(error_msg)
    else:
        await realms_list_cmd.finish(result_msg)


@enter_realm_cmd.handle()
async def handle_enter_realm(event: MessageEvent, args: Message = CommandArg()):
    """传送到指定里界"""
    arg_text = args.extract_plain_text().strip()

    if not arg_text:
        await enter_realm_cmd.finish("⛔ 格式错误\n正确格式：传送 <里界名>\n例如：传送 第三病栋")

    # 解析里界名称
    realm_display_name = arg_text

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            error_msg = "⛔ 请先创建角色"
        else:
            error_msg = None

            # 根据显示名称找到里界配置key
            all_realms = InnerRealmConfig.get_all_realms()
            realm_key = None

            for key, config in all_realms.items():
                if config.get("display_name") == realm_display_name:
                    realm_key = key
                    break

            if not realm_key:
                result_msg = f"⛔ 未找到里界 '{realm_display_name}'\n💡 使用【里界】查看可进入的里界列表"
            else:
                service = InnerRealmService(uow)
                success, message, session = await service.enter_realm(player, realm_key)

                if success:
                    realm_config = InnerRealmConfig.get_realm_config(realm_key)
                    result_msg = (
                        f"{message}\n"
                        f"━━━━━━━━━━━━━\n"
                        f"📍 当前位置: ({session.x}, {session.y})\n"
                        f"💡 使用【里界信息】查看探索进度\n"
                        f"💡 使用【返回】离开并结算"
                    )
                else:
                    result_msg = message

    if error_msg:
        await enter_realm_cmd.finish(error_msg)
    else:
        await enter_realm_cmd.finish(result_msg)


@realm_info_cmd.handle()
async def handle_realm_info(event: MessageEvent):
    """查看当前里界信息"""

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await realm_info_cmd.finish("⛔ 请先创建角色")

        # 直接通过 player.inner_realm 判断
        if not player.inner_realm:
            await realm_info_cmd.finish("⛔ 你不在任何里界中\n💡 使用【里界】查看可进入的里界列表")

        service = InnerRealmService(uow)
        realm_config = InnerRealmConfig.get_realm_config(player.inner_realm)

        if not realm_config:
            await realm_info_cmd.finish("⛔ 里界配置错误")

        # 获取活跃会话
        active_session = await service.get_active_session(player.id, player.inner_realm)
        if not active_session:
            await realm_info_cmd.finish("⛔ 会话数据错误")

        # 解析收集的线索
        clue_ids = json.loads(active_session.clue_collected)
        state = json.loads(active_session.state) if active_session.state else {}
        boss_defeated = state.get("boss_defeated", False)

        # 理智状态指示器
        sanity_icon = "🟢"
        if active_session.sanity <= 10:
            sanity_icon = "💀"
        elif active_session.sanity <= 30:
            sanity_icon = "🔴"
        elif active_session.sanity <= 50:
            sanity_icon = "🟡"

        lines = [
            f"🌌 {realm_config['display_name']}",
            "━━━━━━━━━━━━━",
            f"📍 当前位置: ({active_session.x}, {active_session.y})",
            f"{sanity_icon} 理智值: {active_session.sanity}/100",
            f"⚔️ 击杀数: {active_session.killed_count}",
            f"🛡️ 救出数: {active_session.saved_count}",
            f"📖 线索数: {len(clue_ids)}/5",
        ]

        if boss_defeated:
            lines.append("👹 核心BOSS: 已击败")
        else:
            lines.append("👹 核心BOSS: 未遭遇")

        # 显示认知篡改状态
        tamper_active = []
        if state.get("phantom_npc_active"):
            tamper_active.append("幻影")
        if state.get("memory_altered"):
            tamper_active.append("记忆错乱")
        if state.get("sensory_distorted"):
            tamper_active.append("感官扭曲")
        if state.get("time_dilated"):
            tamper_active.append("时间错乱")
        if state.get("identity_confused"):
            tamper_active.append("身份混淆")
        if state.get("truth_inverted"):
            tamper_active.append("真相反转")

        if tamper_active:
            lines.append(f"⚠️ 认知异常: {', '.join(tamper_active)}")

        lines.extend([
            "━━━━━━━━━━━━━",
            "💡 使用【返回】结算并离开里界"
        ])

        result_msg = "\n".join(lines)
        await realm_info_cmd.finish(result_msg)


@exit_realm_cmd.handle()
async def handle_exit_realm(event: MessageEvent):
    """离开里界并结算"""

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            # 玩家不存在，不处理，让其他系统继续
            return

        # 直接通过 player.inner_realm 判断
        if not player.inner_realm:
            # 玩家不在里界中，不处理，让诡域系统的返回命令继续处理
            return

        service = InnerRealmService(uow)
        realm_config = InnerRealmConfig.get_realm_config(player.inner_realm)

        if not realm_config:
            await exit_realm_cmd.finish("⛔ 里界配置错误")

        # 获取活跃会话
        active_session = await service.get_active_session(player.id, player.inner_realm)
        if not active_session:
            await exit_realm_cmd.finish("⛔ 会话数据错误")

        # 玩家在里界中，处理离开逻辑
        # 离开里界恢复理智
        final_sanity = active_session.sanity
        recovered_amount, _ = await service.trigger_sanity_recovery(
            active_session, "leave_realm"
        )

        # 结算结局（会清空 player.inner_realm）
        ending_info = await service.settle_ending(player, active_session, realm_config)

        lines = [
            f"🌌 离开 {realm_config['display_name']}",
            "━━━━━━━━━━━━━",
            f"🎬 结局: {ending_info['display_name']}",
            "",
            ending_info['description'],
            "━━━━━━━━━━━━━",
            "📊 本次探索统计:",
            f"⚔️ 击杀数: {active_session.killed_count}",
            f"🛡️ 救出数: {active_session.saved_count}",
            f"📖 线索数: {len(json.loads(active_session.clue_collected))}",
            f"🧠 最终理智: {final_sanity}/100 (+{recovered_amount})"
        ]

        # 显示奖励（当前暂不发放，Phase 2实现）
        if ending_info.get("rewards"):
            lines.append("━━━━━━━━━━━━━")
            lines.append("🎁 获得奖励:")
            for reward in ending_info["rewards"]:
                item_name = reward.get("name", "未知物品")
                amount = reward.get("amount", 1)
                lines.append(f"  • {item_name} x{amount}")

            lines.append("\n💡 提示: 奖励发放功能将在后续版本实现")

        result_msg = "\n".join(lines)
        await exit_realm_cmd.finish(result_msg)


# ==================== 事件触发命令 ====================

# 搜刮命令
search_cmd = on_command("搜刮", block=True, priority=4)

@search_cmd.handle()
async def handle_search(event: MessageEvent):
    """搜刮当前位置"""

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await search_cmd.finish("⛔ 请先创建角色")

        # 检查是否在里界中
        if not player.inner_realm:
            await search_cmd.finish("⛔ 你不在任何里界中")

        service = InnerRealmService(uow)

        # 获取活跃会话
        active_session = await service.get_active_session(player.id, player.inner_realm)
        if not active_session:
            await search_cmd.finish("⛔ 会话数据错误")

        # 获取当前位置地块
        current_tile = await service.get_current_tile(active_session)
        if not current_tile:
            await search_cmd.finish("⛔ 地块数据错误")

        # 执行搜刮判定
        success, message = await service.perform_search(player, active_session, current_tile)

        await search_cmd.finish(message)


# 威吓命令
intimidate_cmd = on_command("威吓", block=True, priority=4)

@intimidate_cmd.handle()
async def handle_intimidate(event: MessageEvent, args: Message = CommandArg()):
    """威吓当前位置的NPC"""
    arg_text = args.extract_plain_text().strip()

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await intimidate_cmd.finish("⛔ 请先创建角色")

        # 检查是否在里界中
        if not player.inner_realm:
            await intimidate_cmd.finish("⛔ 你不在任何里界中")

        service = InnerRealmService(uow)

        # 获取活跃会话
        active_session = await service.get_active_session(player.id, player.inner_realm)
        if not active_session:
            await intimidate_cmd.finish("⛔ 会话数据错误")

        # 获取当前位置地块
        current_tile = await service.get_current_tile(active_session)
        if not current_tile:
            await intimidate_cmd.finish("⛔ 地块数据错误")

        # 执行威吓判定
        success, message = await service.perform_intimidation(
            player, active_session, current_tile, arg_text if arg_text else None
        )

        await intimidate_cmd.finish(message)


# 处决命令
assassination_cmd = on_command("处决", block=True, priority=4)

@assassination_cmd.handle()
async def handle_assassination(event: MessageEvent, args: Message = CommandArg()):
    """静默击杀当前位置的目标"""
    arg_text = args.extract_plain_text().strip()

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await assassination_cmd.finish("⛔ 请先创建角色")

        # 检查是否在里界中
        if not player.inner_realm:
            await assassination_cmd.finish("⛔ 你不在任何里界中")

        service = InnerRealmService(uow)

        # 获取活跃会话
        active_session = await service.get_active_session(player.id, player.inner_realm)
        if not active_session:
            await assassination_cmd.finish("⛔ 会话数据错误")

        # 获取当前位置地块
        current_tile = await service.get_current_tile(active_session)
        if not current_tile:
            await assassination_cmd.finish("⛔ 地块数据错误")

        # 执行处决判定
        success, message = await service.perform_assassination(
            player, active_session, current_tile, arg_text if arg_text else None
        )

        await assassination_cmd.finish(message)


# 交谈命令
talk_cmd = on_command("交谈", block=True, priority=4)

@talk_cmd.handle()
async def handle_talk(event: MessageEvent, args: Message = CommandArg()):
    """与NPC交谈"""
    arg_text = args.extract_plain_text().strip()

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await talk_cmd.finish("⛔ 请先创建角色")

        # 检查是否在里界中
        if not player.inner_realm:
            await talk_cmd.finish("⛔ 你不在任何里界中")

        service = InnerRealmService(uow)

        # 获取活跃会话
        active_session = await service.get_active_session(player.id, player.inner_realm)
        if not active_session:
            await talk_cmd.finish("⛔ 会话数据错误")

        # 获取当前位置地块
        current_tile = await service.get_current_tile(active_session)
        if not current_tile:
            await talk_cmd.finish("⛔ 地块数据错误")

        # 执行交谈
        success, message = await service.talk_to_npc(
            player, active_session, current_tile, arg_text if arg_text else None
        )

        await talk_cmd.finish(message)


# 救助命令
rescue_cmd = on_command("救助", aliases={"救出"}, block=True, priority=4)

@rescue_cmd.handle()
async def handle_rescue(event: MessageEvent):
    """救助幸存者"""

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await rescue_cmd.finish("⛔ 请先创建角色")

        # 检查是否在里界中
        if not player.inner_realm:
            await rescue_cmd.finish("⛔ 你不在任何里界中")

        service = InnerRealmService(uow)

        # 获取活跃会话
        active_session = await service.get_active_session(player.id, player.inner_realm)
        if not active_session:
            await rescue_cmd.finish("⛔ 会话数据错误")

        # 获取当前位置地块
        current_tile = await service.get_current_tile(active_session)
        if not current_tile:
            await rescue_cmd.finish("⛔ 地块数据错误")

        # 执行救助
        success, message = await service.save_survivor(player, active_session, current_tile)

        await rescue_cmd.finish(message)


# 查看线索命令
view_clues_cmd = on_command("查看线索", aliases={"线索列表", "已收集线索"}, block=True, priority=4)

@view_clues_cmd.handle()
async def handle_view_clues(event: MessageEvent):
    """查看已收集的线索"""

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await view_clues_cmd.finish("⛔ 请先创建角色")

        # 检查是否在里界中
        if not player.inner_realm:
            await view_clues_cmd.finish("⛔ 你不在任何里界中")

        service = InnerRealmService(uow)

        # 获取活跃会话
        active_session = await service.get_active_session(player.id, player.inner_realm)
        if not active_session:
            await view_clues_cmd.finish("⛔ 会话数据错误")

        # 获取里界配置
        realm_config = InnerRealmConfig.get_realm_config(player.inner_realm)
        if not realm_config:
            await view_clues_cmd.finish("⛔ 里界配置错误")

        # 解析收集的线索
        clue_ids = json.loads(active_session.clue_collected)

        if not clue_ids:
            await view_clues_cmd.finish("⛔ 你还没有收集任何线索\n💡 探索地图寻找【CLUE】地块")

        # 获取线索详情
        all_clues = {c["id"]: c for c in realm_config.get("clues", [])}

        lines = [
            "📖 已收集线索",
            "━━━━━━━━━━━━━",
            f"已收集：{len(clue_ids)} / {len(all_clues)}",
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

        await view_clues_cmd.finish("\n".join(lines))
