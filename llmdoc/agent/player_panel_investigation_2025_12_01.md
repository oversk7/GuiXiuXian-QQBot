# 玩家面板实现深入调查报告

**报告日期**: 2025-12-01
**调查者**: scout (LLM代理)
**报告类型**: 代码架构调研

---

## 1. Code Sections (The Evidence)

### 玩家面板命令实现
- `plugins/xiuxian_game/player/info.py:44` (`profile` 命令): 主面板命令，别名包含"面板"、"状态"，支持查看指定UID玩家
- `plugins/xiuxian_game/player/battle_info.py:17` (`battle_info` 命令): 战力/属性命令，别名包含"属性"、"我的战力"
- `plugins/xiuxian_game/player/info.py:51-174` (profile.handle()): 面板渲染的完整实现，包含属性显示、装备加成统计、公会信息、坐标系统

### Player 模型定义
- `plugins/xiuxian_game/models/player.py:12-198` (Player 类): 完整的玩家模型，87个字段
- `plugins/xiuxian_game/models/player.py:218-246` (get_effective_attributes): 获取有效属性的方法

### 属性计算系统
- `plugins/xiuxian_game/domain/attributes/attribute_calculator.py:13-100` (AttributeCalculator): 统一属性计算器，组合多个属性来源
- `plugins/xiuxian_game/domain/attributes/player_attributes_integration.py` (get_effective_attributes_v2): 集成的属性计算入口
- `plugins/xiuxian_game/player/info.py:100` (get_effective_attributes_v2调用): 面板使用的属性计算接口

### 临时buff系统
- `plugins/xiuxian_game/models/temporary_buff.py:14-98` (TemporaryBuff 类): 临时buff模型，JSON存储属性加成

### 装备系统
- `plugins/xiuxian_game/models/inventory.py:1-80` (ItemInstance 模型起始): 物品实例模型，含装备加成机制
- `plugins/xiuxian_game/player/info.py:104-114` (装备加成统计): 面板从equipped装备中统计 _persist_bonus 加成

### 关联表系统
- `plugins/xiuxian_game/models/guild.py:16-78` (Guild、GuildMember、GuildBuilding): 公会三表结构
- `plugins/xiuxian_game/models/marriage.py:7-28` (Marriage): 婚姻关系表
- `plugins/xiuxian_game/models/inventory.py` (ItemInstance): 背包/装备表，关联到Player

---

## 2. Report (The Answers)

### 玩家面板显示的命令实现

#### 主要命令
| 命令名 | 别名 | 文件位置 | 功能描述 |
|--------|------|--------|--------|
| 角色 | 面板、状态 | info.py:44 | 显示玩家基础信息、战斗属性、经济数据、坐标位置 |
| 战力 | 属性、我的战力 | battle_info.py:17 | 显示详细的战斗属性（暴击率、连击率、闪避率等） |

#### 面板命令的完整流程 (info.py:51-174)

1. **命令解析** (line 52-60): 解析参数获取目标UID（可选）
2. **玩家获取** (line 63-79): 通过UnitOfWork获取玩家对象，支持跨平台账号切换
3. **坐标更新** (line 81-97): 若玩家在自动导航中，更新坐标位置（兼容双层坐标系）
4. **属性计算** (line 100): 调用 `get_effective_attributes_v2()` 获取最终属性（包含所有加成）
5. **装备加成统计** (line 102-114): 遍历已穿戴装备，从 `extra_attrs["_persist_bonus"]` 提取加成值
6. **公会信息** (line 116-121): 查询Guild表获取公会名称
7. **消息渲染** (line 153-171): 格式化为结构化文本消息，包含六个分区

#### 面板显示的所有字段

| 分区 | 字段 | 数据来源 | 显示格式 |
|------|------|--------|--------|
| **信息** | 昵称 | Player.nickname | {nickname}[UID:{uid}] |
| | 性别 | Player.sex | {sex} |
| | 等级 | Player.level + reincarnation_level | Lv.{level} · {realm_name} |
| | 经验 | Player.exp / max_exp | Exp {exp}/{exp_max} |
| **状态** | 生命值 | min(Player.hp, effective_max_hp) / effective_max_hp | ❤️生命 {hp}/{max_hp} |
| | 理智值 | min(Player.mp, effective_max_mp) / effective_max_mp | 🧠理智 {mp}/{max_mp} |
| | 攻击力 | get_effective_attributes_v2["attack"] + 装备加成 | ⚔力 {attack} (+{equipment_bonus}) |
| | 防御力 | get_effective_attributes_v2["defense"] + 装备加成 | 🛡防 {defense} (+{equipment_bonus}) |
| | 敏捷 | get_effective_attributes_v2["agility"] + 装备加成 | 👟敏 {agility} (+{equipment_bonus}) |
| | 运气 | get_effective_attributes_v2["luck"] + 装备加成 | 🍀运 {luck} (+{equipment_bonus}) |
| | 咒抗 | Player.stamina | 🔮咒抗 {stamina} |
| **其他** | 金币 | Player.gold | 🪙金币 {gold} |
| | 怨念/点数 | Player.resentment / attribute_points | 💀怨念 {resentment} ✨点数 {points} |
| | 公会 | Guild.name 或 "无所属" | ☯公会 {guild_name} |
| | 位置 | Player坐标系统 | 📍位置 {region} ({x},{y}) |

**坐标系统说明**:
- 在诡域: 显示 "Nlevel层诡域 (dungeon_x,dungeon_y) \| 现实 (real_world_x,real_world_y)"
- 在现实: 显示 "大都会 (real_world_x,real_world_y)"

#### 战力命令的显示内容 (battle_info.py:20-67)

| 属性 | 字段名 | 来源 |
|------|--------|------|
| 血量 | hp/max_hp | effective_attrs + Player.hp |
| 理智 | mp/max_mp | effective_attrs + Player.mp |
| 攻击 | attack | effective_attrs |
| 防御 | defense | effective_attrs |
| 敏捷 | agility | effective_attrs |
| 运气 | luck | effective_attrs |
| **扩展属性** | (来自BattleIntegrationHelper) | - |
| **临时buff** | 激活buff数量 | TemporaryBuff.get_active_buffs() |

---

## 3. Player 模型完整字段清单

### Player 表 (player_py: 87 个字段)

#### 基础信息 (6个字段)
| 字段名 | 数据类型 | 默认值 | 说明 | 可为空 |
|--------|---------|--------|------|--------|
| id | String(32) | - | 平台ID（主键） | ❌ |
| uid | Integer | auto-increment | 自增UID（唯一） | ❌ |
| nickname | String(24) | - | 昵称 | ❌ |
| level | Integer | 1 | 等级 | ❌ |
| sex | Gender(String(8)) | 男 | 性别（男/女） | ❌ |
| created_at | DateTime | func.now() | 创建时间 | ❌ |

#### 经验和属性点 (3个字段)
| 字段名 | 数据类型 | 默认值 | 说明 | 可为空 |
|--------|---------|--------|------|--------|
| exp | Integer | 0 | 当前经验值 | ❌ |
| attribute_points | Integer | 0 | 可分配的属性点 | ❌ |
| reincarnation_level | Integer | 0 | 转数（冥返次数） | ❌ |
| breakthrough_fail_count | Integer | 0 | 当前连续突破失败次数 | ❌ |

#### 基础属性 (5个字段)
| 字段名 | 数据类型 | 默认值 | 说明 | 可为空 |
|--------|---------|--------|------|--------|
| attack | Integer | 1 | 攻击力 | ❌ |
| defense | Integer | 5 | 防御力 | ❌ |
| agility | Integer | 5 | 敏捷度 | ❌ |
| luck | Integer | 1 | 运气值 | ❌ |
| stamina | Integer | 10 | 咒抗（精神抗性） | ❌ |

#### HP/MP 系统 (4个字段)
| 字段名 | 数据类型 | 默认值 | 说明 | 可为空 |
|--------|---------|--------|------|--------|
| hp | Integer | 20 | 当前生命值 | ❌ |
| max_hp | Integer | 20 | 最大生命值 | ❌ |
| mp | Integer | 20 | 当前理智值 | ❌ |
| max_mp | Integer | 20 | 最大理智值 | ❌ |

#### 扩展战斗属性 (16个字段)
| 字段名 | 数据类型 | 默认值 | 说明 | 可为空 |
|--------|---------|--------|------|--------|
| critical_rate | Integer | 5 | 暴击率（百分比） | ❌ |
| critical_power | Integer | 0 | 暴击力（每点增加0.1倍伤害） | ❌ |
| combo_rate | Integer | 0 | 连击率（百分比） | ❌ |
| counter_rate | Integer | 0 | 反击率/反弹率（百分比） | ❌ |
| dodge_rate | Integer | 0 | 闪避率（百分比） | ❌ |
| accuracy_rate | Integer | 80 | 命中率（百分比） | ❌ |
| skill_crit_rate | Integer | 0 | 灵爆率（技能暴击率，百分比） | ❌ |
| penetration_rate | Integer | 0 | 穿透率（无视防御，百分比） | ❌ |
| anti_crit_rate | Integer | 0 | 抗暴率（降低敌方暴击，百分比） | ❌ |
| lifesteal_rate | Integer | 0 | 吸血率（百分比） | ❌ |
| immobilize_rate | Integer | 0 | 定身率（百分比） | ❌ |
| true_damage_rate | Integer | 0 | 真伤率（百分比） | ❌ |
| regen_rate | Integer | 0 | 回血率（百分比） | ❌ |

#### 战斗统计 (3个字段)
| 字段名 | 数据类型 | 默认值 | 说明 | 可为空 |
|--------|---------|--------|------|--------|
| total_battles | Integer | 0 | 总战斗次数 | ❌ |
| total_wins | Integer | 0 | 总胜利次数 | ❌ |
| total_damage_dealt | Integer | 0 | 总造成伤害 | ❌ |
| resentment | Integer | 0 | 怨念值 | ❌ |

#### 经济系统 (3个字段)
| 字段名 | 数据类型 | 默认值 | 说明 | 可为空 |
|--------|---------|--------|------|--------|
| gold | BigInteger | 1000 | 金币（主要货币） | ❌ |
| gold2 | BigInteger | 0 | 积分（副货币） | ❌ |
| mini_game_score | Integer | 0 | 小游戏积分 | ❌ |

#### 签到系统 (3个字段)
| 字段名 | 数据类型 | 默认值 | 说明 | 可为空 |
|--------|---------|--------|------|--------|
| last_sign | DateTime | NULL | 上次签到日期 | ✅ |
| sign_streak | Integer | 0 | 连续签到天数 | ❌ |
| last_cultivation | DateTime | NULL | 上次修炼时间 | ✅ |

#### 世界坐标系统 - 现实世界 (3个字段)
| 字段名 | 数据类型 | 默认值 | 说明 | 可为空 |
|--------|---------|--------|------|--------|
| region | String(32) | "大都会" | 区域名称 | ❌ |
| x | Integer | 0 | 兼容字段：当前X坐标 | ❌ |
| y | Integer | 0 | 兼容字段：当前Y坐标 | ❌ |

#### 双层坐标系统 - 现实世界 (2个字段)
| 字段名 | 数据类型 | 默认值 | 说明 | 可为空 |
|--------|---------|--------|------|--------|
| real_world_x | Integer | 0 | 现实世界X坐标 | ❌ |
| real_world_y | Integer | 0 | 现实世界Y坐标 | ❌ |

#### 双层坐标系统 - 诡域 (5个字段)
| 字段名 | 数据类型 | 默认值 | 说明 | 可为空 |
|--------|---------|--------|------|--------|
| dungeon_level | Integer | 0 | 当前诡域层级（0=现实世界） | ❌ |
| dungeon_x | Integer | 0 | 诡域内小坐标X（-5到5） | ❌ |
| dungeon_y | Integer | 0 | 诡域内小坐标Y（-5到5） | ❌ |
| max_dungeon_level | Integer | 0 | 到达过的最高诡域层级 | ❌ |

#### 公会系统 (2个字段)
| 字段名 | 数据类型 | 默认值 | 说明 | 可为空 |
|--------|---------|--------|------|--------|
| guild_id | Integer | NULL | 所属公会ID（外键） | ✅ |
| guild_contribution | BigInteger | 0 | 公会贡献值 | ❌ |

#### 阴宅系统 (5个字段)
| 字段名 | 数据类型 | 默认值 | 说明 | 可为空 |
|--------|---------|--------|------|--------|
| mansion_level | Integer | 0 | 阴宅等级（0表示未拥有） | ❌ |
| mansion_x | Integer | NULL | 阴宅X坐标 | ✅ |
| mansion_y | Integer | NULL | 阴宅Y坐标 | ✅ |
| mansion_usage_fee | Integer | 0 | 阴宅使用费用（单位：金币） | ❌ |
| mansion_allow_others | Boolean | True | 是否允许其他玩家使用阴宅 | ❌ |
| mansion_willing_to_pay | Boolean | True | 是否愿意支付费用使用他人阴宅 | ❌ |

#### 背包系统 (1个字段)
| 字段名 | 数据类型 | 默认值 | 说明 | 可为空 |
|--------|---------|--------|------|--------|
| inventory_capacity | Integer | 50 | 背包容量（基础值，可通过月卡增加） | ❌ |

#### VIP 系统 (1个字段)
| 字段名 | 数据类型 | 默认值 | 说明 | 可为空 |
|--------|---------|--------|------|--------|
| vip | Integer | 0 | VIP等级 | ❌ |

#### 闭关系统 (2个字段)
| 字段名 | 数据类型 | 默认值 | 说明 | 可为空 |
|--------|---------|--------|------|--------|
| is_secluded | Boolean | False | 是否在闭关状态 | ❌ |
| seclusion_start_time | DateTime | NULL | 闭关开始时间 | ✅ |

#### 留言板系统 (2个字段)
| 字段名 | 数据类型 | 默认值 | 说明 | 可为空 |
|--------|---------|--------|------|--------|
| last_message_board_check | DateTime | NULL | 最后查看世界留言时间 | ✅ |
| last_private_message_check | DateTime | NULL | 最后查看私信时间 | ✅ |

#### 关系字段 (1个字段)
| 字段名 | 数据类型 | 默认值 | 说明 | 可为空 |
|--------|---------|--------|------|--------|
| monthly_cards | Relationship | - | 与MonthlyCard的一对多关系 | - |

---

## 4. Player 关联表清单

### 直接关联表 (Player作为父表)

#### 1. ItemInstance (背包/装备表)
**文件**: `plugins/xiuxian_game/models/inventory.py`
**关联类型**: 一对多
**外键**: player_id → Player.id
**关键字段**:
- `player_id`: 玩家ID (String, 外键)
- `item_id`: 物品ID (String)
- `quantity`: 堆叠数量 (Integer)
- `equipped`: 是否已穿戴 (Boolean)
- `equipped_slot`: 穿戴位置 (String)
- `upgrade_level`: 升阶等级 (Integer)
- `durability`: 当前耐久 (Integer)
- `max_durability`: 最大耐久 (Integer)
- `gem_slots_data`: 镶嵌孔位信息 (JSON)
- `extra_attrs`: 额外属性JSON (JSON) - **包含_persist_bonus加成**

**关系说明**: 一个玩家拥有多个物品实例，物品可以是消耗品、材料、装备等

---

#### 2. MonthlyCard (月卡表)
**文件**: `plugins/xiuxian_game/models/monthly_card.py`
**关联类型**: 一对多
**外键**: player_id → Player.id
**关键字段**:
- `player_id`: 玩家ID
- `card_type`: 月卡类型
- `purchased_at`: 购买时间
- `expires_at`: 过期时间

**关系说明**: 一个玩家可以购买多个月卡，每个月卡提供不同的加成（背包容量、经验倍率等）

---

### 间接关联表 (通过guild_id)

#### 3. Guild (公会表)
**文件**: `plugins/xiuxian_game/models/guild.py`
**关联类型**: 多对一
**外键**: guild_id → Guild.id
**关键字段**:
- `id`: 公会ID
- `name`: 公会名称
- `president_id`: 会长ID
- `level`: 公会等级
- `treasury`: 公会资金库
- `notice`: 公会公告
- `base_x`, `base_y`: 公会基地坐标
- `territory_range`: 势力范围

**关系说明**: 一个玩家属于最多一个公会

---

#### 4. GuildMember (公会成员表)
**文件**: `plugins/xiuxian_game/models/guild.py`
**关联类型**: 间接（通过Guild）
**关键字段**:
- `guild_id`: 公会ID (外键到Guild)
- `player_id`: 玩家ID
- `position`: 职位 (PRESIDENT/VICE_PRESIDENT/CORE_MEMBER/MEMBER)
- `joined_at`: 加入时间

**关系说明**: 记录玩家在公会中的职位和加入信息，一对一关系

---

#### 5. GuildBuilding (公会建筑表)
**文件**: `plugins/xiuxian_game/models/guild.py`
**关联类型**: 间接（通过Guild）
**关键字段**:
- `guild_id`: 公会ID (外键到Guild)
- `building_type`: 建筑类型 (EXPERIENCE_SHRINE/TREASURY_VAULT/等)
- `level`: 建筑等级

**关系说明**: 公会的建筑为全成员提供加成

---

### 社交关联表

#### 6. Marriage (婚姻表)
**文件**: `plugins/xiuxian_game/models/marriage.py`
**关联类型**: 多对多（通过player1_id/player2_id）
**关键字段**:
- `player1_id`: 玩家1 ID (String(32), 索引)
- `player2_id`: 玩家2 ID (String(32), 索引)
- `married_at`: 结婚时间
- `total_gift_value`: 双方互送礼物总价值

**关系说明**: 一个玩家最多与一个其他玩家有婚姻关系；支持查询某玩家的配偶

---

#### 7. Mentorship (师徒表)
**文件**: `plugins/xiuxian_game/models/mentorship.py`
**关联类型**: 一对多 (作为师父或徒弟)
**关键字段**:
- `master_id`: 师父ID
- `apprentice_id`: 徒弟ID
- `status`: 状态 (PENDING/ACTIVE/EXPIRED)
- `created_at`: 创建时间
- `expires_at`: 过期时间

**关系说明**: 一个玩家可有多个徒弟或多个师父（需检查实际约束）

---

### 交易/记录表 (单向关联)

#### 8. TemporaryBuff (临时Buff表)
**文件**: `plugins/xiuxian_game/models/temporary_buff.py`
**关联类型**: 一对多
**外键**: player_id → Player.id
**关键字段**:
- `player_id`: 玩家ID (String(32), 索引)
- `buff_id`: Buff唯一ID
- `buff_name`: Buff名称
- `attribute_bonuses`: 属性加成 (JSON) - **直接影响面板显示**
- `expires_at`: 过期时间
- `is_active`: 是否激活

**关系说明**: 玩家当前激活的临时buff，通过get_effective_attributes_v2计入最终属性

---

#### 9. WorldMessage (世界留言板表)
**文件**: `plugins/xiuxian_game/models/world_message.py`
**关联类型**: 一对多
**外键**: player_id → Player.id (可能有多个字段)
**说明**: 玩家发布的世界留言，与last_message_board_check字段配合

---

#### 10. DailyTask (每日任务表)
**文件**: `plugins/xiuxian_game/models/daily_task.py`
**关联类型**: 一对多
**说明**: 玩家的每日任务完成状态

---

#### 11. PVPLog (PVP对战记录表)
**文件**: `plugins/xiuxian_game/models/pvp_log.py`
**关联类型**: 一对多
**关键字段**: 作为attacker_id或defender_id
**说明**: 记录玩家的PVP战斗历史

---

#### 12. TradeRecord (交易记录表)
**文件**: `plugins/xiuxian_game/models/trade_record.py`
**关联类型**: 一对多
**说明**: 玩家与玩家之间的交易记录

---

#### 13. GiftRecord (礼物记录表)
**文件**: `plugins/xiuxian_game/models/gift_record.py`
**关联类型**: 一对多
**说明**: 玩家发送/接收的礼物记录

---

#### 14. NavigationTask (自动导航任务表)
**文件**: `plugins/xiuxian_game/models/navigation_task.py`
**关联类型**: 一对一
**外键**: player_id → Player.id (主键，唯一)
**关键字段**:
- `player_id`: 玩家ID (主键)
- `target_x`, `target_y`: 目标坐标
- `created_at`: 创建时间

**关系说明**: 玩家最多有一个活跃的导航任务；面板显示时会更新坐标

---

#### 15. BankAccount (银行账户表)
**文件**: `plugins/xiuxian_game/models/bank_account.py`
**关联类型**: 一对一
**说明**: 玩家的银行账户信息（存款、利息等）

---

#### 16. Stock (股票持仓表)
**文件**: `plugins/xiuxian_game/models/stock.py`
**关联类型**: 一对多
**说明**: 玩家持有的股票和历史数据

---

#### 17. MarketOrder (市场订单表)
**文件**: `plugins/xiuxian_game/models/market_order.py`
**关联类型**: 一对多
**说明**: 玩家发布的交易订单（卖出/买入）

---

#### 18. PartTimeJob (打工表)
**文件**: `plugins/xiuxian_game/models/part_time_job.py`
**关联类型**: 一对多
**说明**: 玩家的打工记录和当前打工状态

---

#### 19. VIPEquipmentBonus (VIP装备永久加成表)
**文件**: `plugins/xiuxian_game/models/vip_equipment_bonus.py`
**关联类型**: 一对多
**说明**: 玩家通过VIP获得的装备永久加成

---

#### 20. ElixirUsageLog (丹药使用记录表)
**文件**: `plugins/xiuxian_game/models/elixir_usage.py`
**关联类型**: 一对多
**说明**: 玩家的丹药使用历史和每日限制追踪

---

### 关联表统计

| 关联类型 | 表名 | 说明 |
|---------|------|------|
| 一对多 | ItemInstance | 背包/装备，直接显示在面板中 |
| 一对多 | MonthlyCard | 月卡，影响背包容量 |
| 多对一 | Guild | 公会，显示在面板中 |
| 间接一对多 | GuildMember | 公会成员职位 |
| 间接一对多 | GuildBuilding | 公会建筑 |
| 多对多 | Marriage | 婚姻关系 |
| 一对多 | Mentorship | 师徒关系 |
| **一对多** | **TemporaryBuff** | **临时buff，直接计入属性** |
| 一对多 | WorldMessage | 世界留言 |
| 一对多 | DailyTask | 每日任务 |
| 一对多 | PVPLog | PVP记录 |
| 一对多 | TradeRecord | 交易记录 |
| 一对多 | GiftRecord | 礼物记录 |
| 一对一 | NavigationTask | 自动导航，影响面板坐标显示 |
| 一对一 | BankAccount | 银行账户 |
| 一对多 | Stock | 股票持仓 |
| 一对多 | MarketOrder | 市场订单 |
| 一对多 | PartTimeJob | 打工记录 |
| 一对多 | VIPEquipmentBonus | VIP装备加成 |
| 一对多 | ElixirUsageLog | 丹药使用记录 |

**面板直接相关的关联**: ItemInstance、TemporaryBuff、Guild、NavigationTask

---

## 5. 面板显示的字段映射关系

### 属性计算链路

```
玩家基础属性 (Player字段)
    ↓
装备加成 (ItemInstance._persist_bonus)
    ↓
临时buff加成 (TemporaryBuff.attribute_bonuses)
    ↓
get_effective_attributes_v2() → 最终属性
    ↓
面板显示
```

### 面板显示的属性来源追踪

| 面板字段 | Player字段 | 装备加成来源 | Buff加成来源 | 计算方式 |
|---------|-----------|----------|----------|--------|
| 生命值 (HP) | Player.hp | - | - | min(Player.hp, effective_max_hp) |
| 最大生命 (MAX_HP) | Player.max_hp | ItemInstance._persist_bonus["max_hp"] | TemporaryBuff.attribute_bonuses["max_hp"] | get_effective_attributes_v2()["max_hp"] |
| 理智值 (MP) | Player.mp | - | - | min(Player.mp, effective_max_mp) |
| 最大理智 (MAX_MP) | Player.max_mp | ItemInstance._persist_bonus["max_mp"] | TemporaryBuff.attribute_bonuses["max_mp"] | get_effective_attributes_v2()["max_mp"] |
| 攻击力 | Player.attack | ItemInstance._persist_bonus["attack"] | TemporaryBuff.attribute_bonuses["attack"] | 基础+装备(已持久化)+临时buff |
| 防御力 | Player.defense | ItemInstance._persist_bonus["defense"] | TemporaryBuff.attribute_bonuses["defense"] | 基础+装备(已持久化)+临时buff |
| 敏捷 | Player.agility | ItemInstance._persist_bonus["agility"] | TemporaryBuff.attribute_bonuses["agility"] | 基础+装备(已持久化)+临时buff |
| 运气 | Player.luck | ItemInstance._persist_bonus["luck"] | TemporaryBuff.attribute_bonuses["luck"] | 基础+装备(已持久化)+临时buff |
| 咒抗 | Player.stamina | - | - | 直接读取 |
| 怨念 | Player.resentment | - | - | 直接读取 |
| 金币 | Player.gold | - | - | 直接读取 |
| 积分 | Player.gold2 | - | - | 直接读取 |
| 属性点 | Player.attribute_points | - | - | 直接读取 |
| 公会 | Player.guild_id | - | - | 查询Guild表 |
| 位置 | Player坐标 | - | - | real_world_x/y 或 dungeon_x/y |

---

## 6. Conclusions (关键发现)

### 核心发现

1. **玩家面板命令实现清晰**:
   - "面板"命令位于 `plugins/xiuxian_game/player/info.py:44`，提供完整的角色信息展示
   - "战力"命令位于 `plugins/xiuxian_game/player/battle_info.py:17`，展示扩展战斗属性

2. **属性计算已统一**:
   - 新的属性计算系统 `get_effective_attributes_v2()` 已替代旧的分散计算
   - 使用AttributeCalculator组合多个属性来源
   - 装备加成通过_persist_bonus机制持久化，避免重复计算

3. **Player模型共87字段，分为14大类**:
   - 基础信息、经验属性、基础属性(5个)、HP/MP系统
   - 扩展战斗属性(16个)、战斗统计、经济系统、签到系统
   - 双层坐标系(现实+诡域)、公会系统、阴宅系统、背包系统、VIP系统、闭关系统、留言板系统

4. **玩家有20个关联表**:
   - **直接一对多**: ItemInstance(背包)、MonthlyCard(月卡)、TemporaryBuff(临时buff)
   - **关键一对多**: NavigationTask(自动导航，影响坐标)、GuildMember、GuildBuilding
   - **社交关联**: Marriage(婚姻)、Mentorship(师徒)
   - **其他**: 交易记录、礼物记录、PVP记录等（不在面板显示）

5. **面板显示的字段映射**:
   - 基础属性直接来自Player表
   - 装备加成存在ItemInstance的_persist_bonus JSON中（已持久化在Player属性上）
   - 临时buff加成通过TemporaryBuff.get_active_buffs()获取，在属性计算时累加
   - 最终属性通过get_effective_attributes_v2()统一计算

6. **坐标系统设计**:
   - 现实世界: real_world_x/y + region字段
   - 诡域: dungeon_x/y + dungeon_level字段 + max_dungeon_level追踪最高层级
   - 面板显示会根据is_in_dungeon()状态选择不同的坐标显示

### 性能优化点

- 装备加成通过_persist_bonus持久化在Player属性上，避免每次查询时重新计算
- 临时buff通过60秒TTL缓存优化查询性能
- 属性计算使用顺序执行（非asyncio.gather）确保session安全

### 设计亮点

- **双层坐标系**支持现实世界和诡域的无缝切换
- **_persist_bonus机制**解决了百分比加成与基础属性同步的问题
- **JSON灵活字段**（extra_attrs、attribute_bonuses）支持动态扩展

---

## 7. Relations (代码关系图)

### 调用关系链

```
玩家命令请求
├── profile命令 (info.py:44)
│   └── profile.handle() (info.py:51-174)
│       ├── get_unified_player() [获取玩家对象]
│       ├── _update_nav_position() [更新导航坐标] → NavigationTask
│       ├── get_effective_attributes_v2() [计算属性]
│       │   └── AttributeCalculator.calculate_final_attributes()
│       │       ├── 基础属性 (Player字段)
│       │       ├── 装备加成来源 (ItemInstance._persist_bonus)
│       │       └── 临时buff加成 (TemporaryBuff.get_active_buffs())
│       ├── 装备加成统计 (ItemInstance.equipped == true)
│       │   └── 遍历加成: extra_attrs["_persist_bonus"]
│       ├── 公会查询 → Guild表
│       └── 消息渲染 [六个分区的格式化输出]
│
└── battle_info命令 (battle_info.py:17)
    └── handle_battle_info() (battle_info.py:21-67)
        ├── get_effective_attributes_v2() [基础战斗属性]
        ├── BattleIntegrationHelper.get_battle_attribute_display_async() [扩展属性]
        └── TemporaryBuff.get_active_buffs() [临时buff检查]
```

### 数据表关系

```
Player (玩家表)
├── 1:N → ItemInstance (背包/装备) - 决定装备加成
├── 1:N → TemporaryBuff (临时buff) - 决定临时属性加成
├── N:1 → Guild (公会) [通过guild_id]
│   ├── Guild.members (GuildMember表)
│   └── Guild.buildings (GuildBuilding表)
├── 1:N → MonthlyCard (月卡) - 影响背包容量
├── 1:N → MarketOrder (交易订单)
├── 1:N → Marriage (婚姻关系) [player1_id或player2_id]
├── 1:N → Mentorship (师徒关系) [master_id或apprentice_id]
├── 1:1 → NavigationTask (自动导航) - 影响面板坐标显示
└── 1:1 → BankAccount (银行账户)
    [其他关联表不直接影响面板显示]
```

### 属性计算数据流

```
ItemInstance (装备)
└── extra_attrs["_persist_bonus"]
    └── recalc_equipment_attributes() 时写入Player属性
        └── Player.attack/defense/agility等 [已包含装备加成]
            └── get_effective_attributes_v2()
                ├── base = 读取Player属性 [包含装备]
                ├── buff_bonus = TemporaryBuff.get_active_buffs()
                │   └── 遍历accumulate attribute_bonuses
                └── final = base + buff_bonus
                    └── 返回最终属性展示在面板
```

### 坐标系统逻辑

```
Player.is_in_dungeon() → true
├── 显示: dungeon_level层诡域 (dungeon_x, dungeon_y)
├── 保留现实坐标: real_world_x, real_world_y
└── Player.exit_dungeon() 时恢复

Player.is_in_dungeon() → false
├── 显示: 大都会 (real_world_x, real_world_y)
└── Player.enter_dungeon(level) 时保存现实坐标
```

---

**报告完成日期**: 2025-12-01
**文件路径**: `/llmdoc/agent/player_panel_investigation_2025_12_01.md`
