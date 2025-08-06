"""
公会任务系统服务
"""
from typing import List, Dict, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from datetime import date, datetime, timedelta
from ..models.player import Player
from ..models.guild import Guild
from .guild_economy_service import GuildEconomyService


class GuildTaskService:
    """公会任务服务类"""
    
    # 任务配置
    DAILY_TASKS = {
        "daily_sign": {
            "name": "每日签到",
            "description": "每日签到一次（已整合到普通签到中）",
            "points_reward": 100,
            "base_exp": 100,  # 基础经验，会根据公会倍率动态计算
            "max_per_day": 1
        },
        "daily_donation": {
            "name": "每日捐献",
            "description": "向公会捐献任意金额（额外奖励）",
            "points_reward": 30,  # 额外奖励30积分
            "base_exp": 30,       # 额外奖励30基础经验
            "max_per_day": 1
        },
        "exploration": {
            "name": "世界探索",
            "description": "在世界地图中探索10个格子",
            "points_reward": 80,
            "base_exp": 80,  # 基础经验，会根据公会倍率动态计算
            "max_per_day": 1,
            "requirement": 10
        },
        "combat_victory": {
            "name": "战斗胜利",
            "description": "在战斗中获得5次胜利",
            "points_reward": 120,
            "base_exp": 120,  # 基础经验，会根据公会倍率动态计算
            "max_per_day": 1,
            "requirement": 5
        }
    }
    
    WEEKLY_TASKS = {
        "weekly_contribution": {
            "name": "以恶鬼身，行菩萨事",
            "description": "一周内累计镇压鬼怪5个",
            "points_reward": 500,
            "base_exp": 500,  # 基础经验，会根据公会倍率动态计算
            "max_per_week": 1,
            "requirement": 50000
        },
        "weekly_active": {
            "name": "周活跃成员",
            "description": "一周内完成20个日常任务",
            "points_reward": 400,
            "base_exp": 400,  # 基础经验，会根据公会倍率动态计算
            "max_per_week": 1,
            "requirement": 20
        }
    }
    

    
    @staticmethod
    async def complete_exploration_task(session: AsyncSession, player_id: str, exploration_count: int) -> Tuple[bool, str, Dict]:
        """完成探索任务"""
        player = await session.get(Player, player_id)
        if not player or not player.guild_id:
            return False, "你未加入任何公会", {}
        
        task_config = GuildTaskService.DAILY_TASKS["exploration"]
        required_count = task_config["requirement"]
        
        if exploration_count < required_count:
            return False, f"探索次数不足，需要{required_count}次", {}
        
        # 检查今日是否已完成
        # 这里简化处理，实际应该有任务完成记录表
        today = date.today()
        
        # 奖励积分和公会经验
        points_reward = task_config["points_reward"]
        base_exp = task_config["base_exp"]
        player.gold2 += points_reward
        player.guild_contribution += points_reward  # 累计贡献增加

        guild_exp_gained = await GuildEconomyService.add_guild_experience(
            session, player.guild_id, base_exp
        )

        session.add(player)

        result = {
            "points_gained": points_reward,
            "guild_exp_gained": guild_exp_gained,
            "task_name": task_config["name"]
        }

        return True, f"探索任务完成！获得{points_reward}积分，公会经验+{guild_exp_gained}", result
    
    @staticmethod
    async def complete_combat_task(session: AsyncSession, player_id: str, victory_count: int) -> Tuple[bool, str, Dict]:
        """完成战斗任务"""
        player = await session.get(Player, player_id)
        if not player or not player.guild_id:
            return False, "你未加入任何公会", {}
        
        task_config = GuildTaskService.DAILY_TASKS["combat_victory"]
        required_count = task_config["requirement"]
        
        if victory_count < required_count:
            return False, f"胜利次数不足，需要{required_count}次", {}
        
        # 奖励积分和公会经验
        points_reward = task_config["points_reward"]
        base_exp = task_config["base_exp"]
        player.gold2 += points_reward
        player.guild_contribution += points_reward  # 累计贡献增加

        guild_exp_gained = await GuildEconomyService.add_guild_experience(
            session, player.guild_id, base_exp
        )

        session.add(player)

        result = {
            "points_gained": points_reward,
            "guild_exp_gained": guild_exp_gained,
            "task_name": task_config["name"]
        }

        return True, f"战斗任务完成！获得{points_reward}积分，公会经验+{guild_exp_gained}", result

    @staticmethod
    async def complete_daily_donation_task(session: AsyncSession, player_id: str) -> Tuple[bool, str, Dict]:
        """完成每日捐献任务（在捐献时自动触发）"""
        player = await session.get(Player, player_id)
        if not player or not player.guild_id:
            return False, "你未加入任何公会", {}

        # 检查今日是否已完成捐献任务
        today = date.today()
        # 这里简化处理，实际应该有任务完成记录表
        # 暂时通过检查今日捐献次数来判断是否已完成任务
        from ..models.donation_log import PlayerDonationLog
        from sqlalchemy import select, func

        stmt = select(func.count(PlayerDonationLog.id)).where(
            PlayerDonationLog.player_id == player_id,
            PlayerDonationLog.donate_date == today
        )
        donation_count = (await session.execute(stmt)).scalar_one()

        # 只有第一次捐献时才能完成每日捐献任务
        if donation_count != 1:
            return False, "每日捐献任务已完成或尚未捐献", {}

        task_config = GuildTaskService.DAILY_TASKS["daily_donation"]
        points_reward = task_config["points_reward"]
        base_exp = task_config["base_exp"]

        # 奖励积分和公会经验
        player.gold2 += points_reward
        player.guild_contribution += points_reward  # 累计贡献增加

        guild_exp_gained = await GuildEconomyService.add_guild_experience(
            session, player.guild_id, base_exp
        )

        session.add(player)

        result = {
            "points_gained": points_reward,
            "guild_exp_gained": guild_exp_gained,
            "task_name": task_config["name"]
        }

        return True, f"每日捐献任务完成！额外获得{points_reward}积分，公会经验+{guild_exp_gained}", result
    
    @staticmethod
    async def get_available_tasks(session: AsyncSession, player_id: str) -> List[Dict]:
        """获取玩家可用的任务列表"""
        player = await session.get(Player, player_id)
        if not player or not player.guild_id:
            return []
        
        available_tasks = []
        today = date.today()
        
        # 日常任务
        for task_id, task_config in GuildTaskService.DAILY_TASKS.items():
            # 检查是否已完成（简化处理）
            completed = False
            if task_id == "daily_sign":
                completed = player.last_sign and player.last_sign.date() == today
            elif task_id == "daily_donation":
                # 检查今日是否已捐献（完成捐献任务）
                from ..models.donation_log import PlayerDonationLog
                stmt = select(func.count(PlayerDonationLog.id)).where(
                    PlayerDonationLog.player_id == player.id,
                    PlayerDonationLog.donate_date == today
                )
                donation_count = (await session.execute(stmt)).scalar_one()
                completed = donation_count > 0

            available_tasks.append({
                "id": task_id,
                "name": task_config["name"],
                "description": task_config["description"],
                "points_reward": task_config["points_reward"],
                "base_exp": task_config["base_exp"],
                "type": "daily",
                "completed": completed,
                "requirement": task_config.get("requirement", 1)
            })
        
        # 周常任务
        for task_id, task_config in GuildTaskService.WEEKLY_TASKS.items():
            available_tasks.append({
                "id": task_id,
                "name": task_config["name"],
                "description": task_config["description"],
                "points_reward": task_config["points_reward"],
                "base_exp": task_config["base_exp"],
                "type": "weekly",
                "completed": False,  # 简化处理
                "requirement": task_config.get("requirement", 1)
            })
        
        return available_tasks
    
    @staticmethod
    async def get_guild_task_summary(session: AsyncSession, guild_id: int) -> Dict:
        """获取公会任务完成情况汇总"""
        # 获取公会成员数量
        stmt = select(func.count(Player.id)).where(Player.guild_id == guild_id)
        member_count = (await session.execute(stmt)).scalar_one()
        
        # 今日签到人数（简化处理）
        today = date.today()
        stmt = select(func.count(Player.id)).where(
            and_(
                Player.guild_id == guild_id,
                func.date(Player.last_sign) == today
            )
        )
        signed_today = (await session.execute(stmt)).scalar_one()
        
        return {
            "member_count": member_count,
            "signed_today": signed_today,
            "sign_rate": signed_today / member_count if member_count > 0 else 0,
            "active_level": "高" if signed_today / member_count > 0.8 else "中" if signed_today / member_count > 0.5 else "低"
        }
