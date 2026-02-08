"""
厨师系统数据模型

包含:
- Chef: 厨师实体
- ChefCandidate: 厨师候选(招募系统临时数据)
- ChefTier: 厨师等级枚举
- CookingCategory: 烹饪类别枚举
"""
from sqlalchemy import String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from enum import Enum as PyEnum
from .db import Base


class ChefTier(str, PyEnum):
    """厨师等级枚举"""
    APPRENTICE = "apprentice"      # 学徒厨师
    HELPER = "helper"              # 帮厨
    COOK = "cook"                  # 厨师
    HEAD_CHEF = "head_chef"        # 大厨
    MASTER_CHEF = "master_chef"    # 特级厨师


class CookingCategory(str, PyEnum):
    """烹饪类别枚举"""
    FISH = "fish"          # 鱼鲜类
    SOUP = "soup"          # 汤煲类
    GRILL = "grill"        # 烤制类
    STEAM = "steam"        # 蒸煮类
    DESSERT = "dessert"    # 甜点类


class ChefPersonality(str, PyEnum):
    """厨师性格枚举"""
    DILIGENT = "diligent"          # 勤劳
    LAZY = "lazy"                  # 懒散
    PERFECTIONIST = "perfectionist"  # 完美主义
    FRUGAL = "frugal"              # 节俭
    TALKATIVE = "talkative"        # 话痨


class Chef(Base):
    """厨师模型

    雇佣的厨师NPC
    """
    __tablename__ = "chef"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    restaurant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("restaurant.id", ondelete="CASCADE"),
        index=True,
        comment="所属餐厅ID"
    )
    name: Mapped[str] = mapped_column(String(32), comment="厨师名字")
    tier: Mapped[str] = mapped_column(
        String(20),
        comment="等级: apprentice/helper/cook/head_chef/master_chef"
    )
    skill: Mapped[int] = mapped_column(Integer, comment="厨艺值(影响成功率)")
    speed: Mapped[int] = mapped_column(Integer, comment="速度(菜/时)")
    specialty: Mapped[str] = mapped_column(
        String(20),
        comment="擅长类别: fish/soup/grill/steam/dessert"
    )
    personality: Mapped[str] = mapped_column(
        String(20),
        comment="性格: diligent/lazy/perfectionist/frugal/talkative"
    )
    salary: Mapped[int] = mapped_column(Integer, comment="时薪(金币)")
    hired_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        server_default="2025-02-08 00:00:00",
        comment="雇佣时间"
    )


class ChefCandidate(Base):
    """厨师候选模型

    招募系统生成的临时候选
    """
    __tablename__ = "chef_candidate"

    __table_args__ = (
        Index("ix_chef_candidate_player_created", "player_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("player.id", ondelete="CASCADE"),
        index=True,
        comment="招募发起人"
    )
    name: Mapped[str] = mapped_column(String(32), comment="厨师名字")
    tier: Mapped[str] = mapped_column(String(20), comment="等级")
    skill: Mapped[int] = mapped_column(Integer, comment="厨艺值")
    speed: Mapped[int] = mapped_column(Integer, comment="速度")
    specialty: Mapped[str] = mapped_column(String(20), comment="擅长类别")
    personality: Mapped[str] = mapped_column(String(20), comment="性格")
    salary: Mapped[int] = mapped_column(Integer, comment="时薪")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        server_default="2025-02-08 00:00:00",
        comment="创建时间(过期后可清理)"
    )
