"""NPC人设配置模块"""
from dataclasses import dataclass, field
from typing import Dict, List
import yaml
from pathlib import Path


@dataclass
class PersonalityTemplate:
    """NPC人设模板"""

    # 基本身份
    name: str
    role: str  # "镇上的大块头", "茶馆老板", "流浪剑客"

    # 语言特征
    pronouns: List[str] = field(default_factory=list)  # ["俺", "本大爷"]（使用的自称）
    speech_patterns: List[str] = field(default_factory=list)  # ["粗犷", "直爽", "豪迈"]
    key_words: List[str] = field(default_factory=list)  # ["嘿呀", "果然", "怎么了"]（常用词汇）

    # 性格特征 (0-100)
    personality_traits: Dict[str, int] = field(default_factory=dict)
    # {
    #     "loyalty": 80,      # 忠诚度
    #     "cheerfulness": 70,  # 开朗度
    #     "aggressiveness": 60 # 好斗度
    # }

    # 背景故事
    background: str = ""
    relationships: Dict[str, str] = field(default_factory=dict)
    # {
    #     "武安勇": "朋友",
    #     "魔神": "恩人"
    # }

    # 行为规则
    behavioral_rules: List[str] = field(default_factory=list)  # ["不会背叛跟随者", "喜欢在茶馆闲聊"]
    preferred_actions: List[str] = field(default_factory=list)  # ["切磋", "饮酒", "打工"]

    # 知识领域
    knowledge_domain: List[str] = field(default_factory=list)  # ["锻造", "装备升阶"]

    def build_system_prompt(self, favorability: int = 50, context: dict = None) -> str:
        """构建AI系统提示词"""
        context = context or {}

        # 根据好感度确定态度
        attitude = self._get_attitude_by_favorability(favorability)

        # 构建性格描述
        personality_desc = ", ".join([
            f"{trait}度{value}/100"
            for trait, value in self.personality_traits.items()
        ])

        # 构建关系描述
        relationships_desc = "\n".join([
            f"- {name}: {relation}"
            for name, relation in self.relationships.items()
        ])

        # 构建行为规则
        rules_desc = "\n".join([f"- {rule}" for rule in self.behavioral_rules])

        prompt = f"""你是一个修仙游戏中的NPC角色，扮演{self.name}。

【角色身份】
- 名称: {self.name}
- 角色: {self.role}
- 背景: {self.background}

【语言风格】
- 自称: 使用{', '.join(self.pronouns)}（如"俺"、"本大爷"等）
- 性格: {', '.join(self.speech_patterns)}
- 常用词汇: {', '.join(self.key_words)}

【性格数值】
{personality_desc}

【人物关系】
{relationships_desc if relationships_desc else '暂无特殊关系'}

【行为准则】
{rules_desc if rules_desc else '遵循基本道德规范'}

【知识领域】
你擅长: {', '.join(self.knowledge_domain) if self.knowledge_domain else '无特殊专长'}

【对话风格】
- 好感度{favorability}时，用{attitude}的态度说话
- 回复要短小精悍，不超过150字
- 要体现NPC的性格特征和背景
- 适度添加修仙世界观元素（如"道友"、"修为"等）

【内容限制】
- 不要讨论政治、色情、暴力、赌博、诈骗等敏感话题
- 不要透露你是AI，保持角色扮演
- 涉及游戏功能时，引导玩家使用对应指令（如【锻造】、【市集】）

【当前场景】
- 地点: {context.get('location_name', '未知')}
- 玩家: {context.get('player_name', '道友')}（等级{context.get('player_level', '?')}）
"""

        return prompt

    def _get_attitude_by_favorability(self, favorability: int) -> str:
        """根据好感度返回对应的态度描述"""
        if favorability <= 20:
            return "冷漠、敷衍"
        elif favorability <= 40:
            return "友好、配合"
        elif favorability <= 60:
            return "热情、主动"
        elif favorability <= 80:
            return "亲切、信任"
        else:
            return "忠诚、无条件"

    @classmethod
    def from_dict(cls, data: dict) -> "PersonalityTemplate":
        """从字典创建人设模板"""
        return cls(
            name=data.get("name", ""),
            role=data.get("role", ""),
            pronouns=data.get("pronouns", []),
            speech_patterns=data.get("speech_patterns", []),
            key_words=data.get("key_words", []),
            personality_traits=data.get("personality_traits", {}),
            background=data.get("background", ""),
            relationships=data.get("relationships", {}),
            behavioral_rules=data.get("behavioral_rules", []),
            preferred_actions=data.get("preferred_actions", []),
            knowledge_domain=data.get("knowledge_domain", [])
        )

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "name": self.name,
            "role": self.role,
            "pronouns": self.pronouns,
            "speech_patterns": self.speech_patterns,
            "key_words": self.key_words,
            "personality_traits": self.personality_traits,
            "background": self.background,
            "relationships": self.relationships,
            "behavioral_rules": self.behavioral_rules,
            "preferred_actions": self.preferred_actions,
            "knowledge_domain": self.knowledge_domain
        }


class PersonalityManager:
    """人设管理器"""

    _personalities: Dict[str, PersonalityTemplate] = {}

    @classmethod
    def load_from_file(cls, file_path: Path):
        """从YAML文件加载人设配置"""
        if not file_path.exists():
            raise FileNotFoundError(f"人设配置文件不存在: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if not data or "personalities" not in data:
            raise ValueError("人设配置文件格式错误，缺少 'personalities' 字段")

        for npc_name, personality_data in data["personalities"].items():
            cls._personalities[npc_name] = PersonalityTemplate.from_dict(personality_data)

    @classmethod
    def get_personality(cls, npc_name: str) -> PersonalityTemplate | None:
        """获取NPC人设"""
        return cls._personalities.get(npc_name)

    @classmethod
    def has_personality(cls, npc_name: str) -> bool:
        """检查NPC是否有配置的人设"""
        return npc_name in cls._personalities

    @classmethod
    def get_all_personalities(cls) -> Dict[str, PersonalityTemplate]:
        """获取所有人设"""
        return cls._personalities.copy()

    @classmethod
    def clear(cls):
        """清空所有人设"""
        cls._personalities.clear()
