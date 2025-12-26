# 如何创建剧情 (Story Engine 使用指南)

## 1. 快速开始

### 1.1 创建剧情文件

1. 在 `plugins/xiuxian_game/data/stories/` 目录创建JSON文件
2. 文件名格式: `<story_id>.json` (例: `my_story.json`)
3. 使用UTF-8编码保存

### 1.2 最小可用剧情模板

```json
{
  "id": "my_story",
  "title": "我的第一个剧情",
  "description": "这是一个简单的示例剧情",
  "start_node": "start",
  "nodes": {
    "start": {
      "type": "story",
      "content": "欢迎来到我的剧情!",
      "next": "end"
    },
    "end": {
      "type": "end",
      "content": "剧情结束!"
    }
  }
}
```

### 1.3 测试剧情

1. 重启机器人加载新剧情
2. 游戏内输入 `【试炼列表】` 查看剧情
3. 输入 `【开始试炼 my_story】` 开始测试

## 2. 节点类型详解

### 2.1 story节点 - 普通剧情

**用途**: 展示剧情文本,玩家发送任意消息继续。

```json
"intro": {
  "type": "story",
  "content": "你走进了一片黑暗的森林...",
  "next": "choice_node"
}
```

**可选字段**:
- `effects`: 应用效果 (修改属性/变量)
- `next`: 下一个节点 (字符串或条件跳转数组)

### 2.2 choice节点 - 选择分支

**用途**: 提供多个选项,玩家选择决定后续路径。

```json
"fork_road": {
  "type": "choice",
  "content": "前方道路分叉,你选择:",
  "options": [
    {
      "id": 1,
      "text": "走左边",
      "next": "left_path"
    },
    {
      "id": 2,
      "text": "走右边",
      "conditions": {
        "player_level": {">=": 5}
      },
      "next": "right_path"
    }
  ]
}
```

**选项字段**:
- `id`: 数字序号 (玩家输入1或2选择)
- `text`: 显示文本
- `next`: 跳转目标 (可用条件跳转)
- `conditions` (可选): 显示/选择条件
- `effects` (可选): 选择后应用的效果

### 2.3 end节点 - 结束

**用途**: 剧情结束点,结束后自动退出试炼。

```json
"good_ending": {
  "type": "end",
  "content": "🎭 试炼结束\n\n你成功完成了试炼!",
  "effects": {
    "player": {
      "gold": "+1000",
      "exp": "+500"
    }
  }
}
```

## 3. 条件系统使用

### 3.1 简单条件 (默认 and)

```json
"conditions": {
  "player_level": {">=": 10},
  "player_gold": {">=": 1000}
}
```
**含义**: 等级≥10 且 金币≥1000

### 3.2 or 逻辑

```json
"conditions": {
  "or": [
    {"player_gold": {">": 1000}},
    {"player_vip": {">=": 1}}
  ]
}
```
**含义**: 金币>1000 或 VIP≥1

### 3.3 复杂嵌套

```json
"conditions": {
  "or": [
    {
      "and": [
        {"player_level": {">=": 10}},
        {"player_gold": {">=": 1000}}
      ]
    },
    {"player_vip": {">=": 2}}
  ]
}
```
**含义**: (等级≥10 且 金币≥1000) 或 VIP≥2

### 3.4 变量类型

| 类型 | 前缀 | 示例 |
|------|------|------|
| 玩家属性 | `player_` | `player_level`, `player_gold`, `player_hp` |
| 剧情变量 | `story_` | `story_has_key`, `story_reputation` |
| 直接变量 | 无 | `has_key`, `quest_stage` |

## 4. 条件跳转使用

### 4.1 固定跳转 (简单)

```json
"next": "node_2"
```

### 4.2 条件跳转 (if-else)

```json
"next": [
  {
    "if": {"player_gold": {">": 1000}},
    "goto": "rich_ending"
  },
  {
    "if": {"player_level": {">=": 10}},
    "goto": "strong_ending"
  },
  {
    "goto": "normal_ending"
  }
]
```

**执行逻辑**: 从上到下检查条件,跳转到第一个满足的分支,如果都不满足则执行默认分支(无`if`字段)。

### 4.3 在选项中使用

```json
{
  "id": 1,
  "text": "尝试突破封印",
  "effects": {
    "player": {"hp": "-50"}
  },
  "next": [
    {
      "if": {"player_level": {">=": 15}},
      "goto": "success"
    },
    {
      "goto": "fail"
    }
  ]
}
```

## 5. 效果系统使用

### 5.1 修改玩家属性

```json
"effects": {
  "player": {
    "gold": "+500",      // 增加500金币
    "exp": "+1000",      // 增加1000经验
    "hp": "-50",         // 减少50生命
    "attack": "+10",     // 增加10攻击
    "level": 15          // 直接设置为15级
  }
}
```

**规则**:
- 字符串 `"+X"` / `"-X"`: 相对变化
- 数字: 绝对值设置

### 5.2 修改剧情变量

```json
"effects": {
  "variables": {
    "has_key": true,
    "reputation": "+10",
    "quest_stage": 2
  }
}
```

### 5.3 组合效果

```json
"effects": {
  "player": {
    "gold": "-1000",
    "attack": "+50"
  },
  "variables": {
    "bought_sword": true,
    "merchant_favor": "+5"
  }
}
```

## 6. 变量使用

### 6.1 设置变量

```json
"effects": {
  "variables": {
    "has_key": true,
    "keys_collected": "+1"
  }
}
```

### 6.2 检查变量

```json
"conditions": {
  "has_key": {"==": true},
  "keys_collected": {">=": 3}
}
```

### 6.3 在文本中引用

```json
"content": "你好 {player_name},你的等级是 {player_level}。\n你拥有 {player_gold} 金币,已收集 {keys_collected} 把钥匙。"
```

## 7. 最佳实践

### 7.1 节点命名

```json
// ✅ 好的命名
"meet_merchant"
"check_player_level"
"hero_ending"

// ❌ 不好的命名
"node1"
"temp"
"a"
```

### 7.2 总是提供默认分支

```json
// ✅ 安全
"next": [
  {"if": {...}, "goto": "path_a"},
  {"if": {...}, "goto": "path_b"},
  {"goto": "default_path"}  // 确保有默认
]

// ❌ 可能卡住
"next": [
  {"if": {...}, "goto": "path_a"},
  {"if": {...}, "goto": "path_b"}
  // 如果两个条件都不满足,玩家会卡住!
]
```

### 7.3 嵌套复杂度控制

**建议**: 嵌套不超过2层

```json
// ✅ 清晰
{
  "or": [
    {"and": [cond1, cond2]},
    cond3
  ]
}

// ❌ 过于复杂
{
  "or": [
    {
      "and": [
        {"or": [cond1, cond2]},
        {"and": [cond3, cond4]}
      ]
    },
    cond5
  ]
}
```

## 8. 测试清单

创建剧情后,确保测试:

- [ ] 所有分支都能到达
- [ ] 所有条件都被正确触发
- [ ] 没有死循环
- [ ] 所有结束节点都能到达
- [ ] 变量正确设置和使用
- [ ] 效果正确应用
- [ ] 有默认分支防止卡住

## 9. 常见问题

### Q: 如何实现计数器?

```json
// 初始化
"effects": {
  "variables": {"counter": 0}
}

// 递增
"effects": {
  "variables": {"counter": "+1"}
}

// 检查
"conditions": {
  "counter": {">=": 3}
}
```

### Q: 如何实现多次访问同一节点?

```json
"repeatable_node": {
  "type": "choice",
  "options": [
    {
      "id": 1,
      "text": "再次访问",
      "effects": {
        "variables": {"visit_count": "+1"}
      },
      "next": "repeatable_node"  // 跳回自己
    },
    {
      "id": 2,
      "text": "离开",
      "next": "exit"
    }
  ]
}
```

## 10. 参考资料

- 完整示例: `plugins/xiuxian_game/data/stories/mysterious_merchant.json`
- 详细教程: `plugins/xiuxian_game/story/TUTORIAL.md`
- 引擎架构: `/llmdoc/architecture/story-engine-enhanced-conditions.md`
