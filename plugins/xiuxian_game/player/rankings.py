from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select, func
import random

from ..models.db import safe_session
from ..models.player import Player
from ..models.bank_account import BankAccount
from ..models.stock import StockHolding
from ..utils import message_add_head
from .realm_utils import realm_by_level_and_reincarnation, number_to_chinese


def _format_wealth(amount: int) -> str:
    """格式化财富显示，使用w（万）、e（亿）等单位

    Args:
        amount: 金额数值

    Returns:
        格式化后的字符串
    """
    if amount >= 100_000_000:  # 1亿以上
        value = amount / 100_000_000
        if value >= 10:
            return f"{value:.1f}e💰"
        else:
            return f"{value:.2f}e💰"
    elif amount >= 10_000:  # 1万以上
        value = amount / 10_000
        if value >= 100:
            return f"{value:.1f}w💰"
        else:
            return f"{value:.2f}w💰"
    else:
        return f"{amount}💰"

# ==================== 修为榜 ====================
level_rank_cmd = on_command("修为榜", aliases={"等级榜"}, block=True, priority=5)

@level_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """按等级 (level) 及经验排序的前 30 名玩家排行榜，支持分页"""
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
        stmt = select(Player).order_by(Player.reincarnation_level.desc(), Player.level.desc(), Player.exp.desc()).offset(offset).limit(page_size)
        players = (await session.execute(stmt)).scalars().all()

    if not players:
        await level_rank_cmd.finish("暂无排行榜数据")

    lines = [f"📈 修为排行榜 (第{page}/3页)", "━━━━━━━━━━━━━"]
    for idx, p in enumerate(players, start=offset + 1):
        # 使用新的境界显示函数，包含转生信息
        realm_name = realm_by_level_and_reincarnation(p.level, p.reincarnation_level)
        # 使用emoji装饰前三名
        rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        lines.append(f"{rank_emoji} {p.nickname}[UID:{p.uid}] - Lv.{p.level}『{realm_name}』 ({p.exp} EXP)")
    
    if page < 3:
        lines.append("━━━━━━━━━━━━━")
        lines.append("💡 使用【修为榜 页码】查看其他页")

    await level_rank_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 幸运榜 ====================
luck_rank_cmd = on_command("幸运榜", aliases={"运气榜", "幸运排行榜"}, block=True, priority=5)

@luck_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """显示幸运值最高的前10名玩家"""
    async with safe_session() as session:
        stmt = select(Player).order_by(Player.luck.desc()).limit(10)
        players = (await session.execute(stmt)).scalars().all()

    if not players:
        await luck_rank_cmd.finish("暂无排行榜数据")

    wishes = random.choice(["你信任那些微小的可能性，于是，世界便以暴击的星火与翻倍的惊喜回应这份信任。",
                            "这份加点，不是侥幸，是宣言：你相信，那1%的闪光，足以点亮100%的征程。",
                            "凡俗眼中的偶然，是你掌中的必然。",
    ])
    lines = ["🍀 幸运排行榜", wishes, "━━━━━━━━━━━━━"]
    for idx, p in enumerate(players, 1):
        # 使用emoji装饰前三名
        rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        lines.append(f"{rank_emoji} {p.nickname}[UID:{p.uid}] - 🍀{p.luck}")

    await luck_rank_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 财富榜 ====================
wealth_rank_cmd = on_command("财富榜", aliases={"财富排行榜"}, block=True, priority=5)

@wealth_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """显示总财富最多的前30名玩家，支持分页
    总财富 = 面板金币 + 银行余额 + 投资价值
    """
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
        # 组合候选玩家：金币前50 + 存款前50，避免只按金币过滤导致银行富豪缺失
        gold_top_ids = (await session.execute(select(Player.id).order_by(Player.gold.desc()).limit(50))).scalars().all()
        bank_top_ids = (await session.execute(select(BankAccount.player_id).order_by(BankAccount.balance.desc()).limit(50))).scalars().all()
        player_ids = list({*gold_top_ids, *bank_top_ids})

        if not player_ids:
            await wealth_rank_cmd.finish("暂无排行榜数据")

        # 拉取候选玩家
        all_players_stmt = select(Player).where(Player.id.in_(player_ids))
        all_players = (await session.execute(all_players_stmt)).scalars().all()

        # 批量查询银行余额并结息以确保余额最新
        bank_stmt = select(BankAccount).where(BankAccount.player_id.in_(player_ids))
        bank_accounts = (await session.execute(bank_stmt)).scalars().all()
        # 结息，保持与【存款榜】一致的口径
        from ..economy.bank import _apply_interest
        for acc in bank_accounts:
            _apply_interest(acc)
        if bank_accounts:
            session.add_all(bank_accounts)
            await session.commit()
        bank_map = {acc.player_id: acc.balance for acc in bank_accounts}

        # 批量查询投资持仓
        from sqlalchemy.orm import selectinload
        holdings_stmt = select(StockHolding).options(
            selectinload(StockHolding.stock)
        ).where(
            StockHolding.player_id.in_(player_ids),
            StockHolding.shares > 0
        )
        all_holdings = (await session.execute(holdings_stmt)).scalars().all()

        # 按玩家ID分组计算投资价值
        investment_map = {}
        for holding in all_holdings:
            if holding.player_id not in investment_map:
                investment_map[holding.player_id] = 0
            investment_map[holding.player_id] += holding.current_value

        # 计算每个玩家的总财富
        wealth_data = []
        for player in all_players:
            # 面板金币
            gold = player.gold

            # 银行余额
            bank_balance = bank_map.get(player.id, 0)

            # 投资价值
            investment_value = investment_map.get(player.id, 0)

            # 总财富
            total_wealth = gold + bank_balance + investment_value

            wealth_data.append({
                'player': player,
                'gold': gold,
                'bank_balance': bank_balance,
                'investment_value': investment_value,
                'total_wealth': total_wealth
            })

        # 按总财富排序
        wealth_data.sort(key=lambda x: x['total_wealth'], reverse=True)

        # 分页处理
        page_data = wealth_data[offset:offset + page_size]

        lines = [f"💰 财富排行榜 (第{page}/3页)", "━━━━━━━━━━━━━"]
        for idx, data in enumerate(page_data, start=offset + 1):
            p = data['player']
            total = data['total_wealth']

            # 使用emoji装饰前三名
            rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."

            # 格式化金额显示
            formatted_wealth = _format_wealth(total)

            lines.append(f"{rank_emoji} {p.nickname}[UID:{p.uid}] - {formatted_wealth}")

        if page < 3:
            lines.append("━━━━━━━━━━━━━")
            lines.append("💡 使用【财富榜 页码】查看其他页")
            lines.append("💡 总财富 = 面板金币 + 银行余额 + 投资价值")

    await wealth_rank_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 探索榜 ====================
exploration_rank_cmd = on_command("探索榜", aliases={"探索排行榜", "诡域榜"}, block=True, priority=5)

@exploration_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """显示最高探索层数的前10名玩家"""
    async with safe_session() as session:
        stmt = select(Player).order_by(Player.max_dungeon_level.desc()).limit(10)
        players = (await session.execute(stmt)).scalars().all()

    if not players:
        await exploration_rank_cmd.finish("暂无排行榜数据")

    exploration_quotes = [
        "深渊凝视着你，而你也在凝视着深渊。",
        "越是深入未知，越能发现自己的极限。",
        "在诡域的深处，只有最勇敢的灵魂才能前行。",
        "每一层诡域，都是对意志的考验。",
        "探索者的足迹，是通往真理的阶梯。"
    ]

    quote = random.choice(exploration_quotes)
    lines = ["🌀 探索排行榜", quote, "━━━━━━━━━━━━━"]

    for idx, p in enumerate(players, 1):
        # 使用emoji装饰前三名
        rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."

        # 根据探索层数显示不同的称号（扩充高阶段位）
        lvl = p.max_dungeon_level
        if lvl == 0:
            title = "🌱新手探索者"
        elif lvl < 10:
            title = "🔍初级探索者"
        elif lvl < 50:
            title = "⚔️资深探索者"
        elif lvl < 100:
            title = "🌟精英探索者"
        elif lvl < 200:
            title = "👑大师探索者"
        elif lvl < 300:
            title = "🕳️深渊行者"
        elif lvl < 500:
            title = "🔮虚空寻路者"
        elif lvl < 800:
            title = "👁️边界见证者"
        elif lvl < 1000:
            title = "🌀维度旅者"
        elif lvl < 1500:
            title = "🌙禁忌开拓者"
        else:
            title = "🌌不可名状的先驱"

        lines.append(f"{rank_emoji} {p.nickname}[UID:{p.uid}] - {title} 第{p.max_dungeon_level}层")

    await exploration_rank_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 敏捷榜 ====================
agility_rank_cmd = on_command("敏捷榜", aliases={"速度榜", "敏捷排行榜", "速度排行榜"}, block=True, priority=5)

@agility_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """显示敏捷值最高的前10名玩家"""
    async with safe_session() as session:
        stmt = select(Player).order_by(Player.agility.desc()).limit(10)
        players = (await session.execute(stmt)).scalars().all()

    if not players:
        await agility_rank_cmd.finish("暂无排行榜数据")

    agility_quotes = [
        "疾如风，徐如林，侵掠如火，不动如山。",
        "速度不仅是力量，更是智慧的体现。",
        "在瞬息万变的战场上，敏捷决定生死。",
        "身如闪电，心如止水，这便是敏捷的真谛。",
        "快者为王，慢者为寇。"
    ]

    quote = random.choice(agility_quotes)
    lines = ["⚡ 敏捷排行榜", quote, "━━━━━━━━━━━━━"]

    for idx, p in enumerate(players, 1):
        # 使用emoji装饰前三名
        rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."

        # 根据敏捷值显示不同的称号（扩充高阶段位）
        agi = p.agility
        if agi < 10:
            title = "🐌迟缓者"
        elif agi < 30:
            title = "🚶‍♂️步行者"
        elif agi < 60:
            title = "🏃‍♂️奔跑者"
        elif agi < 100:
            title = "🦌疾风者"
        elif agi < 150:
            title = "⚡闪电者"
        elif agi < 200:
            title = "🌪️风暴者"
        elif agi < 300:
            title = "🌬️音障破者"
        elif agi < 500:
            title = "🌠流星掠影"
        elif agi < 800:
            title = "🛰️轨道驰骋者"
        elif agi < 1200:
            title = "⏱️时隙跃迁者"
        elif agi < 2000:
            title = "🕳️相对论践踏者"
        else:
            title = "🌀相位神行者"

        lines.append(f"{rank_emoji} {p.nickname}[UID:{p.uid}] - {title} ⚡{p.agility}")

    await agility_rank_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 小游戏榜 ====================
mini_game_rank_cmd = on_command("小游戏榜", aliases={"游戏榜", "小游戏排行榜"}, block=True, priority=5)

@mini_game_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """显示小游戏积分最高的前10名玩家"""
    async with safe_session() as session:
        stmt = select(Player).order_by(Player.mini_game_score.desc()).limit(10)
        players = (await session.execute(stmt)).scalars().all()

    if not players:
        await mini_game_rank_cmd.finish("暂无排行榜数据")

    game_quotes = [
        "游戏人生，人生如戏，在虚拟与现实间寻找真我。",
        "每一次游戏都是一次冒险，每一分积分都是勇气的见证。",
        "在游戏的世界里，你就是自己命运的主宰。",
        "胜负乃兵家常事，重要的是享受游戏的过程。",
        "小游戏，大智慧，方寸之间见真章。"
    ]

    quote = random.choice(game_quotes)
    lines = ["🎮 小游戏排行榜", quote, "━━━━━━━━━━━━━"]

    for idx, p in enumerate(players, 1):
        # 使用emoji装饰前三名
        rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."

        # 根据积分显示不同的称号
        if p.mini_game_score == 0:
            title = "🌱游戏新手"
        elif p.mini_game_score < 10:
            title = "🎯初级玩家"
        elif p.mini_game_score < 50:
            title = "🎲资深玩家"
        elif p.mini_game_score < 100:
            title = "🎪游戏达人"
        elif p.mini_game_score < 200:
            title = "🎨游戏大师"
        elif p.mini_game_score < 500:
            title = "👑游戏王者"
        else:
            title = "🌟传奇玩家"

        lines.append(f"{rank_emoji} {p.nickname}[UID:{p.uid}] - {title} 🎮{p.mini_game_score}分")

    await mini_game_rank_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 排行榜总览 ====================
all_rankings_cmd = on_command("排行榜", aliases={"榜单", "排行榜总览"}, block=True, priority=5)

@all_rankings_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """显示所有排行榜的入口"""
    lines = [
        "🏆 排行榜总览",
        "━━━━━━━━━━━━━",
        "🎯 玩家排行榜：",
        "📈 【修为榜】 - 查看修为排行",
        "🍀 【幸运榜】 - 查看幸运排行",
        "💰 【财富榜】 - 查看财富排行（含现金+存款+投资）",
        "🌀 【探索榜】 - 查看探索排行",
        "⚡ 【敏捷榜】 - 查看敏捷排行",
        "🎮 【小游戏榜】 - 查看小游戏排行",
        "🎣 【钓鱼排行】 - 查看钓鱼排行",
        "",
        "🏛️ 系统排行榜：",
        "🏦 【存款榜】 - 查看存款排行",
        "💕 【恩爱榜】 - 查看夫妻恩爱排行",
        "🎓 【恩师榜】 - 查看师父恩师排行",
        "👹 【BOSS排行】 - 查看世界BOSS伤害排行",
        "🏰 【公会列表】 - 查看公会排行",
        "━━━━━━━━━━━━━",
        "💡 发送对应指令查看详细排行榜"
    ]

    await all_rankings_cmd.finish(message_add_head("\n".join(lines), event))


