# Repository 模式实现架构

## 1. Identity

- **What it is**: 基于泛型接口 `IRepository[T]` 的数据访问抽象层，包含 42 个具体仓储实现
- **Purpose**: 解耦业务逻辑与数据库操作细节，提供可测试的数据访问接口，支持领域查询方法

## 2. Core Components

- `domain/repositories/base.py` (`IRepository`): 仓储基础接口，定义标准 CRUD 操作（get_by_id, add, update, delete, exists, count）
- `infrastructure/repositories/player_repository.py` (`PlayerRepository`): 玩家仓储，包含 get_by_uid, get_with_monthly_cards 等领域查询
- `infrastructure/repositories/guild_repository.py` (`GuildRepository`): 公会仓储，管理 Guild 和 GuildMember 实体
- `infrastructure/repositories/item_repository.py` (`ItemRepository`): 物品仓储，处理物品实例 CRUD 操作
- `infrastructure/repositories/stock_repository.py` (`StockRepository`): 股票仓储，包含股票查询和状态管理
- `infrastructure/repositories/daily_task_repository.py` (`DailyTaskRepository`): 每日任务仓储，处理任务链查询
- ... (共 42 个仓储实现，覆盖所有领域实体)

## 3. Execution Flow (LLM Retrieval Map)

### 标准数据查询流程
- **1. 接口定义**: `domain/repositories/base.py:14-113` 定义泛型接口 `IRepository[T]`，包含抽象方法
- **2. 具体实现**: `infrastructure/repositories/player_repository.py` 实现接口，通过构造函数注入 `AsyncSession`
- **3. 延迟初始化**: `infrastructure/uow/unit_of_work.py:94-99` 通过属性装饰器延迟创建 Repository 实例
- **4. 查询执行**: `infrastructure/repositories/player_repository.py` 使用 SQLAlchemy 2.0 风格的 `select()` 语句查询数据

### 领域查询方法示例
- **1. 定义领域方法**: `player_repository.py:272-276` 实现 `get_by_uid()` 方法，根据 QQ UID 查询玩家
- **2. 关联加载优化**: `player_repository.py:278-286` 使用 `joinedload()` 解决 N+1 查询问题
- **3. 复杂查询**: `guild_repository.py` 实现多表关联查询，处理公会成员和建筑数据

## 4. Design Rationale

**为什么使用 Repository 模式**：
1. **抽象数据访问**：隐藏 SQLAlchemy 细节，业务逻辑只操作领域对象
2. **可测试性**：通过 Mock Repository 进行单元测试，无需连接真实数据库
3. **查询集中化**：领域特定查询方法（如 `get_by_uid`）集中在 Repository 中，避免 SQL 分散
4. **替换灵活性**：未来可替换 ORM 实现（如切换到 Tortoise ORM）而不影响业务代码

**Repository 设计规范**：
- 继承 `IRepository[EntityType]` 泛型接口
- 通过构造函数接收 `AsyncSession`（由 Unit of Work 注入）
- 实现 `get_by_id`, `add`, `update`, `delete`, `exists`, `count` 标准方法
- 添加领域特定查询方法（如 `get_with_monthly_cards`）
- 使用 `select()` + `execute()` 进行查询，返回强类型对象
