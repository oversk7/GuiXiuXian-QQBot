"""
成就系统命令
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg
from nonebot.adapters.qq import Message
from ..models.db import safe_session
from ..models.player import Player
from ..platform_utils import get_unified_player
from ..utils import message_add_head
from .achievement_service import AchievementService

achievement_cmd = on_command("成就", aliases={"成就列表", "我的成就"}, block=True, priority=5)


@achievement_cmd.handle()
async def handle_achievement(event: MessageEvent, args: Message = CommandArg()):
    """显示玩家成就列表或成就详情"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await achievement_cmd.finish("⛔ 请先创建角色")

        # 解析参数
        arg_text = args.extract_plain_text().strip()

        # 如果有参数，显示成就详情
        if arg_text:
            await show_achievement_detail(session, player, arg_text, event)
            return

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
        lines.append("💡 提示：使用【成就 成就名】查看详情")
        lines.append("💡 完成成就可获得金币、经验和属性点奖励！")

        await achievement_cmd.finish(message_add_head("\n".join(lines), event))


async def show_achievement_detail(session, player, achievement_name: str, event: MessageEvent):
    """显示成就详情"""
    # 加载成就配置
    config = AchievementService._load_achievement_config()
    if not config:
        await achievement_cmd.finish("⛔ 成就配置加载失败")

    # 查找成就
    achievement_data = None
    achievement_id = None
    for aid, ach in config["basic_achievements"].items():
        if ach["title"] == achievement_name or aid == achievement_name:
            achievement_data = ach
            achievement_id = aid
            break

    if not achievement_data:
        await achievement_cmd.finish(f"❌ 未找到成就: {achievement_name}")

    # 获取玩家成就和统计数据
    data = await AchievementService.get_player_achievements(session, player.id)

    # 检查是否已解锁
    unlocked = any(ach["id"] == achievement_id for ach in data["unlocked"])

    # 获取当前进度
    progress = data.get("progress", {}).get(achievement_id, 0)
    target = achievement_data["condition_value"]

    # 构建详情消息
    lines = [
        f"{achievement_data['icon']} {achievement_data['title']}",
        "━━━━━━━━━━━━━",
        f"📝 描述：{achievement_data['description']}",
        f"✨ 寄语：{achievement_data.get('flavor_text', '无')}",
        "",
        "📊 完成条件：",
    ]

    # 显示条件类型
    condition_type = achievement_data["condition_type"]
    condition_map = {
        "command_count": "完成指定命令",
        "level_up": "等级提升",
        "level_reached": "达到指定等级",
        "battle_win": "战斗胜利",
        "kill_count": "击杀敌人",
        "equipment_obtained": "获得装备",
        "gold_total": "累计获得金币",
        "locations_visited": "探索地点",
        "login_streak": "连续登录"
    }
    lines.append(f"  类型：{condition_map.get(condition_type, condition_type)}")
    lines.append(f"  目标：{target}")

    # 显示进度
    if unlocked:
        lines.append(f"  状态：✅ 已解锁")
        # 查找解锁时间
        for ach in data["unlocked"]:
            if ach["id"] == achievement_id:
                lines.append(f"  解锁时间：{ach.get('unlocked_at', '未知')}")
                break
    else:
        progress_pct = int(progress / target * 100) if target > 0 else 0
        lines.append(f"  状态：🔒 未解锁")
        lines.append(f"  进度：{progress}/{target} ({progress_pct}%)")

    lines.append("")
    lines.append("🎁 奖励：")
    rewards = achievement_data.get("rewards", {})
    if rewards.get("exp"):
        lines.append(f"  怨炁 +{rewards['exp']}")
    if rewards.get("gold"):
        lines.append(f"  金币 +{rewards['gold']}")
    if rewards.get("attribute_points"):
        lines.append(f"  属性点 +{rewards['attribute_points']}")

    lines.append("━━━━━━━━━━━━━")

    await achievement_cmd.finish(message_add_head("\n".join(lines), event))
