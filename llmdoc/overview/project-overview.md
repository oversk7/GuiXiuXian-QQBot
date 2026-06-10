# 诡修仙2 (GuiXiuXian2) 项目概述

## 1. Identity

- **What it is**: 基于 NoneBot2 框架的 QQ 修仙主题文字 RPG 机器人游戏
- **Purpose**: 为 QQ 群提供完整的修仙题材角色扮演游戏体验,包含修炼、战斗、社交、经济等多元化玩法

## 2. High-Level Description

诡修仙2 是一个功能完整的异步 QQ 机器人游戏,采用现代 Python 技术栈构建。游戏以暗黑修仙为世界观,融合了传统修仙元素与诡异题材,提供深度养成、战斗、社交、经济等系统。项目采用分层架构设计,数据访问通过 Repository 模式抽象,以 safe_session/UnitOfWork 两档模式管理事务边界。

### 核心玩法循环
1. **修炼成长** → 修炼获得经验 → 突破提升境界 → 冥返转生获得更强潜力
2. **战斗挑战** → 装备收集 → 属性养成 → PvP/PvE 战斗
3. **社交互动** → 加入公会 → NPC 对话 → 师徒/婚姻关系
4. **经济经营** → 跑商交易 → 市场买卖 → 气运投资

### 技术架构特点
- **渐进式迁移**: 旧式静态方法服务与新式实例服务(`*_new.py`)并存,逐模块迁移
- **Repository 模式**: 数据访问层抽象,63 个 Repository 实现覆盖所有领域
- **两档事务管理**: 命令处理器默认 `safe_session()`;跨多表事务使用 UnitOfWork,解决连接泄漏和数据一致性问题
- **自动数据库迁移**: 启动时自动检测并升级数据库结构,零停机部署

---

## 3. 核心系统概览

### 3.1 修仙系统 (Cultivation System)

**核心机制**:
- **境界体系**: 凡人(1-300级) → 腐体境 → 血咒境 → ... → 冥返转生 → 更高境界
- **修炼系统**: 每 5 分钟修炼一次,获得经验(受月卡/转数/公会/阴宅加成)
- **闭关系统**: 离线修炼,基础 9 小时(高级月卡 12 小时)
- **突破机制**: 30 级前 100% 成功,30 级后成功率递减(最低 10%),失败保留 70-80% 修为
- **冥返转生**: 300/500/1000/1500 级可转生,保留丹药和 VIP 装备加成,转数提供属性点和修炼效率加成

**关键文件**:
- `plugins/xiuxian_game/cultivate/core.py` - 修炼/突破/闭关核心逻辑
- `plugins/xiuxian_game/player/realm_utils.py` - 境界计算工具
- `plugins/xiuxian_game/cultivate/reincarnation.py` - 冥返转生服务

### 3.2 战斗与装备系统 (Battle & Equipment System)

**战斗系统**:
- **回合制战斗**: 支持先手判定、连击(2-4 次)、反击、闪避、暴击、穿透
- **战斗属性**: 暴击率、连击率、反击率、闪避率、命中率、暴击力等
- **PvP 系统**: 无损切磋,基于双方属性模拟战斗
- **PvE 系统**: 与怪物战斗,获得材料和经验

**装备系统**:
- **装备限制**: 最多 4 件装备,不可穿戴同名装备
- **三层属性加成**: 固定值 + 百分比 + 升阶倍率(每阶 +20%) + 宝石镶嵌
- **特殊效果**: 吸血、反伤、真伤、mp_from_hp(血转蓝)等
- **升阶系统**: 0-10 阶,材料递进,成功率递减(90%/70%/50%/30%),失败降级或销毁
- **装备锻造**: 消耗材料+金币+血肉结晶

**关键文件**:
- `plugins/xiuxian_game/battle/enhanced_engine.py` - 增强战斗引擎
- `plugins/xiuxian_game/battle/battle_effects.py` - 战斗效果管理器
- `plugins/xiuxian_game/item/equipment_service.py` - 装备服务

### 3.3 物品与材料系统 (Item & Material System)

**物品类型**:
- **7 大类型**: 消耗品、材料、装备、商品、鬼魂碎片、宝石、鱼类
- **稀有度分级**: 白/绿/蓝/紫/橙/红,影响价格和掉落率
- **材料系统**: 按诡域深度分层掉落(1-20 重白色,21-50 重绿色,...)
- **背包管理**: 默认 100 格(月卡+50),装备不占背包,鱼类独立存储

**丹药系统**:
- **永久属性丹**: 持久化到玩家属性
- **临时 BUFF 丹**: 创建 TemporaryBuff 记录(60 秒 TTL 缓存优化)
- **耐药性系统**: 部分丹药有每日使用限制

**关键文件**:
- `plugins/xiuxian_game/models/inventory.py` - 物品数据模型
- `plugins/xiuxian_game/item/item_effects.py` - 物品效果注册表
- `plugins/xiuxian_game/item/material_stats.py` - 材料统计

### 3.4 经济系统 (Economy System)

**双轨货币**:
- **金币**: 主要货币,用于购买、修复、跑商等
- **积分**: 高端装备专属性货币,通过公会捐献获得(1 金币 = 0.7 积分)

**交易系统**:
- **跑商系统**: 13 个市集,动态定价(供需因子+随机波动),4 小时同地点限制
- **交易市场**: 订单簿模式(买单/卖单),自动撮合,阶梯税收(5%-20%),价格上限 8 倍底价
- **气运投资**: 6 大股票类型,每小时价格波动,3% 手续费,持仓管理费 0.1%/天
- **打工系统**: 稳定收入来源(80-180 金币),频率限制(每小时 10 次)

**通胀控制**:
- 财富指数联动:高玩财富增长 → 自动提升底价(1.0-3.0 倍)
- 阶梯税收回收金币
- 利率系统已取消

**关键文件**:
- `plugins/xiuxian_game/economy/market.py` - 交易市场系统
- `plugins/xiuxian_game/economy/merchants.py` - 跑商系统
- `plugins/xiuxian_game/economy/stock_service.py` - 气运投资

### 3.5 公会(宗门)系统 (Guild System)

**核心功能**:
- **宗门管理**: 创建、加入、退出、职位管理(会长/副会长/核心成员/普通成员)
- **建筑系统**: 8 种功能建筑(经验神龛/资金金库/训练场/灵塔等),提供各类加成
- **经济系统**: 捐献系统、资金库、公会升级
- **任务系统**: 日常任务、周任务,获得积分和公会经验
- **设施系统**: 基地设置、传送阵、丹房、仓库

**职位权限**:
- **会长**: 所有权限(1 人)
- **副会长**: 设置职位、踢核心/普通成员(3 人)
- **核心成员**: 10% 经验加成(公会容量/2 人)
- **普通成员**: 基础权限(无限制,受总容量限制)

**容量计算**: `10 + (level-1)*5` (Lv1: 10 人,Lv2: 15 人...)

**关键文件**:
- `plugins/xiuxian_game/guild/guild_service.py` - 公会核心服务
- `plugins/xiuxian_game/guild/guild_building_service.py` - 建筑服务
- `plugins/xiuxian_game/guild/guild.py` - 公会命令处理器(1613 行)

### 3.6 社交系统 (Social System)

**关系系统**:
- **师徒系统**: 师徒关系,获得导师点和奖励
- **婚姻系统**: 配偶关系,可传送、共享阴宅
- **NPC 好感度**: 0-100 好感度,5 个关系等级(陌生人/熟识/友好/亲密/知心)
- **送礼系统**: 仅限配偶/师徒,每日 10 次,单次 100 件或 10000 金币价值

**AI 对话系统**:
- **AI NPC**: 支持自然对话和游戏指令角色扮演
- **人设系统**: 性格特征、语言风格、背景故事、关系网络
- **长期记忆**: 每 20 轮对话自动总结,提取关键事件,权重衰减(每天 5%)
- **好感度递减**: 防止刷好感度

**关键文件**:
- `plugins/xiuxian_game/dialogue/ai_dialogue_service.py` - AI 对话服务
- `plugins/xiuxian_game/dialogue/npc_favorability_service.py` - 好感度服务
- `plugins/xiuxian_game/social/mentorship_system_service.py` - 师徒服务

### 3.7 故事引擎系统 (Story Engine)

**核心机制**:
- **状态机模式**: 节点构成状态机,通过 `next` 和 `options` 进行状态转移
- **条件评估**: 支持简单条件、逻辑运算(and/or)、嵌套组合、玩家属性检查、故事变量检查
- **节点类型**: story(叙述节点)、choice(选择节点)、end(结束节点)
- **效果应用**: 玩家属性变化、变量变化、特殊效果(试炼成功记录、首次奖励)

**调试工具**:
- **StoryDebugger**: 7 个检查步骤(加载、验证结构、验证节点、检查引用、路径分析、验证条件、验证效果)
- **InteractiveDebugger**: 交互式调试器,支持逐步执行、修改属性、查看变量

**关键文件**:
- `plugins/xiuxian_game/story/engine.py` - 故事引擎核心
- `plugins/xiuxian_game/story/interactive_story.py` - 互动试炼命令
- `plugins/xiuxian_game/story/story_debugger.py` - 调试工具

---

## 4. 技术栈

### 4.1 核心框架
- **NoneBot2**: 异步 QQ 机器人框架
- **Python 3.9+**: 编程语言
- **FastAPI**: Web 框架
- **Uvicorn**: ASGI 服务器

### 4.2 数据层
- **SQLAlchemy 2.0**: 异步 ORM
- **SQLite**: 默认数据库(开发环境)
- **MySQL**: 生产数据库(可选)
- **Alembic**: 数据库迁移工具(保留,实际使用 auto_migrate)

### 4.3 架构模式
- **Repository 模式**: 数据访问抽象(63 个实现)
- **Unit of Work 模式**: 多表事务统一管理
- **手动构造注入**: 服务通过构造函数显式接收 Repository,便于测试时注入 Mock
- **策略模式**: 属性来源、效果类型可扩展
- **工厂模式**: AttributeCalculatorFactory 单例
- **适配器模式**: 旧代码适配新接口(IEffect)

### 4.4 AI 集成
- **智谱 AI (zhipu)**: 主 AI provider,模型 GLM-4-Flash-250414
- **302.ai (ai302)**: 备用 provider,模型 gpt-3.5-turbo
- **Fallback 机制**: 主 provider 失败自动切换

---

## 5. 项目结构

```
plugins/xiuxian_game/
├── models/                      # 数据模型层(ORM)
│   ├── db.py                    # 数据库引擎、Session 工厂
│   ├── auto_migrate.py          # 自动迁移系统
│   ├── player.py                # 玩家模型
│   ├── guild.py                 # 公会模型
│   ├── inventory.py             # 物品和装备模型
│   └── ...                      # 其他模型
│
├── domain/                      # 领域层
│   ├── repositories/            # Repository 接口
│   │   └── base.py              # IRepository 抽象基类
│   ├── attributes/              # 属性系统
│   │   ├── attribute_calculator.py  # 属性计算器(组合模式)
│   │   ├── attribute_calculator_factory.py  # 单例工厂
│   │   └── attribute_sources/   # 属性来源(策略模式)
│   └── effects/                 # 效果系统
│       ├── interfaces.py        # IEffect 统一接口
│       ├── registry.py          # 效果注册中心
│       └── adapters/            # 适配器(桥接旧代码)
│
├── infrastructure/              # 基础设施层
│   ├── repositories/            # Repository 实现(42 个)
│   │   ├── player_repository.py
│   │   ├── guild_repository.py
│   │   └── ...
│   └── uow/                     # Unit of Work
│       └── unit_of_work.py      # 事务管理
│
├── player/                      # 玩家系统
│   ├── info.py                  # 玩家信息命令
│   ├── help.py                  # 帮助信息
│   └── realm_utils.py           # 境界工具
│
├── cultivate/                   # 修仙系统
│   ├── core.py                  # 修炼/突破/闭关
│   └── reincarnation.py         # 冥返转生
│
├── battle/                      # 战斗系统
│   ├── enhanced_engine.py       # 战斗引擎
│   ├── battle_effects.py        # 效果管理器
│   └── battle_attributes.py     # 战斗属性计算
│
├── item/                        # 物品系统
│   ├── equipment_service.py     # 装备服务(DI)
│   ├── equipment_upgrade_service.py  # 升阶服务
│   ├── gem_socket_service.py    # 宝石镶嵌
│   ├── item_effects.py          # 物品效果注册表
│   └── catalog.py               # 物品图鉴
│
├── economy/                     # 经济系统
│   ├── market.py                # 交易市场
│   ├── merchants.py             # 跑商系统
│   ├── stock_service.py         # 气运投资
│   └── part_time_job_commands.py # 打工系统
│
├── guild/                       # 公会系统
│   ├── guild_service.py         # 公会核心服务
│   ├── guild_building_service.py  # 建筑服务
│   ├── guild_economy_service_new.py   # 经济服务
│   └── guild.py                 # 公会命令处理器
│
├── social/                      # 社交系统
│   ├── mentorship_system_service.py # 师徒服务
│   ├── marriage_service.py      # 婚姻服务
│   └── gift_service_new.py      # 送礼服务
│
├── dialogue/                    # AI 对话系统
│   ├── ai_dialogue_service.py   # AI 对话服务
│   ├── npc_personality.py       # NPC 人设系统
│   ├── npc_favorability_service.py  # 好感度服务
│   └── dialogue_summarization_service.py  # 对话总结
│
├── story/                       # 故事引擎
│   ├── engine.py                # 故事引擎核心
│   ├── interactive_story.py     # 互动试炼命令
│   └── story_debugger.py        # 调试工具
│
├── world/                       # 世界系统
│   ├── npc_service.py           # NPC 服务
│   ├── dungeon_battle.py        # 诡域战斗
│   └── weekly_theme.py          # 周主题系统
│
├── data/                        # 配置数据
│   ├── items.yaml               # 物品主配置
│   ├── config.yaml              # 游戏配置
│   └── map.yaml                 # 地图配置
│
└── config.py                    # 配置加载器(建立索引)
```

---

## 6. 架构设计特点

### 6.1 服务架构统一(历史说明)

项目曾长期存在"旧静态方法服务 + `*_new.py` DI 风格服务"双轨并存。**2026-06-10 迁移全部完成**:15 个仅剩单实现的 `*_new.py` 已改回正式命名,9 对平行实现已逐对合并(保留功能超集方,数值语义对齐生产实际生效版本)。

当前统一标准:
- 服务为实例方法类,构造函数显式传入 Repository(手动注入,无容器)
- 不在服务内部 commit,事务由外层 `safe_session()`/UnitOfWork 控制
- 历史静态调用面保留为模块级兼容函数(如 `guild_building_service.get_guild_bonuses(session, ...)`),内部委托唯一实现

### 6.2 Repository 模式

**目的**:
- 抽象数据访问,隐藏 SQL 细节
- 提供面向对象的接口
- 支持依赖注入和单元测试

**实现**:
- **基础接口**: `IRepository[T]` 泛型抽象基类
- **42 个实现**: PlayerRepository, GuildRepository, ItemRepository 等
- **领域查询方法**: 每个 Repository 提供 CRUD + 特定查询方法

**示例**:
```python
class PlayerRepository(IRepository[Player]):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, player_id: str) -> Optional[Player]:
        # 标准查询

    async def get_by_uid(self, uid: int) -> Optional[Player]:
        # 领域查询

    async def get_with_monthly_cards(self, player_id: str):
        # 预加载优化(避免 N+1)
```

### 6.3 Unit of Work 模式

**解决的问题**:
- 传统代码打开多个独立会话,破坏事务原子性
- 多个 Repository 协作时无法共享 Session
- 事务边界不清晰,导致数据不一致

**核心实现**:
```python
async with UnitOfWork(session_factory) as uow:
    player = await uow.players.get_by_id(player_id)
    guild = await uow.guilds.get_by_id(player.guild_id)
    # 所有 Repository 共享同一个 Session
    # 自动 commit/rollback
```

**关键特性**:
- **延迟初始化**: Repository 仅在首次访问时创建
- **会话共享**: 所有 Repository 使用同一个 AsyncSession
- **自动事务管理**: 上下文退出时自动 commit/rollback
- **异常处理**: 特殊处理 Nonebot2 流程控制异常
- **连接泄漏防护**: 确保会话总是被关闭

### 6.4 自动数据库迁移 (Auto Migrate)

**解决的问题**:
- 传统 Alembic 需要手动执行命令
- 新环境部署容易遗漏迁移步骤
- ENUM 类型修改需要手动 SQL 脚本

**核心机制**:
- **启动时自动执行**: 检测并添加缺失字段、索引、ENUM 值
- **零停机部署**: 重启 Bot 自动升级数据库结构
- **安全 ENUM 重建**: 6 步安全流程(验证→临时列→复制→删除旧列→创建新列→恢复数据→删除临时列)

**使用方法**:
```python
# 添加新字段
REQUIRED_FIELDS = {
    "player": {
        "new_field": "INT DEFAULT 0 COMMENT '新字段'"
    }
}
# 重启 Bot,自动添加字段
```

### 6.5 属性计算架构

**AttributeCalculator v2** (组合模式 + 策略模式):
- **管理多个属性来源**: BuffAttributeSource, EquipmentAttributeSource 等
- **并发计算**: 各来源独立计算,最后汇总
- **缓存优化**: BuffAttributeSource 使用 60 秒 TTL 缓存,减少 90% 数据库查询
- **区分持久化**: 只累加 `is_persisted=False` 的来源(装备和丹药已持久化到 player 属性)

**计算流程**:
```
最终属性 = 基础属性(含装备+丹药+VIP)
          + 临时 buff(动态查询,60秒缓存)
```

---

## 7. 核心玩法循环

### 7.1 新手期(1-30 级)
- **体验目标**: 快速成长,理解核心机制
- **关键行为**: 修炼、突破、装备收集、加入公会
- **数值特点**: 100% 突破成功,线性经验增长

### 7.2 成长期(30-100 级)
- **体验目标**: 策略选择,社交互动
- **关键行为**: 装备升阶、跑商交易、参与公会、闭关修炼
- **数值特点**: 突破成功率递减,鼓励使用护航道具

### 7.3 进阶期(100-300 级)
- **体验目标**: 长期目标,深度养成
- **关键行为**: 气运投资、打造高级装备、公会建设、NPC 关系培养
- **数值特点**: 经验需求巨大,转生成为核心

### 7.4 高手期(300 级+)
- **体验目标**: 无限成长,收集成就
- **关键行为**: 冥返转生、诡域探索、PVP 切磋、市场交易
- **数值特点**: 转数提供实际收益,无限境界扩展

---

## 8. 数据库设计

### 8.1 核心表

- **player**: 玩家信息(属性、坐标、境界、社交关系)
- **inventory**: 物品实例(装备、材料、消耗品)
- **guild**: 公会信息
- **guild_member**: 公会成员关系
- **guild_building**: 公会建筑
- **stocks**: 气运投资股票
- **stock_holdings**: 股票持仓
- **market_order**: 市场订单(买单/卖单)
- **npc_favorability**: NPC 好感度
- **npc_dialogue_history**: NPC 对话历史
- **npc_long_term_memory**: NPC 长期记忆(总结+关键事件)
- **story_session**: 故事会话记录
- **mentorship**: 师徒关系
- **marriage**: 婚姻关系

### 8.2 数据库配置

**SQLite** (默认):
```yaml
database:
  type: "sqlite"
  sqlite:
    path: "data/game.db"
    timeout: 30
```

**MySQL** (生产环境):
```yaml
database:
  type: "mysql"
  mysql:
    host: "localhost"
    port: 3306
    user: "root"
    password: "password"
    database: "guixiuxian_db"
    pool_size: 20
    max_overflow: 10
```

---

## 9. 关键配置

### 9.1 NoneBot 配置 (`.env`)

```bash
ENVIRONMENT=dev
DRIVER=~fastapi+~httpx+~websockets
LOG_LEVEL=DEBUG
USE_NEW_EFFECT_SYSTEM=true
QQ_IS_SANDBOX=false
COMMAND_START=["/",""]
SUPERUSERS=["10828B7EC666EF1E868F52B96FE5F265"]
```

### 9.2 游戏配置 (`data/config.yaml`)

核心参数:
- **修炼**: `cool_down: 300` (5 分钟), `base_exp: 50`
- **突破**: `change_level: 30`, `fail_keep_ratio: 0.7`
- **掉落率**: 白色 30%,绿色 15%,蓝色 8%,紫色 3%,橙色 1%
- **经济倍率**: MATERIAL 0.7x, GEM 2.0x, EQUIPMENT 4.0x

### 9.3 月卡配置

| 功能 | 基础月卡 | 高级月卡 |
|------|---------|---------|
| 修炼效率 | +20% | +50% |
| 闭关时长 | 9 小时 | 12 小时 |
| 闭关效率 | +20% | +50% |
| 背包格子 | +5 | +20 |
| 突破保护 | 75% | 80% |
| 自动采集 | 无 | 有 |

---

## 10. 开发者相关

### 10.1 启动流程

```python
# 1. bot.py
nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(Adapter)
nonebot.load_from_toml("pyproject.toml")

# 2. plugins/xiuxian_game/__init__.py
@driver.on_startup
async def _():
    await init_db()  # 创建表 + auto_migrate
    # 注册物品效果适配器
    adapters = register_all_item_effect_adapters()
```

### 10.2 数据库迁移

**添加新字段**:
1. 在 `models/auto_migrate.py` 的 `REQUIRED_FIELDS` 添加字段定义
2. 重启 Bot,自动执行迁移

**添加新 ENUM 值**:
1. 在 `models/auto_migrate.py` 的 `REQUIRED_ENUMS` 更新枚举值
2. 重启 Bot,自动重建 ENUM 列

### 10.3 帮助信息更新

**单一数据源**: `data/knowledge/*.yaml`(2026-06-10 起)。yaml 的 `body` 同时作为 AI 检索语料和游戏内帮助页内容,由 `player/help_topics.py` 在启动时渲染并注册命令。

**修改已有系统的帮助**: 直接编辑对应 yaml 的 `body`(【命令】会渲染成可点击按钮,整行 ━ 渲染成分隔线)。

**新增帮助主题**: 在 yaml 中添加:
```yaml
help_command: "钓鱼系统"      # 注册的帮助命令名
help_aliases:                 # 别名(可选)
  - 钓鱼帮助
```

`player/help.py` 仅保留主菜单(帮助)和 8 个模块导航页。CI 的 `check_help_consistency.py` 会拦截"新增命令但没写帮助"。

---

## 11. 技术债务与改进方向

### 11.1 已知问题

1. **属性计算复杂**: 多层叠加可能导致性能问题
2. **经济平衡**: 长期通胀压力,高玩财富集中
3. **新手门槛**: 300 级才能转生,前期体验较长

### 11.2 改进方向

1. **数据访问模式统一**: 命令处理器统一 `safe_session()`,跨多表事务统一 UnitOfWork
2. **`*_new.py` 命名收尾**: 旧版已删除的模块改回正式命名,新旧并存的模块列迁移清单逐个关闭旧版
3. **巨型文件拆分**: `dungeon_battle.py`、`merchants.py`、`guild.py` 等超 1500 行文件按"命令层薄、服务层厚"拆分
4. **help 单一数据源**: `help.py` 从 `data/knowledge/*.yaml` 生成,消除双份手工维护
5. **测试债清算**: 修复或删除 CI 绿名单外的存量失败测试,逐步扩大覆盖

> 注: 曾列出的 Redis 缓存、CQRS、事件溯源、微服务拆分等方向已移除——对单进程单机 QQ 机器人属于过度设计。

---

## 12. 相关文档

- **架构文档**: `/llmdoc/architecture/` - 系统架构详细说明
- **使用指南**: `/llmdoc/guides/` - 操作指南
- **参考手册**: `/llmdoc/reference/` - API 规范、数据模型

**核心架构文档**:
- `/llmdoc/architecture/unit-of-work-and-di.md` - Unit of Work 与数据访问模式
- `/llmdoc/architecture/repository-pattern-implementation.md` - Repository 模式实现
- `/llmdoc/architecture/battle-engine-architecture.md` - 战斗引擎架构

**核心指南**:
- `/llmdoc/guides/how-to-add-battle-effect.md` - 如何添加战斗效果
