from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from datetime import datetime
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.bank_account import BankAccount
from ..utils import message_add_head

# ---- 阶梯利率设置 ----
# (上限, 利率/小时)
_TIERS = [
    (100_000, 0.001),   # 10w 以内 0.1%
    (500_000, 0.0005),  # 10w-50w 0.05%
    (1_000_000, 0.0001),# 50w-100w 0.01%
    (float("inf"), 0.0) # 100w 以上无利息
]

def _tier_rate(balance: int) -> float:
    for limit, rate in _TIERS:
        if balance <= limit:
            return rate
    return 0.0

# 命令
bank_balance_cmd = on_command("余额", aliases={"冥行账单"}, block=True, priority=5)
bank_deposit_cmd = on_command("存", aliases={"存款"}, block=True, priority=5)
bank_withdraw_cmd = on_command("取", aliases={"取款"}, block=True, priority=5)
bank_invest_cmd = on_command("银行投资", aliases={"投资理财"}, block=True, priority=5)

# ==================== 存款排行榜 ====================
deposit_rank_cmd = on_command("存款榜", aliases={"冥行榜"}, block=True, priority=5)

def _apply_interest(acc: BankAccount):
    now = datetime.now()
    delta_hours = (now - acc.last_interest).total_seconds() / 3600
    if delta_hours <= 0 or acc.balance <= 0:
        acc.last_interest = now
        return 0
    gain = int(acc.balance * _tier_rate(acc.balance) * delta_hours)
    # 单次结息上限 1w
    cap = 10_000
    if gain > cap:
        gain = cap
    if gain > 0:
        acc.balance += gain
    acc.last_interest = now
    return gain


@bank_balance_cmd.handle()
async def handle_balance(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await bank_balance_cmd.finish("⛔ 请先创建角色")
        acc = await session.get(BankAccount, player.id)
        if not acc:
            acc = BankAccount(player_id=player.id, balance=0, last_interest=datetime.now())
            session.add(acc)
            await session.commit()
        gain = _apply_interest(acc)
        session.add(acc)
        await session.commit()
        msg = f"🏦 冥行票据\n▫️ 本次利息：{gain} 金币\n▫️ 当前存款：{acc.balance} 金币\n▫️ 阶梯利率，当存款超过100w时不再产生利息\n\n💡 使用「银行投资」查看投资理财选项"
        await bank_balance_cmd.finish(message_add_head(msg, event))


@bank_deposit_cmd.handle()
async def handle_deposit(event: MessageEvent, args: Message = CommandArg()):
    amt_str = args.extract_plain_text().strip()
    if not amt_str:
        await bank_deposit_cmd.finish("⛔ 格式：存 金额")
    try:
        amt = int(amt_str)
        if amt <= 0:
            raise ValueError
    except ValueError:
        await bank_deposit_cmd.finish("⛔ 金额必须为正整数")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await bank_deposit_cmd.finish("⛔ 请先创建角色")
        if player.gold < amt:
            await bank_deposit_cmd.finish("⛔ 金币不足")
        acc = await session.get(BankAccount, player.id)
        if not acc:
            acc = BankAccount(player_id=player.id, balance=0, last_interest=datetime.now())
            session.add(acc)
            await session.flush()
        _apply_interest(acc)
        player.gold -= amt
        acc.balance += amt
        session.add_all([player, acc])
        await session.commit()
        await bank_deposit_cmd.finish(message_add_head(f"✅ 存入 {amt} 金币，当前存款 {acc.balance}", event))


@bank_withdraw_cmd.handle()
async def handle_withdraw(event: MessageEvent, args: Message = CommandArg()):
    amt_str = args.extract_plain_text().strip()
    if not amt_str:
        await bank_withdraw_cmd.finish("⛔ 格式：取 金额")
    try:
        amt = int(amt_str)
        if amt <= 0:
            raise ValueError
    except ValueError:
        await bank_withdraw_cmd.finish("⛔ 金额必须为正整数")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await bank_withdraw_cmd.finish("⛔ 请先创建角色")
        acc = await session.get(BankAccount, player.id)
        if not acc or acc.balance <= 0:
            await bank_withdraw_cmd.finish("⛔ 你没有任何存款")
        _apply_interest(acc)
        if amt > acc.balance:
            await bank_withdraw_cmd.finish("⛔ 取款金额超过存款")
        acc.balance -= amt
        player.gold += amt
        session.add_all([player, acc])
        await session.commit()
        await bank_withdraw_cmd.finish(message_add_head(f"💰 取出 {amt} 金币，剩余存款 {acc.balance}", event))


@deposit_rank_cmd.handle()
async def handle_deposit_rank(event: MessageEvent):
    async with safe_session() as session:
        # 先取前20余额账号，再结息，避免遍历全库
        from sqlalchemy import func as _func
        sub_stmt = select(BankAccount).order_by(BankAccount.balance.desc()).limit(20)
        accounts = (await session.execute(sub_stmt)).scalars().all()
        if not accounts:
            await deposit_rank_cmd.finish("暂无存款数据")
        rows = []
        for acc in accounts:
            _apply_interest(acc)
            rows.append(acc)
        # 按更新后余额排序取10
        rows.sort(key=lambda x: x.balance, reverse=True)
        top10 = rows[:10]
        # 自动提交利息写回
        session.add_all(top10)
        await session.commit()
        lines = ["🏦 存款排行榜", "▃▃▃▃▃▃▃▃▃▃"]
        for idx, acc in enumerate(top10, 1):
            p = await session.get(Player, acc.player_id)
            if not p:
                continue
            lines.append(f"{idx}. {p.nickname}[UID:{p.uid}] - {acc.balance}💰")
        await deposit_rank_cmd.finish(message_add_head("\n".join(lines), event))


@bank_invest_cmd.handle()
async def handle_bank_invest(event: MessageEvent):
    """银行投资理财"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await bank_invest_cmd.finish("⛔ 请先创建角色")

        acc = await session.get(BankAccount, player.id)
        if not acc:
            acc = BankAccount(player_id=player.id, balance=0, last_interest=datetime.now())
            session.add(acc)
            await session.commit()

        # 应用利息
        gain = _apply_interest(acc)
        session.add(acc)
        await session.commit()

        msg = (
            "🏦 冥界银行投资理财中心\n"
            "▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃\n"
            f"💰 当前存款：{acc.balance:,} 金币\n"
            f"💎 本次利息：{gain} 金币\n\n"
            "💎 投资产品：\n"
            "1️⃣ 气运投资 - 高风险高收益\n"
            "   • 使用「气运行情」查看可投资项目\n"
            "   • 使用「投资气运 代码 数量 银行」从银行账户投资\n"
            "   • 使用「出售气运 代码 数量 银行」出售后存入银行\n\n"
            "2️⃣ 定期存款 - 稳定收益\n"
            "   • 当前阶梯利率：\n"
            "   • 10万以内：0.1%/小时\n"
            "   • 10-50万：0.05%/小时\n"
            "   • 50-100万：0.01%/小时\n"
            "   • 100万以上：无利息\n\n"
            "💡 风险提示：气运投资有风险，投资需谨慎！"
        )

        await bank_invest_cmd.finish(message_add_head(msg, event))