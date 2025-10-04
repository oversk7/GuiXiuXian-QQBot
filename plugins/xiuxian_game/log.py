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

    # 默认显示最近1条，可以指定数量
    try:
        count = int(args_text) if args_text else 1
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
        error_summaries = []
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 从后往前读取，找到ERROR日志
        # 日志格式：2025-10-04 10:57:04.850 | ERROR | ...
        # 只提取最后一行的错误信息，避免路径被识别为URL
        current_error_lines = []

        for i in range(len(lines) - 1, -1, -1):
            line = lines[i]
            line_stripped = line.strip()

            # 检查是否是新的日志条目（以日期时间开头，格式：YYYY-MM-DD HH:MM:SS）
            is_log_start = False
            if len(line_stripped) > 19:
                try:
                    # 尝试解析时间戳部分：YYYY-MM-DD
                    if (line_stripped[0:4].isdigit() and
                        line_stripped[4] == '-' and
                        line_stripped[5:7].isdigit() and
                        line_stripped[7] == '-'):
                        is_log_start = True
                except (IndexError, ValueError):
                    pass

            if is_log_start:
                # 这是一条新的日志行
                if "ERROR" in line or "EXCEPTION" in line:
                    # 找到一条ERROR日志的开始
                    current_error_lines = [line]

                    # 继续向后读取，收集完整的错误信息
                    j = i + 1
                    max_lines = 100  # 每条报错最多读取100行
                    lines_collected = 1

                    while j < len(lines) and lines_collected < max_lines:
                        next_line = lines[j]
                        next_stripped = next_line.strip()

                        # 检查下一行是否是新的日志条目
                        is_next_log_start = False
                        if len(next_stripped) > 19:
                            try:
                                if (next_stripped[0:4].isdigit() and
                                    next_stripped[4] == '-' and
                                    next_stripped[5:7].isdigit() and
                                    next_stripped[7] == '-'):
                                    is_next_log_start = True
                            except (IndexError, ValueError):
                                pass

                        # 如果遇到新的日志条目，停止收集
                        if is_next_log_start:
                            break

                        # 收集这一行
                        current_error_lines.append(next_line)
                        j += 1
                        lines_collected += 1

                    # 提取最后一行的错误信息（通常是异常类型和消息）
                    # 从后往前找第一个非空行
                    last_error_line = None
                    for error_line in reversed(current_error_lines):
                        stripped = error_line.strip()
                        if stripped and not stripped.startswith('│'):
                            # 检查是否包含常见的异常关键词
                            if any(keyword in stripped for keyword in ['Error:', 'Exception:', 'Error', 'Exception']):
                                last_error_line = stripped
                                break

                    # 如果没找到异常行，就用ERROR日志行本身
                    if not last_error_line:
                        # 从ERROR行中提取错误信息
                        # 格式：2025-10-04 10:57:04.850 | ERROR | module:function:line - 错误信息
                        error_line = current_error_lines[0]
                        if '| ERROR |' in error_line:
                            parts = error_line.split('| ERROR |', 1)
                            if len(parts) > 1:
                                last_error_line = parts[1].strip()
                            else:
                                last_error_line = error_line.strip()
                        else:
                            last_error_line = error_line.strip()

                    # 保存错误摘要
                    error_summaries.append(last_error_line)

                    if len(error_summaries) >= count:
                        break

        if not error_summaries:
            await view_error_log_cmd.finish(message_add_head("✅ 没有找到报错日志", event))

        # 反转列表，使最新的在最后
        error_summaries.reverse()

        # 构建消息 - 只显示最后一行错误信息
        if len(error_summaries) == 1:
            msg_lines = [
                "🔍 最近1条报错",
                "━━━━━━━━━━━━━",
                "",
                f"❌ {error_summaries[0]}",
                "",
                "━━━━━━━━━━━━━",
                "💡 使用【查看报错 数量】可查看更多"
            ]
        else:
            # 显示多条错误摘要
            msg_lines = [
                f"🔍 最近{len(error_summaries)}条报错",
                "━━━━━━━━━━━━━",
                ""
            ]
            for idx, error in enumerate(error_summaries, 1):
                msg_lines.append(f"{idx}. {error}")
            msg_lines.extend([
                "",
                "━━━━━━━━━━━━━",
                "💡 仅显示错误摘要，避免路径拦截"
            ])

        message = "\n".join(msg_lines)

        # 如果消息太长，只保留最新的几条
        if len(message) > 4500:
            # 只显示最新的3条
            recent_errors = error_summaries[-3:]
            msg_lines = [
                f"🔍 最新3条报错（共{len(error_summaries)}条）",
                "━━━━━━━━━━━━━",
                ""
            ]
            for idx, error in enumerate(recent_errors, 1):
                msg_lines.append(f"{idx}. {error}")
            msg_lines.extend([
                "",
                "━━━━━━━━━━━━━",
                f"💡 共找到 {len(error_summaries)} 条报错",
                "💡 仅显示最新3条错误摘要"
            ])
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