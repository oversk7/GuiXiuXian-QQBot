"""百科的获取来源和升阶用途：读取游戏服务正在使用的定义，不查询库存。"""
from ..config import config
from ..utils_markdown import cmd


def source_lines(item_id: str) -> list[str]:
    from ..economy import merchant_service as merchants
    from ..quest.novice_quest_service import NoviceQuestService

    item = config.items_config["by_id"].get(item_id)
    if item is None:
        return []
    lines = []
    for market in merchants.MARKETS:
        if market.can_sell_to_player(item_id):
            lines.append(f"市集购买：{market.name}（{market.x}, {market.y}）；价格与库存见{cmd('市集')}。")
    if item_id in merchants.SHOP_ITEMS:
        lines.append(f"黑市基础商品；价格与库存见{cmd('黑市')}。")
    if item_id in merchants.SEASONING_SHOP_ITEMS:
        lines.append(f"食材铺出售；详情见{cmd('食材铺')}。")
    if item_id in merchants.BLACK_MARKET_CANDIDATES:
        lines.append(f"黑市轮换候选商品，不保证今日上架；见{cmd('黑市')}。")
    if item_id in merchants.HEADQUARTERS_ITEMS:
        lines.append(f"缉邪司总部兑换：{merchants.HEADQUARTERS_ITEMS[item_id]} 积分。")

    rules = config.map_config.get("dungeon_generation_rules", {})
    for span, materials in rules.get("material_tiers", {}).items():
        channels = []
        if item_id in materials.get("basic_materials", []):
            channels.append("基础材料采集池")
        if item_id in materials.get("merchant_materials", []):
            channels.append("诡域商人材料池")
        if channels:
            # 999 是现有材料分档表的实际上界；更深层使用服务的默认池。
            lines.append(f"{span} 重诡域：{'、'.join(channels)}。")
    # 当前配置仅覆盖到999；更深层按实际函数回退，不误报为最高档无限延伸。
    ranges = [int(str(span).split('-')[1]) for span in rules.get('material_tiers', {})
              if '-' in str(span) and str(span).split('-')[1].isdigit()]
    if ranges:
        end = max(ranges)
        merchant_pool, basic_pool = config._get_materials_for_level(end + 1, rules)
        if item_id in merchant_pool or item_id in basic_pool:
            pool = "、".join(label for ids, label in ((merchant_pool, '商人材料池'), (basic_pool, '基础材料池')) if item_id in ids)
            lines.append(f"{end + 1} 重及以上诡域：{pool}。")
    from ..world.dungeon_generation_service import get_materials_by_rarity
    if item_id in get_materials_by_rarity(item.rarity):
        if item.rarity in ('green', 'blue', 'purple'):
            lines.append("诡域战斗同品质补充池：怪物等级开放该品质、且当地商人材料池缺少该品质时可能掉落；具体可查指定深度图鉴。")
        if item.rarity in ('green', 'blue', 'purple', 'orange'):
            lines.append("诡域商人随机补充商品：随诡域档位选择品质，不保证每次上架；具体可查指定深度图鉴。")
    from ..world.dungeon_generation_service import (
        FRAGMENT_ITEM_ID, FRAGMENT_DROP_RATE, TREASURE_MATERIAL_ITEM_ID, TREASURE_MATERIAL_CHANCE,
    )
    if item_id == TREASURE_MATERIAL_ITEM_ID and TREASURE_MATERIAL_CHANCE > 0:
        lines.append("诡域手动探索宝箱格独立材料奖励；扫荡不包含宝箱格。")
    if item_id == FRAGMENT_ITEM_ID and FRAGMENT_DROP_RATE > 0:
        lines.append("诡域精英怪独立掉落的铭文碎片，不依赖普通材料品质池。")
    drop = getattr(item, "dungeon_drop", None)
    if drop:
        lower = drop['min_level']
        upper = drop.get('max_level')
        span = f"Lv.{lower}～{upper}" if upper is not None else f"Lv.{lower}及以上"
        lines.append(f"诡域怪物额外装备掉落池：{span}；精英怪概率更高。")

    from ..guild_boss.config import BLOOD_RELIC_ITEM_ID, BLOOD_RELIC_TOP_N
    if item_id == BLOOD_RELIC_ITEM_ID:
        lines.append(f"公会血祭·邪坛镇压成功，伤害前{BLOOD_RELIC_TOP_N}名获得；见{cmd('镇诡帮助')}。")

    from ..fishing.service import FishingService

    for pool, label in ((FishingService.FISH_RARITY_CONFIG, '现实世界垂钓'),
                        (FishingService.GHOST_FISH_RARITY_CONFIG, '诡域垂钓')):
        if any(item_id in tier['fish_list'] for tier in pool.values()):
            lines.append(f"{label}鱼池；见{cmd('钓鱼')}。")
    for city, fish_id in FishingService.COASTAL_FISHING_SPOTS.items():
        if fish_id == item_id:
            lines.append(f"{city}沿海特色钓点专属鱼；需在钓点范围内垂钓。")
    for pool, label in ((FishingService.REAL_WORLD_SALVAGE_POOL, '现实世界'),
                        (FishingService.DUNGEON_SALVAGE_POOL, '诡域')):
        if any(entry[0] == item_id for entry in pool):
            lines.append(f"{label}钓鱼打捞池（概率获得）。")

    for chain in NoviceQuestService._load_quest_config().get("chains", []):
        for step in chain.get("steps", []):
            for reward in step.get("rewards", {}).get("items", []):
                if reward.get("item_id") == item_id:
                    lines.append(f"新手任务「{chain['name']}·{step['title']}」奖励 ×{reward.get('quantity', 1)}。")
        for reward in chain.get("completion_reward", {}).get("items", []):
            if reward.get("item_id") == item_id:
                lines.append(f"新手任务章节「{chain['name']}」完成奖励 ×{reward.get('quantity', 1)}。")
    return list(dict.fromkeys(lines))


def upgrade_use_lines(item_id: str) -> list[str]:
    from .equipment_upgrade_service import EquipmentUpgradeService, _load_upgrade_config

    tables = _load_upgrade_config().get("materials", {})
    # 只显示当前确实有装备采用的材料档位，避免把预留表当作开放玩法。
    tier_names: dict[str, list[str]] = {}
    for item in config.items_config["by_id"].values():
        if getattr(item.type, 'value', item.type) != 'EQUIPMENT':
            continue
        tier = "normal" if item.recipe else EquipmentUpgradeService._get_rare_material_tier(item)
        if tier not in tables:
            tier = 'normal'
        tier_names.setdefault(tier, []).append(item.name)
    lines = []
    for tier, names in tier_names.items():
        levels = [(level, costs[item_id]) for level, costs in tables[tier].items() if costs.get(item_id, 0)]
        if not levels:
            continue
        example = '、'.join(names[:3]) + ('等装备' if len(names) > 3 else '')
        amounts = '、'.join(f'{level}阶×{count}' for level, count in levels)
        lines.append(f"用于{example}升阶：{amounts}；实际消耗见{cmd('升阶信息 编号', '升阶信息 ')}。")
    return lines
