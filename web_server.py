"""
简单的Web服务器，用于托管游戏指南页面
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from pathlib import Path
import logging

app = FastAPI(title="诡修仙游戏指南", description="诡修仙游戏的web指南页面")

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 恶意路径黑名单
MALICIOUS_PATHS = [
    "phpmyadmin", "pma", "mysql", "sqlmanager", "webadmin",
    "admin", "wp-admin", "phpmanager", "dbadmin", "websql",
    "sqlweb", "webdb", "mysqladmin", "php-myadmin"
]

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """安全中间件: 过滤恶意扫描请求"""
    path = request.url.path.lower().strip("/")

    # 检查是否为恶意扫描路径
    for malicious in MALICIOUS_PATHS:
        if malicious in path:
            logger.warning(f"🚫 拦截恶意扫描: {request.client.host} -> {request.url.path}")
            return JSONResponse(
                status_code=403,
                content={"detail": "Access Forbidden"}
            )

    # 记录正常访问
    if path and path not in ["health", "favicon.ico"]:
        logger.info(f"✅ 正常访问: {request.client.host} -> {request.url.path}")

    response = await call_next(request)
    return response

# CORS配置(如果需要跨域访问)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境建议限制具体域名
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent

# 挂载静态文件目录（如果有的话）
static_dir = PROJECT_ROOT / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", response_class=HTMLResponse)
async def game_guide():
    """游戏指南主页"""
    guide_file = PROJECT_ROOT / "game_guide.html"
    
    if not guide_file.exists():
        raise HTTPException(status_code=404, detail="游戏指南文件不存在")
    
    try:
        with open(guide_file, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取文件失败: {str(e)}")

@app.get("/guide", response_class=HTMLResponse)
async def guide_alias():
    """游戏指南别名路径"""
    return await game_guide()

@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "message": "诡修仙游戏指南服务运行正常"}

@app.get("/api/info")
async def game_info():
    """游戏基本信息API"""
    return {
        "game_name": "诡修仙",
        "description": "诡异风格的文字修仙游戏",
        "qq_group": "962494679",
        "features": [
            "修炼系统 - 突破境界获得属性点",
            "诡域探索 - 无限层副本系统", 
            "装备系统 - 锻造升阶镶嵌宝石",
            "跑商系统 - 利用差价赚取金币",
            "炼丹系统 - 制作丹药提升属性",
            "公会系统 - 社交合作获得福利"
        ],
        "quick_start": [
            "注册 - 创建角色",
            "修炼 - 开始修炼",
            "面板 - 查看属性", 
            "帮助 - 查看指令"
        ]
    }

if __name__ == "__main__":
    # 开发环境运行
    # 安全提示: 使用127.0.0.1仅允许本地访问,防止外部扫描攻击
    uvicorn.run(
        "web_server:app",
        host="127.0.0.1",  # 仅本地访问
        port=8888,
        reload=True,
        log_level="info"
    )
