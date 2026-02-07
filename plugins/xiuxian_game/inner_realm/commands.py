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
exit_realm_cmd = on_command("返回", aliases={"离开里界"}, block=True, priority=5)


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
            error_msg = "⛔ 请先创建角色"
        else:
            error_msg = None

            service = InnerRealmService(uow)

            # 查找玩家的活跃会话
            all_realms = InnerRealmConfig.get_all_realms()
            active_session = None
            realm_config = None

            for realm_key in all_realms.keys():
                session = await service.get_active_session(player.id, realm_key)
                if session:
                    active_session = session
                    realm_config = InnerRealmConfig.get_realm_config(realm_key)
                    break

            if not active_session or not realm_config:
                result_msg = "⛔ 你不在任何里界中\n💡 使用【里界】查看可进入的里界列表"
            else:
                # 解析收集的线索
                clue_ids = json.loads(active_session.clue_collected)
                state = json.loads(active_session.state) if active_session.state else {}
                boss_defeated = state.get("boss_defeated", False)

                lines = [
                    f"🌌 {realm_config['display_name']}",
                    "━━━━━━━━━━━━━",
                    f"📍 当前位置: ({active_session.x}, {active_session.y})",
                    f"⚔️ 击杀数: {active_session.killed_count}",
                    f"🛡️ 救出数: {active_session.saved_count}",
                    f"📖 线索数: {len(clue_ids)}/5",
                ]

                if boss_defeated:
                    lines.append("👹 核心BOSS: 已击败")
                else:
                    lines.append("👹 核心BOSS: 未遭遇")

                lines.extend([
                    "━━━━━━━━━━━━━",
                    "💡 使用【返回】结算并离开里界"
                ])

                result_msg = "\n".join(lines)

    if error_msg:
        await realm_info_cmd.finish(error_msg)
    else:
        await realm_info_cmd.finish(result_msg)


@exit_realm_cmd.handle()
async def handle_exit_realm(event: MessageEvent):
    """离开里界并结算"""

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            error_msg = "⛔ 请先创建角色"
        else:
            error_msg = None

            service = InnerRealmService(uow)

            # 查找玩家的活跃会话
            all_realms = InnerRealmConfig.get_all_realms()
            active_session = None
            realm_config = None

            for realm_key in all_realms.keys():
                session = await service.get_active_session(player.id, realm_key)
                if session:
                    active_session = session
                    realm_config = InnerRealmConfig.get_realm_config(realm_key)
                    break

            if not active_session or not realm_config:
                result_msg = "⛔ 你不在任何里界中"
            else:
                # 结算结局
                ending_info = await service.settle_ending(active_session, realm_config)

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
                    f"📖 线索数: {len(json.loads(active_session.clue_collected))}"
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

    if error_msg:
        await exit_realm_cmd.finish(error_msg)
    else:
        await exit_realm_cmd.finish(result_msg)
