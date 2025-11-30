# AttributeCalculator 集成使用指南

**版本**: 1.0
**日期**: 2025-11-26
**状态**: 可用于生产 ✅

---

## 📋 目录

1. [快速开始](#快速开始)
2. [Feature Flag控制](#feature-flag控制)
3. [在Player模型中使用](#在player模型中使用)
4. [在命令处理中使用](#在命令处理中使用)
5. [缓存管理](#缓存管理)
6. [监控和统计](#监控和统计)
7. [迁移指南](#迁移指南)

---

## 快速开始

### 1. 基本使用

```python
from domain.attributes import (
    get_effective_attributes_v2,
    get_attribute_breakdown_v2,
    invalidate_player_buff_cache,
)

# 获取有效属性（与旧版API兼容）
attrs = await get_effective_attributes_v2(player, session)
print(f"Attack: {attrs['attack']}")

# 获取详细分解
breakdown = await get_attribute_breakdown_v2(player, session)
print(f"基础攻击: {breakdown['base']['attack']}")
print(f"装备加成: {breakdown['equipment']['attack']}")
print(f"Buff加成: {breakdown['buff']['attack']}")
print(f"总攻击: {breakdown['total']['attack']}")
```

### 2. 工厂模式（高级用法）

```python
from domain.attributes import AttributeCalculatorFactory

# 获取全局单例
calculator = AttributeCalculatorFactory.get_instance()

# 计算属性
attrs_bonus = await calculator.calculate_simple(player, session)
print(f"Attack: {attrs_bonus.attack}")

# 获取详细分解
breakdown = await calculator.calculate_with_breakdown(player, session)
print(f"Total attack: {breakdown.total.attack}")
```

---

## Feature Flag控制

### 环境变量配置

通过环境变量控制是否使用AttributeCalculator v2：

```bash
# 启用AttributeCalculator v2（新实现）
export USE_ATTRIBUTE_CALCULATOR_V2=true

# 禁用（使用旧实现）
export USE_ATTRIBUTE_CALCULATOR_V2=false  # 默认
```

### 在代码中使用

```python
from domain.attributes import USE_ATTRIBUTE_CALCULATOR_V2

async def get_player_attributes(player, session):
    if USE_ATTRIBUTE_CALCULATOR_V2:
        # 使用新实现（含60秒TTL缓存）
        return await get_effective_attributes_v2(player, session)
    else:
        # 使用旧实现
        return await player.get_effective_attributes(session)
```

---

## 在Player模型中使用

### 方案A：直接替换（建议生产环境验证后使用）

在 `plugins/xiuxian_game/models/player.py` 中修改：

```python
async def get_effective_attributes(self, session=None) -> dict:
    """获取有效属性（包含装备加成、丹药加成和临时buff加成）"""

    # 使用AttributeCalculator v2（含缓存优化）
    from ..domain.attributes import get_effective_attributes_v2
    return await get_effective_attributes_v2(self, session)
```

### 方案B：Feature Flag切换（推荐）

```python
async def get_effective_attributes(self, session=None) -> dict:
    """获取有效属性（包含装备加成、丹药加成和临时buff加成）"""

    from ..domain.attributes import (
        USE_ATTRIBUTE_CALCULATOR_V2,
        get_effective_attributes_v2
    )

    if USE_ATTRIBUTE_CALCULATOR_V2:
        # 使用AttributeCalculator v2
        return await get_effective_attributes_v2(self, session)

    # 原有实现（保持向后兼容）
    base_attrs = {
        "max_hp": self.max_hp,
        "max_mp": self.max_mp,
        # ... 其他属性
    }

    if session:
        from .temporary_buff import TemporaryBuff
        buff_bonuses = await TemporaryBuff.get_total_attribute_bonuses(session, self.id)
        for attr, bonus in buff_bonuses.items():
            if attr in base_attrs:
                base_attrs[attr] += bonus

    return base_attrs
```

---

## 在命令处理中使用

### 示例1：角色面板查询

```python
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from ..infrastructure.uow import UnitOfWork
from ..models.db import AsyncSessionLocal
from ..domain.attributes import get_effective_attributes_v2

profile_cmd = on_command("角色", block=True)

@profile_cmd.handle()
async def handle_profile(event: MessageEvent):
    async with UnitOfWork(AsyncSessionLocal) as uow:
        # 获取玩家
        player = await uow.players.get_by_uid(event.user_id)

        # 使用AttributeCalculator获取属性
        attrs = await get_effective_attributes_v2(player, uow.session)

        # 构建消息
        msg = f"攻击: {attrs['attack']}\n防御: {attrs['defense']}"

        await uow.commit()
        await profile_cmd.finish(msg)
```

### 示例2：获取详细分解

```python
from ..domain.attributes import get_attribute_breakdown_v2

@breakdown_cmd.handle()
async def handle_breakdown(event: MessageEvent):
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await uow.players.get_by_uid(event.user_id)

        # 获取详细分解
        breakdown = await get_attribute_breakdown_v2(player, uow.session)

        msg = (
            f"🏷 基础属性: {breakdown['base']['attack']}攻击\n"
            f"⚔️ 装备加成: +{breakdown['equipment']['attack']}\n"
            f"💊 丹药加成: +{breakdown['elixir']['attack']}\n"
            f"✨ Buff加成: +{breakdown['buff']['attack']}\n"
            f"━━━━━━━━━━━\n"
            f"📊 总攻击: {breakdown['total']['attack']}"
        )

        await uow.commit()
        await breakdown_cmd.finish(msg)
```

---

## 缓存管理

### 使指定玩家缓存失效

**重要**：当玩家使用临时buff物品时，必须主动失效缓存

```python
from ..domain.attributes import invalidate_player_buff_cache

# 玩家使用临时buff物品后
async def use_temporary_buff_item(player, item_cfg):
    # ... 创建TemporaryBuff记录 ...

    # 使缓存失效（重要！）
    invalidate_player_buff_cache(player.id)
```

### 在物品效果中集成

在 `plugins/xiuxian_game/item/item_effects.py` 中：

```python
@register_effect(ItemEffectType.TEMPORARY_BUFF)
async def _temporary_buff(player, cfg, qty, ctx, session):
    """临时buff效果"""

    # ... 创建buff逻辑 ...

    # 使缓存失效
    from ..domain.attributes import invalidate_player_buff_cache
    invalidate_player_buff_cache(player.id)

    return {"success": True, "message": "buff已生效"}
```

---

## 监控和统计

### 获取缓存统计

```python
from domain.attributes import get_attribute_calculator_stats

# 获取统计信息
stats = get_attribute_calculator_stats()
print(stats)

# 输出示例:
# {
#     "buff_cache": {
#         "total": 150,      # 缓存总数
#         "valid": 145,      # 有效缓存数
#         "expired": 5       # 过期缓存数
#     }
# }
```

### 定时任务清理过期缓存（可选）

```python
from domain.attributes import AttributeCalculatorFactory

# 每5分钟清理一次过期缓存
async def cleanup_expired_cache():
    factory = AttributeCalculatorFactory.get_instance()
    if factory._buff_source:
        expired_count = factory._buff_source.cleanup_expired_cache()
        print(f"Cleaned {expired_count} expired cache entries")
```

---

## 迁移指南

### 阶段1：并行测试（当前阶段）

1. **保持旧代码不变**
2. **使用v2命令测试**：
   ```bash
   角色v2  # 测试重构版本
   角色    # 使用原版本
   ```
3. **对比输出一致性**

### 阶段2：Feature Flag灰度

1. **修改Player.get_effective_attributes使用Feature Flag**
2. **在测试环境启用**：
   ```bash
   export USE_ATTRIBUTE_CALCULATOR_V2=true
   nb run
   ```
3. **验证所有功能正常**

### 阶段3：全量切换

1. **在生产环境启用Feature Flag**
2. **监控缓存命中率和性能**
3. **确认无问题后移除Feature Flag**

### 阶段4：清理旧代码

1. **移除旧的get_effective_attributes实现**
2. **移除Feature Flag检查**
3. **更新所有文档**

---

## 性能优化收益

### Buff查询优化

| 场景 | 旧实现 | 新实现 | 优化效果 |
|------|--------|--------|---------|
| **单次战斗** | 每回合查数据库 | 60秒内使用缓存 | **90%查询减少** |
| **10回合战斗** | 10次查询 | 1次查询 | **-90%** |
| **玩家PK** | 双方各10次 | 双方各1次 | **-90%** |

### 缓存命中率（预期）

- **首次查询**: 0% （必须查数据库）
- **60秒内重复查询**: ~95%（使用缓存）
- **战斗场景**: ~90%（多回合战斗）

---

## 常见问题

### Q1: 如何确认使用了新实现？

**A**: 查看日志或添加调试代码：

```python
from domain.attributes import USE_ATTRIBUTE_CALCULATOR_V2
print(f"Using AttributeCalculator v2: {USE_ATTRIBUTE_CALCULATOR_V2}")
```

### Q2: 缓存会导致属性更新延迟吗？

**A**: 不会，只要正确调用 `invalidate_player_buff_cache(player.id)`：

- 使用buff物品时 → 立即失效缓存 ✅
- buff过期 → 下次查询时自动过滤 ✅
- 战斗期间 → 60秒TTL覆盖整场战斗 ✅

### Q3: 旧实现和新实现的输出格式一致吗？

**A**: 完全一致，`get_effective_attributes_v2` 返回与旧版本相同的dict格式

### Q4: 如何回滚到旧实现？

**A**: 设置环境变量：

```bash
export USE_ATTRIBUTE_CALCULATOR_V2=false
# 或者直接不设置（默认为false）
```

---

## 相关文档

- [属性计算器重构总结](../../llmdoc/ATTRIBUTE_CALCULATOR_REFACTORING.md)
- [重构进度跟踪](../../llmdoc/REFACTORING_PROGRESS.md)
- [使用示例](../infrastructure/USAGE_EXAMPLES.md)

---

**维护者**: Claude Code + 开发团队
**文档位置**: `domain/attributes/INTEGRATION_GUIDE.md`
