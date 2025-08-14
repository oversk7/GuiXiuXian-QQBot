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
elixir_tolerance_cmd = on_command("耐药性", aliases={"丹药耐药性"}, block=True, priority=5)
elixir_bonus_cmd = on_command("丹药加成", aliases={"丹药总加成", "丹药效果"}, block=True, priority=5)
rename_cmd = on_command("改名", block=True, priority=5)
drop_item = on_command("丢弃", aliases={"抛弃", "drop"}, block=True, priority=5)

# ---------------- 背包类别映射 ----------------
# 用户输入 → 内部标识
CATEGORY_MAPPING = {
    "消耗品": "CONSUMABLE",
    "材料": "MATERIAL",
    "商品": "GOODS",
    "装备": "EQUIPMENT",
    "丹药": "ELIXIR",  # 特殊标记，实质为 CONSUMABLE 下的一类
    "鬼怪碎片": "GHOST_FRAGMENT",
}

# 默认展示顺序（决定排序权重）
CATEGORY_ORDER = [
    "CONSUMABLE_NON_ELIXIR",  # 普通消耗品（不含丹药）
    "MATERIAL",
    "GOODS",
    "ELIXIR",                # 丹药（item_id 以 _elixir 结尾）
    "EQUIPMENT",
    "GHOST_FRAGMENT",        # 鬼怪碎片
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

        # ---------------- 丹药使用限制检查 ----------------
        is_elixir = item_config.item_id.endswith("_elixir")
        if is_elixir:
            # 检查每日使用限制
            daily_limit = item_config.daily_limit if item_config.daily_limit > 0 else 999
            usage_stmt = select(ElixirUsageLog).where(
                ElixirUsageLog.player_id == player.id,
                ElixirUsageLog.item_id == item_config.item_id,
                ElixirUsageLog.use_date == date.today(),
            )
            log_row = (await session.execute(usage_stmt)).scalars().first()
            used_today = log_row.quantity if log_row else 0
            if used_today + quantity > daily_limit:
                await use_item.finish(f"⛔ {item_config.name} 每日最多可服用 {daily_limit} 颗，今日已用 {used_today} 颗")

        # 调用统一效果执行器（传递session以支持耐药性）
        success, msg = await apply_effect(player, item_config, quantity, ctx="world", session=session)

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

        # 特殊处理：扫荡令的材料奖励
        if item_config.effect_type == ItemEffectType.SWEEP_DUNGEON and hasattr(player, '_sweep_materials'):
            for material_id, material_quantity in player._sweep_materials:
                try:
                    await ItemInstance.add_item(session, player.id, material_id, material_quantity)
                except ValueError as e:
                    # 如果添加材料失败，记录但不影响主流程
                    pass
            # 清理临时属性
            delattr(player, '_sweep_materials')

        session.add(player)
        await session.commit()

        await use_item.finish(f"✅ 成功使用 {item_name} ✖️{quantity}\n" + msg)


@elixir_tolerance_cmd.handle()
async def handle_elixir_tolerance(event: MessageEvent, args: Message = CommandArg()):
    """查看丹药使用状态"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await elixir_tolerance_cmd.finish("⛔ 请先创建角色")

        # 获取所有丹药的使用记录
        from sqlalchemy import select
        stmt = select(ElixirUsageLog).where(
            ElixirUsageLog.player_id == player.id,
            ElixirUsageLog.use_date == date.today()
        )
        logs = (await session.execute(stmt)).scalars().all()

        if not logs:
            await elixir_tolerance_cmd.finish("📊 今日尚未服用任何丹药")

        # 构建使用状态报告
        lines = ["📊 今日丹药使用状态", "=" * 30]

        for log in logs:
            item_config = config.items_config["by_id"].get(log.item_id)
            if not item_config:
                continue

            # 计算剩余可用次数
            remaining = max(0, item_config.daily_limit - log.quantity)

            # 状态显示
            if remaining > 0:
                status = f"🟢 可用 {remaining} 次"
            else:
                status = "🔴 已达上限"

            lines.append(f"{item_config.name}")
            lines.append(f"  今日使用：{log.quantity}/{item_config.daily_limit}")
            lines.append(f"  状态：{status}")
            lines.append("")

        result = "\n".join(lines)
        await elixir_tolerance_cmd.finish(result)


@elixir_bonus_cmd.handle()
async def handle_elixir_bonus(event: MessageEvent):
    """查看丹药总加成"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await elixir_bonus_cmd.finish("⛔ 请先创建角色")

        # 获取所有丹药使用记录（不限日期，因为丹药效果是永久的）
        from sqlalchemy import select
        stmt = select(ElixirUsageLog).where(ElixirUsageLog.player_id == player.id)
        logs = (await session.execute(stmt)).scalars().all()

        if not logs:
            await elixir_bonus_cmd.finish("📊 你还没有服用过任何丹药")

        # 统计每种丹药的总使用量
        elixir_usage_total = {}
        for log in logs:
            if log.item_id not in elixir_usage_total:
                elixir_usage_total[log.item_id] = 0
            elixir_usage_total[log.item_id] += log.quantity

        # 计算总属性加成
        total_bonus = {
            "max_hp": 0,
            "max_mp": 0,
            "attack": 0,
            "agility": 0,
            "luck": 0,
            "defense": 0
        }

        # 构建详细报告
        lines = ["💊 丹药总加成统计", "=" * 30]

        # 按丹药分类显示
        for item_id, total_qty in elixir_usage_total.items():
            item_config = config.items_config["by_id"].get(item_id)
            if not item_config or item_config.effect_type != ItemEffectType.BUFF:
                continue

            effect_params = item_config.effect_params or {}
            if not effect_params:
                continue

            lines.append(f"🔹 {item_config.name}")
            lines.append(f"  总服用次数：{total_qty}")

            # 计算该丹药的属性加成
            elixir_bonus = []
            for attr, value in effect_params.items():
                if attr in total_bonus:
                    bonus_value = int(value) * total_qty
                    total_bonus[attr] += bonus_value

                    # 属性名称映射
                    attr_names = {
                        "max_hp": "体质",
                        "max_mp": "智力",
                        "attack": "力量",
                        "agility": "敏捷",
                        "luck": "幸运",
                        "defense": "防御"
                    }
                    attr_name = attr_names.get(attr, attr)
                    elixir_bonus.append(f"{attr_name}+{bonus_value}")

            if elixir_bonus:
                lines.append(f"  属性加成：{', '.join(elixir_bonus)}")
            lines.append("")

        # 显示总计
        lines.append("🌟 总计加成")
        lines.append("-" * 20)

        total_display = []
        attr_names = {
            "max_hp": "体质",
            "max_mp": "智力",
            "attack": "力量",
            "agility": "敏捷",
            "luck": "幸运",
            "defense": "防御"
        }

        for attr, total_value in total_bonus.items():
            if total_value > 0:
                attr_name = attr_names.get(attr, attr)
                total_display.append(f"{attr_name}+{total_value}")

        if total_display:
            lines.append(f"✨ {', '.join(total_display)}")
        else:
            lines.append("暂无属性加成")

        result = "\n".join(lines)
        await elixir_bonus_cmd.finish(message_add_head(result, event))


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