"""
等级功能解锁提示系统

当玩家升级或突破到特定等级时,提示可以使用的新功能
"""

from typing import Optional

# 等级区间到功能解锁的映射
# 格式: (最低等级, 最高等级): (标题, [功能列表])
LEVEL_UNLOCK_MAP = {
    (1, 9): (
        "🌱 初入江湖 (Lv.1-9)",
        [
            "⚔️ 【修炼】提升等级",
            "💼 【打工】赚取金币",
            "🛒 【市场】买卖物品",
            "📍 【查看】探索位置",
            "🎁 【签到】每日奖励"
        ]
    ),
    (10, 29): (
        "⚡ 略有小成 (Lv.10-29)",
        [
            "🗺️ 【导航 x y】自动移动",
            "🔍 【查找 NPC】搜索NPC",
            "📍 【前往 地点】快速导航",
            "⚔️ 【攻击 目标】PVP战斗",
            "🏪 【购买 物品】交易物品"
        ]
    ),
    (30, 59): (
        "🔥 渐入佳境 (Lv.30-59)",
        [
            "📜 【委托】接取每日任务",
            "🏰 【诡域列表】探索副本",
            "⚒️ 【锻造】升级装备",
            "💎 【镶嵌】装备宝石系统",
            "🏛️ 【建筑列表】查看公会建筑"
        ]
    ),
    (60, 99): (
        "⚔️ 小有名气 (Lv.60-99)",
        [
            "☯️ 【创建公会】建立势力",
            "🏦 【银行】存款理财",
            "📈 【股票】投资系统",
            "💍 【求婚】社交系统",
            "🏠 【阴宅】购买府邸"
        ]
    ),
    (100, 199): (
        "🌟 名震一方 (Lv.100-199)",
        [
            "🔄 【转生】突破境界",
            "🎁 【赠礼】赠送礼物",
            "👨‍🏫 【收徒】师徒系统",
            "🎲 【钓鱼】休闲玩法",
            "📖 【剧情】探索故事"
        ]
    ),
    (200, 999): (
        "💫 天下无双 (Lv.200+)",
        [
            "🌍 【世界BOSS】挑战强敌",
            "🏆 【排行榜】查看排名",
            "💬 【留言板】世界聊天",
            "🎭 【AI对话】智能NPC",
            "🔮 【秘境探索】高级副本"
        ]
    ),
}


def get_feature_unlock_message(new_level: int, old_level: int = None) -> Optional[str]:
    """
    根据新等级生成功能解锁提示消息

    Args:
        new_level: 当前等级
        old_level: 突破前等级(可选),用于判断是否跨区间

    Returns:
        功能解锁提示消息,如果没有跨区间则返回None
    """
    # 找到新等级对应的区间
    new_range = None
    old_range = None

    for (min_lv, max_lv), (title, features) in LEVEL_UNLOCK_MAP.items():
        if min_lv <= new_level <= max_lv:
            new_range = ((min_lv, max_lv), (title, features))
        if old_level and min_lv <= old_level <= max_lv:
            old_range = ((min_lv, max_lv), (title, features))

    # 如果没有找到新区间,或者新旧区间相同,则不提示
    if not new_range:
        return None

    if old_level and old_range and old_range[0] == new_range[0]:
        return None

    # 生成提示消息
    (min_lv, max_lv), (title, features) = new_range

    msg = f"\n━━━━━━━━━━━━━\n"
    msg += f"🎉 {title} 功能解锁！\n"
    msg += "━━━━━━━━━━━━━\n"

    for feature in features:
        msg += f"{feature}\n"

    msg += "━━━━━━━━━━━━━\n"
    msg += "💡 输入【帮助】查看所有命令"

    return msg


def get_breakthrough_unlock_message(new_level: int, old_level: int) -> Optional[str]:
    """
    突破时的功能解锁提示(简化版)

    只在跨越等级区间时提示核心功能
    """
    # 找到是否跨越区间
    new_range_key = None
    old_range_key = None

    for (min_lv, max_lv) in LEVEL_UNLOCK_MAP.keys():
        if min_lv <= new_level <= max_lv:
            new_range_key = (min_lv, max_lv)
        if min_lv <= old_level <= max_lv:
            old_range_key = (min_lv, max_lv)

    # 没有跨区间,不提示
    if not new_range_key or new_range_key == old_range_key:
        return None

    title, features = LEVEL_UNLOCK_MAP[new_range_key]

    # 突破时只提示前3个核心功能
    msg = f"\n━━━━━━━━━━━━━\n"
    msg += f"✨ 恭喜突破！{title}\n"
    msg += "━━━━━━━━━━━━━\n"
    msg += "🎯 解锁新功能：\n"

    for feature in features[:3]:  # 只显示前3个
        msg += f"{feature}\n"

    if len(features) > 3:
        msg += f"...还有 {len(features) - 3} 个功能\n"

    msg += "━━━━━━━━━━━━━\n"
    msg += "💡 【帮助】查看完整功能"

    return msg
