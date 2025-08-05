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

# ---------------- 指令：查看装备栏 ----------------
list_equipment = on_command("装备栏", aliases={"我的装备"}, block=True, priority=5)

@list_equipment.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await list_equipment.finish("⛔ 请先创建角色")

        # 查询玩家所有装备条目
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == event.get_user_id(),
            ItemInstance.item_id.in_(EQUIP_ITEM_IDS)
        )
        equips = (await session.execute(stmt)).scalars().all()

        if not equips:
            await list_equipment.finish("🎒 你的装备栏空空如也")

        lines = ["🎽 装备栏", "━━━"]
        for eq in equips:
            tpl = eq.config
            equip_state = "🟢已装备" if eq.equipped else "🔘未装备"

            # 构建装备信息
            info_parts = []

            # 基础信息
            info_parts.append(f"🆔{eq.id}│{tpl.name}")

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

        await list_equipment.finish(message_add_head("\n".join(lines), event))


# ---------------- 指令：装备详情 ----------------
equipment_detail = on_command("装备详情", aliases={"装备信息", "查看装备"}, block=True, priority=5)

@equipment_detail.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    if not arg:
        await equipment_detail.finish("⛔ 格式：装备详情 装备ID/名称")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await equipment_detail.finish("⛔ 请先创建角色")

        # 查找装备
        equip = None
        
        # 尝试按ID查找
        if arg.isdigit():
            equip_id = int(arg)
            equip = await session.get(ItemInstance, equip_id)
            if not equip or equip.player_id != event.get_user_id() or not equip.is_equipment:
                await equipment_detail.finish("⛔ 无效装备 ID 或非本人所有")
        else:
            # 按名称查找，优先选择已装备的
            item_config = config.items_config["by_name"].get(arg)
            if not item_config or item_config.type.value != "EQUIPMENT":
                await equipment_detail.finish("⛔ 未找到对应装备名称，或该物品不是装备")

            # 查找玩家所有该名称的装备，优先选择已装备的
            stmt = select(ItemInstance).where(
                ItemInstance.player_id == event.get_user_id(),
                ItemInstance.item_id == item_config.item_id
            ).order_by(ItemInstance.equipped.desc(), ItemInstance.upgrade_level.desc())

            items = (await session.execute(stmt)).scalars().all()
            if not items:
                await equipment_detail.finish(f"⛔ 你没有 {arg}")
            
            equip = items[0]

        # 获取装备配置
        tpl = equip.config
        if not tpl:
            await equipment_detail.finish("⛔ 装备配置错误")

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
            f"🎨 品质：{tpl.rarity}",
            f"👕 状态：{'🟢已装备' if equip.equipped else '🔘未装备'}",
            ""
        ]

        # 基础属性
        if tpl.attr_bonus or tpl.attr_ratio:
            lines.append("📈 基础属性：")
            
            # 获取升阶加成倍率
            upgrade_multiplier = equip.get_upgrade_bonus_multiplier()
            
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
                        lines.append(f"  • {attr_name}：{base_ratio:.1f}% → {current_ratio:.1f}% (+{bonus_ratio:.1f}%)")
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

        # 描述
        lines.append("📝 描述：")
        lines.append(f"  {tpl.description}")

        await equipment_detail.finish(message_add_head("\n".join(lines), event))


# ---------------- 指令：穿戴装备 ----------------
wear_equipment = on_command("装备", aliases={"穿戴", "佩戴"}, block=True, priority=5)

@wear_equipment.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    if not arg:
        await wear_equipment.finish("⛔ 格式：装备 装备ID/名称")

    async with safe_session() as session:
        equip = None

        # 尝试按ID查找
        if arg.isdigit():
            equip_id = int(arg)
            equip = await session.get(ItemInstance, equip_id)
            if not equip or equip.player_id != event.get_user_id() or not equip.is_equipment:
                await wear_equipment.finish("⛔ 无效装备 ID 或非本人所有")
        else:
            # 按名称查找，优先选择耐久度最高的未装备装备
            item_config = config.items_config["by_name"].get(arg)
            if not item_config or item_config.type.value != "EQUIPMENT":
                await wear_equipment.finish("⛔ 未找到对应装备名称，或该物品不是装备")

            # 查找玩家所有该名称的未装备装备，按耐久度降序排列
            stmt = select(ItemInstance).where(
                ItemInstance.player_id == event.get_user_id(),
                ItemInstance.item_id == item_config.item_id,
                ItemInstance.equipped == False
            ).order_by(ItemInstance.durability.desc())

            unequipped_items = (await session.execute(stmt)).scalars().all()
            if not unequipped_items:
                await wear_equipment.finish(f"⛔ 你没有未装备的 {arg}")

            # 选择耐久度最高的那件
            equip = unequipped_items[0]

        # 检查是否已装备
        if equip.equipped:
            await wear_equipment.finish("⛔ 该装备已经穿戴")

        # 获取玩家信息
        player = await session.get(Player, event.get_user_id())

        # 检查等级要求
        if equip.config.required_level > player.level:
            await wear_equipment.finish(f"⛔ 等级不足，需要 Lv.{equip.config.required_level}")

        # 检查是否有同类型装备已装备，如果有则先卸下
        same_type_stmt = select(ItemInstance).where(
            ItemInstance.player_id == event.get_user_id(),
            ItemInstance.item_id == equip.item_id,
            ItemInstance.equipped == True
        )
        same_type_equipped = (await session.execute(same_type_stmt)).scalars().all()

        for old_equip in same_type_equipped:
            old_equip.equipped = False
            # 移除旧装备的属性加成
            old_delta = (old_equip.extra_attrs or {}).get("_persist_bonus", {})
            for k, v in old_delta.items():
                current_value = getattr(player, k, 0)
                setattr(player, k, max(0, current_value - v))
            session.add(old_equip)

        # 穿戴新装备
        equip.equipped = True

        # 计算并应用属性加成
        # 获取玩家基础属性（无装备加成）
        base_attrs = {
            "attack": player.attack,
            "defense": player.defense,
            "agility": player.agility,
            "luck": player.luck,
            "max_hp": player.max_hp,
            "max_mp": player.max_mp,
        }

        # 创建临时属性字典用于计算装备加成
        temp_attrs = base_attrs.copy()

        # 使用装备的 apply_attr_bonus 方法计算加成
        equip.apply_attr_bonus(temp_attrs, base_attrs)

        # 计算差值（即装备提供的加成）
        delta = {}
        for attr, new_value in temp_attrs.items():
            base_value = base_attrs[attr]
            if new_value != base_value:
                delta[attr] = new_value - base_value

        # 应用属性加成到玩家
        for k, v in delta.items():
            current_value = getattr(player, k, 0)
            setattr(player, k, current_value + v)

        session.add(player)

        # 保存 delta 到 extra_attrs 便于卸下时恢复
        extra_old = equip.extra_attrs or {}
        extra_new = {**extra_old, "_persist_bonus": delta}
        equip.extra_attrs = extra_new

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
        await unwear_equipment.finish("⛔ 格式：卸下 装备ID/名称")

    async with safe_session() as session:
        equip = None

        # 尝试按ID查找
        if arg.isdigit():
            equip_id = int(arg)
            equip = await session.get(ItemInstance, equip_id)
            if not equip or equip.player_id != event.get_user_id() or not equip.is_equipment:
                await unwear_equipment.finish("⛔ 无效装备 ID 或非本人所有")
        else:
            # 按名称查找，优先选择已装备的
            item_config = config.items_config["by_name"].get(arg)
            if not item_config or item_config.type.value != "EQUIPMENT":
                await unwear_equipment.finish("⛔ 未找到对应装备名称，或该物品不是装备")

            # 查找玩家所有该名称的已装备装备，按升阶等级降序排列
            from sqlalchemy import select
            stmt = select(ItemInstance).where(
                ItemInstance.player_id == event.get_user_id(),
                ItemInstance.item_id == item_config.item_id,
                ItemInstance.equipped == True
            ).order_by(ItemInstance.upgrade_level.desc())

            equipped_items = (await session.execute(stmt)).scalars().all()
            if not equipped_items:
                await unwear_equipment.finish(f"⛔ 你没有已装备的 {arg}")

            # 选择升阶等级最高的那件
            equip = equipped_items[0]

        # 检查是否已装备
        if not equip.equipped:
            await unwear_equipment.finish("⛔ 该装备未穿戴")

        # 获取玩家信息
        player = await session.get(Player, event.get_user_id())

        # 检查是否为炼丹炉，如果是则处理进行中的炼丹任务
        from ..alchemy.service import AlchemyService
        from ..models.alchemy_task import AlchemyRecord

        furnace_ids = list(AlchemyService.FURNACE_QUALITIES.keys())
        failed_tasks = []
        if equip.item_id in furnace_ids:
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

        furnace_ids = list(AlchemyService.FURNACE_QUALITIES.keys())
        all_failed_tasks = []  # 所有失败的炼丹任务

        unworn_equipment = []  # 记录卸下的装备信息

        # 逐个卸下装备
        for equip in equipped_items:
            # 检查是否为炼丹炉，如果是则处理进行中的炼丹任务
            failed_tasks = []
            if equip.item_id in furnace_ids:
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

        session.add(player)
        await session.commit()

        # 构建结果消息
        result_msg = f"✅ 成功卸下 {len(unworn_equipment)} 件装备：\n" + "、".join(unworn_equipment)

        if all_failed_tasks:
            for task_info in all_failed_tasks:
                result_msg += f"\n🔄 {task_info}"

        await unwear_all_equipment.finish(result_msg)



