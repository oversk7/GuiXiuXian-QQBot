# 如何添加新效果

## 目标

本文档指导开发者如何在诡修仙项目中添加新的游戏效果,包括物品效果和战斗效果。

---

## 前提条件

1. 阅读 `/architecture/effect-system.md` 了解效果系统架构
2. 确定效果类型:物品效果(使用时触发) 或 战斗效果(战斗中触发)
3. 确定效果参数和触发条件

---

## 添加物品效果 (难度: ⭐, 10-50行代码)

### Step 1: 添加效果类型枚举

编辑 `plugins/xiuxian_game/models/inventory.py`:

```python
class ItemEffectType(str, Enum):
    # ... 现有效果类型
    YOUR_NEW_EFFECT = "your_new_effect"  # 添加新类型
```

### Step 2: 实现效果处理函数

编辑 `plugins/xiuxian_game/item/item_effects.py`,添加带装饰器的处理函数:

```python
@register(ItemEffectType.YOUR_NEW_EFFECT)
async def _your_new_effect(
    player: Player,
    cfg: ItemConfig,
    qty: int,
    ctx: EffectContext,
    session: AsyncSession
) -> dict:
    """
    你的新效果描述

    effect_params格式:
    {
        "param1": value1,
        "param2": value2
    }
    """
    # 1. 读取效果参数
    param1 = cfg.effect_params.get("param1", default_value)
    param2 = cfg.effect_params.get("param2", default_value)

    # 2. 执行效果逻辑
    # 例如: 修改玩家属性
    player.gold += param1 * qty

    # 3. (可选) 记录使用日志
    # await log_usage(session, player, cfg)

    # 4. 返回结果
    return {
        "success": True,
        "message": f"效果生效,获得{param1 * qty}金币",
        "changes": {"gold": param1 * qty}
    }
```

### Step 3: 配置物品

编辑 `plugins/xiuxian_game/data/items.yaml`:

```yaml
- id: new_item_001
  name: "新道具名称"
  type: CONSUMABLE
  quality: COMMON
  effect_type: YOUR_NEW_EFFECT
  effect_params:
    param1: 100
    param2: "some_value"
  price: 500
  description: "使用后获得100金币"
```

### Step 4: 测试效果

```bash
# 启动机器人
python bot.py

# 在QQ群中测试
/give @用户 new_item_001 1
/use new_item_001
```

**验证标准**:
- 效果成功触发
- 玩家属性正确变化
- 返回消息正确显示

---

## 添加战斗效果 (难度: ⭐⭐⭐, 20-100行代码)

### Step 1: 添加效果类型枚举

编辑 `plugins/xiuxian_game/battle/battle_effects.py`:

```python
class EffectType(str, Enum):
    # ... 现有效果类型
    YOUR_BATTLE_EFFECT = "your_battle_effect"  # 添加新类型
```

### Step 2: (可选) 添加触发类型

如果需要新的触发时机,在 `TriggerType` 枚举中添加:

```python
class TriggerType(str, Enum):
    # ... 现有触发类型
    YOUR_NEW_TRIGGER = "your_new_trigger"  # 添加新触发类型
```

### Step 3: 在战斗引擎中实现效果逻辑

编辑 `plugins/xiuxian_game/battle/enhanced_engine.py`,在合适的位置应用效果:

```python
async def _execute_enhanced_attack(self, attacker, defender, turn_num):
    # ... 现有逻辑

    # 在攻击前检查你的新触发类型
    pre_effects = self.effect_manager.check_triggers(
        attacker.id,
        TriggerType.YOUR_NEW_TRIGGER,
        context={"defender": defender, "turn": turn_num}
    )

    for effect in pre_effects:
        if effect.effect_type == EffectType.YOUR_BATTLE_EFFECT:
            # 应用效果逻辑
            damage *= 1.5  # 例如: 提升50%伤害
            await self._add_battle_log(f"{attacker.name}触发了{effect.effect_type}!")

    # ... 继续战斗逻辑
```

### Step 4: 配置装备特殊效果

编辑装备配置(在 `items.yaml` 的装备项中):

```yaml
- id: weapon_with_new_effect
  name: "带新效果的武器"
  type: EQUIPMENT
  slot: WEAPON
  base_attack: 100
  special_effects:
    - trigger: YOUR_NEW_TRIGGER  # 触发时机
      effect: YOUR_BATTLE_EFFECT  # 效果类型
      chance: 30  # 触发概率30%
      value: 50  # 效果数值
      duration: 3  # 持续3回合
```

### Step 5: 测试战斗效果

```python
# 创建测试脚本 test_battle_effect.py
async def test_new_effect():
    async with safe_session() as session:
        player1 = await get_player(session, "player1_id")
        player2 = await get_player(session, "player2_id")

        engine = EnhancedBattleEngine(player1, player2, session)
        result = await engine.start_battle()

        # 检查战斗日志中是否有效果触发记录
        assert "触发了YOUR_BATTLE_EFFECT" in result["battle_log"]
```

**验证标准**:
- 触发概率符合预期(测试100次战斗)
- 效果数值正确应用
- 持续时间正确管理
- 战斗日志正确记录

---

## 添加临时Buff效果 (难度: ⭐, 0行代码,仅配置)

### Step 1: 复用现有效果类型

临时buff使用现有的 `TEMPORARY_BUFF` 或 `TEMPORARY_BUFF_PERCENT` 类型,无需编码。

### Step 2: 配置物品

编辑 `plugins/xiuxian_game/data/items.yaml`:

```yaml
- id: strength_potion
  name: "力量药水"
  type: CONSUMABLE
  quality: RARE
  effect_type: TEMPORARY_BUFF
  effect_params:
    buff_id: "strength_potion"
    buff_name: "力量增幅"
    duration: 3600  # 持续1小时(秒)
    bonuses:
      attack: 50  # 增加50点攻击
      critical_rate: 10  # 增加10点暴击率
  price: 1000
  description: "使用后1小时内攻击+50,暴击率+10%"
```

### Step 3: 测试临时buff

```bash
# 在QQ群中测试
/use strength_potion
/buff  # 查看当前增益状态
/profile  # 确认属性增加
```

**验证标准**:
- buff成功创建并显示在 `/buff` 列表中
- 玩家属性增加正确
- 1小时后buff自动过期
- 战斗中正确应用buff加成

---

## 常见问题

**Q: 如何让效果支持数量倍率?**

A: 在效果处理函数中使用 `qty` 参数:
```python
value = base_value * qty
```

**Q: 如何让效果有冷却时间?**

A: 使用 `daily_limit` 字段:
```yaml
effect_params:
  daily_limit: 3  # 每天最多使用3次
```

**Q: 如何让战斗效果支持叠加?**

A: 在 `TriggerConfig` 中设置 `max_stacks`:
```yaml
special_effects:
  - effect: YOUR_EFFECT
    max_stacks: 5  # 最多叠加5层
```

**Q: 如何调试效果不生效?**

A:
1. 检查 `_REGISTRY` 是否包含你的效果类型
2. 检查物品配置的 `effect_type` 是否正确
3. 查看日志中的异常信息
4. 在效果函数中添加print调试

---

**相关文档**:
- 效果系统架构: `/architecture/effect-system.md`
- 代码示例: `/llmdoc/REFACTORING_PLAN_v4.md:320-462`
- 物品配置: `plugins/xiuxian_game/data/items.yaml`
