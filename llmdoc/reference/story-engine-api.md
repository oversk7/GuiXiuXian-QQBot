# Story Engine API 参考

## 1. Core Summary

Story Engine 是基于状态机的剧情系统,支持复杂条件逻辑、多分支跳转和变量管理。本文档提供核心API和配置格式的快速参考。

## 2. Source of Truth

- **核心引擎**: `plugins/xiuxian_game/story/engine.py` - StoryEngine类定义
- **交互处理**: `plugins/xiuxian_game/story/interactive_story.py` - 命令处理和消息格式化
- **数据模型**: `plugins/xiuxian_game/models/story_session.py` - StorySession模型
- **配置示例**: `plugins/xiuxian_game/data/stories/mysterious_merchant.json` - 完整功能演示
- **教程文档**: `plugins/xiuxian_game/story/TUTORIAL.md` - 面向用户的完整教程
- **架构文档**: `/llmdoc/architecture/story-engine-enhanced-conditions.md` - 系统架构设计

## 3. Story Configuration Format

### 3.1 剧情文件结构

```json
{
  "id": "story_id",
  "title": "剧情标题",
  "description": "剧情描述",
  "start_node": "start",
  "nodes": {
    "node_id": { /* 节点定义 */ }
  }
}
```

### 3.2 节点类型

| 类型 | 说明 | 必需字段 | 可选字段 |
|------|------|---------|---------|
| `story` | 普通剧情节点 | `type`, `content`, `next` | `effects`, `image` |
| `choice` | 选择节点 | `type`, `content`, `options` | `image` |
| `end` | 结束节点 | `type`, `content` | `effects` |

### 3.3 条件格式

**基础运算符**:
- `==`, `!=`: 相等/不等
- `>`, `>=`, `<`, `<=`: 比较运算
- `in`, `not_in`: 包含/不包含

**逻辑运算符**:
```json
{
  "and": [cond1, cond2, ...],  // 且
  "or": [cond1, cond2, ...]     // 或
}
```

**变量前缀**:
- `player_*`: 玩家属性 (如 `player_level`, `player_gold`)
- `story_*`: 剧情变量 (如 `story_has_key`)
- 无前缀: 简写剧情变量

### 3.4 跳转格式

**固定跳转**:
```json
"next": "node_id"
```

**条件跳转**:
```json
"next": [
  {"if": condition, "goto": "node_a"},
  {"if": condition, "goto": "node_b"},
  {"goto": "default_node"}
]
```

### 3.5 效果格式

```json
"effects": {
  "player": {
    "gold": "+500",     // 相对变化
    "level": 10         // 绝对值
  },
  "variables": {
    "has_key": true,
    "reputation": "+10"
  }
}
```

## 4. StoryEngine API

### 4.1 Core Methods

**`evaluate_condition(condition, player, variables) -> bool`**
- 评估条件是否满足
- 支持 and/or/嵌套逻辑
- 位置: `engine.py:67-112`

**`resolve_next(next_field, player, variables) -> Optional[str]`**
- 解析next字段,支持条件跳转
- 返回目标节点ID
- 位置: `engine.py:135-171`

**`apply_effects(effects, player, variables) -> Tuple[Player, Dict]`**
- 应用效果到玩家和变量
- 位置: `engine.py:173-199`

**`get_current_node(story_session, player) -> Optional[Dict]`**
- 获取当前节点信息
- 自动过滤条件不满足的选项
- 位置: `engine.py:264-294`

**`process_choice(story_session, player, choice_id) -> Tuple[bool, str, Optional[Dict]]`**
- 处理玩家选择
- 返回: (成功标志, 消息, 下一节点)
- 位置: `engine.py:296-333`

### 4.2 Helper Methods

**`_check_value(value, check) -> bool`**
- 检查单个值是否满足条件
- 位置: `engine.py:114-133`

**`format_content(content, player, variables) -> str`**
- 格式化内容,替换变量占位符
- 位置: `engine.py:218-262`

## 5. StorySession Model

### 5.1 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer | 主键 |
| `player_id` | Integer | 玩家ID |
| `story_id` | String | 剧情ID |
| `current_node` | String | 当前节点ID |
| `variables` | JSON | 剧情变量 |
| `is_active` | Boolean | 是否活跃 |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |

### 5.2 方法

**`get_active_session(session, player_id) -> Optional[StorySession]`**
- 获取玩家的活跃试炼会话
- 位置: `models/story_session.py`

**`create_session(session, player_id, story_id, start_node) -> StorySession`**
- 创建新的试炼会话
- 位置: `models/story_session.py`

**`get_variables() -> Dict`**
- 获取剧情变量字典
- 位置: `models/story_session.py`

**`set_variables(variables: Dict)`**
- 设置剧情变量
- 位置: `models/story_session.py`

## 6. Command Handlers

### 6.1 玩家命令

| 命令 | 说明 | 处理器位置 |
|------|------|----------|
| `【试炼列表】` | 显示可用剧情 | `interactive_story.py:35-61` |
| `【开始试炼 <id>】` | 开始指定剧情 | `interactive_story.py:64-101` |
| `【试炼状态】` | 查看当前进度 | `interactive_story.py:104-127` |
| `【退出试炼】` | 退出当前剧情 | `interactive_story.py:130-148` |
| `<数字>` | 选择选项 | `interactive_story.py:151-212` |
| `<任意消息>` | 继续剧情 | `interactive_story.py:215-282` |

## 7. Supported Player Attributes

### 7.1 基础属性

- `player_level`: 等级
- `player_exp`: 经验值
- `player_gold`: 金币
- `player_gold2`: 灵石
- `player_vip`: VIP等级

### 7.2 战斗属性

- `player_hp`: 当前生命
- `player_max_hp`: 最大生命
- `player_mp`: 当前法力
- `player_max_mp`: 最大法力
- `player_attack`: 攻击力
- `player_defense`: 防御力
- `player_agility`: 敏捷
- `player_stamina`: 耐力
- `player_luck`: 幸运

### 7.3 其他属性

- `player_x`, `player_y`: 当前坐标
- `player_guild_id`: 公会ID
- `player_attribute_points`: 属性点
- `player_sign_streak`: 连续签到天数

## 8. Variable Placeholders

### 8.1 文本中可用占位符

| 占位符 | 替换内容 |
|--------|---------|
| `{player_name}` | 玩家昵称 |
| `{player_uid}` | 玩家UID |
| `{player_level}` | 等级 |
| `{player_gold}` | 金币 |
| `{player_hp}` | 当前生命 |
| `{变量名}` | 剧情变量值 |

### 8.2 使用示例

```json
"content": "你好 {player_name},你的等级是 {player_level}。\n你拥有 {player_gold} 金币。"
```

## 9. Testing Reference

### 9.1 测试文件

- `plugins/xiuxian_game/story/test_core_logic.py` - 核心逻辑测试
- 8个测试全部通过,覆盖:
  - 简单条件
  - AND/OR逻辑
  - 嵌套条件
  - 固定/条件跳转

### 9.2 测试示例

```python
# 测试OR逻辑
condition = {
    "or": [
        {"player_level": {">=": 20}},
        {"player_gold": {">=": 10000}}
    ]
}
assert engine.evaluate_condition(condition, player, {}) == True
```

## 10. Extension Points

### 10.1 未来功能 (未实现)

- NOT运算符
- 变量引用 (变量值作为条件值)
- 函数式条件 (如 `has_item`)
- 条件结果缓存

### 10.2 自定义扩展

**添加新运算符**: 修改 `_check_value()` 方法 (`engine.py:114-133`)

**添加新变量类型**: 扩展 `evaluate_condition()` 中的变量解析逻辑 (`engine.py:94-111`)
