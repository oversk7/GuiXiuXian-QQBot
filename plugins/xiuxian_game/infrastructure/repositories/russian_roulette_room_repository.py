"""
俄罗斯轮盘房间仓储

提供RussianRouletteRoom实体的数据访问层，支持：
1. 房间ID查询和复合条件查询
2. 玩家活跃房间查询
3. 群组活跃房间查询
4. 批量查询和状态管理
"""

from typing import Optional, List
from datetime import datetime
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.russian_roulette import RussianRouletteRoom, RoomStatus


class RussianRouletteRoomRepository(IRepository[RussianRouletteRoom]):
    """俄罗斯轮盘房间仓储"""

    def __init__(self, session: AsyncSession):
        """
        初始化房间仓储

        Args:
            session: 数据库会话
        """
        self._session = session

    # ==================== 基础查询 ====================

    async def find_by_id(self, id: int) -> Optional[RussianRouletteRoom]:
        """
        通过主键ID查询房间

        Args:
            id: 房间主键ID

        Returns:
            房间实体，不存在返回None
        """
        return await self._session.get(RussianRouletteRoom, id)

    async def get_by_id(self, entity_id: int) -> Optional[RussianRouletteRoom]:
        """get_by_id别名，调用find_by_id以符合IRepository接口"""
        return await self.find_by_id(entity_id)

    async def find_by_room_id(self, room_id: str) -> Optional[RussianRouletteRoom]:
        """
        通过房间ID查询房间

        Args:
            room_id: 房间ID（UUID的前8位）

        Returns:
            房间实体，不存在返回None
        """
        stmt = select(RussianRouletteRoom).where(
            RussianRouletteRoom.room_id == room_id
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    # ==================== 业务查询 ====================

    async def find_player_active_room(self, player_id: str) -> Optional[RussianRouletteRoom]:
        """
        查询玩家当前的活跃房间

        活跃房间定义：状态为WAITING、BETTING或PLAYING的房间

        Args:
            player_id: 玩家ID

        Returns:
            玩家的活跃房间，不存在返回None
        """
        stmt = select(RussianRouletteRoom).where(
            and_(
                or_(
                    RussianRouletteRoom.player1_id == player_id,
                    RussianRouletteRoom.player2_id == player_id
                ),
                RussianRouletteRoom.status.in_([
                    RoomStatus.WAITING.value,
                    RoomStatus.BETTING.value,
                    RoomStatus.PLAYING.value
                ])
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def find_group_active_room(self, group_id: str) -> Optional[RussianRouletteRoom]:
        """
        查询群组当前的活跃房间

        活跃房间定义：状态为WAITING、BETTING或PLAYING的房间

        Args:
            group_id: 群组ID

        Returns:
            群组的活跃房间，不存在返回None
        """
        stmt = select(RussianRouletteRoom).where(
            and_(
                RussianRouletteRoom.group_id == group_id,
                RussianRouletteRoom.status.in_([
                    RoomStatus.WAITING.value,
                    RoomStatus.BETTING.value,
                    RoomStatus.PLAYING.value
                ])
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    # ==================== 复合条件查询 ====================

    async def find_by_room_id_and_group(
        self,
        room_id: str,
        group_id: str,
        status: Optional[str] = None
    ) -> Optional[RussianRouletteRoom]:
        """
        通过房间ID和群组ID查询房间，可选状态过滤

        Args:
            room_id: 房间ID
            group_id: 群组ID
            status: 房间状态（可选），如RoomStatus.WAITING.value

        Returns:
            符合条件的房间，不存在返回None
        """
        conditions = [
            RussianRouletteRoom.room_id == room_id,
            RussianRouletteRoom.group_id == group_id
        ]

        if status is not None:
            conditions.append(RussianRouletteRoom.status == status)

        stmt = select(RussianRouletteRoom).where(and_(*conditions))
        result = await self._session.execute(stmt)
        return result.scalars().first()

    # ==================== 批量查询 ====================

    async def find_inactive_rooms(self, threshold: datetime) -> List[RussianRouletteRoom]:
        """
        查询超过指定时间的非活跃房间（用于清理）

        Args:
            threshold: 时间阈值（如：1小时前）

        Returns:
            非活跃房间列表
        """
        stmt = select(RussianRouletteRoom).where(
            and_(
                RussianRouletteRoom.updated_at < threshold,
                RussianRouletteRoom.status != RoomStatus.FINISHED.value
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    # ==================== 状态管理 ====================

    async def create(self, room: RussianRouletteRoom) -> RussianRouletteRoom:
        """
        创建新房间

        Args:
            room: 房间实体

        Returns:
            创建后的房间实体（包含生成的ID）
        """
        self._session.add(room)
        await self._session.flush()  # 刷新以获取生成的ID
        return room

    async def add(self, entity: RussianRouletteRoom) -> RussianRouletteRoom:
        """add别名，调用create以符合IRepository接口"""
        return await self.create(entity)

    async def update(self, room: RussianRouletteRoom) -> RussianRouletteRoom:
        """
        更新房间信息

        Args:
            room: 房间实体

        Returns:
            更新后的房间实体
        """
        self._session.add(room)
        await self._session.flush()
        return room

    async def delete(self, entity_id: int) -> bool:
        """
        删除房间

        Args:
            entity_id: 房间ID

        Returns:
            是否删除成功
        """
        entity = await self.get_by_id(entity_id)
        if entity:
            await self._session.delete(entity)
            await self._session.flush()
            return True
        return False

    async def exists(self, entity_id: int) -> bool:
        """
        检查房间是否存在

        Args:
            entity_id: 房间ID

        Returns:
            是否存在
        """
        entity = await self.get_by_id(entity_id)
        return entity is not None

    async def count(self) -> int:
        """
        获取房间总数

        Returns:
            房间数量
        """
        from sqlalchemy import func
        stmt = select(func.count()).select_from(RussianRouletteRoom)
        result = await self._session.execute(stmt)
        return result.scalar()
