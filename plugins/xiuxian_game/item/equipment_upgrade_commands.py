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
from .equipment_commands import find_equipment_by_input, get_equipment_short_id, EQUIP_ITEM_IDS


async def _recalculate_equipment_attributes(session, player: Player):
    """重新计算装备属性加成"""
    # 获取所有已装备的装备
    equip_item_ids = config.items_config["by_type"]["EQUIPMENT"]
    stmt = select(ItemInstance).where(
        ItemInstance.player_id == player.id,
        ItemInstance.equipped == True,
        ItemInstance.item_id.in_(equip_item_ids)
    )
    equipped_items = (await session.execute(stmt)).scalars().all()

    # 1. 先卸下所有装备，恢复基础属性
    for eq in equipped_items:
        # 恢复玩家属性
        delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
        for k, v in delta.items():
            setattr(player, k, getattr(player, k) - v)

        # 清除持久化记录并标记未穿戴
        if "_persist_bonus" in (eq.extra_attrs or {}):
            extra_new = {k: v for k, v in eq.extra_attrs.items() if k != "_persist_bonus"}
            eq.extra_attrs = extra_new

        eq.equipped = False

    # 2. 获取玩家基础属性（无装备加成）
    base_attrs = {
        "attack": player.attack,
        "defense": player.defense,
        "agility": player.agility,
        "luck": player.luck,
        "max_hp": player.max_hp,
        "max_mp": player.max_mp,
    }

    # 3. 重新穿戴所有装备，每件都基于基础属性计算
    for eq in equipped_items:
        # 标记为已装备
        eq.equipped = True

        # 基于基础属性计算装备加成
        attrs_temp = base_attrs.copy()
        eq.apply_attr_bonus(attrs_temp, base_attrs)
        new_delta = {}
        for k in attrs_temp:
            if k in base_attrs:
                if attrs_temp[k] != base_attrs[k]:
                    new_delta[k] = attrs_temp[k] - base_attrs[k]
            else:
                # 对于base_attrs中不存在的属性，直接使用新值作为加成
                if attrs_temp[k] != 0:
                    new_delta[k] = attrs_temp[k]

        # 应用到玩家属性
        for k, v in new_delta.items():
            setattr(player, k, getattr(player, k) + v)

        # 保存新的持久化加成
        extra = eq.extra_attrs or {}
        extra["_persist_bonus"] = new_delta
        eq.extra_attrs = extra
        session.add(eq)

    # 3.5 处理“生命→理智”的全局被动（如：斩龙闪）——应在面板上全局生效
    # 将 YAML 中的 mp_from_hp 从战斗内首回合，转为此处的全局持久化属性加成
    # 口径：先应用其它装备的HP加成，再据此计算能转换的MP（排除自身对HP的加成，避免自我放大）
    mp_from_hp_effects = []  # (equip, pct, flat, is_percentage)
    total_pct = 0.0
    total_flat = 0
    for eq2 in equipped_items:
        cfg2 = eq2.config if hasattr(eq2, 'config') else None
        if not cfg2 or not getattr(cfg2, 'special_effects', None):
            continue
        for eff in cfg2.special_effects:
            if eff.get('effect') == 'mp_from_hp':
                is_pct = bool(eff.get('is_percentage', True))
                if is_pct:
                    val_pct = float(eff.get('value', 0) or 0)
                    if val_pct > 0:
                        total_pct += val_pct
                        mp_from_hp_effects.append((eq2, val_pct, 0, True))
                else:
                    val_flat = int(eff.get('value', 0) or 0)
                    if val_flat > 0:
                        total_flat += val_flat
                        mp_from_hp_effects.append((eq2, 0.0, val_flat, False))
    if mp_from_hp_effects:
        current_hp_after_all = int(getattr(player, 'max_hp', 0) or 0)
        hp_from_self_equips = 0
        for (eq2, _, _, _) in mp_from_hp_effects:
            delta2 = (eq2.extra_attrs or {}).get("_persist_bonus", {})
            hp_from_self_equips += int(delta2.get("max_hp", 0) or 0)
        base_for_convert = max(1, current_hp_after_all - hp_from_self_equips)
        bonus_from_pct = int(base_for_convert * total_pct / 100.0) if total_pct > 0 else 0
        total_bonus_mp = bonus_from_pct + int(total_flat)
        if total_bonus_mp > 0:
            remaining = total_bonus_mp
            for idx, (eq2, pct, flat, is_pct) in enumerate(mp_from_hp_effects):
                part = 0
                if is_pct and pct > 0:
                    part = int(base_for_convert * pct / 100.0)
                elif (not is_pct) and flat > 0:
                    part = int(flat)
                if idx == len(mp_from_hp_effects) - 1:
                    part = remaining
                remaining -= part
                if part <= 0:
                    continue
                player.max_mp = int(getattr(player, 'max_mp', 0)) + part
                extra2 = eq2.extra_attrs or {}
                persist = dict(extra2.get("_persist_bonus", {}))
                persist["max_mp"] = int(persist.get("max_mp", 0)) + part
                extra2["_persist_bonus"] = persist
                eq2.extra_attrs = extra2
                session.add(eq2)

    # 确保当前HP/MP不超过新的上限
    if player.hp > player.max_hp:
        player.hp = player.max_hp
    if player.mp > player.max_mp:
        player.mp = player.max_mp

    session.add(player)


# ---------------- 指令：查看升阶信息 ----------------
upgrade_info_cmd = on_command("升阶信息", aliases={"升阶预览"}, block=True, priority=5)

@upgrade_info_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    if not arg:
        await upgrade_info_cmd.finish("⛔ 格式：升阶信息 装备编号/名称")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
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
        required_equipment_count = EquipmentUpgradeService.get_equipment_requirements(current_level)
        required_materials = EquipmentUpgradeService.get_upgrade_materials(current_level)
        required_gold = EquipmentUpgradeService.get_upgrade_gold_cost(current_level)

        # 获取可用装备数量
        available_equipment = await EquipmentUpgradeService.get_available_equipment_for_upgrade(
            session, player.id, equip.item_id, current_level
        )
        success_rate = EquipmentUpgradeService.get_success_rate(current_level, False, player.luck)
        success_rate_with_protection = EquipmentUpgradeService.get_success_rate(current_level, True, player.luck)

        # 计算基础成功率（不含运气加成）
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
        player = await session.get(Player, event.get_user_id())
        if not player:
            await upgrade_equipment_cmd.finish("⛔ 请先创建角色")

        # 查找装备
        equip = await find_equipment_by_input(session, event.get_user_id(), equipment_arg)
        if not equip:
            await upgrade_equipment_cmd.finish("⛔ 未找到指定装备，请使用装备栏中显示的编号或装备名称")

        # 执行升阶
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
        player = await session.get(Player, event.get_user_id())
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

        for equip in equips:
            if equip.upgrade_level >= 10:
                continue  # 跳过已满级装备

            current_level = equip.upgrade_level
            target_level = current_level + 1
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
