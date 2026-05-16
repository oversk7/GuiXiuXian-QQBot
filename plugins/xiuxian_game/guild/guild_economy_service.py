"""
公会经济系统服务
"""
from typing import Tuple, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import date
from ..models.guild import Guild
from ..models.player import Player
from ..models.donation_log import PlayerDonationLog
from .guild_building_service import GuildBuildingService


class GuildEconomyService:
    """公会经济服务类"""
    
    # 配置常量
    DAILY_DONATION_POINTS_LIMIT = 100  # 每日通过捐献最多获得的积分
    GOLD_PER_DONATION_POINT = 1000  # 每1000金币获得1积分
    GOLD_TO_POINTS_RATIO = 0.001  # 金币转积分比率（1000金币=1积分）
    POINTS_TO_EXP_RATIO = 1.0     # 积分转公会经验比率（受建筑影响）
    
    @staticmethod
    def get_guild_upgrade_cost(level: int) -> Dict[str, int]:
        """获取公会升级成本"""
        if level <= 5:
            exp_cost = 1000 * (5 ** (level - 1))
        else:
            exp_cost = 1000 * 250 * (level - 5)
        
        # 升级还需要消耗资金
        gold_cost = level * 50000  # 每级需要5万金币
        
        return {
            "exp": exp_cost,
            "gold": gold_cost
        }
    
    @staticmethod
    def get_guild_capacity(level: int) -> int:
        """获取公会容量"""
        return 10 + (level - 1) * 5
    
    @staticmethod
    async def donate_gold(session: AsyncSession, player_id: str, amount: int) -> Tuple[bool, str, Dict]:
        """捐献金币"""
        player = await session.get(Player, player_id)
        if not player or not player.guild_id:
            return False, "你未加入任何公会", {}
        
        if player.gold < amount:
            return False, "金币不足", {}
        
        today = date.today()
        stmt = select(func.coalesce(func.sum(PlayerDonationLog.amount), 0)).where(
            PlayerDonationLog.player_id == player_id,
            PlayerDonationLog.donate_date == today
        )
        donated_today = (await session.execute(stmt)).scalar_one()

        guild = await session.get(Guild, player.guild_id)
        if not guild:
            return False, "公会数据异常", {}
        
        # 获取公会建筑加成
        bonuses = await GuildBuildingService.get_guild_bonuses(session, guild.id)
        exp_multiplier = bonuses.get("exp_multiplier", 1.0)
        treasury_limit = bonuses.get("treasury_limit", 100000)
        
        # 扣除玩家金币
        player.gold -= amount
        
        # 计算积分和经验
        points_gained = GuildEconomyService.calculate_donation_points(donated_today, amount)
        exp_gained = int(points_gained * GuildEconomyService.POINTS_TO_EXP_RATIO * exp_multiplier)
        
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
        session.add(donation_log)
        
        # 检查公会升级
        upgrade_info = GuildEconomyService.check_guild_upgrade(guild)
        
        session.add_all([player, guild])
        
        result = {
            "points_gained": points_gained,
            "exp_gained": exp_gained,
            "treasury_added": treasury_addition,
            "new_contribution": player.guild_contribution,
            "guild_exp": guild.exp,
            "guild_treasury": guild.treasury,
            "points_limit_reached": GuildEconomyService.is_donation_points_limit_reached(
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
        """检查公会是否可以升级"""
        cost = GuildEconomyService.get_guild_upgrade_cost(guild.level)
        
        can_upgrade = (guild.exp >= cost["exp"] and guild.treasury >= cost["gold"])
        
        return {
            "can_upgrade": can_upgrade,
            "cost": cost,
            "current_exp": guild.exp,
            "current_treasury": guild.treasury
        }
    
    @staticmethod
    async def upgrade_guild(session: AsyncSession, guild_id: int, player_id: str) -> Tuple[bool, str]:
        """升级公会"""
        guild = await session.get(Guild, guild_id)
        if not guild:
            return False, "公会不存在"
        
        # 权限检查（只有会长可以升级）
        if guild.president_id != player_id:
            return False, "只有会长才能升级公会"
        
        # 检查升级条件
        upgrade_info = GuildEconomyService.check_guild_upgrade(guild)
        if not upgrade_info["can_upgrade"]:
            cost = upgrade_info["cost"]
            return False, f"升级条件不足，需要经验{cost['exp']}、资金{cost['gold']}"
        
        # 执行升级
        cost = upgrade_info["cost"]
        guild.level += 1
        guild.exp -= cost["exp"]
        guild.treasury -= cost["gold"]
        
        session.add(guild)
        
        return True, f"公会升级至{guild.level}级成功！"
    
    @staticmethod
    async def add_guild_experience(session: AsyncSession, guild_id: int, base_exp: int) -> int:
        """添加公会经验（考虑建筑加成）"""
        guild = await session.get(Guild, guild_id)
        if not guild:
            return 0
        
        # 获取经验倍率加成
        bonuses = await GuildBuildingService.get_guild_bonuses(session, guild_id)
        exp_multiplier = bonuses.get("exp_multiplier", 1.0)
        
        # 计算实际获得的经验
        actual_exp = int(base_exp * exp_multiplier)
        guild.exp += actual_exp
        
        session.add(guild)
        return actual_exp
    
    @staticmethod
    async def get_daily_donation_remaining(session: AsyncSession, player_id: str) -> int:
        """获取玩家今日还能通过捐献获得多少积分"""
        today = date.today()
        stmt = select(func.coalesce(func.sum(PlayerDonationLog.amount), 0)).where(
            PlayerDonationLog.player_id == player_id,
            PlayerDonationLog.donate_date == today
        )
        donated_today = (await session.execute(stmt)).scalar_one()

        points_gained = min(
            donated_today // GuildEconomyService.GOLD_PER_DONATION_POINT,
            GuildEconomyService.DAILY_DONATION_POINTS_LIMIT,
        )
        return max(0, GuildEconomyService.DAILY_DONATION_POINTS_LIMIT - points_gained)
    
    @staticmethod
    def format_large_number(num: int) -> str:
        """格式化大数字为万单位"""
        if num < 100000:
            return str(num)
        return f"{num / 10000:.1f}w"
