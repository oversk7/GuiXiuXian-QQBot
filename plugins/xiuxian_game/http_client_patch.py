"""HTTP 客户端连接复用补丁

NoneBot 的 httpx 驱动每次 request() 都新建 httpx.AsyncClient(重新 TCP+TLS 握手),
QQ 适配器所有发消息 API 调用都走该路径,每条回复多耗约 100~150ms。
启动时建立一个常驻 Session 并将 driver.request 指向它,以复用连接。
"""

from nonebot import get_driver, logger
from nonebot.drivers import HTTPClientMixin

driver = get_driver()

_session = None


@driver.on_startup
async def _setup_shared_http_session() -> None:
    global _session
    if not isinstance(driver, HTTPClientMixin):
        return
    _session = driver.get_session()
    await _session.setup()
    driver.request = _session.request  # type: ignore[method-assign]
    logger.info("HTTP连接复用补丁已启用（共享 httpx Session）")


@driver.on_shutdown
async def _close_shared_http_session() -> None:
    if _session is not None:
        await _session.close()
