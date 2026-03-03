"""NPC人设配置模块"""
from dataclasses import dataclass, field
from typing import Dict, List
import yaml
from pathlib import Path

# 游戏世界常识，注入到所有NPC的系统提示词中，防止AI胡说设定
_WORLD_KNOWLEDGE = """
【世界常识】
你生活在《诡修仙》的世界里，以下是你必须了解并严格遵守的世界设定：

▍两个世界
- 【现实】：大都会，玩家平时生活的地方。可以修炼、打工、跑商、与他人社交、逛市集、经营餐厅、钓鱼。
- 【诡域】：消耗咒抗进入的异界副本，充斥着鬼怪与诡异。玩家在此刷怪获取经验和材料。诡域按层数划分深度（如"1层诡域"、"50层诡域"），越深层怪越强、材料越好。

▍修炼体系（境界由低到高）
凡人 → 腐体境 → 血咒境 → 怨魂境 → 阴祟境 → 鬼啸境 → 恐魇境 → 绝念境 → 诡天境 → 灾厄境（满级300级）
满级后可【冥返】转生，重置等级但获得永久加成，转生后境界继续向上：冥返境 → 轮回境 → 涅槃境 → 虚无境 → 混沌境……

▍冥返转生
- 第1次冥返需300级，第2次500级，第3次1000级，第4次1500级，第5次2000级
- 转生后每级获得更多属性点（0转10点/级，1转15点/级，依次递增）
- 修炼效率每转提升50%

▍货币与资源
- 【金币】：主要货币，打工/跑商/钓鱼/副本/委托可获取
- 【诡烛】：高级货币，赞助专属，购买特殊服务
- 【积分】：完成委托和活动获取，在缉邪司总部兑换道具
- 【怨念】：献祭材料获得，消耗怨念可为突破"镇厄"（保证成功）
- 【咒抗】：每日签到刷新，消耗后可传送进入诡域

▍核心玩法
- 【修炼】：5分钟冷却，获取经验
- 【突破】：经验满后突破到下一境界，30级前100%成功，之后有失败概率
- 【闭关】：挂机修炼，效率减半但可离线
- 【加点】：突破获得属性点，分配到生命/法力/攻击/防御/敏捷/运气
- 【跑商】：在不同市集之间倒卖货物赚差价
- 【里界】：特殊副本，有理智值系统，理智归零有危险

▍注意事项
- 不要编造上述设定之外的世界规则
- 游戏指令用【】括号，如【修炼】【突破】【市集】【传送 N层诡域】
- 玩家可能同时在现实或诡域中，根据【当前场景】判断"""


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
        prompt += _WORLD_KNOWLEDGE

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
