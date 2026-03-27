"""
六爻起卦功能模块
根据当前时间和占问事由，用传统时间起卦法生成完整排盘（六亲、六神、世应、纳甲），
再调用大模型进行专业解析。
"""
import logging
import aiohttp
from datetime import datetime
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams
from nonebot.params import CommandArg
from ..models.db import safe_session
from ..platform_utils import get_unified_player
from ..utils import message_add_head, check_action_limit, record_action
from ..ai_guide import call_ai_with_fallback

logger = logging.getLogger(__name__)

# =====================================================================
#  易经六爻基础数据
# =====================================================================

# 八卦：序号(先天八卦数) -> 名称、自然象、五行
BAGUA = {
    1: {"name": "乾", "symbol": "☰", "nature": "天", "element": "金"},
    2: {"name": "兑", "symbol": "☱", "nature": "泽", "element": "金"},
    3: {"name": "离", "symbol": "☲", "nature": "火", "element": "火"},
    4: {"name": "震", "symbol": "☳", "nature": "雷", "element": "木"},
    5: {"name": "巽", "symbol": "☴", "nature": "风", "element": "木"},
    6: {"name": "坎", "symbol": "☵", "nature": "水", "element": "水"},
    7: {"name": "艮", "symbol": "☶", "nature": "山", "element": "土"},
    8: {"name": "坤", "symbol": "☷", "nature": "地", "element": "土"},
}

# 八卦二进制（初爻→三爻，从下到上）
# 乾☰三阳 兑☱上阴 离☲中阴 震☳仅初阳 巽☴仅初阴 坎☵中阳 艮☶仅上阳 坤☷三阴
GUA_BINARY = {
    1: [1, 1, 1],  # 乾 ☰ 阳阳阳
    2: [1, 1, 0],  # 兑 ☱ 阳阳阴
    3: [1, 0, 1],  # 离 ☲ 阳阴阳
    4: [1, 0, 0],  # 震 ☳ 阳阴阴（仅初爻为阳）
    5: [0, 1, 1],  # 巽 ☴ 阴阳阳（仅初爻为阴）
    6: [0, 1, 0],  # 坎 ☵ 阴阳阴
    7: [0, 0, 1],  # 艮 ☶ 阴阴阳（仅上爻为阳）
    8: [0, 0, 0],  # 坤 ☷ 阴阴阴
}

# 六十四卦名称表 (上卦, 下卦) -> 卦名
HEXAGRAM_NAMES = {
    (1, 1): "乾为天", (1, 2): "天泽履", (1, 3): "天火同人", (1, 4): "天雷无妄",
    (1, 5): "天风姤",  (1, 6): "天水讼", (1, 7): "天山遁",   (1, 8): "天地否",
    (2, 1): "泽天夬", (2, 2): "兑为泽", (2, 3): "泽火革",   (2, 4): "泽雷随",
    (2, 5): "泽风大过", (2, 6): "泽水困", (2, 7): "泽山咸", (2, 8): "泽地萃",
    (3, 1): "火天大有", (3, 2): "火泽睽", (3, 3): "离为火", (3, 4): "火雷噬嗑",
    (3, 5): "火风鼎",  (3, 6): "火水未济", (3, 7): "火山旅", (3, 8): "火地晋",
    (4, 1): "雷天大壮", (4, 2): "雷泽归妹", (4, 3): "雷火丰", (4, 4): "震为雷",
    (4, 5): "雷风恒",  (4, 6): "雷水解", (4, 7): "雷山小过", (4, 8): "雷地豫",
    (5, 1): "风天小畜", (5, 2): "风泽中孚", (5, 3): "风火家人", (5, 4): "风雷益",
    (5, 5): "巽为风",  (5, 6): "风水涣", (5, 7): "风山渐",   (5, 8): "风地观",
    (6, 1): "水天需", (6, 2): "水泽节", (6, 3): "水火既济", (6, 4): "水雷屯",
    (6, 5): "水风井",  (6, 6): "坎为水", (6, 7): "水山蹇", (6, 8): "水地比",
    (7, 1): "山天大畜", (7, 2): "山泽损", (7, 3): "山火贲", (7, 4): "山雷颐",
    (7, 5): "山风蛊",  (7, 6): "山水蒙", (7, 7): "艮为山", (7, 8): "山地剥",
    (8, 1): "地天泰", (8, 2): "地泽临", (8, 3): "地火明夷", (8, 4): "地雷复",
    (8, 5): "地风升",  (8, 6): "地水师", (8, 7): "地山谦", (8, 8): "坤为地",
}

# 六十四卦 Unicode 符号映射（卦名简称 -> 卦象符号）
HEXAGRAM_UNICODE = {
    "乾": "䷀", "坤": "䷁", "屯": "䷂", "蒙": "䷃", "需": "䷄", "讼": "䷅",
    "师": "䷆", "比": "䷇", "小畜": "䷈", "履": "䷉", "泰": "䷊", "否": "䷋",
    "同人": "䷌", "大有": "䷍", "谦": "䷎", "豫": "䷏", "随": "䷐", "蛊": "䷑",
    "临": "䷒", "观": "䷓", "噬嗑": "䷔", "贲": "䷕", "剥": "䷖", "复": "䷗",
    "无妄": "䷘", "大畜": "䷙", "颐": "䷚", "大过": "䷛", "坎": "䷜", "离": "䷝",
    "咸": "䷞", "恒": "䷟", "遁": "䷠", "大壮": "䷡", "晋": "䷢", "明夷": "䷣",
    "家人": "䷤", "睽": "䷥", "蹇": "䷦", "解": "䷧", "损": "䷨", "益": "䷩",
    "夬": "䷪", "姤": "䷫", "萃": "䷬", "升": "䷭", "困": "䷮", "井": "䷯",
    "革": "䷰", "鼎": "䷱", "震": "䷲", "艮": "䷳", "渐": "䷴", "归妹": "䷵",
    "丰": "䷶", "旅": "䷷", "巽": "䷸", "兑": "䷹", "涣": "䷺", "节": "䷻",
    "中孚": "䷼", "小过": "䷽", "既济": "䷾", "未济": "䷿",
}


def get_hexagram_symbol(hexagram_name: str) -> str:
    """从卦名中提取对应的Unicode卦象符号"""
    # 先尝试完整匹配"X为Y"格式，如"乾为天"→取"乾"
    for key in sorted(HEXAGRAM_UNICODE.keys(), key=len, reverse=True):
        if key in hexagram_name:
            return HEXAGRAM_UNICODE[key]
    return "☯"

# ===== 纳甲系统 =====
# 八卦纳甲：每卦6爻对应的天干地支（从初爻到上爻）
# 阳卦(乾震坎艮)纳阳干，阴卦(坤巽离兑)纳阴干
NAJIA = {
    "乾": [("甲", "子", "水"), ("甲", "寅", "木"), ("甲", "辰", "土"),
           ("壬", "午", "火"), ("壬", "申", "金"), ("壬", "戌", "土")],
    "兑": [("丁", "巳", "火"), ("丁", "卯", "木"), ("丁", "丑", "土"),
           ("丁", "亥", "水"), ("丁", "酉", "金"), ("丁", "未", "土")],
    "离": [("己", "卯", "木"), ("己", "丑", "土"), ("己", "亥", "水"),
           ("己", "酉", "金"), ("己", "未", "土"), ("己", "巳", "火")],
    "震": [("庚", "子", "水"), ("庚", "寅", "木"), ("庚", "辰", "土"),
           ("庚", "午", "火"), ("庚", "申", "金"), ("庚", "戌", "土")],
    "巽": [("辛", "丑", "土"), ("辛", "亥", "水"), ("辛", "酉", "金"),
           ("辛", "未", "土"), ("辛", "巳", "火"), ("辛", "卯", "木")],
    "坎": [("戊", "寅", "木"), ("戊", "辰", "土"), ("戊", "午", "火"),
           ("戊", "申", "金"), ("戊", "戌", "土"), ("戊", "子", "水")],
    "艮": [("丙", "辰", "土"), ("丙", "午", "火"), ("丙", "申", "金"),
           ("丙", "戌", "土"), ("丙", "子", "水"), ("丙", "寅", "木")],
    "坤": [("乙", "未", "土"), ("乙", "巳", "火"), ("乙", "卯", "木"),
           ("癸", "丑", "土"), ("癸", "亥", "水"), ("癸", "酉", "金")],
}

# ===== 六亲系统 =====
# 根据卦宫五行与爻五行的生克关系确定六亲
# 我宫五行 -> 爻五行 -> 六亲名
LIUQIN_TABLE = {
    # (宫五行, 爻五行) -> 六亲
    ("金", "金"): "兄弟", ("金", "木"): "妻财", ("金", "水"): "子孙",
    ("金", "火"): "官鬼", ("金", "土"): "父母",
    ("木", "木"): "兄弟", ("木", "土"): "妻财", ("木", "火"): "子孙",
    ("木", "金"): "官鬼", ("木", "水"): "父母",
    ("水", "水"): "兄弟", ("水", "火"): "妻财", ("水", "木"): "子孙",
    ("水", "土"): "官鬼", ("水", "金"): "父母",
    ("火", "火"): "兄弟", ("火", "金"): "妻财", ("火", "土"): "子孙",
    ("火", "水"): "官鬼", ("火", "木"): "父母",
    ("土", "土"): "兄弟", ("土", "水"): "妻财", ("土", "金"): "子孙",
    ("土", "木"): "官鬼", ("土", "火"): "父母",
}

# ===== 六神系统 =====
# 日天干决定六神排列（从初爻到上爻）
# 甲乙日起青龙，丙丁日起朱雀，戊日起勾陈，己日起腾蛇，庚辛日起白虎，壬癸日起玄武
LIUSHEN_ORDER = ["青龙", "朱雀", "勾陈", "腾蛇", "白虎", "玄武"]
TIANGAN_LIUSHEN_START = {
    "甲": 0, "乙": 0,  # 青龙起
    "丙": 1, "丁": 1,  # 朱雀起
    "戊": 2,            # 勾陈起
    "己": 3,            # 腾蛇起
    "庚": 4, "辛": 4,  # 白虎起
    "壬": 5, "癸": 5,  # 玄武起
}

# ===== 八宫六十四卦归属表 =====
# (上卦, 下卦) -> (宫名, 宫五行, 世爻位, 应爻位)
# 按八宫卦序：本宫→一世→二世→三世→四世→五世→游魂→归魂
# 数据来源：传统分宫卦象次序表，经网络多源交叉验证
HEXAGRAM_PALACE = {
    # 乾宫（金）
    (1, 1): ("乾", "金", 6, 3),  # 乾为天（本宫）
    (1, 5): ("乾", "金", 1, 4),  # 天风姤（一世）
    (1, 7): ("乾", "金", 2, 5),  # 天山遁（二世）
    (1, 8): ("乾", "金", 3, 6),  # 天地否（三世）
    (5, 8): ("乾", "金", 4, 1),  # 风地观（四世）
    (7, 8): ("乾", "金", 5, 2),  # 山地剥（五世）
    (3, 8): ("乾", "金", 4, 1),  # 火地晋（游魂）
    (3, 1): ("乾", "金", 3, 6),  # 火天大有（归魂）
    # 兑宫（金）
    (2, 2): ("兑", "金", 6, 3),  # 兑为泽
    (2, 6): ("兑", "金", 1, 4),  # 泽水困
    (2, 8): ("兑", "金", 2, 5),  # 泽地萃
    (2, 7): ("兑", "金", 3, 6),  # 泽山咸
    (6, 7): ("兑", "金", 4, 1),  # 水山蹇
    (8, 7): ("兑", "金", 5, 2),  # 地山谦
    (4, 7): ("兑", "金", 4, 1),  # 雷山小过（游魂）
    (4, 2): ("兑", "金", 3, 6),  # 雷泽归妹（归魂）
    # 离宫（火）
    (3, 3): ("离", "火", 6, 3),  # 离为火
    (3, 7): ("离", "火", 1, 4),  # 火山旅
    (3, 5): ("离", "火", 2, 5),  # 火风鼎
    (3, 6): ("离", "火", 3, 6),  # 火水未济
    (7, 6): ("离", "火", 4, 1),  # 山水蒙
    (5, 6): ("离", "火", 5, 2),  # 风水涣
    (1, 6): ("离", "火", 4, 1),  # 天水讼（游魂）
    (1, 3): ("离", "火", 3, 6),  # 天火同人（归魂）
    # 震宫（木）
    (4, 4): ("震", "木", 6, 3),  # 震为雷
    (4, 8): ("震", "木", 1, 4),  # 雷地豫
    (4, 6): ("震", "木", 2, 5),  # 雷水解
    (4, 5): ("震", "木", 3, 6),  # 雷风恒
    (8, 5): ("震", "木", 4, 1),  # 地风升
    (6, 5): ("震", "木", 5, 2),  # 水风井
    (2, 5): ("震", "木", 4, 1),  # 泽风大过（游魂）
    (2, 4): ("震", "木", 3, 6),  # 泽雷随（归魂）
    # 巽宫（木）
    (5, 5): ("巽", "木", 6, 3),  # 巽为风
    (5, 1): ("巽", "木", 1, 4),  # 风天小畜
    (5, 3): ("巽", "木", 2, 5),  # 风火家人
    (5, 4): ("巽", "木", 3, 6),  # 风雷益
    (1, 4): ("巽", "木", 4, 1),  # 天雷无妄
    (3, 4): ("巽", "木", 5, 2),  # 火雷噬嗑
    (7, 4): ("巽", "木", 4, 1),  # 山雷颐（游魂）
    (7, 5): ("巽", "木", 3, 6),  # 山风蛊（归魂）
    # 坎宫（水）
    (6, 6): ("坎", "水", 6, 3),  # 坎为水
    (6, 2): ("坎", "水", 1, 4),  # 水泽节
    (6, 4): ("坎", "水", 2, 5),  # 水雷屯
    (6, 3): ("坎", "水", 3, 6),  # 水火既济
    (2, 3): ("坎", "水", 4, 1),  # 泽火革
    (4, 3): ("坎", "水", 5, 2),  # 雷火丰
    (8, 3): ("坎", "水", 4, 1),  # 地火明夷（游魂）
    (8, 6): ("坎", "水", 3, 6),  # 地水师（归魂）
    # 艮宫（土）
    (7, 7): ("艮", "土", 6, 3),  # 艮为山
    (7, 3): ("艮", "土", 1, 4),  # 山火贲
    (7, 1): ("艮", "土", 2, 5),  # 山天大畜
    (7, 2): ("艮", "土", 3, 6),  # 山泽损
    (3, 2): ("艮", "土", 4, 1),  # 火泽睽
    (1, 2): ("艮", "土", 5, 2),  # 天泽履
    (5, 2): ("艮", "土", 4, 1),  # 风泽中孚（游魂）
    (5, 7): ("艮", "土", 3, 6),  # 风山渐（归魂）
    # 坤宫（土）
    (8, 8): ("坤", "土", 6, 3),  # 坤为地
    (8, 4): ("坤", "土", 1, 4),  # 地雷复
    (8, 2): ("坤", "土", 2, 5),  # 地泽临
    (8, 1): ("坤", "土", 3, 6),  # 地天泰
    (4, 1): ("坤", "土", 4, 1),  # 雷天大壮
    (2, 1): ("坤", "土", 5, 2),  # 泽天夬
    (6, 1): ("坤", "土", 4, 1),  # 水天需（游魂）
    (6, 8): ("坤", "土", 3, 6),  # 水地比（归魂）
}


# ===== 四柱（年月日时柱）简易计算 =====
TIANGAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
DIZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
DIZHI_WUXING = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火",
    "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水"
}

HOUR_TO_DIZHI_IDX = {
    23: 0, 0: 0, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3,
    7: 4, 8: 4, 9: 5, 10: 5, 11: 6, 12: 6, 13: 7, 14: 7,
    15: 8, 16: 8, 17: 9, 18: 9, 19: 10, 20: 10, 21: 11, 22: 11
}


def _calc_sizhu(now: datetime) -> dict:
    """
    计算四柱（年柱、月柱、日柱、时柱）—— 简化算法
    精确四柱需要万年历，这里用公式近似，足够起卦使用
    """
    year = now.year
    month = now.month
    day = now.day
    hour = now.hour

    # 年柱（以立春为界，简化为公历2月4日）
    y = year if month > 2 or (month == 2 and day >= 4) else year - 1
    year_tg_idx = (y - 4) % 10
    year_dz_idx = (y - 4) % 12

    # 月柱天干（年干×2+月数 的规律，简化）
    # 月柱地支固定：正月寅、二月卯...
    m = month - 1 if month >= 2 else 11  # 简化调整
    if month == 1:
        m = 11  # 丑月
    elif month == 2:
        m = 0 if day < 4 else 0  # 寅月
        m = 2  # 寅
    else:
        m = month  # 近似
    month_dz_idx = (month + 1) % 12  # 简化：正月=寅(2)
    if month_dz_idx == 0:
        month_dz_idx = 12
    month_dz_idx = (month_dz_idx + 1) % 12  # 调整

    # 简化月柱天干
    month_tg_idx = (year_tg_idx * 2 + month) % 10

    # 日柱（使用简化公式，非精确万年历）
    # 蔡勒公式近似
    total_days = (year - 1) * 365 + (year - 1) // 4 - (year - 1) // 100 + (year - 1) // 400
    month_days = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0:
        month_days[2] = 29
    for i in range(1, month):
        total_days += month_days[i]
    total_days += day
    # 基于已知日期推算：2000年1月1日为甲子日的一个近似锚点
    anchor = (2000 - 1) * 365 + (2000 - 1) // 4 - (2000 - 1) // 100 + (2000 - 1) // 400 + 1
    day_offset = (total_days - anchor + 12) % 60  # 加偏移校准
    day_tg_idx = day_offset % 10
    day_dz_idx = day_offset % 12

    # 时柱
    hour_dz_idx = HOUR_TO_DIZHI_IDX.get(hour, 0)
    hour_tg_idx = (day_tg_idx * 2 + hour_dz_idx) % 10

    # 旬空计算（日柱所在旬的空亡地支）
    xun_start = (day_tg_idx - day_dz_idx) % 12
    kong1_idx = (10 + xun_start) % 12  # 旬空第一个
    kong2_idx = (11 + xun_start) % 12  # 旬空第二个

    return {
        "year": f"{TIANGAN[year_tg_idx]}{DIZHI[year_dz_idx]}",
        "month": f"{TIANGAN[month_tg_idx]}{DIZHI[month_dz_idx]}",
        "day": f"{TIANGAN[day_tg_idx]}{DIZHI[day_dz_idx]}",
        "hour": f"{TIANGAN[hour_tg_idx]}{DIZHI[hour_dz_idx]}",
        "day_tg": TIANGAN[day_tg_idx],
        "day_dz": DIZHI[day_dz_idx],
        "xunkong": f"{DIZHI[kong1_idx]}{DIZHI[kong2_idx]}",
    }


# =====================================================================
#  起卦与排盘
# =====================================================================

def _get_palace_info(upper_num: int, lower_num: int) -> tuple[str, str, int, int]:
    """
    从八宫归属表中获取卦的宫名、宫五行、世爻、应爻
    返回 (宫名, 宫五行, 世爻位, 应爻位)
    """
    info = HEXAGRAM_PALACE.get((upper_num, lower_num))
    if info:
        return info
    # 理论上不会走到这里（64卦全部覆盖），但做兜底
    return BAGUA[upper_num]["name"], BAGUA[upper_num]["element"], 6, 3


def generate_hexagram(now: datetime, question: str) -> dict:
    """
    时间起卦法 + 问事字数辅助，生成完整排盘

    Returns:
        包含完整排盘信息的字典
    """
    year = now.year
    month = now.month
    day = now.day
    hour = now.hour
    year_num = year % 100
    hour_dz_idx = HOUR_TO_DIZHI_IDX.get(hour, 0)
    dizhi_num = hour_dz_idx + 1  # 子=1, 丑=2, ...

    # 字数扰动
    char_sum = sum(ord(c) for c in question) if question else 0

    # 上卦
    upper_num = (year_num + month + day + char_sum) % 8 or 8
    # 下卦
    lower_num = (year_num + month + day + dizhi_num + char_sum) % 8 or 8
    # 动爻（1-6）
    dong_yao = (year_num + month + day + dizhi_num + char_sum) % 6 or 6

    upper = BAGUA[upper_num]
    lower = BAGUA[lower_num]
    hexagram_name = HEXAGRAM_NAMES.get((upper_num, lower_num), f"{upper['name']}{lower['name']}")

    # 四柱
    sizhu = _calc_sizhu(now)

    # 从八宫归属表获取宫名、宫五行、世应
    palace_name, palace_element, shi, ying = _get_palace_info(upper_num, lower_num)

    # 六神（根据日天干）
    liushen_start = TIANGAN_LIUSHEN_START.get(sizhu["day_tg"], 0)

    # 纳甲：获取本卦每爻的天干地支
    lower_najia = NAJIA[lower["name"]]  # 初爻到三爻
    upper_najia = NAJIA[upper["name"]]  # 四爻到六爻（取后3个）

    # 生成六爻详细信息
    yaos = []
    for i in range(1, 7):
        # 确定阴阳
        if i <= 3:
            gua_num = lower_num
            yao_pos_in_gua = i - 1  # 0,1,2
            tg, dz, wx = lower_najia[i - 1]
        else:
            gua_num = upper_num
            yao_pos_in_gua = i - 4  # 0,1,2
            tg, dz, wx = upper_najia[i - 4 + 3]  # 上卦取后3组

        is_yang = GUA_BINARY[gua_num][yao_pos_in_gua] == 1
        is_dong = (i == dong_yao)

        # 六亲
        liuqin = LIUQIN_TABLE.get((palace_element, wx), "?")

        # 六神
        liushen = LIUSHEN_ORDER[(liushen_start + i - 1) % 6]

        # 世/应标记
        shi_ying_mark = ""
        if i == shi:
            shi_ying_mark = "世"
        elif i == ying:
            shi_ying_mark = "应"

        # 阴阳符号
        if is_yang:
            yao_symbol = "---"
            yao_mark = "〇" if is_dong else ""
        else:
            yao_symbol = "- -"
            yao_mark = "ㄨ" if is_dong else ""

        yao_names = ["初", "二", "三", "四", "五", "上"]

        yaos.append({
            "position": yao_names[i - 1],
            "index": i,
            "is_yang": is_yang,
            "is_dong": is_dong,
            "symbol": yao_symbol,
            "dong_mark": yao_mark,
            "tiangan": tg,
            "dizhi": dz,
            "wuxing": wx,
            "liuqin": liuqin,
            "liushen": liushen,
            "shi_ying": shi_ying_mark,
        })

    # 变卦计算
    changed_upper = upper_num
    changed_lower = lower_num
    if dong_yao <= 3:
        gua_copy = list(GUA_BINARY[lower_num])
        gua_copy[dong_yao - 1] = 1 - gua_copy[dong_yao - 1]
        for k, v in GUA_BINARY.items():
            if v == gua_copy:
                changed_lower = k
                break
    else:
        gua_copy = list(GUA_BINARY[upper_num])
        gua_copy[dong_yao - 4] = 1 - gua_copy[dong_yao - 4]
        for k, v in GUA_BINARY.items():
            if v == gua_copy:
                changed_upper = k
                break

    changed_name = HEXAGRAM_NAMES.get(
        (changed_upper, changed_lower),
        f"{BAGUA[changed_upper]['name']}{BAGUA[changed_lower]['name']}"
    )

    # 变卦六爻纳甲（用于展示变爻的变化结果）
    changed_lower_najia = NAJIA[BAGUA[changed_lower]["name"]]
    changed_upper_najia = NAJIA[BAGUA[changed_upper]["name"]]
    _, changed_palace_element, c_shi, c_ying = _get_palace_info(changed_upper, changed_lower)

    changed_yaos = []
    for i in range(1, 7):
        if i <= 3:
            gua_num = changed_lower
            yao_pos = i - 1
            tg, dz, wx = changed_lower_najia[i - 1]
        else:
            gua_num = changed_upper
            yao_pos = i - 4
            tg, dz, wx = changed_upper_najia[i - 4 + 3]

        is_yang = GUA_BINARY[gua_num][yao_pos] == 1
        liuqin = LIUQIN_TABLE.get((changed_palace_element, wx), "?")

        # 变卦的世应
        shi_ying_mark = ""
        if i == c_shi:
            shi_ying_mark = "世"
        elif i == c_ying:
            shi_ying_mark = "应"

        changed_yaos.append({
            "is_yang": is_yang,
            "symbol": "---" if is_yang else "- -",
            "tiangan": tg,
            "dizhi": dz,
            "wuxing": wx,
            "liuqin": liuqin,
            "shi_ying": shi_ying_mark,
        })

    return {
        "hexagram_name": hexagram_name,
        "upper": upper,
        "lower": lower,
        "upper_num": upper_num,
        "lower_num": lower_num,
        "dong_yao": dong_yao,
        "yaos": yaos,
        "changed_name": changed_name,
        "changed_upper": BAGUA[changed_upper],
        "changed_lower": BAGUA[changed_lower],
        "changed_yaos": changed_yaos,
        "sizhu": sizhu,
        "palace_name": palace_name,
        "palace_element": palace_element,
        "shi": shi,
        "ying": ying,
        "time_str": now.strftime("%Y年%m月%d日"),
    }


# =====================================================================
#  排盘格式化
# =====================================================================

def build_ai_prompt(hex_data: dict, question: str) -> list:
    """构建发送给大模型的消息，包含完整排盘信息"""
    system_prompt = """你是一位精通《易经》六爻占卜的国学大师，擅长用通俗易懂的方式为普通人解读卦象。

你将收到一个完整的六爻排盘，包含四柱、六亲、六神、世应、纳甲、动爻和变卦信息。

解卦格式要求（严格遵守）：
1.【卦意】一句话说明本卦核心含义，然后用大白话解释"简单说就是……"
2.【用神分析】找出用神，分析旺衰生克，然后加一句"也就是说……"的通俗翻译
3.【动爻变化】分析动爻影响，然后加"换句话说……"的白话解释
4.【综合判断】结合世应、六神给出明确结论，用"对你来说……"开头说人话
5.【行动建议】针对所问之事给出具体可操作的建议，说清楚该做什么、不该做什么
6.【忠告】一句简短有力的忠告

重要：每一段专业分析后面都必须跟一句通俗易懂的大白话翻译，让完全不懂易经的人也能看明白。
字数控制在400-600字。
不要使用markdown格式，用纯文本。"""

    # 构建排盘文本
    sz = hex_data["sizhu"]
    hex_info_lines = [
        f"起卦时间：{hex_data['time_str']}",
        f"四柱：{sz['year']}年 {sz['month']}月 {sz['day']}日 {sz['hour']}时",
        f"旬空：{sz['xunkong']}",
        f"占问事由：{question or '未指定'}",
        f"",
        f"本卦：{hex_data['hexagram_name']}（{hex_data['palace_name']}宫·{hex_data['palace_element']}）",
        f"变卦：{hex_data['changed_name']}",
        f"世爻：第{hex_data['shi']}爻  应爻：第{hex_data['ying']}爻",
        f"",
        f"六爻排盘（从上爻到初爻）：",
    ]

    for i in range(5, -1, -1):
        yao = hex_data["yaos"][i]
        cy = hex_data["changed_yaos"][i]
        dong_str = " 动" if yao["is_dong"] else ""
        shi_ying_str = f" [{yao['shi_ying']}]" if yao["shi_ying"] else ""
        line = f"{yao['liushen']} {yao['liuqin']}{yao['tiangan']}{yao['dizhi']}{yao['wuxing']} {'阳' if yao['is_yang'] else '阴'}{dong_str}{shi_ying_str}"
        if yao["is_dong"]:
            c_shi = f" [{cy['shi_ying']}]" if cy["shi_ying"] else ""
            line += f" → {cy['liuqin']}{cy['tiangan']}{cy['dizhi']}{cy['wuxing']}{c_shi}"
        hex_info_lines.append(line)

    hex_info = "\n".join(hex_info_lines)
    user_message = f"请为以下六爻排盘进行详细解读：\n\n{hex_info}\n\n请给出完整的六爻解卦分析。"

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]


# =====================================================================
#  NoneBot 命令注册
# =====================================================================

DIVINATION_COST = 500  # 起卦消耗金币

liuyao_cmd = on_command("起卦", aliases={"六爻", "卜卦"}, block=True, priority=5)


@liuyao_cmd.handle()
async def handle_liuyao(event: MessageEvent, args: Message = CommandArg()):
    """六爻起卦功能"""
    user_id = event.get_user_id()

    # 检查频率限制
    allowed, error_msg = check_action_limit(user_id, "liuyao")
    if not allowed:
        await liuyao_cmd.finish(error_msg)

    question = args.extract_plain_text().strip()
    if not question:
        await liuyao_cmd.finish(message_add_head(
            "☯ 请输入占问事由\n"
            "用法：【起卦 你的问题】\n"
            "例如：起卦 近期事业运势如何",
            event
        ))

    if len(question) > 50:
        await liuyao_cmd.finish(message_add_head("⚠️ 问题过长，请控制在50字以内", event))

    # 检查玩家和扣除金币
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await liuyao_cmd.finish("您还没有创建角色，请先注册。")

        if player.gold < DIVINATION_COST:
            await liuyao_cmd.finish(message_add_head(
                f"⚠️ 金币不足，起卦需要 {DIVINATION_COST} 金币\n"
                f"当前金币：{player.gold}",
                event
            ))

        player.gold -= DIVINATION_COST
        await session.commit()

    # 记录操作
    record_action(user_id, "liuyao")

    await liuyao_cmd.send(message_add_head(f"☯ 天机推演中，正在为「{question}」起卦...", event))

    # 起卦
    now = datetime.now()
    hex_data = generate_hexagram(now, question)

    # 调用大模型解卦
    ai_analysis = ""
    try:
        messages = build_ai_prompt(hex_data, question)
        result = await call_ai_with_fallback(messages)
        ai_analysis = result['choices'][0]['message']['content'].strip()
    except KeyError:
        ai_analysis = "（天机不可泄露，解卦暂时无法获取）"
    except TimeoutError:
        ai_analysis = "（天机运算超时，请稍后再试）"
    except (aiohttp.ClientError, ValueError, ConnectionError) as e:
        logger.error(f"[六爻] AI解卦失败: {type(e).__name__}: {e}", exc_info=True)
        ai_analysis = "（天机晦涩，解卦暂时无法获取）"

    # 使用Markdown模板展示
    try:
        desc_parts = []
        sz = hex_data["sizhu"]
        desc_parts.append(f"📅 {hex_data['time_str']}")
        desc_parts.append(f"四柱：{sz['year']} {sz['month']} {sz['day']} {sz['hour']}")
        desc_parts.append(f"旬空：{sz['xunkong']}  💰 消耗{DIVINATION_COST}金币")
        desc_parts.append(f"🤔 所问：{question}")
        desc_parts.append("━━━━━━━━━━━━━")

        # 本卦 → 变卦（带Unicode卦象）
        main_symbol = get_hexagram_symbol(hex_data['hexagram_name'])
        changed_symbol = get_hexagram_symbol(hex_data['changed_name'])
        desc_parts.append(f"{main_symbol} {hex_data['hexagram_name']}({hex_data['palace_name']}) → {changed_symbol} {hex_data['changed_name']}")
        desc_parts.append("")

        # 排盘（简化显示）
        for i in range(5, -1, -1):
            yao = hex_data["yaos"][i]
            cy = hex_data["changed_yaos"][i]
            shi_ying = yao["shi_ying"]
            dong = yao["dong_mark"]
            main = f"{yao['liushen']} {yao['liuqin']}{yao['dizhi']}{yao['wuxing']} {yao['symbol']}"
            if dong:
                main += f" {dong}"
            if shi_ying:
                main += f" {shi_ying}"
            if yao["is_dong"]:
                main += f" → {cy['liuqin']}{cy['dizhi']}{cy['wuxing']} {cy['symbol']}"
                if cy["shi_ying"]:
                    main += f" {cy['shi_ying']}"
            desc_parts.append(main)

        desc_parts.append("━━━━━━━━━━━━━")

        # AI解析
        desc_parts.append("🔮 卦象解析：")
        if len(ai_analysis) > 800:
            ai_analysis = ai_analysis[:800] + "……"
        desc_parts.append(ai_analysis)
        desc_parts.append("")
        desc_parts.append("💡 卦象仅供娱乐参考，切勿过分迷信")

        desc = "\r".join(desc_parts)
        title = f"{main_symbol} 六爻 · {hex_data['hexagram_name']}"
        hint = "💡 点击下方按钮快速操作"

        btn1 = "起卦 今日运势"
        btn2 = "抽签"
        btn3 = "娱乐系统"
        btn4 = "帮助"

        title = title.replace('\n', '\r')
        desc = desc.replace('\n', '\r')
        hint = hint.replace('\n', '\r')

        template_params = [
            MessageMarkdownParams(key="title", values=[title]),
            MessageMarkdownParams(key="desc", values=[desc]),
            MessageMarkdownParams(key="imgurl", values=[f"https://thirdqq.qlogo.cn/qqapp/102499345/{user_id}/0"]),
            MessageMarkdownParams(key="width", values=["32"]),
            MessageMarkdownParams(key="height", values=["32"]),
            MessageMarkdownParams(key="hint", values=[hint]),
            MessageMarkdownParams(key="t1", values=[btn1]),
            MessageMarkdownParams(key="t2", values=[btn2]),
            MessageMarkdownParams(key="t3", values=[btn3]),
            MessageMarkdownParams(key="t4", values=[btn4])
        ]

        markdown_msg = MessageMarkdown(
            custom_template_id="102499345_1770445216",
            params=template_params
        )

        msg = MessageSegment.markdown(markdown_msg)
    except (KeyError, ValueError, TypeError) as e:
        logger.error(f"[六爻] Markdown构建失败: {e}", exc_info=True)
        await liuyao_cmd.finish(message_add_head("⚠️ 卦象展示失败，请稍后重试", event))

    await liuyao_cmd.finish(msg)


# 注册频率限制配置
from ..utils import rate_limiter, RateLimitConfig

rate_limiter.register_action("liuyao", RateLimitConfig(
    max_requests=10,   # 5分钟内最多10次
    time_window=300.0,
    cooldown=30.0      # 每次间隔30秒（AI调用有成本）
))
