"""突破成功率公式单元测试

覆盖：等级门槛、衰减曲线、下限、失败累加、封顶、运气加成、保底、双区服配置。
不依赖数据库和 nonebot 环境。
"""

import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
plugins_path = project_root / "plugins" / "xiuxian_game"
sys.path.insert(0, str(plugins_path))

from formulas.breakthrough import calculate_breakthrough_chance

# 与 data/config.yaml 中 cultivate.breakthrough 一致（一区/legacy）
LEGACY = {
    "change_level": 30,
    "base_success_rate": 0.8,
    "decay_per_level": 0.005,
    "min_success_rate": 0.1,
    "fail_bonus_enabled": True,
    "fail_bonus_rate": 0.01,
    "fail_bonus_max_rate": 0.95,
    "pity_threshold": 10,
}

# 与 data/config.yaml 中 server_profiles.new_shard 一致（二区）
NEW_SHARD = {
    **LEGACY,
    "change_level": 25,
    "base_success_rate": 0.75,
    "decay_per_level": 0.006,
    "min_success_rate": 0.12,
}


def test_below_change_level_always_succeeds():
    assert calculate_breakthrough_chance(1, 0, LEGACY) == 1.0
    assert calculate_breakthrough_chance(29, 0, LEGACY) == 1.0
    # 低于门槛时失败数和运气都不影响
    assert calculate_breakthrough_chance(29, 99, LEGACY, luck_break_bonus=0.1) == 1.0


def test_base_rate_at_change_level():
    assert calculate_breakthrough_chance(30, 0, LEGACY) == pytest.approx(0.8)


def test_decay_curve():
    # level 100: 0.8 - 0.005 * 70 = 0.45
    assert calculate_breakthrough_chance(100, 0, LEGACY) == pytest.approx(0.45)
    # level 130: 0.8 - 0.005 * 100 = 0.30
    assert calculate_breakthrough_chance(130, 0, LEGACY) == pytest.approx(0.30)


def test_min_rate_floor():
    # level 300: 0.8 - 0.005*270 = -0.55 → 下限 0.1
    assert calculate_breakthrough_chance(300, 0, LEGACY) == pytest.approx(0.1)
    assert calculate_breakthrough_chance(9999, 0, LEGACY) == pytest.approx(0.1)


def test_fail_bonus_accumulates():
    # level 100 基础 0.45，5 次失败 +0.05 → 0.50
    assert calculate_breakthrough_chance(100, 5, LEGACY) == pytest.approx(0.50)


def test_fail_bonus_capped():
    # level 30 基础 0.8，50 次失败理论 +0.5 → 封顶 0.95（但 50>=保底阈值→1.0）
    # 用低于保底阈值的失败数验证封顶：9 次失败 0.8+0.09=0.89 未触顶
    assert calculate_breakthrough_chance(30, 9, LEGACY) == pytest.approx(0.89)
    # 关闭保底验证纯封顶行为
    no_pity = {**LEGACY, "pity_threshold": 999}
    assert calculate_breakthrough_chance(30, 50, no_pity) == pytest.approx(0.95)


def test_fail_bonus_disabled():
    cfg = {**LEGACY, "fail_bonus_enabled": False, "pity_threshold": 999}
    assert calculate_breakthrough_chance(100, 5, cfg) == pytest.approx(0.45)


def test_luck_bonus_added_and_capped():
    # level 100 基础 0.45 + 运气 0.10 → 0.55
    assert calculate_breakthrough_chance(100, 0, LEGACY, luck_break_bonus=0.10) == pytest.approx(0.55)
    # 已接近封顶时运气不能突破 0.95
    no_pity = {**LEGACY, "pity_threshold": 999}
    assert calculate_breakthrough_chance(30, 50, no_pity, luck_break_bonus=0.10) == pytest.approx(0.95)


def test_pity_guarantees_success():
    assert calculate_breakthrough_chance(100, 10, LEGACY) == 1.0
    assert calculate_breakthrough_chance(300, 15, LEGACY) == 1.0
    # 差一次不触发保底
    assert calculate_breakthrough_chance(100, 9, LEGACY) == pytest.approx(0.54)


def test_new_shard_profile():
    assert calculate_breakthrough_chance(24, 0, NEW_SHARD) == 1.0
    assert calculate_breakthrough_chance(25, 0, NEW_SHARD) == pytest.approx(0.75)
    # level 100: 0.75 - 0.006 * 75 = 0.30
    assert calculate_breakthrough_chance(100, 0, NEW_SHARD) == pytest.approx(0.30)
    assert calculate_breakthrough_chance(9999, 0, NEW_SHARD) == pytest.approx(0.12)


def test_monotonic_in_level_and_fail_count():
    # 成功率随等级不升、随失败次数不降（抽样验证）
    chances = [calculate_breakthrough_chance(lv, 0, LEGACY) for lv in range(30, 300, 10)]
    assert all(a >= b for a, b in zip(chances, chances[1:]))
    by_fails = [calculate_breakthrough_chance(100, n, LEGACY) for n in range(0, 11)]
    assert all(a <= b for a, b in zip(by_fails, by_fails[1:]))
