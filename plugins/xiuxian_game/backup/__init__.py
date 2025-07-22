"""数据库备份模块"""
from .scheduler import setup_backup_scheduler
from . import commands

# 导入调度器设置，这样在模块加载时就会自动设置定时任务
# 导入命令模块以注册命令处理器
__all__ = ["setup_backup_scheduler"]
