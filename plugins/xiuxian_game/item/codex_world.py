"""公开世界资料图鉴数据源。"""

from ..config import config
from ..utils_markdown import cmd
from ..world.npc_definitions import SOCIAL_AGENT_CITIES, STATION_MASTER_NAMES, INTELLIGENCE_DEALERS, SOCIAL_NPCS

def _entry(key: str, name: str, category: str, description: str, aliases=None, lines=None) -> dict:
    return {
        "key": key,
        "name": name,
        "category": category,
        "description": description,
        "aliases": list(aliases or []),
        "lines": list(lines or []),
    }


def _item_link(item_id: str) -> str:
    item = config.items_config["by_id"].get(item_id)
    if not item:
        return item_id
    return cmd(item.name, f"图鉴 item:{item_id}")


def _format_affix_ranges(affix: dict) -> list[str]:
    from .affix_service import get_affix_display_name

    rarity_names = {"white": "白色", "green": "绿色", "blue": "蓝色", "purple": "紫色", "orange": "橙色"}
    primary = affix.get("ranges", affix.get("chance_ranges", {}))
    lines = []
    def span(bounds):
        return f"{bounds[0]}～{bounds[1]}" if bounds[0] != bounds[1] else str(bounds[0])
    for rarity, bounds in primary.items():
        values = {"affix_id": affix["affix_id"], "tier": "T1" if "ranges" in affix else "T2", "value": span(bounds)}
        duration = affix.get("duration_ranges", {}).get(rarity)
        secondary = affix.get("value_ranges", {}).get(rarity)
        if secondary or duration:
            values["value2"] = span(secondary or duration)
        if duration:
            values["duration"] = span(duration)
        lines.append(f"{rarity_names.get(rarity, rarity)}：{get_affix_display_name(values)}")
    return lines


def get_entries() -> list[dict]:
    """读取公开地图、首领、套装、词缀、宠物和守护兽资料。"""
    entries: list[dict] = []

    # 市集坐标是实际地图配置；不查询玩家位置或个人宅邸数据。
    from ..economy.merchant_service import MARKET_CONFIGS, HEADQUARTERS_COORD
    from ..world.location_init import _get_merchant_name

    for market_id, market in MARKET_CONFIGS.items():
        x, y = market["coord"]
        entries.append(_entry(
            f"map:{market_id}", market["name"], "地点",
            f"大都会市集，坐标（{x}, {y}）。",
            aliases=[f"{market['name']}市集", f"{market['name']}地图"],
            lines=[f"坐标：({x}, {y})",
                   f"当地商人：{cmd(_get_merchant_name(market['name']), f'图鉴 npc:merchant:{market_id}')}",
                   cmd('前往', f"导航 {market['name']}")],
        ))
        entries.append(_entry(
            f"npc:merchant:{market_id}", _get_merchant_name(market['name']), "人物",
            f"设于{market['name']}的市集商人。", aliases=[market['name'] + '商人'],
            lines=[f"所在地点：{cmd(market['name'], f'图鉴 map:{market_id}')}",
                   "职能：市集买卖；当前营业与库存以游戏内交互为准。"],
        ))
    hq_x, hq_y = HEADQUARTERS_COORD
    entries.append(_entry(
        "map:headquarters", "缉邪司总部", "地点",
        f"缉邪司总部位于风雪镇，坐标（{hq_x}, {hq_y}）。",
        aliases=["缉邪司", "缉邪司总部地图"],
        lines=[f"位置：风雪镇（{hq_x}, {hq_y}）"],
    ))

    # NPC personality/story files are intentionally excluded. Static world-boss
    # names and titles are public encounter data; lore descriptions are omitted.
    from ..world_boss.service import WorldBossService

    for boss in WorldBossService.BOSS_POOL:
        entries.append(_entry(
            f"boss:{boss['name']}", boss["name"], "首领",
            f"世界首领，称号：{boss['title']}。",
            aliases=[boss["title"]], lines=["首领轮换出现，具体状态以游戏内世界首领信息为准。"],
        ))

    from .set_bonus_service import _load_config as load_sets
    from .affix_service import get_affix_config

    for set_id, set_data in load_sets().get("sets", {}).items():
        pieces = set_data.get("pieces", [])
        lines = ["套装部件：" + "、".join(_item_link(item_id) for item_id in pieces)]
        for threshold, bonus in sorted(set_data.get("bonuses", {}).items(), key=lambda pair: int(pair[0])):
            lines.append(f"{threshold}件：{bonus.get('description', '')}")
        entries.append(_entry(
            f"set:{set_id}", set_data["name"], "套装",
            f"包含{len(pieces)}件装备。", aliases=[set_id], lines=lines,
        ))

    affix_config = get_affix_config().get("affixes", {})
    for tier in ("t1", "t2"):
        for affix in affix_config.get(tier, []):
            range_lines = _format_affix_ranges(affix)
            entries.append(_entry(
                f"affix:{affix['affix_id']}", affix["name"], "词缀",
                f"{tier.upper()}词缀。", aliases=[affix["affix_id"]],
                lines=[f"类型：{tier.upper()}", *range_lines],
            ))

    from ..pet.config import PetConfigManager
    from ..spirit_field.config import GuardianBeastManager

    for pet in PetConfigManager().get_all_beasts():
        entries.append(_entry(
            f"pet:{pet.beast_id}", pet.name, "宠物", pet.description,
            aliases=[pet.beast_id],
            lines=[f"稀有度：{pet.rarity}", f"守田拦截率：{pet.intercept_rate}%"],
        ))
    for guardian in GuardianBeastManager().get_all_beasts():
        entries.append(_entry(
            f"guardian:{guardian.beast_id}", guardian.name, "守护兽", guardian.description,
            aliases=[guardian.beast_id],
            lines=[f"稀有度：{guardian.rarity}", f"拦截率：{guardian.intercept_rate}%",
                   f"对应物品：{_item_link(guardian.item_id)}"],
        ))

    # 只从静态初始化定义公开NPC名字与职能，不读取npc_personalities或NPC数据库。
    function_names = {"matchmaker": "姻缘事务", "sworn_ceremony": "结义事务", "mentorship": "师徒事务"}
    social_npcs = [(npc["name"], npc["city"], function_names[npc["function"]]) for npc in SOCIAL_NPCS]
    social_npcs.extend((name, city, "姻缘、结义与师徒事务")
                       for city, name in SOCIAL_AGENT_CITIES.items())
    for npc_name, city, function in social_npcs:
        entries.append(_entry(
            f"npc:{city}:{npc_name}", npc_name, "人物",
            f"设于{city}，办理{function}。", aliases=[city + npc_name],
            lines=[f"所在地点：{city}", f"职能：{function}"],
        ))

    station_master_names = STATION_MASTER_NAMES
    intel_dealers = INTELLIGENCE_DEALERS
    for city, npc_name in station_master_names.items():
        entries.append(_entry(
            f"npc:station:{city}", npc_name, "人物",
            f"设于{city}，负责驿站事务及路线信息。", aliases=[city + "驿丞"],
            lines=[f"所在地点：{city}", "职能：驿站事务、城市导航与地点信息"],
        ))
    for city, npc_name in intel_dealers.items():
        entries.append(_entry(
            f"npc:intel:{city}", npc_name, "人物",
            f"设于{city}，提供商品行情情报。", aliases=[city + "情报贩子"],
            lines=[f"所在地点：{city}", "职能：查询本集群及邻近城市物价与跑商建议"],
        ))

    from ..guild_boss.config import BLOOD_BOSS_POOL, BOSS_POOL as GUILD_BOSS_POOL

    for boss in [*GUILD_BOSS_POOL, *BLOOD_BOSS_POOL]:
        requirements = []
        if boss.get("min_ferocity"):
            requirements.append(f"最低凶戾度：{boss['min_ferocity']}")
        if boss in BLOOD_BOSS_POOL:
            requirements.append("血祭邪坛专属诡异池")
        entries.append(_entry(
            f"guild_boss:{boss['name']}", boss["name"], "首领",
            f"公会镇诡首领，称号：{boss['title']}。", aliases=[boss["title"]],
            lines=requirements,
        ))

    return entries


def dungeon_entry(depth: int) -> dict:
    """按真实诡域生成配置展示深度信息，不展开动态怪物属性。"""
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        raise ValueError("诡域深度必须是正整数")

    rules = config.map_config.get("dungeon_generation_rules", {})
    level = config._generate_dungeon_level_config(depth, rules)

    def material_names(item_ids: list[str]) -> list[str]:
        names = []
        for item_id in item_ids:
            item = config.items_config["by_id"].get(item_id)
            names.append(_item_link(item_id) if item else item_id)
        return names

    level_range = level["level_range"]
    lines = [
        f"诡异等级范围：{level_range[0]}-{level_range[1]}",
        f"理智消耗：{level['mp_cost']}",
        "基础材料：" + ("、".join(material_names(level.get("basic_materials", []))) or "无"),
        "商人材料：" + ("、".join(material_names(level.get("merchant_materials", []))) or "无"),
    ]
    return _entry(
        f"dungeon:{depth}", f"{depth}层诡域", "地点",
        f"诡域深度资料；怪物等级范围{level_range[0]}-{level_range[1]}，每次探索的怪物组合以实际生成结果为准。",
        aliases=[f"诡域{depth}", f"第{depth}层"], lines=lines,
    )
