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

# 获取所有装备物品ID
EQUIP_ITEM_IDS = config.items_config["by_type"]["EQUIPMENT"]


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

        lines = [f"🎽 装备栏 ({equipped_count}/4)", "━━━━━━━━━━━━━"]

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
            "orange": "传说"
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

        # 宝石镶嵌信息
        if equip.available_gem_slots > 0:
            lines.append("💎 宝石镶嵌：")
            lines.append(f"  • 孔位：{equip.used_gem_slots}/{equip.available_gem_slots}")
            
            if equip.used_gem_slots > 0:
                from .gem_socket_service import GemSocketService
                gem_info = await GemSocketService.get_equipment_gem_info(equip)
                for slot_info in gem_info:
                    if not slot_info["is_empty"]:
                        slot_num = slot_info["slot_number"]
                        gem_name = slot_info["gem_name"]
                        gem_type = slot_info["gem_type"]
                        lines.append(f"  • 孔位{slot_num}：{gem_type} - {gem_name}")
            
            lines.append("")

        # 升阶提升说明
        if equip.upgrade_level > 0:
            lines.append("⭐ 升阶加成：")
            lines.append(f"  • 当前等阶：+{equip.upgrade_level}阶")
            lines.append(f"  • 属性倍率：{upgrade_multiplier:.1f}x")
            lines.append(f"  • 总提升：+{(upgrade_multiplier - 1) * 100:.0f}%")
            lines.append("")

        # 特殊效果（显示解锁状态）
        if hasattr(tpl, 'special_effects') and tpl.special_effects:
            lines.append("✨ 特殊效果：")

            # 计算已解锁的效果数量（每2阶解锁1个效果）
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
        await wear_equipment.finish("⛔ 格式：装备 装备编号/名称")

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await wear_equipment.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await wear_equipment.finish("⛔ 请先创建角色")

        # 查找装备
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

        # 检查是否已装备
        if equip.equipped:
            await wear_equipment.finish("⛔ 该装备已经穿戴")

        # 检查等级要求
        if equip.config.required_level > player.level:
            await wear_equipment.finish(f"⛔ 等级不足，需要 Lv.{equip.config.required_level}")

        # 检查是否有同名装备已装备
        same_type_stmt = select(ItemInstance).where(
            ItemInstance.player_id == event.get_user_id(),
            ItemInstance.item_id == equip.item_id,
            ItemInstance.equipped == True
        )
        same_type_equipped = (await session.execute(same_type_stmt)).scalars().all()

        if same_type_equipped:
            await wear_equipment.finish(f"⛔ 已装备同名装备 {equip.config.name}，不能重复穿戴")

        # 检查装备数量限制（最多4件）
        all_equipped_stmt = select(ItemInstance).where(
            ItemInstance.player_id == event.get_user_id(),
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(EQUIP_ITEM_IDS)
        )
        all_equipped = (await session.execute(all_equipped_stmt)).scalars().all()

        if len(all_equipped) >= 4:
            await wear_equipment.finish("⛔ 装备栏已满，最多只能穿戴4件装备，请先卸下其他装备")

        # 获取所有已装备的装备（不包括即将穿戴的这件）
        all_equipped_stmt = select(ItemInstance).where(
            ItemInstance.player_id == event.get_user_id(),
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(EQUIP_ITEM_IDS)
        )
        currently_equipped = (await session.execute(all_equipped_stmt)).scalars().all()

        # 1. 先卸下所有装备，恢复基础属性
        for eq in currently_equipped:
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

        # 3. 重新穿戴所有装备（包括新装备），每件都基于基础属性计算
        all_equipment_to_wear = currently_equipped + [equip]

        for eq in all_equipment_to_wear:
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

        # 确保当前HP/MP不超过新的上限
        if player.hp > player.max_hp:
            player.hp = player.max_hp
        if player.mp > player.max_mp:
            player.mp = player.max_mp

        session.add(player)

        await session.commit()

        # 显示穿戴的装备信息，包括ID和耐久度
        durability_info = f" (ID:{equip.id}, 耐久:{equip.durability}/{equip.config.durability})"
        await wear_equipment.finish(f"✅ 成功穿戴 {equip.config.name}{durability_info}")


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
        from ..alchemy.service import AlchemyService
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

        # 确保当前HP/MP不超过新的上限
        if player.hp > player.max_hp:
            player.hp = player.max_hp
        if player.mp > player.max_mp:
            player.mp = player.max_mp

        session.add(player)
        session.add(equip)
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
        player = await session.get(Player, event.get_user_id())
        if not player:
            await unwear_all_equipment.finish("⛔ 请先创建角色")

        # 查找所有已装备的装备
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == event.get_user_id(),
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(EQUIP_ITEM_IDS)
        )
        equipped_items = (await session.execute(stmt)).scalars().all()

        if not equipped_items:
            await unwear_all_equipment.finish("⛔ 你没有穿戴任何装备")

        # 处理炼丹炉相关的任务
        from ..alchemy.service import AlchemyService
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
                        AlchemyRecord.player_id == event.get_user_id(),
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

            session.add(equip)
            unworn_equipment.append(f"{equip.config.name}(ID:{equip.id})")
            all_failed_tasks.extend(failed_tasks)

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



