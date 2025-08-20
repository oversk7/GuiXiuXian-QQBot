"""
阴宅系统服务层
提供阴宅等级管理、升级费用计算、修炼效率加成等功能
"""
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.player import Player
from ..config import config
import math


class MansionService:
    """阴宅服务类"""
    
    # 阴宅等级配置
    MAX_LEVEL = 10  # 最大等级
    BASE_UPGRADE_COST = 10_000_000  # 基础升级费用（1千万）
    COST_MULTIPLIER = 1.5  # 费用递增倍数
    BASE_EFFICIENCY = 0.2  # 基础效率加成（20%）
    EFFICIENCY_INCREMENT = 0.09  # 每级效率递增（9%）
    
    @classmethod
    def get_upgrade_cost(cls, current_level: int) -> int:
        """
        计算升级到下一级所需的金币
        
        Args:
            current_level: 当前阴宅等级
            
        Returns:
            升级所需金币数量，如果已达到最大等级则返回0
        """
        if current_level >= cls.MAX_LEVEL:
            return 0
        
        # 升级费用公式：基础费用 * (倍数 ^ 当前等级)
        cost = int(cls.BASE_UPGRADE_COST * (cls.COST_MULTIPLIER ** current_level))
        return cost
    
    @classmethod
    def get_efficiency_bonus(cls, mansion_level: int) -> float:
        """
        获取阴宅修炼效率加成

        Args:
            mansion_level: 阴宅等级

        Returns:
            效率加成比例（如0.1表示10%加成）
        """
        if mansion_level <= 0:
            return 0.0

        # 效率加成公式：基础效率 + ((等级-1) * 递增值)
        # 1级=20%, 2级=29%, 3级=38%, ..., 10级=101%
        efficiency = cls.BASE_EFFICIENCY + ((mansion_level - 1) * cls.EFFICIENCY_INCREMENT)
        return efficiency
    
    @classmethod
    def get_mansion_info(cls, mansion_level: int) -> dict:
        """
        获取阴宅详细信息
        
        Args:
            mansion_level: 阴宅等级
            
        Returns:
            包含等级、效率加成、升级费用等信息的字典
        """
        efficiency = cls.get_efficiency_bonus(mansion_level)
        upgrade_cost = cls.get_upgrade_cost(mansion_level)
        
        return {
            "level": mansion_level,
            "efficiency_bonus": efficiency,
            "efficiency_percent": efficiency * 100,
            "upgrade_cost": upgrade_cost,
            "max_level": cls.MAX_LEVEL,
            "is_max_level": mansion_level >= cls.MAX_LEVEL
        }
    
    @classmethod
    def has_mansion(cls, player: Player) -> bool:
        """检查玩家是否拥有阴宅"""
        return player.mansion_level > 0

    @classmethod
    def is_at_mansion(cls, player: Player) -> bool:
        """检查玩家是否在阴宅位置"""
        if not cls.has_mansion(player):
            return False

        # 检查玩家当前坐标是否与阴宅坐标一致
        current_x, current_y = player.get_current_coordinates()
        return (current_x == player.mansion_x and
                current_y == player.mansion_y)

    @classmethod
    async def can_upgrade(cls, session: AsyncSession, player: Player) -> tuple[bool, str]:
        """
        检查玩家是否可以升级阴宅

        Args:
            session: 数据库会话
            player: 玩家对象

        Returns:
            (是否可以升级, 错误信息)
        """
        # 检查是否已达到最大等级
        if player.mansion_level >= cls.MAX_LEVEL:
            return False, f"阴宅已达到最大等级({cls.MAX_LEVEL}级)"

        # 检查金币是否足够
        upgrade_cost = cls.get_upgrade_cost(player.mansion_level)
        if player.gold < upgrade_cost:
            return False, f"金币不足，需要{upgrade_cost:,}金币，当前拥有{player.gold:,}金币"

        # 检查是否在阴宅位置
        if cls.has_mansion(player) and not cls.is_at_mansion(player):
            return False, f"必须在阴宅位置({player.mansion_x}, {player.mansion_y})才能升级"

        return True, ""
    
    @classmethod
    async def upgrade_mansion(cls, session: AsyncSession, player: Player) -> tuple[bool, str]:
        """
        升级玩家的阴宅

        Args:
            session: 数据库会话
            player: 玩家对象

        Returns:
            (是否成功, 结果信息)
        """
        # 检查是否可以升级
        can_upgrade, error_msg = await cls.can_upgrade(session, player)
        if not can_upgrade:
            return False, error_msg

        # 计算升级费用
        upgrade_cost = cls.get_upgrade_cost(player.mansion_level)
        old_level = player.mansion_level

        # 执行升级
        player.gold -= upgrade_cost
        player.mansion_level += 1

        # 获取新等级信息
        new_info = cls.get_mansion_info(player.mansion_level)

        success_msg = (
            f"🏚️ 阴宅升级成功！\n"
            f"━━━━━━━━━━━━━\n"
            f"✧ 等级：{old_level} → {player.mansion_level}\n"
            f"✧ 修炼效率：+{new_info['efficiency_percent']:.1f}%\n"
            f"✧ 阴宅位置：({player.mansion_x}, {player.mansion_y})\n"
            f"✧ 消耗金币：{upgrade_cost:,}\n"
            f"✧ 剩余金币：{player.gold:,}\n"
            f"━━━━━━━━━━━━━"
        )

        if not new_info['is_max_level']:
            next_cost = cls.get_upgrade_cost(player.mansion_level)
            success_msg += f"\n⬇️ 下级升级需要：{next_cost:,}金币"
        else:
            success_msg += f"\n🎉 阴宅已达到最大等级！"

        return True, success_msg
    
    @classmethod
    async def purchase_mansion(cls, session: AsyncSession, player: Player) -> tuple[bool, str]:
        """
        购买阴宅（从0级升级到1级）

        Args:
            session: 数据库会话
            player: 玩家对象

        Returns:
            (是否成功, 结果信息)
        """
        # 检查是否已拥有阴宅
        if player.mansion_level > 0:
            return False, "你已经拥有阴宅了"

        # 检查金币是否足够
        purchase_cost = cls.get_upgrade_cost(0)  # 购买费用等于0级升级费用
        if player.gold < purchase_cost:
            return False, f"金币不足，购买阴宅需要{purchase_cost:,}金币，当前拥有{player.gold:,}金币"

        # 设置阴宅位置为玩家当前位置
        current_x, current_y = player.get_current_coordinates()

        # 执行购买
        player.gold -= purchase_cost
        player.mansion_level = 1
        player.mansion_x = current_x
        player.mansion_y = current_y

        # 获取阴宅信息
        mansion_info = cls.get_mansion_info(1)

        success_msg = (
            f"🏚️ 成功购买阴宅！\n"
            f"━━━━━━━━━━━━━\n"
            f"✧ 阴宅等级：1级\n"
            f"✧ 阴宅位置：({current_x}, {current_y})\n"
            f"✧ 修炼效率：+{mansion_info['efficiency_percent']:.1f}%\n"
            f"✧ 消耗金币：{purchase_cost:,}\n"
            f"✧ 剩余金币：{player.gold:,}\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 只有在阴宅位置修炼才能享受加成\n"
            f"⬇️ 下级升级需要：{mansion_info['upgrade_cost']:,}金币"
        )

        return True, success_msg
    
    @classmethod
    def format_mansion_status(cls, player: Player) -> str:
        """
        格式化显示阴宅状态

        Args:
            player: 玩家对象

        Returns:
            格式化的阴宅状态字符串
        """
        current_x, current_y = player.get_current_coordinates()

        if player.mansion_level <= 0:
            purchase_cost = cls.get_upgrade_cost(0)
            return (
                f"🏚️ 阴宅状态\n"
                f"━━━━━━━━━━━━━\n"
                f"✧ 状态：未拥有\n"
                f"✧ 当前位置：({current_x}, {current_y})\n"
                f"✧ 购买费用：{purchase_cost:,}金币\n"
                f"✧ 当前金币：{player.gold:,}金币\n"
                f"━━━━━━━━━━━━━\n"
                f"💡 阴宅将建在当前位置\n"
                f"💡 只有在阴宅位置修炼才有加成\n"
                f"⬇️ 【购买阴宅】开始你的阴宅之旅"
            )

        mansion_info = cls.get_mansion_info(player.mansion_level)
        is_at_mansion = cls.is_at_mansion(player)

        status_msg = (
            f"🏚️ 阴宅状态\n"
            f"━━━━━━━━━━━━━\n"
            f"✧ 等级：{mansion_info['level']}级"
        )

        if mansion_info['is_max_level']:
            status_msg += " (满级)"

        status_msg += (
            f"\n✧ 阴宅位置：({player.mansion_x}, {player.mansion_y})\n"
            f"✧ 当前位置：({current_x}, {current_y})"
        )

        if is_at_mansion:
            status_msg += " ✅\n"
        else:
            status_msg += " ❌\n"

        status_msg += (
            f"✧ 修炼效率：+{mansion_info['efficiency_percent']:.1f}%"
        )

        if not is_at_mansion:
            status_msg += " (需在阴宅位置)"

        status_msg += (
            f"\n✧ 当前金币：{player.gold:,}金币\n"
            f"━━━━━━━━━━━━━"
        )

        if not mansion_info['is_max_level']:
            status_msg += (
                f"\n✧ 升级费用：{mansion_info['upgrade_cost']:,}金币"
            )
            if is_at_mansion:
                status_msg += f"\n⬇️ 【升级阴宅】提升修炼效率"
            else:
                status_msg += f"\n💡 需要在阴宅位置才能升级"
        else:
            status_msg += f"\n🎉 阴宅已达到最大等级！"

        return status_msg
