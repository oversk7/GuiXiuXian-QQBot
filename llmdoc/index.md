# 诡修仙2 (GuiXiuXian2) 技术文档索引

> **面向LLM的检索地图** - 本索引为AI Agent和其他LLM提供快速、精确的文档检索路径

---

## 快速导航

- **[项目概览](#项目概览)** - 了解这是什么项目
- **[核心系统](#核心系统)** - 理解主要功能模块
- **[架构设计](#架构设计)** - 系统如何构建(LLM检索地图)
- **[使用指南](#使用指南)** - 操作指南和最佳实践
- **[参考手册](#参考手册)** - API规范和配置
- **[快速开始](#快速开始)** - 新手入门路径

---

## 项目概览

### 入门文档
- **[项目概述](/llmdoc/overview/project-overview.md)** - 项目定位、核心玩法循环、技术架构全景图
  - 游戏特色: 修仙+暗黑题材RPG,35个境界体系,冥返转生系统
  - 技术栈: NoneBot2 + SQLAlchemy 2.0 + Repository模式 + Unit of Work
  - 核心系统: 战斗、经济、公会、NPC对话、故事引擎

### 系统概览
- **[玩家与属性系统](/llmdoc/overview/player-attributes-overview.md)** - 玩家数据管理、属性计算框架、境界转生机制
- **[战斗系统](/llmdoc/overview/combat-system-overview.md)** - 回合制战斗引擎、装备驱动效果、PvP/PvE机制
- **[经济系统](/llmdoc/overview/economy-system-overview.md)** - 双轨货币、交易市场、跑商、气运投资
- **[数据访问层](/llmdoc/overview/data-access-overview.md)** - Repository模式、Unit of Work、依赖注入、自动迁移

---

## 核心系统

### 玩家与成长
- **[玩家系统架构](/llmdoc/architecture/player-system-architecture.md)** - 数据模型、Repository实现、生命周期管理
  - Player模型30+字段(属性、坐标、社交关系)
  - PlayerRepository领域查询(get_by_uid, get_nearby_players)
  - UnitOfWork事务边界管理

- **[属性计算架构](/llmdoc/architecture/attribute-calculation-architecture.md)** - 组合模式+策略模式,多来源属性计算
  - AttributeCalculator v2管理多个属性来源
  - 60秒TTL缓存优化90%临时buff查询
  - 区分持久化(装备/丹药)与动态计算(buff)

- **[境界突破指南](/llmdoc/guides/realm-breakthrough-guide.md)** - 突破成功率、冥返转生、经验曲线
  - 30级前100%成功,30级后递减(最低10%)
  - 冥返等级要求(300/500/1000/1500/2000级)
  - 转数加成(属性点、修炼效率)

### 战斗系统
- **[战斗引擎架构](/llmdoc/architecture/battle-engine-architecture.md)** - 回合执行流程、伤害计算、胜负判定
  - EnhancedBattleEngine控制战斗初始化和回合循环
  - BattleAttributeCalculator计算战斗属性(暴击、连击、闪避等)
  - 支持随机种子实现可重现战斗

- **[效果系统架构](/llmdoc/architecture/effect-system-architecture.md)** - 统一效果管理,触发机制,效果叠加
  - 20+种效果类型,10+种触发类型
  - 桥接模式集成IEffect接口
  - 装备效果解锁(普通装备+2阶解锁,VIP装备0阶全解锁)

- **[战斗系统指南](/llmdoc/guides/battle-system-guide.md)** - 发起PvP/PvE战斗、查询战斗属性、理解伤害计算
  - 使用BattleIntegrationHelper.compact_player_vs_player_battle发起切磋
  - 斩龙闪20%必中伤害拆分机制
  - 防御减伤公式: max(1, damage - min(defense, damage*defense/(defense+100)))

- **[添加战斗效果指南](/llmdoc/guides/how-to-add-battle-effect.md)** - 通过YAML配置添加新效果,无需修改代码
  - 添加新EffectType/TriggerType的步骤
  - 配置参数说明(trigger, chance, effect, value, duration等)
  - 环境条件效果(理智上限、区域白名单、周主题白名单)

### 经济系统
- **[经济系统架构](/llmdoc/architecture/economy-system-architecture.md)** - 货币管理、价格计算、交易撮合、税收控制
  - MarketOrder订单簿模式,自动撮合
  - 阶梯税收(0-20%),直接销毁回收货币
  - 财富指数联动(1.0-3.0倍)响应全服财富水平

- **[市场交易架构](/llmdoc/architecture/market-trading-architecture.md)** - 跑商系统、动态定价、供需因子
  - 13个市集配置,4小时同地点限制
  - 供需因子(0.6-1.6)影响价格,每日20%回归
  - 跨市场交易5%奖励

- **[市场交易指南](/llmdoc/guides/market-trading-guide.md)** - 挂牌买卖、撤牌、查牌、税率
  - 挂牌命令: 【挂牌 出售/收购 物品名 单价 数量】
  - 每人最多6个订单,装备交易冻结状态
  - 底价自动吸附,8倍底价上限

- **[经济平衡指南](/llmdoc/guides/economy-balance-guide.md)** - 通胀控制、财富分配、价格调控
  - 财富指数公式: scale = 1.0 + (median_wealth/5B)^0.3 * 0.3
  - EMA平滑处理: current = prev*0.85 + new*0.15

### 物品与装备
- **[物品装备架构](/llmdoc/agent/scout_item_equipment.md)** - 物品类型、稀有度分级、材料系统
  - 7大类型: 消耗品、材料、装备、商品、鬼魂碎片、宝石、鱼类
  - 稀有度: 白/绿/蓝/紫/橙/红
  - 材料按诡域深度分层掉落(1-20重白色,21-50重绿色...)

### 公会系统
- **[公会系统架构](/llmdoc/agent/scout_guild_system.md)** - 宗门管理、建筑系统、职位权限
  - 8种功能建筑(经验神龛、资金金库、训练场等)
  - 职位: 会长/副会长/核心成员/普通成员
  - 容量计算: 10 + (level-1)*5

### NPC与对话
- **[故事对话系统](/llmdoc/agent/scout_story_dialogue_investigation_2025_01_10.md)** - AI对话引擎、NPC人设、长期记忆
   - AI NPC支持自然对话和游戏指令角色扮演
   - 每20轮对话自动总结,提取关键事件
   - 好感度递减防止刷好感度

---

## 架构设计

### 数据访问层
- **[Repository模式实现](/llmdoc/architecture/repository-pattern-implementation.md)** - 42个Repository,泛型接口,领域查询
  - IRepository[T]泛型抽象基类
  - 标准CRUD + 领域查询方法(如get_by_uid)
  - joinedload()预加载优化N+1问题

- **[Unit of Work和DI](/llmdoc/architecture/unit-of-work-and-di.md)** - 事务边界管理、依赖注入容器、生命周期
  - UnitOfWork统一事务管理,自动commit/rollback
  - DIContainer支持Singleton/Scoped/Transient三种生命周期
  - 延迟初始化Repository,所有Repository共享同一Session

- **[数据访问迁移指南](/llmdoc/guides/data-access-migration-guide.md)** - 从Legacy架构迁移到新架构
  - 步骤1: 创建Repository实现
  - 步骤2: 添加到UnitOfWork
  - 步骤3: 创建新Service类(移除内部commit)
  - 步骤4: 更新CommandHandler(使用async with UnitOfWork)
  - 步骤5: 测试和验证
  - 步骤6: 清理旧代码

### 设计模式
- **Repository模式** - 数据访问抽象,可测试性,查询集中化
- **Unit of Work模式** - 事务原子性,会话共享,连接泄漏防护
- **依赖注入(DI)** - 解耦合,可测试性,生命周期管理
- **策略模式** - 属性来源系统(IAttributeSource)
- **桥接模式** - 战斗效果桥接(BattleEffectBridge)
- **工厂模式** - AttributeCalculatorFactory单例
- **适配器模式** - 旧代码适配新接口(IEffect)

### 架构特点
- **双轨架构并存** - Legacy静态方法服务与DI架构服务平滑共存
- **自动数据库迁移** - 启动时自动检测并升级数据库结构,零停机部署
- **缓存优化** - 60秒TTL缓存减少90%临时buff查询
- **属性持久化** - 装备加成预计算并持久化到player表



---

## 使用指南

### 属性系统
- **[玩家属性指南](/llmdoc/guides/player-attribute-guide.md)** - 获取有效属性、添加属性来源、修改玩家属性
  - 使用get_effective_attributes_v2()获取含所有加成的属性
  - 实现IAttributeSource接口添加新属性来源
  - 装备加成持久化 vs 临时buff动态计算

### 数据库操作
- **[自动迁移系统](/llmdoc/overview/project-overview.md#64-自动数据库迁移-auto-migrate)** - 添加新字段、添加ENUM值
  - 在REQUIRED_FIELDS字典中添加字段定义
  - 重启Bot自动执行迁移
  - 安全ENUM重建6步流程

### 开发规范
- **[编码规范](/llmdoc/reference/coding-conventions.md)** - Python代码风格、命名约定、文件组织、设计模式
   - 强制类型注解,ORM字段使用Mapped[T]语法
   - 类命名PascalCase,函数命名snake_case
   - Repository实现IRepository[T]接口
   - UoW外部调用finish()防止连接泄漏

### 帮助信息更新
- **[帮助系统](/llmdoc/overview/project-overview.md#104-帮助信息更新)** - 添加/修改命令时更新help.py
  - 位置: plugins/xiuxian_game/player/help.py
  - 格式: {"命令名": {"usage": "...", "description": "...", "examples": [...]}}



---

## 参考手册

### 系统参考
- **[经济系统参考](/llmdoc/reference/economy-system-reference.md)** - 配置参数、计算公式、常量定义
  - 修炼配置: cool_down: 300, base_exp: 50
  - 突破配置: change_level: 30, fail_keep_ratio: 0.7
  - 掉落率: 白色30%,绿色15%,蓝色8%,紫色3%,橙色1%
  - 经济倍率: MATERIAL 0.7x, GEM 2.0x, EQUIPMENT 4.0x



### 配置文件
- **NoneBot配置** (`.env`) - ENVIRONMENT, LOG_LEVEL, COMMAND_START, SUPERUSERS
- **游戏配置** (`data/config.yaml`) - 修炼、突破、掉落率、经济倍率
- **数据库配置** (`config/database.yaml`) - SQLite/MySQL连接配置
- **物品配置** (`data/items.yaml`) - 物品主配置,装备特殊效果

### 月卡配置
| 功能 | 基础月卡 | 高级月卡 |
|------|---------|---------|
| 修炼效率 | +20% | +50% |
| 闭关时长 | 9小时 | 12小时 |
| 闭关效率 | +20% | +50% |
| 背包格子 | +5 | +20 |
| 突破保护 | 75% | 80% |
| 自动采集 | 无 | 有 |

---

## 快速开始

### 新手入门路径

#### 1. 了解项目 (必读)
1. 阅读 [项目概述](/llmdoc/overview/project-overview.md) - 了解项目定位和核心玩法
2. 阅读 [数据访问层概览](/llmdoc/overview/data-access-overview.md) - 理解Repository+UnitOfWork+DI架构
3. 阅读 [编码规范](/llmdoc/reference/coding-conventions.md) - 遵循项目代码风格

#### 2. 理解核心系统 (按需)
- **玩家系统**: [玩家系统架构](/llmdoc/architecture/player-system-architecture.md)
- **属性系统**: [属性计算架构](/llmdoc/architecture/attribute-calculation-architecture.md)
- **战斗系统**: [战斗系统指南](/llmdoc/guides/battle-system-guide.md)
- **经济系统**: [经济系统架构](/llmdoc/architecture/economy-system-architecture.md)

#### 3. 开始开发
- **添加新功能**: 参考 [数据访问迁移指南](/llmdoc/guides/data-access-migration-guide.md)
- **添加战斗效果**: 参考 [如何添加战斗效果](/llmdoc/guides/how-to-add-battle-effect.md)
- **修改玩家属性**: 参考 [玩家属性指南](/llmdoc/guides/player-attribute-guide.md)
- **数据库迁移**: 参考 [自动迁移系统](/llmdoc/overview/project-overview.md#64-自动数据库迁移-auto-migrate)

#### 4. 更新文档
- 架构文档更新: `/llmdoc/architecture/`
- 操作指南更新: `/llmdoc/guides/`
- 参考文档更新: `/llmdoc/reference/`
- **必须同步更新本索引文件**

---

## 常见任务速查

### 添加新功能
1. 创建数据模型 (models/)
2. 创建Repository (infrastructure/repositories/)
3. 添加到UnitOfWork (infrastructure/uow/unit_of_work.py)
4. 创建Service (domain/ 或 功能目录/*_service_new.py)
5. 更新帮助信息 (player/help.py)

### 修复Bug
1. 定位代码位置 (使用本索引找到相关模块)
2. 阅读[架构文档](#架构设计)理解数据流
3. 阅读[指南文档](#使用指南)了解使用方式
4. 遵循[编码规范](#编码规范)修改代码

### 性能优化
1. 检查是否使用Repository而非直接Session
2. 检查是否使用joinedload()避免N+1查询
3. 检查是否使用60秒TTL缓存(buff_source.py)
4. 检查是否预计算并持久化属性(装备加成)

### 数据库迁移
1. 在models/auto_migrate.py的REQUIRED_FIELDS添加字段定义
2. 重启Bot,自动执行迁移
3. 验证字段是否正确添加
4. 更新相关代码使用新字段

---

## 技术债务与改进方向

### 已知问题
1. **属性计算复杂** - 多层叠加可能导致性能问题
2. **经济平衡** - 长期通胀压力,高玩财富集中
3. **新手门槛** - 300级才能转生,前期体验较长

### 改进方向
1. ~~**完成架构迁移**~~ - ✅ **已完成** (2026-01-10: 26/26服务全部迁移到DI架构)
2. **引入缓存** - Redis缓存热点数据(如玩家属性)
3. **CQRS** - 读写分离,查询用轻量级Query
4. **事件溯源** - 关键操作记录事件日志
5. **微服务拆分** - 经济服务、社交服务独立部署

### 代码清理记录
- **2026-01-10**: 完成完整legacy代码清理(删除21个文件,约6,624行)
  - 第一阶段: 删除13个低风险legacy文件 (~3,800行)
  - 第二阶段: 删除5个中风险legacy文件 (~1,693行)
  - 第三阶段: 迁移并删除3个文件 (~1,131行)
  - **架构迁移完成度: 100%** (26/26个服务全部完成)
  - 详细报告: `/llmdoc/agent/legacy_code_complete_cleanup_2026_01_10.md`
  - 调查报告: `/llmdoc/agent/legacy_files_investigation_2026_01_10.md`

---

## 文档分类说明

### /llmdoc/overview/ (概览)
回答"这是什么?" - 高层次项目上下文、系统概览、核心概念

### /llmdoc/architecture/ (架构)
回答"如何构建?" - LLM检索地图,核心组件、执行流程、设计原理

### /llmdoc/guides/ (指南)
回答"如何操作?" - 步骤化操作指南、最佳实践、调试技巧

### /llmdoc/reference/ (参考)
回答"具体细节?" - API规范、配置参数、数据模型、常量定义

### /llmdoc/agent/ (Agent报告)
调查报告、问题分析、实现状态 - LLM Agent工作成果

---

## 文档维护

### 文档质量标准
- **Brevity**: 每个文档少于150行,简洁明了
- **Clarity**: 目的清晰,标题直观
- **Accuracy**: 基于验证的代码,可追溯源文件
- **Categorization**: 放入正确的分类(overview/architecture/guides/reference)
- **Formatting**: 严格遵循ContentFormat_*/格式规范

### 代码引用规范
- **优先引用**: 使用`path/to/file.ext:line_start-line_end`格式
- **避免大段代码**: 不粘贴超过15行的代码块
- **说明意图**: 简要描述引用代码的作用

### 更新检查清单
- [ ] 文档内容准确(基于最新代码)
- [ ] 引用路径正确(行号准确)
- [ ] 遵循格式规范(ContentFormat_*)
- [ ] 文件路径使用绝对路径
- [ ] 同步更新本索引文件

---

**版本**: 3.3
**最后更新**: 2026-01-24
**维护者**: 项目架构组
**文档生成器**: recorder (Claude Code Agent)
**最近更新**: 清理不准确的文档内容，删除未实现的 Markdown 模版相关文档

---

> **提示**: 本索引是LLM的检索地图,按照从高到低的层次组织。使用Ctrl+F快速查找关键词,或跟随"快速开始"路径逐步了解项目。
