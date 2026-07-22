from sqlalchemy import String, Integer, Boolean, DateTime, Text, Enum as SQLEnum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime, date
from enum import Enum
from .db import Base


class TaskType(Enum):
    """任务类型枚举"""
    GHOST_ELIMINATION = "ghost_elimination"  # 鬼怪入侵事件处理
    PEN_SPIRIT_CASE = "pen_spirit_case"      # 笔仙案件调查
    FAKE_IMMORTAL_CULT = "fake_immortal_cult"  # 伪仙邪教事件
    SHAPE_SHIFTER_HUNT = "shape_shifter_hunt"  # 变形鬼怪追捕
    STONE_CURSE_BREAK = "stone_curse_break"    # 石化诅咒破解
    TORTURE_CULT_RAID = "torture_cult_raid"    # 酷刑邪教清剿
    TUTORIAL = "tutorial"                      # 新手教程任务


class TaskStatus(Enum):
    """任务状态枚举"""
    AVAILABLE = "available"      # 可接取
    ACCEPTED = "accepted"        # 已接取
    COMPLETED = "completed"      # 已完成
    EXPIRED = "expired"          # 已过期


class DailyTask(Base):
    """每日任务表
    
    记录每日生成的任务信息，包括任务类型、目标坐标、状态等
    """
    __tablename__ = "daily_task"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True, comment="玩家ID")
    
    # 任务基本信息
    task_type: Mapped[str] = mapped_column(String(50), comment="任务类型")
    title: Mapped[str] = mapped_column(String(100), comment="任务标题")
    description: Mapped[str] = mapped_column(Text, comment="任务描述")
    
    # 任务目标信息
    target_region: Mapped[str] = mapped_column(String(32), default="大都会", comment="目标区域")
    target_x: Mapped[int] = mapped_column(Integer, comment="目标坐标X")
    target_y: Mapped[int] = mapped_column(Integer, comment="目标坐标Y")
    
    # 任务状态
    status: Mapped[str] = mapped_column(String(20), default="available", comment="任务状态")
    
    # 敌人信息（用于战斗）
    enemy_name: Mapped[str] = mapped_column(String(50), comment="敌人名称")
    enemy_level: Mapped[int] = mapped_column(Integer, comment="敌人等级")
    enemy_hp: Mapped[int] = mapped_column(Integer, comment="敌人血量")
    enemy_attack: Mapped[int] = mapped_column(Integer, comment="敌人攻击力")
    enemy_defense: Mapped[int] = mapped_column(Integer, comment="敌人防御力")
    enemy_agility: Mapped[int] = mapped_column(Integer, comment="敌人敏捷")
    
    # 奖励信息
    exp_reward: Mapped[int] = mapped_column(Integer, default=0, comment="经验奖励")
    gold_reward: Mapped[int] = mapped_column(Integer, default=0, comment="金币奖励")
    guild_points_reward: Mapped[int] = mapped_column(Integer, default=0, comment="公会积分奖励")

    # 新手任务链扩展字段
    quest_chain_id: Mapped[str] = mapped_column(String(50), nullable=True, comment="任务链ID（如novice_basic）")
    quest_step: Mapped[int] = mapped_column(Integer, nullable=True, comment="任务链步骤（1、2、3...）")
    quest_progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="新手任务当前动作进度")
    is_tutorial: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否为新手教程任务")
    auto_accept: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否自动接取")

    # 时间信息
    task_date: Mapped[date] = mapped_column(default=date.today, comment="任务日期")
    accepted_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="接取时间")
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="完成时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())
    
    # 关系
    player: Mapped["Player"] = relationship("Player", backref="daily_tasks")
    
    def is_available(self) -> bool:
        """检查任务是否可接取"""
        return self.status == "available"

    def is_accepted(self) -> bool:
        """检查任务是否已接取"""
        return self.status == "accepted"

    def is_completed(self) -> bool:
        """检查任务是否已完成"""
        return self.status == "completed"

    def accept_task(self) -> None:
        """接取任务"""
        if self.status == "available":
            self.status = "accepted"
            self.accepted_at = datetime.now()

    def complete_task(self) -> None:
        """完成任务"""
        if self.status == "accepted":
            self.status = "completed"
            self.completed_at = datetime.now()

    def expire_task(self) -> None:
        """任务过期"""
        if self.status in ["available", "accepted"]:
            self.status = "expired"
    
    @property
    def location_str(self) -> str:
        """获取位置字符串"""
        return f"{self.target_region}({self.target_x},{self.target_y})"
    
    @property
    def enemy_stats(self) -> dict:
        """获取敌人属性字典"""
        return {
            "name": self.enemy_name,
            "level": self.enemy_level,
            "hp": self.enemy_hp,
            "attack": self.enemy_attack,
            "defense": self.enemy_defense,
            "agility": self.enemy_agility
        }
    
    def get_reward_summary(self, has_guild: bool = None) -> str:
        """获取奖励摘要

        Args:
            has_guild: 玩家是否有公会，如果为None则显示通用信息
        """
        rewards = []
        if self.exp_reward > 0:
            rewards.append(f"经验+{self.exp_reward}")
        if self.gold_reward > 0:
            rewards.append(f"金币+{self.gold_reward}")
        if self.guild_points_reward > 0:
            rewards.append(f"积分+{self.guild_points_reward}")
            # 只有有公会的玩家才显示公会经验
            if has_guild is True:
                rewards.append("公会经验+额外")  # 公会经验是动态计算的
            elif has_guild is None:
                rewards.append("公会经验+额外(需加入公会)")  # 通用显示
        return " ".join(rewards) if rewards else "无奖励"
