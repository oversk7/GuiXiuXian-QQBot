# Battle UI Markdown 改版实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将所有战斗日志替换为 QQ 官方长文字展示模版（代码块可折叠），统一战斗 UI 风格，删除旧图片生成代码。

**Architecture:** 新建一个集中式 helper `battle/battle_markdown.py`，封装 `build_battle_markdown()` 函数；各战斗命令文件调用该函数替换原有 `"\n".join(result_lines)` 或图片生成逻辑；service 层不依赖 NoneBot2 `MessageSegment`。

**Tech Stack:** Python 3.10+, NoneBot2, nonebot-adapter-qq (`MessageSegment.markdown`, `MessageMarkdown`, `MessageMarkdownParams`), QQ 长文字展示模版 ID `102499345_1772280837`

**Spec:** `docs/superpowers/specs/2026-03-13-battle-ui-markdown-design.md`

---

## 文件变更总览

| 操作 | 文件 |
|------|------|
| **新建** | `plugins/xiuxian_game/battle/battle_markdown.py` |
| **删除** | `plugins/xiuxian_game/battle/battle_image.py` |
| **修改** | `plugins/xiuxian_game/battle/integration_helper.py` |
| **修改** | `plugins/xiuxian_game/battle/pvp_commands.py` |
| **修改** | `plugins/xiuxian_game/world/attack_command.py` |
| **修改** | `plugins/xiuxian_game/world_boss/service_new.py` |
| **修改** | `plugins/xiuxian_game/world_boss/__init__.py` |
| **修改** | `plugins/xiuxian_game/lower_world/commands.py` |
| **修改** | `plugins/xiuxian_game/inner_realm/service.py` |
| **修改** | `plugins/xiuxian_game/inner_realm/commands.py` |
| **检查（无需改动）** | `plugins/xiuxian_game/battle/__init__.py` |

---

## Chunk 1: Helper 函数 + 清理 integration_helper.py

### Task 1: 新建 `battle/battle_markdown.py`

**Files:**
- Create: `plugins/xiuxian_game/battle/battle_markdown.py`

- [ ] **Step 1: 新建文件，写入完整实现**

```python
"""
战斗 Markdown 构建助手

使用 QQ 官方长文字展示模版渲染战斗日志。
模版 ID：102499345_1772280837

约束：
  - desc 内不能包含 Markdown 特殊字符（# * _ [ ] ` > |）
  - 换行必须用 \r 而非 \n
"""
import re

from nonebot.adapters.qq import MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams

BATTLE_TEMPLATE_ID = "102499345_1772280837"

_SANITIZE_RE = re.compile(r'[#*_\[\]`>|]')


def _sanitize_desc(text: str) -> str:
    """移除 Markdown 特殊字符，并将所有换行统一为 \\r"""
    text = text.replace('\n', '\r')
    text = _SANITIZE_RE.sub('', text)
    return text


def build_battle_markdown(
    title: str,
    battle_log: list,
    hint: str,
    btn1: str,
    btn2: str,
    btn3: str,
) -> MessageSegment:
    """
    构建战斗长文字 Markdown 消息段。

    Args:
        title:      模版标题（显示在代码块上方）
        battle_log: 战斗日志行列表，各行用 \\r 连接后放入代码块
        hint:       底部提示文字
        btn1/2/3:   三个快捷按钮文字

    Returns:
        MessageSegment，可直接 await cmd.finish(segment)
    """
    # 将各行用 \r 连接，并对行内可能存在的 \n 也替换为 \r
    raw = '\r'.join(str(line).replace('\n', '\r') for line in battle_log)
    desc = _sanitize_desc(raw)

    params = [
        MessageMarkdownParams(key="title", values=[title]),
        MessageMarkdownParams(key="desc",  values=[desc]),
        MessageMarkdownParams(key="hint",  values=[hint]),
        MessageMarkdownParams(key="t1",    values=[btn1]),
        MessageMarkdownParams(key="t2",    values=[btn2]),
        MessageMarkdownParams(key="t3",    values=[btn3]),
    ]
    markdown = MessageMarkdown(custom_template_id=BATTLE_TEMPLATE_ID, params=params)
    return MessageSegment.markdown(markdown)
```

- [ ] **Step 2: 验证语法**

```bash
python -c "from plugins.xiuxian_game.battle.battle_markdown import build_battle_markdown; print('OK')"
```

期望输出：`OK`（无 ImportError）

- [ ] **Step 3: Commit**

```bash
git add plugins/xiuxian_game/battle/battle_markdown.py
git commit -m "feat: 新建 battle_markdown helper，封装 QQ 长文字展示模版构建逻辑"
```

---

### Task 2: 清理 `battle/integration_helper.py` 的 battle_image 导入块

**Files:**
- Modify: `plugins/xiuxian_game/battle/integration_helper.py:12-16`

- [ ] **Step 1: 确认当前第 12-16 行内容**

读取文件确认第 12-16 行为：
```python
try:
    from .battle_image import get_battle_image_generator, should_use_image
    IMAGE_SUPPORT = True
except ImportError:
    IMAGE_SUPPORT = False
```

- [ ] **Step 2: 删除这 5 行**

将以上 5 行完整删除（不留空行替换）。

- [ ] **Step 3: 确认 `IMAGE_SUPPORT` 在该文件中无其他引用**

在 `integration_helper.py` 中搜索 `IMAGE_SUPPORT`，确认无其他出现位置后才删除。

- [ ] **Step 4: Commit**

```bash
git add plugins/xiuxian_game/battle/integration_helper.py
git commit -m "refactor: 删除 integration_helper.py 中的 battle_image try/except 导入块"
```

---

## Chunk 2: 修改 pvp_commands.py + 删除 battle_image.py

### Task 3: 修改 `battle/pvp_commands.py`

**Files:**
- Modify: `plugins/xiuxian_game/battle/pvp_commands.py`

涉及 3 处改动：删除旧导入、修改 `handle_pvp()`、修改 `handle_simulate()`。

- [ ] **Step 1: 修改文件顶部导入（第 7 行和第 18 行）**

删除：
```python
import base64
```
（第 7 行）

删除：
```python
from .battle_image import get_battle_image_generator
```
（第 18 行）

在第 17 行（`from .integration_helper import BattleIntegrationHelper`）下方新增：
```python
from .battle_markdown import build_battle_markdown
```

- [ ] **Step 2: 修改 `handle_pvp()` — 替换图片生成逻辑（原第 113-131 行）**

删除：
```python
            # 生成战斗图片
            gen = get_battle_image_generator()
            img_bytes = gen.generate_battle_image(
                battle_log=battle_log,
                player1_name=f"{challenger.nickname}[{challenger.uid}]",
                player2_name=f"{target_player.nickname}[{target_player.uid}]",
                player1_level=challenger.level,
                player2_level=target_player.level,
                player1_hp=p1_final_hp,
                player1_max_hp=challenger.max_hp,
                player2_hp=p2_final_hp,
                player2_max_hp=target_player.max_hp,
                winner_name=winner_name,
            )

            img_b64 = base64.b64encode(img_bytes).decode()
            msg = message_add_head("⚔️ 战斗结束，查看图片获取详情", event)
            msg.append(MessageSegment.file_image(img_b64))
            await pvp_cmd.finish(msg)
```

替换为：
```python
            title = f"⚔️ 切磋结果 · {challenger.nickname} vs {target_player.nickname}"
            await pvp_cmd.finish(build_battle_markdown(
                title=title,
                battle_log=battle_log,
                hint="快捷操作: 切磋 | 面板 | 战力",
                btn1="切磋",
                btn2="面板",
                btn3="战力",
            ))
```

- [ ] **Step 3: 修改 `handle_simulate()` — 替换图片生成逻辑（原第 212-230 行）**

删除：
```python
            # 生成战斗图片
            gen = get_battle_image_generator()
            img_bytes = gen.generate_battle_image(
                battle_log=battle_log,
                player1_name=f"{player1.nickname}[{player1.uid}]",
                player2_name=f"{player2.nickname}[{player2.uid}]",
                player1_level=player1.level,
                player2_level=player2.level,
                player1_hp=p1_final_hp,
                player1_max_hp=player1.max_hp,
                player2_hp=p2_final_hp,
                player2_max_hp=player2.max_hp,
                winner_name=winner_name,
            )

            img_b64 = base64.b64encode(img_bytes).decode()
            msg = message_add_head("🎮 模拟战斗结束，查看图片获取详情", event)
            msg.append(MessageSegment.file_image(img_b64))
            await simulate_cmd.finish(msg)
```

替换为：
```python
            title = f"🎮 模拟战斗 · {player1.nickname} vs {player2.nickname}"
            await simulate_cmd.finish(build_battle_markdown(
                title=title,
                battle_log=battle_log,
                hint="快捷操作: 切磋 | 面板 | 战力",
                btn1="切磋",
                btn2="面板",
                btn3="战力",
            ))
```

- [ ] **Step 4: 确认 `MessageSegment` 导入是否仍需要**

检查 `pvp_commands.py` 中其他地方是否还使用 `MessageSegment`。如果只有已删除的 `MessageSegment.file_image(img_b64)` 使用了它，则将顶部导入行：
```python
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
```
改为：
```python
from nonebot.adapters.qq import MessageEvent, Message
```

- [ ] **Step 5: Commit**

```bash
git add plugins/xiuxian_game/battle/pvp_commands.py
git commit -m "feat: pvp_commands 切磋/模拟战斗改用 QQ 长文字 Markdown 展示，删除图片生成逻辑"
```

---

### Task 4: 删除 `battle/battle_image.py` + 检查 `battle/__init__.py`

**Files:**
- Delete: `plugins/xiuxian_game/battle/battle_image.py`
- Verify: `plugins/xiuxian_game/battle/__init__.py`

- [ ] **Step 1: 搜索全项目确认无其他文件导入 `battle_image`**

```bash
grep -r "battle_image" plugins/ --include="*.py"
```

期望：无任何结果（所有导入已在前面步骤中删除）

- [ ] **Step 2: 检查 `battle/__init__.py` 是否有 battle_image 导出**

读取 `plugins/xiuxian_game/battle/__init__.py`，确认无 `battle_image` 相关导出（根据已知信息该文件不含此导出，无需修改）。

- [ ] **Step 3: 删除文件**

```bash
git rm plugins/xiuxian_game/battle/battle_image.py
```

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor: 删除 battle_image.py，完全移除图片生成功能"
```

---

## Chunk 3: 修改 `world/attack_command.py`

### Task 5: 修改 `world/attack_command.py` — 6 个 finish() 路径

**Files:**
- Modify: `plugins/xiuxian_game/world/attack_command.py`

该文件从代码角度有 **4 处** `finish()` 调用需要修改，对应规格所述的 **6 种战斗类型**（城镇切磋、荒野死斗、诡域死斗三种 PvP 类型共享同一处代码路径 Step 4，只需修改一次）：

| 规格路径 | 代码路径 |
|---------|---------|
| 镜怨体质前置判定 | Step 2（路径 1）|
| 龙影闪前置判定 | Step 3（路径 2）|
| 城镇切磋 / 荒野死斗 / 诡域死斗 | Step 4（路径 3，统一处理，`battle_type` 变量区分标题）|
| PvE NPC 攻击 | Step 5（路径 4）|

- [ ] **Step 1: 在文件顶部添加导入**

在 `from ..utils import message_add_head` 附近添加：
```python
from ..battle.battle_markdown import build_battle_markdown
```

- [ ] **Step 2: 修改路径 1 — 镜怨体质前置判定（约第 585 行）**

找到：
```python
            await attack_cmd.finish(message_add_head("\n".join(result_lines), event))
```
（位于镜怨体质 `try/except (ValueError, SQLAlchemyError)` 块后、龙影闪判定前）

替换为：
```python
            await attack_cmd.finish(build_battle_markdown(
                title=f"⚔️ 战斗结果 · {attacker.nickname} vs {target.nickname}",
                battle_log=result_lines,
                hint="快捷操作: 探索 | 面板 | 背包",
                btn1="探索",
                btn2="面板",
                btn3="背包",
            ))
```

**注意**：此处 `result_lines` 仅含前置判定文本（无 `battle_log`），直接作为 desc 传入。

- [ ] **Step 3: 修改路径 2 — 龙影闪前置判定（约第 663 行）**

找到第二个：
```python
            await attack_cmd.finish(message_add_head("\n".join(result_lines), event))
```
（位于龙影闪 `try/except (ValueError, SQLAlchemyError)` 块后、`# 执行PVP战斗` 注释前）

替换为：
```python
            await attack_cmd.finish(build_battle_markdown(
                title=f"⚔️ 战斗结果 · {attacker.nickname} vs {target.nickname}",
                battle_log=result_lines,
                hint="快捷操作: 探索 | 面板 | 背包",
                btn1="探索",
                btn2="面板",
                btn3="背包",
            ))
```

- [ ] **Step 4: 修改路径 3 — PvP 主战斗结果（约第 945 行）**

找到：
```python
        await attack_cmd.finish(message_add_head("\n".join(result_lines), event))
```
（位于成就检查 `result_lines.extend(achievement_msgs)` 之后、`except ValueError` 之前）

此处 `result_lines` 已包含：`battle_type` 标题行、玩家信息行、`battle_log` 内容、分割线、伤害/掉落/任务/成就信息。
`battle_type` 变量在本代码块内已定义（"🏘️ 城镇切磋" / "⚔️ 荒野死斗" / "👹 诡域死斗"）。

替换为：
```python
        await attack_cmd.finish(build_battle_markdown(
            title=f"{battle_type} · {attacker.nickname} vs {target.nickname}",
            battle_log=result_lines,
            hint="快捷操作: 探索 | 面板 | 背包",
            btn1="探索",
            btn2="面板",
            btn3="背包",
        ))
```

- [ ] **Step 5: 修改路径 4 — PvE NPC 攻击结果（约第 1291 行）**

找到：
```python
        await attack_cmd.finish(message_add_head("\n".join(result_lines), event))
```
（位于 `handle_npc_attack` 函数末尾，成就检查之后，`except ValueError` 之前）

此处 `result_lines` 已包含完整战斗日志。`target_npc.name` 在函数签名中可用。

替换为：
```python
        await attack_cmd.finish(build_battle_markdown(
            title=f"⚔️ 战斗结果 · {attacker.nickname} vs {target_npc.name}",
            battle_log=result_lines,
            hint="快捷操作: 探索 | 面板 | 背包",
            btn1="探索",
            btn2="面板",
            btn3="背包",
        ))
```

- [ ] **Step 6: Commit**

```bash
git add plugins/xiuxian_game/world/attack_command.py
git commit -m "feat: attack_command 所有战斗结果改用 QQ 长文字 Markdown 展示"
```

---

## Chunk 4: 修改 world_boss

### Task 6: 修改 `world_boss/service_new.py` + `world_boss/__init__.py`

**Files:**
- Modify: `plugins/xiuxian_game/world_boss/service_new.py:365-466`
- Modify: `plugins/xiuxian_game/world_boss/__init__.py:71-95`

**设计说明**：
- `attack_boss()` 目前返回 `(bool, str)`。`ok=False` 返回短错误字符串，`ok=True` 返回已 join 的结果字符串，但 `battle_log` 未包含在内。
- 修改后：`ok=True` 时返回 `(True, list[str])`（包含 battle_log + 摘要行）；`ok=False` 时返回 `(False, list[str])`（单行错误文字）。
- `__init__.py` 根据 `ok` 决定使用 Markdown 还是纯文本。

- [ ] **Step 1: 修改 `service_new.py` 中 `attack_boss()` 的所有早期 `return False` 路径**

将全部 `return False, "..."` 改为 `return False, ["..."]`（共 4 处）：

```python
# 原：
return False, f"⛔ 今日攻击次数已用完！明日20:00重置（...）"
# 改：
return False, [f"⛔ 今日攻击次数已用完！明日20:00重置（...）"]

# 原：
return False, f"⏰ 攻击冷却中，请等待 {remaining} 秒"
# 改：
return False, [f"⏰ 攻击冷却中，请等待 {remaining} 秒"]

# 原：
return False, "💀 你已重伤倒地，无法参与战斗！请先恢复生命值"
# 改：
return False, ["💀 你已重伤倒地，无法参与战斗！请先恢复生命值"]
```

（具体错误文本以实际代码为准，所有 `return False, "..."` 均需改为 `return False, ["..."]`）

- [ ] **Step 2: 修改 `attack_boss()` 末尾的 `ok=True` 返回（约第 466 行）**

找到：
```python
        return True, "\n".join(lines)
```

将其替换为（在 `lines.append(random.choice(flavor_texts))` 之后）：
```python
        # 组合完整战斗内容：battle_log + 分割线 + 摘要
        full_lines = list(battle_log) + ["━━━━━━━━━━━━━"] + lines
        return True, full_lines
```

同时更新函数签名注释（docstring Returns 部分）：
```python
    Returns:
        (是否成功, 结果行列表)
        ok=True:  list[str]，包含完整 battle_log 与摘要行
        ok=False: list[str]，单行错误文字
```

- [ ] **Step 3: 修改 `world_boss/__init__.py` 中 `handle_attack()` 函数（第 71-95 行）**

在文件顶部导入区添加：
```python
from ..battle.battle_markdown import build_battle_markdown
```

找到 `handle_attack()` 内的结果处理部分：
```python
        cycle, tip = await service.check_and_refresh_cycle()
        ok, reply = await service.attack_boss(cycle, player)
        if tip:
            reply = tip + "\n" + reply
        await attack_cmd.finish(message_add_head(reply, event))
```

替换为：
```python
        cycle, tip = await service.check_and_refresh_cycle()
        ok, lines = await service.attack_boss(cycle, player)
        if ok:
            if tip:
                lines = [tip, "━━━━━━━━━━━━━"] + lines
            await attack_cmd.finish(build_battle_markdown(
                title=f"🌑 讨伐结果 · {cycle.boss_name}",
                battle_log=lines,
                hint="快捷操作: 讨伐BOSS | BOSS排行 | 面板",
                btn1="讨伐BOSS",
                btn2="BOSS排行",
                btn3="面板",
            ))
        else:
            reply = "\n".join(lines)
            if tip:
                reply = tip + "\n" + reply
            await attack_cmd.finish(message_add_head(reply, event))
```

- [ ] **Step 4: Commit**

```bash
git add plugins/xiuxian_game/world_boss/service_new.py plugins/xiuxian_game/world_boss/__init__.py
git commit -m "feat: 世界BOSS讨伐结果改用 QQ 长文字 Markdown 展示，包含完整战斗日志"
```

---

## Chunk 5: 修改 `lower_world/commands.py`

### Task 7: 修改 `lower_world/commands.py` — 迎战胜负结果

**Files:**
- Modify: `plugins/xiuxian_game/lower_world/commands.py`

**设计说明**：
- 胜利路径（约第 517-529 行）：当前将 `battle_log` 与叙事文本拼接为单个字符串 `msg`。
- 失败路径（约第 660-670 行）：同上。
- 修改方案：构建一个 `log_lines` 列表（含 battle_log + 叙事文字），传入 `build_battle_markdown()`。

- [ ] **Step 1: 在文件顶部添加导入**

在文件现有导入区找到合适位置，添加：
```python
from ..battle.battle_markdown import build_battle_markdown
```

- [ ] **Step 2: 修改胜利路径（约第 517-529 行）**

找到：
```python
            msg = (
                "\n".join(battle_log) + "\n"
                "\n"
                "━━━━━━━━━━━━━\n"
                + random.choice(victory_endings) + "\n"
                "\n"
                f"+{points}天灾点（当前：{stronghold.calamity_points}点）\n"
                "「大都会那边有人因此平安了。\n"
                " 他们不知道你的名字。」\n"
                "\n"
                f"⏳ 下一波英雄将于 {WAVE_INTERVAL_HOURS} 小时后到达"
            )
            await battle_hero_cmd.finish(msg)
```

替换为：
```python
            victory_ending = random.choice(victory_endings)
            log_lines = list(battle_log) + [
                "━━━━━━━━━━━━━",
                victory_ending,
                "",
                f"+{points}天灾点（当前：{stronghold.calamity_points}点）",
                "「大都会那边有人因此平安了。",
                " 他们不知道你的名字。」",
                "",
                f"⏳ 下一波英雄将于 {WAVE_INTERVAL_HOURS} 小时后到达",
            ]
            await battle_hero_cmd.finish(build_battle_markdown(
                title=f"🏰 迎战结果 · {hero['name']}",
                battle_log=log_lines,
                hint="快捷操作: 迎战 | 镇守 | 天灾商店",
                btn1="迎战",
                btn2="镇守",
                btn3="天灾商店",
            ))
```

**注意**：`victory_endings` 列表中的叙事文字包含 `\n`，`build_battle_markdown()` 内部会将其替换为 `\r`，并且 `_sanitize_desc()` 会剥离其中的 Markdown 特殊字符。叙事文字本身无 Markdown 语法字符，这是安全的。

- [ ] **Step 3: 修改失败路径（约第 660-670 行）**

找到：
```python
            msg = (
                "\n".join(battle_log) + "\n"
                "\n"
                "━━━━━━━━━━━━━\n"
                "你倒下了。\n"
                "\n"
                + random.choice(defeat_endings) + "\n"
                "\n"
                "⛓️ 你被封印24小时"
            )
            await battle_hero_cmd.finish(msg)
```

替换为：
```python
            defeat_ending = random.choice(defeat_endings)
            log_lines = list(battle_log) + [
                "━━━━━━━━━━━━━",
                "你倒下了。",
                "",
                defeat_ending,
                "",
                "⛓️ 你被封印24小时",
            ]
            await battle_hero_cmd.finish(build_battle_markdown(
                title=f"🏰 迎战结果 · {hero['name']}",
                battle_log=log_lines,
                hint="快捷操作: 迎战 | 镇守 | 天灾商店",
                btn1="迎战",
                btn2="镇守",
                btn3="天灾商店",
            ))
```

- [ ] **Step 4: Commit**

```bash
git add plugins/xiuxian_game/lower_world/commands.py
git commit -m "feat: 下位世界迎战结果改用 QQ 长文字 Markdown 展示"
```

---

## Chunk 6: 修改 inner_realm

### Task 8: 修改 `inner_realm/service.py` — `start_battle_with_npc()` 返回结构化数据

**Files:**
- Modify: `plugins/xiuxian_game/inner_realm/service.py:1558-1667`

**设计说明**：
- 当前 `start_battle_with_npc()` 返回 `(victory, full_message: str, rewards)`。
- 修改为返回 `(victory, log_lines: list[str], result_lines: list[str], rewards)`。
- 调用方 `perform_intimidation()` 和 `perform_assassination()` 将 `log_lines + result_lines` 用 `"\n".join()` 合并为字符串，维持原有字符串拼接行为。
- 直接调用方 `attack_cmd`（在 `inner_realm/commands.py`）改为使用 `build_battle_markdown()`。

- [ ] **Step 1: 修改 `start_battle_with_npc()` 函数签名和返回值**

找到函数末尾（约第 1664-1667 行）：
```python
        # 组合完整战斗消息
        full_message = "\n".join(battle_log) + "\n" + "\n".join(result_lines)

        return victory, full_message, rewards
```

替换为：
```python
        # 返回结构化数据，由命令层决定如何展示
        return victory, list(battle_log), result_lines, rewards
```

同时更新函数 docstring 的 Returns 部分：
```python
    Returns:
        (是否胜利, 战斗日志行列表, 结果行列表, 战斗奖励)
```

- [ ] **Step 2: 修改 `perform_intimidation()` 中调用 `start_battle_with_npc()` 的位置（共 2 处）**

**第一处**（约第 245 行，大失败·伪装者暴露）：

找到：
```python
                victory, battle_result, rewards = await self.start_battle_with_npc(
                    player, tile, session
                )

                return victory, f"{battle_msg}\n\n{battle_result}"
```

替换为：
```python
                victory, log_lines, res_lines, rewards = await self.start_battle_with_npc(
                    player, tile, session
                )
                battle_result = "\n".join(log_lines + res_lines)

                return victory, f"{battle_msg}\n\n{battle_result}"
```

**第二处**（约第 270 行，失败·特殊NPC反击）：

找到：
```python
                victory, battle_result, rewards = await self.start_battle_with_npc(
                    player, tile, session
                )

                return victory, f"{battle_msg}\n\n{battle_result}"
```

替换为：
```python
                victory, log_lines, res_lines, rewards = await self.start_battle_with_npc(
                    player, tile, session
                )
                battle_result = "\n".join(log_lines + res_lines)

                return victory, f"{battle_msg}\n\n{battle_result}"
```

- [ ] **Step 3: 修改 `perform_assassination()` 中调用 `start_battle_with_npc()` 的位置（1 处）**

找到（约第 386 行）：
```python
            victory, battle_result, rewards = await self.start_battle_with_npc(
                player, tile, session
            )

            return victory, f"{battle_msg}\n\n{battle_result}"
```

替换为：
```python
            victory, log_lines, res_lines, rewards = await self.start_battle_with_npc(
                player, tile, session
            )
            battle_result = "\n".join(log_lines + res_lines)

            return victory, f"{battle_msg}\n\n{battle_result}"
```

- [ ] **Step 4: Commit**

```bash
git add plugins/xiuxian_game/inner_realm/service.py
git commit -m "refactor: inner_realm start_battle_with_npc 改为返回结构化数据(log_lines, result_lines)"
```

---

### Task 9: 修改 `inner_realm/commands.py` — attack_cmd 使用 Markdown

**Files:**
- Modify: `plugins/xiuxian_game/inner_realm/commands.py:541-545`

- [ ] **Step 1: 在文件顶部添加导入**

在现有导入区找到合适位置，添加：
```python
from ..battle.battle_markdown import build_battle_markdown
```

- [ ] **Step 2: 修改 `handle_attack()` 中使用 `start_battle_with_npc()` 的部分（约第 541-545 行）**

找到：
```python
        # 发起战斗
        victory, message, rewards = await service.start_battle_with_npc(
            player, current_tile, active_session
        )

        await attack_cmd.finish(message)
```

替换为：
```python
        # 发起战斗
        victory, log_lines, res_lines, rewards = await service.start_battle_with_npc(
            player, current_tile, active_session
        )

        await attack_cmd.finish(build_battle_markdown(
            title="🌀 内界战斗结果",
            battle_log=log_lines + res_lines,
            hint="快捷操作: 攻击 | 里界信息 | 返回",
            btn1="攻击",
            btn2="里界信息",
            btn3="返回",
        ))
```

**注意**：规格文件中按钮为 `探索 | 试炼状态 | 退出试炼`，但里界系统实际命令为 `攻击`、`里界信息`、`返回`，此处以实际命令为准。

- [ ] **Step 3: Commit**

```bash
git add plugins/xiuxian_game/inner_realm/commands.py
git commit -m "feat: inner_realm 攻击战斗结果改用 QQ 长文字 Markdown 展示"
```

---

## 验证清单

完成所有 Task 后，启动 bot 逐一测试以下命令：

- [ ] 发送 `切磋 <UID>` — 应收到 Markdown 模版消息（代码块含战斗日志，底部有三个按钮）
- [ ] 发送 `模拟战斗 <UID1> <UID2>` — 同上
- [ ] 在荒野/诡域发送 `攻击 <目标>` — Markdown 展示（荒野/诡域死斗或NPC）
- [ ] 发送 `讨伐BOSS` — Markdown 展示（含完整战斗日志）
- [ ] 发送 `迎战` — Markdown 展示（含叙事文字）
- [ ] 里界内发送 `攻击` — Markdown 展示
- [ ] 确认 `诡域探索战斗` 不受影响（维持原有反馈类 Markdown 模版）
- [ ] 全局搜索确认无任何文件还在导入 `battle_image`

```bash
grep -r "battle_image" plugins/ --include="*.py"
```

期望：无任何结果
