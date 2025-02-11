from nonebot import on_command, require
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from nonebot.params import CommandArg
from typing import Dict, Optional
from datetime import datetime, timedelta
from ..data.db import safe_session
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from ..models.team import Team, TeamMember
from nonebot_plugin_apscheduler import scheduler
from nonebot.log import logger
from ..models.player import get_player_by_uid
from ..battle.core import BattleType
from .core import _player_battles
from ..models.player import Player

# 组队命令
team_cmd = on_command("队伍", block=True, priority=5)
join_cmd = on_command("加入队伍", block=True, priority=5)
disband_cmd = on_command("解散队伍", block=True, priority=5)
leave_cmd = on_command("退出队伍", block=True, priority=5)
kick_cmd = on_command("踢出", block=True, priority=5)
mode_cmd = on_command("模式", block=True, priority=5)

# 组队系统缓存
_team_invitations: Dict[int, Dict[str, datetime]] = {}  # {队伍ID: {受邀者ID: 过期时间}}

# 新增定时清理任务
@scheduler.scheduled_job("interval", minutes=1)
def _clean_expired_invitations():
    now = datetime.now()
    expired_count = 0
    for team_id in list(_team_invitations.keys()):
        invites = _team_invitations[team_id]
        # 保留未过期的邀请
        valid_invites = {k: v for k, v in invites.items() if v > now}
        if valid_invites:
            _team_invitations[team_id] = valid_invites
        else:
            del _team_invitations[team_id]
            expired_count += 1
    logger.info(f"🧹 已清理过期邀请，本次清理{expired_count}个过期队伍邀请")

# 组队功能
class TeamManager:
    """基于数据库的组队管理器"""
    async def create_team(self, session: AsyncSession, leader_id: str) -> Team:
        # 检查唯一约束
        existing = await session.execute(
            select(Team).where(Team.leader_id == leader_id)
        )
        if existing.scalars().first():
            raise ValueError("每个玩家只能创建一个队伍")
        
        new_team = Team(leader_id=leader_id)
        session.add(new_team)
        await session.flush()  # 获取自动生成的team_id
        
        # 添加队长为成员
        session.add(TeamMember(team_id=new_team.id, player_id=leader_id))
        await session.commit()
        return new_team

    async def join_team(self, session: AsyncSession, team_id: int, member_id: str) -> bool:
        # 新增检查：是否已加入其他队伍
        existing_member = await session.execute(
            select(TeamMember).where(TeamMember.player_id == member_id)
        )
        if existing_member.scalars().first():
            raise ValueError("你已加入其他队伍，请先退出")

        # 检查邀请有效性
        if not self._is_valid_invitation(team_id, member_id):
            print(f"邀请无效: {team_id}, {member_id}")
            return False
        
        # 检查是否已在队伍中
        existing = await session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.player_id == member_id
            )
        )
        if existing.scalars().first():
            return False
        
        # 添加成员
        session.add(TeamMember(team_id=team_id, player_id=member_id))
        await session.commit()
        
        # 加入成功后移除对应邀请
        if team_id in _team_invitations and member_id in _team_invitations[team_id]:
            del _team_invitations[team_id][member_id]
            if not _team_invitations[team_id]:
                del _team_invitations[team_id]
        
        return True

    async def get_team(self, session: AsyncSession, team_id: int) -> Optional[Team]:
        result = await session.execute(
            select(Team)
            .options(joinedload(Team.members).joinedload(TeamMember.player))
            .where(Team.id == team_id)
        )
        return result.scalars().first()

    def _is_valid_invitation(self, team_id: int, member_id: str) -> bool:
        """检查邀请是否有效"""
        now = datetime.now()
        print(f"检查邀请: {team_id}, {member_id}, {_team_invitations[team_id]}")
        return (
            team_id in _team_invitations and 
            member_id in _team_invitations[team_id] and 
            _team_invitations[team_id][member_id] > now
        )

    async def disband_team(self, session: AsyncSession, team_id: int):
        """解散队伍"""
        # 删除队伍和成员
        await session.execute(delete(TeamMember).where(TeamMember.team_id == team_id))
        await session.execute(delete(Team).where(Team.id == team_id))
        # 清理邀请缓存
        _team_invitations.pop(team_id, None)
        await session.commit()

    async def leave_team(self, session: AsyncSession, user_id: str) -> bool:
        """退出队伍，返回是否成功"""
        # 获取用户所在队伍
        member = await session.execute(
            select(TeamMember)
            .options(joinedload(TeamMember.team))
            .where(TeamMember.player_id == user_id)
        )
        member = member.scalars().first()
        if not member:
            return False

        team = member.team
        if team.leader_id == user_id:  # 队长退出等于解散队伍
            await self.disband_team(session, team.id)
            return True
        else:  # 普通成员退出
            await session.delete(member)
            await session.commit()
            return True

    async def kick_member(self, session: AsyncSession, leader_id: str, target_uid: str) -> bool:
        """踢出队员"""
        # 验证操作者是队长
        team = await session.execute(
            select(Team).where(Team.leader_id == leader_id)
        )
        team = team.scalars().first()
        if not team:
            return False

        # 删除目标成员
        result = await session.execute(
            delete(TeamMember)
            .where(TeamMember.team_id == team.id)
            .where(TeamMember.player_id == target_uid)
        )
        if result.rowcount == 0:
            return False
        await session.commit()
        return True

    async def can_start_team_explore(self, session: AsyncSession, team_id: int) -> bool:
        """检查队伍是否可以开始探索"""
        team = await self.get_team(session, team_id)
        if not team:
            return False

        # 检查所有队员状态
        for member in team.members:
            player = member.player
            if (player.explore_mode != BattleType.TEAM or 
                player.id in _player_battles or  # 通过缓存检查战斗状态
                player.position != team.leader.position):
                return False
        return True

team_manager = TeamManager()

# 优化组队命令处理
@team_cmd.handle()
async def handle_team(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()
    user_id = event.get_user_id()
    
    async with safe_session() as session:
        if arg == "创建":
            try:
                team = await team_manager.create_team(session, user_id)
                msg = f"🎉 队伍创建成功！队伍ID：{team.id}"
            except ValueError as e:
                msg = f"⛔ {str(e)}"
            await team_cmd.finish(msg)
            
        elif arg.startswith("邀请"):
            target_uid = arg[2:].strip()
            # 获取当前用户的队伍
            team = await session.execute(
                select(Team).where(Team.leader_id == user_id)
            )
            team = team.scalars().first()
            if not team:
                await team_cmd.finish("⛔ 请先创建队伍")
            target_player = await get_player_by_uid(target_uid)
            if not target_player:
                await team_cmd.finish("⛔ 目标玩家不存在")

            # 存储到内存邀请缓存（保留3分钟）
            _team_invitations.setdefault(team.id, {})
            _team_invitations[team.id][target_player.id] = datetime.now() + timedelta(minutes=3)
            await team_cmd.finish(f"📨 已向玩家 {target_uid} 发送组队邀请，有效期3分钟\n 队伍ID：{team.id}")

        elif arg == "解散":
            # 获取用户队伍
            team = await session.execute(
                select(Team).where(Team.leader_id == user_id)
            )
            team = team.scalars().first()
            if not team:
                await team_cmd.finish("⛔ 你还没有创建队伍")
                return
            
            await team_manager.disband_team(session, team.id)
            await team_cmd.finish("🗑️ 队伍已解散")

@join_cmd.handle()
async def handle_join(event: MessageEvent, args: Message = CommandArg()):
    user_id = event.get_user_id()
    arg = args.extract_plain_text().strip()
    
    if not arg.isdigit():
        await join_cmd.finish("⛔ 请输入正确的队伍ID")
    team_id = int(arg)
    
    async with safe_session() as session:
        team = await team_manager.get_team(session, team_id)
        if not team:
            await join_cmd.finish("⛔ 队伍不存在")
            
        if await team_manager.join_team(session, team_id, user_id):
            # 获取队伍成员信息
            members = [m.player.nickname for m in team.members]
            await join_cmd.finish(f"✅ 成功加入队伍！队伍成员：{'、'.join(members)}")
        else:
            await join_cmd.finish("⛔ 加入失败，请确认邀请是否有效")

@disband_cmd.handle()
async def handle_disband(event: MessageEvent):
    user_id = event.get_user_id()
    async with safe_session() as session:
        # 获取用户队伍
        team = await session.execute(
            select(Team).where(Team.leader_id == user_id)
        )
        team = team.scalars().first()
        if not team:
            await disband_cmd.finish("⛔ 你还没有创建队伍或不是队长")
            return

        await team_manager.disband_team(session, team.id)
        await disband_cmd.finish("🗑️ 队伍已解散")

@leave_cmd.handle()
async def handle_leave(event: MessageEvent):
    user_id = event.get_user_id()
    async with safe_session() as session:
        success = await team_manager.leave_team(session, user_id)
        if not success:
            await leave_cmd.finish("⛔ 你当前没有加入任何队伍")
            return
        await leave_cmd.finish("🚪 你已退出队伍")

@kick_cmd.handle()
async def handle_kick(event: MessageEvent, args: Message = CommandArg()):
    target_uid = args.extract_plain_text().strip()
    if not target_uid.isdigit():
        await kick_cmd.finish("⛔ 请输入正确的UID")
    
    user_id = event.get_user_id()
    async with safe_session() as session:
        success = await team_manager.kick_member(session, user_id, target_uid)
        if not success:
            await kick_cmd.finish("⛔ 踢出失败，请确认你是队长且目标在队伍中")
            return
        await kick_cmd.finish(f"👢 已踢出玩家 {target_uid}")

@mode_cmd.handle()
async def handle_mode(event: MessageEvent, args: Message = CommandArg()):
    mode_map = {
        "个人": BattleType.SOLO,
        "组队": BattleType.TEAM
    }
    
    mode = args.extract_plain_text().strip()
    if mode not in mode_map:
        await mode_cmd.finish("⛔ 无效模式，可选：个人/组队")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        player.explore_mode = mode_map[mode]
        await session.commit()
        
    await mode_cmd.finish(f"✅ 已切换为【{mode}】探索模式")
