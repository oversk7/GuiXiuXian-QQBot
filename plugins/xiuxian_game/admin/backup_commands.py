"""
MySQL 数据库备份管理命令
仅限管理员使用，通过 mysqldump 进行全量备份
"""
import asyncio
import os
from datetime import datetime
from pathlib import Path

from nonebot import on_command, logger
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..ai_guide import is_admin
from ..utils import message_add_head
from ..models.db import load_database_config

# 备份目录
BACKUP_DIR = Path(__file__).parent.parent.parent.parent / "backups"
# 最多保留备份数量
MAX_BACKUPS = 10

# 命令注册
backup_cmd = on_command("手动备份", aliases={"数据库备份"}, block=True, priority=5)
backup_status_cmd = on_command("备份状态", aliases={"备份列表"}, block=True, priority=5)


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


@backup_cmd.handle()
async def handle_backup(event: MessageEvent):
    if not await is_admin(event):
        await backup_cmd.finish("⛔ 仅管理员可使用此命令")

    try:
        mysql_cfg = _get_mysql_config()
    except RuntimeError as e:
        await backup_cmd.finish(f"⛔ {e}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{timestamp}.sql.gz"
    filepath = BACKUP_DIR / filename

    host = mysql_cfg["host"]
    port = mysql_cfg.get("port", 3306)
    user = mysql_cfg["user"]
    password = mysql_cfg["password"]
    database = mysql_cfg["database"]

    # mysqldump | gzip > file
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
            logger.error(f"mysqldump 失败: {err_msg}")
            await backup_cmd.finish(f"⛔ 备份失败\n{err_msg[:200]}")

        # 检查文件有效性
        if not filepath.exists() or filepath.stat().st_size == 0:
            filepath.unlink(missing_ok=True)
            await backup_cmd.finish("⛔ 备份失败：生成的文件为空")

        file_size_mb = filepath.stat().st_size / (1024 * 1024)
        _cleanup_old_backups()

        msg_lines = [
            "✅ 数据库备份成功",
            "━━━━━━━━━━━━━",
            f"📄 文件：{filename}",
            f"📦 大小：{file_size_mb:.2f} MB",
            f"📁 路径：backups/",
            f"🗂️ 保留策略：最近 {MAX_BACKUPS} 个备份",
        ]
        await backup_cmd.finish(message_add_head("\n".join(msg_lines), event))

    except asyncio.TimeoutError:
        filepath.unlink(missing_ok=True)
        await backup_cmd.finish("⛔ 备份超时（超过5分钟）")
    except FileNotFoundError:
        await backup_cmd.finish("⛔ 未找到 mysqldump 命令，请确认已安装 MySQL 客户端工具")


@backup_status_cmd.handle()
async def handle_backup_status(event: MessageEvent):
    if not await is_admin(event):
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

    for f in files:
        size_mb = f.stat().st_size / (1024 * 1024)
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%m-%d %H:%M")
        msg_lines.append(f"📄 {f.name}  ({size_mb:.1f}MB, {mtime})")

    msg_lines.append("━━━━━━━━━━━━━")
    msg_lines.append(f"🗂️ 保留策略：最近 {MAX_BACKUPS} 个")

    await backup_status_cmd.finish(message_add_head("\n".join(msg_lines), event))
