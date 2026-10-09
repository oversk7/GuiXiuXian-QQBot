"""
公会经济系统服务 - DI架构版本

将GuildEconomyService改造为依赖注入架构，通过Repository抽象数据访问
"""

from typing import Tuple, Dict
from datetime import date
from ..models.guild import Guild
from ..models.player import Player
from ..models.donation_log import PlayerDonationLog
from ..infrastructure.repositories.guild_repository import GuildRepository
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
from ..infrastructure.repositories.player_donation_log_repository import PlayerDonationLogRepository
from .guild_building_service import GuildBuildingService


class GuildEconomyService:
    """公会经济服务类 - DI架构版本"""

    # 配置常量（类常量，保持向后兼容）
    DAILY_DONATION_POINTS_LIMIT = 100  # 每日通过捐献最多获得的积分
    GOLD_PER_DONATION_POINT = 1000  # 每1000金币获得1积分
    GOLD_TO_POINTS_RATIO = 0.001  # 金币转积分比率（1000金币=1积分）
    POINTS_TO_EXP_RATIO = 1.0     # 积分转公会经验比率（受建筑影响）

    def __init__(
        self,
        guild_repo: GuildRepository,
        player_repo: PlayerRepository,
        donation_log_repo: PlayerDonationLogRepository,
        building_repo: GuildBuildingRepository,
    ):
        """
        初始化公会经济服务

        Args:
            guild_repo: 公会仓储
            player_repo: 玩家仓储
            donation_log_repo: 捐献日志仓储
            building_repo: 公会建筑仓储
        """
        self._guild_repo = guild_repo
        self._player_repo = player_repo
        self._donation_log_repo = donation_log_repo
        self._building_repo = building_repo

    @staticmethod
    def get_guild_upgrade_cost(level: int) -> Dict[str, int]:
        """
        获取公会升级成本

        Args:
            level: 当前等级

        Returns:
            成本字典 {"exp": int, "gold": int}

        对应原代码:
            guild_economy_service.py Line 22-36

        Note:
            保留为静态方法，因为是纯函数，无需依赖注入
        """
        if level <= 5:
            exp_cost = 1000 * (5 ** (level - 1))
        else:
            # 从5级的62.5万衔接，之后每级增加25万，避免6级需求倒挂。
            exp_cost = 625000 + 250000 * (level - 5)

        # 升级还需要消耗资金
        gold_cost = level * 50000  # 每级需要5万金币

        return {
            "exp": exp_cost,
            "gold": gold_cost
        }

    @staticmethod
    def get_guild_capacity(level: int) -> int:
        """
        获取公会容量

        Args:
            level: 公会等级

        Returns:
            公会容量

        对应原代码:
            guild_economy_service.py Line 38-41

        Note:
            保留为静态方法，因为是纯函数，无需依赖注入
        """
        return 10 + (level - 1) * 5

    async def donate_gold(
        self, player_id: str, amount: int
    ) -> Tuple[bool, str, Dict]:
        """
        捐献金币

        Args:
            player_id: 玩家ID
            amount: 捐献金额

        Returns:
            (是否成功, 消息, 结果数据)

        对应原代码:
            guild_economy_service.py Line 43-117

        Note:
            ✅ 原代码无P0问题：Line 104的add_all无内部commit
            新版本移除session参数，通过Repository操作数据
        """
        player = await self._player_repo.get_by_id(player_id)
        if not player or not player.guild_id:
            return False, "你未加入任何公会", {}

        if player.gold < amount:
            return False, "金币不足", {}

        today = date.today()
        donated_today = await self._donation_log_repo.get_today_donation_amount(
            player_id, today
        )

        guild = await self._guild_repo.get_by_id(player.guild_id)
        if not guild:
            return False, "公会数据异常", {}

        # 获取公会建筑加成（通过GuildBuildingService）
        building_service = GuildBuildingService(
            guild_repo=self._guild_repo,
            building_repo=self._building_repo,
            item_repo=None  # get_guild_bonuses不需要item_repo
        )
        bonuses = await building_service.get_guild_bonuses(guild.id)
        exp_multiplier = bonuses.get("exp_multiplier", 1.0)
        treasury_limit = bonuses.get("treasury_limit", 100000)

        # 扣除玩家金币
        player.gold -= amount

        # 计算积分和经验
        points_gained = self.calculate_donation_points(donated_today, amount)
        exp_gained = int(points_gained * self.POINTS_TO_EXP_RATIO * exp_multiplier)

        # 更新玩家数据
        player.gold2 += points_gained  # 个人积分
        player.guild_contribution += points_gained  # 累计贡献（应该是积分，不是金币）

        # 更新公会数据
        guild.exp += exp_gained

        # 资金进入公会资金库（有上限）
        treasury_addition = min(amount, treasury_limit - guild.treasury)
        if treasury_addition > 0:
            guild.treasury += treasury_addition

        # 记录捐献日志
        donation_log = PlayerDonationLog(
            player_id=player_id,
            donate_date=today,
            amount=amount
        )
        await self._donation_log_repo.add(donation_log)

        # 检查公会升级
        upgrade_info = self.check_guild_upgrade(guild)

        # 更新实体
        await self._player_repo.update(player)
        await self._guild_repo.update(guild)

        result = {
            "points_gained": points_gained,
            "exp_gained": exp_gained,
            "treasury_added": treasury_addition,
            "new_contribution": player.guild_contribution,
            "guild_exp": guild.exp,
            "guild_treasury": guild.treasury,
            "points_limit_reached": self.is_donation_points_limit_reached(
                donated_today + amount
            ),
            "can_upgrade": upgrade_info["can_upgrade"],
            "upgrade_cost": upgrade_info["cost"]
        }

        return True, "捐献成功", result

    @classmethod
    def calculate_donation_points(cls, donated_before: int, amount: int) -> int:
        """按今日累计捐献额计算本次可获得积分，受每日积分上限限制。"""
        donated_before = int(donated_before or 0)
        amount = int(amount)
        points_before = min(
            donated_before // cls.GOLD_PER_DONATION_POINT,
            cls.DAILY_DONATION_POINTS_LIMIT,
        )
        points_after = min(
            (donated_before + amount) // cls.GOLD_PER_DONATION_POINT,
            cls.DAILY_DONATION_POINTS_LIMIT,
        )
        return max(0, points_after - points_before)

    @classmethod
    def is_donation_points_limit_reached(cls, donated_today: int) -> bool:
        """判断今日捐献积分是否已达上限。"""
        donated_today = int(donated_today or 0)
        return donated_today // cls.GOLD_PER_DONATION_POINT >= cls.DAILY_DONATION_POINTS_LIMIT

    @staticmethod
    def check_guild_upgrade(guild: Guild) -> Dict:
        """
        检查公会是否可以升级

        Args:
            guild: 公会实例

        Returns:
            升级信息字典

        对应原代码:
            guild_economy_service.py Line 119-131

        Note:
            保留为静态方法，因为只需要Guild对象，不需要访问数据库
        """
        cost = GuildEconomyService.get_guild_upgrade_cost(guild.level)

        can_upgrade = (guild.exp >= cost["exp"] and guild.treasury >= cost["gold"])

        return {
            "can_upgrade": can_upgrade,
            "cost": cost,
            "current_exp": guild.exp,
            "current_treasury": guild.treasury
        }

    async def upgrade_guild(
        self, guild_id: int, player_id: str
    ) -> Tuple[bool, str]:
        """
        升级公会

        Args:
            guild_id: 公会ID
            player_id: 操作玩家ID

        Returns:
            (是否成功, 消息)

        对应原代码:
            guild_economy_service.py Line 133-158

        Note:
            ✅ 原代码无P0问题：Line 156的add无内部commit
            新版本移除session参数，通过Repository操作数据
        """
        guild = await self._guild_repo.get_by_id(guild_id)
        if not guild:
            return False, "公会不存在"

        # 权限检查（只有会长可以升级）
        if guild.president_id != player_id:
            return False, "只有会长才能升级公会"

        # 检查升级条件
        upgrade_info = self.check_guild_upgrade(guild)
        if not upgrade_info["can_upgrade"]:
            cost = upgrade_info["cost"]
            return False, f"升级条件不足，需要经验{cost['exp']}、资金{cost['gold']}"

        # 执行升级
        cost = upgrade_info["cost"]
        guild.level += 1
        guild.exp -= cost["exp"]
        guild.treasury -= cost["gold"]

        await self._guild_repo.update(guild)

        return True, f"公会升级至{guild.level}级成功！"

    async def add_guild_experience(
        self, guild_id: int, base_exp: int
    ) -> int:
        """
        添加公会经验（考虑建筑加成）

        Args:
            guild_id: 公会ID
            base_exp: 基础经验值

        Returns:
            实际获得的经验值

        对应原代码:
            guild_economy_service.py Line 160-176

        Note:
            ✅ 原代码无P0问题：Line 175的add无内部commit
            新版本移除session参数，通过Repository操作数据
        """
        guild = await self._guild_repo.get_by_id(guild_id)
        if not guild:
            return 0

        # 获取经验倍率加成（通过GuildBuildingService）
        building_service = GuildBuildingService(
            guild_repo=self._guild_repo,
            building_repo=self._building_repo,
            item_repo=None  # get_guild_bonuses不需要item_repo
        )
        bonuses = await building_service.get_guild_bonuses(guild_id)
        exp_multiplier = bonuses.get("exp_multiplier", 1.0)

        # 计算实际获得的经验
        actual_exp = int(base_exp * exp_multiplier)
        guild.exp += actual_exp

        await self._guild_repo.update(guild)
        return actual_exp

    async def get_daily_donation_remaining(self, player_id: str) -> int:
        """
        获取玩家今日还能通过捐献获得多少积分

        Args:
            player_id: 玩家ID

        Returns:
            今日剩余可获得积分

        对应原代码:
            guild_economy_service.py Line 178-188
        """
        today = date.today()
        donated_today = await self._donation_log_repo.get_today_donation_amount(
            player_id, today
        )

        points_gained = min(
            donated_today // self.GOLD_PER_DONATION_POINT,
            self.DAILY_DONATION_POINTS_LIMIT,
        )
        return max(0, self.DAILY_DONATION_POINTS_LIMIT - points_gained)

    @staticmethod
    def format_large_number(num: int) -> str:
        """
        格式化大数字为万单位

        Args:
            num: 数字

        Returns:
            格式化后的字符串

        对应原代码:
            guild_economy_service.py Line 190-195

        Note:
            保留为静态方法，因为是纯函数，无需依赖注入
        """
        if num < 100000:
            return str(num)
        return f"{num / 10000:.1f}w"
