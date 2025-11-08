from __future__ import annotations

from sqlalchemy import String, Integer, DateTime, Boolean, Text, func, select, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.ext.mutable import MutableDict
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import json

from .db import Base


class TemporaryBuff(Base):
    """临时buff状态表"""
    __tablename__ = "temporary_buff"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True, comment="玩家平台ID")
    buff_id: Mapped[str] = mapped_column(String(64), comment="buff标识ID")
    buff_name: Mapped[str] = mapped_column(String(100), comment="buff名称")
    
    # 属性加成数据
    attribute_bonuses: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        server_default='{}',
        comment="属性加成JSON: {attr_name: bonus_value}"
    )
    
    # 时间相关
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    expires_at: Mapped[datetime] = mapped_column(DateTime, comment="过期时间")
    duration_minutes: Mapped[int] = mapped_column(Integer, comment="持续时间(分钟)")
    
    # 状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text('1'), comment="是否激活")
    
    # 来源信息
    source_item_id: Mapped[str] = mapped_column(String(64), nullable=True, comment="来源物品ID")
    source_description: Mapped[str] = mapped_column(String(200), nullable=True, comment="来源描述")
    
    # 额外数据
    extra_data: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        server_default='{}',
        comment="额外数据JSON"
    )

    def is_expired(self) -> bool:
        """检查buff是否已过期"""
        return datetime.now() >= self.expires_at

    def get_remaining_time(self) -> timedelta:
        """获取剩余时间"""
        if self.is_expired():
            return timedelta(0)
        return self.expires_at - datetime.now()

    def get_remaining_minutes(self) -> int:
        """获取剩余分钟数"""
        remaining = self.get_remaining_time()
        return max(0, int(remaining.total_seconds() / 60))

    def get_attribute_bonuses(self) -> Dict[str, int]:
        """获取属性加成字典"""
        return self.attribute_bonuses or {}

    def set_attribute_bonuses(self, bonuses: Dict[str, int]):
        """设置属性加成"""
        self.attribute_bonuses = bonuses

    @classmethod
    async def get_active_buffs(cls, session, player_id: str) -> List["TemporaryBuff"]:
        """获取玩家的所有激活buff"""
        stmt = select(cls).where(
            cls.player_id == player_id,
            cls.is_active == True,
            cls.expires_at > datetime.now()
        ).order_by(cls.expires_at)
        
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def cleanup_expired_buffs(cls, session, player_id: str = None):
        """清理过期的buff"""
        from sqlalchemy import update
        
        stmt = update(cls).where(
            cls.expires_at <= datetime.now(),
            cls.is_active == True
        ).values(is_active=False)
        
        if player_id:
            stmt = stmt.where(cls.player_id == player_id)
        
        await session.execute(stmt)

    @classmethod
    async def create_buff(
        cls, 
        session, 
        player_id: str, 
        buff_id: str, 
        buff_name: str,
        attribute_bonuses: Dict[str, int],
        duration_minutes: int,
        source_item_id: str = None,
        source_description: str = None,
        extra_data: Dict[str, Any] = None
    ) -> "TemporaryBuff":
        """创建新的临时buff"""
        
        # 先清理过期的buff
        await cls.cleanup_expired_buffs(session, player_id)
        
        # 检查是否已存在相同的buff
        existing_stmt = select(cls).where(
            cls.player_id == player_id,
            cls.buff_id == buff_id,
            cls.is_active == True,
            cls.expires_at > datetime.now()
        )
        existing_buff = (await session.execute(existing_stmt)).scalars().first()
        
        if existing_buff:
            # 如果已存在，延长时间并更新属性加成
            existing_buff.expires_at = datetime.now() + timedelta(minutes=duration_minutes)
            existing_buff.duration_minutes = duration_minutes
            existing_buff.attribute_bonuses = attribute_bonuses
            if extra_data:
                existing_buff.extra_data = extra_data
            return existing_buff
        else:
            # 创建新buff
            new_buff = cls(
                player_id=player_id,
                buff_id=buff_id,
                buff_name=buff_name,
                attribute_bonuses=attribute_bonuses,
                duration_minutes=duration_minutes,
                expires_at=datetime.now() + timedelta(minutes=duration_minutes),
                source_item_id=source_item_id,
                source_description=source_description,
                extra_data=extra_data or {}
            )
            session.add(new_buff)
            return new_buff

    @classmethod
    async def get_total_attribute_bonuses(cls, session, player_id: str) -> Dict[str, int]:
        """获取玩家所有激活buff的总属性加成"""
        active_buffs = await cls.get_active_buffs(session, player_id)
        
        total_bonuses = {}
        for buff in active_buffs:
            bonuses = buff.get_attribute_bonuses()
            for attr, value in bonuses.items():
                if attr in total_bonuses:
                    total_bonuses[attr] += value
                else:
                    total_bonuses[attr] = value
        
        return total_bonuses

    def format_display(self) -> str:
        """格式化显示buff信息"""
        remaining_minutes = self.get_remaining_minutes()
        
        # 格式化时间显示
        if remaining_minutes >= 60:
            hours = remaining_minutes // 60
            minutes = remaining_minutes % 60
            time_str = f"{hours}小时{minutes}分钟" if minutes > 0 else f"{hours}小时"
        else:
            time_str = f"{remaining_minutes}分钟"
        
        # 格式化属性加成
        bonuses = self.get_attribute_bonuses()
        bonus_strs = []
        attr_map = {
            "max_hp": "体",
            "max_mp": "智", 
            "attack": "力",
            "defense": "防",
            "agility": "敏",
            "luck": "运",
            "critical_rate": "暴击率",
            "critical_power": "暴击力",
            "combo_rate": "连击率",
            "counter_rate": "反击率",
            "dodge_rate": "闪避率",
            "accuracy_rate": "命中率",
            "skill_crit_rate": "灵爆率",
            "penetration_rate": "穿透率",
            "anti_crit_rate": "抗暴率"
        }
        
        for attr, value in bonuses.items():
            attr_name = attr_map.get(attr, attr)
            if value > 0:
                bonus_strs.append(f"{attr_name}+{value}")
            elif value < 0:
                bonus_strs.append(f"{attr_name}{value}")
        
        bonus_text = ", ".join(bonus_strs) if bonus_strs else "无加成"
        
        return f"✨ {self.buff_name} ({bonus_text}) - 剩余{time_str}"
