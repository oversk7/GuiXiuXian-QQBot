from nonebot.adapters.qq import Message, MessageEvent
from typing import Optional, Dict
from .config import config
import math

import time
from collections import defaultdict, deque
from dataclasses import dataclass


def message_add_head(content: str, event: Optional[MessageEvent] = None) -> Message:
    """
    后续可能添加统一的消息头
    """
    head = "『诡修仙』\n"
    return Message(head + content)



def calculate_level_up_exp(current_level: int, server_id: int | None = None) -> int:
    """
    根据配置计算升级所需经验
    使用混合曲线：前期线性增长，后期指数增长
    """
    if server_id is not None:
        from .server_config import get_server_game_config
        cfg = get_server_game_config(server_id)["game"]
    else:
        cfg = config.game_config["game"]
    base = cfg["base_exp"]
    curve = cfg["exp_curve"]

    if current_level < curve["curve_change_level"]:
        # 前期：一次函数
        return int(base + (current_level-1) * curve["early_multiplier"])
    else:
        # 后期：二次函数
        level_diff = current_level - curve["curve_change_level"]
        return int(calculate_level_up_exp(curve["curve_change_level"] - 1, server_id) + (level_diff ** 2) * curve["late_multiplier"])


def generate_progress_bar(current: int, maximum: int, length: int = 8) -> str:
    """
    生成简洁的进度条
    :param current: 当前值
    :param maximum: 最大值
    :param length: 进度条长度（默认8格）
    :return: 格式化的进度条字符串 "[████░░░░] 50%"
    """
    if maximum <= 0:
        percentage = 0
    else:
        percentage = min(current / maximum, 1.0)  # 限制最大100%

    filled = int(percentage * length)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {int(percentage * 100)}%"


def calculate_cultivation_times_needed(current_exp: int, max_exp: int, avg_exp_per_cultivation: int) -> int:
    """
    计算还需要修炼多少次才能升级
    :param current_exp: 当前经验
    :param max_exp: 升级所需经验
    :param avg_exp_per_cultivation: 平均每次修炼获得的经验
    :return: 还需修炼次数
    """
    if avg_exp_per_cultivation <= 0:
        return 999  # 防止除零错误

    remaining_exp = max(max_exp - current_exp, 0)
    times = math.ceil(remaining_exp / avg_exp_per_cultivation)
    return times



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
    """根据 *Luck* 值返回 0‒1 之间的触发概率，符合"先稳后急再缓"的 S 型。

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


def luck_prob_tiered(luck_value: int | float) -> float:
    """分段幸运概率函数 - 解决高幸运值边际递减问题

    分段机制 (倍率模式):
    - 0-149: 使用原Logistic曲线 (基础段,最大~0.997)
    - 150-499: 基础 + 0.2倍率 = 最大~1.197
    - 500-999: 基础 + 0.3倍率 = 最大~1.297
    - 1000-1999: 基础 + 0.4倍率 = 最大~1.397
    - 2000-2999: 基础 + 0.5倍率 = 最大~1.497
    - 3000-4999: 基础 + 0.6倍率 = 最大~1.597
    - 5000-7999: 基础 + 0.7倍率 = 最大~1.697
    - 8000-9999: 基础 + 0.8倍率 = 最大~1.797
    - 10000+: 基础 + 1.0倍率 = 最大~1.997 (传说段)

    参数
    ------
    luck_value : int | float
        玩家当前 Luck 值。

    返回
    ----
    float
        概率因子 (可以超过1.0,用于倍率计算)

    示例
    ----
    >>> luck_prob_tiered(90)    # ~0.882 (基础段)
    >>> luck_prob_tiered(150)   # ~1.197 (第2段)
    >>> luck_prob_tiered(2000)  # ~1.497 (第5段)
    >>> luck_prob_tiered(3000)  # ~1.597 (第6段)
    >>> luck_prob_tiered(10000) # ~1.997 (第9段传说)
    """
    # 基础段 (原Logistic曲线)
    base_prob = luck_prob(luck_value, midpoint=60, steepness=30)

    # 分段额外加成 (9段制)
    tier_bonus = 0.0

    if luck_value >= 10000:
        tier_bonus = 1.0  # 传说段
    elif luck_value >= 8000:
        tier_bonus = 0.8  # 第8段
    elif luck_value >= 5000:
        tier_bonus = 0.7  # 第7段
    elif luck_value >= 3000:
        tier_bonus = 0.6  # 第6段
    elif luck_value >= 2000:
        tier_bonus = 0.5  # 第5段
    elif luck_value >= 1000:
        tier_bonus = 0.4  # 第4段
    elif luck_value >= 500:
        tier_bonus = 0.3  # 第3段
    elif luck_value >= 150:
        tier_bonus = 0.2  # 第2段

    # 组合: 基础概率 + 分段加成 (无上限,允许>1.0)
    final_prob = base_prob + tier_bonus
    return final_prob


def damage_reduction_rate(defense: int | float) -> float:
    """计算防御力对应的免伤率

    使用平方根调节公式：免伤率 = 防御 / (防御 + 300 + 30√防御)

    这个公式的特点：
    1. 收益递减：防御越高，每点防御带来的免伤提升越小
    2. 全程有效：100-3000防御区间每个阶段都有可见收益
    3. 约2850防御触及60%硬顶，不会过早封顶
    4. 与原公式同形（d/(d+K)），只是K随防御值缓慢增大

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

    # 平方根调节公式：d / (d + 300 + 30*sqrt(d))
    # 相比原公式 d/(d+300)，分母多了 30*sqrt(d) 项
    # 使曲线在高防御区间增长更缓慢，封顶点从450推迟到约2850
    reduction = defense / (defense + 300 + 30 * math.sqrt(defense))

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

# 注意：通用指令（move、explore 等）的速率限制已迁移到 message_guard.py 统一处理
# 这里仅保留特殊业务逻辑的速率限制配置

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



