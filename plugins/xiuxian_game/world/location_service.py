"""
地点管理服务

提供统一的地点管理功能，包括地点查询、附近地点搜索、地点NPC管理等
"""

from typing import List, Dict, Optional, Tuple
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.location import Location
from ..models.npc import NPC, NPCType, NPCStatus
from ..models.player import Player


class LocationService:
    """地点管理服务类"""
    
    @staticmethod
    async def get_location_by_id(session: AsyncSession, location_id: str) -> Optional[Location]:
        """根据ID获取地点"""
        stmt = select(Location).where(Location.location_id == location_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_location_by_coordinates(session: AsyncSession, x: int, y: int, 
                                        region: str = "大都会") -> Optional[Location]:
        """根据坐标获取地点"""
        stmt = select(Location).where(
            and_(
                Location.x == x,
                Location.y == y,
                Location.region == region,
                Location.is_active == True
            )
        ).options(selectinload(Location.npcs))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_nearby_locations(session: AsyncSession, x: int, y: int, 
                                 region: str = "大都会", max_distance: int = 100) -> List[Location]:
        """获取附近的地点"""
        stmt = select(Location).where(
            and_(
                Location.region == region,
                Location.is_active == True,
                func.abs(Location.x - x) + func.abs(Location.y - y) <= max_distance
            )
        ).options(selectinload(Location.npcs))
        result = await session.execute(stmt)
        locations = result.scalars().all()
        
        # 按距离排序
        locations.sort(key=lambda loc: abs(loc.x - x) + abs(loc.y - y))
        return locations
    
    @staticmethod
    async def get_locations_by_type(session: AsyncSession, location_type: str, 
                                  region: str = "大都会") -> List[Location]:
        """根据类型获取地点"""
        stmt = select(Location).where(
            and_(
                Location.location_type == location_type,
                Location.region == region,
                Location.is_active == True
            )
        ).options(selectinload(Location.npcs))
        result = await session.execute(stmt)
        return result.scalars().all()
    
    @staticmethod
    async def get_locations_with_function(session: AsyncSession, function_name: str,
                                        region: str = "大都会") -> List[Location]:
        """获取具有指定功能的地点"""
        stmt = select(Location).where(
            and_(
                Location.region == region,
                Location.is_active == True
            )
        ).options(selectinload(Location.npcs))
        result = await session.execute(stmt)
        locations = result.scalars().all()
        
        # 过滤具有指定功能的地点
        return [loc for loc in locations if loc.has_function(function_name)]
    
    @staticmethod
    async def create_location(session: AsyncSession, location_id: str, name: str,
                            x: int, y: int, location_type: str = "normal",
                            description: str = None, region: str = "大都会") -> Location:
        """创建新地点"""
        location = Location(
            location_id=location_id,
            name=name,
            description=description or f"{name}，一个普通的地点",
            x=x,
            y=y,
            region=region,
            location_type=location_type
        )
        
        session.add(location)
        await session.flush()  # 获取ID
        return location
    
    @staticmethod
    async def update_location(session: AsyncSession, location_id: str, 
                            **kwargs) -> Optional[Location]:
        """更新地点信息"""
        location = await LocationService.get_location_by_id(session, location_id)
        if not location:
            return None
        
        for key, value in kwargs.items():
            if hasattr(location, key):
                setattr(location, key, value)
        
        return location
    
    @staticmethod
    async def delete_location(session: AsyncSession, location_id: str) -> bool:
        """删除地点（软删除）"""
        location = await LocationService.get_location_by_id(session, location_id)
        if not location:
            return False
        
        location.is_active = False
        return True
    
    @staticmethod
    async def get_location_summary(session: AsyncSession, location: Location) -> Dict:
        """获取地点摘要信息"""
        # 获取地点的NPC信息
        active_npcs = location.get_active_npcs()
        
        # 按类型分组NPC
        npcs_by_type = {}
        for npc in active_npcs:
            npc_type = npc.npc_type.value
            if npc_type not in npcs_by_type:
                npcs_by_type[npc_type] = []
            npcs_by_type[npc_type].append(npc)
        
        # 获取地点功能
        functions = []
        if location.functions:
            functions = [func_name for func_name, config in location.functions.items()
                        if config.get("enabled", False)]
        
        return {
            "location": location,
            "npcs_by_type": npcs_by_type,
            "total_npcs": len(active_npcs),
            "functions": functions,
            "has_market": location.has_function("market"),
            "has_job": location.has_function("part_time_job"),
            "has_forge": location.has_function("forge"),
            "has_special_shop": location.has_function("special_shop")
        }
    
    @staticmethod
    async def get_nearby_players(session: AsyncSession, x: int, y: int, 
                               region: str = "大都会", max_distance: int = 100,
                               exclude_player_id: str = None) -> List[Player]:
        """获取附近的玩家"""
        conditions = [
            Player.region == region,
            func.abs(Player.x - x) + func.abs(Player.y - y) <= max_distance
        ]
        
        if exclude_player_id:
            conditions.append(Player.id != exclude_player_id)
        
        stmt = select(Player).where(and_(*conditions))
        result = await session.execute(stmt)
        players = result.scalars().all()
        
        # 按距离排序
        players.sort(key=lambda p: abs(p.x - x) + abs(p.y - y))
        return players
    
    @staticmethod
    def format_location_info(location_summary: Dict, player_x: int, player_y: int,
                           nearby_players: List[Player] = None) -> str:
        """格式化地点信息显示"""
        location = location_summary["location"]
        npcs_by_type = location_summary["npcs_by_type"]
        
        lines = [
            f"所在地 ※ {location.name}({location.x},{location.y})",
            location.description,
            ""
        ]
        
        # 显示附近玩家
        if nearby_players:
            player_count = len(nearby_players)
            if player_count > 0:
                # 显示前20个玩家
                display_players = nearby_players[:20]
                player_names = []
                for p in display_players:
                    distance = abs(p.x - player_x) + abs(p.y - player_y)
                    player_names.append(f"{p.nickname}[{p.uid}]")
                
                lines.append(f"⛹️附近玩家({player_count}): {' '.join(player_names)}")
                if player_count > 20:
                    lines.append(f"...等{player_count}个玩家")
                lines.append("⬇️ 攻击 <玩家|NPC>")
                lines.append("")
        
        # 显示NPC
        total_npcs = location_summary["total_npcs"]
        if total_npcs > 0:
            lines.append(f"🤖NPC({total_npcs}): ")
            
            # 按类型显示NPC
            for npc_type, npcs in npcs_by_type.items():
                for npc in npcs:
                    hint = npc.get_interaction_hint()
                    lines.append(f"{npc.get_display_name()}{hint}")
            
            lines.append("⬇️ 交互 <NPC>")
            lines.append("")
        
        # 显示地点功能
        functions = location_summary["functions"]
        if "part_time_job" in functions:
            lines.append(f"💼工作地点: {location.name}")
        
        if "market" in functions:
            lines.append(f"🏬 市集：{location.name}")
        
        if "forge" in functions:
            lines.append(f"⚒️ 工坊：{location.name}")
        
        if "special_shop" in functions:
            lines.append(f"🏛️ 特殊商店：{location.name}")
        
        return "\n".join(lines)
    
    @staticmethod
    async def migrate_from_job_locations(session: AsyncSession) -> int:
        """从JobLocation表迁移数据到Location表"""
        from ..models.part_time_job import JobLocation
        
        # 获取所有JobLocation
        stmt = select(JobLocation).where(JobLocation.is_active == True)
        result = await session.execute(stmt)
        job_locations = result.scalars().all()
        
        migrated_count = 0
        
        for job_loc in job_locations:
            # 检查是否已存在
            existing = await LocationService.get_location_by_coordinates(
                session, job_loc.x, job_loc.y, job_loc.region
            )
            
            if existing:
                # 更新现有地点，添加打工功能
                if not existing.has_function("part_time_job"):
                    job_config = {
                        "enabled": True,
                        "available_jobs": job_loc.available_jobs,
                        "max_workers": job_loc.max_workers,
                        "required_level": job_loc.required_level
                    }
                    existing.add_function("part_time_job", job_config)
                    migrated_count += 1
            else:
                # 创建新地点
                location = Location.create_job_location(
                    location_id=job_loc.location_id,
                    name=job_loc.name,
                    x=job_loc.x,
                    y=job_loc.y,
                    description=job_loc.description,
                    available_jobs=job_loc.available_jobs
                )
                location.required_level = job_loc.required_level
                location.config["max_workers"] = job_loc.max_workers
                
                session.add(location)
                migrated_count += 1
        
        return migrated_count
