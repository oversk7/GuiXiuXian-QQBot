"""突破成功率公式（纯函数）

从 cultivate/core.py 提取，单一事实来源：
等级衰减 → 失败累加(封顶) → 运气加成(封顶) → 保底必成。
"""


def calculate_breakthrough_chance(
    level: int,
    fail_count: int,
    cfg_break: dict,
    luck_break_bonus: float = 0.0,
) -> float:
    """计算突破成功率。

    Args:
        level: 玩家当前等级
        fail_count: 连续突破失败次数（player.breakthrough_fail_count）
        cfg_break: 突破配置段（config["cultivate"]["breakthrough"]）
        luck_break_bonus: 运气突破加成（调用方用 luck_prob(luck)*0.10 算好传入；
            低于 change_level 时无效）

    Returns:
        0.0~1.0 的成功率；低于 change_level 或达到保底阈值时为 1.0
    """
    change_level = cfg_break["change_level"]
    if level < change_level:
        return 1.0

    base_rate = cfg_break.get("base_success_rate", 0.8)
    decay = cfg_break.get("decay_per_level", 0.005)
    min_rate = cfg_break.get("min_success_rate", 0.05)
    success_chance = max(min_rate, base_rate - decay * (level - change_level))

    # 失败累加机制
    if cfg_break.get("fail_bonus_enabled", True):
        fail_bonus_rate = cfg_break.get("fail_bonus_rate", 0.01)
        success_chance += fail_count * fail_bonus_rate
        # 应用成功率上限
        success_chance = min(success_chance, cfg_break.get("fail_bonus_max_rate", 0.95))

    # 运气突破加成（与失败累加共用同一上限）
    success_chance = min(
        success_chance + luck_break_bonus, cfg_break.get("fail_bonus_max_rate", 0.95)
    )

    # 保底机制：连续失败达到阈值则必定成功
    if fail_count >= cfg_break.get("pity_threshold", 10):
        return 1.0

    return success_chance
