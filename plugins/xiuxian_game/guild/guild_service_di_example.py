"""
GuildService DI使用示例

展示如何在Command Handler中使用依赖注入版本的GuildService
"""

from sqlalchemy.ext.asyncio import AsyncSession
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.guild_repository import GuildRepository
from .guild_service_new import GuildService
from ..models.db import AsyncSessionLocal


# ============================================================
# 方式1: 手动创建依赖 (不使用DI容器)
# ============================================================

async def example_create_guild_manual():
    """
    示例1: 手动创建依赖

    优点: 简单直接
    缺点: 每次都要手动创建依赖
    """
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        # 创建仓储
        player_repo = PlayerRepository(uow.session)
        guild_repo = GuildRepository(uow.session)

        # 创建Service (注入依赖)
        guild_service = GuildService(
            player_repo=player_repo,
            guild_repo=guild_repo,
            uow=uow  # 传入UoW以支持需要session的方法
        )

        # 调用业务方法
        success, message, guild = await guild_service.create_guild(
            player_id="123456789",
            guild_name="测试公会"
        )

        if success:
            print(f"✅ {message}")
            await uow.commit()
        else:
            print(f"❌ {message}")


# ============================================================
# 方式2: 使用UoW的属性访问 (推荐)
# ============================================================

async def example_create_guild_with_uow():
    """
    示例2: 使用UoW的players和guilds属性

    优点: UoW已经管理了仓储的生命周期
    缺点: 需要确保UoW已经初始化仓储
    """
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        # UoW已经有players和guilds仓储属性
        guild_service = GuildService(
            player_repo=uow.players,  # 使用UoW的players属性
            guild_repo=uow.guilds,    # 使用UoW的guilds属性
            uow=uow
        )

        success, message, guild = await guild_service.create_guild(
            player_id="123456789",
            guild_name="测试公会"
        )

        if success:
            print(f"✅ {message}")
            await uow.commit()
        else:
            print(f"❌ {message}")


# ============================================================
# 方式3: 使用DI容器 (最终目标)
# ============================================================

async def example_create_guild_with_di_container():
    """
    示例3: 使用DI容器 (需要先实现容器集成)

    优点: 完全解耦,最佳实践
    缺点: 需要额外的容器配置
    """
    from ..infrastructure.di import DIContainer

    # 假设全局容器已经注册了所有依赖
    global_container = DIContainer()

    # TODO: 注册依赖 (在启动时完成)
    # container.register_scoped(PlayerRepository, ...)
    # container.register_scoped(GuildRepository, ...)
    # container.register_scoped(GuildService, ...)

    # 使用时直接resolve
    # guild_service = global_container.resolve(GuildService)

    # 调用业务方法
    # success, message, guild = await guild_service.create_guild(...)

    print("⚠️ DI容器集成尚未实现,请先完成启动集成")


# ============================================================
# 实际Command Handler示例
# ============================================================

async def create_guild_command_handler(player_id: str, guild_name: str):
    """
    实际Command Handler示例

    这是一个典型的Nonebot2命令处理器如何调用Service的示例
    """
    def session_factory():
        return AsyncSessionLocal()

    try:
        async with UnitOfWork(session_factory) as uow:
            # 创建Service
            guild_service = GuildService(
                player_repo=uow.players,
                guild_repo=uow.guilds,
                uow=uow
            )

            # 调用业务逻辑
            success, message, guild = await guild_service.create_guild(
                player_id=player_id,
                guild_name=guild_name
            )

            if success:
                # 事务自动提交(UoW的__aexit__)
                return f"✅ {message}\n公会ID: {guild.id}"
            else:
                # 事务自动回滚
                return f"❌ {message}"

    except Exception as e:
        return f"❌ 创建公会失败: {str(e)}"


# ============================================================
# 对比: 旧版本 vs 新版本
# ============================================================

async def comparison_old_vs_new():
    """
    对比旧版本和新版本的调用方式
    """
    from ..models.db import safe_session
    from .guild_service import GuildService as OldGuildService
    from .guild_service_new import GuildService as NewGuildService

    # ========== 旧版本 (静态方法) ==========
    print("旧版本调用:")
    async with safe_session() as session:
        success, message, guild = await OldGuildService.create_guild(
            session=session,  # ❌ 需要传递session
            player_id="123456789",
            guild_name="测试公会"
        )
        print(f"  {message}")

    # ========== 新版本 (DI) ==========
    print("\n新版本调用:")
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        new_service = NewGuildService(
            player_repo=uow.players,
            guild_repo=uow.guilds,
            uow=uow
        )

        success, message, guild = await new_service.create_guild(
            # ✅ 不需要传递session,通过仓储访问数据
            player_id="123456789",
            guild_name="测试公会"
        )
        print(f"  {message}")


# ============================================================
# 优势总结
# ============================================================

"""
新版本的优势:

1. **更好的测试性**: 可以mock PlayerRepository和GuildRepository
2. **更清晰的职责划分**: Service只负责业务逻辑,Repository负责数据访问
3. **统一的事务管理**: 通过UoW确保一个命令=一个事务
4. **更易扩展**: 添加新的依赖只需修改构造函数
5. **类型安全**: IDE可以提供更好的代码补全和类型检查

需要注意的点:

1. 需要传入UoW以支持某些方法(如需要访问GuildPermission)
2. 复杂查询(如get_guild_members)暂时使用UoW.session直接查询
3. 迁移过程需要同时更新所有Command Handler

下一步:

1. 创建DI容器启动集成
2. 更新Command Handler使用新版Service
3. 测试验证功能
4. 逐步废弃旧版本
"""
