"""
MySQL 数据库备份管理命令
仅限管理员使用，通过 mysqldump 进行全量备份
支持自动定时备份（每天凌晨4点）和手动恢复
"""
import asyncio
import re
from datetime import datetime
from pathlib import Path

from nonebot import on_command, logger
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from nonebot_plugin_apscheduler import scheduler

from ..ai_guide import is_admin
from ..utils import message_add_head
from ..models.db import load_database_config

# 备份目录
BACKUP_DIR = Path(__file__).parent.parent.parent.parent / "backups"
# 最多保留备份数量
MAX_BACKUPS = 10
# 安全文件名正则（仅允许 backup_YYYYMMDD_HHMMSS.sql.gz）
_SAFE_FILENAME_RE = re.compile(r"^backup_\d{8}_\d{6}\.sql\.gz$")

# 命令注册
backup_cmd = on_command("手动备份", aliases={"数据库备份"}, block=True, priority=15)
backup_status_cmd = on_command("备份状态", aliases={"备份列表"}, block=True, priority=15)
restore_cmd = on_command("恢复备份", block=True, priority=15)


def _get_mysql_config() -> dict:
    """从 database.yaml 读取 MySQL 连接配置"""
    config = load_database_config()
    db_config = config["database"]
    if db_config.get("type") != "mysql":
        raise RuntimeError("当前数据库类型不是 MySQL，无法使用 mysqldump 备份")
    return db_config["mysql"]


def _list_backups() -> list[Path]:
    """列出所有备份文件，按修改时间倒序"""
    if not BACKUP_DIR.exists():
        return []
    files = list(BACKUP_DIR.glob("backup_*.sql.gz"))
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files


def _cleanup_old_backups():
    """清理超出保留数量的旧备份"""
    files = _list_backups()
    for old_file in files[MAX_BACKUPS:]:
        old_file.unlink(missing_ok=True)
        logger.info(f"清理旧备份: {old_file.name}")


async def _do_backup(tag: str = "") -> tuple[bool, str]:
    """
    执行 mysqldump 备份，返回 (成功与否, 消息).
    tag: 备份文件名中的可选标记，如 "auto"
    """
    try:
        mysql_cfg = _get_mysql_config()
    except RuntimeError as e:
        return False, str(e)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = f"backup_{tag + '_' if tag else ''}"
    filename = f"{prefix}{timestamp}.sql.gz"
    filepath = BACKUP_DIR / filename

    host = mysql_cfg["host"]
    port = mysql_cfg.get("port", 3306)
    user = mysql_cfg["user"]
    password = mysql_cfg["password"]
    database = mysql_cfg["database"]

    dump_cmd = (
        f'mysqldump -h {host} -P {port} -u {user} -p"{password}" '
        f'--single-transaction --quick --routines --triggers '
        f'"{database}"'
    )
    full_cmd = f'{dump_cmd} | gzip > "{filepath}"'

    try:
        process = await asyncio.create_subprocess_shell(
            full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=300)

        if process.returncode != 0:
            err_msg = stderr.decode(errors="replace").strip()
            filepath.unlink(missing_ok=True)
            return False, f"mysqldump 失败: {err_msg[:200]}"

        if not filepath.exists() or filepath.stat().st_size == 0:
            filepath.unlink(missing_ok=True)
            return False, "备份失败：生成的文件为空"

        file_size_mb = filepath.stat().st_size / (1024 * 1024)
        _cleanup_old_backups()
        return True, f"{filename} ({file_size_mb:.2f} MB)"

    except asyncio.TimeoutError:
        filepath.unlink(missing_ok=True)
        return False, "备份超时（超过5分钟）"
    except FileNotFoundError:
        return False, "未找到 mysqldump 命令，请确认已安装 MySQL 客户端工具"


# ============================================================
# 自动定时备份：每天凌晨 4:00
# ============================================================
@scheduler.scheduled_job("cron", hour="4", minute="0", id="auto_db_backup")
async def auto_backup():
    logger.info("⏰ 开始执行自动数据库备份...")
    ok, msg = await _do_backup()
    if ok:
        logger.info(f"✅ 自动备份成功: {msg}")
    else:
        logger.error(f"❌ 自动备份失败: {msg}")


# ============================================================
# 手动备份命令
# ============================================================
@backup_cmd.handle()
async def handle_backup(event: MessageEvent):
    if not is_admin(event.get_user_id()):
        await backup_cmd.finish("⛔ 仅管理员可使用此命令")

    await backup_cmd.send("正在执行数据库备份，请稍候...")

    ok, msg = await _do_backup()
    if not ok:
        await backup_cmd.finish(f"⛔ {msg}")

    msg_lines = [
        "✅ 数据库备份成功",
        "━━━━━━━━━━━━━",
        f"📄 {msg}",
        f"📁 路径：backups/",
        f"🗂️ 保留策略：最近 {MAX_BACKUPS} 个备份",
    ]
    await backup_cmd.finish(message_add_head("\n".join(msg_lines), event))


# ============================================================
# 备份状态 / 列表命令
# ============================================================
@backup_status_cmd.handle()
async def handle_backup_status(event: MessageEvent):
    if not is_admin(event.get_user_id()):
        await backup_status_cmd.finish("⛔ 仅管理员可使用此命令")

    files = _list_backups()

    if not files:
        await backup_status_cmd.finish(message_add_head(
            "📁 暂无备份文件\n💡 使用【手动备份】创建备份", event
        ))

    msg_lines = [
        f"📁 数据库备份列表（共 {len(files)} 个）",
        "━━━━━━━━━━━━━",
    ]

    for i, f in enumerate(files, 1):
        size_mb = f.stat().st_size / (1024 * 1024)
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%m-%d %H:%M")
        msg_lines.append(f"{i}. {f.name}  ({size_mb:.1f}MB, {mtime})")

    msg_lines.append("━━━━━━━━━━━━━")
    msg_lines.append(f"🗂️ 保留策略：最近 {MAX_BACKUPS} 个")
    msg_lines.append("💡 恢复备份：【恢复备份 序号/文件名】")

    await backup_status_cmd.finish(message_add_head("\n".join(msg_lines), event))


# ============================================================
# 恢复备份命令
# ============================================================
@restore_cmd.handle()
async def handle_restore(event: MessageEvent, args: Message = CommandArg()):
    if not is_admin(event.get_user_id()):
        await restore_cmd.finish("⛔ 仅管理员可使用此命令")

    arg_text = args.extract_plain_text().strip()
    if not arg_text:
        await restore_cmd.finish(
            "用法：【恢复备份 序号/文件名】\n"
            "💡 先用【备份列表】查看可用备份"
        )

    files = _list_backups()
    if not files:
        await restore_cmd.finish("⛔ 没有可用的备份文件")

    # 支持按序号或文件名选择
    target: Path | None = None
    if arg_text.isdigit():
        idx = int(arg_text)
        if 1 <= idx <= len(files):
            target = files[idx - 1]
        else:
            await restore_cmd.finish(f"⛔ 序号超出范围，有效范围 1-{len(files)}")
    else:
        # 按文件名匹配
        for f in files:
            if f.name == arg_text:
                target = f
                break
        if target is None:
            await restore_cmd.finish(f"⛔ 未找到备份文件：{arg_text}")

    # 安全检查：只允许恢复符合命名规范的文件
    if not _SAFE_FILENAME_RE.match(target.name):
        await restore_cmd.finish("⛔ 文件名格式不合法")

    try:
        mysql_cfg = _get_mysql_config()
    except RuntimeError as e:
        await restore_cmd.finish(f"⛔ {e}")

    # 恢复前先自动做一次当前备份
    await restore_cmd.send(
        f"⚠️ 即将恢复备份：{target.name}\n"
        "正在先备份当前数据库..."
    )

    pre_ok, pre_msg = await _do_backup()
    if pre_ok:
        logger.info(f"恢复前自动备份成功: {pre_msg}")
    else:
        logger.warning(f"恢复前自动备份失败: {pre_msg}（继续恢复）")

    await restore_cmd.send("开始恢复数据库，请稍候...")

    host = mysql_cfg["host"]
    port = mysql_cfg.get("port", 3306)
    user = mysql_cfg["user"]
    password = mysql_cfg["password"]
    database = mysql_cfg["database"]

    # gunzip | mysql
    restore_shell = (
        f'gunzip < "{target}" | '
        f'mysql -h {host} -P {port} -u {user} -p"{password}" "{database}"'
    )

    try:
        process = await asyncio.create_subprocess_shell(
            restore_shell,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=600)

        if process.returncode != 0:
            err_msg = stderr.decode(errors="replace").strip()
            logger.error(f"数据库恢复失败: {err_msg}")
            await restore_cmd.finish(
                f"⛔ 恢复失败\n{err_msg[:200]}\n"
                f"💡 恢复前的备份: {pre_msg if pre_ok else '无'}"
            )

        mtime = datetime.fromtimestamp(target.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        msg_lines = [
            "✅ 数据库恢复成功",
            "━━━━━━━━━━━━━",
            f"📄 恢复文件：{target.name}",
            f"🕐 备份时间：{mtime}",
            f"🛡️ 恢复前备份：{'已保存 ' + pre_msg if pre_ok else '⚠️ 失败'}",
            "━━━━━━━━━━━━━",
            "⚠️ 注意：如果 bot 有内存缓存，建议重启以确保数据一致",
        ]
        await restore_cmd.finish(message_add_head("\n".join(msg_lines), event))

    except asyncio.TimeoutError:
        await restore_cmd.finish("⛔ 恢复超时（超过10分钟）")
    except FileNotFoundError:
        await restore_cmd.finish("⛔ 未找到 mysql/gunzip 命令，请确认已安装相关工具")
