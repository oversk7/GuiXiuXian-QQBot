"""区服配置解析。

默认配置仍来自 data/config.yaml 顶层字段。每个区服可以通过
server_profiles 覆盖部分配置，从而让新区使用更稳的数值曲线。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .config import config

DEFAULT_SERVER_ID = 1


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged

def get_servers_config() -> dict[int, dict[str, Any]]:
    raw_servers = config.game_config.get("servers", {}) or {}
    servers: dict[int, dict[str, Any]] = {}
    for sid, data in raw_servers.items():
        try:
            server_id = int(sid)
        except (TypeError, ValueError):
            continue
        servers[server_id] = data or {}
    if DEFAULT_SERVER_ID not in servers:
        servers[DEFAULT_SERVER_ID] = {
            "name": "一区",
            "config_profile": "legacy",
            "open_registration": True,
        }
    return servers


def get_server_name(server_id: int | None) -> str:
    sid = server_id or DEFAULT_SERVER_ID
    return get_servers_config().get(sid, {}).get("name", f"{sid}区")


def is_server_open_for_registration(server_id: int) -> bool:
    server = get_servers_config().get(server_id)
    if not server:
        return False
    return bool(server.get("open_registration", True))


def get_server_game_config(server_id: int | None = None) -> dict[str, Any]:
    """返回指定区服的完整游戏配置。

    顶层配置作为 legacy 基线；server_profiles 中对应 profile 只需写覆盖项。
    """
    sid = server_id or DEFAULT_SERVER_ID
    base = deepcopy(config.game_config)
    servers = base.pop("servers", None)
    profiles = base.pop("server_profiles", None) or {}

    server_meta = get_servers_config().get(sid, {})
    profile_name = server_meta.get("config_profile", "legacy")
    profile_override = profiles.get(profile_name, {})

    merged = _deep_merge(base, profile_override)
    merged["server"] = {
        "id": sid,
        "name": get_server_name(sid),
        "config_profile": profile_name,
    }
    if servers is not None:
        merged["servers"] = servers
    if profiles is not None:
        merged["server_profiles"] = profiles
    return merged
