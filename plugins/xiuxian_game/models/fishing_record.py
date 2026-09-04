from sqlalchemy import String, Integer, DateTime, ForeignKey, BigInteger, Index, case
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime, timedelta
from typing import Optional
from .db import Base
from .player import Player


class FishingRecord(Base):
    """钓鱼记录模型
    
    记录玩家的钓鱼活动，包括钓鱼次数、获得的鱼类等信息
    """
    __tablename__ = "fishing_record"
    __table_args__ = (
        Index("ix_fishing_record_player_time", "player_id", "fishing_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True, comment="玩家ID")
    fish_id: Mapped[str] = mapped_column(String(32), index=True, comment="鱼类物品ID")
    quantity: Mapped[int] = mapped_column(Integer, default=1, comment="钓到的数量")
    fishing_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), comment="钓鱼时间")
    location_x: Mapped[int] = mapped_column(Integer, comment="钓鱼地点X坐标")
    location_y: Mapped[int] = mapped_column(Integer, comment="钓鱼地点Y坐标")
    dungeon_level: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="钓鱼时诡域层级(0=现实世界)")

    # 关联关系
    player: Mapped["Player"] = relationship("Player", backref="fishing_records")

    @classmethod
    async def record_fishing(cls, session, player_id: str, fish_id: str, quantity: int, x: int, y: int, dungeon_level: int = 0):
        """记录一次钓鱼活动"""
        record = cls(
            player_id=player_id,
            fish_id=fish_id,
            quantity=quantity,
            location_x=x,
            location_y=y,
            dungeon_level=dungeon_level
        )
        session.add(record)
        return record
    
    @classmethod
    async def get_player_fishing_stats(cls, session, player_id: str) -> dict:
        """获取玩家钓鱼统计信息"""
        from sqlalchemy import select, func as sql_func

        today_start = datetime.combine(datetime.now().date(), datetime.min.time())
        stmt = select(
            sql_func.count(cls.id),
            sql_func.coalesce(sql_func.sum(cls.quantity), 0),
            sql_func.coalesce(
                sql_func.sum(case((cls.fishing_time >= today_start, 1), else_=0)),
                0,
            ),
        ).where(cls.player_id == player_id)
        total_count, total_fish, today_count = (await session.execute(stmt)).one()

        return {
            "total_fishing_count": int(total_count),
            "today_fishing_count": int(today_count),
            "total_fish_caught": int(total_fish),
        }
    
    @classmethod
    async def get_recent_fishing_records(cls, session, player_id: str, limit: int = 10):
        """获取玩家最近的钓鱼记录"""
        from sqlalchemy import select, desc
        
        stmt = select(cls).where(cls.player_id == player_id).order_by(desc(cls.fishing_time)).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()
    
    @classmethod
    async def can_fishing(cls, session, player_id: str, cooldown_minutes: int = 5) -> bool:
        """检查玩家是否可以钓鱼（冷却时间检查）"""
        from sqlalchemy import select, desc
        
        # 获取最近一次钓鱼记录
        stmt = select(cls).where(cls.player_id == player_id).order_by(desc(cls.fishing_time)).limit(1)
        result = await session.execute(stmt)
        last_record = result.scalar_one_or_none()
        
        if not last_record:
            return True
        
        # 检查冷却时间
        cooldown_time = timedelta(minutes=cooldown_minutes)
        return datetime.now() - last_record.fishing_time >= cooldown_time
    
    @classmethod
    async def get_last_fishing_time(cls, session, player_id: str) -> Optional[datetime]:
        """获取玩家最后一次钓鱼时间"""
        from sqlalchemy import select, desc
        
        stmt = select(cls.fishing_time).where(cls.player_id == player_id).order_by(desc(cls.fishing_time)).limit(1)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


class FishingStats(Base):
    """钓鱼统计模型
    
    记录玩家的钓鱼统计数据，用于排行榜等功能
    """
    __tablename__ = "fishing_stats"
    
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), primary_key=True, comment="玩家ID")
    total_fishing_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="总钓鱼次数")
    total_fish_caught: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="总钓鱼数量")
    rare_fish_caught: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="稀有鱼类数量")
    legendary_fish_caught: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="传说鱼类数量")
    best_fish_value: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="最贵鱼类价值")
    total_fish_value: Mapped[BigInteger] = mapped_column(BigInteger, default=0, server_default="0", comment="总鱼类价值")
    max_fishing_dungeon_level: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="钓到鱼的最深诡域层级")
    last_updated: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), comment="最后更新时间")
    
    # 关联关系
    player: Mapped["Player"] = relationship("Player", backref="fishing_stats")
    
    @classmethod
    async def get_or_create(cls, session, player_id: str):
        """获取或创建钓鱼统计记录"""
        from sqlalchemy import select

        stmt = select(cls).where(cls.player_id == player_id)
        result = await session.execute(stmt)
        stats = result.scalar_one_or_none()

        if not stats:
            stats = cls(
                player_id=player_id,
                total_fishing_count=0,
                total_fish_caught=0,
                rare_fish_caught=0,
                legendary_fish_caught=0,
                best_fish_value=0,
                total_fish_value=0
            )
            session.add(stats)

        return stats
    
    async def update_stats(self, session, fish_value: int, fish_rarity: str, quantity: int = 1):
        """更新钓鱼统计数据"""
        self.total_fishing_count += 1
        self.total_fish_caught += quantity
        self.total_fish_value += fish_value * quantity
        
        if fish_value > self.best_fish_value:
            self.best_fish_value = fish_value
        
        # 根据稀有度更新计数
        if fish_rarity == "purple":  # 稀有
            self.rare_fish_caught += quantity
        elif fish_rarity == "orange":  # 传说
            self.legendary_fish_caught += quantity
        
        self.last_updated = datetime.now()
        session.add(self)
