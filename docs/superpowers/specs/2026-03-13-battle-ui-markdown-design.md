# 战斗 UI 长文字 Markdown 模版改版设计

**日期：** 2026-03-13
**状态：** 已批准，待实施
**影响范围：** 5 个战斗命令文件 + 1 个新增 helper + 1 个删除文件

---

## 背景

将所有战斗日志改用 QQ 官方"长文字展示模版"（代码块可折叠展开），统一战斗 UI 风格，提升可读性。用户可点击代码块展开完整战斗过程。

---

## 使用的模版

**长文字展示模版**
模版 ID：`102499345_1772280837`

```
# {{.title}}
```bash
{{.desc}}
```
***
> {{.hint}} <qqbot-cmd-input text="{{.t1}}" /> <qqbot-cmd-input text="{{.t2}}" /> <qqbot-cmd-input text="{{.t3}}" />
```

**模版参数规范：**
- `{{.desc}}` 内不能包含 Markdown 语法（`#` `*` `_` 等）
- 换行符必须使用 `\r` 而非 `\n`

---

## 不在本次改版范围内

- **诡域探索战斗**（`world/dungeon_battle.py`）：已使用反馈类模版（`102499345_1769177016`，含 8 个方向按钮），维持现状

---

## 架构设计

### 新建 Helper 文件

**路径：** `plugins/xiuxian_game/battle/battle_markdown.py`

```python
def build_battle_markdown(
    title: str,            # 战斗标题
    battle_log: list[str], # 战斗日志行列表
    hint: str,             # 提示文字（快捷操作说明）
    btn1: str,             # 快捷按钮1
    btn2: str,             # 快捷按钮2
    btn3: str,             # 快捷按钮3
) -> MessageSegment        # 返回可直接附加到 Message 的 segment
```

**实现要点：**
1. 将 `battle_log` 用 `\r` 连接
2. 剥离 desc 内的 Markdown 特殊字符（`#` `*` `_` `[` `]` 等）
3. 使用 `MessageMarkdown(custom_template_id="102499345_1772280837", params=[...])`
4. 不做主动字符截断（长文字模版专为此设计）

### 删除的文件

- `plugins/xiuxian_game/battle/battle_image.py`（整个文件删除）
- 同步删除所有对该文件的导入引用

---

## 各命令修改详情

### 1. `battle/pvp_commands.py` — 切磋 / 模拟战斗

**修改内容：**
- 删除 `from .battle_image import get_battle_image_generator` 导入
- 删除图片生成代码块（`gen.generate_battle_image(...)` 等约 20 行）
- 替换为调用 `build_battle_markdown()`

**标题格式：**

| 命令 | title |
|------|-------|
| 切磋 | `⚔️ 切磋结果 · {挑战者昵称} vs {被挑战者昵称}` |
| 模拟战斗 | `🎮 模拟战斗 · {玩家1昵称} vs {玩家2昵称}` |

**按钮：** `切磋` / `面板` / `战力`
**hint：** `快捷操作: 切磋 | 面板 | 战力`

---

### 2. `world/attack_command.py` — 攻击命令（PvE + PvP）

**修改内容：**
- 当前 `result_lines` 构建完后，改用 `build_battle_markdown()` 发送
- PvP 切磋、荒野死斗、诡域死斗使用不同标题

**标题格式：**

| 战斗类型 | title |
|---------|-------|
| 攻击 NPC | `⚔️ 战斗结果 · {玩家昵称} vs {NPC名}` |
| 城镇切磋 | `🏘️ 城镇切磋 · {攻击者} vs {防守者}` |
| 荒野死斗 | `⚔️ 荒野死斗 · {攻击者} vs {防守者}` |
| 诡域死斗 | `👹 诡域死斗 · {攻击者} vs {防守者}` |

**按钮：** `探索` / `面板` / `背包`
**hint：** `快捷操作: 探索 | 面板 | 背包`

---

### 3. `world_boss/__init__.py` — 讨伐世界 BOSS

**修改内容：**
- 讨伐结果改为 `build_battle_markdown()` 发送

**标题格式：** `🌑 讨伐结果 · {BOSS名}`
**按钮：** `讨伐BOSS` / `BOSS排行` / `面板`
**hint：** `快捷操作: 讨伐BOSS | BOSS排行 | 面板`

---

### 4. `lower_world/commands.py` — 迎战

**修改内容：**
- `"\n".join(battle_log)` 改为 `build_battle_markdown()` 发送

**标题格式：** `🏰 迎战结果 · {英雄名}`
**按钮：** `迎战` / `镇守` / `天灾商店`
**hint：** `快捷操作: 迎战 | 镇守 | 天灾商店`

---

### 5. `inner_realm/service.py` — 内界战斗

**架构约束：** service 层不得依赖 NoneBot2 的 `MessageSegment`（违反分层原则）。且 `start_battle_with_npc()` 的返回值被 `perform_intimidation()`、`perform_assassination()` 等方法以字符串拼接方式使用，不能直接变为 `MessageSegment`。

**修改方案：service 层改为返回结构化数据，命令层构建 Markdown。**

**service 层改动：**
- `start_battle_with_npc()` 返回值从 `(victory, full_message: str, rewards)` 改为 `(victory, log_lines: list[str], result_lines: list[str], rewards)`
- 不再在 service 层 `join` 战斗日志

**命令层改动（`inner_realm/commands.py`）：**
- 接收 `log_lines` 和 `result_lines`，合并后调用 `build_battle_markdown()`

**上层调用方同步调整（`perform_intimidation`、`perform_assassination` 等）：**
- 这些方法内部以字符串拼接方式使用 `battle_result`，需改为先合并 `log_lines + result_lines` 后 `"\r".join()`，或改为在 service 层仅提供字符串摘要供拼接

**标题格式：** `🌀 内界战斗结果`
**按钮：** `探索` / `试炼状态` / `退出试炼`
**hint：** `快捷操作: 探索 | 试炼状态 | 退出试炼`

---

## 实施顺序

1. 新建 `battle/battle_markdown.py`（helper 函数）
2. 修改 `battle/pvp_commands.py`（删图片逻辑，改模版）
3. 修改 `battle/integration_helper.py`（删除 `battle_image` 的 `try/except ImportError` 块及 `IMAGE_SUPPORT` 相关代码）
4. 删除 `battle/battle_image.py`
5. 修改 `world/attack_command.py`（共 6 个 `finish()` 路径：PvE、城镇切磋、荒野死斗、诡域死斗、镜怨体质前置判定、龙影闪前置判定）
6. 修改 `world_boss/__init__.py`
7. 修改 `lower_world/commands.py`
8. 修改 `inner_realm/service.py` + 命令层（见下方架构说明）
9. 检查 `battle/__init__.py` 中是否有对 `battle_image` 的导出，有则删除

---

## 不改动的内容

- 诡域探索战斗（`dungeon_battle.py`）
- 战斗引擎逻辑（`enhanced_engine.py`、`integration_helper.py` 的战斗计算部分，只删图片相关代码）
- 所有非战斗相关的 UI 模块
- 试炼系统的文字交互（非战斗节点）

---

## 风险与注意事项

1. **`attack_command.py` 有 6 个 `finish()` 路径**，需逐一修改，避免遗漏：PvE、城镇切磋、荒野死斗、诡域死斗、镜怨体质前置判定、龙影闪前置判定。

2. **hint 中的 `|` 分隔符**：在 QQ Markdown 引用块内使用 `|` 通常不触发表格语法，可以使用。若渲染异常，备用方案是改用 `·` 或 `丨`（全角竖线）。

3. **`lower_world/commands.py` 叙事文案**：胜败结局的随机叙事文字需追加到 `battle_log` 列表末尾，与战斗日志一同放入 `desc` 字段。

4. **`build_battle_markdown()` 的换行处理**：不仅需对各行间用 `\r` 连接，还需将行内可能存在的 `\n`（如 `drop_msg`）也替换为 `\r`，防止混用。
