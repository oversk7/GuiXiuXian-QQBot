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
    from ..economy.merchants import goods_ids
    if item_id in goods_ids:
        methods.append("市集购买")

    # 检查是否在万事屋中出售
    from ..economy.merchants import SHOP_ITEMS
    if item_id in SHOP_ITEMS:
        methods.append("万事屋购买")

    # 检查区域信息
    map_config = config.map_config
    merchant_regions = []
    basic_regions = []

    for region_name, region_config in map_config.get("regions", {}).items():
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
        if basic_regions:
            regions_str = "、".join(basic_regions[:3])  # 最多显示3个区域
            if len(basic_regions) > 3:
                regions_str += "等"
            methods.append(f"探索({regions_str})")

    if rarity in ["green", "blue", "purple", "orange"]:
        methods.append("战斗掉落")
        if merchant_regions:
            regions_str = "、".join(merchant_regions[:3])
            if len(merchant_regions) > 3:
                regions_str += "等"
            methods.append(f"副本商人({regions_str})")

    # 根据稀有度添加通用获取方式
    if rarity in ["green", "blue"]:
        methods.append("中高级怪物掉落")
    elif rarity in ["purple", "orange"]:
        methods.append("高级/顶级怪物掉落")

    # 扫荡令获取（主要是基础材料）
    if rarity == "white":
        methods.append("扫荡令扫荡")

    return "、".join(methods) if methods else "暂无获取途径"

# 图鉴命令：查询物品、装备和鬼怪的详细信息
catalog_cmd = on_command("图鉴", aliases={"查看","查看物品","详情"}, block=True, priority=5)


@catalog_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """展示物品、装备和鬼怪的名称和描述，可选参数 name 用于关键字过滤"""
    keyword = args.extract_plain_text().strip()

    # 必须提供关键字，否则提醒
    if not keyword:
        await catalog_cmd.finish("⛔ 请提供要查询的名称，例如：图鉴 回春散 或 图鉴 贞子")

    # 获取玩家信息（用于查询丹药使用状态）
    player = None
    elixir_usage_map = {}
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
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

    # 搜索鬼怪
    ghost_matches = []
    for ghost_config in config.ghosts_config["all"]:
        if (keyword in ghost_config.get("name", "") or
            keyword in ghost_config.get("description", "") or
            keyword == ghost_config.get("ghost_id", "")):
            ghost_matches.append(ghost_config)

    # 如果找到了鬼怪匹配，则从物品匹配中移除对应的鬼怪碎片
    if ghost_matches:
        ghost_fragment_ids = set()
        for ghost_config in ghost_matches:
            fragment_id = ghost_config.get("fragment_item_id", "")
            if fragment_id:
                ghost_fragment_ids.add(fragment_id)

        # 过滤掉鬼怪碎片
        item_matches = [cfg for cfg in item_matches if cfg.item_id not in ghost_fragment_ids]

    # 检查是否有匹配结果
    total_matches = len(item_matches) + len(ghost_matches)
    if total_matches == 0:
        await catalog_cmd.finish("⛔ 未找到符合条件的物品/装备/鬼怪")

    # 若匹配过多（>6），让用户缩小范围
    if total_matches > 6:
        await catalog_cmd.finish(f"⚠️ 匹配到 {total_matches} 条记录，请输入更精确的名称")

    # 类型映射
    TYPE_NAME_MAP = {
        "CONSUMABLE": "消耗品",
        "MATERIAL": "材料",
        "EQUIPMENT": "装备",
        "GOODS": "商品",
        "GHOST_FRAGMENT": "鬼怪投影"
    }

    lines = ["📖 图鉴查询结果 ✨", "━━━━━━━━━━"]

    # 显示物品匹配结果
    for cfg in item_matches:
        type_cn = TYPE_NAME_MAP.get(cfg.type.value, cfg.type.value)

        extra_info = ""
        # 若为装备，附加属性加成信息
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
                extra_info = "\n🔧 属性加成：" + " 、".join(bonus_parts)

        # 若为材料，展示价格、怨念值和获取方式
        elif cfg.type.value == "MATERIAL":
            grudge_info = f"😈 怨念值：{cfg.grudge_value}" if cfg.grudge_value else ""

            # 获取材料获取方式
            obtain_methods = _get_material_obtain_methods(cfg.item_id, cfg.rarity)
            obtain_info = f"📍 获取方式：{obtain_methods}" if obtain_methods else ""

            extra_info = "\n" + "\n".join(filter(bool, [grudge_info, obtain_info]))

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

        lines.append(f"✨ {cfg.name} ✨  [{type_cn}]\n{cfg.description}{extra_info}\n")

    # 显示鬼怪匹配结果
    for ghost_config in ghost_matches:
        name = ghost_config.get("name", "未知鬼怪")
        description = ghost_config.get("description", "暂无描述")

        # 鬼怪属性信息
        hp = ghost_config.get("hp", 0)
        attack = ghost_config.get("attack", 0)
        defense = ghost_config.get("defense", 0)
        agility = ghost_config.get("agility", 0)
        prestige_level = ghost_config.get("base_prestige_level", 1)
        rarity = ghost_config.get("rarity", "common")

        # 稀有度映射
        rarity_map = {
            "common": "普通",
            "rare": "稀有",
            "epic": "史诗",
            "legendary": "传说"
        }
        rarity_cn = rarity_map.get(rarity, rarity)

        # 合成信息
        fragment_id = ghost_config.get("fragment_item_id", "")
        fragments_needed = ghost_config.get("fragments_to_complete", 0)
        fragment_config = config.items_config["by_id"].get(fragment_id)
        fragment_name = fragment_config.name if fragment_config else "未知碎片"

        extra_info = (
            f"\n👻 属性：体{hp} 力{attack} 防{defense} 敏{agility}"
            f"\n🔥 基础威压：{prestige_level}  ⭐ 稀有度：{rarity_cn}"
            f"\n🧩 合成需要：{fragment_name} x{fragments_needed}"
        )

        lines.append(f"👻 {name} 👻  [鬼怪]\n{description}{extra_info}\n")

    await catalog_cmd.finish(message_add_head("\n".join(lines), event))