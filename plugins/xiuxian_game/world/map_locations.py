from __future__ import annotations

"""地图系统 - 显示所有地点信息

提供地图指令，显示游戏中所有重要地点的坐标和功能说明
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, MessageSegment, Message
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.part_time_job import JobLocation
from ..utils import message_add_head
from ..config import config

# 辅助函数
def _show_default_job_locations(lines):
    """显示默认的打工地点配置"""
    try:
        from ..economy.part_time_job_service import PartTimeJobService
        for location_data in PartTimeJobService.JOB_LOCATIONS.values():
            lines.append(f"• {location_data['name']} ({location_data['x']},{location_data['y']}) - {location_data['description']}")
    except ImportError:
        # 如果导入失败，显示基本信息（已整合到城镇中）
        lines.append("• 上京商业中心 (0,0) - 繁华的商业区")
        lines.append("• 荔湾镇工业区 (120,200) - 工厂集中的工业区")
        lines.append("• 郸城娱乐街区 (120,120) - 充满活力的娱乐区")
        lines.append("• 东郊物流中心 (390,50) - 物流配送中心")

# 可视化地图指令
visual_map_cmd = on_command("地图", aliases={"可视化地图"}, block=True, priority=5)

# 附近地点指令
nearby_locations_cmd = on_command("附近地点", aliases={"周边"}, block=True, priority=5)

@nearby_locations_cmd.handle()
async def _(event: MessageEvent):
    """显示附近的重要地点"""
    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await nearby_locations_cmd.finish("⛔ 请先创建角色")
        
        if player.region != "大都会":
            await nearby_locations_cmd.finish("⛔ 只有在大都会才能查看附近地点")
        
        # 计算距离的函数
        def calculate_distance(x1, y1, x2, y2):
            return abs(x1 - x2) + abs(y1 - y2)  # 曼哈顿距离
        
        nearby_places = []
        
        # 获取当前正确的坐标
        current_x, current_y = player.get_current_coordinates()

        # 1. 检查市集
        from ..economy.merchants import MARKETS
        for market in MARKETS:
            distance = calculate_distance(current_x, current_y, market.x, market.y)
            if distance <= 100:  # 100格内
                nearby_places.append({
                    "name": f"🏪 {market.name}",
                    "coord": f"({market.x},{market.y})",
                    "distance": distance,
                    "type": "市集"
                })
        
        # 2. 检查缉邪司总部
        from ..economy.merchants import HEADQUARTERS_COORD
        hq_distance = calculate_distance(current_x, current_y, HEADQUARTERS_COORD[0], HEADQUARTERS_COORD[1])
        if hq_distance <= 100:
            nearby_places.append({
                "name": "🏛️ 缉邪司总部",
                "coord": f"{HEADQUARTERS_COORD}",
                "distance": hq_distance,
                "type": "特殊商店"
            })
        
        # 3. 检查打工地点
        try:
            stmt = select(JobLocation).where(JobLocation.is_active == True)
            job_locations = (await session.execute(stmt)).scalars().all()
            
            for location in job_locations:
                distance = calculate_distance(current_x, current_y, location.x, location.y)
                if distance <= 100:
                    nearby_places.append({
                        "name": f"💼 {location.name}",
                        "coord": f"({location.x},{location.y})",
                        "distance": distance,
                        "type": "打工地点"
                    })
        except Exception:
            # 如果查询失败，使用默认配置
            try:
                from ..economy.part_time_job_service import PartTimeJobService
                for location_data in PartTimeJobService.JOB_LOCATIONS.values():
                    distance = calculate_distance(current_x, current_y, location_data['x'], location_data['y'])
                    if distance <= 100:
                        nearby_places.append({
                            "name": f"💼 {location_data['name']}",
                            "coord": f"({location_data['x']},{location_data['y']})",
                            "distance": distance,
                            "type": "打工地点"
                        })
            except ImportError:
                # 如果导入失败，跳过打工地点
                pass
        
        if not nearby_places:
            await nearby_locations_cmd.finish(message_add_head(
                f"📍 当前位置：({current_x},{current_y})\n"
                "🔍 附近100格内暂无重要地点\n"
                "💡 使用【地图】查看所有地点", event))
        
        # 按距离排序
        nearby_places.sort(key=lambda x: x["distance"])
        
        lines = [
            f"📍 当前位置：({current_x},{current_y})",
            "🔍 附近地点 (100格内)：",
            "━━━━━━━━━━━━━"
        ]
        
        for place in nearby_places[:10]:  # 最多显示10个
            lines.append(f"{place['name']} {place['coord']} - 距离{place['distance']}格")
        
        lines.extend([
            "━━━━━━━━━━━━━",
            "💡 使用【导航 x y】前往指定坐标"
        ])
        
        await nearby_locations_cmd.finish(message_add_head("\n".join(lines), event))


@visual_map_cmd.handle()
async def _(event: MessageEvent):
    """生成可视化地图"""
    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await visual_map_cmd.finish("⛔ 请先创建角色")

        try:
            # 导入地图可视化器
            from .map_visualizer import MapVisualizer
            from ..economy.merchants import MARKETS, HEADQUARTERS_COORD
            import base64

            # 生成地图
            visualizer = MapVisualizer()
            map_image_bytes = await visualizer.generate_map(session, player.id)

            # 将图片转换为base64编码
            base64_img = base64.b64encode(map_image_bytes).decode("utf-8")

            # 创建详细的坐标信息
            coord_info = []
            coord_info.append("📍 地点坐标详情：")
            coord_info.append("━━━━━━━━━━━━━")

            # 市集坐标
            coord_info.append("🟠 市集地点：")
            for market in MARKETS:
                coord_info.append(f"   • {market.name} ({market.x},{market.y})")

            # 缉邪司总部
            hq_x, hq_y = HEADQUARTERS_COORD
            coord_info.append("🟡 特殊地点：")
            coord_info.append(f"   • 缉邪司总部 ({hq_x},{hq_y})")

            # 打工地点
            try:
                from ..economy.part_time_job_service import PartTimeJobService
                coord_info.append("🟣 打工地点：")
                for location_data in PartTimeJobService.JOB_LOCATIONS.values():
                    coord_info.append(f"   • {location_data['name']} ({location_data['x']},{location_data['y']})")
            except ImportError:
                coord_info.append("🟣 打工地点：")
                coord_info.append("   • 上京商业中心 (0,0)")
                coord_info.append("   • 荔湾镇工业区 (120,200)")
                coord_info.append("   • 郸城娱乐街区 (120,120)")
                coord_info.append("   • 东郊物流中心 (390,50)")

            # 当前玩家位置 - 使用正确的当前坐标
            current_x, current_y = player.get_current_coordinates()
            coord_info.append("🔴 你的位置：")
            coord_info.append(f"   • {player.nickname} ({current_x},{current_y})")

            coord_info.append("━━━━━━━━━━━━━")
            coord_info.append("💡 使用【导航 x y】可前往指定坐标")

            # 创建图片消息
            img = MessageSegment.file_image(base64_img)
            text_msg = message_add_head("🗺️ 大都会地图全览\n" + "\n".join(coord_info), event)
            msg = Message(text_msg).append(img)

            await visual_map_cmd.finish(msg)

        except ImportError as e:
            await visual_map_cmd.finish(message_add_head(
                "❌ 地图可视化功能不可用\n"
                "━━━━━━━━━━━━━\n"
                "缺少必要的图像处理库 PIL\n"
                "请管理员安装：pip install Pillow\n"
                "━━━━━━━━━━━━━\n"
                "💡 可使用【地图】查看文字版地图", event))
        except ValueError as e:
            await visual_map_cmd.finish(message_add_head(
                f"❌ 生成地图失败：{str(e)}\n"
                "━━━━━━━━━━━━━\n"
                "💡 可使用【地图】查看文字版地图", event))
