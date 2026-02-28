"""
餐厅系统数据模型

包含:
- Restaurant: 餐厅实体
- RestaurantStorage: 餐厅食材仓库
- RestaurantMenu: 餐厅菜单
"""
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, JSON, BigInteger, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.mutable import MutableDict
from datetime import datetime
from enum import Enum as PyEnum
from .db import Base


class Restaurant(Base):
    """餐厅模型

    一个玩家只能拥有一家餐厅
    """
    __tablename__ = "restaurant"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("player.id"),
        unique=True,  # 每个玩家只能有一家餐厅
        index=True,
        comment="所属玩家ID"
    )
    level: Mapped[int] = mapped_column(Integer, default=1, server_default="1", comment="餐厅等级(1-10)")
    area: Mapped[int] = mapped_column(Integer, default=10, server_default="10", comment="面积/席位数")
    kitchen_level: Mapped[int] = mapped_column(Integer, default=1, server_default="1", comment="厨房等级(1-5)")
    reputation: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="声望(0-10000)")
    max_chefs: Mapped[int] = mapped_column(Integer, default=1, server_default="1", comment="厨师上限")
    storage_level: Mapped[int] = mapped_column(Integer, default=1, server_default="1", comment="仓库等级(1-5)")
    storage_capacity: Mapped[int] = mapped_column(Integer, default=50, server_default="50", comment="仓库容量")
    is_open: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", comment="是否营业中")
    total_income: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", comment="累计总收入")
    total_expense: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", comment="累计总支出")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        server_default="2025-02-08 00:00:00",
        comment="创建时间"
    )
    last_settlement: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        server_default="2025-02-08 00:00:00",
        comment="上次结算时间"
    )

    # 厨师招募冷却系统
    last_recruit_time: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
        comment="上次招募厨师时间"
    )
    daily_recruit_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        comment="当日招募次数(用于递增费用计算)"
    )
    last_recruit_date: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        comment="上次招募日期(YYYY-MM-DD格式,用于每日重置)"
    )


class RestaurantStorage(Base):
    """餐厅食材仓库

    存储餐厅的食材和调料
    """
    __tablename__ = "restaurant_storage"

    __table_args__ = (
        Index("ix_restaurant_storage_restaurant_item", "restaurant_id", "item_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    restaurant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("restaurant.id", ondelete="CASCADE"),
        index=True,
        comment="所属餐厅ID"
    )
    item_id: Mapped[str] = mapped_column(String(32), comment="食材物品ID(items.yaml)")
    quantity: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="数量")


class RestaurantMenu(Base):
    """餐厅菜单

    记录餐厅当前供应的菜品
    """
    __tablename__ = "restaurant_menu"

    __table_args__ = (
        Index("ix_restaurant_menu_restaurant_recipe", "restaurant_id", "recipe_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    restaurant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("restaurant.id", ondelete="CASCADE"),
        index=True,
        comment="所属餐厅ID"
    )
    recipe_id: Mapped[str] = mapped_column(String(32), comment="食谱ID(recipes.yaml)")
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="1",
        comment="是否在当前菜单上"
    )
