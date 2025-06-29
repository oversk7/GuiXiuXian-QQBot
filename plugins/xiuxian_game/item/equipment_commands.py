from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from sqlalchemy import select
from ..models.db import safe_session
from ..models import Player, EquipmentInstance
from ..config import config
from ..utils import message_add_head

# ---------------- 指令：装备列表 ----------------
list_equipment = on_command("装备列表", aliases={"装备"}, block=True, priority=5)

@list_equipment.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await list_equipment.finish("⛔ 请先创建角色")

        stmt = select(EquipmentInstance).where(EquipmentInstance.player_id == event.get_user_id())
        equips = (await session.execute(stmt)).scalars().all()

        if not equips:
            await list_equipment.finish("🎒 你的装备栏空空如也")

        lines = ["🎽 𝗘𝗾𝘂𝗶𝗽𝗺𝗲𝗻𝘁", "━━━"]
        for eq in equips:
            tpl = eq.template
            equip_state = "🟢已装备" if eq.equipped else ("🛒在售" if eq.on_market else "🔘未装备")
            lines.append(
                f"🆔{eq.id}│{tpl.name} Dur {eq.durability}/{tpl.durability} {equip_state}"
            )
        await list_equipment.finish(message_add_head("\n".join(lines), event))

# ---------------- 指令：穿戴装备 ----------------
wear_equipment = on_command("穿戴", block=True, priority=5)

@wear_equipment.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    if not arg or not arg.isdigit():
        await wear_equipment.finish("⛔ 格式：穿戴 装备ID（整数）")
    equip_id = int(arg)

    async with safe_session() as session:
        equip = await session.get(EquipmentInstance, equip_id)
        if not equip or equip.player_id != event.get_user_id():
            await wear_equipment.finish("⛔ 无效装备 ID 或非本人所有")

        if equip.equipped:
            await wear_equipment.finish("🧐 该装备已处于穿戴状态")

        if equip.on_market:
            await wear_equipment.finish("❌ 该装备已上架市场，无法穿戴")

        # 暂不区分装备槽，直接将其标记为已穿戴
        equip.equipped = True
        await session.commit()
        await wear_equipment.finish(f"✅ 成功穿戴 {equip.template.name}")

# ---------------- 指令：卸下装备 ----------------
unwear_equipment = on_command("卸下", block=True, priority=5)

@unwear_equipment.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    if not arg or not arg.isdigit():
        await unwear_equipment.finish("⛔ 格式：卸下 装备ID（整数）")
    equip_id = int(arg)

    async with safe_session() as session:
        equip = await session.get(EquipmentInstance, equip_id)
        if not equip or equip.player_id != event.get_user_id():
            await unwear_equipment.finish("⛔ 无效装备 ID 或非本人所有")

        if not equip.equipped:
            await unwear_equipment.finish("🧐 该装备当前未穿戴")

        equip.equipped = False
        await session.commit()
        await unwear_equipment.finish(f"🔻 已卸下 {equip.template.name}") 