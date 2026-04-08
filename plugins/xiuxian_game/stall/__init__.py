"""
个人摊位系统模块

功能：
- 玩家自由定价的直购交易渠道
- 消耗摊位令在城镇开摊，持续24小时
- 支持装备实例和普通物品
- 超高溢价累进税防止洗金
"""

from . import stall_commands    # 注册命令处理器
from . import stall_scheduler   # 注册定时任务

__all__ = ["stall_commands", "stall_scheduler"]
