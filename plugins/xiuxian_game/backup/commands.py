"""数据库备份管理命令"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from datetime import datetime
import os

from .service import backup_service
from ..utils import message_add_head


# ==================== 手动备份 ====================
manual_backup_cmd = on_command("手动备份", block=True, priority=1, permission=SUPERUSER)

@manual_backup_cmd.handle()
async def handle_manual_backup(event: MessageEvent):
    """手动触发数据库备份"""
    try:
        await manual_backup_cmd.send("🔄 正在执行数据库备份...")
        
        success = backup_service.create_backup()
        
        if success:
            # 获取最新备份信息
            backups = backup_service.get_backup_list()
            if backups:
                latest = backups[0]
                size_mb = latest["size"] / (1024 * 1024)
                created_time = latest["created_time"].strftime("%Y-%m-%d %H:%M:%S")
                
                message = (
                    "✅ 数据库备份成功！\n"
                    "━━━━━━━━━━━━━\n"
                    f"📁 备份文件: {latest['filename']}\n"
                    f"📊 文件大小: {size_mb:.2f} MB\n"
                    f"🕒 备份时间: {created_time}\n"
                    f"📦 总备份数: {len(backups)}"
                )
            else:
                message = "✅ 数据库备份成功！"
        else:
            message = "❌ 数据库备份失败，请检查日志"
        
        await manual_backup_cmd.finish(message_add_head(message, event))
        
    except Exception as e:
        await manual_backup_cmd.finish(message_add_head(f"❌ 备份过程中发生错误: {str(e)}", event))


# ==================== 备份状态 ====================
backup_status_cmd = on_command("备份状态", aliases={"备份列表"}, block=True, priority=1, permission=SUPERUSER)

@backup_status_cmd.handle()
async def handle_backup_status(event: MessageEvent):
    """查看备份状态和列表"""
    try:
        backups = backup_service.get_backup_list()
        
        if not backups:
            message = (
                "📦 数据库备份状态\n"
                "━━━━━━━━━━━━━\n"
                "❌ 暂无备份文件\n"
                "💡 使用【手动备份】创建备份"
            )
        else:
            message_lines = [
                "📦 数据库备份状态",
                "━━━━━━━━━━━━━",
                f"📊 备份总数: {len(backups)}",
                f"🔄 自动备份: 每2小时一次",
                f"📁 保留数量: 最近 {backup_service.max_backups} 个",
                "",
                "📋 备份文件列表:"
            ]
            
            for i, backup in enumerate(backups, 1):
                size_mb = backup["size"] / (1024 * 1024)
                created_time = backup["created_time"].strftime("%m-%d %H:%M")
                
                # 标记最新备份
                prefix = "🆕" if i == 1 else f"{i:2d}."
                message_lines.append(f"{prefix} {backup['filename']}")
                message_lines.append(f"    📊 {size_mb:.2f}MB | 🕒 {created_time}")
                
                if i < len(backups):  # 不是最后一个
                    message_lines.append("")
            
            message = "\n".join(message_lines)
        
        await backup_status_cmd.finish(message_add_head(message, event))
        
    except Exception as e:
        await backup_status_cmd.finish(message_add_head(f"❌ 获取备份状态失败: {str(e)}", event))


# ==================== 恢复备份 ====================
restore_backup_cmd = on_command("恢复备份", block=True, priority=1, permission=SUPERUSER)

@restore_backup_cmd.handle()
async def handle_restore_backup(event: MessageEvent, args: Message = CommandArg()):
    """从备份恢复数据库"""
    backup_filename = args.extract_plain_text().strip()
    
    if not backup_filename:
        # 显示可用的备份文件
        backups = backup_service.get_backup_list()
        if not backups:
            await restore_backup_cmd.finish(message_add_head("❌ 没有可用的备份文件", event))
        
        message_lines = [
            "🔄 数据库恢复",
            "━━━━━━━━━━━━━",
            "请指定要恢复的备份文件名:",
            "格式: 恢复备份 <文件名>",
            "",
            "📋 可用备份:"
        ]
        
        for i, backup in enumerate(backups[:5], 1):  # 只显示前5个
            created_time = backup["created_time"].strftime("%m-%d %H:%M")
            message_lines.append(f"{i}. {backup['filename']} ({created_time})")
        
        message = "\n".join(message_lines)
        await restore_backup_cmd.finish(message_add_head(message, event))
    
    try:
        # 确认操作
        await restore_backup_cmd.send(message_add_head(
            f"⚠️ 警告：即将恢复备份\n"
            f"📁 备份文件: {backup_filename}\n"
            f"🔄 这将覆盖当前数据库！\n"
            f"⏳ 正在执行恢复...", event))
        
        success = backup_service.restore_backup(backup_filename)
        
        if success:
            message = (
                "✅ 数据库恢复成功！\n"
                "━━━━━━━━━━━━━\n"
                f"📁 已从 {backup_filename} 恢复\n"
                "🔄 建议重启机器人以确保数据一致性"
            )
        else:
            message = (
                "❌ 数据库恢复失败！\n"
                "━━━━━━━━━━━━━\n"
                "可能原因:\n"
                "• 备份文件不存在\n"
                "• 文件权限问题\n"
                "• 备份文件损坏"
            )
        
        await restore_backup_cmd.finish(message_add_head(message, event))
        
    except Exception as e:
        await restore_backup_cmd.finish(message_add_head(f"❌ 恢复过程中发生错误: {str(e)}", event))
