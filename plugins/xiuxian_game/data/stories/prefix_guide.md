# 剧情系统前缀完整指南

## 📝 文本替换前缀（在content中使用）

### 玩家基本信息
```
{player_name}        - 玩家昵称
{player_uid}         - 玩家UID
{player_level}       - 玩家等级
{player_sex}         - 玩家性别（男/女）
{player_region}      - 玩家所在区域
```

### 玩家属性
```
{player_exp}         - 当前经验值
{player_hp}          - 当前生命值
{player_max_hp}      - 最大生命值
{player_mp}          - 当前理智值
{player_max_mp}      - 最大理智值
{player_attack}      - 攻击力
{player_defense}     - 防御力
{player_agility}     - 敏捷
{player_stamina}     - 咒抗
{player_luck}        - 运气
{player_resentment}  - 怨念值
```

### 玩家财富
```
{player_gold}        - 金币
{player_gold2}       - 积分
{player_vip}         - VIP等级
```

### 玩家位置
```
{player_x}           - X坐标
{player_y}           - Y坐标
```

### 公会信息
```
{player_guild_id}           - 公会ID（无公会显示"无"）
{player_guild_contribution} - 公会贡献值
```

### 其他信息
```
{player_attribute_points}   - 可分配属性点
{player_sign_streak}        - 连续签到天数
```

### 剧情变量
```
{任何变量名}          - 你在effects中设置的剧情变量
```

## 🎯 条件判断前缀（在conditions中使用）

### 玩家属性条件
```json
"conditions": {
  "player_level": {">=": 10},           // 等级≥10
  "player_gold": {">": 1000},           // 金币>1000
  "player_hp": {"<": 50},               // 生命值<50
  "player_attack": {">=": 20},          // 攻击力≥20
  "player_defense": {"<=": 15},         // 防御力≤15
  "player_agility": {"==": 10},         // 敏捷==10
  "player_luck": {"!=": 0},             // 运气≠0
  "player_resentment": {">": 100},      // 怨念值>100
  "player_vip": {">=": 1},              // VIP等级≥1
  "player_sex": {"==": "女"},           // 性别为女
  "player_region": {"==": "大都会"}     // 在大都会区域
}
```

### 剧情变量条件
```json
"conditions": {
  "story_fear_level": {"<": 8},         // 剧情变量fear_level<8
  "story_has_key": {"==": true},        // 剧情变量has_key为true
  "story_choice_count": {">=": 3},      // 剧情变量choice_count≥3
  "story_current_room": {"==": "库房"}  // 剧情变量current_room为"库房"
}
```

### 直接变量条件（不推荐，建议用story_前缀）
```json
"conditions": {
  "fear_level": {"<": 5},               // 等同于story_fear_level
  "has_item": {"==": true}              // 等同于story_has_item
}
```

## 💫 Effects修改前缀（在effects中使用）

### 玩家属性修改
```json
"effects": {
  "player": {
    "gold": "+100",              // 金币+100
    "exp": "+50",                // 经验+50
    "hp": "-20",                 // 生命-20
    "max_hp": "+10",             // 最大生命+10
    "mp": "+5",                  // 理智+5
    "max_mp": "+5",              // 最大理智+5
    "attack": "+3",              // 攻击力+3
    "defense": "+2",             // 防御+2
    "agility": "+1",             // 敏捷+1
    "stamina": "+2",             // 咒抗+2
    "luck": "+1",                // 运气+1
    "resentment": "+20",         // 怨念值+20
    "level": 10,                 // 设置等级为10（绝对值）
    "vip": 1,                    // 设置VIP等级为1
    "attribute_points": "+5"     // 属性点+5
  }
}
```

### 剧情变量修改
```json
"effects": {
  "variables": {
    "fear_level": "+1",          // 恐惧值+1
    "has_key": true,             // 设置为true
    "puzzle_pieces": "+1",       // 拼图片+1
    "current_room": "森林",      // 设置当前房间
    "choice_count": "+1",        // 选择次数+1
    "player_name": "{player_name}" // 保存玩家名字到变量
  }
}
```

## 📸 配图功能

### 在节点中添加图片
```json
{
  "start": {
    "type": "story",
    "content": "故事内容...",
    "image": "images/scene1.png",
    "next": "next_node"
  }
}
```

### 图片路径规则
- 路径相对于 `plugins/xiuxian_game/data/stories/` 目录
- 推荐使用 `images/` 子目录组织图片
- 支持格式：PNG、JPEG、GIF、WebP
- 如果图片不存在，会跳过图片显示

## 📋 支持的操作符

### 条件判断操作符
```
"=="  - 等于
"!="  - 不等于
">"   - 大于
">="  - 大于等于
"<"   - 小于
"<="  - 小于等于
"in"  - 包含在列表中
"not_in" - 不包含在列表中
```

### Effects修改格式
```
"+数字"  - 相对增加（如 "+100"）
"-数字"  - 相对减少（如 "-50"）
数字     - 绝对设置（如 100）
字符串   - 设置字符串值（如 "森林"）
布尔值   - 设置布尔值（如 true/false）
```

## 💡 使用示例

### 完整的节点示例（带配图）
```json
"example_node": {
  "type": "choice",
  "content": "🏠 {player_name}，你现在在{current_room}。\n\n你的状态：\n💰 金币：{player_gold}\n❤️ 生命：{player_hp}/{player_max_hp}\n🧠 理智：{player_mp}/{player_max_mp}\n⚔️ 攻击：{player_attack}\n\n恐惧值：{fear_level}/10",
  "image": "images/room_scene.png",
  "options": [
    {
      "id": 1,
      "text": "使用钥匙开门",
      "next": "open_door",
      "conditions": {
        "story_has_key": {"==": true},
        "player_gold": {">=": 100}
      },
      "effects": {
        "variables": {
          "has_key": false,
          "doors_opened": "+1"
        },
        "player": {
          "gold": "-100"
        }
      }
    }
  ]
}
```

### 不同类型节点的配图示例
```json
// 普通故事节点
"story_node": {
  "type": "story",
  "content": "你走进了一个神秘的房间...",
  "image": "images/mysterious_room.png",
  "next": "next_scene"
}

// 选择节点
"choice_node": {
  "type": "choice",
  "content": "你面前出现了三条路...",
  "image": "images/three_paths.png",
  "options": [...]
}

// 结束节点
"end_node": {
  "type": "end",
  "content": "试炼完成！",
  "image": "images/victory_scene.png",
  "effects": {"rewards": {...}}
}
```

这样你就可以在剧情中使用所有这些前缀来创建丰富的互动体验了！
