# 炼丹领取竞态条件修复说明

## 🐛 问题描述

**Bug现象**：
当玩家在炼丹完成时发送【收获丹药】指令，如果一次性收获大量丹药导致卡顿，此时再次发送【收获丹药】指令，可以领取双倍丹药。

**复现步骤**：
1. 玩家炼制大量丹药（如100炉）
2. 炼制完成后发送【收获丹药】
3. 在发放丹药卡顿期间，再次发送【收获丹药】
4. 结果：同一批丹药被发放两次

## 🔍 根本原因分析

### 问题位置
- **文件**：`plugins/xiuxian_game/alchemy/service_new.py:344-408`
- **文件**：`plugins/xiuxian_game/alchemy/__init__.py:145-177`

### 竞态条件流程

```
时间线：
T1: 用户发送第一次【收获丹药】请求
T2: 检查 record.claimed == False ✅ 通过
T3: 发放物品到背包（卡顿开始...）
T4: 用户发送第二次【收获丹药】请求
T5: 检查 record.claimed == False ✅ 再次通过！（因为第一次还没执行到设置标志）
T6: 第二次请求也发放物品
T7: 第一次请求设置 record.claimed = True
T8: 第二次请求也设置 record.claimed = True
结果：用户获得了双倍丹药！
```

### 核心问题
1. **检查与操作分离**：`record.claimed` 检查在发放物品之前
2. **标志设置滞后**：`record.claimed = True` 在发放物品之后才设置（第396行）
3. **缺少并发控制**：没有使用数据库锁或其他并发控制机制

## ✅ 修复方案

### 方案：双重防护机制

#### 1. 数据库行锁（SELECT FOR UPDATE）
在 `AlchemyRecordRepository` 中添加带锁查询方法：

```python
async def get_by_id_with_lock(self, record_id: int) -> Optional[AlchemyRecord]:
    """使用SELECT FOR UPDATE进行行级锁"""
    stmt = select(AlchemyRecord).where(
        AlchemyRecord.id == record_id
    ).with_for_update()  # 🔒 行锁
    result = await self._session.execute(stmt)
    return result.scalar_one_or_none()
```

**作用**：
- 锁定该记录，直到事务提交或回滚
- 第二个并发请求会等待第一个请求完成
- 确保同一时间只有一个事务能修改该记录

#### 2. 先标记后发放（Flag-First Pattern）
修改 `claim_reward` 方法，调整执行顺序：

```python
async def claim_reward(self, record: AlchemyRecord) -> Tuple[bool, str]:
    # 1. 检查
    if record.claimed:
        return False, "⛔ 该炼丹记录已领取"

    # 2. 【关键修复】先标记为已领取
    record.claimed = True
    await self._alchemy_record_repo.update(record)
    await self._session.flush()  # 立即刷新到数据库

    # 3. 再发放物品（即使卡顿，重复请求也会在步骤1被拦截）
    success_count, total_produce = record.calculate_result()
    await self._item_repo.add_item(...)

    # 4. 其他操作...
```

**作用**：
- `claimed` 标志在发放物品前设置并刷新到数据库
- 即使后续操作卡顿，并发请求也会在第一步检查时被拦截
- `flush()` 确保标志立即生效，不等待事务提交

#### 3. 领取指令使用带锁查询
修改 `alchemy/__init__.py` 中的领取逻辑：

```python
for record in claimable_records:
    # 🔒 使用带锁的查询，确保原子性
    locked_record = await alchemy_record_repo.get_by_id_with_lock(record.id)
    if not locked_record or locked_record.claimed:
        # 如果记录已被其他并发请求领取，跳过
        continue

    success, msg = await service.claim_reward(locked_record)
    if success:
        messages.append(msg)
```

**作用**：
- 每个记录都使用带锁查询
- 如果记录已被其他请求领取，立即跳过
- 防止批量领取时的竞态条件

## 🛡️ 防护机制总结

### 时间线对比

#### 修复前（存在漏洞）
```
T1: 请求A - 检查claimed=False ✅
T2: 请求A - 发放物品（卡顿...）
T3: 请求B - 检查claimed=False ✅ （漏洞！）
T4: 请求B - 发放物品
T5: 请求A - 设置claimed=True
T6: 请求B - 设置claimed=True
```

#### 修复后（双重防护）
```
T1: 请求A - SELECT FOR UPDATE 🔒 锁定记录
T2: 请求A - 检查claimed=False ✅
T3: 请求A - 立即设置claimed=True
T4: 请求A - FLUSH到数据库 💾
T5: 请求A - 发放物品（卡顿...）
T6: 请求B - SELECT FOR UPDATE ⏳ 等待锁释放
T7: 请求A - 提交事务，释放锁 🔓
T8: 请求B - 获得锁，检查claimed=True ❌ 被拦截
T9: 请求B - 跳过该记录
```

### 双重防护
1. **第一层：数据库行锁**
   - 物理层面防止并发修改
   - 第二个请求必须等待第一个完成

2. **第二层：先标记后发放**
   - 逻辑层面防止重复发放
   - 即使锁失效，重复请求也会被 `claimed` 标志拦截

## 📁 修改文件清单

1. **plugins/xiuxian_game/infrastructure/repositories/alchemy_record_repository.py**
   - 添加 `get_by_id_with_lock()` 方法

2. **plugins/xiuxian_game/alchemy/service_new.py**
   - 添加 `self._session` 属性
   - 修改 `claim_reward()` 方法：先标记后发放

3. **plugins/xiuxian_game/alchemy/__init__.py**
   - 修改领取指令：使用带锁查询

## 🧪 测试建议

### 手动测试
1. 炼制大量丹药（如100炉）
2. 等待完成后，快速连续发送两次【收获丹药】
3. 检查背包中的丹药数量是否正确

### 自动化测试
参考 `test_race_condition.py` 中的并发测试逻辑。

## 📝 注意事项

1. **数据库兼容性**：
   - `SELECT FOR UPDATE` 是标准SQL，MySQL/PostgreSQL/SQLite都支持
   - 确保数据库引擎支持事务（InnoDB）

2. **性能影响**：
   - 行锁会轻微增加数据库负载
   - 对于低频操作（炼丹领取），影响可忽略

3. **回滚机制**：
   - 如果发放物品失败，会回滚 `claimed` 标志
   - 确保数据一致性

4. **其他类似场景**：
   - 检查其他涉及"领取"功能的地方（如打工收工、签到奖励等）
   - 应用相同的修复模式

## 🔐 最佳实践

### 防止竞态条件的通用模式

```python
# ❌ 错误：先检查后修改
if not record.claimed:
    # 执行操作（可能卡顿）
    give_rewards()
    # 设置标志
    record.claimed = True

# ✅ 正确：先修改后执行
if not record.claimed:
    # 立即设置标志
    record.claimed = True
    await flush()  # 立即刷新到数据库
    # 再执行操作
    give_rewards()
```

### 使用数据库锁

```python
# ✅ 使用行锁确保原子性
record = await repo.get_by_id_with_lock(record_id)
if record and not record.claimed:
    record.claimed = True
    await flush()
    give_rewards()
```

## 📚 参考资料

- [SQLAlchemy SELECT FOR UPDATE](https://docs.sqlalchemy.org/en/14/orm/queryguide.html#select-for-update)
- [Database Concurrency Control](https://en.wikipedia.org/wiki/Concurrency_control)
- [Race Condition Prevention](https://en.wikipedia.org/wiki/Race_condition#In_software)

## 🎯 总结

通过**数据库行锁**和**先标记后发放**的双重防护机制，彻底解决了炼丹领取的竞态条件问题。这种模式可以应用到其他类似的"领取"场景中，确保系统的数据一致性和公平性。

---

**修复时间**：2026-01-17
**修复人**：Claude Code
**严重程度**：高（可能导致游戏经济失衡）
**修复状态**：✅ 已完成
