"""管理员命令: 测试 QQ 群主动消息权限（群消息 + C2C 私信）。"""

from nonebot import logger, on_command
from nonebot.adapters.qq import Bot, Message, MessageEvent
from nonebot.adapters.qq.event import GroupAtMessageCreateEvent
from nonebot.adapters.qq.exception import (
    ActionFailed,
    NetworkError,
    RateLimitException,
    UnauthorizedException,
)
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER


active_message_test = on_command(
    "测试主动消息",
    aliases={"主动消息测试"},
    permission=SUPERUSER,
    priority=1,
    block=True,
)


def _resolve_target(event: MessageEvent, arg_text: str) -> tuple[str | None, str]:
    parts = arg_text.split(maxsplit=1)
    if len(parts) == 2 and len(parts[0]) >= 16:
        return parts[0], parts[1].strip()
    return getattr(event, "group_openid", None), arg_text


@active_message_test.handle()
async def handle_active_message_test(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
):
    """直接调用群主动发送接口，不携带事件 msg_id/event_id。"""
    arg_text = args.extract_plain_text().strip()
    if not arg_text:
        await active_message_test.finish(
            "用法: 测试主动消息 [内容]\n"
            "或: 测试主动消息 <group_openid> <内容>"
        )

    group_openid, content = _resolve_target(event, arg_text)
    if not group_openid:
        await active_message_test.finish(
            "当前事件没有 group_openid，请使用: 测试主动消息 <group_openid> <内容>"
        )
    if not content:
        await active_message_test.finish("主动消息内容不能为空")

    try:
        await bot.send_to_group(group_openid=group_openid, message=content)
    except (ActionFailed, NetworkError, RateLimitException, UnauthorizedException) as e:
        logger.error(f"[Admin] 主动消息测试失败: {e}")
        await active_message_test.finish(f"主动消息发送失败: {e}")

    logger.info(f"[Admin] 主动消息测试已发送到群: {group_openid}")
    await active_message_test.finish("主动消息测试已发出")


# ==================== C2C 私信测试 ====================

c2c_message_test = on_command(
    "测试私信",
    aliases={"私信测试"},
    permission=SUPERUSER,
    priority=1,
    block=True,
)


@c2c_message_test.handle()
async def handle_c2c_message_test(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
):
    """在群里发「测试私信 内容」，bot 会主动私信你。"""
    content = args.extract_plain_text().strip()
    if not content:
        await c2c_message_test.finish("用法: 测试私信 <内容>")

    if not isinstance(event, GroupAtMessageCreateEvent):
        await c2c_message_test.finish("此命令只能在群里使用")

    user_openid = event.author.member_openid
    try:
        await bot.send_to_c2c(openid=user_openid, message=content)
    except (ActionFailed, NetworkError, RateLimitException, UnauthorizedException) as e:
        logger.error(f"[Admin] C2C 私信测试失败: {e}")
        await c2c_message_test.finish(f"C2C 私信发送失败: {e}")

    logger.info(f"[Admin] C2C 私信测试已发送到: {user_openid}")
    await c2c_message_test.finish("C2C 私信已发出，请检查私信")
