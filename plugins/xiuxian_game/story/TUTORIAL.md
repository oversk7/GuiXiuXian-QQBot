# Story Engine 教程文档

## 📖 目录

1. [快速入门](#快速入门)
2. [基本概念](#基本概念)
3. [节点类型](#节点类型)
4. [条件系统](#条件系统)
5. [跳转系统](#跳转系统)
6. [效果系统](#效果系统)
7. [变量系统](#变量系统)
8. [完整示例](#完整示例)
9. [最佳实践](#最佳实践)

---

## 快速入门

### 最小示例

```json
{
  "id": "hello_world",
  "title": "Hello World",
  "description": "最简单的剧情示例",
  "start_node": "start",
  "nodes": {
    "start": {
      "type": "story",
      "content": "你好,世界!",
      "next": "end"
    },
    "end": {
      "type": "end",
      "content": "剧情结束!"
    }
  }
}
```

### 文件位置

剧情文件存放在: `plugins/xiuxian_game/data/stories/`
文件格式: JSON (UTF-8编码)

### 游戏内使用

```
【试炼列表】         # 查看所有可用剧情
【开始试炼 hello_world】  # 开始指定剧情
【试炼状态】         # 查看当前进度
【退出试炼】         # 退出当前剧情
```

---

## 基本概念

### 剧情结构

```
Story (剧情)
├── id (唯一标识符)
├── title (标题)
├── description (描述)
├── start_node (起始节点)
└── nodes (节点集合)
    ├── node_1
    ├── node_2
    └── ...
```

### 节点 (Node)

节点是剧情的基本单元,类似于C++中的状态机状态。

```cpp
// 类比: C++状态机
enum State {
    START,
    CHOICE_A,
    CHOICE_B,
    END
};
```

```json
// JSON剧情节点
"start": {
  "type": "story",
  "content": "剧情文本",
  "next": "choice_a"
}
```

---

## 节点类型

### 1. story - 普通剧情节点

展示剧情文本,玩家发送任意消息继续。

```json
"intro": {
  "type": "story",
  "content": "你走进了一片黑暗的森林...",
  "next": "next_node"
}
```

### 2. choice - 选择节点

玩家需要做出选择。

```json
"make_choice": {
  "type": "choice",
  "content": "你看到两条路:",
  "options": [
    {
      "id": 1,
      "text": "左边的小路",
      "next": "left_path"
    },
    {
      "id": 2,
      "text": "右边的大路",
      "next": "right_path"
    }
  ]
}
```

玩家发送数字 `1` 或 `2` 进行选择。

### 3. end - 结束节点

剧情结束点。

```json
"ending": {
  "type": "end",
  "content": "剧情结束!\n\n你获得了胜利!"
}
```

---

## 条件系统

### 基本条件格式

```json
"conditions": {
  "player_level": {">=": 10}
}
```

### 支持的运算符

| 运算符 | 含义 | 示例 |
|--------|------|------|
| `==` | 等于 | `{"==": 10}` |
| `!=` | 不等于 | `{"!=": 0}` |
| `>` | 大于 | `{">": 5}` |
| `>=` | 大于等于 | `{">=": 10}` |
| `<` | 小于 | `{"<": 100}` |
| `<=` | 小于等于 | `{"<=": 50}` |
| `in` | 包含于 | `{"in": [1, 2, 3]}` |
| `not_in` | 不包含于 | `{"not_in": [4, 5, 6]}` |

### 变量类型

**1. 玩家属性** (前缀 `player_`)

```json
{
  "player_level": {">=": 10},      // 等级
  "player_gold": {">": 1000},      // 金币
  "player_hp": {">=": 100},        // 生命值
  "player_attack": {">": 50},      // 攻击力
  "player_vip": {">=": 1}          // VIP等级
}
```

**2. 剧情变量** (前缀 `story_`)

```json
{
  "story_has_key": {"==": true},
  "story_reputation": {">": 50}
}
```

**3. 直接变量** (无前缀,简写)

```json
{
  "has_key": {"==": true}
}
```

### 逻辑运算符 (重点!)

#### and 逻辑 (所有条件都必须满足)

**方式1: 默认行为 (简写)**

```json
"conditions": {
  "player_level": {">=": 10},
  "player_gold": {">=": 1000}
}
// 等价于 C++: (player.level >= 10 && player.gold >= 1000)
```

**方式2: 明确指定**

```json
"conditions": {
  "and": [
    {"player_level": {">=": 10}},
    {"player_gold": {">=": 1000}}
  ]
}
```

#### or 逻辑 (至少一个条件满足)

```json
"conditions": {
  "or": [
    {"player_gold": {">": 1000}},
    {"player_vip": {">=": 1}}
  ]
}
// 等价于 C++: (player.gold > 1000 || player.vip >= 1)
```

#### 嵌套组合

**示例1: (A && B) || C**

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

等价于C++:
```cpp
if ((player.level >= 10 && player.gold >= 1000) || player.vip >= 2) {
    // ...
}
```

**示例2: (A || B) && C**

```json
"conditions": {
  "and": [
    {
      "or": [
        {"player_level": {">=": 20}},
        {"player_vip": {">=": 1}}
      ]
    },
    {"player_gold": {">=": 500}}
  ]
}
```

等价于C++:
```cpp
if ((player.level >= 20 || player.vip >= 1) && player.gold >= 500) {
    // ...
}
```

---

## 跳转系统

### 固定跳转 (简单模式)

```json
"next": "node_2"
```

### 条件跳转 (if-else if-else)

```json
"next": [
  {
    "if": {"player_gold": {">": 1000}},
    "goto": "rich_path"
  },
  {
    "if": {"player_level": {">=": 10}},
    "goto": "strong_path"
  },
  {
    "goto": "normal_path"  // 默认分支(无if)
  }
]
```

等价于C++:
```cpp
if (player.gold > 1000) {
    goto rich_path;
} else if (player.level >= 10) {
    goto strong_path;
} else {
    goto normal_path;
}
```

### 复杂条件跳转

```json
"next": [
  {
    "if": {
      "and": [
        {"player_level": {">=": 20}},
        {"story_reputation": {">": 50}}
      ]
    },
    "goto": "hero_ending"
  },
  {
    "if": {
      "or": [
        {"story_reputation": {"<": 0}},
        {"story_evil_deeds": {">": 10}}
      ]
    },
    "goto": "villain_ending"
  },
  {
    "goto": "normal_ending"
  }
]
```

### 在选项中使用条件跳转

```json
{
  "id": 1,
  "text": "尝试说服他",
  "effects": {
    "variables": {
      "tried_persuasion": true
    }
  },
  "next": [
    {
      "if": {
        "and": [
          {"player_level": {">=": 15}},
          {"story_charisma": {">": 30}}
        ]
      },
      "goto": "persuasion_success"
    },
    {
      "goto": "persuasion_fail"
    }
  ]
}
```

---

## 效果系统

### 修改玩家属性

```json
"effects": {
  "player": {
    "gold": "+500",      // 相对变化: 增加500
    "exp": "+1000",      // 增加1000经验
    "hp": "-50",         // 减少50生命值
    "attack": "+10",     // 增加10攻击力
    "level": 15          // 绝对值: 设置为15级
  }
}
```

**相对变化 vs 绝对值**

```json
// 相对变化 (字符串,带+/-)
"gold": "+500"   // gold = gold + 500
"hp": "-50"      // hp = hp - 50

// 绝对值 (数字)
"gold": 1000     // gold = 1000
"hp": 100        // hp = 100
```

### 修改剧情变量

```json
"effects": {
  "variables": {
    "has_key": true,
    "reputation": "+10",
    "evil_deeds": "+1",
    "quest_stage": 2
  }
}
```

### 组合效果

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

---

## 变量系统

### 剧情变量的生命周期

```json
// 节点1: 设置变量
"node_1": {
  "type": "choice",
  "content": "...",
  "options": [
    {
      "id": 1,
      "text": "拿走钥匙",
      "effects": {
        "variables": {
          "has_key": true,      // 设置变量
          "keys_collected": "+1"
        }
      },
      "next": "node_2"
    }
  ]
}

// 节点2: 检查变量
"node_2": {
  "type": "story",
  "content": "你来到了一扇锁着的门前...",
  "next": [
    {
      "if": {"has_key": {"==": true}},  // 使用变量
      "goto": "unlock_door"
    },
    {
      "goto": "locked_out"
    }
  ]
}
```

### 内容中使用变量

```json
"content": "你好 {player_name},你的等级是 {player_level}。\n你拥有 {player_gold} 金币。"
```

支持的占位符:
- `{player_name}` - 玩家昵称
- `{player_level}` - 等级
- `{player_gold}` - 金币
- `{player_hp}` - 生命值
- `{player_attack}` - 攻击力
- 以及所有剧情变量: `{变量名}`

---

## 完整示例

### 示例: 带分支的商人交易

```json
{
  "id": "merchant_trade",
  "title": "商人交易",
  "description": "与神秘商人进行交易",
  "start_node": "meet_merchant",
  "nodes": {
    "meet_merchant": {
      "type": "story",
      "content": "一个商人向你走来...\n\n「年轻人,需要点什么吗?」",
      "next": "show_goods"
    },

    "show_goods": {
      "type": "choice",
      "content": "商人展示了他的商品:",
      "options": [
        {
          "id": 1,
          "text": "购买神秘药水 (1000金币)",
          "conditions": {
            "player_gold": {">=": 1000}
          },
          "effects": {
            "player": {
              "gold": "-1000",
              "hp": "+100"
            },
            "variables": {
              "bought_potion": true
            }
          },
          "next": "after_trade"
        },
        {
          "id": 2,
          "text": "讨价还价",
          "next": "bargain"
        },
        {
          "id": 3,
          "text": "离开",
          "next": "leave"
        }
      ]
    },

    "bargain": {
      "type": "story",
      "content": "你尝试和商人讨价还价...",
      "next": [
        {
          "if": {
            "or": [
              {"player_level": {">=": 15}},
              {"player_vip": {">=": 1}}
            ]
          },
          "goto": "bargain_success"
        },
        {
          "goto": "bargain_fail"
        }
      ]
    },

    "bargain_success": {
      "type": "story",
      "content": "商人同意降价!\n\n「好吧,看在你的面子上,500金币。」",
      "effects": {
        "player": {
          "gold": "-500",
          "hp": "+100"
        }
      },
      "next": "after_trade"
    },

    "bargain_fail": {
      "type": "story",
      "content": "商人摇了摇头。\n\n「一口价,1000金币,不讲价。」",
      "next": "show_goods"
    },

    "after_trade": {
      "type": "story",
      "content": "交易完成!商人满意地点了点头。",
      "next": "check_bonus"
    },

    "check_bonus": {
      "type": "story",
      "content": "商人似乎还有话要说...",
      "next": [
        {
          "if": {
            "and": [
              {"bought_potion": {"==": true}},
              {"player_gold": {">=": 2000}}
            ]
          },
          "goto": "vip_offer"
        },
        {
          "goto": "normal_ending"
        }
      ]
    },

    "vip_offer": {
      "type": "choice",
      "content": "「看起来你是个有钱人...我这里还有更好的东西!」",
      "options": [
        {
          "id": 1,
          "text": "我感兴趣! (2000金币)",
          "conditions": {
            "player_gold": {">=": 2000}
          },
          "effects": {
            "player": {
              "gold": "-2000",
              "attack": "+50"
            }
          },
          "next": "rich_ending"
        },
        {
          "id": 2,
          "text": "不了,谢谢",
          "next": "normal_ending"
        }
      ]
    },

    "leave": {
      "type": "end",
      "content": "你离开了商人。\n\n「随时欢迎回来!」"
    },

    "normal_ending": {
      "type": "end",
      "content": "交易结束!\n\n商人收起货物离开了。"
    },

    "rich_ending": {
      "type": "end",
      "content": "你获得了珍贵的宝物!\n\n商人满意地笑了:「欢迎下次再来!」"
    }
  }
}
```

---

## 最佳实践

### 1. 节点命名规范

```json
// ✅ 好的命名
"meet_merchant"
"check_player_level"
"hero_ending"

// ❌ 不好的命名
"node1"
"a"
"temp"
```

### 2. 使用有意义的变量名

```json
// ✅ 清晰
"has_key": true
"merchant_favor": 50

// ❌ 不清晰
"flag1": true
"value": 50
```

### 3. 合理使用默认分支

```json
// ✅ 总是提供默认路径
"next": [
  {"if": {...}, "goto": "path_a"},
  {"if": {...}, "goto": "path_b"},
  {"goto": "default_path"}  // 确保有默认分支
]

// ❌ 可能卡住
"next": [
  {"if": {...}, "goto": "path_a"},
  {"if": {...}, "goto": "path_b"}
  // 如果两个条件都不满足,玩家会卡住!
]
```

### 4. 条件复杂度控制

```json
// ✅ 清晰的两层嵌套
{
  "or": [
    {"and": [cond1, cond2]},
    cond3
  ]
}

// ❌ 过度嵌套(难以维护)
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

建议: 嵌套不超过2层

### 5. 测试清单

开发剧情时,确保测试:

- [ ] 所有分支都能到达
- [ ] 所有条件都被正确触发
- [ ] 没有死循环
- [ ] 所有结束节点都能到达
- [ ] 变量正确设置和使用
- [ ] 效果正确应用

### 6. 调试技巧

**添加调试节点**

```json
"debug_checkpoint": {
  "type": "story",
  "content": "DEBUG: player_level={player_level}, has_key={has_key}",
  "next": "actual_node"
}
```

**简化条件测试**

```json
// 开发时: 简单条件
"conditions": {
  "player_level": {">=": 1}
}

// 上线时: 实际条件
"conditions": {
  "and": [
    {"player_level": {">=": 20}},
    {"player_gold": {">=": 10000}}
  ]
}
```

---

## 常见问题

### Q: 如何实现计数器?

```json
// 初始化
"effects": {
  "variables": {
    "counter": 0
  }
}

// 递增
"effects": {
  "variables": {
    "counter": "+1"
  }
}

// 检查
"conditions": {
  "counter": {">=": 3}
}
```

### Q: 如何实现多次访问同一个节点?

```json
"repeatable_node": {
  "type": "choice",
  "content": "你已经访问了 {visit_count} 次",
  "options": [
    {
      "id": 1,
      "text": "再次访问",
      "effects": {
        "variables": {
          "visit_count": "+1"
        }
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

### Q: 如何实现"记忆"玩家之前的选择?

```json
// 第一次选择
"first_choice": {
  "type": "choice",
  "content": "...",
  "options": [
    {
      "id": 1,
      "text": "选择A",
      "effects": {
        "variables": {
          "first_choice": "A"
        }
      },
      "next": "..."
    }
  ]
}

// 后续根据之前的选择
"later_node": {
  "type": "story",
  "content": "...",
  "next": [
    {
      "if": {"first_choice": {"==": "A"}},
      "goto": "path_for_A"
    },
    {
      "goto": "path_for_others"
    }
  ]
}
```

---

**祝你创作愉快! 🎮**
