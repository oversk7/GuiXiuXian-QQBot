"""
NPC管理服务

提供统一的NPC管理功能，包括NPC创建、查询、复活、状态管理等
"""

from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.npc import NPC, NPCType, NPCStatus
from ..models.location import Location
from ..models.player import Player


class NPCService:
    """NPC管理服务类"""
    
    @staticmethod
    async def get_npc_by_id(session: AsyncSession, npc_id: str) -> Optional[NPC]:
        """根据ID获取NPC"""
        stmt = select(NPC).where(NPC.npc_id == npc_id).options(selectinload(NPC.location))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_npc_by_name(session: AsyncSession, name: str, location_id: int = None) -> Optional[NPC]:
        """根据名称获取NPC（可指定地点）"""
        conditions = [NPC.name == name, NPC.is_active == True]
        if location_id:
            conditions.append(NPC.location_id == location_id)
        
        stmt = select(NPC).where(and_(*conditions)).options(selectinload(NPC.location))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_npcs_by_location(session: AsyncSession, location_id: int, 
                                 npc_type: NPCType = None, include_dead: bool = False) -> List[NPC]:
        """获取指定地点的NPC"""
        conditions = [NPC.location_id == location_id, NPC.is_active == True]
        
        if npc_type:
            conditions.append(NPC.npc_type == npc_type)
        
        if not include_dead:
            conditions.append(NPC.status != NPCStatus.DEAD)
        
        stmt = select(NPC).where(and_(*conditions)).options(selectinload(NPC.location))
        result = await session.execute(stmt)
        return result.scalars().all()
    
    @staticmethod
    async def get_npcs_by_type(session: AsyncSession, npc_type: NPCType, 
                             region: str = "大都会") -> List[NPC]:
        """根据类型获取NPC"""
        stmt = select(NPC).join(Location).where(
            and_(
                NPC.npc_type == npc_type,
                NPC.is_active == True,
                Location.region == region,
                NPC.status != NPCStatus.DEAD
            )
        ).options(selectinload(NPC.location))
        result = await session.execute(stmt)
        return result.scalars().all()
    
    @staticmethod
    async def create_npc(session: AsyncSession, npc_id: str, name: str, npc_type: NPCType,
                        location_id: int, description: str = None, **kwargs) -> NPC:
        """创建新NPC"""
        npc = NPC(
            npc_id=npc_id,
            name=name,
            npc_type=npc_type,
            location_id=location_id,
            description=description or f"{name}，一个{npc_type.value}",
            **kwargs
        )
        
        session.add(npc)
        await session.flush()  # 获取ID
        return npc
    
    @staticmethod
    async def create_merchant_npc(session: AsyncSession, npc_id: str, name: str,
                                location_id: int, market_items: List[str] = None) -> NPC:
        """创建商人NPC"""
        npc = NPC.create_merchant(npc_id, name, location_id, market_items)
        session.add(npc)
        await session.flush()
        return npc
    
    @staticmethod
    async def create_craftsman_npc(session: AsyncSession, npc_id: str, name: str,
                                 location_id: int) -> NPC:
        """创建工匠NPC"""
        npc = NPC.create_craftsman(npc_id, name, location_id)
        session.add(npc)
        await session.flush()
        return npc
    
    @staticmethod
    async def create_employer_npc(session: AsyncSession, npc_id: str, name: str,
                                location_id: int, available_jobs: Dict = None) -> NPC:
        """创建雇主NPC"""
        npc = NPC.create_employer(npc_id, name, location_id, available_jobs)
        session.add(npc)
        await session.flush()
        return npc
    
    @staticmethod
    async def create_ghost_npc(session: AsyncSession, npc_id: str, name: str,
                             location_id: int, level: int, hp: int, attack: int,
                             defense: int, agility: int) -> NPC:
        """创建鬼怪NPC"""
        npc = NPC.create_ghost(npc_id, name, location_id, level, hp, attack, defense, agility)
        session.add(npc)
        await session.flush()
        return npc
    
    @staticmethod
    async def kill_npc(session: AsyncSession, npc_id: str) -> bool:
        """击杀NPC"""
        npc = await NPCService.get_npc_by_id(session, npc_id)
        if not npc or not npc.is_killable:
            return False
        
        npc.kill()
        return True
    
    @staticmethod
    async def respawn_npc(session: AsyncSession, npc_id: str) -> bool:
        """复活NPC"""
        npc = await NPCService.get_npc_by_id(session, npc_id)
        if not npc:
            return False
        
        return npc.respawn()
    
    @staticmethod
    async def check_and_respawn_npcs(session: AsyncSession) -> int:
        """检查并复活到期的NPC"""
        # 查找可以复活的NPC
        stmt = select(NPC).where(
            and_(
                NPC.status == NPCStatus.RESPAWNING,
                NPC.respawn_time <= datetime.now(),
                NPC.is_active == True
            )
        )
        result = await session.execute(stmt)
        npcs = result.scalars().all()
        
        respawned_count = 0
        for npc in npcs:
            if npc.respawn():
                respawned_count += 1
        
        return respawned_count
    
    @staticmethod
    async def update_npc(session: AsyncSession, npc_id: str, **kwargs) -> Optional[NPC]:
        """更新NPC信息"""
        npc = await NPCService.get_npc_by_id(session, npc_id)
        if not npc:
            return None
        
        for key, value in kwargs.items():
            if hasattr(npc, key):
                setattr(npc, key, value)
        
        return npc
    
    @staticmethod
    async def delete_npc(session: AsyncSession, npc_id: str) -> bool:
        """删除NPC（软删除）"""
        npc = await NPCService.get_npc_by_id(session, npc_id)
        if not npc:
            return False
        
        npc.is_active = False
        return True
    
    @staticmethod
    async def get_npc_interaction_info(session: AsyncSession, npc: NPC) -> Dict:
        """获取NPC交互信息"""
        if npc.is_dead() or npc.is_respawning():
            return {
                "can_interact": False,
                "status": "unavailable",
                "message": f"{npc.name}当前不可用"
            }
        
        interaction_info = {
            "can_interact": True,
            "status": "available",
            "npc": npc,
            "functions": []
        }
        
        # 根据NPC类型添加可用功能
        if npc.npc_type == NPCType.MERCHANT:
            interaction_info["functions"].append({
                "name": "trade",
                "display": "交易",
                "description": "与商人进行物品交易"
            })
        elif npc.npc_type == NPCType.CRAFTSMAN:
            interaction_info["functions"].extend([
                {
                    "name": "forge",
                    "display": "锻造",
                    "description": "锻造新装备"
                },
                {
                    "name": "enhance",
                    "display": "强化",
                    "description": "强化现有装备"
                },
                {
                    "name": "gem_socket",
                    "display": "镶嵌",
                    "description": "镶嵌宝石"
                }
            ])
        elif npc.npc_type == NPCType.EMPLOYER:
            interaction_info["functions"].append({
                "name": "part_time_job",
                "display": "打工",
                "description": "寻找工作机会"
            })
        elif npc.npc_type == NPCType.GHOST:
            interaction_info["functions"].append({
                "name": "battle",
                "display": "战斗",
                "description": "与鬼怪战斗"
            })
        
        return interaction_info
    
    @staticmethod
    async def find_npc_by_partial_name(session: AsyncSession, partial_name: str,
                                     location_id: int = None) -> List[NPC]:
        """根据部分名称查找NPC"""
        conditions = [
            NPC.name.like(f"%{partial_name}%"),
            NPC.is_active == True,
            NPC.status != NPCStatus.DEAD
        ]
        
        if location_id:
            conditions.append(NPC.location_id == location_id)
        
        stmt = select(NPC).where(and_(*conditions)).options(selectinload(NPC.location))
        result = await session.execute(stmt)
        return result.scalars().all()
    
    @staticmethod
    async def get_dynamic_npcs(session: AsyncSession, location_id: int = None) -> List[NPC]:
        """获取动态生成的NPC"""
        conditions = [NPC.is_dynamic == True, NPC.is_active == True]
        
        if location_id:
            conditions.append(NPC.location_id == location_id)
        
        stmt = select(NPC).where(and_(*conditions)).options(selectinload(NPC.location))
        result = await session.execute(stmt)
        return result.scalars().all()
    
    @staticmethod
    async def cleanup_expired_dynamic_npcs(session: AsyncSession, 
                                         max_age_hours: int = 24) -> int:
        """清理过期的动态NPC"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        stmt = select(NPC).where(
            and_(
                NPC.is_dynamic == True,
                NPC.created_at < cutoff_time,
                NPC.status == NPCStatus.DEAD
            )
        )
        result = await session.execute(stmt)
        expired_npcs = result.scalars().all()
        
        for npc in expired_npcs:
            npc.is_active = False
        
        return len(expired_npcs)
    
    @staticmethod
    def format_npc_list(npcs: List[NPC]) -> str:
        """格式化NPC列表显示"""
        if not npcs:
            return "暂无NPC"
        
        lines = []
        for npc in npcs:
            status_info = ""
            if npc.is_dead():
                status_info = "[已死亡]"
            elif npc.is_respawning():
                remaining = npc.respawn_time - datetime.now()
                minutes = int(remaining.total_seconds() / 60)
                status_info = f"[复活中:{minutes}分钟]"
            
            hint = npc.get_interaction_hint()
            lines.append(f"{npc.name}{status_info}{hint}")
        
        return "\n".join(lines)
