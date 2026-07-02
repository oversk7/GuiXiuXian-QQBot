"""剧本库：把生成过的剧本留档，供复用开局。

复用把开局成本从 6 次 LLM 调用降到 1 次（仅开场正文）。
玩没玩过不做记录，剧透与否靠玩家自觉。
存储为 data/scenarios/scn_XXXX.json，低频文件操作，无需数据库。
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime
from typing import Any

from .common import DirectoryNames, resolve_data_dir
from .core import GameSession

logger = logging.getLogger(__name__)

PLUGIN_DIR = os.path.dirname(__file__)

# 剧本模板保存的 GameSession 字段（生成器的全部产出）
TEMPLATE_FIELDS = (
    "scene_name",
    "background",
    "player_identity",
    "hidden_truth",
    "rules",
    "win_condition",
    "clues",
    "core_symbols",
    "scene_structure",
    "npc_guidance",
    "rule_network",
)

_lock = threading.Lock()


def _scenarios_dir() -> str:
    path = os.path.join(resolve_data_dir(PLUGIN_DIR, DirectoryNames.DATA), "scenarios")
    os.makedirs(path, exist_ok=True)
    return path


def _file_path(scenario_id: int) -> str:
    return os.path.join(_scenarios_dir(), f"scn_{scenario_id:04d}.json")


def _load_file(path: str) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        logger.warning("剧本文件损坏或不可读: %s", path)
        return None


def _write_file(path: str, data: dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def _all_scenarios() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for name in sorted(os.listdir(_scenarios_dir())):
        if re.fullmatch(r"scn_\d+\.json", name):
            data = _load_file(os.path.join(_scenarios_dir(), name))
            if data:
                items.append(data)
    return items


def save_scenario(session: GameSession) -> int:
    """生成成功后把剧本存入库，返回剧本编号。"""
    with _lock:
        existing = [
            int(m.group(1))
            for name in os.listdir(_scenarios_dir())
            if (m := re.fullmatch(r"scn_(\d+)\.json", name))
        ]
        scenario_id = max(existing, default=0) + 1

        data: dict[str, Any] = {
            "id": scenario_id,
            "mode": session.game_mode,
            "created_at": datetime.now().isoformat(),
            "stats": {"plays": 1, "endings": {}},
            "template": {field: getattr(session, field, None) for field in TEMPLATE_FIELDS},
        }
        _write_file(_file_path(scenario_id), data)

    logger.info("剧本已入库: #%s 《%s》", scenario_id, session.scene_name)
    return scenario_id


def list_available(mode: str = "单人") -> list[dict[str, Any]]:
    """列出指定模式的全部剧本摘要。"""
    result = []
    for data in _all_scenarios():
        if data.get("mode") != mode:
            continue
        template = data.get("template") or {}
        stats = data.get("stats") or {}
        endings = stats.get("endings") or {}
        cleared = sum(v for k, v in endings.items() if k in ("perfect", "success", "cleared"))
        result.append(
            {
                "id": data.get("id"),
                "scene_name": template.get("scene_name", "未知场景"),
                "plays": stats.get("plays", 0),
                "cleared": cleared,
            }
        )
    return result


def load_scenario(scenario_id: int) -> dict[str, Any] | None:
    return _load_file(_file_path(scenario_id))


def build_session_from_scenario(data: dict[str, Any], group_id: str) -> GameSession:
    """用库存剧本模板构建新的 GameSession（玩家与运行时状态由激活流程补齐）。"""
    template = data.get("template") or {}
    session = GameSession(
        group_id=group_id,
        scene_name=template.get("scene_name", "未知场景"),
        background=template.get("background", ""),
        player_identity=template.get("player_identity", "访客"),
        hidden_truth=template.get("hidden_truth", ""),
        game_mode=str(data.get("mode", "单人")),
        rules=template.get("rules") or [],
        win_condition=template.get("win_condition", ""),
        clues=template.get("clues") or [],
        core_symbols=template.get("core_symbols") or [],
        scene_structure=template.get("scene_structure") or {},
        npc_guidance=template.get("npc_guidance") or {},
    )
    session.rule_network = template.get("rule_network") or {}
    session.world_flags["scenario_id"] = int(data.get("id", 0))
    return session


def record_play(scenario_id: int) -> None:
    with _lock:
        data = _load_file(_file_path(scenario_id))
        if not data:
            return
        stats = data.setdefault("stats", {"plays": 0, "endings": {}})
        stats["plays"] = int(stats.get("plays", 0)) + 1
        _write_file(_file_path(scenario_id), data)


def record_result(scenario_id: int, ending_type: str) -> None:
    """结局回写：用于统计剧本质量（通关率）。"""
    with _lock:
        data = _load_file(_file_path(scenario_id))
        if not data:
            return
        endings = data.setdefault("stats", {}).setdefault("endings", {})
        key = str(ending_type or "unknown")
        endings[key] = int(endings.get(key, 0)) + 1
        _write_file(_file_path(scenario_id), data)
