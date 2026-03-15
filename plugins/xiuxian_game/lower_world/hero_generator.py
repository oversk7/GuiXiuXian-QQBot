"""
下位世界英雄生成器
根据玩家等级和当前波次，生成对应强度的英雄
"""
import random
import json
from typing import Dict

# ==================== 数据池 ====================

KINGDOMS = [
    "莱纳斯王国", "阿尔托帝国", "圣光教廷", "银月联盟",
    "东境共和国", "龙脊山城邦", "碧海商会", "暮光公国",
]

FIRST_NAMES = [
    "艾伦", "莱昂哈特", "席拉", "伊莲娜", "托尔",
    "芙蕾雅", "奥尔加", "克劳德", "米雷亚", "赛勒斯",
    "艾莉丝", "加文", "罗伦", "薇薇安", "赫克托",
]

# 普通英雄（1-10波）
NORMAL_HERO_CLASSES = [
    {"title": "骑士", "flavour_pool": [
        "他加入骑士团已经十年，从未想过有一天会面对这种存在。",
        "她的盾牌上刻着父亲的名字，那是家族三代人的传承。",
        "他在出发前，把仅剩的积蓄寄回了老家的妻子那里。",
    ]},
    {"title": "圣女", "flavour_pool": [
        "她以为祈祷能带来庇护。来了以后，她只是沉默地握紧了权杖。",
        "教会说这是神圣的试炼。她不知道神有没有在看。",
        "她今年十七岁，是本届最年轻的圣女候选人。",
    ]},
    {"title": "魔导士", "flavour_pool": [
        "他花了二十年研究魔法，没想到第一次实战是这种场合。",
        "她的导师说：力量是为了保护。她一直记着这句话。",
        "他带来了三本魔法书，出发前烧掉了其中两本——减轻重量。",
    ]},
    {"title": "骑士团长", "flavour_pool": [
        "她带领三百骑士出征，只有她一个人走到了这里。",
        "他说不害怕是假的。但他是团长，他不能表现出来。",
        "她在出发前，对着部下说：你们回去。剩下的交给我。",
    ]},
    {"title": "龙骑士", "flavour_pool": [
        "他的坐骑在两天前落下了，他一个人走完了剩下的路。",
        "她和龙一起长大，现在龙不在了，她感觉少了一半的自己。",
        "他说：龙不需要理由，人才需要。他的理由是：我的孩子还等着我回去。",
    ]},
    {"title": "大法师", "flavour_pool": [
        "他活了九十七岁，见过太多东西。见过这个，还是第一次。",
        "她的魔力已经快耗尽了。她知道，但她没有退路。",
        "他带着一个任务：弄清楚天灾是什么。他现在站在这里，还是不明白。",
    ]},
]

# 勇者系（11波以上）
HERO_CLASSES = [
    {
        "title": "剑勇者",
        "atk_mult": 1.4, "def_mult": 1.0, "agi_mult": 1.1, "hp_mult": 1.0,
        "crit_rate": 20,
        "flavour_pool": [
            "召唤仪式结束时，他还穿着打铁的围裙。",
            "她说：我不想当英雄。但没有人问过她。",
            "他接过圣剑时，手在抖。没有人知道，因为他一直握得很紧。",
        ],
    },
    {
        "title": "盾勇者",
        "atk_mult": 0.7, "def_mult": 2.0, "agi_mult": 0.8, "hp_mult": 1.5,
        "crit_rate": 5,
        "flavour_pool": [
            "盾是最重的武器，她扛着它走了三天三夜。",
            "他们说盾勇者是最弱的。他默默记住了每一个说这话的人的名字。",
            "她的盾上有一道裂缝，那是上一个天灾留下的。",
        ],
    },
    {
        "title": "枪勇者",
        "atk_mult": 1.1, "def_mult": 0.9, "agi_mult": 1.5, "hp_mult": 1.0,
        "combo_rate": 25,
        "flavour_pool": [
            "他在马戏团学过杂技，现在枪法比任何人都快。",
            "她的目标是：活着回去，然后再也不来。",
            "他说：快比力气更重要。他活到现在，靠的就是这个。",
        ],
    },
    {
        "title": "弓勇者",
        "atk_mult": 1.2, "def_mult": 0.8, "agi_mult": 1.3, "hp_mult": 0.9,
        "ignore_defense": 20,
        "flavour_pool": [
            "她从小在山里长大，学会射箭比学会说话还早。",
            "他在最远的距离命中过目标，但那次他的手没有抖。这次抖了。",
            "她的箭只剩三支了。她数过，够了。",
        ],
    },
    {
        "title": "棍勇者",
        "atk_mult": 1.0, "def_mult": 1.0, "agi_mult": 1.0, "hp_mult": 1.2,
        "counter_rate": 20,
        "flavour_pool": [
            "他的棍法来自一个游方僧，那个僧人说：棍是生命的节拍。",
            "她一个人打败过一整队山贼，现在面对的是另一个量级。",
            "他说他不害怕。他媳妇说：你脸都白了。他说：那只是光线问题。",
        ],
    },
    {
        "title": "炮勇者",
        "atk_mult": 1.6, "def_mult": 0.8, "agi_mult": 0.5, "hp_mult": 1.1,
        "crit_rate": 10,
        "flavour_pool": [
            "她的大炮重两百斤，她一个人扛着走来的。",
            "他研究火药三十年，第一次把成果用在这种地方。",
            "她说：我只需要命中一次。一次就够了。",
        ],
    },
    {
        "title": "书勇者",
        "atk_mult": 1.0, "def_mult": 1.0, "agi_mult": 1.0, "hp_mult": 1.0,
        "flavour_pool": [
            "他翻遍了所有古籍，没有找到天灾的记录。所以他来亲眼看看。",
            "她的书里夹着一张纸，上面写着她女儿的名字。",
            "他说：知识是最强的武器。她同伴说：你先把书放下，举起剑。",
        ],
    },
    {
        "title": "镰勇者",
        "atk_mult": 1.1, "def_mult": 0.9, "agi_mult": 1.1, "hp_mult": 1.0,
        "lifesteal": 15,
        "flavour_pool": [
            "她的镰刀是从一个死神那里抢来的，那个死神比她还弱。",
            "他说他不怕死，因为他已经死过一次了。",
            "她越打越勇，血越少力气越大——没有人知道为什么，包括她自己。",
        ],
    },
]


# 词缀池（21+波勇者专属强化）
AFFIXES = [
    {
        "id": "sacred",
        "prefix": "神圣加护的",
        "hp_mult": 1.3, "atk_mult": 1.2,
        "flavour_suffix": "圣光在{pronoun}身上燃得格外炽烈，像是神明亲自在场。",
    },
    {
        "id": "berserk",
        "prefix": "狂暴之怒附身的",
        "atk_mult": 1.3, "def_mult": 0.7,
        "flavour_suffix": "{pronoun}的眼睛红了，理智在燃烧中渐渐消退。",
    },
    {
        "id": "guardian",
        "prefix": "守护之志加身的",
        "def_mult": 1.8, "hp_mult": 1.2, "atk_mult": 0.7,
        "flavour_suffix": "{pronoun}背后仿佛有千万人在看着，那些人不能倒。",
    },
    {
        "id": "swift",
        "prefix": "疾风加持的",
        "agi_mult": 1.8,
        "combo_rate": 20,
        "flavour_suffix": "{pronoun}的速度快到影子跟不上，像风一样来了又走。",
    },
    {
        "id": "divine",
        "prefix": "神明祝福降临的",
        "hp_mult": 1.2, "atk_mult": 1.2, "def_mult": 1.2, "agi_mult": 1.2,
        "flavour_suffix": "有什么东西在{pronoun}的血液里流动——那不是{pronoun}自己的力量。",
    },
    {
        "id": "cursed",
        "prefix": "诅咒之刃缠绕的",
        "atk_mult": 1.3,
        "lifesteal": 25,
        "flavour_suffix": "{pronoun}的伤口不会流血，失去的力气会以另一种方式回来。",
    },
    {
        "id": "veteran",
        "prefix": "百战不死的",
        "hp_mult": 1.1, "atk_mult": 1.1, "def_mult": 1.1, "agi_mult": 1.1,
        "counter_rate": 20,
        "flavour_suffix": "{pronoun}见过太多，早已知道什么招数接什么招数。",
    },
    {
        "id": "desperate",
        "prefix": "破釜沉舟的",
        "atk_mult": 1.3, "hp_mult": 0.7,
        "crit_rate": 25,
        "flavour_suffix": "{pronoun}把退路全堵死了——赢了回家，输了就在这里。",
    },
]


def apply_affixes(stats: dict, affixes: list) -> dict:
    """将词缀叠加应用到属性上"""
    result = dict(stats)
    for affix in affixes:
        for key in ("hp_mult", "atk_mult", "def_mult", "agi_mult"):
            attr = key.replace("_mult", "")
            attr_map = {"hp": "hp", "atk": "attack", "def": "defense", "agi": "agility"}
            real_key = attr_map.get(attr, attr)
            if key in affix and real_key in result:
                result[real_key] = int(result[real_key] * affix[key])
        # 特殊战斗属性（叠加取较大值，不重复累加）
        for special in ("crit_rate", "combo_rate", "counter_rate", "lifesteal", "ignore_defense"):
            if special in affix:
                result[special] = max(result.get(special, 0), affix[special])
    return result


def calculate_hero_level(player_level: int, wave_number: int) -> int:
    """
    计算英雄等级：
    - 1-20波：线性增长 0.6 + 波次 × 0.03
    - 21+波：对数减速增长，避免数值爆炸
    """
    if wave_number <= 20:
        ratio = 0.6 + wave_number * 0.03
    else:
        # 20波时 ratio=1.2，之后每10波约增长0.15，逐步放缓
        import math
        base_ratio = 1.2
        extra = math.log(1 + (wave_number - 20) / 10) * 0.5
        ratio = base_ratio + extra
    return max(1, int(player_level * ratio))


def calculate_hero_stats(hero_level: int, hero_class: Dict) -> Dict:
    """根据英雄等级和职业计算属性"""
    stats = {
        "hp": int(hero_level * 42 * hero_class.get("hp_mult", 1.0)),
        "attack": int(hero_level * 3.8 * hero_class.get("atk_mult", 1.0)),
        "defense": int(hero_level * 1.5 * hero_class.get("def_mult", 1.0)),
        "agility": int(hero_level * 1.2 * hero_class.get("agi_mult", 1.0)),
    }
    for key in ("crit_rate", "combo_rate", "counter_rate", "lifesteal", "ignore_defense"):
        if key in hero_class:
            stats[key] = hero_class[key]
    return stats


def generate_hero(player_level: int, wave_number: int) -> Dict:
    """
    生成一个英雄，返回包含完整信息的字典。

    Returns:
        {
            "name": str,      # 如"莱纳斯王国召唤的剑勇者·艾伦"
            "title": str,     # 如"剑勇者"
            "level": int,
            "hp": int, "attack": int, "defense": int, "agility": int,
            "flavour": str,   # 一句话背景
            "affixes": list,  # 词缀列表（21+波才有）
            ... 其他特殊属性
        }
    """
    hero_level = calculate_hero_level(player_level, wave_number)
    kingdom = random.choice(KINGDOMS)
    name_part = random.choice(FIRST_NAMES)

    if wave_number <= 10:
        hero_class = random.choice(NORMAL_HERO_CLASSES)
        full_name = f"{kingdom}的{hero_class['title']}·{name_part}"
    else:
        hero_class = random.choice(HERO_CLASSES)
        full_name = f"{kingdom}召唤的{hero_class['title']}·{name_part}"

    stats = calculate_hero_stats(hero_level, hero_class)
    flavour = random.choice(hero_class["flavour_pool"])

    # 21+波：随机附加词缀强化
    selected_affixes = []
    affix_names = []
    if wave_number > 20:
        # 波次越高词缀越多：21-30波1个，31+波2个
        affix_count = 2 if wave_number > 30 else 1
        selected_affixes = random.sample(AFFIXES, min(affix_count, len(AFFIXES)))
        stats = apply_affixes(stats, selected_affixes)
        affix_names = [a["prefix"] for a in selected_affixes]

        # 在名字前加词缀修饰
        prefix_str = "、".join(affix_names)
        full_name = f"{prefix_str}{full_name}"

        # 添加词缀flavour（检测代词）
        _female = {"席拉", "伊莲娜", "芙蕾雅", "奥尔加", "米雷亚", "艾莉丝", "薇薇安"}
        pron = "她" if any(fn in name_part for fn in _female) else "他"
        affix_flavour = "　".join(
            a["flavour_suffix"].format(pronoun=pron) for a in selected_affixes
        )
        flavour = f"{flavour}\n{affix_flavour}"

    return {
        "name": full_name,
        "title": hero_class["title"],
        "level": hero_level,
        "flavour": flavour,
        "affixes": affix_names,
        **stats,
    }


def hero_to_json(hero: Dict) -> str:
    return json.dumps(hero, ensure_ascii=False)


def hero_from_json(data: str) -> Dict:
    return json.loads(data)
