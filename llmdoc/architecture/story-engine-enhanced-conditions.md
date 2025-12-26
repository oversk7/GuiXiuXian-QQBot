# Story Engine 增强条件和跳转系统架构

## 1. Identity

- **What it is**: Story Engine的条件系统和跳转系统增强,支持复杂逻辑运算和多分支条件跳转
- **Purpose**: 提供类似C++风格的条件语法,使剧情创作者能够设计复杂的分支剧情和多路径结局

## 2. Core Components

- `plugins/xiuxian_game/story/engine.py` (StoryEngine): 剧情状态机核心引擎
  - `evaluate_condition()` (L67-112): 条件评估器,支持 and/or/嵌套逻辑
  - `resolve_next()` (L135-171): 条件跳转解析器,支持 if-else if-else 语法
  - `process_choice()` (L296-333): 选择处理器,集成条件跳转
- `plugins/xiuxian_game/story/interactive_story.py` (交互处理器):
  - `handle_continue()` (L215-282): 普通节点处理,集成条件跳转
  - `handle_choice()` (L151-212): 选择节点处理
- `plugins/xiuxian_game/data/stories/mysterious_merchant.json`: 完整示例剧情,展示所有新功能
- `plugins/xiuxian_game/story/TUTORIAL.md`: 系统性教程文档,面向C++用户

## 3. Execution Flow (LLM Retrieval Map)

### 3.1 条件系统增强

**设计思路**: 参考C++逻辑运算符语法,使JSON配置更简洁直观。

**支持的条件格式**:

1. **简单条件 (默认 and)**:
   ```json
   "conditions": {
     "player_level": {">=": 10},
     "player_gold": {">=": 1000}
   }
   ```
   等价于: `(player.level >= 10 && player.gold >= 1000)`

2. **明确 and 逻辑**:
   ```json
   "conditions": {
     "and": [
       {"player_level": {">=": 10}},
       {"player_gold": {">=": 1000}}
     ]
   }
   ```

3. **or 逻辑**:
   ```json
   "conditions": {
     "or": [
       {"player_gold": {">": 1000}},
       {"player_vip": {">=": 1}}
     ]
   }
   ```
   等价于: `(player.gold > 1000 || player.vip >= 1)`

4. **嵌套组合 (A && B) || C**:
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

**实现位置**: `engine.py:67-112`

**核心算法**:
1. 递归检查逻辑运算符 (`and`/`or`)
2. 嵌套调用 `evaluate_condition()` 处理子条件
3. 简单条件使用 `_check_value()` 进行运算符比较

**支持的运算符**: `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not_in`

### 3.2 条件跳转系统

**设计思路**: 模拟C++的 if-else if-else 语法,使分支逻辑更清晰。

**跳转格式**:

1. **固定跳转 (简单模式)**:
   ```json
   "next": "node_2"
   ```

2. **条件跳转 (if-else if-else)**:
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
       "goto": "normal_path"
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

**实现位置**:
- `engine.py:135-171` - 核心解析逻辑
- `engine.py:296-333` - 在选择处理中应用
- `interactive_story.py:215-282` - 在普通节点中应用

**算法逻辑**:
1. 检查 `next` 是字符串还是数组
2. 如果是数组,遍历每个分支
3. 对每个带 `if` 的分支评估条件
4. 返回第一个满足条件的 `goto`,或默认分支(无 `if`)

### 3.3 完整使用示例

**神秘商人剧情** (`mysterious_merchant.json`):

**场景1: 嵌套条件判断** (L56-79)
```json
"next": [
  {
    "if": {
      "and": [
        {"player_level": {">=": 10}},
        {"player_gold": {">=": 1000}}
      ]
    },
    "goto": "worthy_power"
  },
  {
    "if": {
      "or": [
        {"player_level": {">=": 15}},
        {"player_vip": {">=": 1}}
      ]
    },
    "goto": "special_power"
  },
  {
    "goto": "unworthy_power"
  }
]
```

**逻辑解释**:
- **路径1**: 等级≥10 且 金币≥1000 → 高级力量结局
- **路径2**: 等级≥15 或 VIP≥1 → 特殊试炼
- **默认**: 其他情况 → 被拒绝

**场景2: 选择中的条件跳转** (L127-144)
```json
{
  "id": 2,
  "text": "接受试炼证明自己",
  "effects": {
    "player": {"hp": "-50"}
  },
  "next": [
    {
      "if": {"player_hp": {">=": 100}},
      "goto": "trial_success"
    },
    {
      "goto": "trial_fail"
    }
  ]
}
```

**逻辑**: 消耗50生命后,如果剩余生命≥100则通过,否则失败。

### 3.4 向后兼容性设计

**关键原则**: 所有现有剧情配置无需修改即可正常工作。

**兼容机制**:
1. **简单条件默认为 and**: 旧配置的多条件自动视为 and 关系
2. **固定跳转优先**: `"next": "node_id"` 仍然有效
3. **条件可选**: `conditions` 字段仍可省略

**测试验证**: 8个测试全部通过 (`test_core_logic.py`):
- ✅ 简单条件
- ✅ AND 逻辑 (默认和明确)
- ✅ OR 逻辑
- ✅ 嵌套条件 (A && B) || C
- ✅ 固定跳转
- ✅ 条件跳转
- ✅ 复杂条件跳转

## 4. Design Rationale

**为什么选择C++风格语法?**
1. **目标用户**: 教程明确面向"有C++基础的用户"
2. **学习曲线**: 熟悉的语法降低学习成本
3. **可读性**: `and`/`or` 比自定义操作符更直观

**为什么使用JSON而非代码?**
1. **安全性**: 剧情配置不能执行任意代码
2. **验证性**: JSON格式易于验证和错误检查
3. **可视化**: 未来可能开发可视化编辑器

**为什么允许无限嵌套?**
- 实际使用中建议嵌套≤2层(最佳实践),但引擎本身不限制,以提供最大灵活性

## 5. Integration Points

| 集成点 | 文件位置 | 说明 |
|-------|---------|------|
| 选择处理 | `interactive_story.py:151-212` | 玩家选择选项时触发条件跳转 |
| 普通节点继续 | `interactive_story.py:215-282` | 普通剧情节点跳转时评估条件 |
| 条件显示选项 | `engine.py:283-293` | 根据条件过滤显示的选择选项 |
| 效果应用 | `engine.py:173-199` | 应用玩家属性和剧情变量变化 |

## 6. Future Enhancements (未实现)

- **not 运算符**: `{"not": {"player_level": {"<": 10}}}`
- **变量引用**: `{"player_level": {">": "{story_required_level}"}}`
- **函数式条件**: `{"has_item": "magic_key"}`
- **条件缓存**: 复杂条件的结果缓存优化
