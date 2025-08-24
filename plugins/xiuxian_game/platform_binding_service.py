"""
跨平台绑定服务类
处理绑定逻辑、安全验证和数据同步
"""
from typing import Optional, Tuple, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from datetime import datetime

from .models.player import Player
from .models.platform_binding import PlatformBinding


class PlatformBindingService:
    """跨平台绑定服务"""
    
    @staticmethod
    async def create_binding_key(session: AsyncSession, player_id: str) -> Tuple[bool, str, Optional[str]]:
        """
        为玩家创建绑定密钥
        
        Args:
            session: 数据库会话
            player_id: 玩家ID
            
        Returns:
            Tuple[是否成功, 消息, 绑定密钥]
        """
        try:
            # 检查玩家是否存在
            player = await session.get(Player, player_id)
            if not player:
                return False, "玩家不存在", None
            
            # 查找现有绑定记录
            binding_stmt = select(PlatformBinding).where(
                PlatformBinding.primary_platform_id == player_id,
                PlatformBinding.is_active == True
            )
            binding_result = await session.execute(binding_stmt)
            binding = binding_result.scalars().first()
            
            if binding and binding.secondary_platform_id:
                return False, "账号已经绑定了频道账号", None
            
            if not binding:
                # 创建新的绑定记录
                binding = PlatformBinding(
                    primary_platform_id=player_id,
                    secondary_platform_id=None,
                    is_active=True
                )
                session.add(binding)
            
            # 生成新的绑定密钥
            binding.binding_key = PlatformBinding.generate_binding_key()
            binding.updated_at = datetime.now()
            
            await session.commit()

            return True, "绑定密钥生成成功", binding.binding_key

        except IntegrityError as e:
            await session.rollback()
            if "uq_primary_platform_id" in str(e):
                return False, "该账号已有绑定记录", None
            return False, f"数据库约束错误：{str(e)}", None
        except Exception as e:
            await session.rollback()
            return False, f"生成绑定密钥失败：{str(e)}", None
    
    @staticmethod
    async def verify_and_bind(session: AsyncSession, secondary_platform_id: str, 
                             binding_key: str, target_uid: int) -> Tuple[bool, str, Optional[Player]]:
        """
        验证绑定密钥并执行绑定
        
        Args:
            session: 数据库会话
            secondary_platform_id: 次平台ID（频道用户ID）
            binding_key: 绑定密钥
            target_uid: 目标玩家UID
            
        Returns:
            Tuple[是否成功, 消息, 玩家对象]
        """
        try:
            # 检查次平台用户是否已有角色
            existing_player = await session.get(Player, secondary_platform_id)
            if existing_player:
                return False, "你已经有角色了，无法绑定其他账号", None
            
            # 查找目标玩家
            target_player_stmt = select(Player).where(Player.uid == target_uid)
            target_player_result = await session.execute(target_player_stmt)
            target_player = target_player_result.scalars().first()
            
            if not target_player:
                return False, "找不到指定UID的玩家", None
            
            # 查找绑定记录
            binding_stmt = select(PlatformBinding).where(
                PlatformBinding.primary_platform_id == target_player.id,
                PlatformBinding.binding_key == binding_key,
                PlatformBinding.is_active == True
            )
            binding_result = await session.execute(binding_stmt)
            binding = binding_result.scalars().first()
            
            if not binding:
                return False, "绑定密钥无效", None
            
            if not binding.is_key_valid():
                return False, "绑定密钥无效", None
            
            if binding.secondary_platform_id:
                return False, "该账号已经绑定了其他频道账号", None
            
            # 执行绑定
            binding.secondary_platform_id = secondary_platform_id
            binding.clear_binding_key()
            
            await session.commit()

            return True, "账号绑定成功", target_player

        except IntegrityError as e:
            await session.rollback()
            if "uq_secondary_platform_id" in str(e):
                return False, "该频道账号已被其他群聊账号绑定", None
            return False, f"数据库约束错误：{str(e)}", None
        except Exception as e:
            await session.rollback()
            return False, f"绑定失败：{str(e)}", None
    
    @staticmethod
    async def get_binding_info(session: AsyncSession, player_id: str) -> Optional[Dict[str, Any]]:
        """
        获取玩家的绑定信息
        
        Args:
            session: 数据库会话
            player_id: 玩家ID
            
        Returns:
            绑定信息字典或None
        """
        try:
            binding_stmt = select(PlatformBinding).where(
                PlatformBinding.primary_platform_id == player_id,
                PlatformBinding.is_active == True
            )
            binding_result = await session.execute(binding_stmt)
            binding = binding_result.scalars().first()
            
            if not binding:
                return None
            
            info = {
                "has_binding": True,
                "is_bound": bool(binding.secondary_platform_id),
                "created_at": binding.created_at,
                "updated_at": binding.updated_at
            }
            
            if binding.binding_key:
                info.update({
                    "has_pending_key": True,
                    "binding_key": binding.binding_key,
                    "key_valid": binding.is_key_valid()
                })
            else:
                info["has_pending_key"] = False
            
            return info
            
        except Exception:
            return None
    
    @staticmethod
    async def unbind_account(session: AsyncSession, player_id: str) -> Tuple[bool, str]:
        """
        解除账号绑定
        
        Args:
            session: 数据库会话
            player_id: 玩家ID
            
        Returns:
            Tuple[是否成功, 消息]
        """
        try:
            binding_stmt = select(PlatformBinding).where(
                PlatformBinding.primary_platform_id == player_id,
                PlatformBinding.is_active == True
            )
            binding_result = await session.execute(binding_stmt)
            binding = binding_result.scalars().first()
            
            if not binding or not binding.secondary_platform_id:
                return False, "账号没有绑定频道账号"
            
            # 解除绑定
            binding.is_active = False
            binding.updated_at = datetime.now()
            
            await session.commit()
            
            return True, "账号绑定已解除"
            
        except Exception as e:
            await session.rollback()
            return False, f"解除绑定失败：{str(e)}"
    
    @staticmethod
    async def find_player_by_platform(session: AsyncSession, platform_id: str) -> Optional[Player]:
        """
        通过平台ID查找玩家（支持跨平台绑定）
        
        Args:
            session: 数据库会话
            platform_id: 平台ID
            
        Returns:
            玩家对象或None
        """
        try:
            # 首先尝试直接查找
            player = await session.get(Player, platform_id)
            if player:
                return player
            
            # 尝试通过绑定关系查找（作为次平台ID）
            binding_stmt = select(PlatformBinding).where(
                PlatformBinding.secondary_platform_id == platform_id,
                PlatformBinding.is_active == True
            )
            binding_result = await session.execute(binding_stmt)
            binding = binding_result.scalars().first()
            
            if binding:
                player = await session.get(Player, binding.primary_platform_id)
                return player
            
            return None
            
        except Exception:
            return None
    

    
    @staticmethod
    async def get_binding_statistics(session: AsyncSession) -> Dict[str, int]:
        """
        获取绑定统计信息
        
        Args:
            session: 数据库会话
            
        Returns:
            统计信息字典
        """
        try:
            # 统计总绑定数
            total_bindings_stmt = select(PlatformBinding).where(
                PlatformBinding.is_active == True,
                PlatformBinding.secondary_platform_id.isnot(None)
            )
            total_bindings_result = await session.execute(total_bindings_stmt)
            total_bindings = len(total_bindings_result.scalars().all())
            
            # 统计待绑定数
            pending_bindings_stmt = select(PlatformBinding).where(
                PlatformBinding.is_active == True,
                PlatformBinding.secondary_platform_id.is_(None),
                PlatformBinding.binding_key.isnot(None)
            )
            pending_bindings_result = await session.execute(pending_bindings_stmt)
            pending_bindings = len(pending_bindings_result.scalars().all())
            
            return {
                "total_bindings": total_bindings,
                "pending_bindings": pending_bindings
            }
            
        except Exception:
            return {
                "total_bindings": 0,
                "pending_bindings": 0
            }
