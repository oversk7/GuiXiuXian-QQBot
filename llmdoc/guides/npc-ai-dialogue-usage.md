# NPC AI对话系统使用指南

本指南介绍如何使用NPC AI对话系统的核心功能（方案2实施版本）。

## 前置条件

1. 确认已部署NPC AI对话系统（查看 `/architecture/npc-ai-dialogue-implementation.md`）
2. 确认智谱AI API密钥已配置（`data/config.yaml:ai_dialogue.zhipu.api_key`）
3. 确认PersonalityManager已加载人设配置（bot启动日志）

## 管理员操作

### Step 1: 为NPC启用AI对话

```
命令: 【启用NPC AI <NPC名称>】

示例: 【启用NPC AI 武安勇】

输出:
✅ 已为NPC「武安勇」启用AI对话

配置信息:
- AI模型: GLM-4.5-Flash
- 初始好感度: 50
- 启用状态: ✅ 已启用

玩家现在可以通过【交互 武安勇】与该NPC进行AI对话。
```

**工作原理**:
- 设置 `npc.extra_data["ai_enabled"] = True`
- 设置 `npc.extra_data["ai_model"] = "GLM-4.5-Flash"`
- 为该NPC创建初始好感度记录（默认50）

### Step 2: 查看NPC AI状态

```
命令: 【查看NPC AI <NPC名称>】

示例: 【查看NPC AI 武安勇】

输出:
📊 NPC「武安勇」AI配置
━━━━━━━━━━━━━
🤖 AI状态: ✅ 已启用
📦 AI模型: GLM-4.5-Flash
💖 初始好感度: 50
📝 人设配置: 已加载（镇上的大块头）
```

### Step 3: 禁用NPC AI对话（可选）

```
命令: 【禁用NPC AI <NPC名称>】

示例: 【禁用NPC AI 武安勇】

输出:
✅ 已为NPC「武安勇」禁用AI对话
该NPC将恢复使用默认交互方式。
```

## 玩家操作

### Step 4: 与NPC进行AI对话

```
前提: 玩家需要在NPC所在的地点

命令: 【交互 <NPC名称>】

示例: 【交互 武安勇】

输出:
👤 武安勇
━━━━━━━━━━━━━
💬 嘿呀，道友你好！俺是武安勇，镇上的大块头。有什么需要帮忙的尽管说，俺虽然粗鲁了点，但心地还是挺好的！

💖 好感度: 52/100
🔗 关系: 熟识
━━━━━━━━━━━━━
💡 提示: 多次交互可以提升好感度
```

**对话记录**:
- 每次对话都会保存到 `npc_dialogue_history` 表
- AI会考虑最近10轮对话历史（保持上下文连贯）

**好感度变化**:
- 基于对话内容的情感分析自动调整：
  - 极度负面（辱骂）: -10 好感度
  - 负面（不友好）: -3 好感度
  - 正面（友好）: +3 好感度
  - 中性（普通）: +1 好感度
- 好感度影响NPC的态度和回复风格
- 存在递减机制，高好感度时日常对话效果降低

### Step 5: 查看对话历史

```
命令: 【对话历史 <NPC名称>】

示例: 【对话历史 武安勇】

输出:
📖 与【武安勇】的对话历史
━━━━━━━━━━━━━
显示最近10条记录：

【1. 12-06 14:30】
  【你】: 你好
  【武安勇】: 嘿呀，道友你好！
  好感度: +3 → 53/100

【2. 12-06 14:35】
  【你】: 你最近怎么样
  【武安勇】: 俺挺好的，谢谢关心！
  好感度: +3 → 56/100

━━━━━━━━━━━━━
当前好感度: 56/100 (友好)
总互动次数: 2次
```

**功能说明**:
- 显示与指定NPC的最近10轮对话
- 每条记录包含时间、对话内容、好感度变化
- 可用别名: 【查看对话 武安勇】或【对话记录 武安勇】

### Step 6: 查看好感度等级

**关系等级划分**:
| 好感度 | 关系等级 | NPC态度 |
|-------|---------|---------|
| 0-20 | 陌生人 | 冷漠、敷衍 |
| 21-40 | 熟识 | 友好、配合 |
| 41-60 | 友好 | 热情、主动 |
| 61-80 | 亲密 | 亲切、信任 |
| 81-100 | 知心 | 忠诚、无条件 |

**示例对话（不同好感度）**:

**好感度20（陌生人）**:
```
玩家: 【交互 武安勇】
NPC: "嗯，有事吗？俺很忙的。"
```

**好感度50（友好）**:
```
玩家: 【交互 武安勇】
NPC: "嘿呀，道友你好！俺是武安勇，有什么需要帮忙的尽管说！"
```

**好感度85（知心）**:
```
玩家: 【交互 武安勇】
NPC: "兄弟你来了！俺这辈子能遇到你这样的好友，真是三生有幸啊！"
```

## 高级功能

### 长期记忆系统（新增 2025-12-07）

**三层记忆架构原理**:

NPC不会记住所有对话细节，而是采用三层记忆模拟真实人类记忆：

```
第1层（短期记忆）: 最近10轮原始对话
  - 玩家: "你好"
  - NPC: "嘿呀，道友你好！"
  ↓
第2层（中期记忆）: 最近3次AI总结（每次总结20-30轮）
  - "这段时间玩家经常向我询问修炼建议，我们聊了很多关于战斗技巧的话题"
  ↓
第3层（长期记忆）: 最近5个重要事件
  - 事件1: 玩家赠送珍贵礼物 (+10好感度)
  - 事件2: 玩家承诺帮助完成任务
  - 事件3: 玩家与我发生激烈争执 (-10好感度)
```

**自动总结触发机制**:
- **触发条件**: 每20-30轮对话自动触发一次AI总结
- **异步执行**: 总结在后台进行，不阻塞玩家交互
- **AI分析**: 智谱AI自动提取对话要点和关键事件
- **事件分类**: gift（礼物）、quest（任务）、promise（承诺）、conflict（冲突）、emotion（情感变化）

**示例**:

玩家与"武安勇"对话50轮后：
```
短期记忆（最近10轮）:
  - 第41轮: 玩家问"最近过得怎么样？"
  - 第42轮: NPC说"挺好的，谢谢关心！"
  ...

中期记忆（3次总结）:
  - 总结1（第1-25轮）: "玩家初次与我相识，询问了我的背景和经历"
  - 总结2（第26-50轮）: "我们聊了修炼心得，玩家似乎对战斗技巧很感兴趣"

长期记忆（5个事件）:
  - 事件1: 玩家第10轮对话时承诺帮我找工作（重要性8/10）
  - 事件2: 玩家第35轮对话时夸奖我是好人（重要性5/10，+3好感度）
```

**查看长期记忆（管理员）**:

```sql
-- 查看玩家与某个NPC的长期记忆
SELECT
    memory_type,
    content,
    event_type,
    importance_score,
    created_at,
    weight
FROM npc_long_term_memory
WHERE npc_id = ? AND player_id = ?
ORDER BY created_at DESC
LIMIT 20;

-- 查看总结检查点
SELECT
    last_summarized_dialogue_id,
    total_dialogues_summarized,
    last_summary_time,
    next_summary_threshold
FROM npc_dialogue_summary_checkpoint
WHERE npc_id = ? AND player_id = ?;
```

**长期记忆管理**:

1. **记忆衰减**: 随着时间推移，老记忆的权重会自动降低（decay_rate=0.95/天）
   - 新记忆: weight=1.0
   - 30天后: weight=0.21
   - 60天后: weight=0.05（接近遗忘）

2. **清理策略**:
   ```sql
   -- 清理权重过低的记忆（管理员手动执行）
   DELETE FROM npc_long_term_memory
   WHERE weight < 0.1;

   -- 清理180天前的记忆
   DELETE FROM npc_long_term_memory
   WHERE created_at < DATE_SUB(NOW(), INTERVAL 180 DAY);
   ```

3. **手动触发总结**（调试用）:
   ```python
   # 管理员可以在代码中手动触发总结
   from plugins.xiuxian_game.dialogue.dialogue_summarization_service import DialogueSummarizationService

   summary_service = DialogueSummarizationService(memory_repo, dialogue_repo)
   await summary_service.summarize_dialogues(
       npc_id=1,
       player_id="123456",
       npc_personality=personality
   )
   ```

**性能优化**:
- Token消耗减少: 5-10%（对话越多优化越明显）
- 异步后台总结: 不影响玩家交互体验
- 索引优化: 长期记忆查询<50ms

### 好感度递减与门槛系统

**递减机制说明**:
- NPC好感度系统采用**递减效应设计**，模拟真实人际关系的发展规律
- 日常对话在高好感度时效果大幅降低，需要重大事件（礼物、任务、战斗）突破

**等级门槛**:
| 好感度 | 关系等级 | 日常对话效果 | 如何突破 |
|-------|---------|------------|---------|
| 0-20 | 陌生人 | 100%效果 | 多次对话即可 |
| 20-40 | 熟识 | 80%效果 | 需要更多交流 |
| 40-60 | 友好 | 60%效果 | 需要赠送礼物或完成任务 |
| 60-80 | 亲密 | 40%效果 | 需要共同战斗或完成重要任务 |
| 80-100 | 知心 | 20%效果 | 需要经历生死考验 |

**门槛附近效果**:
- 距离门槛≤2点时: 日常对话几乎无效（基础变化≤3时直接归零）
- 距离门槛3-5点时: 日常对话效果减半
- 游戏会在接近门槛时给出提示，例如:
  ```
  💡 提示: 即将突破至【友好】关系，需要赠送礼物或完成任务才能更进一步
  ⚠️ 日常对话已无法增进关系，需要特殊互动
  ```

**重大事件（未来实现）**:
- 赠送礼物: +10 好感度（可突破门槛）
- 完成任务: +15 好感度（可突破门槛）
- 救命之恩: +20 好感度（可突破所有门槛）
- 并肩作战: +5 好感度（可部分突破）
- 战斗失败（NPC死亡）: -20 好感度
- 背叛行为: -30 好感度

**情感分析系统**:
- 系统会自动分析玩家对话内容的情感倾向
- **正面词汇**（喜欢、爱、好、棒、谢谢等）: +3 好感度
- **中性对话**（无特殊情感）: +1 好感度
- **负面词汇**（讨厌、烦、笨、差劲等）: -3 好感度
- **极度负面**（辱骂、攻击性词汇）: -10 好感度

**对话示例**:
```
# 正面对话
玩家: 【交互 武安勇】你人真好！
NPC: 哈哈，兄弟你过奖了！俺只是做了该做的事。
好感度: 52/100 (📈 +3)

# 中性对话
玩家: 【交互 武安勇】最近怎么样？
NPC: 还不错，每天练练拳脚，干干活。
好感度: 53/100 (📈 +1)

# 负面对话
玩家: 【交互 武安勇】你真笨
NPC: 你...你说什么？俺可不笨！
好感度: 50/100 (📉 -3)

# 极度负面对话
玩家: 【交互 武安勇】你是傻子
NPC: 你！！！太过分了！俺不想跟你说话！
好感度: 40/100 (📉 -10)
```

### 防刷好感度机制（新增 2025-12-07）

**问题**: 玩家可能通过无意义刷屏快速提升好感度

**防刷规则**:

| 规则 | 触发条件 | 好感度变化 | 示例 |
|-----|---------|-----------|------|
| 敷衍检测 | ≤3字符 | 0 | "嗯"、"啊"、"哦" |
| 阶段性递减 | 好感度<40，中性对话 | +1 | "你好吗？"（新手期有效） |
| 阶段性递减 | 好感度≥40，中性对话 | 0 | "你好吗？"（高好感度无效） |
| 空消息 | 无对话内容 | 0 | 防止空消息刷屏 |

**玩家体验**:
```
# 低好感度时（<40）
玩家: 【交互 武安勇】最近怎么样？
NPC: 还行吧。
好感度: 35/100 (📈 +1) ✅ 中性对话有效

# 高好感度时（≥40）
玩家: 【交互 武安勇】最近怎么样？
NPC: 挺好的，谢谢关心！
好感度: 42/100 (➖ ±0) ⚠️ 需要正面对话

# 敷衍回复
玩家: 【交互 武安勇】嗯
NPC: 嗯，怎么了？
好感度: 42/100 (➖ ±0) ⚠️ 敷衍回复无效

# 正面对话
玩家: 【交互 武安勇】你人真好！
NPC: 哈哈，兄弟你过奖了！
好感度: 45/100 (📈 +3) ✅ 正面对话有效
```

**突破高好感度瓶颈**:
- 好感度≥40时，需要：
  - 正面词汇（喜欢、爱、好、棒、谢谢等）
  - 或重大事件（礼物+10、任务+15、战斗+5等）
- 结合递减机制，形成完整防刷体系

### 人设系统

**查看NPC人设**:
- NPC人设配置文件: `data/npc_personalities.yaml`
- **11个预设人设**（Phase 3扩展 2025-12-07）:
  - 4个基础NPC（武安勇、铁匠老王、药铺掌柜、司长曹延华）
  - 2个商人NPC（商人李掌柜、商人王五）
  - 5个工匠NPC（百工坊宗师、心魔巧匠、幽魂锻师、疯狂技师、炼魂大师）

**武安勇人设示例**:
```yaml
武安勇:
  name: "武安勇"
  role: "镇上的大块头"
  pronouns: ["俺", "本大爷"]  # 自称
  speech_patterns: ["粗犷", "直爽", "豪迈"]  # 语气
  key_words: ["嘿呀", "果然", "怎么了", "兄弟"]  # 口头禅
  personality_traits:
    loyalty: 80       # 忠诚度
    cheerfulness: 70  # 开朗度
    aggressiveness: 60 # 好斗度
  background: "出身贫寒，靠蛮力讨生活，后遇到道友改变人生。"
  behavioral_rules:
    - "对给他东西的人很感激"
    - "喜欢参加战团切磋"
    - "会认真执行跟随者的指令"
```

**添加新NPC人设**:
1. 编辑 `data/npc_personalities.yaml`
2. 添加新NPC配置（参考现有11个示例）
3. 重启bot或手动重载配置

**人设分类**:
- **基础NPC**: 适用于通用角色（守卫、市民、教官等）
- **商人NPC**: 适用于市集商人（精明型、朴实型）
- **工匠NPC**: 适用于不同主题工匠（宗师级、怪谈、幽魂、疯狂、终极）

**新增工匠主题人设** (2025-12-07):
- **心魔巧匠**: 适合金陵地图，怪谈风格，阴郁神秘
- **幽魂锻师**: 适合云岭地图，幽魂风格，飘忽淡然
- **疯狂技师**: 适合摩配镇地图，疯狂风格，兴奋不羁
- **炼魂大师**: 适合风雪镇地图，终极风格，威严高傲

### 长期记忆管理（新增 2025-12-07）

**查看长期记忆（管理员）**:

```sql
-- 查看玩家与某个NPC的所有长期记忆
SELECT
    id,
    memory_type,
    content,
    event_type,
    importance_score,
    weight,
    created_at
FROM npc_long_term_memory
WHERE npc_id = 1 AND player_id = '123456'
ORDER BY created_at DESC;

-- 查看重要事件（按重要性排序）
SELECT *
FROM npc_long_term_memory
WHERE npc_id = 1 AND player_id = '123456' AND memory_type = 'event'
ORDER BY importance_score * weight DESC
LIMIT 10;

-- 查看AI总结
SELECT *
FROM npc_long_term_memory
WHERE npc_id = 1 AND player_id = '123456' AND memory_type = 'summary'
ORDER BY created_at DESC
LIMIT 5;
```

**清理长期记忆**:

```sql
-- 1. 清理权重过低的记忆（接近遗忘）
DELETE FROM npc_long_term_memory
WHERE weight < 0.1;

-- 2. 清理180天前的记忆
DELETE FROM npc_long_term_memory
WHERE created_at < DATE_SUB(NOW(), INTERVAL 180 DAY);

-- 3. 清理所有NPC的低权重记忆（批量清理）
DELETE FROM npc_long_term_memory
WHERE weight < 0.1 AND created_at < DATE_SUB(NOW(), INTERVAL 60 DAY);
```

**手动触发记忆衰减**:

```python
# 管理员可以定期执行记忆衰减任务（建议每周一次）
from plugins.xiuxian_game.infrastructure.repositories.npc_long_term_memory_repository import NPCLongTermMemoryRepository

async with safe_session() as session:
    memory_repo = NPCLongTermMemoryRepository(session)
    await memory_repo.decay_old_memories(days=7, decay_rate=0.95)
    await session.commit()
```

**监控存储增长**:

```sql
-- 查看长期记忆总数
SELECT COUNT(*) AS total_memories FROM npc_long_term_memory;

-- 按NPC统计记忆数量
SELECT npc_id, COUNT(*) AS memory_count
FROM npc_long_term_memory
GROUP BY npc_id
ORDER BY memory_count DESC;

-- 查看存储占用（估算）
SELECT
    ROUND(SUM(LENGTH(content)) / 1024 / 1024, 2) AS size_mb
FROM npc_long_term_memory;
```

### 对话历史管理

**查看对话历史**:
- 数据库表: `npc_dialogue_history`
- 保留时间: 30天（`config.yaml:ai_dialogue.history.ttl_days`）
- AI上下文: 最近10轮对话

**清理对话历史**（管理员）:
```sql
-- 清理30天前的对话记录
DELETE FROM npc_dialogue_history
WHERE created_at < DATE_SUB(NOW(), INTERVAL 30 DAY);

-- 清理所有对话历史（慎用）
TRUNCATE TABLE npc_dialogue_history;
```

### 成本控制

**查看AI调用成本**:
- 日志文件: 每次AI调用都会记录token消耗
- 预算控制: `config.yaml:ai_dialogue.cost_control.daily_budget_usd`

**限流配置**:
- 每玩家每小时: 30次对话（`rate_limit_per_player_per_hour`）
- 单次对话token上限: 300 tokens（`max_tokens_per_dialogue`）

## 故障排除

### 问题1: NPC不回复

**原因**: AI对话未启用或API密钥配置错误

**解决方案**:
1. 检查NPC是否启用AI: `【查看NPC AI <NPC名称>】`
2. 检查API密钥: `data/config.yaml:ai_dialogue.zhipu.api_key`
3. 查看bot启动日志: `[NPCDialogue] 成功加载 X 个NPC人设配置`

### 问题2: AI回复质量差

**原因**: NPC人设配置不完整或提示词不清晰

**解决方案**:
1. 检查 `npc_personalities.yaml` 中NPC配置
2. 补充完整的 `background`、`behavioral_rules`、`speech_patterns`
3. 重启bot使配置生效

### 问题3: 好感度不变化

**原因**: 对话历史未正确保存

**解决方案**:
1. 检查数据库连接
2. 查看 `npc_favorability` 表是否有记录
3. 查看日志中是否有错误信息

### 问题4: AI API调用失败

**原因**: 网络问题、API限流、密钥无效

**降级方案**: 系统会自动使用预设对话回复，不影响玩家交互

**检查日志**:
```
logger.error(f"AI对话生成失败: {e}")
```

## 配置调优

### 优化AI回复质量

**调整temperature参数**:
```yaml
# config.yaml
ai_dialogue:
  zhipu:
    temperature: 0.1  # 0=严格一致，1=富有创意
```

**建议值**:
- 0.1: 严肃NPC（守卫、教官）
- 0.3: 中立NPC（商人、工匠）
- 0.5: 活泼NPC（武安勇、市井NPC）

### 优化成本

**减少token消耗**:
1. 减少对话历史轮数: `history.max_rounds: 10 → 5`
2. 减少单次token上限: `max_tokens: 300 → 200`
3. 启用缓存（未来功能）

**启用限流**:
```yaml
cost_control:
  enable_rate_limit: true
  rate_limit_per_player_per_hour: 30  # 每玩家每小时30次
```

## 最佳实践

### 1. 人设设计原则

- **一致性**: NPC的性格、语言风格要始终一致
- **差异化**: 不同NPC要有明显区别（避免千篇一律）
- **深度**: 提供详细的背景故事和行为准则

### 2. 好感度运营

- **梯度设计**: 不同好感度等级有明显差异
- **奖励机制**: 高好感度可以解锁特殊功能（未来扩展）
- **负面惩罚**: 预留负面行为减少好感度的机制（未来扩展）

### 3. 成本控制

- **监控**: 定期检查AI调用日志和成本
- **预算**: 设置合理的每日预算上限
- **降级**: 确保AI失败时有备用方案

### 4. 玩家体验

- **响应速度**: AI回复应在3秒内完成
- **对话长度**: 控制NPC回复在100字以内（避免刷屏）
- **上下文**: 确保AI能记住最近的对话（10轮历史）

---

**相关文档**:
- 实施记录: `/llmdoc/architecture/npc-ai-dialogue-implementation.md`
- 完整架构: `/llmdoc/architecture/dialogue-npc-system.md`（包含未实现功能）
- 数据模型: `/llmdoc/reference/data-models.md`
