"""
NPC管理系统数据模型

管理游戏中的所有NPC，包括商人、工匠、雇主、鬼怪等
"""

from sqlalchemy import Integer, String, DateTime, Boolean, JSON, func, Text, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.mutable import MutableDict
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from enum import Enum
from .db import Base


class NPCType(Enum):
    """NPC类型枚举"""
    MERCHANT = "merchant"        # 商人 - 市集交易
    CRAFTSMAN = "craftsman"      # 工匠 - 装备锻造
    EMPLOYER = "employer"        # 雇主 - 提供打工
    GHOST = "ghost"             # 鬼怪 - 委托任务目标
    SPECIAL_VENDOR = "special_vendor"  # 特殊商贩
    GUARD = "guard"             # 守卫
    NORMAL = "normal"           # 普通NPC


class NPCStatus(Enum):
    """NPC状态枚举"""
    ALIVE = "alive"             # 存活
    DEAD = "dead"               # 死亡
    RESPAWNING = "respawning"   # 复活中


class NPC(Base):
    """NPC表 - 管理游戏中的所有NPC"""
    __tablename__ = "npc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    npc_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, comment="NPC唯一标识")
    
    # 基本信息
    name: Mapped[str] = mapped_column(String(100), comment="NPC名称")
    description: Mapped[str] = mapped_column(Text, comment="NPC描述")
    npc_type: Mapped[NPCType] = mapped_column(SQLEnum(NPCType), comment="NPC类型")
    
    # 位置信息
    location_id: Mapped[int] = mapped_column(Integer, ForeignKey("location.id"), comment="所在地点ID")
    
    # NPC状态
    status: Mapped[NPCStatus] = mapped_column(SQLEnum(NPCStatus), default=NPCStatus.ALIVE, comment="NPC状态")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否激活")
    is_killable: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否可被击杀")
    is_dynamic: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否为动态生成")
    
    # 战斗属性（用于可战斗的NPC）
    level: Mapped[int] = mapped_column(Integer, default=1, comment="等级")
    hp: Mapped[int] = mapped_column(Integer, default=100, comment="血量")
    max_hp: Mapped[int] = mapped_column(Integer, default=100, comment="最大血量")
    attack: Mapped[int] = mapped_column(Integer, default=10, comment="攻击力")
    defense: Mapped[int] = mapped_column(Integer, default=5, comment="防御力")
    agility: Mapped[int] = mapped_column(Integer, default=10, comment="敏捷")
    
    # 复活机制
    death_time: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="死亡时间")
    respawn_time: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="复活时间")
    respawn_duration_minutes: Mapped[int] = mapped_column(Integer, default=60, comment="复活时长(分钟)")
    
    # 功能配置
    functions: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        comment="NPC功能配置JSON"
    )
    
    # 扩展数据
    extra_data: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        comment="扩展数据JSON"
    )
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    # 关系
    location: Mapped["Location"] = relationship("Location", back_populates="npcs")
    dialogue_histories: Mapped[list["NPCDialogueHistory"]] = relationship(
        "NPCDialogueHistory",
        back_populates="npc",
        cascade="all, delete-orphan"
    )
    favorability_records: Mapped[list["NPCFavorability"]] = relationship(
        "NPCFavorability",
        back_populates="npc",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<NPC(id={self.npc_id}, name={self.name}, type={self.npc_type.value})>"
    
    def is_dead(self) -> bool:
        """检查NPC是否死亡"""
        return self.status == NPCStatus.DEAD
    
    def is_respawning(self) -> bool:
        """检查NPC是否正在复活"""
        return self.status == NPCStatus.RESPAWNING
    
    def can_respawn(self) -> bool:
        """检查是否可以复活"""
        if not self.is_dead() or not self.respawn_time:
            return False
        return datetime.now() >= self.respawn_time
    
    def kill(self) -> None:
        """击杀NPC"""
        if not self.is_killable:
            return
        
        self.status = NPCStatus.DEAD
        self.death_time = datetime.now()
        self.hp = 0
        
        # 设置复活时间
        if self.respawn_duration_minutes > 0:
            self.respawn_time = self.death_time + timedelta(minutes=self.respawn_duration_minutes)
            self.status = NPCStatus.RESPAWNING
    
    def respawn(self) -> bool:
        """复活NPC"""
        if not self.can_respawn():
            return False
        
        self.status = NPCStatus.ALIVE
        self.hp = self.max_hp
        self.death_time = None
        self.respawn_time = None
        return True
    
    def take_damage(self, damage: int) -> bool:
        """受到伤害，返回是否死亡"""
        if self.is_dead():
            return True
        
        self.hp = max(0, self.hp - damage)
        if self.hp <= 0:
            self.kill()
            return True
        return False
    
    def heal(self, amount: int) -> None:
        """治疗"""
        if not self.is_dead():
            self.hp = min(self.max_hp, self.hp + amount)
    
    def has_function(self, function_name: str) -> bool:
        """检查NPC是否具有指定功能"""
        if self.functions is None:
            return False
        return function_name in self.functions and self.functions[function_name].get("enabled", False)
    
    def get_function_config(self, function_name: str) -> Dict[str, Any]:
        """获取指定功能的配置"""
        if self.functions is None:
            return {}
        return self.functions.get(function_name, {})
    
    def add_function(self, function_name: str, config: Dict[str, Any] = None) -> None:
        """添加NPC功能"""
        if self.functions is None:
            self.functions = {}
        if config is None:
            config = {}
        config["enabled"] = True
        self.functions[function_name] = config
    
    def remove_function(self, function_name: str) -> None:
        """移除NPC功能"""
        if self.functions is not None and function_name in self.functions:
            self.functions[function_name]["enabled"] = False
    
    def get_display_name(self) -> str:
        """获取显示名称"""
        if self.is_dead():
            return f"{self.name}[已死亡]"
        elif self.is_respawning():
            remaining = self.respawn_time - datetime.now()
            minutes = int(remaining.total_seconds() / 60)
            return f"{self.name}[复活中:{minutes}分钟]"
        else:
            return self.name
    
    def get_interaction_hint(self) -> str:
        """获取交互提示"""
        if self.is_dead() or self.is_respawning():
            return ""
        
        hints = []
        if self.npc_type == NPCType.MERCHANT:
            hints.append("交易")
        elif self.npc_type == NPCType.CRAFTSMAN:
            hints.append("锻造装备")
        elif self.npc_type == NPCType.EMPLOYER:
            hints.append("打工")
        elif self.npc_type == NPCType.GHOST:
            hints.append("战斗")
        
        return "[" + "、".join(hints) + "]" if hints else ""
    
    @classmethod
    def create_merchant(cls, npc_id: str, name: str, location_id: int,
                       market_items: list = None) -> "NPC":
        """创建商人NPC"""
        npc = cls(
            npc_id=npc_id,
            name=name,
            description=f"商人{name}，专门从事各种商品交易",
            npc_type=NPCType.MERCHANT,
            location_id=location_id,
            is_killable=False
        )
        
        # 添加交易功能
        trade_config = {
            "enabled": True,
            "items": market_items or []
        }
        npc.add_function("trade", trade_config)
        
        return npc
    
    @classmethod
    def create_craftsman(cls, npc_id: str, name: str, location_id: int) -> "NPC":
        """创建工匠NPC"""
        npc = cls(
            npc_id=npc_id,
            name=name,
            description=f"工匠{name}，精通装备锻造和强化技艺",
            npc_type=NPCType.CRAFTSMAN,
            location_id=location_id,
            is_killable=False
        )
        
        # 添加锻造功能
        forge_config = {
            "enabled": True,
            "services": ["forge", "enhance", "gem_socket"]
        }
        npc.add_function("forge", forge_config)
        
        return npc
    
    @classmethod
    def create_employer(cls, npc_id: str, name: str, location_id: int,
                       available_jobs: dict = None) -> "NPC":
        """创建雇主NPC"""
        npc = cls(
            npc_id=npc_id,
            name=name,
            description=f"雇主{name}，为勤劳的人们提供工作机会",
            npc_type=NPCType.EMPLOYER,
            location_id=location_id,
            is_killable=False
        )
        
        # 添加打工功能
        job_config = {
            "enabled": True,
            "available_jobs": available_jobs or {}
        }
        npc.add_function("part_time_job", job_config)
        
        return npc
    
    @classmethod
    def create_ghost(cls, npc_id: str, name: str, location_id: int,
                    level: int, hp: int, attack: int, defense: int, agility: int) -> "NPC":
        """创建鬼怪NPC"""
        npc = cls(
            npc_id=npc_id,
            name=name,
            description=f"邪恶的{name}，散发着不祥的气息",
            npc_type=NPCType.GHOST,
            location_id=location_id,
            is_killable=True,
            is_dynamic=True,
            level=level,
            hp=hp,
            max_hp=hp,
            attack=attack,
            defense=defense,
            agility=agility,
            respawn_duration_minutes=0  # 鬼怪不复活
        )
        
        return npc
