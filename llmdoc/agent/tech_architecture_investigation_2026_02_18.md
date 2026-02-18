<!-- 此文件是 scout agent 的原始情报报告，供其他 LLM Agent 检索使用 -->

# 诡修仙2 技术架构全面调查报告

**调查日期**: 2026-02-18
**调查者**: scout agent
**目的**: 为新项目编写编码提示词提供技术参考

---

### Code Sections (The Evidence)

#### 核心基础设施

- `plugins/xiuxian_game/domain/repositories/base.py` (`IRepository[T]`): 泛型仓储抽象基类，定义6个标准抽象方法：`get_by_id`, `add`, `update`, `delete`, `exists`, `count`。使用 `ABC`, `Generic[T]`, `TypeVar('T')` 实现。
- `plugins/xiuxian_game/infrastructure/uow/unit_of_work.py` (`UnitOfWork`): 工作单元实现。管理42个仓储属性，全部延迟初始化（`@property` + 懒加载）。实现 `__aenter__`/`__aexit__` 异步上下文管理，自动 commit/rollback。包含 `with_uow` 装饰器工具函数。
- `plugins/xiuxian_game/infrastructure/di/container.py` (`DIContainer`, `ServiceLifetime`): 依赖注入容器，支持 `SINGLETON`/`SCOPED`/`TRANSIENT` 三种生命周期。`resolve()` 方法按生命周期返回实例。`create_scope()` 创建新作用域容器。
- `plugins/xiuxian_game/infrastructure/di/setup.py` (`setup_di_container`): DI 容器启动配置。注册 `AsyncSession`(scoped), `UnitOfWork`(scoped), `PlayerRepository`/`GuildRepository`(transient，注意其 factory 会 raise NotImplementedError —— Repository 应通过 `uow.players` 等属性访问而非直接 resolve)。

#### 数据模型层

- `plugins/xiuxian_game/models/player.py` (`Player`, `Gender`): 玩家 ORM 模型。使用 SQLAlchemy 2.0 `Mapped[T]` 语法定义字段。包含 30+ 字段（属性、坐标、货币、战斗统计等），字段均有 `comment` 注释。枚举类继承 `str, PyEnum`。
- `plugins/xiuxian_game/models/inventory.py` (`ItemType`, `ItemEffectType`): 物品类型枚举（11种类型）和物品效果类型枚举（20+种类型），均继承 `str, PyEnum`。
- `plugins/xiuxian_game/models/auto_migrate.py` (`auto_migrate`, `REQUIRED_FIELDS`, `REQUIRED_ENUMS`, `REQUIRED_INDEXES`): 自动数据库迁移模块。`REQUIRED_FIELDS` 字典格式为 `{表名: {字段名: "SQL字段定义字符串"}}`。启动时自动执行创表/加字段/加索引/修复ENUM。

#### 效果系统

- `plugins/xiuxian_game/domain/effects/interfaces.py` (`IEffect`, `EffectContext`, `EffectResult`, `TriggerType`, `BaseItemEffect`, `BaseBattleEffect`): 统一效果接口。`IEffect` 有3个抽象方法：`effect_id`(property), `can_trigger`, `execute`。`EffectContext` 是 dataclass，包含 player/session/trigger_type 等字段。
- `plugins/xiuxian_game/domain/effects/registry.py` (`EffectRegistry`, `register_effect`): 效果注册中心，全局单例。支持装饰器注册 `@register_effect("effect_id")`，也支持 `register_class()` 直接注册。`index_by_trigger()` 建立触发类型索引。
- `plugins/xiuxian_game/domain/effects/adapters/battle_effect_bridge.py` (`BattleEffectBridge`): 桥接模式，将 `TriggerConfig` 包装为 `IEffect` 接口，委托给 `BattleEffectManager`，返回 `BattleEffect` 在 `EffectResult.extra_data` 中。
- `plugins/xiuxian_game/battle/battle_effects.py` (`BattleEffectManager`, `TriggerType`, `EffectType`, `BattleEffect`, `TriggerConfig`): 战斗效果管理器主体。定义 20+ 种 `EffectType`，10+ 种 `TriggerType`。`check_triggers()` 做触发类型匹配+概率判定+条件检查。

#### 战斗系统

- `plugins/xiuxian_game/battle/enhanced_engine.py` (`EnhancedBattleEngine`): 核心战斗引擎。控制初始化、回合执行、伤害计算。支持随机种子、装备触发器注册（按升阶解锁）、灵影体质系统、斩龙闪 20% 必中拆分。
- `plugins/xiuxian_game/battle/battle_attributes.py` (`BattleAttributeCalculator`): 战斗属性计算器。计算暴击/连击/反击/闪避/命中/穿透等有效属性，应用属性上限。
- `plugins/xiuxian_game/battle/integration_helper.py` (`BattleIntegrationHelper`): 战斗集成辅助，提供 `compact_player_vs_player_battle` 等高层 PvP/PvE 接口。
- `plugins/xiuxian_game/utils.py` (`apply_defense_mitigation`): 防御减伤公式：`max(1, damage - min(defense, damage*defense/(defense+100)))`。

#### 故事引擎

- `plugins/xiuxian_game/story/engine.py` (`StoryEngine`): 故事状态机。从 `data/stories/*.json` 加载剧情文件。支持状态节点（story/choice/end）、条件评估（and/or/嵌套）、效果应用（属性变化/变量变化）。
- `plugins/xiuxian_game/story/interactive_story.py`: 互动试炼命令处理器。
- `plugins/xiuxian_game/story/story_debugger.py` (`StoryDebugger`): 7步剧情调试工具。

#### AI 对话系统

- `plugins/xiuxian_game/dialogue/ai_dialogue_service.py` (`AIDialogueService`): AI 对话生成服务。读取 `config.yaml` 中的 `ai_dialogue` 配置。支持 zhipu/ai302 双 provider，自动 fallback。`generate_dialogue()` 构建 system_prompt + 对话历史并调用 API。
- `plugins/xiuxian_game/dialogue/npc_personality.py` (`PersonalityTemplate`): NPC 人设系统，`build_system_prompt()` 生成 AI 提示词。
- `plugins/xiuxian_game/dialogue/npc_favorability_service.py`: 好感度服务，5个关系等级，每天5%衰减。
- `plugins/xiuxian_game/dialogue/dialogue_summarization_service.py`: 每20轮对话自动总结服务。

#### 服务层示例

- `plugins/xiuxian_game/guild/guild_service_new.py` (`GuildService`): DI 架构服务标准实现。构造函数接收 `player_repo: PlayerRepository`, `guild_repo: GuildRepository`, `uow: Optional[UnitOfWork]`。实例方法，不内部 commit。
- `plugins/xiuxian_game/guild/guild.py`: 公会命令处理器（1613行）。展示标准命令注册模式：`on_command("命令名", block=True, priority=5)` → `@cmd.handle()` → `async with UnitOfWork(session_factory) as uow:` → UoW外部调用 `finish()`。

#### 配置系统

- `plugins/xiuxian_game/config.py` (`Config`): 配置加载器，基于 `pydantic_settings.BaseSettings`。以 `@property` 形式暴露 `game_config`, `items_config`, `map_config`。`items_config` 建立三种索引：`by_id`, `by_name`, `by_type`。
- `plugins/xiuxian_game/data/config.yaml`: 游戏主配置（修炼/突破/掉落率/经济倍率等）。
- `plugins/xiuxian_game/data/items.yaml`: 物品主配置，含 `special_effects` YAML 字段描述装备效果。
- `plugins/xiuxian_game/config/database.yaml`: 数据库连接配置（SQLite/MySQL）。

#### 玩家系统

- `plugins/xiuxian_game/player/help.py`: 帮助信息字典，格式 `{"命令名": {"usage": ..., "description": ..., "examples": [...]}}`。添加任何命令必须同步更新此文件。
- `plugins/xiuxian_game/platform_utils.py` (`get_unified_player`): 统一玩家获取函数，接受 `session` 和 `event` 参数。

---

### Report (The Answers)

#### result

**1. 项目整体目录结构**

```
plugins/xiuxian_game/
├── models/           # ORM模型层（player.py, inventory.py, guild.py, ...）
├── domain/           # 领域层接口（repositories/base.py, effects/interfaces.py, attributes/）
├── infrastructure/   # 基础设施层（repositories/实现42个, uow/, di/）
├── player/           # 玩家系统（help.py, info.py, realm_utils.py）
├── cultivate/        # 修仙系统（core.py, reincarnation.py）
├── battle/           # 战斗系统（enhanced_engine.py, battle_effects.py, battle_attributes.py）
├── item/             # 物品系统（equipment_service_new.py, item_effects.py）
├── economy/          # 经济系统（market.py, merchants.py, stock_service_new.py）
├── guild/            # 公会系统（guild.py命令处理器, guild_service_new.py）
├── social/           # 社交系统（mentorship_service_new.py, marriage_service.py）
├── dialogue/         # AI对话系统（ai_dialogue_service.py, npc_personality.py）
├── story/            # 故事引擎（engine.py, interactive_story.py, story_debugger.py）
├── world/            # 世界系统（npc_service_new.py, dungeon_battle.py）
├── cooking/          # 烹饪餐厅系统（已完成，2026-02-08）
├── data/             # 配置数据（items.yaml, config.yaml, map.yaml, stories/）
└── config.py         # 配置加载器
```

**2. Repository 模式具体实现**

- **接口位置**: `domain/repositories/base.py` 的 `IRepository[T]`
- **标准方法**: `get_by_id`, `add`, `update`, `delete`, `exists`, `count`（全部抽象）
- **实现规范**: 子类继承 `IRepository[EntityType]`，构造函数接收 `AsyncSession`，私有属性 `self._session`
- **查询风格**: 使用 `select()` + `execute()`，避免 `session.query()`
- **预加载**: 使用 `joinedload()` 解决 N+1 问题
- **领域查询**: 在 Repository 类中添加领域特定方法（如 `get_by_uid(uid: int)`）

**3. Unit of Work 实现细节**

- **文件位置**: `infrastructure/uow/unit_of_work.py`
- **会话管理**: `__aenter__` 调用 `session_factory()` 创建 `AsyncSession`，`__aexit__` 自动 commit/rollback/close
- **NoneBot2 特殊处理**: `FinishedException`/`PausedException`/`RejectedException` 视为正常流程，执行 commit 而非 rollback
- **仓储延迟初始化**: 所有仓储为 `None` 初始化，通过 `@property` 首次访问时才实例化（`from ..repositories.xxx_repository import XxxRepository; self._xxx = XxxRepository(self._session)`）
- **连接泄漏防护**: `finally` 块中必定关闭会话；在 UoW 外部调用 `finish()`
- **`with_uow` 装饰器**: 可用于简化 UoW 管理，将 UoW 注入为 `uow` 关键字参数

**4. DI Container 配置**

- **文件位置**: `infrastructure/di/container.py` 和 `infrastructure/di/setup.py`
- **三种生命周期**: `SINGLETON`（全局缓存）、`SCOPED`（作用域缓存，可 `create_scope` 重置）、`TRANSIENT`（每次新建）
- **注册方式**: `container.register_singleton/scoped/transient(ServiceType, factory_fn)`，factory 接收容器自身为参数
- **实际模式**: 项目实际使用 "Service Locator + UoW" 混合模式，而非纯 DI。Repository 通过 `uow.players` 等属性获取，Service 在 Command Handler 中手动创建并传入 Repository

**5. auto_migrate.py 实现**

- **三个数据字典**:
  - `REQUIRED_FIELDS`: `{表名: {字段名: "SQL定义字符串"}}` — 自动添加缺失字段
  - `REQUIRED_TABLES`: `{表名: "CREATE TABLE SQL"}` — 自动创建缺失表
  - `REQUIRED_ENUMS`: `{表名: {列名: [允许值列表]}}` — 自动修复 ENUM 类型不匹配
  - `REQUIRED_INDEXES`: `[(表名, 索引名, 索引列)]` — 自动创建缺失索引
- **执行时机**: Bot 启动时，在 `init_db()` 中调用 `auto_migrate(engine)`
- **SQL字段定义格式**: `"INT DEFAULT 0 COMMENT '说明'"` 或 `"VARCHAR(64) NULL COMMENT '说明'"`，支持 MySQL 语法

**6. 效果系统注册机制**

- **注册方式 1（装饰器）**: `@register_effect("effect_id")` 或 `@effect_registry.register("effect_id")`
- **注册方式 2（直接调用）**: `effect_registry.register_class("effect_id", EffectClass, singleton=False)`
- **桥接注册（装备效果）**: 启动时调用 `register_all_battle_effect_bridges()`，自动从 `items.yaml` 的 `special_effects` 字段解析 `TriggerConfig` 并创建 `BattleEffectBridge` 注册
- **触发类型索引**: `effect_registry.index_by_trigger(effect_id, TriggerType.ON_ATTACK)` 建立快速查找索引
- **全局单例**: `get_effect_registry()` 返回全局 `EffectRegistry` 实例

**7. 数据模型定义约定**

- **ORM语法**: SQLAlchemy 2.0 `Mapped[T]` + `mapped_column()`，所有字段有 `comment` 参数
- **继承**: 所有模型继承 `Base`（来自 `models/db.py`）
- **枚举**: 枚举类继承 `str, PyEnum`，`str` 在前使枚举值可直接用作字符串
- **可空字段**: `Mapped[str | None]` + `nullable=True`
- **JSON字段**: 使用 `MutableDict.as_mutable(JSON)` 或直接 `JSON`
- **时间字段**: `DateTime` 类型，`server_default=func.now()` 或 `nullable=True`
- **主键**: `String(32)` 类型（平台ID）或 `Integer autoincrement`
- **索引**: 关键查询字段加 `index=True`

**8. 指令处理器标准写法**

```python
# 1. 定义命令
some_cmd = on_command("命令名", block=True, priority=5)

# 2. 注册处理函数
@some_cmd.handle()
async def handle_some(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()

    # 3. 参数验证在 UoW 外部（避免连接泄漏）
    if not arg_text:
        await some_cmd.finish("⛔ 格式错误")  # 安全，UoW 尚未开启

    # 4. UoW 内部只做数据操作，结果存变量
    result_msg = ""
    async with UnitOfWork(lambda: AsyncSessionLocal()) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            result_msg = "⛔ 请先创建角色"
        else:
            service = SomeService(player_repo=uow.players, ...)
            success, msg = await service.do_something(...)
            result_msg = msg

    # 5. UoW 外部发送消息（避免连接泄漏）
    await some_cmd.finish(result_msg)
```

**关键规则**:
- 验证逻辑在 UoW 外部（避免 `finish()` 在 UoW 内部引发 `FinishedException`）
- 结果消息存变量，UoW 关闭后再 `finish()`
- 使用 `get_unified_player(uow.session, event)` 获取玩家
- 仅捕获特定异常，不使用 `except Exception:`

**9. AI 对话系统接口**

- **主服务**: `AIDialogueService.generate_dialogue(npc, personality, question, dialogue_history, favorability, context)` → `(回复文本, token数)`
- **AI Provider**: 智谱 GLM-4-Flash-250414 为主，302.ai gpt-3.5-turbo 为备用
- **配置位置**: `data/config.yaml` 的 `ai_dialogue` 节点
- **长期记忆**: 每20轮自动总结，通过 `context["long_term_memory"]` 注入 system_prompt
- **配置的API调用**: `from ..ai_guide import call_zhipu_api`

**10. 配置文件格式和加载**

- **主入口**: `config.py` 的 `Config` 类（pydantic_settings.BaseSettings）
- **配置访问**: `from ..config import config`，然后 `config.game_config["key"]`, `config.items_config["by_name"]["物品名"]`
- **游戏配置路径**: `data/config.yaml`（修炼/突破/掉落率/经济等参数）
- **物品配置路径**: `data/items.yaml`（物品定义，包含 `special_effects` YAML 块）
- **数据库配置路径**: `config/database.yaml`（SQLite/MySQL 连接参数）
- **NoneBot配置**: `.env` 文件（`USE_NEW_EFFECT_SYSTEM=true`, `COMMAND_START=["/",""]` 等）

---

#### conclusions

1. **架构模式**: DDD 四层架构（Models → Repository → UoW → Service），Repository 模式 + Unit of Work + 手动 DI（非纯 DI 注入）
2. **文件命名约定**: `_new.py` 为 DI 版本，`_legacy.py` 为旧版（已全部清理），无后缀为统一入口；全部架构迁移于 2026-01-10 完成
3. **ORM**: SQLAlchemy 2.0 异步 API，`Mapped[T]`语法，`select()` + `execute()` 查询风格
4. **枚举**: 所有枚举继承 `str, PyEnum`，可作字符串直接使用
5. **事务边界**: 严格在 `async with UnitOfWork()` 内部完成所有数据操作，在 UoW 外部调用 `finish()` 发送响应
6. **数据库迁移**: 只使用 `auto_migrate.py` 的 `REQUIRED_FIELDS` 字典，禁止 Alembic 命令
7. **效果系统**: 三层设计（IEffect接口 → EffectRegistry全局注册中心 → BattleEffectBridge桥接战斗效果），支持装饰器注册
8. **AI 集成**: 智谱 GLM 主 + 302.ai 备用，通过 `call_zhipu_api` 统一调用，配置在 `config.yaml` 的 `ai_dialogue` 节点
9. **故事引擎**: 状态机模式，从 JSON 文件驱动，支持 and/or/嵌套条件，无需修改代码即可添加新故事
10. **帮助信息**: 添加任何命令都必须更新 `player/help.py`，否则【帮助】命令无法显示

---

#### relations

- `guild.py`（命令处理器）调用 `UnitOfWork`，从 `uow.players`/`uow.guilds` 获取 Repository，手动创建 `GuildService(player_repo=uow.players, guild_repo=uow.guilds)`
- `UnitOfWork` 管理所有 Repository 属性，所有 Repository 共享同一个 `AsyncSession`
- `UnitOfWork.__aexit__` 特殊检测 NoneBot2 的 `FinishedException` → 提交而非回滚
- `auto_migrate.py` 在 Bot 启动时由 `models/db.py` 的 `init_db()` 调用
- `EffectRegistry`（全局单例） ← `BattleEffectBridge`（桥接层） ← `BattleEffectManager`（战斗引擎核心）
- `EnhancedBattleEngine` 调用 `BattleEffectManager.check_triggers()` → 查找匹配效果 → 应用到战斗状态
- `AIDialogueService` 从 `config.game_config["ai_dialogue"]` 读取配置，调用 `call_zhipu_api`
- `Config`（pydantic BaseSettings）→ 加载 YAML 文件 → 建立 `items_config` 的三种索引（by_id/by_name/by_type）
- `StoryEngine` 从 `data/stories/*.json` 加载，通过 `evaluate_condition()` 评估节点条件，通过 `AsyncSession` 访问 Player 数据

---

**生成时间**: 2026-02-18
**报告类型**: 技术架构全面调查（用于编写编码提示词）
