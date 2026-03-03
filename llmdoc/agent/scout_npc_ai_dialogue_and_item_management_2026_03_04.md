# NPC AI对话系统与物品管理调查报告

**调查日期**: 2026-03-04
**调查任务**: 调查游戏恢复药品定义、背包添加物品方法、NPC AI对话交互流程及文本处理机制

---

## Code Sections (证据清单)

### 1. 恢复药品配置

- `plugins/xiuxian_game/data/items.yaml:3-17` (`heal_potion`, `spirit_herb`): 初级恢复药品定义，固定值恢复
  - `heal_potion` (回春散): `RESTORE_HP`, 恢复40HP, item_id="heal_potion"
  - `spirit_herb` (凝神草): `RESTORE_MP`, 恢复40MP, item_id="spirit_herb"

- `plugins/xiuxian_game/data/items.yaml:19-33` (`blood_pact`, `yin_grass`): 中级恢复药品，固定值恢复
  - `blood_pact` (血契丹): `RESTORE_HP`, 恢复120HP, item_id="blood_pact"
  - `yin_grass` (阴冥草): `RESTORE_MP`, 恢复120MP, item_id="yin_grass"

- `plugins/xiuxian_game/data/items.yaml:1471-1484` (百分比恢复丹药): 高级恢复药品，百分比恢复
  - `life_recovery_elixir` (回生丹): `RESTORE_HP_PERCENT`, 恢复30%生命值, 每日限100次
  - `soul_recovery_elixir` (凝魂丹): `RESTORE_MP_PERCENT`, 恢复30%理智值, 每日限100次

- `plugins/xiuxian_game/data/items.yaml:1486-1502` (大回生丹/大凝魂丹): 超级恢复药品
  - `great_life_recovery_elixir` (大回生丹): `RESTORE_HP_PERCENT`, 恢复60%生命值, 每日限100次
  - `great_soul_recovery_elixir` (大凝魂丹): `RESTORE_MP_PERCENT`, 恢复60%理智值, 每日限100次

- `plugins/xiuxian_game/data/items.yaml:3203-3208` (`knocker_anxiangx`): 活动专属复合恢复药品
  - `knocker_anxiangx` (安神线香): `RESTORE_HP_MP_PERCENT`, 恢复20%HP + 10%MP

- `plugins/xiuxian_game/data/items.yaml:35-41` (`revive_potion`): 复活药品
  - `revive_potion` (仿制还魂丹): `REVIVE`, 恢复30%状态

### 2. ItemConfig数据模型

- `plugins/xiuxian_game/models/inventory.py:60-113` (`ItemConfig`): 物品配置类，解析items.yaml数据
  - 关键字段: `item_id`, `name`, `type`, `effect_type`, `effect_params`, `price`
  - 恢复类effect_type: `RESTORE_HP`, `RESTORE_MP`, `RESTORE_HP_PERCENT`, `RESTORE_MP_PERCENT`, `RESTORE_HP_MP_PERCENT`

- `plugins/xiuxian_game/models/inventory.py:13-28` (`ItemType`, `ItemEffectType`): 枚举类型定义
  - ItemType枚举包含: CONSUMABLE, MATERIAL, EQUIPMENT, GOODS等14种类型
  - ItemEffectType枚举包含20+种效果类型

### 3. 背包添加物品方法

- `plugins/xiuxian_game/models/inventory.py:316-413` (`ItemInstance.add_item`): 静态方法，添加物品到玩家背包
  - **方法签名**: `async def add_item(session, player_id: str, template_id: str, quantity: int = 1, durability: int = None) -> bool`
  - **参数说明**:
    - `session`: 数据库会话(AsyncSession)
    - `player_id`: 玩家ID字符串
    - `template_id`: 物品item_id(对应items.yaml中的item_id)
    - `quantity`: 数量(默认1)
    - `durability`: 耐久度(装备专用,默认None使用配置值)
  - **返回值**: 成功返回True, 背包满或物品不存在抛出ValueError异常
  - **核心逻辑**:
    1. 从config.items_config获取ItemConfig
    2. 检查玩家是否存在
    3. 查询玩家背包现有物品
    4. 装备类型(EQUIPMENT)直接添加,不占背包格子
    5. 普通物品检查背包空间是否足够(含月卡加成容量)
    6. 自动堆叠到已有物品(每格最多STACK_SIZE=100个)
    7. 超出堆叠限制自动拆分到新格子
    8. 执行flush()确保立即可见

- `plugins/xiuxian_game/infrastructure/repositories/item_repository.py:146-160` (`ItemRepository.add_item`): Repository层封装
  - 封装了ItemInstance.add_item静态方法，保持向后兼容
  - **方法签名**: `async def add_item(self, player_id: str, item_id: str, quantity: int = 1) -> None`

### 4. NPC AI对话交互入口

- `plugins/xiuxian_game/world/npc_interaction.py:24-174` (`interact_cmd`, `handle_npc_interaction`): 交互命令处理器
  - **命令**: 【交互 <NPC名称>】或【对话 <NPC名称>】
  - **流程**:
    1. 解析命令参数(支持"交互 NPC名 对话内容"格式)
    2. 获取玩家当前位置和NPC列表
    3. 智能匹配NPC名称(支持模糊匹配、关键词匹配)
    4. 调用`handle_npc_type_interaction`处理具体交互

- `plugins/xiuxian_game/world/npc_interaction.py:177-221` (`handle_npc_type_interaction`): NPC类型分发器
  - **优先检查AI对话**: 如果NPC的`extra_data.ai_enabled=True`，直接调用`handle_ai_dialogue_interaction`
  - **降级策略**: AI对话失败则显示友好提示
  - **异常处理**: 特别处理NoneBot2的FinishedException(流程控制异常)，不应被捕获

### 5. NPC AI对话核心处理流程

- `plugins/xiuxian_game/world/npc_interaction.py:513-761` (`handle_ai_dialogue_interaction`): AI对话交互核心函数
  - **函数签名**: `async def handle_ai_dialogue_interaction(session, player: Player, npc, event: MessageEvent, question: str = None)`
  - **参数说明**:
    - `session`: 数据库会话
    - `player`: 玩家对象
    - `npc`: NPC对象
    - `event`: QQ消息事件
    - `question`: 玩家对话内容(可选,默认为"你好")
  - **完整流程**:
    1. **初始化服务** (行536-540):
       - 创建`AIDialogueService`(AI对话生成服务)
       - 创建`NPCFavorabilityService`(好感度服务)
       - 创建`NPCDialogueHistoryRepository`(对话历史仓储)

    2. **获取NPC人设** (行542-554):
       - 从`PersonalityManager.get_personality(npc.name)`获取预设人设
       - 如果无预设，使用默认`PersonalityTemplate`(包含name, role, pronouns, speech_patterns等)

    3. **获取好感度** (行556-561):
       - 调用`fav_service.get_favorability()`获取或创建好感度记录
       - 初始好感度从`npc.extra_data.base_favorability`获取(默认50)

    4. **获取对话历史** (行563-568):
       - 调用`history_repo.get_recent_interactions()`获取最近10轮对话

    5. **情感分析** (行570-571):
       - 调用`fav_service.analyze_dialogue_sentiment(question)`分析玩家情感
       - 返回值: "very_negative", "negative", "positive", "neutral"

    6. **获取长期记忆** (行573-584):
       - 创建`DialogueSummarizationService`总结服务
       - 调用`summary_service.get_long_term_context()`获取长期记忆
       - 参数: `include_summaries=3`(最近3次总结), `include_events=5`(最近5个重要事件)

    7. **构建上下文** (行586-601):
       - 包含: 位置名称、玩家名称、等级、坐标、情感分析结果、情感提示、长期记忆
       - 情感提示为字典映射,给AI提供情感响应指导

    8. **生成AI回复** (行603-616):
       - 发送"正在思考..."提示消息
       - 调用`ai_service.generate_dialogue()`生成NPC回复
       - 传入参数: npc, personality, question, dialogue_history, favorability, context
       - **返回**: `(npc_response: str, tokens_used: int)`元组

    9. **更新好感度** (行618-634):
       - 调用`fav_service.get_favorability_change_by_interaction_type()`计算好感度变化
       - 参数: `"dialogue"`, `dialogue_content=question`, `current_favorability`
       - 调用`fav_service.add_interaction()`记录互动并更新好感度

    10. **保存对话历史** (行636-653):
        - 创建`NPCDialogueHistory`对象记录对话详情
        - 包含: npc_id, player_id, dialogue_type, player_input, npc_response, favorability_change, favorability_after, dialogue_duration_seconds, ai_tokens_used, ai_cost
        - 调用`history_repo.save()`和`session.commit()`持久化

    11. **异步触发对话总结** (行655-683):
        - 使用`asyncio.create_task()`创建后台任务
        - 后台任务使用独立的session
        - 调用`summary_service.summarize_dialogues()`检查并执行总结(每20轮对话触发)
        - 不阻塞用户交互

    12. **格式化输出** (行686-743):
        - 显示上次对话历史(最后1条,截取长度避免过长)
        - 显示当前对话(玩家输入+NPC回复)
        - 显示好感度变化(带emoji图标: 📈增加, 📉减少, ➖不变)
        - 显示关系等级、互动次数
        - 显示门槛突破提示(接近20/40/60/80好感度时)
        - 显示特殊提示(高好感度但变化小时提示需要特殊互动)
        - 调用`interact_cmd.finish()`发送最终消息

### 6. AI对话生成服务

- `plugins/xiuxian_game/dialogue/ai_dialogue_service.py:15-342` (`AIDialogueService`): AI对话生成服务类
  - **初始化配置** (行18-44): 从config.game_config加载AI配置,包括provider、模型、温度、超时、降级策略等

- `plugins/xiuxian_game/dialogue/ai_dialogue_service.py:46-116` (`generate_dialogue`): 生成自然对话回复
  - **函数签名**: `async def generate_dialogue(self, npc: NPC, personality: PersonalityTemplate, question: str, dialogue_history: List[NPCDialogueHistory], favorability: int, context: Optional[dict] = None) -> tuple[str, int]`
  - **返回值**: `(NPC回复文本, 消耗的token数)`元组
  - **核心流程**:
    1. 构建系统提示词: `personality.build_system_prompt(favorability, context)`
    2. 添加长期记忆到系统提示词(如果context中提供)
    3. 构建messages列表:
       - 首条: `{"role": "system", "content": system_prompt}`
       - 对话历史: 交替添加user和assistant消息(最近10轮)
       - 当前问题: `{"role": "user", "content": question}`
    4. 调用`_call_ai_with_fallback(messages)`请求AI API
    5. 提取回复内容: `result['choices'][0]['message']['content'].strip()`
    6. 验证回复质量: `_validate_response(response)`
    7. 失败降级: 返回预设回复

- `plugins/xiuxian_game/dialogue/ai_dialogue_service.py:251-341` (`_call_ai_with_fallback`): AI API调用与降级机制
  - **函数签名**: `async def _call_ai_with_fallback(self, messages: list, provider: str = None) -> dict`
  - **降级流程**:
    1. 尝试主provider(默认"zhipu"智谱AI)
    2. 主provider失败且fallback_enabled=True时,尝试fallback_provider(默认"ai302")
    3. 所有provider均失败时抛出综合异常
  - **API调用**:
    - `call_zhipu_api(messages, model="GLM-4-Flash-250414", timeout, temperature)`
    - `call_302ai_api(messages, model="gpt-3.5-turbo", timeout, temperature)`

### 7. AI对话返回文本结构

- `plugins/xiuxian_game/dialogue/ai_dialogue_service.py:100-111` (回复提取与验证): AI回复直接作为纯文本返回
  - **提取位置**: `result['choices'][0]['message']['content'].strip()`
  - **格式**: 纯文本字符串,无结构化解析
  - **验证规则** (行200-213):
    - 长度检查: `min_response_length <= len(response) <= max_response_length`
    - 非空检查: `response.strip()` 不为空
  - **失败降级** (行215-226): 返回基于好感度的预设文本

- `plugins/xiuxian_game/world/npc_interaction.py:686-743` (文本格式化输出): 发送给玩家的文本结构
  - **输出格式** (Markdown风格):
    ```
    💬 【NPC名】
    ━━━━━━━━━━━━━
    📜 上次对话：
      【你】: 玩家输入...
      【NPC名】: NPC回复...
    ━━━━━━━━━━━━━
    🗨️ 当前对话：
      【你】: 玩家输入
      【NPC名】: AI生成的回复文本(纯文本)

    ❤️ 好感度: 50/100 (📈 +2)
    🔗 关系等级: 友好
    🔄 互动次数: 15次
    💡 提示: 即将突破至【亲密】关系...
    ```
  - **文本处理**:
    1. AI返回的`npc_response`直接作为对话内容显示
    2. 不进行额外的解析或转换
    3. 仅对历史对话进行长度截取(player_input[:30], npc_response[:40])
    4. 添加emoji图标和好感度变化提示

---

## Report (调查结果)

### result

#### 1. 游戏恢复药品清单

游戏中的恢复药品分为以下几类，均在`plugins/xiuxian_game/data/items.yaml`中定义：

**固定值恢复(初级)**:
- `heal_potion` (回春散): 恢复40HP, 价格100, effect_type: RESTORE_HP
- `spirit_herb` (凝神草): 恢复40MP, 价格100, effect_type: RESTORE_MP

**固定值恢复(中级)**:
- `blood_pact` (血契丹): 恢复120HP, 价格1000, effect_type: RESTORE_HP
- `yin_grass` (阴冥草): 恢复120MP, 价格500, effect_type: RESTORE_MP

**百分比恢复(高级丹药)**:
- `life_recovery_elixir` (回生丹): 恢复30%HP, 价格80000, 每日限100次
- `soul_recovery_elixir` (凝魂丹): 恢复30%MP, 价格80000, 每日限100次
- `great_life_recovery_elixir` (大回生丹): 恢复60%HP, 价格150000, 每日限100次
- `great_soul_recovery_elixir` (大凝魂丹): 恢复60%MP, 价格150000, 每日限100次

**复合恢复(活动限定)**:
- `knocker_anxiangx` (安神线香): 恢复20%HP + 10%MP, 价格200, effect_type: RESTORE_HP_MP_PERCENT

**复活药品**:
- `revive_potion` (仿制还魂丹): 复活并恢复30%状态, 价格50000, effect_type: REVIVE

#### 2. 背包添加物品方法

**核心方法位置**: `plugins/xiuxian_game/models/inventory.py:316-413`

**方法签名**:
```python
@staticmethod
async def add_item(
    session,               # 数据库会话(AsyncSession)
    player_id: str,       # 玩家ID
    template_id: str,     # 物品item_id(items.yaml中的item_id)
    quantity: int = 1,    # 数量(默认1)
    durability: int = None # 耐久度(装备专用)
) -> bool
```

**Repository封装**: `plugins/xiuxian_game/infrastructure/repositories/item_repository.py:146-160`
```python
async def add_item(
    self,
    player_id: str,
    item_id: str,
    quantity: int = 1
) -> None
```

**使用示例**:
```python
# 直接使用静态方法
await ItemInstance.add_item(session, player.id, "heal_potion", 5)

# 通过Repository
item_repo = ItemRepository(session)
await item_repo.add_item(player.id, "blood_pact", 3)
```

**关键特性**:
- 装备类型不占背包格子,普通物品每格最多堆叠100个(STACK_SIZE)
- 自动检查背包容量(含月卡加成)
- 自动堆叠到已有物品,超出限制自动拆分新格子
- 背包满时抛出ValueError异常,不会部分添加
- 调用flush()确保物品立即可见

#### 3. AI对话交互完整流程

**入口**: `plugins/xiuxian_game/world/npc_interaction.py:513-761` (`handle_ai_dialogue_interaction`)

**流程图**:
```
1. 玩家发送命令【交互 NPC名 对话内容】
   ↓
2. handle_npc_interaction 解析命令,匹配NPC
   ↓
3. handle_npc_type_interaction 检查ai_enabled标志
   ↓ (ai_enabled=True)
4. handle_ai_dialogue_interaction 核心处理:
   ├─ 初始化服务(AIDialogueService, NPCFavorabilityService, Repositories)
   ├─ 获取NPC人设(PersonalityManager)
   ├─ 获取好感度记录(初始值从npc.extra_data.base_favorability)
   ├─ 获取对话历史(最近10轮)
   ├─ 分析玩家情感(analyze_dialogue_sentiment)
   ├─ 获取长期记忆(最近3次总结+5个重要事件)
   ├─ 构建上下文(位置、玩家信息、情感分析、长期记忆)
   ├─ 发送"正在思考..."提示
   ├─ 调用AI生成回复(generate_dialogue)
   │  ├─ 构建系统提示词(personality.build_system_prompt)
   │  ├─ 构建messages列表(system + 历史对话 + 当前问题)
   │  ├─ 调用AI API(_call_ai_with_fallback)
   │  │  ├─ 尝试主provider(zhipu)
   │  │  └─ 失败时尝试fallback(ai302)
   │  ├─ 提取回复: result['choices'][0]['message']['content']
   │  ├─ 验证回复质量(长度、非空)
   │  └─ 返回(npc_response: str, tokens_used: int)
   ├─ 计算好感度变化(get_favorability_change_by_interaction_type)
   ├─ 更新好感度(add_interaction)
   ├─ 保存对话历史(NPCDialogueHistory对象)
   ├─ 触发异步总结任务(后台,不阻塞)
   └─ 格式化输出并发送给玩家
      ├─ 显示上次对话(最后1条)
      ├─ 显示当前对话(玩家输入 + AI回复)
      ├─ 显示好感度变化(带emoji图标)
      ├─ 显示关系等级、互动次数
      ├─ 显示门槛突破提示
      └─ 调用interact_cmd.finish()发送消息
```

**AI生成回复后的处理流程**:
1. **提取回复文本**: 直接从API响应中提取`choices[0].message.content`
2. **验证质量**: 检查长度(10-200字符)和非空
3. **失败降级**: 验证失败返回基于好感度的预设文本
4. **直接使用**: AI回复作为纯文本直接显示,无结构化解析
5. **格式化输出**: 包裹在Markdown风格的消息框中,添加emoji和好感度信息
6. **发送给玩家**: 调用`interact_cmd.finish(message_add_head(...))`发送

**返回格式**:
- AI生成的`npc_response`为纯文本字符串
- 无JSON解析、无特殊标记提取
- 仅对历史对话进行长度截取(防止过长)
- 添加emoji、好感度、关系等级等元信息后发送

#### 4. AI对话返回文本的处理机制

**结构化解析**: 无，AI返回的文本直接作为NPC对话内容使用

**文本处理流程**:
1. **AI返回** (行100-101): `result['choices'][0]['message']['content'].strip()`
   - 格式: 纯文本字符串
   - 示例: "你好呀，今天感觉怎么样？有什么需要帮助的吗？"

2. **质量验证** (行107-109): 调用`_validate_response(response)`
   - 检查长度: 10-200字符
   - 检查非空: `response.strip()` 不为空
   - 失败时使用预设回复

3. **直接存储** (行640-651): 作为`npc_response`字段存入数据库
   - 保存到`NPCDialogueHistory`对象
   - 字段类型: 纯文本字符串

4. **格式化显示** (行704-706):
   ```python
   lines.append("🗨️ 当前对话：")
   lines.append(f"  【你】: {question}")
   lines.append(f"  【{npc.name}】: {npc_response}")
   ```
   - AI返回的文本直接插入对话框
   - 无额外解析或转换

5. **历史对话截取** (行696-700):
   ```python
   player_text = last_dialogue.player_input[:30] + "..."
   npc_text = last_dialogue.npc_response[:40] + "..."
   ```
   - 仅对历史对话进行长度截取
   - 当前对话不截取

**结论**: AI返回的文本是纯自然语言字符串，系统不进行任何结构化解析(如JSON提取、关键词识别等)，直接作为NPC的对话内容展示给玩家。所有结构化信息(好感度变化、关系等级等)由Python代码逻辑计算并添加到输出消息中。

---

## conclusions

1. **恢复药品分级明确**: 游戏包含9种主要恢复药品,分为固定值(40/120HP或MP)、百分比(30%/60%)和复合恢复(20%HP+10%MP)三类,价格从100到150000金币不等。

2. **背包系统设计合理**: 采用ItemInstance静态方法`add_item`处理物品添加,自动处理堆叠(每格100个)、容量检查(含月卡加成)和装备特殊逻辑(不占背包)。Repository层提供DI架构封装。

3. **AI对话流程完善**: NPC AI对话系统包含12个核心步骤,从服务初始化到异步总结任务,实现了完整的对话生成、好感度管理、长期记忆和降级策略。关键特性:
   - 多provider降级机制(智谱AI → 302.ai)
   - 情感分析驱动好感度变化
   - 长期记忆系统(最近3次总结+5个重要事件)
   - 异步总结任务(每20轮对话触发,不阻塞用户)

4. **AI文本无结构化解析**: AI返回的对话文本是纯自然语言字符串,系统直接使用不进行JSON解析或关键词提取。所有结构化信息(好感度、关系等级)由Python代码逻辑计算并添加到输出消息中,与AI生成的文本分离。

5. **异常处理策略清晰**: NPC交互系统特别处理NoneBot2的FinishedException(流程控制异常),不应被捕获。AI对话失败时自动降级到预设回复,确保用户体验不中断。

---

## relations

1. **物品配置与数据模型**: `items.yaml` → `ItemConfig` → `ItemInstance`
   - items.yaml定义物品模板(item_id, effect_type, effect_params等)
   - ItemConfig类解析YAML数据并提供属性访问
   - ItemInstance使用config.items_config["by_id"]获取模板配置

2. **背包添加流程**: `ItemInstance.add_item` → `ItemRepository.add_item`
   - 静态方法作为底层实现,处理堆叠、容量检查、数据库操作
   - Repository封装静态方法,提供DI架构接口
   - 调用方使用Repository或直接调用静态方法

3. **NPC交互命令链**: `interact_cmd` → `handle_npc_interaction` → `handle_npc_type_interaction` → `handle_ai_dialogue_interaction`
   - interact_cmd接收用户命令并解析参数
   - handle_npc_interaction匹配NPC并调用类型分发器
   - handle_npc_type_interaction检查ai_enabled标志并路由到AI处理
   - handle_ai_dialogue_interaction执行完整AI对话流程

4. **AI对话服务依赖**: `handle_ai_dialogue_interaction` 依赖多个服务
   - `AIDialogueService`: 调用AI API生成回复
   - `NPCFavorabilityService`: 计算和更新好感度
   - `PersonalityManager`: 提供NPC人设
   - `DialogueSummarizationService`: 管理长期记忆和对话总结
   - `NPCDialogueHistoryRepository`: 存储对话历史

5. **AI生成流程**: `generate_dialogue` → `_call_ai_with_fallback` → `call_zhipu_api/call_302ai_api`
   - generate_dialogue构建messages列表和系统提示词
   - _call_ai_with_fallback实现多provider降级机制
   - 调用具体API函数(智谱AI或302.ai)
   - 提取回复文本并验证质量

6. **数据持久化链**: AI对话 → `NPCDialogueHistory` → 数据库 → 异步总结任务
   - 对话历史保存到NPCDialogueHistory表
   - 包含player_input, npc_response, favorability_change, ai_tokens_used等字段
   - 后台异步任务定期总结对话(每20轮)并存入NPCLongTermMemory表

7. **好感度系统**: 情感分析 → 好感度变化计算 → 互动记录 → 关系等级更新
   - analyze_dialogue_sentiment分析玩家情感(very_negative/negative/positive/neutral)
   - get_favorability_change_by_interaction_type计算好感度变化(含递减机制)
   - add_interaction记录互动并更新好感度和total_interactions计数
   - 关系等级根据好感度阈值(20/40/60/80)动态更新
