from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams
from nonebot.params import CommandArg
from sqlalchemy import select
from datetime import date
import yaml
from pathlib import Path
import aiohttp
import asyncio
from io import BytesIO
from PIL import Image

from ..config import config
from ..utils import message_add_head
from ..models.db import safe_session
from ..models.player import Player
from ..models.elixir_usage import ElixirUsageLog


def _get_material_obtain_methods(item_id: str, rarity: str) -> str:
    """获取材料的获取方式信息"""

    def _format_scope(tiers: list[str], regions: list[str]) -> str:
        """格式化展示诡域范围或旧区域信息"""
        # 去重但保持顺序
        unique_tiers = list(dict.fromkeys(tiers))
        unique_regions = list(dict.fromkeys(regions))

        if unique_tiers:
            display = "、".join(unique_tiers[:3])
            if len(unique_tiers) > 3:
                display += "等"
            return f"{display}重诡域"

        if unique_regions:
            display = "、".join(unique_regions[:3])
            if len(unique_regions) > 3:
                display += "等"
            return display

        return ""

    def _append_scope(methods_list: list[str], label: str, tiers: list[str], regions: list[str]):
        scope = _format_scope(tiers, regions)
        if scope:
            methods_list.append(f"{label}（{scope}）")
        else:
            methods_list.append(label)

    methods: list[str] = []

    # 检查是否在市集中出售
    from ..economy.merchants import MARKETS

    if any(market.can_sell_to_player(item_id) for market in MARKETS):
        methods.append("市集购买")

    # 检查是否在万事屋中出售
    from ..economy.merchants import SHOP_ITEMS

    if item_id in SHOP_ITEMS:
        methods.append("万事屋购买")

    # 检查诡域材料配置
    map_config = config.map_config
    merchant_tiers: list[str] = []
    basic_tiers: list[str] = []

    # 检查动态诡域材料配置
    dungeon_rules = map_config.get("dungeon_generation_rules", {})
    material_tiers = dungeon_rules.get("material_tiers", {})

    for tier_range, materials in material_tiers.items():
        merchant_materials = materials.get("merchant_materials", [])
        if item_id in merchant_materials:
            merchant_tiers.append(tier_range)

        basic_materials = materials.get("basic_materials", [])
        if item_id in basic_materials:
            basic_tiers.append(tier_range)

    # 兼容旧区域配置（如果还有的话）
    merchant_regions: list[str] = []
    basic_regions: list[str] = []

    for region_name, region_config in map_config.get("regions", {}).items():
        # 跳过大都会等非诡域区域
        if region_name == "大都会":
            continue

        merchant_materials = region_config.get("merchant_materials", [])
        if item_id in merchant_materials:
            merchant_regions.append(region_name)

        basic_materials = region_config.get("basic_materials", [])
        if item_id in basic_materials:
            basic_regions.append(region_name)

    has_basic_scope = bool(basic_tiers or basic_regions)
    has_merchant_scope = bool(merchant_tiers or merchant_regions)

    # 根据稀有度添加获取方式
    if rarity == "white":
        _append_scope(methods, "材料格子采集", basic_tiers, basic_regions)

        if has_basic_scope:
            _append_scope(methods, "扫荡令扫荡（材料格子）", basic_tiers, basic_regions)

        # 白色材料亦可能来自战斗掉落
        methods.append("诡异战斗掉落（概率）")

    else:
        # 战斗掉落说明：怪物等级越高，稀有材料出现概率越高
        methods.append("诡异战斗掉落（怪物等级越高掉落率越高）")

        # 扫荡令仅在对应诡域中有高阶材料配置时才能掉落
        if has_merchant_scope:
            _append_scope(methods, "扫荡令扫荡（概率获得）", merchant_tiers, merchant_regions)

        # 精英诡异有更高掉落概率
        methods.append("精英诡异战斗（更高概率）")

    # 诡域商人售卖范围
    if has_merchant_scope:
        _append_scope(methods, "诡域商人售卖", merchant_tiers, merchant_regions)

    return "\n".join(f"• {method}" for method in methods) if methods else "暂无获取途径"


def _load_item_images() -> dict:
    """加载物品图片配置

    Returns:
        物品ID到图片URL的映射字典
    """
    config_path = Path(__file__).parent.parent.parent.parent / "data" / "item_images.yaml"

    if not config_path.exists():
        return {}

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return data if data else {}
    except Exception as e:
        print(f"加载物品图片配置失败: {e}")
        return {}


def _get_item_image_url(item_id: str) -> str:
    """获取物品图片URL

    Args:
        item_id: 物品ID

    Returns:
        图片URL，如果没有配置则返回空字符串
    """
    images = _load_item_images()
    return images.get(item_id, "")


def _load_image_dimensions_cache() -> dict:
    """加载图片尺寸缓存

    Returns:
        物品ID到图片信息的映射字典 {item_id: {"url": "...", "width": 300, "height": 200}}
    """
    cache_path = Path(__file__).parent.parent.parent.parent / "data" / "item_image_dimensions.yaml"

    if not cache_path.exists():
        return {}

    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return data if data else {}
    except Exception as e:
        print(f"加载图片尺寸缓存失败: {e}")
        return {}


def _save_image_dimensions_cache(data: dict) -> bool:
    """保存图片尺寸缓存

    Args:
        data: 缓存数据字典

    Returns:
        是否保存成功
    """
    try:
        cache_path = Path(__file__).parent.parent.parent.parent / "data" / "item_image_dimensions.yaml"
        # 确保目录存在
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        with open(cache_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        return True
    except Exception as e:
        print(f"保存图片尺寸缓存失败: {e}")
        return False


async def _get_image_dimensions_with_cache(item_id: str, image_url: str, max_size: int = 300) -> tuple[str, str]:
    """获取图片尺寸并按比例缩放（带缓存）

    Args:
        item_id: 物品ID
        image_url: 图片URL
        max_size: 最大尺寸限制（宽度或高度的最大值）

    Returns:
        (width, height) 缩放后的宽度和高度字符串
    """
    # 加载缓存
    cache = _load_image_dimensions_cache()

    # 检查缓存是否有效
    if item_id in cache:
        cached_info = cache[item_id]
        # 如果URL没有变化，直接使用缓存
        if cached_info.get("url") == image_url:
            width = cached_info.get("width", 200)
            height = cached_info.get("height", 200)
            print(f"使用缓存的图片尺寸: {item_id} -> {width}x{height}")
            return str(width), str(height)

    # 缓存无效或不存在，需要下载图片获取尺寸
    print(f"下载图片获取尺寸: {image_url}")

    try:
        # 设置超时时间
        timeout = aiohttp.ClientTimeout(total=10)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(image_url) as response:
                if response.status != 200:
                    print(f"获取图片失败: HTTP {response.status}")
                    return "200", "200"  # 返回默认尺寸

                # 读取图片数据
                image_data = await response.read()

                # 使用PIL解析图片尺寸
                image = Image.open(BytesIO(image_data))
                original_width, original_height = image.size

                # 计算等比缩放
                if original_width > max_size or original_height > max_size:
                    # 需要缩放
                    if original_width > original_height:
                        # 宽度更大，以宽度为基准
                        scale = max_size / original_width
                    else:
                        # 高度更大，以高度为基准
                        scale = max_size / original_height

                    new_width = int(original_width * scale)
                    new_height = int(original_height * scale)
                else:
                    # 不需要缩放
                    new_width = original_width
                    new_height = original_height

                # 更新缓存
                cache[item_id] = {
                    "url": image_url,
                    "width": new_width,
                    "height": new_height
                }
                _save_image_dimensions_cache(cache)
                print(f"已缓存图片尺寸: {item_id} -> {new_width}x{new_height}")

                return str(new_width), str(new_height)

    except asyncio.TimeoutError:
        print(f"获取图片尺寸超时: {image_url}")
        return "200", "200"  # 返回默认尺寸
    except Exception as e:
        print(f"获取图片尺寸失败: {e}")
        return "200", "200"  # 返回默认尺寸


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
        "GEM": "镶嵌物",
        "FISH": "鱼类",
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
                "orange": "传说",
                "red": "永恒"
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

            # 特殊效果信息（显示解锁条件）
            if hasattr(cfg, 'special_effects') and cfg.special_effects:
                # VIP定制装备列表（0阶即全解锁）
                VIP_EQUIPMENT_IDS = {"vip_blade_zhanlongshan", "vip_robe_jingyuanzhiyi"}
                is_vip_equipment = cfg.item_id in VIP_EQUIPMENT_IDS

                if is_vip_equipment:
                    effects_lines = ["✨ 特殊效果（VIP定制，0阶全解锁）："]
                    for effect in cfg.special_effects:
                        desc = effect.get('description', '')
                        if desc:
                            effects_lines.append(f"  • {desc}")
                else:
                    effects_lines = ["✨ 特殊效果（升阶解锁）："]
                    for idx, effect in enumerate(cfg.special_effects, start=1):
                        # 获取效果描述
                        desc = effect.get('description', '')
                        if desc:
                            # 计算解锁所需的升阶等级
                            required_level = idx * 2
                            effects_lines.append(f"  • [{idx}] {desc} (+{required_level}阶解锁)")
                equipment_info.extend(effects_lines)

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
            obtain_info = f"📍 获取方式：\n{obtain_methods}" if obtain_methods else ""

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

        # 若为鱼类，展示稀有度和价格信息
        elif cfg.type.value == "FISH":
            rarity_display = cfg.get_rarity_display()
            rarity_map = {
                "white": "普通",
                "green": "优良",
                "blue": "精品",
                "purple": "稀有",
                "orange": "传说"
            }
            rarity_name = rarity_map.get(cfg.rarity, cfg.rarity)
            fish_info = [
                f"⭐ 稀有度：{rarity_display}{rarity_name}",
                f"💰 价值：{cfg.price:,} 金币",
                f"🎣 获取方式：钓鱼系统"
            ]
            extra_info = "\n" + "\n".join(fish_info)

        lines.append(f"✨ {cfg.name} ✨  [{type_cn}]\n{cfg.description}{extra_info}")

    # 如果只有一个匹配结果，尝试使用Markdown模板展示（支持所有物品类型）
    if len(item_matches) == 1:
        cfg = item_matches[0]
        item_image_url = _get_item_image_url(cfg.item_id)

        # 构建描述信息（根据物品类型定制）
        rarity_display = cfg.get_rarity_display()
        rarity_map = {
            "white": "普通",
            "green": "优良" if cfg.type.value == "FISH" else "优秀",
            "blue": "精品" if cfg.type.value == "FISH" else "稀有",
            "purple": "稀有" if cfg.type.value == "FISH" else "史诗",
            "orange": "传说",
            "red": "永恒"
        }
        rarity_name = rarity_map.get(cfg.rarity, cfg.rarity)

        # 根据物品类型构建描述
        desc_parts = [f"{cfg.description}", ""]

        # 添加稀有度和价值信息
        if hasattr(cfg, 'rarity') and cfg.rarity:
            desc_parts.append(f"⭐ 稀有度：{rarity_display}{rarity_name}")
        if cfg.price > 0:
            desc_parts.append(f"💰 价值：{cfg.price:,} 金币")

        # 根据物品类型添加特定信息
        if cfg.type.value == "FISH":
            desc_parts.append(f"🎣 获取方式：钓鱼系统")
        elif cfg.type.value == "MATERIAL":
            desc_parts.append(f"📦 类型：材料")
            if cfg.grudge_value > 0:
                desc_parts.append(f"😈 怨念值：{cfg.grudge_value}")
        elif cfg.type.value == "EQUIPMENT":
            desc_parts.append(f"⚔️ 类型：装备")
            if hasattr(cfg, 'required_level'):
                desc_parts.append(f"📊 等级要求：Lv.{cfg.required_level}")
        elif cfg.type.value == "CONSUMABLE":
            desc_parts.append(f"💊 类型：消耗品")
        elif cfg.type.value == "GEM":
            desc_parts.append(f"💎 类型：镶嵌物")
        elif cfg.type.value == "GIFT":
            desc_parts.append(f"🎁 类型：礼物")
            if hasattr(cfg, 'favorability') and cfg.favorability > 0:
                desc_parts.append(f"💝 好感度：+{cfg.favorability}")

        desc = "\r".join(desc_parts)

        # 根据物品类型定制快捷操作按钮（4个）
        type_buttons = {
            "FISH": ["钓鱼", "鱼栏", "钓鱼记录", "钓鱼排行"],
            "MATERIAL": ["背包", "锻造列表", "市集", "帮助"],
            "EQUIPMENT": ["装备栏", "锻造列表", "升阶列表", "背包"],
            "CONSUMABLE": ["背包", "使用", "一键嗑药", "帮助"],
            "GEM": ["背包", "镶嵌物品", "孔位", "帮助"],
            "GIFT": ["背包", "赠送", "社交系统", "帮助"],
            "GOODS": ["背包", "市集", "帮助", "图鉴"]
        }
        buttons = type_buttons.get(cfg.type.value, ["背包", "图鉴", "帮助", "面板"])

        # 提示信息（简化版，因为按钮已经独立出来）
        hint = "💡 点击下方按钮快速操作"

        # 根据物品类型定制标题图标
        type_icons = {
            "FISH": "🐟",
            "MATERIAL": "📦",
            "EQUIPMENT": "⚔️",
            "CONSUMABLE": "💊",
            "GEM": "💎",
            "GIFT": "🎁",
            "GOODS": "🏪"
        }
        icon = type_icons.get(cfg.type.value, "📖")

        # 如果没有配图，使用占位URL和0尺寸
        if not item_image_url:
            item_image_url = "https://example.com/placeholder.png"  # 占位URL
            width = "0"
            height = "0"
        elif cfg.type.value == "FISH":
            # 鱼类图片统一尺寸：宽300x高163
            width, height = "300", "163"
        else:
            # 其他类型物品获取图片实际尺寸并等比缩放（带缓存）
            width, height = await _get_image_dimensions_with_cache(cfg.item_id, item_image_url)

        # 构建Markdown模板参数（使用带按钮的图鉴类模版）
        template_params = [
            MessageMarkdownParams(key="title", values=[f"{icon} {cfg.name}"]),
            MessageMarkdownParams(key="desc", values=[desc]),
            MessageMarkdownParams(key="imgurl", values=[item_image_url]),
            MessageMarkdownParams(key="width", values=[width]),
            MessageMarkdownParams(key="height", values=[height]),
            MessageMarkdownParams(key="hint", values=[hint]),
            MessageMarkdownParams(key="t1", values=[buttons[0]]),
            MessageMarkdownParams(key="t2", values=[buttons[1]]),
            MessageMarkdownParams(key="t3", values=[buttons[2]]),
            MessageMarkdownParams(key="t4", values=[buttons[3]])
        ]

        markdown = MessageMarkdown(
            custom_template_id="102499345_1769693953",
            params=template_params
        )

        # 发送Markdown消息
        msg = Message("📖 物品图鉴")
        msg.append(MessageSegment.markdown(markdown))
        await catalog_cmd.finish(msg)

    await catalog_cmd.finish(message_add_head("\n".join(lines), event))