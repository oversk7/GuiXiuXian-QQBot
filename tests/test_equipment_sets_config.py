"""装备套装配置校验

套装完全由 data/equipment_sets.yaml 驱动，本测试保证：
- 每个套装的 pieces 都是 items.yaml 中真实存在的 EQUIPMENT
- t1_bonuses 的键都是战斗档认可的属性键（否则静默不生效）
- triggers 能被 set_bonus_service 成功转换为 TriggerConfig（枚举值合法）
- 套装之间部件不重叠（一件装备只属于一个套装）
"""
from pathlib import Path

import yaml

from plugins.xiuxian_game.item.set_bonus_service import (
    get_active_set_bonuses,
    get_set_t1_bonuses,
    get_set_trigger_configs,
    _load_config,
)

DATA_DIR = Path("plugins/xiuxian_game/data")

# 战斗档认可的 T1 属性键（battle_attributes.calculate_effective_attributes 的 base_attrs）
VALID_T1_KEYS = {
    "critical_rate", "critical_power", "combo_rate", "counter_rate",
    "dodge_rate", "accuracy_rate", "skill_crit_rate", "penetration_rate",
    "anti_crit_rate", "anti_combo_rate", "anti_counter_rate",
    "lifesteal_rate", "immobilize_rate", "true_damage_rate", "regen_rate",
}


def _all_equipment_ids() -> set:
    data = yaml.safe_load(open(DATA_DIR / "items.yaml", encoding="utf-8"))
    ids = set()

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                if isinstance(v, dict) and v.get("type") == "EQUIPMENT":
                    ids.add(v["item_id"])
                else:
                    walk(v)

    walk(data)
    return ids


def test_pieces_exist_and_disjoint():
    sets = _load_config()["sets"]
    equip_ids = _all_equipment_ids()
    seen = {}
    for set_id, set_def in sets.items():
        pieces = set_def["pieces"]
        assert len(pieces) >= 2, f"{set_id} 至少需要2件部件"
        for pid in pieces:
            assert pid in equip_ids, f"{set_id} 的部件 {pid} 不是 items.yaml 中的装备"
            assert pid not in seen, f"{pid} 同时属于 {seen.get(pid)} 和 {set_id}"
            seen[pid] = set_id


def test_t1_keys_valid():
    sets = _load_config()["sets"]
    for set_id, set_def in sets.items():
        for threshold, bonus in set_def.get("bonuses", {}).items():
            assert int(threshold) <= len(set_def["pieces"]), \
                f"{set_id} 的 {threshold}件加成超过部件总数"
            for key in bonus.get("t1_bonuses", {}):
                assert key in VALID_T1_KEYS, f"{set_id} 的 t1 键 {key} 不被战斗档认可"


def test_triggers_all_convert():
    """全部件穿满时，yaml 中定义的每条 trigger 都应转换成功（无静默丢弃）。"""
    sets = _load_config()["sets"]
    for set_id, set_def in sets.items():
        pieces = set_def["pieces"]
        expected = sum(
            len(b.get("triggers", []))
            for b in set_def.get("bonuses", {}).values()
        )
        configs = get_set_trigger_configs(pieces)
        assert len(configs) == expected, \
            f"{set_id} 有 trigger 转换失败（枚举值不合法？）：期望{expected}，实际{len(configs)}"


def test_activation_thresholds():
    sets = _load_config()["sets"]
    for set_id, set_def in sets.items():
        pieces = set_def["pieces"]
        # 只穿1件不激活
        assert set_id not in get_active_set_bonuses(pieces[:1])
        # 穿2件激活2件档
        active = get_active_set_bonuses(pieces[:2])
        assert set_id in active, f"{set_id} 2件未激活"
        assert active[set_id]["active_bonuses"][0]["threshold"] == 2
        # 全穿激活全部档位
        active_full = get_active_set_bonuses(pieces)
        thresholds = [ab["threshold"] for ab in active_full[set_id]["active_bonuses"]]
        assert thresholds == sorted(int(t) for t in set_def.get("bonuses", {}))
        # t1 合并数值为正
        merged = get_set_t1_bonuses(pieces)
        for key, val in merged.items():
            assert val > 0, f"{set_id} 合并后 {key} 非正数"
