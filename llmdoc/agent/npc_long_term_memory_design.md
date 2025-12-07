# NPC对话历史系统与长期记忆机制设计

**调查日期**: 2025-12-07
**调查范围**: NPC对话历史、AI总结压缩、长期记忆存储、性能优化
**调查目标**: 设计一个对话总结压缩系统，在保持对话上下文的同时降低token消耗

---

## Code Sections (The Evidence)

### 1. 当前对话历史系统实现

#### 1.1 数据模型
- `plugins/xiuxian_game/models/npc_dialogue_history.py` (NPCDialogueHistory Model): 对话历史表，记录所有对话
  - 字段：npc_id, player_id, dialogue_type, player_input, npc_response
  - 好感度跟踪：favorability_change, favorability_after
  - 元数据：ai_tokens_used, ai_cost, dialogue_duration_seconds, created_at
  - 索引：`idx_npc_player_created` (npc_id + player_id + created_at)

#### 1.2 对话历史查询
- `plugins/xiuxian_game/infrastructure/repositories/npc_dialogue_history_repository.py:23-53` (`get_recent_interactions`): 查询最近N轮对话
  - 当前限制：最近10轮（可配置）
  - 排序：按created_at倒序，返回时反转为正序
  - 性能：使用复合索引，查询效率高

#### 1.3 AI上下文构建
- `plugins/xiuxian_game/dialogue/ai_dialogue_service.py:76-86` (messages列表构建): 将对话历史转换为AI messages格式
  - 系统提示词（system）：1条
  - 历史对话（user/assistant交替）：最多10轮（20条消息）
  - 当前问题（user）：1条
  - **总token消耗估算**：系统提示词（~200 tokens）+ 历史（~50 tokens/轮 × 10 = 500 tokens）+ 当前问题（~20 tokens）= **~720 tokens/次**

#### 1.4 当前配置
- `plugins/xiuxian_game/data/config.yaml:121` (`max_rounds`): 保留最近5轮对话
- `plugins/xiuxian_game/data/config.yaml:122` (`ttl_days`): 对话历史保留30天
- `plugins/xiuxian_game/dialogue/ai_dialogue_service.py:38` (`self.max_history_rounds`): 从配置读取，默认10轮

### 2. AI调用基础设施

#### 2.1 智谱AI集成
- `plugins/xiuxian_game/ai_guide.py:26-68` (`call_zhipu_api`): 异步调用智谱AI GLM-4.5-Flash
  - 模型：GLM-4-Flash-250414（配置可变）
  - 超时：30秒
  - Temperature：0.1（低随机性）
  - 降级机制：支持302.ai作为备用provider

#### 2.2 成本计算
- `plugins/xiuxian_game/dialogue/ai_dialogue_service.py:237-254` (`calculate_cost`): 计算AI调用成本
  - 定价：智谱AI GLM-4.5-Flash为 **0.1元/百万token**（输入输出同价）
  - 成本存储：以分为单位（避免浮点精度问题）
  - 当前对话成本：~720 tokens × 0.0000001元 = **0.000072元/次**（可忽略不计）

#### 2.3 缓存系统（已配置但未实施）
- `plugins/xiuxian_game/data/config.yaml:132-134` (cache配置):
  - `enabled: true`
  - `ttl_seconds: 3600`（1小时）
  - ❌ **未实现**：AI对话服务中无缓存逻辑

### 3. 好感度与情感分析系统

#### 3.1 情感分析逻辑
- `plugins/xiuxian_game/dialogue/npc_favorability_service.py:125-171` (`analyze_dialogue_sentiment`): 基于关键词的情感分类
  - 极度负面（去死、傻、垃圾等）：-10好感度
  - 负面（讨厌、烦、笨等）：-3好感度
  - 正面（喜欢、好、谢谢等）：+3好感度
  - 中性（无关键词）：+1好感度（但受递减影响）

#### 3.2 好感度递减机制
- `plugins/xiuxian_game/dialogue/npc_favorability_service.py:173-235` (`calculate_favorability_change_with_decay`): 根据当前好感度调整变化值
  - 等级门槛：20（熟识）、40（友好）、60（亲密）、80（知心）、95（满级）
  - 门槛附近效果：距离门槛≤2点时，日常对话几乎无效
  - 递减乘数：
    - 0-20（陌生人）：1.0×（100%）
    - 20-40（熟识）：0.8×（80%）
    - 40-60（友好）：0.6×（60%）
    - 60-80（亲密）：0.4×（40%）
    - 80-100（知心）：0.2×（20%）

### 4. 对话历史查看与统计

#### 4.1 查看命令
- `plugins/xiuxian_game/world/npc_interaction_history.py` (对话历史查看): 显示最近10条对话
  - 显示内容：时间、玩家输入、NPC回复、好感度变化
  - 当前状态：好感度、关系等级、总互动次数

#### 4.2 统计分析
- `plugins/xiuxian_game/infrastructure/repositories/npc_dialogue_history_repository.py:161-212` (`get_dialogue_stats`): 统计对话数据
  - 统计指标：总对话数、总耗时、总token数、总成本
  - 支持按npc_id、player_id、时间范围过滤

---

## Report (The Answers)

### 1. 当前系统分析

#### 1.1 对话历史的存储结构

**数据库表**: `npc_dialogue_history`

**核心字段**:
- **关联键**: npc_id (NPC ID) + player_id (玩家ID)
- **对话内容**: player_input (玩家输入) + npc_response (NPC回复)
- **对话类型**: dialogue_type (natural_dialogue | game_command)
- **好感度跟踪**: favorability_change (本次变化) + favorability_after (变化后总值)
- **成本跟踪**: ai_tokens_used (消耗token数) + ai_cost (成本，以分为单位)
- **时间戳**: created_at (对话时间)

**存储策略**:
- 所有对话永久保存（仅TTL清理：30天）
- 查询时按时间倒序，限制条数（最近10轮）
- 使用复合索引 `idx_npc_player_created` 优化查询性能

**当前容量估算**（假设1000次对话/天，4个NPC）:
- 每条记录约500字节（平均）
- 月存储：1000 × 30 × 500字节 = **15MB/月**
- 年存储：15MB × 12 = **180MB/年**
- **结论**: 存储成本低，不需要清理历史数据

#### 1.2 上下文构建逻辑

**AI上下文构建流程** (`ai_dialogue_service.py:76-89`):
1. 添加系统提示词（1条，~200 tokens）
2. 添加对话历史（最近N轮，每轮2条消息：user + assistant）
3. 添加当前问题（1条，~20 tokens）

**当前配置**:
- `max_rounds: 5`（配置文件）
- `self.max_history_rounds: 10`（代码默认值）
- **实际使用**: 代码使用 `self.max_history_rounds`，即10轮

**Token消耗分析**:
- 系统提示词：~200 tokens（固定）
- 对话历史：~50 tokens/轮 × 10轮 = **500 tokens**（占70%）
- 当前问题：~20 tokens
- AI回复：~100 tokens（输出）
- **总消耗**: 720 tokens/次输入 + 100 tokens输出 = **820 tokens/次**

**性能瓶颈**:
- 10轮对话历史占用50%以上的token
- 对话越长（玩家输入长、NPC回复长），token消耗越高
- 无token上限控制，可能导致超长对话失败

#### 1.3 存在的限制和问题

**问题1: 对话历史未压缩**
- 所有历史对话原样保存
- AI每次调用都要重新处理完整对话历史
- 早期对话的细节对当前对话意义不大，但仍占用token

**问题2: 缺少长期记忆机制**
- 仅保留最近10轮对话（短期记忆）
- 第11轮之前的对话完全丢失上下文
- 无法记忆关键事件（如：玩家送礼物、表达情感、完成任务等）

**问题3: token消耗不可控**
- 没有对话长度限制
- 没有对话历史的动态截断
- 可能在长对话时超过API token限制

**问题4: 缺少缓存机制**
- 配置文件已定义缓存设置，但代码未实现
- 相同问题重复调用AI，浪费成本

**问题5: 好感度系统与对话内容脱节**
- 情感分析仅基于关键词匹配（简单规则）
- 无法理解对话的深层含义（如讽刺、暗示等）
- 无法提取关键事件作为长期记忆

---

### 2. 长期记忆系统设计方案

#### 2.1 核心设计理念

**目标**:
- **对话压缩**: 每20-30轮对话自动触发总结，将历史压缩为关键事件和情感变化
- **长期记忆**: 提取关键事件（送礼物、完成任务、表达情感、重要承诺等）存储为结构化记忆
- **记忆分层**: 短期记忆（最近5轮原文）+ 中期记忆（近期总结，5-20轮）+ 长期记忆（关键事件）
- **成本优化**: 将对话历史从10轮（500 tokens）压缩到总结（~100 tokens），节省80%的token消耗

**设计原则**:
- **不干扰现有系统**: 长期记忆作为可选增强功能，不修改现有对话历史表
- **异步总结**: 总结操作在后台异步执行，不阻塞玩家交互
- **优雅降级**: 总结失败时，回退到使用完整对话历史

#### 2.2 数据库设计

**新表1: `npc_long_term_memory`**（长期记忆表）

```sql
CREATE TABLE npc_long_term_memory (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    npc_id INT NOT NULL,                        -- NPC ID
    player_id VARCHAR(32) NOT NULL,             -- 玩家ID

    -- 记忆类型
    memory_type VARCHAR(20) NOT NULL,           -- summary | event | emotion

    -- 记忆内容
    memory_content TEXT NOT NULL,               -- 记忆描述（AI生成的总结或事件描述）

    -- 关键事件（仅event类型）
    event_category VARCHAR(20),                 -- gift | quest | promise | conflict | milestone
    event_importance INT DEFAULT 5,             -- 重要性：1（低）-10（高）

    -- 情感变化（仅emotion类型）
    emotion_change INT DEFAULT 0,               -- 情感变化值（-10到+10）
    emotion_reason VARCHAR(100),                -- 情感变化原因

    -- 时间范围（仅summary类型）
    summary_start_time DATETIME,                -- 总结起始时间
    summary_end_time DATETIME,                  -- 总结结束时间
    summary_dialogue_count INT DEFAULT 0,       -- 总结覆盖的对话数量

    -- 元数据
    ai_tokens_used INT,                         -- AI总结消耗的token数
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_npc_player (npc_id, player_id),
    INDEX idx_memory_type (memory_type),
    INDEX idx_importance (event_importance DESC)
);
```

**字段说明**:
- `memory_type`:
  - `summary`: 对话总结（每20-30轮生成一次）
  - `event`: 关键事件（送礼物、完成任务、表达情感等）
  - `emotion`: 情感变化（重大好感度波动）
- `event_category`:
  - `gift`: 赠送礼物
  - `quest`: 完成任务
  - `promise`: 重要承诺
  - `conflict`: 冲突/争吵
  - `milestone`: 关系等级突破
- `event_importance`: 重要性权重（1-10），用于决定是否纳入AI上下文

**新表2: `npc_dialogue_summary_checkpoint`**（总结检查点表）

```sql
CREATE TABLE npc_dialogue_summary_checkpoint (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    npc_id INT NOT NULL,
    player_id VARCHAR(32) NOT NULL,

    -- 总结状态
    last_summary_dialogue_id BIGINT,            -- 上次总结的最后一条对话ID
    last_summary_time DATETIME,                 -- 上次总结时间
    next_summary_threshold INT DEFAULT 20,      -- 下次总结的对话阈值（动态调整）

    -- 统计
    total_dialogues_summarized INT DEFAULT 0,   -- 已总结的对话总数
    total_summaries_created INT DEFAULT 0,      -- 已创建的总结数量

    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uk_npc_player (npc_id, player_id)
);
```

**为什么不扩展现有表？**
- `npc_dialogue_history` 保持纯粹的对话记录职责
- 长期记忆和检查点是独立功能，可以随时启用/禁用
- 方便未来迁移和优化（如Redis缓存）

#### 2.3 对话压缩与总结策略

**触发条件**（满足任意一项即触发）:
1. **对话数量阈值**: 自上次总结后累积20-30轮对话（可配置）
2. **关系等级突破**: 好感度突破关系等级门槛（20/40/60/80）
3. **重大事件**: 好感度单次变化≥10（极度负面或重大正面事件）

**总结流程**:
1. 查询待总结的对话（`last_summary_dialogue_id` 之后的所有对话）
2. 调用AI生成对话总结（使用专用提示词）
3. 提取关键事件（AI识别出的重要互动）
4. 保存总结到 `npc_long_term_memory` 表（`memory_type=summary`）
5. 保存关键事件到 `npc_long_term_memory` 表（`memory_type=event`）
6. 更新检查点 `last_summary_dialogue_id` 和 `last_summary_time`

**AI总结提示词设计**:

```python
SUMMARY_PROMPT_TEMPLATE = """
你是一个对话分析专家，负责总结玩家与NPC的对话历史。

【任务】
分析以下{dialogue_count}轮对话，生成简洁的总结（100字以内）和关键事件列表。

【对话历史】
{dialogue_history}

【输出格式】
请以JSON格式返回：
{{
  "summary": "对话总结（描述整体内容和情感变化）",
  "key_events": [
    {{
      "event_type": "gift | quest | promise | conflict | milestone",
      "description": "事件描述（20字以内）",
      "importance": 7,  // 重要性1-10
      "emotion_change": 3  // 情感变化-10到+10
    }}
  ],
  "overall_emotion": 5,  // 整体情感倾向-10（极度负面）到+10（极度正面）
  "relationship_progress": "关系进展描述（30字以内）"
}}

【要求】
1. 总结要简洁明了，突出重点
2. 关键事件只提取真正重要的互动（≥5的importance）
3. 情感变化基于对话内容的深层理解，不仅仅是关键词匹配
4. 如果没有关键事件，key_events返回空数组
"""
```

**性能优化**:
- 总结操作异步执行（使用后台任务队列）
- 单次总结token消耗：~800 tokens输入 + ~200 tokens输出 = **1000 tokens**（成本0.0001元）
- 触发频率：每20-30轮对话1次，成本可控

#### 2.4 记忆使用策略（AI上下文构建优化）

**新的上下文构建逻辑**:

```python
async def build_ai_context_with_memory(
    npc_id: int,
    player_id: str,
    current_question: str
) -> List[dict]:
    """
    构建包含长期记忆的AI上下文

    优先级：
    1. 系统提示词（包含NPC人设）
    2. 长期记忆（关键事件，最多5条）
    3. 中期总结（最近1-2次总结）
    4. 短期对话（最近5轮原文）
    5. 当前问题
    """
    messages = []

    # 1. 系统提示词（~200 tokens）
    system_prompt = build_system_prompt(npc, personality, favorability)
    messages.append({"role": "system", "content": system_prompt})

    # 2. 长期记忆（关键事件，~100 tokens）
    key_events = await get_key_events(npc_id, player_id, limit=5, min_importance=7)
    if key_events:
        memory_context = "【重要记忆】\n"
        for event in key_events:
            memory_context += f"- {event.memory_content}\n"
        messages.append({"role": "system", "content": memory_context})

    # 3. 中期总结（最近1-2次总结，~100 tokens）
    recent_summaries = await get_recent_summaries(npc_id, player_id, limit=2)
    if recent_summaries:
        summary_context = "【最近对话总结】\n"
        for summary in recent_summaries:
            summary_context += f"- {summary.memory_content}\n"
        messages.append({"role": "system", "content": summary_context})

    # 4. 短期对话（最近5轮原文，~250 tokens）
    recent_dialogues = await get_recent_dialogues(npc_id, player_id, limit=5)
    for dialogue in recent_dialogues:
        messages.append({"role": "user", "content": dialogue.player_input})
        messages.append({"role": "assistant", "content": dialogue.npc_response})

    # 5. 当前问题（~20 tokens）
    messages.append({"role": "user", "content": current_question})

    return messages
```

**Token消耗对比**:

| 方案 | 系统提示词 | 长期记忆 | 中期总结 | 短期对话 | 当前问题 | 总计 | 节省率 |
|------|---------|---------|---------|---------|---------|------|--------|
| **原方案** | 200 | 0 | 0 | 500 (10轮) | 20 | 720 | 0% |
| **新方案** | 200 | 100 (5事件) | 100 (2总结) | 250 (5轮) | 20 | **670** | **7%** |

**优化效果**:
- Token节省：50 tokens/次（7%）
- 上下文质量提升：包含关键事件和总结，AI更好理解长期关系
- 短期对话减少：从10轮降到5轮，降低噪音

#### 2.5 触发机制设计

**方案1: 实时触发（推荐）**

**优点**:
- 及时更新，玩家体验最好
- 无需额外调度器，代码简单

**缺点**:
- 总结操作可能延迟玩家交互（如果同步执行）

**实施方案**:
- 在 `handle_ai_dialogue_interaction` 中检查总结条件
- 如果满足条件，发起异步任务（使用 `asyncio.create_task`）
- 总结失败不影响对话继续

**代码示例**:

```python
async def handle_ai_dialogue_interaction(...):
    # ... 现有对话逻辑 ...

    # 检查是否需要总结
    if await should_trigger_summary(npc.id, player.id):
        # 异步触发总结，不阻塞当前对话
        asyncio.create_task(
            summarize_dialogue_history(npc.id, player.id)
        )
        logger.info(f"[LongTermMemory] 触发异步总结: npc={npc.id}, player={player.id}")
```

**方案2: 定时任务触发（备选）**

**优点**:
- 不影响玩家交互性能
- 可以批量处理多个玩家

**缺点**:
- 需要额外的调度器（如APScheduler）
- 总结可能滞后，影响AI上下文准确性

**实施方案**:
- 创建定时任务（每小时或每天）
- 扫描所有需要总结的NPC-Player对
- 批量生成总结

**推荐**: 方案1（实时触发），因为当前对话量不高，实时总结不会造成性能问题。

#### 2.6 记忆权重和遗忘机制（Phase 3，可选）

**记忆权重系统**:
- 根据 `event_importance` 和时间衰减计算记忆权重
- 高权重记忆优先纳入AI上下文

**遗忘机制**:
- 低重要性事件（importance < 5）在90天后自动删除
- 普通事件（importance 5-7）在180天后删除
- 重要事件（importance ≥ 8）永久保留

**时间衰减函数**:

```python
def calculate_memory_weight(event: LongTermMemory) -> float:
    """
    计算记忆权重（0-10）

    权重 = 基础重要性 × 时间衰减系数
    """
    base_importance = event.event_importance
    days_ago = (datetime.now() - event.created_at).days

    # 时间衰减：30天内不衰减，之后每30天衰减10%
    decay_factor = max(0.5, 1.0 - (days_ago // 30) * 0.1)

    return base_importance * decay_factor
```

---

### 3. 实施方案

#### Phase 1: 基础总结功能（2-3天）

**目标**: 实现对话压缩和基础总结

**任务清单**:
1. **数据库设计**:
   - 创建 `npc_long_term_memory` 表
   - 创建 `npc_dialogue_summary_checkpoint` 表
   - 添加数据库迁移脚本

2. **Repository层**:
   - `LongTermMemoryRepository`: CRUD操作，查询关键事件和总结
   - `DialogueSummaryCheckpointRepository`: 管理总结检查点

3. **Service层**:
   - `DialogueSummarizationService`: 对话总结生成服务
     - `should_trigger_summary()`: 检查是否需要总结
     - `summarize_dialogue_history()`: 生成总结
     - `extract_key_events()`: 提取关键事件（从AI总结结果中解析）

4. **AI提示词设计**:
   - `SUMMARY_PROMPT_TEMPLATE`: 对话总结提示词
   - `EVENT_EXTRACTION_PROMPT`: 关键事件提取提示词

5. **集成点**:
   - `world/npc_interaction.py`: 在AI对话后检查总结触发条件
   - `dialogue/ai_dialogue_service.py`: 添加 `build_ai_context_with_memory()` 方法

**验收标准**:
- ✅ 每20-30轮对话自动生成总结
- ✅ 总结保存到数据库
- ✅ 总结失败时不影响正常对话

#### Phase 2: 关键事件提取（2-3天）

**目标**: 使用AI提取关键事件，优化上下文质量

**任务清单**:
1. **事件分类系统**:
   - 定义 `EventCategory` 枚举（gift, quest, promise, conflict, milestone）
   - 定义 `EventImportance` 评分规则（1-10）

2. **AI事件提取**:
   - 优化 `SUMMARY_PROMPT_TEMPLATE`，要求AI返回结构化事件列表
   - 实现 `parse_ai_summary_result()`: 解析AI返回的JSON格式

3. **记忆查询优化**:
   - `get_key_events()`: 按重要性和时间排序，返回Top N事件
   - `get_recent_summaries()`: 返回最近N次总结

4. **上下文构建优化**:
   - 实现 `build_ai_context_with_memory()`: 集成长期记忆到AI上下文
   - 替换现有的 `_build_history_context()` 方法

5. **测试与调优**:
   - 测试AI总结质量
   - 调整提示词和事件提取规则

**验收标准**:
- ✅ AI能准确提取关键事件（准确率≥80%）
- ✅ AI上下文包含长期记忆
- ✅ Token消耗降低5-10%

#### Phase 3: 记忆权重和遗忘机制（1-2天，可选）

**目标**: 实现智能记忆管理，降低长期存储成本

**任务清单**:
1. **权重计算**:
   - 实现 `calculate_memory_weight()`: 基于重要性和时间衰减
   - 修改 `get_key_events()`: 按权重排序

2. **遗忘机制**:
   - 创建定时任务（每周或每月）
   - 删除过期的低重要性事件

3. **统计与监控**:
   - 记录总结次数、token消耗、存储空间
   - 提供管理员命令查看统计数据

**验收标准**:
- ✅ 低重要性事件自动清理
- ✅ 长期存储成本可控（<50MB/年）

---

### 4. 成本和性能评估

#### 4.1 AI总结的Token消耗

**单次总结成本**:
- 输入token：20轮对话 × 50 tokens/轮 + 提示词 200 tokens = **1200 tokens**
- 输出token：总结100字 + 事件列表100字 = **200 tokens**
- 总消耗：1400 tokens
- 单次成本：1400 × 0.0000001元 = **0.00014元**（可忽略不计）

**月度成本估算**（假设1000次对话/天，4个NPC）:
- 对话成本：1000次 × 820 tokens × 0.0000001元 = **0.082元/天** = 2.46元/月
- 总结成本：1000次 ÷ 25（平均每25轮总结1次）× 1400 tokens × 0.0000001元 = **0.0056元/天** = 0.17元/月
- **总成本**: 2.46 + 0.17 = **2.63元/月**

**结论**: 总结系统的成本极低（+7%），对总成本几乎无影响。

#### 4.2 数据库存储开销

**长期记忆表** (`npc_long_term_memory`):
- 每条记录约300字节（平均）
- 每20轮对话生成1次总结 + 2-3个关键事件 = 4条记录
- 月存储：(1000次对话/天 ÷ 20) × 4条 × 300字节 × 30天 = **1.8MB/月**
- 年存储：1.8MB × 12 = **21.6MB/年**

**检查点表** (`npc_dialogue_summary_checkpoint`):
- 每个NPC-Player对1条记录
- 假设100个活跃玩家 × 4个NPC = 400条记录
- 存储：400 × 200字节 = **0.08MB**

**总存储开销**: 21.6MB/年 + 0.08MB ≈ **22MB/年**（可忽略不计）

**结论**: 存储成本极低，不需要特殊的数据清理策略。

#### 4.3 对用户体验的影响（延迟）

**当前对话延迟**:
- 查询对话历史：~50ms
- 调用AI API：~2000ms
- 保存对话记录：~50ms
- **总延迟**: ~2100ms（2.1秒）

**新增总结操作延迟**（异步执行，不阻塞）:
- 查询待总结对话：~100ms
- 调用AI总结API：~3000ms
- 保存总结和事件：~100ms
- **总延迟**: ~3200ms（3.2秒，后台执行）

**对玩家的影响**:
- 使用异步任务 (`asyncio.create_task`)，总结在后台执行
- 玩家对话不受总结延迟影响
- **结论**: 对用户体验无影响

#### 4.4 AI上下文质量提升

**当前方案（10轮原文）**:
- 包含所有对话细节
- 上下文噪音多（无关闲聊、重复内容）
- AI难以把握长期关系变化

**新方案（5轮原文 + 总结 + 关键事件）**:
- 短期对话保留细节
- 中长期对话通过总结提炼重点
- 关键事件突出重要互动
- AI更好理解玩家与NPC的关系历程

**预期效果**:
- AI回复更符合长期关系
- 减少重复内容和遗忘问题
- 玩家沉浸感提升

---

## Conclusions (结论)

### 核心发现

1. **当前系统可扩展性良好**:
   - 对话历史表设计合理，查询性能高
   - AI调用服务完整，支持降级和容错
   - 好感度系统完善，情感分析可优化

2. **长期记忆是必要增强**:
   - 10轮对话历史不足以支撑长期关系
   - 对话压缩可节省token消耗（5-10%）
   - 关键事件提取显著提升AI上下文质量

3. **实施成本可控**:
   - 开发周期：5-8天（含测试）
   - 运行成本：+0.17元/月（+7%，可忽略）
   - 存储成本：22MB/年（可忽略）

4. **技术风险低**:
   - 使用异步任务，不影响玩家交互
   - 优雅降级，总结失败不影响对话
   - 数据库表独立，可随时启用/禁用

### 推荐方案

**Phase 1（必须）**: 基础总结功能（2-3天）
- 实现对话压缩和自动总结
- 建立长期记忆数据表
- 集成到现有对话流程

**Phase 2（推荐）**: 关键事件提取（2-3天）
- 使用AI提取关键事件
- 优化AI上下文构建
- 测试和调优总结质量

**Phase 3（可选）**: 记忆权重和遗忘机制（1-2天）
- 实现智能记忆管理
- 降低长期存储成本
- 提供统计和监控功能

**总工期**: 5-8天（Phase 1 + Phase 2 + Phase 3）

---

## Relations (关系)

### 系统交互关系

1. **对话历史系统 → 总结服务**:
   - `NPCDialogueHistoryRepository.get_recent_interactions()` 提供待总结的对话
   - `DialogueSummarizationService.summarize_dialogue_history()` 生成总结

2. **总结服务 → AI API**:
   - `AIDialogueService._call_ai_with_fallback()` 调用智谱AI
   - 使用 `SUMMARY_PROMPT_TEMPLATE` 生成总结

3. **长期记忆 → AI上下文构建**:
   - `LongTermMemoryRepository.get_key_events()` 提供关键事件
   - `AIDialogueService.build_ai_context_with_memory()` 构建上下文

4. **好感度系统 → 关键事件提取**:
   - `NPCFavorabilityService.add_interaction()` 记录好感度变化
   - 好感度突破门槛时触发关键事件记录

5. **对话命令 → 总结触发**:
   - `handle_ai_dialogue_interaction()` 在对话后检查总结条件
   - 满足条件时异步触发 `summarize_dialogue_history()`

### 依赖关系

- **长期记忆系统** 依赖于 **对话历史系统**（数据来源）
- **AI总结** 依赖于 **智谱AI API**（外部服务）
- **关键事件提取** 依赖于 **AI总结结果**（结构化输出）
- **优化的AI上下文** 依赖于 **长期记忆查询**（记忆检索）

---

**相关文档**:
- 实施记录: `/llmdoc/architecture/npc-ai-dialogue-implementation.md`
- 使用指南: `/llmdoc/guides/npc-ai-dialogue-usage.md`
- Service API: `/llmdoc/reference/service-api-reference.md`
