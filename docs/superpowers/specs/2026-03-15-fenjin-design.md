# 【焚金】系统设计文档

**日期**: 2026-03-15
**状态**: 已确认
**设计目标**: 为高级玩家提供主动消耗金币的途径，缓解金币通货膨胀

---

## 1. 背景与目标

游戏中金币长期存在通货膨胀压力，高级玩家财富积累过多，缺乏有效的消耗途径。【焚金】系统提供一个**主动命令**，让玩家用金币换取修为，核心是：

- **通缩优先**：消耗金币是主要目的，修为获取是奖励
- **高级玩家导向**：转化效率随等级提升，对高等级玩家更具吸引力
- **无封顶黑洞**：无每日限制，随时可用，高级玩家可以持续投入

---

## 2. 功能设计

### 2.1 命令格式

```
【焚金 <金额>】
```

**示例**：
- `【焚金 100000】` — 消耗10万金币，换取修为
- `【焚金 1000000】` — 消耗100万金币，换取修为

### 2.2 转化公式

```python
import math

BASE_COST_PER_EXP = 1000   # 基础每修为金币成本
BASE_EXP_UNIT = 100        # 基准修为单位

level_factor = 1.0 + (player.level / 100.0)   # 等级加成系数
exp_gain = math.floor(
    math.sqrt(amount / BASE_COST_PER_EXP) * BASE_EXP_UNIT * level_factor
)
```

**效果示例（不同等级消耗100万金币）**：

| 玩家等级 | level_factor | 获得修为 |
|----------|--------------|----------|
| 10级     | 1.1          | 11,000   |
| 50级     | 1.5          | 15,000   |
| 100级    | 2.0          | 20,000   |
| 300级    | 4.0          | 40,000   |
| 1000级   | 11.0         | 110,000  |

**效果示例（100级玩家消耗不同金额）**：

| 消耗金币    | 获得修为 | 平均金/修为 |
|-------------|----------|-------------|
| 10,000      | 2,000    | 5           |
| 100,000     | 6,324    | 15.8        |
| 1,000,000   | 20,000   | 50          |
| 10,000,000  | 63,245   | 158         |
| 100,000,000 | 200,000  | 500         |

> **边际递减**：花越多钱，平均每修为的成本越高，从而形成持续的通缩黑洞。

### 2.3 限制条件

| 条件 | 值 |
|------|-----|
| 最低消耗金额 | 1,000 金币 |
| 每日限制 | 无限制 |
| 修为上限 | 不超过当前级别升级所需修为（不能超过满修为） |
| 突破触发 | **不自动突破**，仅积累修为，需手动【突破】 |

### 2.4 消息格式

成功时：
```
🔥 焚金仪式
━━━━━━━━━━━━━
消耗: 1,000,000 金币
境界: 血咒境 Lv.50（等级加成 ×1.5）
获得修为: +15,000
当前修为: 45,000 / 90,000
━━━━━━━━━━━━━
⚠️ 修为已积累，使用【突破】继续成长
```

失败时（金币不足）：
```
⛔ 金币不足，当前: 500 金币，需要至少: 1,000 金币
```

---

## 3. 技术实现

### 3.1 文件变更

| 文件 | 变更内容 |
|------|----------|
| `plugins/xiuxian_game/cultivate/core.py` | 添加 `fenjin` 命令处理器 |
| `plugins/xiuxian_game/player/help.py` | 添加【焚金】帮助信息 |

不需要新建 Service 或数据库字段，直接操作 `player.gold` 和 `player.exp`。

### 3.2 核心实现逻辑

```python
fenjin = on_command("焚金", block=True, priority=5)

@fenjin.handle()
async def handle_fenjin(event: MessageEvent, args: Message = CommandArg()):
    """焚金 — 消耗金币换取修为"""
    arg_text = args.extract_plain_text().strip()

    # 参数校验（在 try-except 外部）
    if not arg_text or not arg_text.isdigit():
        await fenjin.finish("用法: 【焚金 <金额>】\n例如: 【焚金 100000】")

    amount = int(arg_text)
    if amount < 1000:
        await fenjin.finish("⛔ 焚金最低消耗1000金币")

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await fenjin.finish("请先创建角色")

        if player.gold < amount:
            await fenjin.finish(f"⛔ 金币不足，当前: {player.gold:,} 金币")

        # 计算修为
        level_factor = 1.0 + (player.level / 100.0)
        exp_gain = math.floor(
            math.sqrt(amount / 1000) * 100 * level_factor
        )

        # 修为上限：不超过升级所需修为
        exp_cap = calculate_level_up_exp(player.level)
        exp_gain = min(exp_gain, max(0, exp_cap - player.exp))

        if exp_gain <= 0:
            await fenjin.finish("⛔ 修为已满，请先【突破】")

        # 扣减金币并增加修为
        player.gold -= amount
        player.exp += exp_gain
        session.add(player)
        await session.commit()

        # 返回结果
        realm_name = realm_by_level_and_reincarnation(player.level, player.reincarnation_level)
        await fenjin.finish(
            f"🔥 焚金仪式\n"
            f"━━━━━━━━━━━━━\n"
            f"消耗: {amount:,} 金币\n"
            f"境界: {realm_name} Lv.{player.level}（等级加成 ×{level_factor:.1f}）\n"
            f"获得修为: +{exp_gain:,}\n"
            f"当前修为: {player.exp:,} / {exp_cap:,}\n"
            f"━━━━━━━━━━━━━\n"
            f"⚠️ 修为已积累，使用【突破】继续成长"
        )
```

### 3.3 帮助信息

在 `player/help.py` 中添加：
```python
"焚金": {
    "usage": "【焚金 <金额>】",
    "description": "消耗金币换取修为，边际收益递减，高等级效率更高。无每日限制，金币最低1000。",
    "examples": ["【焚金 10000】", "【焚金 1000000】"]
}
```

---

## 4. 平衡性分析

### 4.1 通缩效果

正常修炼每5分钟约获得 50-200 修为。花10万金约能换 6000 修为（100级），相当于约30-120次修炼，即2.5-10小时的修炼量。**性价比明显低于正常修炼**，确保焚金不会替代修炼系统，只是一个额外的金币消耗渠道。

### 4.2 高级玩家导向

- 1000级玩家的 `level_factor = 11`，消耗相同金币获得11倍修为
- 高级玩家升级所需修为也极高，焚金获得的修为仍然是"杯水车薪"
- 高级玩家金币更多，有更强动力使用此功能

### 4.3 防滥用

- 修为上限防止一次性超出满修为（不能跳级）
- 不触发自动突破，突破仍需手动操作（保留突破失败/护航机制）
- 无需新增数据库字段，无法被轻易绕过

---

## 5. 未来可扩展方向

- 引入**焚金加成道具**，让消耗道具也能提升转化效率
- 添加**全服焚金排行榜**，展示谁烧钱最多（社交压力促进更多消耗）
- 焚金可以累计**焚金积分**，换取特殊称号或奖励
