# NPC AI对话系统实施记录

## 1. Identity

- **What it is**: 基于智谱AI GLM-4.5-Flash的NPC自然对话系统（方案2核心功能版）
- **Purpose**: 为NPC提供AI驱动的角色扮演对话，支持好感度关系，提升玩家沉浸式体验

## 2. Core Components

### 2.1 数据模型（2个新模型）

- `plugins/xiuxian_game/models/npc_dialogue_history.py` (NPCDialogueHistory): 对话历史表，记录玩家与NPC的所有对话
- `plugins/xiuxian_game/models/npc_favorability.py` (NPCFavorability): 好感度关系表，记录玩家与NPC的好感度和关系等级
- `plugins/xiuxian_game/models/npc.py` (NPC): 添加relationship反向关联（dialogue_histories, favorability_records）

### 2.2 Repository层（2个新Repository）

- `plugins/xiuxian_game/infrastructure/repositories/npc_dialogue_history_repository.py` (NPCDialogueHistoryRepository): 对话历史CRUD和查询
- `plugins/xiuxian_game/infrastructure/repositories/npc_favorability_repository.py` (NPCFavorabilityRepository): 好感度CRUD和查询

### 2.3 Service层（2个新Service）

- `plugins/xiuxian_game/dialogue/ai_dialogue_service.py` (AIDialogueService): AI对话生成服务，集成智谱AI
- `plugins/xiuxian_game/dialogue/npc_favorability_service.py` (NPCFavorabilityService): 好感度管理服务

### 2.4 NPC人设系统

- `plugins/xiuxian_game/dialogue/npc_personality.py` (PersonalityTemplate, PersonalityManager): 人设模板数据类和管理器
- `plugins/xiuxian_game/data/npc_personalities.yaml`: 4个预设NPC人设配置（武安勇、铁匠老王、药铺掌柜、缉邪司教官）

### 2.5 命令集成

- `plugins/xiuxian_game/world/npc_interaction.py` (handle_ai_dialogue_interaction): AI对话处理函数，集成到现有NPC交互系统
- `plugins/xiuxian_game/dialogue/admin_commands.py`: 3个管理员命令（启用/禁用/查看NPC AI）

### 2.6 配置管理

- `plugins/xiuxian_game/data/config.yaml` (ai_dialogue段): AI API密钥、模型配置、成本控制、限流、安全配置

### 2.7 启动逻辑

- `plugins/xiuxian_game/__init__.py`: PersonalityManager自动加载（bot启动时）

### 2.8 长期记忆系统（新增 2025-12-07）

**数据模型**:
- `plugins/xiuxian_game/models/npc_long_term_memory.py` (NPCLongTermMemory): 存储对话总结和关键事件
- `plugins/xiuxian_game/models/npc_long_term_memory.py` (NPCDialogueSummaryCheckpoint): 总结触发检查点

**Repository层**:
- `plugins/xiuxian_game/infrastructure/repositories/npc_long_term_memory_repository.py` (NPCLongTermMemoryRepository): 长期记忆CRUD和查询
  - `create_memory()`: 创建记忆（总结或事件）
  - `get_recent_summaries()`: 获取最近N次总结
  - `get_important_events()`: 获取重要事件（按重要性和权重排序）
  - `decay_old_memories()`: 批量记忆权重衰减
  - `create_or_update_checkpoint()`: 创建或更新总结检查点
  - `get_checkpoint()`: 获取检查点状态

**Service层**:
- `plugins/xiuxian_game/dialogue/dialogue_summarization_service.py` (DialogueSummarizationService): 对话总结服务
  - `should_trigger_summary()`: 判断是否触发总结（20-30轮阈值）
  - `summarize_dialogues()`: 执行总结（调用AI提取总结和事件）
  - `_call_ai_for_summary()`: 调用智谱AI分析对话
  - `get_long_term_context()`: 构建长期记忆上下文（最近3次总结+5个重要事件）

**对话历史Repository增强**:
- `plugins/xiuxian_game/infrastructure/repositories/npc_dialogue_history_repository.py:214-259`
  - `get_dialogue_count()`: 获取对话总数（用于触发判断）
  - `get_dialogues_after_id()`: 获取指定ID之后的对话（用于增量总结）

### 2.9 好感度优化（防刷机制，2025-12-07）

**防刷逻辑**:
- `plugins/xiuxian_game/dialogue/npc_favorability_service.py:268-280`
  - **敷衍检测**: ≤3字符的消息好感度变化为0
  - **阶段性递减**: 好感度<40时中性对话+1，≥40时为0
  - **空消息处理**: 无对话内容时好感度变化为0

**修复YAML格式**:
- `plugins/xiuxian_game/data/npc_personalities.yaml:50` - 修复"药铺掌柜"缺少key的YAML错误

### 2.10 人设扩展（11个NPC，2025-12-07）

**新增人设配置**:
- `plugins/xiuxian_game/data/npc_personalities.yaml:92-247`
  - **商人类（2个）**: 商人李掌柜（精明型，上京市集）、商人王五（朴实型，北郊市集）
  - **工匠类（5个）**:
    - 百工坊宗师（宗师级，上京）
    - 心魔巧匠（怪谈主题，金陵）
    - 幽魂锻师（幽魂主题，云岭）
    - 疯狂技师（疯狂主题，摩配镇）
    - 炼魂大师（终极主题，风雪镇）

**人设覆盖**: 从4个扩展到11个，覆盖6个地点和3个主题分类

## 3. Execution Flow (LLM Retrieval Map)

### 3.1 AI对话触发流程

```
1. 玩家命令: 【交互 武安勇】
   ↓
2. NPC交互路由: world/npc_interaction.py:handle_npc_interaction()
   - 检查NPC类型（如果是normal且ai_enabled=True）
   ↓
3. 调用AI对话处理: world/npc_interaction.py:238 handle_ai_dialogue_interaction()
   ↓
4. 初始化Service:
   - AIDialogueService(从config读取API密钥)
   - NPCFavorabilityService(session)
   ↓
5. 获取或创建好感度记录:
   - NPCFavorabilityService.get_favorability(npc_id, player_id, initial=50)
   ↓
6. 加载NPC人设:
   - PersonalityManager.get_personality(npc.name)
   - 如果不存在，返回default人设
   ↓
7. 加载对话历史:
   - NPCDialogueHistoryRepository.get_recent_interactions(npc_id, player_id, limit=10)
   ↓
8. 生成AI回复:
   - AIDialogueService.generate_dialogue(
       npc, personality, question="你好",
       dialogue_history, favorability
     )
   - 调用智谱AI API（call_zhipu_api）
   - 返回: (npc_response, tokens_used)
   ↓
9. 更新好感度:
   - NPCFavorabilityService.add_interaction(
       npc_id, player_id, "dialogue", favorability_delta=2
     )
   ↓
10. 保存对话历史:
    - NPCDialogueHistory.create(
        dialogue_type="natural_dialogue",
        player_input="你好",
        npc_response="...",
        ai_tokens_used=tokens_used
      )
    ↓
11. 响应玩家:
    msg = f"""👤 {npc.name}
    💬 {npc_response}

    💖 好感度: {favorability.current_favorability}/100
    🔗 关系: {favorability.relationship_level}"""
```

### 3.2 管理员命令流程

```
管理员命令: 【启用NPC AI 武安勇】
   ↓
1. dialogue/admin_commands.py:handle_enable_npc_ai()
   ↓
2. 验证管理员权限: ai_guide.is_admin(user_id)
   ↓
3. 查询NPC: NPCService.get_npc_by_name(npc_name)
   ↓
4. 启用AI对话: NPCService.enable_ai_for_npc(
     npc, model="GLM-4.5-Flash", base_favorability=50
   )
   - 设置 npc.extra_data["ai_enabled"] = True
   - 设置 npc.extra_data["ai_model"] = "GLM-4.5-Flash"
   ↓
5. 响应管理员: "✅ 已为NPC「武安勇」启用AI对话"
```

### 3.3 长期记忆总结流程（新增 2025-12-07）

```
玩家对话完成后（npc_interaction.py:605-633）
   ↓
1. 检查是否应该触发总结:
   - summary_service.should_trigger_summary(npc_id, player_id)
   - 条件: 新对话数 >= 20-30轮
   ↓
2. 如果需要总结，创建异步后台任务:
   - asyncio.create_task(summarize_task())
   - 不阻塞用户交互，立即返回对话结果
   ↓
3. 后台总结任务执行:
   a. 获取检查点: memory_repo.get_checkpoint(npc_id, player_id)
   b. 获取新对话: dialogue_repo.get_dialogues_after_id(last_id)
   c. 调用AI分析:
      - _call_ai_for_summary(dialogues, npc_personality)
      - AI提取总结文本和关键事件列表
   d. 保存总结:
      - memory_repo.create_memory(type="summary", content=总结文本)
   e. 保存关键事件:
      - 遍历事件列表，create_memory(type="event", ...)
   f. 更新检查点:
      - memory_repo.create_or_update_checkpoint(latest_id)
   ↓
4. 下次对话时使用长期记忆:
   - summary_service.get_long_term_context(npc_id, player_id)
   - 获取最近3次总结 + 5个重要事件
   - 注入到AI系统提示词（ai_dialogue_service.py:75-78）
```

**三层记忆架构**:
```
第1层（短期记忆）: 最近10轮原始对话（dialogue_history表）
   ↓
第2层（中期记忆）: 最近3次AI总结（long_term_memory表，type=summary）
   ↓
第3层（长期记忆）: 最近5个重要事件（long_term_memory表，type=event）

好处:
- 减少token消耗（预计5-10%）
- 保留重要信息（不丢失关键事件）
- 记忆权重衰减（老记忆逐渐淡化）
```

## 4. Design Rationale

### 4.1 为什么选择方案2（核心功能版）？

**实施范围**: 仅实现AI对话生成 + 好感度系统 + 长期记忆，不包括虚拟Player和游戏指令执行。

**理由**:
1. **最小可行产品（MVP）**: 6-8天开发周期（Phase 1-2），2天优化周期（Phase 3），快速验证AI对话可行性
2. **技术风险可控**: 避免虚拟Player系统的数据一致性复杂度
3. **成本可控**: 智谱AI GLM-4.5-Flash成本低（约3元/月），适合初期测试
4. **长期记忆优化**: Phase 3新增三层记忆架构，减少token消耗5-10%
5. **未来可扩展**: 预留了虚拟Player和指令执行的接口设计

### 4.2 为什么选择智谱AI GLM-4.5-Flash？

**对比分析**:
| LLM | 成本 | 延迟 | 中文能力 | 选择原因 |
|-----|------|------|---------|---------|
| 智谱AI GLM-4.5-Flash | $0.1/M tokens | <2s | ⭐⭐⭐⭐⭐ | ✅ 成本最低、中文最佳 |
| Claude 3.5 Sonnet | $3/M input, $15/M output | ~3s | ⭐⭐⭐⭐ | ❌ 成本高30倍 |
| OpenAI GPT-4 | $10/M tokens | ~4s | ⭐⭐⭐ | ❌ 成本高100倍 |

**成本估算**:
- 1000次对话/天，平均700 tokens/次
- 月消耗: 1000 × 30 × 700 = 21M tokens
- 月成本: 21M × $0.0000001 ≈ $0.42（约3元人民币）

### 4.3 为什么从硬编码迁移到config.yaml？

**安全问题**: 原ai_guide.py硬编码API密钥，存在泄漏风险。

**解决方案**:
1. `data/config.yaml:93-120` 添加ai_dialogue配置段
2. `ai_guide.py` 修改为从config读取API密钥
3. 提供降级机制（AI失败时使用预设对话）

### 4.4 降级机制设计

**触发条件**: AI API调用失败、超时、限流。

**降级策略**:
```python
# ai_dialogue_service.py:146-161
except Exception as e:
    logger.error(f"AI对话生成失败: {e}", exc_info=True)

    # 降级策略：返回预设对话
    fallback_responses = [
        "抱歉，我暂时无法理解你的意思。",
        "我需要想一想，稍后再聊吧。",
        "这个话题太复杂了，我需要时间思考。"
    ]
    return random.choice(fallback_responses), 0
```

## 5. Integration Points

### 5.1 已完整集成的功能

**NPC交互系统集成**:
- `world/npc_interaction.py:236-239` - 检查ai_enabled标志，调用handle_ai_dialogue_interaction()
- 完美兼容现有NPC类型系统（商人、工匠、普通NPC等）

**数据库自动迁移**:
- `models/auto_migrate.py:129-171` - 添加npc_dialogue_history和npc_favorability表定义
- bot启动时自动创建表，无需手动执行SQL

**配置系统集成**:
- `data/config.yaml:93-120` - ai_dialogue配置段
- `ai_guide.py` - API密钥从配置读取

**启动逻辑集成**:
- `__init__.py:71-86` - PersonalityManager自动加载npc_personalities.yaml
- 启动日志: "[NPCDialogue] 成功加载 4 个NPC人设配置"

### 5.2 管理员命令集成

**3个新命令**:
1. `【启用NPC AI <NPC名称>】` - 为指定NPC启用AI对话
2. `【禁用NPC AI <NPC名称>】` - 为指定NPC禁用AI对话
3. `【查看NPC AI <NPC名称>】` - 查看NPC的AI配置状态

**权限控制**: 使用ai_guide.is_admin()进行管理员验证

## 6. Key Implementation Details

### 6.1 防刷好感度机制（新增 2025-12-07）

**问题**: 玩家可能通过无意义刷屏（"你好"、"嗯"、"啊"等）快速提升好感度

**解决方案** (`npc_favorability_service.py:268-280`):

| 防刷规则 | 触发条件 | 好感度变化 | 说明 |
|---------|---------|-----------|------|
| 敷衍检测 | ≤3字符 | 0 | 过短的消息视为敷衍 |
| 阶段性递减 | 好感度<40，中性对话 | +1 | 新手期普通对话有效 |
| 阶段性递减 | 好感度≥40，中性对话 | 0 | 高好感度需要正面对话 |
| 空消息处理 | 无对话内容 | 0 | 防止空消息刷好感度 |

**代码逻辑**:
```python
# 中性内容：检测敷衍回复和好感度阶段
if len(dialogue_content.strip()) <= 3:
    base_change = 0  # 无意义对话不增加好感度
elif current_favorability < 40:
    base_change = 1  # 新手期：普通对话可以增加好感
else:
    base_change = 0  # 高好感度期：需要正面对话或重大事件
```

**效果**:
- 防止玩家通过"嗯"、"啊"等短词刷屏
- 高好感度（≥40）后，需要有意义的正面对话才能增加好感度
- 结合递减机制，形成完整的防刷体系

### 6.2 人设提示词模板

**系统提示词构建** (`ai_dialogue_service.py:166-210`):
```python
system_prompt = f"""你是一个修仙游戏中的NPC角色，扮演{personality.name}。

【角色身份】
- 名称: {personality.name}
- 角色: {personality.role}
- 背景: {personality.background}

【语言风格】
- 自称: {personality.pronouns}（如"俺"、"本大爷"等）
- 性格: {personality.speech_patterns}
- 常用词汇: {personality.key_words}

【性格数值】
- 忠诚度: {personality.personality_traits.get('loyalty', 50)}/100
- 开朗度: {personality.personality_traits.get('cheerfulness', 50)}/100
- 好斗度: {personality.personality_traits.get('aggressiveness', 50)}/100

【行为准则】
{personality.behavioral_rules}

【对话风格】
- 好感度{favorability}时，用{attitude}的态度说话
- 回复要短小精悍，不超过100字
- 要体现NPC的性格特征和背景
"""
```

### 6.3 好感度计算规则（含递减与情感分析+防刷机制）

**变化规则** (`npc_favorability_service.py:237-318`):
| 互动类型 | 基础好感度变化 | 触发场景 | 是否受递减影响 |
|---------|--------------|---------|--------------|
| dialogue (很负面) | -10 | 辱骂、攻击性对话 | ❌ 否（重大事件） |
| dialogue (负面) | -3 | 不友好内容 | ✅ 是 |
| dialogue (正面) | +3 | 友好内容 | ✅ 是 |
| dialogue (中性) | +1 | 普通对话 | ✅ 是 |
| gift | +10 | 赠送物品（未实现） | 部分（≥60好感度时×0.8） |
| quest_complete | +15 | 完成任务（未实现） | ❌ 否（重大事件） |
| save_life | +20 | 救命之恩（未实现） | ❌ 否（重大事件） |
| combat (胜利) | +5 | 与NPC并肩作战（未实现） | 部分（≥60好感度时×0.7） |
| combat (失败) | -20 | NPC被击杀（未实现） | ❌ 否（重大事件） |
| betrayal | -30 | 背叛行为（未实现） | ❌ 否（重大事件） |

**情感分析系统** (`npc_favorability_service.py:125-171`):
- **极度负面词汇**: 去死、滚、傻、蠢、废物、垃圾、白痴等 → `very_negative` (-10好感度)
- **负面词汇**: 讨厌、烦、无聊、没用、笨、差劲等 → `negative` (-3好感度)
- **正面词汇**: 喜欢、爱、好、棒、厉害、谢谢、感谢等 → `positive` (+3好感度)
- **中性对话**: 未匹配任何关键词 → `neutral` (+1好感度)

**好感度递减机制** (`npc_favorability_service.py:173-235`):
- **核心设计**: 日常对话在接近关系等级门槛时效果大幅降低，需要重大事件突破
- **等级门槛**: 20 (熟识), 40 (友好), 60 (亲密), 80 (知心), 95 (满级)
- **门槛附近效果**:
  - 距离门槛≤2点时: 日常对话几乎无效（≤3的好感度变化直接归零）
  - 距离门槛3-5点时: 日常对话效果减半
- **等级递减乘数**:
  ```python
  0-20 (陌生人):   1.0× (100%效果)
  20-40 (熟识):    0.8× (80%效果)
  40-60 (友好):    0.6× (60%效果)
  60-80 (亲密):    0.4× (40%效果)
  80-100 (知心):   0.2× (20%效果)
  ```
- **重大事件不受限制**: gift (+10), quest_complete (+15), save_life (+20), combat胜利 (+5) 可直接突破门槛

**关系等级**:
```python
def _update_relationship_level(favorability: int) -> str:
    if favorability >= 80:
        return "知心"
    elif favorability >= 60:
        return "亲密"
    elif favorability >= 40:
        return "友好"
    elif favorability >= 20:
        return "熟识"
    else:
        return "陌生人"
```

### 6.4 对话历史管理（修复懒加载问题）

**存储策略**:
- 每次对话保存完整记录（player_input, npc_response, tokens_used, favorability_change, favorability_after）
- 查询时限制最近10轮（max_rounds配置）
- TTL 30天（history.ttl_days配置）

**懒加载修复** (`npc_dialogue_history_repository.py:40-53`):
- **问题**: 原实现直接使用`result.scalars().all()`，导致关联对象懒加载失败
- **解决方案**: 查询后立即加载所有对话记录到内存，避免懒加载
- **性能优化**: 查询时`limit=10`，只获取最近10条对话，减少数据传输

**新增计数方法** (`npc_dialogue_history_repository.py:214-259`):
- `get_dialogue_count()`: 获取对话总数（用于总结触发判断）
- `get_dialogues_after_id()`: 获取指定ID之后的对话（用于增量总结）

**上下文构建优化** (`ai_dialogue_service.py:83-105`):
- **多轮对话支持**: 每个玩家与同一NPC有独立的对话历史上下文
- **格式**: 使用标准的messages list格式（role: user/assistant）供AI理解
```python
history_context = []
for h in dialogue_history[-self.max_history_rounds:]:
    history_context.append({
        "role": "user",
        "content": h.player_input
    })
    history_context.append({
        "role": "assistant",
        "content": h.npc_response
    })
```

### 6.5 对话历史查看命令

**新增命令** (`world/npc_interaction_history.py`):
- **命令**: 【对话历史 NPC名字】，别名: 查看对话、对话记录
- **功能**: 查看最近10条与指定NPC的对话记录
- **显示内容**:
  - 时间戳（月-日 时:分）
  - 玩家发言和NPC回复
  - 每轮对话的好感度变化和变化后的好感度
  - 当前好感度和关系等级
  - 总互动次数
- **示例输出**:
  ```
  📖 与【武安勇】的对话历史
  ━━━━━━━━━━━━━
  显示最近3条记录：

  【1. 12-06 14:30】
    【你】: 你好
    【武安勇】: 嘿呀，道友你好！
    好感度: +3 → 53/100

  【2. 12-06 14:35】
    【你】: 你是傻子
    【武安勇】: 你...你说什么！
    好感度: -10 → 43/100

  ━━━━━━━━━━━━━
  当前好感度: 45/100 (友好)
  总互动次数: 2次
  ```

### 6.6 长期记忆三层架构（新增 2025-12-07）

**设计原理**:

传统方法问题：每次对话传递最近100+轮完整历史，token消耗巨大

三层记忆解决方案：
```
第1层（短期记忆）: 最近10轮原始对话
第2层（中期记忆）: 最近3次AI总结（每次总结20-30轮对话）
第3层（长期记忆）: 最近5个重要事件（礼物/任务/冲突等）
```

**数据模型** (`models/npc_long_term_memory.py:14-84`):

| 字段 | 类型 | 说明 |
|-----|------|------|
| memory_type | summary/event | 记忆类型 |
| content | Text | 记忆内容 |
| event_type | gift/quest/promise/conflict/emotion | 事件分类 |
| importance_score | 1-10 | 重要性评分 |
| emotion_change | Integer | 情感变化值 |
| weight | Float | 记忆权重（随时间衰减） |
| from_dialogue_id/to_dialogue_id | Integer | 关联的对话范围 |

**检查点模型** (`models/npc_long_term_memory.py:86-138`):

| 字段 | 说明 |
|-----|------|
| last_summarized_dialogue_id | 最后总结的对话ID |
| total_dialogues_summarized | 已总结的对话总数 |
| next_summary_threshold | 下次总结阈值（20-30轮） |

**记忆查询优化** (`npc_long_term_memory_repository.py`):
- `get_recent_summaries()`: 按创建时间倒序，获取最近N次总结
- `get_important_events()`: 按重要性×权重排序，获取最重要的N个事件
- `decay_old_memories()`: 批量更新记忆权重（decay_rate=0.95）

**Token消耗对比**:

| 方案 | 每次对话token消耗 | 100轮对话累计 | 优化幅度 |
|-----|---------------|------------|---------|
| 传统方法（传递100轮完整历史） | ~7000 tokens | 700,000 tokens | - |
| 三层记忆（10+3+5） | ~6000-6500 tokens | 600,000-650,000 tokens | 5-10% |

**优势**:
1. **减少token消耗**: 总结压缩历史，预计减少5-10%成本
2. **保留重要信息**: 关键事件不会因时间流逝而丢失
3. **记忆衰减**: 模拟人类记忆遗忘规律，老记忆权重降低
4. **异步后台**: 总结任务不阻塞用户交互

### 6.7 异步后台总结机制（新增 2025-12-07）

**问题**: 调用AI总结对话需要2-5秒，如果同步执行会阻塞用户交互

**解决方案** (`npc_interaction.py:605-633`):

```python
# 对话完成后检查是否需要总结
if await summary_service.should_trigger_summary(npc.id, player.id):
    # 创建异步后台任务
    async def summarize_task():
        try:
            await summary_service.summarize_dialogues(
                npc_id=npc.id,
                player_id=player.id,
                npc_personality=personality
            )
        except Exception as e:
            logger.error(f"后台总结任务失败: {e}")

    # 不等待任务完成，立即返回对话结果
    asyncio.create_task(summarize_task())
```

**工作流程**:
1. 玩家发送对话 → AI回复（2秒）
2. 检查总结阈值（0.01秒）
3. 如果需要总结，创建后台任务
4. **立即返回对话结果给玩家**（不等待总结）
5. 后台任务执行总结（2-5秒，不影响玩家）

**错误处理**:
- 后台任务失败不影响主流程
- 使用try-except捕获异常并记录日志
- 下次对话时重新触发总结

**数据库事务**:
- 后台任务使用独立的session
- 总结完成后才提交事务
- 避免脏读和数据不一致

### 6.8 UI改进：简洁对话显示

**优化前问题** (`world/npc_interaction.py:515-583之前`):
- 每次对话显示完整的10轮历史记录，导致刷屏
- 玩家和NPC名字没有明确标识，不易阅读

**优化后方案** (`world/npc_interaction.py:579-636`):
1. **仅显示上一条对话** (lines 586-594):
   - 如果有历史记录，只显示最后一轮
   - 截断过长文本（玩家输入30字，NPC回复40字）
   - 使用【你】和【NPC名】括号标识说话者

2. **好感度变化可视化** (lines 602-615):
   - 正向变化: 📈 +X
   - 负向变化: 📉 -X
   - 无变化: ➖ ±0
   - 显示当前好感度、关系等级、互动次数

3. **门槛提示系统** (lines 617-629):
   - 当好感度接近门槛（差3点以内）时显示突破提示
   - 提示内容说明如何突破当前等级：
     ```
     20→熟识: "需要更多交流才能成为朋友"
     40→友好: "需要赠送礼物或完成任务才能更进一步"
     60→亲密: "需要共同战斗或完成重要任务才能建立亲密关系"
     80→知心: "需要经历生死考验才能成为知心好友"
     ```

4. **递减效应警告** (lines 631-635):
   - 当好感度≥60且单次变化≤1时，提示"日常对话已无法增进关系，需要特殊互动"
   - 引导玩家使用重大事件（礼物、任务、战斗）突破瓶颈

**输出示例**:
```
💬 【武安勇】
━━━━━━━━━━━━━
📜 上次对话：
  【你】: 你最近怎么样？
  【武安勇】: 俺最近挺好的，多谢关心...
━━━━━━━━━━━━━
🗨️ 当前对话：
  【你】: 我送你个礼物
  【武安勇】: 兄弟你太客气了！俺很喜欢！

❤️ 好感度: 78/100 (📈 +2)
🔗 关系等级: 亲密
🔄 互动次数: 15次
💡 提示: 即将突破至【知心】关系，需要经历生死考验才能成为知心好友
```

## 7. Configuration Reference

### 7.1 AI对话配置 (config.yaml:93-120)

```yaml
ai_dialogue:
  # LLM服务商配置
  provider: "zhipu"  # zhipu | openai | claude | local

  # 智谱AI配置
  zhipu:
    api_key: "YOUR_API_KEY"  # 智谱AI API密钥
    model: "GLM-4.5-Flash"  # 默认模型
    max_tokens: 300  # 单次对话最大token数
    temperature: 0.1  # 温度参数（0-1）
    timeout: 30  # API调用超时时间（秒）

  # 对话历史管理
  history:
    max_rounds: 10  # 保留最近多少轮对话
    ttl_days: 30  # 对话历史保留天数

  # 成本控制
  cost_control:
    daily_budget_usd: 10.0  # 每日预算（美元）
    max_tokens_per_dialogue: 300  # 单次对话token上限
    enable_rate_limit: true  # 启用限流
    rate_limit_per_player_per_hour: 30  # 每玩家每小时对话次数上限

  # 内容安全
  safety:
    max_response_length: 200  # 最大回复长度（字符）
    min_response_length: 10  # 最小回复长度
    enable_content_filter: true  # 启用内容过滤
```

### 7.2 NPC人设配置 (npc_personalities.yaml)

**11个预设人设** (Phase 3扩展 2025-12-07):

**基础NPC（4个）**:
1. **武安勇** - 镇上的大块头（粗犷、直爽、豪迈）
2. **铁匠老王** - 铁匠（爽朗、健谈、自豪）
3. **药铺掌柜** - 药铺掌柜（精明、谨慎、礼貌）
4. **司长曹延华** - 缉邪司司长（严肃、正直、鼓励）

**商人类NPC（2个）**:
5. **商人李掌柜** - 上京市集商人（精明、热情、圆滑）
6. **商人王五** - 北郊市集商人（朴实、实在、憨厚）

**工匠类NPC（5个）**:
7. **百工坊宗师** - 上京百工坊宗师（严肃、自豪、专业、传承）
8. **心魔巧匠** - 金陵怪谈工匠（阴郁、神秘、执着）
9. **幽魂锻师** - 云岭幽魂锻造师（飘忽、缥缈、淡然）
10. **疯狂技师** - 摩配镇疯狂技师（疯狂、兴奋、不羁）
11. **炼魂大师** - 风雪镇炼魂宗师（威严、深沉、高傲）

**配置结构**:
```yaml
personalities:
  武安勇:
    name: "武安勇"
    role: "镇上的大块头"
    pronouns: ["俺", "本大爷"]
    speech_patterns: ["粗犷", "直爽", "豪迈"]
    key_words: ["嘿呀", "果然", "怎么了", "兄弟"]
    personality_traits:
      loyalty: 80
      cheerfulness: 70
      aggressiveness: 60
    background: "出身贫寒，靠蛮力讨生活..."
    behavioral_rules:
      - "对给他东西的人很感激"
      - "喜欢参加战团切磋"
    preferred_actions: ["切磋", "饮酒", "打工"]
    knowledge_domain: ["战斗", "蛮力修炼"]
```

## 8. Future Enhancements (未实现功能)

### 8.1 虚拟Player系统

**设计**: 为NPC创建虚拟Player账号，支持游戏指令执行。

**未实现原因**: 技术复杂度高，数据一致性风险大，优先级低。

**预计工作量**: 额外6-8天。

### 8.2 游戏指令执行

**设计**: NPC可以执行玩家指令（使用物品、打工、锻造等）。

**未实现原因**: 依赖虚拟Player系统，方案2不包含此功能。

**预计工作量**: 额外4-6天。

### 8.3 NPC自主决策

**设计**: NPC定时自主执行行动（如打工、修炼、移动）。

**未实现原因**: 需要复杂的决策引擎和调度系统，投入产出比低。

**预计工作量**: 额外8-10天。

### 8.4 对话缓存系统

**设计**: 缓存相同问题的AI回复，减少API调用成本。

**未实现原因**: 初期对话量低，缓存收益有限。

**预计工作量**: 2天（使用Redis实现TTL缓存）。

## 9. Deployment Checklist

**已完成（Phase 1-2，2025-12-06）**:
- [x] 数据库表自动创建（auto_migrate.py集成）
- [x] PersonalityManager启动加载
- [x] AI API密钥配置化
- [x] 管理员命令集成
- [x] NPC交互系统集成
- [x] 降级机制实现
- [x] 情感分析系统
- [x] 递减机制好感度系统
- [x] 对话历史查看命令

**已完成（Phase 3优化，2025-12-07）**:
- [x] 防刷好感度机制（敷衍检测+阶段性递减）
- [x] 长期记忆数据模型和Repository
- [x] 对话总结Service（AI驱动）
- [x] 异步后台总结任务
- [x] 三层记忆架构集成
- [x] 人设扩展到11个（4基础+2商人+5工匠）
- [x] 数据库auto_migrate集成（long_term_memory表）

**待部署**:
- [ ] 配置实际的智谱AI API密钥（生产环境）
- [ ] 为现有NPC启用AI对话（管理员执行）
- [ ] 监控AI调用成本和错误率
- [ ] 监控长期记忆存储增长（定期清理）
- [ ] 玩家反馈收集和人设优化
- [ ] 评估长期记忆对token消耗的实际影响

## 10. Cost and Performance

### 10.1 成本分析

**月度预算（Phase 3优化后）**:
- 假设场景: 1000次对话/天，平均650 tokens/次（含长期记忆上下文）
- 月消耗: 1000 × 30 × 650 = 19.5M tokens
- 月成本: 19.5M × $0.0000001 ≈ $0.39 ≈ 2.7元人民币
- **对比Phase 2**: 700 tokens/次 → 650 tokens/次，节省7%

**长期记忆成本优化**:
| 对话轮数 | 传统方法token | 三层记忆token | 节省比例 |
|---------|------------|-------------|---------|
| 20轮 | 1400 | 1400 | 0% |
| 50轮 | 3500 | 3200 | 8.6% |
| 100轮 | 7000 | 6300 | 10% |
| 200轮 | 14000 | 12000 | 14.3% |

**额外成本（总结任务）**:
- 每20-30轮触发一次总结: ~500 tokens
- 月度总结次数: (1000×30) / 25 = 1200次
- 月度总结成本: 1200 × 500 × $0.0000001 ≈ $0.06 ≈ 0.4元
- **总成本**: 2.7 + 0.4 = 3.1元/月

**成本控制措施**:
1. token上限: 300 tokens/次对话
2. 限流: 30次/玩家/小时
3. 日预算: $10/天（约70元人民币）
4. 总结阈值: 20-30轮（避免频繁总结）
5. 记忆衰减: 老记忆权重降低（减少查询量）

### 10.2 性能指标

**预期性能（Phase 3优化后）**:
- AI响应时间: <2秒（智谱AI GLM-4.5-Flash）
- 数据库查询: <100ms（对话历史、好感度）
- 长期记忆查询: <50ms（索引优化）
- 异步总结任务: 2-5秒（不阻塞用户）
- 总响应时间: <3秒（不含后台总结）

**性能优化**:
- 对话历史查询限制10轮（减少数据传输）
- 好感度查询使用索引（npc_id, player_id）
- 长期记忆使用复合索引（npc_id, player_id, created_at）
- 异步后台总结（不阻塞用户交互）
- 记忆权重衰减（批量更新，减少查询频率）
- 未来可考虑Redis缓存人设配置

**存储增长预估**:
| 数据类型 | 每条大小 | 月度增长 | 年度增长 |
|---------|---------|---------|---------|
| 对话历史 | ~500B | 15MB | 180MB |
| 长期记忆（总结） | ~200B | 0.24MB | 2.9MB |
| 长期记忆（事件） | ~300B | 0.36MB | 4.3MB |
| **总计** | - | **15.6MB** | **187.2MB** |

**数据清理建议**:
- 对话历史: 保留30天（config.yaml配置）
- 长期记忆: 保留180天，权重<0.1时自动删除
- 定期执行: `decay_old_memories()`批量衰减

---

**相关文档**:
- 架构设计: `/llmdoc/architecture/dialogue-npc-system.md`（完整设计方案，包含未实现功能）
- 使用指南: `/llmdoc/guides/npc-ai-dialogue-usage.md`
- Service API: `/llmdoc/reference/service-api-reference.md`
- 数据模型: `/llmdoc/reference/data-models.md`
