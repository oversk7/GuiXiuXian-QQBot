from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from datetime import datetime
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.bank_account import BankAccount
from ..utils import message_add_head

INTEREST_RATE_PER_HOUR = 0.001  # 0.1% 每小时

# 命令
bank_balance_cmd = on_command("余额", aliases={"冥行账单"}, block=True, priority=5)
bank_deposit_cmd = on_command("存", aliases={"存款"}, block=True, priority=5)
bank_withdraw_cmd = on_command("取", aliases={"取款"}, block=True, priority=5)

# ==================== 存款排行榜 ====================
deposit_rank_cmd = on_command("存款榜", aliases={"冥行榜"}, block=True, priority=5)

def _apply_interest(acc: BankAccount):
    now = datetime.now()
    delta_hours = (now - acc.last_interest).total_seconds() / 3600
    if delta_hours <= 0 or acc.balance <= 0:
        acc.last_interest = now
        return 0
    gain = int(acc.balance * INTEREST_RATE_PER_HOUR * delta_hours)
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
        msg = f"🏦 冥行票据\n▫️ 本次利息：{gain} 金币\n▫️ 当前存款：{acc.balance} 金币"
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
        from sqlalchemy import func as _func
        # 扩大检索范围，避免因部分玩家数据缺失导致展示不足
        sub_stmt = select(BankAccount).order_by(BankAccount.balance.desc()).limit(100)
        accounts = (await session.execute(sub_stmt)).scalars().all()
        if not accounts:
            await deposit_rank_cmd.finish("暂无存款数据")

        rows: list[tuple[BankAccount, Player]] = []
        for acc in accounts:
            _apply_interest(acc)
            player_obj = await session.get(Player, acc.player_id)
            if player_obj:
                rows.append((acc, player_obj))
        # 排序并取前10有效玩家
        rows.sort(key=lambda t: t[0].balance, reverse=True)
        top_rows = rows[:10]
        # 写回利息
        session.add_all([acc for acc, _ in top_rows])
        await session.commit()
        lines = ["🏦 存款排行榜", "▃"*10]
        for idx, (acc, p) in enumerate(top_rows, 1):
            lines.append(f"{idx}. {p.nickname}[UID:{p.uid}] - {acc.balance}💰")
        await deposit_rank_cmd.finish(message_add_head("\n".join(lines), event)) 