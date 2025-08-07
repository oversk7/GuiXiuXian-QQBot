"""
公会任务完成记录模型
"""
from sqlalchemy import String, Integer, Boolean, DateTime, Date, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime, date, timedelta
from enum import Enum
from .db import Base


class GuildTaskType(Enum):
    """公会任务类型枚举"""
    DAILY_SIGN = "daily_sign"              # 每日签到
    DAILY_DONATION = "daily_donation"      # 每日捐献
    EXPLORATION = "exploration"            # 世界探索
    COMBAT_VICTORY = "combat_victory"      # 战斗胜利
    WEEKLY_ACTIVE = "weekly_active"        # 周活跃成员
    WEEKLY_COMMISSION = "weekly_commission" # 周委托完成


class GuildTaskRecord(Base):
    """公会任务完成记录表"""
    __tablename__ = "guild_task_record"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True, comment="玩家ID")
    guild_id: Mapped[int] = mapped_column(Integer, ForeignKey("guild.id"), index=True, comment="公会ID")
    
    # 任务信息
    task_type: Mapped[GuildTaskType] = mapped_column(SQLEnum(GuildTaskType), comment="任务类型")
    task_date: Mapped[date] = mapped_column(Date, default=date.today, comment="任务日期")
    
    # 任务进度和奖励
    progress: Mapped[int] = mapped_column(Integer, default=1, comment="完成进度")
    points_reward: Mapped[int] = mapped_column(Integer, default=0, comment="获得积分")
    guild_exp_reward: Mapped[int] = mapped_column(Integer, default=0, comment="公会经验奖励")
    
    # 时间记录
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), comment="完成时间")
    
    # 关系
    player: Mapped["Player"] = relationship("Player")
    guild: Mapped["Guild"] = relationship("Guild")


class PlayerTaskStats(Base):
    """玩家任务统计表"""
    __tablename__ = "player_task_stats"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), unique=True, index=True, comment="玩家ID")
    
    # 日常任务统计
    total_explorations: Mapped[int] = mapped_column(Integer, default=0, comment="总探索次数")
    total_combat_victories: Mapped[int] = mapped_column(Integer, default=0, comment="总战斗胜利次数")
    total_commissions: Mapped[int] = mapped_column(Integer, default=0, comment="总委托完成次数")
    
    # 今日统计
    today_explorations: Mapped[int] = mapped_column(Integer, default=0, comment="今日探索次数")
    today_combat_victories: Mapped[int] = mapped_column(Integer, default=0, comment="今日战斗胜利次数")
    today_commissions: Mapped[int] = mapped_column(Integer, default=0, comment="今日委托完成次数")
    
    # 本周统计
    week_commissions: Mapped[int] = mapped_column(Integer, default=0, comment="本周委托完成次数")
    week_daily_tasks: Mapped[int] = mapped_column(Integer, default=0, comment="本周日常任务完成次数")
    
    # 统计重置时间
    last_daily_reset: Mapped[date] = mapped_column(Date, default=date.today, comment="上次日常重置日期")
    last_weekly_reset: Mapped[date] = mapped_column(Date, default=date.today, comment="上次周常重置日期")
    
    # 关系
    player: Mapped["Player"] = relationship("Player")
    
    def reset_daily_stats(self):
        """重置日常统计"""
        today = date.today()
        if self.last_daily_reset != today:
            self.today_explorations = 0
            self.today_combat_victories = 0
            self.today_commissions = 0
            self.last_daily_reset = today
    
    def reset_weekly_stats(self):
        """重置周常统计（每周一重置）"""
        today = date.today()
        # 计算本周一的日期
        days_since_monday = today.weekday()
        monday = today - timedelta(days=days_since_monday)
        
        if self.last_weekly_reset < monday:
            self.week_commissions = 0
            self.week_daily_tasks = 0
            self.last_weekly_reset = monday
