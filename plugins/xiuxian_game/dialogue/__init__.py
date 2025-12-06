"""NPC对话系统模块"""

from .npc_personality import PersonalityTemplate, PersonalityManager
from .ai_dialogue_service import AIDialogueService
from .npc_favorability_service import NPCFavorabilityService
from . import admin_commands  # 导入管理员命令（包含批量启用/禁用NPC AI）

__all__ = [
    "PersonalityTemplate",
    "PersonalityManager",
    "AIDialogueService",
    "NPCFavorabilityService",
]
