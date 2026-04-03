"""地图 Web API — 提供玩家位置、城镇、导航数据

安全措施:
1. 不暴露玩家平台 ID（QQ 号），只返回 UID 和昵称
2. IP 级速率限制 (30 req/min)，基于 request.client.host（不信任 X-Forwarded-For）
3. 安全响应头 (CSP with nonce, X-Frame-Options 等)
4. 查询参数校验
5. 数据库异常兜底
"""

from __future__ import annotations

import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from nonebot import logger
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ..models.db import AsyncSessionLocal
from ..models.player import Player
from ..models.navigation_task import NavigationTask

router = APIRouter()

# ==================== 城镇坐标 ====================

CITIES = [
    {"name": "上京", "x": 0, "y": 0, "desc": "政治中心"},
    {"name": "北郊", "x": 100, "y": 460, "desc": "工业区"},
    {"name": "东郊", "x": 390, "y": 50, "desc": "制造基地"},
    {"name": "西郊", "x": -420, "y": 140, "desc": "文化区"},
    {"name": "南郊", "x": -100, "y": -480, "desc": "港口"},
    {"name": "金陵", "x": 220, "y": -350, "desc": "古都"},
    {"name": "云岭", "x": -250, "y": 490, "desc": "山区"},
    {"name": "郸城", "x": 120, "y": 120, "desc": "商业重镇"},
    {"name": "荔湾镇", "x": 120, "y": 200, "desc": "特色小镇"},
    {"name": "摩配镇", "x": 80, "y": 140, "desc": "机械城"},
    {"name": "风雪镇", "x": -5, "y": 390, "desc": "边境小镇"},
    {"name": "舟山", "x": 200, "y": -200, "desc": "海岛城市"},
    {"name": "大昌市", "x": -400, "y": -240, "desc": "西南商埠"},
]

# ==================== HTML 缓存（启动时加载，避免阻塞事件循环） ====================

_html_cache: str | None = None
_NONCE_PLACEHOLDER = "%%CSP_NONCE%%"


def _load_html() -> str:
    global _html_cache
    if _html_cache is None:
        html_path = Path(__file__).parent / "static" / "map.html"
        if html_path.exists():
            _html_cache = html_path.read_text(encoding="utf-8")
        else:
            _html_cache = ""
    return _html_cache


# ==================== 速率限制器 ====================


class _RateLimiter:
    """简易内存速率限制器，IP → 时间戳列表，自动清理过期条目防止内存膨胀"""

    MAX_IPS = 10_000  # 最多跟踪的 IP 数量

    def __init__(self, max_requests: int = 30, window: int = 60):
        self.max_requests = max_requests
        self.window = window
        self._hits: dict[str, list[float]] = {}

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        cutoff = now - self.window

        # 获取并清理该 IP 的过期记录
        hits = [t for t in self._hits.get(ip, []) if t > cutoff]

        if len(hits) >= self.max_requests:
            self._hits[ip] = hits
            return False

        hits.append(now)
        self._hits[ip] = hits

        # 防止内存无限增长：条目过多时清理最旧的
        if len(self._hits) > self.MAX_IPS:
            self._cleanup(cutoff)

        return True

    def _cleanup(self, cutoff: float) -> None:
        """批量清理过期和空条目"""
        to_delete = [ip for ip, ts in self._hits.items() if not ts or ts[-1] < cutoff]
        for ip in to_delete:
            del self._hits[ip]


_limiter = _RateLimiter(max_requests=30, window=60)

# ==================== 安全响应头 ====================


def _secure(resp: JSONResponse) -> JSONResponse:
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ==================== 路由 ====================


@router.get("/map", response_class=HTMLResponse)
async def serve_map() -> HTMLResponse:
    """提供地图前端页面（CSP nonce 防 XSS）"""
    content = _load_html()
    if not content:
        return HTMLResponse(content="<h1>地图页面未找到</h1>", status_code=404)

    # 每次请求生成随机 nonce，替换占位符注入到 script 标签
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


@router.get("/api/map/data")
async def get_map_data(request: Request) -> JSONResponse:
    """返回地图所需全部数据 (玩家位置 + 城镇 + 导航任务)

    安全: 不返回玩家平台 ID, 只返回 UID/昵称/游戏坐标。
    """
    # 速率限制 — 只信任 request.client.host，不信任可伪造的 X-Forwarded-For
    client_ip = request.client.host if request.client else "unknown"

    if not _limiter.is_allowed(client_ip):
        return _secure(JSONResponse(
            status_code=429,
            content={"error": "请求过于频繁，请稍后再试"},
        ))

    try:
        async with AsyncSessionLocal() as session:
            # 一次查询：玩家 LEFT JOIN 导航任务（不查 Player.id 即 QQ 号）
            stmt = (
                select(
                    Player.uid,
                    Player.nickname,
                    Player.level,
                    Player.real_world_x,
                    Player.real_world_y,
                    Player.dungeon_level,
                    NavigationTask.target_x,
                    NavigationTask.target_y,
                )
                .outerjoin(NavigationTask, Player.id == NavigationTask.player_id)
            )
            rows = (await session.execute(stmt)).all()
    except SQLAlchemyError as e:
        logger.error(f"[MapAPI] 数据库查询失败: {e}")
        return _secure(JSONResponse(
            status_code=503,
            content={"error": "服务暂时不可用"},
        ))

    players = []
    for uid, name, level, rwx, rwy, dl, ntx, nty in rows:
        p: dict = {
            "uid": uid,
            "name": name or f"修仙者#{uid}",
            "x": rwx or 0,
            "y": rwy or 0,
            "lv": level or 1,
        }
        in_dungeon = (dl or 0) > 0
        if in_dungeon:
            p["dg"] = dl
        if ntx is not None and nty is not None and not in_dungeon:
            p["nav"] = {"tx": ntx, "ty": nty}
        players.append(p)

    return _secure(JSONResponse(content={
        "ts": int(time.time()),
        "cities": CITIES,
        "players": players,
    }))
