from nonebot.adapters.qq import Message, MessageSegment, MessageEvent
from typing import Optional, Dict
from .config import config
import math
import re  # 用于正则匹配域名
import time
from collections import defaultdict, deque
from dataclasses import dataclass


def message_add_head(content: str, event: Optional[MessageEvent] = None) -> Message:
    """
    后续可能添加统一的消息头
    """
    head = "『诡修仙』\n"
    return Message(head + content)



def calculate_level_up_exp(current_level: int) -> int:
    """
    根据配置计算升级所需经验
    使用混合曲线：前期线性增长，后期指数增长
    """
    cfg = config.game_config["game"]
    base = cfg["base_exp"]
    curve = cfg["exp_curve"]

    if current_level < curve["curve_change_level"]:
        # 前期：一次函数
        return int(base + (current_level-1) * curve["early_multiplier"])
    else:
        # 后期：二次函数
        level_diff = current_level - curve["curve_change_level"]
        return int(calculate_level_up_exp(curve["curve_change_level"]-1) + (level_diff ** 2) * curve["late_multiplier"])



async def generate_exp_table(max_level: int = 100) -> str:
    """
    生成经验表格并保存到文件
    返回文件路径
    """
    import csv
    from pathlib import Path

    cfg = config.game_config["game"]
    table = []
    total_exp = 0

    for level in range(1, max_level + 1):
        required = calculate_level_up_exp(level)
        total_exp += required
        table.append({
            "等级": level,
            "升级所需经验": required,
            "累计总经验": total_exp
        })

    # 确保数据目录存在
    output_path = config.data_dir / "level_exp_table.csv"
    with open(output_path, "w", newline="", encoding="utf8") as f:
        writer = csv.DictWriter(f, fieldnames=["等级", "升级所需经验", "累计总经验"])
        writer.writeheader()
        writer.writerows(table)

    return str(output_path)


async def paginate_items(items: list, page: int, page_size: Optional[int] = None, capacity_info: str = None) -> str:
    """分页格式化背包物品

    • 普通物品显示数量：✖️{qty}
    • 装备显示耐久：🛠️ {cur}/{max}
    """
    # 从配置获取分页大小
    cfg_page_size = config.game_config["game"]["inventory_page_size"]
    page_size = page_size or cfg_page_size
    start = (page - 1) * page_size
    end = start + page_size
    current_page_items = items[start:end]

    # 计算总页数时使用实际分页大小
    total_pages = (len(items) - 1) // page_size + 1
    page_info = f"\n📖 第 {page} 页（共 {total_pages} 页)"

    # 添加容量信息
    if capacity_info:
        page_info = f"\n{capacity_info}" + page_info

    lines: list[str] = []
    for offset, inst in enumerate(current_page_items, start=1):
        global_idx = start + offset  # 背包全局序号 (从1开始)
        if getattr(inst, "is_equipment", False):
            tpl = inst.config
            lines.append(
                f"{global_idx}. {tpl.name} 🛠️ {inst.durability}/{tpl.durability}\n"
            )
        else:
            lines.append(
                f"{global_idx}. {inst.config.name} ✖️{inst.quantity}\n"
            )

    return "🎒 你的背包\n" + "".join(lines) + page_info


# ---------------- Luck 概率曲线 ----------------

# Luck 值采用 S 型（Logistic）曲线：
# 先稳增长 → 急剧提升 → 最后趋于平缓
#
#   prob = 1 / (1 + e ^(-(luck - midpoint) / steepness))
#
# • midpoint  决定曲线中点（Luck≈midpoint 时概率≈0.5）
# • steepness 控制斜率，值越小曲线越陡
#
# 默认参数以 Luck≈60 达到 50% 触发率，Luck≈90 时≈88%，Luck≈120 时>98%。

def luck_prob(
    luck_value: int | float,
    midpoint: float = 60,
    steepness: float = 30,
) -> float:
    """根据 *Luck* 值返回 0‒1 之间的触发概率，符合“先稳后急再缓”的 S 型。

    参数
    ------
    luck_value : int | float
        玩家当前 Luck 值。
    midpoint : float, 可选
        曲线的中点，Luck≈midpoint 时概率≈0.5。
    steepness : float, 可选
        斜率参数，数值越小，中段上升越陡。
    """

    # 基础保护
    lv = float(luck_value)
    if lv <= 0:
        return 0.0

    # Logistic 曲线
    prob = 1.0 / (1.0 + math.exp(-(lv - midpoint) / steepness))

    # 理论上已在 (0,1) 内，这里做硬裁剪避免浮点误差
    return max(0.0, min(prob, 1.0))


def damage_reduction_rate(defense: int | float) -> float:
    """计算防御力对应的免伤率

    使用调整后的公式：免伤率 = 防御 / (防御 + 300)

    这个公式的特点：
    1. 收益递减：防御越高，每点防御带来的免伤提升越小
    2. 更温和的增长：100防御 = 25%免伤，300防御 = 50%免伤
    3. 适合本游戏：考虑到防御值容易获得，降低了免伤率增长速度
    4. 自然上限：理论上永远无法达到100%免伤

    参数
    ------
    defense : int | float
        防御力数值

    返回值
    ------
    float
        免伤率，范围 [0, 0.6]，最高60%免伤
    """
    if defense <= 0:
        return 0.0

    # 调整后的公式：防御 / (防御 + 300)
    # 这样100防御只有25%免伤，300防御才有50%免伤
    reduction = defense / (defense + 300)

    # 硬性上限60%，确保至少40%伤害穿透
    return min(reduction, 0.6)


DEFENSE_FLAT_REDUCTION_RATIO: float = 0.2
"""防御转换为数值减伤时的比例系数。"""

DEFENSE_MAX_FLAT_PORTION: float = 0.5
"""数值减伤相对于原始伤害所能占据的最大比例。"""


def apply_defense_mitigation(
    base_damage: int,
    defense: int | float,
    penetration_ratio: float = 0.0,
) -> dict[str, float]:
    """综合计算防御带来的数值减伤与比例减伤。

    参数
    ------
    base_damage : int
        即将结算的原始伤害值。
    defense : int | float
        防御力数值。
    penetration_ratio : float, 可选
        穿透比例，范围为 ``[0, 1]``，用于削减有效防御。

    返回值
    ------
    dict
        ``{"final_damage", "blocked", "flat_reduction", "percent_reduction"}``
        四个键分别表示最终伤害、被防御抵挡的总伤害、数值减伤量以及
        比例减伤率。
    """

    if base_damage <= 0:
        return {
            "final_damage": 0,
            "blocked": 0,
            "flat_reduction": 0,
            "percent_reduction": 0.0,
        }

    if defense <= 0:
        final = max(1, int(base_damage))
        return {
            "final_damage": final,
            "blocked": base_damage - final,
            "flat_reduction": 0,
            "percent_reduction": 0.0,
        }

    effective_penetration = max(0.0, min(1.0, penetration_ratio))
    effective_defense = defense * (1.0 - effective_penetration)

    if effective_defense <= 0:
        final = max(1, int(base_damage))
        return {
            "final_damage": final,
            "blocked": base_damage - final,
            "flat_reduction": 0,
            "percent_reduction": 0.0,
        }

    # 数值减伤：以防御的一定比例换算，同时限制为原始伤害的一半以内
    flat_reduction = int(effective_defense * DEFENSE_FLAT_REDUCTION_RATIO)
    max_flat_reduction = int(base_damage * DEFENSE_MAX_FLAT_PORTION)
    flat_reduction = max(0, min(flat_reduction, max_flat_reduction))

    damage_after_flat = max(0, base_damage - flat_reduction)

    percent_reduction = damage_reduction_rate(effective_defense)
    reduced_damage = damage_after_flat * (1 - percent_reduction)
    final_damage = int(reduced_damage)

    if damage_after_flat > 0 and final_damage <= 0:
        final_damage = 1

    final_damage = max(0, min(base_damage, final_damage))
    if base_damage > 0 and final_damage <= 0:
        final_damage = 1

    blocked = max(0, base_damage - final_damage)

    return {
        "final_damage": final_damage,
        "blocked": blocked,
        "flat_reduction": flat_reduction,
        "percent_reduction": percent_reduction,
    }


# ---------------- URL 转义工具 ----------------

def bypass_urls(
    text: str,
    mode: str = "unicode",
    whitelist: list[str] | None = None,
) -> str:
    """在文本中查找英文域名并根据不同 *mode* 进行转义。

    参数说明
    ----------
    text: str
        待处理文本。
    mode: str
        转义模式，可选值
        ``unicode``      : 在点号前插入不可见字符 ``\u200E``（默认）
        ``space``        : 在点号前插入空格
        ``fullStop``     : 将半角点号替换为中文句号 ``。``
        ``remove``       : 直接删除匹配到的域名
        ``uppercase``    : 整个域名转为大写
        ``tldUppercase`` : 仅将顶级域名 TLD 转为大写
    whitelist: list[str] | None
        白名单域名列表，命中后将保持原样，不做任何处理。

    返回值
    -------
    str
        处理后的文本。

    Notes
    -----
    1. 为了保持依赖最小化，这里并未引入第三方库获取 "全部" 顶级域名列表，而是使用
       一个正则 ``([A-Za-z0-9-]+\.)+[A-Za-z]{2,63}`` 来粗略匹配"看起来像"域名的串。
       在大多数常见场景下已足够；如需严格匹配，可替换为公开的 TLD 列表。
    2. 该函数 **不会** 主动发送消息，也不包含任何异步操作，可安全在任何上下文中调用。
    """

    whitelist = whitelist or []

    # 点号替换映射
    dot_replacer_map: dict[str, str] = {
        "unicode": "\u200E.",  # U+200E (LRM) + '.'
        "space": " .",
        "fullStop": "。",
    }

    # 用于匹配英文域名的正则表达式：<sub>.<domain>.<tld>
    domain_pattern = re.compile(r"((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,63})(?=[^A-Za-z0-9-]|$)")

    def _replace(match: re.Match[str]) -> str:
        domain = match.group(1)

        # 白名单直接放行
        if domain in whitelist:
            return domain

        # 各模式处理
        if mode == "remove":
            return ""
        if mode == "uppercase":
            return domain.upper()
        if mode == "tldUppercase":
            parts = domain.split(".")
            if len(parts) > 1:
                parts[-1] = parts[-1].upper()
            return ".".join(parts)
        # 默认走点号替换类模式（unicode / space / fullStop）
        replacer = dot_replacer_map.get(mode, "\u200E.")
        return domain.replace(".", replacer)

    return domain_pattern.sub(_replace, text)


# ============== 频率限制系统 ==============

@dataclass
class RateLimitConfig:
    """频率限制配置"""
    max_requests: int  # 最大请求数
    time_window: float  # 时间窗口（秒）
    cooldown: float = 0.0  # 单次操作最小间隔（秒）


class RateLimiter:
    """频率限制器

    支持两种限制模式：
    1. 滑动窗口：在指定时间窗口内限制最大请求数
    2. 冷却时间：两次操作之间的最小间隔
    """

    def __init__(self):
        # 用户请求历史记录 {user_id: deque[timestamp]}
        self._request_history: Dict[str, deque] = defaultdict(lambda: deque())
        # 用户最后请求时间 {user_id: timestamp}
        self._last_request_time: Dict[str, float] = {}
        # 不同操作的配置
        self._configs: Dict[str, RateLimitConfig] = {}

    def register_action(self, action: str, config: RateLimitConfig):
        """注册操作的频率限制配置"""
        self._configs[action] = config

    def check_rate_limit(self, user_id: str, action: str) -> tuple[bool, Optional[str]]:
        """检查是否超过频率限制

        Returns:
            (是否允许, 错误消息)
        """
        if action not in self._configs:
            return True, None

        config = self._configs[action]
        current_time = time.time()

        # 检查冷却时间
        if config.cooldown > 0:
            last_time = self._last_request_time.get(user_id, 0)
            if current_time - last_time < config.cooldown:
                remaining = config.cooldown - (current_time - last_time)
                return False, f"⏳ 操作过于频繁，请等待 {remaining:.1f} 秒后再试"

        # 检查滑动窗口
        if config.max_requests > 0 and config.time_window > 0:
            history = self._request_history[user_id]

            # 清理过期记录
            cutoff_time = current_time - config.time_window
            while history and history[0] < cutoff_time:
                history.popleft()

            # 检查是否超过限制
            if len(history) >= config.max_requests:
                return False, f"⚠️ 操作过于频繁，请在 {config.time_window} 秒内最多操作 {config.max_requests} 次"

        return True, None

    def record_request(self, user_id: str, action: str):
        """记录用户请求"""
        if action not in self._configs:
            return

        current_time = time.time()
        config = self._configs[action]

        # 记录请求时间
        self._last_request_time[user_id] = current_time

        # 记录到滑动窗口
        if config.max_requests > 0 and config.time_window > 0:
            self._request_history[user_id].append(current_time)


# 全局频率限制器实例
rate_limiter = RateLimiter()

# 注册默认的操作限制 - 防止高频刷材料
rate_limiter.register_action("move", RateLimitConfig(
    max_requests=25,
    time_window=30,
    cooldown=0.9
))

rate_limiter.register_action("explore", RateLimitConfig(
    max_requests=25,
    time_window=30,
    cooldown=0.9  # 每次探索间隔
))

# 打工系统频率限制 - 防止过度刷金币
rate_limiter.register_action("start_work", RateLimitConfig(
    max_requests=10,  # 每小时最多开始10次工作
    time_window=3600.0,  # 1小时时间窗口
    cooldown=60.0  # 每次开始工作间隔1分钟
))

def check_action_limit(user_id: str, action: str) -> tuple[bool, Optional[str]]:
    """便捷函数：检查操作限制"""
    return rate_limiter.check_rate_limit(user_id, action)


def record_action(user_id: str, action: str):
    """便捷函数：记录操作"""
    rate_limiter.record_request(user_id, action)


def get_weekly_theme() -> dict:
    """获取当前周主题信息（便捷函数）"""
    try:
        from .world.weekly_theme import WeeklyThemeManager
        theme = WeeklyThemeManager.get_current_theme()
        config = WeeklyThemeManager.get_theme_config(theme)
        return {
            "theme": theme,
            "name": config.get("name", ""),
            "emoji": config.get("emoji", ""),
            "description": config.get("description", "")
        }
    except ImportError:
        return {"theme": None, "name": "", "emoji": "", "description": ""}


# ---------------- 周主题氛围 ----------------
from datetime import datetime

_WEEKLY_THEMES: list[dict] = [
    {"name": "地铁惊悸", "emoji": "🚇", "hint": "末班车上总有一个空座，不要坐。", "favored_regions": ["大都会"]},
    {"name": "医院回廊", "emoji": "🏥", "hint": "镜子里的人会先眨眼。", "favored_regions": ["大都会"]},
    {"name": "出租屋镜像", "emoji": "🏠", "hint": "第三次敲门时，别回头。", "favored_regions": ["大都会"]},
    {"name": "午夜公交", "emoji": "🚌", "hint": "司机不会收钱，他收的是别的。", "favored_regions": ["大都会"]},
    {"name": "商场停电", "emoji": "🛒", "hint": "当广播倒放时，躲进衣柜。", "favored_regions": ["大都会"]},
    {"name": "公园无头雕像", "emoji": "🗿", "hint": "影子里多了一张脸。", "favored_regions": ["大都会"]},
    {"name": "图书馆耳语", "emoji": "📚", "hint": "第十三页被撕掉了。", "favored_regions": ["大都会"]},
]

def get_weekly_theme() -> dict:
    """返回当前周主题。
    采用 ISO 周数进行轮换，保证全服一致且无需持久化。
    返回: {name, emoji, hint, favored_regions}
    """
    try:
        iso_week = datetime.now().isocalendar().week
    except AttributeError:
        # 兼容性处理
        iso_week = int(datetime.now().strftime("%W")) or 1
    idx = (iso_week - 1) % len(_WEEKLY_THEMES)
    return _WEEKLY_THEMES[idx]


def format_theme_banner(prefix: str = "本周主题") -> str:
    t = get_weekly_theme()
    return f"{t['emoji']} {prefix}：{t['name']}\n{t['hint']}"


