"""快捷指令：生成群全量消息权限开通链接。"""

from nonebot import on_command
from nonebot.adapters.qq import Message, MessageEvent
from nonebot.params import CommandArg

_BOT_UIN = "3889410934"
_BOT_UID = "u_mnz4oqdeDstsM_R5ZJxa7A"

_URL_TEMPLATE = (
    "https://club.vip.qq.com/transfer?open_kuikly_info="
    "%7B%22page_name%22%3A%20%22ai_group_service_agreement_pop_page%22"
    "%2C%22groupCode%22%3A{group_code}"
    "%2C%22botUin%22%3A{bot_uin}"
    "%2C%22botUid%22%3A%22{bot_uid}%22"
    "%2C%22screen%22%3A1%7D"
)

open_full_msg_cmd = on_command(
    "开启全量消息",
    aliases={"全量消息", "开通全量消息"},
    priority=5,
    block=True,
)


@open_full_msg_cmd.handle()
async def handle_open_full_msg(event: MessageEvent, args: Message = CommandArg()):
    group_code = args.extract_plain_text().strip()
    if not group_code or not group_code.isdigit():
        await open_full_msg_cmd.finish(
            "用法：开启全量消息 <群号>\n"
            "例如：开启全量消息 123456789\n"
            "群主用最新版QQ点击生成的链接即可进入权限管理界面"
        )

    url = _URL_TEMPLATE.format(
        group_code=group_code,
        bot_uin=_BOT_UIN,
        bot_uid=_BOT_UID,
    )
    await open_full_msg_cmd.finish(
        f"群 {group_code} 全量消息权限开通链接：\n{url}\n\n"
        "请群主使用最新版QQ点击链接，按提示开启即可"
    )
