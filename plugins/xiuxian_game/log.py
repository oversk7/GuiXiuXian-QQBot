from nonebot import on_message, on_command, logger
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from pathlib import Path
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import json
from .models.db import safe_session
from .models.player import Player
from .utils import message_add_head

# --- 性能埋点：E2E 指令耗时 + 日志文件输出 ---
import time, logging, os
from logging.handlers import RotatingFileHandler
from nonebot.message import run_preprocessor, run_postprocessor

# 轻量文件日志，避免刷屏控制台
_log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
os.makedirs(_log_dir, exist_ok=True)

def _ensure_file_logger(name: str, filename: str):
    lg = logging.getLogger(name)
    # 避免重复添加handler
    if not any(isinstance(h, RotatingFileHandler) and getattr(h, 'baseFilename', '').endswith(filename) for h in lg.handlers):
        handler = RotatingFileHandler(os.path.join(_log_dir, filename), maxBytes=2*1024*1024, backupCount=3, encoding="utf-8")
        fmt = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
        handler.setFormatter(fmt)
        lg.addHandler(handler)
        lg.setLevel(logging.INFO)

_ensure_file_logger("perf", "perf.log")
_ensure_file_logger("sql", "sql.log")
_ensure_file_logger("hot", "hot.log")

@run_preprocessor
async def _perf_pre(bot, event, state):
    # 记录开始时间
    setattr(event, "_perf_t0", time.perf_counter())

@run_postprocessor
async def _perf_post(bot, event, state, matcher):
    t0 = getattr(event, "_perf_t0", None)
    if t0 is None:
        return
    ms = (time.perf_counter() - t0) * 1000
    try:
        mtype = getattr(matcher, "type", "?")
        mname = getattr(matcher, "module_name", "?")
        logging.getLogger("perf").info(f"{mtype}-{mname} {ms:.1f}ms")
    except AttributeError:
        # 属性获取失败不影响主流程
        pass

# 不阻拦也不回复，仅后台记录
log_uid_matcher = on_message(priority=1, block=False)

@log_uid_matcher.handle()
async def _(event: MessageEvent):
    """记录触发指令的玩家信息，并同步最近活跃时间"""
    try:
        async with safe_session() as session:
            player = await session.get(Player, event.get_user_id())
        uid = player.uid if player else "未注册"
        nickname = player.nickname if player else "未注册"
        cmd_text_raw = event.get_plaintext().strip()
        command = cmd_text_raw if cmd_text_raw else "未知指令"
        logger.info(f"UID:{uid} 昵称:{nickname} 指令:{command}")
        # 仅在文本非空时记录活跃时间
        if cmd_text_raw:
            _update_last_active(player, event.get_user_id(), command)
    except SQLAlchemyError as e:
        logger.error(f"UID:未知 昵称:未知 指令:未知 状态:失败 错误:{str(e)}")



def _update_last_active(player: Player | None, user_id: str, command: str) -> None:
    """将玩家最近活跃时间写入日志目录下的last_active.json
    不改动数据库，避免迁移；后续有需要可读取此文件做活跃统计/展示
    """
    log_dir = Path(__file__).parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "last_active.json"

    data = {}
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
    except (json.JSONDecodeError, OSError):
        data = {}

    record = {
        "uid": (player.uid if player else None),
        "nickname": (player.nickname if player else None),
        "last_active": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_command": command,
    }

    # 使用平台ID作为键，便于通过event.get_user_id()直接读取
    data[str(user_id)] = record

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        # 写入失败不影响主流程
        pass


# ==================== 查看全服最近活动记录 ====================
recent_activity_cmd = on_command("最近活动", aliases={"活动记录", "全服活动"}, block=True, priority=5)

@recent_activity_cmd.handle()
async def handle_recent_activity(event: MessageEvent, args: Message = CommandArg()):
    """查看全服最近玩家活动记录或指定UID玩家的活动记录"""
    args_text = args.extract_plain_text().strip()

    # 解析参数：可能是数量或UID
    target_uid = None
    count = 10  # 默认显示10条

    if args_text:
        try:
            num = int(args_text)
            # 判断是数量还是UID
            # 如果数字在1-50之间，视为数量；否则视为UID
            if 1 <= num <= 50:
                count = num
            else:
                # 视为UID
                target_uid = num
                count = 50  # 查看指定玩家时，最多显示50条
        except ValueError:
            await recent_activity_cmd.finish("⛔ 请输入有效的数字（数量1-50或玩家UID）")

    log_dir = Path(__file__).parent.parent.parent / "logs"
    path = log_dir / "last_active.json"

    if not path.exists():
        await recent_activity_cmd.finish(message_add_head("❌ 暂无活动记录", event))

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict) or not data:
            await recent_activity_cmd.finish(message_add_head("❌ 暂无活动记录", event))

        # 将所有记录转换为列表，并按时间排序
        records = []
        for user_id, record in data.items():
            if record.get("last_active") and record.get("uid"):
                # 如果指定了UID，只收集该玩家的记录
                if target_uid is not None and record.get("uid") != target_uid:
                    continue

                try:
                    # 解析时间字符串
                    active_time = datetime.strptime(record["last_active"], "%Y-%m-%d %H:%M:%S")
                    records.append({
                        "uid": record["uid"],
                        "nickname": record.get("nickname", "未知"),
                        "time": active_time,
                        "command": record.get("last_command", "未知指令"),
                    })
                except (ValueError, KeyError):
                    continue

        if not records:
            if target_uid is not None:
                await recent_activity_cmd.finish(message_add_head(f"❌ 未找到UID:{target_uid}的活动记录", event))
            else:
                await recent_activity_cmd.finish(message_add_head("❌ 暂无有效活动记录", event))

        # 按时间倒序排序（最新的在前）
        records.sort(key=lambda x: x["time"], reverse=True)

        # 取前N条
        records = records[:count]

        # 构建消息
        now = datetime.now()
        if target_uid is not None:
            # 查看指定玩家的活动
            player_name = records[0]["nickname"]
            msg_lines = [
                f"📊 {player_name}(UID:{target_uid})的最近{len(records)}条活动",
                "━━━━━━━━━━━━━",
                ""
            ]
        else:
            # 查看全服活动
            msg_lines = [
                f"📊 全服最近{len(records)}条活动",
                "━━━━━━━━━━━━━",
                ""
            ]

        for idx, rec in enumerate(records, 1):
            # 计算时间差
            time_diff = now - rec["time"]

            # 格式化时间差
            if time_diff.total_seconds() < 60:
                time_str = f"{int(time_diff.total_seconds())}秒前"
            elif time_diff.total_seconds() < 3600:
                time_str = f"{int(time_diff.total_seconds() / 60)}分钟前"
            elif time_diff.total_seconds() < 86400:
                time_str = f"{int(time_diff.total_seconds() / 3600)}小时前"
            else:
                time_str = f"{int(time_diff.total_seconds() / 86400)}天前"

            # 截断过长的指令
            cmd_display = rec["command"]
            if len(cmd_display) > 20:
                cmd_display = cmd_display[:20] + "..."

            if target_uid is not None:
                # 查看指定玩家时，不显示玩家名称
                msg_lines.append(f"{time_str} | {cmd_display}")
            else:
                # 查看全服时，显示玩家名称
                msg_lines.append(f"{time_str} | {rec['nickname']}(UID:{rec['uid']}) | {cmd_display}")

        msg_lines.extend([
            "",
            "━━━━━━━━━━━━━",
        ])

        if target_uid is not None:
            msg_lines.append(f"💡 使用【最近活动】查看全服活动")
        else:
            msg_lines.append(f"💡 使用【最近活动 数量】查看更多（最多50条）")
            msg_lines.append(f"💡 使用【最近活动 UID】查看指定玩家活动")

        message = "\n".join(msg_lines)
        await recent_activity_cmd.finish(message_add_head(message, event))

    except json.JSONDecodeError:
        await recent_activity_cmd.finish(message_add_head("❌ 活动记录文件格式错误", event))
    except OSError as e:
        await recent_activity_cmd.finish(message_add_head(f"❌ 读取活动记录失败: {str(e)}", event))


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