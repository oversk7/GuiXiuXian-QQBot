# 战斗系统使用指南

本文档指导如何在游戏开发中使用战斗系统,包括发起战斗、查询战斗属性、理解伤害计算。

## 1. 发起PvP战斗(玩家切磋)

### 基本用法

```python
from plugins.xiuxian_game.battle.integration_helper import BattleIntegrationHelper

# 简洁版PvP战斗(推荐用于切磋)
(player1_won, battle_log, p1_damage, p2_damage) = await BattleIntegrationHelper.compact_player_vs_player_battle(
    player1=challenger,  # Player对象: 挑战者
    player2=defender,    # Player对象: 被挑战者
    session=session,     # AsyncSession: 数据库会话
    seed=None,          # Optional[str]: 随机种子(用于可重现战斗)
    max_rounds=30       # int: 最大回合数
)
```

**特点:**
- 无损切磋: 不修改玩家实际HP,战毕不保存状态
- 紧凑日志: 格式简洁,适合消息发送
- 完整逻辑: 支持所有战斗效果和触发机制

**参考位置:** `plugins/xiuxian_game/battle/integration_helper.py:152-246`

### 生成随机种子

```python
import hashlib
import time

# 生成确定性随机种子(用于测试或回放)
seed = hashlib.md5(f"{player1.id}_{player2.id}_{int(time.time())}".encode()).hexdigest()

# 使用相同种子可以重现相同的战斗过程
result1 = await BattleIntegrationHelper.compact_player_vs_player_battle(player1, player2, session, seed=seed)
result2 = await BattleIntegrationHelper.compact_player_vs_player_battle(player1, player2, session, seed=seed)
# result1和result2的战斗过程完全一致
```

### 格式化战斗日志

```python
# 简洁版日志已格式化,可直接发送
log_message = "\n".join(battle_log)
await pvp_cmd.finish(log_message)
```

**日志格式示例:**
```
⚔️ PVP切磋结果 ⚔️
━━━━━━━━━━━━━
🔥 玩家A[UID:1001] Lv.50 筑基期
🆚 玩家B[UID:1002] Lv.50 筑基期
━━━━━━━━━━━━━
⚔️ 玩家A攻击玩家B 造成150伤害 [20%:30 + 80%:120]
🔄 连击x2 造成120伤害
⚔️ 玩家B攻击玩家A 造成140伤害
🧡 玩家A吸血22HP
💚 玩家B回复10HP
━━━━━━━━━━━━━
💡 这只是模拟切磋,不会造成任何实际损失
```

## 2. 发起PvE战斗(玩家vs怪物)

### 基本用法

```python
from plugins.xiuxian_game.battle.integration_helper import BattleIntegrationHelper

# 玩家vs怪物战斗
(player_won, battle_log, player_damage, monster_damage) = await BattleIntegrationHelper.player_vs_monster_battle(
    player=player,           # Player对象
    monster={                # 怪物字典
        "name": "废弃医院怪物",
        "hp": 5000,
        "max_hp": 5000,
        "attack": 800,
        "defense": 600,
        "agility": 100,
        "level": 50,
        "critical_rate": 20,
        "dodge_rate": 30
    },
    player_equipped_items=equipped_items,  # 玩家装备列表
    session=session,
    seed=None
)
```

**参考位置:** `plugins/xiuxian_game/battle/integration_helper.py:249-340`

## 3. 查询战斗属性

### 计算有效战斗属性

```python
from plugins.xiuxian_game.battle.battle_attributes import BattleAttributeCalculator

# 计算包含临时buff的有效战斗属性
battle_attrs = await BattleAttributeCalculator.calculate_effective_attributes_async(
    player=player,          # Player对象
    session=session,        # AsyncSession(用于查询临时buff)
    equipment_bonus=None    # Optional[Dict]: 额外装备加成
)

# 返回结果:
# {
#     "critical_rate": 50.0,      # 暴击率%
#     "critical_power": 150,      # 暴击力
#     "combo_rate": 20.0,         # 连击率%
#     "counter_rate": 30.0,       # 反击率%
#     "dodge_rate": 40.0,         # 闪避率%
#     "accuracy_rate": 80.0,      # 命中率%
#     "skill_crit_rate": 25.0,    # 灵爆率%
#     "penetration_rate": 10.0,   # 穿透率%
#     "anti_crit_rate": 15.0      # 抗暴率%
# }
```

**参考位置:** `plugins/xiuxian_game/battle/battle_attributes.py:88-152`

### 理解属性上限

```python
# 查看属性上限配置
from plugins.xiuxian_game.battle.battle_attributes import BattleAttributeCalculator

caps = BattleAttributeCalculator.ATTRIBUTE_CAPS
# {
#     "critical_rate": 500,    # 暴击率上限500%
#     "combo_rate": 60,        # 连击率上限60%
#     "counter_rate": 80,      # 反击率上限80%
#     "dodge_rate": 500,       # 闪避率上限500%
#     "accuracy_rate": 500,    # 命中率上限500%(可与闪避率抵消)
#     "skill_crit_rate": 70,   # 灵爆率上限70%
#     "penetration_rate": 100, # 穿透率上限100%
#     "anti_crit_rate": 500    # 抗暴率上限500%
# }
```

**参考位置:** `plugins/xiuxian_game/battle/battle_attributes.py:16-25`

### 判定战斗属性

```python
from plugins.xiuxian_game.battle.battle_attributes import BattleAttributeCalculator

# 命中概率计算
hit_chance = BattleAttributeCalculator.calculate_hit_chance(
    attacker_accuracy=80,  # 攻击者命中率%
    defender_dodge=30      # 防御者闪避率%
)
# 返回: 0.5 (50%命中概率,范围0.1-1.0)

# 暴击判定
is_critical = BattleAttributeCalculator.roll_critical_hit(
    crit_rate=50,          # 暴击率%
    rng=rng               # Optional[random.Random]: 随机数生成器
)
# 返回: True或False

# 连击判定
combo_count = BattleAttributeCalculator.roll_combo_attack(
    combo_rate=30,         # 连击率%
    rng=rng
)
# 返回: 1(无连击)或2-4(连击次数)

# 先手判定
player_first = BattleAttributeCalculator.determine_turn_order(
    player_agility=150,   # 玩家敏捷
    enemy_agility=120,    # 敌方敏捷
    rng=rng
)
# 返回: True(玩家先手)或False(敌方先手)
```

**参考位置:** `plugins/xiuxian_game/battle/battle_attributes.py:155-233`

## 4. 理解伤害计算

### 防御减伤公式

```python
from plugins.xiuxian_game.utils import apply_defense_mitigation

# 计算防御减伤
final_damage = apply_defense_mitigation(
    base_damage=1000,  # 基础伤害
    defense=600        # 防御力
)
# 计算过程:
# flat_reduction = min(600, 1000 * 600 / (600 + 1000))
#                 = min(600, 375) = 375
# final_damage = max(1, 1000 - 375) = 625
```

**公式:** `final_damage = max(1, base_damage - min(defense, base_damage * defense / (defense + 100)))`

**参考位置:** `plugins/xiuxian_game/utils.py`

### 暴击伤害计算

```python
# 暴击倍数 = 1.5 + (暴击力 * 0.1)
critical_multiplier = 1.5 + (critical_power * 0.1)
final_damage = base_damage * critical_multiplier

# 示例: 暴击力150,基础伤害1000
# multiplier = 1.5 + (150 * 0.1) = 3.0
# final_damage = 1000 * 3.0 = 3000
```

### 穿透机制

```python
# 穿透率削减防御力
penetration_ratio = penetration_rate / 100.0
effective_defense = defense * (1 - penetration_ratio)

# 示例: 穿透率50%,防御力600
# effective_defense = 600 * (1 - 0.5) = 300
```

### 斩龙闪20%必中伤害拆分

斩龙闪的特殊机制(通过IGNORE_DEFENSE效果实现):

```python
# 20%部分: 必中(绕过命中判定),不参与暴击/穿透/减伤
damage_20_percent = base_damage * 0.2

# 80%部分: 常规判定(命中→暴击→穿透→防御减伤)
damage_80_percent = apply_defense_mitigation(base_damage * 0.8, defense)

# 最终伤害 = 20%部分 + 80%部分
final_damage = damage_20_percent + damage_80_percent
```

**参考位置:** `plugins/xiuxian_game/battle/enhanced_engine.py:631-646`

## 5. 获取玩家装备

### 查询已装备物品

```python
from sqlalchemy import select
from plugins.xiuxian_game.models.inventory import ItemInstance

# 查询玩家已装备的物品
stmt = select(ItemInstance).where(
    ItemInstance.player_id == player.id,
    ItemInstance.equipped == True
)
equipped_items = (await session.execute(stmt)).scalars().all()

# 每个ItemInstance包含:
# - item: ItemConfig(物品配置)
# - config: ItemConfig(别名,指向item)
# - enhancement_level: 升阶等级(影响效果解锁)
# - extra_attrs: Dict(额外属性加成)
```

**装备效果解锁规则:**
- 普通装备: +2阶解锁第1个效果,+4阶解锁第2个,依此类推
- VIP定制装备(斩龙闪、镜怨之衣): 0阶即解锁全部效果

**参考位置:** `plugins/xiuxian_game/battle/integration_helper.py:88-102`

## 6. 战斗命令实现示例

### PvP切磋命令

```python
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from nonebot.params import CommandArg
from plugins.xiuxian_game.battle.integration_helper import BattleIntegrationHelper

pvp_cmd = on_command("切磋", aliases={"pvp", "PVP"}, block=True)

@pvp_cmd.handle()
async def handle_pvp(event: MessageEvent, args: Message = CommandArg()):
    # 解析参数
    msg = args.extract_plain_text().strip()
    if not msg:
        await pvp_cmd.finish("请输入: 切磋 <对方UID>")

    target_uid = int(msg)

    # 获取双方玩家
    challenger = await get_player_by_qq(event.user_id, session)
    defender = await get_player_by_uid(target_uid, session)

    # 执行战斗
    (player1_won, battle_log, p1_damage, p2_damage) = await BattleIntegrationHelper.compact_player_vs_player_battle(
        player1=challenger,
        player2=defender,
        session=session
    )

    # 发送结果
    result_message = "\n".join(battle_log)
    await pvp_cmd.finish(result_message)
```

### 模拟战斗命令

```python
simulate_cmd = on_command("模拟战斗", block=True)

@simulate_cmd.handle()
async def handle_simulate(event: MessageEvent, args: Message = CommandArg()):
    # 解析参数: 模拟战斗 <UID1> <UID2>
    msg = args.extract_plain_text().strip().split()
    if len(msg) != 2:
        await simulate_cmd.finish("请输入: 模拟战斗 <UID1> <UID2>")

    uid1, uid2 = int(msg[0]), int(msg[1])

    # 获取双方玩家
    player1 = await get_player_by_uid(uid1, session)
    player2 = await get_player_by_uid(uid2, session)

    # 执行战斗(使用随机种子实现可重现)
    import hashlib
    seed = hashlib.md5(f"{uid1}_{uid2}".encode()).hexdigest()

    (player1_won, battle_log, _, _) = await BattleIntegrationHelper.compact_player_vs_player_battle(
        player1=player1,
        player2=player2,
        session=session,
        seed=seed
    )

    # 发送结果
    await simulate_cmd.finish("\n".join(battle_log))
```

## 7. 调试技巧

### 使用随机种子重现战斗

```python
# 第一次战斗
seed = "test_seed_123"
result1 = await BattleIntegrationHelper.compact_player_vs_player_battle(p1, p2, session, seed=seed)
print("\n".join(result1[1]))

# 第二次战斗(使用相同种子)
result2 = await BattleIntegrationHelper.compact_player_vs_player_battle(p1, p2, session, seed=seed)
# 结果完全一致,便于调试
```

### 查看战斗日志

```python
# battle_log包含详细的战斗过程
for log_entry in battle_log:
    print(log_entry)
    # 输出示例:
    # "⚔️ 玩家A攻击玩家B 造成150伤害 [20%:30 + 80%:120]"
    # "🔄 连击x2 造成120伤害"
    # "🧡 玩家A吸血22HP"
    # "✨ 玩家B的buff_attack效果结束"
```

### 检查效果是否注册

```python
from plugins.xiuxian_game.domain.effects.adapters.battle_effect_register import get_registered_bridges

# 获取所有已注册的战斗效果桥接器
bridges = get_registered_bridges()
print(f"已注册 {len(bridges)} 个战斗效果")

# 查找特定效果
for bridge in bridges:
    if "斩龙闪" in bridge.effect_id:
        print(f"找到效果: {bridge.effect_id}")
        print(f"  触发类型: {bridge.trigger_config.trigger}")
        print(f"  效果类型: {bridge.trigger_config.effect}")
        print(f"  触发概率: {bridge.trigger_config.chance}%")
```

### 启用调试日志

```python
import logging
logging.getLogger("plugins.xiuxian_game.battle").setLevel(logging.DEBUG)
```
