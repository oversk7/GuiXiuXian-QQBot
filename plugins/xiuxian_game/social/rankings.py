from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select, func

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from ..utils_markdown import cmd, build_markdown
from ..platform_utils import get_unified_player


# ==================== 社交统计 ====================
social_stats_cmd = on_command("社交统计", aliases={"社交信息"}, block=True, priority=5)

@social_stats_cmd.handle()
async def handle_social_stats(event: MessageEvent):
    async with safe_session() as session:
        # 统计玩家总数
        player_count = (await session.execute(select(func.count(Player.id)))).scalar_one()

        # 统计最高魅力值
        max_charm_stmt = select(func.max(Player.charm))
        max_charm_value = (await session.execute(max_charm_stmt)).scalar_one() or 0

        lines = [
            "📊 社交系统统计",
            "━━━━━━━━━━━━━━",
            f"👥 总玩家数：{player_count}",
            f"💖 最高魅力值：{max_charm_value}",
            "",
            "💡 使用【魅力榜】查看魅力值排行",
            "💡 使用【赠礼】向其他玩家赠送礼物",
            "💡 使用【转移】当面转移物品"
        ]

        await social_stats_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 魅力榜 ====================
charm_ranking_cmd = on_command("魅力榜", aliases={"魅力排行榜"}, block=True, priority=5)

@charm_ranking_cmd.handle()
async def handle_charm_ranking(event: MessageEvent, args: Message = CommandArg()):
    """显示魅力值排行榜，无参数时以自己为中心展示"""
    page_text = args.extract_plain_text().strip()
    page_size = 10
    page = None
    player = None
    player_rank = None

    async with safe_session() as session:
        total_count = (await session.execute(
            select(func.count()).select_from(Player).where(Player.charm > 0)
        )).scalar_one()
        if total_count == 0:
            await charm_ranking_cmd.finish(message_add_head("💖 魅力排行榜\n━━━━━━━━━━━━━\n暂无数据", event))

        if not page_text:
            player = await get_unified_player(session, event)
            if player and player.charm > 0:
                players_above = (await session.execute(
                    select(func.count()).select_from(Player).where(Player.charm > player.charm)
                )).scalar_one()
                player_rank = players_above + 1
                rank_idx = player_rank - 1
                half = page_size // 2
                offset = max(0, rank_idx - half)
                if offset + page_size > total_count:
                    offset = max(0, total_count - page_size)
            else:
                offset = 0
        else:
            try:
                page = int(page_text)
            except ValueError:
                page = 1
            page = max(1, min(page, 3))
            offset = (page - 1) * page_size

        stmt = (
            select(Player)
            .where(Player.charm > 0)
            .order_by(Player.charm.desc())
            .offset(offset)
            .limit(page_size)
        )
        players = (await session.execute(stmt)).scalars().all()

    if not players:
        await charm_ranking_cmd.finish(build_markdown("💖 魅力排行榜\n***\n暂无数据"))

    if player_rank is not None:
        lines = [f"# 💖 魅力排行榜", f"你的排名: 第**{player_rank}**名", "***"]
    elif page is not None:
        lines = [f"# 💖 魅力排行榜 (第{page}/3页)", "***"]
    else:
        lines = ["# 💖 魅力排行榜", "***"]

    for idx, p in enumerate(players, start=offset + 1):
        rank_emoji = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        marker = " **◀你**" if player and p.id == player.id else ""
        lines.append(f"{rank_emoji} {cmd(p.nickname, f'面板 {p.uid}')} - {p.charm} 🍫{marker}")

    lines.append("***")
    lines.append("💡 收到好感度礼物可增加魅力值")

    await charm_ranking_cmd.finish(build_markdown("\n".join(lines)))
