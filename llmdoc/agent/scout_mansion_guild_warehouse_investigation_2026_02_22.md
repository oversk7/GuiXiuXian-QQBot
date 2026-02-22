# 阴宅系统与公会仓库集成调查报告
<!-- 调查日期: 2026-02-22 -->
<!-- 任务: 调查阴宅命令结构、模型注册方式、位置检查逻辑、ItemType枚举值 -->

## 调查目标

1. 读取 `plugins/xiuxian_game/__init__.py`，查看插件注册方式（如何导入其他命令模块）
2. 读取 `plugins/xiuxian_game/models/__init__.py`（若存在），查看模型注册方式
3. 读取 `plugins/xiuxian_game/models/guild.py` 第1-85行，查看 GuildWarehouseItem 完整模型定义
4. 读取 `plugins/xiuxian_game/cultivate/mansion_commands.py` 完整内容（查看现有阴宅命令的结构，尤其是位置检查逻辑）
5. 读取 `plugins/xiuxian_game/cultivate/mansion_service_new.py` 完整内容（查看 MansionService 完整实现，尤其是坐标/位置检查方法）
6. 读取 `plugins/xiuxian_game/infrastructure/repositories/guild_warehouse_item_repository.py` 完整内容
7. 读取 `plugins/xiuxian_game/player/help.py` 查看帮助命令的结构（前50行即可）
8. 读取 `plugins/xiuxian_game/models/auto_migrate.py` 前30行，了解迁移格式

---

## Code Sections (证据)

### 插件注册与模块导入

- `plugins/xiuxian_game/__init__.py:16-43` - **插件子模块导入区块**
  - 使用相对导入 `from . import` 导入所有子系统模块
  - 第19行导入 `cultivate` 模块（包含阴宅系统）
  - 第24行导入 `guild` 模块（包含公会系统）
  - **重要**: mansion_commands 通过 `cultivate.__init__.py` 自动导入

- `plugins/xiuxian_game/cultivate/__init__.py:1-7` - **cultivate模块导入结构**
  - 第4行导入 `mansion_commands` 模块以注册命令
  - 第6行导出 `MansionService` 供外部使用

### 模型注册与数据库结构

- `plugins/xiuxian_game/models/__init__.py:1-88` - **模型统一导出清单**
  - 第5行导入公会相关所有模型（包括 `GuildWarehouseItem`）
  - 第65-88行 `__all__` 列表定义了公开的模型
  - 所有模型统一从此文件导出，便于外部导入

- `plugins/xiuxian_game/models/guild.py:85-98` - **GuildWarehouseItem完整模型定义**
  - 表名: `guild_warehouse_item`
  - 字段:
    - `id` (Integer, 主键, 自增)
    - `guild_id` (Integer, ForeignKey("guild.id"), 公会ID)
    - `item_id` (String(32), 物品ID)
    - `quantity` (Integer, default=1, 数量)
    - `deposited_by` (String(32), 存入者玩家ID)
    - `deposited_at` (DateTime, 存入时间)
  - **无 item_type 字段**，物品类型通过 `item_id` 从配置中获取

- `plugins/xiuxian_game/models/inventory.py:13-28` - **ItemType枚举完整定义**
  - 枚举值类型: `str, PyEnum`
  - 具体枚举值:
    - `CONSUMABLE = "CONSUMABLE"` (消耗品)
    - `MATERIAL = "MATERIAL"` (材料)
    - `EQUIPMENT = "EQUIPMENT"` (装备)
    - `GOODS = "GOODS"` (商品)
    - `GHOST_FRAGMENT = "GHOST_FRAGMENT"` (鬼魂碎片)
    - `GEM = "GEM"` (宝石)
    - `FISH = "FISH"` (鱼类)
    - `GIFT = "GIFT"` (好感度礼物)
    - `SEASONING = "SEASONING"` (调料)
    - `DISH = "DISH"` (菜肴)
    - `RECIPE = "RECIPE"` (食谱)
    - `VEGETABLE = "VEGETABLE"` (灵蔬)
    - `HERB = "HERB"` (诡药)
    - `SEED = "SEED"` (灵种)
    - `GUARDIAN_BEAST = "GUARDIAN_BEAST"` (诡兽)

### 阴宅命令处理器结构

- `plugins/xiuxian_game/cultivate/mansion_commands.py:12-19` - **阴宅命令注册列表**
  - 使用 `on_command` 注册7个阴宅命令
  - 所有命令优先级为4，block=True
  - 命令包括: 阴宅状态、购买、升级、设置费用、切换权限、切换付费意愿、迁移阴宅

- `plugins/xiuxian_game/cultivate/mansion_commands.py:22-37` - **查看阴宅状态命令处理器**
  - 使用 `safe_session()` 上下文管理器
  - 通过 `session.get(Player, user_id)` 获取玩家数据
  - 调用 `MansionService.format_mansion_status(player)` 静态方法格式化输出
  - **不使用Repository，直接使用Session查询**

- `plugins/xiuxian_game/cultivate/mansion_commands.py:72-107` - **升级阴宅命令处理器**
  - 第86-90行: **检查是否拥有阴宅** (`player.mansion_level <= 0`)
  - 第93-98行: **实例化MansionService并注入PlayerRepository**
  - 第99行: 调用 `service.upgrade_mansion(player)` 执行升级
  - 第102-103行: 手动保存数据 (`session.add(player)` + `await session.commit()`)
  - **位置检查在service内部执行，而非command层**

- `plugins/xiuxian_game/cultivate/mansion_commands.py:221-324` - **迁移阴宅命令处理器（复杂流程）**
  - 第227-277行: 无参数时显示迁移确认信息
  - 第238行: 使用 `MansionService.has_mansion(player)` 检查是否拥有阴宅
  - 第246-257行: 调用 `service.can_migrate_mansion(player, target_x, target_y)` 检查迁移条件
  - 第280-297行: 确认后执行迁移 `service.migrate_mansion(player, target_x, target_y)`
  - **采用确认机制，第一次调用显示信息，第二次调用执行操作**

### 阴宅服务层实现

- `plugins/xiuxian_game/cultivate/mansion_service_new.py:12-34` - **MansionService类定义与配置**
  - 第27-34行: `__init__` 注入 `PlayerRepository`
  - 第15-25行: 阴宅配置常量（等级、费用、效率加成）
  - **采用DI架构，构造函数注入依赖**

- `plugins/xiuxian_game/cultivate/mansion_service_new.py:116-129` - **has_mansion与is_at_mansion静态方法**
  - `has_mansion(player)`: 检查 `player.mansion_level > 0`
  - `is_at_mansion(player)`:
    - 第123行: 先检查是否拥有阴宅
    - 第127-129行: **比较玩家当前坐标与阴宅坐标** (`player.get_current_coordinates()` vs `player.mansion_x/mansion_y`)
  - **核心位置检查逻辑**

- `plugins/xiuxian_game/cultivate/mansion_service_new.py:131-143` - **find_mansion_owner_at_location方法**
  - 通过 `PlayerRepository.find_mansion_owner_at_location(x, y)` 查询指定位置的阴宅主人
  - **Repository封装了查询逻辑**

- `plugins/xiuxian_game/cultivate/mansion_service_new.py:319-342` - **can_upgrade方法（位置检查示例）**
  - 第330-331行: 检查是否达到最大等级
  - 第334-336行: 检查金币是否足够
  - 第339-340行: **位置检查** - 如果拥有阴宅且不在阴宅位置，则无法升级
  - **返回 tuple[bool, str] - (是否成功, 错误信息)**

- `plugins/xiuxian_game/cultivate/mansion_service_new.py:435-474` - **can_migrate_mansion方法（完整位置检查示例）**
  - 第448-449行: 检查是否拥有阴宅
  - 第452-453行: 检查目标位置是否是原点(0,0)
  - 第456-457行: 检查目标位置是否与当前位置相同
  - 第460-462行: 调用 `check_distance_from_towns(target_x, target_y)` 检查距离市集的限制
  - 第465-467行: 调用 `find_mansion_owner_at_location(target_x, target_y)` 检查是否有其他玩家阴宅
  - 第470-472行: 检查金币是否足够
  - **多层次位置检查逻辑的最佳实践**

- `plugins/xiuxian_game/cultivate/mansion_service_new.py:565-593` - **check_distance_from_towns静态方法**
  - 第577行: 从 `economy.merchants` 导入 `MARKETS` 和 `HEADQUARTERS_COORD`
  - 第579行: 最小距离限制为20格
  - 第582-585行: 遍历所有市集，使用曼哈顿距离检查
  - 第588-591行: 检查与缉邪司总部的距离
  - **防止在城镇市集附近建造阴宅**

### Repository实现

- `plugins/xiuxian_game/infrastructure/repositories/guild_warehouse_item_repository.py:15-26` - **GuildWarehouseItemRepository类定义**
  - 继承 `IRepository[GuildWarehouseItem]` 泛型接口
  - 构造函数注入 `AsyncSession`
  - **标准Repository模式实现**

- `plugins/xiuxian_game/infrastructure/repositories/guild_warehouse_item_repository.py:41-61` - **get_all_by_guild_id方法**
  - 使用 SQLAlchemy 2.0 风格的 `select()` 语句
  - 第56-58行: 按 `deposited_at` 降序排序
  - 返回 `List[GuildWarehouseItem]`
  - **用于查询公会仓库所有物品**

- `plugins/xiuxian_game/infrastructure/repositories/guild_warehouse_item_repository.py:63-87` - **get_by_guild_and_item_id方法**
  - 第79-84行: 使用 `and_()` 组合多个查询条件
  - 按ID升序排序（用于堆叠物品）
  - **用于查询公会仓库中指定物品的所有堆叠**

- `plugins/xiuxian_game/infrastructure/repositories/guild_warehouse_item_repository.py:118-135` - **get_total_slots_count方法**
  - 使用 `func.count()` 聚合函数
  - 返回当前占用的格子数
  - **用于检查仓库容量**

### 帮助系统结构

- `plugins/xiuxian_game/player/help.py:24-50` - **帮助命令处理器结构**
  - 第25行: 使用 `on_command("帮助", aliases={"help","怎么玩"})`
  - 第31-50行: 使用多行字符串拼接帮助菜单
  - 第36-44行: 分类展示各系统（新手上路、成长核心、资源获取等）
  - **帮助信息直接硬编码在命令处理器中，未使用配置文件**

### 数据库迁移系统

- `plugins/xiuxian_game/models/auto_migrate.py:1-30` - **自动迁移模块头部**
  - 第4行注释: "无需手动执行 SQL 或 Alembic 命令"
  - 第6-10行: 功能列表（创建表、添加字段、创建索引、修复ENUM）
  - 第23-29行: **REQUIRED_FIELDS 字典结构**
    - 格式: `{表名: {字段名: 字段定义}}`
    - 示例: `"relisted_at": "DATETIME NULL COMMENT '重新上市时间'"`
  - **重启Bot自动执行迁移**

---

## Report (调查结果)

### result

#### 1. 插件注册方式

- **主入口**: `plugins/xiuxian_game/__init__.py` 使用相对导入 `from . import` 导入所有子系统
- **阴宅系统注册**: 第19行导入 `cultivate` 模块，`cultivate/__init__.py` 第4行导入 `mansion_commands` 自动注册命令
- **公会系统注册**: 第24行导入 `guild` 模块，包含公会仓库功能
- **无需额外配置**: 只需在子模块 `__init__.py` 中导入命令处理器文件即可自动注册

#### 2. 模型注册方式

- **统一导出**: `models/__init__.py` 统一导入所有模型并通过 `__all__` 列表公开
- **GuildWarehouseItem**: 第5行从 `guild.py` 导入，第65行添加到 `__all__`
- **自动建表**: 所有继承 `Base` 的模型会在 `init_db()` 时自动创建表
- **无需额外注册**: 只需定义模型类并添加到 `__all__` 即可

#### 3. GuildWarehouseItem 完整模型定义

```python
class GuildWarehouseItem(Base):
    __tablename__ = "guild_warehouse_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer, ForeignKey("guild.id"), comment="公会ID")
    item_id: Mapped[str] = mapped_column(String(32), comment="物品ID")
    quantity: Mapped[int] = mapped_column(Integer, default=1, comment="数量")
    deposited_by: Mapped[str] = mapped_column(String(32), comment="存入者玩家ID")
    deposited_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), comment="存入时间")
```

- **无 item_type 字段**: 物品类型通过 `item_id` 从配置中获取
- **支持堆叠**: 同一物品可有多条记录（通过 quantity 控制数量）

#### 4. 现有阴宅命令结构

- **命令注册**: 使用 `on_command` 注册7个命令，优先级4，block=True
- **Session管理**: 使用 `safe_session()` 上下文管理器
- **Service调用**: 实例化 `MansionService` 并注入 `PlayerRepository`
- **手动提交**: 调用 `session.add(player)` + `session.commit()` 保存数据
- **位置检查**: 在Service层执行，Command层只负责参数解析和结果输出
- **确认机制**: 迁移阴宅采用两步确认（第一次显示信息，第二次执行）

#### 5. 位置检查逻辑（专用函数）

**核心位置检查方法**:
- `MansionService.has_mansion(player)` - 检查是否拥有阴宅 (`mansion_level > 0`)
- `MansionService.is_at_mansion(player)` - 检查玩家是否在自己的阴宅位置
  - 通过 `player.get_current_coordinates()` 获取当前坐标
  - 比较 `(current_x, current_y)` 与 `(mansion_x, mansion_y)`
- `MansionService.check_distance_from_towns(x, y)` - 检查是否距离市集过近（20格限制）
- `MansionService.find_mansion_owner_at_location(x, y)` - 查找指定位置的阴宅主人

**位置检查使用场景**:
- `can_upgrade()` - 必须在阴宅位置才能升级
- `can_migrate_mansion()` - 检查目标位置是否合法（不在原点、不距离市集过近、无其他玩家阴宅）

#### 6. ItemType 枚举值（完整列表）

**字符串值**（用于数据库存储和配置文件）:
- `"CONSUMABLE"` - 消耗品
- `"MATERIAL"` - 材料
- `"EQUIPMENT"` - 装备
- `"GOODS"` - 商品
- `"GHOST_FRAGMENT"` - 鬼魂碎片
- `"GEM"` - 宝石
- `"FISH"` - 鱼类
- `"GIFT"` - 好感度礼物
- `"SEASONING"` - 调料
- `"DISH"` - 菜肴
- `"RECIPE"` - 食谱
- `"VEGETABLE"` - 灵蔬
- `"HERB"` - 诡药
- `"SEED"` - 灵种
- `"GUARDIAN_BEAST"` - 诡兽

**枚举类型**: `str, PyEnum`（继承自 `str` 和 `PyEnum`，可直接用于字符串比较）

#### 7. GuildWarehouseItemRepository 实现

- **继承**: `IRepository[GuildWarehouseItem]` 泛型接口
- **核心查询方法**:
  - `get_all_by_guild_id(guild_id)` - 获取公会仓库所有物品（按存入时间降序）
  - `get_by_guild_and_item_id(guild_id, item_id)` - 获取指定物品的所有堆叠（按ID升序）
  - `get_total_slots_count(guild_id)` - 获取当前占用格子数
- **CRUD操作**: `add()`, `update()`, `delete()`, `exists()`, `count()`
- **使用 SQLAlchemy 2.0 风格**: `select()` + `execute()` + `scalar_one_or_none()`

#### 8. 帮助系统结构

- **命令**: `【帮助】` 或 `【help】` 或 `【怎么玩】`
- **实现方式**: 硬编码多行字符串拼接，未使用配置文件
- **分类展示**: 新手上路、成长核心、资源获取、战斗挑战、经济市场、社交公会、图鉴记录、福利娱乐、天灾玩法
- **模块详情**: 用户发送模块名查看详细指令

#### 9. 自动迁移格式

**字段定义格式**:
```python
REQUIRED_FIELDS = {
    "表名": {
        "字段名": "字段类型 约束 COMMENT '注释'"
    }
}
```

**示例**:
```python
"stocks": {
    "relisted_at": "DATETIME NULL COMMENT '重新上市时间'",
    "relist_reason": "VARCHAR(100) NULL COMMENT '重新上市原因'"
}
```

**执行方式**: 重启Bot自动检测并添加缺失字段，无需手动SQL

---

### conclusions

1. **插件注册机制**: 采用模块自动导入机制，只需在子模块 `__init__.py` 导入命令文件即可注册，无需在主入口显式注册
2. **模型注册机制**: 所有模型在 `models/__init__.py` 统一导出，继承 `Base` 的模型会在 `init_db()` 自动建表
3. **GuildWarehouseItem无类型字段**: 仓库物品表不存储 `item_type` 字段，物品类型通过 `item_id` 从配置中获取
4. **位置检查专用函数**: MansionService 提供 `is_at_mansion(player)` 静态方法检查玩家是否在自己的阴宅位置
5. **阴宅命令采用DI架构**: 实例化Service并注入Repository，但仍需手动 `session.commit()` 保存数据
6. **ItemType枚举为字符串类型**: 继承 `str, PyEnum`，枚举值为大写字符串（如 `"MATERIAL"`, `"CONSUMABLE"`, `"GEM"`）
7. **Repository标准化实现**: 所有Repository继承 `IRepository[T]` 泛型接口，使用SQLAlchemy 2.0异步语法
8. **帮助系统硬编码**: 帮助信息直接写在命令处理器中，未使用配置文件动态管理
9. **自动迁移简化部署**: 通过 `REQUIRED_FIELDS` 字典定义字段，重启Bot自动执行迁移，零停机部署

---

### relations

1. **mansion_commands → mansion_service_new**: 命令处理器实例化MansionService并调用业务方法
2. **mansion_service_new → player_repository**: MansionService依赖PlayerRepository查询玩家和阴宅数据
3. **cultivate.__init__ → mansion_commands**: cultivate模块的 `__init__.py` 导入mansion_commands自动注册命令
4. **__init__.py → cultivate**: 主插件入口导入cultivate模块，触发阴宅命令注册
5. **models.__init__ → guild**: 模型统一导出文件导入GuildWarehouseItem等公会模型
6. **guild_warehouse_item_repository → GuildWarehouseItem**: Repository封装GuildWarehouseItem的数据访问逻辑
7. **mansion_service_new → economy.merchants**: 位置检查方法依赖跑商系统的市集坐标配置
8. **auto_migrate → models**: 启动时根据REQUIRED_FIELDS自动添加模型缺失字段
9. **GuildWarehouseItem.item_id → config.items_config**: 仓库物品的类型信息通过item_id从配置中查询，而非数据库字段
10. **MansionService.is_at_mansion → Player.get_current_coordinates**: 位置检查通过玩家模型的坐标getter方法获取当前位置

---

**调查完成时间**: 2026-02-22
**调查执行者**: scout (Claude Code Agent)
**调查范围**: 阴宅系统架构、公会仓库模型、位置检查逻辑、ItemType枚举、Repository实现、帮助系统、自动迁移
**代码覆盖**: 9个核心文件，329行关键代码
