# Service DI架构实现

## 1. Identity

- **What it is**: 诡修仙项目Service层依赖注入（DI）架构的技术实现文档
- **Purpose**: 为LLM代理提供DI架构的核心组件、执行流程和集成模式的检索地图

## 2. Core Components

### 基础设施层 (Infrastructure)

`plugins/xiuxian_game/infrastructure/di/container.py` (Container, register, resolve, create_scope): DI容器实现，支持三种生命周期管理

`plugins/xiuxian_game/infrastructure/uow/unit_of_work.py` (UnitOfWork, commit, rollback, __aenter__, __aexit__): 工作单元模式，统一事务边界，懒加载47个Repository

`plugins/xiuxian_game/infrastructure/repositories/*.py` (47个Repository类): 数据访问抽象层，实现CRUD和业务查询方法

### 领域层 (Domain)

`plugins/xiuxian_game/domain/repositories/base.py` (IRepository[T]): 仓储接口定义，泛型支持

`plugins/xiuxian_game/domain/repositories/*.py` (47个接口): 各业务实体的Repository接口定义

### Service层 (Application)

所有Service类从静态方法改为实例方法模式：
- `plugins/xiuxian_game/guild/guild_service_new.py` (GuildServiceNew)
- `plugins/xiuxian_game/item/equipment_service_new.py` (EquipmentServiceNew)
- `plugins/xiuxian_game/economy/stock_service_new.py` (StockServiceNew)
- ...等27个Service类

### 命令处理层 (Presentation)

所有命令处理器通过Feature Flag集成新旧实现：
- `plugins/xiuxian_game/guild/guild.py` (USE_NEW_GUILD_SERVICE = True)
- `plugins/xiuxian_game/item/equipment_commands.py` (USE_NEW_EQUIPMENT_SERVICE = True)
- ...等46个命令处理文件

## 3. Execution Flow (LLM Retrieval Map)

### DI容器生命周期

**1. 注册阶段**: 应用启动时注册所有Service和Repository
- 位置: `plugins/xiuxian_game/__init__.py:on_startup`
- 操作: `container.register(GuildService, GuildServiceNew, lifetime='scoped')`

**2. 解析阶段**: 处理命令时创建作用域容器
- 位置: 命令处理器开头
- 操作: `scope = container.create_scope()`

**3. 注入阶段**: 从作用域容器解析Service实例
- 操作: `service = scope.resolve(GuildService)`
- 依赖: 自动注入构造函数所需的Repository

**4. 清理阶段**: 命令处理结束时销毁作用域
- 操作: `scope.dispose()`
- 效果: 释放scoped生命周期的实例

### UnitOfWork事务流程

**1. 创建UoW**: 在命令处理器中创建工作单元
```python
# 位置: guild/guild.py:create_guild_handler
async with UnitOfWork() as uow:
```

**2. 解析Repository**: 懒加载访问Repository属性
```python
# uow.guilds首次访问时创建GuildRepository实例
guild_repo = uow.guilds
```

**3. 业务操作**: 通过Repository执行数据访问
```python
# 所有操作使用同一个session
guild = await guild_repo.add(new_guild)
member = await uow.guild_members.add(new_member)
```

**4. 事务提交**: 退出上下文时自动提交或回滚
```python
# UnitOfWork.__aexit__自动调用commit或rollback
await uow.commit()
```

### Service调用流程（新架构）

**1. 命令接收**: Nonebot2接收用户命令
- 位置: `guild/guild.py:create_guild`

**2. Feature Flag判断**: 检查是否使用新架构
```python
if USE_NEW_GUILD_SERVICE:
    # 新架构路径
else:
    # 旧架构路径（保留兼容）
```

**3. 创建UoW**: 打开工作单元
```python
async with UnitOfWork() as uow:
```

**4. 解析Service**: 从DI容器获取Service实例
```python
service = GuildServiceNew(
    uow.guilds,
    uow.players,
    uow.guild_members
)
```

**5. 调用方法**: 执行业务逻辑
```python
guild = await service.create_guild(player_id, name)
```

**6. 提交事务**: UoW自动提交
```python
# __aexit__自动调用
await uow.commit()
```

**7. 响应用户**: 返回结果消息
```python
await matcher.send(f"公会{name}创建成功")
```

## 4. Design Rationale

### 为什么使用DI容器而不是手动注入？

**优势**:
- 集中管理依赖配置
- 支持生命周期管理（singleton/scoped/transient）
- 自动解析依赖链
- 便于测试时替换实现

**对比手动注入**:
```python
# 手动注入（繁琐，重复代码）
guild_repo = GuildRepository(session)
player_repo = PlayerRepository(session)
service = GuildService(guild_repo, player_repo)

# DI容器（简洁，配置化）
service = container.resolve(GuildService)
```

### 为什么Repository和Service分离？

**职责分离**:
- Repository: 数据访问抽象，封装SQL查询逻辑
- Service: 业务逻辑编排，协调多个Repository

**可测试性**:
- Repository可独立测试（真实数据库或Mock）
- Service可Mock Repository测试业务逻辑

**可替换性**:
- 更换数据源只需替换Repository实现
- 业务逻辑不受影响

### 为什么保留Feature Flag？

**风险控制**:
- 灰度发布，逐步切换
- 快速回滚，修改常量即可
- A/B测试，对比新旧性能

**部署策略**:
```python
# 阶段1: 开发完成，Feature Flag = False（使用旧版）
USE_NEW_GUILD_SERVICE = False

# 阶段2: 测试验证，Feature Flag = True（小范围测试）
USE_NEW_GUILD_SERVICE = True

# 阶段3: 全量上线，移除旧代码（未来清理）
# 删除旧版本代码和Feature Flag判断
```

### 为什么UoW懒加载Repository？

**性能优化**:
- 只创建实际使用的Repository实例
- 避免初始化不需要的依赖

**代码示例**:
```python
# UnitOfWork.__init__不创建Repository
self._guilds = None

# 首次访问时才创建
@property
def guilds(self) -> GuildRepository:
    if self._guilds is None:
        self._guilds = GuildRepository(self.session)
    return self._guilds
```

## 5. 集成模式

### 模式A: 简单Service（单Repository）

**适用场景**: Service只依赖1-2个Repository

**代码示例**:
```python
# Service定义
class FishingServiceNew:
    def __init__(self, fishing_repo: FishingRepository):
        self.fishing_repo = fishing_repo

# 命令处理器集成
async with UnitOfWork() as uow:
    service = FishingServiceNew(uow.fishing)
    result = await service.cast_rod(player_id)
    await uow.commit()
```

### 模式B: 复杂Service（多Repository）

**适用场景**: Service依赖3个以上Repository

**代码示例**:
```python
# Service定义
class GuildServiceNew:
    def __init__(
        self,
        guild_repo: GuildRepository,
        player_repo: PlayerRepository,
        member_repo: GuildMemberRepository,
        building_repo: GuildBuildingRepository
    ):
        self.guild_repo = guild_repo
        self.player_repo = player_repo
        self.member_repo = member_repo
        self.building_repo = building_repo

# 命令处理器集成
async with UnitOfWork() as uow:
    service = GuildServiceNew(
        uow.guilds,
        uow.players,
        uow.guild_members,
        uow.guild_buildings
    )
    guild = await service.create_guild(player_id, name)
    await uow.commit()
```

### 模式C: Service间协作

**适用场景**: Service A需要调用Service B

**代码示例**:
```python
# GuildFacilityService调用GuildBuildingService
class GuildFacilityServiceNew:
    def __init__(self, ...):
        # 不在构造函数注入其他Service
        pass

    async def can_use_teleport(self, guild_id: int) -> bool:
        # 在方法内部创建依赖的Service
        building_service = GuildBuildingServiceNew(
            self.building_repo,
            self.guild_repo
        )
        config = await building_service.get_building_config(
            guild_id, "传送阵"
        )
        return config is not None
```

### 模式D: N+1查询优化

**适用场景**: 避免循环中逐个查询关联对象

**代码示例**:
```python
# Repository实现预加载
class PlayerRepository(BaseRepository[Player]):
    async def get_with_monthly_cards(
        self, player_id: int
    ) -> Player | None:
        # 使用joinedload预加载关联
        result = await self.session.execute(
            select(Player)
            .options(joinedload(Player.monthly_cards))
            .where(Player.id == player_id)
        )
        return result.unique().scalar_one_or_none()

# Service调用
player = await self.player_repo.get_with_monthly_cards(player_id)
# 直接访问关联对象，不触发额外查询
for card in player.monthly_cards:
    # ...
```

## 6. 重构对比

### 属性计算器（未重构，待优化）

**当前状态**: 5处属性计算位置
- `player.py:get_effective_attributes` - 主入口（含buff）
- `equipment_commands.py:recalc_equipment_attributes` - 装备重算
- `battle/attribute_calculator.py:calculate_effective_attributes` - 战斗属性（同步版本）
- `item/item_effects.py` - 物品效果临时属性
- `world_boss/__init__.py` - 世界BOSS属性加成

**未来重构方向**: 统一到AttributeCalculator，使用组合模式

### 效果系统（部分重构）

**物品效果**: 保留装饰器注册系统
- `item/item_effects.py:_REGISTRY` - 45+种效果
- `item/item_effects.py:register` - 装饰器注册

**战斗效果**: 保留管理器模式
- `battle/battle_effects.py:BattleEffectManager` - 75+种效果
- `battle/battle_effects.py:TriggerConfig` - 触发配置

**未来统一方向**: IEffect接口 + BattleEffectBridge适配器

---

**相关文档**:
- 完成里程碑: `/llmdoc/overview/service-di-completion.md`
- 重构进度: `/SERVICE_REFACTORING_PROGRESS.md`
- 当前架构: `/llmdoc/architecture/current-architecture.md`
- 数据访问层: `/llmdoc/architecture/data-access-layer.md`
