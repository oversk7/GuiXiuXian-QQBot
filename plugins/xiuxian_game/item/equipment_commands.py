from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from sqlalchemy import select
from ..models.db import safe_session
from ..models import Player, ItemInstance
from ..config import config
from ..utils import message_add_head

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

        # 计算并持久化属性增量
        player = await session.get(Player, event.get_user_id())

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
        await unwear_equipment.finish(f"🔻 已卸下 {equip.config.name}{durability_info}")