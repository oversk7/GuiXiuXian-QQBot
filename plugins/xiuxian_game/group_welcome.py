"""新人进群欢迎。

监听官方「群用户添加」事件（GROUP_MEMBER_ADD，需在 .env 的 intent 中开启
group_members，并在开放平台后台勾选对应事件订阅），通过 event_id 被动回复
向群内发送欢迎卡片，引导新人注册。
"""
from nonebot import logger, on_notice
from nonebot.adapters.qq import Bot, Message, MessageSegment
from nonebot.adapters.qq.event import GroupMemberAddEvent
from nonebot.adapters.qq.models import MessageMarkdown, MessageMarkdownParams

group_welcome = on_notice(priority=5, block=False)


@group_welcome.handle()
async def _(bot: Bot, event: GroupMemberAddEvent):
    try:
        # 新人头像（openid 按接入的机器人 appid 解析，本地/生产均可用）
        avatar_url = f"https://thirdqq.qlogo.cn/qqapp/{bot.self_id}/{event.member_openid}/0"

        title = "🕯️ 新道友踏入诡界"
        desc = "\r".join([
            "道友，你终于来了。",
            "此界名为诡修仙——修的是仙，遇的是诡。",
            "━━━━━━━━━━━━━",
            "【注册】 创建角色，踏入仙途",
            "【新手指引】 学习指令格式",
            "【帮助】 查看全部玩法",
        ])
        hint = "💡 点击下方按钮快速开始"

        template_params = [
            MessageMarkdownParams(key="title", values=[title]),
            MessageMarkdownParams(key="desc", values=[desc]),
            MessageMarkdownParams(key="imgurl", values=[avatar_url]),
            MessageMarkdownParams(key="width", values=["64"]),
            MessageMarkdownParams(key="height", values=["64"]),
            MessageMarkdownParams(key="hint", values=[hint]),
            MessageMarkdownParams(key="t1", values=["注册"]),
            MessageMarkdownParams(key="t2", values=["新手指引"]),
            MessageMarkdownParams(key="t3", values=["帮助"]),
            MessageMarkdownParams(key="t4", values=["签到"]),
        ]
        markdown_msg = MessageMarkdown(
            custom_template_id="102499345_1770445216",
            params=template_params,
        )
        await group_welcome.send(Message(MessageSegment.markdown(markdown_msg)))
    except Exception as e:
        logger.warning(f"[GroupWelcome] 欢迎卡片发送失败，回退文本版: {e}")
        try:
            await group_welcome.send(
                "🕯️ 道友，欢迎来到诡修仙。\n"
                "发送【注册】创建角色，发送【帮助】查看玩法。"
            )
        except Exception as e2:
            logger.warning(f"[GroupWelcome] 欢迎文本发送失败: {e2}")
