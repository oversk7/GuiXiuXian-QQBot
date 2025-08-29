from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select
import random

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from .info import realm_by_level, number_to_chinese

# ==================== 修为榜 ====================
level_rank_cmd = on_command("修为榜", aliases={"等级榜"}, block=True, priority=5)

@level_rank_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """按等级 (level) 及经验排序的前 10 名玩家排行榜"""
    async with safe_session() as session:
        stmt = select(Player).order_by(Player.reincarnation_level.desc(), Player.level.desc(), Player.exp.desc()).limit(10)
        players = (await session.execute(stmt)).scalars().all()

    if not players:
        await level_rank_cmd.finish("暂无排行榜数据")

    lines = ["📈 修为排行榜", "━━━━━━━━━━━━━"]
    for idx, p in enumerate(players, 1):
        # 使用新的境界显示函数，包含转生信息
        realm_name = realm_by_level_and_reincarnation(p.level, p.reincarnation_level)
        # 使用emoji装饰前三名
        rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        lines.append(f"{rank_emoji} {p.nickname}[UID:{p.uid}] - Lv.{p.level}『{realm_name}』 ({p.exp} EXP)")

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
    """显示金币最多的前10名玩家"""
    async with safe_session() as session:
        stmt = select(Player).order_by(Player.gold.desc()).limit(10)
        players = (await session.execute(stmt)).scalars().all()

    if not players:
        await wealth_rank_cmd.finish("暂无排行榜数据")

    lines = ["💰 财富排行榜", "━━━━━━━━━━━━━"]
    for idx, p in enumerate(players, 1):
        # 使用emoji装饰前三名
        rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        lines.append(f"{rank_emoji} {p.nickname}[UID:{p.uid}] - {p.gold}💰")

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

        # 根据探索层数显示不同的称号
        if p.max_dungeon_level == 0:
            title = "🌱新手探索者"
        elif p.max_dungeon_level < 10:
            title = "🔍初级探索者"
        elif p.max_dungeon_level < 50:
            title = "⚔️资深探索者"
        elif p.max_dungeon_level < 100:
            title = "🌟精英探索者"
        elif p.max_dungeon_level < 200:
            title = "👑大师探索者"
        else:
            title = "🌌传说探索者"

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

        # 根据敏捷值显示不同的称号
        if p.agility < 10:
            title = "🐌迟缓者"
        elif p.agility < 30:
            title = "🚶‍♂️步行者"
        elif p.agility < 60:
            title = "🏃‍♂️奔跑者"
        elif p.agility < 100:
            title = "🦌疾风者"
        elif p.agility < 150:
            title = "⚡闪电者"
        elif p.agility < 200:
            title = "🌪️风暴者"
        else:
            title = "💫光速者"

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
        "💰 【财富榜】 - 查看财富排行",
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
