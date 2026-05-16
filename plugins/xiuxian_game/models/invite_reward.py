from sqlalchemy import Integer, String, DateTime, Boolean, func, text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .db import Base


class InviteReward(Base):
    """邀请奖励记录表"""
    __tablename__ = "invite_reward"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    server_id: Mapped[int] = mapped_column(Integer, default=1, index=True, comment="所属区服ID")
    invitee_uid: Mapped[int] = mapped_column(Integer, index=True, comment="被邀请者UID")
    inviter_uid: Mapped[int] = mapped_column(Integer, index=True, comment="邀请者UID")
    
    # 奖励发放状态
    level_1_rewarded: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('0'), comment="1级奖励是否已发放")
    level_10_rewarded: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('0'), comment="10级奖励是否已发放")
    level_50_rewarded: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('0'), comment="50级奖励是否已发放")
    
    # 奖励发放时间
    level_1_rewarded_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="1级奖励发放时间")
    level_10_rewarded_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="10级奖励发放时间")
    level_50_rewarded_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="50级奖励发放时间")
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
