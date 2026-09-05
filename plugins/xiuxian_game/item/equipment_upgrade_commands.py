"""
装备升阶命令模块

提供装备升阶相关的用户交互命令：
1. 查看升阶信息
2. 执行升阶操作
3. 升阶预览
"""

from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from sqlalchemy import select
from ..models.db import safe_session
from ..models import Player, ItemInstance
from ..config import config
from ..utils_markdown import cmd, build_markdown
from .equipment_upgrade_service import EquipmentUpgradeService, _load_upgrade_config
from .equipment_commands import (
    find_equipment_by_input,
    get_equipment_short_id,
)
# 从装备服务模块导入（已解耦）
from .equipment_service import recalc_equipment_attributes, EQUIP_ITEM_IDS
from ..platform_utils import require_player

# 使用DI架构的EquipmentService和EquipmentUpgradeService


async def _recalculate_equipment_attributes(session, player: Player):
    """重新计算装备属性加成"""
    # 新版本: 使用DI架构的EquipmentService
    from ..infrastructure.repositories.item_repository import ItemRepository
    from ..infrastructure.repositories.player_repository import PlayerRepository
    from .equipment_service import EquipmentService

    equipment_service = EquipmentService(
        item_repo=ItemRepository(session),
        player_repo=PlayerRepository(session)
    )
    await equipment_service.recalc_equipment_attributes(player)
# ---------------- 指令：查看升阶信息 ----------------
upgrade_info_cmd = on_command("升阶信息", aliases={"升阶预览"}, block=True, priority=9)

@upgrade_info_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    if not arg:
        await upgrade_info_cmd.finish("⛔ 格式：升阶信息 装备编号/名称")

    async with safe_session() as session:
        player = await require_player(session, event, upgrade_info_cmd)

        # 查找装备
        equip = await find_equipment_by_input(session, player.id, arg)
        if not equip:
            await upgrade_info_cmd.finish("⛔ 未找到指定装备，请使用装备栏中显示的编号或装备名称")

        if not equip.is_equipment:
            await upgrade_info_cmd.finish("⛔ 该物品不是装备")

        # 获取升阶信息
        current_level = equip.upgrade_level
        if current_level >= 10:
            await upgrade_info_cmd.finish(f"✨ {equip.config.name} 已达最高等级 (+{current_level}阶)")

        target_level = current_level + 1

        # 新版本: 使用DI架构的EquipmentUpgradeService
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from .equipment_upgrade_service import EquipmentUpgradeService

        upgrade_service = EquipmentUpgradeService(
            item_repo=ItemRepository(session),
            player_repo=PlayerRepository(session)
        )

        from ..guild.guild_building_access import get_active_base_building_effects
        from ..models.guild import BuildingType
        refining_effects, refining_name = await get_active_base_building_effects(
            session, player, BuildingType.REFINING_PAVILION
        )
        success_rate_bonus = refining_effects.get("upgrade_success_bonus", 0.0)
        gold_discount = refining_effects.get("upgrade_gold_discount", 0.0)

        required_equipment_count = upgrade_service.get_equipment_requirements(current_level, equip.item_id)
        required_materials = upgrade_service.get_upgrade_materials(current_level, equip.item_id)
        base_required_gold = upgrade_service.get_upgrade_gold_cost(current_level)
        required_gold = upgrade_service.apply_gold_discount(base_required_gold, gold_discount)
        available_equipment = await upgrade_service._item_repo.get_available_equipment_for_upgrade(player.id, equip.item_id, current_level)
        success_rate = upgrade_service.get_success_rate(current_level, False, player.luck, success_rate_bonus)
        success_rate_with_protection = upgrade_service.get_success_rate(current_level, True, player.luck, success_rate_bonus)
        base_success_rate = upgrade_service.get_success_rate(current_level, False, 0)
        # 构建信息显示
        lines = [
            f"# ⚔️ 装备升阶信息",
            f"***",
            f"🎯 装备：{equip.config.name} (ID:{equip.id})",
            f"📊 当前等级：+**{current_level}**阶 → +**{target_level}**阶",
            f"💰 金币消耗：**{required_gold:,}**",
            f"📈 基础成功率：**{base_success_rate:.1%}**",
            f"🍀 运气加成后：**{success_rate:.1%}**",
            f"💎 稳定水晶加成：**{success_rate_with_protection:.1%}**",
            "",
            "🔧 装备合成需求："
        ]
        if refining_effects:
            lines.insert(8, f"⭐ {refining_name}加成：成功率+{success_rate_bonus:.0%}，金币折扣{gold_discount:.0%}")
            if required_gold != base_required_gold:
                lines.insert(4, f"💰 原价：{base_required_gold:,}")

        # 显示装备需求
        equipment_status = "✅" if len(available_equipment) >= required_equipment_count else "❌"
        lines.append(f"{equipment_status} {equip.config.name} +{current_level}阶: {len(available_equipment)}/{required_equipment_count}")

        lines.append("")
        lines.append("📦 升阶石需求：")

        # 显示升阶石需求和拥有情况
        for material_id, required_qty in required_materials.items():
            material_config = config.items_config["by_id"].get(material_id)
            material_name = material_config.name if material_config else material_id

            # 查询拥有数量
            stmt = select(ItemInstance.quantity).where(
                ItemInstance.player_id == player.id,
                ItemInstance.item_id == material_id
            )
            result = await session.execute(stmt)
            owned_qty = sum(result.scalars().all())

            status = "✅" if owned_qty >= required_qty else "❌"
            lines.append(f"{status} {material_name}: {owned_qty}/{required_qty}")

        lines.extend([
            "",
            "💡 使用方法：",
            f"• {cmd(f'升阶 {arg}', f'升阶 {arg}')}",
            f"• {cmd(f'升阶 {arg} 稳定水晶', f'升阶 {arg} 稳定水晶')}",
            "",
            "📝 说明：",
            f"• 需要消耗 {required_equipment_count-1} 个相同装备作为材料",
            "• 只有未装备的装备才能用于合成",
            "• 优先消耗耐久度较低的装备"
        ])

        # 宝石状态提醒
        gem_warn_lines = []
        # 主装备宝石
        main_gem_count = sum(1 for v in (equip.gem_slots_data or {}).values() if v)
        # 副装备（将被消耗的）宝石
        consumed_equips = [eq for eq in available_equipment if eq.id != equip.id]
        consumed_gem_total = sum(
            sum(1 for v in (eq.gem_slots_data or {}).values() if v)
            for eq in consumed_equips
        )
        consequence = _load_upgrade_config()["failure_consequences"].get(target_level, {"downgrade": 0, "destroy": 0.0})

        if main_gem_count > 0 or consumed_gem_total > 0:
            gem_warn_lines.append("")
            gem_warn_lines.append("🔮 宝石提醒：")
        if consumed_gem_total > 0:
            gem_warn_lines.append(f"  💎 副装备上共有 {consumed_gem_total} 个宝石，升阶时将自动全量回收到背包")
        if main_gem_count > 0 and consequence["destroy"] > 0:
            gem_warn_lines.append(f"  ⚠️ 该装备已镶嵌 {main_gem_count} 个宝石")
            gem_warn_lines.append(f"  🎲 此阶段有 {consequence['destroy']:.0%} 装备损坏风险，损坏时每个宝石独立 50% 存活")
            gem_warn_lines.append("  🛡️ 使用稳定水晶可防止装备损坏，宝石全部保留")

        lines.extend(gem_warn_lines)

        buttons = f"\n{cmd('升阶列表')} | {cmd('装备栏')} | {cmd('升阶信息 编号', '升阶信息 ')}"
        await upgrade_info_cmd.finish(build_markdown("\n".join(lines) + buttons))


# ---------------- 指令：装备升阶 ----------------
upgrade_equipment_cmd = on_command("升阶", aliases={"装备升阶"}, block=True, priority=9, force_whitespace=True)

@upgrade_equipment_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    if not arg_text:
        await upgrade_equipment_cmd.finish("⛔ 格式：升阶 装备编号/名称 [稳定水晶]")

    # 解析参数
    parts = arg_text.split()
    equipment_arg = parts[0]
    use_protection = len(parts) > 1 and ("稳定水晶" in parts[1] or "护身符" in parts[1])

    async with safe_session() as session:
        player = await require_player(session, event, upgrade_equipment_cmd)

        # 查找装备
        equip = await find_equipment_by_input(session, player.id, equipment_arg)
        if not equip:
            await upgrade_equipment_cmd.finish("⛔ 未找到指定装备，请使用装备栏中显示的编号或装备名称")

        # 执行升阶
        # 新版本: 使用DI架构的EquipmentUpgradeService
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from .equipment_upgrade_service import EquipmentUpgradeService

        upgrade_service = EquipmentUpgradeService(
            item_repo=ItemRepository(session),
            player_repo=PlayerRepository(session)
        )
        from ..guild.guild_building_access import get_active_base_building_effects
        from ..models.guild import BuildingType
        refining_effects, refining_name = await get_active_base_building_effects(
            session, player, BuildingType.REFINING_PAVILION
        )
        success_rate_bonus = refining_effects.get("upgrade_success_bonus", 0.0)
        gold_discount = refining_effects.get("upgrade_gold_discount", 0.0)

        success, message, result_info = await upgrade_service.perform_upgrade(
            equip,
            player,
            use_protection,
            success_rate_bonus=success_rate_bonus,
            gold_discount=gold_discount,
        )
        # 如果装备升级成功且装备已穿戴，需要重新计算装备属性加成
        if success and equip.equipped:
            await _recalculate_equipment_attributes(session, player)

        await session.commit()

        # 构建结果消息
        result_lines = [message]
        
        if result_info:
            # 显示消耗信息
            consumed_equipment = result_info.get("consumed_equipment", [])
            if consumed_equipment:
                result_lines.append(f"🔧 消耗装备：{', '.join(consumed_equipment)}")

            consumed_materials = result_info.get("consumed_materials", {})
            if consumed_materials:
                material_list = []
                for material_id, qty in consumed_materials.items():
                    material_config = config.items_config["by_id"].get(material_id)
                    material_name = material_config.name if material_config else material_id
                    material_list.append(f"{material_name}×{qty}")
                result_lines.append(f"💎 消耗升阶石：{', '.join(material_list)}")

            consumed_gold = result_info.get("consumed_gold", 0)
            if consumed_gold > 0:
                result_lines.append(f"💰 消耗金币：{consumed_gold:,}")
                if result_info.get("gold_discount", 0) > 0:
                    result_lines.append(
                        f"⭐ {refining_name}金币折扣：-{result_info['gold_discount']:.0%}"
                    )

            if result_info.get("success_rate_bonus", 0) > 0:
                result_lines.append(
                    f"⭐ {refining_name}成功率加成：+{result_info['success_rate_bonus']:.0%}"
                )

        buttons = f"\n{cmd('升阶列表')} | {cmd('装备栏')} | {cmd('升阶信息 编号', '升阶信息 ')}"
        await upgrade_equipment_cmd.finish(build_markdown("\n".join(result_lines) + buttons))


# ---------------- 指令：升阶列表 ----------------
upgrade_list_cmd = on_command("升阶列表", aliases={"可升阶装备"}, block=True, priority=9)

@upgrade_list_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player = await require_player(session, event, upgrade_list_cmd)

        from ..infrastructure.repositories.item_repository import ItemRepository

        all_equips = await ItemRepository(session).get_equipment_for_numbering(
            player.id, EQUIP_ITEM_IDS
        )
        equips = [equip for equip in all_equips if not equip.equipped]

        if not equips:
            await upgrade_list_cmd.finish("🎒 你没有可升阶的装备")

        lines = ["# ⚔️ 可升阶装备列表", "***"]

        # 新版本: 使用DI架构的EquipmentUpgradeService
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from .equipment_upgrade_service import EquipmentUpgradeService

        upgrade_service = EquipmentUpgradeService(
            item_repo=ItemRepository(session),
            player_repo=PlayerRepository(session)
        )

        for equip in equips:
            if equip.upgrade_level >= 10:
                continue  # 跳过已满级装备

            current_level = equip.upgrade_level
            target_level = current_level + 1

            success_rate = upgrade_service.get_success_rate(current_level, False, player.luck)

            # 获取简短编号
            short_id = get_equipment_short_id(all_equips, equip)

            lines.append(
                f"🆔{short_id} │ {equip.config.name} "
                f"+{current_level}→+{target_level} "
                f"({success_rate:.1%})"
            )

        if len(lines) == 2:  # 只有标题
            await upgrade_list_cmd.finish("✨ 所有装备都已达到最高等级")

        lines.append("")
        lines.append("💡 使用 /升阶信息 装备ID 查看详细信息")

        buttons = f"\n{cmd('升阶列表')} | {cmd('装备栏')} | {cmd('升阶信息 编号', '升阶信息 ')}"
        await upgrade_list_cmd.finish(build_markdown("\n".join(lines) + buttons))

# ---------------- 指令：一键升阶 ----------------
auto_upgrade_cmd = on_command("一键升阶", block=True, priority=9, force_whitespace=True)

@auto_upgrade_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    if not arg_text:
        await auto_upgrade_cmd.finish("⛔ 格式：一键升阶 装备编号/名称 目标阶数 [稳定水晶]\n示例：一键升阶 1 5")

    # 解析参数
    parts = arg_text.split()
    if len(parts) < 2:
        await auto_upgrade_cmd.finish("⛔ 格式：一键升阶 装备编号/名称 目标阶数 [稳定水晶]")

    equipment_arg = parts[0]
    use_protection = len(parts) > 2 and ("稳定水晶" in parts[2] or "护身符" in parts[2])

    # 解析目标阶数
    try:
        target_level = int(parts[1])
    except ValueError:
        await auto_upgrade_cmd.finish("⛔ 目标阶数必须是数字（1-10）")

    if target_level < 1 or target_level > 10:
        await auto_upgrade_cmd.finish("⛔ 目标阶数范围：1-10")

    async with safe_session() as session:
        player = await require_player(session, event, auto_upgrade_cmd)

        # 查找装备
        equip = await find_equipment_by_input(session, player.id, equipment_arg)
        if not equip:
            await auto_upgrade_cmd.finish("⛔ 未找到指定装备，请使用装备栏中显示的编号或装备名称")

        if not equip.is_equipment:
            await auto_upgrade_cmd.finish("⛔ 该物品不是装备")

        if equip.upgrade_level >= target_level:
            await auto_upgrade_cmd.finish(f"⛔ 装备当前已是 +{equip.upgrade_level}阶，无需升阶")

        if equip.equipped:
            await auto_upgrade_cmd.finish("⛔ 请先卸下装备再进行升阶")

        # 检查月卡权益
        from ..models.monthly_card import MonthlyCard as MonthlyCardModel
        active_cards = await MonthlyCardModel.get_all_active_cards(session, player.id)
        if not active_cards:
            await auto_upgrade_cmd.finish("⛔ 一键升阶是月卡专属功能，请先购买月卡\n💡 发送【赞助】了解月卡权益")

        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository

        upgrade_service = EquipmentUpgradeService(
            item_repo=ItemRepository(session),
            player_repo=PlayerRepository(session)
        )

        from ..guild.guild_building_access import get_active_base_building_effects
        from ..models.guild import BuildingType
        refining_effects, refining_name = await get_active_base_building_effects(
            session, player, BuildingType.REFINING_PAVILION
        )
        success_rate_bonus = refining_effects.get("upgrade_success_bonus", 0.0)
        gold_discount = refining_effects.get("upgrade_gold_discount", 0.0)

        # 记录初始状态
        start_level = equip.upgrade_level
        equip_name = equip.config.name
        attempts = 0
        successes = 0
        failures = 0
        destroyed = False
        final_level = start_level
        stop_reason = ""
        round_logs = []  # 记录每轮简要结果
        prepare_logs = []  # 素材准备日志（独立展示）

        MAX_ATTEMPTS = 200  # 防止无限循环

        # 循环升阶直到达到目标或无法继续
        while equip.upgrade_level < target_level and attempts < MAX_ATTEMPTS:
            current_level = equip.upgrade_level
            required_side_count = upgrade_service.get_equipment_requirements(current_level, equip.item_id) - 1

            # --- 阶段一：准备足够的辅助装备 ---
            side_pieces = await upgrade_service._get_side_pieces(
                player.id, equip.item_id, current_level, equip.id
            )

            prepare_fail = False
            while len(side_pieces) < required_side_count:
                ok = await upgrade_service._prepare_one_side_piece(
                    current_level, equip.item_id, player, equip.id,
                    prepare_logs, {"attempts": attempts, "successes": successes, "failures": failures},
                    depth=0, use_protection=use_protection
                )
                if not ok:
                    stop_reason = (
                        f"无法凑足 +{current_level}阶素材"
                        f"（需要{required_side_count}个，现有{len(side_pieces)}个）"
                    )
                    prepare_fail = True
                    break
                side_pieces = await upgrade_service._get_side_pieces(
                    player.id, equip.item_id, current_level, equip.id
                )

            if prepare_fail:
                break

            # --- 阶段二：升阶主装备 ---
            can_upgrade, reason = await upgrade_service.can_upgrade(equip, player, gold_discount)
            if not can_upgrade:
                stop_reason = reason
                break

            attempts += 1
            success, message, result_info = await upgrade_service.perform_upgrade(
                equip,
                player,
                use_protection,
                success_rate_bonus=success_rate_bonus,
                gold_discount=gold_discount,
            )
            result_type = result_info.get("result", "")

            if result_type == "destroyed":
                destroyed = True
                stop_reason = "主装备已损坏"
                round_logs.append(f"第{attempts}次主升：💀 损坏")
                break

            new_level = result_info.get("new_level", equip.upgrade_level)

            if success:
                successes += 1
                round_logs.append(f"第{attempts}次主升：✅ →+{new_level}阶")
            else:
                failures += 1
                if result_type == "downgraded":
                    round_logs.append(f"第{attempts}次主升：📉 降到+{new_level}阶")
                elif result_type == "failed_protected":
                    round_logs.append(f"第{attempts}次主升：🛡️ 水晶保护(+{new_level}阶)")
                else:
                    round_logs.append(f"第{attempts}次主升：❌ 失败(+{new_level}阶)")

        if not destroyed:
            final_level = equip.upgrade_level

        await session.commit()

        # 构建结果消息
        lines = ["⚔️ 一键升阶完成", "━━━━━━━━━━━━━"]
        if destroyed:
            lines.append(f"🎯 {equip_name}：+{start_level}阶 → 💀 已损坏")
        else:
            lines.append(f"🎯 {equip_name}：+{start_level}阶 → +{final_level}阶")

        lines.append(f"📊 共尝试 {attempts} 次（成功 {successes} 次 / 失败 {failures} 次）")
        if refining_effects:
            lines.append(f"⭐ {refining_name}加成：成功率+{success_rate_bonus:.0%}，金币折扣{gold_discount:.0%}")

        # 显示轮次日志（最多显示最后15条）
        if round_logs:
            lines.append("")
            if len(round_logs) > 15:
                lines.append(f"（仅显示最后15次，共 {len(round_logs)} 次）")
                display_logs = round_logs[-15:]
            else:
                display_logs = round_logs
            lines.extend(display_logs)

        # 素材准备日志（最多显示10条）
        if prepare_logs:
            lines.append("")
            lines.append("📦 素材准备过程：")
            if len(prepare_logs) > 10:
                lines.append(f"（仅显示最后10条，共{len(prepare_logs)}条）")
                lines.extend(prepare_logs[-10:])
            else:
                lines.extend(prepare_logs)

        lines.append("")
        if destroyed:
            lines.append("💀 装备已在升阶中损坏！")
        elif final_level >= target_level:
            lines.append(f"✅ 已成功达到目标 +{target_level}阶！")
        elif attempts == 0 and not prepare_logs:
            lines.append(f"⛔ 无法开始升阶：{stop_reason}")
        elif attempts >= MAX_ATTEMPTS:
            lines.append(f"⛔ 已达最大尝试次数（{MAX_ATTEMPTS}次），停止升阶")
        else:
            lines.append(f"⛔ 中途停止：{stop_reason}")

        await auto_upgrade_cmd.finish(message_add_head("\n".join(lines), event))


# ---------------- 辅助函数 ----------------
