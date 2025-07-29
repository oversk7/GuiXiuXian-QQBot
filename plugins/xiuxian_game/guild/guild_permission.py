"""
公会权限管理系统
"""
from typing import Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models.guild import Guild, GuildMember, GuildPosition
from ..models.player import Player


class GuildPermission:
    """公会权限管理类"""
    
    @staticmethod
    async def get_member_position(session: AsyncSession, player_id: str, guild_id: int) -> Optional[GuildPosition]:
        """获取成员在指定公会中的职位"""
        stmt = select(GuildMember.position).where(
            GuildMember.player_id == player_id,
            GuildMember.guild_id == guild_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    
    @staticmethod
    async def can_manage_position(session: AsyncSession, operator_id: str, guild_id: int, target_position: GuildPosition) -> Tuple[bool, str]:
        """检查操作者是否有权限设置目标职位"""
        operator_position = await GuildPermission.get_member_position(session, operator_id, guild_id)
        
        if not operator_position:
            return False, "你不是该公会成员"
        
        # 会长可以设置任何职位（除了会长本身）
        if operator_position == GuildPosition.PRESIDENT:
            if target_position == GuildPosition.PRESIDENT:
                return False, "不能设置其他人为会长，请使用转让会长功能"
            return True, ""
        
        # 副会长可以设置核心成员和普通成员
        if operator_position == GuildPosition.VICE_PRESIDENT:
            if target_position in [GuildPosition.CORE_MEMBER, GuildPosition.MEMBER]:
                return True, ""
            return False, "副会长只能设置核心成员和普通成员职位"
        
        # 其他职位无权限设置职位
        return False, "你没有权限设置成员职位"
    
    @staticmethod
    async def can_kick_member(session: AsyncSession, operator_id: str, guild_id: int, target_id: str) -> Tuple[bool, str]:
        """检查操作者是否有权限踢出目标成员"""
        operator_position = await GuildPermission.get_member_position(session, operator_id, guild_id)
        target_position = await GuildPermission.get_member_position(session, target_id, guild_id)
        
        if not operator_position:
            return False, "你不是该公会成员"
        
        if not target_position:
            return False, "目标不是该公会成员"
        
        if operator_id == target_id:
            return False, "不能踢出自己"
        
        # 会长可以踢出除自己外的任何人
        if operator_position == GuildPosition.PRESIDENT:
            return True, ""
        
        # 副会长可以踢出核心成员和普通成员
        if operator_position == GuildPosition.VICE_PRESIDENT:
            if target_position in [GuildPosition.CORE_MEMBER, GuildPosition.MEMBER]:
                return True, ""
            return False, "副会长不能踢出会长或其他副会长"
        
        # 其他职位无权限踢人
        return False, "你没有权限踢出成员"
    
    @staticmethod
    async def can_manage_guild(session: AsyncSession, player_id: str, guild_id: int) -> Tuple[bool, str]:
        """检查是否有公会管理权限（会长和副会长）"""
        position = await GuildPermission.get_member_position(session, player_id, guild_id)
        
        if not position:
            return False, "你不是该公会成员"
        
        if position in [GuildPosition.PRESIDENT, GuildPosition.VICE_PRESIDENT]:
            return True, ""
        
        return False, "只有会长和副会长才能进行此操作"
    
    @staticmethod
    async def can_build(session: AsyncSession, player_id: str, guild_id: int) -> Tuple[bool, str]:
        """检查是否有建造权限（仅会长）"""
        position = await GuildPermission.get_member_position(session, player_id, guild_id)
        
        if not position:
            return False, "你不是该公会成员"
        
        if position == GuildPosition.PRESIDENT:
            return True, ""
        
        return False, "只有会长才能建造公会建筑"
    
    @staticmethod
    def get_position_display_name(position: GuildPosition) -> str:
        """获取职位显示名称"""
        position_names = {
            GuildPosition.PRESIDENT: "会长",
            GuildPosition.VICE_PRESIDENT: "副会长", 
            GuildPosition.CORE_MEMBER: "核心成员",
            GuildPosition.MEMBER: "普通成员"
        }
        return position_names.get(position, "未知职位")
    
    @staticmethod
    def get_exp_bonus_multiplier(position: GuildPosition) -> float:
        """获取职位对应的经验加成倍率"""
        # 只有普通成员不享受经验加成
        if position == GuildPosition.MEMBER:
            return 1.0
        else:
            return 1.1  # 其他职位享受10%经验加成
    
    @staticmethod
    async def get_position_limits(session: AsyncSession, guild_id: int) -> dict:
        """获取各职位的人数限制"""
        # 获取公会信息
        guild = await session.get(Guild, guild_id)
        if not guild:
            return {}
        
        # 计算最大人数
        max_members = 10 + (guild.level - 1) * 5
        
        return {
            GuildPosition.PRESIDENT: 1,  # 会长固定1位
            GuildPosition.VICE_PRESIDENT: 3,  # 副会长最多3位
            GuildPosition.CORE_MEMBER: max_members // 2,  # 核心成员最多50%
            GuildPosition.MEMBER: max_members  # 普通成员无限制（受总人数限制）
        }
    
    @staticmethod
    async def check_position_limit(session: AsyncSession, guild_id: int, position: GuildPosition) -> Tuple[bool, str]:
        """检查职位人数是否已达上限"""
        limits = await GuildPermission.get_position_limits(session, guild_id)
        limit = limits.get(position, 0)
        
        if limit == 0:
            return False, "无效的职位"
        
        # 统计当前职位人数
        stmt = select(GuildMember).where(
            GuildMember.guild_id == guild_id,
            GuildMember.position == position
        )
        current_count = len((await session.execute(stmt)).scalars().all())
        
        if current_count >= limit:
            position_name = GuildPermission.get_position_display_name(position)
            return False, f"{position_name}人数已达上限({limit}人)"
        
        return True, ""
