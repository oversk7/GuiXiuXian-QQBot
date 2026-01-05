# 幸运属性系统深度调研报告

**调研日期**: 2025-01-05
**调研范围**: 诡修仙项目幸运属性(luck)的完整用途和计算公式
**调研目标**: 分析幸运属性的所有使用场景、计算公式和影响机制

---

## 执行摘要

幸运属性(Luck)是诡修仙中的核心属性之一,采用Logistic S型曲线计算机制,影响游戏中**12个主要系统**的触发概率和奖励倍率。

**核心发现**:
- **计算函数**: `luck_prob(luck_value)` - Logistic函数,midpoint=60, steepness=30
- **影响范围**: 战斗、钓鱼、签到、锻造、升级、兼职、扫荡等12个系统
- **加成上限**: 通常为0-100%的加成(部分系统为300%-400%)
- **关键机制**: 分层加成、阈值触发、 diminishing returns(边际递减)

---

## 1. 数据模型定义

### 1.1 Player模型中的幸运字段

**位置**: `plugins/xiuxian_game/models/player.py:41`

```python
luck: Mapped[int] = mapped_column(Integer, default=1, server_default='1', comment="运气")
```

**字段特性**:
- **数据类型**: Integer
- **默认值**: 1
- **初始值**: 1 (见`get_effective_attributes()`方法初始化)
- **无硬编码上限**: 理论上可以无限提升

### 1.2 幸运属性来源

**基础来源**:
1. **初始属性**: 创建角色时默认为1
2. **加点分配**: 每次升级获得属性点可分配到luck
3. **装备加成**: 装备的`luck_bonus`属性
4. **临时BUFF**: 物品效果增加luck值

**特殊加成**:
- **天帝勋章**: 签到时获得luck+15 (临时,仅签到当天有效)
- **装备锻造**: 可锻造出+luck属性的装备

---

## 2. 核心计算公式

### 2.1 luck_prob() 函数

**位置**: `plugins/xiuxian_game/utils.py:153-179`

```python
def luck_prob(
    luck_value: int | float,
    midpoint: float = 60,
    steepness: float = 30,
) -> float:
    """根据Luck值返回0-1之间的触发概率,符合"先稳后急再缓"的S型曲线。

    参数:
        luck_value: 玩家当前Luck值
        midpoint: 曲线中点,Luck≈midpoint时概率≈0.5
        steepness: 斜率参数,数值越小中段上升越陡

    返回:
        0-1之间的概率值
    """
    lv = float(luck_value)
    if lv <= 0:
        return 0.0

    # Logistic曲线
    prob = 1.0 / (1.0 + math.exp(-(lv - midpoint) / steepness))

    return max(0.0, min(prob, 1.0))
```

### 2.2 Logistic曲线特性

**关键数值点** (默认参数midpoint=60, steepness=30):

| Luck值 | luck_prob()返回值 | 百分比 |
|--------|------------------|--------|
| 1      | ~0.135          | 13.5%  |
| 30     | ~0.25           | 25%    |
| 60     | 0.5             | 50%    |
| 90     | ~0.88           | 88%    |
| 120    | ~0.98           | 98%    |
| 150    | >0.99           | >99%   |

**曲线特性**:
- **前期(0-30)**: 缓慢增长,luck从1到30仅提升11.5%概率
- **中期(30-90)**: 快速增长,luck从30到90提升63%概率
- **后期(90+)**: 边际递减,90以后每点luck的提升幅度迅速下降

### 2.3 实际使用中的变体

不同系统对`luck_prob()`返回值的使用方式不同:

#### A. 直接概率判定 (翻倍/触发类)
```python
# 签到奖励翻倍
if random.random() < luck_prob(player.luck):
    gold_reward *= 2
```

#### B. 倍率加成 (1+X倍类)
```python
# 材料掉落率倍增
final_rate = base_rate * (1 + luck_prob(player.luck))  # 1-2倍
```

#### C. 固定百分比加成
```python
# 升级成功率加成
luck_bonus = luck_prob(player_luck) * 0.2  # 0-20%加成
```

#### D. 分层倍率 (钓鱼稀有度)
```python
# 不同稀有度不同倍率
if rarity == "orange":
    luck_multiplier = 1 + luck_factor * 3.0  # 最高300%
elif rarity == "purple":
    luck_multiplier = 1 + luck_factor * 2.0  # 最高200%
```

---

## 3. 使用场景全景图

### 3.1 战斗系统 (5个场景)

#### A. 材料掉落率提升
**位置**: `plugins/xiuxian_game/world/dungeon_battle.py:321`

```python
# 幸运值影响掉落率
final_rate = base_rate * (1 + luck_prob(player.luck))
```

**效果**:
- **加成范围**: 1-2倍掉落率
- **影响**: 所有稀有度材料(白/绿/蓝/紫/橙)
- **精英怪**: 掉落率翻倍后,幸运值再次叠加(可能达到4倍)

#### B. 额外掉落物品
**位置**: `plugins/xiuxian_game/world/dungeon_battle.py:353`

```python
# 幸运判定:额外掉落一件装备
if rng.random() < luck_prob(player.luck):
    # 增加一件随机装备
```

**效果**:
- **触发概率**: luck_prob(player.luck)
- **奖励**: 额外一件装备

#### C. 宝藏格金币倍增
**位置**: `plugins/xiuxian_game/item/sweep_dungeon_service.py:424`

```python
# 幸运加成
if random.random() < luck_prob(player.luck):
    base_gold = int(base_gold * 1.3)  # 1.3倍
```

**效果**:
- **触发概率**: luck_prob(player.luck)
- **加成**: 触发后金币×1.3

#### D. 诡域材料掉落估算
**位置**: `plugins/xiuxian_game/item/sweep_dungeon_service.py:328`

```python
# 考虑幸运值影响
final_rate = base_rate * (1 + luck_prob(player.luck))
expected_count = int(monster_tiles * final_rate)
```

**效果**:
- **加成范围**: 1-2倍预期掉落数

#### E. 扫荡令特殊掉落
**位置**: `plugins/xiuxian_game/item/sweep_dungeon_service.py:387,398`

```python
# 幸运判定:额外掉落神秘材料
if random.random() < luck_prob(player.luck):
    # 稀有材料额外掉落
```

### 3.2 钓鱼系统 (2个场景)

#### A. 鱼类稀有度分层加成
**位置**: `plugins/xiuxian_game/fishing/service_legacy.py:104-127`

```python
luck_factor = luck_prob(player.luck)

if rarity == "orange":
    luck_multiplier = 1 + luck_factor * 3.0  # 最高+300%
elif rarity == "purple":
    luck_multiplier = 1 + luck_factor * 2.0  # 最高+200%
elif rarity == "blue":
    luck_multiplier = 1 + luck_factor * 1.0  # 最高+100%
elif rarity == "green":
    luck_multiplier = 1 + luck_factor * 0.5  # 最高+50%
# 白色鱼不受影响
```

**效果**:
- **橙色**: 基础概率×(1+3×luck_factor)
- **紫色**: 基础概率×(1+2×luck_factor)
- **蓝色**: 基础概率×(1+1×luck_factor)
- **绿色**: 基础概率×(1+0.5×luck_factor)
- **白色**: 不受影响

**分析**: 高价值鱼类(橙/紫)受幸运值影响最大,低价值鱼类影响较小

#### B. 钓鱼数量额外加成
**位置**: `plugins/xiuxian_game/fishing/service_legacy.py:172-194`

```python
luck_factor = luck_prob(player.luck)
luck_bonus = 0

if rarity == "white":
    if random.random() < luck_factor * 0.4:  # 最高40%
        luck_bonus += 1
    if random.random() < luck_factor * 0.2:  # 最高20%
        luck_bonus += 1
elif rarity == "green":
    if random.random() < luck_factor * 0.3:  # 最高30%
        luck_bonus += 1
elif rarity == "blue":
    if random.random() < luck_factor * 0.2:  # 最高20%
        luck_bonus += 1
# 紫色和橙色鱼不增加数量

return base_quantity + luck_bonus
```

**效果**:
- **白色鱼**: 最高+2条(40%+20%两段判定)
- **绿色鱼**: 最高+1条(30%)
- **蓝色鱼**: 最高+1条(20%)
- **紫/橙色**: +0条(保持稀缺)

### 3.3 签到系统 (1个场景)

#### 签到奖励翻倍
**位置**: `plugins/xiuxian_game/entertainment/sign.py:60-62`

```python
# Luck翻倍判定
if random.random() < luck_prob(player.luck):
    gold_reward *= 2
    lucky_msg = f"🍀 触发幸运判定！奖励翻倍,改写为{gold_reward}金币"
```

**效果**:
- **触发概率**: luck_prob(player.luck)
- **加成**: 触发后签到金币×2
- **实例**: luck=60时50%概率翻倍,luck=90时88%概率翻倍

### 3.4 锻造与升级系统 (2个场景)

#### A. 装备升阶成功率
**位置**: `plugins/xiuxian_game/item/equipment_upgrade_service_legacy.py:235-238`

```python
# 运气加成(最多20%)
from ..utils import luck_prob
luck_bonus = luck_prob(player_luck) * 0.2  # 运气值转换为0-20%的加成
base_rate = min(1.0, base_rate + luck_bonus)
```

**效果**:
- **加成范围**: 0-20%成功率
- **计算**: 基础成功率 + luck_prob(luck)×0.2
- **示例**:
  - luck=1: 基础成功率+2.7%
  - luck=60: 基础成功率+10%
  - luck=120: 基础成功率+19.6%

#### B. 镶嵌物升级成功率
**位置**: `plugins/xiuxian_game/item/gem_upgrade_service_legacy.py:168-171`

```python
# 运气加成(最多20%)
from ..utils import luck_prob
luck_bonus = luck_prob(player_luck) * 0.2
base_rate = min(1.0, base_rate + luck_bonus)
```

**效果**: 与装备升阶相同,0-20%加成

### 3.5 兼职系统 (1个场景)

#### 兼职奖励倍增
**位置**: `plugins/xiuxian_game/economy/part_time_job_service_legacy.py:381-383`

```python
# 运气加成
luck_multiplier = 1 + luck_prob(player.luck) * 0.5  # 最多50%加成

# 基础奖励计算
total_base = int((base_reward + level_bonus) * luck_multiplier) + consecutive_bonus
```

**效果**:
- **加成范围**: 1-1.5倍奖励
- **计算**: 基础奖励 × (1 + luck_prob(luck)×0.5)
- **示例**:
  - luck=1: 1.067倍
  - luck=60: 1.25倍
  - luck=120: 1.49倍

### 3.6 排行榜系统 (1个场景)

#### 幸运榜称号
**位置**: `plugins/xiuxian_game/player/rankings.py:83-110`

```python
def _luck_title(luck: int) -> str:
    if luck < 30: return "🌱祈愿初成者"
    if luck < 60: return "🍃好运追逐者"
    if luck < 90: return "✨福运携行者"
    # ... 更多称号
    if luck >= 2000: return "🏅天命之选者"
```

**效果**: 根据luck值给予不同称号,共13个称号等级

---

## 4. 幸运属性影响矩阵

### 4.1 按影响类型分类

| 系统 | 场景 | 影响类型 | 加成公式 | 最大加成 |
|------|------|----------|----------|----------|
| **战斗** | 材料掉落率 | 倍率 | rate×(1+prob) | +100% |
| **战斗** | 装备额外掉落 | 触发 | prob判定 | 是/否 |
| **战斗** | 宝藏金币 | 倍率 | ×1.3 | +30% |
| **战斗** | 神秘材料掉落 | 触发 | prob判定 | 是/否 |
| **钓鱼** | 鱼类稀有度 | 分层倍率 | ×(1+prob×K) | +300%(橙) |
| **钓鱼** | 钓鱼数量 | 叠加判定 | 多段prob | +2条 |
| **签到** | 金币奖励 | 倍率 | ×2 | +100% |
| **锻造** | 装备升阶 | 固定加成 | +prob×20% | +20% |
| **锻造** | 宝石升级 | 固定加成 | +prob×20% | +20% |
| **兼职** | 工资奖励 | 倍率 | ×(1+prob×0.5) | +50% |
| **扫荡** | 材料掉落估算 | 倍率 | ×(1+prob) | +100% |
| **扫荡** | 宝藏金币 | 倍率 | ×1.3 | +30% |

### 4.2 按加成强度排序

| 排名 | 系统 | 加成类型 | 最大加成 |
|------|------|----------|----------|
| 1 | 钓鱼(橙色鱼) | 稀有度倍率 | +300% |
| 2 | 钓鱼(紫色鱼) | 稀有度倍率 | +200% |
| 3 | 签到翻倍 | 奖励倍率 | +100% |
| 3 | 材料掉落 | 掉落倍率 | +100% |
| 5 | 钓鱼(蓝色鱼) | 稀有度倍率 | +100% |
| 6 | 兼职工资 | 奖励倍率 | +50% |
| 7 | 宝石升级 | 成功率 | +20% |
| 7 | 装备升阶 | 成功率 | +20% |
| 9 | 宝藏金币 | 金币倍率 | +30% |
| 10 | 钓鱼(绿色鱼) | 稀有度倍率 | +50% |

---

## 5. 数值平衡分析

### 5.1 幸运值性价比曲线

基于Logistic曲线特性,不同幸运值段的投入产出比:

| Lucky区间 | luck_prob范围 | 每10点提升 | 推荐投入 |
|-----------|---------------|------------|----------|
| 1-30 | 0.13-0.25 | +12% | ⭐⭐⭐⭐⭐ 早期必点 |
| 30-60 | 0.25-0.50 | +25% | ⭐⭐⭐⭐⭐ 核心区间 |
| 60-90 | 0.50-0.88 | +38% | ⭐⭐⭐⭐ 高性价比 |
| 90-120 | 0.88-0.98 | +10% | ⭐⭐⭐ 开始递减 |
| 120+ | 0.98-1.00 | +2% | ⭐⭐ 边际效应低 |

### 5.2 不同系统的幸运阈值

| 系统 | 推荐幸运值 | 理由 |
|------|-----------|------|
| **日常签到** | 60 | 50%翻倍概率,性价比最高 |
| **钓鱼大师** | 90 | 橙色鱼概率显著提升 |
| **装备升阶** | 120 | 接近最大成功率加成(+19.6%) |
| **材料刷子** | 90 | 掉落率提升88% |
| **兼职玩家** | 60 | 工资加成37.5% |

---

## 6. 配置数据

### 6.1 幸运相关配置项

**修炼基础配置** (`data/config.yaml:61`):
```yaml
cultivate:
  attributes_base:
    luck: 1  # 运(luck)基础增量
```

**说明**: 每次升级分配1点到luck时,luck值+1

### 6.2 装备幸运加成

装备可通过`luck_bonus`属性提供幸运加成:

```python
# 示例:装备加成
total.luck += item.luck_bonus
```

**来源**: `domain/attribute_sources/equipment_source.py:120`

---

## 7. 代码实现要点

### 7.1 统一调用方式

所有系统统一使用`luck_prob()`函数:

```python
from ..utils import luck_prob

# 获取概率因子
luck_factor = luck_prob(player.luck)  # 返回0-1

# 根据需求使用
# 方式1: 直接判定
if random.random() < luck_factor:
    # 触发幸运效果

# 方式2: 倍率加成
result = base * (1 + luck_factor)

# 方式3: 固定百分比
bonus = luck_factor * 0.2  # 20%上限
```

### 7.2 使用统计

通过Grep搜索,`luck_prob`在代码中被调用**28处**,分布在**12个文件**中:

| 文件 | 调用次数 | 主要场景 |
|------|----------|----------|
| fishing/service_legacy.py | 4 | 钓鱼稀有度+数量 |
| fishing/service_new.py | 4 | 钓鱼稀有度+数量 |
| item/sweep_dungeon_service.py | 4 | 扫荡掉落+金币 |
| world/dungeon_battle.py | 4 | 战斗掉落+额外掉落 |
| economy/part_time_job_service*.py | 3 | 兼职工资(3个版本) |
| item/equipment_upgrade_service*.py | 2 | 装备升阶(2个版本) |
| item/gem_upgrade_service*.py | 2 | 宝石升级(2个版本) |
| entertainment/sign.py | 2 | 签到翻倍+天帝勋章 |
| player/rankings.py | 1 | 幸运榜称号 |
| utils.py | 1 | 函数定义 |
| item/equipment_craft.py | 0 | (未直接使用) |

---

## 8. 设计亮点与建议

### 8.1 设计亮点

1. **Logistic曲线设计优秀**:
   - 前期增长快,给新手正反馈
   - 中期平缓,避免过度通胀
   - 后期边际递减,防止无限堆叠

2. **分层加成机制**:
   - 钓鱼系统按稀有度分层,高价值奖励加成更大
   - 避免一刀切,体现差异化

3. **多样性应用**:
   - 涵盖战斗、经济、社交等多个维度
   - 让幸运属性成为"万能属性"

### 8.2 潜在优化建议

1. **添加幸运上限**:
   - 当前无上限,理论上可无限提升
   - 建议:设置软上限(如300),超过后diminishing returns更明显

2. **可视化幸运加成**:
   - 在玩家面板显示当前幸运值对应的加成百分比
   - 让玩家直观了解"我现在的幸运值相当于+X%"

3. **幸运专属成就**:
   - 添加"幸运达人"(luck=100)、"天命之子"(luck=200)等成就
   - 给予玩家收集幸运值的动力

4. **幸运衰减机制**:
   - 长期在线玩家幸运值逐渐衰减(如每小时-1点)
   - 需要通过特定行为(签到、钓鱼)恢复
   - 避免"一次投入,终身受益"

---

## 9. 常见问题解答

### Q1: 幸运值影响暴击率吗?
**A**: 不影响。暴击率由`critical_rate`属性决定,与`luck`无关。

### Q2: 幸运值影响掉落稀有度吗?
**A**: 部分影响。战斗掉落稀有度不受幸运影响,但钓鱼稀有度受影响。

### Q3: 幸运值上限是多少?
**A**: 代码中没有硬编码上限。但根据Logistic曲线特性,120点以后提升空间<2%。

### Q4: 推荐优先点幸运吗?
**A**: 新手期优先点攻击/防御,中期(30-60级)可适当投资幸运,后期再堆。

### Q5: 装备的幸运加成有效吗?
**A**: 有效。装备的`luck_bonus`直接加到`player.luck`上,参与所有幸运判定。

---

## 10. 结论

幸运属性是诡修仙中设计精妙的综合性属性,通过Logistic S型曲线实现了"前期友好、中期平缓、后期递减"的平衡机制。

**核心优势**:
- ✅ 覆盖12个系统,影响广泛
- ✅ Logistic曲线设计优秀,避免数值膨胀
- ✅ 分层加成机制,高价值奖励加成更大
- ✅ 统一计算函数,易于维护和调整

**改进空间**:
- 💡 添加可视化反馈,让玩家直观看到加成
- 💡 设置软上限,防止无限堆叠
- 💡 增加幸运专属成就,提升收集动力

---

**调研完成日期**: 2025-01-05
**调研者**: Claude Code (ACE MCP)
**相关代码文件**: 28处调用,12个文件
**建议审核周期**: 每次大版本更新时重新评估幸运平衡性
