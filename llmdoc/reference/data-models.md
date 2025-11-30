# 数据模型参考

## 1. Core Summary

诡修仙项目包含49个SQLAlchemy数据模型,覆盖玩家、物品、公会、社交、经济、战斗等系统。本文档提供核心模型的快速参考。

## 2. Source of Truth

**主要代码位置**:
- `plugins/xiuxian_game/models/player.py` - Player模型(87字段)
- `plugins/xiuxian_game/models/inventory.py` - ItemInstance模型
- `plugins/xiuxian_game/models/guild.py` - 公会三表结构
- `plugins/xiuxian_game/models/temporary_buff.py` - 临时buff模型
- `plugins/xiuxian_game/models/__init__.py` - 所有模型导出

**调研报告**:
- `llmdoc/agent/data_access_investigation.md` - 数据访问层调研

**相关文档**:
- 架构分析: `/architecture/data-access-layer.md`
- 当前架构: `/architecture/current-architecture.md`

---

## 3. 核心模型速查

### Player (玩家模型)

**位置**: `plugins/xiuxian_game/models/player.py`

**字段数量**: 87个

**主要字段分类**:
- 基础信息: `id`, `uid`, `nickname`, `level`, `sex`, `hp`, `max_hp`, `mp`, `max_mp`
- 战斗属性: `attack`, `defense`, `agility`, `stamina`, `luck`, `resentment`
- 扩展战斗: `critical_rate`, `critical_power`, `combo_rate`, `counter_rate`, `dodge_rate`, `accuracy_rate`, `skill_crit_rate`, `penetration_rate`, `lifesteal_rate`等16个
- 坐标系统: `region`, `x`, `y` (现实世界), `dungeon_level`, `dungeon_x`, `dungeon_y` (诡域)
- 公会关联: `guild_id`, `guild_contribution`
- 经济系统: `gold`, `gold2`, `vip`
- 阴宅系统: `mansion_level`, `mansion_x`, `mansion_y`

**关键方法**:
- `get_effective_attributes(session)` - 获取最终有效属性(含临时buff)
- `get_attribute_breakdown(session)` - 属性来源分解
- `is_in_dungeon()` - 判断是否在诡域
- `enter_dungeon(level)` - 进入诡域
- `exit_dungeon()` - 离开诡域

**关联关系**:
- → MonthlyCard (一对多)
- → Guild (多对一,通过guild_id)
- → ItemInstance (一对多,通过player_id)

---

### ItemInstance (物品实例模型)

**位置**: `plugins/xiuxian_game/models/inventory.py`

**用途**: 统一管理装备和消耗品

**主要字段**:
- 基础: `id`, `player_id`, `item_id`, `quantity`
- 装备扩展: `equipped`, `equipped_slot`, `upgrade_level`, `durability`, `max_durability`
- 镶嵌系统: `gem_slots_data` (JSON字段)
- 属性加成: `extra_attrs` (JSON字段,包含`_persist_bonus`)

**关键静态方法**:
- `add_item(session, player_id, item_id, qty)` - 添加物品到背包(处理堆叠)
- `consume_item(session, player_id, item_id, qty)` - 扣除物品(优先消耗未满堆叠)

**关键实例方法**:
- `apply_attr_bonus(player, base_attrs, result_dict)` - 计算装备属性加成

**配置加载**:
- 从 `config.items_config` 获取ItemConfig对象
- 包含 `effect_type`, `effect_params`, `base_stats`等

---

### Guild/GuildMember/GuildBuilding (公会三表)

**位置**: `plugins/xiuxian_game/models/guild.py`

**Guild表** (公会基础信息):
- `id`, `name`, `leader_id`, `level`, `treasury`, `influence`
- `territory` (JSON字段,存储势力范围)

**GuildMember表** (成员关系):
- `id`, `guild_id`, `player_id`, `position`, `contribution`

**GuildBuilding表** (建筑管理):
- `id`, `guild_id`, `building_type`, `level`

**关联关系**:
- Guild ← GuildMember (一对多, cascade delete)
- Guild ← GuildBuilding (一对多, cascade delete)

---

### TemporaryBuff (临时buff模型)

**位置**: `plugins/xiuxian_game/models/temporary_buff.py`

**主要字段**:
- `id`, `player_id`, `buff_id`, `buff_name`
- `attribute_bonuses` (JSON字段,存储属性加成)
- `expires_at` (过期时间)
- `source_item_id` (来源物品)

**关键类方法**:
- `create_buff(session, player_id, buff_config)` - 创建或刷新buff
- `get_active_buffs(session, player_id)` - 获取激活的buff列表
- `get_total_attribute_bonuses(session, player_id)` - 获取总属性加成
- `cleanup_expired_buffs(session, player_id)` - 清理过期buff

**实例方法**:
- `is_expired()` - 判断是否过期
- `get_remaining_time()` - 获取剩余时间

---

## 4. 其他重要模型

### 经济系统
- `BankAccount` - 银行账户(余额、利息、最后更新时间)
- `MarketOrder` - 市场订单(卖家、物品、价格、状态)
- `Stock` - 股票(价格、变动趋势、历史数据)

### 社交系统
- `Marriage` - 婚姻(双方player_id、结婚时间)
- `Mentor` - 师徒(师父、徒弟、状态)

### 战斗系统
- `WorldBoss` - 世界Boss(血量、阶段、奖励池)
- `BossContribution` - Boss贡献记录

### 其他
- `MonthlyCard` - 月卡记录
- `ElixirUsageLog` - 丹药使用记录
- `VIPEquipmentBonus` - VIP装备永久加成

---

## 5. 模型设计模式

### 使用JSON字段存储灵活数据

**ItemInstance.extra_attrs**:
```python
extra_attrs = {
    "_persist_bonus": {  # 装备持久化加成
        "attack": 120,
        "defense": 80
    },
    "custom_data": {  # 自定义扩展数据
        "key": "value"
    }
}
```

**TemporaryBuff.attribute_bonuses**:
```python
attribute_bonuses = {
    "attack": 50,
    "critical_rate": 10,
    "max_hp": 200
}
```

### 使用cascade级联删除

```python
# Guild模型
members = relationship(
    "GuildMember",
    back_populates="guild",
    cascade="all, delete-orphan"  # 删除公会时自动删除所有成员记录
)
```

### 使用索引优化查询

```python
class Player(Base):
    __tablename__ = "players"

    # 复合索引
    __table_args__ = (
        Index("idx_region_coords", "region", "x", "y"),
        Index("idx_guild", "guild_id"),
    )
```

---

## 6. 查询模式参考

### 基础查询

```python
# 通过主键查询
player = await session.get(Player, player_id)

# 条件查询
stmt = select(Player).where(Player.nickname == "张三")
player = (await session.execute(stmt)).scalar_one_or_none()
```

### 关联查询(避免N+1)

```python
# 预加载关联对象
stmt = (
    select(Player)
    .options(joinedload(Player.monthly_cards))
    .where(Player.id == player_id)
)
player = (await session.execute(stmt)).unique().scalar_one_or_none()
```

### 聚合查询

```python
# 查询总数
stmt = select(func.count(Player.id)).where(Player.level > 50)
count = (await session.execute(stmt)).scalar()
```

---

**相关文档**:
- 数据访问层: `/architecture/data-access-layer.md`
- 查询优化: `/guides/how-to-optimize-query.md`
- 调研报告: `llmdoc/agent/data_access_investigation.md`
