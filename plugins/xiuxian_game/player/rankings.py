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
        realm_name = realm_by_level(p.level)
        # 使用emoji装饰前三名
        rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        # 转数信息（只有冥返过才显示）
        reincarnation_text = ""
        if p.reincarnation_level > 0:
            chinese_reincarnation = number_to_chinese(p.reincarnation_level)
            reincarnation_text = f"{chinese_reincarnation}转 "
        lines.append(f"{rank_emoji} {p.nickname}[UID:{p.uid}] - {reincarnation_text}Lv.{p.level}『{realm_name}』 ({p.exp} EXP)")

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
