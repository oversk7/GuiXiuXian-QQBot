"""
Markdown模版调试工具
用于测试不同的消息发送方式
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams
from nonebot.params import CommandArg


# 测试1: 纯Markdown模版
md_pure_test_cmd = on_command("md纯测试", priority=4, block=True)

@md_pure_test_cmd.handle()
async def handle_md_pure_test(event: MessageEvent, args: Message = CommandArg()):
    """测试纯Markdown模版(不带额外文本)"""
    template_params = [
        MessageMarkdownParams(key="t1", values=["修炼"]),
        MessageMarkdownParams(key="t2", values=["面板"]),
        MessageMarkdownParams(key="t3", values=["背包"]),
        MessageMarkdownParams(key="t4", values=["装备"]),
        MessageMarkdownParams(key="t5", values=["战斗"]),
        MessageMarkdownParams(key="t6", values=["探索"]),
        MessageMarkdownParams(key="t7", values=["经济"]),
        MessageMarkdownParams(key="t8", values=["社交"]),
        MessageMarkdownParams(key="t9", values=["公会"]),
        MessageMarkdownParams(key="t10", values=["帮助"]),
    ]

    markdown = MessageMarkdown(
        custom_template_id="102499345_1768473387",
        params=template_params
    )

    # 只发送Markdown,不带额外文本
    await md_pure_test_cmd.finish(MessageSegment.markdown(markdown))


# 测试2: 文本+Markdown组合
md_combined_test_cmd = on_command("md组合测试", priority=4, block=True)

@md_combined_test_cmd.handle()
async def handle_md_combined_test(event: MessageEvent, args: Message = CommandArg()):
    """测试文本+Markdown组合"""
    template_params = [
        MessageMarkdownParams(key="t1", values=["修炼"]),
        MessageMarkdownParams(key="t2", values=["面板"]),
        MessageMarkdownParams(key="t3", values=["背包"]),
        MessageMarkdownParams(key="t4", values=["装备"]),
        MessageMarkdownParams(key="t5", values=["战斗"]),
        MessageMarkdownParams(key="t6", values=["探索"]),
        MessageMarkdownParams(key="t7", values=["经济"]),
        MessageMarkdownParams(key="t8", values=["社交"]),
        MessageMarkdownParams(key="t9", values=["公会"]),
        MessageMarkdownParams(key="t10", values=["帮助"]),
    ]

    markdown = MessageMarkdown(
        custom_template_id="102499345_1768473387",
        params=template_params
    )

    # 先文本,再Markdown
    msg = Message("📝 这是文本消息\n\n👇 下面是Markdown按钮:")
    msg.append(MessageSegment.markdown(markdown))

    await md_combined_test_cmd.finish(msg)


# 测试3: 分开发送
md_separate_test_cmd = on_command("md分开测试", priority=4, block=True)

@md_separate_test_cmd.handle()
async def handle_md_separate_test(event: MessageEvent, args: Message = CommandArg()):
    """测试分开发送文本和Markdown"""
    # 先发送文本
    await md_separate_test_cmd.send("📝 第一条:文本消息\n\n👇 下一条:Markdown按钮")

    # 再发送Markdown
    template_params = [
        MessageMarkdownParams(key="t1", values=["修炼"]),
        MessageMarkdownParams(key="t2", values=["面板"]),
        MessageMarkdownParams(key="t3", values=["背包"]),
        MessageMarkdownParams(key="t4", values=["装备"]),
        MessageMarkdownParams(key="t5", values=["战斗"]),
        MessageMarkdownParams(key="t6", values=["探索"]),
        MessageMarkdownParams(key="t7", values=["经济"]),
        MessageMarkdownParams(key="t8", values=["社交"]),
        MessageMarkdownParams(key="t9", values=["公会"]),
        MessageMarkdownParams(key="t10", values=["帮助"]),
    ]

    markdown = MessageMarkdown(
        custom_template_id="102499345_1768473387",
        params=template_params
    )

    await md_separate_test_cmd.finish(MessageSegment.markdown(markdown))


# 调试帮助
md_debug_help_cmd = on_command("md调试帮助", priority=4, block=True)

@md_debug_help_cmd.handle()
async def handle_md_debug_help(event: MessageEvent, args: Message = CommandArg()):
    """显示调试帮助"""
    help_text = """
🔧 Markdown调试工具
━━━━━━━━━━━━━

📝 可用测试命令:

1. /md纯测试
   • 只发送Markdown模版
   • 不带任何额外文本
   • 用于测试纯按钮显示

2. /md组合测试
   • 文本+Markdown组合
   • 在一条消息中
   • 用于测试组合效果

3. /md分开测试
   • 分两条消息发送
   • 第一条:文本
   • 第二条:Markdown按钮

4. /md测试
   • 原始测试工具
   • 可自定义参数

━━━━━━━━━━━━━

💡 推荐测试流程:
1. 先用 /md纯测试 查看纯按钮效果
2. 再用 /md组合测试 查看组合效果
3. 最后用 /md分开测试 查看分开效果
4. 选择效果最好的方式

━━━━━━━━━━━━━

⚠️ 注意:
• 不同QQ版本显示可能不同
• 建议在手机端测试
• 某些客户端可能不支持Markdown
"""

    await md_debug_help_cmd.finish(Message(help_text))
