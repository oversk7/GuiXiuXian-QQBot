"""
社交系统模块

包含礼物系统、关系系统、账号切换系统、排行榜和红包功能
使用统一的PlayerRelationship表管理所有社交关系
"""

# 导入所有命令处理器以确保它们被注册
from . import gift_commands  # 新的送礼系统命令(赠礼/转移)
from . import gift_shop  # 礼物商店系统
from . import relationship_commands  # 关系管理命令(好感度/离婚/断义等)
from . import rankings
from . import account_switching
from . import red_envelope  # 红包系统
from . import npc_mentor  # 师徒系统（香火商店、买食谱独立指令）

__all__ = ["gift_commands", "gift_shop", "relationship_commands", "rankings", "account_switching", "red_envelope", "npc_mentor"]
