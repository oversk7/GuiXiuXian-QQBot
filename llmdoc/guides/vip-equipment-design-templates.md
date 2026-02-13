# VIP定制装备设计模板

## 1. Identity

- **What it is:** VIP定制装备设计方案集，提供带专属主动技能的高端装备设计模板
- **Purpose:** 为1000元档位的VIP装备定制提供参考方案，实现差异化的游戏体验和战略价值

## 2. 设计原则

### 2.1 定价合理性(1000元 vs 斩龙闪600元)

**斩龙闪的价值基准:**
- 6个强力被动效果，0阶全解锁
- 属性总量: 固定300点，百分比300%
- 每日成长: 最多+120生命+40随机属性
- 无主动技能

**1000元档位的额外价值(+400元):**
1. **专属主动技能** - 改变玩法的战略性技能
2. **便利性价值** - 节省大量时间(跑图、跑商、救援)
3. **战略性价值** - 公会战、世界BOSS抢夺优势
4. **独特性** - 全服唯一定制，炫耀价值
5. **成长空间** - 基础属性不低于斩龙闪，成长机制相当

### 2.2 平衡性要求

- 技能必须有冷却时间和资源消耗
- 强力效果需要条件限制或代价
- 避免破坏经济系统(不能无限刷金币/材料)
- 保持PvP公平性(技能有反制手段)
- 成长型效果需要明确上限

### 2.3 技术可行性

- 优先使用现有系统(坐标、诡域、战斗)
- 避免需要大量新表或复杂状态管理
- 冷却时间存储在player表的JSON字段
- 技能效果可通过existing机制实现

## 3. 设计方案模板

### 方案一:【归雨】- 雨钉锚点流

**核心定位:** 灵活机动，雨钉锚点传送，携带队友

**基础属性:**
```yaml
item_id: "vip_gui_yu"
name: "归雨"
description: "雨落下之前，你已经不在这里了。"
type: "EQUIPMENT"
rarity: "red"
durability: 360
required_level: 10
attr_bonus: {"attack": 300, "mp": 100, "hp": 100}
attr_ratio: {"attack": 3.0, "mp": 1.0, "hp": 1.0}
gem_slots: 5
```

**装备效果:**
```yaml
special_effects:
  - trigger: "on_attack"
    chance: 25
    effect: "defense_penetration"
    value: 30
    duration: 2
    description: "[1] 伞骨穿：攻击时25%概率，伞骨自伞檐下无声探出；对方尚未看清，已被刺入要害——无视敌人30%防御(持续2回合)"

  - trigger: "on_critical"
    chance: 100
    effect: "lifesteal"
    value: 15
    duration: 0
    description: "[2] 噬雨：暴击时鲜血溅上伞面，来不及落下便被伞布吞尽；伞色似乎更深了一分——吸取造成伤害的15%作为生命值"

  - trigger: "on_dodge"
    chance: 100
    effect: "buff_dodge"
    value: 15
    duration: 2
    description: "[3] 化雨身：闪避时你只是偏了一步，但在对方眼里，你像被雨洗散的影子——闪避率+15%(持续2回合)"

  - trigger: "each_turn"
    chance: 100
    effect: "damage_reduction"
    value: 5
    duration: 999
    description: "[4] 伞下：你撑伞而立，心里生出一种不该有的安稳；可对方看见伞下那道影子，分明不像你——受到伤害减少5%"

  - trigger: "on_kill"
    effect: "gain_agility"
    is_percentage: false
    value: 2
    description: "[5] 夺伞步：击杀后脚步更轻，低头才发现伞柄上又多了一道细纹，像在记名——永久+2敏捷(每日20次，上限+40敏捷)"

  - trigger: "passive"
    effect: "none"
    description: "[6] 鬼域雨钉：可设置3个传送锚点。\
【锚点 设置 名称】在当前位置钉下“雨钉”\
【锚点 传送 1】踏入伞影即走(CD5分钟，消耗5%理智)\
【锚点 携带 UID 1】将对方一并送走(对方回复【同意传送】后生效)\
【锚点】查看列表"

```

**专属主动技能: 鬼域雨钉传送**
- **指令:** `锚点 [操作]`
- **冷却时间:** 5分钟
- **理智消耗:** 5%最大理智
- **装备耐久:** 每次传送-3

**技能选项:**

**1. 设置雨钉**
- **指令:** `锚点 设置 [名称]`
- **效果:** 在当前位置钉下一枚雨钉(最多3个)
- **消耗:** 无消耗，可随时设置
- **示例:** `锚点 设置 公会基地`、`锚点 设置 刷怪点`

**2. 踏入伞影(传送到雨钉)**
- **指令:** `锚点 传送 1/2/3` 或 `锚点 传送 [名称]`
- **效果:** 踏入伞影传送到指定雨钉坐标
- **消耗:** 5%最大理智，耐久3点，CD 5分钟
- **示例:** `锚点 传送 1`、`锚点 传送 公会基地`

**3. 携带同行(双指令确认制)**

采用与求婚/拜师系统相同的异步双指令确认模式(参考`npc_matchmaker.py`和`npc_mentor.py`)：

**发起方(玩家A):**
- **指令:** `锚点 携带 [玩家UID] [锚点序号/名称]`
- **效果:** 向目标玩家发送传送邀请，将对方一并送走(有效期5分钟)
- **消耗:** 确认后才扣除(5%最大理智 + 耐久5点)
- **示例:** `锚点 携带 10001 公会基地`
- **系统提示:**
  ```
  📨 已向 张三[UID:10001] 发送传送邀请
  目标雨钉：[1] 公会基地 - 大都会(100, 200)
  💡 对方需在5分钟内回复【同意传送】
  ```

**接收方(玩家B):**
- **同意:** 回复 `同意传送`
- **拒绝:** 回复 `拒绝传送` 或不回复(5分钟后自动过期)
- **消耗:** 同意后扣除5%最大理智
- **系统提示(同意后):**
  ```
  ✨ 传送成功！
  📍 你和 李四[UID:10002] 一起传送到
  [1] 公会基地 - 大都会(100, 200)
  ```

**4. 查看雨钉列表**
- **指令:** `锚点 列表` 或 `锚点`
- **效果:** 显示所有已钉下的雨钉信息
- **格式:**
  ```
  📍 鬼域雨钉列表
  ━━━━━━━━━━━━━
  [1] 公会基地 - 大都会(100, 200)
  [2] 刷怪点 - 50层诡域(3, -2)
  [3] 市集 - 大都会(-50, 80)
  ━━━━━━━━━━━━━
  💡 使用【锚点 传送 1】踏入伞影(CD5分钟)
  💡 使用【锚点 携带 UID 1】将对方一并送走
  ```

**5. 拔除雨钉**
- **指令:** `锚点 删除 1/2/3` 或 `锚点 删除 [名称]`
- **效果:** 拔除指定雨钉，可重新设置
- **消耗:** 无

**实现要点:**
```python
# 雨钉数据结构存储在 vip_equipment_data
player.vip_equipment_data["rain_anchors"] = [
    {
        "id": 1,
        "name": "公会基地",
        "x": 100,
        "y": 200,
        "region": "大都会",
        "dungeon_level": 0,
        "created_at": "2026-02-12 10:30:00"
    },
    # ... 最多3个
]

# 携带传送邀请(存储在目标玩家的vip_equipment_data中)
# 与求婚/拜师系统相同模式：发起→存储→对方确认→执行
target_player.vip_equipment_data["carry_invite"] = {
    "from_id": "player_id_xxx",  # 发起者player_id
    "from_uid": 10002,           # 发起者UID(用于显示)
    "from_name": "李四",         # 发起者昵称
    "anchor_name": "公会基地",   # 目标雨钉名称
    "anchor_data": {             # 雨钉完整数据
        "x": 100, "y": 200,
        "region": "大都会",
        "dungeon_level": 0
    },
    "created_at": "2026-02-12 10:30:00",
    "expires_at": "2026-02-12 10:35:00"  # 5分钟后过期
}

# 【同意传送】指令处理
# on_command("同意传送")
async def handle_accept_carry(event, session, player):
    invite = player.vip_equipment_data.get("carry_invite")
    if not invite:
        return "⛔ 没有待处理的传送邀请"

    # 检查是否过期
    if datetime.now() > datetime.fromisoformat(invite["expires_at"]):
        del player.vip_equipment_data["carry_invite"]
        return "⛔ 传送邀请已过期"

    # 查找发起者
    from_player = await session.get(Player, invite["from_id"])

    # 执行双人传送
    anchor = invite["anchor_data"]
    for p in [player, from_player]:
        if anchor["dungeon_level"] > 0:
            p.enter_dungeon(anchor["dungeon_level"])
            p.dungeon_x = anchor["x"]
            p.dungeon_y = anchor["y"]
        else:
            if p.is_in_dungeon():
                p.exit_dungeon()
            p.real_world_x = anchor["x"]
            p.real_world_y = anchor["y"]
        p.x = anchor["x"]
        p.y = anchor["y"]

    # 扣除双方理智(5%最大理智)
    player.mp -= int(player.max_mp * 0.05)
    from_player.mp -= int(from_player.max_mp * 0.05)

    # 清除邀请
    del player.vip_equipment_data["carry_invite"]

    return f"✨ 传送成功！你和 {invite['from_name']} 一起到达 {invite['anchor_name']}"
```

**雨钉特性:**
- 雨钉永久有效(除非手动拔除或达到上限后覆盖)
- 雨钉可以在现实世界或诡域中设置
- 诡域雨钉会记录层级+坐标，传送时直接进入对应层级
- 雨钉可以命名，方便记忆(不命名则显示为"雨钉1/2/3")
- 携带同行的队友也会到达相同坐标(不是±3随机)

**适合场景:**
- 公会集结(在公会基地钉下雨钉，随时召集队友)
- 世界BOSS抢夺(在BOSS刷新点钉下雨钉)
- 深渊探索(在高层诡域钉下雨钉，快速返回刷怪)
- 跑商效率(在多个市集钉下雨钉快速传送)

---

### 方案二:【时空断层刀】- 时间回溯流

**核心定位:** 悔棋神技，容错率高，时间操控

**基础属性:**
```yaml
item_id: "vip_time_fracture_blade"
name: "时空断层刀"
description: "斩断因果的时间之刃，可逆转已发生的历史"
type: "EQUIPMENT"
rarity: "red"
durability: 370
required_level: 10
attr_bonus: {"attack": 120, "hp": 90, "agility": 80}
attr_ratio: {"attack": 1.1, "hp": 0.9, "agility": 0.8}
gem_slots: 5
```

**被动效果:**
```yaml
special_effects:
  - trigger: "passive"
    effect: "custom_time_snapshot"
    description: "[1] 时间印记：每30分钟自动保存状态快照(生命%、理智%、坐标)"

  - trigger: "on_attacked"
    effect: "custom_crisis_predict"
    description: "[2] 预知危机：生命首次降至30%以下时自动触发时光倒流(每战1次)"

  - trigger: "first_turn"
    effect: "buff_combo"
    value: 25
    duration: 3
    description: "[3] 时间加速：前3回合连击率+25%"

  - trigger: "on_critical"
    effect: "custom_history_echo"
    description: "[4] 历史回响：暴击后下次攻击重现本次50%伤害"

  - trigger: "on_kill"
    effect: "gain_attack"
    is_percentage: false
    value: 2
    description: "[5] 时之掠夺：击杀敌人后永久+2攻击(每日20次，+40攻击)"

  - trigger: "passive"
    effect: "custom_time_sense"
    description: "[6] 时间感知：可查看过去1小时内经过当前坐标的玩家"
```

**专属主动技能: 时光倒流**
- **指令:** `时光倒流` 或 `倒流 [时间]`
- **冷却时间:** 6小时
- **理智消耗:** 50%最大理智
- **装备耐久:** -10
- **特殊代价:** 倒流30分钟需支付当前金币10%作为"时间税"

**技能选项:**
1. `倒流 5分钟` - 恢复到5分钟前坐标和状态
2. `倒流 30分钟` - 恢复到30分钟前快照(含背包物品!)
3. `倒流 战前` - 恢复到最近一次战斗开始前
4. `倒流 诡域入口` - 传送回进入当前诡域时的坐标

**特殊机制:**
- **时间悖论:** 倒流30分钟会丢失该期间的永久成长
- **历史修正:** 倒流后30分钟内成长效果×2(补偿)
- **战斗限制:** 倒流战前后，当日无法再对同一目标战斗

**实现要点:**
- 状态快照存储在: `player_time_snapshots` 表
- 背包快照存储JSON: `{"timestamp": ..., "inventory": [...]}`
- 倒流逻辑需回滚多个表数据(谨慎操作)
- 防止无限刷材料: 记录倒流使用次数

**适合场景:** 挑战高难度BOSS，高风险深渊探索，贵重交易保护

---

### 方案三:【深渊潜行者】- 诡域速通流

**核心定位:** 诡域速通，跳层挑战，深度探索

**基础属性:**
```yaml
item_id: "vip_abyss_stalker"
name: "深渊潜行者"
description: "深渊的宠儿，可无视层级限制自由穿梭诡域"
type: "EQUIPMENT"
rarity: "red"
durability: 350
required_level: 10
attr_bonus: {"agility": 120, "hp": 90, "mp": 90}
attr_ratio: {"agility": 1.1, "hp": 0.9, "mp": 0.9}
gem_slots: 5
```

**被动效果:**
```yaml
special_effects:
  - trigger: "passive"
    effect: "custom_abyss_adapt"
    description: "[1] 深渊适应：诡域中每深1层+1%全属性(最高100层+100%)"

  - trigger: "passive"
    effect: "custom_layer_phase"
    description: "[2] 层级穿梭：诡域移动时5%概率穿越到±1层相同坐标"

  - trigger: "passive"
    effect: "custom_speedrun_bonus"
    description: "[3] 速通奖励：5回合内击败怪物额外+50%经验和材料"

  - trigger: "on_kill"
    effect: "custom_abyss_weaken"
    description: "[4] 深渊共鸣：击杀后下层怪物-2级(10分钟，叠加，最多-10)"

  - trigger: "on_kill"
    effect: "gain_hp"
    is_percentage: false
    value: 2
    description: "[5] 深度掠夺：击杀敌人后永久+2体质(每日20次，+40体质)"

  - trigger: "passive"
    effect: "custom_abyss_vision"
    description: "[6] 深渊视界：可查看当前诡域完整地图(格子类型、怪物等级)"
```

**专属主动技能: 深渊潜行**
- **指令:** `深渊潜行` 或 `潜行 [目标层]`
- **冷却时间:** 1小时
- **理智消耗:** 目标层级×1点(去50层消耗50理智)
- **装备耐久:** 跨越层数×0.5(去50层消耗25耐久)

**技能选项:**
1. `潜行 N层` - 直接传送到目标层(可跳过未解锁层)
2. `潜行 最深层` - 传送到已解锁最深层
3. `潜行 挑战层` - 传送到最深+5层(高风险高回报)
4. `潜行 宝藏层` - 扫描1-100层，传送到宝藏最多层

**特殊机制:**
- **跳层惩罚:** 潜行到未解锁层，怪物等级+50%
- **挑战层:** 失败被传送回表世界，24小时不能再用
- **深渊征服者:** 首次击败挑战层永久+层级×10全属性
- **速通大师:** 连续5层<3回合击败，下次潜行免费

**实现要点:**
- 扩展`player.can_enter_dungeon_level()`允许VIP跳层
- 层级扫描查询: `SELECT region, COUNT(*) FROM world_tile WHERE event_type='TREASURE'`
- 挑战层失败记录在: `vip_equipment_data.challenge_failed_at`
- 速通连击记录在: `vip_equipment_data.speedrun_streak`

**适合场景:** 刷材料效率最大化，冲层数排行榜，高层诡域探索

---

### 方案四:【血誓·归乡之刃】- 生命锚点流

**核心定位:** 战略布局，团队协作，空间锚定

**基础属性:**
```yaml
item_id: "vip_blood_oath_blade"
name: "血誓·归乡之刃"
description: "以生命之血铭刻空间坐标，可召唤盟友或紧急撤退"
type: "EQUIPMENT"
rarity: "red"
durability: 380
required_level: 10
attr_bonus: {"hp": 140, "attack": 100, "defense": 70}
attr_ratio: {"hp": 1.1, "attack": 0.9, "defense": 0.8}
gem_slots: 5
```

**被动效果:**
```yaml
special_effects:
  - trigger: "passive"
    effect: "custom_life_anchor"
    description: "[1] 生命锚点：可设置3个锚点，其他玩家可看到标记"

  - trigger: "on_attacked"
    chance: 15
    effect: "custom_blood_pull"
    description: "[2] 血之牵引：被攻击时15%概率瞬移到最近锚点"

  - trigger: "low_hp"
    threshold: 20
    effect: "custom_home_guard"
    description: "[3] 归乡守护：生命≤20%自动传送到锚点+回50%血(每战1次)"

  - trigger: "on_death"
    effect: "custom_blood_rebirth"
    description: "[4] 血肉重生：死亡时在最近锚点复活60%血(每战1次)"

  - trigger: "on_kill"
    effect: "gain_hp"
    is_percentage: false
    value: 2
    description: "[5] 生命掠夺：击杀敌人后永久+2体质(每日20次，+40体质)"

  - trigger: "passive"
    effect: "custom_life_share"
    description: "[6] 生命共享：锚点10格内公会成员可消耗你10%血为其回30%血"
```

**专属主动技能: 血誓传送**
- **指令:** `血誓传送` 或 `锚点 [操作]`
- **冷却时间:** 传送30分钟，召唤6小时
- **生命消耗:** 10%-30%当前生命值
- **装备耐久:** 每次传送-3

**技能选项:**
1. `锚点 设置` - 在当前位置设置锚点(-20%生命)
2. `锚点 传送1/2/3` - 传送到指定锚点(-10%生命)
3. `锚点 召唤 UID` - 召唤玩家到锚点(双方各-30%生命，需同意)
4. `锚点 公会集结` - 召唤所有在线公会成员(-10000公会资金)
5. `锚点 删除 序号` - 删除锚点，返还设置时的生命值

**特殊机制:**
- **锚点持续:** 7天自动消失
- **锚点破坏:** 其他玩家可使用"破界符"破坏锚点
- **公会集结:** 需公会等级≥5，CD 24小时
- **战略价值:** 在BOSS点/市集/公会领地设置锚点

**实现要点:**
- 锚点存储在新表: `vip_life_anchors` (player_id, x, y, region, created_at)
- 锚点可见性: 在`world_tile`表添加`anchor_markers` JSON字段
- 召唤需要被召唤者确认: 使用`AskUserQuestion`工具
- 公会集结需检查公会等级和资金

**适合场景:** 公会战集结，世界BOSS抢夺，市集跑商，团队副本

---

### 方案五:【折光年】- 时间拨针流 ✅ 已定稿

**核心定位:** 时间系怀表，日常效率型，拨针操控游戏内各种日常CD/次数

**定价:** 1000元

**设计理念:** 怀表让你每天比别人多活一点。被动效果提供中等偏上的战斗力，主动技能聚焦日常实用性（重置签到、加速闭关、额外BOSS次数、额外委托），每个技能都是玩家每天真正会用的。

**基础属性:**
```yaml
item_id: "vip_chrono_watch"
name: "折光年"
description: "光会拐弯，时间也会。"
type: "EQUIPMENT"
rarity: "red"
durability: 360
required_level: 10
attr_bonus: {"attack": 100, "hp": 100, "agility": 100, "defense": 100}
attr_ratio: {"attack": 1.0, "hp": 1.0, "agility": 1.0, "defense": 1.0}
gem_slots: 5
repair_cost: 5
```

**属性对标(1000元档):**

| | 斩龙闪(600) | 归雨(1000) | 折光年(1000) |
|--|-----------|----------|------------|
| 固定总量 | 300 | 500 | 400 |
| 百分比总量 | 300% | 500% | 400% |
| 分布 | 攻/生/敏 | 攻/智/生 | 攻/生/敏/防(均衡) |
| 宝石槽 | 5 | 5 | 5 |

**装备效果(5个被动):**
```yaml
special_effects:
  - trigger: "first_turn"
    effect: "buff_combo"
    value: 20
    duration: 2
    description: "[1] 零时域：战斗开始时怀表指针倒转，你的出手永远快对方一拍——前2回合连击率+20%"

  - trigger: "on_hit"
    effect: "execute"
    is_percentage: true
    value: 20
    description: "[2] 终末审判：当敌人生命低于20%时，怀表指针归零——时间到了，无视任何效果直接终结"

  - trigger: "each_turn"
    chance: 100
    effect: "damage_reduction"
    value: 10
    duration: 999
    description: "[3] 缓释之壳：怀表周围的时间流速略慢，一切攻击都像穿过粘稠的空气——受到伤害减少10%"

  - trigger: "on_kill"
    effect: "gain_hp"
    is_percentage: false
    value: 2
    description: "[4] 时间掠夺：击杀敌人时夺取对方'剩余寿命'——永久+2体质(+6生命值；战后结算；每日最多20次，共+120生命值)"

  - trigger: "on_kill"
    effect: "gain_attack"
    is_percentage: false
    value: 2
    description: "[5] 终焉铭刻：每一次终结都被怀表铭刻为'注定之事'——永久+2攻击力(战后结算；每日最多20次，共+40攻击力)"
```

**被动效果对标:**

| # | 折光年 | 归雨 | 对标说明 |
|---|-------|------|---------|
| [1] | 前2回合连击+20% | 攻击25%概率无视30%防御 | 开场爆发，弱于归雨穿甲 |
| [2] | 20%血量斩杀 | 暴击吸血15% | 终结能力，斩龙闪为30% |
| [3] | 每回合减伤10% | 每回合减伤5%(伞下) | 差不多 |
| [4] | 击杀+2体质(每日20) | 击杀+2敏捷(每日20) | 成长机制对等 |
| [5] | 击杀+2攻击(每日20) | 无(归雨5个被动) | 多一个成长，补偿无穿甲/吸血 |

**专属主动技能: 拨针系统(日常效率)**

怀表操控的是"日常时间线"，每个技能都是玩家每天真正会用、实现成本极低的日常增益。

**技能选项:**

| 指令 | 效果 | 每日上限 | 耐久消耗 |
|------|------|---------|---------|
| 【拨针 签到】 | 重置签到，可再签一次 | 1次 | -3 |
| 【拨针 闭关】 | 闭关立即按上限时长结算出关 | 1次 | -5 |
| 【拨针 讨伐】 | 世界BOSS攻击次数+1 | 1次 | -5 |
| 【拨针 委托】 | 额外刷新一个每日委托 | 1次 | -3 |
| 【折光年】 | 查看怀表状态面板 | 无限 | 0 |

**1. 拨针·签到(重置签到)**
- **指令:** `拨针 签到`
- **效果:** 重置`last_sign`，允许当日再签一次(额外金币+咒抗+扫荡令)
- **限制:** 每日1次；不累加连续签到天数(streak不变)
- **实现:** `player.last_sign`设为昨天，下次签到正常走签到逻辑
- **系统提示:**
  ```
  ⏱️ 怀表指针逆转——今天重新开始了
  ✅ 签到已重置，可再次【签到】
  ⚠️ 不会额外增加连续签到天数
  💡 今日拨针·签到 (1/1)
  ```

**2. 拨针·闭关(时间加速)**
- **指令:** `拨针 闭关`
- **前提:** 玩家必须处于闭关状态(`is_secluded = True`)
- **效果:** 无论闭关了多久，直接按闭关时长上限结算经验并出关
- **限制:** 每日1次
- **实现:** 将`player.seclusion_start_time`往前拨`max_seclusion_time`秒，然后触发正常出关结算
- **关键代码逻辑:**
  ```python
  # 核心：把闭关开始时间往前拨到上限
  max_seclusion_time = benefits["seclusion_time_limit"]  # 月卡决定上限
  player.seclusion_start_time = datetime.now() - timedelta(seconds=max_seclusion_time)
  # 之后正常走出关逻辑，delta_time会被cap到max_seclusion_time
  ```
- **系统提示:**
  ```
  ⏱️ 怀表疯狂旋转——时间被压缩了
  ⏩ 闭关时间加速至上限
  ✅ 出关结算中...
  （接正常出关消息）
  ```

**3. 拨针·讨伐(BOSS额外次数)**
- **指令:** `拨针 讨伐`
- **效果:** 当日世界BOSS攻击次数+1(在当前基础上恢复1次)
- **限制:** 每日1次
- **实现:** `damage_record.attacks_today -= 1`(最低到0)
- **系统提示:**
  ```
  ⏱️ 怀表拨回了一场战斗的时间
  ✅ 世界BOSS攻击次数+1
  💡 今日拨针·讨伐 (1/1)
  ```

**4. 拨针·委托(额外委托)**
- **指令:** `拨针 委托`
- **效果:** 无视每日3个上限，额外生成1个新的每日委托
- **限制:** 每日1次
- **实现:** 调用`DailyTaskService.force_generate_new_task()`，跳过上限检查
- **系统提示:**
  ```
  ⏱️ 怀表齿轮转动——新的因果浮现
  ✅ 已刷新一个额外的每日委托
  💡 使用【委托】查看详情
  ```

**5. 折光年(状态面板)**
- **指令:** `折光年`
- **效果:** 展示怀表耐久、今日拨针使用情况、每日成长统计
- **系统提示:**
  ```
  ⏱️ 折光年
  ━━━━━━━━━━━━━
  🔋 耐久：352/360
  ━━━━━━━━━━━━━
  ⏳ 今日拨针：
    签到：✅ 可用 (0/1)
    闭关：❌ 已用 (1/1)
    讨伐：✅ 可用 (0/1)
    委托：✅ 可用 (0/1)
  ━━━━━━━━━━━━━
  📊 今日成长：
    时间掠夺：+8体质 (12/20)
    终焉铭刻：+6攻击 (17/20)
  ```

**数据存储(复用现有JSON字段):**
```python
# 全部存在 vip_equipment_data JSON字段，按日期自动重置
player.vip_equipment_data["chrono_dial"] = {
    "sign":      {"date": "2026-02-14", "used": 0},
    "seclusion": {"date": "2026-02-14", "used": 0},
    "boss":      {"date": "2026-02-14", "used": 0},
    "task":      {"date": "2026-02-14", "used": 0},
}
# date不是今天则视为已重置(used=0)
```

**实现复杂度评估:**

| 模块 | 复杂度 | 说明 |
|------|--------|------|
| YAML被动效果 | 极低 | 全部使用现有EffectType，纯配置 |
| 拨针·签到 | 极低 | 改`last_sign`，约3行核心代码 |
| 拨针·闭关 | 低 | 改`seclusion_start_time`后触发出关，约10行 |
| 拨针·讨伐 | 低 | 改`attacks_today`，需查询世界BOSS记录，约5行 |
| 拨针·委托 | 低 | 调用现有`force_generate_new_task()`，约5行 |
| 永劫面板 | 极低 | 纯展示格式化，约20行 |
| 总计 | **极低** | 一个文件约150行，不需要新表/新EffectType/定时任务 |

**适合场景:** 日常高效率玩家，每天签到/修炼/打BOSS/做委托全都用得上

---

## 4. 方案对比矩阵

| 装备 | 定价 | 核心技能 | 冷却 | 难度 | 适合玩家 | 实现复杂度 | 状态 |
|------|------|---------|-----|------|---------|-----------|------|
| 归雨 | 1000元 | 雨钉传送 | 5分钟 | ★★☆☆☆ | 灵活机动型 | 低 | ✅ 已实现 |
| 折光年 | 1000元 | 拨针系统 | 每日重置 | ★☆☆☆☆ | 日常效率型 | 极低 | 📋 已定稿 |
| 时空断层刀 | 1000元 | 时光倒流 | 6小时 | ★★★★★ | 高风险挑战型 | 高 | 💡 备选 |
| 深渊潜行者 | 1000元 | 深渊潜行 | 1小时 | ★★★★☆ | 效率速通型 | 中等 | 💡 备选 |
| 血誓·归乡之刃 | 1000元 | 血誓传送 | 30分钟 | ★★☆☆☆ | 团队协作型 | 中等 | 💡 备选 |

**三件已确定VIP装备对比:**

| 维度 | 斩龙闪(600) | 归雨(1000) | 折光年(1000) |
|------|-----------|----------|------------|
| 定位 | 纯战斗·斩杀 | 机动·闪避 | 全能·日常效率 |
| 属性总量 | 300/300% | 500/500% | 400/400% |
| 被动数量 | 6个(极强) | 5个(中强) | 5个(中等) |
| 主动技能 | 无 | 锚点传送(5子指令) | 拨针系统(4子指令) |
| 每日成长 | +120生命+40随机 | +40敏捷 | +120生命+40攻击 |
| 战斗强度 | S | A | B+ |
| 日常价值 | C | A(传送) | S(签到/闭关/BOSS/委托) |
| 实现复杂度 | 已实现 | 已实现 | 极低 |

**推荐优先级:**
1. **折光年** - 实现最简单，日常价值最高，所有技能复用现有系统
2. **归雨** - 机制简洁，携带同行功能独特，战斗技能常规稳定
3. **深渊潜行者** - 与诡域系统深度绑定，提升刷图效率
4. **血誓·归乡之刃** - 团队协作价值高，公会战核心装备
5. **时空断层刀** - 实现复杂度高，需谨慎处理状态回滚

---

## 5. 通用实现框架

### 5.1 数据库表扩展

**player表新增字段:**
```python
# plugins/xiuxian_game/models/player.py
class Player(Base):
    # VIP装备数据(JSON)
    vip_equipment_data: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        comment="VIP装备专属数据(坐标标记、快照等)"
    )

    # VIP技能冷却时间(JSON)
    vip_skill_cooldown: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        comment="VIP技能冷却时间戳"
    )
```

**新增锚点表(仅血誓装备需要):**
```python
# plugins/xiuxian_game/models/vip_life_anchor.py
class VIPLifeAnchor(Base):
    __tablename__ = "vip_life_anchors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True)
    anchor_name: Mapped[str] = mapped_column(String(50), default="锚点")
    x: Mapped[int] = mapped_column(Integer)
    y: Mapped[int] = mapped_column(Integer)
    region: Mapped[str] = mapped_column(String(50))
    dungeon_level: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)  # 7天后过期
```

### 5.2 通用技能框架代码

**插件入口:**
```python
# plugins/xiuxian_game/item/vip_equipment_skills.py
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

# 归雨 雨钉技能
gui_yu_anchor_cmd = on_command("锚点", block=True, priority=5)

@gui_yu_anchor_cmd.handle()
async def handle_gui_yu_anchor(event: MessageEvent, args: Message = CommandArg()):
    """处理归雨雨钉技能"""
    args_text = args.extract_plain_text().strip()

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await gui_yu_anchor_cmd.finish("⛔ 请先创建角色")

        # 1. 检查是否装备该装备
        if not await check_vip_equipment(session, player, "vip_gui_yu"):
            await gui_yu_anchor_cmd.finish("⛔ 需要装备【归雨】才能使用此技能")

        # 2. 解析指令
        if not args_text or args_text == "列表":
            # 显示锚点列表
            msg = format_anchor_list(player)
            await gui_yu_anchor_cmd.finish(msg)

        parts = args_text.split()
        operation = parts[0] if parts else ""

        if operation == "设置":
            # 设置锚点
            anchor_name = parts[1] if len(parts) > 1 else f"锚点{len(player.vip_equipment_data.get('rain_anchors', [])) + 1}"
            success, msg = await set_rain_anchor(session, player, anchor_name)

        elif operation == "传送":
            # 传送到锚点
            if len(parts) < 2:
                await gui_yu_anchor_cmd.finish("⛔ 请指定锚点，例如：锚点 传送 1")

            # 检查冷却时间
            if not check_skill_cooldown(player, "rain_anchor_teleport", hours=1):
                remain = get_cooldown_remain(player, "rain_anchor_teleport")
                await gui_yu_anchor_cmd.finish(f"⛔ 技能冷却中，剩余{remain}")

            # 检查理智值
            if player.mp < 15:
                await gui_yu_anchor_cmd.finish("⛔ 理智值不足15点")

            anchor_id = parts[1]
            success, msg = await teleport_to_anchor(session, player, anchor_id)

            if success:
                # 扣除消耗
                player.mp -= 15
                await deduct_equipment_durability(session, player, "vip_gui_yu", 3)
                set_skill_cooldown(player, "rain_anchor_teleport")
                await session.commit()

        elif operation == "携带":
            # 携带队友传送
            if len(parts) < 3:
                await gui_yu_anchor_cmd.finish("⛔ 请指定玩家和锚点，例如：锚点 携带 10001 1")

            # 检查冷却时间
            if not check_skill_cooldown(player, "rain_anchor_teleport", hours=1):
                remain = get_cooldown_remain(player, "rain_anchor_teleport")
                await gui_yu_anchor_cmd.finish(f"⛔ 技能冷却中，剩余{remain}")

            # 检查理智值
            if player.mp < 15:
                await gui_yu_anchor_cmd.finish("⛔ 理智值不足15点")

            target_uid = parts[1]
            anchor_id = parts[2]
            success, msg = await carry_teleport(session, player, target_uid, anchor_id, event)

            if success:
                # 扣除消耗
                player.mp -= 15
                await deduct_equipment_durability(session, player, "vip_gui_yu", 5)
                set_skill_cooldown(player, "rain_anchor_teleport")
                await session.commit()

        elif operation == "删除":
            # 删除锚点
            if len(parts) < 2:
                await gui_yu_anchor_cmd.finish("⛔ 请指定要删除的锚点，例如：锚点 删除 1")

            anchor_id = parts[1]
            success, msg = await delete_rain_anchor(session, player, anchor_id)

        else:
            await gui_yu_anchor_cmd.finish("⛔ 未知操作\n可用操作：设置、传送、携带、删除、列表")

        await gui_yu_anchor_cmd.finish(msg)
```

**通用检查函数:**
```python
# plugins/xiuxian_game/item/vip_skill_utils.py
from datetime import datetime, timedelta

async def check_vip_equipment(session, player, equipment_id: str) -> bool:
    """检查玩家是否装备指定VIP装备"""
    from .equipment_service import EquipmentService
    service = EquipmentService(session)
    equipped = await service.get_equipped_items(player.id)
    return any(e.item_id == equipment_id for e in equipped)

def check_skill_cooldown(player, skill_key: str, hours: int) -> bool:
    """检查技能是否冷却完成"""
    if not player.vip_skill_cooldown:
        return True

    last_use = player.vip_skill_cooldown.get(skill_key)
    if not last_use:
        return True

    cooldown_time = datetime.fromisoformat(last_use) + timedelta(hours=hours)
    return datetime.now() >= cooldown_time

def get_cooldown_remain(player, skill_key: str) -> str:
    """获取剩余冷却时间"""
    last_use = player.vip_skill_cooldown.get(skill_key)
    if not last_use:
        return "0秒"

    # 计算剩余时间并格式化
    remain = datetime.fromisoformat(last_use) + timedelta(hours=2) - datetime.now()
    hours = int(remain.total_seconds() // 3600)
    minutes = int((remain.total_seconds() % 3600) // 60)
    return f"{hours}小时{minutes}分钟"

def set_skill_cooldown(player, skill_key: str):
    """设置技能冷却"""
    if not player.vip_skill_cooldown:
        player.vip_skill_cooldown = {}
    player.vip_skill_cooldown[skill_key] = datetime.now().isoformat()

async def deduct_equipment_durability(session, player, equipment_id: str, amount: int):
    """扣除装备耐久度"""
    from .equipment_service import EquipmentService
    service = EquipmentService(session)
    equipment = await service.get_equipped_item_by_id(player.id, equipment_id)
    if equipment:
        equipment.durability = max(0, equipment.durability - amount)
```

### 5.3 技能效果实现示例

**锚点设置功能:**
```python
async def set_rain_anchor(session, player, anchor_name: str):
    """设置雨钉锚点"""
    if not player.vip_equipment_data:
        player.vip_equipment_data = {}

    anchors = player.vip_equipment_data.get("rain_anchors", [])

    # 检查锚点数量上限
    if len(anchors) >= 3:
        return False, "⛔ 锚点数量已达上限(3个)，请先删除旧锚点"

    # 获取当前坐标
    current_x, current_y = player.get_current_coordinates()
    current_region = player.get_current_region()
    dungeon_level = player.dungeon_level if player.is_in_dungeon() else 0

    # 创建新锚点
    new_anchor = {
        "id": len(anchors) + 1,
        "name": anchor_name,
        "x": current_x,
        "y": current_y,
        "region": current_region,
        "dungeon_level": dungeon_level,
        "created_at": datetime.now().isoformat()
    }

    anchors.append(new_anchor)
    player.vip_equipment_data["rain_anchors"] = anchors

    location_str = f"{current_region}({current_x}, {current_y})"
    return True, f"✨ 锚点设置成功！\n📍 [{new_anchor['id']}] {anchor_name} - {location_str}"


def format_anchor_list(player) -> str:
    """格式化锚点列表"""
    anchors = player.vip_equipment_data.get("rain_anchors", [])

    if not anchors:
        return "⛔ 未设置任何锚点\n💡 使用【锚点 设置 名称】在当前位置设置锚点"

    lines = ["📍 鬼域雨钉列表", "━━━━━━━━━━━━━"]
    for anchor in anchors:
        location = f"{anchor['region']}({anchor['x']}, {anchor['y']})"
        lines.append(f"[{anchor['id']}] {anchor['name']} - {location}")

    lines.extend([
        "━━━━━━━━━━━━━",
        "💡 使用【锚点 传送 1】传送到锚点",
        "💡 使用【锚点 携带 UID 1】携带队友传送",
        "💡 使用【锚点 删除 1】删除锚点"
    ])

    return "\n".join(lines)


async def teleport_to_anchor(session, player, anchor_id: str):
    """传送到锚点"""
    anchors = player.vip_equipment_data.get("rain_anchors", [])
    if not anchors:
        return False, "⛔ 未设置任何锚点"

    # 查找锚点(支持序号或名称)
    anchor = None
    try:
        # 尝试按序号查找
        idx = int(anchor_id) - 1
        if 0 <= idx < len(anchors):
            anchor = anchors[idx]
    except ValueError:
        # 按名称查找
        for a in anchors:
            if a["name"] == anchor_id:
                anchor = a
                break

    if not anchor:
        return False, f"⛔ 未找到锚点: {anchor_id}"

    # 执行传送
    if anchor["dungeon_level"] > 0:
        # 传送到诡域
        player.enter_dungeon(anchor["dungeon_level"])
        player.dungeon_x = anchor["x"]
        player.dungeon_y = anchor["y"]
        player.x = anchor["x"]
        player.y = anchor["y"]
    else:
        # 传送到现实世界
        if player.is_in_dungeon():
            player.exit_dungeon()
        player.real_world_x = anchor["x"]
        player.real_world_y = anchor["y"]
        player.x = anchor["x"]
        player.y = anchor["y"]

    location = f"{anchor['region']}({anchor['x']}, {anchor['y']})"
    return True, f"✨ 踏入伞影传送成功！\n📍 传送到 [{anchor['id']}] {anchor['name']} - {location}"


async def carry_teleport(session, player, target_uid: str, anchor_id: str, event):
    """携带队友传送"""
    from ..platform_utils import get_unified_player

    # 1. 查找目标玩家
    target = await session.execute(
        select(Player).where(Player.id == target_uid)
    )
    target_player = target.scalar_one_or_none()

    if not target_player:
        return False, f"⛔ 未找到玩家: {target_uid}"

    # 2. 检查是否在附近
    px, py = player.get_current_coordinates()
    tx, ty = target_player.get_current_coordinates()
    distance = max(abs(px - tx), abs(py - ty))

    if distance > 5:
        return False, f"⛔ 目标玩家距离过远(>{distance}格)，需在±5格范围内"

    # 3. 检查目标理智值
    if target_player.mp < 15:
        return False, f"⛔ 目标玩家理智值不足15点"

    # 4. 发送确认请求(简化版，实际需要通过消息系统)
    # TODO: 实现消息确认机制或使用AskUserQuestion
    # 这里假设已确认

    # 5. 查找锚点
    anchors = player.vip_equipment_data.get("rain_anchors", [])
    anchor = None
    try:
        idx = int(anchor_id) - 1
        if 0 <= idx < len(anchors):
            anchor = anchors[idx]
    except ValueError:
        for a in anchors:
            if a["name"] == anchor_id:
                anchor = a
                break

    if not anchor:
        return False, f"⛔ 未找到锚点: {anchor_id}"

    # 6. 执行双人传送
    for p in [player, target_player]:
        if anchor["dungeon_level"] > 0:
            p.enter_dungeon(anchor["dungeon_level"])
            p.dungeon_x = anchor["x"]
            p.dungeon_y = anchor["y"]
        else:
            if p.is_in_dungeon():
                p.exit_dungeon()
            p.real_world_x = anchor["x"]
            p.real_world_y = anchor["y"]
        p.x = anchor["x"]
        p.y = anchor["y"]

    # 7. 扣除目标玩家理智
    target_player.mp -= 15

    location = f"{anchor['region']}({anchor['x']}, {anchor['y']})"
    return True, (
        f"✨ 携带传送成功！\n"
        f"📍 你和 {target_player.nickname} 传送到\n"
        f"[{anchor['id']}] {anchor['name']} - {location}"
    )


async def delete_rain_anchor(session, player, anchor_id: str):
    """删除锚点"""
    anchors = player.vip_equipment_data.get("rain_anchors", [])
    if not anchors:
        return False, "⛔ 未设置任何锚点"

    # 查找并删除锚点
    anchor = None
    try:
        idx = int(anchor_id) - 1
        if 0 <= idx < len(anchors):
            anchor = anchors.pop(idx)
    except ValueError:
        for i, a in enumerate(anchors):
            if a["name"] == anchor_id:
                anchor = anchors.pop(i)
                break

    if not anchor:
        return False, f"⛔ 未找到锚点: {anchor_id}"

    # 重新编号
    for i, a in enumerate(anchors):
        a["id"] = i + 1

    player.vip_equipment_data["rain_anchors"] = anchors

    return True, f"✅ 已删除锚点: [{anchor['id']}] {anchor['name']}"
```

---

## 6. 定制流程建议

### 6.1 需求收集
1. 询问定制者的游戏风格(进攻/防守/辅助/探索)
2. 了解主要玩法场景(PvP/PvE/公会战/刷材料)
3. 确定预算(600元/1000元/更高)
4. 是否需要专属主动技能

### 6.2 方案设计
1. 从本文档选择合适的模板
2. 根据需求调整属性加成和被动效果
3. 设计或修改主动技能机制
4. 计算平衡性(对比同价位装备)

### 6.3 技术实现
1. 编写YAML配置(items.yaml)
2. 实现专属效果类型(battle_effects.py)
3. 实现主动技能指令(vip_equipment_skills.py)
4. 数据库迁移(auto_migrate.py)
5. 更新帮助信息(player/help.py)

### 6.4 测试验证
1. 功能测试(技能是否正常触发)
2. 平衡性测试(是否过强/过弱)
3. 边界测试(极端情况处理)
4. 性能测试(是否影响服务器性能)

### 6.5 交付上线
1. 与定制者确认最终方案
2. 部署到正式服务器
3. 在游戏内展示(【我的装备】可看到)
4. 记录到装备档案

---

## 7. 扩展方向

### 7.1 套装系统
- 同一定制者可购买2-4件套装
- 2件套/4件套激活额外效果
- 例如: 归雨套装(归雨+雨夜披风)
  - 2件套: 雨钉冷却-50%
  - 4件套: 传送免费，但强制进入"暴雨形态"(全属性+50%，持续5分钟)

### 7.2 装备进化
- 装备使用达到一定次数后可"觉醒"
- 觉醒后解锁第7个被动效果或技能强化
- 例如: 归雨觉醒→归雨·无声
  - 新增效果: 传送时可携带1名队友

### 7.3 装备共鸣
- 多个VIP装备同时装备时触发"共鸣效果"
- 例如: 归雨+时空断层刀
  - 共鸣: 雨中时停(传送时自动保存快照，失败自动倒流)

### 7.4 专属试炼
- VIP装备绑定专属试炼副本
- 通关后装备属性永久提升
- 例如: 归雨试炼-穿越100层诡域
  - 奖励: 归雨所有属性+20%

---

## 8. 参考资料

- **战斗系统:** `/llmdoc/overview/combat-system-overview.md`
- **效果系统:** `/llmdoc/architecture/effect-system-architecture.md`
- **添加战斗效果:** `/llmdoc/guides/how-to-add-battle-effect.md`
- **玩家坐标系统:** `plugins/xiuxian_game/models/player.py:89-183`
- **诡域传送系统:** `plugins/xiuxian_game/world/teleport.py`
- **装备服务:** `plugins/xiuxian_game/item/equipment_service.py`
- **现有VIP装备:** `plugins/xiuxian_game/data/items.yaml:1185-1253` (斩龙闪、镜怨披风)

---

**版本:** 1.1
**创建时间:** 2026-02-12
**维护者:** 项目策划组
**最后更新:** 2026-02-14
**更新记录:** v1.1 新增方案五【折光年】(已定稿，1000元档，时间拨针流)，更新方案对比矩阵
