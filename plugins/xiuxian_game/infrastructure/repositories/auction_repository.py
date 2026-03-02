"""
拍卖行仓储

提供 AuctionItem 实体的数据访问层，支持：
1. 按ID查询
2. 查询活跃拍卖列表
3. 查询需要结算的已过期拍卖
4. 查询即将结束（30分钟内）未提醒的拍卖
5. 查询玩家自己发起的拍卖
"""

from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.auction import AuctionItem, AuctionBidHistory


class AuctionRepository(IRepository[AuctionItem]):
    """拍卖行仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    # ==================== 标准CRUD ====================

    async def get_by_id(self, auction_id: int) -> Optional[AuctionItem]:
        """按主键查询拍卖条目"""
        return await self._session.get(AuctionItem, auction_id)

    async def add(self, entity: AuctionItem) -> AuctionItem:
        """创建拍卖条目"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: AuctionItem) -> AuctionItem:
        """更新拍卖条目"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity_id: int) -> bool:
        """删除拍卖条目"""
        entity = await self.get_by_id(entity_id)
        if entity:
            await self._session.delete(entity)
            await self._session.flush()
            return True
        return False

    async def exists(self, entity_id: int) -> bool:
        entity = await self.get_by_id(entity_id)
        return entity is not None

    async def count(self) -> int:
        stmt = select(AuctionItem)
        result = await self._session.execute(stmt)
        return len(result.scalars().all())

    # ==================== 业务查询 ====================

    async def find_active_auctions(self, page: int = 1, page_size: int = 10) -> List[AuctionItem]:
        """分页查询当前进行中的拍卖（按结束时间升序，最快结束的在最前）"""
        offset = (page - 1) * page_size
        stmt = (
            select(AuctionItem)
            .where(AuctionItem.status == "active")
            .order_by(AuctionItem.end_at.asc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def count_active_auctions(self) -> int:
        """统计当前进行中的拍卖总数"""
        stmt = select(AuctionItem).where(AuctionItem.status == "active")
        result = await self._session.execute(stmt)
        return len(result.scalars().all())

    async def find_seller_active_auctions(self, seller_id: str) -> List[AuctionItem]:
        """查询卖家当前活跃的拍卖条目"""
        stmt = (
            select(AuctionItem)
            .where(
                and_(
                    AuctionItem.seller_id == seller_id,
                    AuctionItem.status == "active",
                )
            )
            .order_by(AuctionItem.end_at.asc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def find_seller_all_auctions(self, seller_id: str) -> List[AuctionItem]:
        """查询卖家所有拍卖条目（含历史）"""
        stmt = (
            select(AuctionItem)
            .where(AuctionItem.seller_id == seller_id)
            .order_by(AuctionItem.start_at.desc())
            .limit(20)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def find_expired_unsettled(self) -> List[AuctionItem]:
        """查询所有已到期但状态仍为 active 的拍卖（需要结算）"""
        now = datetime.now()
        stmt = (
            select(AuctionItem)
            .where(
                and_(
                    AuctionItem.status == "active",
                    AuctionItem.end_at <= now,
                )
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def find_near_ending_unreminded(self) -> List[AuctionItem]:
        """查询即将在30分钟内结束且尚未发送提醒的拍卖"""
        now = datetime.now()
        remind_threshold = now + timedelta(minutes=30)
        stmt = (
            select(AuctionItem)
            .where(
                and_(
                    AuctionItem.status == "active",
                    AuctionItem.end_at > now,
                    AuctionItem.end_at <= remind_threshold,
                    AuctionItem.reminded_30min == False,
                )
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def find_by_equipment_instance(self, instance_id: int) -> Optional[AuctionItem]:
        """查询装备实例是否正在拍卖中"""
        stmt = (
            select(AuctionItem)
            .where(
                and_(
                    AuctionItem.item_instance_id == instance_id,
                    AuctionItem.is_instance_trade == True,
                    AuctionItem.status == "active",
                )
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


class AuctionBidHistoryRepository:
    """竞价历史仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def add(self, entity: AuctionBidHistory) -> AuctionBidHistory:
        """记录一条竞价历史"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def find_by_auction(self, auction_id: int, limit: int = 10) -> List[AuctionBidHistory]:
        """按拍卖编号查询竞价历史（最新的在最前）"""
        stmt = (
            select(AuctionBidHistory)
            .where(AuctionBidHistory.auction_id == auction_id)
            .order_by(AuctionBidHistory.bid_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

