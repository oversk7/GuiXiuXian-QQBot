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

from ..utils_markdown import cmd, build_markdown
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
    daily_return_pct = fund.daily_return * 100
    return_emoji = "📈" if fund.daily_return > 0 else "📉" if fund.daily_return < 0 else "➡️"

    fund_config = BankFundService.LIVELY_FUND_CONFIG

    content = (
        f"# 💎 理财产品列表\n"
        f"***\n"
        f"📊 {fund.fund_name}\n"
        f"💰 基金规模：**{fund.total_scale:,}** 金币\n"
        f"👥 参与人数：**{fund.participant_count}** 人\n"
        f"{return_emoji} 昨日收益率：**{daily_return_pct:+.2f}%**\n"
        f"***\n"
        f"📝 投资说明\n"
        f"▫️ 最低投资：**{fund_config['min_investment']:,}** 金币\n"
        f"▫️ 最高投资：**{fund_config['max_investment']:,}** 金币\n"
        f"▫️ 管理费：**{fund_config['management_fee_rate']*100:.1f}%**/天\n"
        f"▫️ 收益波动：**±{fund_config['max_daily_change']*100:.0f}%**/天\n"
        f"***\n"
        f"{cmd('购买理财 金额', '购买理财 ')} | {cmd('购买理财 金额 银行', '购买理财 ')}\n"
        f"{cmd('我的理财')} | {cmd('定期理财')}"
    )

    await fund_list_cmd.finish(build_markdown(content))


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

    content = (
        f"{message}\n"
        f"***\n"
        f"{cmd('我的理财')} | {cmd('理财产品')}"
    )
    await fund_buy_cmd.finish(build_markdown(content))


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

    content = (
        f"{message}\n"
        f"***\n"
        f"{cmd('我的理财')} | {cmd('理财产品')} | {cmd('购买理财 金额', '购买理财 ')}"
    )
    await fund_sell_cmd.finish(build_markdown(content))


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
        content = (
            f"💼 你还没有任何理财产品\n"
            f"***\n"
            f"{cmd('理财产品')} | {cmd('购买理财 金额', '购买理财 ')}"
        )
        await fund_holdings_cmd.finish(build_markdown(content))

    # 构建消息
    lines = ["# 💼 我的理财持仓", "***"]

    total_principal = 0
    total_value = 0
    total_profit = 0

    for idx, holding in enumerate(holdings, 1):
        profit_str = f"+{holding.accumulated_profit:,}" if holding.accumulated_profit >= 0 else f"{holding.accumulated_profit:,}"
        profit_emoji = "📈" if holding.accumulated_profit > 0 else "📉" if holding.accumulated_profit < 0 else "➡️"

        # 计算持有天数
        days_held = (datetime.now() - holding.buy_date).days

        lines.append(f"【{idx}】 持仓编号：**{holding.id}**")
        lines.append(f"💰 本金：**{holding.principal:,}** 金币")
        lines.append(f"📊 当前市值：**{holding.current_value:,}** 金币")
        lines.append(f"{profit_emoji} 累计盈亏：**{profit_str}** 金币")
        lines.append(f"📅 持有天数：**{days_held}** 天")
        lines.append(f"🕐 上次结算：{holding.last_settlement.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"{cmd('赎回理财 ' + str(holding.id), '赎回理财 ' + str(holding.id))} | {cmd('赎回到银行', '赎回理财 ' + str(holding.id) + ' 银行')}")
        lines.append("")

        total_principal += holding.principal
        total_value += holding.current_value
        total_profit += holding.accumulated_profit

    # 总计
    lines.append("***")
    total_profit_str = f"+{total_profit:,}" if total_profit >= 0 else f"{total_profit:,}"
    total_return_pct = (total_profit / total_principal * 100) if total_principal > 0 else 0

    lines.append("📝 汇总")
    lines.append(f"💰 总本金：**{total_principal:,}** 金币")
    lines.append(f"📊 总市值：**{total_value:,}** 金币")
    lines.append(f"📈 总盈亏：**{total_profit_str}** 金币 (**{total_return_pct:+.2f}%**)")
    lines.append("***")
    lines.append(f"{cmd('理财产品')} | {cmd('购买理财 金额', '购买理财 ')}")

    await fund_holdings_cmd.finish(build_markdown("\n".join(lines)))


# ==================== 定期理财（七日定存）命令 ====================

fixed_list_cmd = on_command("定期理财", block=True, priority=5)
fixed_buy_cmd = on_command("购买定期", block=True, priority=5)
fixed_holdings_cmd = on_command("我的定期", block=True, priority=5)
fixed_redeem_cmd = on_command("赎回定期", block=True, priority=5)


@fixed_list_cmd.handle()
async def handle_fixed_list(event: MessageEvent):
    """查看七日定存产品介绍"""
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            error_msg = "⛔ 请先创建角色"
        else:
            error_msg = None
            fund_service = BankFundService(
                fund_repo=uow.bank_funds,
                holding_repo=uow.fund_holdings,
                bank_account_repo=uow.bank_accounts,
                player_repo=uow.players
            )
            fund = await fund_service.get_or_create_fixed_weekly_fund()
            await uow.commit()

    if error_msg:
        await fixed_list_cmd.finish(error_msg)

    cfg = BankFundService.FIXED_WEEKLY_CONFIG
    gross = cfg["interest_rate"] * 100
    fee = cfg["interest_rate"] * cfg["fee_rate"] * 100
    net = gross - fee

    content = (
        f"# 🏦 冥界七日定存\n"
        f"***\n"
        f"📊 基金规模：**{fund.total_scale:,}** 金币\n"
        f"👥 参与人数：**{fund.participant_count}** 人\n"
        f"***\n"
        f"📝 产品说明\n"
        f"▫️ 锁定期：**7**天（到期方可赎回）\n"
        f"▫️ 周利率：**{gross:.0f}%**（毛）/ **{net:.0f}%**（净）\n"
        f"▫️ 管理费：利息的 **{cfg['fee_rate']*100:.0f}%**\n"
        f"▫️ 最低投资：**{cfg['min_investment']:,}** 金币\n"
        f"▫️ 最高投资：**{cfg['max_investment']:,}** 金币\n\n"
        f"⚠️ 锁定期间不可提前赎回，请确保资金不急用\n"
        f"***\n"
        f"{cmd('购买定期 金额', '购买定期 ')} | {cmd('购买定期 金额 银行', '购买定期 ')}\n"
        f"{cmd('我的定期')} | {cmd('理财产品')}"
    )
    await fixed_list_cmd.finish(build_markdown(content))


@fixed_buy_cmd.handle()
async def handle_fixed_buy(event: MessageEvent, args: Message = CommandArg()):
    """购买七日定存"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await fixed_buy_cmd.finish("⛔ 格式：购买定期 <金额> [银行]")

    parts = args_text.split()
    if not parts[0].isdigit():
        await fixed_buy_cmd.finish("⛔ 金额必须为正整数")

    amount = int(parts[0])
    if amount <= 0:
        await fixed_buy_cmd.finish("⛔ 金额必须为正整数")

    use_bank = len(parts) > 1 and parts[1] in ["银行", "bank"]

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            error_msg = "⛔ 请先创建角色"
        else:
            error_msg = None
            fund_service = BankFundService(
                fund_repo=uow.bank_funds,
                holding_repo=uow.fund_holdings,
                bank_account_repo=uow.bank_accounts,
                player_repo=uow.players
            )
            success, message = await fund_service.buy_fixed_weekly(player, amount, use_bank)
            if success:
                await uow.commit()
            else:
                error_msg = message

    if error_msg:
        await fixed_buy_cmd.finish(error_msg)

    content = (
        f"{message}\n"
        f"***\n"
        f"{cmd('我的定期')} | {cmd('定期理财')}"
    )
    await fixed_buy_cmd.finish(build_markdown(content))


@fixed_holdings_cmd.handle()
async def handle_fixed_holdings(event: MessageEvent):
    """查看我的七日定存持仓"""
    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            error_msg = "⛔ 请先创建角色"
        else:
            error_msg = None
            fund_service = BankFundService(
                fund_repo=uow.bank_funds,
                holding_repo=uow.fund_holdings,
                bank_account_repo=uow.bank_accounts,
                player_repo=uow.players
            )
            holdings = await fund_service.get_player_fixed_holdings(player.id)

    if error_msg:
        await fixed_holdings_cmd.finish(error_msg)

    if not holdings:
        content = (
            f"📋 你目前没有持有七日定存\n"
            f"***\n"
            f"{cmd('定期理财')} | {cmd('购买定期 金额', '购买定期 ')}"
        )
        await fixed_holdings_cmd.finish(build_markdown(content))

    cfg = BankFundService.FIXED_WEEKLY_CONFIG
    now = datetime.now()

    lines = ["# 📋 我的七日定存", "***"]
    total_principal = 0

    for idx, h in enumerate(holdings, 1):
        gross_interest = int(h.principal * cfg["interest_rate"])
        fee = int(gross_interest * cfg["fee_rate"])
        net_interest = gross_interest - fee

        if now >= h.maturity_date:
            status = "✅ 已到期（可赎回）"
            countdown = ""
        else:
            remaining = h.maturity_date - now
            hours = int(remaining.total_seconds() // 3600)
            mins = int((remaining.total_seconds() % 3600) // 60)
            status = "⏳ 锁定中"
            countdown = f"（剩余 {hours}小时{mins}分）"

        lines.append(f"【{idx}】编号 **{h.id}**")
        lines.append(f"💰 本金：**{h.principal:,}** 金币")
        lines.append(f"📈 预期净收益：**+{net_interest:,}** 金币")
        lines.append(f"📅 到期时间：{h.maturity_date.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"🔒 状态：{status}{countdown}")
        if now >= h.maturity_date:
            lines.append(f"{cmd('赎回定期 ' + str(h.id), '赎回定期 ' + str(h.id))} | {cmd('赎回到银行', '赎回定期 ' + str(h.id) + ' 银行')}")
        lines.append("")
        total_principal += h.principal

    lines.append("***")
    lines.append(f"💰 定存总额：**{total_principal:,}** 金币")
    lines.append("***")
    lines.append(f"{cmd('定期理财')} | {cmd('购买定期 金额', '购买定期 ')}")

    await fixed_holdings_cmd.finish(build_markdown("\n".join(lines)))


@fixed_redeem_cmd.handle()
async def handle_fixed_redeem(event: MessageEvent, args: Message = CommandArg()):
    """赎回七日定存（仅限到期后）"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await fixed_redeem_cmd.finish("⛔ 格式：赎回定期 <编号> [银行]")

    parts = args_text.split()
    if not parts[0].isdigit():
        await fixed_redeem_cmd.finish("⛔ 编号必须为正整数")

    holding_id = int(parts[0])
    if holding_id <= 0:
        await fixed_redeem_cmd.finish("⛔ 编号必须为正整数")

    to_bank = len(parts) > 1 and parts[1] in ["银行", "bank"]

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            error_msg = "⛔ 请先创建角色"
        else:
            error_msg = None
            fund_service = BankFundService(
                fund_repo=uow.bank_funds,
                holding_repo=uow.fund_holdings,
                bank_account_repo=uow.bank_accounts,
                player_repo=uow.players
            )
            success, message = await fund_service.redeem_fixed_weekly(player, holding_id, to_bank)
            if success:
                await uow.commit()
            else:
                error_msg = message

    if error_msg:
        await fixed_redeem_cmd.finish(error_msg)

    content = (
        f"{message}\n"
        f"***\n"
        f"{cmd('我的定期')} | {cmd('定期理财')} | {cmd('购买定期 金额', '购买定期 ')}"
    )
    await fixed_redeem_cmd.finish(build_markdown(content))
