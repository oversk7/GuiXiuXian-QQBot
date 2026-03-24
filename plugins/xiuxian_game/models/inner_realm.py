from sqlalchemy import Integer, String, DateTime, Text, func, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from .db import Base
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .player import Player


class InnerRealmSession(Base):
    """
    里界探索会话表

    设计要点:
    - 每个玩家每个里界有一个独立实例
    - 记录探索进度和统计信息
    - 每日0点重置里界状态（居民复活、物品刷新）
    - 支持多结局结算
    """
    __tablename__ = "inner_realm_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 玩家信息
    player_id: Mapped[str] = mapped_column(
        String(32),
        index=True,
        comment="玩家ID"
    )

    # 里界信息
    realm_name: Mapped[str] = mapped_column(
        String(64),
        index=True,
        comment="里界名称（如：third_ward）"
    )

    # 时间信息
    entered_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        comment="进入时间"
    )
    last_refresh: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        comment="上次刷新时间（每日0点）"
    )

    # 统计信息
    killed_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default='0',
        comment="击杀数量"
    )
    saved_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default='0',
        comment="救出幸存者数量"
    )

    # 理智系统
    sanity: Mapped[int] = mapped_column(
        Integer,
        default=100,
        server_default='100',
        comment="当前理智值（0-100）"
    )

    # 收集线索（JSON数组）
    clue_collected: Mapped[str] = mapped_column(
        Text,
        default='[]',
        comment="已收集的线索ID列表（JSON数组）"
    )

    # 当前位置
    x: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default='0',
        comment="当前X坐标"
    )
    y: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default='0',
        comment="当前Y坐标"
    )

    # 探索状态（JSON对象）
    state: Mapped[str] = mapped_column(
        Text,
        default='{}',
        comment="探索状态（JSON对象，存储自定义数据）"
    )

    # 是否已结算
    is_settled: Mapped[bool] = mapped_column(
        Integer,  # SQLite使用Integer存储布尔值
        default=0,
        server_default='0',
        comment="是否已结算（0=未结算，1=已结算）"
    )

    # 场景节点系统字段
    current_scene: Mapped[str] = mapped_column(
        String(50), nullable=True, comment="当前场景节点ID"
    )
    visited_scenes: Mapped[str] = mapped_column(
        Text, default='[]', comment="已访问场景列表(JSON)"
    )
    inventory: Mapped[str] = mapped_column(
        Text, default='{}', comment="里界内道具(JSON)"
    )
    is_first_clear: Mapped[bool] = mapped_column(
        Integer, default=0, server_default='0', comment="是否首次通关(0/1)"
    )
    move_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default='0', comment="移动次数"
    )

    # 关联地块
    tiles: Mapped[list["InnerRealmTile"]] = relationship(
        "InnerRealmTile",
        back_populates="session",
        cascade="all, delete-orphan"
    )

    # 表约束
    __table_args__ = (
        # 确保同一玩家同一里界只有一个活跃会话
        Index('idx_player_realm_unique', 'player_id', 'realm_name', unique=True),
    )


class InnerRealmTile(Base):
    """
    里界地块表

    设计要点:
    - 每个会话有625个地块（25x25）
    - 记录每个地块的事件类型和状态
    - 支持事件触发后的状态变化
    """
    __tablename__ = "inner_realm_tile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 关联会话
    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("inner_realm_session.id", ondelete="CASCADE"),
        index=True,
        comment="关联的会话ID"
    )

    # 坐标
    x: Mapped[int] = mapped_column(
        Integer,
        index=True,
        comment="X坐标"
    )
    y: Mapped[int] = mapped_column(
        Integer,
        index=True,
        comment="Y坐标"
    )

    # 事件类型
    event_type: Mapped[str] = mapped_column(
        String(32),
        default='EMPTY',
        server_default='EMPTY',
        comment="事件类型（NPC/LOOT/CLUE/EMPTY/BOSS）"
    )

    # 地块状态（JSON对象）
    state: Mapped[str] = mapped_column(
        Text,
        default='{}',
        comment="地块状态（JSON对象，如NPC血量、是否已搜刮等）"
    )

    # 是否已触发
    is_triggered: Mapped[bool] = mapped_column(
        Integer,  # SQLite使用Integer存储布尔值
        default=0,
        server_default='0',
        comment="是否已触发（0=未触发，1=已触发）"
    )

    # 刷新时间
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        comment="上次刷新时间"
    )

    # 关联会话
    session: Mapped["InnerRealmSession"] = relationship(
        "InnerRealmSession",
        back_populates="tiles"
    )

    # 表约束
    __table_args__ = (
        # 确保同一会话中每个坐标只有一个地块
        Index('idx_session_position_unique', 'session_id', 'x', 'y', unique=True),
    )
