# 增强战斗系统集成指南

## 📋 概述

增强战斗系统在现有战斗引擎基础上添加了：
1. **状态效果系统** - 支持Buff/Debuff、持续效果、效果叠加
2. **触发系统** - 支持多种触发条件(攻击时、暴击时、闪避时等)
3. **新战斗属性** - 吸血率、定身率、真伤率、回血率

## 🔧 快速开始

### 1. 数据库迁移

```bash
# 执行SQL迁移脚本
sqlite3 plugins/xiuxian_game/data/game.db < plugins/xiuxian_game/migrations/add_battle_effects.sql
```

### 2. 在战斗中使用增强引擎

```python
from ..battle.enhanced_engine import EnhancedBattleEngine
from sqlalchemy import select

async def battle_with_monster(player, monster_stats, session):
    """使用增强战斗引擎进行战斗"""
    
    # 创建增强战斗引擎
    engine = EnhancedBattleEngine()
    
    # 获取玩家装备
    from ..models.inventory import ItemInstance
    stmt = select(ItemInstance).where(
        ItemInstance.player_id == player.id,
        ItemInstance.equipped == True
    )
    equipped_items = (await session.execute(stmt)).scalars().all()
    
    # 初始化战斗
    engine.start_battle(player, monster_stats, equipped_items)
    
    # 战斗循环
    battle_log = []
    max_rounds = 30
    
    for round_num in range(1, max_rounds + 1):
        # 玩家回合
        player_turn = engine.execute_turn(player, monster_stats, is_player_turn=True)
        battle_log.extend(player_turn["messages"])
        
        # 扣除怪物血量
        monster_stats["hp"] -= player_turn["damage_dealt"]
        
        if monster_stats["hp"] <= 0:
            battle_log.append(f"🎉 {player.nickname}获胜！")
            return True, battle_log
        
        # 怪物回合(简化版，不使用增强效果)
        monster_damage = monster_stats["attack"]
        player.hp -= monster_damage
        battle_log.append(f"👹 {monster_stats['name']}攻击{player.nickname}，造成{monster_damage}伤害")
        
        if player.hp <= 0:
            battle_log.append(f"💀 {player.nickname}战败...")
            return False, battle_log
    
    battle_log.append("⏱️ 战斗超时，平局")
    return False, battle_log
```

### 3. 配置装备特殊效果

在 `items.yaml` 中添加 `special_effects` 字段：

```yaml
- item_id: "vampire_blade"
  name: "吸血之刃"
  type: "EQUIPMENT"
  price: 50000
  durability: 150
  attr_bonus: {"attack": 80}
  
  # 特殊效果配置
  special_effects:
    - trigger: "on_attack"      # 攻击时触发
      chance: 100               # 100%概率
      effect: "lifesteal"       # 吸血效果
      value: 15                 # 吸血15%
      duration: 0               # 立即生效
      description: "攻击时吸血15%"
    
    - trigger: "on_critical"    # 暴击时触发
      chance: 50                # 50%概率
      effect: "lifesteal"       # 额外吸血
      value: 25                 # 额外吸血25%
      duration: 0
      description: "暴击时额外吸血25%"
```

## 📊 触发类型说明

| 触发类型 | 说明 | 示例场景 |
|---------|------|---------|
| `on_attack` | 攻击时触发 | 吸血、真伤、定身 |
| `on_defense` | 被攻击时触发 | 反弹、防御提升 |
| `on_critical` | 暴击时触发 | 额外伤害、定身 |
| `on_dodge` | 闪避成功时触发 | 攻击力提升、反击 |
| `on_kill` | 击杀敌人时触发 | 回血、属性提升 |
| `first_turn` | 战斗首回合触发 | 开场增益 |
| `each_turn` | 每回合开始时触发 | 持续回血、属性提升 |
| `low_hp` | 低血量时触发 | 绝境爆发 |
| `on_hit` | 命中时触发 | 额外效果 |

## 🎯 效果类型说明

| 效果类型 | 说明 | value含义 | duration含义 |
|---------|------|----------|-------------|
| `lifesteal` | 吸血 | 吸血百分比 | 0(立即生效) |
| `true_damage` | 真实伤害 | 真伤百分比 | 0(立即生效) |
| `immobilize` | 定身 | 无 | 持续回合数 |
| `buff_attack` | 攻击力提升 | 提升百分比 | 持续回合数 |
| `buff_defense` | 防御力提升 | 提升百分比 | 持续回合数 |
| `buff_critical` | 暴击率提升 | 提升百分比 | 持续回合数 |
| `buff_dodge` | 闪避率提升 | 提升百分比 | 持续回合数 |
| `buff_accuracy` | 命中率提升 | 提升百分比 | 持续回合数 |
| `regen` | 每回合回血 | 回血百分比 | -1(永久) |
| `damage_boost` | 伤害提升 | 提升百分比 | 0(立即生效) |

## 💡 战斗日志示例

```
⚔️ 张三 VS 精英·红衣怨女
━━━ 第1回合 ━━━
✨ 触发【先手手套】 张三攻击力+100%(持续3回合)
✨ 触发【先手手套】 张三暴击率+50%(持续3回合)
⚔️ 张三攻击精英·红衣怨女 💥暴击！ 造成450伤害
🧡 吸血恢复67生命值
⛓️ 触发【束缚之链】 精英·红衣怨女被定身1回合
👹 精英·红衣怨女被定身，无法行动

━━━ 第2回合 ━━━
💚 张三回复80生命值
⚔️ 张三攻击精英·红衣怨女 造成320伤害
🔥 真实伤害额外造成48伤害
👹 精英·红衣怨女被定身，无法行动

━━━ 第3回合 ━━━
✨ 攻击力+100% 效果结束
⚔️ 张三攻击精英·红衣怨女 造成280伤害
👹 精英·红衣怨女攻击张三，造成150伤害
↩️ 张三反弹75伤害给精英·红衣怨女

🎉 张三获胜！
```

## 🔄 与现有系统的兼容性

### 1. 完全兼容现有战斗引擎

```python
# 旧代码仍然可以正常工作
from ..battle.battle_engine import BattleEngine
engine = BattleEngine()
result = engine.execute_player_turn(player, monster, base_attack)

# 新代码使用增强功能
from ..battle.enhanced_engine import EnhancedBattleEngine
enhanced_engine = EnhancedBattleEngine()
enhanced_engine.start_battle(player, monster, equipped_items)
result = enhanced_engine.execute_turn(player, monster)
```

### 2. 渐进式迁移

可以逐步将战斗场景迁移到增强引擎：
- 先迁移副本战斗
- 再迁移野外遇敌
- 最后迁移PVP战斗

### 3. 装备配置向后兼容

没有 `special_effects` 字段的装备仍然正常工作，只是没有特殊效果。

## 📝 最佳实践

### 1. 效果平衡性

```yaml
# ✅ 推荐：合理的数值
special_effects:
  - trigger: "on_attack"
    chance: 30              # 适中的触发概率
    effect: "lifesteal"
    value: 15               # 适中的吸血率
    
# ❌ 不推荐：过于强大
special_effects:
  - trigger: "on_attack"
    chance: 100             # 100%触发
    effect: "lifesteal"
    value: 80               # 80%吸血(太高)
```

### 2. 效果组合

```yaml
# ✅ 推荐：互补的效果组合
special_effects:
  - trigger: "on_attack"
    effect: "lifesteal"
    value: 15
  - trigger: "on_critical"
    effect: "immobilize"
    duration: 1
    
# ❌ 不推荐：重复的效果
special_effects:
  - trigger: "on_attack"
    effect: "lifesteal"
    value: 15
  - trigger: "on_attack"
    effect: "lifesteal"
    value: 20               # 重复效果
```

### 3. 持续时间设置

```yaml
# 立即生效的效果
- effect: "lifesteal"
  duration: 0               # 立即生效

# 短期buff
- effect: "buff_attack"
  duration: 3               # 持续3回合

# 永久效果
- effect: "regen"
  duration: -1              # 永久生效(整场战斗)
```

## 🐛 常见问题

### Q1: 特殊效果不触发？

检查以下几点：
1. 装备是否已穿戴(`equipped=True`)
2. `special_effects`配置是否正确
3. 触发概率是否太低
4. 触发条件是否满足(如`low_hp`需要血量低于阈值)

### Q2: 效果叠加不生效？

确保设置了 `max_stacks` 参数：

```yaml
special_effects:
  - trigger: "on_dodge"
    effect: "buff_attack"
    value: 50
    duration: 2
    max_stacks: 3           # 允许叠加3层
```

### Q3: 战斗日志太长？

可以在战斗结束后只显示关键信息：

```python
# 只显示重要消息
important_messages = [msg for msg in battle_log if any(
    keyword in msg for keyword in ["获胜", "战败", "暴击", "触发"]
)]
```

## 🚀 性能优化建议

1. **批量处理效果** - 每回合统一处理所有效果，避免频繁查询
2. **缓存装备配置** - 战斗开始时一次性加载所有装备效果
3. **限制效果数量** - 每个装备最多5-10个特殊效果
4. **异步处理** - 使用异步方法处理数据库操作

## 📚 参考资料

- `battle_effects.py` - 效果系统核心代码
- `enhanced_engine.py` - 增强战斗引擎
- `enhanced_equipment_examples.yaml` - 装备配置示例
- `add_battle_effects.sql` - 数据库迁移脚本
