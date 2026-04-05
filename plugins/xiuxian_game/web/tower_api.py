"""诡域塔 3D 可视化 API

提供诡域格子数据、玩家分布等信息，供前端3D塔页面使用。

安全措施:
1. 不暴露玩家平台 ID，只返回 UID 和昵称
2. 复用 map_api 的速率限制器
3. 安全响应头
"""

from __future__ import annotations

import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from nonebot import logger
from sqlalchemy import select, func, distinct
from sqlalchemy.exc import SQLAlchemyError

from ..models.db import AsyncSessionLocal
from ..models.player import Player
from ..models.world_tile import WorldTile
from .map_api import _limiter, _secure, _NONCE_PLACEHOLDER

router = APIRouter()


def _load_tower_html() -> str:
    html_path = Path(__file__).parent / "static" / "tower.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return ""


@router.get("/tower", response_class=HTMLResponse)
async def serve_tower() -> HTMLResponse:
    """诡域塔 3D 可视化页面"""
    content = _load_tower_html()
    if not content:
        return HTMLResponse(content="<h1>诡域塔页面未找到</h1>", status_code=404)

    nonce = secrets.token_urlsafe(16)
    page = content.replace(_NONCE_PLACEHOLDER, nonce)

    resp = HTMLResponse(content=page)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    resp.headers["Content-Security-Policy"] = (
        f"default-src 'self'; "
        f"script-src 'nonce-{nonce}'; "
        f"style-src 'self' 'unsafe-inline'; "
        f"img-src 'self' data:; "
        f"connect-src 'self'; "
        f"font-src 'self'"
    )
    return resp


@router.get("/api/tower/data")
async def get_tower_data(request: Request, page: int = 1, size: int = 20) -> JSONResponse:
    """返回诡域塔数据：格子信息 + 玩家分布

    参数:
        page: 页码 (1-based)，每页 size 层
        size: 每页层数，最大50
    """
    client_ip = request.client.host if request.client else "unknown"
    if not _limiter.is_allowed(client_ip):
        return _secure(JSONResponse(status_code=429, content={"error": "请求过于频繁"}))

    # 参数校验
    page = max(1, min(page, 1000))
    size = max(1, min(size, 50))
    start_level = (page - 1) * size + 1
    end_level = start_level + size - 1

    try:
        async with AsyncSessionLocal() as session:
            # 1. 获取全服最高层和各层有人数
            max_level_result = await session.execute(
                select(func.max(Player.max_dungeon_level))
            )
            global_max = max_level_result.scalar() or 0

            # 2. 获取当前在诡域中的玩家
            dungeon_players_stmt = (
                select(
                    Player.uid,
                    Player.nickname,
                    Player.level,
                    Player.dungeon_level,
                    Player.dungeon_x,
                    Player.dungeon_y,
                )
                .where(Player.dungeon_level > 0)
            )
            dp_rows = (await session.execute(dungeon_players_stmt)).all()

            # 3. 获取指定层范围的格子数据
            regions = [f"{lv}层诡域" for lv in range(start_level, end_level + 1)]
            tiles_stmt = (
                select(WorldTile.region, WorldTile.x, WorldTile.y, WorldTile.event_type)
                .where(WorldTile.region.in_(regions))
            )
            tile_rows = (await session.execute(tiles_stmt)).all()

            # 4. 统计每层的探索者人数（历史最高层 >= 该层）
            explorer_counts_stmt = (
                select(
                    Player.max_dungeon_level,
                    func.count(Player.id),
                )
                .where(Player.max_dungeon_level > 0)
                .group_by(Player.max_dungeon_level)
            )
            ec_rows = (await session.execute(explorer_counts_stmt)).all()

    except SQLAlchemyError as e:
        logger.error(f"[TowerAPI] 数据库查询失败: {e}")
        return _secure(JSONResponse(status_code=503, content={"error": "服务暂时不可用"}))

    # 计算每层累计通关人数（max_dungeon_level >= lv 的玩家数）
    # 先建立 max_level -> count 映射，再从高到低累加
    level_counts: dict[int, int] = {}
    for max_lv, cnt in ec_rows:
        level_counts[max_lv] = cnt
    cleared_counts: dict[int, int] = {}
    cumulative = 0
    for lv in range(global_max, 0, -1):
        cumulative += level_counts.get(lv, 0)
        cleared_counts[lv] = cumulative

    # 组装格子数据 per layer
    tiles_by_layer: dict[int, list] = {}
    for region, tx, ty, etype in tile_rows:
        try:
            lv = int(region.replace("层诡域", ""))
        except ValueError:
            continue
        tiles_by_layer.setdefault(lv, []).append({"x": tx, "y": ty, "t": etype})

    # 当前在诡域的玩家
    players_in_dungeon = []
    players_per_layer: dict[int, int] = {}
    for uid, name, plv, dlv, dx, dy in dp_rows:
        players_in_dungeon.append({
            "uid": uid,
            "name": name or f"修仙者#{uid}",
            "lv": plv or 1,
            "dl": dlv,
            "x": dx or 0,
            "y": dy or 0,
        })
        players_per_layer[dlv] = players_per_layer.get(dlv, 0) + 1

    # 构建层数据
    layers = []
    for lv in range(start_level, min(end_level, max(global_max, 1)) + 1):
        layers.append({
            "lv": lv,
            "tiles": tiles_by_layer.get(lv, []),
            "cleared": cleared_counts.get(lv, 0),
            "active": players_per_layer.get(lv, 0),
        })

    return _secure(JSONResponse(content={
        "ts": int(time.time()),
        "global_max": global_max,
        "page": page,
        "size": size,
        "total_layers": max(global_max, 1),
        "layers": layers,
        "players": players_in_dungeon,
    }))
