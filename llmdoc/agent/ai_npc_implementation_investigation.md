# AI NPC实现方案调研报告

**调研日期**: 2025-12-01
**调研范围**: 项目现有AI基础设施、NPC系统、技术选型建议、实施方案
**调研目标**: 为项目AI NPC系统提供完整的实现路径

---

## Code Sections (The Evidence)

### 现有AI基础设施

- `plugins/xiuxian_game/ai_guide.py` (`call_zhipu_api`): 已集成智谱AI API (GLM-4.5-Flash)，用于AI引导系统
- `plugins/xiuxian_game/ai_guide.py:23-55`: 异步HTTP调用智谱AI，使用aiohttp，支持超时控制
- `plugins/xiuxian_game/ai_guide.py:28`: API密钥硬编码在代码中
- `plugins/xiuxian_game/entertainment/daily_apis.py:5`: 已安装requests库，用于外部API调用
- `pyproject.toml:1-18`: 项目依赖配置文件，未包含AI相关依赖

### NPC系统架构

- `plugins/xiuxian_game/models/npc.py` (NPC Model): NPC数据模型，包含76-80行的extra_data字段（JSON存储）
- `plugins/xiuxian_game/models/npc.py:16-25` (NPCType): NPC类型枚举，包含MERCHANT、CRAFTSMAN、EMPLOYER、GHOST、NORMAL等7种类型
- `plugins/xiuxian_game/world/npc_service_new.py` (NPCService): NPC业务服务类（DI架构）
- `plugins/xiuxian_game/world/npc_service_new.py:417-506`: AI Agent NPC相关预留方法（7个方法）

### AI接口预留

- `plugins/xiuxian_game/world/npc_service_new.py:419-431` (`is_ai_enabled`): 检查NPC是否启用AI对话，读取extra_data["ai_enabled"]
- `plugins/xiuxian_game/world/npc_service_new.py:433-445` (`get_ai_personality`): 获取NPC的AI性格配置
- `plugins/xiuxian_game/world/npc_service_new.py:447-459` (`get_ai_model`): 获取NPC使用的AI模型，默认"glm-4.5-flash"
- `plugins/xiuxian_game/world/npc_service_new.py:461-473` (`get_ai_forbidden_topics`): 获取NPC禁忌话题列表
- `plugins/xiuxian_game/world/npc_service_new.py:475-505` (`enable_ai_for_npc`): 为NPC启用AI对话，更新extra_data配置

### 现有对话机制

- `plugins/xiuxian_game/world/npc_interaction.py:248-263` (`handle_generic_interaction`): 通用NPC交互处理
- `plugins/xiuxian_game/world/npc_interaction.py:266-311` (`handle_neutral_npc_interaction`): 中立NPC交互，支持预设对话列表（extra_data["dialogues"]）
- `plugins/xiuxian_game/world/npc_interaction.py:251`: 判断是否为中立NPC：extra_data.get("is_neutral") and extra_data.get("dialogues")
- `plugins/xiuxian_game/world/npc_interaction.py:270-284`: 对话选择逻辑：70%按顺序，30%随机

### 数据存储结构

- `plugins/xiuxian_game/models/npc.py:76-80` (extra_data): JSON字段，支持灵活扩展
- `plugins/xiuxian_game/models/npc.py:39`: npc_id字段，String(64)，唯一索引
- `plugins/xiuxian_game/models/npc.py:42-44`: 基本信息：name、description、npc_type
- `plugins/xiuxian_game/models/db.py:47-66` (safe_session): 自动提交会话管理器，用于NPC数据修改

---

## Report (The Answers)

### result

#### 1. 现有AI基础设施分析

**✅ 已集成智谱AI**：
- 项目已在`ai_guide.py`中成功集成智谱AI GLM-4.5-Flash模型
- 使用aiohttp异步调用API，性能良好
- 已有完整的错误处理和超时控制机制（30秒超时）

**⚠️ 存在的问题**：
- **API密钥硬编码**：`ai_guide.py:28`直接写在代码中，存在安全风险
- **缺少配置管理**：未使用项目现有的config.yaml或环境变量管理API密钥
- **依赖未声明**：pyproject.toml中未包含aiohttp依赖（可能通过其他库间接安装）

**✅ 无其他AI服务集成**：
- 未发现OpenAI、Anthropic、通义千问等其他LLM服务
- 无API密钥配置文件（如.env）
- 专一使用智谱AI，避免服务商切换成本

#### 2. NPC系统当前状态

**✅ DI架构完整**：
- NPCService已完成DI重构，使用Repository模式
- 预留7个AI相关方法，接口设计合理
- extra_data字段设计灵活，支持AI配置存储

**✅ AI配置结构预留**：
```json
{
  "ai_enabled": true,
  "ai_model": "glm-4.5-flash",
  "ai_personality": {
    "name": "铁匠老王",
    "role": "工匠",
    "traits": ["爽朗", "健谈"],
    "knowledge_domain": ["锻造", "装备升阶"]
  },
  "ai_forbidden_topics": ["政治", "敏感内容"],
  "ai_response_style": {
    "length": "medium",
    "tone": "friendly"
  }
}
```

**⚠️ 缺少AI对话逻辑**：
- 预留方法仅读取配置，未实现实际AI调用
- 未集成到npc_interaction.py的交互流程中
- 需要实现对话历史管理和上下文记忆

**✅ 现有对话机制**：
- 中立NPC支持预设对话列表（extra_data["dialogues"]）
- 70%顺序+30%随机的对话选择策略
- 可作为AI对话的降级方案

#### 3. 类似的AI对话功能

**✅ AI引导系统**（`ai_guide.py`）：
- 使用智谱AI GLM-4.5-Flash模型
- 系统提示词包含完整的游戏指令知识库（943行）
- 上下文管理：玩家信息（昵称、等级、UID）
- 消息格式化：150字以内简洁回复
- 安全控制：仅回答游戏相关问题，忽略剧情状态玩家

**✅ 管理员SQL查询**（`ai_guide.py:473-533`）：
- 自然语言转SQL查询，支持UPDATE操作
- 危险操作检测：禁止DELETE、DROP、INSERT等
- 结果格式化：AI整理查询结果为中文报告

**💡 可复用经验**：
- 系统提示词设计模式
- 上下文管理策略
- 安全控制机制
- 消息格式化方法

#### 4. 技术选型建议

##### 方案A：智谱AI GLM-4.5-Flash（推荐）

**优势**：
- ✅ **零迁移成本**：项目已集成，代码可复用
- ✅ **响应速度快**：Flash模型专为低延迟优化
- ✅ **成本较低**：0.0001元/千tokens（输入），0.0002元/千tokens（输出）
- ✅ **中文优化**：对中文游戏场景理解更好
- ✅ **开发友好**：已有成功案例（ai_guide.py）

**劣势**：
- ⚠️ 模型能力弱于GPT-4，复杂对话可能质量下降
- ⚠️ API稳定性依赖国内服务商

**费用估算**（每日1000次对话）：
- 平均每次对话：系统提示500tokens + 用户输入50tokens + 回复150tokens = 700tokens
- 每日费用：1000次 × 0.7K tokens × 0.00015元 ≈ 0.105元/天 ≈ 3.15元/月
- **结论**：极低成本，可忽略

##### 方案B：OpenAI GPT-3.5-turbo（备选）

**优势**：
- ✅ **对话质量高**：生成内容更自然、有趣
- ✅ **API稳定**：国际大厂，服务可靠
- ✅ **生态完善**：大量示例和工具

**劣势**：
- ⚠️ **需要国际网络**：需配置代理或使用中转API
- ⚠️ **成本较高**：0.0015美元/1K tokens（输入），0.002美元/1K tokens（输出）
- ⚠️ **合规风险**：需关注国内API使用政策

**费用估算**（每日1000次对话）：
- 每日费用：1000次 × 0.7K tokens × 0.00175美元 × 7.2人民币 ≈ 8.82元/天 ≈ 264.6元/月
- **结论**：成本显著高于智谱AI（84倍）

##### 方案C：本地LLM（Llama、ChatGLM等）

**优势**：
- ✅ **零API费用**：一次性硬件投入
- ✅ **数据隐私**：完全本地部署
- ✅ **无调用限制**：不受API频率限制

**劣势**：
- ⚠️ **硬件成本高**：需RTX 4090级别GPU（约12000元）
- ⚠️ **响应速度慢**：本地推理延迟2-5秒
- ⚠️ **运维复杂**：需专业知识维护模型
- ⚠️ **模型质量低**：小参数模型对话质量不如云端大模型

**结论**：不适合QQ游戏机器人场景（响应速度要求高）

#### 5. 架构设计草案

##### 5.1 核心组件

```
NPC对话系统
├── AIDialogueService (新增)
│   ├── generate_response() - 生成AI回复
│   ├── build_context() - 构建对话上下文
│   ├── manage_history() - 管理对话历史
│   └── fallback_to_preset() - 降级到预设对话
├── NPCService (扩展)
│   ├── is_ai_enabled() - 已预留
│   ├── get_ai_personality() - 已预留
│   └── interact_with_ai_npc() - 新增AI对话入口
├── DialogueHistoryRepository (新增)
│   ├── save_dialogue() - 保存对话记录
│   ├── get_recent_history() - 获取最近对话
│   └── cleanup_old_history() - 清理过期记录
└── NPC.extra_data (已有)
    ├── ai_enabled - 是否启用AI
    ├── ai_model - 使用的模型
    ├── ai_personality - 性格配置
    └── ai_forbidden_topics - 禁忌话题
```

##### 5.2 数据模型扩展

**新增表：dialogue_history**
```sql
CREATE TABLE dialogue_history (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    player_id VARCHAR(64) NOT NULL,
    npc_id VARCHAR(64) NOT NULL,
    role ENUM('player', 'npc') NOT NULL,
    content TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_player_npc (player_id, npc_id, created_at)
);
```

**扩展NPC.extra_data字段**（无需迁移，JSON灵活扩展）：
- `conversation_history_limit`: 保留对话轮数（默认10轮）
- `ai_response_cache`: 响应缓存配置
- `dialogue_stats`: 对话统计（总对话数、平均长度等）

##### 5.3 系统提示词设计

**基础模板**：
```python
SYSTEM_PROMPT_TEMPLATE = """你是《诡修仙》游戏中的NPC"{npc_name}"，职业是{npc_role}。

性格特点：
{personality_traits}

知识领域：
{knowledge_domain}

当前场景：
- 地点：{location_name}
- 玩家：{player_name}（等级{player_level}）

对话规则：
1. 保持角色一致性，用{response_tone}的语气回复
2. 回复控制在50-150字
3. 涉及游戏功能时，引导玩家使用对应指令（如【锻造】、【市集】）
4. 避免讨论：{forbidden_topics}
5. 适度添加修仙世界观元素（如"道友"、"修为"等）

玩家说：{player_message}

请作为{npc_name}回复："""
```

**个性化示例**：
- **铁匠老王**（工匠NPC）：爽朗健谈，喜欢炫耀手艺，引导玩家升阶装备
- **药铺掌柜**（商人NPC）：精明谨慎，介绍丹药效果，提醒每日服用上限
- **缉邪司教官**（守卫NPC）：严肃正直，讲解战斗技巧，鼓励玩家讨伐鬼怪

##### 5.4 对话流程设计

```
玩家输入 "交互 铁匠老王 你好"
    ↓
NPCService.interact_with_npc()
    ↓
检查 is_ai_enabled(npc) → True
    ↓
AIDialogueService.generate_response()
    ├── 1. 加载NPC personality配置
    ├── 2. 获取最近10轮对话历史
    ├── 3. 构建系统提示词
    ├── 4. 调用智谱AI API
    ├── 5. 检测违规内容
    ├── 6. 保存对话记录
    └── 7. 返回回复
    ↓
格式化输出给玩家
```

**降级机制**：
- API调用失败 → 使用预设对话列表（extra_data["dialogues"]）
- AI响应过慢（>5秒） → 提示"NPC正在思考..."并异步返回
- 违规内容检测 → 使用安全的预设回复

##### 5.5 性能优化策略

**对话历史管理**：
- 仅保留最近10轮对话（约2KB上下文）
- 超过100轮后，自动清理30天前的记录
- 使用数据库索引加速查询（idx_player_npc）

**响应缓存**（可选）：
- 对于常见问题（如"你是谁"、"能做什么"），缓存标准回复
- 缓存键：npc_id + 问题指纹（MD5）
- 缓存时长：1小时
- **效果**：减少API调用，降低成本

**异步处理**：
- 对话历史保存异步化，不阻塞主流程
- API调用超时设为5秒，超时使用降级方案

#### 6. 实施步骤建议

##### Phase 1：基础设施准备（1-2天）

**任务清单**：
1. ✅ 提取ai_guide.py中的`call_zhipu_api`函数为公共服务
2. ✅ 将API密钥迁移到config.yaml或环境变量
3. ✅ 创建AIDialogueService类框架
4. ✅ 创建dialogue_history数据表
5. ✅ 编写DialogueHistoryRepository

**验收标准**：
- API密钥不在代码中硬编码
- dialogue_history表创建成功
- 单元测试：DialogueHistoryRepository的CRUD操作

##### Phase 2：AI对话核心功能（3-4天）

**任务清单**：
1. ✅ 实现AIDialogueService.generate_response()
2. ✅ 设计3个NPC的系统提示词模板
3. ✅ 集成到npc_interaction.py的交互流程
4. ✅ 实现对话历史的加载与保存
5. ✅ 添加违规内容检测（关键词过滤）

**验收标准**：
- 玩家可与AI NPC正常对话
- 对话上下文连贯（能记住前几轮对话）
- 响应时间<3秒（90%情况下）

##### Phase 3：优化与扩展（2-3天）

**任务清单**：
1. ✅ 实现降级机制（API失败时使用预设对话）
2. ✅ 添加响应缓存（可选）
3. ✅ 为10个常用NPC配置AI personality
4. ✅ 添加管理员指令：【启用AI <NPC名>】、【禁用AI <NPC名>】
5. ✅ 编写玩家使用文档

**验收标准**：
- API失败时玩家无感知（自动降级）
- 缓存命中率>30%（如果启用）
- 10个NPC可正常AI对话
- 管理员可动态控制AI开关

##### Phase 4：监控与调优（1-2天）

**任务清单**：
1. ✅ 添加对话统计（每日对话数、平均长度、API调用次数）
2. ✅ 配置异常告警（API错误率>5%）
3. ✅ 分析对话质量，优化系统提示词
4. ✅ 清理过期对话历史的定时任务

**验收标准**：
- 可查看每日对话数据统计
- API错误时管理员收到通知
- 对话质量评分>4.0/5.0（玩家反馈）

#### 7. 风险评估

##### 7.1 技术风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| **API调用失败** | 中 | 高 | 降级到预设对话列表，添加重试机制 |
| **响应速度慢** | 低 | 中 | 设置5秒超时，异步返回 |
| **对话质量差** | 中 | 中 | 优化系统提示词，收集玩家反馈迭代 |
| **数据库性能瓶颈** | 低 | 中 | 定期清理对话历史，添加索引 |

##### 7.2 成本风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| **API费用超预算** | 低 | 低 | 设置每日调用上限（如5000次），启用响应缓存 |
| **高频刷屏攻击** | 中 | 中 | 限制每玩家每分钟对话3次 |
| **恶意对话消耗** | 低 | 低 | 禁止单次对话超过100字，检测重复内容 |

**成本控制策略**：
- 设置API调用限流：每玩家每分钟3次，每日30次
- 启用响应缓存：常见问题缓存1小时
- 定期清理对话历史：保留30天
- 监控每日费用：超过10元/天时告警

##### 7.3 内容安全风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| **AI生成违规内容** | 低 | 高 | 关键词过滤，禁忌话题列表，人工审核 |
| **玩家诱导AI说敏感话题** | 中 | 高 | 系统提示词强调禁忌话题，检测敏感词 |
| **对话记录泄露隐私** | 低 | 中 | 脱敏存储玩家ID，定期清理历史 |

**内容审核策略**：
- **禁忌话题列表**：政治、色情、暴力、诈骗、赌博
- **敏感词过滤**：使用DFA算法实时检测回复内容
- **人工抽检**：每日随机抽查100条对话记录
- **玩家举报**：提供【举报对话 <NPC名>】指令

##### 7.4 玩法平衡风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| **AI NPC替代游戏指令** | 中 | 中 | AI回复中引导玩家使用指令，而非直接执行 |
| **玩家沉迷聊天忽略游戏** | 低 | 低 | 限制对话频率，AI适度引导玩法 |
| **AI NPC知识过时** | 中 | 低 | 定期更新系统提示词，同步游戏更新 |

**平衡策略**：
- AI NPC定位为"引导助手"，而非"万能工具"
- 对话回复中包含游戏指令提示（如"试试【锻造】指令吧"）
- 限制单次对话长度（50-150字），避免长篇大论
- 定期更新NPC知识库，同步游戏版本更新

---

## conclusions

1. **项目已具备AI NPC实现基础**：智谱AI GLM-4.5-Flash已集成，NPCService已预留7个AI方法，extra_data字段支持灵活配置
2. **推荐技术选型：智谱AI GLM-4.5-Flash**：零迁移成本，响应速度快，成本极低（约3元/月），中文优化
3. **核心风险可控**：通过降级机制、限流策略、内容审核、成本监控，可有效控制技术、成本、安全风险
4. **实施周期：8-11天**：基础设施2天 + 核心功能4天 + 优化扩展3天 + 监控调优2天
5. **最大挑战：对话质量一致性**：需精心设计系统提示词，持续收集玩家反馈迭代优化
6. **降级方案完善**：AI失败时自动使用预设对话列表（已有中立NPC对话机制），玩家无感知
7. **数据隐私保护**：对话历史定期清理（30天），玩家ID脱敏存储，支持手动删除对话
8. **性能优化充分**：异步处理、响应缓存、数据库索引、对话历史限制，保证响应速度<3秒

---

## relations

### 代码关系

1. **ai_guide.py → AIDialogueService**：`call_zhipu_api`函数可提取为公共服务，复用API调用逻辑
2. **NPCService → AIDialogueService**：预留的7个AI方法调用AIDialogueService生成对话
3. **npc_interaction.py → NPCService**：交互流程中调用`is_ai_enabled`判断是否使用AI对话
4. **NPC.extra_data → AIDialogueService**：存储ai_personality、ai_model等配置，传递给AI生成上下文
5. **DialogueHistoryRepository → AIDialogueService**：管理对话历史的保存、加载、清理
6. **safe_session() → DialogueHistoryRepository**：使用项目现有会话管理器，保证事务一致性

### 功能关系

1. **AI引导系统 → AI NPC系统**：系统提示词设计、上下文管理、消息格式化经验可复用
2. **中立NPC对话 → AI对话降级方案**：预设对话列表作为API失败时的备选方案
3. **限流机制 → 成本控制**：复用项目现有的rate_limiter，限制API调用频率
4. **DI架构 → 可测试性**：NPCService、AIDialogueService均采用依赖注入，便于单元测试

### 数据关系

1. **NPC表 → dialogue_history表**：一对多关系，一个NPC可有多条对话记录
2. **Player表 → dialogue_history表**：一对多关系，一个玩家可与多个NPC对话
3. **extra_data字段 → 系统提示词**：JSON配置动态生成个性化提示词
4. **对话历史 → 上下文窗口**：最近10轮对话构成AI上下文，保证对话连贯性
