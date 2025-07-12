from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from typing import Dict
from sqlalchemy import select
import random
from datetime import datetime, timedelta

from ..config import config
from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..models.equipment import EquipmentInstance
from ..models.alchemy_task import AlchemyTask
from ..utils import message_add_head

# ---------------- 常量 ----------------
# 炉子品质映射：item_id -> (成功率系数, 耐久消耗基数)
_FURNACE_QUALITIES: Dict[str, tuple[float,int]] = {
    "furnace_white": (0.8, 7),   # 成功率×0.8，耐久消耗7
    "furnace_green": (1.0, 5),   # 成功率×1.0
    "furnace_blue":  (1.25, 4),
    "furnace_purple":(1.5, 3),
    "furnace_gold":  (2.0, 2),
}

# ---------------- 工具函数 ----------------

def _get_recipes():
    return config.elixirs_config.get("elixirs", {})


def _format_recipes(page: int = 1, page_size: int = 5) -> str:
    recipes_dict = _get_recipes()
    recipes = list(recipes_dict.values())
    total_pages = (len(recipes)-1)//page_size + 1 if recipes else 1
    page = max(1, min(page, total_pages))
    start = (page-1)*page_size
    end = start+page_size
    current = recipes[start:end]

    lines = ["📜 可用丹方", "━"*10]
    for idx, r in enumerate(current, start=start+1):
        prod_cfg = config.items_config["by_id"][r["produce_item_id"]]
        mats = ", ".join([f"{config.items_config['by_id'][mid].name}✖️{qty}" for mid, qty in r["materials"].items()])
        lines.append(f"{idx}. {prod_cfg.name} (成功率 {int(r['base_success']*100)}%)\n   材料: {mats}")
    lines.append(f"\n页 {page}/{total_pages}")
    return "\n".join(lines)


async def _pickup_furnace(session, player_id: str) -> EquipmentInstance | None:
    stmt = select(EquipmentInstance).where(
        EquipmentInstance.player_id == player_id,
        EquipmentInstance.template_id.in_(_FURNACE_QUALITIES.keys()),
        EquipmentInstance.on_market == False,
    )
    furnaces = (await session.execute(stmt)).scalars().all()
    if not furnaces:
        return None
    # 按品质系数、耐久排序
    furnaces.sort(key=lambda inst: (_FURNACE_QUALITIES[inst.template_id][0], inst.durability), reverse=True)
    return furnaces[0]

# ---------------- 指令 ----------------

recipe_cmd = on_command("丹方", aliases={"炼丹配方"}, block=True, priority=5)
# 格式：炼丹 炉ID 配方序号|名称 [数量]
start_cmd = on_command("炼丹", block=True, priority=5)
status_cmd = on_command("炼丹状态", block=True, priority=5)


@recipe_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    try:
        page = int(arg) if arg else 1
    except ValueError:
        page = 1
    content = _format_recipes(page)
    await recipe_cmd.finish(message_add_head(content, event))


@start_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """炼丹 炉ID 配方序号|名称 [数量]"""
    params = args.extract_plain_text().strip().split()
    if len(params) < 2 or len(params) > 3:
        await start_cmd.finish("⛔ 格式：炼丹 炉ID 配方序号|名称 [数量]")

    # ---- 解析炉子 ID ----
    equip_id_str = params[0]
    if not equip_id_str.isdigit():
        await start_cmd.finish("⛔ 炉ID 必须是数字，可通过背包/装备列表查询")
    equip_id = int(equip_id_str)

    # ---- 配方标识 ----
    target = params[1]

    # ---- 数量解析 ----
    qty = 1
    if len(params) == 3:
        try:
            qty = int(params[2])
            if qty < 1:
                raise ValueError
        except ValueError:
            await start_cmd.finish("⛔ 数量必须为正整数")

    # ---- 解析丹方 ----
    recipes_dict = _get_recipes()
    recipes = list(recipes_dict.values())
    if target.isdigit():
        idx = int(target)
        if idx < 1 or idx > len(recipes):
            await start_cmd.finish("⛔ 无效的丹方序号")
        recipe = recipes[idx-1]
    else:
        recipe = None
        # 先按产物名称匹配
        for r in recipes:
            prod_name = config.items_config["by_id"][r["produce_item_id"]].name
            if prod_name == target:
                recipe = r
                break
        if not recipe:
            # 按 key
            recipe = recipes_dict.get(target)
        if not recipe:
            await start_cmd.finish("⛔ 未找到该丹方")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await start_cmd.finish("⛔ 请先创建角色")

        # --- 获取炉子实例 ----
        furnace_inst = await session.get(EquipmentInstance, equip_id)
        if not furnace_inst or furnace_inst.player_id != player.id:
            await start_cmd.finish("⛔ 未找到对应炼丹炉或非本人所有")
        if furnace_inst.template_id not in _FURNACE_QUALITIES:
            await start_cmd.finish("⛔ 该装备不是炼丹炉，请指定正确的炉子ID")
        if furnace_inst.on_market:
            await start_cmd.finish("⛔ 该炉子已上架交易，无法使用")

        coeff, dura_cost_base = _FURNACE_QUALITIES[furnace_inst.template_id]

        # 获取背包材料信息
        invs = (await session.execute(select(ItemInstance).where(ItemInstance.player_id == player.id))).scalars().all()

        # 检查耐久
        total_dura_need = dura_cost_base * qty
        if furnace_inst.durability < total_dura_need:
            await start_cmd.finish("⛔ 炉子耐久不足，需要 {total_dura_need}，当前 {furnace_inst.durability}")

        # 检查材料
        mats_required = {mid: q*qty for mid,q in recipe["materials"].items()}
        for mid, need in mats_required.items():
            total_have = sum(i.quantity for i in invs if i.item_id == mid)
            if total_have < need:
                name = config.items_config["by_id"][mid].name
                await start_cmd.finish(f"⛔ 材料不足：{name}✖️{need}")

        # 扣材料
        for mid, need in mats_required.items():
            success_consume = await ItemInstance.consume_item(session, player.id, mid, need)
            if not success_consume:
                await session.rollback()
                await start_cmd.finish("⛔ 扣除材料失败")

        # 扣除炉子耐久并检查损坏
        broken = furnace_inst.lose_durability(total_dura_need)
        furnace_note = "（炉子已损坏）" if broken else f"（剩余耐久 {furnace_inst.durability})"
        if broken:
            await session.delete(furnace_inst)

        # 创建定时任务
        success_rate = min(0.95, recipe["base_success"] * coeff)
        base_time_min = 5  # 每炉基础耗时 5 分钟，可配置
        finish_at = datetime.now() + timedelta(minutes=base_time_min * qty)

        task = AlchemyTask(
            player_id=player.id,
            furnace_id=None if broken else furnace_inst.id,
            recipe_key=list(recipes_dict.keys())[recipes.index(recipe)] if isinstance(recipes_dict, dict) else "?",
            qty=qty,
            success_rate=success_rate,
            produce_item_id=recipe["produce_item_id"],
            produce_per=recipe.get("quantity", 1),
            finish_at=finish_at,
        )
        session.add(task)
        await session.commit()

        prod_name = config.items_config["by_id"][recipe["produce_item_id"]].name
        msg = (
            f"🕰️ 炼丹开始：{prod_name} ✖️{qty} 炉\n"
            f"🎯 理论成功率：{int(success_rate*100)}%\n"
            f"⏳ 预计完成时间：{finish_at.strftime('%H:%M:%S')}\n"
            f"🔧 炉子状况 {furnace_note}"
        )
        await start_cmd.finish(message_add_head(msg, event))


@status_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        tasks = (await session.execute(
            select(AlchemyTask).where(AlchemyTask.player_id == event.get_user_id())
        )).scalars().all()

        if not tasks:
            await status_cmd.finish("📭 当前没有炼丹任务")

        lines = ["📋 炼丹任务", "━"*10]
        now = datetime.now()

        for t in tasks:
            prod_cfg = config.items_config["by_id"][t.produce_item_id]
            if not t.delivered and now >= t.finish_at:
                # 结算
                rng = random.Random(t.id)
                success_count = 0
                for _ in range(t.qty):
                    if rng.random() < t.success_rate:
                        success_count += 1
                if success_count:
                    total_qty = success_count * t.produce_per
                    await ItemInstance.add_item(session, t.player_id, t.produce_item_id, total_qty)
                t.delivered = True
                await session.commit()
                result_msg = f"✅ 已完成，成功 {success_count}/{t.qty} 炉，共得 {success_count*t.produce_per} 颗"
            else:
                if t.delivered:
                    result_msg = "✅ 已领取"
                else:
                    remain = int((t.finish_at - now).total_seconds())
                    result_msg = f"⏳ 剩余 {remain//60}分{remain%60}秒"

            lines.append(f"• {prod_cfg.name} ✖️{t.qty} 炉  {result_msg}")

        await status_cmd.finish(message_add_head("\n".join(lines), event)) 