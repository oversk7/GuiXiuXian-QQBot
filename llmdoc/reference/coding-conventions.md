# 编码规范 (Coding Conventions)

## 1. Python代码风格

### 1.1 基础风格
- **Python版本**: Python 3.9+
- **编码**: UTF-8
- **缩进**: 4空格
- **行长**: 不超过120字符 (软限制)
- **导入顺序**: 标准库 → 第三方库 → 本地模块

### 1.2 类型注解 (Type Hints)
- **强制使用**: 所有公共函数和方法必须使用类型注解
- **ORM字段**: 使用SQLAlchemy 2.0的`Mapped[T]`语法 (`plugins/xiuxian_game/models/player.py:20-30`)
- **泛型支持**: 使用`Generic[T]`实现泛型类 (`plugins/xiuxian_game/domain/repositories/base.py:10`)

### 1.3 字符串风格
- **文档字符串**: 三引号`"""`,使用Google风格
- **普通字符串**: 优先使用双引号`"`
- **SQL语句**: 使用三引号多行字符串

---

## 2. 命名约定

### 2.1 类命名 (Class Naming)
- **格式**: `PascalCase` (大驼峰)
- **服务类**: `功能名 + Service` (如`GuildService`, `EquipmentService`)
- **仓储类**: `实体名 + Repository` (如`PlayerRepository`)
- **枚举类**: 继承`str`和`Enum` (如`class TriggerType(str, Enum)`)
- **数据类**: 使用`@dataclass`,描述性名称 (如`BattleEffect`, `TriggerConfig`)

### 2.2 函数和方法命名 (Function/Method Naming)
- **格式**: `snake_case` (小写+下划线)
- **异步函数**: `async def`,必须包含`async`前缀提示
- **私有方法**: 单下划线前缀 `_private_method`
- **保护方法**: 双下划线前缀 `__protected_method` (谨慎使用)

### 2.3 变量命名 (Variable Naming)
- **格式**: `snake_case`
- **常量**: `UPPER_SNAKE_CASE` (如`ATTRIBUTE_CAPS`)
- **实例变量**: 私有属性使用单下划线前缀 `self._session`
- **布尔变量**: 使用`is/has/can`前缀 (如`is_active`, `has_permission`)

### 2.4 文件命名 (File Naming)
- **格式**: `snake_case.py`
- **后缀约定**:
  - `_legacy.py` - 旧架构代码 (静态方法,直接传session)
  - `_new.py` - 新架构代码 (实例方法,DI)
  - 无后缀 - 统一入口或工具模块

---

## 3. 文件组织约定

### 3.1 目录结构
```
plugins/xiuxian_game/
├── models/              # 数据模型层 (ORM实体)
├── domain/              # 领域层 (接口,值对象)
│   ├── repositories/    # 仓储接口
│   └── attributes/      # 属性系统
├── infrastructure/      # 基础设施层
│   ├── repositories/    # 仓储实现
│   └── uow/            # Unit of Work
├── guild/              # 公会领域 (业务逻辑)
├── battle/             # 战斗领域
├── config/             # 配置文件
└── utils.py            # 全局工具函数
```

### 3.2 服务编写规范
**标准模式**(2026-06-10 起全库统一,新旧双轨已合并完毕):
- 实例方法类,通过构造函数注入 Repository
- 不内部 commit,由外层 safe_session/UoW 控制事务
- 示例: `plugins/xiuxian_game/item/equipment_service.py`

**兼容入口**:
- 历史静态调用面保留为模块级函数,内部委托唯一的 Service 实现
- 示例: `equipment_service.recalc_equipment_attributes(session, ...)`、`guild_building_service.get_guild_bonuses(session, ...)`

---

## 4. 关键设计模式约定

### 4.1 Repository模式
**实现规范**:
- 继承`IRepository[T]`接口 (`plugins/xiuxian_game/domain/repositories/base.py:10-40`)
- 通过构造函数接收`AsyncSession`
- 实现6个标准方法: `get_by_id`, `add`, `update`, `delete`, `exists`, `count`
- 添加领域查询方法 (如`get_by_uid`, `get_with_monthly_cards`)
- 不直接commit,仅返回对象

**示例**:
```python
class PlayerRepository(IRepository[Player]):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, player_id: str) -> Optional[Player]:
        stmt = select(Player).where(Player.id == player_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
```

### 4.2 Unit of Work模式
**实现规范**:
- 继承`UnitOfWork`基类 (`plugins/xiuxian_game/infrastructure/uow/unit_of_work.py:20-100`)
- 延迟初始化所有Repository属性
- 实现上下文管理器`async with`
- 自动管理commit/rollback
- 特殊处理Nonebot2的`FinishedException`

**使用规范**:
```python
async with UnitOfWork(session_factory) as uow:
    player = await uow.players.get_by_id(player_id)
    # 业务逻辑...
    # 自动提交或回滚
```

### 4.3 依赖注入 (DI)模式
**实现规范**:
- Service通过构造函数接收依赖
- 不使用全局变量或单例模式(除明确配置外)
- Repository由UoW注入,不由DI容器直接创建

**示例**:
```python
class GuildService:
    def __init__(
        self,
        player_repo: PlayerRepository,
        guild_repo: GuildRepository,
        uow: Optional[UnitOfWork] = None
    ):
        self._player_repo = player_repo
        self._guild_repo = guild_repo
        self._uow = uow
```

### 4.4 策略模式
**应用场景**: 属性来源系统 (`plugins/xiuxian_game/domain/attributes/attribute_sources/`)
- 实现`IAttributeSource`接口
- 每个Source独立计算策略
- 通过`AttributeCalculator`组合使用

---

## 5. 异步编程约定

### 5.1 异步函数
- **数据库操作**: 必须使用`async/await`
- **I/O操作**: 推荐使用`async/await` (如HTTP请求)
- **CPU密集**: 使用`asyncio.to_thread`或线程池

### 5.2 异步上下文管理
- **Session管理**: 使用`async with AsyncSessionLocal() as session:`
- **UoW管理**: 使用`async with UnitOfWork(session_factory) as uow:`

### 5.3 并发控制
- **批量查询**: 使用`asyncio.gather`并发执行
- **锁机制**: 使用`asyncio.Lock`而非`threading.Lock`

---

## 6. 数据库操作约定

### 6.1 ORM使用规范
- **查询**: 使用`select()`构建查询,避免`session.query()`
- **关系加载**: 使用`joinedload()`预加载,避免N+1问题 (`plugins/xiuxian_game/infrastructure/repositories/player_repository.py:78-86`)
- **批量操作**: 使用`update()`/`delete()`批量更新删除
- **事务**: 由UoW统一管理,不在Service内部commit

### 6.2 数据库迁移
- **禁止使用Alembic命令**
- **使用auto_migrate**: 在`plugins/xiuxian_game/models/auto_migrate.py`的`REQUIRED_FIELDS`中添加字段定义
- **重启Bot**: 自动检测并添加缺失字段/表/索引

### 6.3 连接泄漏防护
- **必须规则**: 在UoW外部调用`cmd.finish()`
- **错误示例**:
```python
async with UnitOfWork(session_factory) as uow:
    if not player:
        await cmd.finish("⛔ 错误")  # ❌ 连接泄漏
```
- **正确示例**:
```python
async with UnitOfWork(session_factory) as uow:
    if not player:
        error_msg = "⛔ 错误"
if error_msg:
    await cmd.finish(error_msg)  # ✅
```

---

## 7. 配置管理约定

### 7.1 配置文件位置
- **数据库配置**: `plugins/xiuxian_game/config/database.yaml`
- **物品配置**: `plugins/xiuxian_game/config/items.yaml`
- **游戏配置**: `plugins/xiuxian_game/data/config.yaml`

### 7.2 配置加载
- 使用YAML格式
- 支持环境变量覆盖
- 启动时一次性加载,避免频繁IO

---

## 8. 错误处理约定

### 8.1 异常处理
- **业务逻辑错误**: 返回`(False, "错误消息")`元组
- **系统异常**: 捕获并记录日志,返回友好提示
- **数据库异常**: 捕获`SQLAlchemyError`,触发回滚

### 8.2 日志规范
- **级别**:
  - `DEBUG`: 详细调试信息
  - `INFO`: 关键流程节点
  - `WARNING`: 可恢复的异常情况
  - `ERROR`: 错误但程序可继续
  - `SUCCESS`: 成功操作 (使用loguru的扩展级别)

---

## 9. 测试约定

### 9.1 单元测试
- **位置**: `tests/`目录
- **命名**: `test_<模块名>.py`
- **Mock**: 使用`unittest.mock` Mock Repository

### 9.2 测试覆盖
- Repository层: 必须覆盖
- Service层: 优先覆盖核心业务逻辑
- 集成测试: 关键流程端到端测试

---

## 10. 文档约定

### 10.1 代码注释
- **类文档**: 描述职责和依赖
- **方法文档**: Args/Returns/Raises格式
- **复杂逻辑**: 行内注释说明原因

### 10.2 API文档
- **命令帮助**: 更新`plugins/xiuxian_game/player/help.py`
- **架构文档**: 更新`llmdoc/architecture/`
- **参考文档**: 更新`llmdoc/reference/`

---

## 11. 性能优化约定

### 11.1 缓存策略
- **临时buff缓存**: 60秒TTL (`plugins/xiuxian_game/domain/attributes/attribute_sources/buff_source.py:40-50`)
- **装备属性预计算**: 持久化到player表
- **单例模式**: 全局共享实例 (如`AttributeCalculatorFactory`)

### 11.2 数据库优化
- **索引**: 关键查询字段添加`index=True`
- **批量查询**: `get_many_by_ids()`减少往返
- **预加载**: `joinedload()`避免N+1

---

## 12. 安全约定

### 12.1 输入验证
- **用户输入**: 必须验证和清理
- **SQL注入**: 禁止字符串拼接SQL,使用参数化查询
- **权限检查**: 敏感操作验证玩家身份

### 12.2 敏感数据
- **密码**: 使用哈希存储
- **API密钥**: 使用环境变量,不提交到Git
- **玩家数据**: 遵循隐私保护原则

---

## 附录: 快速检查清单

### 代码提交前检查
- [ ] 所有公共函数有类型注解
- [ ] 异步函数使用`async/await`
- [ ] 使用Repository而非直接Session
- [ ] UoW外部调用`finish()`
- [ ] 数据库字段添加到`REQUIRED_FIELDS`
- [ ] 更新帮助文档`help.py`
- [ ] 通过单元测试

### 架构迁移检查
- [ ] Repository实现`IRepository[T]`
- [ ] Service通过构造函数注入
- [ ] 移除内部`session.commit()`
- [ ] 使用`async with UnitOfWork()`
- [ ] 更新文档标记为已完成

---

**版本**: 1.0
**最后更新**: 2026-01-10
**维护者**: 项目架构组
