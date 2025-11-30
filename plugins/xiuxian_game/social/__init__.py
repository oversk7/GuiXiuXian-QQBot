"""
社交系统模块

包含婚姻系统、师徒系统、礼物系统、账号切换系统和排行榜功能
"""

# 导入所有命令处理器以确保它们被注册
from . import marriage
from . import mentorship
from . import gift
from . import rankings
from . import account_switching

__all__ = ["marriage", "mentorship", "gift", "rankings", "account_switching"]
