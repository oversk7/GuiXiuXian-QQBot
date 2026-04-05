"""Web 模块 - 在 NoneBot2 的 FastAPI 实例上挂载地图 API 路由"""

from nonebot import get_driver, logger

driver = get_driver()


@driver.on_startup
async def _register_web_routes():
    from nonebot import get_app
    from .map_api import router
    from .tower_api import router as tower_router

    app = get_app()
    app.include_router(router)
    app.include_router(tower_router)
    logger.success("[Web] 路由已挂载: /map, /api/map/data, /tower, /api/tower/data")
