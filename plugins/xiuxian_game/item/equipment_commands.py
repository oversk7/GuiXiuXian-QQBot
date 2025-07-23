from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from sqlalchemy import select
from ..models.db import safe_session
from ..models import Player, ItemInstance
from ..config import config
from ..utils import message_add_head
import random

# 最多可装备数量（可调整或改为读取配置）
MAX_EQUIPPED = 4  # TODO: 后续可写入 config.game_config
EQUIP_ITEM_IDS = config.items_config["by_type"]["EQUIPMENT"]

# ---------------- 指令：装备列表 ----------------
list_equipment = on_command("我的装备", aliases={"装备栏"}, block=True, priority=5)

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
            lines.append(
                f"🆔{eq.id}│{tpl.name} 🛠️ {eq.durability}/{tpl.durability} {equip_state}"
            )
        await list_equipment.finish(message_add_head("\n".join(lines), event))

# ---------------- 指令：穿戴装备 ----------------
wear_equipment = on_command("穿戴", aliases={"携带","装备"}, block=True, priority=5)

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
            if not equip or equip.player_id != event.get_user_id() or equip.config.type.value != "EQUIPMENT":
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
                await wear_equipment.finish(f"⛔ 你没有未穿戴的 {arg}")

            # 选择耐久度最高的那件
            equip = unequipped_items[0]

        if equip.equipped:
            await wear_equipment.finish("🧐 该装备已处于穿戴状态")

        # ----- 上限检查 -----
        cur_equipped = (await session.execute(
            select(ItemInstance).where(
                ItemInstance.player_id == event.get_user_id(),
                ItemInstance.equipped == True,
                ItemInstance.item_id.in_(EQUIP_ITEM_IDS)
            )
        )).scalars().all()
        if len(cur_equipped) >= MAX_EQUIPPED:
            await wear_equipment.finish(f"⛔ 你已穿戴 {len(cur_equipped)} 件装备，已达到上限 ({MAX_EQUIPPED})，请先卸下一件后再穿戴")

        # ----- 同名装备检查 -----
        # 检查是否已经穿戴了同名装备
        equip_name = equip.config.name
        for equipped_item in cur_equipped:
            if equipped_item.config.name == equip_name:
                await wear_equipment.finish(f"⛔ 你已经穿戴了 {equip_name}，同一名称的装备不能重复穿戴")

        # 计算并持久化属性增量
        player = await session.get(Player, event.get_user_id())

        # 记录穿戴前是否满血满蓝
        was_hp_full = player.hp >= player.max_hp
        was_mp_full = player.mp >= player.max_mp

        # 先标记为已装备，以便 apply_attr_bonus 生效
        equip.equipped = True

        base_attrs = {
            "attack": player.attack,
            "defense": player.defense,
            "agility": player.agility,
            "luck": player.luck,
            "max_hp": player.max_hp,
            "max_mp": player.max_mp,
        }
        new_attrs = base_attrs.copy()
        equip.apply_attr_bonus(new_attrs)
        delta = {k: new_attrs[k] - base_attrs[k] for k in new_attrs if new_attrs[k] != base_attrs[k]}

        # 应用到玩家本体
        for k, v in delta.items():
            setattr(player, k, getattr(player, k) + v)

        # 如果穿戴前是满血满蓝，穿戴后也应该保持满状态
        if was_hp_full and "max_hp" in delta:
            player.hp = player.max_hp
        if was_mp_full and "max_mp" in delta:
            player.mp = player.max_mp

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
            if not equip or equip.player_id != event.get_user_id() or equip.config.type.value != "EQUIPMENT":
                await unwear_equipment.finish("⛔ 无效装备 ID 或非本人所有")
        else:
            # 按名称查找，优先选择耐久度最低的已装备装备
            from ..config import config
            item_config = config.items_config["by_name"].get(arg)
            if not item_config or item_config.type.value != "EQUIPMENT":
                await unwear_equipment.finish("⛔ 未找到对应装备名称，或该物品不是装备")

            # 查找玩家所有该名称的已装备装备，按耐久度升序排列
            stmt = select(ItemInstance).where(
                ItemInstance.player_id == event.get_user_id(),
                ItemInstance.item_id == item_config.item_id,
                ItemInstance.equipped == True
            ).order_by(ItemInstance.durability.asc())

            equipped_items = (await session.execute(stmt)).scalars().all()
            if not equipped_items:
                await unwear_equipment.finish(f"⛔ 你没有穿戴任何 {arg}")

            # 选择耐久度最低的那件
            equip = equipped_items[0]

        if not equip.equipped:
            await unwear_equipment.finish("🧐 该装备当前未穿戴")

        # 检查是否为炼丹炉，如果是则处理进行中的炼丹任务
        from ..alchemy.service import AlchemyService
        from ..models.alchemy_task import AlchemyRecord

        furnace_ids = list(AlchemyService.FURNACE_QUALITIES.keys())
        failed_tasks = []  # 初始化失败任务列表

        if equip.item_id in furnace_ids:
            # 查找使用该炼丹炉的进行中任务
            from sqlalchemy import select, and_
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
                    materials_dict = record.get_materials_dict()
                    returned_materials = []

                    for material_id, total_used in materials_dict.items():
                        try:
                            await ItemInstance.add_item(session, record.player_id, material_id, total_used)
                            from ..config import config
                            material_name = config.items_config["by_id"][material_id].name
                            returned_materials.append(f"{material_name}✖️{total_used}")
                        except ValueError:
                            # 如果添加失败，忽略该材料的返还
                            pass

                    # 删除失败的炼丹记录
                    await session.delete(record)

                    if returned_materials:
                        failed_tasks.append(f"返还材料：{', '.join(returned_materials)}")
                    else:
                        failed_tasks.append("炼丹任务已取消")

        # 恢复玩家属性
        player = await session.get(Player, event.get_user_id())
        delta = (equip.extra_attrs or {}).get("_persist_bonus", {})
        for k, v in delta.items():
            setattr(player, k, getattr(player, k) - v)

        # 修正生命/理智不超过新上限
        if player.hp > player.max_hp:
            player.hp = player.max_hp
        if player.mp > player.max_mp:
            player.mp = player.max_mp

        # 清除持久化记录并标记未穿戴
        if "_persist_bonus" in (equip.extra_attrs or {}):
            extra_new = {k: v for k, v in equip.extra_attrs.items() if k != "_persist_bonus"}
            equip.extra_attrs = extra_new

        equip.equipped = False
        await session.commit()

        # 显示卸下的装备信息，包括ID和耐久度
        durability_info = f" (ID:{equip.id}, 耐久:{equip.durability}/{equip.config.durability})"
        result_msg = f"🔻 已卸下 {equip.config.name}{durability_info}"

        # 如果是炼丹炉且有失败的任务，添加相关信息
        if equip.item_id in furnace_ids and failed_tasks:
            result_msg += f"\n⚠️ 炼丹炉被卸下，{len(failed_tasks)}个进行中的炼丹任务已取消："
            for task_info in failed_tasks:
                result_msg += f"\n🔄 {task_info}"

        await unwear_equipment.finish(result_msg)

# ---------------- 指令：装备分解 ----------------
decompose_equipment = on_command("分解", aliases={"装备分解"}, block=True, priority=5)

@decompose_equipment.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    if not arg:
        await decompose_equipment.finish("⛔ 格式：分解 装备ID/名称")

    async with safe_session() as session:
        equip = None

        # 尝试按ID查找
        if arg.isdigit():
            equip_id = int(arg)
            equip = await session.get(ItemInstance, equip_id)
            if not equip or equip.player_id != event.get_user_id() or not equip.is_equipment:
                await decompose_equipment.finish("⛔ 无效装备 ID 或非本人所有")
        else:
            # 按名称查找，优先选择耐久度最低的未装备装备
            item_config = config.items_config["by_name"].get(arg)
            if not item_config or item_config.type.value != "EQUIPMENT":
                await decompose_equipment.finish("⛔ 未找到对应装备名称，或该物品不是装备")

            # 查找玩家所有该名称的未装备装备，按耐久度升序排列
            stmt = select(ItemInstance).where(
                ItemInstance.player_id == event.get_user_id(),
                ItemInstance.item_id == item_config.item_id,
                ItemInstance.equipped == False
            ).order_by(ItemInstance.durability.asc())

            unequipped_items = (await session.execute(stmt)).scalars().all()
            if not unequipped_items:
                await decompose_equipment.finish(f"⛔ 你没有未装备的 {arg}")

            # 选择耐久度最低的那件
            equip = unequipped_items[0]

        # 检查是否已装备
        if equip.equipped:
            await decompose_equipment.finish("⛔ 请先卸下装备再进行分解")

        # 获取玩家信息
        player = await session.get(Player, event.get_user_id())

        # 检查装备是否有配方
        recipe_materials = {}
        if equip.config.recipe:
            recipe_materials = equip.config.recipe.get("materials", {})

        # 计算耐久度比例，用于损失率计算
        durability_ratio = equip.durability / equip.config.durability if equip.config.durability > 0 else 0
        base_loss_rate = 0.4  # 基础损失率40%
        durability_bonus = durability_ratio * 0.2  # 耐久度越高，损失越少，最多减少20%损失
        final_loss_rate = max(0.2, base_loss_rate - durability_bonus)  # 最少损失20%

        decompose_results = []

        if recipe_materials:
            # 有配方的装备：分解获得材料
            materials_to_add = []

            # 先计算所有要获得的材料，不立即添加到背包
            for material_id, original_qty in recipe_materials.items():
                # 计算实际获得数量（有随机性）
                min_gain = max(1, int(original_qty * (1 - final_loss_rate) * 0.8))
                max_gain = max(1, int(original_qty * (1 - final_loss_rate) * 1.2))
                gained_qty = random.randint(min_gain, max_gain)

                if gained_qty > 0:
                    materials_to_add.append((material_id, gained_qty))

            # 尝试添加所有材料到背包（事务性操作）
            for material_id, gained_qty in materials_to_add:
                try:
                    await ItemInstance.add_item(session, event.get_user_id(), material_id, gained_qty)
                    material_config = config.items_config["by_id"].get(material_id)
                    material_name = material_config.name if material_config else material_id
                    decompose_results.append(f"{material_name} ✖️{gained_qty}")
                except ValueError as e:
                    # 如果背包空间不足，回滚事务
                    await session.rollback()
                    await decompose_equipment.finish(f"⛔ 背包空间不足：{e}")
        else:
            # 没有配方的装备：分解获得金币
            # 基础金币 = 装备价格 * 耐久度比例 * (1 - 损失率) * 随机系数
            base_gold = int(equip.config.price * durability_ratio * (1 - final_loss_rate))
            # 添加随机性 ±20%
            min_gold = max(1, int(base_gold * 0.8))
            max_gold = max(1, int(base_gold * 1.2))
            gained_gold = random.randint(min_gold, max_gold)

            # 添加金币
            player.gold += gained_gold
            decompose_results.append(f"金币 ✖️{gained_gold}")

        # 删除装备
        await session.delete(equip)
        await session.commit()

        # 构建结果消息
        durability_info = f"耐久:{equip.durability}/{equip.config.durability}"
        loss_rate_display = f"{final_loss_rate:.0%}"

        if recipe_materials:
            # 有配方的装备分解结果
            if decompose_results:
                materials_msg = "、".join(decompose_results)
                result_msg = (
                    f"🔨 成功分解 {equip.config.name} (ID:{equip.id}, {durability_info})\n"
                    f"📦 获得材料：{materials_msg}\n"
                    f"💔 材料损失率：{loss_rate_display}"
                )
            else:
                result_msg = f"🔨 分解了 {equip.config.name}，但没有获得任何材料"
        else:
            # 没有配方的装备分解结果
            if decompose_results:
                gold_msg = "、".join(decompose_results)
                result_msg = (
                    f"🔨 成功分解 {equip.config.name} (ID:{equip.id}, {durability_info})\n"
                    f"� 获得：{gold_msg}\n"
                    f"💔 回收损失率：{loss_rate_display}"
                )
            else:
                result_msg = f"🔨 分解了 {equip.config.name}，但没有获得任何金币"

        await decompose_equipment.finish(message_add_head(result_msg, event))