# 重构后的代码使用示例

本文档提供重构后代码的使用示例，展示如何使用Repository和UnitOfWork。

## 示例1: 修复player/info.py的多会话问题

### 问题代码 (旧)

```python
# player/info.py - 打开4个独立会话，破坏事务原子性
@profile.handle()
async def handle_profile(event: MessageEvent):
    # 会话1: 获取玩家
    async with safe_session() as session1:
        player = await get_player(session1, event)

    # 会话2: 更新导航
    async with safe_session() as session2:
        # 更新逻辑...
        pass

    # 会话3: 查询属性
    async with safe_session() as session3:
        attrs = await player.get_effective_attributes(session3)

    # 会话4: 查询公会
    async with safe_session() as session4:
        if player.guild_id:
            guild = await session4.get(Guild, player.guild_id)
```

**问题**:
- 打开4个独立会话，每个会话独立提交
- 无法保证整体业务逻辑的原子性
- 可能导致部分成功、部分失败的不一致状态

### 解决方案 (新)

```python
# player/info_v2.py - 使用UnitOfWork统一事务边界
from ...infrastructure.uow import UnitOfWork
from ...models.db import AsyncSessionLocal

@profile_v2.handle()
async def handle_profile_v2(event: MessageEvent):
    """重构后的个人信息查询 - 使用UnitOfWork"""

    # 单一事务边界，所有操作共享同一个会话
    async with UnitOfWork(AsyncSessionLocal) as uow:
        # 获取玩家
        player = await uow.players.get_by_uid(event.get_user_id())
        if not player:
            await profile_v2.finish("你还未创建角色")

        # 查询公会信息（如果有）
        guild = None
        if player.guild_id:
            guild = await uow.guilds.get_by_id(player.guild_id)

        # 查询临时buff
        active_buffs = await uow.buffs.get_active_buffs(player.id)

        # 查询月卡（优化了N+1查询）
        player_with_cards = await uow.players.get_with_monthly_cards(player.id)

        # 更新导航时间戳
        player.last_info_check = datetime.now()

        # 所有操作在同一个事务中提交
        await uow.commit()

        # 构建响应消息
        message = build_profile_message(player, guild, active_buffs, player_with_cards.monthly_cards)
        await profile_v2.send(message)
```

**优点**:
- ✅ 单一事务边界，确保原子性
- ✅ 所有仓储共享同一个会话
- ✅ 代码更清晰，易于理解
- ✅ 优化了N+1查询（使用joinedload）

## 示例2: 使用Repository优化查询

### 问题代码 (旧)

```python
# bank.py deposit_rank_cmd - N+1查询
async with safe_session() as session:
    stmt = select(BankAccount).order_by(BankAccount.balance.desc()).limit(30)
    accounts = (await session.execute(stmt)).scalars().all()

    for i, acc in enumerate(accounts):
        player = await session.get(Player, acc.player_id)  # ❌ N+1查询
        # ...
```

### 解决方案 (新)

```python
# bank_v2.py - 使用Repository优化查询
from ...infrastructure.uow import UnitOfWork
from ...infrastructure.repositories.bank_repository import BankRepository

@deposit_rank_v2.handle()
async def handle_deposit_rank_v2():
    """存款排行榜 - 优化后"""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        # 使用Repository的优化查询（预加载Player）
        top_accounts = await uow.banks.get_top_accounts_with_players(30)

        # 直接访问player，不触发额外查询
        for i, acc in enumerate(top_accounts):
            player = acc.player  # ✅ 已经预加载，不触发查询
            # ...
```

## 示例3: 自定义Repository方法

```python
# infrastructure/repositories/player_repository.py
class PlayerRepository(IRepository[Player]):
    # ... 基础方法 ...

    async def get_nearby_players(
        self,
        x: int,
        y: int,
        region: str,
        max_distance: int
    ) -> List[Player]:
        """
        获取附近的玩家（优化的查询）

        - 使用边界框预过滤（数据库层）
        - 使用曼哈顿距离后过滤（应用层）
        """
        # 边界框查询（利用索引）
        stmt = select(Player).where(
            and_(
                Player.region == region,
                Player.x.between(x - max_distance, x + max_distance),
                Player.y.between(y - max_distance, y + max_distance)
            )
        )
        result = await self._session.execute(stmt)
        players = result.scalars().all()

        # 曼哈顿距离后过滤
        return [
            p for p in players
            if abs(p.x - x) + abs(p.y - y) <= max_distance
        ]
```

## 迁移策略

### 阶段1: 并行开发（当前）

保留旧代码，创建新的v2版本：

```python
# player/info.py - 旧版本（保留）
@profile.handle()
async def handle_profile(event):
    # 旧逻辑...
    pass

# player/info_v2.py - 新版本（并行开发）
@profile_v2.handle()
async def handle_profile_v2(event):
    # 新逻辑（使用UoW）...
    pass
```

### 阶段2: Feature Flag切换

```python
from ...config import config

@profile.handle()
async def handle_profile(event):
    if config.feature_flags.get('use_uow', False):
        return await handle_profile_v2(event)
    else:
        # 旧逻辑...
        pass
```

### 阶段3: 完全切换

验证无误后，删除旧代码，将v2重命名为主版本。

## 测试示例

```python
# tests/test_player_repository.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from infrastructure.repositories import PlayerRepository
from models.player import Player

@pytest.fixture
async def test_db():
    """创建测试数据库"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.mark.asyncio
async def test_player_repository_get_by_id(test_db):
    """测试根据ID获取玩家"""
    async with AsyncSession(test_db) as session:
        repo = PlayerRepository(session)

        # 添加测试玩家
        player = Player(id="test_player", uid="123456", nickname="测试玩家")
        await repo.add(player)
        await session.commit()

        # 查询玩家
        found = await repo.get_by_id("test_player")
        assert found is not None
        assert found.nickname == "测试玩家"

@pytest.mark.asyncio
async def test_uow_transaction():
    """测试UoW事务管理"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = Player(uid="123456", nickname="测试玩家")
        await uow.players.add(player)

        guild = Guild(name="测试公会", leader_id=player.id)
        await uow.guilds.add(guild)

        # 同一个事务中
        await uow.commit()

    # 验证
    async with UnitOfWork(AsyncSessionLocal) as uow:
        found_player = await uow.players.get_by_uid("123456")
        found_guild = await uow.guilds.get_by_name("测试公会")
        assert found_player is not None
        assert found_guild is not None
```

## 常见问题

### Q: 如何获取UnitOfWork的会话？

A: 使用`uow.session`属性（但尽量避免直接操作会话）：

```python
async with UnitOfWork(AsyncSessionLocal) as uow:
    # 尽量使用仓储方法
    player = await uow.players.get_by_id(player_id)

    # 特殊情况下可以直接访问会话
    raw_result = await uow.session.execute(custom_query)
```

### Q: 如何在UoW中处理异常？

A: UoW会自动回滚异常：

```python
async with UnitOfWork(AsyncSessionLocal) as uow:
    try:
        player = await uow.players.get_by_id(player_id)
        if not player:
            raise PlayerNotFoundError("玩家不存在")

        player.gold += 100
        await uow.commit()
    except PlayerNotFoundError:
        # UoW已自动回滚
        await profile.finish("玩家不存在")
```

### Q: 旧代码还能用吗？

A: 可以！重构是渐进式的，旧代码保持不变，可以逐步迁移。
