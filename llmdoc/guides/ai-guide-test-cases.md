# AI Guide 测试用例

**文档创建日期**: 2025-12-01
**功能**: 测试 ai_guide 系统根据玩家面板生成正确 SQL 的能力
**相关文件**: `plugins/xiuxian_game/ai_guide.py`

---

## 1. 功能说明

AI Guide 系统现在支持：
- 完整的 Player 表 87 个字段识别
- 根据玩家面板数据生成准确的 UPDATE SQL
- 智能识别坐标系统（现实世界/诡域）
- 正确映射扩展战斗属性字段名

---

## 2. 测试用例

### 测试用例 1：基础玩家面板覆盖

**输入（管理员发送）**：
```
将UID 1001的玩家数据改为：
昵称：测试玩家
等级：50
经验：3000
性别：男
生命：500/500
理智：400/400
攻击：200
防御：150
敏捷：100
运气：50
咒抗：30
金币：50000
积分：1000
怨念：200
转数：1
位置：大都会 (100, 200)
```

**预期生成 SQL**：
```sql
UPDATE player SET
  nickname = '测试玩家',
  level = 50,
  exp = 3000,
  sex = '男',
  hp = 500,
  max_hp = 500,
  mp = 400,
  max_mp = 400,
  attack = 200,
  defense = 150,
  agility = 100,
  luck = 50,
  stamina = 30,
  gold = 50000,
  gold2 = 1000,
  resentment = 200,
  reincarnation_level = 1,
  real_world_x = 100,
  real_world_y = 200,
  dungeon_level = 0,
  region = '大都会'
WHERE uid = 1001
```

---

### 测试用例 2：完整战斗属性覆盖

**输入（管理员发送）**：
```
将昵称为"战神"的玩家战斗属性改为：
暴击率：50%
暴击力：40
连击率：30%
反击率：20%
闪避率：35%
命中率：95%
灵爆率：25%
穿透率：35%
抗暴率：28%
吸血率：15%
定身率：8%
真伤率：10%
回血率：12%
```

**预期生成 SQL**：
```sql
UPDATE player SET
  critical_rate = 50,
  critical_power = 40,
  combo_rate = 30,
  counter_rate = 20,
  dodge_rate = 35,
  accuracy_rate = 95,
  skill_crit_rate = 25,
  penetration_rate = 35,
  anti_crit_rate = 28,
  lifesteal_rate = 15,
  immobilize_rate = 8,
  true_damage_rate = 10,
  regen_rate = 12
WHERE nickname = '战神'
```

---

### 测试用例 3：诡域坐标系统

**输入（管理员发送）**：
```
将UID 1002的玩家传送到第5层诡域的坐标(3, -2)
```

**预期生成 SQL**：
```sql
UPDATE player SET
  dungeon_level = 5,
  dungeon_x = 3,
  dungeon_y = -2,
  region = '5层诡域',
  x = 3,
  y = -2
WHERE uid = 1002
```

---

### 测试用例 4：现实世界返回

**输入（管理员发送）**：
```
将UID 1002的玩家从诡域返回现实世界坐标(390, 50)
```

**预期生成 SQL**：
```sql
UPDATE player SET
  dungeon_level = 0,
  real_world_x = 390,
  real_world_y = 50,
  region = '大都会',
  x = 390,
  y = 50
WHERE uid = 1002
```

---

### 测试用例 5：完整玩家面板数据（来自【面板】命令）

**输入（管理员复制粘贴玩家面板）**：
```
【玩家面板】
━━━━━━━━━━━━━
✨ 信息
昵称：剑圣[UID:1003]
性别：女 · Lv.120 · 金丹期
Exp 5000/8000

❤️ 状态
❤️生命 1500/1500
🧠理智 1200/1200
⚔力 600 (+150)
🛡防 450 (+100)
👟敏 300 (+80)
🍀运 180 (+50)
🔮咒抗 60

💰 其他
🪙金币 800000
💀怨念 1500 ✨点数 25
☯公会 无所属
📍位置 大都会 (250, 380)
```

**预期生成 SQL**：
```sql
UPDATE player SET
  nickname = '剑圣',
  sex = '女',
  level = 120,
  exp = 5000,
  hp = 1500,
  max_hp = 1500,
  mp = 1200,
  max_mp = 1200,
  attack = 600,
  defense = 450,
  agility = 300,
  luck = 180,
  stamina = 60,
  gold = 800000,
  resentment = 1500,
  attribute_points = 25,
  real_world_x = 250,
  real_world_y = 380,
  dungeon_level = 0,
  region = '大都会',
  guild_id = NULL
WHERE uid = 1003
```

**注意**：
- 装备加成 (+150, +100等) 已经包含在基础属性中，不需要单独设置
- AI 应该识别"金丹期"境界对应的等级
- "无所属" 公会应设置为 `guild_id = NULL`

---

## 3. 常见错误和修正

### 错误 1：字段名不匹配

❌ **错误**：
```sql
UPDATE player SET critical_damage = 40 WHERE uid = 1001
```

✅ **正确**：
```sql
UPDATE player SET critical_power = 40 WHERE uid = 1001
```

**原因**: 字段名是 `critical_power`（暴击力），不是 `critical_damage`

---

### 错误 2：坐标系统混淆

❌ **错误**：
```sql
UPDATE player SET x = 100, y = 200 WHERE uid = 1001
```

✅ **正确**：
```sql
UPDATE player SET
  real_world_x = 100,
  real_world_y = 200,
  dungeon_level = 0,
  region = '大都会',
  x = 100,
  y = 200
WHERE uid = 1001
```

**原因**: 双层坐标系统需要同时更新多个字段

---

### 错误 3：缺少关键坐标字段

❌ **错误**：
```sql
UPDATE player SET dungeon_level = 5 WHERE uid = 1001
```

✅ **正确**：
```sql
UPDATE player SET
  dungeon_level = 5,
  dungeon_x = 0,
  dungeon_y = 0,
  region = '5层诡域',
  x = 0,
  y = 0
WHERE uid = 1001
```

**原因**: 进入诡域需要设置完整的坐标信息

---

## 4. 验证步骤

### 步骤 1：准备测试环境
```bash
# 启动游戏机器人
python bot.py
```

### 步骤 2：发送测试消息
以管理员身份在 QQ 群发送测试用例 1 的输入

### 步骤 3：查看生成的 SQL
AI Guide 会输出：
1. "🔧 管理员修改模式：正在分析您的修改需求..."
2. "⚡ 正在执行修改操作..."
3. "✅ 修改操作执行成功！"

### 步骤 4：验证数据库
```sql
SELECT nickname, level, exp, hp, max_hp, attack, defense, agility, luck, gold
FROM player
WHERE uid = 1001
```

预期结果应该匹配输入的面板数据

---

## 5. 已改进的功能

### 改进 1：完整的字段覆盖
- **之前**: 只支持约 30 个常用字段
- **现在**: 支持全部 87 个 Player 字段
- **包括**: 战斗统计、签到系统、阴宅系统、VIP 系统等

### 改进 2：准确的字段映射
- **之前**: `critical_damage` → **错误**
- **现在**: `critical_power` → **正确**
- **之前**: `hit_rate` → **错误**
- **现在**: `accuracy_rate` → **正确**

### 改进 3：智能坐标识别
- 自动识别玩家是在现实世界还是诡域
- 正确设置 6 个坐标相关字段
- 支持"第N层诡域"格式解析

### 改进 4：详细的字段说明
- 每个字段包含数据类型、默认值、说明
- 分类清晰（14 个分类）
- 包含可为空标识

---

## 6. 后续改进建议

1. **增加字段验证**：
   - 验证数值范围（如等级 1-300，百分比 0-100）
   - 验证枚举值（如性别只能是"男"或"女"）

2. **支持批量操作**：
   - 一次修改多个玩家
   - 支持条件筛选（如"将所有等级>100的玩家金币设为1000"）

3. **增加回滚功能**：
   - 记录修改前的数据
   - 支持"撤销上次修改"命令

4. **智能字段推断**：
   - 根据等级自动推荐合理的属性值
   - 根据转数计算经验上限

---

**测试完成标准**：
- ✅ 所有 5 个测试用例生成正确的 SQL
- ✅ 字段名完全匹配 Player 模型
- ✅ 坐标系统处理正确
- ✅ 无 SQL 语法错误
- ✅ 执行后数据库数据正确更新
