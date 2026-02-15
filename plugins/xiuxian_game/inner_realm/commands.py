"""
里界系统命令处理器

⚠️ 注意：里界系统当前处于迭代开发阶段，仅管理员可用
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from nonebot.rule import Rule
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
    except Exception:
        return False


# ==================== 命令注册 ====================
# ⚠️ 里界系统处于迭代开发阶段，所有命令仅限管理员使用
# 注册命令
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
    permission=SUPERUSER
)


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
    """传送到指定里界（智能识别，不匹配则传递给诡域系统）"""
    arg_text = args.extract_plain_text().strip()

    # 如果没有参数，交给诡域系统处理
    if not arg_text:
        return

    # 检查是否是诡域格式（包含"层诡域"），如果是则交给诡域系统
    if "层诡域" in arg_text or arg_text == "诡域":
        return

    # 解析里界名称
    realm_display_name = arg_text

    def session_factory():
        return AsyncSessionLocal()

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

        # 只有确认是里界命令时才finish（阻断后续处理）
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
            await exit_realm_cmd.finish("⛔ 请先创建角色")

        # Rule 已经保证玩家在里界中，这里无需再次检查
        # if not player.inner_realm:
        #     return  # 不再需要这个判断

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
search_cmd = on_command("搜刮", block=True, priority=4, permission=SUPERUSER)

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
intimidate_cmd = on_command("威吓", block=True, priority=4, permission=SUPERUSER)

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
assassination_cmd = on_command("处决", block=True, priority=4, permission=SUPERUSER)

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
talk_cmd = on_command("交谈", block=True, priority=4, permission=SUPERUSER)

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
rescue_cmd = on_command("救助", aliases={"救出"}, block=True, priority=4, permission=SUPERUSER)

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


# 攻击命令（主动发起战斗）
attack_cmd = on_command("攻击", block=True, priority=4, permission=SUPERUSER)

@attack_cmd.handle()
async def handle_attack(event: MessageEvent):
    """主动攻击当前位置的NPC或BOSS"""

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await attack_cmd.finish("⛔ 请先创建角色")

        # 检查是否在里界中
        if not player.inner_realm:
            await attack_cmd.finish("⛔ 你不在任何里界中")

        service = InnerRealmService(uow)

        # 获取活跃会话
        active_session = await service.get_active_session(player.id, player.inner_realm)
        if not active_session:
            await attack_cmd.finish("⛔ 会话数据错误")

        # 获取当前位置地块
        current_tile = await service.get_current_tile(active_session)
        if not current_tile:
            await attack_cmd.finish("⛔ 地块数据错误")

        # 检查是否可以攻击
        if current_tile.event_type not in ["NPC", "BOSS"]:
            await attack_cmd.finish("⛔ 这里没有可以攻击的目标...")

        state = json.loads(current_tile.state) if current_tile.state else {}

        if not state.get("alive"):
            await attack_cmd.finish("⛔ 这里只剩下一具尸体...")

        # 发起战斗
        victory, message, rewards = await service.start_battle_with_npc(
            player, current_tile, active_session
        )

        await attack_cmd.finish(message)


# 查看线索命令
view_clues_cmd = on_command("查看线索", aliases={"线索列表", "已收集线索"}, block=True, priority=4, permission=SUPERUSER)

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


# ==================== 观察命令 ====================

observe_cmd = on_command("观察", aliases={"环顾", "查看环境"},
                         rule=in_inner_realm_rule, block=True,
                         priority=4, permission=SUPERUSER)


@observe_cmd.handle()
async def handle_observe(event: MessageEvent):
    """仔细观察当前位置和周围环境"""

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await observe_cmd.finish("⛔ 请先创建角色")

        if not player.inner_realm:
            await observe_cmd.finish("⛔ 你不在任何里界中")

        service = InnerRealmService(uow)

        # 获取活跃会话
        active_session = await service.get_active_session(player.id, player.inner_realm)
        if not active_session:
            await observe_cmd.finish("⛔ 会话数据错误")

        # 获取里界配置
        realm_config = InnerRealmConfig.get_realm_config(player.inner_realm)
        if not realm_config:
            await observe_cmd.finish("⛔ 里界配置错误")

        # 生成详细观察信息
        result_msg = await service.observe_surroundings(active_session, realm_config)

        await observe_cmd.finish(result_msg)


# ==================== 移动命令 ====================

# 移动命令 - 使用 Rule 确保只在里界时才匹配，避免与诡域系统冲突
move_cmd = on_command("移动", rule=in_inner_realm_rule, block=True, priority=4, permission=SUPERUSER)
up_cmd = on_command("上", rule=in_inner_realm_rule, block=True, priority=4, permission=SUPERUSER)
down_cmd = on_command("下", rule=in_inner_realm_rule, block=True, priority=4, permission=SUPERUSER)
left_cmd = on_command("左", rule=in_inner_realm_rule, block=True, priority=4, permission=SUPERUSER)
right_cmd = on_command("右", rule=in_inner_realm_rule, block=True, priority=4, permission=SUPERUSER)


async def _handle_move(event: MessageEvent, dx: int, dy: int):
    """统一的移动处理函数"""
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            return "⛔ 请先创建角色"

        # 检查是否在里界中
        if not player.inner_realm:
            return "⛔ 你不在任何里界中\n💡 使用【里界】查看可进入的里界列表"

        service = InnerRealmService(uow)

        # 获取活跃会话
        active_session = await service.get_active_session(player.id, player.inner_realm)
        if not active_session:
            return "⛔ 会话数据错误"

        # 获取里界配置
        realm_config = InnerRealmConfig.get_realm_config(player.inner_realm)
        if not realm_config:
            return "⛔ 里界配置错误"

        # 执行移动
        success, message = await service.move_in_realm(active_session, dx, dy, realm_config)

        if not success:
            return message

        # 移动成功后生成完整反馈
        feedback = await service.generate_move_feedback(active_session, realm_config)

        # 检查是否触发认知篡改
        tamper_warning = ""
        tamper_event = await service.check_cognition_tamper(active_session)
        if tamper_event:
            tamper_desc = await service.apply_cognition_tamper(active_session, tamper_event)
            tamper_warning = f"\n\n{tamper_desc}"

        return f"{feedback}{tamper_warning}"


@move_cmd.handle()
async def handle_move(event: MessageEvent, args: Message = CommandArg()):
    """移动命令"""
    arg_text = args.extract_plain_text().strip()

    if not arg_text:
        await move_cmd.finish("⛔ 格式错误\n正确格式：移动 <方向>\n方向：上/下/左/右")

    # 解析方向
    direction_map = {
        "上": (0, -1),
        "下": (0, 1),
        "左": (-1, 0),
        "右": (1, 0)
    }

    if arg_text not in direction_map:
        await move_cmd.finish("⛔ 方向错误\n可用方向：上/下/左/右")

    dx, dy = direction_map[arg_text]
    result_msg = await _handle_move(event, dx, dy)
    await move_cmd.finish(result_msg)


@up_cmd.handle()
async def handle_up(event: MessageEvent):
    """向上移动"""
    result_msg = await _handle_move(event, 0, -1)
    await up_cmd.finish(result_msg)


@down_cmd.handle()
async def handle_down(event: MessageEvent):
    """向下移动"""
    result_msg = await _handle_move(event, 0, 1)
    await down_cmd.finish(result_msg)


@left_cmd.handle()
async def handle_left(event: MessageEvent):
    """向左移动"""
    result_msg = await _handle_move(event, -1, 0)
    await left_cmd.finish(result_msg)


@right_cmd.handle()
async def handle_right(event: MessageEvent):
    """向右移动"""
    result_msg = await _handle_move(event, 1, 0)
    await right_cmd.finish(result_msg)
