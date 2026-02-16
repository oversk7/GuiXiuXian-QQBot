# Repositories Layer - 数据访问

**文件数:** 35 | **基类:** IRepository[T]

## OVERVIEW

Repository模式实现。泛型接口 + 领域查询方法。UoW管理Session共享。

## WHERE TO LOOK

| Repository | 文件 | 核心方法 |
|------------|------|----------|
| PlayerRepository | `player_repository.py` | get_by_uid, get_nearby_players |
| ItemRepository | `item_repository.py` | get_by_owner, find_by_name |
| GuildRepository | `guild_repository.py` | get_by_name, get_member_count |
| NPCRepository | `npc_repository.py` | get_by_location |

## PATTERN

```python
class IRepository(Protocol[T]):
    async def get_by_id(self, id: Any) -> T | None: ...
    async def save(self, entity: T) -> T: ...
    async def delete(self, entity: T) -> None: ...

class PlayerRepository(IRepository[Player]):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_uid(self, uid: str) -> Player | None:
        return await self._session.get(Player, uid)

    async def get_nearby_players(self, x: int, y: int, radius: int) -> list[Player]:
        stmt = select(Player).where(...)
        return (await self._session.execute(stmt)).scalars().all()
```

## CONVENTIONS

- 构造函数注入 `AsyncSession`
- 查询命名: `get_by_*` (单值), `find_*` (列表)
- 预加载: 使用 `joinedload()` 避免N+1
- **禁止commit/rollback** → 由UoW管理

## ANTI-PATTERNS

```python
# ❌ 错误: Repository内commit
async def save(self, player: Player) -> Player:
    self._session.add(player)
    await self._session.commit()  # 禁止!

# ✅ 正确: 只add，让UoW commit
async def save(self, player: Player) -> Player:
    self._session.add(player)
    return player
```
