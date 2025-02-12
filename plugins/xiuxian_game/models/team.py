from sqlalchemy import String, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from ..data.db import Base
from enum import Enum as PyEnum
from typing import List
from sqlalchemy import func
from ..models.player import Player

class TeamStatus(str, PyEnum):
    FORMING = "组队中"
    READY = "已就绪"
    IN_BATTLE = "战斗中"

class Team(Base):
    __tablename__ = "teams"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    leader_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True, unique=True)
    status: Mapped[TeamStatus] = mapped_column(String(16), default=TeamStatus.FORMING)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    leader: Mapped["Player"] = relationship("Player", foreign_keys=[leader_id])
    members: Mapped[List["TeamMember"]] = relationship("TeamMember", back_populates="team")

class TeamMember(Base):
    __tablename__ = "team_members"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id"), index=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    team: Mapped["Team"] = relationship("Team", back_populates="members")
    player: Mapped["Player"] = relationship("Player") 