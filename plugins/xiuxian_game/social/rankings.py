from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from sqlalchemy import select, func

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head


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
async def handle_charm_ranking(event: MessageEvent):
    """魅力榜命令 - 显示全服魅力值Top100"""
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal

    async with UnitOfWork(AsyncSessionLocal) as uow:
        # 获取魅力值Top100
        from sqlalchemy import desc

        result = await uow.session.execute(
            select(uow.players.model.nickname, uow.players.model.charm)
            .where(uow.players.model.charm > 0)
            .order_by(desc(uow.players.model.charm))
            .limit(100)
        )

        ranking = list(result.all())

        if not ranking:
            await charm_ranking_cmd.finish(message_add_head("💖 全服魅力榜 💖\n━━━━━━━━━━━━━━━━━━━━\n\n暂无数据", event))
            return

        # 格式化输出
        lines = [
            "💖 全服魅力榜 💖",
            "━━━━━━━━━━━━━━━━━━━━",
            ""
        ]

        for idx, (nickname, charm) in enumerate(ranking, start=1):
            # 前三名特殊标识
            if idx == 1:
                medal = "🥇"
            elif idx == 2:
                medal = "🥈"
            elif idx == 3:
                medal = "🥉"
            else:
                medal = "  "

            lines.append(f"{medal} #{idx:3d} {nickname}: {charm} 魅力值")

        lines.append("")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 提示: 收到好感度礼物可增加魅力值")

        await charm_ranking_cmd.finish(message_add_head("\n".join(lines), event))
