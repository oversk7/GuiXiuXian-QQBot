# Feature Flag控制指南

本指南说明如何使用Feature Flag控制新效果系统（物品效果适配器 + 战斗效果桥接器）的启用和禁用。

## 步骤1: 了解Feature Flag机制

**Feature Flag位置**: `.env` 文件中的 `USE_NEW_EFFECT_SYSTEM` 变量

**作用**:
- `true` - 启用新效果系统（ItemEffectAdapter + BattleEffectBridge）
- `false` - 禁用新效果系统，使用旧的效果实现

**当前状态**: 已启用 (`USE_NEW_EFFECT_SYSTEM=true`)

**参考**: `plugins/xiuxian_game/domain/effects/adapters/__init__.py`

## 步骤2: 查看当前配置

**操作**: 打开项目根目录的 `.env` 文件。

**查找**:
```env
USE_NEW_EFFECT_SYSTEM=true
```

**验证状态**:
```python
from plugins.xiuxian_game.domain.effects.adapters import USE_NEW_EFFECT_SYSTEM

if USE_NEW_EFFECT_SYSTEM:
    print("✅ 新效果系统已启用")
else:
    print("❌ 新效果系统已禁用")
```

## 步骤3: 修改Feature Flag

### 启用新效果系统

**操作**: 编辑 `.env` 文件，设置：
```env
USE_NEW_EFFECT_SYSTEM=true
```

**重启bot**: Feature Flag仅在启动时读取，修改后需要重启。

**验证启用**:
```bash
# 启动日志应显示
[SUCCESS] [EffectSystem] 成功注册 20 个物品效果适配器
[SUCCESS] [EffectSystem] 成功注册 23 个战斗效果桥接器
[SUCCESS] [EffectSystem] 新效果系统已启用
```

**参考**: `plugins/xiuxian_game/__init__.py:63-64`

### 禁用新效果系统

**操作**: 编辑 `.env` 文件，设置：
```env
USE_NEW_EFFECT_SYSTEM=false
```

**重启bot**。

**验证禁用**:
```bash
# 启动日志应显示
[SUCCESS] [EffectSystem] 成功注册 20 个物品效果适配器
[SUCCESS] [EffectSystem] 成功注册 23 个战斗效果桥接器
[INFO] [EffectSystem] 新效果系统已禁用，使用旧效果实现
```

**行为**: 旧的效果实现继续工作，新的适配器和桥接器仅注册但不使用。

## 步骤4: 在代码中使用Feature Flag

### 物品效果适配器示例

**位置**: `plugins/xiuxian_game/item/inventory.py`

**实现**:
```python
from plugins.xiuxian_game.domain.effects.adapters import (
    USE_NEW_EFFECT_SYSTEM,
    apply_effect_with_fallback
)

async def use_item(session, player, item_config, quantity):
    """使用物品"""

    if USE_NEW_EFFECT_SYSTEM:
        # 使用新的适配器系统
        result = await apply_effect_with_fallback(
            session=session,
            player=player,
            item_config=item_config,
            quantity=quantity
        )
        return result
    else:
        # 使用旧的效果系统
        from ..item.item_effects import apply_effect
        result = await apply_effect(
            player=player,
            cfg=item_config,
            qty=quantity,
            session=session
        )
        return result
```

**参考**: `plugins/xiuxian_game/domain/effects/adapters/integration.py:67-123`

### apply_effect_with_fallback函数

**功能**: 自动选择新旧实现，带fallback机制。

**签名**:
```python
async def apply_effect_with_fallback(
    session,
    player,
    item_config,
    quantity: int = 1
) -> Dict[str, Any]
```

**逻辑**:
1. 如果 `USE_NEW_EFFECT_SYSTEM=true`，尝试使用适配器
2. 如果适配器执行失败，自动fallback到旧实现
3. 如果 `USE_NEW_EFFECT_SYSTEM=false`，直接使用旧实现

**参考**: `plugins/xiuxian_game/domain/effects/adapters/integration.py:67-123`

### 战斗效果桥接器示例（未来集成）

**当前状态**: 战斗效果桥接器已注册，但尚未集成到战斗引擎。

**预期集成方式**:
```python
# plugins/xiuxian_game/battle/enhanced_engine.py (未来)

from plugins.xiuxian_game.domain.effects.adapters import USE_NEW_EFFECT_SYSTEM

def _register_equipment_triggers(self, unit_id, equipment):
    """注册装备触发器"""

    if USE_NEW_EFFECT_SYSTEM:
        # 使用新的桥接器系统
        for equip in equipment:
            bridges = create_bridges_from_equipment(equip.item_id)
            for bridge in bridges:
                # 将桥接器添加到某个列表，供后续触发检查使用
                pass
    else:
        # 使用旧的TriggerConfig系统
        for equip in equipment:
            item_config = config.items_config.get(equip.item_id)
            if item_config and item_config.special_effects:
                triggers = parse_triggers_from_yaml(item_config.special_effects)
                self.effect_manager.register_triggers(unit_id, triggers)
```

**注意**: 战斗效果桥接器的完整集成尚未实现，当前仅注册到效果注册中心。

## 步骤5: 灰度测试策略

### 策略1: 本地测试

**操作**:
1. 设置 `USE_NEW_EFFECT_SYSTEM=true`
2. 重启bot
3. 执行物品使用命令（如 `使用 恢复丹 1`）
4. 观察日志，确认使用了适配器
5. 验证效果正确应用

**验证日志**:
```bash
[DEBUG] [ItemEffectAdapter] 执行适配器: item_restore_hp_default
[DEBUG] [ItemEffectAdapter] 效果参数: {'hp_restore': 100}
[SUCCESS] 恢复了100点生命值
```

### 策略2: 生产灰度

**操作**:
1. 在低峰时段设置 `USE_NEW_EFFECT_SYSTEM=true`
2. 重启bot
3. 监控错误日志
4. 如果出现问题，立即设置 `USE_NEW_EFFECT_SYSTEM=false` 并重启

**监控指标**:
- 错误日志数量
- 物品使用成功率
- 战斗结果一致性

**回滚条件**:
- 错误率 > 1%
- 用户反馈物品效果异常
- 战斗结果与旧系统不一致

### 策略3: A/B测试（未来）

**实现**:
```python
# 根据玩家ID或群ID动态选择
def should_use_new_system(player_id: str) -> bool:
    # 示例：50%的玩家使用新系统
    return int(player_id) % 2 == 0

# 在apply_effect中使用
if should_use_new_system(player.id):
    result = await apply_effect_with_fallback(...)
else:
    result = await legacy_apply_effect(...)
```

**注意**: 当前未实现A/B测试机制，仅支持全局Feature Flag。

## 步骤6: 故障排查

### 问题1: Feature Flag修改后未生效

**症状**: 修改 `.env` 后，日志仍显示旧状态。

**原因**: Feature Flag仅在启动时读取。

**解决**: 重启bot。

### 问题2: 新旧系统行为不一致

**症状**: `USE_NEW_EFFECT_SYSTEM=true` 时效果异常。

**排查**:

**6.1 检查适配器日志**:
```bash
# 搜索日志中的 [ItemEffectAdapter] 或 [BattleEffectBridge]
grep "ItemEffectAdapter" logs/debug.log
```

**6.2 检查fallback机制**:
```bash
# 搜索 "Fallback to legacy effect"
grep "Fallback" logs/debug.log
```

**6.3 比较结果**:
```python
# 测试新旧系统的结果
USE_NEW_EFFECT_SYSTEM = True
result_new = await apply_effect_with_fallback(...)

USE_NEW_EFFECT_SYSTEM = False
result_old = await legacy_apply_effect(...)

# 对比
assert result_new == result_old, "结果不一致！"
```

**解决**: 如果发现不一致，设置 `USE_NEW_EFFECT_SYSTEM=false` 并提交Issue。

### 问题3: 物品效果适配器未注册

**症状**: 启动日志显示 "成功注册 0 个物品效果适配器"。

**原因**: `register_all_item_effect_adapters()` 未被调用。

**检查**: 查看 `plugins/xiuxian_game/__init__.py:54-56`

**解决**: 确保启动脚本中包含注册代码。

### 问题4: 战斗效果桥接器未生效

**症状**: 战斗中装备效果未触发。

**原因**: 战斗效果桥接器尚未集成到战斗引擎（当前仅注册）。

**当前状态**: Stage 2完成了桥接器实现和注册，但尚未集成到 `enhanced_engine.py`。

**下一步**: 在Stage 3集成到战斗引擎，增加Feature Flag控制。

## 步骤7: 性能监控

### 监控指标

**物品效果**:
- 适配器执行时间
- Fallback频率
- 错误率

**战斗效果** (未来):
- 桥接器触发频率
- 条件检查耗时
- 环境检查耗时

### 日志级别控制

**开发调试**:
```env
LOG_LEVEL=DEBUG  # 显示所有适配器和桥接器日志
```

**生产环境**:
```env
LOG_LEVEL=INFO  # 仅显示成功/失败日志
```

**参考**: `.env` 和 `bot.py` 的日志配置

---

**最佳实践**:
- ✅ 本地测试通过后再启用生产环境
- ✅ 低峰时段启用新系统
- ✅ 保持 `LOG_LEVEL=DEBUG` 直到重构完成
- ✅ 监控错误日志，及时发现问题
- ✅ 准备好随时回滚（设置 `USE_NEW_EFFECT_SYSTEM=false`）

**相关文档**:
- 物品效果集成: `plugins/xiuxian_game/domain/effects/adapters/INTEGRATION_GUIDE.md`
- 战斗效果桥接器: `/llmdoc/architecture/battle-effect-bridge.md`
- API参考: `/llmdoc/reference/battle-effect-bridge-api.md`
