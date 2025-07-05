from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from datetime import datetime
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.bank_account import BankAccount
from ..utils import message_add_head

INTEREST_RATE_PER_HOUR = 0.0005  # 0.05% 每小时

# 命令
bank_balance_cmd = on_command("余额", aliases={"冥行账单"}, block=True, priority=5)
bank_deposit_cmd = on_command("存", aliases={"存款"}, block=True, priority=5)
bank_withdraw_cmd = on_command("取", aliases={"取款"}, block=True, priority=5)


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