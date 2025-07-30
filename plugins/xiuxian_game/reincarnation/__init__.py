"""
冥返系统模块
"""
from .service import ReincarnationService
from . import commands  # 导入命令模块以注册命令

__all__ = ["ReincarnationService"]
