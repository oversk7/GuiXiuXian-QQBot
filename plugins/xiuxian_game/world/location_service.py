"""
地点管理服务（DI架构）

提供统一的地点管理功能，包括地点查询、附近地点搜索、地点摘要与信息格式化等
"""

from typing import List, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.location import Location
from ..models.player import Player
from ..utils_markdown import cmd
from ..infrastructure.repositories.location_repository import LocationRepository


class LocationService:
    """
    地点管理服务类（DI版本）

    依赖注入:
        - LocationRepository: 地点数据访问

    职责:
        - 地点查询和管理
        - 地点摘要信息生成
        - 附近玩家查询
        - 地点信息格式化
        - 数据迁移
    """

    def __init__(self, location_repo: LocationRepository):
        """
        初始化地点服务

        Args:
            location_repo: 地点仓储实例（由UnitOfWork注入）
        """
        self._location_repo = location_repo

    # ==================== 查询方法 ====================

    async def get_location_by_id(self, location_id: str) -> Optional[Location]:
        """
        根据ID获取地点

        Args:
            location_id: 地点唯一标识

        Returns:
            Location对象，如果不存在则返回None
        """
        return await self._location_repo.find_by_id(location_id)

    async def get_location_by_coordinates(
        self,
        x: int,
        y: int,
        region: str = "大都会"
    ) -> Optional[Location]:
        """
        根据坐标获取地点（预加载NPC）

        Args:
            x: X坐标
            y: Y坐标
            region: 所属区域，默认"大都会"

        Returns:
            Location对象，如果不存在则返回None
        """
        return await self._location_repo.find_by_coordinates(x, y, region)

    async def get_nearby_locations(
        self,
        x: int,
        y: int,
        region: str = "大都会",
        max_distance: int = 100
    ) -> List[Location]:
        """
        获取附近的地点（SQL排序优化）

        优化说明:
            - 使用SQL ORDER BY替代Python排序
            - 减少数据传输和内存使用

        Args:
            x: 中心X坐标
            y: 中心Y坐标
            region: 所属区域，默认"大都会"
            max_distance: 最大曼哈顿距离，默认100

        Returns:
            地点列表，按距离升序排序
        """
        return await self._location_repo.find_nearby(x, y, region, max_distance)

    async def get_locations_by_type(
        self,
        location_type: str,
        region: str = "大都会"
    ) -> List[Location]:
        """
        根据类型获取地点

        Args:
            location_type: 地点类型
            region: 所属区域，默认"大都会"

        Returns:
            地点列表
        """
        return await self._location_repo.find_by_type(location_type, region)

    async def get_locations_with_function(
        self,
        function_name: str,
        region: str = "大都会"
    ) -> List[Location]:
        """
        获取具有指定功能的地点（JSON查询优化）

        优化说明:
            - 使用MySQL json_extract直接在数据库过滤
            - 避免全表扫描 + Python过滤

        Args:
            function_name: 功能名称（如"market", "forge"等）
            region: 所属区域，默认"大都会"

        Returns:
            地点列表
        """
        return await self._location_repo.find_with_function(function_name, region)

    async def get_nearby_players(
        self,
        x: int,
        y: int,
        region: str = "大都会",
        max_distance: int = 100,
        exclude_player_id: str = None,
        server_id: int = 1
    ) -> List[Player]:
        """
        获取附近的玩家（SQL排序优化）

        Args:
            x: 中心X坐标
            y: 中心Y坐标
            region: 所属区域，默认"大都会"
            max_distance: 最大曼哈顿距离，默认100
            exclude_player_id: 排除的玩家ID（通常是当前玩家）
            server_id: 分服ID（多服分片隔离）

        Returns:
            玩家列表，按距离升序排序
        """
        return await self._location_repo.find_nearby_players(
            x, y, region, max_distance, exclude_player_id, server_id
        )

    async def search_locations_by_name(
        self,
        name_keyword: str,
        region: str = None,
        limit: int = 10
    ) -> List[Location]:
        """
        模糊搜索地点名称

        Args:
            name_keyword: 地点名称关键词
            region: 可选，限定区域
            limit: 返回结果数量上限，默认10

        Returns:
            地点列表
        """
        return await self._location_repo.find_by_name_like(
            name_keyword, region, limit
        )

    # ==================== 写入方法 ====================

    async def create_location(
        self,
        location_id: str,
        name: str,
        x: int,
        y: int,
        location_type: str = "normal",
        description: str = None,
        region: str = "大都会"
    ) -> Location:
        """
        创建新地点

        Args:
            location_id: 地点唯一标识
            name: 地点名称
            x: X坐标
            y: Y坐标
            location_type: 地点类型，默认"normal"
            description: 地点描述
            region: 所属区域，默认"大都会"

        Returns:
            创建的Location对象
        """
        location = Location(
            location_id=location_id,
            name=name,
            description=description or f"{name}，一个普通的地点",
            x=x,
            y=y,
            region=region,
            location_type=location_type
        )

        return await self._location_repo.add(location)

    async def update_location(
        self,
        location_id: str,
        **kwargs
    ) -> Optional[Location]:
        """
        更新地点信息

        Args:
            location_id: 地点唯一标识
            **kwargs: 要更新的字段

        Returns:
            更新后的Location对象，如果不存在则返回None
        """
        location = await self.get_location_by_id(location_id)
        if not location:
            return None

        for key, value in kwargs.items():
            if hasattr(location, key):
                setattr(location, key, value)

        return await self._location_repo.update(location)

    async def delete_location(self, location_id: str) -> bool:
        """
        删除地点（软删除）

        Args:
            location_id: 地点唯一标识

        Returns:
            是否删除成功
        """
        return await self._location_repo.delete(location_id)

    # ==================== 业务逻辑方法 ====================

    async def get_location_summary(self, location: Location) -> Dict:
        """
        获取地点摘要信息

        Args:
            location: Location对象

        Returns:
            地点摘要信息字典，包含:
                - location: Location对象
                - npcs_by_type: NPC按类型分组
                - total_npcs: NPC总数
                - functions: 地点功能列表
                - has_market: 是否有市集
                - has_job: 是否有打工点
                - has_forge: 是否有工坊
                - has_special_shop: 是否有特殊商店
        """
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

    async def migrate_from_job_locations(self, session: AsyncSession) -> int:
        """
        从JobLocation表迁移数据到Location表

        注意: 此方法是数据迁移方法，需要访问JobLocation模型，暂时保留session参数

        Args:
            session: 数据库会话（迁移时需要访问JobLocation表）

        Returns:
            迁移的地点数量
        """
        from sqlalchemy import select
        from ..models.part_time_job import JobLocation

        # 获取所有JobLocation
        stmt = select(JobLocation).where(JobLocation.is_active == True)
        result = await session.execute(stmt)
        job_locations = result.scalars().all()

        migrated_count = 0

        for job_loc in job_locations:
            # 检查是否已存在
            existing = await self.get_location_by_coordinates(
                job_loc.x, job_loc.y, job_loc.region
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

                await self._location_repo.add(location)
                migrated_count += 1

        return migrated_count

    # ==================== 纯计算方法 ====================

    @staticmethod
    def format_location_info(
        location_summary: Dict,
        player_x: int,
        player_y: int,
        nearby_players: List[Player] = None
    ) -> str:
        """
        格式化地点信息显示（纯计算函数，无DB访问）

        Args:
            location_summary: 地点摘要信息（由get_location_summary返回）
            player_x: 玩家X坐标
            player_y: 玩家Y坐标
            nearby_players: 附近玩家列表

        Returns:
            格式化后的地点信息字符串
        """
        location = location_summary["location"]
        npcs_by_type = location_summary["npcs_by_type"]

        coord_str = f"({location.x},{location.y})"
        name_display = location.name if coord_str in location.name else f"{location.name}{coord_str}"
        lines = [
            f"# 所在地 · {name_display}",
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
                    player_names.append(cmd(f'{p.nickname}[{p.uid}]', f'切磋 {p.uid}'))

                lines.append(f"附近玩家({player_count}): {' '.join(player_names)}")
                if player_count > 20:
                    lines.append(f"...等{player_count}个玩家")
                lines.append("")

        # 显示NPC
        total_npcs = location_summary["total_npcs"]
        if total_npcs > 0:
            lines.append(f"**NPC({total_npcs}):**")

            # 按类型显示NPC
            for npc_type, npcs in npcs_by_type.items():
                for npc in npcs:
                    if npc.is_dead() or npc.is_respawning():
                        # 死亡/复活中的NPC不做蓝字
                        hint = npc.get_interaction_hint()
                        lines.append(f"{npc.get_display_name()}{hint}")
                    elif npc_type == "ghost":
                        # 鬼怪NPC：点击直接死斗
                        hint = npc.get_interaction_hint()
                        lines.append(f"{cmd(npc.name, f'攻击 {npc.name}')}⚔️{hint}")
                    else:
                        hint = npc.get_interaction_hint()
                        lines.append(f"{cmd(npc.name, f'交互 {npc.name}')}{hint}")

            lines.append("")

        # 显示地点功能
        functions = location_summary["functions"]
        if "part_time_job" in functions:
            lines.append(f"💼工作地点: {cmd('打工')}")

        if "market" in functions:
            lines.append(f"🏬 市集: {cmd('市集')}")

        if "forge" in functions:
            lines.append(f"⚒️ 工坊: {cmd('锻造列表')}")

        if "special_shop" in functions:
            lines.append(f"🏛️ 特殊商店: {location.name}")

        return "\n".join(lines)
