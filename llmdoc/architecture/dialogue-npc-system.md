# 对话NPC系统架构设计

## 1. Identity

- **What it is**: 一个支持自然对话与游戏指令双重交互的NPC AI系统，允许NPC执行游戏命令、进行角色扮演对话、维护好感度关系
- **Purpose**: 为玩家与NPC提供沉浸式交互体验，使NPC成为活生生的游戏伙伴，支持多种NPC角色的自主决策和长期记忆

## 2. Core Components

### 2.1 指令解析层
- `plugins/xiuxian_game/dialogue/command_parser.py` (DialogueCommandParser): 负责解析玩家输入，区分游戏指令与自然对话，返回结构化指令对象

### 2.2 NPC人设层
- `plugins/xiuxian_game/dialogue/npc_personality.py` (NPCPersonality, PersonalityTemplate): 定义NPC人设配置（称谓、语气、性格、背景故事），支持多个预设模板和自定义配置

### 2.3 虚拟Player账号管理
- `plugins/xiuxian_game/dialogue/npc_virtual_player.py` (NPCVirtualPlayer, VirtualPlayerManager): 为NPC创建虚拟账号、管理NPC背包、同步NPC属性与物品状态

### 2.4 AI对话生成
- `plugins/xiuxian_game/dialogue/ai_dialogue_service.py` (AIDialogueService): 使用LLM生成NPC角色扮演回复，基于NPC人设、上下文、好感度动态调整

### 2.5 指令执行引擎
- `plugins/xiuxian_game/dialogue/game_command_executor.py` (GameCommandExecutor): 执行游戏指令（如"执行使用追风膏"、"跟随玩家"），协调Service层完成业务逻辑

### 2.6 好感度系统
- `plugins/xiuxian_game/dialogue/npc_favorability.py` (NPCFavorability, FavorabilityRecord): 维护玩家与NPC的好感度关系，记录互动历史，影响NPC态度和决策

### 2.7 对话历史存储
- `plugins/xiuxian_game/models/npc_dialogue_history.py` (NPCDialogueHistory): 数据模型，记录对话历史、互动记录、关键事件，支持上下文查询

### 2.8 对话命令集成
- `plugins/xiuxian_game/dialogue/dialogue_commands.py` (dialogue_handler): Nonebot2命令处理器，集成指令解析、AI对话、指令执行的完整流程

## 3. Execution Flow (LLM Retrieval Map)

### 3.1 对话命令触发流程

```
1. 玩家输入: @浅鸟 对话武安勇 执行使用追风膏
   ↓
2. Nonebot2路由匹配: on_command("对话", aliases={"交互"})
   位置: dialogue_commands.py:handle_dialogue_command()
   ↓
3. 权限检查: 验证玩家存在、不在诡域、NPC存在
   ↓
4. 指令解析: 调用DialogueCommandParser.parse()
   位置: command_parser.py:parse_user_input()
   返回: ParsedDialogueCommand(
       type="game_command" | "natural_dialogue",
       npc_name="武安勇",
       content="执行使用追风膏" | "你有追风膏吗？",
       ...
   )
   ↓
5. 路由分发: 根据parsed_cmd.type选择处理路径
   - game_command → 5a
   - natural_dialogue → 5b
```

### 3.2 游戏指令执行流程 (Path 5a)

```
5a. 游戏指令执行
   ↓
6. 创建虚拟Player: 若NPC尚无虚拟账号，调用VirtualPlayerManager.create_virtual_player()
   位置: npc_virtual_player.py:create_virtual_player()
   操作: 创建player表记录，关联NPC
   ↓
7. 解析指令: GameCommandExecutor.parse_game_command()
   识别指令类型: "使用", "跟随", "锻造", "挂牌", "打工"等
   ↓
8. 执行指令: 调用相应的Service方法
   示例: 执行使用追风膏
   ├─ 调用 ItemService.use_item(virtual_player_id, item_id)
   ├─ 物品消耗、属性加成应用
   └─ 返回效果描述 → "涂抹追风膏，足下生风！移速提升九成！！！"
   ↓
9. AI对话生成: 调用AIDialogueService.generate_roleplay_response()
   输入: {
       "npc": NPC对象,
       "action": "使用追风膏",
       "game_output": "移速提升九成",
       "context": {...}
   }
   输出: "嘿呀，这追风膏果真是好东西，涂了之后俺感觉脚下像生了风一样，速度快了不少！"
   ↓
10. 更新好感度: FavorabilityRecord.add_interaction()
    关键: 游戏指令执行后增加好感度 (+5 ~ +15)
    ↓
11. 保存对话历史: NPCDialogueHistory.save()
    记录: action, game_output, npc_response, favorability_change
    ↓
12. 响应用户:
    NPC回复：多谢魔神兄弟给俺这追风膏，俺这就用了。（拿起追风膏，熟练地涂抹开来）
             (当前好感度: 100)
    游戏输出：涂抹追风膏，足下生风！移速提升九成！！！
    NPC回复：嘿呀，这追风膏果真是好东西，涂了之后俺感觉脚下像生了风一样，速度快了不少！
```

### 3.3 自然对话流程 (Path 5b)

```
5b. 自然对话
   ↓
6. 加载对话历史: NPCDialogueHistory.get_recent_interactions()
   获取最近N条互动记录，建立上下文
   ↓
7. AI对话生成: AIDialogueService.generate_dialogue()
   输入: {
       "npc": NPC对象,
       "personality": NPCPersonality,
       "question": "你有追风膏吗？",
       "dialogue_history": [...],
       "favorability": 100,
       "context": {...}
   }
   处理: LLM根据NPC人设、对话历史、好感度生成回复
   ↓
8. 更新好感度: FavorabilityRecord.add_interaction()
   自然对话增加好感度 (+1 ~ +3)
   ↓
9. 保存对话历史: NPCDialogueHistory.save()
   ↓
10. 响应用户:
    NPC回复：俺这没有追风膏啊，怎么了墨涵兄弟，你是急需这玩意儿不成？
             (当前好感度: 100)
```

### 3.4 NPC虚拟Player账号同步流程

```
背景：每个对话NPC拥有虚拟Player账号，用于执行游戏指令

同步场景1: 物品转移
玩家: @浅鸟 对话武安勇 执行接收38个追风膏
   ↓
1. 虚拟Player扣除物品: ItemService.consume_item(virtual_player_id, "追风膏", 38)
   操作: inventory表中扣除38个追风膏
   ↓
2. 玩家增加物品: ItemService.add_item(player_id, "追风膏", 38)
   ↓
3. 更新NPCVirtualPlayer.inventory_snapshot: 快照当前背包
   用于验证同步一致性

同步场景2: NPC属性更新
玩家: @浅鸟 对话武安勇 执行使用追风膏
   ↓
1. 应用效果: 虚拟Player属性计算
   调用 AttributeCalculator.calculate_effective_attributes()
   ↓
2. 更新NPC显示属性: 更新NPC表中的临时属性字段
   用于战斗、展示等场景
```

## 4. 数据模型设计

### 4.1 NPC模型扩展 (models/npc.py)

```python
class NPC(Base):
    __tablename__ = "npc"

    # 现有字段 (保留)
    id, npc_id, name, description, npc_type, location_id
    status, is_active, is_killable, level, hp, max_hp, attack, defense, agility

    # === 对话系统新增字段 ===

    # 虚拟账号关联
    virtual_player_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("player.id"),
        nullable=True, comment="关联的虚拟Player账号ID"
    )
    virtual_player: Mapped["Player"] = relationship(
        "Player", foreign_keys=[virtual_player_id]
    )

    # 人设配置
    personality_template: Mapped[str] = mapped_column(
        String(50), default="default",
        comment="人设模板名称"
    )
    personality_config: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        comment="人设配置JSON，包含称谓、语气、背景等"
    )

    # AI对话参数
    ai_dialogue_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True,
        comment="是否启用AI对话"
    )
    ai_model_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True,
        comment="使用的AI模型ID（如claude-3.5-sonnet）"
    )
    ai_context_tokens: Mapped[int] = mapped_column(
        Integer, default=2000,
        comment="AI上下文token限制"
    )

    # 好感度
    base_favorability: Mapped[int] = mapped_column(
        Integer, default=50,
        comment="初始好感度(0-100)"
    )

    # 对话历史统计
    dialogue_count: Mapped[int] = mapped_column(
        Integer, default=0,
        comment="累计对话次数"
    )
    last_dialogue_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True,
        comment="最后对话时间"
    )

    # NPC决策参数
    autonomous_action_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="是否启用自主决策"
    )
    autonomous_action_interval_minutes: Mapped[int] = mapped_column(
        Integer, default=60,
        comment="自主决策间隔(分钟)"
    )
```

### 4.2 NPC对话历史模型 (models/npc_dialogue_history.py)

```python
class NPCDialogueHistory(Base):
    """记录玩家与NPC的对话历史"""
    __tablename__ = "npc_dialogue_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 关键关联
    npc_id: Mapped[int] = mapped_column(Integer, ForeignKey("npc.id"), index=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True)

    npc: Mapped["NPC"] = relationship("NPC")
    player: Mapped["Player"] = relationship("Player")

    # 对话内容
    dialogue_type: Mapped[str] = mapped_column(
        String(20), comment="对话类型: game_command | natural_dialogue"
    )
    player_input: Mapped[str] = mapped_column(Text, comment="玩家输入")
    npc_response: Mapped[str] = mapped_column(Text, comment="NPC回复")

    # 游戏命令相关
    game_command: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="游戏指令内容（仅game_command类型）"
    )
    game_output: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="游戏指令执行结果"
    )
    game_command_status: Mapped[str] = mapped_column(
        String(20), default="success",
        comment="指令执行状态: success | failed | partial"
    )

    # 好感度变化
    favorability_change: Mapped[int] = mapped_column(
        Integer, default=0,
        comment="本次对话导致的好感度变化"
    )
    favorability_after: Mapped[int] = mapped_column(
        Integer, default=50,
        comment="本次对话后的总好感度"
    )

    # 元数据
    dialogue_duration_seconds: Mapped[int] = mapped_column(
        Integer, default=0,
        comment="对话耗时(秒)"
    )
    ai_tokens_used: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="AI调用消耗的token数"
    )
    ai_cost: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="AI调用成本(USD)"
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )
```

### 4.3 好感度记录模型 (models/npc_favorability.py)

```python
class NPCFavorability(Base):
    """记录玩家与NPC的好感度关系"""
    __tablename__ = "npc_favorability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    npc_id: Mapped[int] = mapped_column(Integer, ForeignKey("npc.id"), index=True, unique=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True, unique=True)

    npc: Mapped["NPC"] = relationship("NPC")
    player: Mapped["Player"] = relationship("Player")

    # 好感度数据
    current_favorability: Mapped[int] = mapped_column(
        Integer, default=50,
        comment="当前好感度(0-100)"
    )
    total_interactions: Mapped[int] = mapped_column(
        Integer, default=0,
        comment="累计互动次数"
    )
    total_favorability_gained: Mapped[int] = mapped_column(
        Integer, default=0,
        comment="累计好感度获得"
    )

    # 关系等级
    relationship_level: Mapped[str] = mapped_column(
        String(20), default="陌生人",
        comment="关系等级: 陌生人|熟识|友好|亲密|知心"
    )

    # 特殊关系
    is_follower: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="是否跟随关系"
    )
    is_partner: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="是否伴侣关系"
    )

    # 关键事件记录
    first_interaction_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    last_interaction_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    milestone_events: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        comment="关键事件记录，如\"100好感度解锁\""
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
```

## 5. 指令解析策略

### 5.1 混合模式 (推荐方案)

采用**关键词预筛选 + AI兜底**的混合策略：

```
用户输入: "对话武安勇 执行使用追风膏"
   ↓
1. 关键词识别 (快速路径)
   检查是否包含: "执行", "使用", "跟随", "锻造", "挂牌", "打工"等
   ├─ 包含 → 确定为game_command，直接执行
   └─ 不包含 → 继续步骤2
   ↓
2. AI意图识别 (精确路径)
   调用LLM: "用户说'你有追风膏吗？'，这是游戏指令还是自然对话？"
   返回: natural_dialogue
```

### 5.2 指令类型识别表

| 用户输入 | 关键词 | 指令类型 | 处理路径 |
|---------|--------|---------|---------|
| 执行使用追风膏 | "执行" | game_command | GameCommandExecutor |
| 跟随我 | "跟随" | game_command | FollowService |
| 你有什么装备吗 | 无 | natural_dialogue | AIDialogueService |
| 执行挂牌精铁剑3000 | "执行", "挂牌" | game_command | MarketService |
| 打工茶馆伙计 | "打工" | game_command | JobService |
| 帮我锻造这把剑 | 无（需AI判断） | natural_dialogue | AIDialogueService |

### 5.3 ParsedDialogueCommand数据结构

```python
@dataclass
class ParsedDialogueCommand:
    """解析后的对话指令"""

    # 基本信息
    npc_name: str  # "武安勇"
    player_input: str  # "执行使用追风膏"
    dialogue_type: str  # "game_command" | "natural_dialogue"

    # 游戏指令相关
    game_command_type: str | None  # "use_item", "follow", "forge", "market_sell", "part_time_job"
    game_command_args: dict = field(default_factory=dict)  # {"item_id": "追风膏", "qty": 1}

    # 自然对话相关
    question: str | None  # "你有追风膏吗？"
    intent: str | None  # "query", "request", "chat", "complain"

    # 元数据
    confidence: float  # 0.0-1.0，指令类型识别的置信度
    source: str  # "keyword" | "ai"
```

## 6. NPC人设配置

### 6.1 PersonalityTemplate结构

```python
@dataclass
class PersonalityTemplate:
    """NPC人设模板"""

    # 基本身份
    name: str  # "武安勇"
    role: str  # "镇上的大块头", "茶馆老板", "流浪剑客"

    # 语言特征
    pronouns: list[str]  # ["俺", "本大爷"]（使用的自称）
    speech_patterns: list[str]  # ["粗犷", "直爽", "豪迈"]
    key_words: list[str]  # ["嘿呀", "果然", "怎么了"]（常用词汇）

    # 性格特征
    personality_traits: dict[str, int] = field(default_factory=dict)
    # {
    #     "loyalty": 80,      # 忠诚度
    #     "cheerfulness": 70,  # 开朗度
    #     "aggressiveness": 60 # 好斗度
    # }

    # 背景故事
    background: str  # 详细的人物背景
    relationships: dict[str, str] = field(default_factory=dict)
    # {
    #     "武安勇": "朋友",
    #     "魔神": "恩人"
    # }

    # AI提示词
    system_prompt: str  # 发送给LLM的完整系统提示词

    # 行为规则
    behavioral_rules: list[str]  # ["不会背叛跟随者", "喜欢在茶馆闲聊", "害怕权贵"]
    preferred_actions: list[str]  # ["切磋", "饮酒", "打工"]
```

### 6.2 AI系统提示词模板

```python
PERSONALITY_PROMPT_TEMPLATE = """你是一个修仙游戏中的NPC角色，扮演{name}。

【角色身份】
- 名称: {name}
- 角色: {role}
- 背景: {background}

【语言风格】
- 自称: 使用{pronouns}（如"俺"、"本大爷"等）
- 性格: {personality_description}
- 常用词汇: {key_words}
- 说话特点: {speech_patterns}

【性格数值】
- 忠诚度: {loyalty}/100（低=容易背叛, 高=忠诚至死）
- 开朗度: {cheerfulness}/100（低=沉默寡言, 高=热情开朗）
- 好斗度: {aggressiveness}/100（低=温和, 高=好战）

【人物关系】
{relationships}

【行为准则】
{behavioral_rules}

【指令执行风格】
当玩家要求你执行游戏指令时:
1. 先用一句角色扮演的台词表现你的态度
2. 用(动作描写)表现你的行为，如(拿起追风膏，熟练地涂抹开来)
3. 执行指令后，再用一句台词总结你的感受

【对话风格】
- 好感度{favorability}时，用{favorability_attitude}的态度说话
- 回复要短小精悍，不超过100字
- 要体现NPC的性格特征和背景

【当前状态】
- 好感度: {favorability}/100
- 累计互动: {total_interactions}次
- 最后对话: {last_dialogue_at}
- 跟随状态: {follower_status}
"""
```

### 6.3 预设人设示例

**武安勇（大块头）**:
```json
{
  "name": "武安勇",
  "role": "镇上的大块头",
  "pronouns": ["俺", "本大爷"],
  "personality": "粗犷、直爽、豪迈",
  "background": "出身贫寒，靠蛮力讨生活，后遇到魔神改变人生",
  "behavioral_rules": [
    "对给他东西的人很感激",
    "喜欢参加战团切磋",
    "会认真执行跟随者的指令",
    "害怕权贵但敢反抗"
  ]
}
```

## 7. 虚拟Player账号设计

### 7.1 NPCVirtualPlayer管理器

```python
class VirtualPlayerManager:
    """管理NPC的虚拟Player账号"""

    async def create_virtual_player(
        self,
        npc: NPC,
        player_repo: PlayerRepository
    ) -> Player:
        """
        为NPC创建虚拟Player账号

        设计要点:
        1. player_id = "npc_{npc_id}" 特殊标识
        2. nickname = NPC名称
        3. virtual_player_owner_npc_id = npc.id 反向引用
        4. 初始属性与NPC战斗属性同步
        5. 自动创建初始背包
        """

    async def sync_virtual_player_attributes(
        self,
        npc: NPC,
        session: AsyncSession
    ) -> None:
        """
        同步虚拟Player属性与NPC属性
        触发时机: 装备穿戴、Buff生效、属性增长
        """

    async def get_virtual_player_inventory(
        self,
        npc: NPC,
        session: AsyncSession
    ) -> List[ItemInstance]:
        """获取NPC的背包物品"""

    async def add_item_to_npc(
        self,
        npc: NPC,
        item_id: str,
        quantity: int,
        session: AsyncSession
    ) -> ItemInstance:
        """为NPC添加物品（如玩家赠送）"""

    async def remove_item_from_npc(
        self,
        npc: NPC,
        item_id: str,
        quantity: int,
        session: AsyncSession
    ) -> bool:
        """从NPC背包移除物品（NPC使用）"""
```

### 7.2 虚拟Player账号特殊处理

在以下位置添加虚拟Player检查：

**Platform工具**: `plugins/xiuxian_game/platform_utils.py`
```python
def is_npc_virtual_player(player_id: str) -> bool:
    """检查是否为NPC虚拟Player"""
    return player_id.startswith("npc_")

async def get_npc_from_virtual_player(
    session: AsyncSession,
    player_id: str
) -> Optional[NPC]:
    """从虚拟Player反向查询NPC"""
    if is_npc_virtual_player(player_id):
        # 查询NPC表，匹配virtual_player_id
        return await NPCRepository(session).get_by_virtual_player_id(player_id)
    return None
```

## 8. AI对话服务接口

### 8.1 AIDialogueService核心方法

```python
class AIDialogueService:
    """
    使用LLM生成NPC对话的服务

    对接LLM: Claude API / OpenAI API / 本地模型
    """

    async def generate_roleplay_response(
        self,
        npc: NPC,
        personality: NPCPersonality,
        action: str,  # "使用追风膏"
        game_output: str,  # "移速提升九成"
        dialogue_history: List[NPCDialogueHistory],
        favorability: int,
        context: dict = None
    ) -> str:
        """
        生成NPC执行游戏指令后的角色扮演回复

        流程:
        1. 构建prompt = system_prompt + action_context + history_summary
        2. 调用LLM生成回复
        3. 验证回复质量（长度、语言、一致性）
        4. 返回回复文本
        """

    async def generate_dialogue(
        self,
        npc: NPC,
        personality: NPCPersonality,
        question: str,  # "你有追风膏吗？"
        dialogue_history: List[NPCDialogueHistory],
        favorability: int,
        context: dict = None
    ) -> str:
        """
        生成NPC对自然对话的回复

        流程:
        1. 检查缓存（相同问题是否有历史回复）
        2. 构建prompt含对话历史（最多5条）
        3. 调用LLM
        4. 缓存结果
        5. 返回回复
        """

    async def generate_autonomous_action(
        self,
        npc: NPC,
        personality: NPCPersonality,
        context: dict  # 包含NPC状态、位置、物品等
    ) -> Optional[str]:
        """
        生成NPC自主决策的行动描述

        触发时机: 定时任务（如每60分钟）
        用途: 让NPC主动执行某些操作（如打工、修炼）

        返回示例: "武安勇开始在茶馆打工"
        """
```

### 8.2 LLM调用配置

```python
# plugins/xiuxian_game/dialogue/ai_config.py

class AIDialogueConfig:
    """AI对话配置"""

    # LLM服务商
    LLM_PROVIDER = "claude"  # "claude" | "openai" | "local"

    # Claude API
    CLAUDE_API_KEY = env("CLAUDE_API_KEY")
    CLAUDE_MODEL = "claude-3-5-sonnet-20241022"
    CLAUDE_MAX_TOKENS = 300

    # 缓存策略
    DIALOGUE_CACHE_TTL = 3600  # 对话缓存有效期(秒)
    MAX_DIALOGUE_HISTORY = 5    # AI考虑的最大历史条数

    # 成本控制
    DAILY_AI_BUDGET_USD = 10.0  # 每日AI调用预算
    MAX_TOKENS_PER_DIALOGUE = 300  # 单次对话最多消耗token数

    # 质量控制
    MIN_RESPONSE_LENGTH = 10  # 最小回复长度
    MAX_RESPONSE_LENGTH = 200  # 最大回复长度
    RESPONSE_VALIDATION = True  # 是否验证回复质量
```

## 9. 游戏指令执行引擎

### 9.1 GameCommandExecutor核心设计

```python
class GameCommandExecutor:
    """
    执行游戏指令的引擎

    职责:
    1. 解析指令类型 (use_item, follow, forge, market_sell, part_time_job)
    2. 验证NPC权限 (NPC是否能执行此指令)
    3. 调用相应Service完成业务逻辑
    4. 返回执行结果描述
    """

    def __init__(
        self,
        item_service: ItemService,
        market_service: MarketService,
        forge_service: ForgeService,
        job_service: JobService,
        # ... other services
    ):
        """依赖注入Service实例"""

    async def execute_command(
        self,
        npc: NPC,
        virtual_player: Player,
        parsed_cmd: ParsedDialogueCommand,
        session: AsyncSession
    ) -> CommandExecutionResult:
        """
        执行解析后的游戏指令

        返回:
        CommandExecutionResult(
            status="success" | "failed" | "partial",
            game_output="移速提升九成",  # 游戏执行结果
            error_message=None,  # 失败原因
            items_changed=[],  # 物品变化
            attributes_changed={},  # 属性变化
        )
        """

    async def validate_npc_permission(
        self,
        npc: NPC,
        command_type: str
    ) -> bool:
        """
        验证NPC是否有权执行某种指令

        规则:
        - 使用物品: NPC背包有该物品
        - 跟随: NPC没有其他主人
        - 锻造: NPC是工匠类型，有锻造功能
        - 挂牌: NPC是商人类型
        - 打工: NPC是雇主类型
        """
```

### 9.2 支持的指令类型

| 指令 | 格式 | 调用Service | 示例 |
|-----|------|-----------|------|
| use_item | 执行使用[物品名] | ItemService.use_item() | 执行使用追风膏 |
| follow | 跟随[玩家名] | FollowService.start_follow() | 跟随我 |
| forge | 执行锻造[装备配置] | ForgeService.forge_equipment() | 执行锻造精铁剑 |
| market_sell | 执行挂牌[物品][价格] | MarketService.sell_item() | 执行挂牌精铁剑3000 |
| part_time_job | 执行打工[职位类型] | JobService.start_job() | 执行打工茶馆伙计 |
| learn_skill | 执行学习[技能名] | SkillService.learn_skill() | 执行学习剑法 |
| cultivate | 执行修炼[时长] | CultivateService.cultivate() | 执行修炼60分钟 |
| attack | 执行攻击[目标NPC] | BattleService.start_battle() | 执行攻击山贼王 |

## 10. 好感度系统设计

### 10.1 FavorabilityRecord管理

```python
class NPCFavorabilityService:
    """好感度管理服务"""

    async def add_interaction(
        self,
        npc_id: int,
        player_id: str,
        interaction_type: str,  # "command_execution" | "dialogue" | "gift" | "combat"
        favorability_delta: int,  # 变化值，可为负
        event_description: str = None
    ) -> NPCFavorability:
        """
        记录一次互动并更新好感度

        好感度变化规则:
        - 游戏指令执行成功: +5 ~ +15（取决于指令类型）
        - 自然对话: +1 ~ +3
        - 赠送物品: +10 ~ +30（取决于物品价值）
        - 战斗胜利（与NPC队友）: +5
        - 战斗失败（NPC被击杀）: -50
        - 拒绝NPC请求: -10
        """

    async def get_favorability(
        self,
        npc_id: int,
        player_id: str
    ) -> NPCFavorability:
        """获取当前好感度数据"""

    async def unlock_relationship_level(
        self,
        npc_id: int,
        player_id: str
    ) -> str:
        """
        根据好感度更新关系等级

        等级划分:
        - 0-20: 陌生人 (NPC冷淡)
        - 21-40: 熟识 (NPC友好)
        - 41-60: 友好 (NPC积极合作)
        - 61-80: 亲密 (NPC优先帮助)
        - 81-100: 知心 (NPC无条件跟随)
        """

    def get_favorability_attitude(self, favorability: int) -> str:
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
```

## 11. 实施步骤

### Phase 1: 数据模型与基础设施 (Week 1-2)
- [ ] 新增 NPC 表字段：virtual_player_id, personality_config 等
- [ ] 创建 NPCDialogueHistory 数据模型
- [ ] 创建 NPCFavorability 数据模型
- [ ] 编写 Alembic 迁移脚本

**文件清单**:
- `models/npc_dialogue_history.py` (新建)
- `models/npc_favorability.py` (新建)
- `models/npc.py` (修改)
- `alembic/versions/add_dialogue_npc_fields.py` (新建)

### Phase 2: 指令解析与虚拟Player (Week 2-3)
- [ ] 实现 DialogueCommandParser
- [ ] 实现 VirtualPlayerManager
- [ ] 实现 platform_utils 虚拟Player检查
- [ ] 编写单元测试

**文件清单**:
- `dialogue/command_parser.py` (新建)
- `dialogue/npc_virtual_player.py` (新建)
- `platform_utils.py` (修改)
- `tests/test_dialogue_command_parser.py` (新建)

### Phase 3: 人设配置与AI对话 (Week 3-4)
- [ ] 定义 PersonalityTemplate 数据结构
- [ ] 设计 AI 系统提示词模板
- [ ] 实现 AIDialogueService (集成 Claude API)
- [ ] 创建预设人设配置 (YAML/JSON)

**文件清单**:
- `dialogue/npc_personality.py` (新建)
- `dialogue/ai_dialogue_service.py` (新建)
- `dialogue/ai_config.py` (新建)
- `data/npc_personalities.json` (新建)

### Phase 4: 指令执行与好感度 (Week 4-5)
- [ ] 实现 GameCommandExecutor
- [ ] 实现 NPCFavorabilityService
- [ ] 集成现有 Service (ItemService, MarketService 等)
- [ ] 编写集成测试

**文件清单**:
- `dialogue/game_command_executor.py` (新建)
- `dialogue/npc_favorability_service.py` (新建)
- `infrastructure/repositories/npc_dialogue_history_repository.py` (新建)
- `infrastructure/repositories/npc_favorability_repository.py` (新建)

### Phase 5: 命令集成与对话流程 (Week 5-6)
- [ ] 实现 dialogue_commands.py 完整流程
- [ ] 集成所有子系统
- [ ] 端到端测试
- [ ] 性能优化与缓存

**文件清单**:
- `dialogue/dialogue_commands.py` (新建)
- `tests/test_dialogue_e2e.py` (新建)

### Phase 6: NPC自主决策 (Week 6-7) [可选]
- [ ] 实现定时任务触发
- [ ] 实现 autonomous action 生成
- [ ] 编写后台任务调度

**文件清单**:
- `dialogue/autonomous_action_scheduler.py` (新建)

## 12. 代码改动清单

### 新增文件 (11个)

| 文件路径 | 用途 |
|---------|------|
| `dialogue/command_parser.py` | 指令解析核心 |
| `dialogue/npc_personality.py` | NPC人设配置 |
| `dialogue/ai_dialogue_service.py` | AI对话生成 |
| `dialogue/ai_config.py` | AI配置管理 |
| `dialogue/npc_virtual_player.py` | 虚拟Player管理 |
| `dialogue/game_command_executor.py` | 指令执行引擎 |
| `dialogue/npc_favorability_service.py` | 好感度管理 |
| `dialogue/dialogue_commands.py` | 命令入口 |
| `dialogue/__init__.py` | 模块初始化 |
| `models/npc_dialogue_history.py` | 对话历史模型 |
| `models/npc_favorability.py` | 好感度关系模型 |

### 修改文件 (5个)

| 文件路径 | 改动 |
|---------|------|
| `models/npc.py` | 新增4个字段 + 虚拟Player关系 |
| `platform_utils.py` | 新增虚拟Player识别函数 |
| `world/npc_interaction.py` | 新增对话命令支持 |
| `infrastructure/repositories/npc_repository.py` | 新增查询方法 |
| `__init__.py` (插件入口) | 注册对话命令处理器 |

### 新增Repository (2个)

| 文件路径 | 用途 |
|---------|------|
| `infrastructure/repositories/npc_dialogue_history_repository.py` | 对话历史CRUD |
| `infrastructure/repositories/npc_favorability_repository.py` | 好感度关系CRUD |

### 数据库迁移

```python
# alembic/versions/001_add_dialogue_npc_system.py

def upgrade():
    """迁移脚本"""
    # 1. NPC表新增字段
    op.add_column('npc', Column('virtual_player_id', String(32), ForeignKey('player.id')))
    op.add_column('npc', Column('personality_template', String(50)))
    op.add_column('npc', Column('personality_config', JSON))
    op.add_column('npc', Column('ai_dialogue_enabled', Boolean, default=True))
    op.add_column('npc', Column('ai_model_id', String(50)))
    op.add_column('npc', Column('ai_context_tokens', Integer, default=2000))
    op.add_column('npc', Column('base_favorability', Integer, default=50))
    op.add_column('npc', Column('dialogue_count', Integer, default=0))
    op.add_column('npc', Column('last_dialogue_at', DateTime))
    op.add_column('npc', Column('autonomous_action_enabled', Boolean, default=False))
    op.add_column('npc', Column('autonomous_action_interval_minutes', Integer, default=60))

    # 2. 创建对话历史表
    op.create_table('npc_dialogue_history', ...)

    # 3. 创建好感度表
    op.create_table('npc_favorability', ...)

    # 4. 创建索引
    op.create_index('idx_npc_virtual_player_id', 'npc', ['virtual_player_id'])
    op.create_index('idx_dialogue_history_npc_player', 'npc_dialogue_history', ['npc_id', 'player_id'])
```

## 13. 集成与适配

### 13.1 与现有Service集成

所有游戏指令执行依赖现有Service：

```python
# dialogue/game_command_executor.py

class GameCommandExecutor:
    def __init__(
        self,
        session: AsyncSession,
        # 现有Service的Repository
        item_repo: ItemRepository,
        inventory_repo: InventoryRepository,
        market_repo: MarketRepository,
        job_repo: JobRepository,
        guild_repo: GuildRepository,
        # ...
    ):
        """通过Repository注入现有Service的数据访问层"""
        self.item_repo = item_repo
        # ...

    async def execute_use_item(self, npc: NPC, item_name: str, qty: int):
        """执行使用物品指令"""
        # 1. 查询虚拟Player背包
        inventory = await self.inventory_repo.get_by_player_id(npc.virtual_player_id)

        # 2. 调用现有的ItemService逻辑
        # 核心逻辑迁移到此处或创建Facade

        # 3. 返回游戏输出
```

### 13.2 与事件系统集成

在关键事件发布对话事件：

```python
# dialogue/dialogue_commands.py

# 监听事件
from domain.events import event_bus, PlayerLevelUpEvent

@event_bus.subscribe_func(PlayerLevelUpEvent)
async def on_player_level_up(event: PlayerLevelUpEvent):
    """玩家升级时，NPC伙伴主动评论"""
    # 如果玩家有跟随NPC，调用AI生成祝贺词
```

## 14. 成本估算与风险评估

### 14.1 成本估算

| 项目 | 成本 | 备注 |
|-----|------|------|
| 开发工时 | 30-40小时 | Phase 1-5 |
| AI API成本 | $0.50-$2/天 | 300条对话/天，avg 150 tokens/对话 |
| 数据库存储 | <10MB | 对话历史、好感度 |
| 缓存成本 | 低 | Redis缓存对话回复 |
| 测试工时 | 10-15小时 | 单元测试、集成测试 |

### 14.2 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|-----|------|------|------|
| LLM API成本超支 | 中 | 高 | 实施token限制、缓存策略、每日预算 |
| NPC虚拟Player数据不一致 | 低 | 高 | 实施同步验证、事务管理、定期检查 |
| AI生成内容质量不稳定 | 中 | 中 | 实施内容验证、人工审核、提示词优化 |
| 指令执行冲突 | 低 | 中 | 实施权限检查、冲突检测、日志记录 |
| 性能退化 | 中 | 中 | 实施缓存、异步处理、查询优化 |

### 14.3 降低风险的策略

1. **Token限制**: 单次对话最多300 tokens，缓存相同问题回复
2. **异步处理**: AI对话异步调用，不阻塞玩家操作
3. **逐步上线**: Feature Flag控制，先小范围测试
4. **监控告警**: 记录AI API成本、错误率、响应时间
5. **降级方案**: AI服务不可用时，使用模板回复

---

**相关文档**:
- `/architecture/current-architecture.md` - 当前架构详情
- `/architecture/service-di-architecture.md` - Service DI模式
- `/architecture/event-system-architecture.md` - 事件系统
- `/reference/data-models.md` - 数据模型参考
- `/guides/how-to-add-effect.md` - 添加新效果参考
