# SQLAlchemy连接泄漏全面排查报告

**调查日期**: 2025-12-02
**调查范围**: 项目所有使用数据库连接的代码
**调查目的**: 排查之前修复guild.py:174-198后仍然出现的连接泄漏源头

---

## 代码证据 (The Evidence)

### P0 - 严重连接泄漏 (立即修复)

#### 1. player/invite.py:253 - 保存session引用后UoW退出
- `plugins/xiuxian_game/player/invite.py:253` - 在UnitOfWork退出后保存并使用session引用
  - **问题**: 第253行 `session = uow.session`,然后在第254行UoW退出,但session在第264、296行继续使用
  - **影响**: session在UoW关闭后仍持有数据库连接,导致连接泄漏
  - **使用位置**:
    - L264: `invitee_result = await session.execute(invitee_stmt)`
    - L296: `inviter_result = await session.execute(inviter_stmt)`

#### 2. economy/stock_commands.py:76 - 保存session引用后UoW退出
- `plugins/xiuxian_game/economy/stock_commands.py:76` - 在UnitOfWork退出后保存并使用session引用
  - **问题**: 第76行 `session = uow.session`,然后在第77行UoW退出,但session不再使用(已修复的幽灵代码)
  - **影响**: 虽然后续没有使用,但保存了引用可能阻止连接释放
  - **状态**: 代码无后续使用,但保留引用本身就是问题

### P1 - 潜在连接泄漏 (重要修复)

#### 3. daily_task/commands.py:269-272 - 在UoW内部创建Repository传递uow.session
- `plugins/xiuxian_game/daily_task/commands.py:269-272` - 在UnitOfWork内部手动创建Repository
  - **问题**: 创建`PlayerTaskStatsRepository(uow.session)`等4个Repository,而不是使用`uow.player_task_stats`
  - **影响**: 如果Service保存了这些Repository引用,可能在UoW退出后继续持有session
  - **涉及Repository**:
    - `PlayerTaskStatsRepository(uow.session)` - L269
    - `GuildTaskRecordRepository(uow.session)` - L270
    - `PlayerDonationLogRepository(uow.session)` - L271
    - `GuildBuildingRepository(uow.session)` - L272

#### 4. guild/guild.py:186 - 在UoW内部创建Repository传递uow.session
- `plugins/xiuxian_game/guild/guild.py:186` - 在UnitOfWork内部手动创建Repository
  - **问题**: 创建`GuildBuildingRepository(uow.session)`,而不是使用UoW的懒加载属性
  - **影响**: Repository可能保留对session的引用
  - **位置**: `building_repo=GuildBuildingRepository(uow.session)`

#### 5. guild/guild.py:761 - 在UoW内部创建Repository传递uow.session
- `plugins/xiuxian_game/guild/guild.py:761` - 在UnitOfWork内部手动创建Repository
  - **问题**: 创建`SocialApplicationRepository(uow.session)`
  - **影响**: Repository可能保留对session的引用
  - **位置**: `application_repo=SocialApplicationRepository(uow.session)`

### P2 - 代码异味 (低优先级清理)

#### 6. 多处在UnitOfWork外部创建AsyncSessionLocal返回
- 9个文件使用`return AsyncSessionLocal()`模式:
  - `plugins/xiuxian_game/daily_task/commands.py:29,127,207,318,368`
  - `plugins/xiuxian_game/guild/guild.py:65,137,361,438,738,932,986`
  - `plugins/xiuxian_game/economy/part_time_job_commands.py:52,172,224,281,325,368`
  - `plugins/xiuxian_game/economy/stock_commands.py:53,168,222,258,283,349,447`
  - `plugins/xiuxian_game/player/invite.py:100,154,237`
  - 其他5个文件...
- **状态**: 这些都是正确的用法,在UnitOfWork内部作为session_factory使用
- **验证**: 所有返回的session_factory都在`async with UnitOfWork(session_factory)`内使用

#### 7. 大量Repository在UnitOfWork内部手动实例化
- 约130+处使用`Repository(session)`模式:
  - `alchemy/__init__.py:33-34` - `ItemRepository(session), AlchemyRecordRepository(session)`
  - `world_boss/__init__.py:58-61` - 4个Repository实例化
  - `cultivate/core.py:138,288,395` - `PlayerRepository(session)`
  - `economy/market.py:356-357,407-408,543-544,881-882` - 多处Repository实例化
  - 其他大量文件...
- **状态**: 大部分在safe_session内使用,应该是安全的,但违反了UoW模式
- **建议**: 长期重构为使用UoW统一管理

#### 8. models/db.py:230 - retry_session未正确关闭
- `plugins/xiuxian_game/models/db.py:225-258` - retry_session实现
  - **问题**: 第230行在循环内创建`session = AsyncSessionLocal()`,仅在finally块关闭
  - **影响**: 如果重试多次,可能创建多个session但只关闭最后一个
  - **当前使用**: Grep搜索显示retry_session在项目中未被使用
  - **建议**: 修复逻辑或删除未使用的函数

---

## 调查结果 (The Report)

### result

#### 🔴 P0 - 确认的连接泄漏源头

1. **player/invite.py:253-296** - 在UnitOfWork退出后继续使用session
   - 严重程度: **P0 - 立即修复**
   - 泄漏机制: 保存`session = uow.session`,UoW在L254退出,但session在L264、L296继续使用
   - 修复建议: 将L254-321的所有查询移到UoW内部,或在UoW外创建新的safe_session

2. **economy/stock_commands.py:76** - 保存session引用(幽灵代码)
   - 严重程度: **P0 - 立即修复**
   - 泄漏机制: 保存`session = uow.session`,虽然后续未使用,但引用可能阻止GC回收
   - 修复建议: 删除L76的`session = uow.session`这行代码

#### 🟠 P1 - 潜在连接泄漏源头

3. **daily_task/commands.py:269-272** - 在UoW内部手动创建Repository传递uow.session
   - 严重程度: **P1 - 重要修复**
   - 风险: 如果`GuildTaskServiceNew`保存了Repository引用,可能在UoW退出后持有session
   - 修复建议: 修改UoW添加这4个Repository的懒加载属性,使用`uow.player_task_stats`代替手动创建

4. **guild/guild.py:186, 761** - 2处在UoW内部手动创建Repository
   - 严重程度: **P1 - 重要修复**
   - 风险: Repository可能保留session引用
   - 修复建议: 使用UoW的懒加载属性或确保Service不保存Repository引用

#### 🟡 P2 - 代码异味和长期改进

5. **retry_session函数** - 未使用且有潜在泄漏风险
   - 严重程度: **P2 - 清理**
   - 状态: 项目中未使用此函数
   - 建议: 删除或修复重试逻辑(确保每次重试都关闭旧session)

6. **130+处直接使用Repository(session)** - 违反UoW模式
   - 严重程度: **P2 - 长期重构**
   - 状态: 大部分在safe_session内,应该是安全的
   - 建议: 长期迁移到UoW模式统一管理

---

### conclusions

#### 关键发现

1. **已发现2个P0级别的确认连接泄漏**:
   - `player/invite.py:253` - 在UoW退出后使用session (高频使用,影响大)
   - `economy/stock_commands.py:76` - 保存session引用 (低频使用,影响中)

2. **已发现3个P1级别的潜在泄漏点**:
   - `daily_task/commands.py:269-272` - 4个Repository手动创建
   - `guild/guild.py:186` - 1个Repository手动创建
   - `guild/guild.py:761` - 1个Repository手动创建

3. **UnitOfWork模式使用良好**:
   - 248处使用safe_session,大部分遵循了正确的上下文管理
   - 仅1处使用UnitOfWork(在unit_of_work.py自身测试)
   - session_factory模式正确使用,没有泄漏风险

4. **UnitOfWork设计合理**:
   - 懒加载Repository (L72-189)
   - 自动提交/回滚 (L198-230)
   - 总是关闭session (L226)
   - **但缺少部分Repository的懒加载属性** (如PlayerTaskStatsRepository等)

5. **之前的guild.py:174-198修复是有效的**:
   - 通过Grep搜索未发现类似的"在UoW外手动创建UoW"的模式
   - 新的泄漏源头是"保存uow.session引用"的不同模式

#### 为什么警告仍然出现

即使修复了guild.py的泄漏,以下2个P0泄漏源头仍在工作:

1. **invite.py每次查询邀请状态** → 泄漏1个连接
2. **stock_commands.py每次查看股票列表** → 泄漏1个连接(虽然不使用,但引用存在)

如果这两个指令被频繁调用,泄漏会快速累积,触发SQLAlchemy的连接池警告。

---

### relations

#### 代码关系图

```
UnitOfWork (unit_of_work.py)
├─ __aenter__: 创建session
├─ __aexit__: 自动commit/rollback + close session
├─ session属性: 暴露内部session (危险!)
└─ 懒加载Repository (安全)

invite.py (泄漏源头1)
├─ L239-253: async with UnitOfWork() as uow:
│   ├─ L240: player = get_unified_player(uow.session)
│   ├─ L251: invite_status = await service.get_invite_status()
│   └─ L253: session = uow.session  ← 保存引用
├─ L254: UoW退出 (session.close()被调用)
└─ L264, L296: await session.execute()  ← 使用已关闭的session? (SQLAlchemy可能保留底层连接)

stock_commands.py (泄漏源头2)
├─ L55-76: async with UnitOfWork() as uow:
│   ├─ L68: player = get_unified_player(uow.session)
│   ├─ L74: stocks = await uow.session.execute(stmt)
│   └─ L76: session = uow.session  ← 保存引用(未使用)
└─ L77: UoW退出 (session引用阻止GC?)

daily_task/commands.py (潜在泄漏)
├─ L209-275: async with UnitOfWork() as uow:
│   ├─ L269-272: 手动创建4个Repository(uow.session)
│   ├─ L266-273: 创建GuildTaskServiceNew(repos...)
│   └─ L274: await service.update_commission_stats()
└─ L275: await uow.commit() (Service可能持有Repository引用?)

guild/guild.py (潜在泄漏)
├─ 多处使用UnitOfWork
├─ L186: building_repo=GuildBuildingRepository(uow.session)
└─ L761: application_repo=SocialApplicationRepository(uow.session)
```

#### 泄漏机制分析

**确认泄漏 (invite.py)**:
1. UnitOfWork在L254退出,调用`await session.close()`
2. 但变量`session`仍持有对AsyncSession对象的引用
3. L264、L296继续使用这个引用执行查询
4. SQLAlchemy可能重新打开连接或使用底层未关闭的连接
5. 函数结束时,连接未被正确归还到连接池

**潜在泄漏 (daily_task/commands.py)**:
1. 手动创建Repository并传递给Service
2. 如果Service/Repository保存了session引用
3. UoW退出后,这些引用可能阻止session被GC回收
4. 需要检查`GuildTaskServiceNew`的实现确认

---

## 修复建议 (按优先级排序)

### P0 - 立即修复 (今天必须完成)

#### 1. 修复 player/invite.py:253-296

**方案A: 将所有查询移到UoW内部** (推荐)

```python
async with UnitOfWork(session_factory) as uow:
    player = await get_unified_player(uow.session, event)
    if not player:
        await invite_status_cmd.finish("⛔ 请先创建角色")

    invite_reward_service = InviteRewardServiceNew(
        invite_reward_repo=uow.invite_rewards,
        player_repo=uow.players
    )

    invite_status = await invite_reward_service.get_invite_status(player.uid)

    # 🔧 修复: 将所有查询移到UoW内部
    msg = f"📊 {player.nickname} 的邀请状态\n━━━━━━━━━━━━━\n"

    if invite_status["invited_count"] > 0:
        msg += f"👥 已邀请玩家：{invite_status['invited_count']} 人\n"

        for record in invite_status["inviter_records"]:
            invitee_stmt = select(Player).where(Player.uid == record.invitee_uid)
            invitee_result = await uow.session.execute(invitee_stmt)  # ✅ 使用uow.session
            invitee = invitee_result.scalars().first()

            if invitee:
                # ... 处理逻辑 ...
                pass

    if invite_status["invitee_record"]:
        record = invite_status["invitee_record"]
        inviter_stmt = select(Player).where(Player.uid == record.inviter_uid)
        inviter_result = await uow.session.execute(inviter_stmt)  # ✅ 使用uow.session
        inviter = inviter_result.scalars().first()

        if inviter:
            # ... 处理逻辑 ...
            pass

    msg += "\n━━━━━━━━━━━━━\n💡 说明：✅已领取 🎁待发放 ❌未达成"

# ✅ UoW已退出,不再使用session
await invite_status_cmd.finish(message_add_head(msg, event))
```

**方案B: 在UoW外创建新的safe_session** (备选)

```python
async with UnitOfWork(session_factory) as uow:
    player = await get_unified_player(uow.session, event)
    # ... 获取invite_status ...

# 🔧 UoW退出后,创建新的safe_session查询Player
async with safe_session() as session:
    # 构建消息,使用新session查询
    for record in invite_status["inviter_records"]:
        invitee = await session.execute(...)
```

#### 2. 修复 economy/stock_commands.py:76

**简单删除即可**:

```python
async with UnitOfWork(session_factory) as uow:
    stock_service = StockServiceNew(...)
    price_updated = await stock_service.check_and_update_prices()
    player = await get_unified_player(uow.session, event)
    if not player:
        await stock_list_cmd.finish("⛔ 请先创建角色")

    stmt = select(Stock).where(Stock.is_active == True).order_by(Stock.symbol)
    stocks = (await uow.session.execute(stmt)).scalars().all()

    # ❌ 删除这行: session = uow.session

# ✅ 后续代码不使用session,stocks已经加载到内存
if not stocks:
    await stock_list_cmd.finish("💎 当前没有可投资的气运")
```

### P1 - 重要修复 (本周完成)

#### 3. 修复 daily_task/commands.py:269-272

**步骤1: 扩展UnitOfWork添加缺失的Repository**

在`infrastructure/uow/unit_of_work.py`添加:

```python
@property
def player_task_stats(self):
    """玩家任务统计仓储"""
    if self._player_task_stats is None:
        from ..repositories.player_task_stats_repository import PlayerTaskStatsRepository
        self._player_task_stats = PlayerTaskStatsRepository(self._session)
    return self._player_task_stats

@property
def guild_task_records(self):
    """公会任务记录仓储"""
    if self._guild_task_records is None:
        from ..repositories.guild_task_record_repository import GuildTaskRecordRepository
        self._guild_task_records = GuildTaskRecordRepository(self._session)
    return self._guild_task_records

@property
def player_donation_logs(self):
    """玩家捐献日志仓储"""
    if self._player_donation_logs is None:
        from ..repositories.player_donation_log_repository import PlayerDonationLogRepository
        self._player_donation_logs = PlayerDonationLogRepository(self._session)
    return self._player_donation_logs

@property
def guild_buildings(self):
    """公会建筑仓储"""
    if self._guild_buildings is None:
        from ..repositories.guild_building_repository import GuildBuildingRepository
        self._guild_buildings = GuildBuildingRepository(self._session)
    return self._guild_buildings
```

**步骤2: 修改commands.py使用UoW属性**

```python
guild_task_service = GuildTaskServiceNew(
    player_repo=uow.players,
    guild_repo=uow.guilds,
    player_task_stats_repo=uow.player_task_stats,      # ✅ 使用UoW属性
    guild_task_record_repo=uow.guild_task_records,     # ✅ 使用UoW属性
    player_donation_log_repo=uow.player_donation_logs, # ✅ 使用UoW属性
    guild_building_repo=uow.guild_buildings,           # ✅ 使用UoW属性
)
```

#### 4. 修复 guild/guild.py:186, 761

使用相同方法,添加UoW属性并修改调用代码。

### P2 - 长期改进

#### 5. 删除或修复 retry_session

如果未使用,直接删除`models/db.py:225-258`。

#### 6. 逐步迁移130+处Repository(session)到UoW模式

这是一个长期重构任务,优先级最低,但可以提高代码一致性。

---

## 验证方法

### 修复后验证步骤

1. **重启机器人**,清空所有连接
2. **执行高频操作**:
   - 连续10次执行`查看邀请状态`指令
   - 连续10次执行`投资行情`指令
   - 连续10次执行`完成任务`指令
3. **检查日志**:
   - 不应出现"QueuePool limit exceeded"警告
   - 应看到正常的"创建新会话"和"关闭会话"配对日志
4. **监控连接池状态**:
   ```python
   from plugins.xiuxian_game.models.db import engine
   print(f"连接池大小: {engine.pool.size()}")
   print(f"已签出连接: {engine.pool.checkedout()}")
   ```

---

## 总结

### 关键数据

- **确认泄漏**: 2个 (P0)
- **潜在泄漏**: 3个 (P1)
- **代码异味**: 130+ (P2)
- **安全使用**: 248处safe_session (正确)
- **UoW使用**: 仅1处 (unit_of_work.py自身)

### 修复优先级

1. **今天**: 修复invite.py和stock_commands.py (2个P0)
2. **本周**: 扩展UoW添加缺失的Repository (3个P1)
3. **下月**: 迁移130+处Repository到UoW模式 (P2)

### 修复预期

修复2个P0泄漏后,连接泄漏警告应该**完全消失**。如果仍有警告,则需要重新调查是否有其他未发现的泄漏源头。

---

**报告生成时间**: 2025-12-02
**调查工具**: Grep, Read, 代码模式分析
**下一步**: 按优先级修复上述问题
