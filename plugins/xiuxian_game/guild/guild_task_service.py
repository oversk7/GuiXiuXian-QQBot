"""
公会任务系统服务 - DI架构版本

通过Repository抽象数据访问，支持依赖注入
"""
from typing import List, Dict, Tuple
from datetime import date
from ..models.player import Player
from ..models.guild_task_record import GuildTaskRecord, GuildTaskType
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.guild_repository import GuildRepository
from ..infrastructure.repositories.player_task_stats_repository import PlayerTaskStatsRepository
from ..infrastructure.repositories.guild_task_record_repository import GuildTaskRecordRepository
from ..infrastructure.repositories.player_donation_log_repository import PlayerDonationLogRepository
from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
from .guild_economy_service import GuildEconomyService


class GuildTaskService:
    """公会任务服务类 - DI架构版本"""

    # 任务配置（类常量，保持向后兼容）
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

    def __init__(
        self,
        player_repo: PlayerRepository,
        guild_repo: GuildRepository,
        player_task_stats_repo: PlayerTaskStatsRepository,
        guild_task_record_repo: GuildTaskRecordRepository,
        player_donation_log_repo: PlayerDonationLogRepository,
        guild_building_repo: GuildBuildingRepository,
    ):
        """
        初始化公会任务服务

        Args:
            player_repo: 玩家仓储
            guild_repo: 公会仓储
            player_task_stats_repo: 玩家任务统计仓储
            guild_task_record_repo: 公会任务记录仓储
            player_donation_log_repo: 玩家捐献日志仓储
            guild_building_repo: 公会建筑仓储（用于创建GuildEconomyService）
        """
        self._player_repo = player_repo
        self._guild_repo = guild_repo
        self._player_task_stats_repo = player_task_stats_repo
        self._guild_task_record_repo = guild_task_record_repo
        self._player_donation_log_repo = player_donation_log_repo
        self._guild_building_repo = guild_building_repo

    async def get_or_create_player_stats(self, player_id: str):
        """
        获取或创建玩家任务统计

        Args:
            player_id: 玩家ID

        Returns:
            PlayerTaskStats实例

        对应原代码:
            guild_task_service.py Line 71-96
        """
        return await self._player_task_stats_repo.get_or_create(player_id)

    async def record_task_completion(
        self, player_id: str, guild_id: int,
        task_type: GuildTaskType, points_reward: int,
        guild_exp_reward: int, progress: int = 1
    ) -> None:
        """
        记录任务完成

        Args:
            player_id: 玩家ID
            guild_id: 公会ID
            task_type: 任务类型
            points_reward: 积分奖励
            guild_exp_reward: 公会经验奖励
            progress: 任务进度（默认1）

        对应原代码:
            guild_task_service.py Line 99-111
        """
        record = GuildTaskRecord(
            player_id=player_id,
            guild_id=guild_id,
            task_type=task_type,
            progress=progress,
            points_reward=points_reward,
            guild_exp_reward=guild_exp_reward
        )
        await self._guild_task_record_repo.add(record)

    async def check_task_completed_today(
        self, player_id: str, task_type: GuildTaskType
    ) -> bool:
        """
        检查今日是否已完成指定任务

        Args:
            player_id: 玩家ID
            task_type: 任务类型

        Returns:
            是否已完成

        对应原代码:
            guild_task_service.py Line 114-126
        """
        return await self._guild_task_record_repo.check_task_completed_today(
            player_id, task_type
        )

    async def update_exploration_stats(self, player_id: str, count: int = 1) -> None:
        """
        更新探索统计

        Args:
            player_id: 玩家ID
            count: 增加数量（默认1）

        对应原代码:
            guild_task_service.py Line 129-134
        """
        await self._player_task_stats_repo.increment_exploration_stats(player_id, count)

    async def update_combat_victory_stats(self, player_id: str, count: int = 1) -> None:
        """
        更新战斗胜利统计

        Args:
            player_id: 玩家ID
            count: 增加数量（默认1）

        对应原代码:
            guild_task_service.py Line 137-142
        """
        await self._player_task_stats_repo.increment_combat_victory_stats(player_id, count)

    async def update_commission_stats(self, player_id: str, count: int = 1) -> None:
        """
        更新委托完成统计

        Args:
            player_id: 玩家ID
            count: 增加数量（默认1）

        对应原代码:
            guild_task_service.py Line 145-151
        """
        await self._player_task_stats_repo.increment_commission_stats(player_id, count)

    async def complete_exploration_task(self, player_id: str) -> Tuple[bool, str, Dict]:
        """
        完成探索任务

        Args:
            player_id: 玩家ID

        Returns:
            (是否成功, 消息, 结果字典)

        对应原代码:
            guild_task_service.py Line 154-196
        """
        player = await self._player_repo.get_by_id(player_id)
        if not player or not player.guild_id:
            return False, "你未加入任何公会", {}

        # 检查今日是否已完成
        if await self.check_task_completed_today(player_id, GuildTaskType.EXPLORATION):
            return False, "今日探索任务已完成", {}

        # 获取玩家统计数据
        stats = await self.get_or_create_player_stats(player_id)
        task_config = self.DAILY_TASKS["exploration"]
        required_count = task_config["requirement"]

        if stats.today_explorations < required_count:
            return False, f"探索次数不足，需要{required_count}次，当前{stats.today_explorations}次", {}

        # 奖励积分和公会经验
        points_reward = task_config["points_reward"]
        base_exp = task_config["base_exp"]
        player.gold2 += points_reward
        player.guild_contribution += points_reward  # 累计贡献增加

        # 调用GuildEconomyService添加公会经验
        guild_economy_service = GuildEconomyService(
            guild_repo=self._guild_repo,
            player_repo=self._player_repo,
            donation_log_repo=self._player_donation_log_repo,
            building_repo=self._guild_building_repo,
        )
        guild_exp_gained = await guild_economy_service.add_guild_experience(
            player.guild_id, base_exp
        )

        # 记录任务完成
        await self.record_task_completion(
            player_id, player.guild_id, GuildTaskType.EXPLORATION,
            points_reward, guild_exp_gained
        )

        await self._player_repo.update(player)

        result = {
            "points_gained": points_reward,
            "guild_exp_gained": guild_exp_gained,
            "task_name": task_config["name"]
        }

        return True, f"探索任务完成！获得{points_reward}积分，公会经验+{guild_exp_gained}", result

    async def complete_combat_task(self, player_id: str) -> Tuple[bool, str, Dict]:
        """
        完成战斗任务

        Args:
            player_id: 玩家ID

        Returns:
            (是否成功, 消息, 结果字典)

        对应原代码:
            guild_task_service.py Line 199-241
        """
        player = await self._player_repo.get_by_id(player_id)
        if not player or not player.guild_id:
            return False, "你未加入任何公会", {}

        # 检查今日是否已完成
        if await self.check_task_completed_today(player_id, GuildTaskType.COMBAT_VICTORY):
            return False, "今日战斗任务已完成", {}

        # 获取玩家统计数据
        stats = await self.get_or_create_player_stats(player_id)
        task_config = self.DAILY_TASKS["combat_victory"]
        required_count = task_config["requirement"]

        if stats.today_combat_victories < required_count:
            return False, f"胜利次数不足，需要{required_count}次，当前{stats.today_combat_victories}次", {}

        # 奖励积分和公会经验
        points_reward = task_config["points_reward"]
        base_exp = task_config["base_exp"]
        player.gold2 += points_reward
        player.guild_contribution += points_reward  # 累计贡献增加

        # 调用GuildEconomyService添加公会经验
        guild_economy_service = GuildEconomyService(
            guild_repo=self._guild_repo,
            player_repo=self._player_repo,
            donation_log_repo=self._player_donation_log_repo,
            building_repo=self._guild_building_repo,
        )
        guild_exp_gained = await guild_economy_service.add_guild_experience(
            player.guild_id, base_exp
        )

        # 记录任务完成
        await self.record_task_completion(
            player_id, player.guild_id, GuildTaskType.COMBAT_VICTORY,
            points_reward, guild_exp_gained
        )

        await self._player_repo.update(player)

        result = {
            "points_gained": points_reward,
            "guild_exp_gained": guild_exp_gained,
            "task_name": task_config["name"]
        }

        return True, f"战斗任务完成！获得{points_reward}积分，公会经验+{guild_exp_gained}", result

    async def complete_daily_donation_task(self, player_id: str) -> Tuple[bool, str, Dict]:
        """
        完成每日捐献任务（在捐献时自动触发）

        Args:
            player_id: 玩家ID

        Returns:
            (是否成功, 消息, 结果字典)

        对应原代码:
            guild_task_service.py Line 244-297
        """
        player = await self._player_repo.get_by_id(player_id)
        if not player or not player.guild_id:
            return False, "你未加入任何公会", {}

        # 检查今日是否已完成捐献任务
        if await self.check_task_completed_today(player_id, GuildTaskType.DAILY_DONATION):
            return False, "每日捐献任务已完成", {}

        # 检查今日是否已捐献（通过捐献日志确认）
        today = date.today()
        donation_count = await self._player_donation_log_repo.count_today_donations(player_id, today)

        # 只有已捐献时才能完成每日捐献任务
        if donation_count == 0:
            return False, "请先进行捐献", {}

        task_config = self.DAILY_TASKS["daily_donation"]
        points_reward = task_config["points_reward"]
        base_exp = task_config["base_exp"]

        # 奖励积分和公会经验
        player.gold2 += points_reward
        player.guild_contribution += points_reward  # 累计贡献增加

        # 调用GuildEconomyService添加公会经验
        guild_economy_service = GuildEconomyService(
            guild_repo=self._guild_repo,
            player_repo=self._player_repo,
            donation_log_repo=self._player_donation_log_repo,
            building_repo=self._guild_building_repo,
        )
        guild_exp_gained = await guild_economy_service.add_guild_experience(
            player.guild_id, base_exp
        )

        # 记录任务完成
        await self.record_task_completion(
            player_id, player.guild_id, GuildTaskType.DAILY_DONATION,
            points_reward, guild_exp_gained
        )

        # 更新日常任务完成统计
        await self.update_daily_task_completion_stats(player_id)

        await self._player_repo.update(player)

        result = {
            "points_gained": points_reward,
            "guild_exp_gained": guild_exp_gained,
            "task_name": task_config["name"]
        }

        return True, f"每日捐献任务完成！额外获得{points_reward}积分，公会经验+{guild_exp_gained}", result

    async def complete_weekly_active_task(self, player_id: str) -> Tuple[bool, str, Dict]:
        """
        完成周活跃成员任务

        Args:
            player_id: 玩家ID

        Returns:
            (是否成功, 消息, 结果字典)

        对应原代码:
            guild_task_service.py Line 300-342
        """
        player = await self._player_repo.get_by_id(player_id)
        if not player or not player.guild_id:
            return False, "你未加入任何公会", {}

        # 检查本周是否已完成
        if await self.check_task_completed_this_week(player_id, GuildTaskType.WEEKLY_ACTIVE):
            return False, "本周活跃任务已完成", {}

        # 获取玩家统计数据
        stats = await self.get_or_create_player_stats(player_id)
        task_config = self.WEEKLY_TASKS["weekly_active"]
        required_count = task_config["requirement"]

        if stats.week_daily_tasks < required_count:
            return False, f"本周日常任务完成次数不足，需要{required_count}次，当前{stats.week_daily_tasks}次", {}

        # 奖励积分和公会经验
        points_reward = task_config["points_reward"]
        base_exp = task_config["base_exp"]
        player.gold2 += points_reward
        player.guild_contribution += points_reward  # 累计贡献增加

        # 调用GuildEconomyService添加公会经验
        guild_economy_service = GuildEconomyService(
            guild_repo=self._guild_repo,
            player_repo=self._player_repo,
            donation_log_repo=self._player_donation_log_repo,
            building_repo=self._guild_building_repo,
        )
        guild_exp_gained = await guild_economy_service.add_guild_experience(
            player.guild_id, base_exp
        )

        # 记录任务完成
        await self.record_task_completion(
            player_id, player.guild_id, GuildTaskType.WEEKLY_ACTIVE,
            points_reward, guild_exp_gained
        )

        await self._player_repo.update(player)

        result = {
            "points_gained": points_reward,
            "guild_exp_gained": guild_exp_gained,
            "task_name": task_config["name"]
        }

        return True, f"周活跃任务完成！获得{points_reward}积分，公会经验+{guild_exp_gained}", result

    async def complete_weekly_commission_task(self, player_id: str) -> Tuple[bool, str, Dict]:
        """
        完成周委托任务

        Args:
            player_id: 玩家ID

        Returns:
            (是否成功, 消息, 结果字典)

        对应原代码:
            guild_task_service.py Line 345-387
        """
        player = await self._player_repo.get_by_id(player_id)
        if not player or not player.guild_id:
            return False, "你未加入任何公会", {}

        # 检查本周是否已完成
        if await self.check_task_completed_this_week(player_id, GuildTaskType.WEEKLY_COMMISSION):
            return False, "本周委托任务已完成", {}

        # 获取玩家统计数据
        stats = await self.get_or_create_player_stats(player_id)
        task_config = self.WEEKLY_TASKS["weekly_commission"]
        required_count = task_config["requirement"]

        if stats.week_commissions < required_count:
            return False, f"本周委托完成次数不足，需要{required_count}次，当前{stats.week_commissions}次", {}

        # 奖励积分和公会经验
        points_reward = task_config["points_reward"]
        base_exp = task_config["base_exp"]
        player.gold2 += points_reward
        player.guild_contribution += points_reward  # 累计贡献增加

        # 调用GuildEconomyService添加公会经验
        guild_economy_service = GuildEconomyService(
            guild_repo=self._guild_repo,
            player_repo=self._player_repo,
            donation_log_repo=self._player_donation_log_repo,
            building_repo=self._guild_building_repo,
        )
        guild_exp_gained = await guild_economy_service.add_guild_experience(
            player.guild_id, base_exp
        )

        # 记录任务完成
        await self.record_task_completion(
            player_id, player.guild_id, GuildTaskType.WEEKLY_COMMISSION,
            points_reward, guild_exp_gained
        )

        await self._player_repo.update(player)

        result = {
            "points_gained": points_reward,
            "guild_exp_gained": guild_exp_gained,
            "task_name": task_config["name"]
        }

        return True, f"周委托任务完成！获得{points_reward}积分，公会经验+{guild_exp_gained}", result

    async def check_task_completed_this_week(
        self, player_id: str, task_type: GuildTaskType
    ) -> bool:
        """
        检查本周是否已完成指定任务

        Args:
            player_id: 玩家ID
            task_type: 任务类型

        Returns:
            是否已完成

        对应原代码:
            guild_task_service.py Line 390-406
        """
        return await self._guild_task_record_repo.check_task_completed_this_week(
            player_id, task_type
        )

    async def get_available_tasks(self, player_id: str) -> List[Dict]:
        """
        获取玩家可用的任务列表

        Args:
            player_id: 玩家ID

        Returns:
            任务列表

        对应原代码:
            guild_task_service.py Line 409-480
        """
        player = await self._player_repo.get_by_id(player_id)
        if not player or not player.guild_id:
            return []

        available_tasks = []
        stats = await self.get_or_create_player_stats(player_id)

        # 日常任务
        for task_id, task_config in self.DAILY_TASKS.items():
            completed = False
            progress = 0
            requirement = task_config.get("requirement", 1)

            if task_id == "daily_sign":
                completed = await self.check_task_completed_today(player_id, GuildTaskType.DAILY_SIGN)
                progress = 1 if (player.last_sign and player.last_sign.date() == date.today()) else 0
            elif task_id == "daily_donation":
                completed = await self.check_task_completed_today(player_id, GuildTaskType.DAILY_DONATION)
                # 检查今日是否已捐献
                donation_count = await self._player_donation_log_repo.count_today_donations(
                    player_id, date.today()
                )
                progress = donation_count
            elif task_id == "exploration":
                completed = await self.check_task_completed_today(player_id, GuildTaskType.EXPLORATION)
                progress = stats.today_explorations
            elif task_id == "combat_victory":
                completed = await self.check_task_completed_today(player_id, GuildTaskType.COMBAT_VICTORY)
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
        for task_id, task_config in self.WEEKLY_TASKS.items():
            completed = False
            progress = 0
            requirement = task_config.get("requirement", 1)

            if task_id == "weekly_active":
                completed = await self.check_task_completed_this_week(player_id, GuildTaskType.WEEKLY_ACTIVE)
                progress = stats.week_daily_tasks
            elif task_id == "weekly_commission":
                completed = await self.check_task_completed_this_week(player_id, GuildTaskType.WEEKLY_COMMISSION)
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

    async def update_daily_task_completion_stats(self, player_id: str) -> None:
        """
        更新日常任务完成统计（用于周活跃任务）

        Args:
            player_id: 玩家ID

        对应原代码:
            guild_task_service.py Line 483-487
        """
        await self._player_task_stats_repo.increment_daily_task_completion(player_id)

    async def try_auto_complete_tasks(self, player_id: str) -> List[str]:
        """
        尝试自动完成满足条件的任务

        Args:
            player_id: 玩家ID

        Returns:
            已完成任务的消息列表

        对应原代码:
            guild_task_service.py Line 490-520
        """
        player = await self._player_repo.get_by_id(player_id)
        if not player or not player.guild_id:
            return []

        completed_tasks = []

        # 检查探索任务
        success, message, _ = await self.complete_exploration_task(player_id)
        if success:
            completed_tasks.append(f"🗺️ {message}")
            await self.update_daily_task_completion_stats(player_id)

        # 检查战斗任务
        success, message, _ = await self.complete_combat_task(player_id)
        if success:
            completed_tasks.append(f"⚔️ {message}")
            await self.update_daily_task_completion_stats(player_id)

        # 检查周活跃任务
        success, message, _ = await self.complete_weekly_active_task(player_id)
        if success:
            completed_tasks.append(f"📅 {message}")

        # 检查周委托任务
        success, message, _ = await self.complete_weekly_commission_task(player_id)
        if success:
            completed_tasks.append(f"📋 {message}")

        return completed_tasks

    async def get_guild_task_summary(self, guild_id: int) -> Dict:
        """获取公会任务完成情况汇总"""
        from sqlalchemy import select, func, and_
        from ..models.player import Player

        member_count = await self._guild_repo.get_member_count(guild_id)

        # 今日签到人数（直接查 Player 表，与旧版逻辑一致）
        today = date.today()
        session = self._guild_repo._session
        stmt = select(func.count(Player.id)).where(
            and_(
                Player.guild_id == guild_id,
                func.date(Player.last_sign) == today,
            )
        )
        signed_today = (await session.execute(stmt)).scalar_one()

        sign_rate = signed_today / member_count if member_count > 0 else 0
        return {
            "member_count": member_count,
            "signed_today": signed_today,
            "sign_rate": sign_rate,
            "active_level": "高" if sign_rate > 0.8 else "中" if sign_rate > 0.5 else "低",
        }
