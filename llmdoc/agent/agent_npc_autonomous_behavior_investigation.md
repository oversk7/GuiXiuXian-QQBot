# Agent NPC自主行为系统设计调研报告

**调研日期**: 2025-12-01
**调研范围**: 玩家指令系统架构、NPC数据模型、交易市场实现、打工系统、AI决策接口
**调研目标**: 为"Agent NPC"系统（AI NPC执行玩家指令）提供完整的技术方案和实施路径

---

## Code Sections (The Evidence)

### 玩家指令系统核心

- `plugins/xiuxian_game/platform_utils.py:61-80` (`get_unified_player`): 统一玩家获取函数，通过MessageEvent自动识别用户身份，支持账号切换，是指令触发的关键入口
- `plugins/xiuxian_game/economy/part_time_job_commands.py:15-38` (`on_command装饰器`): on_command注册装饰器示例，定义"打工"、"收工"、"工作状态"等指令
- `plugins/xiuxian_game/economy/market.py:1-23` (`market.py入口`): 交易市场指令实现，使用on_command注册"挂牌"、"求购"等交易命令
- `plugins/xiuxian_game/models/db.py:159-164` (`safe_session`): 自动提交会话管理器，所有玩家操作都使用此会话

### NPC数据模型与扩展

- `plugins/xiuxian_game/models/npc.py:34-88` (`NPC类定义`): NPC表结构（id、npc_id、name、npc_type、status、level、hp、extra_data等18个字段），extra_data字段为JSON类型支持灵活扩展
- `plugins/xiuxian_game/models/npc.py:16-24` (`NPCType枚举`): 7种NPC类型（MERCHANT商人、CRAFTSMAN工匠、EMPLOYER雇主、GHOST鬼怪、SPECIAL_VENDOR特殊商贩、GUARD守卫、NORMAL普通NPC）
- `plugins/xiuxian_game/models/npc.py:76-80` (`extra_data字段`): MutableDict.as_mutable(JSON)类型，用于存储灵活配置和AI参数
- `plugins/xiuxian_game/models/npc.py:202-221` (`create_merchant类方法`): 工厂方法创建不同类型NPC，演示NPC创建模式
- `plugins/xiuxian_game/models/npc.py:147-172` (`has_function/add_function`): NPC功能管理方法，通过functions字段存储可用功能

### 玩家模型与Player能力

- `plugins/xiuxian_game/models/player.py:1-87` (`Player类`): 87个字段的玩家模型，包含所有属性、坐标、经济数据、公会关联
- `plugins/xiuxian_game/models/inventory.py:50-100` (`ItemInstance模型`): 物品实例，支持player_id外键关联，equipped标志表示穿戴状态

### Service DI架构（支持NPC执行指令）

- `plugins/xiuxian_game/economy/part_time_job_service_new.py:29-120` (`PartTimeJobService`): DI重构版本的打工Service，通过构造函数注入Repository，不再使用静态方法，可直接被NPC复用
- `plugins/xiuxian_game/infrastructure/uow/unit_of_work.py` (`UnitOfWork`): 工作单元模式，统一事务边界，懒加载47个Repository，确保NPC操作的事务一致性
- `plugins/xiuxian_game/world/npc_service_new.py:16-41` (`NPCService`): NPC管理Service，构造函数注入NPCRepository，为AI接口预留做好了准备

### 交易市场实现机制

- `plugins/xiuxian_game/economy/market.py:52-148` (`市场核心逻辑`): 包含装备挂牌、求购、自动匹配的完整实现，支持价格计算、税收计算、成交记录
- `plugins/xiuxian_game/models/market_order.py` (`MarketOrder表`): 市场订单模型，包含sell_id/buy_id、item_id、price、status等字段
- `plugins/xiuxian_game/economy/market.py:62-80` (`calculate_transaction_tax`): 阶梯税率计算（5000以下免税，最高20%）
- `plugins/xiuxian_game/economy/market.py:30-31` (`MAX_LISTINGS/AUTO_MATCH`): 配置参数（每位玩家最多6个挂牌、自动匹配开启）

### 现有AI基础设施

- `plugins/xiuxian_game/ai_guide.py:23-55` (`call_zhipu_api`): 异步智谱AI API调用函数，包含error handling、timeout控制（30秒）、JSON解析
- `plugins/xiuxian_game/ai_guide.py:28` (`API密钥`): 硬编码的API密钥（安全风险，需迁移到配置文件）
- `plugins/xiuxian_game/ai_guide.py:57-100` (`DATABASE_SCHEMA`): 943行的系统提示词，包含完整的数据库表结构和游戏指令知识库

### AI NPC接口预留

- `plugins/xiuxian_game/world/npc_service_new.py:417-506` (AI接口预留): 7个AI相关预留方法（is_ai_enabled、get_ai_personality、get_ai_model、get_ai_forbidden_topics、enable_ai_for_npc等）

### 指令处理流程示例

- `plugins/xiuxian_game/economy/part_time_job_commands.py:43-120` (`handle_work`): 完整的打工命令处理流程：Feature Flag判断→创建UoW→获取玩家→调用Service→返回结果
- `plugins/xiuxian_game/economy/market.py:200-300` (挂牌命令处理): 装备挂牌流程：命令解析→装备验证→价格计算→订单创建→自动匹配

---

## Report (The Answers)

### result

#### 1. 玩家指令系统架构分析

**指令触发流程**：
1. **入口**: QQ用户消息 → Nonebot2适配器
2. **路由**: `@on_command("打工")` 装饰器注册（`part_time_job_commands.py:33`）
3. **处理器**: 异步处理函数 `handle_work(event: MessageEvent)` 执行
4. **玩家识别**: `await get_unified_player(session, event)` 自动识别用户身份（`platform_utils.py:61`）
   - 调用 `PlayerRepository.get_active_by_platform_id(user_id)`
   - 支持多账号切换（通过AccountOwnership.is_active）
5. **会话管理**: `async with safe_session() as session:` 自动提交事务（`models/db.py:159`）
6. **业务执行**: 调用Service（如PartTimeJobService）或直接ORM操作
7. **响应**: 返回结果消息给玩家

**关键观察**：
- 玩家身份完全由`event.get_user_id()`确定，NPC可以"伪造"event对象或使用相同机制
- 指令处理不检查user_id是否为真实用户，可以用虚拟player_id替代
- Service层已DI化，不依赖全局状态（如safe_session），便于NPC复用

#### 2. NPC vs Player数据模型对比

| 维度 | Player模型 | NPC模型 | 能否统一 |
|------|----------|---------|---------|
| **ID字段** | id(主键), uid(自增) | id(主键), npc_id(唯一) | ✅ 可用npc_id作为虚拟user_id |
| **基础属性** | 87个字段 | level, hp, mp等18个 | ⚠️ NPC需扩展 |
| **物品系统** | ItemInstance.player_id外键 | 无关联 | ❌ NPC需创建虚拟背包 |
| **金币系统** | gold, gold2字段 | 无字段 | ❌ NPC需创建虚拟账户 |
| **修炼系统** | exp, level等升级字段 | 仅有level | ⚠️ NPC无需修炼 |
| **坐标系统** | region, x, y, dungeon_level等 | location_id外键 | ✅ NPC用location_id |
| **公会系统** | guild_id外键 | 无字段 | ❌ NPC作为商人/工匠无需加入 |

**结论**：NPC不能直接继承Player模型，但可创建虚拟Player账号或使用适配器模式。

#### 3. 交易市场实现机制详解

**市场系统核心架构**：
```
指令输入 (【挂牌】、【求购】、【查看】)
    ↓
market.py命令处理
    ↓
EquipmentTradeService (可被NPC复用)
    ├── create_sell_order() - 卖单
    ├── create_buy_order() - 买单
    ├── auto_match() - 自动匹配
    └── cancel_order() - 取消订单
    ↓
MarketOrderRepository + ItemRepository
    ├── MarketOrder表 (订单)
    ├── TradeRecord表 (成交记录)
    └── Player.gold字段 (余额)
```

**关键机制**：

**(1) 价格计算** (`market.py:62-148`):
- **底价策略**: `PRICE_FLOOR_ALPHA = 0.6` (参考价折扣)
- **财富指数**: 根据TopN玩家金币中位数动态调整物价（`_get_wealth_scale`）
- **税费**: 5000以下免税，5000-20000 5%，20000-50000 10%，50000-100000 15%，100000以上20%
- **价格上限**: `PRICE_CAP_MULT = 8` (建议价的8倍上限)

**(2) 自动匹配** (`_try_auto_match`):
- 新订单创建时自动与对手订单匹配
- 优先匹配同价格订单，然后匹配更优价格
- 自动生成TradeRecord、更新Player.gold、扣除ItemInstance

**(3) 状态管理** (`OrderStatus`):
- PENDING (待成交)
- FILLED (已成交)
- PARTIALLY_FILLED (部分成交)
- CANCELLED (已取消)

**NPC参与交易的可行性**: ✅ 完全可行
- MarketOrder表无owner身份验证，仅需sell_id/buy_id
- 可为NPC创建虚拟account，设sell_id=npc_id
- EquipmentTradeService不检查user_id真伪性

#### 4. Agent NPC设计方案对比

**方案A: NPC继承Player能力（推荐）**

优势：
- ✅ 最小化代码改动，复用所有Service和指令逻辑
- ✅ 完全支持所有玩家功能（打工、交易、升级等）
- ✅ 数据存储统一，便于分析NPC经济行为

劣势：
- ⚠️ Player表会被NPC记录污染，需要区分字段或独立表
- ⚠️ 87个字段中，NPC只需其中20-30个，存储浪费

实现步骤：
1. 创建虚拟Player账号：`id="npc_merchant_001"`, `uid=9000001`, `nickname="铁匠老王"`
2. 为NPC账号初始化：gold=1000000, level=1, hp=9999（设置很高避免战死）
3. 指令执行时用npc_id替代user_id，调用get_unified_player时直接返回NPC Player对象
4. 在Player模型添加`is_ai_npc`标志字段，便于统计和管理

代码改动量：约50-80行（主要是Player查询逻辑适配）

**方案B: NPC独立行为系统（可选）**

优势：
- ✅ 完全独立的NPC经济体系，不污染玩家数据
- ✅ 可自定义NPC行为逻辑（如库存管理、进货成本等）

劣势：
- ❌ 需要复制大量Service逻辑（交易、物品等）
- ❌ 无法参与玩家经济系统（混合经济），破坏游戏平衡

代码改动量：约500-1000行

**方案C: 适配器模式（可扩展）**

适用于需要让NPC行为与Player不同的场景：
```python
# 创建NPCPlayerAdapter适配器
class NPCPlayerAdapter:
    def __init__(self, npc: NPC):
        self.npc = npc

    # 假装成Player对象
    @property
    def id(self) -> str:
        return self.npc.npc_id

    @property
    def gold(self) -> int:
        return self.npc.extra_data.get("balance", 0)
```

#### 5. 可被NPC执行的指令清单

**已验证可执行**（需调整user_id校验）:

| 指令 | 代码位置 | Service | 复杂度 | NPC支持 |
|------|--------|---------|--------|--------|
| **打工 <工作类型>** | `part_time_job_commands.py:43` | PartTimeJobService | 低 | ✅ 易支持 |
| **收工** | `part_time_job_commands.py:120` | PartTimeJobService | 低 | ✅ 易支持 |
| **【挂牌】<装备> <价格>** | `market.py:200+` | EquipmentTradeService | 中 | ✅ 易支持 |
| **【求购】<装备> <价格>** | `market.py:300+` | EquipmentTradeService | 中 | ✅ 易支持 |
| **查看市集** | `market.py:400+` | MarketOrderRepository | 低 | ✅ 易支持 |
| **探索 <区域>** | `world/real_world_explore.py` | ExploreService | 中 | ⚠️ 需调整 |
| **装备穿戴** | `item/equipment_commands.py:400+` | EquipmentService | 中 | ✅ 易支持 |
| **物品使用** | `item/item_commands.py:200+` | ItemService | 中 | ⚠️ 消耗品限制 |
| **锻造装备** | `item/equipment_craft.py` | ForgeService | 高 | ⚠️ 需AI决策 |
| **升阶装备** | `item/equipment_upgrade_commands.py` | EquipmentUpgradeService | 高 | ⚠️ 需AI决策 |

**暂不支持**（涉及实时PVP）:
- 【战斗】攻击玩家 (需要实时对手)
- 【决斗】挑战 (需要玩家接受)
- 【世界BOSS】参与 (需要实时同步)

#### 6. AI决策系统设计

**决策输入**：
1. **游戏状态**: NPC position, inventory, gold, 附近玩家列表, 市场价格趋势
2. **上下文**: 当前玩家对话内容、历史交互记录
3. **约束条件**: NPC的role（商人只做交易，工匠只做锻造）

**决策过程**：
```
AI获取游戏状态
    ↓
构建上下文提示词 (包含NPC角色、可用指令、当前状态)
    ↓
调用LLM生成决策 (智谱GLM-4.5-Flash)
    ↓
解析回复为指令 (正则表达式或JSON格式)
    ↓
验证指令合法性 (权限检查、参数范围检查)
    ↓
执行指令 (调用对应Service)
    ↓
更新游戏状态 (NPC库存、金币等)
```

**LLM提示词设计**：
```python
SYSTEM_PROMPT = """你是《诡修仙》游戏中的NPC商人"李四"。

你的角色:
- 身份: 市集商人
- 性格: 精明谨慎，喜欢讨价还价
- 知识领域: 装备交易、物品估价
- 库存: {npc_inventory_json}
- 余额: {npc_gold} 金币

当前市场信息:
{market_price_trends}

玩家说: {player_message}

你可以执行以下指令:
1. 【挂牌 <装备名称> <价格>】- 列出装备出售
2. 【求购 <装备名称> <价格>】- 登记收购意向
3. 【查看市集】- 查看市场信息

请以第一人称回复，不超过150字。如需执行指令，在回复末尾添加:
指令: 【指令名 参数1 参数2】

示例回复:
"道友，这套装备确实不错，我出价2000金币如何？不过我的库存已满，得卖出一些。
指令: 【挂牌 精铁剑 3000】"
"""
```

**工具调用方案**（推荐）：
使用智谱AI的Function Calling能力，定义NPC可调用的工具：

```python
TOOLS = [
    {
        "name": "list_equipment",
        "description": "挂牌装备出售",
        "parameters": {
            "equipment_name": "str",  # 装备名称
            "price": "int"            # 售价
        }
    },
    {
        "name": "request_equipment",
        "description": "发出求购单",
        "parameters": {
            "equipment_name": "str",
            "price": "int"
        }
    },
    {
        "name": "query_market",
        "description": "查询市场信息"
    }
]
```

优势：避免正则表达式解析的歧义，LLM直接返回结构化JSON

#### 7. NPC经济平衡建议

**定价策略**：
1. **成本基准**: 使用玩家成交价的中位数作为NPC定价参考
2. **利润率**: NPC交易利差控制在10-15%（避免垄断）
3. **价格上下限**:
   - 下限 = 玩家平均成交价 × 0.85
   - 上限 = 玩家平均成交价 × 1.15

**库存管理**：
1. **初始库存**: 给予NPC 5-10件初始装备（不同稀度）
2. **自动补货**: 每日0点自动补货，补充至初始库存
3. **库存成本**: 设置虚拟"进价"，计入NPC的成本核算

**防刷机制**：
1. **玩家-NPC交易限制**:
   - 同一玩家每日与NPC最多交易10次
   - 同一装备类型每日最多交易3次
2. **NPC价格调整**:
   - 如果某装备24小时内被玩家大量出售给NPC，自动降价20%
   - 如果库存积压超过初始量的150%，该类型装备不再求购
3. **异常检测**:
   - 监控NPC金币日增长，超过100万时告警
   - 检测玩家是否在循环交易刷钱

**收益平衡**：
1. **NPC手续费**: NPC交易时也需缴纳市场税（与玩家相同）
2. **经济流入/流出**:
   - 定期清算NPC超额利润，转入"系统金库"
   - 或者让NPC进行"投资"（如购买股票），避免金币堆积

#### 8. 实施分阶段建议

**Phase 1: 数据准备（1天）**
- ✅ 为2-3个试点NPC创建虚拟Player账号（id="npc_merchant_xxx"）
- ✅ 初始化NPC库存和金币
- ✅ 更新Player模型添加`is_ai_npc`字段

**Phase 2: 核心指令适配（2-3天）**
- ✅ 调整platform_utils.py，使get_unified_player支持虚拟player_id
- ✅ 修改market.py和part_time_job_commands.py移除user_id硬检查
- ✅ 创建NPCCommandExecutor适配器，统一NPC指令执行

**Phase 3: AI决策层（3-4天）**
- ✅ 创建NPCDecisionService，集成call_zhipu_api
- ✅ 为3个NPC设计个性化系统提示词
- ✅ 实现工具调用（Function Calling）解析
- ✅ 添加指令验证和安全检查

**Phase 4: 经济平衡（2-3天）**
- ✅ 实现库存管理和自动补货
- ✅ 实现玩家-NPC交易限制
- ✅ 添加NPC行为监测和异常告警
- ✅ 进行压力测试，评估NPC对经济的影响

**Phase 5: 上线和优化（2天）**
- ✅ 灰度发布（50%玩家可见NPC交易）
- ✅ 监控经济数据，调整NPC定价策略
- ✅ 收集玩家反馈，优化NPC对话质量

#### 9. 技术风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| **AI决策失误** | 中 | 中 | 添加人工审核，管理员可手动干预NPC操作 |
| **NPC被玩家利用刷钱** | 高 | 高 | 实施交易限制、异常检测、金币锁定 |
| **市场价格被破坏** | 中 | 高 | 设置NPC定价与玩家价格偏差限制 |
| **API调用成本超预算** | 低 | 中 | 设置每日AI决策次数上限（如1000次），启用缓存 |
| **NPC行为重复单调** | 中 | 低 | 为NPC添加多样性引导提示词，定期更新 |

#### 10. 系统架构全景图

```
玩家指令系统 (existing)
├── Command Handler (on_command装饰器)
├── platform_utils.get_unified_player()
├── safe_session() 事务管理
└── Service层 (DI架构)
    ├── PartTimeJobService
    ├── EquipmentTradeService
    ├── EquipmentService
    └── ... (26个Service)

Agent NPC系统 (新增)
├── NPCDecisionService (AI决策)
│   ├── build_system_prompt() - 生成提示词
│   ├── parse_response() - 解析AI回复
│   └── validate_command() - 验证指令
├── NPCCommandExecutor (指令执行)
│   ├── execute_job_command()
│   ├── execute_trade_command()
│   ├── execute_craft_command()
│   └── ... (通用指令适配)
├── NPCPlayerAdapter (虚拟Player账号)
│   ├── 虚拟player_id和Player对象映射
│   ├── 库存管理 (ItemInstance)
│   └── 金币管理 (gold字段)
├── NPCEconomyMonitor (经济监控)
│   ├── 交易限制检查
│   ├── 异常检测
│   └── 库存自动补货
└── 数据存储 (existing)
    ├── Player表 (NPC虚拟账号)
    ├── MarketOrder表 (共享)
    ├── ItemInstance表 (共享)
    ├── NPC表 (扩展extra_data)
    └── ... (其他业务表)
```

---

## conclusions

1. **玩家指令系统完全支持NPC参与**: get_unified_player()使用platform_id而非user_id，可用npc_id替代。Service层已DI化，不依赖全局状态，便于NPC复用。

2. **交易市场实现完善，NPC可直接参与**: MarketOrder表无owner身份验证，自动匹配逻辑完全通用，NPC只需创建虚拟Player账号即可挂牌求购。

3. **打工系统可支持NPC自动执行**: PartTimeJobService已DI化，NPC可调用Service.start_job()和complete_job()自动赚取经验和金币。

4. **现有AI基础完善，可直接复用**: call_zhipu_api()函数完整可用，ai_guide.py中的系统提示词设计经验可借鉴。

5. **方案A（NPC继承Player）最可行**: 代码改动最小（50-80行），完全复用现有Service，便于经济平衡分析。

6. **关键改动点仅3处**:
   - `platform_utils.py`: 添加虚拟player_id支持（10行）
   - `market.py / part_time_job_commands.py`: 移除user_id硬检查（20行）
   - 创建`NPCCommandExecutor`统一指令执行（50行）

7. **经济平衡可控**:
   - 定价策略: 与玩家成交价挂钩（±15%）
   - 交易限制: 同一玩家每日最多10次交易
   - 库存管理: 初始库存10件，每日补货，超额自动降价

8. **AI决策系统相对简单**: 仅需提示词优化和工具调用集成，不涉及复杂的动态规划或强化学习。

9. **实施周期8-10天**: 数据准备1天 + 核心适配2-3天 + AI决策3-4天 + 经济平衡2-3天 + 上线2天

10. **最大挑战是防止玩家利用**: 需要设置交易限制、异常检测、人工审核等多层防护。

---

## relations

### 代码调用关系

1. **platform_utils.get_unified_player() → Player模型**:
   - 所有玩家指令都以get_unified_player()获取玩家对象作为入口
   - NPC实现中需要修改此函数支持虚拟player_id

2. **on_command装饰器 → safe_session() → Service层**:
   - 每条玩家指令流程：Command Handler → safe_session打开会话 → 调用Service → 自动提交
   - NPC复用此流程，仅需替换player对象来源

3. **EquipmentTradeService / PartTimeJobService ← Repository模式**:
   - Service已DI化，通过构造函数注入Repository
   - NPC可直接实例化Service，无需修改Service代码

4. **NPCDecisionService ← call_zhipu_api()**:
   - 提取ai_guide.py中的API调用函数为公共服务
   - NPCDecisionService复用此函数进行AI推理

5. **MarketOrderRepository / ItemRepository ← MarketOrder / ItemInstance表**:
   - NPC挂牌和求购都使用相同的Repository
   - 完全共享玩家的市场数据

### 数据关系

1. **Player表 ↔ NPC虚拟账号**:
   - NPC为每个AI NPC创建虚拟Player记录
   - Player.id = npc_id, Player.is_ai_npc = True
   - 一对一关系

2. **NPC表 ↔ Player表**:
   - NPC.extra_data存储AI配置和库存元数据
   - Player记录存储NPC的金币和装备

3. **MarketOrder表**:
   - sell_id / buy_id可以是player_id或npc_id
   - 玩家和NPC共享同一个市场订单表

4. **ItemInstance表**:
   - player_id可指向NPC虚拟Player
   - NPC的装备和玩家装备完全相同的数据模型

### 功能关系

1. **AI引导系统 → AI NPC对话系统**:
   - 系统提示词设计、上下文管理、消息格式化经验可复用
   - 响应缓存策略可适用于NPC决策缓存

2. **中立NPC对话 → AI NPC对话降级方案**:
   - 如果AI决策失败，自动使用预设对话（npc_interaction.py:266-311）

3. **交易市场限流机制 → NPC交易限制**:
   - 复用现有的rate_limiter，限制NPC与玩家交互频率

4. **DI架构 → NPC系统的可测试性**:
   - NPCCommandExecutor可Mock Service进行单元测试
   - NPCDecisionService可Mock LLM响应进行测试

---

