"""
公会任务系统服务
"""
from typing import List, Dict, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from datetime import date, datetime, timedelta
from ..models.player import Player
from ..models.guild import Guild
from ..models.guild_task_record import GuildTaskRecord, GuildTaskType, PlayerTaskStats
from .guild_economy_service import GuildEconomyService


class GuildTaskService:
    """公会任务服务类"""
    
    # 任务配置
    DAILY_TASKS = {
        "daily_sign": {
            "name": "每日签到",
            "description": "每日签到一次",
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
            "name": "诡域探索",
            "description": "在任意诡域中探索20个格子",
            "points_reward": 50,
            "base_exp": 50,  # 基础经验，会根据公会倍率动态计算
            "max_per_day": 1,
            "requirement": 20
        },
        "combat_victory": {
            "name": "杀诡达人",
            "description": "在诡域战斗中获得10次胜利",
            "points_reward": 100,
            "base_exp": 100,  # 基础经验，会根据公会倍率动态计算
            "max_per_day": 1,
            "requirement": 10
        }
    }
    
    WEEKLY_TASKS = {
        "weekly_active": {
            "name": "周活跃成员",
            "description": "一周内完成20个日常任务",
            "points_reward": 300,
            "base_exp": 300,  # 基础经验，会根据公会倍率动态计算
            "max_per_week": 1,
            "requirement": 20
        },
        "weekly_commission": {
            "name": "以恶鬼身，行菩萨事",
            "description": "一周完成10次委托",
            "points_reward": 300,
            "base_exp": 300,  # 基础经验，会根据公会倍率动态计算
            "max_per_week": 1,
            "requirement": 10
        }
    }

    @staticmethod
    async def get_or_create_player_stats(session: AsyncSession, player_id: str) -> PlayerTaskStats:
        """获取或创建玩家任务统计"""
        stmt = select(PlayerTaskStats).where(PlayerTaskStats.player_id == player_id)
        stats = (await session.execute(stmt)).scalar_one_or_none()

        if not stats:
            stats = PlayerTaskStats(
                player_id=player_id,
                total_explorations=0,
                total_combat_victories=0,
                total_commissions=0,
                today_explorations=0,
                today_combat_victories=0,
                today_commissions=0,
                week_commissions=0,
                week_daily_tasks=0
            )
            session.add(stats)
            await session.flush()  # 确保获得ID

        # 重置过期的统计数据
        stats.reset_daily_stats()
        stats.reset_weekly_stats()
        session.add(stats)

        return stats

    @staticmethod
    async def record_task_completion(session: AsyncSession, player_id: str, guild_id: int,
                                   task_type: GuildTaskType, points_reward: int,
                                   guild_exp_reward: int, progress: int = 1) -> None:
        """记录任务完成"""
        record = GuildTaskRecord(
            player_id=player_id,
            guild_id=guild_id,
            task_type=task_type,
            progress=progress,
            points_reward=points_reward,
            guild_exp_reward=guild_exp_reward
        )
        session.add(record)

    @staticmethod
    async def check_task_completed_today(session: AsyncSession, player_id: str,
                                       task_type: GuildTaskType) -> bool:
        """检查今日是否已完成指定任务"""
        today = date.today()
        stmt = select(func.count(GuildTaskRecord.id)).where(
            and_(
                GuildTaskRecord.player_id == player_id,
                GuildTaskRecord.task_type == task_type,
                GuildTaskRecord.task_date == today
            )
        )
        count = (await session.execute(stmt)).scalar_one()
        return count > 0

    @staticmethod
    async def update_exploration_stats(session: AsyncSession, player_id: str, count: int = 1) -> None:
        """更新探索统计"""
        stats = await GuildTaskService.get_or_create_player_stats(session, player_id)
        stats.total_explorations += count
        stats.today_explorations += count
        session.add(stats)

    @staticmethod
    async def update_combat_victory_stats(session: AsyncSession, player_id: str, count: int = 1) -> None:
        """更新战斗胜利统计"""
        stats = await GuildTaskService.get_or_create_player_stats(session, player_id)
        stats.total_combat_victories += count
        stats.today_combat_victories += count
        session.add(stats)

    @staticmethod
    async def update_commission_stats(session: AsyncSession, player_id: str, count: int = 1) -> None:
        """更新委托完成统计"""
        stats = await GuildTaskService.get_or_create_player_stats(session, player_id)
        stats.total_commissions += count
        stats.today_commissions += count
        stats.week_commissions += count
        session.add(stats)

    @staticmethod
    async def complete_exploration_task(session: AsyncSession, player_id: str) -> Tuple[bool, str, Dict]:
        """完成探索任务"""
        player = await session.get(Player, player_id)
        if not player or not player.guild_id:
            return False, "你未加入任何公会", {}

        # 检查今日是否已完成
        if await GuildTaskService.check_task_completed_today(session, player_id, GuildTaskType.EXPLORATION):
            return False, "今日探索任务已完成", {}

        # 获取玩家统计数据
        stats = await GuildTaskService.get_or_create_player_stats(session, player_id)
        task_config = GuildTaskService.DAILY_TASKS["exploration"]
        required_count = task_config["requirement"]

        if stats.today_explorations < required_count:
            return False, f"探索次数不足，需要{required_count}次，当前{stats.today_explorations}次", {}

        # 奖励积分和公会经验
        points_reward = task_config["points_reward"]
        base_exp = task_config["base_exp"]
        player.gold2 += points_reward
        player.guild_contribution += points_reward  # 累计贡献增加

        guild_exp_gained = await GuildEconomyService.add_guild_experience(
            session, player.guild_id, base_exp
        )

        # 记录任务完成
        await GuildTaskService.record_task_completion(
            session, player_id, player.guild_id, GuildTaskType.EXPLORATION,
            points_reward, guild_exp_gained
        )

        session.add(player)

        result = {
            "points_gained": points_reward,
            "guild_exp_gained": guild_exp_gained,
            "task_name": task_config["name"]
        }

        return True, f"探索任务完成！获得{points_reward}积分，公会经验+{guild_exp_gained}", result
    
    @staticmethod
    async def complete_combat_task(session: AsyncSession, player_id: str) -> Tuple[bool, str, Dict]:
        """完成战斗任务"""
        player = await session.get(Player, player_id)
        if not player or not player.guild_id:
            return False, "你未加入任何公会", {}

        # 检查今日是否已完成
        if await GuildTaskService.check_task_completed_today(session, player_id, GuildTaskType.COMBAT_VICTORY):
            return False, "今日战斗任务已完成", {}

        # 获取玩家统计数据
        stats = await GuildTaskService.get_or_create_player_stats(session, player_id)
        task_config = GuildTaskService.DAILY_TASKS["combat_victory"]
        required_count = task_config["requirement"]

        if stats.today_combat_victories < required_count:
            return False, f"胜利次数不足，需要{required_count}次，当前{stats.today_combat_victories}次", {}

        # 奖励积分和公会经验
        points_reward = task_config["points_reward"]
        base_exp = task_config["base_exp"]
        player.gold2 += points_reward
        player.guild_contribution += points_reward  # 累计贡献增加

        guild_exp_gained = await GuildEconomyService.add_guild_experience(
            session, player.guild_id, base_exp
        )

        # 记录任务完成
        await GuildTaskService.record_task_completion(
            session, player_id, player.guild_id, GuildTaskType.COMBAT_VICTORY,
            points_reward, guild_exp_gained
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
        if await GuildTaskService.check_task_completed_today(session, player_id, GuildTaskType.DAILY_DONATION):
            return False, "每日捐献任务已完成", {}

        # 检查今日是否已捐献（通过捐献日志确认）
        today = date.today()
        from ..models.donation_log import PlayerDonationLog

        stmt = select(func.count(PlayerDonationLog.id)).where(
            PlayerDonationLog.player_id == player_id,
            PlayerDonationLog.donate_date == today
        )
        donation_count = (await session.execute(stmt)).scalar_one()

        # 只有已捐献时才能完成每日捐献任务
        if donation_count == 0:
            return False, "请先进行捐献", {}

        task_config = GuildTaskService.DAILY_TASKS["daily_donation"]
        points_reward = task_config["points_reward"]
        base_exp = task_config["base_exp"]

        # 奖励积分和公会经验
        player.gold2 += points_reward
        player.guild_contribution += points_reward  # 累计贡献增加

        guild_exp_gained = await GuildEconomyService.add_guild_experience(
            session, player.guild_id, base_exp
        )

        # 记录任务完成
        await GuildTaskService.record_task_completion(
            session, player_id, player.guild_id, GuildTaskType.DAILY_DONATION,
            points_reward, guild_exp_gained
        )

        # 更新日常任务完成统计
        await GuildTaskService.update_daily_task_completion_stats(session, player_id)

        session.add(player)

        result = {
            "points_gained": points_reward,
            "guild_exp_gained": guild_exp_gained,
            "task_name": task_config["name"]
        }

        return True, f"每日捐献任务完成！额外获得{points_reward}积分，公会经验+{guild_exp_gained}", result

    @staticmethod
    async def complete_weekly_active_task(session: AsyncSession, player_id: str) -> Tuple[bool, str, Dict]:
        """完成周活跃成员任务"""
        player = await session.get(Player, player_id)
        if not player or not player.guild_id:
            return False, "你未加入任何公会", {}

        # 检查本周是否已完成
        if await GuildTaskService.check_task_completed_this_week(session, player_id, GuildTaskType.WEEKLY_ACTIVE):
            return False, "本周活跃任务已完成", {}

        # 获取玩家统计数据
        stats = await GuildTaskService.get_or_create_player_stats(session, player_id)
        task_config = GuildTaskService.WEEKLY_TASKS["weekly_active"]
        required_count = task_config["requirement"]

        if stats.week_daily_tasks < required_count:
            return False, f"本周日常任务完成次数不足，需要{required_count}次，当前{stats.week_daily_tasks}次", {}

        # 奖励积分和公会经验
        points_reward = task_config["points_reward"]
        base_exp = task_config["base_exp"]
        player.gold2 += points_reward
        player.guild_contribution += points_reward  # 累计贡献增加

        guild_exp_gained = await GuildEconomyService.add_guild_experience(
            session, player.guild_id, base_exp
        )

        # 记录任务完成
        await GuildTaskService.record_task_completion(
            session, player_id, player.guild_id, GuildTaskType.WEEKLY_ACTIVE,
            points_reward, guild_exp_gained
        )

        session.add(player)

        result = {
            "points_gained": points_reward,
            "guild_exp_gained": guild_exp_gained,
            "task_name": task_config["name"]
        }

        return True, f"周活跃任务完成！获得{points_reward}积分，公会经验+{guild_exp_gained}", result

    @staticmethod
    async def complete_weekly_commission_task(session: AsyncSession, player_id: str) -> Tuple[bool, str, Dict]:
        """完成周委托任务"""
        player = await session.get(Player, player_id)
        if not player or not player.guild_id:
            return False, "你未加入任何公会", {}

        # 检查本周是否已完成
        if await GuildTaskService.check_task_completed_this_week(session, player_id, GuildTaskType.WEEKLY_COMMISSION):
            return False, "本周委托任务已完成", {}

        # 获取玩家统计数据
        stats = await GuildTaskService.get_or_create_player_stats(session, player_id)
        task_config = GuildTaskService.WEEKLY_TASKS["weekly_commission"]
        required_count = task_config["requirement"]

        if stats.week_commissions < required_count:
            return False, f"本周委托完成次数不足，需要{required_count}次，当前{stats.week_commissions}次", {}

        # 奖励积分和公会经验
        points_reward = task_config["points_reward"]
        base_exp = task_config["base_exp"]
        player.gold2 += points_reward
        player.guild_contribution += points_reward  # 累计贡献增加

        guild_exp_gained = await GuildEconomyService.add_guild_experience(
            session, player.guild_id, base_exp
        )

        # 记录任务完成
        await GuildTaskService.record_task_completion(
            session, player_id, player.guild_id, GuildTaskType.WEEKLY_COMMISSION,
            points_reward, guild_exp_gained
        )

        session.add(player)

        result = {
            "points_gained": points_reward,
            "guild_exp_gained": guild_exp_gained,
            "task_name": task_config["name"]
        }

        return True, f"周委托任务完成！获得{points_reward}积分，公会经验+{guild_exp_gained}", result

    @staticmethod
    async def check_task_completed_this_week(session: AsyncSession, player_id: str,
                                           task_type: GuildTaskType) -> bool:
        """检查本周是否已完成指定任务"""
        today = date.today()
        # 计算本周一的日期
        days_since_monday = today.weekday()
        monday = today - timedelta(days=days_since_monday)

        stmt = select(func.count(GuildTaskRecord.id)).where(
            and_(
                GuildTaskRecord.player_id == player_id,
                GuildTaskRecord.task_type == task_type,
                GuildTaskRecord.task_date >= monday
            )
        )
        count = (await session.execute(stmt)).scalar_one()
        return count > 0

    @staticmethod
    async def get_available_tasks(session: AsyncSession, player_id: str) -> List[Dict]:
        """获取玩家可用的任务列表"""
        player = await session.get(Player, player_id)
        if not player or not player.guild_id:
            return []

        available_tasks = []
        stats = await GuildTaskService.get_or_create_player_stats(session, player_id)

        # 日常任务
        for task_id, task_config in GuildTaskService.DAILY_TASKS.items():
            completed = False
            progress = 0
            requirement = task_config.get("requirement", 1)

            if task_id == "daily_sign":
                completed = await GuildTaskService.check_task_completed_today(session, player_id, GuildTaskType.DAILY_SIGN)
                progress = 1 if (player.last_sign and player.last_sign.date() == date.today()) else 0
            elif task_id == "daily_donation":
                completed = await GuildTaskService.check_task_completed_today(session, player_id, GuildTaskType.DAILY_DONATION)
                # 检查今日是否已捐献
                from ..models.donation_log import PlayerDonationLog
                stmt = select(func.count(PlayerDonationLog.id)).where(
                    PlayerDonationLog.player_id == player_id,
                    PlayerDonationLog.donate_date == date.today()
                )
                progress = (await session.execute(stmt)).scalar_one()
            elif task_id == "exploration":
                completed = await GuildTaskService.check_task_completed_today(session, player_id, GuildTaskType.EXPLORATION)
                progress = stats.today_explorations
            elif task_id == "combat_victory":
                completed = await GuildTaskService.check_task_completed_today(session, player_id, GuildTaskType.COMBAT_VICTORY)
                progress = stats.today_combat_victories

            available_tasks.append({
                "id": task_id,
                "name": task_config["name"],
                "description": task_config["description"],
                "points_reward": task_config["points_reward"],
                "base_exp": task_config["base_exp"],
                "type": "daily",
                "completed": completed,
                "progress": progress,
                "requirement": requirement
            })

        # 周常任务
        for task_id, task_config in GuildTaskService.WEEKLY_TASKS.items():
            completed = False
            progress = 0
            requirement = task_config.get("requirement", 1)

            if task_id == "weekly_active":
                completed = await GuildTaskService.check_task_completed_this_week(session, player_id, GuildTaskType.WEEKLY_ACTIVE)
                progress = stats.week_daily_tasks
            elif task_id == "weekly_commission":
                completed = await GuildTaskService.check_task_completed_this_week(session, player_id, GuildTaskType.WEEKLY_COMMISSION)
                progress = stats.week_commissions

            available_tasks.append({
                "id": task_id,
                "name": task_config["name"],
                "description": task_config["description"],
                "points_reward": task_config["points_reward"],
                "base_exp": task_config["base_exp"],
                "type": "weekly",
                "completed": completed,
                "progress": progress,
                "requirement": requirement
            })

        return available_tasks

    @staticmethod
    async def update_daily_task_completion_stats(session: AsyncSession, player_id: str) -> None:
        """更新日常任务完成统计（用于周活跃任务）"""
        stats = await GuildTaskService.get_or_create_player_stats(session, player_id)
        stats.week_daily_tasks += 1
        session.add(stats)

    @staticmethod
    async def try_auto_complete_tasks(session: AsyncSession, player_id: str) -> List[str]:
        """尝试自动完成满足条件的任务"""
        player = await session.get(Player, player_id)
        if not player or not player.guild_id:
            return []

        completed_tasks = []

        # 检查探索任务
        success, message, _ = await GuildTaskService.complete_exploration_task(session, player_id)
        if success:
            completed_tasks.append(f"🗺️ {message}")
            await GuildTaskService.update_daily_task_completion_stats(session, player_id)

        # 检查战斗任务
        success, message, _ = await GuildTaskService.complete_combat_task(session, player_id)
        if success:
            completed_tasks.append(f"⚔️ {message}")
            await GuildTaskService.update_daily_task_completion_stats(session, player_id)

        # 检查周活跃任务
        success, message, _ = await GuildTaskService.complete_weekly_active_task(session, player_id)
        if success:
            completed_tasks.append(f"📅 {message}")

        # 检查周委托任务
        success, message, _ = await GuildTaskService.complete_weekly_commission_task(session, player_id)
        if success:
            completed_tasks.append(f"📋 {message}")

        return completed_tasks

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
