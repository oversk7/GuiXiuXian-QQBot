from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..models.inventory import ItemType, ItemEffectType
from ..utils import message_add_head, paginate_items
from sqlalchemy import select
from ..config import config
from .item_effects import apply_effect
from datetime import date
from ..models.elixir_usage import ElixirUsageLog
from ..models.navigation_task import NavigationTask
from ..models.guild import Guild

async def _handle_expand_territory(session, player: Player, item_config, quantity: int):
    """处理公会扩张令的特殊逻辑"""
    # 检查玩家是否加入公会
    if not player.guild_id:
        return False, "⛔ 你尚未加入任何公会，无法使用公会扩张令"

    # 获取公会信息
    guild = await session.get(Guild, player.guild_id)
    if not guild:
        return False, "⛔ 公会数据异常"

    # 检查是否为会长
    if guild.president_id != player.id:
        return False, "⛔ 只有会长才能使用公会扩张令"

    # 检查公会是否已设置基地
    if guild.base_x is None or guild.base_y is None:
        return False, "⛔ 公会尚未设置基地，无法扩张势力范围"

    # 扩张势力范围
    expand_value = int(item_config.effect_params.get("value", 1)) * quantity
    old_range = guild.territory_range
    guild.territory_range += expand_value

    # 设置合理的上限
    MAX_TERRITORY_RANGE = 20
    if guild.territory_range > MAX_TERRITORY_RANGE:
        guild.territory_range = MAX_TERRITORY_RANGE
        actual_expand = MAX_TERRITORY_RANGE - old_range
        if actual_expand <= 0:
            return False, f"⛔ 公会势力范围已达到上限({MAX_TERRITORY_RANGE})，无法继续扩张"
        session.add(guild)
        return True, f"🏰 公会势力范围扩张成功！{old_range} → {guild.territory_range} (已达上限)"

    session.add(guild)
    return True, f"🏰 公会势力范围扩张成功！{old_range} → {guild.territory_range}"


inventory_cmd = on_command("背包", block=True, priority=5)
use_item = on_command("使用", block=True, priority=5)

teleport_cmd = on_command("传送", block=True, priority=5)
rename_cmd = on_command("改名", block=True, priority=5)
revive_cmd = on_command("返回", aliases={"复活"}, block=True, priority=5)

drop_item = on_command("丢弃", aliases={"抛弃", "drop"}, block=True, priority=5)

# ---------------- 背包类别映射 ----------------
# 用户输入 → 内部标识
CATEGORY_MAPPING = {
    "消耗品": "CONSUMABLE",
    "材料": "MATERIAL",
    "商品": "GOODS",
    "装备": "EQUIPMENT",
    "丹药": "ELIXIR",  # 特殊标记，实质为 CONSUMABLE 下的一类
}

# 默认展示顺序（决定排序权重）
CATEGORY_ORDER = [
    "CONSUMABLE_NON_ELIXIR",  # 普通消耗品（不含丹药）
    "MATERIAL",
    "GOODS",
    "ELIXIR",                # 丹药（item_id 以 _elixir 结尾）
    "EQUIPMENT",
]

@use_item.handle()
async def handle_use_item(event: MessageEvent, args: Message = CommandArg()):
    params = args.extract_plain_text().strip().split()
    if not params:
        await use_item.finish("⛔ 格式错误，正确格式：使用 [物品名称] [数量]")

    item_name = params[0]
    quantity = 1
    
    if len(params) > 1:
        try:
            quantity = int(params[1])
            if quantity <= 0:
                raise ValueError
        except ValueError:
            await use_item.finish("⛔ 数量必须为正整数")

    async with safe_session() as session:
        # 获取玩家和物品信息
        player = await session.get(Player, event.get_user_id())
        if not player:
            await use_item.finish("⛔ 请先创建角色")

        # 查找物品
        item_config = config.items_config["by_name"].get(item_name)
        if not item_config:
            await use_item.finish(f"⛔ 不存在物品：{item_name}")

        # 检查背包中是否有该物品 (聚合数量)
        inv_rows = (await session.execute(
            select(ItemInstance)
            .where(ItemInstance.player_id == event.get_user_id())
            .where(ItemInstance.item_id == item_config.item_id)
        )).scalars().all()
        total_qty = sum(r.quantity for r in inv_rows)

        if total_qty < quantity:
            await use_item.finish(f"⛔ {item_name} 数量不足")

        # 特殊道具直接跳转对应指令
        if item_config.effect_type == ItemEffectType.CHANGE_NAME:
            await use_item.finish("🪄 请使用指令进行改名：/改名 新名字")
        elif item_config.effect_type == ItemEffectType.TELEPORT:
            await use_item.finish("🪄 请使用指令进行传送：/传送 地点名称")

        # ---------------- 每日丹药使用限制 ----------------
        ELIXIR_DAILY_LIMIT = 5
        is_elixir = item_config.item_id.endswith("_elixir")
        if is_elixir:
            usage_stmt = select(ElixirUsageLog).where(
                ElixirUsageLog.player_id == player.id,
                ElixirUsageLog.item_id == item_config.item_id,
                ElixirUsageLog.use_date == date.today(),
            )
            log_row = (await session.execute(usage_stmt)).scalars().first()
            used_today = log_row.quantity if log_row else 0
            if used_today + quantity > ELIXIR_DAILY_LIMIT:
                await use_item.finish(f"⛔ 每日最多可服用 {ELIXIR_DAILY_LIMIT} 颗丹药，今日已用 {used_today} 颗")

        # 调用统一效果执行器
        success, msg = await apply_effect(player, item_config, quantity, ctx="world")

        # 特殊处理：公会扩张令
        if not success and msg == "EXPAND_TERRITORY_SPECIAL_HANDLING":
            success, msg = await _handle_expand_territory(session, player, item_config, quantity)
            if not success:
                await session.rollback()
                await use_item.finish(msg)

        if not success:
            # 未生效，不扣除物品
            await session.rollback()
            await use_item.finish(msg)

        # 扣除物品数量，优先消耗未满堆叠
        success_consume = await ItemInstance.consume_item(session, player.id, item_config.item_id, quantity)
        if not success_consume:
            await session.rollback()
            await use_item.finish("⛔ 扣除物品失败，请重试")

        session.add(player)

        # 更新使用日志
        if is_elixir:
            if log_row:
                log_row.quantity += quantity
            else:
                session.add(ElixirUsageLog(player_id=player.id, item_id=item_config.item_id, use_date=date.today(), quantity=quantity))

        await session.commit()

        await use_item.finish(f"✅ 成功使用 {item_name} ✖️{quantity}\n" + msg)

@inventory_cmd.handle()
async def handle_inventory(event: MessageEvent, args: Message = CommandArg()):
    # 解析参数：/背包 [类型] [页数]
    params = args.extract_plain_text().strip().split()
    category_key: str | None = None  # 内部标识（CATEGORY_MAPPING 的 value）
    page: int = 1

    if len(params) == 1:
        # 可能是类型或页码
        if params[0] in CATEGORY_MAPPING:
            category_key = CATEGORY_MAPPING[params[0]]
        else:
            try:
                page = int(params[0])
                if page < 1:
                    raise ValueError
            except ValueError:
                await inventory_cmd.finish("⛔ 格式错误，正确格式：背包 [类型] [页数] 或 背包 [页数]")
    elif len(params) == 2:
        # 类型 + 页码
        type_str, page_str = params
        category_key = CATEGORY_MAPPING.get(type_str)
        if not category_key:
            await inventory_cmd.finish(f"⛔ 无效背包类型：{type_str}")
        try:
            page = int(page_str)
            if page < 1:
                raise ValueError
        except ValueError:
            await inventory_cmd.finish("⛔ 页码必须为正整数")
    elif len(params) > 2:
        await inventory_cmd.finish("⛔ 格式错误，正确格式：背包 [类型] [页数]")

    # --- 获取背包数据 ---
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await inventory_cmd.finish("⛔ 请先创建角色")

        result = await session.execute(
            select(ItemInstance)
            .where(ItemInstance.player_id == event.get_user_id())
            .where(ItemInstance.quantity > 0)
        )
        items: list[ItemInstance] = result.scalars().all()

        if not items:
            await inventory_cmd.finish("🎒 你的背包空无一物")

        # ----------- Python 端分类过滤 -----------
        def _is_elixir(inst: ItemInstance) -> bool:
            return inst.config.item_id.endswith("_elixir")

        def _category_id(inst: ItemInstance) -> str:
            if inst.config.type == ItemType.CONSUMABLE:
                return "ELIXIR" if _is_elixir(inst) else "CONSUMABLE_NON_ELIXIR"
            return inst.config.type.value  # MATERIAL / GOODS / EQUIPMENT

        if category_key:
            if category_key == "ELIXIR":
                items = [it for it in items if _is_elixir(it)]
            elif category_key == "CONSUMABLE":
                items = [it for it in items if it.config.type == ItemType.CONSUMABLE and not _is_elixir(it)]
            else:
                items = [it for it in items if it.config.type.value == category_key]

            if not items:
                await inventory_cmd.finish("🎒 该分类下暂无物品")

        # 排序（仅全背包视图按固定顺序）
        if not category_key:
            order_map = {k: i for i, k in enumerate(CATEGORY_ORDER)}
            items.sort(key=lambda it: (order_map.get(_category_id(it), 99), it.config.name))
        else:
            # 指定分类时按名称排序即可
            items.sort(key=lambda it: it.config.name)

        # ---------- 分页 ----------
        page_size = config.game_config["game"]["inventory_page_size"]
        total_pages = (len(items) - 1) // page_size + 1
        page = max(1, min(page, total_pages))

        # 获取容量信息（包含月卡加成）
        effective_capacity = await player.get_effective_inventory_capacity(session)
        used_slots = len(items)
        capacity_info = f"📦 容量：{used_slots}/{effective_capacity}"

        # 如果有月卡加成，显示详细信息
        if effective_capacity > player.inventory_capacity:
            bonus = effective_capacity - player.inventory_capacity
            capacity_info += f" (💳+{bonus})"

        formatted = await paginate_items(items, page, page_size=page_size, capacity_info=capacity_info)
        await inventory_cmd.finish(message_add_head(formatted, event))

@teleport_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    target_region = args.extract_plain_text().strip()
    if not target_region:
        await teleport_cmd.finish("⛔ 请指定目标区域，例如：传送 美少年路口")

    # 验证区域
    valid_regions = list(config.map_config["regions"].keys())
    if target_region not in valid_regions:
        await teleport_cmd.finish("⛔ 目的地不存在，可发送 /诡域 查看全部诡域（副本）")

    STAM_COST = 1  # 咒抗消耗

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await teleport_cmd.finish("⛔ 请先创建角色")

        if player.stamina < STAM_COST:
            await teleport_cmd.finish(f"⛔ 你的咒抗不足以在传送过程中维持清醒，需要 {STAM_COST}，当前 {player.stamina}")

        # 查询是否存在导航任务
        nav_task: NavigationTask | None = await session.get(NavigationTask, player.id)

        # 扣除咒抗并移动
        player.stamina -= STAM_COST
        player.region = target_region
        session.add(player)
        # 若有导航则删除
        if nav_task:
            await session.delete(nav_task)

        await session.commit()

    msg_lines = [
        f"🚪 你耗费 {STAM_COST} 咒抗跨越裂隙，抵达『{target_region}』",
        f"当前位置：{target_region} ({player.x},{player.y})",
    ]
    if nav_task:
        msg_lines.insert(1, "🛑 原导航任务已中断")
    msg = "\n".join(msg_lines)
    await teleport_cmd.finish(message_add_head(msg, event))

@rename_cmd.handle()
async def handle_rename(event: MessageEvent, args: Message = CommandArg()):
    new_name = args.extract_plain_text().strip()
    if not new_name or len(new_name) > 12:
        await rename_cmd.finish("⛔ 名称不能为空且最长12个字符")

    async with safe_session() as session:
        # 获取玩家和改名卡信息
        player = await session.get(Player, event.get_user_id())
        if not player:
            await rename_cmd.finish("⛔ 请先创建角色")

        rename_item = config.items_config["by_name"]["改名卡"]
        inv_result = await session.execute(
            select(ItemInstance)
            .where(ItemInstance.player_id == event.get_user_id())
            .where(ItemInstance.item_id == rename_item.item_id)
        )
        inventory: ItemInstance = inv_result.scalars().first()

        if not inventory or inventory.quantity < 1:
            await rename_cmd.finish("⛔ 改名卡数量不足")

        # 执行改名操作
        inventory.quantity -= 1
        if inventory.quantity <= 0:
            await session.delete(inventory)
        
        player.nickname = new_name
        session.add(player)
        await session.commit()

        await rename_cmd.finish(f"🎉 成功修改角色名为：{new_name}\n"
                               f"剩余改名卡：{inventory.quantity-1 if inventory else 0}张")

@revive_cmd.handle()
async def handle_revive(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await revive_cmd.finish("⛔ 请先创建角色")
        player.hp = player.max_hp
        player.mp = player.max_mp
        player.region = "大都会"
        session.add(player)
        await session.commit()
        msg = (
            "✨ 你从破碎的黑梦中惊醒，踏入『现实世界』。\n"
            "━━━━━━━━━━━━━\n"
            "✧ 生命与理智完全恢复\n"
            "✧ 但你的精神状态可能不太好...\n"
            f"✧ 当前坐标：({player.x},{player.y})\n"
            "━━━━━━━━━━━━━\n"
            "⬇️ 【导航 <x> <y>】劳逸结合，现实经商\n"
            "⬇️ 【传送 <诡域>】这诡何时能杀绝？"

        )

        await revive_cmd.finish(message_add_head(msg, event))

@drop_item.handle()
async def handle_drop_item(event: MessageEvent, args: Message = CommandArg()):
    """丢弃背包中的物品

    用法：丢弃 [物品名称] [数量]
    示例：丢弃 回春散 2
    """
    params = args.extract_plain_text().strip().split()
    if len(params) != 2:
        await drop_item.finish("⛔ 格式错误，正确格式：丢弃 [物品名称] [数量]")

    item_name, qty_str = params
    # 参数校验
    try:
        quantity = int(qty_str)
        if quantity <= 0:
            raise ValueError
    except ValueError:
        await drop_item.finish("⛔ 数量必须为正整数")

    async with safe_session() as session:
        # 获取玩家
        player = await session.get(Player, event.get_user_id())
        if not player:
            await drop_item.finish("⛔ 请先创建角色")

        # 通过名称查找物品模板
        item_cfg = config.items_config["by_name"].get(item_name)
        if not item_cfg:
            await drop_item.finish(f"⛔ 不存在物品：{item_name}")

        try:
            await ItemInstance.consume_item(session, player.id, item_cfg.item_id, quantity)
        except ValueError as e:
            await drop_item.finish(f"⛔ 丢弃失败：{e}")
        await session.commit()

    await drop_item.finish(f"🗑️ 已丢弃 {item_name} ✖️{quantity}")