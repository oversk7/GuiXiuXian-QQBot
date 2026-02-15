from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select, func
from math import ceil
import random

from ..models.db import safe_session
from ..models.player import Player
from ..models.bank_account import BankAccount
from ..models.stock import StockHolding, Stock
from ..utils import message_add_head
from ..platform_utils import get_unified_player
from .realm_utils import realm_by_level_and_reincarnation, number_to_chinese


def _calculate_centered_offset(player_rank: int, total_count: int, page_size: int = 10) -> int:
    """计算以玩家为中心的显示偏移量

    当玩家前面不足half个人时，从头开始往后凑够page_size个。
    当玩家后面不足时，向前推移以凑够page_size个。

    Args:
        player_rank: 玩家排名（1-indexed）
        total_count: 总参与人数
        page_size: 显示条目数

    Returns:
        0-indexed的查询偏移量
    """
    rank_idx = player_rank - 1
    half = page_size // 2
    start = max(0, rank_idx - half)
    if start + page_size > total_count:
        start = max(0, total_count - page_size)
    return start


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
    """按等级及经验排序的玩家排行榜，无参数时以自己为中心展示"""
    page_text = args.extract_plain_text().strip()
    page_size = 10
    page = None
    player = None
    player_rank = None

    async with safe_session() as session:
        total_count = (await session.execute(select(func.count()).select_from(Player))).scalar_one()
        if total_count == 0:
            await level_rank_cmd.finish("暂无排行榜数据")

        if not page_text:
            player = await get_unified_player(session, event)
            if player:
                rank_stmt = select(func.count()).select_from(Player).where(
                    (Player.reincarnation_level > player.reincarnation_level) |
                    (
                        (Player.reincarnation_level == player.reincarnation_level) &
                        (Player.level > player.level)
                    ) |
                    (
                        (Player.reincarnation_level == player.reincarnation_level) &
                        (Player.level == player.level) &
                        (Player.exp > player.exp)
                    )
                )
                players_above = (await session.execute(rank_stmt)).scalar_one()
                player_rank = players_above + 1
                offset = _calculate_centered_offset(player_rank, total_count, page_size)
            else:
                offset = 0
        else:
            try:
                page = int(page_text)
            except ValueError:
                page = 1
            page = max(1, min(page, 3))
            offset = (page - 1) * page_size

        stmt = select(Player).order_by(
            Player.reincarnation_level.desc(), Player.level.desc(), Player.exp.desc()
        ).offset(offset).limit(page_size)
        players = (await session.execute(stmt)).scalars().all()

    if not players:
        await level_rank_cmd.finish("暂无排行榜数据")

    if player_rank is not None:
        lines = [f"📈 修为排行榜 (你的排名: 第{player_rank}名)", "━━━━━━━━━━━━━"]
    elif page is not None:
        lines = [f"📈 修为排行榜 (第{page}/3页)", "━━━━━━━━━━━━━"]
    else:
        lines = ["📈 修为排行榜", "━━━━━━━━━━━━━"]

    for idx, p in enumerate(players, start=offset + 1):
        realm_name = realm_by_level_and_reincarnation(p.level, p.reincarnation_level)
        rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        marker = " ◀" if player and p.id == player.id else ""
        lines.append(f"{rank_emoji} {p.nickname}[UID:{p.uid}] - Lv.{p.level}『{realm_name}』 ({p.exp} EXP){marker}")

    lines.append("━━━━━━━━━━━━━")
    lines.append("💡 使用【修为榜 页码】查看指定页(1-3)")

    await level_rank_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 幸运榜 ====================
luck_rank_cmd = on_command("幸运榜", aliases={"运气榜", "幸运排行榜"}, block=True, priority=5)


def _luck_title(luck: int) -> str:
    if luck < 30:
        return "🌱祈愿初成者"
    if luck < 60:
        return "🍃好运追逐者"
    if luck < 90:
        return "✨福运携行者"
    if luck < 130:
        return "🌈奇迹召唤者"
    if luck < 180:
        return "🌟命运眷顾者"
    if luck < 250:
        return "🪄祝福编织者"
    if luck < 400:
        return "🛡️奇迹庇护者"
    if luck < 600:
        return "🔥奇迹续燃者"
    if luck < 800:
        return "🪐命运引航者"
    if luck < 1000:
        return "🌌幸运主宰者"
    if luck < 1300:
        return "✨星命庇佑者"
    if luck < 1600:
        return "🌠福运星辉者"
    if luck < 2000:
        return "🌀无上幸运者"
    return "🏅天命之选者"


@luck_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """显示幸运值最高的玩家排行榜，无参数时以自己为中心展示"""
    page_text = args.extract_plain_text().strip()
    page_size = 10
    page = None
    player = None
    player_rank = None

    async with safe_session() as session:
        total_count = (await session.execute(select(func.count()).select_from(Player))).scalar_one()
        if total_count == 0:
            await luck_rank_cmd.finish("暂无排行榜数据")

        if not page_text:
            player = await get_unified_player(session, event)
            if player:
                players_above = (await session.execute(
                    select(func.count()).select_from(Player).where(Player.luck > player.luck)
                )).scalar_one()
                player_rank = players_above + 1
                offset = _calculate_centered_offset(player_rank, total_count, page_size)
            else:
                offset = 0
        else:
            try:
                page = int(page_text)
            except ValueError:
                page = 1
            total_pages = min(3, max(1, ceil(total_count / page_size)))
            page = max(1, min(page, total_pages))
            offset = (page - 1) * page_size

        stmt = select(Player).order_by(Player.luck.desc()).offset(offset).limit(page_size)
        players = (await session.execute(stmt)).scalars().all()

    if not players:
        await luck_rank_cmd.finish("暂无排行榜数据")

    wishes = random.choice([
        "你信任那些微小的可能性，于是，世界便以暴击的星火与翻倍的惊喜回应这份信任。",
        "这份加点，不是侥幸，是宣言：你相信，那1%的闪光，足以点亮100%的征程。",
        "凡俗眼中的偶然，是你掌中的必然。",
    ])

    if player_rank is not None:
        lines = [f"🍀 幸运排行榜 (你的排名: 第{player_rank}名)", wishes, "━━━━━━━━━━━━━"]
    elif page is not None:
        total_pages = min(3, max(1, ceil(total_count / page_size)))
        lines = [f"🍀 幸运排行榜 (第{page}/{total_pages}页)", wishes, "━━━━━━━━━━━━━"]
    else:
        lines = ["🍀 幸运排行榜", wishes, "━━━━━━━━━━━━━"]

    for idx, p in enumerate(players, start=offset + 1):
        rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        title = _luck_title(p.luck)
        marker = " ◀" if player and p.id == player.id else ""
        lines.append(f"{rank_emoji} {p.nickname}[UID:{p.uid}] - {title} 🍀{p.luck}{marker}")

    lines.append("━━━━━━━━━━━━━")
    lines.append("💡 使用【幸运榜 页码】查看指定页")

    await luck_rank_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 财富榜 ====================
wealth_rank_cmd = on_command("财富榜", aliases={"财富排行榜"}, block=True, priority=5)

@wealth_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """显示总财富最多的玩家排行榜，无参数时以自己为中心展示
    总财富 = 面板金币 + 银行余额 + 投资价值
    """
    page_text = args.extract_plain_text().strip()
    page_size = 10
    page = None
    player = None
    player_rank = None

    async with safe_session() as session:
        # 获取当前玩家（无论是否指定页码，财富榜需要构建候选列表）
        if not page_text:
            player = await get_unified_player(session, event)

        # 组合候选玩家：金币前50 + 存款前50 + 投资市值前50，确保高额投资者不会遗漏
        gold_top_ids = (await session.execute(select(Player.id).order_by(Player.gold.desc()).limit(50))).scalars().all()
        bank_top_ids = (await session.execute(select(BankAccount.player_id).order_by(BankAccount.balance.desc()).limit(50))).scalars().all()
        # 投资市值Top：按 sum(shares * current_price) 排序
        invest_top_ids = (await session.execute(
            select(StockHolding.player_id)
            .join(Stock, Stock.id == StockHolding.stock_id)
            .where(StockHolding.shares > 0)
            .group_by(StockHolding.player_id)
            .order_by(func.sum(StockHolding.shares * Stock.current_price).desc())
            .limit(50)
        )).scalars().all()
        player_ids = list({*gold_top_ids, *bank_top_ids, *invest_top_ids})

        # 确保当前玩家在候选列表中（用于centered view）
        if player and player.id not in player_ids:
            player_ids.append(player.id)

        if not player_ids:
            await wealth_rank_cmd.finish("暂无排行榜数据")

        # 拉取候选玩家
        all_players_stmt = select(Player).where(Player.id.in_(player_ids))
        all_players = (await session.execute(all_players_stmt)).scalars().all()

        # 批量查询银行余额
        bank_stmt = select(BankAccount).where(BankAccount.player_id.in_(player_ids))
        bank_accounts = (await session.execute(bank_stmt)).scalars().all()
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
        for p in all_players:
            gold = p.gold
            bank_balance = bank_map.get(p.id, 0)
            investment_value = investment_map.get(p.id, 0)
            total_wealth = gold + bank_balance + investment_value
            wealth_data.append({
                'player': p,
                'total_wealth': total_wealth
            })

        # 按总财富排序
        wealth_data.sort(key=lambda x: x['total_wealth'], reverse=True)

        if not page_text and player:
            # 以自己为中心展示
            for idx, data in enumerate(wealth_data, 1):
                if data['player'].id == player.id:
                    player_rank = idx
                    break
            if player_rank:
                offset = _calculate_centered_offset(player_rank, len(wealth_data), page_size)
            else:
                offset = 0
        elif page_text:
            try:
                page = int(page_text)
            except ValueError:
                page = 1
            page = max(1, min(page, 3))
            offset = (page - 1) * page_size
        else:
            offset = 0

        # 分页处理
        page_data = wealth_data[offset:offset + page_size]

        if player_rank is not None:
            lines = [f"💰 财富排行榜 (你的排名: 第{player_rank}名)", "━━━━━━━━━━━━━"]
        elif page is not None:
            lines = [f"💰 财富排行榜 (第{page}/3页)", "━━━━━━━━━━━━━"]
        else:
            lines = ["💰 财富排行榜", "━━━━━━━━━━━━━"]

        for idx, data in enumerate(page_data, start=offset + 1):
            p = data['player']
            total = data['total_wealth']
            rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
            formatted_wealth = _format_wealth(total)
            marker = " ◀" if player and p.id == player.id else ""
            lines.append(f"{rank_emoji} {p.nickname}[UID:{p.uid}] - {formatted_wealth}{marker}")

        lines.append("━━━━━━━━━━━━━")
        lines.append("💡 使用【财富榜 页码】查看指定页(1-3)")
        lines.append("💡 总财富 = 面板金币 + 银行余额 + 投资价值")

    await wealth_rank_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 探索榜 ====================
exploration_rank_cmd = on_command("探索榜", aliases={"探索排行榜", "诡域榜"}, block=True, priority=5)

@exploration_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """显示最高探索层数的玩家排行榜，无参数时以自己为中心展示"""
    page_text = args.extract_plain_text().strip()
    page_size = 10
    page = None
    player = None
    player_rank = None

    async with safe_session() as session:
        total_count = (await session.execute(select(func.count()).select_from(Player))).scalar_one()
        if total_count == 0:
            await exploration_rank_cmd.finish("暂无排行榜数据")

        if not page_text:
            player = await get_unified_player(session, event)
            if player:
                players_above = (await session.execute(
                    select(func.count()).select_from(Player).where(
                        Player.max_dungeon_level > player.max_dungeon_level
                    )
                )).scalar_one()
                player_rank = players_above + 1
                offset = _calculate_centered_offset(player_rank, total_count, page_size)
            else:
                offset = 0
        else:
            try:
                page = int(page_text)
            except ValueError:
                page = 1
            page = max(1, min(page, 3))
            offset = (page - 1) * page_size

        stmt = select(Player).order_by(Player.max_dungeon_level.desc()).offset(offset).limit(page_size)
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

    if player_rank is not None:
        lines = [f"🌀 探索排行榜 (你的排名: 第{player_rank}名)", quote, "━━━━━━━━━━━━━"]
    elif page is not None:
        lines = [f"🌀 探索排行榜 (第{page}/3页)", quote, "━━━━━━━━━━━━━"]
    else:
        lines = ["🌀 探索排行榜", quote, "━━━━━━━━━━━━━"]

    for idx, p in enumerate(players, start=offset + 1):
        rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."

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

        marker = " ◀" if player and p.id == player.id else ""
        lines.append(f"{rank_emoji} {p.nickname}[UID:{p.uid}] - {title} 第{p.max_dungeon_level}层{marker}")

    lines.append("━━━━━━━━━━━━━")
    lines.append("💡 使用【探索榜 页码】查看指定页(1-3)")

    await exploration_rank_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 敏捷榜 ====================
agility_rank_cmd = on_command("敏捷榜", aliases={"速度榜", "敏捷排行榜", "速度排行榜"}, block=True, priority=5)

@agility_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """显示敏捷值排行榜，无参数时以自己为中心展示"""
    page_text = args.extract_plain_text().strip()
    page_size = 10
    page = None
    player = None
    player_rank = None

    async with safe_session() as session:
        total_count = (await session.execute(select(func.count()).select_from(Player))).scalar_one()
        if total_count == 0:
            await agility_rank_cmd.finish("暂无排行榜数据")

        if not page_text:
            player = await get_unified_player(session, event)
            if player:
                players_above = (await session.execute(
                    select(func.count()).select_from(Player).where(Player.agility > player.agility)
                )).scalar_one()
                player_rank = players_above + 1
                offset = _calculate_centered_offset(player_rank, total_count, page_size)
            else:
                offset = 0
        else:
            try:
                page = int(page_text)
            except ValueError:
                page = 1
            page = max(1, min(page, 3))
            offset = (page - 1) * page_size

        stmt = select(Player).order_by(Player.agility.desc()).offset(offset).limit(page_size)
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

    if player_rank is not None:
        lines = [f"⚡ 敏捷排行榜 (你的排名: 第{player_rank}名)", quote, "━━━━━━━━━━━━━"]
    elif page is not None:
        lines = [f"⚡ 敏捷排行榜 (第{page}/3页)", quote, "━━━━━━━━━━━━━"]
    else:
        lines = ["⚡ 敏捷排行榜", quote, "━━━━━━━━━━━━━"]

    for idx, p in enumerate(players, start=offset + 1):
        rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."

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

        marker = " ◀" if player and p.id == player.id else ""
        lines.append(f"{rank_emoji} {p.nickname}[UID:{p.uid}] - {title} ⚡{p.agility}{marker}")

    lines.append("━━━━━━━━━━━━━")
    lines.append("💡 使用【敏捷榜 页码】查看指定页(1-3)")

    await agility_rank_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 小游戏榜 ====================
mini_game_rank_cmd = on_command("小游戏榜", aliases={"游戏榜", "小游戏排行榜"}, block=True, priority=5)

@mini_game_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """显示小游戏积分排行榜，无参数时以自己为中心展示"""
    page_text = args.extract_plain_text().strip()
    page_size = 10
    page = None
    player = None
    player_rank = None

    async with safe_session() as session:
        total_count = (await session.execute(select(func.count()).select_from(Player))).scalar_one()
        if total_count == 0:
            await mini_game_rank_cmd.finish("暂无排行榜数据")

        if not page_text:
            player = await get_unified_player(session, event)
            if player:
                players_above = (await session.execute(
                    select(func.count()).select_from(Player).where(
                        Player.mini_game_score > player.mini_game_score
                    )
                )).scalar_one()
                player_rank = players_above + 1
                offset = _calculate_centered_offset(player_rank, total_count, page_size)
            else:
                offset = 0
        else:
            try:
                page = int(page_text)
            except ValueError:
                page = 1
            page = max(1, min(page, 3))
            offset = (page - 1) * page_size

        stmt = select(Player).order_by(Player.mini_game_score.desc()).offset(offset).limit(page_size)
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

    if player_rank is not None:
        lines = [f"🎮 小游戏排行榜 (你的排名: 第{player_rank}名)", quote, "━━━━━━━━━━━━━"]
    elif page is not None:
        lines = [f"🎮 小游戏排行榜 (第{page}/3页)", quote, "━━━━━━━━━━━━━"]
    else:
        lines = ["🎮 小游戏排行榜", quote, "━━━━━━━━━━━━━"]

    for idx, p in enumerate(players, start=offset + 1):
        rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."

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

        marker = " ◀" if player and p.id == player.id else ""
        lines.append(f"{rank_emoji} {p.nickname}[UID:{p.uid}] - {title} 🎮{p.mini_game_score}分{marker}")

    lines.append("━━━━━━━━━━━━━")
    lines.append("💡 使用【小游戏榜 页码】查看指定页(1-3)")

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


