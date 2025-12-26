# 抽奖系统奖品发放逻辑深度调查报告

## 1. 系统架构总结

抽奖系统采用双表设计（Lottery活动表+LotteryParticipant参与者表），支持金币/物品/装备三种奖品类型。发起人在创建抽奖时扣除奖品，开奖时通过随机算法选择中奖者并发放奖品。

---

## 2. 代码证据

### 2.1 抽奖创建流程

**文件位置**: `plugins/xiuxian_game/admin/lottery_commands.py:96-212`

#### 金币扣除（第107-118行）
```python
if prize_name == "金币":
    lottery_type = LotteryType.GOLD
    # 检查金币是否足够
    if creator.gold < total_prize:
        await create_lottery_cmd.finish(...)
    # 扣除金币
    creator.gold -= total_prize
    session.add(creator)
```

#### 物品/装备扣除（第119-152行）
```python
else:
    # 查找物品配置
    item_cfg = config.items_config["by_name"].get(prize_name)
    # 判断是装备还是普通物品
    if item_cfg.type == ItemType.EQUIPMENT:
        lottery_type = LotteryType.EQUIPMENT
    else:
        lottery_type = LotteryType.ITEM

    # 检查背包物品数量
    stmt = select(ItemInstance).where(...)
    items = (await session.execute(stmt)).scalars().all()
    total_owned = sum(item.quantity for item in items)

    if total_owned < total_prize:
        await create_lottery_cmd.finish(...)

    # 扣除物品
    try:
        await ItemInstance.consume_item(session, creator.id, item_id, total_prize)
    except ValueError as e:
        await create_lottery_cmd.finish(f"⛔ 扣除物品失败：{e}")
```

**关键发现**:
- ✅ 奖品在创建抽奖时立即从发起人背包扣除
- ✅ 扣除失败会终止创建流程
- ✅ 扣除的奖品数量记录在 `Lottery.total_prize` 字段中

---

### 2.2 抽奖开奖流程

**文件位置**: `plugins/xiuxian_game/admin/lottery_commands.py:308-419`

#### 中奖者选择（第350-356行）
```python
# 随机抽取中奖者
participant_count = len(participants)
actual_winner_count = min(lottery.winner_count, participant_count)

# 随机打乱参与者列表并选择中奖者
random.shuffle(participants)
winners = participants[:actual_winner_count]
```

#### 奖品发放核心逻辑（第358-389行）
```python
winner_names = []
for winner in winners:
    winner.is_winner = True
    winner.won_at = datetime.now()
    winner.prize_received = True  # ⚠️ 立即标记为已领取
    session.add(winner)

    # 获取中奖玩家对象
    winner_player = await session.get(Player, winner.player_id)
    if not winner_player:
        continue

    # 发放奖品
    if lottery.lottery_type == LotteryType.GOLD:
        winner_player.gold += lottery.prize_per_winner
        session.add(winner_player)
    else:
        # 发放物品或装备
        try:
            await ItemInstance.add_item(
                session,
                winner_player.id,
                lottery.item_id,
                lottery.prize_per_winner
            )
        except ValueError as e:
            # ⚠️ 背包满了，记录但继续
            winner_names.append(f"{winner.player_name}[UID:{winner.player_uid}]❌背包满")
            continue  # ⚠️ 直接跳过，奖品消失

    winner_names.append(f"{winner.player_name}[UID:{winner.player_uid}]")
```

#### 抽奖状态更新（第391-396行）
```python
# 更新抽奖状态
lottery.status = LotteryStatus.FINISHED
lottery.finished_at = datetime.now()
session.add(lottery)

await session.commit()  # ⚠️ 事务提交，无法回滚
```

---

### 2.3 背包满异常处理机制

**关键代码**: `plugins/xiuxian_game/admin/lottery_commands.py:377-387`

**问题分析**:
```python
try:
    await ItemInstance.add_item(...)
except ValueError as e:
    # 背包满了，记录但继续
    winner_names.append(f"{winner.player_name}[UID:{winner.player_uid}]❌背包满")
    continue  # ⚠️ 直接跳过，奖品消失
```

**异常抛出位置**: `plugins/xiuxian_game/models/inventory.py:360`
```python
if used_slots + extra_slots_needed > effective_capacity:
    raise ValueError(f"背包空间不足")
```

**事务管理**: `plugins/xiuxian_game/models/db.py:195-211`
```python
async def safe_session():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()  # 自动提交成功的事务
        except SQLAlchemyError as e:
            await session.rollback()
            raise e
        except Exception as e:
            # Nonebot2流程控制异常会提交事务
            if isinstance(e, (FinishedException, ...)):
                await session.commit()
                raise e
```

---

### 2.4 奖品流向追踪

#### 奖品状态流转图

```
[创建抽奖]
    ↓
发起人背包扣除 → 记录在 Lottery.total_prize
    ↓
[开奖流程]
    ↓
┌─────────────────────────┐
│ 遍历中奖者发放奖品       │
│                         │
│  金币奖品：             │
│   ✅ 直接增加到玩家.gold │
│                         │
│  物品/装备奖品：         │
│   ├─ try: add_item()    │
│   │   ├─ 成功：✅        │
│   │   └─ ValueError:    │
│   │       └─ continue   │ ⚠️ 奖品消失
│   │                     │
│   └─ ❌ 未退还发起人    │
└─────────────────────────┘
    ↓
更新 lottery.status = FINISHED
    ↓
commit() → 事务不可回滚
```

---

## 3. 问题分析

### 3.1 核心问题：奖品消失漏洞

**严重程度**: 🔴 高（直接导致奖品永久丢失）

**问题描述**:
- 当中奖玩家背包满时，`ItemInstance.add_item()` 抛出 `ValueError`
- 异常被 `try-except` 捕获后，仅记录中奖者为"背包满"，然后 `continue` 跳过
- 未执行退还奖品给发起人的逻辑
- 奖品从发起人背包扣除后，既未发放成功，也未退还，永久消失

**影响范围**:
- ✅ 金币奖品不受影响（直接增加 `player.gold`，无异常）
- ❌ 物品奖品受影响（`ItemInstance.add_item()` 可能抛出 `ValueError`）
- ❌ 装备奖品受影响（装备也通过 `ItemInstance.add_item()` 处理）

**触发条件**:
- 中奖玩家背包已使用格数 + 新增物品需要格数 > 有效背包容量
- 触发代码：`inventory.py:359-360`

---

### 3.2 次要问题

#### 问题2：过早标记奖品已领取

**位置**: `lottery_commands.py:363`

```python
winner.prize_received = True  # 在发放前就标记为已领取
```

**问题**:
- 标记 `prize_received = True` 在发放奖品之前执行
- 如果后续发放失败，状态不一致（标记已领取，实际未领取）
- 虽然当前实现会 commit 事务，但语义上不正确

#### 问题3：缺少发放失败的补偿机制

**位置**: `lottery_commands.py:386`

```python
continue  # 直接跳过，无任何补偿逻辑
```

**问题**:
- 没有记录发放失败的详细日志
- 没有通知中奖玩家清理背包后重新领取
- 没有退还奖品给发起人

---

### 3.3 事务安全性分析

**当前事务管理**:
- ✅ 使用 `safe_session()` 确保异常自动回滚
- ✅ 整个开奖流程在单个事务中执行
- ❌ `ValueError` 被 `try-except` 捕获后未抛出，事务正常提交

**事务边界**:
```python
async with safe_session() as session:  # 事务开始
    # ... 发放奖品
    try:
        await ItemInstance.add_item(...)
    except ValueError as e:
        continue  # ⚠️ 未抛出异常，事务继续

    await session.commit()  # 事务提交
```

**风险点**:
- 部分奖品发放成功，部分奖品消失（原子性被破坏）
- 抽奖状态为 `FINISHED`，但实际奖品未完全发放
- 无法通过回滚恢复（已提交事务）

---

## 4. 修复方案对比

### 方案1：发放失败时退还发起人（推荐）

**实施位置**: `lottery_commands.py:377-387`

**修改逻辑**:
```python
# 追踪发放失败的奖品数量
failed_prizes = 0

for winner in winners:
    # ... 标记中奖者

    if lottery.lottery_type == LotteryType.GOLD:
        winner_player.gold += lottery.prize_per_winner
        session.add(winner_player)
    else:
        try:
            await ItemInstance.add_item(
                session,
                winner_player.id,
                lottery.item_id,
                lottery.prize_per_winner
            )
        except ValueError as e:
            # 背包满，退还给发起人
            failed_prizes += lottery.prize_per_winner
            winner.prize_received = False  # 标记为未领取
            winner_names.append(f"{winner.player_name}[UID:{winner.player_uid}]❌背包满")
            continue

    winner_names.append(f"{winner.player_name}[UID:{winner.player_uid}]")

# 退还失败的奖品给发起人
if failed_prizes > 0:
    creator = await session.get(Player, lottery.creator_id)
    if creator:
        if lottery.lottery_type == LotteryType.GOLD:
            creator.gold += failed_prizes
        else:
            await ItemInstance.add_item(
                session,
                creator.id,
                lottery.item_id,
                failed_prizes
            )
```

**优点**:
- ✅ 防止奖品消失，确保资产守恒
- ✅ 逻辑简单，修改量小
- ✅ 向下兼容，不影响正常发放流程

**缺点**:
- ⚠️ 发起人可能也背包满，需要二次异常处理
- ⚠️ 中奖玩家失去领奖机会（无法事后补领）

**实施难度**: 低（约30行代码修改）

---

### 方案2：延迟领奖机制

**实施位置**: 新增 `claim_lottery_reward` 命令

**修改逻辑**:
1. 开奖时仅标记中奖者，不立即发放奖品
2. 中奖玩家通过 `领取奖励 抽奖ID` 命令主动领取
3. 发起人可以在一定期限后（如7天）收回未领取的奖品

**优点**:
- ✅ 中奖玩家可以清理背包后再领取
- ✅ 完全避免奖品消失问题
- ✅ 提供更灵活的奖品管理

**缺点**:
- ❌ 需要新增命令和定时任务
- ❌ 修改量大，增加系统复杂度
- ❌ 需要修改数据模型（新增奖品池表）

**实施难度**: 高（约150行代码+数据库迁移）

---

### 方案3：全量回滚机制

**实施位置**: `lottery_commands.py:358-396`

**修改逻辑**:
```python
try:
    for winner in winners:
        # ... 发放奖品
        await ItemInstance.add_item(...)

except ValueError as e:
    # 发放失败，回滚整个开奖流程
    raise ValueError(f"开奖失败：部分中奖者背包满，请通知中奖者清理背包后重新开奖")
```

**优点**:
- ✅ 保证事务原子性（要么全部成功，要么全部失败）
- ✅ 逻辑最简单，代码修改最少

**缺点**:
- ❌ 一个中奖者背包满会导致所有中奖者无法领奖
- ❌ 用户体验差（需要手动重新开奖）
- ❌ 无法处理部分中奖者长期背包满的情况

**实施难度**: 极低（约5行代码修改）

---

## 5. 推荐方案与实施步骤

### 推荐：方案1（发放失败时退还发起人）

**推荐理由**:
1. 解决核心问题（奖品消失）
2. 实施简单，风险可控
3. 向下兼容，不影响正常流程
4. 符合用户预期（中奖者背包满 = 放弃奖品）

---

### 实施步骤

#### Step 1: 修改开奖流程（核心修复）

**文件**: `plugins/xiuxian_game/admin/lottery_commands.py`

**修改位置**: 第358-396行

```python
# 发放奖品
winner_names = []
failed_prizes = 0  # 新增：追踪失败的奖品数量

for winner in winners:
    winner.is_winner = True
    winner.won_at = datetime.now()
    session.add(winner)

    # 获取中奖玩家对象
    winner_player = await session.get(Player, winner.player_id)
    if not winner_player:
        continue

    # 发放奖品
    if lottery.lottery_type == LotteryType.GOLD:
        winner_player.gold += lottery.prize_per_winner
        winner.prize_received = True  # 金币发放成功
        session.add(winner_player)
    else:
        # 发放物品或装备
        try:
            await ItemInstance.add_item(
                session,
                winner_player.id,
                lottery.item_id,
                lottery.prize_per_winner
            )
            winner.prize_received = True  # 发放成功后再标记
        except ValueError as e:
            # 背包满了，累计失败奖品，稍后退还发起人
            failed_prizes += lottery.prize_per_winner
            winner.prize_received = False  # 标记为未领取
            winner_names.append(f"{winner.player_name}[UID:{winner.player_uid}]❌背包满")
            continue

    winner_names.append(f"{winner.player_name}[UID:{winner.player_uid}]")

# 退还失败的奖品给发起人
if failed_prizes > 0:
    creator = await session.get(Player, lottery.creator_id)
    if creator:
        if lottery.lottery_type == LotteryType.GOLD:
            creator.gold += failed_prizes
            session.add(creator)
        else:
            try:
                await ItemInstance.add_item(
                    session,
                    creator.id,
                    lottery.item_id,
                    failed_prizes
                )
            except ValueError:
                # 发起人背包也满了，记录到extra_attrs（留待后续领取或管理员处理）
                if lottery.extra_attrs is None:
                    lottery.extra_attrs = {}
                lottery.extra_attrs["unclaimed_refund"] = failed_prizes
                session.add(lottery)

# 更新抽奖状态
lottery.status = LotteryStatus.FINISHED
lottery.finished_at = datetime.now()
session.add(lottery)

await session.commit()
```

---

#### Step 2: 更新数据模型（支持退还记录）

**文件**: `plugins/xiuxian_game/models/lottery.py`

**修改位置**: 第25-56行

```python
class Lottery(Base):
    """抽奖活动表"""
    __tablename__ = "lottery"

    # ... 现有字段 ...

    # 新增：额外数据存储（用于记录退还失败等信息）
    extra_attrs: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        comment="额外数据（如未领取退还数）"
    )
```

**数据库迁移**:
```bash
# 创建迁移脚本
alembic revision -m "add_lottery_extra_attrs"

# 编辑迁移文件，添加字段
ALTER TABLE lottery ADD COLUMN extra_attrs JSON DEFAULT '{}';

# 执行迁移
alembic upgrade head
```

---

#### Step 3: 优化开奖结果消息

**文件**: `plugins/xiuxian_game/admin/lottery_commands.py`

**修改位置**: 第398-419行

```python
# 构建消息
msg_lines = [
    f"🎊 抽奖结果公布！",
    f"━━━━━━━━━━━━━",
    f"🆔 抽奖ID：{lottery.id}",
    f"🎁 奖品：{lottery.item_name}",
    f"👥 参与人数：{participant_count} 人",
    f"🎯 中奖人数：{actual_winner_count} 人",
    f"📦 每人获得：{lottery.prize_per_winner} 个",
    f"━━━━━━━━━━━━━",
    f"🏆 中奖名单："
]

for i, name in enumerate(winner_names, 1):
    msg_lines.append(f"{i}. {name}")

# 新增：显示退还信息
if failed_prizes > 0:
    msg_lines.append(f"━━━━━━━━━━━━━")
    msg_lines.append(f"📦 退还发起人：{failed_prizes} 个（因中奖者背包满）")

if actual_winner_count < participant_count:
    msg_lines.append(f"━━━━━━━━━━━━━")
    msg_lines.append(f"💔 未中奖：{participant_count - actual_winner_count} 人")

msg = "\n".join(msg_lines)
await draw_lottery_cmd.finish(message_add_head(msg, event))
```

---

#### Step 4: 单元测试

**测试文件**: `tests/test_lottery_refund.py`

```python
async def test_lottery_refund_when_inventory_full():
    """测试中奖者背包满时奖品退还"""
    # 1. 创建发起人和中奖者
    # 2. 发起抽奖（10个棺材钉）
    # 3. 填满中奖者背包
    # 4. 执行开奖
    # 5. 断言：发起人背包恢复10个棺材钉
    # 6. 断言：中奖者 prize_received = False
```

---

### 测试清单

- [ ] 正常发放流程（中奖者背包有空间）
- [ ] 中奖者背包满（应退还发起人）
- [ ] 发起人背包也满（应记录到 extra_attrs）
- [ ] 金币奖品（不受背包影响）
- [ ] 装备奖品（占用1格，背包满也会失败）
- [ ] 部分中奖者背包满，部分成功（混合场景）

---

## 6. 结论

### 核心发现

1. **存在奖品消失漏洞**：中奖者背包满时，奖品既未发放成功，也未退还发起人，永久丢失
2. **影响范围**：物品和装备奖品受影响，金币奖品不受影响
3. **修复优先级**：P0紧急修复（直接导致资产损失）

### 最终推荐

- **修复方案**：方案1（发放失败时退还发起人）
- **实施难度**：低（约50行代码修改 + 数据库迁移）
- **实施时间**：约2小时（开发1小时 + 测试1小时）
- **风险评估**：低（向下兼容，仅修改异常处理逻辑）

### 长期优化建议

- 考虑实施方案2（延迟领奖机制），提升用户体验
- 添加抽奖系统管理命令（查看未领取奖品、手动补发等）
- 完善日志记录（记录每次奖品发放的详细日志）
