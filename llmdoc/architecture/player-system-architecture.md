# 玩家系统架构设计

## 1. Identity

- **What it is**: 基于Repository+UnitOfWork+DI模式的玩家数据管理架构
- **Purpose**: 提供高性能、可测试的玩家数据访问和业务逻辑处理

## 2. Core Components

- `plugins/xiuxian_game/models/player.py` (Player类): 核心玩家数据模型,包含30+字段(基础信息、属性、坐标、社交关系、时间戳)
- `plugins/xiuxian_game/infrastructure/repositories/player_repository.py` (PlayerRepository): 玩家仓储实现,提供CRUD和领域查询方法(get_by_uid, get_nearby_players, get_guild_members等)
- `plugins/xiuxian_game/infrastructure/uow/unit_of_work.py` (UnitOfWork): 统一事务管理,自动commit/rollback,确保原子性
- `plugins/xiuxian_game/player/info.py` (profile/register/change_gender命令): 玩家信息命令处理器,支持智能输入解析和分步注册流程
- `plugins/xiuxian_game/models/monthly_card.py` (MonthlyCard类): 月卡系统,提供修炼效率、背包容量等加成
- `plugins/xiuxian_game/models/marriage.py` (Marriage类): 婚姻关系记录
- `plugins/xiuxian_game/models/mentorship.py` (Mentorship类): 师徒关系记录
- `plugins/xiuxian_game/models/npc_favorability.py` (NPCFavorability类): NPC好感度关系
- `plugins/xiuxian_game/models/account_ownership.py` (AccountOwnership类): 多账号所有权管理

## 3. Execution Flow (LLM Retrieval Map)

### 3.1 查看玩家面板流程
- **1. 命令接收**: 用户输入【角色】或【面板】,`plugins/xiuxian_game/player/info.py:230-280`解析参数
- **2. 事务创建**: `plugins/xiuxian_game/infrastructure/uow/unit_of_work.py:40-60`创建UnitOfWork上下文
- **3. 数据查询**: `plugins/xiuxian_game/infrastructure/repositories/player_repository.py:30-45`通过get_by_id查询Player对象
- **4. 坐标更新**: `plugins/xiuxian_game/models/player.py:180-200`的get_current_coordinates()自动导航
- **5. 属性计算**: `plugins/xiuxian_game/domain/attributes/player_attributes_integration.py:20-35`的get_effective_attributes_v2()计算有效属性
- **6. 装备统计**: `plugins/xiuxian_game/item/equipment_service.py:15-25`查询装备列表并统计加成
- **7. 公会信息**: `plugins/xiuxian_game/infrastructure/repositories/guild_repository.py:50-65`查询公会数据
- **8. 格式化输出**: `plugins/xiuxian_game/player/info.py:285-350`格式化属性显示(基础+加成)
- **9. 附加检查**: `plugins/xiuxian_game/player/info.py:355-380`检查未读留言、私信、新手任务、成就

### 3.2 创建角色流程
- **1. 命令解析**: `plugins/xiuxian_game/player/info.py:50-100`解析昵称和性别,支持智能输入清理
- **2. 前置检查**: `plugins/xiuxian_game/player/info.py:105-125`检查是否已有角色或转让历史
- **3. UID生成**: `plugins/xiuxian_game/player/info.py:130-145`查询当前最大UID并分配新UID
- **4. 实例创建**: `plugins/xiuxian_game/models/player.py:60-120`创建Player实例,初始化默认属性
- **5. 任务初始化**: `plugins/xiuxian_game/quest/newbie_quest.py:20-40`初始化新手任务
- **6. 事务提交**: UnitOfWork自动提交,`plugins/xiuxian_game/infrastructure/uow/unit_of_work.py:80-100`处理异常
- **7. 响应发送**: `plugins/xiuxian_game/player/info.py:150-170`发送注册成功消息

### 3.3 玩家数据关联查询流程
- **1. 预加载优化**: `plugins/xiuxian_game/infrastructure/repositories/player_repository.py:78-86`使用joinedload预加载MonthlyCard
- **2. 批量查询**: `plugins/xiuxian_game/infrastructure/repositories/player_repository.py:120-135`的get_many_by_ids()减少数据库往返
- **3. 地理查询**: `plugins/xiuxian_game/infrastructure/repositories/player_repository.py:145-165`使用边界框+曼哈顿距离优化附近玩家查询

## 4. Design Rationale

**为什么使用Repository模式?**
- **数据访问抽象**: 隐藏SQLAlchemy实现细节,提供领域模型风格的接口
- **可测试性**: 可通过Mock Repository进行单元测试,无需真实数据库
- **统一接口**: 所有Repository继承IRepository[T],保证接口一致性

**为什么使用UnitOfWork模式?**
- **事务边界管理**: 确保多个Repository操作的原子性,避免数据不一致
- **连接泄漏防护**: 自动管理Session生命周期,特殊处理Nonebot2流程控制异常
- **延迟初始化**: Repository仅在首次访问时创建,减少资源消耗

**为什么双轨架构并存?**
- **渐进式迁移**: 保留Legacy版本确保稳定性,New版本采用DI架构提高可测试性
- **向后兼容**: 统一入口调用new版本,旧代码无需修改
- **降低风险**: 逐步迁移调用方,避免大规模重构导致的bug

**为什么装备加成持久化到player属性?**
- **性能优化**: 避免每次战斗重新计算装备加成,提升战斗系统性能
- **简化查询**: 无需关联inventory表,直接读取player属性即可
- **特殊处理**: mp_from_hp特效基于HP百分比转MP,需要持久化后才能正确计算
