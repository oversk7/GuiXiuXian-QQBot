"""
里界系统模块

提供完整的里界探索体验:
- 2D6骰子判定系统
- 多结局叙事
- 细思极恐的碎片拼图
"""
from . import commands  # 导入命令处理器以注册
from . import scheduler  # 导入定时任务以注册

__all__ = ["commands", "scheduler"]
