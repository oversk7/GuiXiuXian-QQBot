# 对话NPC系统API参考

本文档提供对话NPC系统的核心API接口和数据结构参考。

## 1. 核心数据结构

### 1.1 ParsedDialogueCommand (指令解析结果)

```python
@dataclass
class ParsedDialogueCommand:
    """解析后的对话指令"""

    npc_name: str
    """NPC名称，如"武安勇" """

    player_input: str
    """玩家原始输入，如"执行使用追风膏" """

    dialogue_type: str
    """对话类型: "game_command" | "natural_dialogue" """

    game_command_type: Optional[str] = None
    """游戏指令类型，如"use_item", "follow", "forge"
    仅当dialogue_type="game_command"时有值 """

    game_command_args: dict = field(default_factory=dict)
    """指令参数，如{"item_id": "追风膏", "qty": 1} """

    question: Optional[str] = None
    """自然对话问题，如"你有追风膏吗？"
    仅当dialogue_type="natural_dialogue"时有值 """

    intent: Optional[str] = None
    """对话意图: "query", "request", "chat", "complain"
    仅当dialogue_type="natural_dialogue"时有值 """

    confidence: float = 1.0
    """指令类型识别的置信度(0.0-1.0)"""

    source: str = "keyword"
    """识别源: "keyword" | "ai" """
```

### 1.2 CommandExecutionResult (指令执行结果)

```python
@dataclass
class CommandExecutionResult:
    """游戏指令执行结果"""

    status: str
    """执行状态: "success" | "failed" | "partial" """

    game_output: str
    """游戏执行结果输出，如"移速提升九成！！！" """

    error_message: Optional[str] = None
    """失败原因，如"NPC背包里没有该物品" """

    items_changed: list = field(default_factory=list)
    """物品变化列表，如[{"item_id": "追风膏", "delta": -1}] """

    attributes_changed: dict = field(default_factory=dict)
    """属性变化，如{"agility": {"before": 10, "after": 19}} """

    metadata: dict = field(default_factory=dict)
    """其他元数据，如{"execution_time_ms": 150} """
```

### 1.3 NPCPersonality (NPC人设)

```python
@dataclass
class NPCPersonality:
    """NPC人设配置"""

    name: str
    """NPC名称"""

    role: str
    """角色定位，如"镇上的大块头" """

    pronouns: list[str]
    """使用的自称，如["俺", "本大爷"] """

    speech_patterns: list[str]
    """说话特点，如["粗犷", "直爽", "豪迈"] """

    key_words: list[str]
    """常用词汇，如["嘿呀", "果然", "怎么了"] """

    personality_traits: dict[str, int]
    """性格数值，如{"loyalty": 80, "cheerfulness": 70} """

    background: str
    """背景故事"""

    relationships: dict[str, str]
    """人物关系，如{"魔神": "恩人"} """

    system_prompt: str
    """发送给LLM的系统提示词"""

    behavioral_rules: list[str]
    """行为准则，如["不会背叛跟随者"] """

    preferred_actions: list[str]
    """偏好的行动，如["切磋", "饮酒"] """
```

### 1.4 NPCVirtualPlayer (虚拟Player同步)

```python
@dataclass
class NPCVirtualPlayerSnapshot:
    """NPC虚拟Player的快照"""

    npc_id: int
    """关联的NPC ID"""

    virtual_player_id: str
    """虚拟Player ID，格式"npc_{npc_id}" """

    inventory_count: int
    """背包物品总数"""

    inventory_snapshot: dict
    """背包快照，如{"追风膏": {"qty": 38, "updated_at": "2025-12-01"}} """

    attributes: dict
    """属性快照"""

    last_sync_at: datetime
    """最后同步时间"""
```

## 2. Service接口

### 2.1 DialogueCommandParser

**位置**: `plugins/xiuxian_game/dialogue/command_parser.py`

```python
class DialogueCommandParser:
    """指令解析器"""

    async def parse_user_input(
        self,
        text: str,
        npc_name: Optional[str] = None
    ) -> ParsedDialogueCommand:
        """
        解析用户输入

        Args:
            text: 用户输入文本，如"执行使用追风膏"
            npc_name: NPC名称（可选，用于上下文）

        Returns:
            ParsedDialogueCommand对象

        Examples:
            >>> parser = DialogueCommandParser()
            >>> result = await parser.parse_user_input("执行使用追风膏")
            >>> result.dialogue_type
            'game_command'
            >>> result.game_command_type
            'use_item'
        """
```

### 2.2 VirtualPlayerManager

**位置**: `plugins/xiuxian_game/dialogue/npc_virtual_player.py`

```python
class VirtualPlayerManager:
    """虚拟Player管理器"""

    async def create_virtual_player(
        self,
        npc: NPC,
        player_repo: PlayerRepository,
        session: AsyncSession
    ) -> Player:
        """
        为NPC创建虚拟Player账号

        Args:
            npc: NPC对象
            player_repo: Player仓储
            session: 数据库会话

        Returns:
            创建的Player对象

        Raises:
            IntegrityError: NPC已有虚拟账号

        Examples:
            >>> manager = VirtualPlayerManager()
            >>> virtual_player = await manager.create_virtual_player(npc, repo, session)
            >>> virtual_player.id
            'npc_123'
        """

    async def sync_virtual_player_attributes(
        self,
        npc: NPC,
        session: AsyncSession
    ) -> None:
        """
        同步虚拟Player属性与NPC属性

        确保虚拟Player的基础属性与NPC同步。
        在装备穿戴、Buff生效时调用。

        Args:
            npc: NPC对象
            session: 数据库会话

        Examples:
            >>> await manager.sync_virtual_player_attributes(npc, session)
        """

    async def get_virtual_player_inventory(
        self,
        npc: NPC,
        session: AsyncSession
    ) -> List[ItemInstance]:
        """
        获取虚拟Player的背包物品

        Args:
            npc: NPC对象
            session: 数据库会话

        Returns:
            物品实例列表
        """

    async def add_item_to_npc(
        self,
        npc: NPC,
        item_id: str,
        quantity: int,
        session: AsyncSession
    ) -> ItemInstance:
        """
        为NPC添加物品（如玩家赠送）

        Args:
            npc: NPC对象
            item_id: 物品ID
            quantity: 数量
            session: 数据库会话

        Returns:
            物品实例

        Examples:
            >>> await manager.add_item_to_npc(npc, "追风膏", 38, session)
        """

    async def remove_item_from_npc(
        self,
        npc: NPC,
        item_id: str,
        quantity: int,
        session: AsyncSession
    ) -> bool:
        """
        从NPC背包移除物品（NPC使用）

        Args:
            npc: NPC对象
            item_id: 物品ID
            quantity: 数量
            session: 数据库会话

        Returns:
            True if successful, False if insufficient items

        Examples:
            >>> success = await manager.remove_item_from_npc(npc, "追风膏", 1, session)
        """
```

### 2.3 AIDialogueService

**位置**: `plugins/xiuxian_game/dialogue/ai_dialogue_service.py`

```python
class AIDialogueService:
    """AI对话生成服务"""

    async def generate_roleplay_response(
        self,
        npc: NPC,
        personality: NPCPersonality,
        action: str,
        game_output: str,
        dialogue_history: List[NPCDialogueHistory],
        favorability: int,
        context: Optional[dict] = None
    ) -> str:
        """
        生成NPC执行游戏指令后的角色扮演回复

        Args:
            npc: NPC对象
            personality: NPC人设
            action: 执行的动作，如"使用追风膏"
            game_output: 游戏执行结果，如"移速提升九成"
            dialogue_history: 对话历史记录
            favorability: 当前好感度(0-100)
            context: 附加上下文信息

        Returns:
            生成的NPC回复文本

        Examples:
            >>> response = await ai_service.generate_roleplay_response(
            ...     npc=npc,
            ...     personality=personality,
            ...     action="使用追风膏",
            ...     game_output="移速提升九成",
            ...     dialogue_history=[],
            ...     favorability=100
            ... )
            >>> print(response)
            '嘿呀，这追风膏果真是好东西，涂了之后俺感觉脚下像生了风一样，速度快了不少！'
        """

    async def generate_dialogue(
        self,
        npc: NPC,
        personality: NPCPersonality,
        question: str,
        dialogue_history: List[NPCDialogueHistory],
        favorability: int,
        context: Optional[dict] = None
    ) -> str:
        """
        生成NPC对自然对话的回复

        Args:
            npc: NPC对象
            personality: NPC人设
            question: 玩家提问，如"你有追风膏吗？"
            dialogue_history: 对话历史
            favorability: 当前好感度
            context: 附加上下文

        Returns:
            生成的NPC回复

        Examples:
            >>> response = await ai_service.generate_dialogue(
            ...     npc=npc,
            ...     personality=personality,
            ...     question="你有追风膏吗？",
            ...     dialogue_history=[],
            ...     favorability=50
            ... )
            >>> print(response)
            '俺这没有追风膏啊，怎么了墨涵兄弟，你是急需这玩意儿不成？'
        """

    async def generate_autonomous_action(
        self,
        npc: NPC,
        personality: NPCPersonality,
        context: dict
    ) -> Optional[str]:
        """
        生成NPC自主决策的行动描述

        触发时机：定时任务（每小时），用于让NPC主动执行操作。

        Args:
            npc: NPC对象
            personality: NPC人设
            context: 上下文，包含NPC状态、物品、时间等

        Returns:
            行动描述，如"武安勇开始在茶馆打工"，或None表示无行动

        Examples:
            >>> action = await ai_service.generate_autonomous_action(
            ...     npc=npc,
            ...     personality=personality,
            ...     context={"time": "22:00", "location": "茶馆"}
            ... )
        """
```

### 2.4 GameCommandExecutor

**位置**: `plugins/xiuxian_game/dialogue/game_command_executor.py`

```python
class GameCommandExecutor:
    """游戏指令执行引擎"""

    async def execute_command(
        self,
        npc: NPC,
        virtual_player: Player,
        parsed_cmd: ParsedDialogueCommand,
        session: AsyncSession
    ) -> CommandExecutionResult:
        """
        执行解析后的游戏指令

        Args:
            npc: 执行指令的NPC
            virtual_player: NPC的虚拟Player账号
            parsed_cmd: 解析后的指令
            session: 数据库会话

        Returns:
            CommandExecutionResult对象

        Examples:
            >>> result = await executor.execute_command(
            ...     npc=npc,
            ...     virtual_player=virtual_player,
            ...     parsed_cmd=parsed_cmd,
            ...     session=session
            ... )
            >>> result.status
            'success'
            >>> result.game_output
            '移速提升九成！！！'
        """

    async def validate_npc_permission(
        self,
        npc: NPC,
        command_type: str
    ) -> bool:
        """
        验证NPC是否有权执行某种指令

        规则:
        - use_item: NPC背包有该物品
        - follow: NPC没有其他主人，可用
        - forge: NPC类型=craftsman，函数启用锻造
        - market_sell: NPC类型=merchant，函数启用市场
        - part_time_job: NPC类型=employer，函数启用打工

        Args:
            npc: NPC对象
            command_type: 指令类型

        Returns:
            True if NPC has permission, False otherwise
        """
```

### 2.5 NPCFavorabilityService

**位置**: `plugins/xiuxian_game/dialogue/npc_favorability_service.py`

```python
class NPCFavorabilityService:
    """好感度管理服务"""

    async def add_interaction(
        self,
        npc_id: int,
        player_id: str,
        interaction_type: str,
        favorability_delta: int,
        event_description: Optional[str] = None,
        session: AsyncSession = None
    ) -> NPCFavorability:
        """
        记录一次互动并更新好感度

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            interaction_type: 互动类型
                - "command_execution": 指令执行
                - "dialogue": 自然对话
                - "gift": 赠送物品
                - "combat": 战斗
            favorability_delta: 好感度变化(可为负)
            event_description: 事件描述
            session: 数据库会话

        Returns:
            更新后的NPCFavorability对象

        好感度变化规则:
        - 游戏指令执行成功: +5 ~ +15
        - 自然对话: +1 ~ +3
        - 赠送物品: +10 ~ +30（取决于物品价值）
        - 战斗胜利（与NPC队友）: +5
        - 战斗失败（NPC被击杀）: -50
        - 拒绝NPC请求: -10

        Examples:
            >>> fav = await fav_service.add_interaction(
            ...     npc_id=123,
            ...     player_id="qq_12345",
            ...     interaction_type="command_execution",
            ...     favorability_delta=10,
            ...     event_description="执行使用追风膏"
            ... )
            >>> fav.current_favorability
            60
        """

    async def get_favorability(
        self,
        npc_id: int,
        player_id: str,
        session: AsyncSession = None
    ) -> Optional[NPCFavorability]:
        """
        获取玩家与NPC的好感度数据

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            session: 数据库会话

        Returns:
            NPCFavorability对象，若无则返回None
        """

    async def unlock_relationship_level(
        self,
        npc_id: int,
        player_id: str,
        session: AsyncSession = None
    ) -> str:
        """
        根据好感度更新关系等级

        等级划分:
        - 0-20: 陌生人（NPC冷淡，-50%指令奖励）
        - 21-40: 熟识（NPC友好，正常奖励）
        - 41-60: 友好（NPC积极，+20%奖励）
        - 61-80: 亲密（NPC优先帮助，+50%奖励）
        - 81-100: 知心（NPC无条件跟随，+100%奖励）

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            session: 数据库会话

        Returns:
            新的关系等级名称
        """

    def get_favorability_attitude(self, favorability: int) -> str:
        """
        根据好感度返回对应的态度描述

        Args:
            favorability: 好感度值(0-100)

        Returns:
            态度描述文本

        Examples:
            >>> attitude = service.get_favorability_attitude(50)
            >>> attitude
            '冷淡、敷衍'
            >>> attitude = service.get_favorability_attitude(90)
            >>> attitude
            '忠诚、无条件'
        """
```

## 3. 数据模型

### 3.1 NPC (扩展字段)

```python
class NPC(Base):
    # 虚拟账号相关
    virtual_player_id: str | None  # "npc_123"
    virtual_player: Player  # 关系映射

    # 人设相关
    personality_template: str  # "default", "武安勇"
    personality_config: dict  # JSON配置
    ai_dialogue_enabled: bool  # True/False
    ai_model_id: str | None  # "claude-3-5-sonnet-20241022"
    ai_context_tokens: int  # 2000

    # 统计相关
    base_favorability: int  # 50
    dialogue_count: int  # 累计对话次数
    last_dialogue_at: datetime | None  # 最后对话时间

    # 自主决策相关
    autonomous_action_enabled: bool  # False
    autonomous_action_interval_minutes: int  # 60
```

### 3.2 NPCDialogueHistory

```python
class NPCDialogueHistory(Base):
    __tablename__ = "npc_dialogue_history"

    npc_id: int  # 外键
    player_id: str  # 外键

    dialogue_type: str  # "game_command" | "natural_dialogue"
    player_input: str  # 玩家输入
    npc_response: str  # NPC回复

    game_command: str | None  # 指令内容
    game_output: str | None  # 游戏输出
    game_command_status: str  # "success" | "failed" | "partial"

    favorability_change: int  # 好感度变化
    favorability_after: int  # 对话后总好感度

    dialogue_duration_seconds: int  # 耗时
    ai_tokens_used: int | None  # AI token数
    ai_cost: float | None  # AI成本USD

    created_at: datetime  # 创建时间
```

### 3.3 NPCFavorability

```python
class NPCFavorability(Base):
    __tablename__ = "npc_favorability"

    npc_id: int  # 外键
    player_id: str  # 外键

    current_favorability: int  # 当前好感度(0-100)
    total_interactions: int  # 累计互动次数
    total_favorability_gained: int  # 累计好感度获得

    relationship_level: str  # "陌生人"|"熟识"|"友好"|"亲密"|"知心"
    is_follower: bool  # 是否跟随中
    is_partner: bool  # 是否伴侣关系

    first_interaction_at: datetime
    last_interaction_at: datetime
    milestone_events: dict  # {"100好感度解锁": "2025-12-01"}

    updated_at: datetime
```

## 4. 支持的游戏指令

| 指令类型 | 调用条件 | 好感度奖励 | 示例 |
|---------|---------|----------|------|
| use_item | NPC有物品 | +10 | 执行使用追风膏 |
| follow | NPC可用 | +5 | 跟随我 |
| forge | NPC=工匠 | +15 | 执行锻造精铁剑 |
| market_sell | NPC=商人 | +10 | 执行挂牌精铁剑3000 |
| part_time_job | NPC=雇主 | +12 | 执行打工茶馆伙计 |
| learn_skill | NPC有技能 | +8 | 执行学习剑法 |
| cultivate | 任何NPC | +6 | 执行修炼60分钟 |
| attack | NPC可战斗 | +20 | 执行攻击山贼王 |

## 5. 缓存策略

### 5.1 对话回复缓存

```python
# 缓存键: f"dialogue_{npc_id}_{question_hash}"
# 过期时间: 3600秒（1小时）
# 目的: 避免重复调用AI服务

# 示例
cache_key = f"dialogue_{npc.id}_{hash('你有追风膏吗？')}"
cached_response = await redis_client.get(cache_key)
```

### 5.2 NPC人设缓存

```python
# 缓存键: f"personality_{npc_id}"
# 过期时间: 86400秒（1天）
# 目的: 加速人设加载

personality = await redis_client.get(f"personality_{npc.id}")
```

## 6. 错误处理

### 常见异常

```python
class DialogueNPCException(Exception):
    """对话NPC系统基础异常"""

class NPCNotFoundError(DialogueNPCException):
    """NPC不存在"""

class VirtualPlayerCreationError(DialogueNPCException):
    """虚拟Player创建失败"""

class CommandExecutionError(DialogueNPCException):
    """指令执行失败"""

class InsufficientPermissionError(DialogueNPCException):
    """NPC权限不足"""

class AIServiceError(DialogueNPCException):
    """AI服务错误"""
```

### 错误恢复策略

```python
# 降级方案：AI服务不可用
if ai_service_unavailable:
    # 使用模板回复
    response = TEMPLATE_RESPONSES.get(
        command_type,
        "我暂时无法回应，请稍后再试"
    )
```

---

**相关文档**:
- `/llmdoc/architecture/dialogue-npc-system.md` - 系统架构设计
- `/llmdoc/guides/how-to-implement-dialogue-npc.md` - 实施指南
- `/llmdoc/reference/data-models.md` - 数据模型参考
