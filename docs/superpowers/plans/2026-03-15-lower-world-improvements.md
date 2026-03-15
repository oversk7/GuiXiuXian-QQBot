# 天灾系统完善 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完善下位世界天灾系统：失败降波、缩短封印、商店扩充、侦查命令、属性平衡、怪物特殊效果实装。

**Architecture:** 改动集中在 `lower_world/` 四个文件 + `battle/integration_helper.py` 怪物攻击路径。数据库新增 `best_wave` 字段通过 `auto_migrate.py` 迁移。所有改动彼此独立，按 Task 顺序逐个提交。

**Tech Stack:** Python 3.11, NoneBot2, SQLAlchemy 2.0, async/await

---

## File Structure

| 文件 | 职责 | 操作 |
|------|------|------|
| `plugins/xiuxian_game/models/lower_world.py` | 数据模型 | Modify: 新增 `best_wave` 字段 |
| `plugins/xiuxian_game/models/auto_migrate.py` | 自动迁移 | Modify: 新增 `best_wave` 迁移 |
| `plugins/xiuxian_game/lower_world/service.py` | 业务逻辑 | Modify: 失败降波、封印缩短、商店扩充 |
| `plugins/xiuxian_game/lower_world/hero_generator.py` | 英雄生成 | Modify: 缩放公式调整 |
| `plugins/xiuxian_game/lower_world/commands.py` | 命令处理器 | Modify: 侦查命令、兑换解封令、商店UI |
| `plugins/xiuxian_game/battle/integration_helper.py` | 战斗引擎 | Modify: 怪物吸血+穿透实装 |
| `plugins/xiuxian_game/player/help.py` | 帮助信息 | Modify: 新增侦查命令说明 |

---

## Chunk 1: 波次机制 + 封印 + 属性平衡

### Task 1: 失败降波 + 历史最高波次记录

**Files:**
- Modify: `plugins/xiuxian_game/models/lower_world.py:33-34`
- Modify: `plugins/xiuxian_game/models/auto_migrate.py:96-98`
- Modify: `plugins/xiuxian_game/lower_world/service.py:91-120`

- [ ] **Step 1: 数据模型新增 `best_wave` 字段**

在 `models/lower_world.py` 的 `total_waves_won` 字段后面添加：

```python
    best_wave: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", comment="历史最高波次"
    )
```

- [ ] **Step 2: 自动迁移注册**

在 `models/auto_migrate.py` 的 `lower_world_stronghold` 字典内追加：

```python
    "lower_world_stronghold": {
        "last_battle_at": "DATETIME NULL COMMENT '最后一次迎战时间（战斗冷却用）'",
        "best_wave": "INT DEFAULT 1 COMMENT '历史最高波次'"
    },
```

- [ ] **Step 3: 修改 `process_battle_victory` 记录最高波次**

在 `service.py` 的 `process_battle_victory` 函数中，`stronghold.wave_number += 1` 之后追加一行：

```python
    stronghold.best_wave = max(stronghold.best_wave or 1, stronghold.wave_number)
```

- [ ] **Step 4: 修改 `process_battle_defeat` 实现失败降3波**

将 `service.py` 的 `process_battle_defeat` 从：

```python
async def process_battle_defeat(uow: UnitOfWork, stronghold: LowerWorldStronghold):
    """处理战斗失败：封印24小时，清除当前英雄"""
    stronghold.sealed_until = datetime.now() + timedelta(hours=SEAL_DURATION_HOURS)
    stronghold.pending_hero = None
    stronghold.next_wave_at = None
    uow.session.add(stronghold)
```

改为：

```python
async def process_battle_defeat(uow: UnitOfWork, stronghold: LowerWorldStronghold) -> int:
    """
    处理战斗失败：
    - 封印12小时
    - 波次 -3（最低回到1）
    - 清除当前英雄
    返回降低的波次数
    """
    stronghold.sealed_until = datetime.now() + timedelta(hours=SEAL_DURATION_HOURS)
    old_wave = stronghold.wave_number
    stronghold.wave_number = max(1, stronghold.wave_number - 3)
    wave_dropped = old_wave - stronghold.wave_number
    stronghold.pending_hero = None
    stronghold.next_wave_at = None
    uow.session.add(stronghold)
    return wave_dropped
```

- [ ] **Step 5: 缩短封印时长常量**

将 `service.py:17` 的 `SEAL_DURATION_HOURS = 24` 改为：

```python
SEAL_DURATION_HOURS = 12
```

- [ ] **Step 6: 更新 commands.py 失败路径展示降波信息**

在 `commands.py` 的失败处理分支中（当前约第670行 `await process_battle_defeat(uow, stronghold)` 处），改为接收返回值并更新文案：

将：
```python
            await process_battle_defeat(uow, stronghold)
            await uow.commit()
```

改为：
```python
            wave_dropped = await process_battle_defeat(uow, stronghold)
            await uow.commit()
```

然后在失败文案的 `log_lines` 中，将：

```python
                "⛓️ 你被封印24小时",
```

改为：

```python
                f"⛓️ 你被封印{SEAL_DURATION_HOURS}小时" + (f"，波次降低{wave_dropped}波（当前第{stronghold.wave_number}波）" if wave_dropped > 0 else ""),
```

- [ ] **Step 7: 更新 `_show_stronghold_status` 显示历史最高波次**

在 `commands.py` 的 `_show_stronghold_status` 函数中，所有出现 `f"🏆 已胜利波次：{stronghold.total_waves_won}\n"` 的地方（共4处），后面追加一行 `f"🏅 历史最高：第{stronghold.best_wave or stronghold.wave_number}波\n"`。

具体做法：将4处：

```python
            f"🏆 已胜利波次：{stronghold.total_waves_won}\n"
```

全部替换为：

```python
            f"🏆 已胜利波次：{stronghold.total_waves_won}\n"
            f"🏅 历史最高：第{stronghold.best_wave or stronghold.wave_number}波\n"
```

- [ ] **Step 8: Commit**

```bash
git add plugins/xiuxian_game/models/lower_world.py plugins/xiuxian_game/models/auto_migrate.py plugins/xiuxian_game/lower_world/service.py plugins/xiuxian_game/lower_world/commands.py
git commit -m "feat(lower-world): 失败降3波+历史最高波次+封印缩短至12小时"
```

---

### Task 2: 英雄属性缩放平衡

**Files:**
- Modify: `plugins/xiuxian_game/lower_world/hero_generator.py:214-217`

- [ ] **Step 1: 降低等级增长率**

将 `hero_generator.py` 的 `calculate_hero_level` 函数从：

```python
def calculate_hero_level(player_level: int, wave_number: int) -> int:
    """计算英雄等级：英雄等级 = 玩家等级 × (0.6 + 波次 × 0.04)"""
    ratio = 0.6 + wave_number * 0.04
    return max(1, int(player_level * ratio))
```

改为：

```python
def calculate_hero_level(player_level: int, wave_number: int) -> int:
    """
    计算英雄等级：
    - 1-20波：线性增长 0.6 + 波次 × 0.03
    - 21+波：对数减速增长，避免数值爆炸
    """
    if wave_number <= 20:
        ratio = 0.6 + wave_number * 0.03
    else:
        # 20波时 ratio=1.2，之后每10波约增长0.15，逐步放缓
        import math
        base_ratio = 1.2
        extra = math.log(1 + (wave_number - 20) / 10) * 0.5
        ratio = base_ratio + extra
    return max(1, int(player_level * ratio))
```

- [ ] **Step 2: 降低词缀攻击倍率**

将 `hero_generator.py` AFFIXES 中的攻击倍率下调：

- `berserk`（狂暴之怒）: `atk_mult` 从 `1.5` 改为 `1.3`
- `desperate`（破釜沉舟）: `atk_mult` 从 `1.5` 改为 `1.3`

- [ ] **Step 3: 降低炮勇者攻击倍率**

将 `HERO_CLASSES` 中炮勇者的 `atk_mult` 从 `2.0` 改为 `1.6`。

- [ ] **Step 4: Commit**

```bash
git add plugins/xiuxian_game/lower_world/hero_generator.py
git commit -m "feat(lower-world): 降低属性缩放增长率和词缀/职业倍率"
```

---

## Chunk 2: 商店扩充 + 侦查命令

### Task 3: 天灾商店扩充

**Files:**
- Modify: `plugins/xiuxian_game/lower_world/service.py:123-154`
- Modify: `plugins/xiuxian_game/lower_world/commands.py` (兑换逻辑)

- [ ] **Step 1: 添加新商品到 SHOP_ITEMS**

在 `service.py` 的 `SHOP_ITEMS` 列表中，在称号之前插入 2 个新商品：

```python
SHOP_ITEMS = [
    {
        "id": "cultivate_boost",
        "name": "修炼加速（2小时）",
        "desc": "修炼效率+50%，持续2小时",
        "price": 50,
    },
    {
        "id": "battle_boost",
        "name": "战意加持（1场）",
        "desc": "下一场战斗全属性+10%",
        "price": 30,
    },
    {
        "id": "unseal",
        "name": "解封令",
        "desc": "立即解除封印状态",
        "price": 40,
    },
    {
        "id": "scout_intel",
        "name": "侦查情报（1次）",
        "desc": "查看下一波英雄的详细属性",
        "price": 10,
    },
    {
        "id": "title_calamity",
        "name": "称号「第四天灾」",
        "desc": "永久专属称号，一次性购买",
        "price": 200,
    },
]
```

- [ ] **Step 2: 在 commands.py 的兑换逻辑中添加解封令处理**

在 `handle_redeem` 的 `elif item["id"] == "title_calamity":` 之前，添加：

```python
        elif item["id"] == "unseal":
            # 检查是否处于封印状态
            sealed, remaining = is_sealed(stronghold)
            if not sealed:
                await redeem_cmd.finish(
                    "你当前没有被封印，无需使用解封令。\n"
                    "天灾点未扣除。"
                )

            stronghold.calamity_points -= item["price"]
            stronghold.sealed_until = None
            uow.session.add(stronghold)
            # 立即安排下一波
            await schedule_next_wave(uow, stronghold, player.level)
            await uow.commit()
            msg = (
                "✅ 兑换成功！\n"
                "「大都会紧急解除了封印协议。」\n"
                "\n"
                "⛓️ 封印已解除\n"
                f"⏳ 下一波英雄将于 {WAVE_INTERVAL_HOURS} 小时后到达"
            )

        elif item["id"] == "scout_intel":
            # 侦查情报：给玩家一个标记，在【侦查】命令中免费使用一次
            # 实际上侦查命令本身消耗天灾点，此商品项只是展示用
            # 直接提示使用【侦查】命令
            await redeem_cmd.finish(
                "💡 请直接使用【侦查】命令查看下一波英雄情报\n"
                "（消耗10天灾点，无需提前购买）"
            )
```

- [ ] **Step 3: 在 commands.py 的 import 中确保 `is_sealed` 和 `schedule_next_wave` 已导入**

确认 `commands.py` 顶部 import 中已包含 `is_sealed` 和 `schedule_next_wave`（当前已有，无需修改）。

- [ ] **Step 4: Commit**

```bash
git add plugins/xiuxian_game/lower_world/service.py plugins/xiuxian_game/lower_world/commands.py
git commit -m "feat(lower-world): 商店新增解封令(40点)和侦查情报(10点)"
```

---

### Task 4: 侦查命令

**Files:**
- Modify: `plugins/xiuxian_game/lower_world/commands.py` (新命令)
- Modify: `plugins/xiuxian_game/lower_world/__init__.py` (确认加载)
- Modify: `plugins/xiuxian_game/player/help.py`

- [ ] **Step 1: 注册侦查命令**

在 `commands.py` 顶部的命令注册区域（约第38行 `redeem_cmd` 之后）添加：

```python
scout_cmd = on_command("侦查", block=True, priority=5)
```

- [ ] **Step 2: 实现侦查处理器**

在 `commands.py` 的 `handle_redeem` 函数之后（文件末尾），添加：

```python
# 侦查消耗的天灾点
SCOUT_COST = 10


# ==================== 【侦查】 ====================
@scout_cmd.handle()
async def handle_scout(event: MessageEvent):
    """
    【侦查】- 消耗10天灾点查看下一波英雄的属性
    """
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await scout_cmd.finish("请先【注册】后再使用该功能")

        stronghold = await uow.lower_world_strongholds.get_by_player_id(player.id)
        if not stronghold:
            await scout_cmd.finish("你还未建立山寨。使用【降临】开始下位世界之旅")

        # 检查封印状态
        sealed, remaining = is_sealed(stronghold)
        if sealed:
            await scout_cmd.finish(
                f"⛓️ 你被封印中，剩余 {format_time_remaining(remaining)}\n"
                "封印期间无法侦查。"
            )

        # 检查天灾点
        if stronghold.calamity_points < SCOUT_COST:
            await scout_cmd.finish(
                f"天灾点不足！侦查需要 {SCOUT_COST} 点\n"
                f"当前：{stronghold.calamity_points} 点"
            )

        # 如果已有待挑战英雄，直接展示当前英雄的详细属性
        if has_pending_hero(stronghold):
            hero = hero_from_json(stronghold.pending_hero)
            stronghold.calamity_points -= SCOUT_COST
            uow.session.add(stronghold)
            await uow.commit()

            affix_line = ""
            if hero.get("affixes"):
                affix_line = f"🔮 词缀：{'、'.join(hero['affixes'])}\n"

            special_lines = []
            if hero.get("crit_rate"):
                special_lines.append(f"💥 暴击率：{hero['crit_rate']}%")
            if hero.get("combo_rate"):
                special_lines.append(f"⚡ 连击率：{hero['combo_rate']}%")
            if hero.get("counter_rate"):
                special_lines.append(f"🛡️ 反击率：{hero['counter_rate']}%")
            if hero.get("lifesteal"):
                special_lines.append(f"🧡 吸血：{hero['lifesteal']}%")
            if hero.get("ignore_defense"):
                special_lines.append(f"☂️ 穿透：{hero['ignore_defense']}%")
            special_str = "\n".join(special_lines) + "\n" if special_lines else ""

            msg = (
                f"🔍 侦查报告 （-{SCOUT_COST}天灾点）\n"
                "━━━━━━━━━━━━━\n"
                f"⚔️ {hero['name']}\n"
                f"🎖️ Lv.{hero['level']}\n"
                f"{affix_line}"
                f"❤️ HP：{hero['hp']:,}\n"
                f"⚔️ 攻击：{hero['attack']:,}\n"
                f"🛡️ 防御：{hero['defense']:,}\n"
                f"👟 敏捷：{hero['agility']:,}\n"
                f"{special_str}"
                "━━━━━━━━━━━━━\n"
                f"📝 {hero['flavour']}\n"
                "\n"
                f"💎 剩余天灾点：{stronghold.calamity_points}"
            )
            await scout_cmd.finish(msg)

        # 没有待挑战英雄：预览下一波英雄（不消耗，只展示预测）
        from .hero_generator import generate_hero as _gen_hero
        # 使用固定种子预览（和实际生成的不一定一样，但展示属性量级）
        preview_hero = _gen_hero(player.level, stronghold.wave_number)
        stronghold.calamity_points -= SCOUT_COST
        uow.session.add(stronghold)
        await uow.commit()

        msg = (
            f"🔍 侦查预测 （-{SCOUT_COST}天灾点）\n"
            "━━━━━━━━━━━━━\n"
            f"📍 第{stronghold.wave_number}波预计英雄强度：\n"
            f"🎖️ 预估等级：Lv.{preview_hero['level']}\n"
            f"❤️ HP范围：~{preview_hero['hp']:,}\n"
            f"⚔️ 攻击范围：~{preview_hero['attack']:,}\n"
            f"🛡️ 防御范围：~{preview_hero['defense']:,}\n"
            "━━━━━━━━━━━━━\n"
            "⚠️ 英雄未到达，属性仅供参考\n"
            "\n"
            f"💎 剩余天灾点：{stronghold.calamity_points}"
        )
        await scout_cmd.finish(msg)
```

- [ ] **Step 3: 更新帮助信息**

在 `help.py` 的天灾系统帮助命令中（约第2504行 `【迎战】` 之后），追加：

```
"【侦查】 消耗10天灾点，查看当前/下一波英雄详细属性\n"
```

在快捷命令列表（约第2097行）追加 `【侦查】`：

```python
    ("天灾系统", "#10b981", [
        "【降临】 【镇守】 【迎战】 【侦查】",
        "【天灾商店】 【兑换 商品名】",
    ]),
```

- [ ] **Step 4: Commit**

```bash
git add plugins/xiuxian_game/lower_world/commands.py plugins/xiuxian_game/player/help.py
git commit -m "feat(lower-world): 新增【侦查】命令(10天灾点查看英雄属性)"
```

---

## Chunk 3: 怪物特殊效果实装

### Task 5: 怪物吸血 + 穿透实装

**Files:**
- Modify: `plugins/xiuxian_game/battle/integration_helper.py:630-690`

- [ ] **Step 1: 在怪物攻击路径中实装穿透（ignore_defense）**

在 `integration_helper.py` 的 `enhanced_player_vs_monster_battle_v2` 方法中，找到怪物攻击分支（约第648行 `# 应用防御减伤`），在 `apply_defense_mitigation` 调用之前，添加穿透削减玩家防御的逻辑。

将：
```python
                    # 应用防御减伤
                    from ..utils import apply_defense_mitigation

                    if has_true_damage:
```

改为：
```python
                    # 应用穿透（怪物 ignore_defense 削减玩家有效防御）
                    effective_player_defense = player.defense
                    monster_penetration = monster_stats.get("ignore_defense", 0)
                    if monster_penetration > 0:
                        effective_player_defense = int(player.defense * (1 - monster_penetration / 100))

                    # 应用防御减伤
                    from ..utils import apply_defense_mitigation

                    if has_true_damage:
```

然后将该分支中所有 `apply_defense_mitigation(xxx, player.defense)` 调用替换为 `apply_defense_mitigation(xxx, effective_player_defense)`。具体有 3 处：

第657行（真伤+绝魔路径）：
```python
                            mitigation = apply_defense_mitigation(normal_damage_part, effective_player_defense)
```

第666行（普通伤害路径）：
```python
                        mitigation = apply_defense_mitigation(monster_damage, effective_player_defense)
```

注意：第600-610行的**怪物反击路径**中也有 `apply_defense_mitigation(counter_damage, player.defense)`，同样需要应用穿透。在那里也添加：
```python
                        effective_def = player.defense
                        monster_pen = monster_stats.get("ignore_defense", 0)
                        if monster_pen > 0:
                            effective_def = int(player.defense * (1 - monster_pen / 100))
```
并将 `player.defense` 替换为 `effective_def`。

- [ ] **Step 2: 在怪物攻击路径中实装吸血（lifesteal）**

在怪物攻击造成伤害后（约第688行 `battle_log.append(f"👹 {monster_name}攻击...")`）之后，添加吸血逻辑：

```python
                    # 怪物吸血
                    monster_lifesteal = monster_stats.get("lifesteal", 0)
                    if monster_lifesteal > 0 and final_damage > 0:
                        heal_amount = int(final_damage * monster_lifesteal / 100)
                        monster_hp = min(monster_stats["hp"], monster_hp + heal_amount)
                        battle_log.append(f"🧡 {monster_name}吸血恢复{heal_amount}HP")
```

- [ ] **Step 3: Commit**

```bash
git add plugins/xiuxian_game/battle/integration_helper.py
git commit -m "feat(lower-world): 实装怪物穿透(ignore_defense)和吸血(lifesteal)效果"
```

---

### Task 6: 帮助信息完善 + 最终检查

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py`

- [ ] **Step 1: 更新天灾系统帮助详情**

将 `help.py` 中 `handle_lower_world_help` 的帮助文案更新，加入以下内容：

在 `⚔️ 战斗系统：` 部分追加：
```
"【侦查】 消耗10天灾点，查看当前/下一波英雄详细属性（HP/攻击/防御/特殊效果）。提前做好战斗准备。\n"
```

将 `• 战败英雄：山寨受损，需修复` 改为：
```
"  • 被英雄击败：封印12小时 + 波次降低3波（最低回到第1波）\n"
```

在 `📊 玩法机制：` 部分追加：
```
"• 失败降波：战败后波次-3（最低回到第1波），降低难度重新挑战\n"
"• 解封令：在天灾商店花40天灾点立即解除封印\n"
```

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/player/help.py
git commit -m "docs(lower-world): 更新天灾系统帮助信息"
```
