from sqlalchemy import Integer, String, DateTime, Boolean, BigInteger, func, JSON
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timedelta
from typing import Dict, Any
from .db import Base
from sqlalchemy.ext.mutable import MutableDict


class PartTimeJob(Base):
    """打工记录表"""
    __tablename__ = "part_time_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True, comment="玩家ID")
    job_location_id: Mapped[str] = mapped_column(String(32), index=True, comment="工作地点ID")
    job_type: Mapped[str] = mapped_column(String(32), comment="工作类型")

    # 工作状态
    is_working: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否正在工作")
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="开始工作时间")
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="预计结束时间")
    completed_time: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="实际完成时间")

    # 奖励信息
    base_reward: Mapped[int] = mapped_column(Integer, default=0, comment="基础奖励金币")
    bonus_reward: Mapped[int] = mapped_column(Integer, default=0, comment="额外奖励金币")
    total_reward: Mapped[int] = mapped_column(Integer, default=0, comment="总奖励金币")

    # 工作详情
    work_duration_hours: Mapped[int] = mapped_column(Integer, default=2, comment="工作时长(小时)")
    consecutive_days: Mapped[int] = mapped_column(Integer, default=1, comment="连续工作天数")
    special_event: Mapped[str] = mapped_column(String(100), nullable=True, comment="特殊事件描述")

    # 额外数据
    extra_data: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        comment="额外数据JSON"
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    def is_completed(self) -> bool:
        """检查工作是否已完成"""
        if not self.is_working or not self.end_time:
            return False
        return datetime.now() >= self.end_time

    def get_remaining_time(self) -> timedelta:
        """获取剩余工作时间"""
        if not self.is_working or not self.end_time:
            return timedelta(0)
        remaining = self.end_time - datetime.now()
        return remaining if remaining.total_seconds() > 0 else timedelta(0)

    def calculate_total_reward(self) -> int:
        """计算总奖励"""
        return self.base_reward + self.bonus_reward


class JobLocation(Base):
    """工作地点配置表"""
    __tablename__ = "job_location"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="地点ID")
    name: Mapped[str] = mapped_column(String(50), comment="地点名称")
    description: Mapped[str] = mapped_column(String(200), comment="地点描述")

    # 坐标信息
    x: Mapped[int] = mapped_column(Integer, comment="X坐标")
    y: Mapped[int] = mapped_column(Integer, comment="Y坐标")
    region: Mapped[str] = mapped_column(String(32), default="大都会", comment="所属区域")

    # 工作配置
    available_jobs: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        comment="可用工作类型配置JSON"
    )

    # 地点状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否激活")
    required_level: Mapped[int] = mapped_column(Integer, default=1, comment="所需最低等级")
    max_workers: Mapped[int] = mapped_column(Integer, default=10, comment="最大同时工作人数")

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")


class PlayerJobStats(Base):
    """玩家打工统计表"""
    __tablename__ = "player_job_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="玩家ID")

    # 统计数据
    total_jobs_completed: Mapped[int] = mapped_column(Integer, default=0, comment="完成工作总数")
    total_earnings: Mapped[int] = mapped_column(BigInteger, default=0, comment="总收入")
    total_work_hours: Mapped[int] = mapped_column(Integer, default=0, comment="总工作小时数")

    # 连续记录
    current_streak: Mapped[int] = mapped_column(Integer, default=0, comment="当前连续工作天数")
    max_streak: Mapped[int] = mapped_column(Integer, default=0, comment="最大连续工作天数")
    last_work_date: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="最后工作日期")

    # 偏好统计
    favorite_job_type: Mapped[str] = mapped_column(String(32), nullable=True, comment="最喜欢的工作类型")
    favorite_location: Mapped[str] = mapped_column(String(32), nullable=True, comment="最喜欢的工作地点")

    # 成就数据
    achievements: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        comment="成就数据JSON"
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    def update_streak(self, work_date: datetime) -> None:
        """更新连续工作天数"""
        if not self.last_work_date:
            self.current_streak = 1
        else:
            # 检查是否是连续的天数
            days_diff = (work_date.date() - self.last_work_date.date()).days
            if days_diff == 1:
                self.current_streak += 1
            elif days_diff == 0:
                # 同一天，不更新连续天数
                pass
            else:
                # 中断了，重新开始
                self.current_streak = 1

        # 更新最大连续天数
        if self.current_streak > self.max_streak:
            self.max_streak = self.current_streak

        self.last_work_date = work_date