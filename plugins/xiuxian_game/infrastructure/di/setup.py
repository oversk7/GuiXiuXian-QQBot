"""
DI容器启动集成

在应用启动时初始化全局DI容器,注册所有服务
"""

from typing import Optional
from nonebot import logger

from .container import DIContainer
from ..repositories.player_repository import PlayerRepository
from ..repositories.guild_repository import GuildRepository
from ..repositories.item_repository import ItemRepository
from ..repositories.buff_repository import BuffRepository
from ..uow.unit_of_work import UnitOfWork
from ...models.db import AsyncSessionLocal


# 全局DI容器实例
_global_container: Optional[DIContainer] = None


def get_container() -> DIContainer:
    """
    获取全局DI容器

    Returns:
        全局容器实例

    Raises:
        RuntimeError: 如果容器未初始化
    """
    if _global_container is None:
        raise RuntimeError(
            "DI容器未初始化。请在应用启动时调用 setup_di_container()"
        )
    return _global_container


def setup_di_container() -> DIContainer:
    """
    初始化并配置全局DI容器

    在NoneBot的on_startup钩子中调用此函数

    Returns:
        配置好的容器实例
    """
    global _global_container

    logger.info("[DI] 开始初始化依赖注入容器...")

    container = DIContainer()

    # ========== 注册基础设施 ==========

    # 注册Session工厂 (Scoped: 每个请求一个session)
    def session_factory(c):
        return AsyncSessionLocal()

    container.register_scoped(
        "AsyncSession",
        session_factory
    )
    logger.debug("[DI] 已注册: AsyncSession (scoped)")

    # 注册UnitOfWork (Scoped: 每个请求一个UoW)
    def uow_factory(c):
        return UnitOfWork(AsyncSessionLocal)

    container.register_scoped(
        UnitOfWork,
        uow_factory
    )
    logger.debug("[DI] 已注册: UnitOfWork (scoped)")

    # ========== 注册Repository ==========

    # 注意: Repository需要在UoW上下文中创建,这里注册的是工厂函数

    def player_repo_factory(c):
        """PlayerRepository工厂 - 需要在UoW中使用"""
        # 这个工厂不直接使用,而是在UoW中通过uow.players访问
        raise NotImplementedError(
            "PlayerRepository应该通过UoW的players属性访问,而不是直接resolve"
        )

    container.register_transient(
        PlayerRepository,
        player_repo_factory
    )
    logger.debug("[DI] 已注册: PlayerRepository (transient)")

    def guild_repo_factory(c):
        """GuildRepository工厂 - 需要在UoW中使用"""
        raise NotImplementedError(
            "GuildRepository应该通过UoW的guilds属性访问,而不是直接resolve"
        )

    container.register_transient(
        GuildRepository,
        guild_repo_factory
    )
    logger.debug("[DI] 已注册: GuildRepository (transient)")

    # ========== 注册Service ==========

    # GuildService注册示例 (Scoped: 每个请求一个Service实例)
    def guild_service_factory(c):
        """
        GuildService工厂

        注意: 这是一个示例,实际使用时需要在Command Handler中
        通过UoW创建Service实例
        """
        raise NotImplementedError(
            "GuildService应该在Command Handler中手动创建,传入uow.players和uow.guilds"
        )

    # 暂时不注册GuildService,因为它需要UoW上下文
    # container.register_scoped(GuildService, guild_service_factory)
    logger.debug("[DI] GuildService暂不注册到容器(需要UoW上下文)")

    # ========== 完成初始化 ==========

    _global_container = container
    logger.success(f"[DI] 依赖注入容器初始化完成，已注册 {len(container._services)} 个服务")

    return container


def reset_container():
    """
    重置全局容器 (仅用于测试)
    """
    global _global_container
    _global_container = None
    logger.warning("[DI] 全局容器已重置")


# ============================================================
# 使用指南
# ============================================================

"""
使用方式1: 在Command Handler中手动创建Service (推荐)

```python
from ..models.db import AsyncSessionLocal
from ..infrastructure.uow import UnitOfWork
from ..guild.guild_service_new import GuildService

async def create_guild_handler(player_id: str, guild_name: str):
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        # 使用UoW的仓储属性
        guild_service = GuildService(
            player_repo=uow.players,
            guild_repo=uow.guilds,
            uow=uow
        )

        success, message, guild = await guild_service.create_guild(
            player_id=player_id,
            guild_name=guild_name
        )

        if success:
            return f"✅ {message}"
        else:
            return f"❌ {message}"
```

使用方式2: 通过容器获取UoW (高级用法)

```python
from ..infrastructure.di.setup import get_container
from ..infrastructure.uow import UnitOfWork

async def some_handler():
    container = get_container()

    # 获取UoW (每次resolve都创建新的scoped实例)
    uow = container.resolve(UnitOfWork)

    async with uow:
        # 使用uow...
        pass
```

注意事项:

1. **UoW是核心**: 所有数据访问都应该通过UoW进行
2. **Service不要全局单例**: Service应该在每个请求中创建,传入当前的UoW
3. **Repository通过UoW访问**: 使用uow.players, uow.guilds等属性
4. **事务由UoW管理**: async with UoW自动管理commit/rollback

为什么不完全使用DI容器?

1. UoW需要在async with上下文中使用,不适合自动注入
2. Service需要UoW上下文,不能在容器中预先创建
3. 当前的设计更接近"Service Locator + UoW"模式,而不是纯DI

未来优化方向:

1. 实现基于装饰器的自动依赖注入
2. 使用AOP(面向切面编程)自动管理事务
3. 完全异步的依赖解析器
"""
