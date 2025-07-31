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
from datetime import datetime
from nonebot.permission import SUPERUSER
from ..models.db import safe_session
from ..models.player import Player
from ..models.stock import Stock, StockType
from ..utils import message_add_head
from .stock_service import StockService


# 灵石投资相关命令
stock_list_cmd = on_command("灵石行情", aliases={"投资行情", "灵石市场"}, block=True, priority=5)
stock_buy_cmd = on_command("投资灵石", aliases={"购买灵石"}, block=True, priority=5)
stock_sell_cmd = on_command("出售灵石", aliases={"卖出灵石"}, block=True, priority=5)
stock_holdings_cmd = on_command("我的投资", aliases={"灵石持有", "投资持仓"}, block=True, priority=5)
stock_transactions_cmd = on_command("投资记录", aliases={"灵石记录"}, block=True, priority=5)
stock_init_cmd = on_command("初始化灵石", block=True, priority=5)


@stock_list_cmd.handle()
async def handle_stock_list(event: MessageEvent):
    """查看灵石投资行情"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await stock_list_cmd.finish("⛔ 请先创建角色")
        
        # 获取所有活跃股票
        stmt = select(Stock).where(Stock.is_active == True).order_by(Stock.symbol)
        stocks = (await session.execute(stmt)).scalars().all()
        
        if not stocks:
            await stock_list_cmd.finish("💎 当前没有可投资的灵石")
        
        # 按类型分组显示
        type_groups = {}
        for stock in stocks:
            if stock.stock_type not in type_groups:
                type_groups[stock.stock_type] = []
            type_groups[stock.stock_type].append(stock)
        
        # 构建消息
        lines = ["💎 灵石投资行情", "▃▃▃▃▃▃▃▃▃▃"]
        
        type_names = {
            StockType.TECH: "🔬 法宝灵石",
            StockType.FINANCE: "🏦 金融灵石",
            StockType.ENERGY: "⚡ 灵气灵石",
            StockType.CONSUMER: "🛒 丹药灵石",
            StockType.HEALTHCARE: "🏥 医道灵石",
            StockType.MATERIALS: "🏗️ 材料灵石"
        }
        
        for stock_type, stocks_in_type in type_groups.items():
            lines.append(f"\n{type_names.get(stock_type, stock_type)}")
            for stock in stocks_in_type:
                # 计算涨跌
                change_rate = ((stock.current_price - stock.base_price) / stock.base_price) * 100
                change_symbol = "📈" if change_rate > 0 else "📉" if change_rate < 0 else "➡️"
                
                lines.append(
                    f"{stock.symbol} {stock.name}\n"
                    f"  💰 {stock.current_price} 金币 {change_symbol} {change_rate:+.2f}%"
                )
        
        lines.append("\n💡 使用「投资灵石 代码 数量」进行投资")
        lines.append("💡 使用「投资灵石 代码 数量 银行」从银行账户扣款")
        
        await stock_list_cmd.finish(message_add_head("\n".join(lines), event))


@stock_buy_cmd.handle()
async def handle_stock_buy(event: MessageEvent, args: Message = CommandArg()):
    """投资灵石"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await stock_buy_cmd.finish("⛔ 格式：投资灵石 <灵石代码> <数量> [银行]")

    parts = args_text.split()
    if len(parts) < 2:
        await stock_buy_cmd.finish("⛔ 格式：投资灵石 <灵石代码> <数量> [银行]")
    
    symbol = parts[0].upper()
    try:
        shares = int(parts[1])
        if shares <= 0:
            raise ValueError
    except ValueError:
        await stock_buy_cmd.finish("⛔ 灵石数量必须为正整数")
    
    use_bank = len(parts) > 2 and parts[2] in ["银行", "bank"]
    
    # 执行买入
    success, message = await StockService.buy_stock(
        event.get_user_id(), symbol, shares, use_bank
    )
    
    if success:
        await stock_buy_cmd.finish(message_add_head(f"✅ {message}", event))
    else:
        await stock_buy_cmd.finish(message_add_head(f"⛔ {message}", event))


@stock_sell_cmd.handle()
async def handle_stock_sell(event: MessageEvent, args: Message = CommandArg()):
    """出售灵石"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await stock_sell_cmd.finish("⛔ 格式：出售灵石 <灵石代码> <数量> [银行]")

    parts = args_text.split()
    if len(parts) < 2:
        await stock_sell_cmd.finish("⛔ 格式：出售灵石 <灵石代码> <数量> [银行]")
    
    symbol = parts[0].upper()
    try:
        shares = int(parts[1])
        if shares <= 0:
            raise ValueError
    except ValueError:
        await stock_sell_cmd.finish("⛔ 灵石数量必须为正整数")
    
    to_bank = len(parts) > 2 and parts[2] in ["银行", "bank"]
    
    # 执行卖出
    success, message = await StockService.sell_stock(
        event.get_user_id(), symbol, shares, to_bank
    )
    
    if success:
        await stock_sell_cmd.finish(message_add_head(f"✅ {message}", event))
    else:
        await stock_sell_cmd.finish(message_add_head(f"⛔ {message}", event))


@stock_holdings_cmd.handle()
async def handle_stock_holdings(event: MessageEvent):
    """查看灵石投资持仓"""
    holdings = await StockService.get_player_holdings(event.get_user_id())

    if not holdings:
        await stock_holdings_cmd.finish(message_add_head("� 您当前没有投资", event))

    lines = ["� 我的灵石投资", "▃▃▃▃▃▃▃▃▃▃"]
    
    total_value = 0
    total_cost = 0
    
    for holding in holdings:
        total_value += holding["current_value"]
        total_cost += holding["total_cost"]
        
        profit_symbol = "📈" if holding["profit_loss"] > 0 else "📉" if holding["profit_loss"] < 0 else "➡️"
        
        lines.append(
            f"\n{holding['symbol']} {holding['name']}\n"
            f"  � 持有：{holding['shares']} 份\n"
            f"  💰 成本：{holding['avg_cost']} 金币/份\n"
            f"  ✨ 现价：{holding['current_price']} 金币/份\n"
            f"  💵 价值：{holding['current_value']} 金币\n"
            f"  {profit_symbol} 盈亏：{holding['profit_loss']:+} 金币 ({holding['profit_loss_rate']:+.2f}%)"
        )
    
    total_profit = total_value - total_cost
    total_profit_rate = (total_profit / total_cost * 100) if total_cost > 0 else 0
    profit_symbol = "📈" if total_profit > 0 else "📉" if total_profit < 0 else "➡️"
    
    lines.append(f"\n� 总价值：{total_value} 金币")
    lines.append(f"💰 总成本：{total_cost} 金币")
    lines.append(f"{profit_symbol} 总盈亏：{total_profit:+} 金币 ({total_profit_rate:+.2f}%)")
    
    await stock_holdings_cmd.finish(message_add_head("\n".join(lines), event))


@stock_transactions_cmd.handle()
async def handle_stock_transactions(event: MessageEvent):
    """查看投资记录"""
    transactions = await StockService.get_player_transactions(event.get_user_id(), 10)

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
async def handle_stock_init(event: MessageEvent, permission=SUPERUSER):
    """初始化灵石投资数据（仅管理员）"""
    async with safe_session() as session:
        # 检查是否已有灵石数据
        existing_stocks = (await session.execute(select(Stock))).scalars().all()
        if existing_stocks:
            await stock_init_cmd.finish("⛔ 灵石投资数据已存在，无需重复初始化")

        # 初始灵石投资数据
        initial_stocks = [
            # 法宝灵石
            {"symbol": "TECH01", "name": "法宝工坊", "type": StockType.TECH, "base_price": 100, "volatility": 0.08},
            {"symbol": "TECH02", "name": "阵法研究", "type": StockType.TECH, "base_price": 150, "volatility": 0.10},
            {"symbol": "TECH03", "name": "符箓制作", "type": StockType.TECH, "base_price": 80, "volatility": 0.09},

            # 金融灵石
            {"symbol": "FIN01", "name": "冥界钱庄", "type": StockType.FINANCE, "base_price": 200, "volatility": 0.04},
            {"symbol": "FIN02", "name": "仙界商会", "type": StockType.FINANCE, "base_price": 120, "volatility": 0.05},

            # 灵气灵石
            {"symbol": "ENE01", "name": "灵脉开采", "type": StockType.ENERGY, "base_price": 180, "volatility": 0.06},
            {"symbol": "ENE02", "name": "雷电收集", "type": StockType.ENERGY, "base_price": 90, "volatility": 0.07},

            # 丹药灵石
            {"symbol": "CON01", "name": "丹药坊", "type": StockType.CONSUMER, "base_price": 60, "volatility": 0.03},
            {"symbol": "CON02", "name": "灵草种植", "type": StockType.CONSUMER, "base_price": 110, "volatility": 0.04},

            # 医道灵石
            {"symbol": "MED01", "name": "医仙堂", "type": StockType.HEALTHCARE, "base_price": 140, "volatility": 0.05},

            # 材料灵石
            {"symbol": "MAT01", "name": "矿石开采", "type": StockType.MATERIALS, "base_price": 70, "volatility": 0.07},
            {"symbol": "MAT02", "name": "炼器材料", "type": StockType.MATERIALS, "base_price": 95, "volatility": 0.08},
        ]

        # 创建灵石投资项目
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
        await stock_init_cmd.finish("✅ 灵石投资数据初始化完成！共创建了12个投资项目")
