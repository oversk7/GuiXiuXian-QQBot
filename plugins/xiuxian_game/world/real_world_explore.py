"""
现实世界探索命令

在现实世界中查看当前位置信息，包括地点、NPC、附近玩家等
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from .location_service import LocationService
from .npc_service import NPCService
from ..cultivate.mansion import MansionService

# ==================== Feature Flag ====================
# 设置为True使用新版DI架构的LocationService，False使用旧版本
# =====================================================


# ==================== 现实世界探索命令 ====================
real_explore_cmd = on_command("观察", aliases={"附近"}, block=True, priority=5)


@real_explore_cmd.handle()
async def handle_real_world_explore(event: MessageEvent):
    """处理现实世界探索命令"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await real_explore_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await real_explore_cmd.finish("⛔ 请先创建角色")
        
        # 只在现实世界中使用
        if player.is_in_dungeon():
            await real_explore_cmd.finish("⛔ 你在诡域中，使用【探索】命令探索当前格子")
        
        # 检查并复活NPC
        await NPCService.check_and_respawn_npcs(session)
        
        # 获取当前位置信息
        current_x, current_y = player.get_current_coordinates()
        current_region = player.get_current_region()
        
        # 查找当前位置的地点
        location = await LocationService.get_location_by_coordinates(
            session, current_x, current_y, current_region
        )
        
        # 检查新手任务（在显示位置信息之前）
        from ..quest.novice_quest_service import NoviceQuestService
        quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(
            session, player, "command", {"command": "观察"}
        )

        if location:
            # 有地点，显示地点信息
            await show_location_info(session, player, location, current_x, current_y, event, quest_msg if quest_completed else None)
        else:
            # 没有地点，显示基本位置信息
            await show_basic_location_info(session, player, current_x, current_y, current_region, event, quest_msg if quest_completed else None)


async def show_location_info(session: AsyncSession, player: Player, location, current_x: int, current_y: int, event: MessageEvent, quest_msg: str = None):
    """显示地点详细信息"""
    # 获取地点摘要
    location_summary = await LocationService.get_location_summary(session, location)

    # 获取附近玩家
    nearby_players = await LocationService.get_nearby_players(
        session, location.x, location.y, location.region,
        max_distance=0, exclude_player_id=player.id  # 只显示同一坐标的玩家
    )

    # 格式化显示信息 - 使用正确的当前坐标
    info_text = LocationService.format_location_info(
        location_summary, current_x, current_y, nearby_players
    )

    # 添加阴宅信息
    mansion_info = await get_mansion_info_for_location(session, player, current_x, current_y)
    if mansion_info:
        info_text += "\n\n" + mansion_info

    # 添加新手任务完成消息
    if quest_msg:
        info_text += "\n\n" + quest_msg

    # 记录地点访问并检查成就
    from ..achievement.achievement_service import AchievementService
    location_key = f"{location.region}:{location.x}:{location.y}"
    await AchievementService.add_visited_location(session, player.id, location_key)

    # 检查探索类成就
    achievement_messages = await AchievementService.check_achievements(session, player.id)
    if achievement_messages:
        info_text += "\n\n" + "\n\n".join(achievement_messages)

    await real_explore_cmd.finish(message_add_head(info_text, event))


async def show_basic_location_info(session: AsyncSession, player: Player, x: int, y: int,
                                 region: str, event: MessageEvent, quest_msg: str = None):
    """显示基本位置信息（没有特殊地点时）"""
    # 获取附近玩家
    nearby_players = await LocationService.get_nearby_players(
        session, x, y, region, max_distance=3, exclude_player_id=player.id
    )
    
    # 获取附近地点
    nearby_locations = await LocationService.get_nearby_locations(
        session, x, y, region, max_distance=50
    )

    # 获取附近的阴宅
    from ..cultivate.mansion import MansionService
    from sqlalchemy import select, and_, func
    nearby_mansions = []

    # 查询附近50格内的阴宅
    mansion_stmt = select(Player).where(
        and_(
            Player.mansion_level > 0,
            Player.mansion_x.isnot(None),
            Player.mansion_y.isnot(None),
            Player.region == region,
            func.abs(Player.mansion_x - x) + func.abs(Player.mansion_y - y) <= 50
        )
    )
    mansion_result = await session.execute(mansion_stmt)
    mansion_owners = mansion_result.scalars().all()

    for owner in mansion_owners:
        distance = abs(owner.mansion_x - x) + abs(owner.mansion_y - y)
        nearby_mansions.append({
            "name": f"🏚️ {owner.nickname}的阴宅",
            "x": owner.mansion_x,
            "y": owner.mansion_y,
            "distance": distance,
            "level": owner.mansion_level
        })
    
    lines = [
        f"所在地 ※ 荒野({x},{y})",
        "这里是一片普通的区域，没有特殊的建筑或服务。",
        ""
    ]
    
    # 显示附近玩家
    if nearby_players:
        player_count = len(nearby_players)
        display_players = nearby_players[:20]
        player_names = []
        for p in display_players:
            player_names.append(f"{p.nickname}[{p.uid}]")
        
        lines.append(f"⛹️附近玩家({player_count}): {'、'.join(player_names)}")
        if player_count > 20:
            lines.append(f"...等{player_count}个玩家")
        lines.append("👉攻击 <玩家>")
        lines.append("")
    
    # 显示附近地点（包括阴宅）
    all_nearby_places = []

    # 添加普通地点
    for loc in nearby_locations:
        distance = abs(loc.x - x) + abs(loc.y - y)
        all_nearby_places.append({
            "name": loc.name,
            "x": loc.x,
            "y": loc.y,
            "distance": distance,
            "type": "location"
        })

    # 添加阴宅
    all_nearby_places.extend([{
        "name": mansion["name"],
        "x": mansion["x"],
        "y": mansion["y"],
        "distance": mansion["distance"],
        "type": "mansion"
    } for mansion in nearby_mansions])

    if all_nearby_places:
        # 按距离排序
        all_nearby_places.sort(key=lambda p: p["distance"])

        # 获取地点类型图标
        def get_location_icon(place):
            """根据地点类型返回图标"""
            if place["type"] == "mansion":
                return "🏚️"
            # 尝试从地点名称推断类型
            name = place["name"]
            if any(keyword in name for keyword in ["市集", "市", "商"]):
                return "🏪"
            elif any(keyword in name for keyword in ["工坊", "锻造", "炼"]):
                return "⚒️"
            elif any(keyword in name for keyword in ["总部", "司", "缉邪"]):
                return "🏛️"
            elif any(keyword in name for keyword in ["郊", "镇", "城", "岭", "山"]):
                return "📍"
            else:
                return "📌"

        lines.append(f"🗺️ 附近地点（{len(all_nearby_places)}个）：")

        # 显示前10个最近的地点
        display_count = min(10, len(all_nearby_places))
        for place in all_nearby_places[:display_count]:
            icon = get_location_icon(place)
            # 检查地点名称是否已包含坐标，避免重复显示
            if f"({place['x']},{place['y']})" in place["name"]:
                lines.append(f"{icon} {place['name']} - {place['distance']}格")
            else:
                lines.append(f"{icon} {place['name']} ({place['x']},{place['y']}) - {place['distance']}格")

        # 如果还有更多地点，显示提示
        if len(all_nearby_places) > display_count:
            lines.append(f"...还有{len(all_nearby_places) - display_count}个地点")

        lines.append("━━━━━━━━━━━━━")
        lines.append("💡 【前往 地点名】快速导航")
        lines.append("💡 【查找 NPC】搜索NPC位置")
    else:
        lines.append("🔍 附近50格内没有特殊地点")
        lines.append("💡 使用【地图】查看所有地点坐标")
    
    info_text = "\n".join(lines)

    # 添加阴宅信息
    mansion_info = await get_mansion_info_for_location(session, player, x, y)
    if mansion_info:
        info_text += "\n\n" + mansion_info

    # 添加新手任务完成消息
    if quest_msg:
        info_text += "\n\n" + quest_msg

    await real_explore_cmd.finish(message_add_head(info_text, event))


async def get_mansion_info_for_location(session: AsyncSession, player: Player, x: int, y: int) -> str | None:
    """获取指定位置的阴宅信息，用于在观察指令中显示"""
    # 查找当前位置的阴宅主人
    mansion_owner = await MansionService.find_mansion_owner_at_location(session, x, y)

    if not mansion_owner:
        return None

    mansion_info = MansionService.get_mansion_info(mansion_owner.mansion_level)

    # 检查是否可以使用
    can_use, use_msg = await MansionService.can_use_mansion(session, player, mansion_owner)

    # 构建简化的阴宅信息
    if player.id == mansion_owner.id:
        # 阴宅主人查看自己的阴宅
        status_info = "你的阴宅"
        usage_info = ""
    else:
        # 其他玩家查看
        status_info = f"{mansion_owner.nickname}[{mansion_owner.uid}] 的阴宅"
        if can_use:
            if mansion_owner.mansion_usage_fee > 0:
                usage_info = f"💰 使用费用：{mansion_owner.mansion_usage_fee:,}金币"
            else:
                usage_info = "💰 免费使用"
        else:
            usage_info = f"❌ {use_msg}"

    lines = [
        f"🏚️ 阴宅信息",
        f"━━━━━━━━━━━━━",
        f"✧ {status_info} (Lv.{mansion_info['level']})",
        f"✧ 修炼效率：+{mansion_info['efficiency_percent']:.1f}%"
    ]

    if usage_info:
        lines.append(f"✧ {usage_info}")

    return "\n".join(lines)


# ==================== 地点详情命令 ====================
location_detail_cmd = on_command("地点详情", aliases={"地点信息"}, block=True, priority=5)


@location_detail_cmd.handle()
async def handle_location_detail(event: MessageEvent):
    """显示当前地点的详细信息"""
    from ..platform_utils import get_unified_player

    async with safe_session() as session:
        player: Player = await get_unified_player(session, event)
        if not player:
            await location_detail_cmd.finish("⛔ 请先创建角色")
        
        if player.is_in_dungeon():
            await location_detail_cmd.finish("⛔ 你在诡域中，无法查看现实世界地点信息")
        
        # 获取当前位置的地点
        current_x, current_y = player.get_current_coordinates()
        current_region = player.get_current_region()
        
        location = await LocationService.get_location_by_coordinates(
            session, current_x, current_y, current_region
        )
        
        if not location:
            await location_detail_cmd.finish("⛔ 当前位置没有特殊地点")
        
        # 获取地点详细信息
        location_summary = await LocationService.get_location_summary(session, location)
        npcs_by_type = location_summary["npcs_by_type"]
        functions = location_summary["functions"]
        
        lines = [
            f"🏛️ {location.name} 详细信息",
            "━━━━━━━━━━━━━",
            f"📍 坐标：({location.x},{location.y})",
            f"🌍 区域：{location.region}",
            f"📝 描述：{location.description}",
            ""
        ]
        
        # 显示地点功能
        if functions:
            lines.append("⚙️ 地点功能：")
            function_names = {
                "market": "🏬 市集交易",
                "part_time_job": "💼 打工服务", 
                "forge": "⚒️ 装备锻造",
                "special_shop": "🏛️ 特殊商店"
            }
            for func in functions:
                func_name = function_names.get(func, f"🔧 {func}")
                lines.append(f"• {func_name}")
            lines.append("")
        
        # 显示NPC详情
        if npcs_by_type:
            lines.append("🤖 驻守NPC：")
            for npc_type, npcs in npcs_by_type.items():
                type_names = {
                    "merchant": "商人",
                    "craftsman": "工匠", 
                    "employer": "雇主",
                    "ghost": "鬼怪",
                    "special_vendor": "特殊商贩",
                    "guard": "守卫"
                }
                type_name = type_names.get(npc_type, npc_type)
                lines.append(f"• {type_name}：")
                for npc in npcs:
                    status = ""
                    if npc.is_dead():
                        status = " [已死亡]"
                    elif npc.is_respawning():
                        remaining = npc.respawn_time - npc.death_time
                        minutes = int(remaining.total_seconds() / 60)
                        status = f" [复活中:{minutes}分钟]"
                    
                    lines.append(f"  - {npc.name}{status}")
                    if npc.description:
                        lines.append(f"    {npc.description}")
            lines.append("")
        
        # 显示使用提示
        lines.extend([
            "━━━━━━━━━━━━━",
            "💡 使用方法：",
            "• 【交互 <NPC名称>】与NPC交互",
            "• 【攻击 <目标>】攻击玩家或NPC",
            "• 【市集】查看市场（如果有）",
            "• 【打工】查看工作（如果有）"
        ])
        
        info_text = "\n".join(lines)
        await location_detail_cmd.finish(message_add_head(info_text, event))
