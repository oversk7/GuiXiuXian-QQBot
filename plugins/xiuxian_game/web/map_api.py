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
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from nonebot import logger
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ..models.db import AsyncSessionLocal
from ..models.player import Player
from ..models.navigation_task import NavigationTask
from ..models.guild import Guild
from ..world.navigation import _tiles_per_second

router = APIRouter()

# ==================== 城镇坐标 ====================

CITIES = [
    # 京畿
    {"name": "上京", "x": 0, "y": 0, "desc": "天下之都"},
    {"name": "郸城", "x": 150, "y": -130, "desc": "商贸重镇"},
    {"name": "摩配镇", "x": 80, "y": 160, "desc": "机关奇械"},
    {"name": "天海卫", "x": 250, "y": -50, "desc": "东面门户"},
    {"name": "石关", "x": -200, "y": -150, "desc": "西面关隘"},
    # 江南
    {"name": "金陵", "x": 450, "y": -480, "desc": "六朝古都"},
    {"name": "姑苏", "x": 600, "y": -520, "desc": "丝绸名城"},
    {"name": "临安", "x": 580, "y": -650, "desc": "茶道圣地"},
    {"name": "海门", "x": 720, "y": -480, "desc": "远洋商港"},
    {"name": "舟山", "x": 700, "y": -600, "desc": "海岛渔城"},
    # 南海
    {"name": "荔湾镇", "x": 250, "y": -1350, "desc": "岭南重镇"},
    {"name": "鹏城", "x": 350, "y": -1450, "desc": "新兴商港"},
    {"name": "鹭岛", "x": 550, "y": -1200, "desc": "南洋门户"},
    {"name": "琼崖", "x": 200, "y": -1650, "desc": "最南孤岛"},
    # 蜀地
    {"name": "锦官城", "x": -780, "y": -750, "desc": "天府之国"},
    {"name": "大昌市", "x": -600, "y": -800, "desc": "西南枢纽"},
    {"name": "剑阁", "x": -650, "y": -650, "desc": "天险要道"},
    {"name": "夜郎", "x": -900, "y": -950, "desc": "蛮荒秘境"},
    {"name": "云岭", "x": -850, "y": -1150, "desc": "灵山药谷"},
    # 关中
    {"name": "长安", "x": -500, "y": -280, "desc": "武道圣地"},
    {"name": "神都", "x": -350, "y": -320, "desc": "佛道交汇"},
    {"name": "陈仓", "x": -650, "y": -350, "desc": "兵家之地"},
    {"name": "金城", "x": -900, "y": -180, "desc": "丝路起点"},
    # 中原
    {"name": "汴梁", "x": -100, "y": -450, "desc": "中原腹地"},
    {"name": "颍川", "x": -200, "y": -380, "desc": "名士之乡"},
    {"name": "江夏", "x": -30, "y": -680, "desc": "南北咽喉"},
    {"name": "潭州", "x": -80, "y": -900, "desc": "书院圣地"},
    # 北境
    {"name": "辽阳", "x": 350, "y": 650, "desc": "铁骑之城"},
    {"name": "龙城", "x": 280, "y": 900, "desc": "边塞军城"},
    {"name": "风雪镇", "x": 150, "y": 1200, "desc": "缉邪司总部"},
    {"name": "冰原堡", "x": 200, "y": 1400, "desc": "最北要塞"},
    # 西域
    {"name": "玉门", "x": -1200, "y": 100, "desc": "西域门户"},
    {"name": "楼兰", "x": -1400, "y": 250, "desc": "失落古城"},
    {"name": "龟兹", "x": -1550, "y": 300, "desc": "异域风情"},
    {"name": "轮台", "x": -1700, "y": 350, "desc": "最西前哨"},
]

# ==================== HTML 缓存（启动时加载，避免阻塞事件循环） ====================

_NONCE_PLACEHOLDER = "%%CSP_NONCE%%"


def _load_html() -> str:
    """读取地图 HTML（每次读磁盘，方便热更新调试）"""
    html_path = Path(__file__).parent / "static" / "map.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return ""


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
            # 只查 7 天内签到过的活跃玩家，避免全表 2900+ 行拖慢前端
            cutoff = datetime.now() - timedelta(days=7)
            stmt = (
                select(
                    Player.uid,
                    Player.nickname,
                    Player.level,
                    Player.agility,
                    Player.real_world_x,
                    Player.real_world_y,
                    Player.dungeon_level,
                    NavigationTask.target_x,
                    NavigationTask.target_y,
                    NavigationTask.last_update,
                )
                .outerjoin(NavigationTask, Player.id == NavigationTask.player_id)
                .where(Player.last_sign >= cutoff)
            )
            rows = (await session.execute(stmt)).all()

            # 阴宅: 所有拥有阴宅的玩家
            mansion_stmt = (
                select(
                    Player.nickname,
                    Player.mansion_x,
                    Player.mansion_y,
                    Player.mansion_level,
                )
                .where(Player.mansion_level > 0)
                .where(Player.mansion_x.is_not(None))
                .where(Player.mansion_y.is_not(None))
            )
            mansion_rows = (await session.execute(mansion_stmt)).all()

            # 公会基地: 所有有坐标的公会
            guild_stmt = (
                select(
                    Guild.name,
                    Guild.base_x,
                    Guild.base_y,
                    Guild.level,
                )
                .where(Guild.base_x.is_not(None))
                .where(Guild.base_y.is_not(None))
            )
            guild_rows = (await session.execute(guild_stmt)).all()
    except SQLAlchemyError as e:
        logger.error(f"[MapAPI] 数据库查询失败: {e}")
        return _secure(JSONResponse(
            status_code=503,
            content={"error": "服务暂时不可用"},
        ))

    players = []
    now = datetime.now()
    for uid, name, level, agility, rwx, rwy, dl, ntx, nty, nlast in rows:
        px, py = rwx or 0, rwy or 0

        # 导航中：读时插值——库里坐标由 2 分钟轮询推进，这里按
        # 速度×经过时间现算当前展示位置，不写库（基础敏捷近似，
        # 与权威推进的偏差会在下次轮询时自动校正）
        if ntx is not None and nty is not None and nlast is not None:
            elapsed = (now - nlast).total_seconds()
            dx, dy = ntx - px, nty - py
            dist = (dx * dx + dy * dy) ** 0.5
            if elapsed > 0 and dist > 0:
                move = elapsed * _tiles_per_second(max(agility or 0, 0))
                if move >= dist:
                    px, py = ntx, nty
                else:
                    ratio = move / dist
                    px = round(px + dx * ratio, 1)
                    py = round(py + dy * ratio, 1)

        p: dict = {
            "uid": uid,
            "name": name or f"修仙者#{uid}",
            "x": px,
            "y": py,
            "lv": level or 1,
        }
        in_dungeon = (dl or 0) > 0
        if in_dungeon:
            p["dg"] = dl
        if ntx is not None and nty is not None and not in_dungeon:
            p["nav"] = {"tx": ntx, "ty": nty}
        players.append(p)

    mansions = [
        {"owner": name or "无名", "x": mx, "y": my, "lv": mlv}
        for name, mx, my, mlv in mansion_rows
    ]

    guilds = [
        {"name": gname, "x": gx, "y": gy, "lv": glv}
        for gname, gx, gy, glv in guild_rows
    ]

    return _secure(JSONResponse(content={
        "ts": int(time.time()),
        "cities": CITIES,
        "players": players,
        "mansions": mansions,
        "guilds": guilds,
    }))
