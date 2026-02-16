from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
import random
from typing import Callable, Awaitable

from ..models.db import safe_session
from ..utils import message_add_head
from ..platform_utils import get_unified_player
from .realm_utils import realm_by_level_and_reincarnation
from ..queries.ranking_queries import (
    RankedPlayer,
    query_level_ranking,
    query_luck_ranking,
    query_wealth_ranking,
    query_exploration_ranking,
    query_agility_ranking,
    query_mini_game_ranking,
    query_player_rank,
    query_player_rank_by_counting,
)


# ==================== 公共辅助函数 ====================

def _rank_emoji(idx: int) -> str:
    if idx == 1:
        return "🥇"
    if idx == 2:
        return "🥈"
    if idx == 3:
        return "🥉"
    return f"{idx}."


def _calculate_centered_offset(player_rank: int, total_count: int, page_size: int = 10) -> int:
    """计算以玩家为中心的显示偏移量"""
    rank_idx = player_rank - 1
    half = page_size // 2
    start = max(0, rank_idx - half)
    if start + page_size > total_count:
        start = max(0, total_count - page_size)
    return start


def _format_wealth(amount: int) -> str:
    """格式化财富显示"""
    if amount >= 100_000_000:
        value = amount / 100_000_000
        return f"{value:.1f}e💰" if value >= 10 else f"{value:.2f}e💰"
    elif amount >= 10_000:
        value = amount / 10_000
        return f"{value:.1f}w💰" if value >= 100 else f"{value:.2f}w💰"
    else:
        return f"{amount}💰"


async def _ensure_player_in_list(
    ranked_list: list[RankedPlayer],
    player_rank: int | None,
    query_fn,
    page_size: int = 10,
) -> list[RankedPlayer]:
    """当玩家排名超出缓存列表时，扩大查询范围以确保玩家可见"""
    if player_rank and player_rank > len(ranked_list):
        return await query_fn(limit=player_rank + page_size)
    return ranked_list


def _paginate_ranking(
    ranked_list: list[RankedPlayer],
    page: int | None,
    player_rank: int | None,
    player_id: str | None,
    page_size: int = 10,
) -> tuple[list[RankedPlayer], int]:
    """从缓存的排行数据中取出分页数据

    Returns:
        (当前页条目列表, 起始偏移量)
    """
    total = len(ranked_list)
    if not page and player_rank:
        offset = _calculate_centered_offset(player_rank, total, page_size)
    elif page:
        page = max(1, min(page, 3))
        offset = (page - 1) * page_size
    else:
        offset = 0
    return ranked_list[offset:offset + page_size], offset


async def _resolve_player_and_rank(
    event: MessageEvent,
    ranking_type: str,
    page_text: str,
) -> tuple[str | None, int | None, int | None]:
    """解析玩家身份和排名

    Returns:
        (player_id, player_rank, page)
    """
    page = None
    player_id = None
    player_rank = None

    if page_text:
        try:
            page = int(page_text)
        except ValueError:
            page = 1
        page = max(1, min(page, 3))
    else:
        async with safe_session() as session:
            player = await get_unified_player(session, event)
            if player:
                player_id = player.id
                # 先从缓存榜单查找
                player_rank = await query_player_rank(player_id, ranking_type)
                # 如果不在 TOP N 缓存中，做一次精确 COUNT 查询
                if player_rank is None:
                    player_rank = await query_player_rank_by_counting(player_id, ranking_type)

    return player_id, player_rank, page


def _build_header(
    emoji: str,
    title: str,
    player_rank: int | None,
    page: int | None,
    quote: str | None = None,
) -> list[str]:
    """构建排行榜头部"""
    if player_rank is not None:
        header = f"{emoji} {title} (你的排名: 第{player_rank}名)"
    elif page is not None:
        header = f"{emoji} {title} (第{page}/3页)"
    else:
        header = f"{emoji} {title}"

    lines = [header]
    if quote:
        lines.append(quote)
    lines.append("━━━━━━━━━━━━━")
    return lines


# ==================== 称号工具函数 ====================

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


def _exploration_title(lvl: int) -> str:
    if lvl == 0:
        return "🌱新手探索者"
    if lvl < 10:
        return "🔍初级探索者"
    if lvl < 50:
        return "⚔️资深探索者"
    if lvl < 100:
        return "🌟精英探索者"
    if lvl < 200:
        return "👑大师探索者"
    if lvl < 300:
        return "🕳️深渊行者"
    if lvl < 500:
        return "🔮虚空寻路者"
    if lvl < 800:
        return "👁️边界见证者"
    if lvl < 1000:
        return "🌀维度旅者"
    if lvl < 1500:
        return "🌙禁忌开拓者"
    return "🌌不可名状的先驱"


def _agility_title(agi: int) -> str:
    if agi < 10:
        return "🐌迟缓者"
    if agi < 30:
        return "🚶‍♂️步行者"
    if agi < 60:
        return "🏃‍♂️奔跑者"
    if agi < 100:
        return "🦌疾风者"
    if agi < 150:
        return "⚡闪电者"
    if agi < 200:
        return "🌪️风暴者"
    if agi < 300:
        return "🌬️音障破者"
    if agi < 500:
        return "🌠流星掠影"
    if agi < 800:
        return "🛰️轨道驰骋者"
    if agi < 1200:
        return "⏱️时隙跃迁者"
    if agi < 2000:
        return "🕳️相对论践踏者"
    return "🌀相位神行者"


def _mini_game_title(score: int) -> str:
    if score == 0:
        return "🌱游戏新手"
    if score < 10:
        return "🎯初级玩家"
    if score < 50:
        return "🎲资深玩家"
    if score < 100:
        return "🎪游戏达人"
    if score < 200:
        return "🎨游戏大师"
    if score < 500:
        return "👑游戏王者"
    return "🌟传奇玩家"


# ==================== 修为榜 ====================
level_rank_cmd = on_command("修为榜", aliases={"等级榜"}, block=True, priority=5)

@level_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """按等级及经验排序的玩家排行榜"""
    page_text = args.extract_plain_text().strip()
    player_id, player_rank, page = await _resolve_player_and_rank(event, "level", page_text)

    ranked_list = await query_level_ranking()
    if not ranked_list:
        await level_rank_cmd.finish("暂无排行榜数据")
    ranked_list = await _ensure_player_in_list(ranked_list, player_rank, query_level_ranking)

    page_data, offset = _paginate_ranking(ranked_list, page, player_rank, player_id)
    if not page_data:
        await level_rank_cmd.finish("暂无排行榜数据")

    lines = _build_header("📈", "修为排行榜", player_rank, page)

    for entry in page_data:
        realm_name = realm_by_level_and_reincarnation(
            entry.value, entry.extra.get("reincarnation_level", 0)
        )
        marker = " ◀" if player_id and entry.player_id == player_id else ""
        lines.append(
            f"{_rank_emoji(entry.rank)} {entry.nickname}[UID:{entry.uid}] "
            f"- Lv.{entry.value}『{realm_name}』 ({entry.extra.get('exp', 0)} EXP){marker}"
        )

    lines.append("━━━━━━━━━━━━━")
    lines.append("💡 使用【修为榜 页码】查看指定页(1-3)")
    await level_rank_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 幸运榜 ====================
luck_rank_cmd = on_command("幸运榜", aliases={"运气榜", "幸运排行榜"}, block=True, priority=5)

@luck_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """显示幸运值最高的玩家排行榜"""
    page_text = args.extract_plain_text().strip()
    player_id, player_rank, page = await _resolve_player_and_rank(event, "luck", page_text)

    ranked_list = await query_luck_ranking()
    if not ranked_list:
        await luck_rank_cmd.finish("暂无排行榜数据")
    ranked_list = await _ensure_player_in_list(ranked_list, player_rank, query_luck_ranking)

    page_data, offset = _paginate_ranking(ranked_list, page, player_rank, player_id)
    if not page_data:
        await luck_rank_cmd.finish("暂无排行榜数据")

    quote = random.choice([
        "你信任那些微小的可能性，于是，世界便以暴击的星火与翻倍的惊喜回应这份信任。",
        "这份加点，不是侥幸，是宣言：你相信，那1%的闪光，足以点亮100%的征程。",
        "凡俗眼中的偶然，是你掌中的必然。",
    ])
    lines = _build_header("🍀", "幸运排行榜", player_rank, page, quote)

    for entry in page_data:
        title = _luck_title(entry.value)
        marker = " ◀" if player_id and entry.player_id == player_id else ""
        lines.append(f"{_rank_emoji(entry.rank)} {entry.nickname}[UID:{entry.uid}] - {title} 🍀{entry.value}{marker}")

    lines.append("━━━━━━━━━━━━━")
    lines.append("💡 使用【幸运榜 页码】查看指定页")
    await luck_rank_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 财富榜 ====================
wealth_rank_cmd = on_command("财富榜", aliases={"财富排行榜"}, block=True, priority=5)

@wealth_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """显示总财富最多的玩家排行榜（金币+存款+投资）"""
    page_text = args.extract_plain_text().strip()
    player_id, player_rank, page = await _resolve_player_and_rank(event, "wealth", page_text)

    ranked_list = await query_wealth_ranking()
    if not ranked_list:
        await wealth_rank_cmd.finish("暂无排行榜数据")
    ranked_list = await _ensure_player_in_list(ranked_list, player_rank, query_wealth_ranking)

    page_data, offset = _paginate_ranking(ranked_list, page, player_rank, player_id)
    if not page_data:
        await wealth_rank_cmd.finish("暂无排行榜数据")

    lines = _build_header("💰", "财富排行榜", player_rank, page)

    for entry in page_data:
        formatted_wealth = _format_wealth(entry.value)
        marker = " ◀" if player_id and entry.player_id == player_id else ""
        lines.append(f"{_rank_emoji(entry.rank)} {entry.nickname}[UID:{entry.uid}] - {formatted_wealth}{marker}")

    lines.append("━━━━━━━━━━━━━")
    lines.append("💡 使用【财富榜 页码】查看指定页(1-3)")
    lines.append("💡 总财富 = 面板金币 + 银行余额 + 投资价值")
    await wealth_rank_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 探索榜 ====================
exploration_rank_cmd = on_command("探索榜", aliases={"探索排行榜", "诡域榜"}, block=True, priority=5)

@exploration_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """显示最高探索层数的玩家排行榜"""
    page_text = args.extract_plain_text().strip()
    player_id, player_rank, page = await _resolve_player_and_rank(event, "exploration", page_text)

    ranked_list = await query_exploration_ranking()
    if not ranked_list:
        await exploration_rank_cmd.finish("暂无排行榜数据")
    ranked_list = await _ensure_player_in_list(ranked_list, player_rank, query_exploration_ranking)

    page_data, offset = _paginate_ranking(ranked_list, page, player_rank, player_id)
    if not page_data:
        await exploration_rank_cmd.finish("暂无排行榜数据")

    quote = random.choice([
        "深渊凝视着你，而你也在凝视着深渊。",
        "越是深入未知，越能发现自己的极限。",
        "在诡域的深处，只有最勇敢的灵魂才能前行。",
        "每一层诡域，都是对意志的考验。",
        "探索者的足迹，是通往真理的阶梯。"
    ])
    lines = _build_header("🌀", "探索排行榜", player_rank, page, quote)

    for entry in page_data:
        title = _exploration_title(entry.value)
        marker = " ◀" if player_id and entry.player_id == player_id else ""
        lines.append(f"{_rank_emoji(entry.rank)} {entry.nickname}[UID:{entry.uid}] - {title} 第{entry.value}层{marker}")

    lines.append("━━━━━━━━━━━━━")
    lines.append("💡 使用【探索榜 页码】查看指定页(1-3)")
    await exploration_rank_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 敏捷榜 ====================
agility_rank_cmd = on_command("敏捷榜", aliases={"速度榜", "敏捷排行榜", "速度排行榜"}, block=True, priority=5)

@agility_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """显示敏捷值排行榜"""
    page_text = args.extract_plain_text().strip()
    player_id, player_rank, page = await _resolve_player_and_rank(event, "agility", page_text)

    ranked_list = await query_agility_ranking()
    if not ranked_list:
        await agility_rank_cmd.finish("暂无排行榜数据")
    ranked_list = await _ensure_player_in_list(ranked_list, player_rank, query_agility_ranking)

    page_data, offset = _paginate_ranking(ranked_list, page, player_rank, player_id)
    if not page_data:
        await agility_rank_cmd.finish("暂无排行榜数据")

    quote = random.choice([
        "疾如风，徐如林，侵掠如火，不动如山。",
        "速度不仅是力量，更是智慧的体现。",
        "在瞬息万变的战场上，敏捷决定生死。",
        "身如闪电，心如止水，这便是敏捷的真谛。",
        "快者为王，慢者为寇。"
    ])
    lines = _build_header("⚡", "敏捷排行榜", player_rank, page, quote)

    for entry in page_data:
        title = _agility_title(entry.value)
        marker = " ◀" if player_id and entry.player_id == player_id else ""
        lines.append(f"{_rank_emoji(entry.rank)} {entry.nickname}[UID:{entry.uid}] - {title} ⚡{entry.value}{marker}")

    lines.append("━━━━━━━━━━━━━")
    lines.append("💡 使用【敏捷榜 页码】查看指定页(1-3)")
    await agility_rank_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 小游戏榜 ====================
mini_game_rank_cmd = on_command("小游戏榜", aliases={"游戏榜", "小游戏排行榜"}, block=True, priority=5)

@mini_game_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """显示小游戏积分排行榜"""
    page_text = args.extract_plain_text().strip()
    player_id, player_rank, page = await _resolve_player_and_rank(event, "mini_game", page_text)

    ranked_list = await query_mini_game_ranking()
    if not ranked_list:
        await mini_game_rank_cmd.finish("暂无排行榜数据")
    ranked_list = await _ensure_player_in_list(ranked_list, player_rank, query_mini_game_ranking)

    page_data, offset = _paginate_ranking(ranked_list, page, player_rank, player_id)
    if not page_data:
        await mini_game_rank_cmd.finish("暂无排行榜数据")

    quote = random.choice([
        "游戏人生，人生如戏，在虚拟与现实间寻找真我。",
        "每一次游戏都是一次冒险，每一分积分都是勇气的见证。",
        "在游戏的世界里，你就是自己命运的主宰。",
        "胜负乃兵家常事，重要的是享受游戏的过程。",
        "小游戏，大智慧，方寸之间见真章。"
    ])
    lines = _build_header("🎮", "小游戏排行榜", player_rank, page, quote)

    for entry in page_data:
        title = _mini_game_title(entry.value)
        marker = " ◀" if player_id and entry.player_id == player_id else ""
        lines.append(f"{_rank_emoji(entry.rank)} {entry.nickname}[UID:{entry.uid}] - {title} 🎮{entry.value}分{marker}")

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
