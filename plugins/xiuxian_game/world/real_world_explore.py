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


# ==================== 现实世界探索命令 ====================
real_explore_cmd = on_command("观察", aliases={"附近"}, block=True, priority=5)


@real_explore_cmd.handle()
async def handle_real_world_explore(event: MessageEvent):
    """处理现实世界探索命令"""
    async with safe_session() as session:
        player: Player = await session.get(Player, event.get_user_id())
        if not player:
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
        
        if location:
            # 有地点，显示地点信息
            await show_location_info(session, player, location, event)
        else:
            # 没有地点，显示基本位置信息
            await show_basic_location_info(session, player, current_x, current_y, current_region, event)


async def show_location_info(session: AsyncSession, player: Player, location, event: MessageEvent):
    """显示地点详细信息"""
    # 获取地点摘要
    location_summary = await LocationService.get_location_summary(session, location)
    
    # 获取附近玩家
    nearby_players = await LocationService.get_nearby_players(
        session, location.x, location.y, location.region, 
        max_distance=0, exclude_player_id=player.id  # 只显示同一坐标的玩家
    )
    
    # 格式化显示信息
    info_text = LocationService.format_location_info(
        location_summary, player.x, player.y, nearby_players
    )
    
    await real_explore_cmd.finish(message_add_head(info_text, event))


async def show_basic_location_info(session: AsyncSession, player: Player, x: int, y: int, 
                                 region: str, event: MessageEvent):
    """显示基本位置信息（没有特殊地点时）"""
    # 获取附近玩家
    nearby_players = await LocationService.get_nearby_players(
        session, x, y, region, max_distance=0, exclude_player_id=player.id
    )
    
    # 获取附近地点
    nearby_locations = await LocationService.get_nearby_locations(
        session, x, y, region, max_distance=50
    )
    
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
    
    # 显示附近地点
    if nearby_locations:
        lines.append("🗺️ 附近地点：")
        for loc in nearby_locations[:5]:  # 最多显示5个
            distance = abs(loc.x - x) + abs(loc.y - y)
            lines.append(f"• {loc.name} ({loc.x},{loc.y}) - 距离{distance}格")
        lines.append("💡 使用【导航 x y】前往指定地点")
    else:
        lines.append("🔍 附近50格内没有特殊地点")
        lines.append("💡 使用【地图】查看所有地点坐标")
    
    info_text = "\n".join(lines)
    await real_explore_cmd.finish(message_add_head(info_text, event))


# ==================== 地点详情命令 ====================
location_detail_cmd = on_command("地点详情", aliases={"地点信息"}, block=True, priority=5)


@location_detail_cmd.handle()
async def handle_location_detail(event: MessageEvent):
    """显示当前地点的详细信息"""
    async with safe_session() as session:
        player: Player = await session.get(Player, event.get_user_id())
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
