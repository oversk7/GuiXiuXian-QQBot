"""股票交易命令接口

提供用户交互命令：
1. 查看股票列表
2. 买入股票
3. 卖出股票
4. 查看持仓
5. 查看交易记录
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select
from datetime import datetime, timedelta
from nonebot.permission import SUPERUSER
from ..models.db import safe_session
from ..models.player import Player
from ..models.stock import Stock, StockType, StockPriceHistory
from ..utils import message_add_head
from ..platform_utils import get_unified_player
from .stock_service import StockService
from .stock_price_engine import StockPriceEngine
from ..config import config
import random

# ==================== Feature Flag ====================
# 设置为True使用新版DI架构的StockService，False使用旧版本
USE_NEW_STOCK_SERVICE = True
# =====================================================

# 气运投资相关命令
stock_list_cmd = on_command("气运行情", aliases={"投资行情", "灵石行情"}, block=True, priority=5)
stock_buy_cmd = on_command("投资气运", aliases={"投资灵石"}, block=True, priority=5)
stock_sell_cmd = on_command("出售气运", aliases={"出售灵石"}, block=True, priority=5)
stock_holdings_cmd = on_command("我的投资", aliases={"我的气运"}, block=True, priority=5)
stock_transactions_cmd = on_command("投资记录", aliases={"气运记录"}, block=True, priority=5)
stock_refresh_time_cmd = on_command("气运刷新时间", aliases={"投资刷新时间", "价格刷新时间"}, block=True, priority=5)
stock_history_cmd = on_command("气运历史", aliases={"价格历史"}, block=True, priority=5)
stock_analysis_cmd = on_command("气运分析", aliases={"投资分析"}, block=True, priority=5)
stock_init_cmd = on_command("初始化气运", block=True, priority=5, permission=SUPERUSER)
stock_update_cmd = on_command("更新气运价格", aliases={"刷新气运价格"}, block=True, priority=5, permission=SUPERUSER)


@stock_list_cmd.handle()
async def handle_stock_list(event: MessageEvent):
    """查看气运投资行情"""
    try:
        await _handle_stock_list_impl(event)
    except Exception as e:
        from nonebot import logger
        logger.error(f"❌ [投资行情] 发生错误: {e}", exc_info=True)
        await stock_list_cmd.finish(message_add_head(f"⛔ 系统错误：{e}", event))


async def _handle_stock_list_impl(event: MessageEvent):
    """内部实现：查看气运投资行情"""
    if USE_NEW_STOCK_SERVICE:
        # 新版本: 使用DI架构
        from ..infrastructure.uow.unit_of_work import UnitOfWork
        from ..models.db import AsyncSessionLocal
        from .stock_service_new import StockService as StockServiceNew

        def session_factory():
            return AsyncSessionLocal()

        async with UnitOfWork(session_factory) as uow:
            # 创建StockService实例
            stock_service = StockServiceNew(
                player_repo=uow.players,
                stock_repo=uow.stocks,
                stock_holding_repo=uow.stock_holdings,
                stock_transaction_repo=uow.stock_transactions,
                bank_account_repo=uow.bank_accounts
            )

            # 被动触发价格更新
            price_updated = await stock_service.check_and_update_prices()

            player = await get_unified_player(uow.session, event)
            if not player:
                await stock_list_cmd.finish("⛔ 请先创建角色")

            # 获取所有活跃股票
            stmt = select(Stock).where(Stock.is_active == True).order_by(Stock.symbol)
            stocks = (await uow.session.execute(stmt)).scalars().all()

            session = uow.session  # 为后续代码提供session引用
    else:
        # 旧版本: 使用静态方法
        async with safe_session() as session:
            # 被动触发价格更新
            price_updated = await StockService.check_and_update_prices(session)

            player = await get_unified_player(session, event)
            if not player:
                await stock_list_cmd.finish("⛔ 请先创建角色")

            # 获取所有活跃股票
            stmt = select(Stock).where(Stock.is_active == True).order_by(Stock.symbol)
            stocks = (await session.execute(stmt)).scalars().all()

    # 检查是否有股票数据（新旧版本共用）
    if not stocks:
        await stock_list_cmd.finish("💎 当前没有可投资的气运")

    # 按类型分组显示
    type_groups = {}
    for stock in stocks:
        if stock.stock_type not in type_groups:
            type_groups[stock.stock_type] = []
        type_groups[stock.stock_type].append(stock)

    # 构建消息
    lines = ["💎 气运投资行情", "▃▃▃▃▃▃▃▃▃▃"]

    # 计算下次刷新时间（整点刷新）
    now = datetime.now()
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    next_hour = current_hour + timedelta(hours=1)
    time_until_update = next_hour - now

    # 显示刷新时间信息
    if price_updated:
        lines.append("🔄 价格已更新")
    else:
        minutes = int(time_until_update.total_seconds() // 60)
        seconds = int(time_until_update.total_seconds() % 60)
        if minutes > 0:
            lines.append(f"⏰ 下次刷新：{minutes}分{seconds}秒后 ({next_hour.strftime('%H:%M')}整点)")
        else:
            lines.append(f"⏰ 下次刷新：{seconds}秒后")
    lines.append("")

    type_names = {
        StockType.TECH: "🔬 法宝气运",
        StockType.FINANCE: "🏦 金融气运",
        StockType.ENERGY: "⚡ 灵气气运",
        StockType.CONSUMER: "🛒 丹药气运",
        StockType.HEALTHCARE: "🏥 医道气运",
        StockType.MATERIALS: "🏗️ 材料气运"
    }

    for stock_type, stocks_in_type in type_groups.items():
        lines.append(f"\n{type_names.get(stock_type, stock_type)}")
        for stock in stocks_in_type:
            # 计算涨跌
            change_rate = ((stock.current_price - stock.base_price) / stock.base_price) * 100
            change_symbol = "📈" if change_rate > 0 else "📉" if change_rate < 0 else "➡️"

            lines.append(
                f"{stock.symbol} {stock.name}\n"
                f"  💰 {stock.current_price} 金币 {change_symbol}"
            )

    lines.append("\n💡 使用「投资气运 代码 数量」进行投资")
    lines.append("💡 使用「投资气运 代码 数量 银行」从银行账户扣款")

    await stock_list_cmd.finish(message_add_head("\n".join(lines), event))


@stock_buy_cmd.handle()
async def handle_stock_buy(event: MessageEvent, args: Message = CommandArg()):
    """投资气运"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await stock_buy_cmd.finish("⛔ 格式：投资气运 <气运代码> <数量> [银行]")

    parts = args_text.split()
    if len(parts) < 2:
        await stock_buy_cmd.finish("⛔ 格式：投资气运 <气运代码> <数量> [银行]")

    symbol = parts[0].upper()
    try:
        shares = int(parts[1])
        if shares <= 0:
            raise ValueError
    except ValueError:
        await stock_buy_cmd.finish("⛔ 气运数量必须为正整数")

    use_bank = len(parts) > 2 and parts[2] in ["银行", "bank"]

    # 获取玩家ID
    from ..platform_utils import get_platform_info
    _, user_id = get_platform_info(event)

    # 执行买入
    if USE_NEW_STOCK_SERVICE:
        # 新版本: 使用DI架构
        from ..infrastructure.uow.unit_of_work import UnitOfWork
        from ..models.db import AsyncSessionLocal
        from .stock_service_new import StockService as StockServiceNew

        def session_factory():
            return AsyncSessionLocal()

        async with UnitOfWork(session_factory) as uow:
            # 创建StockService实例
            stock_service = StockServiceNew(
                player_repo=uow.players,
                stock_repo=uow.stocks,
                stock_holding_repo=uow.stock_holdings,
                stock_transaction_repo=uow.stock_transactions,
                bank_account_repo=uow.bank_accounts
            )

            # 使用新版本买入
            success, message = await stock_service.buy_stock(
                user_id, symbol, shares, use_bank
            )
    else:
        # 旧版本: 使用静态方法
        async with safe_session() as session:
            success, message = await StockService.buy_stock(
                session, user_id, symbol, shares, use_bank
            )

    if success:
        await stock_buy_cmd.finish(message_add_head(f"✅ {message}", event))
    else:
        await stock_buy_cmd.finish(message_add_head(f"⛔ {message}", event))


@stock_sell_cmd.handle()
async def handle_stock_sell(event: MessageEvent, args: Message = CommandArg()):
    """出售气运"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await stock_sell_cmd.finish("⛔ 格式：出售气运 <气运代码> <数量> [银行]")

    parts = args_text.split()
    if len(parts) < 2:
        await stock_sell_cmd.finish("⛔ 格式：出售气运 <气运代码> <数量> [银行]")

    symbol = parts[0].upper()
    try:
        shares = int(parts[1])
        if shares <= 0:
            raise ValueError
    except ValueError:
        await stock_sell_cmd.finish("⛔ 气运数量必须为正整数")

    to_bank = len(parts) > 2 and parts[2] in ["银行", "bank"]

    # 获取玩家ID
    from ..platform_utils import get_platform_info
    _, user_id = get_platform_info(event)

    # 执行卖出
    if USE_NEW_STOCK_SERVICE:
        # 新版本: 使用DI架构
        from ..infrastructure.uow.unit_of_work import UnitOfWork
        from ..models.db import AsyncSessionLocal
        from .stock_service_new import StockService as StockServiceNew

        def session_factory():
            return AsyncSessionLocal()

        async with UnitOfWork(session_factory) as uow:
            # 创建StockService实例
            stock_service = StockServiceNew(
                player_repo=uow.players,
                stock_repo=uow.stocks,
                stock_holding_repo=uow.stock_holdings,
                stock_transaction_repo=uow.stock_transactions,
                bank_account_repo=uow.bank_accounts
            )

            # 使用新版本卖出
            success, message = await stock_service.sell_stock(
                user_id, symbol, shares, to_bank
            )
    else:
        # 旧版本: 使用静态方法
        async with safe_session() as session:
            success, message = await StockService.sell_stock(
                session, user_id, symbol, shares, to_bank
            )

    if success:
        await stock_sell_cmd.finish(message_add_head(f"✅ {message}", event))
    else:
        await stock_sell_cmd.finish(message_add_head(f"⛔ {message}", event))


@stock_holdings_cmd.handle()
async def handle_stock_holdings(event: MessageEvent):
    """查看气运投资持仓"""
    # 获取玩家ID
    from ..platform_utils import get_platform_info
    _, user_id = get_platform_info(event)

    # 被动触发价格更新和获取持仓
    if USE_NEW_STOCK_SERVICE:
        # 新版本: 使用DI架构
        from ..infrastructure.uow.unit_of_work import UnitOfWork
        from ..models.db import AsyncSessionLocal
        from .stock_service_new import StockService as StockServiceNew

        def session_factory():
            return AsyncSessionLocal()

        async with UnitOfWork(session_factory) as uow:
            # 创建StockService实例
            stock_service = StockServiceNew(
                player_repo=uow.players,
                stock_repo=uow.stocks,
                stock_holding_repo=uow.stock_holdings,
                stock_transaction_repo=uow.stock_transactions,
                bank_account_repo=uow.bank_accounts
            )

            # 使用新版本
            price_updated = await stock_service.check_and_update_prices()
            holdings = await stock_service.get_player_holdings(user_id)
    else:
        # 旧版本: 使用静态方法
        async with safe_session() as session:
            price_updated = await StockService.check_and_update_prices(session)
            holdings = await StockService.get_player_holdings(session, user_id)

    if not holdings:
        await stock_holdings_cmd.finish(message_add_head("� 您当前没有投资", event))

    lines = ["🗠 我的气运投资", "▃▃▃▃▃▃▃▃▃▃"]

    # 获取刷新时间信息
    if USE_NEW_STOCK_SERVICE:
        from ..infrastructure.uow.unit_of_work import UnitOfWork
        from ..models.db import AsyncSessionLocal

        def session_factory():
            return AsyncSessionLocal()

        async with UnitOfWork(session_factory) as uow:
            stmt = select(Stock).where(Stock.is_active == True).order_by(Stock.updated_at.desc()).limit(1)
            latest_stock = (await uow.session.execute(stmt)).scalars().first()

            if latest_stock:
                next_update_time = latest_stock.updated_at + StockService.PRICE_UPDATE_INTERVAL
                now = datetime.now()
                time_until_update = next_update_time - now

                if price_updated:
                    lines.append("🔄 价格已更新")
                else:
                    if time_until_update.total_seconds() > 0:
                        hours = int(time_until_update.total_seconds() // 3600)
                        minutes = int((time_until_update.total_seconds() % 3600) // 60)
                        if hours > 0:
                            lines.append(f"⏰ 下次刷新：{hours}小时{minutes}分钟后")
                        else:
                            lines.append(f"⏰ 下次刷新：{minutes}分钟后")
                    else:
                        lines.append("⏰ 即将刷新价格...")
                lines.append("")
    else:
        async with safe_session() as session:
            stmt = select(Stock).where(Stock.is_active == True).order_by(Stock.updated_at.desc()).limit(1)
            latest_stock = (await session.execute(stmt)).scalars().first()

            if latest_stock:
                next_update_time = latest_stock.updated_at + StockService.PRICE_UPDATE_INTERVAL
                now = datetime.now()
                time_until_update = next_update_time - now

                if price_updated:
                    lines.append("🔄 价格已更新")
                else:
                    if time_until_update.total_seconds() > 0:
                        hours = int(time_until_update.total_seconds() // 3600)
                        minutes = int((time_until_update.total_seconds() % 3600) // 60)
                        if hours > 0:
                            lines.append(f"⏰ 下次刷新：{hours}小时{minutes}分钟后")
                        else:
                            lines.append(f"⏰ 下次刷新：{minutes}分钟后")
                    else:
                        lines.append("⏰ 即将刷新价格...")
                lines.append("")

    total_value = 0
    total_cost = 0

    for holding in holdings:
        total_value += holding["current_value"]
        total_cost += holding["total_cost"]

        profit_symbol = "📈" if holding["profit_loss"] > 0 else "📉" if holding["profit_loss"] < 0 else "➡️"

        lines.append(
            f"\n{holding['symbol']} {holding['name']}\n"
            f"  🗠 持有：{holding['shares']} 份\n"
            f"  💰 成本：{holding['avg_cost']} 金币/份\n"
            f"  ✨ 现价：{holding['current_price']} 金币/份\n"
            f"  💵 价值：{holding['current_value']} 金币\n"
            f"  {profit_symbol} 盈亏：{holding['profit_loss']:+} 金币 ({holding['profit_loss_rate']:+.2f}%)"
        )

    total_profit = total_value - total_cost
    total_profit_rate = (total_profit / total_cost * 100) if total_cost > 0 else 0
    profit_symbol = "📈" if total_profit > 0 else "📉" if total_profit < 0 else "➡️"

    lines.append(f"\n💰 总价值：{total_value} 金币")
    lines.append(f"💰 总成本：{total_cost} 金币")
    lines.append(f"{profit_symbol} 总盈亏：{total_profit:+} 金币 ({total_profit_rate:+.2f}%)")

    await stock_holdings_cmd.finish(message_add_head("\n".join(lines), event))


@stock_transactions_cmd.handle()
async def handle_stock_transactions(event: MessageEvent):
    """查看投资记录"""
    # 获取玩家ID
    from ..platform_utils import get_platform_info
    _, user_id = get_platform_info(event)

    if USE_NEW_STOCK_SERVICE:
        # 新版本: 使用DI架构
        from ..infrastructure.uow.unit_of_work import UnitOfWork
        from ..models.db import AsyncSessionLocal
        from .stock_service_new import StockService as StockServiceNew

        def session_factory():
            return AsyncSessionLocal()

        async with UnitOfWork(session_factory) as uow:
            # 创建StockService实例
            stock_service = StockServiceNew(
                player_repo=uow.players,
                stock_repo=uow.stocks,
                stock_holding_repo=uow.stock_holdings,
                stock_transaction_repo=uow.stock_transactions,
                bank_account_repo=uow.bank_accounts
            )

            # 使用新版本
            transactions = await stock_service.get_player_transactions(user_id, 10)
    else:
        # 旧版本: 使用静态方法
        async with safe_session() as session:
            transactions = await StockService.get_player_transactions(session, user_id, 10)

    if not transactions:
        await stock_transactions_cmd.finish(message_add_head("📋 您还没有投资记录", event))

    lines = ["📋 最近投资记录", "▃▃▃▃▃▃▃▃▃▃"]

    for trans in transactions:
        type_symbol = "🟢" if trans["type"] == "BUY" else "🔴"
        type_text = "投资" if trans["type"] == "BUY" else "出售"

        lines.append(
            f"\n{type_symbol} {type_text} {trans['symbol']} {trans['name']}\n"
            f"  � 数量：{trans['shares']} 份\n"
            f"  💰 价格：{trans['price']} 金币/份\n"
            f"  💵 金额：{trans['total_amount']} 金币\n"
            f"  💸 手续费：{trans['commission']} 金币\n"
            f"  🕐 时间：{trans['created_at'].strftime('%m-%d %H:%M')}"
        )

    await stock_transactions_cmd.finish(message_add_head("\n".join(lines), event))


@stock_init_cmd.handle()
async def handle_stock_init(event: MessageEvent):
    """初始化气运投资数据（仅管理员）"""
    # 检查权限
    async with safe_session() as session:
        # 检查是否已有气运数据
        try:
            existing_stocks = (await session.execute(select(Stock))).scalars().all()
            if existing_stocks:
                await stock_init_cmd.finish("⛔ 气运投资数据已存在，无需重复初始化")
        except Exception as e:
            await stock_init_cmd.finish(f"⛔ 检查数据失败：{e}")

        # 初始气运投资数据
        initial_stocks = [
            {"symbol": "TECH01", "name": "法宝工坊", "type": StockType.TECH, "base_price": 100, "volatility": 0.08},
            {"symbol": "TECH02", "name": "阵法研究", "type": StockType.TECH, "base_price": 150, "volatility": 0.10},
            {"symbol": "TECH03", "name": "符箓制作", "type": StockType.TECH, "base_price": 80, "volatility": 0.09},

            {"symbol": "FIN01", "name": "冥界钱庄", "type": StockType.FINANCE, "base_price": 200, "volatility": 0.04},
            {"symbol": "FIN02", "name": "仙界商会", "type": StockType.FINANCE, "base_price": 120, "volatility": 0.05},

            {"symbol": "ENE01", "name": "灵脉开采", "type": StockType.ENERGY, "base_price": 180, "volatility": 0.06},
            {"symbol": "ENE02", "name": "雷电收集", "type": StockType.ENERGY, "base_price": 90, "volatility": 0.07},

            {"symbol": "CON01", "name": "丹药坊", "type": StockType.CONSUMER, "base_price": 60, "volatility": 0.03},
            {"symbol": "CON02", "name": "灵草种植", "type": StockType.CONSUMER, "base_price": 110, "volatility": 0.04},

            {"symbol": "MED01", "name": "医仙堂", "type": StockType.HEALTHCARE, "base_price": 140, "volatility": 0.05},

            {"symbol": "MAT01", "name": "矿石开采", "type": StockType.MATERIALS, "base_price": 70, "volatility": 0.07},
            {"symbol": "MAT02", "name": "炼器材料", "type": StockType.MATERIALS, "base_price": 95, "volatility": 0.08},
        ]

        # 创建气运投资项目
        for stock_data in initial_stocks:
            stock = Stock(
                symbol=stock_data["symbol"],
                name=stock_data["name"],
                stock_type=stock_data["type"],
                base_price=stock_data["base_price"],
                current_price=stock_data["base_price"],  # 初始价格等于基础价格
                volatility=stock_data["volatility"],
                total_shares=1000000,
                circulating_shares=1000000
            )
            session.add(stock)

        await session.commit()
        await stock_init_cmd.finish("✅ 气运投资数据初始化完成！共创建了12个投资项目")

@stock_update_cmd.handle()
async def handle_stock_update(event: MessageEvent):
    """手动更新气运价格（仅管理员）"""
    # 注意：权限检查已在命令注册时通过 permission=SUPERUSER 完成，这里无需再次检查
    try:
        # 强制更新价格
        if USE_NEW_STOCK_SERVICE:
            # 新版本: 使用DI架构
            from ..infrastructure.uow.unit_of_work import UnitOfWork
            from ..models.db import AsyncSessionLocal
            from .stock_service_new import StockService as StockServiceNew

            def session_factory():
                return AsyncSessionLocal()

            async with UnitOfWork(session_factory) as uow:
                # 创建StockService实例
                stock_service = StockServiceNew(
                    player_repo=uow.players,
                    stock_repo=uow.stocks,
                    stock_holding_repo=uow.stock_holdings,
                    stock_transaction_repo=uow.stock_transactions,
                    bank_account_repo=uow.bank_accounts
                )

                # 使用新版本强制更新
                updated = await stock_service.check_and_update_prices(force_update=True)
        else:
            # 旧版本: 使用静态方法
            async with safe_session() as session:
                updated = await StockService.check_and_update_prices(session, force_update=True)

        if updated:
            await stock_update_cmd.finish(message_add_head("✅ 气运价格已强制更新", event))
        else:
            await stock_update_cmd.finish(message_add_head("⚠️ 价格更新失败或无需更新", event))

    except Exception as e:
        await stock_update_cmd.finish(message_add_head(f"❌ 更新气运价格失败：{e}", event))


@stock_refresh_time_cmd.handle()
async def handle_stock_refresh_time(event: MessageEvent):
    """查看气运价格刷新时间"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await stock_refresh_time_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await stock_refresh_time_cmd.finish("⛔ 请先创建角色")

        # 获取最近更新的股票
        stmt = select(Stock).where(Stock.is_active == True).order_by(Stock.updated_at.desc()).limit(1)
        latest_stock = (await session.execute(stmt)).scalars().first()

        if not latest_stock:
            await stock_refresh_time_cmd.finish("💎 当前没有可投资的气运")

        now = datetime.now()
        last_update_time = latest_stock.updated_at
        next_update_time = last_update_time + StockService.PRICE_UPDATE_INTERVAL
        time_until_update = next_update_time - now
        time_since_update = now - last_update_time

        lines = ["⏰ 气运价格刷新时间", "▃▃▃▃▃▃▃▃▃▃"]

        # 上次更新时间
        hours_since = int(time_since_update.total_seconds() // 3600)
        minutes_since = int((time_since_update.total_seconds() % 3600) // 60)
        if hours_since > 0:
            lines.append(f"📅 上次更新：{hours_since}小时{minutes_since}分钟前")
        else:
            lines.append(f"📅 上次更新：{minutes_since}分钟前")

        lines.append(f"🕐 更新时间：{last_update_time.strftime('%m-%d %H:%M:%S')}")

        # 下次更新时间
        if time_until_update.total_seconds() > 0:
            hours_until = int(time_until_update.total_seconds() // 3600)
            minutes_until = int((time_until_update.total_seconds() % 3600) // 60)
            if hours_until > 0:
                lines.append(f"⏳ 下次更新：{hours_until}小时{minutes_until}分钟后")
            else:
                lines.append(f"⏳ 下次更新：{minutes_until}分钟后")
            lines.append(f"🎯 预计时间：{next_update_time.strftime('%m-%d %H:%M:%S')}")
        else:
            lines.append("⏳ 下次更新：即将刷新...")

        lines.append("")
        lines.append("💡 刷新规则说明：")
        lines.append("• 🔄 被动刷新：查看行情时自动检查")
        lines.append("• ⏰ 刷新间隔：每1小时更新一次")
        lines.append("• 🌅 每日更新：每天9点市场开盘")
        lines.append("• 🔧 备用机制：每12小时自动更新")

        await stock_refresh_time_cmd.finish(message_add_head("\n".join(lines), event))


@stock_history_cmd.handle()
async def handle_stock_history(event: MessageEvent, args: Message = CommandArg()):
    """查看特定股票的价格历史"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await stock_history_cmd.finish("⛔ 格式：气运历史 <气运代码> [天数]")

    parts = args_text.split()
    symbol = parts[0].upper()
    days = 7  # 默认7天

    if len(parts) > 1:
        try:
            days = int(parts[1])
            if days < 1 or days > 30:
                days = 7
        except ValueError:
            days = 7

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await stock_history_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await stock_history_cmd.finish("⛔ 请先创建角色")

        # 获取股票信息
        stmt = select(Stock).where(Stock.symbol == symbol, Stock.is_active == True)
        stock = (await session.execute(stmt)).scalars().first()
        if not stock:
            await stock_history_cmd.finish(f"⛔ 气运项目 {symbol} 不存在")

        # 获取价格历史
        from datetime import timedelta
        start_date = datetime.now() - timedelta(days=days)
        history_stmt = select(StockPriceHistory).where(
            StockPriceHistory.stock_id == stock.id,
            StockPriceHistory.recorded_at >= start_date
        ).order_by(StockPriceHistory.recorded_at.desc()).limit(days * 24)

        price_history = (await session.execute(history_stmt)).scalars().all()

        if not price_history:
            await stock_history_cmd.finish(f"📊 {stock.name}({symbol}) 暂无历史数据")

        lines = [f"📊 {stock.name}({symbol}) 价格历史", "▃▃▃▃▃▃▃▃▃▃"]
        lines.append(f"📅 查询范围：最近{days}天")
        lines.append(f"💰 基础价格：{stock.base_price} 金币")
        lines.append(f"💎 当前价格：{stock.current_price} 金币")

        # 计算总体统计
        prices = [h.price for h in price_history]
        if prices:
            max_price = max(prices)
            min_price = min(prices)
            avg_price = sum(prices) // len(prices)

            lines.append(f"📈 最高价格：{max_price} 金币")
            lines.append(f"📉 最低价格：{min_price} 金币")
            lines.append(f"📊 平均价格：{avg_price} 金币")
            lines.append("")

        # 显示最近的价格变化（最多10条）
        lines.append("🕐 最近价格变化：")
        recent_history = list(reversed(price_history))[:10]

        for record in recent_history:
            change_symbol = "📈" if record.change_rate > 0 else "📉" if record.change_rate < 0 else "➡️"
            time_str = record.recorded_at.strftime("%m-%d %H:%M")
            lines.append(
                f"  {time_str} {change_symbol} {record.price} 金币 "
                f"({record.change_rate:+.2f}%)"
            )

        lines.append("\n💡 使用「气运分析」查看随机性说明")
        await stock_history_cmd.finish(message_add_head("\n".join(lines), event))


@stock_analysis_cmd.handle()
async def handle_stock_analysis(event: MessageEvent):
    """解释股票价格波动的随机性原理"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await stock_analysis_cmd.finish("⛔ 请先创建角色")

        # 获取所有股票的统计数据
        stmt = select(Stock).where(Stock.is_active == True)
        stocks = (await session.execute(stmt)).scalars().all()

        if not stocks:
            await stock_analysis_cmd.finish("💎 当前没有可投资的气运")

        lines = ["🔬 气运价格波动原理分析", "▃▃▃▃▃▃▃▃▃▃▃▃▃▃"]

        lines.append("📊 **为什么有些股票一直涨/跌？**")
        lines.append("")
        lines.append("🎲 **这是正常的随机现象！**")
        lines.append("就像抛硬币，连续出现正面或反面都是可能的")
        lines.append("")

        lines.append("🧮 **价格计算公式：**")
        lines.append("新价格 = 当前价格 × (1 + 综合变化率)")
        lines.append("")
        lines.append("综合变化率 = 随机因子 + 市场情绪 + 回归因子")
        lines.append("")

        lines.append("🔍 **各因子说明：**")
        lines.append("• 🎯 随机因子：正态分布随机数（-20%~+20%）")
        lines.append("• 🌊 市场情绪：全局影响（牛市+2%，熊市-2%）")
        lines.append("• 🔄 回归因子：防止偏离基础价格太远")
        lines.append("")

        lines.append("📈 **为什么会出现连续涨跌？**")
        lines.append("1. 随机数的聚集效应（正常统计现象）")
        lines.append("2. 市场情绪的短期持续影响")
        lines.append("3. 但回归因子会逐渐拉回基础价格")
        lines.append("")

        # 显示当前各股票相对基础价格的偏离情况
        lines.append("📊 **当前价格偏离情况：**")
        for stock in stocks:
            deviation = ((stock.current_price - stock.base_price) / stock.base_price) * 100
            if abs(deviation) > 10:  # 只显示偏离超过10%的
                direction = "高于" if deviation > 0 else "低于"
                lines.append(f"• {stock.symbol} {direction}基础价格 {abs(deviation):.1f}%")

        lines.append("")
        lines.append("🔒 **系统保证：**")
        lines.append("• ✅ 完全随机算法，无人工干预")
        lines.append("• ✅ 价格有下限保护（基础价格20%）")
        lines.append("• ✅ 单次变化限制（±20%）")
        lines.append("• ✅ 长期会回归基础价格")
        lines.append("")




