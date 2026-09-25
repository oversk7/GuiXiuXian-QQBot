from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.adapters.qq.exception import ActionFailed
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
from ..utils_markdown import build_markdown, cmd, color_rarity
from ..models.db import safe_session
from ..models.player import Player
from ..models.elixir_usage import ElixirUsageLog
from ..models.inventory import ItemInstance
from .equipment_service import VIP_EQUIPMENT_IDS

# 具有主动技能的VIP装备ID集合（图鉴中不显示技能详情，仅对持有者提示）
_VIP_ACTIVE_SKILL_IDS: set[str] = {
    "vip_robe_jingyuanzhiyi",  # 镜怨披风
    "vip_gui_yu",              # 归雨
    "vip_chrono_watch",        # 折光年
    "vip_longying_flash",      # 龙影闪
    "vip_ghost_dice",          # 诡面骰
}


def _get_equipment_drop_note(cfg) -> str:
    drop = cfg.dungeon_drop
    if not drop:
        return ""
    level_range = (
        f"Lv.{drop['min_level']}-{drop['max_level']}"
        if drop.get("max_level") is not None
        else f"Lv.{drop['min_level']}及以上"
    )
    return f"📍 获取：诡域{level_range}怪物额外掉落（精英概率更高）"


async def _send_catalog_detail(content: str, image: str | None = None) -> None:
    if image:
        title, body = content.split("\n", 1)
        try:
            await catalog_cmd.send(build_markdown(
                f"{title}\n{image}\n{body}", force_verify_image_resource=True,
            ))
        except ActionFailed as exc:
            # QQ 官方错误码：304010 CHANGE_IMAGE_URL（图片转存错误）。
            if exc.code != 304010:
                raise
            await catalog_cmd.send(build_markdown(content))
    else:
        await catalog_cmd.send(build_markdown(content))
    await catalog_cmd.finish()


def _get_material_tier_note(item_id: str) -> str:
    """材料可获取的诡域深度范围备注（读 material_tiers 配置，含材料格子/商人/战斗掉落）"""
    material_tiers = config.map_config.get("dungeon_generation_rules", {}).get("material_tiers", {})
    ranges = []
    for tier_range, materials in material_tiers.items():
        if item_id in materials.get("basic_materials", []) or item_id in materials.get("merchant_materials", []):
            try:
                start, end = map(int, tier_range.split("-"))
                ranges.append((start, end))
            except ValueError:
                continue
    if not ranges:
        return ""
    # 合并相邻/重叠的深度区间，如 1-20 + 21-50 → 1~50
    ranges.sort()
    merged = [list(ranges[0])]
    for start, end in ranges[1:]:
        if start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    # 配置中的 201-999 是有限档；1000 重起由配置函数回退默认材料池。
    parts = [f"{s}~{e}重" for s, e in merged]
    return f"（{'、'.join(parts)}诡域可获得）"


def _load_item_images() -> dict:
    """加载物品图片配置

    Returns:
        物品ID到图片URL的映射字典
    """
    config_path = Path(__file__).parent.parent / "data" / "item_images.yaml"

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
catalog_cmd = on_command("图鉴", aliases={"查看","查看物品","详情"}, block=True, priority=9)


def _format_codex_list(entries, title: str, page: int, total_pages: int, query: str) -> str:
    lines = [f"📖 {title}（第 {page}/{total_pages} 页）", "━━━━━━━━━━"]
    if title.startswith("装备"):
        lines.append("用法：图鉴 装备 [品质] [等级] [页码]")
    for entry in entries:
        lines.append(f"• {cmd(entry['name'], '图鉴 ' + entry['key'])} [{entry['category']}]")
        if entry.get("description"):
            lines.append(f"  {entry['description']}")
    if total_pages > 1:
        nav = []
        if page > 1:
            nav.append(cmd("上一页", f"图鉴 {query} {page - 1}"))
        if page < total_pages:
            nav.append(cmd("下一页", f"图鉴 {query} {page + 1}"))
        lines.extend(["━━━━━━━━━━", " | ".join(nav)])
    return "\n".join(lines)


async def _send_codex(content: str) -> None:
    await catalog_cmd.finish(build_markdown(f"『诡修仙』\n{content}"))


@catalog_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """统一图鉴目录与查询入口；物品详情卡继续复用原展示。"""
    keyword = args.extract_plain_text().strip()
    from . import codex_service

    entries = codex_service.get_entries()
    if not keyword:
        overview = ["📖 全游戏图鉴", "━━━━━━━━━━"]
        for group in codex_service.categories(entries):
            count = sum(entry["category"] == group for entry in entries)
            overview.append(f"• {cmd(group, f'图鉴 {group}')}（{count}）")
        overview.extend([
            f"• {cmd('丹药/消耗品', '图鉴 丹药')}",
            f"• {cmd('全部配方', '图鉴 配方')}",
            f"• {cmd('玩法', '图鉴 玩法')}",
            f"• {cmd('地图', '图鉴 地图')} | {cmd('人物', '图鉴 人物')}",
            "装备筛选：图鉴 装备 [品质] [等级] [页码]",
        ])
        await _send_codex("\n".join(overview))

    dungeon_query = keyword.split()
    if dungeon_query[0] == "诡域" and len(dungeon_query) > 1:
        if len(dungeon_query) != 2 or not dungeon_query[1].isascii() or not dungeon_query[1].isdigit() or len(dungeon_query[1]) > 9 or int(dungeon_query[1]) < 1:
            await _send_codex("⛔ 请输入正整数深度，例如：图鉴 诡域 50")
        selected = codex_service.dungeon_entry(int(dungeon_query[1]))
        detail_lines, current, total = codex_service.detail_page(selected)
        output = [f"📖 {selected['name']}（{current}/{total}）", "━━━━━━━━━━", *detail_lines]
        await _send_codex("\n".join(output))

    parts = keyword.rsplit(maxsplit=1)
    page = 1
    query = keyword
    exact_input = any(keyword == entry['key'] or keyword == entry['name'] or keyword in entry['aliases'] for entry in entries)
    relation_input = keyword.split(maxsplit=1)
    if len(relation_input) == 2 and relation_input[0] in ('来源', '用途', '来源用途'):
        exact_input = any(entry['key'].startswith('item:') and
                          (relation_input[1] == entry['key'] or relation_input[1] == entry['name'] or relation_input[1] in entry['aliases'])
                          for entry in entries)
    if len(parts) == 2 and parts[1].isascii() and parts[1].isdigit() and not exact_input:
        if len(parts[1]) > 9 or int(parts[1]) < 1:
            await _send_codex("⛔ 页码需为正整数。")
        query, page = parts[0], int(parts[1])

    if query in ("基础铭文", "进阶铭文"):
        advanced = query == "进阶铭文"
        selected_entries = [entry for entry in entries if entry["key"].startswith("item:")
                            and (item := config.items_config["by_id"].get(entry["key"][5:]))
                            and item.type.value == "INSCRIPTION"
                            and (getattr(item, "inscription_type", None) == "advanced") == advanced]
        page_items, current, total = codex_service.page_entries(selected_entries, page=page)
        await _send_codex(_format_codex_list(page_items, query, current, total, query))

    from . import codex_filters
    equipment_query = codex_filters.parse_equipment_query(keyword)
    if equipment_query:
        rarity, max_level, equipment_page = equipment_query
        selected_entries = codex_filters.filter_equipment(entries, rarity, max_level)
        page_items, current, total = codex_service.page_entries(selected_entries, page=equipment_page)
        prefix = keyword.rsplit(maxsplit=1)[0] if keyword.split()[-1].isdigit() else keyword
        title = "装备筛选"
        if max_level is not None:
            title += f"（等级要求不高于{max_level}；转生条件见装备详情）"
        await _send_codex(_format_codex_list(page_items, title, current, total, prefix))

    relation_parts = query.split(maxsplit=1)
    if len(relation_parts) == 2 and relation_parts[0] in ("来源", "用途", "来源用途"):
        item_entries = [entry for entry in entries if entry['key'].startswith('item:')]
        matches = codex_service.search_entries(relation_parts[1], item_entries)
        if not matches:
            await _send_codex("⛔ 未找到该物品，请输入完整物品名。")
        if len(matches) > 1:
            page_items, current, total = codex_service.page_entries(matches, page=page)
            await _send_codex(_format_codex_list(page_items, '请选择物品，再点来源与用途', current, total, query))
        item_id = matches[0]['key'][5:]
        relation_page = page
        relation = {"description": "", "lines": codex_service.get_item_relations(item_id)}
        page_lines, current, total = codex_service.detail_page(relation, relation_page)
        output = [f"📚 {matches[0]['name']} 来源与用途（{current}/{total}）", "━━━━━━━━━━", *page_lines]
        if total > 1:
            nav = []
            if current > 1:
                nav.append(cmd("上一页", f"图鉴 来源 item:{item_id} {current - 1}"))
            if current < total:
                nav.append(cmd("下一页", f"图鉴 来源 item:{item_id} {current + 1}"))
            output.extend(["━━━━━━━━━━", " | ".join(nav)])
        await _send_codex("\n".join(output))

    category = codex_service.resolve_category(query, entries)
    if category:
        page_items, current, total = codex_service.page_entries(entries, category, page)
        await _send_codex(_format_codex_list(page_items, category, current, total, query))

    matched_entries = codex_service.search_entries(query, entries)
    if not matched_entries:
        await _send_codex("⛔ 未找到符合条件的图鉴条目")
    if len(matched_entries) > 1:
        page_items, current, total = codex_service.page_entries(matched_entries, page=page)
        await _send_codex(_format_codex_list(page_items, f"“{query}”候选结果", current, total, query))

    selected = matched_entries[0]
    if selected["key"].startswith("item:"):
        item = config.items_config["by_id"].get(selected["key"][5:])
        item_matches = [item] if item else []
    else:
        detail_lines, current, total = codex_service.detail_page(selected, page)
        output = [f"📖 {selected['name']} [{selected['category']}]（{current}/{total}）",
                  "━━━━━━━━━━", *detail_lines]
        if total > 1:
            nav = []
            if current > 1:
                nav.append(cmd("上一页", f"图鉴 {selected['key']} {current - 1}"))
            if current < total:
                nav.append(cmd("下一页", f"图鉴 {selected['key']} {current + 1}"))
            output.extend(["━━━━━━━━━━", " | ".join(nav)])
        await _send_codex("\n".join(filter(None, output)))

    # 获取玩家信息（用于查询丹药使用状态）
    from ..platform_utils import get_unified_player
    player = None
    elixir_usage_map = {}
    player_active_equip_ids: set[str] = set()
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

            # 查询玩家持有的具有主动技能的VIP装备（用于图鉴提示控制）
            stmt2 = select(ItemInstance.item_id).where(
                ItemInstance.player_id == player.id,
                ItemInstance.item_id.in_(list(_VIP_ACTIVE_SKILL_IDS))
            )
            player_active_equip_ids = set((await session.execute(stmt2)).scalars().all())

    # 统一服务先处理分类与非物品条目；此处只沿用既有物品详情卡。
    total_matches = len(item_matches)

    # 类型映射
    TYPE_NAME_MAP = {
        "CONSUMABLE": "消耗品",
        "MATERIAL": "材料",
        "EQUIPMENT": "装备",
        "GOODS": "商品",
        "GEM": "镶嵌物",
        "FISH": "鱼类",
        "SEASONING": "调味料",
        "DISH": "菜肴",
        "RECIPE": "食谱",
        "GIFT": "礼物",
        "GHOST_FRAGMENT": "鬼魂碎片",
        "VEGETABLE": "灵蔬",
        "HERB": "诡药",
        "SEED": "灵种",
        "GUARDIAN_BEAST": "守护兽",
        "INSCRIPTION": "铭文",
    }

    TYPE_ICON_MAP = {
        "CONSUMABLE": "💊",
        "MATERIAL": "📦",
        "EQUIPMENT": "⚔️",
        "GOODS": "🏪",
        "GEM": "💎",
        "FISH": "🐟",
        "SEASONING": "🧂",
        "DISH": "🍽️",
        "RECIPE": "📜",
        "GIFT": "🎁",
        "GHOST_FRAGMENT": "👻",
        "VEGETABLE": "🌿",
        "HERB": "🌱",
        "SEED": "🫘",
        "GUARDIAN_BEAST": "🐾",
        "INSCRIPTION": "🔮",
    }

    lines = ["📖 图鉴查询结果 ✨", "━━━━━━━━━━"]

    # 显示物品匹配结果
    for cfg in item_matches:
        if cfg.type.value == "INSCRIPTION":
            is_adv = getattr(cfg, 'inscription_type', None) == "advanced"
            type_cn = "进阶铭文" if is_adv else "基础铭文"
        else:
            type_cn = TYPE_NAME_MAP.get(cfg.type.value, cfg.type.value)

        extra_info = ""
        # 若为铭文，展示铭文类型
        if cfg.type.value == "INSCRIPTION":
            is_adv = getattr(cfg, 'inscription_type', None) == "advanced"
            ins_type_cn = "进阶铭文" if is_adv else "基础铭文"
            extra_info = f"\n🔮 铭文类型：{ins_type_cn}"

        # 若为装备，附加等级要求、属性加成、稀有度等信息
        elif cfg.type.value == "EQUIPMENT":
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
                reinc = getattr(cfg, 'required_reincarnation', 0)
                equipment_info.append(f"📊 等级要求：Lv.{cfg.required_level}" + (f"·{reinc}转" if reinc else ""))

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

            if cfg.dungeon_drop:
                equipment_info.append(_get_equipment_drop_note(cfg))

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

            slot_bonus = int(getattr(cfg, "equipment_slot_bonus", 0) or 0)
            if slot_bonus > 0:
                equipment_info.append(f"🎽 装备槽：+{slot_bonus}（穿戴后净增{slot_bonus - 1}格）")

            # 特殊效果信息（显示解锁条件）
            if hasattr(cfg, 'special_effects') and cfg.special_effects:
                is_vip_equipment = cfg.item_id in VIP_EQUIPMENT_IDS

                if is_vip_equipment and cfg.item_id in _VIP_ACTIVE_SKILL_IDS:
                    # 有主动技能的VIP装备：被动效果全部展示，主动技能只提示
                    effects_lines = ["✨ 特殊效果（VIP定制，0阶全解锁）："]
                    for effect in cfg.special_effects:
                        desc = effect.get('description', '')
                        if desc:
                            effects_lines.append(f"  • {desc}")
                    equipment_info.extend(effects_lines)
                    # 所有人都能看到有主动技能，但具体内容仅持有者可查
                    if cfg.item_id in player_active_equip_ids:
                        equipment_info.append(f"🌟 主动技能：发送【{cfg.name}】查看")
                    else:
                        equipment_info.append("🌟 主动技能：（持有者专属）")
                elif is_vip_equipment:
                    effects_lines = ["✨ 特殊效果（VIP定制，0阶全解锁）："]
                    for effect in cfg.special_effects:
                        desc = effect.get('description', '')
                        if desc:
                            effects_lines.append(f"  • {desc}")
                    equipment_info.extend(effects_lines)
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

            extra_info = "\n" + "\n".join(filter(bool, [rarity_info, grudge_info]))

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
            ]
            extra_info = "\n" + "\n".join(fish_info)

        # 若为调味料，展示稀有度、价格和获取来源
        elif cfg.type.value == "SEASONING":
            rarity_display = cfg.get_rarity_display()
            rarity_map = {
                "white": "普通",
                "green": "优秀",
                "blue": "稀有",
                "purple": "史诗",
                "orange": "传说"
            }
            rarity_name = rarity_map.get(cfg.rarity, cfg.rarity)
            seasoning_info = [
                f"⭐ 稀有度：{rarity_display}{rarity_name}",
                f"💰 价值：{cfg.price:,} 金币",
            ]
            extra_info = "\n" + "\n".join(seasoning_info)

        desc_suffix = _get_material_tier_note(cfg.item_id) if cfg.type.value == "MATERIAL" else ""
        lines.append(f"✨ {cfg.name} ✨  [{type_cn}]\n{cfg.description}{desc_suffix}{extra_info}")

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
        desc_suffix = _get_material_tier_note(cfg.item_id) if cfg.type.value == "MATERIAL" else ""
        desc_parts = [f"{cfg.description}{desc_suffix}", ""]
        desc_parts.extend(selected.get('lines', []))
        desc_parts.append(f"📚 来源与用途：{cmd('查看', f'图鉴 来源 item:{cfg.item_id}')}")

        # 添加稀有度和价值信息
        if hasattr(cfg, 'rarity') and cfg.rarity:
            desc_parts.append(f"⭐ 稀有度：{rarity_display}{color_rarity(rarity_name, cfg.rarity)}")
        if cfg.price > 0:
            desc_parts.append(f"💰 价值：**{cfg.price:,}** 金币")

        # 根据物品类型添加特定信息
        if cfg.type.value == "FISH":
            desc_parts.append("🎣 类型：鱼类")
        elif cfg.type.value == "MATERIAL":
            desc_parts.append(f"📦 类型：材料")
            if cfg.grudge_value > 0:
                desc_parts.append(f"😈 怨念值：{cfg.grudge_value}")
        elif cfg.type.value == "EQUIPMENT":
            desc_parts.append(f"⚔️ 类型：装备")
            if cfg.dungeon_drop:
                desc_parts.append(_get_equipment_drop_note(cfg))
            if hasattr(cfg, 'required_level'):
                reinc = getattr(cfg, 'required_reincarnation', 0)
                desc_parts.append(f"📊 等级要求：Lv.{cfg.required_level}" + (f"·{reinc}转" if reinc else ""))

            # 属性加成
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
                desc_parts.append("🔧 属性加成：" + " 、".join(bonus_parts))

            # 宝石孔位信息
            if hasattr(cfg, 'gem_slots') and cfg.gem_slots > 0:
                desc_parts.append(f"💎 宝石孔位：{cfg.gem_slots}个")

            slot_bonus = int(getattr(cfg, "equipment_slot_bonus", 0) or 0)
            if slot_bonus > 0:
                desc_parts.append(f"🎽 装备槽：+{slot_bonus}（穿戴后净增{slot_bonus - 1}格）")

            # 特殊效果信息（显示解锁条件）
            if hasattr(cfg, 'special_effects') and cfg.special_effects:
                is_vip_equipment = cfg.item_id in VIP_EQUIPMENT_IDS

                if is_vip_equipment and cfg.item_id in _VIP_ACTIVE_SKILL_IDS:
                    # 有主动技能的VIP装备：被动效果全部展示，主动技能只提示
                    desc_parts.append("**✨ 特殊效果（VIP定制，0阶全解锁）**")
                    for effect in cfg.special_effects:
                        effect_desc = effect.get('description', '')
                        if effect_desc:
                            desc_parts.append(f"  • {effect_desc}")
                    # 所有人都能看到有主动技能，但具体内容仅持有者可查
                    if cfg.item_id in player_active_equip_ids:
                        desc_parts.append(f"🌟 主动技能：发送 {cmd(cfg.name)} 查看")
                    else:
                        desc_parts.append("🌟 主动技能：（持有者专属）")
                elif is_vip_equipment:
                    desc_parts.append("**✨ 特殊效果（VIP定制，0阶全解锁）**")
                    for effect in cfg.special_effects:
                        effect_desc = effect.get('description', '')
                        if effect_desc:
                            desc_parts.append(f"  • {effect_desc}")
                else:
                    desc_parts.append("**✨ 特殊效果（升阶解锁）**")
                    for idx, effect in enumerate(cfg.special_effects, start=1):
                        # 获取效果描述
                        effect_desc = effect.get('description', '')
                        if effect_desc:
                            # 计算解锁所需的升阶等级
                            required_level = idx * 2
                            desc_parts.append(f"  • [{idx}] {effect_desc} (+{required_level}阶解锁)")
        elif cfg.type.value == "INSCRIPTION":
            is_adv = getattr(cfg, 'inscription_type', None) == "advanced"
            ins_type_cn = "进阶铭文" if is_adv else "基础铭文"
            desc_parts.append(f"🔮 铭文类型：{ins_type_cn}")
            desc_parts.append(f"📍 类型：{ins_type_cn}")
        elif cfg.type.value == "CONSUMABLE":
            desc_parts.append(f"💊 类型：消耗品")
        elif cfg.type.value == "GEM":
            desc_parts.append(f"💎 类型：镶嵌物")
        elif cfg.type.value == "GIFT":
            desc_parts.append(f"🎁 类型：礼物")
            if hasattr(cfg, 'favorability') and cfg.favorability > 0:
                desc_parts.append(f"💝 好感度：+{cfg.favorability}")
        elif cfg.type.value == "SEASONING":
            desc_parts.append(f"🧂 类型：调味料")
            desc_parts.append("📍 来源资料见上方")

        # 根据物品类型定制快捷操作按钮（4个）
        type_buttons = {
            "FISH": ["钓鱼", "鱼栏", "钓鱼记录", "钓鱼排行"],
            "MATERIAL": ["背包", "锻造列表", "市集", "帮助"],
            "EQUIPMENT": ["装备栏", "锻造列表", "升阶列表", "背包"],
            "CONSUMABLE": ["背包", "使用", "一键嗑药", "帮助"],
            "GEM": ["背包", "镶嵌物品", "孔位", "帮助"],
            "GIFT": ["背包", "赠送", "社交系统", "帮助"],
            "GOODS": ["背包", "市集", "帮助", "图鉴"],
            "SEASONING": ["背包", "餐厅", "菜单", "食谱"],
            "DISH": ["背包", "餐厅", "吃", "帮助"],
            "RECIPE": ["背包", "食谱", "餐厅", "帮助"],
            "INSCRIPTION": ["背包", "铭文", "铭文列表", "帮助"],
        }
        buttons = type_buttons.get(cfg.type.value, ["背包", "图鉴", "帮助", "面板"])

        # 根据物品类型定制标题图标
        type_icons = {
            "FISH": "🐟",
            "MATERIAL": "📦",
            "EQUIPMENT": "⚔️",
            "CONSUMABLE": "💊",
            "GEM": "💎",
            "GIFT": "🎁",
            "GOODS": "🏪",
            "SEASONING": "🧂",
            "DISH": "🍽️",
            "RECIPE": "📜",
            "INSCRIPTION": "🔮",
        }
        icon = type_icons.get(cfg.type.value, "📖")

        # 组装原生 Markdown 图鉴卡片
        md_lines = [f"## {icon} {cfg.name}"]
        image = None

        if item_image_url:
            if cfg.type.value == "FISH":
                # 鱼类图片统一尺寸：宽300x高163
                width, height = "300", "163"
            else:
                # 其他类型物品获取图片实际尺寸并等比缩放（带缓存）
                width, height = await _get_image_dimensions_with_cache(cfg.item_id, item_image_url)
            image = f"![{cfg.name} #{width}px #{height}px]({item_image_url})"

        md_lines.append("***")
        md_lines.extend(desc_parts)
        md_lines.append("***")
        md_lines.append("> 📖 点击蓝字快速操作")
        md_lines.append(" | ".join(cmd(b) for b in buttons))

        await _send_catalog_detail("\n".join(md_lines), image)
