"""世界BOSS系统配置文件

包含BOSS池、奖励配置、平衡性参数等
"""

from typing import Dict, List, Tuple, Any

# BOSS池配置
BOSS_POOL = [
    {
        "name": "巴虺",
        "title": "深渊之蛇·无尽吞噬者",
        "description": "盘踞于深渊裂隙中的古老巨蛇，其鳞片如黑曜石般闪烁着不祥的光芒。传说它能吞噬整个世界的光明，将一切拖入永恒的黑暗。",
        "element": "darkness",
        "difficulty": 5
    },
    {
        "name": "黑太岁",
        "title": "腐朽之王·时间侵蚀者", 
        "description": "从时间深处爬出的腐朽存在，身躯由无数腐烂的肉块拼接而成。它的存在本身就是对现实的亵渎，每一次呼吸都在腐蚀着周围的时空。",
        "element": "decay",
        "difficulty": 6
    },
    {
        "name": "夜魇之母",
        "title": "梦境支配者·恐惧编织者",
        "description": "栖息在梦境与现实交界处的恐怖存在，拥有无数触手和眼球。它以恐惧为食，将噩梦编织成现实的枷锁。",
        "element": "nightmare",
        "difficulty": 5
    },
    {
        "name": "深海咏者",
        "title": "深渊传道者·疯狂低语者",
        "description": "来自深海最深处的古老祭司，身躯半鱼半人，口中不断吟唱着令人疯狂的古老咒文。其歌声能够扭曲现实，将理智拖入深渊。",
        "element": "madness",
        "difficulty": 4
    },
    {
        "name": "虚空行者",
        "title": "次元撕裂者·现实扭曲者",
        "description": "游荡在维度裂缝中的无形存在，只有在攻击时才会显现出扭曲的轮廓。它的每一次移动都在撕裂空间，留下无法愈合的虚空伤痕。",
        "element": "void",
        "difficulty": 7
    },
    {
        "name": "血肉教主",
        "title": "生命亵渎者·血肉重塑者",
        "description": "由无数生灵的血肉融合而成的邪恶存在，身躯不断变化着形态。它能够重塑生命的本质，将一切生物扭曲成自己的奴仆。",
        "element": "flesh",
        "difficulty": 6
    }
]

# 攻击限制配置
ATTACK_CONFIG = {
    "daily_limit": 3,           # 每日攻击次数限制
    "cooldown_seconds": 1,      # 攻击冷却时间（秒）
    "reset_hour": 20,           # 每日重置时间（小时）
    "max_rounds": 30            # 战斗最大回合数
}

# 刷新时间配置
REFRESH_CONFIG = {
    "weekdays": [2, 5],         # 刷新日期（0=周一，2=周三，5=周六）
    "hour": 20,                 # 刷新小时
    "minute": 0                 # 刷新分钟
}

# 理智削减配置
SANITY_DAMAGE_CONFIG = {
    "low_level_threshold": 50,  # 低等级阈值
    "low_level_fixed_damage": (40, 80),  # 低等级固定伤害范围
    "high_level_percentage": (0.10, 0.20),  # 高等级百分比伤害范围
}

# 奖励区间配置
REWARD_TIERS = [
    {
        "rank_range": (1, 1),
        "chest": "深渊霸主宝箱",
        "chest_id": "abyss_overlord_chest",
        "description": "🏆 第1名",
        "rarity": "legendary"
    },
    {
        "rank_range": (2, 3),
        "chest": "深渊王者宝箱",
        "chest_id": "abyss_king_chest",
        "description": "🥈 第2-3名",
        "rarity": "epic"
    },
    {
        "rank_range": (4, 10),
        "chest": "深渊勇士宝箱",
        "chest_id": "abyss_warrior_chest",
        "description": "🥉 第4-10名",
        "rarity": "rare"
    },
    {
        "rank_range": (11, 30),
        "chest": "深渊探索者宝箱",
        "chest_id": "abyss_explorer_chest",
        "description": "🎖️ 第11-30名",
        "rarity": "uncommon"
    },
    {
        "rank_range": (31, 100),
        "chest": "深渊挑战者宝箱",
        "chest_id": "abyss_challenger_chest",
        "description": "🏅 第31-100名",
        "rarity": "common"
    },
    {
        "rank_range": (101, 999999),
        "chest": "深渊参与者宝箱",
        "chest_id": "abyss_participant_chest",
        "description": "🎁 参与奖",
        "rarity": "common"
    }
]

# BOSS属性计算配置（简化版）
BOSS_STATS_CONFIG = {
    "defense_variance": (0.9, 1.1),  # 防御力波动范围
    "agility_variance": (0.9, 1.1),  # 敏捷波动范围
    "default_defense": 100,           # 默认防御力
    "default_agility": 80             # 默认敏捷
}

# 伤害计算配置
DAMAGE_CONFIG = {
    "variance_ratio": 0.25,         # 伤害波动比例
    "luck_multiplier": 2,           # 运气加成倍数
    "min_damage": 1                 # 最小伤害
}

# 战斗描述文本池
BATTLE_FLAVOR_TEXTS = [
    "🌀 {boss_name}的触手在虚空中扭动，散发着令人不安的气息...",
    "👁️ 无数眼球注视着你，仿佛要将你的灵魂拖入深渊...",
    "🌊 扭曲的现实在你周围波动，理智在疯狂的边缘摇摆...",
    "⚡ 古老的力量在空气中激荡，每一击都撼动着维度的壁垒...",
    "🔮 虚无的低语在你耳边回响，诉说着不可名状的真理...",
    "🌙 月光在{boss_name}的身躯上扭曲，形成诡异的阴影...",
    "💀 死亡的气息从深渊中涌出，侵蚀着生者的意志...",
    "🕳️ 空间在{boss_name}面前颤抖，现实的边界变得模糊...",
    "🩸 鲜血在虚空中凝结，化作不祥的符文...",
    "🌪️ 混沌的风暴围绕着战场，吞噬着一切光明..."
]

# 宝箱开启描述文本池
CHEST_FLAVOR_TEXTS = [
    "🌀 宝箱中散发出深渊的气息，仿佛在低语着古老的秘密...",
    "👁️ 无数眼球在宝箱内闪烁，见证着你的收获...",
    "🔮 扭曲的能量从宝箱中涌出，化作珍贵的奖励...",
    "⚡ 虚空的力量凝聚成实体，成为你战斗的助力...",
    "🌊 深渊的馈赠降临，带来不可名状的力量...",
    "💎 宝箱内的光芒扭曲着现实，将虚无化为珍宝...",
    "🌙 月光透过宝箱的缝隙，照亮了隐藏的宝藏...",
    "🕳️ 虚空的裂缝中涌出奖励，跨越了时空的界限...",
    "🔥 深渊之火燃烧着宝箱，锻造出珍贵的物品...",
    "❄️ 冰冷的触感从宝箱中传来，带着远古的力量..."
]

# 系统消息配置
SYSTEM_MESSAGES = {
    "boss_spawn": "🌟 新的世界BOSS已降临！{boss_name} 等待着勇士们的挑战！",
    "cycle_settled": "⚔️ {boss_name} 的威胁已结束！共有 {reward_count} 名勇士获得了深渊宝箱奖励！",
    "no_participants": "⚰️ {boss_name} 消散在虚空中，无人获得其力量...",
    "attack_success": "⚔️ 你向 {boss_name} 发起了攻击！",
    "damage_dealt": "💥 造成伤害：{damage:,}",
    "total_damage": "📊 累计伤害：{total_damage:,}",
    "remaining_attacks": "🎯 剩余攻击次数：{remaining}/{total}",
    "sanity_lost": "🧠 你的理智受到了 {damage} 点侵蚀！({old_mp} → {new_mp})",
    "sanity_collapse": "💀 你的理智彻底崩溃，陷入了永恒的疯狂"
}

# 错误消息配置
ERROR_MESSAGES = {
    "no_character": "⛔ 请先创建角色",
    "attacks_exhausted": "⛔ 今日攻击次数已用完！明日20:00重置（{current}/{total}）",
    "cooldown_active": "⏰ 攻击冷却中，请等待 {seconds} 秒",
    "player_dead": "💀 你已重伤倒地，无法参与战斗！请先恢复生命值",
    "no_chests": "⛔ 你没有任何深渊宝箱可以开启",
    "chest_not_found": "⛔ 找不到指定的宝箱，请检查名称或序号",
    "chest_config_error": "⛔ 宝箱配置错误",
    "open_chest_failed": "⛔ 开启失败：{reason}"
}

def get_boss_by_name(name: str) -> Dict[str, Any]:
    """根据名称获取BOSS配置"""
    for boss in BOSS_POOL:
        if boss["name"] == name:
            return boss
    return {}

def get_reward_tier_by_rank(rank: int) -> Dict[str, Any]:
    """根据排名获取奖励等级"""
    for tier in REWARD_TIERS:
        if tier["rank_range"][0] <= rank <= tier["rank_range"][1]:
            return tier
    return REWARD_TIERS[-1]  # 返回参与奖

def get_random_flavor_text(text_pool: List[str], **kwargs) -> str:
    """获取随机的描述文本"""
    import random
    text = random.choice(text_pool)
    return text.format(**kwargs)

def get_battle_flavor_text(boss_name: str) -> str:
    """获取战斗描述文本"""
    return get_random_flavor_text(BATTLE_FLAVOR_TEXTS, boss_name=boss_name)

def get_chest_flavor_text() -> str:
    """获取宝箱开启描述文本"""
    return get_random_flavor_text(CHEST_FLAVOR_TEXTS)
