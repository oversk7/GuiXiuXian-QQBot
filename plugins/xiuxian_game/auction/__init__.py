"""
拍卖行系统模块

功能：
- 稀有、高价值物品的限时竞价交易
- 支持装备实例（镶嵌宝石的高阶装备等）和普通物品
- 拍卖上架/出价/撤拍/结算全流程
- 自动向留言板广播：上架、30分钟提醒、结束结果
"""

from . import auction_commands   # 注册命令处理器
from . import auction_scheduler  # 注册定时任务

__all__ = ["auction_commands", "auction_scheduler"]
