"""
公会核心业务服务 (DI改造版本)

改造说明:
- 从静态方法改为实例方法
- 通过构造函数注入Repository依赖
- 移除方法参数中的session,改为通过UoW管理
- 保持业务逻辑完全一致
"""
from typing import Optional, Tuple, List
from datetime import datetime

from ..models.guild import Guild, GuildMember, GuildPosition
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.guild_repository import GuildRepository
from ..infrastructure.uow.unit_of_work import UnitOfWork
from .guild_permission import GuildPermission


class GuildService:
    """
    公会核心业务服务类 (DI版本)

    依赖注入:
        - player_repo: PlayerRepository
        - guild_repo: GuildRepository
        - uow: UnitOfWork (可选,用于需要直接访问session的场景)
    """

    def __init__(
        self,
        player_repo: PlayerRepository,
        guild_repo: GuildRepository,
        uow: Optional[UnitOfWork] = None
    ):
        """
        初始化公会服务

        Args:
            player_repo: 玩家仓储
            guild_repo: 公会仓储
            uow: 工作单元(可选)
        """
        self._player_repo = player_repo
        self._guild_repo = guild_repo
        self._uow = uow

    async def create_guild(self, player_id: str, guild_name: str) -> Tuple[bool, str, Optional[Guild]]:
        """创建公会"""
        # 检查玩家是否已加入公会
        player = await self._player_repo.get_by_id(player_id)
        if not player:
            return False, "玩家不存在", None

        if player.guild_id:
            return False, "你已经加入了公会", None

        # 检查公会名是否重复
        existing_guild = await self._guild_repo.get_by_name(guild_name)
        if existing_guild:
            return False, "已存在同名公会", None

        # 创建公会
        new_guild = Guild(
            name=guild_name,
            president_id=player_id,
            created_at=datetime.now()
        )
        await self._guild_repo.add(new_guild)

        # 创建会长成员记录
        guild_member = GuildMember(
            guild_id=new_guild.id,
            player_id=player_id,
            position=GuildPosition.PRESIDENT,
            joined_at=datetime.now()
        )
        await self._guild_repo.add_member(guild_member)

        # 更新玩家公会ID
        player.guild_id = new_guild.id
        await self._player_repo.update(player)

        return True, "公会创建成功", new_guild

    async def join_guild(self, player_id: str, guild_id: int) -> Tuple[bool, str]:
        """加入公会"""
        player = await self._player_repo.get_by_id(player_id)
        if not player:
            return False, "玩家不存在"

        if player.guild_id:
            return False, "你已经加入了公会"

        guild = await self._guild_repo.get_by_id(guild_id)
        if not guild:
            return False, "公会不存在"

        # 检查公会容量
        member_count = await self._guild_repo.get_member_count(guild_id)
        max_capacity = self.get_guild_capacity(guild.level)

        if member_count >= max_capacity:
            return False, "公会人数已满"

        # 创建成员记录
        guild_member = GuildMember(
            guild_id=guild_id,
            player_id=player_id,
            position=GuildPosition.MEMBER,
            joined_at=datetime.now()
        )
        await self._guild_repo.add_member(guild_member)

        # 更新玩家公会ID
        player.guild_id = guild_id
        await self._player_repo.update(player)

        return True, "成功加入公会"

    async def leave_guild(self, player_id: str) -> Tuple[bool, str]:
        """退出公会"""
        player = await self._player_repo.get_by_id(player_id)
        if not player or not player.guild_id:
            return False, "你未加入任何公会"

        # 检查是否为会长
        # 注意: GuildPermission.get_member_position需要session,这里需要UoW
        if not self._uow:
            raise ValueError("leave_guild需要UoW以访问GuildPermission")

        position = await GuildPermission.get_member_position(
            self._uow.session, player_id, player.guild_id
        )
        if position == GuildPosition.PRESIDENT:
            return False, "会长不能直接退出公会，请先转让会长职位或解散公会"

        # 删除成员记录
        await self._guild_repo.remove_member(player.guild_id, player_id)

        # 清空玩家公会相关数据
        player.guild_id = None
        player.guild_contribution = 0
        player.gold2 = 0
        await self._player_repo.update(player)

        return True, "成功退出公会"

    async def set_member_position(
        self,
        operator_id: str,
        guild_id: int,
        target_id: str,
        new_position: GuildPosition
    ) -> Tuple[bool, str]:
        """设置成员职位"""
        if not self._uow:
            raise ValueError("set_member_position需要UoW以访问GuildPermission和session")

        # 权限检查
        can_manage, reason = await GuildPermission.can_manage_position(
            self._uow.session, operator_id, guild_id, new_position
        )
        if not can_manage:
            return False, reason

        # 检查职位人数限制
        can_set, limit_reason = await GuildPermission.check_position_limit(
            self._uow.session, guild_id, new_position
        )
        if not can_set:
            return False, limit_reason

        # 获取目标成员记录
        member = await self._guild_repo.get_member(guild_id, target_id)
        if not member:
            return False, "目标不是该公会成员"

        # 更新职位
        old_position = member.position
        member.position = new_position
        # 直接使用session.add (因为Repository没有update_member方法)
        self._uow.session.add(member)

        old_name = GuildPermission.get_position_display_name(old_position)
        new_name = GuildPermission.get_position_display_name(new_position)

        return True, f"职位已从{old_name}变更为{new_name}"

    async def transfer_president(
        self,
        current_president_id: str,
        new_president_id: str,
        guild_id: int
    ) -> Tuple[bool, str]:
        """转让会长职位"""
        if not self._uow:
            raise ValueError("transfer_president需要UoW以访问GuildPermission和session")

        # 检查当前操作者是否为会长
        current_position = await GuildPermission.get_member_position(
            self._uow.session, current_president_id, guild_id
        )
        if current_position != GuildPosition.PRESIDENT:
            return False, "只有会长才能转让职位"

        # 检查目标是否为公会成员
        target_position = await GuildPermission.get_member_position(
            self._uow.session, new_president_id, guild_id
        )
        if not target_position:
            return False, "目标不是该公会成员"

        # 更新公会会长ID
        guild = await self._guild_repo.get_by_id(guild_id)
        guild.president_id = new_president_id
        await self._guild_repo.update(guild)

        # 更新成员职位记录
        # 原会长变为副会长
        old_president_member = await self._guild_repo.get_member(guild_id, current_president_id)
        old_president_member.position = GuildPosition.VICE_PRESIDENT
        self._uow.session.add(old_president_member)

        # 新会长设为会长
        new_president_member = await self._guild_repo.get_member(guild_id, new_president_id)
        new_president_member.position = GuildPosition.PRESIDENT
        self._uow.session.add(new_president_member)

        return True, "会长职位转让成功"

    async def get_member_count(self, guild_id: int) -> int:
        """获取公会成员数量"""
        return await self._guild_repo.get_member_count(guild_id)

    @staticmethod
    def get_guild_capacity(level: int) -> int:
        """获取公会容量 (静态方法,无需依赖注入)"""
        return 10 + (level - 1) * 5

    async def kick_member(
        self,
        operator_id: str,
        guild_id: int,
        target_uid: int
    ) -> Tuple[bool, str]:
        """踢出公会成员"""
        if not self._uow:
            raise ValueError("kick_member需要UoW以访问GuildPermission")

        # 根据UID查找目标玩家
        target_player = await self._player_repo.get_by_uid(target_uid)
        if not target_player:
            return False, "未找到该UID的玩家"

        # 检查目标是否在同一公会
        if target_player.guild_id != guild_id:
            return False, "该玩家不在你的公会中"

        # 权限检查
        can_kick, reason = await GuildPermission.can_kick_member(
            self._uow.session, operator_id, guild_id, target_player.id
        )
        if not can_kick:
            return False, reason

        # 删除成员记录
        await self._guild_repo.remove_member(guild_id, target_player.id)

        # 清空玩家公会相关数据
        target_player.guild_id = None
        target_player.guild_contribution = 0
        target_player.gold2 = 0
        await self._player_repo.update(target_player)

        return True, f"已将 {target_player.nickname}[UID:{target_uid}] 踢出公会"

    async def get_guild_members(self, guild_id: int) -> List[dict]:
        """
        获取公会成员列表

        注意: 这个方法需要复杂查询,暂时使用UoW的session直接查询
        TODO: 未来可以考虑在GuildRepository中添加专门的查询方法
        """
        if not self._uow:
            raise ValueError("get_guild_members需要UoW以执行复杂查询")

        from sqlalchemy import select, case
        from ..models.player import Player

        # 定义职位优先级
        position_priority = case(
            (GuildMember.position == GuildPosition.PRESIDENT, 1),
            (GuildMember.position == GuildPosition.VICE_PRESIDENT, 2),
            (GuildMember.position == GuildPosition.CORE_MEMBER, 3),
            (GuildMember.position == GuildPosition.MEMBER, 4),
            else_=5
        )

        stmt = select(GuildMember, Player).join(
            Player, GuildMember.player_id == Player.id
        ).where(GuildMember.guild_id == guild_id).order_by(
            position_priority.asc(), Player.guild_contribution.desc(), Player.level.desc()
        )

        results = (await self._uow.session.execute(stmt)).all()
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
