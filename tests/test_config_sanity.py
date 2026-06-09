"""游戏配置健全性检查

防止 data/config.yaml 被改出非法数值（如成功率>1、下限>基础值），
让配置改动也受 CI 保护。
"""

from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent.parent / "plugins" / "xiuxian_game" / "data" / "config.yaml"


def _load():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _assert_breakthrough_sane(cfg_break: dict, label: str):
    base = cfg_break.get("base_success_rate", 0.8)
    min_rate = cfg_break.get("min_success_rate", 0.05)
    decay = cfg_break.get("decay_per_level", 0.005)
    assert 0 < min_rate <= base <= 1, f"{label}: 需满足 0 < min({min_rate}) <= base({base}) <= 1"
    assert 0 < decay < 0.1, f"{label}: decay_per_level({decay}) 超出合理范围"
    if "fail_keep_ratio" in cfg_break:
        assert 0 < cfg_break["fail_keep_ratio"] <= 1, f"{label}: fail_keep_ratio 非法"
    if "pity_threshold" in cfg_break:
        assert cfg_break["pity_threshold"] >= 1, f"{label}: pity_threshold 非法"
    if "fail_bonus_rate" in cfg_break:
        assert 0 < cfg_break["fail_bonus_rate"] < 1, f"{label}: fail_bonus_rate 非法"


def test_legacy_breakthrough_config():
    cfg = _load()
    _assert_breakthrough_sane(cfg["cultivate"]["breakthrough"], "cultivate.breakthrough")


def test_new_shard_breakthrough_overrides():
    cfg = _load()
    new_shard = cfg.get("server_profiles", {}).get("new_shard", {})
    override = new_shard.get("cultivate", {}).get("breakthrough")
    if override:
        # 覆盖段与默认段合并后再校验
        merged = {**cfg["cultivate"]["breakthrough"], **override}
        _assert_breakthrough_sane(merged, "server_profiles.new_shard")


def test_monthly_card_config():
    cfg = _load()
    mc = cfg["monthly_card"]
    for tier in ("basic", "premium"):
        assert tier in mc, f"monthly_card 缺少 {tier}"
        assert 0 < mc[tier]["breakthrough_protection"] <= 1
    # 高级月卡权益不应低于基础月卡
    assert mc["premium"]["cultivation_efficiency"] >= mc["basic"]["cultivation_efficiency"]
    assert mc["premium"]["seclusion_time_limit"] >= mc["basic"]["seclusion_time_limit"]


def test_cultivate_basics():
    cfg = _load()
    assert cfg["cultivate"]["cool_down"] > 0
    assert cfg["cultivate"]["base_exp"] > 0
    assert cfg["game"]["max_level"] > 0
