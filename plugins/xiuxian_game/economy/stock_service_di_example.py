"""StockService DI集成示例

展示如何在命令处理器中使用新版StockService（DI模式）

三种使用方式：
1. 手动创建Service（简单场景）
2. 通过UnitOfWork管理（推荐，支持事务）
3. 通过DI容器获取（全局配置）
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg

# ==================== 方式1: 手动创建（不推荐，仅用于简单查询） ====================

async def example_manual_creation(event: MessageEvent):
    """手动创建Service实例（简单查询场景）"""
    from ..models.db import safe_session
    from ..infrastructure.repositories.player_repository import PlayerRepository
    from ..infrastructure.repositories.stock_repository import StockRepository
    from ..infrastructure.repositories.stock_holding_repository import StockHoldingRepository
    from ..infrastructure.repositories.stock_transaction_repository import StockTransactionRepository
    from ..infrastructure.repositories.bank_account_repository import BankAccountRepository
    from .stock_service_new import StockService

    async with safe_session() as session:
        # 手动创建所有依赖
        player_repo = PlayerRepository(session)
        stock_repo = StockRepository(session)
        stock_holding_repo = StockHoldingRepository(session)
        stock_transaction_repo = StockTransactionRepository(session)
        bank_account_repo = BankAccountRepository(session)

        # 创建Service
        stock_service = StockService(
            player_repo=player_repo,
            stock_repo=stock_repo,
            stock_holding_repo=stock_holding_repo,
            stock_transaction_repo=stock_transaction_repo,
            bank_account_repo=bank_account_repo
        )

        # 使用Service（不需要传session参数）
        holdings = await stock_service.get_player_holdings(event.get_user_id())

        # safe_session会自动commit
        return holdings


# ==================== 方式2: 使用UnitOfWork（推荐） ====================

async def example_with_uow(event: MessageEvent):
    """使用UnitOfWork管理事务（推荐方式）"""
    from ..models.db import AsyncSessionLocal
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from .stock_service_new import StockService

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        # 通过UoW的属性直接获取所有仓储
        stock_service = StockService(
            player_repo=uow.players,
            stock_repo=uow.stocks,
            stock_holding_repo=uow.stock_holdings,
            stock_transaction_repo=uow.stock_transactions,
            bank_account_repo=uow.bank_accounts
        )

        # 执行业务操作（不需要传session）
        success, message = await stock_service.buy_stock(
            player_id=event.get_user_id(),
            stock_symbol="TECH001",
            shares=10,
            use_bank=False
        )

        # UoW会自动commit
        return success, message


# ==================== 方式3: 通过DI容器（全局配置，最优雅） ====================

async def example_with_container(event: MessageEvent):
    """使用DI容器（需要在启动时注册）"""
    from ..models.db import AsyncSessionLocal
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..infrastructure.di.container import DIContainer
    from .stock_service_new import StockService

    # 假设在启动时已注册
    # container = get_global_container()

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        # 如果使用DI容器，可以这样注册：
        # container.register_scoped(StockService, lambda c: StockService(
        #     player_repo=uow.players,
        #     stock_repo=uow.stocks,
        #     stock_holding_repo=uow.stock_holdings,
        #     stock_transaction_repo=uow.stock_transactions,
        #     bank_account_repo=uow.bank_accounts
        # ))
        #
        # stock_service = container.resolve(StockService)

        # 目前暂时直接创建
        stock_service = StockService(
            player_repo=uow.players,
            stock_repo=uow.stocks,
            stock_holding_repo=uow.stock_holdings,
            stock_transaction_repo=uow.stock_transactions,
            bank_account_repo=uow.bank_accounts
        )

        # 执行多个操作，共享同一个事务
        holdings = await stock_service.get_player_holdings(event.get_user_id())
        transactions = await stock_service.get_player_transactions(event.get_user_id())

        # UoW自动commit
        return holdings, transactions


# ==================== 实际命令处理器集成示例 ====================

# 旧版本（使用safe_session）
stock_buy_cmd_old = on_command("投资气运_旧", block=True, priority=5)

@stock_buy_cmd_old.handle()
async def handle_stock_buy_old(event: MessageEvent, args = CommandArg()):
    """旧版本：使用静态方法 + safe_session"""
    from ..models.db import safe_session
    from .stock_service import StockService

    args_list = str(args).strip().split()
    if len(args_list) != 2:
        await stock_buy_cmd_old.finish("⛔ 用法: 投资气运 <代码> <数量>")

    stock_symbol = args_list[0]
    try:
        shares = int(args_list[1])
    except ValueError:
        await stock_buy_cmd_old.finish("⛔ 数量必须是整数")

    async with safe_session() as session:
        # 旧版本：传入session参数
        success, message = await StockService.buy_stock(
            session=session,
            player_id=event.get_user_id(),
            stock_symbol=stock_symbol,
            shares=shares,
            use_bank=False
        )

        if success:
            await stock_buy_cmd_old.finish(f"✅ {message}")
        else:
            await stock_buy_cmd_old.finish(f"⛔ {message}")


# 新版本（使用UoW + DI）
stock_buy_cmd_new = on_command("投资气运_新", block=True, priority=5)

@stock_buy_cmd_new.handle()
async def handle_stock_buy_new(event: MessageEvent, args = CommandArg()):
    """新版本：使用DI模式 + UnitOfWork"""
    from ..models.db import AsyncSessionLocal
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from .stock_service_new import StockService

    args_list = str(args).strip().split()
    if len(args_list) != 2:
        await stock_buy_cmd_new.finish("⛔ 用法: 投资气运 <代码> <数量>")

    stock_symbol = args_list[0]
    try:
        shares = int(args_list[1])
    except ValueError:
        await stock_buy_cmd_new.finish("⛔ 数量必须是整数")

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        # 新版本：通过UoW获取所有仓储，创建Service
        stock_service = StockService(
            player_repo=uow.players,
            stock_repo=uow.stocks,
            stock_holding_repo=uow.stock_holdings,
            stock_transaction_repo=uow.stock_transactions,
            bank_account_repo=uow.bank_accounts
        )

        # 调用Service方法（不需要传session）
        success, message = await stock_service.buy_stock(
            player_id=event.get_user_id(),
            stock_symbol=stock_symbol,
            shares=shares,
            use_bank=False
        )

        # UoW会自动commit所有操作

        if success:
            await stock_buy_cmd_new.finish(f"✅ {message}")
        else:
            await stock_buy_cmd_new.finish(f"⛔ {message}")


# ==================== Feature Flag模式（推荐） ====================

# 在stock_commands.py顶部添加：
USE_NEW_STOCK_SERVICE = True  # 切换开关

stock_buy_cmd = on_command("投资气运", block=True, priority=5)

@stock_buy_cmd.handle()
async def handle_stock_buy(event: MessageEvent, args = CommandArg()):
    """支持新旧版本切换的命令处理器"""
    args_list = str(args).strip().split()
    if len(args_list) != 2:
        await stock_buy_cmd.finish("⛔ 用法: 投资气运 <代码> <数量>")

    stock_symbol = args_list[0]
    try:
        shares = int(args_list[1])
    except ValueError:
        await stock_buy_cmd.finish("⛔ 数量必须是整数")

    if USE_NEW_STOCK_SERVICE:
        # ===== 新版本路径 =====
        from ..models.db import AsyncSessionLocal
        from ..infrastructure.uow.unit_of_work import UnitOfWork
        from .stock_service_new import StockService

        def session_factory():
            return AsyncSessionLocal()

        async with UnitOfWork(session_factory) as uow:
            stock_service = StockService(
                player_repo=uow.players,
                stock_repo=uow.stocks,
                stock_holding_repo=uow.stock_holdings,
                stock_transaction_repo=uow.stock_transactions,
                bank_account_repo=uow.bank_accounts
            )

            success, message = await stock_service.buy_stock(
                player_id=event.get_user_id(),
                stock_symbol=stock_symbol,
                shares=shares,
                use_bank=False
            )
    else:
        # ===== 旧版本路径 =====
        from ..models.db import safe_session
        from .stock_service import StockService

        async with safe_session() as session:
            success, message = await StockService.buy_stock(
                session=session,
                player_id=event.get_user_id(),
                stock_symbol=stock_symbol,
                shares=shares,
                use_bank=False
            )

    # 统一返回
    if success:
        await stock_buy_cmd.finish(f"✅ {message}")
    else:
        await stock_buy_cmd.finish(f"⛔ {message}")


# ==================== 迁移步骤 ====================

"""
迁移步骤：

1. 在stock_commands.py顶部添加Feature Flag：
   ```python
   USE_NEW_STOCK_SERVICE = False  # 默认使用旧版本
   ```

2. 在一个命令处理器中添加新版本代码路径（如stock_buy_cmd）

3. 测试新版本功能：
   - 设置 USE_NEW_STOCK_SERVICE = True
   - 重启bot
   - 测试 "投资气运 TECH001 10"

4. 如果测试通过，逐步迁移其他命令处理器

5. 所有命令处理器迁移完成后，删除旧代码路径和Feature Flag

注意事项：
- 新旧版本业务逻辑完全一致
- 新版本优势：统一事务边界，避免多会话问题
- 新版本通过Repository访问数据，更好测试性
"""
