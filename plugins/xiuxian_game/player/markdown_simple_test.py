"""
QQ官方平台Markdown模版简单测试
用于测试模版ID: 102499345_1768473387

注意: Markdown模版通常只在频道(Direct Message)中支持,
群消息可能不支持此功能
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.message import MessageMarkdown
from nonebot.params import CommandArg
import json


# Markdown模版简单测试指令
markdown_simple_test_cmd = on_command("简单md测试", priority=4, block=True)

@markdown_simple_test_cmd.handle()
async def handle_markdown_simple_test(event: MessageEvent, args: Message = CommandArg()):
    """
    简单的Markdown模版测试
    """
    # 获取平台信息
    session_id = event.get_session_id()

    # 判断是否为私聊/频道
    is_direct = session_id.startswith("friend_") or "guild" in str(event).lower()

    if not is_direct:
        await markdown_simple_test_cmd.finish(
            "⚠️ Markdown模版测试\n"
            "━━━━━━━━━━━━━\n"
            "❌ 当前环境不支持Markdown模版\n\n"
            "💡 Markdown模版仅在以下环境中支持:\n"
            "• 频道私聊(Direct Message)\n"
            "• QQ官方频道\n\n"
            "群消息暂不支持Markdown模版功能"
        )

    # 构建简单的模版参数
    template_params = [
        {"key": "t1", "values": ["测试1"]},
        {"key": "t2", "values": ["测试2"]},
        {"key": "t3", "values": ["测试3"]},
    ]

    # 创建Markdown模版
    markdown = MessageMarkdown(
        template_id="102499345_1768473387",
        params=template_params
    )

    # 只发送markdown消息
    test_msg = Message()
    test_msg.append(MessageSegment.markdown(markdown))

    await markdown_simple_test_cmd.finish(test_msg)


# 调试信息指令
md_debug_cmd = on_command("md调试", priority=4, block=True)

@md_debug_cmd.handle()
async def handle_md_debug(event: MessageEvent, args: Message = CommandArg()):
    """
    显示调试信息
    """
    session_id = event.get_session_id()

    debug_info = [
        "🔍 Markdown模版调试信息",
        "━━━━━━━━━━━━━",
        f"会话ID: {session_id}",
        f"是否私聊: {session_id.startswith('friend_')}",
        f"事件类型: {type(event).__name__}",
        "",
        "💡 提示:",
        "• Markdown模版通常只在频道私聊中支持",
        "• 群消息可能返回 '请求数据异常' 错误",
        "• 请尝试在私聊中使用此功能",
        "",
        "📋 测试步骤:",
        "1. 私聊机器人",
        "2. 发送【简单md测试】",
        "3. 查看是否正常显示",
    ]

    await md_debug_cmd.finish(Message("\n".join(debug_info)))


# 参数格式测试指令
md_params_test_cmd = on_command("md参数测试", priority=4, block=True)

@md_params_test_cmd.handle()
async def handle_md_params_test(event: MessageEvent, args: Message = CommandArg()):
    """
    测试不同的参数格式
    """
    # 格式1: 标准格式
    format1 = [
        {"key": "t1", "values": ["格式1-1"]},
        {"key": "t2", "values": ["格式1-2"]},
    ]

    # 格式2: 简化格式
    format2 = {
        "t1": "格式2-1",
        "t2": "格式2-2",
    }

    info = [
        "📝 Markdown参数格式测试",
        "━━━━━━━━━━━━━",
        "",
        "格式1 (标准):",
        json.dumps(format1, ensure_ascii=False, indent=2),
        "",
        "格式2 (简化):",
        json.dumps(format2, ensure_ascii=False, indent=2),
        "",
        "💡 当前代码使用格式1",
        "━━━━━━━━━━━━━",
        "如果仍然报错,可能原因:",
        "1. 模版ID不存在或未审核通过",
        "2. 当前环境不支持Markdown模版",
        "3. 参数键名不匹配(应为t1-t10)",
    ]

    await md_params_test_cmd.finish(Message("\n".join(info)))
