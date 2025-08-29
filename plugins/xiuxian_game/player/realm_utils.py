"""
境界系统工具模块
包含境界名称计算和显示相关的工具函数
"""

REALM_NAMES = [
    "凡人",
    "腐体境",
    "血咒境",
    "怨魂境",
    "阴祟境",
    "鬼啸境",
    "恐魇境",
    "绝念境",
    "诡天境",
    "灾厄境",
    # 一转境界（300-500级）
    "冥返境",
    "轮回境", 
    "涅槃境",
    # 二转境界（500-1000级）
    "虚无境",
    "混沌境",
    "太初境",
    "无极境",
    "永恒境",
    # 三转及以上境界（1000级+）
    "超脱境",
    "至尊境",
    "神话境",
    "传说境",
    "不朽境",
    "万古境",
    "无上境",
]

REALM_THRESHOLDS = [
    20, 40, 60, 80, 100, 130, 160, 190, 250, 300,
    # 一转境界阈值
    350, 400, 500,
    # 二转境界阈值  
    600, 700, 800, 900, 1000,
    # 三转及以上境界阈值
    1200, 1400, 1600, 1800, 2000, 2500, 3000
]

def number_to_chinese(num: int) -> str:
    """将阿拉伯数字转换为中文数字"""
    if num == 0:
        return "零"

    # 中文数字映射
    chinese_digits = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]

    if num < 10:
        return chinese_digits[num]
    elif num < 20:
        if num == 10:
            return "十"
        else:
            return "十" + chinese_digits[num % 10]
    elif num < 100:
        tens = num // 10
        ones = num % 10
        if ones == 0:
            return chinese_digits[tens] + "十"
        else:
            return chinese_digits[tens] + "十" + chinese_digits[ones]
    elif num < 1000:
        hundreds = num // 100
        remainder = num % 100
        result = chinese_digits[hundreds] + "百"
        if remainder == 0:
            return result
        elif remainder < 10:
            return result + "零" + chinese_digits[remainder]
        else:
            return result + number_to_chinese(remainder)
    elif num < 10000:
        thousands = num // 1000
        remainder = num % 1000
        result = chinese_digits[thousands] + "千"
        if remainder == 0:
            return result
        elif remainder < 100:
            return result + "零" + number_to_chinese(remainder)
        else:
            return result + number_to_chinese(remainder)
    else:
        # 处理万以上的数字
        wan = num // 10000
        remainder = num % 10000
        result = number_to_chinese(wan) + "万"
        if remainder == 0:
            return result
        elif remainder < 1000:
            return result + "零" + number_to_chinese(remainder)
        else:
            return result + number_to_chinese(remainder)

def realm_by_level(level: int) -> str:
    """根据等级返回境界名称"""
    for idx, cap in enumerate(REALM_THRESHOLDS):
        if level <= cap:
            return REALM_NAMES[idx]
    
    # 如果超过所有预设阈值，使用动态境界名称
    if level > REALM_THRESHOLDS[-1]:
        # 计算超出的等级段
        excess_level = level - REALM_THRESHOLDS[-1]
        tier = (excess_level - 1) // 500 + 1  # 每500级一个新境界
        
        # 超越境界名称
        transcendent_realms = [
            "破天境", "逆天境", "弑神境", "创世境", "主宰境",
            "至高境", "终极境", "无限境", "永恒境", "绝对境"
        ]
        
        if tier <= len(transcendent_realms):
            return transcendent_realms[tier - 1]
        else:
            # 如果连超越境界都不够用，显示数字境界
            return f"第{number_to_chinese(tier)}重天境"
    
    return REALM_NAMES[-1]


def realm_by_level_and_reincarnation(level: int, reincarnation_level: int = 0) -> str:
    """根据等级和转生等级返回更精确的境界名称"""
    base_realm = realm_by_level(level)
    
    # 如果有转生等级，在境界名称后添加转生标识
    if reincarnation_level > 0:
        # 根据转生等级添加不同的前缀或后缀
        if reincarnation_level == 1:
            return f"一转·{base_realm}"
        elif reincarnation_level == 2:
            return f"二转·{base_realm}"
        elif reincarnation_level == 3:
            return f"三转·{base_realm}"
        elif reincarnation_level <= 9:
            chinese_reincarnation = number_to_chinese(reincarnation_level)
            return f"{chinese_reincarnation}转·{base_realm}"
        else:
            # 超过九转的显示方式
            return f"轮回{reincarnation_level}世·{base_realm}"
    
    return base_realm
