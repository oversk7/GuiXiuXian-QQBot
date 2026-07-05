"""新人进群欢迎。

监听官方「群用户添加」事件（GROUP_MEMBER_ADD，需在 .env 的 intent 中开启
group_members，并在开放平台后台勾选对应事件订阅），通过 event_id 被动回复
向群内发送欢迎卡片，引导新人注册。
"""
from nonebot import logger, on_notice
from nonebot.adapters.qq import Bot, Message
from nonebot.adapters.qq.event import GroupMemberAddEvent

from .utils_markdown import build_markdown, cmd

group_welcome = on_notice(priority=5, block=False)


@group_welcome.handle()
async def _(bot: Bot, event: GroupMemberAddEvent):
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
        await group_welcome.send(Message(build_markdown(content)))
    except Exception as e:
        logger.warning(f"[GroupWelcome] 欢迎卡片发送失败，回退文本版: {e}")
        try:
            await group_welcome.send(
                "🕯️ 道友，欢迎来到诡修仙。\n"
                "发送【注册】创建角色，发送【帮助】查看玩法。"
            )
        except Exception as e2:
            logger.warning(f"[GroupWelcome] 欢迎文本发送失败: {e2}")
