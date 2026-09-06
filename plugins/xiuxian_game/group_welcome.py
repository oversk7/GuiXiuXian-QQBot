"""新人进群欢迎。

监听官方「群用户添加」事件（GROUP_MEMBER_ADD，需在 .env 的 intent 中开启
group_members，并在开放平台后台勾选对应事件订阅），通过 event_id 被动回复
向群内发送欢迎卡片，引导新人注册。
"""
from nonebot import logger, on_command, on_notice
from nonebot.adapters.qq import Bot, Message, MessageEvent, MessageSegment
from nonebot.adapters.qq.event import GroupMemberAddEvent
from nonebot.adapters.qq.exception import ActionFailed, NetworkError
from nonebot.adapters.qq.models import (
    Action, Button, InlineKeyboard, InlineKeyboardRow, MessageKeyboard, Permission, RenderData,
)
from nonebot.params import CommandArg

from .models.db import safe_session
from .models.group_welcome_setting import GroupWelcomeSetting
from .utils_markdown import build_markdown, cmd

group_welcome = on_notice(priority=5, block=False)
group_welcome_cmd = on_command("进群欢迎", priority=5, block=True)


def _welcome_toggle_button(enabled: bool) -> MessageSegment:
    action = "关闭" if enabled else "开启"
    button = Button(
        id="group_welcome_toggle",
        render_data=RenderData(
            label=f"{action}进群欢迎", visited_label=f"{action}进群欢迎", style=0,
        ),
        action=Action(
            type=2,
            permission=Permission(type=1),
            data=f"进群欢迎 {action}",
            enter=True,
            unsupport_tips="请升级新版QQ后使用按钮",
        ),
    )
    return MessageSegment.keyboard(MessageKeyboard(
        content=InlineKeyboard(rows=[InlineKeyboardRow(buttons=[button])]),
    ))


@group_welcome_cmd.handle()
async def handle_group_welcome_setting(
    event: MessageEvent, args: Message = CommandArg()
) -> None:
    group_openid = getattr(event, "group_openid", None)
    if not group_openid:
        await group_welcome_cmd.finish("请在需要设置进群欢迎的QQ群内使用此指令。")

    action = args.extract_plain_text().strip()
    if action not in ("", "开启", "关闭"):
        await group_welcome_cmd.finish(
            "发送【进群欢迎】查看状态，发送【进群欢迎 开启】或【进群欢迎 关闭】修改本群设置。"
        )

    role = getattr(getattr(event, "author", None), "member_role", None)
    can_manage = role in ("admin", "owner")
    if action and not can_manage:
        await group_welcome_cmd.finish("只有本群群主或管理员可以修改进群欢迎开关。")

    async with safe_session() as session:
        if action:
            enabled = action == "开启"
            await session.merge(GroupWelcomeSetting(group_openid=group_openid, enabled=enabled))
        else:
            setting = await session.get(GroupWelcomeSetting, group_openid)
            enabled = setting.enabled if setting else True

    status = "开启" if enabled else "关闭"
    content = "\n".join([
        "# 进群欢迎",
        f"本群进群欢迎已{status}。",
        cmd("帮助", "进群欢迎帮助"),
    ])
    message = Message(build_markdown(content))
    if can_manage:
        message += _welcome_toggle_button(enabled)
    await group_welcome_cmd.finish(message)


@group_welcome.handle()
async def handle_group_welcome(bot: Bot, event: GroupMemberAddEvent) -> None:
    async with safe_session() as session:
        setting = await session.get(GroupWelcomeSetting, event.group_openid)
        if setting is not None and not setting.enabled:
            return

    try:
        # 新人头像（openid 按接入的机器人 appid 解析，本地/生产均可用）
        avatar_url = f"https://thirdqq.qlogo.cn/qqapp/{bot.self_id}/{event.member_openid}/0"

        content = "\n".join([
            "# 🕯️ 新道友踏入诡界",
            f"![新道友 #64px #64px]({avatar_url})",
            "道友，你终于来了。",
            "此界名为**诡修仙**——修的是仙，遇的是诡。",
            "***",
            f"{cmd('【注册】', '注册')} 创建角色，踏入仙途",
            f"{cmd('【新手指引】', '新手指引')} 学习指令格式",
            f"{cmd('【帮助】', '帮助')} 查看全部玩法",
            "***",
            "> 💡 点击蓝字即可快速开始",
            " | ".join([cmd("注册"), cmd("新手指引"), cmd("帮助"), cmd("签到")]),
        ])
        message = Message(build_markdown(content))
        message += _welcome_toggle_button(enabled=True)
        await group_welcome.send(message)
    except (ActionFailed, NetworkError) as e:
        logger.warning(f"[GroupWelcome] 欢迎卡片发送失败，回退文本版: {e}")
        try:
            await group_welcome.send(
                "🕯️ 道友，欢迎来到诡修仙。\n"
                "发送【注册】创建角色，发送【帮助】查看玩法。"
            )
        except (ActionFailed, NetworkError) as e2:
            logger.warning(f"[GroupWelcome] 欢迎文本发送失败: {e2}")
