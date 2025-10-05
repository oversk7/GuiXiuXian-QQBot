from __future__ import annotations
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from sqlalchemy import select
from ..models.db import safe_session
from ..models import Player, ItemInstance
from ..models.npc import NPCType
from ..config import config
from ..utils import message_add_head
from .equipment_commands import find_equipment_by_input
from ..world.location_service import LocationService
from ..world.npc_service import NPCService

# ---------------- 指令：锻造列表 ----------------
# 列出所有可锻造装备
list_craft_cmd = on_command("锻造列表", aliases={"装备列表"}, block=True, priority=5, force_whitespace=True)

@list_craft_cmd.handle()
async def _(event: MessageEvent):
    # 位置前置校验：诡域中禁止，但允许远程查看锻造列表（无须贴身靠近工坊）
    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await list_craft_cmd.finish("⛔ 请先创建角色")
        if player.is_in_dungeon():
            await list_craft_cmd.finish(message_add_head("⛔ 诡域中无法进行锻造相关操作", event))
        # 获取本区域内所有拥有锻造功能的城镇
        forge_locs = await LocationService.get_locations_with_function(session, "forge", player.get_current_region())
        if not forge_locs:
            await list_craft_cmd.finish(message_add_head("⛔ 当前区域暂无工坊", event))

        # 反向映射：装备ID -> 可锻造城镇列表
        item_to_cities: dict[str, set[str]] = {}
        for loc in forge_locs:
            forge_cfg = loc.get_function_config("forge") or {}
            allow_ids: list[str] = forge_cfg.get("allow_items", [])
            for iid in allow_ids:
                tpl = config.items_config["by_id"].get(iid)
                if not tpl or not tpl.recipe:
                    continue
                item_to_cities.setdefault(iid, set()).add(loc.name)

    # 汇总所有有配方的装备，并标注“可锻造城镇”
    all_equip_tpls = [tpl for tpl in config.items_config["by_id"].values() if tpl and tpl.recipe]
    # 优先按 required_level 排序（无则视为1），再按名称
    all_equip_tpls.sort(key=lambda t: ((t.required_level or 1), t.name))

    lines = ["🔨 全部装备锻造一览", "━━━━━━━━━━━━━", "💡 用【配方 装备名】查看材料与花费"]
    for tpl in all_equip_tpls:
        cities = sorted(item_to_cities.get(tpl.item_id, []))
        city_text = "、".join(cities) if cities else "—"
        lines.append(f"• {tpl.get_rarity_display()}{tpl.name}({city_text})")

    await list_craft_cmd.finish(message_add_head("\n".join(lines), event))

# ---------------- 指令：工匠配方一览 ----------------
craftsman_recipes_cmd = on_command("工匠配方一览", aliases={"城市锻造", "城市配方"}, block=True, priority=5)

@craftsman_recipes_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    city_name = args.extract_plain_text().strip()
    if not city_name:
        # 显示所有城市列表
        from ..economy.merchants import MARKETS
        city_list = "、".join([m.name for m in MARKETS])
        await craftsman_recipes_cmd.finish(f"⛔ 格式：工匠配方一览 城市名\n💡 可选城市：{city_list}")

    # 查找城市对应的市集配置
    from ..economy.merchants import MARKETS
    target_market = None
    for m in MARKETS:
        if m.name == city_name:
            target_market = m
            break

    if not target_market:
        city_list = "、".join([m.name for m in MARKETS])
        await craftsman_recipes_cmd.finish(f"⛔ 未找到城市：{city_name}\n💡 可选城市：{city_list}")

    async with safe_session() as session:
        # 查找该城市的地点
        location = await LocationService.get_location_by_coordinates(
            session, target_market.x, target_market.y, "大都会"
        )

        if not location or not location.has_function("forge"):
            await craftsman_recipes_cmd.finish(f"⛔ {city_name} 尚未设置工坊")

        forge_cfg = location.get_function_config("forge") or {}
        allow_ids: list[str] = forge_cfg.get("allow_items", [])

        if not allow_ids:
            await craftsman_recipes_cmd.finish(f"⛔ {city_name} 尚未配置锻造列表")

        # 获取工匠名称
        craftsman_name = _get_craftsman_name_by_city(city_name)

        # 构建装备列表
        craftable_items = []
        for iid in allow_ids:
            tpl = config.items_config["by_id"].get(iid)
            if tpl and tpl.recipe:
                # 获取材料信息
                mats = tpl.recipe.get("materials", {})
                if "flesh_crystal" not in mats:
                    mats = {**mats, "flesh_crystal": 1}
                gold_cost = tpl.recipe.get("gold", 0)

                mat_text = " + ".join([f"{config.items_config['by_id'][mid].name}×{qty}"
                                     for mid, qty in mats.items()])

                craftable_items.append({
                    "name": tpl.name,
                    "rarity": tpl.get_rarity_display(),
                    "level": tpl.required_level or 1,
                    "materials": mat_text,
                    "gold": gold_cost
                })

        if not craftable_items:
            await craftsman_recipes_cmd.finish(f"🧐 {city_name} 暂无可锻造装备")

        # 按等级排序
        craftable_items.sort(key=lambda x: x["level"])

        lines = [f"⚒️ {city_name} - {craftsman_name} 锻造配方一览", "━━━━━━━━━━━━━"]
        for item in craftable_items:
            lines.append(f"• {item['rarity']}{item['name']} (Lv.{item['level']})")
            lines.append(f"  材料：{item['materials']}")
            lines.append(f"  金币：{item['gold']}💰")
            lines.append("")

        await craftsman_recipes_cmd.finish(message_add_head("\n".join(lines), event))

def _get_craftsman_name_by_city(city_name: str) -> str:
    """获取城市对应的工匠名称，按主题风格命名"""
    name_map = {
        # 新手区域工匠 - 朴实名字
        "北郊": "打铁张",
        "东郊": "匠人许",
        "西郊": "工匠周",
        "南郊": "匠师南宫",

        # 中级区域工匠 - 主题化名字
        "荔湾镇": "水鬼匠师",  # 水域主题
        "摩配镇": "疯狂技师",  # 都市恐怖主题
        "郸城": "送葬匠人",  # 死亡主题
        "舟山": "时光工匠",  # 时间/记忆主题

        # 高级区域工匠 - 神秘名字
        "云岭": "幽魂锻师",  # 幽灵主题
        "金陵": "心魔巧匠",  # 心理恐怖主题

        # 终极区域工匠 - 传说级名字
        "上京": "百工坊宗师",  # 首都最高级
        "风雪镇": "炼魂大师",  # 特殊地区
    }
    return name_map.get(city_name, f"工匠{city_name}")

# ---------------- 指令：配方查询 ----------------
recipe_cmd = on_command("配方", aliases={"锻造配方"}, block=True, priority=5)

@recipe_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    equip_name = args.extract_plain_text().strip()
    if not equip_name:
        await recipe_cmd.finish("⛔ 格式：配方 装备名称")

    # 前置校验：允许远程查看（诡域内禁止）
    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await recipe_cmd.finish("⛔ 请先创建角色")
        if player.is_in_dungeon():
            await recipe_cmd.finish(message_add_head("⛔ 诡域中无法查看锻造配方", event))

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
craft_cmd = on_command("锻造", aliases={"装备锻造"}, block=True, priority=5, force_whitespace=True)

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
        # 诡域中禁止锻造
        if player.is_in_dungeon():
            await craft_cmd.finish(message_add_head("⛔ 诡域中无法锻造", event))
        # 校验是否在工匠工坊附近（≤3格）
        from ..world.location_service import LocationService
        x, y = player.get_current_coordinates()
        near = await LocationService.get_nearby_locations(session, x, y, player.get_current_region(), max_distance=3)
        forge_locs = [loc for loc in (near or []) if loc.has_function("forge")]
        if not forge_locs:
            await craft_cmd.finish(message_add_head("⛔ 需要在工匠的工坊附近(≤3格)才能锻造\n💡 使用【观察】【NPC列表】寻找工匠", event))

        # 城市锻造白名单校验
        nearest = min(forge_locs, key=lambda loc: abs(loc.x - x) + abs(loc.y - y))
        forge_cfg = nearest.get_function_config("forge") or {}
        allow_ids: list[str] = forge_cfg.get("allow_items", [])
        if allow_ids and item_cfg.item_id not in allow_ids:
            await craft_cmd.finish(message_add_head(
                f"⛔ {nearest.name} 的工匠尚未掌握『{item_cfg.name}』的锻造\n"
                f"💡 发送【锻造列表】查看可锻造城镇", event))

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
        consumed_materials = {}  # 记录已扣除的材料，用于回滚
        for item_id, need_qty in req_materials.items():
            success_consume = await ItemInstance.consume_item(session, player.id, item_id, need_qty)
            if not success_consume:
                await session.rollback()
                await craft_cmd.finish("⛔ 扣除材料失败")
            consumed_materials[item_id] = need_qty
        player.gold -= req_gold

        # 添加装备到背包
        try:
            await ItemInstance.add_item(session, player.id, item_cfg.item_id, quantity=1, durability=item_cfg.durability)
        except ValueError as e:
            # 背包空间不足，恢复金币（材料已通过 rollback 恢复）
            player.gold += req_gold
            await session.rollback()
            await craft_cmd.finish(f"⛔ {e}")

        await session.commit()

        mat_msg = " ".join([f"{config.items_config['by_id'][mid].name}✖️{qty}" for mid, qty in req_materials.items()])
        reply = (
            f"✅ 成功锻造 {item_cfg.name}！\n"
            f"🔨 消耗：{mat_msg} 以及 金币 {req_gold}💰"
        )
        await craft_cmd.finish(message_add_head(reply, event))

repair_cmd = on_command("修复", aliases={"修理"}, block=True, priority=5)

@repair_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    if not arg_text:
        await repair_cmd.finish("⛔ 格式：修理 装备编号/名称 [金币比例:怨念比例]\n💡 示例：修理 白骨护甲 3:2 或 3：2（金币怨念按3:2分配）\n💡 不指定比例则默认使用金币")

    # 解析参数
    parts = arg_text.split()
    equipment_arg = parts[0]
    gold_ratio = None
    resentment_ratio = None

    if len(parts) == 2:
        ratio_text = parts[1]
        # 支持英文冒号和中文冒号
        if ':' in ratio_text or '：' in ratio_text:
            try:
                # 统一替换为英文冒号进行分割
                normalized_ratio = ratio_text.replace('：', ':')
                ratio_parts = normalized_ratio.split(':')
                if len(ratio_parts) != 2:
                    await repair_cmd.finish("⛔ 比例格式错误，应为 金币比例:怨念比例，如 3:2 或 3：2")
                gold_ratio = int(ratio_parts[0])
                resentment_ratio = int(ratio_parts[1])
                if gold_ratio < 0 or resentment_ratio < 0:
                    await repair_cmd.finish("⛔ 比例不能为负数")
                if gold_ratio == 0 and resentment_ratio == 0:
                    await repair_cmd.finish("⛔ 比例不能都为0")
            except ValueError:
                await repair_cmd.finish("⛔ 比例必须是数字，格式如 3:2 或 3：2")
        else:
            await repair_cmd.finish("⛔ 比例格式错误，应为 金币比例:怨念比例，如 3:2 或 3：2")
    elif len(parts) > 2:
        await repair_cmd.finish("⛔ 参数过多，格式：修理 装备编号/名称 [金币比例:怨念比例]")

    async with safe_session() as session:
        # 查找装备
        equip = await find_equipment_by_input(session, event.get_user_id(), equipment_arg)
        if not equip:
            await repair_cmd.finish("⛔ 未找到指定装备，请使用装备栏中显示的编号或装备名称")

        # 如果是按名称查找且有多个同名装备，优先选择耐久度最低的需要修复的装备
        if not equipment_arg.isdigit():
            item_config = config.items_config["by_name"].get(equipment_arg)
            if item_config:
                stmt = select(ItemInstance).where(
                    ItemInstance.player_id == event.get_user_id(),
                    ItemInstance.item_id == item_config.item_id
                ).order_by(ItemInstance.durability.asc())

                all_items = (await session.execute(stmt)).scalars().all()
                # 过滤出需要修复的装备（耐久度未满的）
                repairable_items = [item for item in all_items if item.durability < item.config.durability]

                if repairable_items:
                    equip = repairable_items[0]  # 选择耐久度最低的那件

        tpl = equip.config
        if equip.durability >= tpl.durability:
            await repair_cmd.finish("🧐 该装备耐久已满，无需修复")

        # 计算总费用
        missing = tpl.durability - equip.durability
        cost_per = tpl.repair_cost if tpl.repair_cost is not None else max(1, int(tpl.price / max(1, tpl.durability)))
        total_cost = cost_per * missing

        player = await session.get(Player, event.get_user_id())

        # 如果用户指定了比例
        if gold_ratio is not None and resentment_ratio is not None:
            # 约分比例（求最大公约数）
            def gcd(a, b):
                if b == 0:
                    return a if a > 0 else 1
                while b:
                    a, b = b, a % b
                return a

            common_divisor = gcd(gold_ratio, resentment_ratio)
            if common_divisor > 0:
                gold_ratio //= common_divisor
                resentment_ratio //= common_divisor

            # 按比例计算实际使用的金币和怨念
            total_ratio = gold_ratio + resentment_ratio
            used_gold = (total_cost * gold_ratio) // total_ratio
            used_resentment = total_cost - used_gold  # 剩余部分用怨念

            # 检查玩家是否有足够的资源
            if player.gold < used_gold:
                await repair_cmd.finish(f"⛔ 金币不足，按比例 {gold_ratio}:{resentment_ratio} 需要金币 {used_gold}💰，当前 {player.gold}💰")
            if player.resentment < used_resentment:
                await repair_cmd.finish(f"⛔ 怨念不足，按比例 {gold_ratio}:{resentment_ratio} 需要怨念 {used_resentment}👻，当前 {player.resentment}👻")
        else:
            # 自动分配：默认全部使用金币
            used_gold = total_cost
            used_resentment = 0

            # 检查金币是否足够
            if player.gold < used_gold:
                await repair_cmd.finish(f"⛔ 金币不足，修复费用 {total_cost}💰，当前 {player.gold}💰\n💡 可使用比例分配，如：修理 {equipment_arg} 1:1 或 1：1（金币怨念各一半）")

        # 扣费并修复
        player.gold -= used_gold
        player.resentment -= used_resentment
        equip.durability = tpl.durability
        await session.commit()

        # 显示修复的装备信息，包括ID和修复前后的耐久度
        durability_info = f" (ID:{equip.id}, {equip.durability - missing}→{equip.durability}/{tpl.durability})"

        # 构建费用信息
        cost_info = f"总费用 {total_cost}，实际耗费 {used_gold}💰"
        if used_resentment > 0:
            cost_info += f" + {used_resentment}👻"

        # 如果使用了比例，显示实际比例
        if gold_ratio is not None and resentment_ratio is not None:
            cost_info += f"（按比例 {gold_ratio}:{resentment_ratio}）"
        elif used_resentment == 0:
            cost_info += "（默认使用金币）"

        await repair_cmd.finish(message_add_head(f"🔧 已修复 {tpl.name}{durability_info}，{cost_info}", event))