"""
公会核心业务服务
"""
from typing import Optional, Tuple, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, delete
from datetime import datetime
from ..models.guild import Guild, GuildMember, GuildPosition, GuildBuilding, BuildingType
from ..models.player import Player
from .guild_permission import GuildPermission


class GuildService:
    """公会核心业务服务类"""
    
    @staticmethod
    async def create_guild(session: AsyncSession, player_id: str, guild_name: str) -> Tuple[bool, str, Optional[Guild]]:
        """创建公会"""
        # 检查玩家是否已加入公会
        player = await session.get(Player, player_id)
        if not player:
            return False, "玩家不存在", None
        
        if player.guild_id:
            return False, "你已经加入了公会", None
        
        # 检查公会名是否重复
        stmt = select(Guild).where(Guild.name == guild_name)
        existing_guild = (await session.execute(stmt)).scalars().first()
        if existing_guild:
            return False, "已存在同名公会", None
        
        # 创建公会
        new_guild = Guild(
            name=guild_name,
            president_id=player_id,
            created_at=datetime.now()
        )
        session.add(new_guild)
        await session.flush()  # 获取guild.id
        
        # 创建会长成员记录
        guild_member = GuildMember(
            guild_id=new_guild.id,
            player_id=player_id,
            position=GuildPosition.PRESIDENT,
            joined_at=datetime.now()
        )
        session.add(guild_member)
        
        # 更新玩家公会ID
        player.guild_id = new_guild.id
        session.add(player)
        
        return True, "公会创建成功", new_guild
    
    @staticmethod
    async def join_guild(session: AsyncSession, player_id: str, guild_id: int) -> Tuple[bool, str]:
        """加入公会"""
        player = await session.get(Player, player_id)
        if not player:
            return False, "玩家不存在"
        
        if player.guild_id:
            return False, "你已经加入了公会"
        
        guild = await session.get(Guild, guild_id)
        if not guild:
            return False, "公会不存在"
        
        # 检查公会容量
        member_count = await GuildService.get_member_count(session, guild_id)
        max_capacity = GuildService.get_guild_capacity(guild.level)
        
        if member_count >= max_capacity:
            return False, "公会人数已满"
        
        # 创建成员记录
        guild_member = GuildMember(
            guild_id=guild_id,
            player_id=player_id,
            position=GuildPosition.MEMBER,
            joined_at=datetime.now()
        )
        session.add(guild_member)
        
        # 更新玩家公会ID
        player.guild_id = guild_id
        session.add(player)
        
        return True, "成功加入公会"
    
    @staticmethod
    async def leave_guild(session: AsyncSession, player_id: str) -> Tuple[bool, str]:
        """退出公会"""
        player = await session.get(Player, player_id)
        if not player or not player.guild_id:
            return False, "你未加入任何公会"
        
        # 检查是否为会长
        position = await GuildPermission.get_member_position(session, player_id, player.guild_id)
        if position == GuildPosition.PRESIDENT:
            return False, "会长不能直接退出公会，请先转让会长职位或解散公会"
        
        # 删除成员记录
        stmt = delete(GuildMember).where(
            and_(GuildMember.player_id == player_id, GuildMember.guild_id == player.guild_id)
        )
        await session.execute(stmt)
        
        # 清空玩家公会相关数据
        player.guild_id = None
        player.guild_contribution = 0  # 清空累计贡献值（累计获得的积分）
        player.gold2 = 0  # 清空个人积分
        session.add(player)
        
        return True, "成功退出公会"
    
    @staticmethod
    async def set_member_position(session: AsyncSession, operator_id: str, guild_id: int, target_id: str, new_position: GuildPosition) -> Tuple[bool, str]:
        """设置成员职位"""
        # 权限检查
        can_manage, reason = await GuildPermission.can_manage_position(session, operator_id, guild_id, new_position)
        if not can_manage:
            return False, reason
        
        # 检查职位人数限制
        can_set, limit_reason = await GuildPermission.check_position_limit(session, guild_id, new_position)
        if not can_set:
            return False, limit_reason
        
        # 获取目标成员记录
        stmt = select(GuildMember).where(
            and_(GuildMember.player_id == target_id, GuildMember.guild_id == guild_id)
        )
        member = (await session.execute(stmt)).scalars().first()
        
        if not member:
            return False, "目标不是该公会成员"
        
        # 更新职位
        old_position = member.position
        member.position = new_position
        session.add(member)
        
        old_name = GuildPermission.get_position_display_name(old_position)
        new_name = GuildPermission.get_position_display_name(new_position)
        
        return True, f"职位已从{old_name}变更为{new_name}"
    
    @staticmethod
    async def transfer_president(session: AsyncSession, current_president_id: str, new_president_id: str, guild_id: int) -> Tuple[bool, str]:
        """转让会长职位"""
        # 检查当前操作者是否为会长
        current_position = await GuildPermission.get_member_position(session, current_president_id, guild_id)
        if current_position != GuildPosition.PRESIDENT:
            return False, "只有会长才能转让职位"
        
        # 检查目标是否为公会成员
        target_position = await GuildPermission.get_member_position(session, new_president_id, guild_id)
        if not target_position:
            return False, "目标不是该公会成员"
        
        # 更新公会会长ID
        guild = await session.get(Guild, guild_id)
        guild.president_id = new_president_id
        session.add(guild)
        
        # 更新成员职位记录
        # 原会长变为副会长
        stmt_old = select(GuildMember).where(
            and_(GuildMember.player_id == current_president_id, GuildMember.guild_id == guild_id)
        )
        old_president_member = (await session.execute(stmt_old)).scalars().first()
        old_president_member.position = GuildPosition.VICE_PRESIDENT
        session.add(old_president_member)
        
        # 新会长设为会长
        stmt_new = select(GuildMember).where(
            and_(GuildMember.player_id == new_president_id, GuildMember.guild_id == guild_id)
        )
        new_president_member = (await session.execute(stmt_new)).scalars().first()
        new_president_member.position = GuildPosition.PRESIDENT
        session.add(new_president_member)
        
        return True, "会长职位转让成功"
    
    @staticmethod
    async def get_member_count(session: AsyncSession, guild_id: int) -> int:
        """获取公会成员数量"""
        stmt = select(func.count(GuildMember.id)).where(GuildMember.guild_id == guild_id)
        return (await session.execute(stmt)).scalar_one()
    
    @staticmethod
    def get_guild_capacity(level: int) -> int:
        """获取公会容量"""
        return 10 + (level - 1) * 5
    
    @staticmethod
    async def get_guild_members(session: AsyncSession, guild_id: int) -> List[dict]:
        """获取公会成员列表"""
        stmt = select(GuildMember, Player).join(
            Player, GuildMember.player_id == Player.id
        ).where(GuildMember.guild_id == guild_id).order_by(
            GuildMember.position.asc(), Player.guild_contribution.desc(), Player.level.desc()
        )
        
        results = (await session.execute(stmt)).all()
        members = []
        
        for member, player in results:
            members.append({
                "player_id": player.id,
                "nickname": player.nickname,
                "uid": player.uid,
                "level": player.level,
                "position": member.position,
                "position_name": GuildPermission.get_position_display_name(member.position),
                "contribution": player.guild_contribution,
                "joined_at": member.joined_at
            })
        
        return members
