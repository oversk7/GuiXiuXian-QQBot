"""命令执行失败后的统一业务提示。

后处理器运行时，safe_session / UnitOfWork 已完成回滚和会话清理。
这里只解释明确可识别的异常，不将未知错误冒充背包不足，也不重放命令。
"""

from nonebot import logger
from nonebot.exception import ActionFailed
from nonebot.matcher import Matcher
from nonebot.message import run_postprocessor
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from .infrastructure.exceptions import InventoryCapacityError


INVENTORY_CAPACITY_MESSAGE = "⚠️ 背包空间不足，物品未能全部放入。请先整理背包，再重试刚才的操作。"
DB_CONFLICT_MESSAGE = "⚠️ 数据已被其他操作更新，本次操作未完成，请重试"


def _failure_message(exception: Exception | None) -> str | None:
    """沿有效异常链识别失败原因；显式 cause 优先，忽略被抑制的 context。"""
    seen: set[int] = set()
    exc = exception
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(exc, InventoryCapacityError):
            return INVENTORY_CAPACITY_MESSAGE
        if isinstance(exc, StaleDataError) or (
            isinstance(exc, OperationalError)
            and getattr(exc.orig, "args", (None,))[0] in (1205, 1213, 3572)
        ):
            return DB_CONFLICT_MESSAGE
        exc = exc.__cause__ or (None if exc.__suppress_context__ else exc.__context__)
    return None


@run_postprocessor
async def handle_command_error(matcher: Matcher, exception: Exception | None) -> None:
    """已处理的业务失败不会冒泡至此；对未处理的已知失败只回复一次。"""
    message = _failure_message(exception)
    if message is None:
        return
    try:
        # send 不抛 finish 的流程异常；NoneBot 为后处理器提供 matcher 上下文。
        await matcher.send(message)
    except ActionFailed as error:
        logger.warning(f"[CommandError] 失败提示发送失败: {error}")
