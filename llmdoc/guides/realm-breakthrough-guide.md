# 境界突破机制指南

## 1. 境界系统基础

### 1.1 境界等级设计

**境界体系** (`plugins/xiuxian_game/player/realm_utils.py:15-35`):
```
凡人 (Lv.1-20) → 腐体境 (Lv.21-40) → 血咒境 (Lv.41-60) → ... → 灾厄境 (Lv.251-300)
→ 冥返 → 一转境界 (冥返境/轮回境/涅槃境, Lv.301-500)
→ 冥返 → 二转境界 (虚无境/混沌境/太初境/无极境/永恒境, Lv.501-1000)
→ 冥返 → 三转及以上 (超脱境/至尊境/神话境...无上境, Lv.1001+)
```

**关键配置**:
- 境界数量: 35个预设境界 + 动态超越境界
- 阈值系统: 每20-500级一个境界阈值
- 动态扩展: 超过3000级后每500级生成新境界

### 1.2 境界名称显示

**转数前缀** (`plugins/xiuxian_game/player/realm_utils.py:128-148`):
```python
from plugins.xiuxian_game.player.realm_utils import realm_by_level_and_reincarnation

# 0转: "血咒境"
realm = realm_by_level_and_reincarnation(50, 0)

# 1转: "一转·血咒境"
realm = realm_by_level_and_reincarnation(350, 1)

# 2转: "二转·血咒境"
realm = realm_by_level_and_reincarnation(550, 2)

# 10转+: "轮回10世·血咒境"
realm = realm_by_level_and_reincarnation(1050, 10)
```

## 2. 突破机制

### 2.1 成功率计算

**突破成功率** (`plugins/xiuxian_game/cultivate/core.py:562-580`):
```python
# 1-30级: 100%成功率
if level < 30:
    success_chance = 1.0
else:
    # 30级后成功率递减
    base_rate = 0.8  # 30级时80%
    decay = 0.005    # 每级-0.5%
    min_rate = 0.1   # 最低10%

    success_chance = max(min_rate, base_rate - decay * (level - 30))

    # 失败累加机制
    fail_bonus = breakthrough_fail_count * 0.01  # 每次失败+1%
    success_chance += fail_bonus
    success_chance = min(success_chance, 0.95)  # 上限95%

# 护航/棺材钉: 必定成功
if use_guardian or use_coffin_nail:
    success_chance = 1.0
```

**失败保护**:
- 无月卡: 保留70%修为
- 基础月卡: 保留75%修为
- 高级月卡: 保留80%修为

### 2.2 护航成本

**怨念护航** (`plugins/xiuxian_game/cultivate/core.py:558-560`):
```python
guardian_cost = 50 + level * 15
# Lv.30: 50 + 30*15 = 500怨念
# Lv.100: 50 + 100*15 = 1550怨念
# Lv.300: 50 + 300*15 = 4550怨念
```

### 2.3 执行突破

**单次突破**:
```python
from plugins.xiuxian_game.cultivate.core import attempt_breakthrough

success, msg = await attempt_breakthrough(
    player=player,
    use_guardian=False,  # 是否使用护航
    use_coffin_nail=False  # 是否使用棺材钉
)
```

**连续突破** (推荐):
```python
from plugins.xiuxian_game.cultivate.core import continuous_breakthrough

result = await continuous_breakthrough(
    player=player,
    use_guardian_mode=True,  # 镇厄模式(自动消耗怨念)
    stop_at_reincarnation=True  # 达到冥返要求等级时停止
)
# result = {
#     'total_breakthroughs': 5,
#     'total_exp_cost': 10000,
#     'total_guardian_cost': 5000,
#     'total_attribute_points': 50
# }
```

## 3. 冥返转生机制

### 3.1 冥返等级要求

**等级要求** (`plugins/xiuxian_game/cultivate/reincarnation.py:192-213`):
```python
from plugins.xiuxian_game.cultivate.reincarnation import get_required_level_for_reincarnation

# 第1次冥返: 300级
req_level = get_required_level_for_reincarnation(0)  # 300

# 第2次冥返: 500级
req_level = get_required_level_for_reincarnation(1)  # 500

# 第3次冥返: 1000级
req_level = get_required_level_for_reincarnation(2)  # 1000

# 第4次冥返: 1500级
req_level = get_required_level_for_reincarnation(3)  # 1500

# 第5次冥返: 2000级
req_level = get_required_level_for_reincarnation(4)  # 2000
```

### 3.2 属性继承规则

**冥返流程** (`plugins/xiuxian_game/cultivate/reincarnation.py:22-90`):
```python
from plugins.xiuxian_game.cultivate.reincarnation import ReincarnationService

async with UnitOfWork(session_factory) as uow:
    service = ReincarnationService(uow.players)
    success, msg = await service.perform_reincarnation(player_id)
```

**属性重置逻辑**:
1. 获取永久加成(丹药使用记录、VIP装备加成)
2. 重置为基础值 + 永久加成
3. 重置等级为1,经验为0,属性点为0
4. 增加转数(reincarnation_level+1)
5. 重新计算装备加成(基于新基础属性)
6. 恢复满血满蓝

### 3.3 转数加成

**每级属性点** (`plugins/xiuxian_game/cultivate/reincarnation.py:174-189`):
```python
from plugins.xiuxian_game.cultivate.reincarnation import get_attribute_points_per_level

# 0转: 10点/级
points = get_attribute_points_per_level(0)  # 10

# 1转: 15点/级
points = get_attribute_points_per_level(1)  # 15

# 2转: 20点/级
points = get_attribute_points_per_level(2)  # 20

# 3转: 25点/级
points = get_attribute_points_per_level(3)  # 25
```

**修炼效率加成**:
```python
from plugins.xiuxian_game/cultivate.reincarnation import get_cultivation_efficiency_bonus

# 1转: +50%修炼速度
bonus = get_cultivation_efficiency_bonus(1)  # 0.5

# 2转: +100%修炼速度
bonus = get_cultivation_efficiency_bonus(2)  # 1.0

# 3转: +150%修炼速度
bonus = get_cultivation_efficiency_bonus(3)  # 1.5
```

### 3.4 装备处理

冥返时会自动重新计算装备加成:
1. 清除所有装备的持久化加成记录
2. 获取冥返后的基础属性
3. 基于新基础属性重新计算装备加成
4. 保存新的持久化加成到`extra_attrs["_persist_bonus"]`

## 4. 修炼系统

### 4.1 修炼经验计算

**基础经验** (`plugins/xiuxian_game/cultivate/core.py:110-168`):
```python
import random

k = 7 if level <= 10 else 6
base_gain = 50 * (1 + level / k)  # base_exp = 50
base_exp_gain = base_gain * random.uniform(0.8, 1.2)
```

**多重加成**:
```python
# 月卡加成
card_bonus = base_exp_gain * 月卡修炼效率(0.2/0.5)

# 转数加成
reincarnation_bonus = base_exp_gain * 转数效率(0.5 * 转数)

# 公会加成
guild_bonus = base_exp_gain * 公会等级倍率

# 阴宅加成
mansion_bonus = base_exp_gain * 阴宅等级倍率(0.2-2.9)

# 总经验
exp_gain = base_exp_gain + card_bonus + reincarnation_bonus + guild_bonus + mansion_bonus
```

### 4.2 修炼冷却

- 基础冷却: 300秒(5分钟)
- 文案池: 12条随机修炼文案
- 进度提示: 显示还需修炼次数和预计小时数

### 4.3 闭关系统

**闭关流程** (`plugins/xiuxian_game/cultivate/core.py:249-372`):
```python
from plugins.xiuxian_game.cultivate.core import start_seclusion

await start_seclusion(player_id)
# 设置is_secluded=True, seclusion_start_time=now
```

**出关结算** (`plugins/xiuxian_game/cultivate/core.py:374-534`):
```python
from plugins/xiuxian_game.cultivate.core import end_seclusion

await end_seclusion(player_id)
# 计算闭关时长、基础经验、加成、获得总经验
```

**棺材钉系统** (仅闭关有效):
- 每个棺材钉提升0.5%效率
- 最多100根有效(50%加成上限)
- 从背包中自动计算数量

## 5. 经验曲线

**升级经验公式** (`plugins/xiuxian_game/utils.py:20-35`):
```python
from plugins.xiuxian_game.utils import calculate_level_up_exp

# 10级前: 线性增长
# Lv.1→2: 10经验
# Lv.2→3: 20经验
# Lv.9→10: 90经验

# 10级后: 指数增长
# Lv.10→11: 90 + 1² * 6 = 96经验
# Lv.30→31: 90 + 20² * 6 = 2490经验
# Lv.100→101: 90 + 90² * 6 = 48,690经验
```

## 6. 最佳实践

- **30级前**: 尽量突破,100%成功率
- **30-100级**: 考虑使用护航道具,失败累加机制
- **100-300级**: 规划冥返,积累永久加成(丹药、VIP装备)
- **300级+**: 优先冥返,转数提供实际收益
- **闭关修炼**: 离线时使用,结合棺材钉提升效率
- **连续突破**: 自动化流程,减少重复操作

## 7. 常见问题

**Q: 突破失败后怎么办?**
A: 失败会保留70-80%修为(月卡加成),并增加下次成功率(+1%),可继续尝试或使用护航。

**Q: 冥返后装备还在吗?**
A: 装备不会丢失,但会基于新基础属性重新计算加成,百分比加成可能变低。

**Q: 什么时候冥返最合适?**
A: 到达要求等级(300/500/1000...)时,且已获得足够永久加成(丹药、VIP装备)后冥返。

**Q: 如何快速提升修炼效率?**
A: 购买月卡(+20%/+50%)、加入公会(建筑加成)、建造阴宅(+20%-290%)、转生(+50%*转数)。
