# 【焚金】系统实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `cultivate/core.py` 添加【焚金】命令，让玩家消耗金币换取修为（平方根曲线+等级联动，无每日限制）。

**Architecture:** 直接在现有 `core.py` 末尾追加命令处理器和常量，不新建文件或 Service。采用"session 内收集结果，session 外调用 finish()"模式，符合项目规范。

**Tech Stack:** NoneBot2, SQLAlchemy (safe_session), Python math 标准库

**Spec:** `docs/superpowers/specs/2026-03-15-fenjin-design.md`

---

## Chunk 1: 实现焚金命令

### Task 1: 在 core.py 末尾追加焚金命令

**Files:**
- Modify: `plugins/xiuxian_game/cultivate/core.py` (末尾追加)
- Modify: `plugins/xiuxian_game/player/help.py` (修炼系统帮助 + 完整帮助列表)

- [ ] **Step 1: 在 `core.py` 文件末尾追加焚金命令**

在 `plugins/xiuxian_game/cultivate/core.py` 的最末尾添加以下代码（在所有现有命令之后）：

```python
# ==================== 焚金 ====================
import math as _math

_FENJIN_MAX_AMOUNT = 10_000_000_000   # 单次上限100亿，防止 math.floor(inf) OverflowError

fenjin = on_command("焚金", block=True, priority=5)

@fenjin.handle()
async def handle_fenjin(event: MessageEvent, args: Message = CommandArg()):
    """焚金 — 消耗金币换取修为（平方根递减 + 等级联动）"""
    from ..platform_utils import get_unified_player
    from ..player.realm_utils import realm_by_level_and_reincarnation

    arg_text = args.extract_plain_text().strip()

    # 参数校验在 session 外部
    if not arg_text or not arg_text.isdigit():
        await fenjin.finish(
            "🔥 焚金仪式\n"
            "━━━━━━━━━━━━━\n"
            "用法：【焚金 <金额>】\n"
            "示例：【焚金 100000】【焚金 1000000】\n"
            "━━━━━━━━━━━━━\n"
            "消耗金币换取修为，边际收益递减\n"
            "等级越高，同等金币换取更多修为\n"
            "最低消耗：1,000 金币"
        )

    amount = int(arg_text)
    if amount < 1000:
        await fenjin.finish("⛔ 焚金最低消耗 1,000 金币")
    if amount > _FENJIN_MAX_AMOUNT:
        await fenjin.finish(f"⛔ 单次焚金上限为 {_FENJIN_MAX_AMOUNT:,} 金币")

    # 在 session 内收集结果，不调用 finish()
    error_msg = None
    result_msg = None

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            error_msg = "⛔ 请先使用【注册】命令创建角色"
        elif player.gold < amount:
            error_msg = (
                f"⛔ 金币不足\n"
                f"当前: {player.gold:,} 金币\n"
                f"需要: {amount:,} 金币"
            )
        else:
            # 计算修为
            # player.exp = 已积累修为（绝对值），exp_cap = 升级所需总修为（绝对值），同一量纲
            level_factor = 1.0 + (player.level / 100.0)
            exp_gain = _math.floor(
                _math.sqrt(amount / 1000) * 100 * level_factor
            )

            exp_cap = calculate_level_up_exp(player.level)
            exp_gain = min(exp_gain, max(0, exp_cap - player.exp))

            if exp_gain <= 0:
                error_msg = "⛔ 修为已满，请先使用【突破】提升境界"
            else:
                player.gold -= amount
                player.exp += exp_gain
                session.add(player)

                realm_name = realm_by_level_and_reincarnation(
                    player.level, player.reincarnation_level
                )
                result_msg = (
                    f"🔥 焚金仪式\n"
                    f"━━━━━━━━━━━━━\n"
                    f"消耗: {amount:,} 金币\n"
                    f"境界: {realm_name} Lv.{player.level}（等级加成 ×{level_factor:.1f}）\n"
                    f"获得修为: +{exp_gain:,}\n"
                    f"当前修为: {player.exp:,} / {exp_cap:,}\n"
                    f"━━━━━━━━━━━━━\n"
                    f"⚠️ 修为已积累，使用【突破】继续成长"
                )

    # session 关闭后再调用 finish()，避免连接泄漏
    if error_msg:
        await fenjin.finish(message_add_head(error_msg, event))
    await fenjin.finish(message_add_head(result_msg, event))
```

- [ ] **Step 2: 更新修炼系统帮助（`help.py`）**

在 `plugins/xiuxian_game/player/help.py` 找到修炼系统帮助处理器（`xiu_lian_cmd`），在其 msg 字符串中「怨念系统」区块后插入焚金说明：

```python
        "━━━━━━━━━━━━━\n"
        "🔥 焚金（通缩）：\n"
        "【焚金 金额】 消耗金币换取修为\n"
        "  边际递减：花越多钱，修为性价比越低\n"
        "  等级联动：高等级换取更多修为\n"
        "  无每日限制，最低消耗1000金币\n"
```

- [ ] **Step 3: 更新完整帮助系统列表（`_FULL_HELP_SYSTEMS`）**

在 `help.py` 的 `_FULL_HELP_SYSTEMS` 列表中，找到 `"修炼系统"` 那一项，在其命令列表中加入 `"【焚金 金额】"`：

当前：
```python
    ("修炼系统", "#8b5cf6", [
        "【修炼】 【闭关】 【出关】",
        "【突破】 【突破 镇厄/棺材钉】",
        "【加点 属性 点数】 【加点帮助】",
        "【献祭 材料 数量】",
        "【面板】 【战力】 【战力说明】",
    ]),
```

改为：
```python
    ("修炼系统", "#8b5cf6", [
        "【修炼】 【闭关】 【出关】",
        "【突破】 【突破 镇厄/棺材钉】",
        "【加点 属性 点数】 【加点帮助】",
        "【献祭 材料 数量】",
        "【焚金 金额】",
        "【面板】 【战力】 【战力说明】",
    ]),
```

- [ ] **Step 4: 提交**

```bash
git add plugins/xiuxian_game/cultivate/core.py plugins/xiuxian_game/player/help.py
git commit -m "feat(cultivate): 添加【焚金】命令 — 金币换修为通缩机制"
```
