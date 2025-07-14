from sqlalchemy import String, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from enum import Enum as PyEnum
from .db import Base


class ApplicationType(str, PyEnum):
    """申请类型"""
    MARRIAGE = "marriage"  # 求婚申请
    MENTORSHIP = "mentorship"  # 拜师申请


class ApplicationStatus(str, PyEnum):
    """申请状态"""
    PENDING = "pending"  # 待处理
    APPROVED = "approved"  # 已同意
    REJECTED = "rejected"  # 已拒绝


class SocialApplication(Base):
    """社交申请记录表（求婚、拜师等）"""
    __tablename__ = "social_application"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    applicant_id: Mapped[str] = mapped_column(String(32), index=True, comment="申请人 ID")
    target_id: Mapped[str] = mapped_column(String(32), index=True, comment="目标玩家 ID")
    application_type: Mapped[ApplicationType] = mapped_column(String(16), index=True, comment="申请类型")
    status: Mapped[ApplicationStatus] = mapped_column(String(16), default=ApplicationStatus.PENDING, server_default='pending', comment="申请状态")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), comment="申请时间")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="处理时间")
    
    def is_pending(self) -> bool:
        """检查是否为待处理状态"""
        return self.status == ApplicationStatus.PENDING
