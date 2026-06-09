from collections import defaultdict
import asyncio

from nonebot import on_command, logger
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..models.inventory import ItemType, ItemEffectType
from ..utils import message_add_head
from ..utils_markdown import cmd, build_markdown
from sqlalchemy import select, func
from ..config import config
from ..queries.inventory_queries import query_inventory_page, query_inventory_usage
from .item_effects import apply_effect
from datetime import date
from ..models.elixir_usage import ElixirUsageLog

from ..models.guild import Guild
from .command_guard import should_silence_unknown_inventory_item

# 导入新效果系统（带Feature Flag）
from ..domain.effects.adapters import apply_effect_with_fallback, USE_NEW_EFFECT_SYSTEM

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


inventory_cmd = on_command("背包", block=True, priority=9, force_whitespace=True)
fish_inventory_cmd = on_command("鱼栏", aliases={"鱼篓", "鱼仓", "鱼库", "我的鱼"}, block=True, priority=9)
use_item = on_command("使用", block=True, priority=9)
elixir_tolerance_cmd = on_command("耐药性", aliases={"丹药耐药性"}, block=True, priority=9)
elixir_bonus_cmd = on_command("丹药加成", aliases={"丹药总加成", "丹药效果"}, block=True, priority=9)
rename_cmd = on_command("改名", block=True, priority=9)
drop_item = on_command("丢弃", aliases={"抛弃", "drop"}, block=True, priority=9)
organize_inventory_cmd = on_command("整理背包", aliases={"整理", "背包整理"}, block=True, priority=9)


# ---------------- 整理背包并发锁 ----------------
_inventory_organize_locks: dict[str, asyncio.Lock] = {}


def _get_inventory_lock(player_id: str) -> asyncio.Lock:
    """获取指定玩家的整理锁，确保同一时间只处理一次整理请求"""

    lock = _inventory_organize_locks.get(player_id)
    if lock is None:
        lock = asyncio.Lock()
        _inventory_organize_locks[player_id] = lock
    return lock

# ---------------- 背包类别映射 ----------------
# 用户输入 → 内部标识
CATEGORY_MAPPING = {
    "消耗品": "CONSUMABLE",
    "材料": "MATERIAL",
    "商品": "GOODS",
    "装备": "EQUIPMENT",
    "丹药": "ELIXIR",  # 特殊标记，实质为 CONSUMABLE 下的一类
    "宝石": "GEM",
    "鱼类": "FISH",
    "礼物": "GIFT",
    "调味品": "SEASONING",
    "调料": "SEASONING",
    "菜肴": "DISH",
    "食谱": "RECIPE",
    "灵蔬": "VEGETABLE",
    "蔬菜": "VEGETABLE",
    "诡药": "HERB",
    "草药": "HERB",
    "灵种": "SEED",
    "种子": "SEED",
    "守护兽": "GUARDIAN_BEAST",
    "诡兽": "GUARDIAN_BEAST",
}

# 物品类型中文映射（用于显示）
TYPE_NAME_MAP = {
    "CONSUMABLE": "消耗品",
    "MATERIAL": "材料",
    "EQUIPMENT": "装备",
    "GOODS": "商品",
    "GEM": "宝石",
    "FISH": "鱼类",
    "GIFT": "礼物",
    "SEASONING": "调味品",
    "DISH": "菜肴",
    "RECIPE": "食谱",
    "VEGETABLE": "灵蔬",
    "HERB": "诡药",
    "SEED": "灵种",
    "GUARDIAN_BEAST": "守护兽",
}

# 分类键名对应的中文（用于翻页导航指令）
CATEGORY_CN_DISPLAY = {
    "CONSUMABLE": "消耗品",
    "MATERIAL": "材料",
    "GOODS": "商品",
    "ELIXIR": "丹药",
    "GEM": "宝石",
    "GIFT": "礼物",
    "SEASONING": "调味品",
    "DISH": "菜肴",
    "RECIPE": "食谱",
    "VEGETABLE": "灵蔬",
    "HERB": "诡药",
    "SEED": "灵种",
    "GUARDIAN_BEAST": "守护兽",
}

# 默认展示顺序（决定排序权重）
CATEGORY_ORDER = [
    "CONSUMABLE_NON_ELIXIR",  # 普通消耗品（不含丹药）
    "MATERIAL",
    "GOODS",
    "GIFT",                  # 礼物
    "SEASONING",             # 调味品
    "DISH",                  # 菜肴
    "RECIPE",                # 食谱
    "VEGETABLE",             # 灵蔬
    "HERB",                  # 诡药
    "SEED",                  # 灵种
    "GUARDIAN_BEAST",        # 守护兽
    "ELIXIR",                # 丹药（item_id 以 _elixir 结尾）
    "GEM",                   # 宝石
    "EQUIPMENT"
]

def _get_item_action_cmd(inst) -> str:
    """根据物品类型返回可点击的蓝字名称，点击后在输入框填入对应指令"""
    cfg = inst.config
    name = cfg.name
    item_type = cfg.type.value
    is_elixir = cfg.item_id.endswith("_elixir")

    if item_type in ("CONSUMABLE", "GOODS", "DISH", "SEASONING", "VEGETABLE", "RECIPE") or is_elixir:
        return cmd(name, f"使用 {name}")
    elif item_type in ("MATERIAL", "HERB", "GHOST_FRAGMENT"):
        return cmd(name, f"献祭 {name}")
    elif item_type in ("GEM", "INSCRIPTION"):
        return cmd(name, f"镶嵌 {name}")
    elif item_type == "SEED":
        return cmd(name, f"种植 {name}")
    elif item_type == "GIFT":
        return cmd(name, f"送礼 {name} ")
    else:
        return name


def _format_inventory_md(
    items: list,
    page: int,
    page_size: int,
    capacity_info: str,
    total_items: int | None = None,
    category_cn: str = "",
) -> str:
    """格式化背包为原生Markdown，物品名称为可点击蓝字"""
    if total_items is not None:
        current_page_items = items
        start = (page - 1) * page_size
        count = total_items
    else:
        start = (page - 1) * page_size
        current_page_items = items[start:start + page_size]
        count = len(items)

    total_pages = max(1, (count - 1) // page_size + 1)

    title = f"# 🎒 背包{'·' + category_cn if category_cn else ''}"
    lines = [title, capacity_info, "***"]

    for offset, inst in enumerate(current_page_items, start=1):
        global_idx = start + offset
        item_link = _get_item_action_cmd(inst)
        lines.append(f"{global_idx}. {item_link} ✖️{inst.quantity}")

    lines.append("***")

    # 翻页导航
    nav_cmd_base = f"背包 {category_cn}" if category_cn else "背包"
    page_nav = []
    if page > 1:
        page_nav.append(cmd("◀上一页", f"{nav_cmd_base} {page - 1}"))
    page_nav.append(f"第**{page}**/{total_pages}页")
    if page < total_pages:
        page_nav.append(cmd("下一页▶", f"{nav_cmd_base} {page + 1}"))
    lines.append("　".join(page_nav))

    lines.append(cmd("背包") + " | " + cmd("整理背包") + " | " + cmd("帮助"))

    return build_markdown("\n".join(lines))


@use_item.handle()
async def handle_use_item(event: MessageEvent, args: Message = CommandArg()):
    params = args.extract_plain_text().strip().split()
    if not params:
        await use_item.finish("⛔ 格式错误，正确格式：使用 [物品名称] [数量]")

    item_name = params[0]
    quantity = 1
    ctx_payload: object = "world"

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import require_player
        player = await require_player(session, event, use_item)

        # 查找物品
        item_config = config.items_config["by_name"].get(item_name)
        if not item_config:
            await use_item.finish(f"⛔ 不存在物品：{item_name}")

        # 先解析使用参数，确保后续校验使用正确的数量
        remaining_args = params[1:]
        if item_config.effect_type == ItemEffectType.DIVINE_PUNISHMENT:
            if not remaining_args:
                await use_item.finish("⛔ 请提供目标UID，例如：使用 天罚符 12345")
            target_uid_str = remaining_args[0]
            if not target_uid_str.isdigit():
                await use_item.finish("⛔ 目标UID必须为正整数")
            ctx_payload = {"scene": "world", "target_uid": int(target_uid_str)}
            quantity = 1
        elif item_config.effect_type == ItemEffectType.SANTA_TELEPORT:
            # 圣诞裂隙：需要提供目标位置
            # 支持两种格式:
            # 1. 坐标: 使用 圣诞裂隙 x y (需要2个参数)
            # 2. 诡域: 使用 圣诞裂隙 N层诡域 (只需要1个参数)
            if len(remaining_args) < 1:
                await use_item.finish("⛔ 请提供目标位置，例如：使用 圣诞裂隙 100 -200 或 使用 圣诞裂隙 5层诡域")
            # 检查是否是诡域传送格式(单个参数包含"层诡域")
            if len(remaining_args) == 1 and "层诡域" not in remaining_args[0]:
                await use_item.finish("⛔ 请提供目标坐标，例如：使用 圣诞裂隙 100 -200 或 使用 圣诞裂隙 5层诡域")
            ctx_payload = {"scene": "world", "target": remaining_args}
            quantity = 1
        elif remaining_args:
            try:
                quantity = int(remaining_args[0])
                if quantity <= 0:
                    raise ValueError
            except ValueError:
                await use_item.finish("⛔ 数量必须为正整数")

        # 检查背包中是否有该物品 (聚合数量)
        inv_rows = (await session.execute(
            select(ItemInstance)
            .where(ItemInstance.player_id == player.id)
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

        # 调用效果执行器（新旧系统自动切换）
        # 根据环境变量 USE_NEW_EFFECT_SYSTEM 选择使用新系统还是旧系统
        if USE_NEW_EFFECT_SYSTEM:
            logger.debug(f"[ItemUse] 使用新效果系统处理: {item_config.name}")
        success, msg = await apply_effect_with_fallback(player, item_config, quantity, ctx=ctx_payload, session=session)

        # 特殊处理：公会扩张令
        if not success and msg == "EXPAND_TERRITORY_SPECIAL_HANDLING":
            success, msg = await _handle_expand_territory(session, player, item_config, quantity)
            if not success:
                await session.rollback()
                await use_item.finish(msg)

        if not success:
            # 未生效，不扣除物品
            await session.rollback()
            # 支持 Markdown 格式的错误消息（如扫荡令装备预检）
            if hasattr(player, '_sweep_use_markdown'):
                delattr(player, '_sweep_use_markdown')
                await use_item.finish(build_markdown(msg))
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
                except ValueError:
                    # 如果添加材料失败，记录但不影响主流程
                    pass
            # 清理临时属性
            delattr(player, '_sweep_materials')

        session.add(player)
        await session.commit()

        # 检查新手任务
        from ..quest.novice_quest_service import NoviceQuestService
        quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(
            session, player, "command", {"command": "使用"}
        )

        # 扫荡令使用 Markdown 富文本发送
        if hasattr(player, '_sweep_use_markdown'):
            delattr(player, '_sweep_use_markdown')
            md_msg = f"✅ 成功使用 **{item_name}** ✖️{quantity}\n\n{msg}"
            if quest_completed and quest_msg:
                md_msg += f"\n\n{quest_msg}"
            await use_item.finish(build_markdown(md_msg))

        result_msg = f"✅ 成功使用 {item_name} ✖️{quantity}\n" + msg
        if quest_completed and quest_msg:
            result_msg += f"\n\n{quest_msg}"

        await use_item.finish(result_msg)


@elixir_tolerance_cmd.handle()
async def handle_elixir_tolerance(event: MessageEvent, args: Message = CommandArg()):
    """查看丹药使用状态"""
    async with safe_session() as session:
        from ..platform_utils import require_player
        player = await require_player(session, event, elixir_tolerance_cmd)

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
        lines = ["# 📊 今日丹药使用状态", "***"]

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

            lines.append(f"💊 **{item_config.name}**")
            lines.append(f"  📈 今日使用：{log.quantity}/{item_config.daily_limit}")
            lines.append(f"  {status}")
            lines.append("")

        lines.append("***")
        lines.append(cmd("丹药加成") + " | " + cmd("背包") + " | " + cmd("帮助"))
        await elixir_tolerance_cmd.finish(build_markdown("\n".join(lines)))


@elixir_bonus_cmd.handle()
async def handle_elixir_bonus(event: MessageEvent):
    """查看丹药总加成"""
    async with safe_session() as session:
        from ..platform_utils import require_player
        player = await require_player(session, event, elixir_bonus_cmd)

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
        lines = ["# 💊 丹药总加成统计", "***"]

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
        lines.append("***")
        lines.append("**🌟 总计加成**")

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

        lines.append("***")
        lines.append(cmd("耐药性") + " | " + cmd("背包") + " | " + cmd("帮助"))
        await elixir_bonus_cmd.finish(build_markdown("\n".join(lines)))


@inventory_cmd.handle()
async def handle_inventory(event: MessageEvent, args: Message = CommandArg()):
    # 解析参数：/背包 [类型/物品名称] [页数]
    params = args.extract_plain_text().strip().split()
    category_key: str | None = None  # 内部标识（CATEGORY_MAPPING 的 value）
    page: int = 1
    query_item_name: str | None = None  # 查询特定物品名称

    if len(params) == 1:
        # 可能是类型、页码或物品名称
        if params[0] in CATEGORY_MAPPING:
            category_key = CATEGORY_MAPPING[params[0]]
        else:
            try:
                page = int(params[0])
                if page < 1:
                    raise ValueError
            except ValueError:
                # 既不是类型也不是页码，当作物品名称处理
                query_item_name = params[0]
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
        await inventory_cmd.finish("⛔ 格式错误，正确格式：背包 [类型/物品名称] [页数]")

    # 装备/鱼类提前拦截（无需查 DB）
    if category_key == "EQUIPMENT":
        await inventory_cmd.finish("⚔️ 装备不在背包中显示\n💡 请使用 /装备栏 查看装备信息")
    if category_key == "FISH":
        await inventory_cmd.finish("🐟 鱼类不再占用背包空间\n💡 请使用 /鱼栏 查看鱼类存量")

    # --- 获取玩家身份 ---
    async with safe_session() as session:
        from ..platform_utils import require_player
        player = await require_player(session, event, inventory_cmd)
        player_id = player.id
        inventory_capacity = player.inventory_capacity
        effective_capacity = await player.get_effective_inventory_capacity(session)

    # --- 处理查询特定物品（SQL SUM） ---
    if query_item_name:
        item_config = config.items_config["by_name"].get(query_item_name)
        if not item_config:
            if should_silence_unknown_inventory_item(event):
                return
            await inventory_cmd.finish(f"⛔ 不存在物品：{query_item_name}")

        if item_config.type == ItemType.EQUIPMENT:
            await inventory_cmd.finish(f"⚔️ {query_item_name} 是装备类物品\n💡 请使用 /装备栏 查看装备信息")
        if item_config.is_fish:
            await inventory_cmd.finish(f"🐟 {query_item_name} 存放在鱼栏中\n💡 请使用 /鱼栏 查看鱼类存量")

        from ..queries import readonly_session as _readonly_session
        async with _readonly_session() as session:
            total_quantity = (await session.execute(
                select(func.sum(ItemInstance.quantity))
                .where(
                    ItemInstance.player_id == player_id,
                    ItemInstance.item_id == item_config.item_id,
                    ItemInstance.quantity > 0,
                )
            )).scalar() or 0

        if total_quantity == 0:
            await inventory_cmd.finish(f"🎒 背包中没有 {query_item_name}")

        type_cn = TYPE_NAME_MAP.get(item_config.type.value, item_config.type.value)
        if item_config.item_id.endswith("_elixir"):
            type_cn = "丹药"

        lines = [
            f"🔍 物品查询结果",
            f"━━━━━━━━━━━━━",
            f"📦 物品名称：{item_config.name}",
            f"🔢 拥有数量：{total_quantity}",
            f"📋 物品类型：{type_cn}",
            f"📝 物品描述：{item_config.description}"
        ]
        await inventory_cmd.finish(message_add_head("\n".join(lines), event))

    # --- 分类查看：DB 层过滤 + 分页 ---
    page_size = config.game_config["game"]["inventory_page_size"]

    if category_key:
        items, total = await query_inventory_page(
            player_id=player_id,
            category=category_key,
            page=page,
            page_size=page_size,
        )
        if not items:
            await inventory_cmd.finish("🎒 该分类下暂无物品")

        used_slots = await query_inventory_usage(player_id)
        capacity_info = f"📦 容量：{used_slots}/{effective_capacity}"
        if effective_capacity > inventory_capacity:
            capacity_info += f" (💳+{effective_capacity - inventory_capacity})"

        # query_inventory_page 已完成 DB 层分页，使用原生Markdown渲染
        cat_cn = CATEGORY_CN_DISPLAY.get(category_key, "")
        await inventory_cmd.finish(_format_inventory_md(items, page, page_size, capacity_info, total_items=total, category_cn=cat_cn))

    # --- 全背包视图：Python 端跨分类排序 ---
    from ..queries import readonly_session as _readonly_session
    async with _readonly_session() as session:
        result = await session.execute(
            select(ItemInstance)
            .where(ItemInstance.player_id == player_id, ItemInstance.quantity > 0)
        )
        all_items: list[ItemInstance] = list(result.scalars().all())

    inventory_items = [item for item in all_items if not item.is_equipment and not item.is_fish and not item.is_inscription]
    if not inventory_items:
        await inventory_cmd.finish("🎒 你的背包空无一物")

    def _is_elixir(inst: ItemInstance) -> bool:
        return inst.config.item_id.endswith("_elixir")

    def _category_id(inst: ItemInstance) -> str:
        if inst.config.type == ItemType.CONSUMABLE:
            return "ELIXIR" if _is_elixir(inst) else "CONSUMABLE_NON_ELIXIR"
        return inst.config.type.value

    order_map = {k: i for i, k in enumerate(CATEGORY_ORDER)}
    inventory_items.sort(key=lambda it: (order_map.get(_category_id(it), 99), it.config.name))

    total_pages = (len(inventory_items) - 1) // page_size + 1
    page = max(1, min(page, total_pages))

    used_slots = len(inventory_items)
    capacity_info = f"📦 容量：{used_slots}/{effective_capacity}"
    if effective_capacity > inventory_capacity:
        capacity_info += f" (💳+{effective_capacity - inventory_capacity})"

    await inventory_cmd.finish(_format_inventory_md(inventory_items, page, page_size, capacity_info))


@fish_inventory_cmd.handle()
async def handle_fish_inventory(event: MessageEvent, args: Message = CommandArg()):
    """查看鱼类存量"""
    params = args.extract_plain_text().strip().split()
    page = 1
    if params:
        if len(params) != 1:
            await fish_inventory_cmd.finish("⛔ 格式错误，正确格式：鱼栏 [页数]")
        try:
            page = int(params[0])
            if page < 1:
                raise ValueError
        except ValueError:
            await fish_inventory_cmd.finish("⛔ 页码必须为正整数")

    async with safe_session() as session:
        from ..platform_utils import require_player

        player = await require_player(session, event, fish_inventory_cmd)

        result = await session.execute(
            select(ItemInstance)
            .where(ItemInstance.player_id == player.id)
            .where(ItemInstance.quantity > 0)
        )
        fish_items = [item for item in result.scalars().all() if item.is_fish]

        if not fish_items:
            await fish_inventory_cmd.finish("🐟 你的鱼栏里一条鱼都没有")

        aggregated: dict[str, int] = defaultdict(int)
        for inst in fish_items:
            aggregated[inst.item_id] += inst.quantity

        entries = []
        total_quantity = 0
        total_value = 0
        rarity_order = {"orange": 0, "purple": 1, "blue": 2, "green": 3, "white": 4}

        for item_id, qty in aggregated.items():
            tpl = config.items_config["by_id"].get(item_id)
            if not tpl:
                continue
            entries.append((tpl, qty))
            total_quantity += qty
            total_value += (tpl.price or 0) * qty

        if not entries:
            await fish_inventory_cmd.finish("🐟 你的鱼栏里一条鱼都没有")

        entries.sort(key=lambda x: (rarity_order.get(getattr(x[0], "rarity", "white"), 99), x[0].name))

        page_size = config.game_config["game"]["inventory_page_size"]
        total_pages = (len(entries) - 1) // page_size + 1
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        current_entries = entries[start:start + page_size]

        lines = [
            "# 🐟 鱼栏存量",
            f"📊 总数量：**{total_quantity}**条　💰 总估值：**{total_value}**金币",
            "***",
        ]

        for idx, (tpl, qty) in enumerate(current_entries, start=start + 1):
            value = (tpl.price or 0) * qty
            lines.append(f"{idx}. {tpl.get_rarity_display()}{tpl.name} ✖️{qty}（估值 {value} 金币）")

        lines.append("***")
        if total_pages > 1:
            lines.append(f"第**{page}**/{total_pages}页")
            nav = []
            if page > 1:
                nav.append(cmd("上一页", f"鱼栏 {page - 1}"))
            if page < total_pages:
                nav.append(cmd("下一页", f"鱼栏 {page + 1}"))
            if nav:
                lines.append(" | ".join(nav))
        lines.append(cmd("鱼栏") + " | " + cmd("背包") + " | " + cmd("帮助"))

        message = "\n".join(lines)
        await fish_inventory_cmd.finish(build_markdown(message))



@rename_cmd.handle()
async def handle_rename(event: MessageEvent, args: Message = CommandArg()):
    new_name = args.extract_plain_text().strip()
    if not new_name or len(new_name) > 12:
        await rename_cmd.finish("⛔ 名称不能为空且最长12个字符")

    # 验证昵称是否合法（违禁词 + 游戏名称检查）
    from ..player.nickname_validator import validate_nickname
    is_valid, error_msg = await validate_nickname(new_name)
    if not is_valid:
        await rename_cmd.finish(f"⛔ {error_msg}")

    async with safe_session() as session:
        # 获取玩家和改名卡信息
        from ..platform_utils import require_player
        player = await require_player(session, event, rename_cmd)

        rename_item = config.items_config["by_name"]["改名卡"]
        inv_result = await session.execute(
            select(ItemInstance)
            .where(ItemInstance.player_id == player.id)
            .where(ItemInstance.item_id == rename_item.item_id)
        )
        inventory: ItemInstance = inv_result.scalars().first()

        if not inventory or inventory.quantity < 1:
            await rename_cmd.finish("⛔ 改名卡数量不足")

        # 执行改名操作
        inventory.quantity -= 1
        remaining = inventory.quantity
        if inventory.quantity <= 0:
            await session.delete(inventory)

        player.nickname = new_name
        session.add(player)
        await session.commit()

        await rename_cmd.finish(f"🎉 成功修改角色名为：{new_name}\n"
                               f"剩余改名卡：{remaining}张")



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
        from ..platform_utils import require_player
        player = await require_player(session, event, drop_item)

        # 通过名称查找物品模板
        item_cfg = config.items_config["by_name"].get(item_name)
        if not item_cfg:
            await drop_item.finish(f"⛔ 不存在物品：{item_name}")

        # 检查是否为鱼类物品
        is_fish = False
        try:
            from ..fishing.service_new import FishingService
            all_fish_ids = []
            for rarity_config in FishingService.FISH_RARITY_CONFIG.values():
                all_fish_ids.extend(rarity_config["fish_list"])
            is_fish = item_cfg.item_id in all_fish_ids
        except ImportError:
            # 如果钓鱼模块不存在，则不是鱼类
            pass

        try:
            await ItemInstance.consume_item(session, player.id, item_cfg.item_id, quantity)
        except ValueError as e:
            await drop_item.finish(f"⛔ 丢弃失败：{e}")
        await session.commit()

    # 根据是否为鱼类显示不同的消息
    if is_fish:
        # 鱼类显示放生消息和功德增加
        if quantity == 1:
            message = f"🐟 你将 {item_name} 放生回了大自然\n✨ 功德 +1"
        else:
            message = f"🐟 你将 {quantity} 条 {item_name} 放生回了大自然\n✨ 功德 +{quantity}"
    else:
        # 普通物品显示丢弃消息
        message = f"🗑️ 已丢弃 {item_name} ✖️{quantity}"

    await drop_item.finish(message)


@organize_inventory_cmd.handle()
async def handle_organize_inventory(event: MessageEvent):
    """整理背包，将同类型可堆叠物品合并"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import require_player
        player = await require_player(session, event, organize_inventory_cmd)

        player_lock = _get_inventory_lock(player.id)
        try:
            await asyncio.wait_for(player_lock.acquire(), timeout=0.1)
        except asyncio.TimeoutError:
            await organize_inventory_cmd.finish("⏳ 正在整理背包，请稍候再试~")

        try:
            # 获取所有背包物品
            result = await session.execute(
                select(ItemInstance)
                .where(ItemInstance.player_id == player.id)
                .where(ItemInstance.quantity > 0)
            )
            all_items: list[ItemInstance] = result.scalars().all()

            # 过滤掉装备、鱼类和铭文，只整理背包物品
            # 铭文每个实例有独立的随机数值(extra_attrs)，不可合并
            items: list[ItemInstance] = [item for item in all_items if not item.is_equipment and not item.is_fish and not item.is_inscription]
            equipment_count = sum(1 for item in all_items if item.is_equipment)
            fish_count = sum(1 for item in all_items if item.is_fish)

            if not items:
                if equipment_count > 0 or fish_count > 0:
                    msg_parts = ["🎒 背包中没有需要整理的物品"]
                    if equipment_count > 0:
                        msg_parts.append(f"⚔️ 装备 {equipment_count} 件（装备不参与整理）")
                    if fish_count > 0:
                        msg_parts.append(f"🐟 鱼类 {fish_count} 种（鱼类存放在鱼栏）")
                    await organize_inventory_cmd.finish("\n".join(msg_parts))
                else:
                    await organize_inventory_cmd.finish("🎒 背包空无一物，无需整理")

            # 统计可堆叠物品
            stackable_items = {}  # item_id -> [ItemInstance, ...]

            for item in items:
                if item.item_id not in stackable_items:
                    stackable_items[item.item_id] = []
                stackable_items[item.item_id].append(item)

            # 检查是否有需要整理的物品
            items_to_organize = []
            for item_id, instances in stackable_items.items():
                if len(instances) > 1:  # 有多个堆叠的同类物品
                    items_to_organize.append((item_id, instances))

            if not items_to_organize:
                await organize_inventory_cmd.finish("✨ 背包已经很整齐了，无需整理")

            # 开始整理
            organized_count = 0
            freed_slots = 0

            try:
                for item_id, instances in items_to_organize:
                    # 计算总数量
                    total_quantity = sum(inst.quantity for inst in instances)

                    # 计算需要的堆叠数
                    from ..models.inventory import STACK_SIZE
                    from math import ceil
                    needed_stacks = ceil(total_quantity / STACK_SIZE)

                    # 删除所有旧的实例
                    for inst in instances:
                        await session.delete(inst)

                    # 创建新的整理后的堆叠
                    remaining_quantity = total_quantity
                    for _ in range(needed_stacks):
                        stack_quantity = min(STACK_SIZE, remaining_quantity)
                        new_instance = ItemInstance(
                            player_id=player.id,
                            item_id=item_id,
                            quantity=stack_quantity
                        )
                        session.add(new_instance)
                        remaining_quantity -= stack_quantity

                    # 统计整理效果
                    original_stacks = len(instances)
                    freed_slots += original_stacks - needed_stacks
                    organized_count += 1

                await session.commit()
            except Exception:
                await session.rollback()
                await organize_inventory_cmd.finish("⛔ 整理背包时发生错误，请重试")

            # 构建结果消息
            result_lines = [
                "🧹 背包整理完成！",
                "━━━━━━━━━━━━━",
                f"📦 整理了 {organized_count} 种物品",
                f"🆓 释放了 {freed_slots} 个背包格子"
            ]

            # 添加装备和鱼类统计
            if equipment_count > 0:
                result_lines.append(f"⚔️ 装备 {equipment_count} 件（装备不参与整理）")
            if fish_count > 0:
                result_lines.append(f"🐟 鱼类 {fish_count} 种（鱼类存放在鱼栏）")

            if freed_slots > 0:
                result_lines.append("✨ 现在背包更加整洁了！")

            result_msg = "\n".join(result_lines)
            await organize_inventory_cmd.finish(message_add_head(result_msg, event))
        finally:
            if player_lock.locked():
                player_lock.release()

# 新增：管理员专用物品转移指令
transfer_item_cmd = on_command("转移物品", block=True, priority=2)

from ..ai_guide import is_admin

@transfer_item_cmd.handle()
async def handle_transfer_item(event: MessageEvent, args: Message = CommandArg()):
    """
    管理员专用：将某玩家背包中的物品转移到另一玩家背包
    用法：转移物品 UID1 UID2 物品名 数量
    """
    from ..models.inventory import ItemInstance

    params = args.extract_plain_text().strip().split()
    if len(params) != 4:
        await transfer_item_cmd.finish("⛔ 格式错误，正确格式：转移物品 UID1 UID2 物品名 数量")

    uid1, uid2, item_name, qty_str = params
    try:
        source_uid = int(uid1)
        target_uid = int(uid2)
        quantity = int(qty_str)
        if quantity <= 0:
            raise ValueError
    except ValueError:
        await transfer_item_cmd.finish("⛔ UID和数量必须为正整数")

    # 权限校验（仅管理员）
    if not is_admin(event.get_user_id()):
        await transfer_item_cmd.finish("⛔ 只有管理员可以使用此指令")

    async with safe_session() as session:
        from ..platform_utils import get_event_server_id

        server_id = await get_event_server_id(session, event)

        # 获取玩家对象
        player1 = (
            await session.execute(
                select(Player).where(Player.uid == source_uid, Player.server_id == server_id)
            )
        ).scalars().first()
        player2 = (
            await session.execute(
                select(Player).where(Player.uid == target_uid, Player.server_id == server_id)
            )
        ).scalars().first()
        if not player1:
            await transfer_item_cmd.finish(f"⛔ 未找到UID为{uid1}的玩家")
        if not player2:
            await transfer_item_cmd.finish(f"⛔ 未找到UID为{uid2}的玩家")
        if player1.server_id != player2.server_id:
            await transfer_item_cmd.finish("⛔ 禁止跨区服转移物品")

        # 查找物品模板
        item_cfg = config.items_config["by_name"].get(item_name)
        if not item_cfg:
            await transfer_item_cmd.finish(f"⛔ 不存在物品：{item_name}")

        # 检查源玩家物品数量
        result = await session.execute(
            select(ItemInstance)
            .where(ItemInstance.player_id == player1.id)
            .where(ItemInstance.item_id == item_cfg.item_id)
        )
        inv_rows = result.scalars().all()
        total_qty = sum(r.quantity for r in inv_rows)
        if total_qty < quantity:
            await transfer_item_cmd.finish(f"⛔ 源玩家背包中{item_name}数量不足（现有{total_qty}）")

        # 扣除源玩家物品
        try:
            await ItemInstance.consume_item(session, player1.id, item_cfg.item_id, quantity)
        except ValueError as e:
            await transfer_item_cmd.finish(f"⛔ 扣除物品失败：{e}")

        # 添加到目标玩家
        try:
            await ItemInstance.add_item(session, player2.id, item_cfg.item_id, quantity)
        except ValueError as e:
            await session.rollback()
            await transfer_item_cmd.finish(f"⛔ 添加物品失败：{e}")

        await session.commit()

    await transfer_item_cmd.finish(f"✅ 已成功将 {item_name} ✖️{quantity} 从 UID:{uid1} 转移到 UID:{uid2}")
