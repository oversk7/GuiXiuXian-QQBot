"""
成就系统命令
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from ..models.db import safe_session
from ..models.player import Player
from ..platform_utils import get_unified_player
from ..utils import message_add_head
from .achievement_service import AchievementService

achievement_cmd = on_command("成就", aliases={"成就列表", "我的成就"}, block=True, priority=5)


@achievement_cmd.handle()
async def handle_achievement(event: MessageEvent):
    """显示玩家成就列表"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await achievement_cmd.finish("⛔ 请先创建角色")

        # 获取成就列表
        data = await AchievementService.get_player_achievements(session, player.id)

        # 构建显示消息
        lines = ["🏆 成就系统", "━━━━━━━━━━━━━"]

        # 显示已解锁成就
        if data["unlocked"]:
            lines.append(f"✅ 已解锁 ({len(data['unlocked'])}/10)：")
            for ach in data["unlocked"]:
                lines.append(f"{ach['icon']} {ach['title']} - {ach['description']}")
            lines.append("")

        # 显示未解锁成就（显示进度）
        if data["locked"]:
            lines.append(f"🔒 未解锁 ({len(data['locked'])}/10)：")
            for ach in data["locked"]:
                progress = data.get("progress", {}).get(ach["id"], 0)
                target = ach["condition_value"]
                lines.append(f"{ach['icon']} {ach['title']} - 进度: {progress}/{target}")
            lines.append("")

        lines.append("━━━━━━━━━━━━━")
        lines.append("💡 完成成就可获得金币、经验和属性点奖励！")

        await achievement_cmd.finish(message_add_head("\n".join(lines), event))
