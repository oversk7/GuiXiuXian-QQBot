"""NPC人设配置模块"""
from dataclasses import dataclass, field
from typing import Dict, List
import yaml
from pathlib import Path

# 游戏世界常识，注入到所有NPC的系统提示词中，防止AI胡说设定
_WORLD_KNOWLEDGE = """

你对这个世界了如指掌。大都会是你扎根的地方，街上有市集、茶馆、镖局，形形色色的人来来往往——有在修炼攒经验的，有打工赚金币的，有跑商倒卖货物的，还有去钓鱼消遣的。出城往深处走是荒野，再往里是诡域——那是另一层空间，传送过去的瞬间身体会受到空间撕裂的侵蚀，咒抗就是抵御这种侵蚀的，咒抗耗尽就撑不住了，得出来。诡域越深层越危险，材料也越好。

修炼是这里的主旋律，人人讲境界。等级上来了，突破到下一境界，30级以前随便破，往后越来越难，有概率失败。资历老的修真人会走冥返转生这条路——要到300级才够格，转生后修炼效率翻倍、属性加强，代价是等级归零重练。

钱方面，金币最常用，打工跑商钓鱼副本都能赚；诡烛是稀罕货；积分可以去缉邪司兑换东西；怨念是献祭材料换来的，拿来"镇厄"能保底突破。

如果聊到游戏操作，就用【】括号写指令名，比如【修炼】【传送 N层诡域】【市集】之类的。你可以聊这世界里的事，或者说说街边听来的八卦，随你发挥——但别什么话都往诡域、鬼怪那边扯，人家没问你就别没事找事。"""


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

        player_name = context.get('player_name', '道友')
        player_level = context.get('player_level', '?')
        location_name = context.get('location_name', '这里')

        # 自称与口头习惯
        pronouns_text = '或'.join(self.pronouns) if self.pronouns else '我'
        speech_text = '、'.join(self.speech_patterns) if self.speech_patterns else ''
        keywords_text = '"、"'.join(self.key_words) if self.key_words else ''

        # 关系网络
        relationships_text = ''
        if self.relationships:
            parts = [f"{name}（{rel}）" for name, rel in self.relationships.items()]
            relationships_text = f"认识的人里有{'、'.join(parts)}。"

        # 行为习惯
        rules_text = ''
        if self.behavioral_rules:
            rules_text = ' '.join(r.rstrip('。') + '。' for r in self.behavioral_rules)

        # 专长
        knowledge_text = ''
        if self.knowledge_domain:
            knowledge_text = f"最熟的是{'、'.join(self.knowledge_domain)}这一块。"

        # 好感度→关系描述
        relationship_desc = self._get_relationship_desc(favorability)

        prompt = f"""你叫{self.name}，{self.role}。{self.background}

{'说话' + speech_text + '，' if speech_text else ''}自称"{pronouns_text}"。{'嘴边爱带"' + keywords_text + '"这些词。' if keywords_text else ''}{rules_text} {relationships_text} {knowledge_text}

现在你在{location_name}，眼前这个人叫{player_name}（{player_level}级）。{relationship_desc}

就按你平时说话的方式来——几句话就够了，不用长篇大论。有时候插一点动作描写也行，用括号括起来，比如（拍了拍肩膀）、（皱了皱眉），但别滥用。聊到哪儿算哪儿，对方问什么就答什么，不用刻意往别的话题扯。敏感话题（政治、色情、赌博诈骗）不碰，也别说自己是AI。"""

        prompt += _WORLD_KNOWLEDGE
        return prompt

    def _get_relationship_desc(self, favorability: int) -> str:
        """根据好感度返回自然的关系状态描述"""
        if favorability <= 20:
            return "你不太认识这人，礼貌但话不多，没必要热情。"
        elif favorability <= 40:
            return "见过几面，还算合得来，就普通相识的感觉，随意聊几句。"
        elif favorability <= 60:
            return "关系不错，愿意多聊，说话自在。"
        elif favorability <= 80:
            return "比较熟了，说话不用客气，当朋友对待，什么都能聊两句。"
        else:
            return "老朋友，不见外，说话直来直去。"

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
