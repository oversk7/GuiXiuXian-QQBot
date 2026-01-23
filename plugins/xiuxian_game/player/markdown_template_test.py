"""
QQ官方平台Markdown模版测试指令
用于测试模版ID: 102499345_1768473387
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams, MessageKeyboard
from nonebot.params import CommandArg


# Markdown模版测试指令
markdown_template_test_cmd = on_command("md测试", aliases={"markdown测试", "模版测试"}, priority=4, block=True)

@markdown_template_test_cmd.handle()
async def handle_markdown_template_test(event: MessageEvent, args: Message = CommandArg()):
    """
    测试QQ官方平台Markdown模版
    模版ID: 102499345_1768473387
    """
    # 获取用户输入的参数
    params_text = args.extract_plain_text().strip()

    # 构建模版参数
    # 模版支持10个输入框: t1-t10
    template_params = []

    # 如果用户提供了参数,按空格分割填充到t1-t10
    if params_text:
        param_list = params_text.split()
        for i in range(10):
            if i < len(param_list):
                template_params.append(
                    MessageMarkdownParams(key=f"t{i+1}", values=[param_list[i]])
                )
            else:
                # 使用默认示例值
                default_values = ["签到", "修炼", "突破", "背包", "装备", "战斗", "探索", "社交", "公会", "娱乐"]
                template_params.append(
                    MessageMarkdownParams(key=f"t{i+1}", values=[default_values[i]])
                )
    else:
        # 使用默认示例值
        default_values = ["签到", "修炼", "突破", "背包", "装备", "战斗", "探索", "社交", "公会", "娱乐"]
        for i in range(10):
            template_params.append(
                MessageMarkdownParams(key=f"t{i+1}", values=[default_values[i]])
            )

    # 创建Markdown模版消息
    markdown = MessageMarkdown(
        custom_template_id="102499345_1768473387",
        params=template_params
    )

    # 发送测试消息
    test_msg = Message("🧪 Markdown模版测试\n━━━━━━━━━━━━━\n模版ID: 102499345_1768473387")
    test_msg.append(MessageSegment.markdown(markdown))

    await markdown_template_test_cmd.finish(test_msg)


# 帮助指令
md_test_help_cmd = on_command("md测试帮助", aliases={"markdown测试帮助"}, priority=4, block=True)

@md_test_help_cmd.handle()
async def handle_md_test_help(event: MessageEvent, args: Message = CommandArg()):
    """
    显示Markdown模版测试帮助信息
    """
    help_text = """
✨ Markdown模版测试帮助 ✨
━━━━━━━━━━━━━
📝 测试指令：
【md测试】 使用默认值测试模版
【md测试 参数1 参数2 ...】 自定义参数测试

━━━━━━━━━━━━━
🎯 模版信息：
• 模版ID: 102499345_1768473387
• 支持参数: t1-t10 (10个输入框)
• 参数类型: 文本输入

━━━━━━━━━━━━━
💡 使用示例：
• /md测试
• /md测试 签到 修炼 突破
• /md测试 测试1 测试2 测试3 测试4 测试5

━━━━━━━━━━━━━
📋 参数说明：
t1-t10: 10个文本输入框的值
         如果参数不足10个,
         剩余的使用默认值

━━━━━━━━━━━━━
⚠️ 注意：
• 仅支持QQ官方平台
• 参数按空格分隔
• 超过10个参数会被忽略
"""

    await md_test_help_cmd.finish(Message(help_text))
