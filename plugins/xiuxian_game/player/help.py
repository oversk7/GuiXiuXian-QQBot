from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

# 注册"帮助"指令
help_cmd = on_command("帮助", aliases={"help","菜单"}, priority=5, block=True)


@help_cmd.handle()
async def handle_help(event: MessageEvent, args: Message = CommandArg()):
    msg = (
        "✨ 欢迎使用帮助系统 ✨\n"
        "═════════════\n"
        "🧘 修炼系统  🎪 活动系统\n"
        "🎭 玩家系统  🎒 背包系统\n"
        "🛒 每日商店  📦 交易系统\n"
        "═════════════\n"
        "💡 输入系统名称查看详细指令\n"
        "💡 教程及反馈请查看此链接：https://tz.nevermonarch.cn/url/?url=https://www.yuque.com/rixingyinyao-dx2t6/gs55vv/rz0e9fsw7c7sggwe \n"
        "💡 官群：962494679，官群签到奖励更多"
    )
    await help_cmd.finish(Message(msg))