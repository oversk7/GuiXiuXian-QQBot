from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select
from datetime import date

from ..config import config
from ..utils import message_add_head
from ..models.db import safe_session
from ..models.player import Player
from ..models.elixir_usage import ElixirUsageLog


def _get_material_obtain_methods(item_id: str, rarity: str) -> str:
    """获取材料的获取方式信息"""
    methods = []

    # 检查是否在市集中出售
    from ..economy.merchants import MARKETS
    market_sellable = any(market.can_sell_to_player(item_id) for market in MARKETS)
    if market_sellable:
        methods.append("市集购买")

    # 检查是否在万事屋中出售
    from ..economy.merchants import SHOP_ITEMS
    if item_id in SHOP_ITEMS:
        methods.append("万事屋购买")

    # 检查诡域材料配置
    map_config = config.map_config
    merchant_tiers = []
    basic_tiers = []

    # 检查动态诡域材料配置
    dungeon_rules = map_config.get("dungeon_generation_rules", {})
    material_tiers = dungeon_rules.get("material_tiers", {})

    for tier_range, materials in material_tiers.items():
        # 检查商人材料
        merchant_materials = materials.get("merchant_materials", [])
        if item_id in merchant_materials:
            merchant_tiers.append(tier_range)

        # 检查基础材料
        basic_materials = materials.get("basic_materials", [])
        if item_id in basic_materials:
            basic_tiers.append(tier_range)

    # 兼容旧区域配置（如果还有的话）
    merchant_regions = []
    basic_regions = []

    for region_name, region_config in map_config.get("regions", {}).items():
        # 跳过大都会等非诡域区域
        if region_name == "大都会":
            continue

        # 检查商人材料
        merchant_materials = region_config.get("merchant_materials", [])
        if item_id in merchant_materials:
            merchant_regions.append(region_name)

        # 检查基础材料
        basic_materials = region_config.get("basic_materials", [])
        if item_id in basic_materials:
            basic_regions.append(region_name)

    # 根据稀有度添加获取方式
    if rarity == "white":
        methods.append("材料格子采集")

        # 优先显示诡域深度信息
        if basic_tiers:
            tiers_str = "、".join(basic_tiers[:3])  # 最多显示3个深度范围
            if len(basic_tiers) > 3:
                tiers_str += "等"
            methods.append(f"诡域探索({tiers_str}重)")
        elif basic_regions:
            regions_str = "、".join(basic_regions[:3])  # 兼容旧区域
            if len(basic_regions) > 3:
                regions_str += "等"
            methods.append(f"探索({regions_str})")

        methods.append("扫荡令扫荡")

    # 战斗掉落说明
    if rarity in ["green", "blue", "purple", "orange"]:
        # 根据稀有度添加具体的掉落说明
        if rarity == "green":
            methods.append("战斗掉落(21级+诡异)")
        elif rarity == "blue":
            methods.append("战斗掉落(61级+诡异)")
        elif rarity == "purple":
            methods.append("战斗掉落(101级+诡异)")
        elif rarity == "orange":
            methods.append("战斗掉落(101级+恐怖诡异)")

        # 扫荡系统也能获得高级材料
        methods.append("扫荡令扫荡(概率获得)")

        # 精英诡异特殊掉落
        methods.append("精英诡异(高概率)")

        # 诡域商人材料
        if merchant_tiers:
            tiers_str = "、".join(merchant_tiers[:3])
            if len(merchant_tiers) > 3:
                tiers_str += "等"
            methods.append(f"诡域商人({tiers_str}重)")
        elif merchant_regions:
            regions_str = "、".join(merchant_regions[:3])
            if len(merchant_regions) > 3:
                regions_str += "等"
            methods.append(f"副本商人({regions_str})")

    return "、".join(methods) if methods else "暂无获取途径"

# 图鉴命令：查询物品、装备和鬼怪的详细信息
catalog_cmd = on_command("图鉴", aliases={"查看","查看物品","详情"}, block=True, priority=5)


@catalog_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """展示物品、装备和鬼怪的名称和描述，可选参数 name 用于关键字过滤"""
    keyword = args.extract_plain_text().strip()

    # 必须提供关键字，否则提醒
    if not keyword:
        await catalog_cmd.finish("⛔ 请提供要查询的名称，例如：图鉴 回春散")

    # 获取玩家信息（用于查询丹药使用状态）
    from ..platform_utils import get_unified_player
    player = None
    elixir_usage_map = {}
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        player = await get_unified_player(session, event)
        if player:
            # 获取今日所有丹药使用记录
            stmt = select(ElixirUsageLog).where(
                ElixirUsageLog.player_id == player.id,
                ElixirUsageLog.use_date == date.today()
            )
            logs = (await session.execute(stmt)).scalars().all()
            elixir_usage_map = {log.item_id: log.quantity for log in logs}

    # 搜索物品
    item_matches = []
    by_id = config.items_config["by_id"]
    # 1. 先尝试精确匹配物品名称
    exact_cfg = config.items_config["by_name"].get(keyword)
    if exact_cfg:
        item_matches.append(exact_cfg)
    else:
        # 2. 子串模糊匹配物品名称或描述
        for cfg in by_id.values():
            if keyword in cfg.name or keyword in cfg.description:
                item_matches.append(cfg)

    # 鬼怪系统已移除，不再搜索鬼怪
    ghost_matches = []

    # 检查是否有匹配结果
    total_matches = len(item_matches)
    if total_matches == 0:
        await catalog_cmd.finish("⛔ 未找到符合条件的物品/装备")

    # 若匹配过多（>6），让用户缩小范围
    if total_matches > 6:
        await catalog_cmd.finish(f"⚠️ 匹配到 {total_matches} 条记录，请输入更精确的名称")

    # 类型映射
    TYPE_NAME_MAP = {
        "CONSUMABLE": "消耗品",
        "MATERIAL": "材料",
        "EQUIPMENT": "装备",
        "GOODS": "商品",
        "GEM": "镶嵌物"
    }

    lines = ["📖 图鉴查询结果 ✨", "━━━━━━━━━━"]

    # 显示物品匹配结果
    for cfg in item_matches:
        type_cn = TYPE_NAME_MAP.get(cfg.type.value, cfg.type.value)

        extra_info = ""
        # 若为装备，附加等级要求、属性加成、稀有度等信息
        if cfg.type.value == "EQUIPMENT":
            ATTR_CN = {
                "attack": "力",
                "defense": "防",
                "agility": "敏",
                "luck": "运",
                "max_hp": "体",
                "max_mp": "智",
                "hp": "体",
                "mp": "智",
            }

            equipment_info = []

            # 等级要求
            if hasattr(cfg, 'required_level'):
                equipment_info.append(f"📊 等级要求：Lv.{cfg.required_level}")

            # 稀有度信息
            rarity_display = cfg.get_rarity_display()
            rarity_map = {
                "white": "普通",
                "green": "优秀",
                "blue": "稀有",
                "purple": "史诗",
                "orange": "传说"
            }
            rarity_name = rarity_map.get(cfg.rarity, cfg.rarity)
            equipment_info.append(f"⭐ 稀有度：{rarity_display}{rarity_name}")

            # 价格信息
            equipment_info.append(f"💰 价值：{cfg.price:,} 金币")

            # 属性加成
            bonus_parts = []
            if cfg.attr_bonus:
                for k, v in cfg.attr_bonus.items():
                    cn = ATTR_CN.get(k, k)
                    bonus_parts.append(f"{cn}+{v}")
            if cfg.attr_ratio:
                for k, v in cfg.attr_ratio.items():
                    if v:
                        cn = ATTR_CN.get(k, k)
                        bonus_parts.append(f"{cn}+{int(v*100)}%")
            if bonus_parts:
                equipment_info.append("🔧 属性加成：" + " 、".join(bonus_parts))

            # 宝石孔位信息
            if hasattr(cfg, 'gem_slots') and cfg.gem_slots > 0:
                equipment_info.append(f"💎 宝石孔位：{cfg.gem_slots}个")

            if equipment_info:
                extra_info = "\n" + "\n".join(equipment_info)

        # 若为材料，展示稀有度、价格、怨念值和获取方式
        elif cfg.type.value == "MATERIAL":
            # 稀有度信息
            rarity_display = cfg.get_rarity_display()
            rarity_map = {
                "white": "普通",
                "green": "优秀",
                "blue": "稀有",
                "purple": "史诗",
                "orange": "传说"
            }
            rarity_name = rarity_map.get(cfg.rarity, cfg.rarity)
            rarity_info = f"⭐ 稀有度：{rarity_display}{rarity_name}"

            grudge_info = f"😈 怨念值：{cfg.grudge_value}" if cfg.grudge_value else ""

            # 获取材料获取方式
            obtain_methods = _get_material_obtain_methods(cfg.item_id, cfg.rarity)
            obtain_info = f"📍 获取方式：{obtain_methods}" if obtain_methods else ""

            extra_info = "\n" + "\n".join(filter(bool, [rarity_info, grudge_info, obtain_info]))

        # 若为丹药，展示每日使用限制和当前状态
        elif cfg.item_id.endswith("_elixir"):
            limit_info = []
            if cfg.daily_limit > 0:
                limit_info.append(f"💊 每日限制：最多可服用 {cfg.daily_limit} 颗")

                # 如果玩家已创建角色，显示今日使用状态
                if player:
                    used_today = elixir_usage_map.get(cfg.item_id, 0)
                    remaining = max(0, cfg.daily_limit - used_today)

                    if remaining > 0:
                        status = f"🟢 今日可用 {remaining} 次"
                    else:
                        status = "🔴 今日已达上限"

                    limit_info.append(f"📊 使用状态：{used_today}/{cfg.daily_limit} ({status})")
                else:
                    limit_info.append("💡 创建角色后可查看使用状态")
            else:
                limit_info.append("💊 每日限制：无限制")

            extra_info = "\n" + "\n".join(limit_info)

        lines.append(f"✨ {cfg.name} ✨  [{type_cn}]\n{cfg.description}{extra_info}")

    await catalog_cmd.finish(message_add_head("\n".join(lines), event))