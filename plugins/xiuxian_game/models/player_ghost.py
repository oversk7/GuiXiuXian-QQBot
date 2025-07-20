from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
from .db import Base
from . import Player


class PlayerGhost(Base):
    """玩家驾驭的鬼怪表
    
    记录玩家拥有的完整鬼怪，用于镇压战斗
    """
    __tablename__ = "player_ghost"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True, comment="玩家ID")
    ghost_id: Mapped[str] = mapped_column(String(32), index=True, comment="鬼怪ID，对应Ghost表")
    
    # 状态信息
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否为当前驾驭的鬼怪")
    level: Mapped[int] = mapped_column(Integer, default=1, comment="鬼怪等级（预留扩展）")
    experience: Mapped[int] = mapped_column(Integer, default=0, comment="鬼怪经验（预留扩展）")
    
    # 时间信息
    obtained_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), comment="获得时间")
    last_used: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="最后使用时间")
    
    # 关系
    owner: Mapped["Player"] = relationship("Player", backref="owned_ghosts")
    
    def activate(self) -> None:
        """激活为当前驾驭的鬼怪"""
        self.is_active = True
        self.last_used = datetime.now()
    
    def deactivate(self) -> None:
        """取消激活"""
        self.is_active = False

    def get_config(self) -> dict:
        """获取鬼怪配置"""
        from ..ghost_suppression.ghost_utils import GhostUtils
        return GhostUtils.get_ghost_config(self.ghost_id)

    def get_actual_attributes(self) -> dict:
        """获取当前等级下的实际属性"""
        from ..ghost_suppression.ghost_utils import GhostUtils
        ghost_config = self.get_config()
        return GhostUtils.calculate_ghost_attributes(ghost_config, self.level)

    def get_upgrade_cost(self) -> int:
        """获取升级到下一级所需的怨念值"""
        from ..ghost_suppression.ghost_utils import GhostUtils
        ghost_config = self.get_config()
        rarity = ghost_config.get("rarity", "common")
        return GhostUtils.get_upgrade_cost(self.level, rarity)

    def can_upgrade(self, player_resentment: int) -> bool:
        """检查是否可以升级"""
        return player_resentment >= self.get_upgrade_cost()

    def upgrade(self) -> int:
        """升级鬼怪，返回消耗的怨念值"""
        cost = self.get_upgrade_cost()
        self.level += 1
        self.experience = 0  # 重置经验
        return cost
