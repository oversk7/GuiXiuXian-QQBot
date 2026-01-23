# 诡修仙2 - 战斗/装备/背包系统交互操作调查报告

**调查日期**: 2026-01-23
**调查范围**: 战斗系统、装备系统、背包系统的操作流程和界面交互
**报告类型**: 功能调查与UI设计建议

---

## 执行摘要

本调查报告深入分析了诡修仙2游戏的三大核心系统(战斗、装备、背包)的操作流程和交互模式。基于代码分析和现有命令实现,提炼出玩家高频操作路径和界面按钮配置建议。

**关键发现**:
1. **战斗系统**: 采用回合制PvP/PvE,战毕返回文本战报,无快捷按钮交互
2. **装备系统**: 装备独立背包,支持穿戴/卸下/升阶/修理,操作频率中等
3. **背包系统**: 7大类型分类展示,支持使用/整理/分类查看,高频操作
4. **界面交互**: 目前使用纯文本命令,已测试Markdown+Keyboard按钮但未全面应用

---

## 代码证据 (The Evidence)

### 1. 战斗系统核心文件

#### 1.1 战斗引擎与结果处理
- `plugins/xiuxian_game/battle/integration_helper.py:152-246` - PvP切磋战斗入口
- `plugins/xiuxian_game/battle/integration_helper.py:249-340` - PvE怪物战斗入口
- `plugins/xiuxian_game/battle/enhanced_engine.py:411-550` - 战斗执行循环

**关键发现**:
```python
# 战斗结果返回格式 (integration_helper.py:37-61)
battle_log.append("━━━━━━━━━━━━")
if victory:
    battle_log.append(f"🎉 {player.nickname}获胜！用时{round_num}回合")
    # 只显示存活方的血条（完整信息）
    player_hp_bar = create_hp_bar(player_hp, player.max_hp, show_full=True)
    battle_log.append(f"  {player.nickname}:")
    battle_log.append(f"    {player_hp_bar}")
else:
    battle_log.append(f"💀 {player.nickname}战败！用时{round_num}回合")
```

**战斗后操作流程**:
- 战斗返回 `(victory: bool, battle_log: List[str], damage_taken: int)`
- 战毕直接发送文本战报,无后续操作按钮
- 玩家需手动输入命令进行后续操作(如使用药品、查看属性、继续战斗)

#### 1.2 诡域探索战斗流程
- `plugins/xiuxian_game/world/dungeon_battle.py:23-70` - 诡域战斗执行流程

**战前装备耐久检查**:
```python
# dungeon_battle.py:33-56
async def check_equipment_durability(session, player_id: str) -> str:
    """检查玩家装备耐久度，如果有装备耐久度低于10，返回提醒消息"""
    equipped_items = result_eq.scalars().all()
    low_durability_items = []
    for eq in equipped_items:
        if eq.durability < 10:
            low_durability_items.append(f"{eq.config.name}(ID:{eq.id}, 耐久:{eq.durability}/{eq.config.durability})")

    if low_durability_items:
        warning_msg = "⚠️ 装备耐久度警告！以下装备耐久度过低，建议及时修理：\n"
        warning_msg += "\n".join([f"🔧 {item}" for item in low_durability_items])
        warning_msg += "\n💡 使用【修理 装备ID/名称】命令进行修理"
        return warning_msg
```

**战斗后掉落处理**:
```python
# dungeon_battle.py:55-70
if victory:
    # 胜利处理 - 获得经验和材料
    exp_gain = rng.randint(1, 4) * monster_level
    player.exp += exp_gain
    battle_summary.append(f"🎉 你击杀了 {monster_full_display}，获得 {exp_gain} EXP")

    # 诡异掉落材料机制
    drop_result = await handle_monster_drops(
        session, player, monster_level, player.region, rng, is_elite
    )
    if drop_result:
        battle_summary.append(drop_result)
```

#### 1.3 装备耐久损耗机制
- `plugins/xiuxian_game/world/dungeon_battle.py:310-330` - 战斗耐久扣除

```python
# 每场战斗扣除1点耐久
for eq in equipped_items:
    if eq.lose_durability(1):
        # 耐久耗尽：自动卸下且不可穿戴
        delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
        for k, v in delta.items():
            setattr(player, k, getattr(player, k) - v)
        eq.equipped = False
        broken_msgs.append(
            f"━━━━━━━━━━━━━\n"
            f"💔 {eq.config.name} 耐久耗尽已自动卸下\n"
            f"   ⚠️ 需修理后才能再次穿戴"
        )
```

**关键发现**: 战斗中装备耐久耗尽会自动卸下,战报中会显示损坏提示,但无直接修理按钮。

---

### 2. 装备系统操作流程

#### 2.1 装备查看与穿戴
- `plugins/xiuxian_game/item/equipment_commands.py:359-458` - 装备/穿戴/卸下命令

**装备栏查看格式**:
```python
# equipment_commands.py:30-80 查看装备栏
"🎽 装备栏 [1/1]"
"━━━━━━━━━━━━━"
"[1] 斩龙闪 (ID:12345)"
"   阶级: +5阶  稀有度: 🟇 橙色"
"   耐久: 95/100  ⚔️ 攻击力: +450 (+25%总计)"
"   🎯 特效: 吸血15% | 斩龙闪20%伤害拆分 | 处决5%"
```

**穿戴装备流程**:
```python
# equipment_commands.py:362-458
async def handle_wear_equipment(event, args):
    # 1. 解析装备编号/名称
    # 2. 检查装备是否存在且属于玩家
    # 3. 检查耐久度是否为0
    if equip.durability == 0:
        await wear_equipment.finish(f"⛔ {equip.config.name} 耐久为0，已自动卸下，请先修理")
    # 4. 检查是否已穿戴同名装备
    # 5. 执行穿戴并重新计算属性
    await equipment_service.recalc_equipment_attributes(player)
    # 6. 显示成功消息
    await wear_equipment.finish(f"✅ 成功穿戴 {equip.config.name} (ID:{equip.id}, 耐久:{equip.durability}/{equip.config.durability})")
```

#### 2.2 装备卸下操作
- `plugins/xiuxian_game/item/equipment_commands.py:460-574` - 卸下装备

```python
# 卸下单件装备
async def handle_unwear_equipment(event, args):
    # 1. 查找装备
    # 2. 标记为未穿戴
    equip.equipped = False
    # 3. 重新计算装备属性
    await equipment_service.recalc_equipment_attributes(player)
    # 4. 显示结果
    await unwear_equipment.finish(f"✅ 成功卸下 {equip.config.name} (ID:{equip.id})")

# 一键卸下全部装备
async def handle_unwear_all_equipment(event):
    # 查找所有已装备装备并批量卸下
```

#### 2.3 装备升阶系统
- `plugins/xiuxian_game/item/equipment_upgrade_commands.py:141-200` - 升阶命令

**升阶成功率**:
- 0→1阶: 90%
- 1→2阶: 70%
- 2→3阶: 50%
- 3→4阶: 30%
- 4+阶: 30%

**升阶消耗**:
- 同名装备x1 (作为材料)
- 金币(按阶级递增)
- 可选: 稳定水晶(提升成功率)

#### 2.4 装备修理系统
- `plugins/xiuxian_game/item/equipment_craft.py:333-438` - 修理命令

**修理费用计算**:
```python
# equipment_craft.py:380-418
total_cost = int((max_durability - current_durability) * repair_cost_per_point)

# 支持金币:怨念比例分配
if gold_ratio and resentment_ratio:
    total_ratio = gold_ratio + resentment_ratio
    used_gold = (total_cost * gold_ratio) // total_ratio
    used_resentment = total_cost - used_gold

    # 检查资源
    if player.gold < used_gold:
        await repair_cmd.finish(f"⛔ 金币不足，按比例 {gold_ratio}:{resentment_ratio} 需要金币 {used_gold}💰")
    if player.resentment < used_resentment:
        await repair_cmd.finish(f"⛔ 怨念不足，按比例 {gold_ratio}:{resentment_ratio} 需要怨念 {used_resentment}👻")
```

**一键修理全部装备**:
- `plugins/xiuxian_game/player/monthly_card.py:459-533` - 月卡功能之一
- 自动修理所有装备,支持金币:怨念比例分配

---

### 3. 背包系统高频操作

#### 3.1 背包分类查看
- `plugins/xiuxian_game/item/inventory.py:119-545` - 背包命令

**支持的操作类型**:
```python
# inventory.py:84-117
CATEGORY_MAPPING = {
    "消耗品": "CONSUMABLE",
    "材料": "MATERIAL",
    "商品": "GOODS",
    "装备": "EQUIPMENT",  # 装备不在背包显示,提示使用装备栏
    "丹药": "ELIXIR",
    "宝石": "GEM",
    "鱼类": "FISH",  # 鱼类独立存储,提示使用鱼栏
    "礼物": "GIFT",
}

# 使用示例
# 【背包】 - 显示所有分类
# 【背包 消耗品】 - 只显示消耗品
# 【背包 材料 2】 - 显示材料第2页
```

**背包显示格式**:
```python
# inventory.py:480-545
"🎒 背包 [1/3] (50/150格)"
"━━━━━━━━━━━━━"
"📦 消耗品 (3/20格)"
"  [1] 回春散 x50 (恢复40HP)"
"  [2] 凝神草 x30 (恢复40MP)"
"📦 材料 (25/80格)"
"  [3] 废铁 x100"
"  [4] 白骨 x50"
"💡 装备不占背包,请使用【装备栏】查看"
```

#### 3.2 使用物品流程
- `plugins/xiuxian_game/item/inventory.py:119-236` - 使用物品命令

```python
# 使用物品完整流程
async def handle_use_item(event, args):
    # 1. 解析参数: 使用 [物品名] [数量]
    # 2. 检查物品是否存在
    # 3. 检查背包数量是否足够
    # 4. 特殊物品处理(丹药每日限制)
    is_elixir = item_config.item_id.endswith("_elixir")
    if is_elixir:
        daily_limit = item_config.daily_limit
        used_today = log_row.quantity if log_row else 0
        if used_today + quantity > daily_limit:
            await use_item.finish(f"⛔ {item_config.name} 每日最多可服用 {daily_limit} 颗")

    # 5. 应用物品效果
    success, msg = await apply_effect_with_fallback(player, item_config, quantity, ...)

    # 6. 扣除物品数量
    success_consume = await ItemInstance.consume_item(session, player.id, item_config.item_id, quantity)

    # 7. 显示结果
    await use_item.finish(msg)
```

**物品效果示例**:
```python
# item_effects.py:84-100 - 恢复HP
@register(ItemEffectType.RESTORE_HP)
async def _restore_hp(player, cfg, qty, ctx, session=None):
    value = int(cfg.effect_params.get("value", 0)) * qty
    if player.hp <= 0:
        return False, "🧐 你已经死亡，无法恢复生命"

    effective_max_hp = player.max_hp
    if session:
        effective_attrs = await player.get_effective_attributes(session)
        effective_max_hp = effective_attrs.get("max_hp", effective_max_hp)

    if player.hp >= effective_max_hp:
        return False, "🧐 你的生命值已满，不需要使用此物品"

    player.hp = min(effective_max_hp, player.hp + value)
    return True, f"❤️ 恢复 {value} 点生命值 (当前 {player.hp}/{effective_max_hp})"
```

#### 3.3 背包整理功能
- `plugins/xiuxian_game/item/inventory.py:765-587` - 整理背包

```python
# 整理逻辑
async def handle_organize_inventory(event):
    # 1. 查询所有物品
    items = [it for it in all_items if not it.is_equipment and not it.is_fish]

    # 2. 统计可堆叠物品
    stackable_items = {}
    for item in items:
        if item.item_id not in stackable_items:
            stackable_items[item.item_id] = []
        stackable_items[item.item_id].append(item)

    # 3. 合并堆叠
    for item_id, instances in stackable_items.items():
        if len(instances) > 1:  # 有多个堆叠
            total_quantity = sum(inst.quantity for inst in instances)
            needed_stacks = ceil(total_quantity / STACK_SIZE)

            # 删除旧实例,创建新堆叠
            for inst in instances:
                await session.delete(inst)

            for _ in range(needed_stacks):
                stack_quantity = min(STACK_SIZE, remaining_quantity)
                new_instance = ItemInstance(...)
                session.add(new_instance)

    # 4. 显示整理结果
    await organize_inventory_cmd.finish(
        "🧹 背包整理完成！\n"
        f"📦 整理了 {organized_count} 种物品\n"
        f"🆓 释放了 {freed_slots} 个背包格子"
    )
```

---

### 4. 战后高频操作流程

#### 4.1 使用药品恢复
- `plugins/xiuxian_game/player/monthly_card.py:285-407` - 一键嗑药

**一键嗑药功能**:
```python
# monthly_card.py:285-407
async def handle_auto_use_medicine(event):
    # 1. 计算需要恢复的血量和蓝量
    hp_needed = max(0, effective_max_hp - current_hp)
    mp_needed = max(0, effective_max_mp - current_mp)

    # 2. 获取背包中回春散和凝神草数量
    heal_potion_count = sum(r.quantity for r in heal_potion_rows)
    spirit_herb_count = sum(r.quantity for r in spirit_herb_rows)

    # 3. 计算需要的药品数量
    heal_potion_needed = min(heal_potion_count, ceil(hp_needed / 40))
    spirit_herb_needed = min(spirit_herb_count, ceil(mp_needed / 40))

    # 4. 使用药品
    for item_name, needed_qty in [("回春散", heal_potion_needed), ("凝神草", spirit_herb_needed)]:
        success, msg = await apply_effect(player, config, needed_qty, ctx="world", session=session)
        if success:
            await ItemInstance.consume_item(session, player.id, item_id, needed_qty)

    # 5. 显示结果
    await auto_use_medicine_cmd.finish(
        "💊 一键嗑药完成\n"
        f"🎯 使用药品：{' + '.join(used_items)}\n"
        f"❤️ 恢复生命：{total_hp_restored}\n"
        f"🧠 恢复理智：{total_mp_restored}"
    )
```

**手动使用药品**:
```bash
# 格式
使用 回春散 [数量]
使用 凝神草 [数量]

# 示例
使用 回春散 5    # 使用5个回春散
使用 凝神草      # 使用1个凝神草
```

#### 4.2 查看属性状态
- `plugins/xiuxian_game/player/battle_info.py:16-50` - 查看战力

```python
# battle_info.py:16-50
@battle_info.handle()
async def handle_battle_info(event, args):
    # 获取有效战斗属性(含临时buff)
    battle_attrs = await BattleAttributeCalculator.calculate_effective_attributes_async(
        player=player,
        session=session
    )

    # 显示战斗属性
    msg = (
        f"⚔️ {player.nickname} 的战斗属性\n"
        "━━━━━━━━━━━━━\n"
        f"❤️ 生命值: {player.hp}/{player.max_hp}\n"
        f"🧠 理智值: {player.mp}/{player.max_mp}\n"
        f"⚔️ 攻击力: {player.attack}\n"
        f"🛡️ 防御力: {player.defense}\n"
        "━━━━━━━━━━━━━\n"
        f"💢 暴击率: {battle_attrs['critical_rate']}%\n"
        f"🔄 连击率: {battle_attrs['combo_rate']}%\n"
        f"⚡ 闪避率: {battle_attrs['dodge_rate']}%\n"
        f"🎯 命中率: {battle_attrs['accuracy_rate']}%"
    )
```

#### 4.3 继续战斗/探索
- `plugins/xiuxian_game/world/dungeon_battle.py:723-472` - 探索命令

```python
# dungeon_battle.py:723-472
@explore_cmd.handle()
async def _(event: MessageEvent):
    # 检查玩家状态
    if player.hp <= 0:
        await explore_cmd.finish(
            "💀 你已死亡，返回现实吧，或者你有复活道具..."
            "\n⬇️ 【返回】 退出副本"
            "\n⬇️ 【使用 还魂丹】 原地复活，继续副本"
        )

    # 获取当前坐标
    current_x, current_y = player.get_current_coordinates()
    current_region = player.get_current_region()

    # 执行事件(战斗/材料/休息等)
    log = await EVENT_HANDLERS[tile.event_type](session, tile, player)

    # 显示结果
    header = f"🧭位置 {current_region} ({current_x},{current_y})"
    await explore_cmd.finish(f"{header}\n{log}")
```

---

### 5. 界面按钮交互测试

#### 5.1 按钮测试示例
- `plugins/xiuxian_game/player/help.py:217-247` - 按钮测试命令

```python
# help.py:217-247
@button_test_cmd.handle()
async def handle_button_test(event, args):
    btn_json = {
        "rows": [
            {
                "buttons": [
                    {
                        "id": "1",
                        "render_data": {
                            "label": "修炼",
                            "visited_label": "",
                            "style": 0
                        },
                        "action": {
                            "type": 2,  # 回调类型
                            "permission": {
                                "type": 2  # 所有人可点击
                            },
                            "data": "/修炼",  # 点击后执行的命令
                            "unsupport_tips": "不支持该操作",
                            "reply": False,
                            "enter": False
                        }
                    }
                ]
            }
        ]
    }
    keyboard = MessageKeyboard(id="102499345_1738493417", content=btn_json)
    await button_test_cmd.finish(MessageSegment.keyboard(keyboard))
```

**关键发现**:
- 已实现QQ机器人键盘按钮功能
- 支持点击按钮直接执行命令(如 `/修炼`)
- 目前仅用于测试,未在战斗/装备/背包系统中全面应用

#### 5.2 Markdown模板功能
- `plugins/xiuxian_game/player/markdown_segment_test.py:13-60` - Markdown工具类

```python
# markdown_segment_test.py:13-60
class MessageSegmentPlus(MessageSegment):
    @classmethod
    def markdown_template(cls, md_id: str, msg_body: list, button_id: str = ""):
        """Markdown模板"""
        data = {
            "markdown": {
                "custom_template_id": md_id,
                "params": msg_body
            }
        }

        if button_id:
            data["keyboard"] = {"id": button_id}  # 关联按钮键盘

        return cls("markdown", {"data": data})
```

**应用示例**:
- `plugins/xiuxian_game/cultivate/markdown_interactions.py:116-140` - 突破快捷菜单

```python
# markdown_interactions.py:116-140
@breakthrough_quick_cmd.handle()
async def handle_breakthrough_quick(event):
    # 创建突破快捷菜单(带按钮)
    markdown = create_breakthrough_markdown()

    msg = Message("⛓️‍💥 突破快捷菜单\n━━━━━━━━━━━━━\n💡 选择突破方式")
    msg.append(MessageSegment.markdown(markdown))  # Markdown内容
    msg.append(MessageSegment.keyboard(keyboard)) # 关联按钮

    await breakthrough_quick_cmd.finish(msg)
```

**关键发现**:
- 已实现Markdown模板+按钮键盘的组合
- 已在突破系统中应用(突破快捷菜单)
- 可复用到战斗/装备/背包系统

---

## 6. 高频操作路径分析

### 6.1 战斗后操作路径

#### 场景1: 战斗胜利,血量健康
```
战斗结束
  ↓
【探索】(继续战斗)
  ↓
进入下一格
```

**建议按钮**:
- 🔄 继续探索 - 执行 `/探索`
- 📦 查看战利品 - 执行 `/背包 材料`

#### 场景2: 战斗胜利,血量较低
```
战斗结束(HP < 50%)
  ↓
【一键嗑药】(恢复HP/MP)
  ↓
血量恢复
  ↓
【探索】(继续战斗)
```

**建议按钮**:
- 💊 一键嗑药 - 执行 `/一键嗑药`
- 🔄 继续探索 - 执行 `/探索`
- 📊 查看属性 - 执行 `/战力`

#### 场景3: 战斗胜利,装备耐久低
```
战斗结束(装备耐久 < 10)
  ↓
系统提示耐久警告
  ↓
【修理全部】(修理装备)
  ↓
装备恢复满耐久
```

**建议按钮**:
- 🔧 修理全部 - 执行 `/修理全部`
- 📊 查看装备 - 执行 `/装备栏`

#### 场景4: 战斗失败,玩家死亡
```
战斗失败(HP = 0)
  ↓
系统提示死亡
  ↓
【使用还魂丹】(复活)
  或
【返回】(退出诡域)
```

**建议按钮**:
- 🧪 使用还魂丹 - 执行 `/使用 还魂丹`
- 🏠 返回现实 - 执行 `/返回`

---

### 6.2 装备管理操作路径

#### 场景1: 获得新装备
```
获得新装备
  ↓
【装备栏】(查看装备)
  ↓
【装备】(穿戴装备)
  ↓
重新计算属性
```

**建议按钮**:
- 👕 穿戴装备 - 执行 `/装备 [装备ID]`
- 📊 查看属性 - 执行 `/战力`

#### 场景2: 装备升阶
```
有多件同名装备
  ↓
【升阶信息】(查看成功率)
  ↓
【升阶】(执行升阶)
  ↓
成功: 装备+1阶
失败: 材料消耗
```

**建议按钮**:
- ⬆️ 执行升阶 - 执行 `/升阶 [装备ID]`
- ⭐ 稳定升阶 - 执行 `/升阶 [装备ID] 稳定水晶`
- 📊 查看信息 - 执行 `/升阶信息 [装备ID]`

#### 场景3: 装备损坏
```
战斗中装备耐久耗尽
  ↓
系统提示自动卸下
  ↓
【修理】(恢复耐久)
  ↓
重新穿戴
```

**建议按钮**:
- 🔧 修理装备 - 执行 `/修理 [装备ID]`
- 👕 重新穿戴 - 执行 `/装备 [装备ID]`
- 🔧 修理全部 - 执行 `/修理全部 1:1`(金币:怨念1:1)

---

### 6.3 背包管理操作路径

#### 场景1: 背包杂乱
```
背包格子紧张
  ↓
【整理背包】(合并堆叠)
  ↓
释放格子
```

**建议按钮**:
- 🧹 整理背包 - 执行 `/整理`

#### 场景2: 使用药品
```
战斗后血量低
  ↓
【背包】(查看药品)
  ↓
【使用】(使用药品)
  ↓
血量恢复
```

**建议按钮**:
- 💊 使用回春散 - 执行 `/使用 回春散 [数量]`
- 🧠 使用凝神草 - 执行 `/使用 凝神草 [数量]`
- ⚡ 一键嗑药 - 执行 `/一键嗑药`

#### 场景3: 查找物品
```
需要找特定物品
  ↓
【背包 分类】(过滤显示)
  ↓
找到物品
```

**建议按钮**:
- 📦 消耗品 - 执行 `/背包 消耗品`
- 🧱 材料 - 执行 `/背包 材料`
- 💎 宝石 - 执行 `/背包 宝石`
- 🎁 礼物 - 执行 `/背包 礼物`
- 🧪 丹药 - 执行 `/背包 丹药`

---

## 7. 操作频率统计

基于代码分析和命令设计,估算各操作的使用频率:

### 高频操作 (每场战斗后多次)
1. **探索/战斗** - 诡域移动和战斗触发
   - 命令: `/探索` / `/战斗` / `/移动`
   - 频率: ⭐⭐⭐⭐⭐ (每次移动)

2. **使用药品** - 战后恢复HP/MP
   - 命令: `/使用 回春散` / `/使用 凝神草`
   - 频率: ⭐⭐⭐⭐⭐ (每次战后)

3. **查看属性** - 确认当前状态
   - 命令: `/战力` / `/我的战力`
   - 频率: ⭐⭐⭐⭐ (每3-5次战后)

4. **查看背包** - 确认材料/药品数量
   - 命令: `/背包`
   - 频率: ⭐⭐⭐⭐ (每次战斗后)

### 中频操作 (每5-10场战斗)
1. **整理背包** - 合并堆叠释放格子
   - 命令: `/整理`
   - 频率: ⭐⭐⭐ (背包满时)

2. **修理装备** - 恢复装备耐久
   - 命令: `/修理 [装备ID]` / `/修理全部`
   - 频率: ⭐⭐⭐ (耐久低时)

3. **装备升阶** - 提升装备属性
   - 命令: `/升阶 [装备ID]`
   - 频率: ⭐⭐ (获得材料后)

4. **穿戴/卸下装备** - 调整装备配置
   - 命令: `/装备 [装备ID]` / `/卸下 [装备ID]`
   - 频率: ⭐⭐ (获得新装备或升阶后)

### 低频操作 (每天1-2次)
1. **查看装备栏** - 确认装备状态
   - 命令: `/装备栏`
   - 频率: ⭐ (每天查看1-2次)

2. **升阶信息查询** - 查看升阶需求
   - 命令: `/升阶信息 [装备ID]`
   - 频率: ⭐ (准备升阶前)

3. **背包分类查看** - 查看特定类型物品
   - 命令: `/背包 消耗品` / `/背包 材料`
   - 频率: ⭐ (需要时)

---

## 8. 按钮配置建议

基于以上调查,提供战斗/装备/背包系统的按钮配置方案:

### 8.1 战斗结果界面按钮

#### 战斗胜利(HP > 50%)
```json
{
  "rows": [
    {
      "buttons": [
        {
          "id": "continue_explore",
          "render_data": {"label": "🔄 继续探索", "style": 0},
          "action": {"type": 2, "data": "/探索"}
        },
        {
          "id": "view_inventory",
          "render_data": {"label": "📦 查看背包", "style": 0},
          "action": {"type": 2, "data": "/背包"}
        }
      ]
    },
    {
      "buttons": [
        {
          "id": "view_attributes",
          "render_data": {"label": "📊 查看属性", "style": 0},
          "action": {"type": 2, "data": "/战力"}
        },
        {
          "id": "view_equipment",
          "render_data": {"label": "👕 查看装备", "style": 0},
          "action": {"type": 2, "data": "/装备栏"}
        }
      ]
    }
  ]
}
```

#### 战斗胜利(HP < 50%)
```json
{
  "rows": [
    {
      "buttons": [
        {
          "id": "use_medicine",
          "render_data": {"label": "💊 一键嗑药", "style": 1},
          "action": {"type": 2, "data": "/一键嗑药"}
        },
        {
          "id": "continue_explore",
          "render_data": {"label": "🔄 继续探索", "style": 0},
          "action": {"type": 2, "data": "/探索"}
        }
      ]
    },
    {
      "buttons": [
        {
          "id": "use_heal_potion",
          "render_data": {"label": "❤️ 使用回春散", "style": 0},
          "action": {"type": 2, "data": "/使用 回春散"}
        },
        {
          "id": "use_spirit_herb",
          "render_data": {"label": "🧠 使用凝神草", "style": 0},
          "action": {"type": 2, "data": "/使用 凝神草"}
        }
      ]
    }
  ]
}
```

#### 战斗胜利(装备耐久 < 10)
```json
{
  "rows": [
    {
      "buttons": [
        {
          "id": "repair_all",
          "render_data": {"label": "🔧 修理全部", "style": 1},
          "action": {"type": 2, "data": "/修理全部 1:1"}
        }
      ]
    },
    {
      "buttons": [
        {
          "id": "view_equipment",
          "render_data": {"label": "👕 查看装备", "style": 0},
          "action": {"type": 2, "data": "/装备栏"}
        },
        {
          "id": "continue_explore",
          "render_data": {"label": "🔄 继续探索", "style": 0},
          "action": {"type": 2, "data": "/探索"}
        }
      ]
    }
  ]
}
```

#### 战斗失败(HP = 0)
```json
{
  "rows": [
    {
      "buttons": [
        {
          "id": "use_revive",
          "render_data": {"label": "🧪 使用还魂丹", "style": 1},
          "action": {"type": 2, "data": "/使用 还魂丹"}
        }
      ]
    },
    {
      "buttons": [
        {
          "id": "return_reality",
          "render_data": {"label": "🏠 返回现实", "style": 0},
          "action": {"type": 2, "data": "/返回"}
        }
      ]
    }
  ]
}
```

---

### 8.2 装备栏界面按钮

#### 查看装备栏
```json
{
  "rows": [
    {
      "buttons": [
        {
          "id": "organize_inventory",
          "render_data": {"label": "🧹 整理背包", "style": 0},
          "action": {"type": 2, "data": "/整理"}
        },
        {
          "id": "view_inventory",
          "render_data": {"label": "📦 查看背包", "style": 0},
          "action": {"type": 2, "data": "/背包"}
        }
      ]
    },
    {
      "buttons": [
        {
          "id": "repair_all_equipment",
          "render_data": {"label": "🔧 修理全部", "style": 1},
          "action": {"type": 2, "data": "/修理全部 1:1"}
        },
        {
          "id": "unwear_all",
          "render_data": {"label": "⬇️ 一键卸下", "style": 0},
          "action": {"type": 2, "data": "/一键卸下"}
        }
      ]
    }
  ]
}
```

#### 装备详情(升阶选项)
```json
{
  "rows": [
    {
      "buttons": [
        {
          "id": "upgrade_equipment",
          "render_data": {"label": "⬆️ 执行升阶", "style": 1},
          "action": {"type": 2, "data": "/升阶 [装备ID]"}
        },
        {
          "id": "upgrade_with_crystal",
          "render_data": {"label": "⭐ 稳定升阶", "style": 0},
          "action": {"type": 2, "data": "/升阶 [装备ID] 稳定水晶"}
        }
      ]
    },
    {
      "buttons": [
        {
          "id": "view_upgrade_info",
          "render_data": {"label": "📊 查看信息", "style": 0},
          "action": {"type": 2, "data": "/升阶信息 [装备ID]"}
        },
        {
          "id": "repair_equipment",
          "render_data": {"label": "🔧 修理装备", "style": 0},
          "action": {"type": 2, "data": "/修理 [装备ID]"}
        }
      ]
    }
  ]
}
```

---

### 8.3 背包界面按钮

#### 背包主页
```json
{
  "rows": [
    {
      "buttons": [
        {
          "id": "organize",
          "render_data": {"label": "🧹 整理背包", "style": 1},
          "action": {"type": 2, "data": "/整理"}
        },
        {
          "id": "view_equipment",
          "render_data": {"label": "👕 查看装备", "style": 0},
          "action": {"type": 2, "data": "/装备栏"}
        }
      ]
    },
    {
      "buttons": [
        {
          "id": "category_consumable",
          "render_data": {"label": "📦 消耗品", "style": 0},
          "action": {"type": 2, "data": "/背包 消耗品"}
        },
        {
          "id": "category_material",
          "render_data": {"label": "🧱 材料", "style": 0},
          "action": {"type": 2, "data": "/背包 材料"}
        }
      ]
    },
    {
      "buttons": [
        {
          "id": "category_elixir",
          "render_data": {"label": "🧪 丹药", "style": 0},
          "action": {"type": 2, "data": "/背包 丹药"}
        },
        {
          "id": "category_gem",
          "render_data": {"label": "💎 宝石", "style": 0},
          "action": {"type": 2, "data": "/背包 宝石"}
        }
      ]
    }
  ]
}
```

#### 背包-消耗品分类
```json
{
  "rows": [
    {
      "buttons": [
        {
          "id": "use_heal_potion",
          "render_data": {"label": "💊 使用回春散", "style": 1},
          "action": {"type": 2, "data": "/使用 回春散"}
        },
        {
          "id": "use_spirit_herb",
          "render_data": {"label": "🧠 使用凝神草", "style": 1},
          "action": {"type": 2, "data": "/使用 凝神草"}
        }
      ]
    },
    {
      "buttons": [
        {
          "id": "auto_use_medicine",
          "render_data": {"label": "⚡ 一键嗑药", "style": 0},
          "action": {"type": 2, "data": "/一键嗑药"}
        },
        {
          "id": "back_to_main",
          "render_data": {"label": "⬅️ 返回", "style": 0},
          "action": {"type": 2, "data": "/背包"}
        }
      ]
    }
  ]
}
```

---

## 结论 (Conclusions)

### 核心发现

1. **战斗系统**
   - 当前采用纯文本战报输出,战毕无快捷按钮
   - 玩家需要手动输入命令进行战后操作
   - 高频操作: 继续探索、使用药品、查看属性

2. **装备系统**
   - 装备独立背包,不占用常规格子
   - 支持穿戴/卸下/升阶/修理四大操作
   - 中频操作: 装备管理主要在获得新装备或升阶时

3. **背包系统**
   - 支持7大类型分类查看,使用频率高
   - 高频操作: 使用药品、整理背包、查看材料
   - 已有堆叠合并机制,但需手动触发

4. **界面交互**
   - 已实现QQ机器人键盘按钮和Markdown模板
   - 目前仅在少数功能中应用(如突破快捷菜单)
   - **可扩展性强,适合应用到战斗/装备/背包系统**

### 建议优先级

#### P0 (最高优先级) - 战斗后操作
1. **战斗结果快捷按钮**
   - 胜利: 继续探索、一键嗑药、查看背包
   - 失败: 使用还魂丹、返回现实
   - 理由: 每场战斗后都需要,操作频率最高

2. **药品快捷使用**
   - 一键嗑药按钮
   - 快速使用回春散/凝神草
   - 理由: 战后恢复必需品,使用频率极高

#### P1 (高优先级) - 装备管理
1. **装备栏快捷操作**
   - 修理全部、一键卸下
   - 理由: 批量操作,提升效率

2. **装备升阶界面**
   - 执行升阶、稳定升阶、查看信息
   - 理由: 升阶是核心玩法,提供便捷入口

#### P2 (中优先级) - 背包管理
1. **背包分类快捷按钮**
   - 消耗品、材料、丹药、宝石等分类
   - 理由: 快速定位物品

2. **背包整理按钮**
   - 一键整理按钮
   - 理由: 背包满时需要,操作频率中等

---

## 关系 (Relations)

### 系统交互关系图

```
战斗系统
  ↓ (战后)
  ├─→ 使用药品 ─→ 背包系统(消耗物品)
  ├─→ 查看属性 ─→ 玩家系统(属性计算)
  ├─→ 继续探索 ─→ 战斗系统(下一场战斗)
  └─→ 修理装备 ─→ 装备系统(耐久恢复)

装备系统
  ↓ (获得装备)
  ├─→ 穿戴装备 ─→ 玩家系统(属性加成)
  ├─→ 升阶装备 ─→ 背包系统(消耗材料/装备)
  └─→ 修理装备 ─→ 经济系统(消耗金币/怨念)

背包系统
  ↓ (使用物品)
  ├─→ 使用药品 ─→ 玩家系统(恢复HP/MP)
  ├─→ 整理背包 ─→ 背包系统(合并堆叠)
  └─→ 查看物品 ─→ 装备系统(装备详情)
```

### 数据流关系

```
战斗结束
  ↓
返回战报日志
  ↓
根据战况生成按钮
  ├─ HP < 50% → 显示"一键嗑药"按钮
  ├─ 装备耐久 < 10 → 显示"修理全部"按钮
  └─ HP = 0 → 显示"使用还魂丹"按钮
  ↓
玩家点击按钮
  ↓
执行对应命令
  ↓
返回新状态
  ↓
根据新状态更新按钮
```

---

## 技术实现建议

### 1. 战斗结果增强

**文件**: `plugins/xiuxian_game/battle/integration_helper.py`

**修改点**: `enhanced_player_vs_monster_battle_v2` 函数返回值

```python
# 当前返回值
return (victory, battle_log, damage_taken)

# 建议返回值
return {
    "victory": victory,
    "battle_log": battle_log,
    "damage_taken": damage_taken,
    "player_hp_percent": player.hp / player.max_hp,  # 新增: HP百分比
    "low_durability_equipment": [...]  # 新增: 低耐久装备列表
}
```

**实现**:
```python
# dungeon_battle.py:23-70 战斗结果处理
result = await BattleIntegrationHelper.enhanced_player_vs_monster_battle_v2(...)

# 根据战况生成按钮
keyboard = generate_post_battle_keyboard(
    victory=result["victory"],
    hp_percent=result["player_hp_percent"],
    low_durability=result["low_durability_equipment"]
)

# 发送战报+按钮
await explore_cmd.finish(
    MessageSegment.text("\n".join(result["battle_log"])) +
    MessageSegment.keyboard(keyboard)
)
```

### 2. 按钮生成工具函数

**新建文件**: `plugins/xiuxian_game/utils/keyboard_utils.py`

```python
"""键盘按钮生成工具函数"""

from typing import List, Dict

def generate_post_battle_keyboard(
    victory: bool,
    hp_percent: float,
    low_durability: List[str] = None
) -> Dict:
    """根据战况生成战斗后按钮"""

    # 战斗失败
    if hp_percent <= 0:
        return {
            "rows": [
                {
                    "buttons": [
                        {
                            "id": "use_revive",
                            "render_data": {"label": "🧪 使用还魂丹", "style": 1},
                            "action": {"type": 2, "data": "/使用 还魂丹"}
                        }
                    ]
                },
                {
                    "buttons": [
                        {
                            "id": "return_reality",
                            "render_data": {"label": "🏠 返回现实", "style": 0},
                            "action": {"type": 2, "data": "/返回"}
                        }
                    ]
                }
            ]
        }

    # 战斗胜利 - HP低
    if hp_percent < 0.5:
        return {
            "rows": [
                {
                    "buttons": [
                        {
                            "id": "use_medicine",
                            "render_data": {"label": "💊 一键嗑药", "style": 1},
                            "action": {"type": 2, "data": "/一键嗑药"}
                        },
                        {
                            "id": "continue_explore",
                            "render_data": {"label": "🔄 继续探索", "style": 0},
                            "action": {"type": 2, "data": "/探索"}
                        }
                    ]
                }
            ]
        }

    # 战斗胜利 - 装备耐久低
    if low_durability:
        return {
            "rows": [
                {
                    "buttons": [
                        {
                            "id": "repair_all",
                            "render_data": {"label": "🔧 修理全部", "style": 1},
                            "action": {"type": 2, "data": "/修理全部 1:1"}
                        }
                    ]
                },
                {
                    "buttons": [
                        {
                            "id": "view_equipment",
                            "render_data": {"label": "👕 查看装备", "style": 0},
                            "action": {"type": 2, "data": "/装备栏"}
                        },
                        {
                            "id": "continue_explore",
                            "render_data": {"label": "🔄 继续探索", "style": 0},
                            "action": {"type": 2, "data": "/探索"}
                        }
                    ]
                }
            ]
        }

    # 战斗胜利 - 状态良好
    return {
        "rows": [
            {
                "buttons": [
                    {
                        "id": "continue_explore",
                        "render_data": {"label": "🔄 继续探索", "style": 1},
                        "action": {"type": 2, "data": "/探索"}
                    },
                    {
                        "id": "view_inventory",
                        "render_data": {"label": "📦 查看背包", "style": 0},
                        "action": {"type": 2, "data": "/背包"}
                    }
                ]
            },
            {
                "buttons": [
                    {
                        "id": "view_attributes",
                        "render_data": {"label": "📊 查看属性", "style": 0},
                        "action": {"type": 2, "data": "/战力"}
                    },
                    {
                        "id": "view_equipment",
                        "render_data": {"label": "👕 查看装备", "style": 0},
                        "action": {"type": 2, "data": "/装备栏"}
                    }
                ]
            }
        ]
    }
```

### 3. 装备栏按钮增强

**文件**: `plugins/xiuxian_game/item/equipment_commands.py`

**修改点**: `show_equipment_menu` 函数

```python
# 当前: 纯文本输出
await equipment_menu_cmd.finish(message_add_head("\n".join(lines), event))

# 建议: 添加按钮
keyboard = {
    "rows": [
        {
            "buttons": [
                {
                    "id": "organize_inventory",
                    "render_data": {"label": "🧹 整理背包", "style": 0},
                    "action": {"type": 2, "data": "/整理"}
                },
                {
                    "id": "view_inventory",
                    "render_data": {"label": "📦 查看背包", "style": 0},
                    "action": {"type": 2, "data": "/背包"}
                }
            ]
        },
        {
            "buttons": [
                {
                    "id": "repair_all_equipment",
                    "render_data": {"label": "🔧 修理全部", "style": 1},
                    "action": {"type": 2, "data": "/修理全部 1:1"}
                },
                {
                    "id": "unwear_all",
                    "render_data": {"label": "⬇️ 一键卸下", "style": 0},
                    "action": {"type": 2, "data": "/一键卸下"}
                }
            ]
        }
    ]
}

await equipment_menu_cmd.finish(
    message_add_head("\n".join(lines), event) +
    MessageSegment.keyboard(keyboard)
)
```

### 4. 背包按钮增强

**文件**: `plugins/xiuxian_game/item/inventory.py`

**修改点**: `handle_inventory_command` 函数

```python
# 当前: 纯文本输出
await inventory_cmd.finish(message_add_head("\n".join(lines), event))

# 建议: 根据显示内容添加相应按钮
keyboard = generate_inventory_keyboard(category=category_key)

await inventory_cmd.finish(
    message_add_head("\n".join(lines), event) +
    MessageSegment.keyboard(keyboard)
)

def generate_inventory_keyboard(category: str = None) -> Dict:
    """根据背包分类生成按钮"""

    if category == "CONSUMABLE":
        # 消耗品分类 - 显示使用药品按钮
        return {
            "rows": [
                {
                    "buttons": [
                        {
                            "id": "use_heal_potion",
                            "render_data": {"label": "💊 使用回春散", "style": 1},
                            "action": {"type": 2, "data": "/使用 回春散"}
                        },
                        {
                            "id": "use_spirit_herb",
                            "render_data": {"label": "🧠 使用凝神草", "style": 1},
                            "action": {"type": 2, "data": "/使用 凝神草"}
                        }
                    ]
                },
                {
                    "buttons": [
                        {
                            "id": "auto_use_medicine",
                            "render_data": {"label": "⚡ 一键嗑药", "style": 0},
                            "action": {"type": 2, "data": "/一键嗑药"}
                        },
                        {
                            "id": "back_to_main",
                            "render_data": {"label": "⬅️ 返回", "style": 0},
                            "action": {"type": 2, "data": "/背包"}
                        }
                    ]
                }
            ]
        }

    # 主背包页面 - 显示分类和整理按钮
    return {
        "rows": [
            {
                "buttons": [
                    {
                        "id": "organize",
                        "render_data": {"label": "🧹 整理背包", "style": 1},
                        "action": {"type": 2, "data": "/整理"}
                    },
                    {
                        "id": "view_equipment",
                        "render_data": {"label": "👕 查看装备", "style": 0},
                        "action": {"type": 2, "data": "/装备栏"}
                    }
                ]
            },
            {
                "buttons": [
                    {
                        "id": "category_consumable",
                        "render_data": {"label": "📦 消耗品", "style": 0},
                        "action": {"type": 2, "data": "/背包 消耗品"}
                    },
                    {
                        "id": "category_material",
                        "render_data": {"label": "🧱 材料", "style": 0},
                        "action": {"type": 2, "data": "/背包 材料"}
                    }
                ]
            }
        ]
    }
```

---

## 总结

本调查报告全面分析了诡修仙2游戏的战斗、装备、背包三大系统的操作流程和交互模式。基于代码证据,提炼出高频操作路径和按钮配置建议。

**核心建议**:
1. **战斗系统**: 增加战后快捷按钮(继续探索、一键嗑药、修理全部)
2. **装备系统**: 增加装备栏快捷操作(修理全部、一键卸下、升阶)
3. **背包系统**: 增加分类快捷入口和常用操作按钮(整理、使用药品)

**技术可行性**:
- 已实现QQ机器人键盘按钮和Markdown模板功能
- 可直接复用现有代码(如`突破快捷菜单`)
- 无需引入新技术,仅需扩展现有功能

**预期效果**:
- 减少50%以上的命令输入操作
- 提升游戏体验流畅度
- 降低新玩家上手难度

---

**调查完成时间**: 2026-01-23
**调查人**: scout (Claude Code Agent)
**报告版本**: 1.0
