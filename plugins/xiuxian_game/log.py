from nonebot import on_message, on_command, logger
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from pathlib import Path
from .models.db import safe_session
from .models.player import Player
from .utils import message_add_head

# 不阻拦也不回复，仅后台记录
log_uid_matcher = on_message(priority=1, block=False)

@log_uid_matcher.handle()
async def _(event: MessageEvent):
    """记录触发指令的玩家信息"""
    try:
        async with safe_session() as session:
            player = await session.get(Player, event.get_user_id())
        uid = player.uid if player else "未注册"
        nickname = player.nickname if player else "未注册"
        command = event.get_plaintext().strip() if event.get_plaintext().strip() else "未知指令"
        logger.info(f"UID:{uid} 昵称:{nickname} 指令:{command}")
    except Exception as e:
        logger.error(f"UID:未知 昵称:未知 指令:未知 状态:失败 错误:{str(e)}")


# ==================== 管理员指令：查看最近报错日志 ====================
view_error_log_cmd = on_command("查看报错", aliases={"最近报错", "报错日志"}, block=True, priority=1, permission=SUPERUSER)

@view_error_log_cmd.handle()
async def handle_view_error_log(event: MessageEvent, args: Message = CommandArg()):
    """管理员查看最近的报错日志"""
    args_text = args.extract_plain_text().strip()

    # 默认显示最近10条，可以指定数量
    try:
        count = int(args_text) if args_text else 10
        if count <= 0 or count > 100:
            await view_error_log_cmd.finish("⛔ 数量必须在1-100之间")
    except ValueError:
        await view_error_log_cmd.finish("⛔ 请输入有效的数字")

    # 读取日志文件
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_file = log_dir / "command_log.txt"

    if not log_file.exists():
        await view_error_log_cmd.finish(message_add_head("❌ 日志文件不存在", event))

    try:
        # 读取日志文件，查找ERROR级别的日志
        error_logs = []
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 从后往前读取，找到ERROR日志
        # 日志格式：2025-10-04 10:57:04.850 | ERROR | ...
        current_error = []
        in_error_block = False

        for line in reversed(lines):
            line_stripped = line.strip()

            # 检查是否是新的日志条目（以日期时间开头，格式：YYYY-MM-DD HH:MM:SS）
            is_log_start = False
            if len(line_stripped) > 19:
                try:
                    # 尝试解析时间戳部分
                    if line_stripped[0:4].isdigit() and line_stripped[4] == '-':
                        is_log_start = True
                except (IndexError, ValueError):
                    pass

            if is_log_start:
                # 这是一条新的日志行
                if "ERROR" in line or "EXCEPTION" in line:
                    # 找到一条ERROR日志的开始
                    current_error.insert(0, line)
                    error_logs.append("".join(current_error))
                    current_error = []
                    in_error_block = False

                    if len(error_logs) >= count:
                        break
                elif in_error_block:
                    # 上一条ERROR日志的多行内容结束
                    in_error_block = False
                    current_error = []
            else:
                # 这是日志的续行（堆栈跟踪等）
                if in_error_block or (current_error and not error_logs):
                    current_error.insert(0, line)

            # 如果刚找到ERROR，标记为在ERROR块中
            if is_log_start and ("ERROR" in line or "EXCEPTION" in line):
                in_error_block = True

        if not error_logs:
            await view_error_log_cmd.finish(message_add_head("✅ 没有找到报错日志", event))

        # 反转列表，使最新的在最后
        error_logs.reverse()

        # 构建消息
        msg_lines = [
            f"🔍 最近{len(error_logs)}条报错日志",
            "━━━━━━━━━━━━━"
        ]

        for i, error_log in enumerate(error_logs, 1):
            # 限制每条日志的长度，避免消息过长
            error_log = error_log.strip()
            if len(error_log) > 500:
                error_log = error_log[:500] + "..."

            msg_lines.append(f"\n📋 报错 #{i}:")
            msg_lines.append(error_log)
            msg_lines.append("━━━━━━━━━━━━━")

        msg_lines.append(f"\n💡 共找到 {len(error_logs)} 条报错")
        msg_lines.append("💡 使用【查看报错 数量】指定查看条数")

        message = "\n".join(msg_lines)

        # 如果消息太长，分段发送
        if len(message) > 4000:
            # 只发送最后一条完整的报错
            msg_lines = [
                "🔍 最近1条完整报错日志",
                "━━━━━━━━━━━━━",
                f"\n📋 最新报错:",
                error_logs[-1].strip(),
                "━━━━━━━━━━━━━",
                f"\n⚠️ 共有 {len(error_logs)} 条报错，消息过长仅显示最新1条",
                "💡 建议查看日志文件获取完整信息"
            ]
            message = "\n".join(msg_lines)

        await view_error_log_cmd.finish(message_add_head(message, event))

    except FileNotFoundError:
        await view_error_log_cmd.finish(message_add_head("❌ 日志文件不存在", event))
    except PermissionError:
        await view_error_log_cmd.finish(message_add_head("❌ 没有权限读取日志文件", event))
    except UnicodeDecodeError:
        await view_error_log_cmd.finish(message_add_head("❌ 日志文件编码错误", event))
    except IOError as e:
        await view_error_log_cmd.finish(message_add_head(f"❌ 读取日志文件失败: {str(e)}", event))