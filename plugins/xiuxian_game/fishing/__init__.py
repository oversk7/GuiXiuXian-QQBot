"""钓鱼系统模块

提供钓鱼玩法相关的所有功能
"""

from .service import FishingService
from . import commands

__all__ = ["FishingService", "commands"]
