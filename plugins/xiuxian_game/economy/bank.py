from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from datetime import datetime
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.bank_account import BankAccount
from ..utils import message_add_head

# ==================== 银行系统改革说明 ====================
# 【2025-12-03】银行系统已取消存款利息
# 原因：利息是纯货币创造，导致严重通货膨胀(最高金币34.4亿)
# 新功能：理财产品（零和博弈，管理费作为货币Sink）
# ======================================================

# 命令
bank_balance_cmd = on_command("余额", aliases={"冥行账单"}, block=True, priority=5)
bank_deposit_cmd = on_command("存", aliases={"存款"}, block=True, priority=5)
bank_withdraw_cmd = on_command("取", aliases={"取款"}, block=True, priority=5)
bank_transfer_cmd = on_command("转账", aliases={"银行转账"}, block=True, priority=5)
bank_invest_cmd = on_command("银行投资", aliases={"投资理财"}, block=True, priority=5)

# ==================== 存款排行榜 ====================
deposit_rank_cmd = on_command("存款榜", aliases={"冥行榜"}, block=True, priority=5)

# 旧利息计算函数已废弃
# def _apply_interest(acc: BankAccount):
#     """已于2025-12-03废弃，不再计算利息"""
#     pass


@bank_balance_cmd.handle()
async def handle_balance(event: MessageEvent):
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await bank_balance_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await bank_balance_cmd.finish("⛔ 请先创建角色")
        acc = await session.get(BankAccount, player.id)
        if not acc:
            acc = BankAccount(player_id=player.id, balance=0, last_interest=datetime.now())
            session.add(acc)
            await session.commit()

        # 已取消利息计算
        msg = (
            f"🏦 冥界银行账单\n"
            f"━━━━━━━━━━━━━\n"
            f"💰 当前存款：{acc.balance:,} 金币\n"
            f"━━━━━━━━━━━━━\n"
            f"📢 银行改革公告\n"
            f"▫️ 已取消存款利息\n"
            f"▫️ 新增理财产品\n\n"
            f"💡 使用「理财产品」查看投资选项"
        )
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
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await bank_deposit_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await bank_deposit_cmd.finish("⛔ 请先创建角色")
        if player.gold < amt:
            await bank_deposit_cmd.finish("⛔ 金币不足")
        acc = await session.get(BankAccount, player.id)
        if not acc:
            acc = BankAccount(player_id=player.id, balance=0, last_interest=datetime.now())
            session.add(acc)
            await session.flush()
        # 已取消利息计算
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
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await bank_withdraw_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await bank_withdraw_cmd.finish("⛔ 请先创建角色")
        acc = await session.get(BankAccount, player.id)
        if not acc or acc.balance <= 0:
            await bank_withdraw_cmd.finish("⛔ 你没有任何存款")
        # 已取消利息计算
        if amt > acc.balance:
            await bank_withdraw_cmd.finish("⛔ 取款金额超过存款")
        acc.balance -= amt
        player.gold += amt
        session.add_all([player, acc])
        await session.commit()
        await bank_withdraw_cmd.finish(message_add_head(f"💰 取出 {amt} 金币，剩余存款 {acc.balance}", event))


@bank_transfer_cmd.handle()
async def handle_transfer(event: MessageEvent, args: Message = CommandArg()):
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await bank_transfer_cmd.finish("⛔ 格式：转账 UID 金额")

    parts = args_text.split()
    if len(parts) != 2:
        await bank_transfer_cmd.finish("⛔ 格式：转账 UID 金额")

    try:
        target_uid = int(parts[0])
        amt = int(parts[1])
        if amt <= 0:
            raise ValueError
    except ValueError:
        await bank_transfer_cmd.finish("⛔ UID和金额必须为正整数")

    async with safe_session() as session:
        # 使用跨平台工具获取转账发起人数据
        from ..platform_utils import get_unified_player, is_guild_message
        sender = await get_unified_player(session, event)
        if not sender:
            if is_guild_message(event):
                await bank_transfer_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await bank_transfer_cmd.finish("⛔ 请先创建角色")

        # 获取转账接收人
        from sqlalchemy import select
        receiver = (await session.execute(select(Player).where(Player.uid == target_uid))).scalars().first()
        if not receiver:
            await bank_transfer_cmd.finish("⛔ 未找到目标玩家")

        # 不能给自己转账
        if sender.id == receiver.id:
            await bank_transfer_cmd.finish("⛔ 不能给自己转账")

        # 获取发起人银行账户
        sender_acc = await session.get(BankAccount, sender.id)
        if not sender_acc:
            sender_acc = BankAccount(player_id=sender.id, balance=0, last_interest=datetime.now())
            session.add(sender_acc)
            await session.flush()

        # 已取消利息计算

        # 检查余额
        if sender_acc.balance < amt:
            await bank_transfer_cmd.finish("⛔ 银行存款不足")

        # 计算税收（3%）
        tax = int(amt * 0.03)
        actual_amount = amt - tax

        # 获取接收人银行账户
        receiver_acc = await session.get(BankAccount, receiver.id)
        if not receiver_acc:
            receiver_acc = BankAccount(player_id=receiver.id, balance=0, last_interest=datetime.now())
            session.add(receiver_acc)
            await session.flush()

        # 已取消利息计算

        # 执行转账
        sender_acc.balance -= amt
        receiver_acc.balance += actual_amount

        session.add_all([sender_acc, receiver_acc])
        await session.commit()

        msg = (
            f"💸 转账成功\n"
            f"━━━━━━━━━━━━━\n"
            f"💰 转账金额：{amt} 金币\n"
            f"💸 手续费：{tax} 金币 (3%)\n"
            f"💎 实际到账：{actual_amount} 金币\n"
            f"👤 收款人：{receiver.nickname}[UID:{receiver.uid}]\n"
            f"💳 剩余存款：{sender_acc.balance} 金币"
        )
        await bank_transfer_cmd.finish(message_add_head(msg, event))


@deposit_rank_cmd.handle()
async def handle_deposit_rank(event: MessageEvent, args: Message = CommandArg()):
    """显示存款最多的前30名玩家，支持分页"""
    # 解析页码参数
    page_text = args.extract_plain_text().strip()
    try:
        page = int(page_text) if page_text else 1
    except ValueError:
        page = 1
    page = max(1, min(page, 3))  # 限制在1-3页
    
    page_size = 10
    offset = (page - 1) * page_size
    
    async with safe_session() as session:
        # 先取前30余额账号，再结息，避免遍历全库
        from sqlalchemy import func as _func
        from sqlalchemy.orm import joinedload

        # 使用joinedload预加载Player，避免N+1查询（11次→1次）
        sub_stmt = (
            select(BankAccount)
            .options(joinedload(BankAccount.player))
            .order_by(BankAccount.balance.desc())
            .limit(30)
        )
        accounts = (await session.execute(sub_stmt)).scalars().all()
        if not accounts:
            await deposit_rank_cmd.finish("暂无存款数据")

        # 已取消利息计算，直接排序

        # 按余额排序
        accounts.sort(key=lambda x: x.balance, reverse=True)
        
        # 分页处理
        page_accounts = accounts[offset:offset + page_size]
        
        # 自动提交利息写回
        session.add_all(accounts)
        await session.commit()
        
        lines = [f"🏦 存款排行榜 (第{page}/3页)", "━━━━━━━━━━━━━"]
        for idx, acc in enumerate(page_accounts, start=offset + 1):
            # 直接使用预加载的player，避免N+1查询
            p = acc.player
            if not p:
                continue
            # 使用emoji装饰前三名
            rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            lines.append(f"{rank_emoji} {p.nickname}[UID:{p.uid}] - {acc.balance}💰")
        
        if page < 3:
            lines.append("━━━━━━━━━━━━━")
            lines.append("💡 使用【存款榜 页码】查看其他页")
        
        await deposit_rank_cmd.finish(message_add_head("\n".join(lines), event))


@bank_invest_cmd.handle()
async def handle_bank_invest(event: MessageEvent):
    """银行投资理财"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await bank_invest_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await bank_invest_cmd.finish("⛔ 请先创建角色")

        acc = await session.get(BankAccount, player.id)
        if not acc:
            acc = BankAccount(player_id=player.id, balance=0, last_interest=datetime.now())
            session.add(acc)
            await session.commit()

        # 已取消利息计算

        msg = (
            "🏦 冥界银行投资理财中心\n"
            "▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃▃\n"
            f"💰 当前存款：{acc.balance:,} 金币\n\n"
            "💎 投资产品：\n"
            "1️⃣ 气运投资 - 高风险高收益\n"
            "   • 使用「气运行情」查看可投资项目\n"
            "   • 使用「投资气运 代码 数量 银行」从银行账户投资\n"
            "   • 使用「出售气运 代码 数量 银行」出售后存入银行\n\n"
            "2️⃣ 活期理财 - 稳健增值(即将上线)\n"
            "   • 随存随取，每日结算\n"
            "   • 日收益±5%，管理费0.1%/天\n"
            "   • 使用「理财产品」查看详情\n\n"
            "📢 银行改革公告:\n"
            "   已取消存款利息，控制通货膨胀\n\n"
            "💡 风险提示：投资有风险，需谨慎！"
        )

        await bank_invest_cmd.finish(message_add_head(msg, event))
