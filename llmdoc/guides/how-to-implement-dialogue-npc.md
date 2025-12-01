# 如何实施对话NPC系统

本指南基于 `/llmdoc/architecture/dialogue-npc-system.md` 的架构设计，提供分阶段的实施步骤。

## 前置条件检查

1. 确认已部署 Service DI 架构（查看 `/guides/deploy-service-di.md`）
2. 确认 NPC 模型已初始化（`models/npc.py` 存在）
3. 确认数据库连接正常（`models/db.py` 可用）
4. 准备 Claude API 密钥（用于AI对话）

## Phase 1: 数据库迁移与模型扩展 (2天)

### Step 1: 备份当前数据库

```bash
# 使用项目的备份工具或MySQL命令
mysqldump -u root -p xiuxian_game > backup_$(date +%Y%m%d).sql
```

### Step 2: 创建 Alembic 迁移脚本

编辑 `alembic/versions/001_add_dialogue_npc_system.py`：

```python
"""Add dialogue NPC system fields

Revision ID: 001_dialogue_npc
Revises: [前一个版本号]
Create Date: 2025-12-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# ... 迁移脚本内容（参考 /llmdoc/architecture/dialogue-npc-system.md 第12.3章）
```

### Step 3: 执行迁移

```bash
cd plugins/xiuxian_game
alembic upgrade head
```

### Step 4: 验证迁移成功

在数据库中检查新表：
```sql
DESCRIBE npc;  -- 验证新增字段
DESCRIBE npc_dialogue_history;  -- 验证新表
DESCRIBE npc_favorability;  -- 验证新表
```

## Phase 2: 指令解析与虚拟Player (3天)

### Step 5: 实现 DialogueCommandParser

创建 `dialogue/command_parser.py`：

```python
# 关键实现点：
# 1. 使用正则表达式识别关键词
# 2. 调用LLM进行意图判断
# 3. 返回ParsedDialogueCommand对象

from dataclasses import dataclass
from typing import Optional

@dataclass
class ParsedDialogueCommand:
    npc_name: str
    player_input: str
    dialogue_type: str  # "game_command" | "natural_dialogue"
    game_command_type: Optional[str] = None
    question: Optional[str] = None
    confidence: float = 1.0

class DialogueCommandParser:
    async def parse_user_input(self, text: str) -> ParsedDialogueCommand:
        """解析用户输入"""
        # 实现：关键词识别 + AI兜底
        pass
```

参考文件：`/llmdoc/architecture/dialogue-npc-system.md` 第5章

### Step 6: 实现 VirtualPlayerManager

创建 `dialogue/npc_virtual_player.py`：

**核心方法**：
- `create_virtual_player()` - 为NPC创建虚拟账号
- `sync_virtual_player_attributes()` - 同步虚拟Player属性
- `get_virtual_player_inventory()` - 获取NPC背包
- `add_item_to_npc()` - 为NPC添加物品
- `remove_item_from_npc()` - 从NPC背包移除物品

**设计要点**：
- 虚拟Player ID格式：`"npc_{npc_id}"`
- 虚拟Player自动关联到NPC表的 `virtual_player_id` 字段
- 使用事务确保一致性

### Step 7: 修改 platform_utils.py

添加虚拟Player识别函数：

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
        npc_repo = NPCRepository(session)
        return await npc_repo.get_by_virtual_player_id(player_id)
    return None
```

### Step 8: 编写单元测试

创建 `tests/test_virtual_player_manager.py`：

```bash
# 测试覆盖：
# - 虚拟Player创建
# - 虚拟Player属性同步
# - 物品添加/移除
# - 虚拟Player识别
```

运行测试：
```bash
pytest tests/test_virtual_player_manager.py -v
```

## Phase 3: NPC人设与AI对话 (3天)

### Step 9: 定义 PersonalityTemplate

创建 `dialogue/npc_personality.py`：

```python
from dataclasses import dataclass, field

@dataclass
class PersonalityTemplate:
    """NPC人设模板"""
    name: str
    role: str
    pronouns: list[str]
    speech_patterns: list[str]
    key_words: list[str]
    personality_traits: dict[str, int] = field(default_factory=dict)
    background: str = ""
    relationships: dict[str, str] = field(default_factory=dict)
    system_prompt: str = ""
    behavioral_rules: list[str] = field(default_factory=list)
```

### Step 10: 创建预设人设配置

创建 `data/npc_personalities.json`：

```json
{
  "武安勇": {
    "name": "武安勇",
    "role": "镇上的大块头",
    "pronouns": ["俺", "本大爷"],
    "personality": "粗犷、直爽、豪迈",
    "background": "出身贫寒，靠蛮力讨生活...",
    "behavioral_rules": [
      "对给他东西的人很感激",
      "喜欢参加战团切磋",
      "会认真执行跟随者的指令"
    ]
  }
}
```

参考：`/llmdoc/architecture/dialogue-npc-system.md` 第6章

### Step 11: 实现 AIDialogueService

创建 `dialogue/ai_dialogue_service.py`：

**Step 11.1**: 配置AI API

创建 `dialogue/ai_config.py`：
```python
class AIDialogueConfig:
    LLM_PROVIDER = "claude"
    CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
    CLAUDE_MODEL = "claude-3-5-sonnet-20241022"
    CLAUDE_MAX_TOKENS = 300
    DIALOGUE_CACHE_TTL = 3600
```

**Step 11.2**: 实现核心方法

```python
class AIDialogueService:
    async def generate_roleplay_response(
        self,
        npc: NPC,
        personality: NPCPersonality,
        action: str,
        game_output: str,
        dialogue_history: List[NPCDialogueHistory],
        favorability: int,
        context: dict = None
    ) -> str:
        """生成角色扮演回复"""
        # 1. 构建系统提示词
        system_prompt = self._build_system_prompt(npc, personality, favorability)

        # 2. 构建用户消息
        user_message = f"""
        执行的指令: {action}
        游戏输出: {game_output}

        请用{npc.name}的人设回复这个指令的执行结果。
        """

        # 3. 调用Claude API
        response = await self._call_claude(system_prompt, user_message)

        # 4. 验证回复质量
        if self._validate_response(response):
            return response
        else:
            return "（静静地点了点头）"  # 降级方案
```

**Step 11.3**: 处理缓存和成本控制

```python
async def generate_dialogue(self, ...):
    # 检查缓存
    cache_key = f"dialogue_{npc_id}_{question_hash}"
    cached = await redis_client.get(cache_key)
    if cached:
        return cached

    # 调用AI
    response = await self._call_claude(...)

    # 缓存结果
    await redis_client.setex(cache_key, 3600, response)

    return response
```

参考：`/llmdoc/architecture/dialogue-npc-system.md` 第8章

### Step 12: 编写集成测试

创建 `tests/test_ai_dialogue_service.py`：

```bash
# 测试覆盖：
# - 角色扮演回复生成
# - 自然对话生成
# - 缓存功能
# - 成本追踪
```

## Phase 4: 指令执行与好感度 (2天)

### Step 13: 实现 GameCommandExecutor

创建 `dialogue/game_command_executor.py`：

**核心设计**：
```python
class GameCommandExecutor:
    """执行游戏指令的引擎"""

    async def execute_command(
        self,
        npc: NPC,
        virtual_player: Player,
        parsed_cmd: ParsedDialogueCommand,
        session: AsyncSession
    ) -> CommandExecutionResult:
        """执行指令"""
        # 1. 验证权限
        if not await self.validate_npc_permission(npc, parsed_cmd.game_command_type):
            return CommandExecutionResult(status="failed", error_message="NPC无此权限")

        # 2. 根据指令类型分发
        if parsed_cmd.game_command_type == "use_item":
            return await self._execute_use_item(npc, virtual_player, ...)
        elif parsed_cmd.game_command_type == "follow":
            return await self._execute_follow(npc, virtual_player, ...)
        # ... 其他指令类型
```

支持的指令类型：`/llmdoc/architecture/dialogue-npc-system.md` 第9.2章

### Step 14: 实现好感度系统

创建 `dialogue/npc_favorability_service.py`：

```python
class NPCFavorabilityService:
    """好感度管理服务"""

    async def add_interaction(
        self,
        npc_id: int,
        player_id: str,
        interaction_type: str,  # "command_execution" | "dialogue" | "gift"
        favorability_delta: int,
        event_description: str = None
    ) -> NPCFavorability:
        """记录互动并更新好感度"""
        # 1. 获取或创建好感度记录
        fav = await self.fav_repo.get_by_npc_and_player(npc_id, player_id)
        if not fav:
            fav = NPCFavorability(npc_id=npc_id, player_id=player_id)

        # 2. 更新好感度
        fav.current_favorability = min(100, max(0, fav.current_favorability + favorability_delta))
        fav.total_interactions += 1

        # 3. 检查关系等级变化
        await self.unlock_relationship_level(fav)

        # 4. 保存
        return await self.fav_repo.save(fav)

    def get_favorability_attitude(self, favorability: int) -> str:
        """返回对应的态度描述"""
        # 参考表：/llmdoc/architecture/dialogue-npc-system.md 第10.1章
```

好感度变化规则：`/llmdoc/architecture/dialogue-npc-system.md` 第10.1章

### Step 15: 创建Repository

创建以下文件：
- `infrastructure/repositories/npc_dialogue_history_repository.py`
- `infrastructure/repositories/npc_favorability_repository.py`

**基本结构**：
```python
class NPCDialogueHistoryRepository(BaseRepository[NPCDialogueHistory]):
    """对话历史仓储"""

    async def get_recent_interactions(
        self,
        npc_id: int,
        player_id: str,
        limit: int = 5
    ) -> List[NPCDialogueHistory]:
        """获取最近N条互动记录"""
```

## Phase 5: 命令集成与完整流程 (3天)

### Step 16: 实现对话命令处理器

创建 `dialogue/dialogue_commands.py`：

**核心流程**：
```python
dialogue_cmd = on_command("对话", aliases={"交互"}, block=True, priority=5)

@dialogue_cmd.handle()
async def handle_dialogue_command(event: MessageEvent, args: Message = CommandArg()):
    """处理对话命令"""

    # 1. 解析输入
    parsed = await parser.parse_user_input(args.extract_plain_text())

    # 2. 查找NPC
    npc = await npc_service.get_npc_by_name(parsed.npc_name, location_id)

    # 3. 路由分发
    if parsed.dialogue_type == "game_command":
        await handle_game_command(npc, parsed, event)
    else:
        await handle_natural_dialogue(npc, parsed, event)

async def handle_game_command(npc: NPC, parsed: ParsedDialogueCommand, event):
    """执行游戏指令"""
    async with safe_session() as session:
        # 1. 获取或创建虚拟Player
        virtual_player = npc.virtual_player or await vm.create_virtual_player(npc)

        # 2. 执行指令
        result = await executor.execute_command(npc, virtual_player, parsed, session)

        # 3. 生成AI回复
        ai_response = await ai_service.generate_roleplay_response(
            npc, ..., result.game_output
        )

        # 4. 更新好感度
        await fav_service.add_interaction(npc.id, event.user_id, "command_execution", delta=10)

        # 5. 保存对话历史
        await history_repo.save(NPCDialogueHistory(...))

        # 6. 响应用户（双重输出）
        msg = f"{ai_response}\n(当前好感度: {fav.current_favorability})\n{result.game_output}"
        await dialogue_cmd.send(message_add_head(msg, event))
```

参考：`/llmdoc/architecture/dialogue-npc-system.md` 第3.2 和 3.3 章

### Step 17: 集成到插件初始化

编辑 `plugins/xiuxian_game/__init__.py`：

```python
# 在on_startup中注册
@on_startup()
async def init_dialogue_system():
    """初始化对话系统"""
    # 1. 加载预设人设
    await PersonalityManager.load_presets("data/npc_personalities.json")

    # 2. 初始化AI服务
    AIDialogueService.initialize()

    # 3. 注册对话命令处理器
    # 由dialogue_commands.py自动注册
```

### Step 18: 编写端到端测试

创建 `tests/test_dialogue_e2e.py`：

```bash
# 测试场景：
# 1. 玩家输入游戏指令 → NPC执行 → 双重输出 → 好感度更新
# 2. 玩家提出问题 → NPC AI回复 → 好感度更新
# 3. NPC虚拟Player背包同步
# 4. 好感度达到关系等级阈值
```

运行测试：
```bash
pytest tests/test_dialogue_e2e.py -v
```

## Phase 6: 性能优化与监控 (2天)

### Step 19: 实施缓存策略

```python
# dialogue/ai_dialogue_service.py

# 1. 缓存AI对话结果
DIALOGUE_CACHE = {}  # {question_hash: (response, timestamp)}

# 2. 缓存NPC人设
PERSONALITY_CACHE = {}  # {npc_id: PersonalityTemplate}

# 3. 定期清理过期缓存
async def cleanup_cache():
    """清理过期缓存"""
    now = time.time()
    DIALOGUE_CACHE = {
        k: v for k, v in DIALOGUE_CACHE.items()
        if now - v[1] < 3600  # 保留1小时内的缓存
    }
```

### Step 20: 添加监控和日志

```python
# dialogue/dialogue_commands.py

import logging
import time

logger = logging.getLogger("dialogue_npc_system")

@dialogue_cmd.handle()
async def handle_dialogue_command(event: MessageEvent, args: Message = CommandArg()):
    start_time = time.time()

    try:
        # 命令处理逻辑
        pass
    except Exception as e:
        logger.error(f"对话命令错误: {e}", exc_info=True)
        await dialogue_cmd.finish("发生错误，请稍后重试")
    finally:
        duration = time.time() - start_time
        logger.info(f"对话耗时: {duration:.2f}秒, NPC: {npc.name}, 玩家: {event.user_id}")
```

### Step 21: 成本追踪

```python
# dialogue/ai_dialogue_service.py

async def _track_ai_cost(tokens_used: int, model: str):
    """追踪AI调用成本"""
    # Claude Sonnet 3.5: input $3/M, output $15/M
    cost = (tokens_used / 1000000) * 9  # 平均成本

    logger.info(f"AI调用成本: ${cost:.6f}, tokens: {tokens_used}, 模型: {model}")

    # 定时检查每日预算
    daily_budget = config.DAILY_AI_BUDGET_USD
```

## Phase 7: 可选功能 - NPC自主决策 (2天)

### Step 22: 实现自主决策调度器

创建 `dialogue/autonomous_action_scheduler.py`：

```python
# 定时任务：每小时执行一次
@scheduler.scheduled_job('interval', hours=1)
async def npc_autonomous_actions():
    """NPC自主决策"""
    async with safe_session() as session:
        # 1. 获取启用自主决策的NPC
        npcs = await npc_repo.get_autonomous_npcs()

        # 2. 为每个NPC生成行动
        for npc in npcs:
            action = await ai_service.generate_autonomous_action(npc, context={...})

            # 3. 执行行动
            # 如：打工、修炼、移动等
```

## 验证检查清单

- [ ] 数据库迁移成功，新表创建完毕
- [ ] 虚拟Player创建正常，背包同步一致
- [ ] 指令解析准确（关键词+AI混合）
- [ ] AI对话生成有效，语言风格符合人设
- [ ] 好感度系统更新正确，关系等级升级正常
- [ ] 对话历史记录完整
- [ ] 双重输出格式符合预期
- [ ] 无N+1查询问题
- [ ] AI API成本在预期范围内
- [ ] 错误处理完善，有降级方案

## 故障排除

### 问题：AI API调用失败

```python
# 降级方案
if ai_service_unavailable:
    # 使用模板回复替代
    response = TEMPLATE_RESPONSES.get(command_type, "我暂时无法回应")
```

### 问题：虚拟Player背包不同步

```python
# 验证脚本
async def verify_npc_virtual_player_sync(npc_id: int):
    """验证虚拟Player同步一致性"""
    npc = await npc_repo.get_by_id(npc_id)
    virtual_player = npc.virtual_player

    # 检查属性一致性
    assert npc.level == virtual_player.level
    assert npc.attack == virtual_player.attack
```

### 问题：好感度异常跳跃

```python
# 审计日志
async def audit_favorability_changes():
    """审计好感度变化"""
    recent = await fav_history_repo.get_recent_changes(hours=24)
    for change in recent:
        if abs(change.delta) > 50:  # 异常值
            logger.warning(f"异常好感度变化: {change}")
```

---

**参考文档**:
- `/llmdoc/architecture/dialogue-npc-system.md` - 系统架构设计
- `/llmdoc/architecture/service-di-architecture.md` - Service DI集成
- `/llmdoc/guides/deploy-service-di.md` - Service DI部署指南
