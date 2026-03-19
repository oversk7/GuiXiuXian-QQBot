"""
装备系统命令模块

提供装备相关的用户交互命令：
1. 查看装备栏
2. 装备详情查看
3. 穿戴装备
4. 卸下装备
5. 一键卸下
"""

from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from sqlalchemy import select, and_
from ..models.db import safe_session
from ..models import Player, ItemInstance
from ..config import config
from ..utils import message_add_head
from ..platform_utils import get_unified_player
# 导入装备服务模块（业务逻辑已移至此处，解决模块耦合）
from .equipment_service import recalc_equipment_attributes, EQUIP_ITEM_IDS

# ==================== Feature Flag ====================
# 设置为True使用新版DI架构的EquipmentService，False使用旧版本
# =====================================================


async def find_equipment_by_input(session, player_id: str, input_arg: str) -> ItemInstance:
    """
    根据用户输入查找装备，支持：
    1. 简短编号（1-装备总数）
    2. 原始ID（数字）
    3. 装备名称

    返回找到的装备实例，如果未找到则返回None
    """
    # 先获取玩家所有装备
    stmt_all = select(ItemInstance).where(
        ItemInstance.player_id == player_id,
        ItemInstance.item_id.in_(EQUIP_ITEM_IDS)
    )
    all_equips = (await session.execute(stmt_all)).scalars().all()

    if input_arg.isdigit():
        input_id = int(input_arg)

        # 如果输入的是简短编号（1-装备总数）
        if 1 <= input_id <= len(all_equips):
            return all_equips[input_id - 1]  # 转换为0基索引
        else:
            # 尝试按原始ID查找
            equip = await session.get(ItemInstance, input_id)
            if equip and equip.player_id == player_id and equip.is_equipment:
                return equip
            return None
    else:
        # 按名称查找
        item_config = config.items_config["by_name"].get(input_arg)
        if not item_config or item_config.type.value != "EQUIPMENT":
            return None

        # 在玩家装备中查找该名称的装备
        for equip in all_equips:
            if equip.item_id == item_config.item_id:
                return equip
        return None


def get_equipment_short_id(all_equips: list, target_equip: ItemInstance) -> int:
    """获取装备的简短编号"""
    for i, equip in enumerate(all_equips, 1):
        if equip.id == target_equip.id:
            return i
    return 0

# ---------------- 指令：查看装备栏 ----------------
list_equipment = on_command("装备栏", aliases={"我的装备"}, block=True, priority=5, force_whitespace=True)

@list_equipment.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    # 解析参数
    arg = args.extract_plain_text().strip()
    page = 1
    if arg:
        try:
            page = int(arg)
            if page < 1:
                page = 1
        except ValueError:
            await list_equipment.finish("⛔ 页码必须是正整数")

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        from ..config import config
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await list_equipment.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await list_equipment.finish("⛔ 请先创建角色")

        # 查询玩家所有装备条目
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.item_id.in_(EQUIP_ITEM_IDS)
        )
        equips = (await session.execute(stmt)).scalars().all()

        if not equips:
            await list_equipment.finish("🎒 你的装备栏空空如也")

        # 统计已装备数量
        equipped_count = sum(1 for eq in equips if eq.equipped)

        # 分页设置
        page_size = config.game_config["game"]["inventory_page_size"]  # 使用与背包相同的分页大小
        total_pages = (len(equips) - 1) // page_size + 1
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        current_page_equips = equips[start_idx:end_idx]

        lines = [f"🎽 装备栏 ({equipped_count}/5)", "━━━━━━━━━━━━━"]

        # 为装备分配简短编号（全局编号）
        for i, eq in enumerate(current_page_equips, start=start_idx + 1):
            tpl = eq.config
            equip_state = "🟢已装备" if eq.equipped else "🔘未装备"

            # 构建装备信息
            info_parts = []

            # 基础信息 - 使用全局编号
            info_parts.append(f"🆔{i}│{tpl.name}")

            # 升阶等级
            if eq.upgrade_level > 0:
                info_parts.append(f"⭐+{eq.upgrade_level}")

            # 耐久度
            info_parts.append(f"🛠️{eq.durability}/{tpl.durability}")

            # 宝石镶嵌信息
            if eq.available_gem_slots > 0:
                info_parts.append(f"💎{eq.used_gem_slots}/{eq.available_gem_slots}")

            # 词缀标记
            from .affix_service import get_affixes_from_equipment
            affix_list = get_affixes_from_equipment(eq.extra_attrs)
            if affix_list:
                info_parts.append(f"🔮{len(affix_list)}词缀")

            # 装备状态
            info_parts.append(equip_state)

            lines.append(" ".join(info_parts))

        # 添加分页信息
        if total_pages > 1:
            lines.append("━━━━━━━━━━━━━")
            lines.append(f"📖 第 {page} 页（共 {total_pages} 页）")
            if page < total_pages:
                lines.append("💡 使用【装备栏 页码】查看其他页")

        await list_equipment.finish(message_add_head("\n".join(lines), event))


# ---------------- 指令：装备详情 ----------------
equipment_detail = on_command("装备详情", aliases={"装备信息", "查看装备"}, block=True, priority=5, force_whitespace=True)

@equipment_detail.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    from ..alchemy.service_new import AlchemyService

    arg = args.extract_plain_text().strip()
    if not arg:
        await equipment_detail.finish("⛔ 格式：装备详情 装备编号/名称")

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await equipment_detail.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await equipment_detail.finish("⛔ 请先创建角色")

        # 查找装备
        equip = await find_equipment_by_input(session, player.id, arg)
        if not equip:
            await equipment_detail.finish("⛔ 未找到指定装备，请使用装备栏中显示的编号或装备名称")

        # 获取装备配置
        tpl = equip.config
        if not tpl:
            await equipment_detail.finish("⛔ 装备配置错误")

        # 稀有度中文映射
        rarity_map = {
            "white": "普通",
            "green": "优秀",
            "blue": "稀有",
            "purple": "史诗",
            "orange": "传说",
            "red": "永恒"
        }
        rarity_display = tpl.get_rarity_display()
        rarity_name = rarity_map.get(tpl.rarity, tpl.rarity)

        # 构建详细信息
        lines = [
            f"⚔️ 装备详情",
            f"━━━━━━━━━━━━━",
            f"🎯 名称：{tpl.name}",
            f"🆔 ID：{equip.id}",
            f"📊 等级要求：Lv.{tpl.required_level}",
            f"⭐ 升阶等级：+{equip.upgrade_level}阶",
            f"🛠️ 耐久度：{equip.durability}/{tpl.durability}",
            f"💰 价值：{tpl.price:,} 金币",
            f"🎨 品质：{rarity_display}{rarity_name}",
            f"👕 状态：{'🟢已装备' if equip.equipped else '🔘未装备'}",
            ""
        ]

        # 获取升阶加成倍率（在所有属性显示前获取）
        upgrade_multiplier = equip.get_upgrade_bonus_multiplier()
        is_furnace = equip.item_id == AlchemyService.FURNACE_ITEM_ID
        furnace_success = furnace_durability = None
        if is_furnace:
            furnace_success, furnace_durability = AlchemyService.get_furnace_effects(equip.upgrade_level)

        # 基础属性
        if tpl.attr_bonus or tpl.attr_ratio:
            lines.append("📈 基础属性：")

            # 固定值属性
            if tpl.attr_bonus:
                for k, v in tpl.attr_bonus.items():
                    base_value = int(v)
                    current_value = int(v * upgrade_multiplier)
                    bonus = current_value - base_value

                    attr_name = {
                        "attack": "攻击力", "defense": "防御力", "agility": "敏捷",
                        "luck": "运气", "hp": "生命值", "mp": "理智值",
                        "max_hp": "最大生命值", "max_mp": "最大理智值"
                    }.get(k, k)

                    if bonus > 0:
                        lines.append(f"  • {attr_name}：{base_value} → {current_value} (+{bonus})")
                    else:
                        lines.append(f"  • {attr_name}：{base_value}")

            # 百分比属性
            if tpl.attr_ratio:
                for k, r in tpl.attr_ratio.items():
                    base_ratio = float(r) * 100
                    current_ratio = float(r) * upgrade_multiplier * 100
                    bonus_ratio = current_ratio - base_ratio

                    attr_name = {
                        "attack": "攻击力", "defense": "防御力", "agility": "敏捷",
                        "luck": "运气", "hp": "生命值", "mp": "理智值",
                        "max_hp": "最大生命值", "max_mp": "最大理智值"
                    }.get(k, k)

                    if bonus_ratio > 0:
                        lines.append(f"  • {attr_name}：{base_ratio:.1f}% → 现在{current_ratio:.1f}% (+{bonus_ratio:.1f}%)")
                    else:
                        lines.append(f"  • {attr_name}：{base_ratio:.1f}%")

            lines.append("")

        # 词缀展示
        from .affix_service import get_affixes_from_equipment, format_affixes_display

        affixes = get_affixes_from_equipment(equip.extra_attrs)
        if affixes:
            lines.append("🔮 词缀：")
            lines.extend(format_affixes_display(affixes))
            lines.append("")

        # 宝石/铭文镶嵌信息
        if equip.available_gem_slots > 0:
            lines.append("💎 镶嵌孔位：")
            lines.append(f"  • 孔位：{equip.used_gem_slots}/{equip.available_gem_slots}")

            if equip.used_gem_slots > 0:
                from .gem_socket_service_new import GemSocketService
                from .inscription_service import get_inscription_display
                gem_info = GemSocketService.get_equipment_gem_info(equip)
                for slot_info in gem_info:
                    if not slot_info["is_empty"]:
                        slot_num = slot_info["slot_number"]
                        if slot_info.get("is_inscription"):
                            display = get_inscription_display(slot_info["inscription_data"])
                            lines.append(f"  • 孔位{slot_num}：📜 {display}")
                        else:
                            gem_name = slot_info["gem_name"]
                            gem_type = slot_info["gem_type"]
                            lines.append(f"  • 孔位{slot_num}：{gem_type} - {gem_name}")

            lines.append("")

        # 炼丹炉专属效果展示
        if is_furnace:
            lines.append("🔥 炼丹效果：")
            lines.append(f"  • 当前成功率倍率：×{furnace_success:.1f}")
            lines.append(f"  • 每炉耐久消耗：{furnace_durability}点")

            next_level = equip.upgrade_level + 1
            max_level = equip.config.max_upgrade_level if equip.config else 10
            if next_level <= max_level:
                next_success, next_durability = AlchemyService.get_furnace_effects(next_level)
                lines.append(
                    f"  • 下一阶(+{next_level})预览：成功率×{next_success:.1f}，耐久消耗 {next_durability}点"
                )
            lines.append("")

        # 升阶提升说明
        if equip.upgrade_level > 0:
            lines.append("⭐ 升阶加成：")
            lines.append(f"  • 当前等阶：+{equip.upgrade_level}阶")
            if is_furnace:
                lines.append(f"  • 成功率提升：+{(furnace_success - 1) * 100:.0f}%")
                lines.append(f"  • 当前耐久消耗：{furnace_durability}点/炉")
            else:
                lines.append(f"  • 属性倍率：{upgrade_multiplier:.1f}x")
                lines.append(f"  • 总提升：+{(upgrade_multiplier - 1) * 100:.0f}%")
            lines.append("")

        # 特殊效果（显示解锁状态）
        if hasattr(tpl, 'special_effects') and tpl.special_effects:
            lines.append("✨ 特殊效果：")

            # VIP定制装备列表（0阶即全解锁）
            VIP_EQUIPMENT_IDS = {"vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi", "heaven_retreat_star_blade", "vip_gui_yu", "vip_chrono_watch", "vip_longying_flash", "vip_ghost_dice", "vip_shoes_longren"}
            is_vip_equipment = equip.item_id in VIP_EQUIPMENT_IDS

            if is_vip_equipment:
                # VIP装备：全部效果已解锁
                for idx, effect in enumerate(tpl.special_effects, start=1):
                    desc = effect.get('description', '')
                    if not desc:
                        continue
                    lines.append(f"  ✅ {desc}")
            else:
                # 普通装备：计算已解锁的效果数量（每2阶解锁1个效果）
                unlocked_count = equip.upgrade_level // 2

                for idx, effect in enumerate(tpl.special_effects, start=1):
                    desc = effect.get('description', '')
                    if not desc:
                        continue

                    # 计算解锁所需的升阶等级
                    required_level = idx * 2

                    if idx <= unlocked_count:
                        # 已解锁
                        lines.append(f"  ✅ [{idx}] {desc}")
                    else:
                        # 未解锁
                        lines.append(f"  🔒 [{idx}] {desc} (需要+{required_level}阶)")

            lines.append("")

        # 描述
        lines.append("📝 描述：")
        lines.append(f"  {tpl.description}")

        await equipment_detail.finish(message_add_head("\n".join(lines), event))


# ---------------- 指令：穿戴装备 ----------------
wear_equipment = on_command("装备", aliases={"穿戴", "佩戴"}, block=True, priority=5, force_whitespace=True)

@wear_equipment.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    if not arg:
        await wear_equipment.finish("⛔ 格式：装备 装备编号/名称 [编号2 编号3 ...]")

    arg_list = arg.split()

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await wear_equipment.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await wear_equipment.finish("⛔ 请先创建角色")

        if len(arg_list) == 1:
            # ---- 单件装备：原有逻辑 ----
            equip = await find_equipment_by_input(session, player.id, arg)
            if not equip:
                await wear_equipment.finish("⛔ 未找到指定装备，请使用装备栏中显示的编号或装备名称")

            # 如果是按名称查找且有多个同名装备，优先选择耐久度最高的未装备装备
            if not arg.isdigit():
                item_config = config.items_config["by_name"].get(arg)
                if item_config:
                    stmt = select(ItemInstance).where(
                        ItemInstance.player_id == player.id,
                        ItemInstance.item_id == item_config.item_id,
                        ItemInstance.equipped == False
                    ).order_by(ItemInstance.durability.desc())

                    unequipped_items = (await session.execute(stmt)).scalars().all()
                    if unequipped_items:
                        equip = unequipped_items[0]  # 选择耐久度最高的那件

            if equip.equipped:
                await wear_equipment.finish("⛔ 该装备已经穿戴")
            if equip.config.required_level > player.level:
                await wear_equipment.finish(f"⛔ 等级不足，需要 Lv.{equip.config.required_level}")
            if equip.durability <= 0:
                await wear_equipment.finish("⛔ 该装备已损坏（耐久为0），请先修理后再穿戴")

            same_type_stmt = select(ItemInstance).where(
                ItemInstance.player_id == player.id,
                ItemInstance.item_id == equip.item_id,
                ItemInstance.equipped == True
            )
            same_type_equipped = (await session.execute(same_type_stmt)).scalars().all()
            if same_type_equipped:
                await wear_equipment.finish(f"⛔ 已装备同名装备 {equip.config.name}，不能重复穿戴")

            all_equipped_stmt = select(ItemInstance).where(
                ItemInstance.player_id == player.id,
                ItemInstance.equipped == True,
                ItemInstance.item_id.in_(EQUIP_ITEM_IDS)
            )
            all_equipped = (await session.execute(all_equipped_stmt)).scalars().all()
            if len(all_equipped) >= 5:
                await wear_equipment.finish("⛔ 装备栏已满，最多只能穿戴5件装备，请先卸下其他装备")

            equip.equipped = True
            session.add(equip)

            from ..infrastructure.repositories.item_repository import ItemRepository
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from .equipment_service_new import EquipmentService

            equipment_service = EquipmentService(
                item_repo=ItemRepository(session),
                player_repo=PlayerRepository(session)
            )
            await equipment_service.recalc_equipment_attributes(player)
            session.add(player)
            await session.commit()

            durability_info = f" (ID:{equip.id}, 耐久:{equip.durability}/{equip.config.durability})"
            if equip.durability == 0:
                await wear_equipment.finish(f"⛔ {equip.config.name} 耐久为0，已自动卸下，请先修理")
            await wear_equipment.finish(f"✅ 成功穿戴 {equip.config.name}{durability_info}")

        else:
            # ---- 批量装备：依次装备，每件完成后立即重算属性并提交 ----
            # 初始化装备服务（整个批次共用）
            from ..infrastructure.repositories.item_repository import ItemRepository
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from .equipment_service_new import EquipmentService

            equipment_service = EquipmentService(
                item_repo=ItemRepository(session),
                player_repo=PlayerRepository(session)
            )

            # 查询当前已装备状态，用于本地维护
            all_equipped_stmt = select(ItemInstance).where(
                ItemInstance.player_id == player.id,
                ItemInstance.equipped == True,
                ItemInstance.item_id.in_(EQUIP_ITEM_IDS)
            )
            currently_equipped = list((await session.execute(all_equipped_stmt)).scalars().all())
            equipped_count = len(currently_equipped)
            equipped_item_ids = set(e.item_id for e in currently_equipped)
            equipped_instance_ids = set(e.id for e in currently_equipped)

            success_list = []
            fail_list = []

            for single_arg in arg_list:
                if equipped_count >= 5:
                    fail_list.append(f"{single_arg}: 装备栏已满")
                    continue

                equip = await find_equipment_by_input(session, player.id, single_arg)
                if not equip:
                    fail_list.append(f"{single_arg}: 未找到")
                    continue

                # 名称查找时，优先选择耐久最高的未装备装备（排除本次已装备的）
                if not single_arg.isdigit():
                    item_config = config.items_config["by_name"].get(single_arg)
                    if item_config:
                        stmt = select(ItemInstance).where(
                            ItemInstance.player_id == player.id,
                            ItemInstance.item_id == item_config.item_id,
                            ItemInstance.equipped == False
                        ).order_by(ItemInstance.durability.desc())
                        unequipped_items = [
                            i for i in (await session.execute(stmt)).scalars().all()
                            if i.id not in equipped_instance_ids
                        ]
                        if unequipped_items:
                            equip = unequipped_items[0]

                if equip.equipped or equip.id in equipped_instance_ids:
                    fail_list.append(f"{equip.config.name}(#{single_arg}): 已穿戴")
                    continue
                if equip.config.required_level > player.level:
                    fail_list.append(f"{equip.config.name}(#{single_arg}): 等级不足(需Lv.{equip.config.required_level})")
                    continue
                if equip.durability <= 0:
                    fail_list.append(f"{equip.config.name}(#{single_arg}): 已损坏需修理")
                    continue
                if equip.item_id in equipped_item_ids:
                    fail_list.append(f"{equip.config.name}(#{single_arg}): 已装备同名装备")
                    continue

                # 标记为已装备，立即重算并提交（与单独执行"装备"指令效果完全一致）
                equip.equipped = True
                session.add(equip)
                await equipment_service.recalc_equipment_attributes(player)
                session.add(player)
                await session.commit()

                # 更新本地状态，供后续装备的检查使用
                equipped_count += 1
                equipped_item_ids.add(equip.item_id)
                equipped_instance_ids.add(equip.id)
                success_list.append(f"{equip.config.name}(ID:{equip.id})")

            lines = []
            if success_list:
                lines.append(f"✅ 成功穿戴：{', '.join(success_list)}")
            if fail_list:
                lines.append("❌ 以下装备失败：")
                lines.extend([f"  • {f}" for f in fail_list])
            if not success_list and not fail_list:
                lines.append("⛔ 未处理任何装备")

            await wear_equipment.finish(message_add_head("\n".join(lines), event))


# ---------------- 指令：卸下装备 ----------------
unwear_equipment = on_command("卸下", block=True, priority=5)

@unwear_equipment.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    if not arg:
        await unwear_equipment.finish("⛔ 格式：卸下 装备编号/名称")

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await unwear_equipment.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await unwear_equipment.finish("⛔ 请先创建角色")

        # 查找装备
        equip = await find_equipment_by_input(session, player.id, arg)
        if not equip:
            await unwear_equipment.finish("⛔ 未找到指定装备，请使用装备栏中显示的编号或装备名称")

        # 如果是按名称查找且有多个同名装备，优先选择已装备且升阶等级最高的
        if not arg.isdigit():
            item_config = config.items_config["by_name"].get(arg)
            if item_config:
                stmt = select(ItemInstance).where(
                    ItemInstance.player_id == player.id,
                    ItemInstance.item_id == item_config.item_id,
                    ItemInstance.equipped == True
                ).order_by(ItemInstance.upgrade_level.desc())

                equipped_items = (await session.execute(stmt)).scalars().all()
                if equipped_items:
                    equip = equipped_items[0]  # 选择升阶等级最高的那件

        # 检查是否已装备
        if not equip.equipped:
            await unwear_equipment.finish("⛔ 该装备未穿戴")

        # 检查是否为炼丹炉，如果是则处理进行中的炼丹任务
        from ..alchemy.service_new import AlchemyService
        from ..models.alchemy_task import AlchemyRecord

        failed_tasks = []
        if equip.item_id == AlchemyService.FURNACE_ITEM_ID:
            # 查找使用该炼丹炉的进行中任务
            stmt = select(AlchemyRecord).where(
                and_(
                    AlchemyRecord.player_id == player.id,
                    AlchemyRecord.furnace_id == equip.id,
                    AlchemyRecord.claimed == False
                )
            )
            alchemy_records = (await session.execute(stmt)).scalars().all()

            # 处理进行中的炼丹任务
            for record in alchemy_records:
                if not record.is_finished():
                    # 任务未完成，按失败处理，返还材料
                    failed_tasks.append(f"炼丹任务失败，返还材料")

                    # 返还材料
                    for material_id, quantity in record.materials.items():
                        try:
                            await ItemInstance.add_item(session, player.id, material_id, quantity)
                        except ValueError:
                            # 背包满了，转换为金币
                            material_config = config.items_config["by_id"].get(material_id)
                            if material_config:
                                gold_value = material_config.price * quantity
                                player.gold += gold_value
                                failed_tasks.append(f"背包已满，{material_config.name}×{quantity} 转为 {gold_value} 金币")

                # 删除炼丹记录
                await session.delete(record)

        # 卸下装备
        equip.equipped = False

        # 移除装备的属性加成
        delta = (equip.extra_attrs or {}).get("_persist_bonus", {})
        for k, v in delta.items():
            current_value = getattr(player, k, 0)
            setattr(player, k, max(0, current_value - v))

        # 清除装备的持久化加成记录
        if "_persist_bonus" in (equip.extra_attrs or {}):
            extra_new = {k: v for k, v in equip.extra_attrs.items() if k != "_persist_bonus"}
            equip.extra_attrs = extra_new

        session.add(equip)

        # 重新计算剩余装备的属性加成，确保 mp_from_hp 等全局被动同步
        # 新版本: 使用DI架构的EquipmentService
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from .equipment_service_new import EquipmentService

        equipment_service = EquipmentService(
            item_repo=ItemRepository(session),
            player_repo=PlayerRepository(session)
        )
        await equipment_service.recalc_equipment_attributes(player)
        await session.commit()

        # 构建结果消息
        result_msg = f"✅ 成功卸下 {equip.config.name} (ID:{equip.id})"
        if failed_tasks:
            result_msg += "\n" + "\n".join([f"🔄 {task}" for task in failed_tasks])

        await unwear_equipment.finish(message_add_head(result_msg, event))


# ---------------- 指令：一键卸下 ----------------
unwear_all_equipment = on_command("一键卸下", aliases={"卸下全部", "全部卸下"}, block=True, priority=5)

@unwear_all_equipment.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await unwear_all_equipment.finish("⛔ 请先创建角色")

        # 查找所有已装备的装备
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(EQUIP_ITEM_IDS)
        )
        equipped_items = (await session.execute(stmt)).scalars().all()

        if not equipped_items:
            await unwear_all_equipment.finish("⛔ 你没有穿戴任何装备")

        # 处理炼丹炉相关的任务
        from ..alchemy.service_new import AlchemyService
        from ..models.alchemy_task import AlchemyRecord

        all_failed_tasks = []  # 所有失败的炼丹任务

        unworn_equipment = []  # 记录卸下的装备信息

        # 逐个卸下装备
        for equip in equipped_items:
            # 检查是否为炼丹炉，如果是则处理进行中的炼丹任务
            failed_tasks = []
            if equip.item_id == AlchemyService.FURNACE_ITEM_ID:
                # 查找使用该炼丹炉的进行中任务
                stmt = select(AlchemyRecord).where(
                    and_(
                        AlchemyRecord.player_id == player.id,
                        AlchemyRecord.furnace_id == equip.id,
                        AlchemyRecord.claimed == False
                    )
                )
                alchemy_records = (await session.execute(stmt)).scalars().all()

                # 处理进行中的炼丹任务
                for record in alchemy_records:
                    if not record.is_finished():
                        # 任务未完成，按失败处理，返还材料
                        failed_tasks.append(f"{equip.config.name}(ID:{equip.id}) 炼丹任务失败，返还材料")

                        # 返还材料
                        for material_id, quantity in record.materials.items():
                            try:
                                await ItemInstance.add_item(session, player.id, material_id, quantity)
                            except ValueError:
                                # 背包满了，转换为金币
                                material_config = config.items_config["by_id"].get(material_id)
                                if material_config:
                                    gold_value = material_config.price * quantity
                                    player.gold += gold_value
                                    failed_tasks.append(f"背包已满，{material_config.name}×{quantity} 转为 {gold_value} 金币")

                    # 删除炼丹记录
                    await session.delete(record)

            # 卸下装备
            equip.equipped = False

            # 移除装备的属性加成
            delta = (equip.extra_attrs or {}).get("_persist_bonus", {})
            for k, v in delta.items():
                current_value = getattr(player, k, 0)
                setattr(player, k, max(0, current_value - v))

            # 清除装备的持久化加成记录
            if "_persist_bonus" in (equip.extra_attrs or {}):
                extra_new = {k: v for k, v in equip.extra_attrs.items() if k != "_persist_bonus"}
                equip.extra_attrs = extra_new

            session.add(equip)
            unworn_equipment.append(f"{equip.config.name}(ID:{equip.id})")
            all_failed_tasks.extend(failed_tasks)

        # 重新计算剩余装备的属性加成，确保属性正确恢复
        # 新版本: 使用DI架构的EquipmentService
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from .equipment_service_new import EquipmentService

        equipment_service = EquipmentService(
            item_repo=ItemRepository(session),
            player_repo=PlayerRepository(session)
        )
        await equipment_service.recalc_equipment_attributes(player)
        # 确保当前HP/MP不超过新的上限
        if player.hp > player.max_hp:
            player.hp = player.max_hp
        if player.mp > player.max_mp:
            player.mp = player.max_mp

        session.add(player)
        await session.commit()

        # 构建结果消息
        result_msg = f"✅ 成功卸下 {len(unworn_equipment)} 件装备：\n" + "、".join(unworn_equipment)

        if all_failed_tasks:
            for task_info in all_failed_tasks:
                result_msg += f"\n🔄 {task_info}"

        await unwear_all_equipment.finish(result_msg)


# ==================== 装备菜单（VIP定制装备专属技能） ====================

# VIP装备技能帮助信息注册表
# 格式: item_id -> { "name": 装备名, "icon": 图标, "skills": 技能说明文本 }
_VIP_EQUIPMENT_SKILL_MENUS: dict[str, dict] = {
    "vip_blade_zhanlongshan": {
        "name": "斩龙闪",
        "icon": "⚔️",
        "skills": (
            "⚔️ 斩龙闪 · 灭法之影\n"
            "━━━━━━━━━━━━━\n"
            "本装备无主动技能\n"
            "6项被动效果战斗中自动生效"
        ),
    },
    "vip_robe_jingyuanzhiyi": {
        "name": "镜怨披风",
        "icon": "🪞",
        "skills": (
            "🪞 镜怨披风 · 镜中怨灵\n"
            "━━━━━━━━━━━━━\n"
            "👻 主动技能 — 怨灵拾荒（每日1次）：\n"
            "【怨灵拾荒】 派出怨灵拾荒/领取战利品\n"
            "【镜怨披风】 查看镜怨披风状态面板\n"
            "━━━━━━━━━━━━━\n"
            "3项被动效果战斗中自动生效"
        ),
    },
    "vip_gui_yu": {
        "name": "归雨",
        "icon": "☂️",
        "skills": (
            "☂️ 归雨 · 鬼域雨钉\n"
            "━━━━━━━━━━━━━\n"
            "🌧️ 主动技能 — 鬼域雨钉（锚点传送）：\n"
            "【锚点】 查看已设置的雨钉锚点\n"
            "【锚点 设置 <名称>】 钉下雨钉（最多3个）\n"
            "【锚点 传送 <编号>】 传送（CD5分钟，耗5%理智）\n"
            "【锚点 携带 <UID> <编号>】 携带他人传送（耗10%理智）\n"
            "【锚点 删除 <编号>】 拔除雨钉\n"
            "【同意传送】/【拒绝传送】 回应携带邀请\n"
            "【归雨】查看归雨状态面板"
        ),
    },
    "heaven_retreat_star_blade": {
        "name": "天退星刀",
        "icon": "🔫",
        "skills": (
            "🔫 天退星刀 · 插翅虎\n"
            "━━━━━━━━━━━━━\n"
            "本装备无主动技能\n"
            "3项被动效果战斗中自动生效"
        ),
    },
    "vip_chrono_watch": {
        "name": "折光年",
        "icon": "⏱️",
        "skills": (
            "⏱️ 折光年 · 拨针系统\n"
            "━━━━━━━━━━━━━\n"
            "⏳ 主动技能 — 拨针系统（日常效率）：\n"
            "【拨针 签到】重置签到（每日1次，耐久-3）\n"
            "【拨针 闭关】立即按满时长出关（每日1次，耐久-5）\n"
            "【拨针 讨伐】BOSS攻击次数+1（每日1次，耐久-5）\n"
            "【拨针 委托】额外刷新委托（每日1次，耐久-3）\n"
            "【折光年】查看怀表状态面板"
        ),
    },
    "vip_longying_flash": {
        "name": "龙影闪",
        "icon": "🌀",
        "skills": (
            "🌀 龙影闪 · 灭法之影\n"
            "━━━━━━━━━━━━━\n"
            "🌀 主动技能 — 虚界锚钉（锚点传送）：\n"
            "【锚钉】 查看已设置的锚钉列表\n"
            "【锚钉 设置 <名称>】 撕开虚界裂隙设锚钉（最多3个）\n"
            "【锚钉 传送 <编号>】 穿越虚界传送（CD5分钟，耗5%理智）\n"
            "【锚钉 携带 <UID> <编号>】 拉对方一同穿越\n"
            "【锚钉 删除 <编号>】 缝合裂隙拔除锚钉\n"
            "【同意穿越】/【拒绝穿越】 回应携带邀请\n"
            "【龙影闪】查看装备状态面板"
        ),
    },
    "vip_ghost_dice": {
        "name": "诡面骰",
        "icon": "🎲",
        "skills": (
            "🎲 诡面骰 · 八面诡纹\n"
            "━━━━━━━━━━━━━\n"
            "🎰 主动技能 — 骰相·乱（八面骰）：\n"
            "【掷骰】摇动命运，随机+100%一项特殊属性（每日1次，耐久-5）\n"
            "【诡面骰】查看诡面骰状态面板\n"
            "━━━━━━━━━━━━━\n"
            "5项被动效果战斗中自动生效"
        ),
    },
    "vip_shoes_longren": {
        "name": "龙刃鞋",
        "icon": "👟",
        "skills": (
            "👟 龙刃鞋 · 踏风流\n"
            "━━━━━━━━━━━━━\n"
            "本装备无主动技能\n"
            "3项被动效果战斗中自动生效"
        ),
    },
}


equip_menu_cmd = on_command("装备菜单", aliases={"装备技能", "VIP技能"}, block=True, priority=5)


@equip_menu_cmd.handle()
async def handle_equip_menu(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await equip_menu_cmd.finish("⛔ 请先创建角色")

        # 查询玩家已装备的所有装备
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(list(_VIP_EQUIPMENT_SKILL_MENUS.keys()))
        )
        equipped_vip = (await session.execute(stmt)).scalars().all()

        if not equipped_vip:
            await equip_menu_cmd.finish(
                "⛔ 你当前没有装备任何VIP定制装备\n"
                "💡 VIP定制装备需穿戴后才能查看专属技能菜单"
            )

        # 按装备构建帮助信息
        lines = ["✨ 你的VIP定制装备技能菜单 ✨", "━━━━━━━━━━━━━"]

        for eq in equipped_vip:
            menu = _VIP_EQUIPMENT_SKILL_MENUS.get(eq.item_id)
            if menu:
                lines.append("")
                lines.append(menu["skills"])

        lines.append("")
        lines.append("━━━━━━━━━━━━━")
        lines.append(f"📌 当前装备了 {len(equipped_vip)} 件VIP定制装备")

        await equip_menu_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 铭文列表命令 ====================

inscription_list_cmd = on_command("铭文列表", aliases={"铭文背包", "我的铭文"}, priority=5, block=True)

@inscription_list_cmd.handle()
async def handle_inscription_list(event: MessageEvent, args: Message = CommandArg()):
    from ..models.db import safe_session
    from .inscription_service import get_inscription_display_from_item

    msg = ""
    async with safe_session() as session:
        player = await Player.get_player_by_event(event, session)
        if not player:
            await inscription_list_cmd.finish("你还没有创建角色")

        from sqlalchemy import or_
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            or_(
                ItemInstance.item_id.like("inscription_%"),
                ItemInstance.item_id.like("adv_inscription_%"),
            )
        )
        inscriptions = (await session.execute(stmt)).scalars().all()

        if not inscriptions:
            msg = "📜 你还没有铭文物品\n💡 击杀精英怪可掉落铭文，或用铭文碎片合成\n💡 发送【合成铭文】消耗5个碎片合成基础铭文"
        else:
            lines = ["📜 铭文列表："]
            rarity_map = {"white": "⚪", "green": "🟢", "blue": "🔵", "purple": "🟣", "orange": "🟠"}
            for i, insc in enumerate(inscriptions, 1):
                display = get_inscription_display_from_item(insc)
                rarity = insc.config.rarity if insc.config else "unknown"
                icon = rarity_map.get(rarity, "⚪")
                lines.append(f"  [{i}] {icon} {display}")
            lines.append(f"\n💡 使用【镶嵌 装备编号 孔位 铭文名】将铭文插入装备")
            msg = "\n".join(lines)

    await inscription_list_cmd.finish(Message(msg))
