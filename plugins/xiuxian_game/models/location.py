"""
地点管理系统数据模型

统一管理游戏中的所有地点，包括市集、打工地点、特殊商店等
"""

from sqlalchemy import Integer, String, DateTime, Boolean, JSON, func, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.mutable import MutableDict
from datetime import datetime
from typing import Dict, Any, List, Optional
from .db import Base


class Location(Base):
    """地点表 - 统一管理游戏中的所有地点"""
    __tablename__ = "location"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, comment="地点唯一标识")
    
    # 基本信息
    name: Mapped[str] = mapped_column(String(100), comment="地点名称")
    description: Mapped[str] = mapped_column(Text, comment="地点描述")
    
    # 坐标信息
    x: Mapped[int] = mapped_column(Integer, comment="X坐标")
    y: Mapped[int] = mapped_column(Integer, comment="Y坐标")
    region: Mapped[str] = mapped_column(String(32), default="大都会", comment="所属区域")
    
    # 地点类型和功能
    location_type: Mapped[str] = mapped_column(String(32), comment="地点类型：market/workshop/job_center/special_shop/normal")
    functions: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        comment="地点功能配置JSON"
    )

    # 地点状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否激活")
    required_level: Mapped[int] = mapped_column(Integer, default=1, comment="进入所需最低等级")

    # 扩展配置
    config: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        comment="地点扩展配置JSON"
    )
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="过期时间（临时地点自动删除）")

    # 关系
    npcs: Mapped[List["NPC"]] = relationship("NPC", back_populates="location", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Location(id={self.location_id}, name={self.name}, coord=({self.x},{self.y}))>"
    
    @property
    def coord_str(self) -> str:
        """返回坐标字符串"""
        return f"({self.x},{self.y})"
    
    def has_function(self, function_name: str) -> bool:
        """检查地点是否具有指定功能"""
        if self.functions is None:
            return False
        return function_name in self.functions and self.functions[function_name].get("enabled", False)
    
    def get_function_config(self, function_name: str) -> Dict[str, Any]:
        """获取指定功能的配置"""
        if self.functions is None:
            return {}
        return self.functions.get(function_name, {})
    
    def add_function(self, function_name: str, config: Dict[str, Any] = None) -> None:
        """添加地点功能"""
        if self.functions is None:
            self.functions = {}
        if config is None:
            config = {}
        config["enabled"] = True
        self.functions[function_name] = config
    
    def remove_function(self, function_name: str) -> None:
        """移除地点功能"""
        if self.functions is not None and function_name in self.functions:
            self.functions[function_name]["enabled"] = False
    
    def get_active_npcs(self) -> List["NPC"]:
        """获取地点中的活跃NPC"""
        return [npc for npc in self.npcs if npc.is_active and not npc.is_dead()]
    
    def get_npcs_by_type(self, npc_type: str) -> List["NPC"]:
        """根据类型获取NPC"""
        return [npc for npc in self.npcs if npc.npc_type == npc_type and npc.is_active]
    
    def calculate_distance(self, x: int, y: int) -> int:
        """计算与指定坐标的曼哈顿距离"""
        return abs(self.x - x) + abs(self.y - y)
    
    @classmethod
    def create_market_location(cls, location_id: str, name: str, x: int, y: int, 
                              market_items: List[str] = None) -> "Location":
        """创建市集地点"""
        location = cls(
            location_id=location_id,
            name=name,
            description=f"{name}市集，这里有各种商品可以交易",
            x=x,
            y=y,
            location_type="market"
        )
        
        # 添加市集功能
        market_config = {
            "enabled": True,
            "items": market_items or [],
            "market_id": location_id
        }
        location.add_function("market", market_config)
        
        return location
    
    @classmethod
    def create_job_location(cls, location_id: str, name: str, x: int, y: int,
                           description: str = None, available_jobs: Dict = None) -> "Location":
        """创建打工地点"""
        location = cls(
            location_id=location_id,
            name=name,
            description=description or f"{name}，这里有各种工作机会",
            x=x,
            y=y,
            location_type="job_center"
        )
        
        # 添加打工功能
        job_config = {
            "enabled": True,
            "available_jobs": available_jobs or {},
            "max_workers": 10
        }
        location.add_function("part_time_job", job_config)
        
        return location
    
    @classmethod
    def create_workshop_location(cls, location_id: str, name: str, x: int, y: int) -> "Location":
        """创建工坊地点"""
        location = cls(
            location_id=location_id,
            name=name,
            description=f"{name}工坊，这里可以锻造和强化装备",
            x=x,
            y=y,
            location_type="workshop"
        )
        
        # 添加锻造功能
        workshop_config = {
            "enabled": True,
            "services": ["forge", "enhance", "gem_socket"]
        }
        location.add_function("forge", workshop_config)
        
        return location
    
    @classmethod
    def create_special_shop_location(cls, location_id: str, name: str, x: int, y: int,
                                   shop_type: str = "general") -> "Location":
        """创建特殊商店地点"""
        location = cls(
            location_id=location_id,
            name=name,
            description=f"{name}，这里有特殊的商品和服务",
            x=x,
            y=y,
            location_type="special_shop"
        )
        
        # 添加特殊商店功能
        shop_config = {
            "enabled": True,
            "shop_type": shop_type
        }
        location.add_function("special_shop", shop_config)
        
        return location
