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
    result_msg = None

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            result_msg = "⛔ 请先创建角色"
        else:
            # 解析参数
            arg_text = args.extract_plain_text().strip()

            # 判断参数类型：数字=页码，非数字=成就名，无参数=第1页
            page = 1
            if arg_text:
                # 尝试解析为页码
                if arg_text.isdigit():
                    page = int(arg_text)
                else:
                    # 不是数字，作为成就名处理
                    result_msg = await get_achievement_detail(session, player, arg_text)

            # 如果没有result_msg，说明是列表查询
            if result_msg is None:
                result_msg = await get_achievement_list(session, player, page)

    # 在上下文外部调用finish，避免连接泄漏
    await achievement_cmd.finish(message_add_head(result_msg, event))


async def get_achievement_list(session, player: Player, page: int) -> str:
    """获取成就列表消息（返回字符串而非调用finish）"""
    # 先检查并解锁成就（包括财富类成就）
    achievement_msgs = await AchievementService.check_achievements(session, player)

    # 获取成就列表
    data = await AchievementService.get_player_achievements(session, player.id)

    # 合并所有成就（已解锁在前，未解锁在后）
    all_achievements = []

    # 添加已解锁成就（标记状态）
    for ach in data["unlocked"]:
        ach_copy = ach.copy()
        ach_copy["is_unlocked"] = True
        all_achievements.append(ach_copy)

    # 添加未解锁成就（标记状态）
    for ach in data["locked"]:
        ach_copy = ach.copy()
        ach_copy["is_unlocked"] = False
        ach_copy["progress"] = data.get("progress", {}).get(ach["id"], 0)
        all_achievements.append(ach_copy)

    # 分页设置
    PAGE_SIZE = 15
    total_count = len(all_achievements)
    total_pages = (total_count + PAGE_SIZE - 1) // PAGE_SIZE  # 向上取整

    # 验证页码
    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages if total_pages > 0 else 1

    # 计算当前页的成就范围
    start_idx = (page - 1) * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_count)
    page_achievements = all_achievements[start_idx:end_idx]

    # 构建显示消息
    lines = [
        "🏆 成就系统",
        f"第 {page}/{total_pages} 页 | 总计 {len(data['unlocked'])}/{total_count} 已解锁",
        "━━━━━━━━━━━━━"
    ]

    # 显示当前页的成就
    for ach in page_achievements:
        if ach["is_unlocked"]:
            lines.append(f"✅ {ach['icon']} {ach['title']} - {ach['description']}")
        else:
            progress = ach.get("progress", 0)
            target = ach["condition_value"]
            condition_type = ach.get("condition_type", "")

            # 对于 account_age 类型的成就，使用特殊显示格式
            if condition_type == "account_age":
                if progress == 1:
                    status_text = f"✅ 符合条件（{target}前创建）"
                else:
                    status_text = f"❌ 限定成就（需{target}前创建）"
                lines.append(f"🔒 {ach['icon']} {ach['title']} - {status_text}")
            else:
                # 其他类型显示数值进度
                lines.append(f"🔒 {ach['icon']} {ach['title']} - 进度: {progress}/{target}")

    lines.append("")
    lines.append("━━━━━━━━━━━━━")
    lines.append("💡 使用【成就 页码】查看其他页")
    lines.append("💡 使用【成就 成就名】查看详情")

    # 附加成就解锁消息（如果有）
    if achievement_msgs:
        lines.append("")
        lines.extend(achievement_msgs)

    return "\n".join(lines)


async def get_achievement_detail(session, player, achievement_name: str) -> str:
    """获取成就详情消息（返回字符串而非调用finish）"""
    # 加载成就配置
    config = AchievementService._load_achievement_config()
    if not config:
        return "⛔ 成就配置加载失败"

    # 查找成就（合并基础成就和高难度成就）
    achievement_data = None
    achievement_id = None

    # 先搜索基础成就
    for aid, ach in config.get("basic_achievements", {}).items():
        if ach["title"] == achievement_name or aid == achievement_name:
            achievement_data = ach
            achievement_id = aid
            break

    # 如果没找到，再搜索高难度成就
    if not achievement_data:
        for aid, ach in config.get("advanced_achievements", {}).items():
            if ach["title"] == achievement_name or aid == achievement_name:
                achievement_data = ach
                achievement_id = aid
                break

    if not achievement_data:
        return f"❌ 未找到成就: {achievement_name}"

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
        "equipment_max_upgrade": "拥有满级装备",
        "gold_total": "累计获得金币",
        "locations_visited": "探索地点",
        "login_streak": "连续登录",
        "total_login_days": "累计登录天数",
        "account_age": "账号创建时间"
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
        lines.append(f"  状态：🔒 未解锁")

        # 对于 account_age 类型，使用特殊显示方式
        if condition_type == "account_age":
            if progress == 1:
                lines.append(f"  条件：✅ 符合（账号创建于 {target} 之前）")
            else:
                lines.append(f"  条件：❌ 不符合（需要在 {target} 之前创建账号）")
        else:
            # 其他类型显示数值进度和百分比
            progress_pct = int(progress / target * 100) if target > 0 else 0
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

    return "\n".join(lines)
