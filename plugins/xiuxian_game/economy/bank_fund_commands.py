"""理财产品命令接口

提供用户交互命令：
1. 查看理财产品列表
2. 购买理财产品
3. 赎回理财产品
4. 查看持仓
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from datetime import datetime

from ..utils import message_add_head
from ..platform_utils import get_unified_player
from .bank_fund_service import BankFundService
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.db import AsyncSessionLocal


# 理财产品相关命令
fund_list_cmd = on_command("理财产品", block=True, priority=5)
fund_buy_cmd = on_command("购买理财", block=True, priority=5)
fund_sell_cmd = on_command("赎回理财", block=True, priority=5)
fund_holdings_cmd = on_command("我的理财", block=True, priority=5)


def session_factory():
    """会话工厂函数"""
    return AsyncSessionLocal()


@fund_list_cmd.handle()
async def handle_fund_list(event: MessageEvent):
    """查看理财产品列表"""
    async with UnitOfWork(session_factory) as uow:
        # 创建服务实例
        fund_service = BankFundService(
            fund_repo=uow.bank_funds,
            holding_repo=uow.fund_holdings,
            bank_account_repo=uow.bank_accounts,
            player_repo=uow.players
        )

        player = await get_unified_player(uow.session, event)
        if not player:
            error_msg = "⛔ 请先创建角色"
        else:
            error_msg = None
            # 获取活期理财基金
            fund = await fund_service.get_or_create_lively_fund()
            await uow.commit()

    # 在 UnitOfWork 外部处理错误
    if error_msg:
        await fund_list_cmd.finish(error_msg)

    # 构建消息
    lines = ["💎 理财产品列表", "▃▃▃▃▃▃▃▃▃▃"]
    lines.append("")

    # 显示活期理财
    daily_return_pct = fund.daily_return * 100
    return_emoji = "📈" if fund.daily_return > 0 else "📉" if fund.daily_return < 0 else "➡️"

    lines.append(f"📊 {fund.fund_name}")
    lines.append(f"  💰 基金规模：{fund.total_scale:,} 金币")
    lines.append(f"  👥 参与人数：{fund.participant_count} 人")
    lines.append(f"  {return_emoji} 昨日收益率：{daily_return_pct:+.2f}%")
    lines.append("")

    # 配置信息
    config = BankFundService.LIVELY_FUND_CONFIG
    lines.append("📝 投资说明")
    lines.append(f"  ▫️ 最低投资：{config['min_investment']:,} 金币")
    lines.append(f"  ▫️ 最高投资：{config['max_investment']:,} 金币")
    lines.append(f"  ▫️ 管理费：{config['management_fee_rate']*100:.1f}%/天")
    lines.append(f"  ▫️ 收益波动：±{config['max_daily_change']*100:.0f}%/天")
    lines.append("")

    lines.append("💡 使用「购买理财 金额」进行投资")
    lines.append("💡 使用「购买理财 金额 银行」从银行账户扣款")
    lines.append("💡 使用「我的理财」查看持仓")

    await fund_list_cmd.finish(message_add_head("\n".join(lines), event))


@fund_buy_cmd.handle()
async def handle_fund_buy(event: MessageEvent, args: Message = CommandArg()):
    """购买理财产品"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await fund_buy_cmd.finish("⛔ 格式：购买理财 <金额> [银行]")

    parts = args_text.split()
    if len(parts) < 1:
        await fund_buy_cmd.finish("⛔ 格式：购买理财 <金额> [银行]")

    try:
        amount = int(parts[0])
        if amount <= 0:
            raise ValueError
    except ValueError:
        await fund_buy_cmd.finish("⛔ 金额必须为正整数")

    use_bank = len(parts) > 1 and parts[1] in ["银行", "bank"]

    # 执行购买
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            error_msg = "⛔ 请先创建角色"
        else:
            error_msg = None
            # 创建服务实例
            fund_service = BankFundService(
                fund_repo=uow.bank_funds,
                holding_repo=uow.fund_holdings,
                bank_account_repo=uow.bank_accounts,
                player_repo=uow.players
            )

            # 购买理财
            success, message = await fund_service.buy_fund(player, amount, use_bank)

            if success:
                await uow.commit()
            else:
                error_msg = message

    # 在 UnitOfWork 外部处理结果
    if error_msg:
        await fund_buy_cmd.finish(error_msg)

    await fund_buy_cmd.finish(message_add_head(message, event))


@fund_sell_cmd.handle()
async def handle_fund_sell(event: MessageEvent, args: Message = CommandArg()):
    """赎回理财产品"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await fund_sell_cmd.finish("⛔ 格式：赎回理财 <编号> [银行]")

    parts = args_text.split()
    if len(parts) < 1:
        await fund_sell_cmd.finish("⛔ 格式：赎回理财 <编号> [银行]")

    try:
        holding_id = int(parts[0])
        if holding_id <= 0:
            raise ValueError
    except ValueError:
        await fund_sell_cmd.finish("⛔ 编号必须为正整数")

    to_bank = len(parts) > 1 and parts[1] in ["银行", "bank"]

    # 执行赎回
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            error_msg = "⛔ 请先创建角色"
        else:
            error_msg = None
            # 创建服务实例
            fund_service = BankFundService(
                fund_repo=uow.bank_funds,
                holding_repo=uow.fund_holdings,
                bank_account_repo=uow.bank_accounts,
                player_repo=uow.players
            )

            # 赎回理财
            success, message = await fund_service.sell_fund(player, holding_id, to_bank)

            if success:
                await uow.commit()
            else:
                error_msg = message

    # 在 UnitOfWork 外部处理结果
    if error_msg:
        await fund_sell_cmd.finish(error_msg)

    await fund_sell_cmd.finish(message_add_head(message, event))


@fund_holdings_cmd.handle()
async def handle_fund_holdings(event: MessageEvent):
    """查看我的理财持仓"""
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            error_msg = "⛔ 请先创建角色"
        else:
            error_msg = None
            # 创建服务实例
            fund_service = BankFundService(
                fund_repo=uow.bank_funds,
                holding_repo=uow.fund_holdings,
                bank_account_repo=uow.bank_accounts,
                player_repo=uow.players
            )

            # 获取持仓
            holdings = await fund_service.get_player_holdings(player.id)

    # 在 UnitOfWork 外部处理错误
    if error_msg:
        await fund_holdings_cmd.finish(error_msg)

    if not holdings:
        await fund_holdings_cmd.finish(message_add_head("💼 你还没有任何理财产品", event))

    # 构建消息
    lines = ["💼 我的理财持仓", "▃▃▃▃▃▃▃▃▃▃"]
    lines.append("")

    total_principal = 0
    total_value = 0
    total_profit = 0

    for idx, holding in enumerate(holdings, 1):
        profit_str = f"+{holding.accumulated_profit:,}" if holding.accumulated_profit >= 0 else f"{holding.accumulated_profit:,}"
        profit_emoji = "📈" if holding.accumulated_profit > 0 else "📉" if holding.accumulated_profit < 0 else "➡️"

        # 计算持有天数
        days_held = (datetime.now() - holding.buy_date).days

        lines.append(f"【{idx}】 持仓编号：{holding.id}")
        lines.append(f"  💰 本金：{holding.principal:,} 金币")
        lines.append(f"  📊 当前市值：{holding.current_value:,} 金币")
        lines.append(f"  {profit_emoji} 累计盈亏：{profit_str} 金币")
        lines.append(f"  📅 持有天数：{days_held} 天")
        lines.append(f"  🕐 上次结算：{holding.last_settlement.strftime('%Y-%m-%d %H:%M')}")
        lines.append("")

        total_principal += holding.principal
        total_value += holding.current_value
        total_profit += holding.accumulated_profit

    # 总计
    lines.append("━━━━━━━━━━━━━")
    total_profit_str = f"+{total_profit:,}" if total_profit >= 0 else f"{total_profit:,}"
    total_return_pct = (total_profit / total_principal * 100) if total_principal > 0 else 0

    lines.append(f"📝 汇总")
    lines.append(f"  💰 总本金：{total_principal:,} 金币")
    lines.append(f"  📊 总市值：{total_value:,} 金币")
    lines.append(f"  📈 总盈亏：{total_profit_str} 金币 ({total_return_pct:+.2f}%)")
    lines.append("")

    lines.append("💡 使用「赎回理财 编号」赎回到现金")
    lines.append("💡 使用「赎回理财 编号 银行」赎回到银行")

    await fund_holdings_cmd.finish(message_add_head("\n".join(lines), event))
