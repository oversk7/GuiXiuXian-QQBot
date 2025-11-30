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
from ..utils import message_add_head
from .equipment_upgrade_service import EquipmentUpgradeService
from .equipment_commands import (
    find_equipment_by_input,
    get_equipment_short_id,
)
# 从装备服务模块导入（已解耦）
from .equipment_service import recalc_equipment_attributes, EQUIP_ITEM_IDS
from ..platform_utils import get_unified_player

# ==================== Feature Flag ====================
# 设置为True使用新版DI架构的EquipmentService，False使用旧版本
USE_NEW_EQUIPMENT_SERVICE = True
# 设置为True使用新版DI架构的EquipmentUpgradeService，False使用旧版本
USE_NEW_EQUIPMENT_UPGRADE_SERVICE = True
# =====================================================


async def _recalculate_equipment_attributes(session, player: Player):
    """重新计算装备属性加成"""
    if USE_NEW_EQUIPMENT_SERVICE:
        # 新版本: 使用DI架构的EquipmentService
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from .equipment_service_new import EquipmentService

        equipment_service = EquipmentService(
            item_repo=ItemRepository(session),
            player_repo=PlayerRepository(session)
        )
        await equipment_service.recalc_equipment_attributes(player)
    else:
        # 旧版本: 使用静态函数
        await recalc_equipment_attributes(session, player)


# ---------------- 指令：查看升阶信息 ----------------
upgrade_info_cmd = on_command("升阶信息", aliases={"升阶预览"}, block=True, priority=5)

@upgrade_info_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    if not arg:
        await upgrade_info_cmd.finish("⛔ 格式：升阶信息 装备编号/名称")

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await upgrade_info_cmd.finish("⛔ 请先创建角色")

        # 查找装备
        equip = await find_equipment_by_input(session, event.get_user_id(), arg)
        if not equip:
            await upgrade_info_cmd.finish("⛔ 未找到指定装备，请使用装备栏中显示的编号或装备名称")

        if not equip.is_equipment:
            await upgrade_info_cmd.finish("⛔ 该物品不是装备")

        # 获取升阶信息
        current_level = equip.upgrade_level
        if current_level >= 10:
            await upgrade_info_cmd.finish(f"✨ {equip.config.name} 已达最高等级 (+{current_level}阶)")

        target_level = current_level + 1

        if USE_NEW_EQUIPMENT_UPGRADE_SERVICE:
            # 新版本: 使用DI架构的EquipmentUpgradeService
            from ..infrastructure.repositories.item_repository import ItemRepository
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from .equipment_upgrade_service_new import EquipmentUpgradeService as EquipmentUpgradeServiceNew

            upgrade_service = EquipmentUpgradeServiceNew(
                item_repo=ItemRepository(session),
                player_repo=PlayerRepository(session)
            )

            required_equipment_count = upgrade_service.get_equipment_requirements(current_level, equip.item_id)
            required_materials = upgrade_service.get_upgrade_materials(current_level, equip.item_id)
            required_gold = upgrade_service.get_upgrade_gold_cost(current_level)
            available_equipment = await upgrade_service._item_repo.get_available_equipment_for_upgrade(player.id, equip.item_id, current_level)
            success_rate = upgrade_service.get_success_rate(current_level, False, player.luck)
            success_rate_with_protection = upgrade_service.get_success_rate(current_level, True, player.luck)
            base_success_rate = upgrade_service.get_success_rate(current_level, False, 0)
        else:
            # 旧版本: 使用静态方法
            required_equipment_count = EquipmentUpgradeService.get_equipment_requirements(current_level)
            required_materials = EquipmentUpgradeService.get_upgrade_materials(current_level)
            required_gold = EquipmentUpgradeService.get_upgrade_gold_cost(current_level)
            available_equipment = await EquipmentUpgradeService.get_available_equipment_for_upgrade(
                session, player.id, equip.item_id, current_level
            )
            success_rate = EquipmentUpgradeService.get_success_rate(current_level, False, player.luck)
            success_rate_with_protection = EquipmentUpgradeService.get_success_rate(current_level, True, player.luck)
            base_success_rate = EquipmentUpgradeService.get_success_rate(current_level, False, 0)

        # 构建信息显示
        lines = [
            f"⚔️ 装备升阶信息（装备合成模式）",
            f"━━━━━━━━━━━━━",
            f"🎯 装备：{equip.config.name} (ID:{equip.id})",
            f"📊 当前等级：+{current_level}阶 → +{target_level}阶",
            f"💰 金币消耗：{required_gold:,}",
            f"📈 基础成功率：{base_success_rate:.1%}",
            f"🍀 运气加成后：{success_rate:.1%}",
            f"💎 稳定水晶加成：{success_rate_with_protection:.1%}",
            "",
            "🔧 装备合成需求："
        ]

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
                ItemInstance.player_id == event.get_user_id(),
                ItemInstance.item_id == material_id
            )
            result = await session.execute(stmt)
            owned_qty = sum(result.scalars().all())

            status = "✅" if owned_qty >= required_qty else "❌"
            lines.append(f"{status} {material_name}: {owned_qty}/{required_qty}")

        lines.extend([
            "",
            "💡 使用方法：",
            f"• 升阶 {arg}",
            f"• 升阶 {arg} 稳定水晶",
            "",
            "📝 说明：",
            f"• 需要消耗 {required_equipment_count-1} 个相同装备作为材料",
            "• 只有未装备的装备才能用于合成",
            "• 优先消耗耐久度较低的装备"
        ])

        await upgrade_info_cmd.finish(message_add_head("\n".join(lines), event))


# ---------------- 指令：装备升阶 ----------------
upgrade_equipment_cmd = on_command("升阶", aliases={"装备升阶"}, block=True, priority=5, force_whitespace=True)

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
        player = await get_unified_player(session, event)
        if not player:
            await upgrade_equipment_cmd.finish("⛔ 请先创建角色")

        # 查找装备
        equip = await find_equipment_by_input(session, event.get_user_id(), equipment_arg)
        if not equip:
            await upgrade_equipment_cmd.finish("⛔ 未找到指定装备，请使用装备栏中显示的编号或装备名称")

        # 执行升阶
        if USE_NEW_EQUIPMENT_UPGRADE_SERVICE:
            # 新版本: 使用DI架构的EquipmentUpgradeService
            from ..infrastructure.repositories.item_repository import ItemRepository
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from .equipment_upgrade_service_new import EquipmentUpgradeService as EquipmentUpgradeServiceNew

            upgrade_service = EquipmentUpgradeServiceNew(
                item_repo=ItemRepository(session),
                player_repo=PlayerRepository(session)
            )
            success, message, result_info = await upgrade_service.perform_upgrade(equip, player, use_protection)
        else:
            # 旧版本: 使用静态方法
            success, message, result_info = await EquipmentUpgradeService.perform_upgrade(
                session, equip, player, use_protection
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

        await upgrade_equipment_cmd.finish(message_add_head("\n".join(result_lines), event))


# ---------------- 指令：升阶列表 ----------------
upgrade_list_cmd = on_command("升阶列表", aliases={"可升阶装备"}, block=True, priority=5)

@upgrade_list_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await upgrade_list_cmd.finish("⛔ 请先创建角色")

        # 查询所有装备
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == event.get_user_id(),
            ItemInstance.item_id.in_(EQUIP_ITEM_IDS),
            ItemInstance.equipped == False  # 只显示未装备的
        )
        equips = (await session.execute(stmt)).scalars().all()

        if not equips:
            await upgrade_list_cmd.finish("🎒 你没有可升阶的装备")

        # 获取玩家所有装备用于编号映射
        stmt_all = select(ItemInstance).where(
            ItemInstance.player_id == event.get_user_id(),
            ItemInstance.item_id.in_(EQUIP_ITEM_IDS)
        )
        all_equips = (await session.execute(stmt_all)).scalars().all()

        lines = ["⚔️ 可升阶装备列表", "━━━━━━━━━━━━━"]

        if USE_NEW_EQUIPMENT_UPGRADE_SERVICE:
            # 新版本: 使用DI架构的EquipmentUpgradeService
            from ..infrastructure.repositories.item_repository import ItemRepository
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from .equipment_upgrade_service_new import EquipmentUpgradeService as EquipmentUpgradeServiceNew

            upgrade_service = EquipmentUpgradeServiceNew(
                item_repo=ItemRepository(session),
                player_repo=PlayerRepository(session)
            )

        for equip in equips:
            if equip.upgrade_level >= 10:
                continue  # 跳过已满级装备

            current_level = equip.upgrade_level
            target_level = current_level + 1

            if USE_NEW_EQUIPMENT_UPGRADE_SERVICE:
                success_rate = upgrade_service.get_success_rate(current_level, False, player.luck)
            else:
                success_rate = EquipmentUpgradeService.get_success_rate(current_level, False, player.luck)

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

        await upgrade_list_cmd.finish(message_add_head("\n".join(lines), event))


# ---------------- 辅助函数 ----------------
