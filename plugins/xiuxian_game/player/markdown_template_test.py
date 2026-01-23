"""
QQ官方平台Markdown模版测试指令
用于测试模版ID: 102499345_1768473387
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.message import MessageMarkdown
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
                template_params.append({
                    "key": f"t{i+1}",
                    "values": [param_list[i]]
                })
            else:
                # 使用默认示例值
                default_values = ["签到", "修炼", "突破", "背包", "装备", "战斗", "探索", "社交", "公会", "娱乐"]
                template_params.append({
                    "key": f"t{i+1}",
                    "values": [default_values[i]]
                })
    else:
        # 使用默认示例值
        default_values = ["签到", "修炼", "突破", "背包", "装备", "战斗", "探索", "社交", "公会", "娱乐"]
        for i in range(10):
            template_params.append({
                "key": f"t{i+1}",
                "values": [default_values[i]]
            })

    # 创建Markdown模版消息
    # 注意: params参数应该是一个字典列表,每个字典包含key和values
    try:
        # 方式1: 尝试使用keyword参数
        markdown = MessageMarkdown(
            template_id="102499345_1768473387",
            params=template_params
        )

        # 发送测试消息 - 只发送markdown,不要附加其他文本
        test_msg = Message()
        test_msg.append(MessageSegment.markdown(markdown))

        await markdown_template_test_cmd.finish(test_msg)
    except Exception as e:
        # 如果失败,尝试方式2: 直接使用content
        await markdown_template_test_cmd.finish(f"❌ Markdown模版测试失败\n━━━━━━━━━━━━━\n错误: {str(e)}\n\n💡 可能原因:\n1. 模版ID不正确\n2. 群消息不支持Markdown模版\n3. 参数格式不正确\n\n调试信息:\n模版参数: {template_params}")


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
