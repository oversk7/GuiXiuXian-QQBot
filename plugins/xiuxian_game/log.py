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
        error_logs = []
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 从后往前读取，找到ERROR日志
        # 日志格式：2025-10-04 10:57:04.850 | ERROR | ...
        # 完整报错包含：ERROR行 + Traceback + 多行堆栈跟踪 + 最终的异常信息
        current_error = []

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
                    current_error.insert(0, line)

                    # 继续向后读取，收集完整的堆栈跟踪
                    # 堆栈跟踪通常包含：Traceback、File行、异常类型等
                    # 限制最多读取100行，避免过长
                    j = i + 1
                    lines_collected = 1  # 已经收集了ERROR行本身
                    max_lines = 100  # 每条报错最多100行

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

                        # 否则，这是当前ERROR的一部分
                        current_error.append(next_line)
                        j += 1
                        lines_collected += 1

                    # 如果达到行数限制，添加提示
                    if lines_collected >= max_lines:
                        current_error.append("\n... (堆栈跟踪过长，已截断) ...\n")

                    # 保存完整的ERROR日志
                    error_logs.append("".join(current_error))
                    current_error = []

                    if len(error_logs) >= count:
                        break

        if not error_logs:
            await view_error_log_cmd.finish(message_add_head("✅ 没有找到报错日志", event))

        # 反转列表，使最新的在最后
        error_logs.reverse()

        # 过滤敏感内容的函数
        def sanitize_log(log_text: str) -> str:
            """过滤日志中的敏感内容，只保留关键报错信息"""
            import re
            lines = log_text.split('\n')
            result_lines = []

            for line in lines:
                # 保留ERROR行
                if '| ERROR' in line or '| EXCEPTION' in line:
                    result_lines.append(line)
                    continue

                # 保留Traceback行
                if line.strip().startswith('Traceback'):
                    result_lines.append(line)
                    continue

                # 处理File行，只保留文件名和行号
                if 'File "' in line:
                    # 提取文件名和行号
                    # 格式：  File "/path/to/file.py", line 123, in function_name
                    match = re.search(r'File "([^"]+)", line (\d+)(?:, in (.+))?', line)
                    if match:
                        full_path = match.group(1)
                        line_num = match.group(2)
                        func_name = match.group(3) if match.group(3) else ''

                        # 只保留文件名（去掉路径）
                        import os
                        file_name = os.path.basename(full_path)

                        # 重新构建行
                        indent = len(line) - len(line.lstrip())
                        if func_name:
                            new_line = ' ' * indent + f'File "{file_name}", line {line_num}, in {func_name}'
                        else:
                            new_line = ' ' * indent + f'File "{file_name}", line {line_num}'
                        result_lines.append(new_line)
                    else:
                        result_lines.append(line)
                    continue

                # 保留异常类型行（如 AttributeError, ValueError 等）
                if line.strip() and (
                    'Error:' in line or
                    'Exception:' in line or
                    line.strip().endswith('Error') or
                    line.strip().endswith('Exception')
                ):
                    result_lines.append(line)
                    continue

                # 保留代码行（通常是缩进的）
                if line.strip() and not line.strip().startswith('│'):
                    result_lines.append(line)

            return '\n'.join(result_lines)

        # 构建消息 - 只显示最新的一条完整报错
        # 因为完整的堆栈跟踪通常很长，一次只显示一条更合适
        if len(error_logs) == 1:
            sanitized_log = sanitize_log(error_logs[0].strip())
            msg_lines = [
                "🔍 最近1条报错日志",
                "━━━━━━━━━━━━━",
                "",
                sanitized_log,
                "",
                "━━━━━━━━━━━━━",
                "💡 使用【查看报错 数量】可查看更多",
                "💡 已过滤完整路径，仅显示文件名"
            ]
        else:
            # 如果有多条，只显示最新的一条完整报错
            sanitized_log = sanitize_log(error_logs[-1].strip())
            msg_lines = [
                f"🔍 最近{len(error_logs)}条报错中的最新1条",
                "━━━━━━━━━━━━━",
                "",
                sanitized_log,
                "",
                "━━━━━━━━━━━━━",
                f"💡 共找到 {len(error_logs)} 条报错",
                "💡 已过滤完整路径，仅显示文件名",
                "💡 如需完整路径请查看日志文件"
            ]

        message = "\n".join(msg_lines)

        # 如果单条消息仍然太长（超过4500字符），进行截断
        if len(message) > 4500:
            # 截取ERROR行和最后的异常信息
            error_log = error_logs[-1].strip()
            lines = error_log.split('\n')

            # 保留第一行（ERROR行）和最后几行（异常信息）
            if len(lines) > 20:
                truncated = '\n'.join(lines[:5]) + '\n\n... (中间省略) ...\n\n' + '\n'.join(lines[-10:])
            else:
                truncated = error_log

            # 过滤敏感内容
            truncated = sanitize_log(truncated)

            msg_lines = [
                "🔍 最新报错日志（已截断）",
                "━━━━━━━━━━━━━",
                "",
                truncated,
                "",
                "━━━━━━━━━━━━━",
                f"💡 共找到 {len(error_logs)} 条报错",
                "💡 完整堆栈跟踪过长已截断",
                "💡 已过滤完整路径，仅显示文件名"
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