# Feature Flag 使用指南

## 环境变量配置

物品效果系统支持通过环境变量控制新旧系统的切换。

### USE_NEW_EFFECT_SYSTEM

**作用**: 控制是否启用新的效果系统

**可选值**:
- `true` - 启用新效果系统（ItemEffectAdapter）
- `false` - 使用旧效果系统（item_effects.py）（默认）

**配置方法**:

#### 方法1: 修改 `.env` 文件（推荐）

```env
# 启用新效果系统
USE_NEW_EFFECT_SYSTEM=true

# 或者禁用（使用旧系统）
USE_NEW_EFFECT_SYSTEM=false
```

#### 方法2: 启动时设置环境变量

**Linux/Mac**:
```bash
export USE_NEW_EFFECT_SYSTEM=true
python bot.py
```

**Windows CMD**:
```cmd
set USE_NEW_EFFECT_SYSTEM=true
python bot.py
```

**Windows PowerShell**:
```powershell
$env:USE_NEW_EFFECT_SYSTEM="true"
python bot.py
```

---

## 工作原理

### 系统架构

```
用户使用物品
    ↓
inventory.py: use_item命令
    ↓
apply_effect_with_fallback()  ← 智能选择
    ├─→ [USE_NEW_EFFECT_SYSTEM=true]  → apply_effect_v2()  → 新系统
    │                                       ├─→ 成功 → 返回结果
    │                                       └─→ 失败 → 回退旧系统
    │
    └─→ [USE_NEW_EFFECT_SYSTEM=false] → apply_effect()     → 旧系统
```

### 新系统执行流程

1. **注册阶段**（启动时）:
   ```python
   # 在 __init__.py 的 on_startup 中
   adapters = register_all_item_effect_adapters()
   # 自动为20个物品效果创建适配器并注册
   ```

2. **使用阶段**（用户使用物品时）:
   ```python
   # inventory.py:192
   success, msg = await apply_effect_with_fallback(...)

   # 如果 USE_NEW_EFFECT_SYSTEM=true
   → apply_effect_v2()
      → get_effect_registry().create(effect_id)
         → 执行适配器的 execute() 方法
            → 调用旧的效果函数
               → 返回结果
   ```

3. **回退机制**:
   - 新系统执行失败 → 自动回退到旧系统
   - 效果未注册 → 自动回退到旧系统
   - 发生异常 → 自动回退到旧系统

---

## 启动日志示例

### Feature Flag关闭（默认）

```
数据库初始化完成
[AdapterRegistry] 开始批量注册物品效果适配器...
[AdapterFactory] 为旧效果 RESTORE_HP 创建适配器: item_restore_hp
[AdapterFactory] 为旧效果 RESTORE_MP 创建适配器: item_restore_mp
... (18个效果)
[AdapterRegistry] 成功注册 20 个物品效果适配器
[EffectSystem] 成功注册 20 个物品效果适配器
[EffectSystem] 新效果系统已注册但未启用（Feature Flag关闭）
```

### Feature Flag开启

```
数据库初始化完成
[AdapterRegistry] 开始批量注册物品效果适配器...
[AdapterFactory] 为旧效果 RESTORE_HP 创建适配器: item_restore_hp
[AdapterFactory] 为旧效果 RESTORE_MP 创建适配器: item_restore_mp
... (18个效果)
[AdapterRegistry] 成功注册 20 个物品效果适配器
[EffectSystem] 成功注册 20 个物品效果适配器
[EffectSystem] 新效果系统已启用  ← 注意这里
```

---

## 使用效果日志

### 使用旧系统

```
[EffectSystem] Feature Flag: 使用旧效果系统
```

### 使用新系统

```
[EffectSystem] Feature Flag: 使用新效果系统
[ItemUse] 使用新效果系统处理: 回春丹
[EffectSystem v2] 执行物品效果: effect_id=item_restore_hp, item=hp_potion, qty=1
[ItemEffectAdapter] 适配旧效果 item_restore_hp: player=xxx, item=hp_potion, qty=1
[ItemEffectAdapter] 旧效果 item_restore_hp 执行完成: success=True, message=恢复了30点生命值
[EffectSystem v2] 效果执行完成: success=True, message=恢复了30点生命值
```

---

## 监控和调试

### 查看系统状态

可以通过以下方式查看系统状态：

```python
from domain.effects.adapters import get_effect_system_status

status = get_effect_system_status()
print(status)
# 输出:
# {
#     "use_new_system": False,
#     "registered_adapters": 20,
#     "total_effects": 20,
#     "adapter_ids": ["item_restore_hp", "item_restore_mp", ...],
#     "feature_flag_env": "false"
# }
```

### 检查是否已注册

```python
from domain.effects.adapters import is_effect_registered

if is_effect_registered("item_restore_hp"):
    print("恢复HP效果已注册")
```

### 获取所有已注册适配器

```python
from domain.effects.adapters import get_registered_adapters

adapters = get_registered_adapters()
print(f"共注册了 {len(adapters)} 个适配器")
```

---

## 迁移建议

### 阶段1: 验证注册（已完成✅）

1. 不启用Feature Flag（`USE_NEW_EFFECT_SYSTEM=false`）
2. 启动机器人，查看日志确认20个适配器已注册
3. 旧系统继续工作

### 阶段2: 渐进式测试（当前阶段）

1. 启用Feature Flag（`USE_NEW_EFFECT_SYSTEM=true`）
2. 测试常用物品：回春丹、理智丹等
3. 观察日志，确认新系统正常工作
4. 如有问题，关闭Feature Flag回退

### 阶段3: 全面切换（未来）

1. 新系统稳定运行一段时间
2. 逐步移除旧系统代码
3. 清理item_effects.py中的旧函数

---

## 常见问题

### Q1: 启用新系统后出现错误怎么办？

**A**: 新系统有自动回退机制，会自动切换到旧系统。但如果出现问题：
1. 关闭Feature Flag: `USE_NEW_EFFECT_SYSTEM=false`
2. 重启机器人
3. 查看日志文件定位问题

### Q2: 新旧系统有性能差异吗？

**A**: 几乎没有。适配器只是简单的函数包装，开销可忽略。

### Q3: 能否只对部分效果启用新系统？

**A**: 当前不支持。Feature Flag是全局开关，要么全部启用，要么全部禁用。

### Q4: 新系统会修改数据库吗？

**A**: 不会。新系统只是调用旧函数的包装层，数据库操作完全一致。

---

**文档位置**: `domain/effects/adapters/FEATURE_FLAG.md`
**创建时间**: 2025-11-27
**维护者**: Claude Code + 开发团队
