from __future__ import annotations
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from sqlalchemy import select
from ..models.db import safe_session
from ..models import Player, ItemInstance, EquipmentInstance
from ..config import config
from ..utils import message_add_head

# ---------------- 指令：锻造列表 ----------------
# 列出所有可锻造装备
list_craft_cmd = on_command("锻造列表", aliases={"可锻造", "装备列表"}, block=True, priority=5)

@list_craft_cmd.handle()
async def _(event: MessageEvent):
    craftable = []
    for item_id in config.items_config["by_type"]["EQUIPMENT"]:
        tpl = config.items_config["by_id"].get(item_id)
        if tpl and tpl.recipe:  # 有配方才可锻造
            craftable.append(tpl.name)

    if not craftable:
        await list_craft_cmd.finish("🧐 目前暂无可锻造装备")

    lines = ["🔨 可锻造装备 (发送 /配方 装备名 查看详情)", "━━━━━━━━━"]
    lines.extend([f"• {name}" for name in craftable])
    await list_craft_cmd.finish(message_add_head("\n".join(lines), event))

# ---------------- 指令：配方查询 ----------------
recipe_cmd = on_command("配方", aliases={"锻造配方"}, block=True, priority=5)

@recipe_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    equip_name = args.extract_plain_text().strip()
    if not equip_name:
        await recipe_cmd.finish("⛔ 格式：配方 装备名称")

    item_cfg = config.items_config["by_name"].get(equip_name)
    if not item_cfg or item_cfg.type.value != "EQUIPMENT" or not item_cfg.recipe:
        await recipe_cmd.finish("⛔ 未找到该装备的锻造配方")

    # 整理配方
    mats = item_cfg.recipe.get("materials", {})
    # 强制需要血肉结晶
    if "flesh_crystal" not in mats:
        mats = {**mats, "flesh_crystal": 1}
    gold_cost = item_cfg.recipe.get("gold", 0)

    # -------- 构建材料 -> 地图 映射 --------
    _region_material_map: dict[str, list[str]] = {}
    for _region, _info in config.map_config.get("regions", {}).items():
        for _mat in _info.get("materials", []) or []:
            _region_material_map.setdefault(_mat, []).append(_region)

    mat_lines = []
    for mid, qty in mats.items():
        mat_cfg = config.items_config['by_id'][mid]
        region_note = ""
        if mid in _region_material_map:
            region_note = f"（{ '、'.join(_region_material_map[mid]) } 特产）"
        mat_lines.append(f"{mat_cfg.name}{region_note} ✖️{qty}")

    lines = [f"📝 {item_cfg.name} 锻造配方", "━━━━━━━━━"]
    lines.extend(mat_lines)
    lines.append(f"💰 金币 {gold_cost}")
    await recipe_cmd.finish(message_add_head("\n".join(lines), event))

# ---------------- 指令：装备锻造 ----------------
craft_cmd = on_command("锻造", aliases={"装备锻造"}, block=True, priority=5)

@craft_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    if not arg_text:
        await craft_cmd.finish("⛔ 格式：锻造 装备名称")

    equip_name = arg_text

    # 获取装备模板
    item_cfg = config.items_config["by_name"].get(equip_name)
    if not item_cfg or item_cfg.type.value != "EQUIPMENT":
        await craft_cmd.finish("⛔ 未找到对应装备模板，或该物品不是装备")

    # 检查是否有配方
    if not item_cfg.recipe:
        await craft_cmd.finish("⛔ 该装备尚未配置锻造配方")

    recipe = item_cfg.recipe
    # 基础配方材料
    req_materials: dict = recipe.get("materials", {}).copy()
    # 强制要求血肉结晶至少 1 个
    req_materials["flesh_crystal"] = max(req_materials.get("flesh_crystal", 0), 1)
    req_gold: int = int(recipe.get("gold", 0))

    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await craft_cmd.finish("⛔ 请先创建角色")

        # 金币校验
        if player.gold < req_gold:
            await craft_cmd.finish(f"⛔ 金币不足，需要 {req_gold}💰，当前 {player.gold}💰")

        # 材料校验
        lacking_msgs = []
        for item_id, req_qty in req_materials.items():
            rows = (await session.execute(
                select(ItemInstance).where(ItemInstance.player_id == player.id, ItemInstance.item_id == item_id)
            )).scalars().all()
            have_qty = sum(r.quantity for r in rows)
            if have_qty < req_qty:
                cfg = config.items_config["by_id"].get(item_id)
                name = cfg.name if cfg else item_id
                lacking_msgs.append(f"{name} ✖️{req_qty} (缺{req_qty-have_qty})")
        if lacking_msgs:
            await craft_cmd.finish("⛔ 材料不足：\n" + "\n".join(lacking_msgs))

        # 扣除材料 & 金币
        for item_id, need_qty in req_materials.items():
            success_consume = await ItemInstance.consume_item(session, player.id, item_id, need_qty)
            if not success_consume:
                await session.rollback()
                await craft_cmd.finish("⛔ 扣除材料失败")
        player.gold -= req_gold

        # 创建装备实例
        equip_inst = EquipmentInstance(
            player_id=event.get_user_id(),
            template_id=item_cfg.item_id,
            durability=item_cfg.durability,
        )
        session.add(equip_inst)

        await session.commit()

        mat_msg = " ".join([f"{config.items_config['by_id'][mid].name}✖️{qty}" for mid, qty in req_materials.items()])
        reply = (
            f"✅ 成功锻造 {item_cfg.name}！\n"
            f"🔨 消耗：{mat_msg} 以及 金币 {req_gold}💰"
        )
        await craft_cmd.finish(message_add_head(reply, event))

# ---------------- 指令：装备修复 ----------------
repair_cmd = on_command("修复", aliases={"装备修复"}, block=True, priority=5)

@repair_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    if not arg_text or not arg_text.isdigit():
        await repair_cmd.finish("⛔ 格式：修复 装备ID")
    equip_id = int(arg_text)

    async with safe_session() as session:
        equip = await session.get(EquipmentInstance, equip_id)
        if not equip or equip.player_id != event.get_user_id():
            await repair_cmd.finish("⛔ 无效装备ID或非本人所有")
        tpl = equip.template
        if equip.durability >= tpl.durability:
            await repair_cmd.finish("🧐 该装备耐久已满，无需修复")

        # 计算费用
        missing = tpl.durability - equip.durability
        cost_per = tpl.repair_cost if tpl.repair_cost is not None else max(1, int(tpl.price / max(1, tpl.durability)))
        total_cost = cost_per * missing

        player = await session.get(Player, event.get_user_id())
        if player.gold < total_cost:
            await repair_cmd.finish(f"⛔ 金币不足，修复费用 {total_cost}💰，当前 {player.gold}💰")

        # 扣费并修复
        player.gold -= total_cost
        equip.durability = tpl.durability
        await session.commit()

        await repair_cmd.finish(message_add_head(f"🔧 已修复 {tpl.name}，耗费 {total_cost}💰 (恢复 {missing} 耐久)", event)) 