"""
装备套装加成服务

从 equipment_sets.yaml 加载套装定义，
根据玩家已装备的 item_id 列表判断激活的套装效果。
"""

from typing import Optional
from pathlib import Path

import yaml

from ..battle.battle_effects import TriggerConfig, TriggerType, EffectType


_set_config: Optional[dict] = None


def _load_config() -> dict:
    global _set_config
    if _set_config is not None:
        return _set_config
    cfg_path = Path(__file__).parent.parent / "data" / "equipment_sets.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        _set_config = yaml.safe_load(f)
    return _set_config


def get_active_set_bonuses(equipped_item_ids: list[str]) -> dict:
    """返回当前激活的套装信息。

    Returns:
        {set_id: {"name", "total_pieces", "equipped_count", "active_bonuses": [
            {"threshold", "description", "t1_bonuses", "triggers"}
        ]}}
    """
    cfg = _load_config()
    result = {}
    id_set = set(equipped_item_ids)

    for set_id, set_def in cfg.get("sets", {}).items():
        pieces = set_def.get("pieces", [])
        count = sum(1 for p in pieces if p in id_set)
        if count < 2:
            continue

        active_bonuses = []
        for threshold, bonus in sorted(set_def.get("bonuses", {}).items()):
            if count >= int(threshold):
                active_bonuses.append({
                    "threshold": int(threshold),
                    "description": bonus.get("description", ""),
                    "t1_bonuses": bonus.get("t1_bonuses", {}),
                    "triggers": bonus.get("triggers", []),
                })

        if active_bonuses:
            result[set_id] = {
                "name": set_def["name"],
                "total_pieces": len(pieces),
                "equipped_count": count,
                "active_bonuses": active_bonuses,
            }

    return result


def get_set_t1_bonuses(equipped_item_ids: list[str]) -> dict[str, float]:
    """合并所有激活套装的T1加成，用于战斗属性计算。"""
    bonuses: dict[str, float] = {}
    for _set_id, info in get_active_set_bonuses(equipped_item_ids).items():
        for ab in info["active_bonuses"]:
            for attr, val in ab["t1_bonuses"].items():
                bonuses[attr] = bonuses.get(attr, 0) + float(val)
    return bonuses


def get_set_trigger_configs(equipped_item_ids: list[str]) -> list[TriggerConfig]:
    """将激活套装的触发效果转为 TriggerConfig 列表。"""
    triggers = []
    for _set_id, info in get_active_set_bonuses(equipped_item_ids).items():
        set_name = info["name"]
        for ab in info["active_bonuses"]:
            for trig_def in ab["triggers"]:
                try:
                    tc = TriggerConfig(
                        trigger=TriggerType(trig_def["trigger"]),
                        chance=float(trig_def.get("chance", 100)),
                        effect=EffectType(trig_def["effect"]),
                        value=float(trig_def.get("value", 0)),
                        duration=int(trig_def.get("duration", 0)),
                        threshold=float(trig_def.get("threshold", 0)),
                        description=trig_def.get("description", f"{set_name}套装效果"),
                        source_equipment=f"套装·{set_name}",
                    )
                    triggers.append(tc)
                except (ValueError, KeyError):
                    continue
    return triggers


def get_equipment_set_info(item_id: str) -> Optional[dict]:
    """查询某件装备所属的套装信息（不需要激活）。

    Returns:
        {"set_id", "name", "pieces": [item_id, ...], "bonuses": {threshold: desc}} 或 None
    """
    cfg = _load_config()
    for set_id, set_def in cfg.get("sets", {}).items():
        if item_id in set_def.get("pieces", []):
            bonus_descs = {}
            for threshold, bonus in sorted(set_def.get("bonuses", {}).items()):
                bonus_descs[int(threshold)] = bonus.get("description", "")
            return {
                "set_id": set_id,
                "name": set_def["name"],
                "pieces": set_def["pieces"],
                "bonuses": bonus_descs,
            }
    return None
