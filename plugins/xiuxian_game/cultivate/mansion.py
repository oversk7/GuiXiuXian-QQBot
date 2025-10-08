"""
阴宅系统服务层
提供阴宅等级管理、升级费用计算、修炼效率加成等功能
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models.player import Player
from ..config import config
import math


class MansionService:
    """阴宅服务类"""
    
    # 阴宅等级配置
    MAX_LEVEL = 30  # 最大等级
    BASE_UPGRADE_COST = 10_000_000  # 基础升级费用（1千万）
    COST_MULTIPLIER = 1.5  # 费用递增倍数
    BASE_EFFICIENCY = 0.2  # 基础效率加成（20%）
    EFFICIENCY_INCREMENT = 0.09  # 每级效率递增（9%）

    # 阴宅使用费用配置
    BASE_MIN_USAGE_FEE = 1000  # 基础最低使用费用（1000金币）
    MAX_USAGE_FEE = 5_000_000  # 最高使用费用（500万金币）
    FEE_LEVEL_MULTIPLIER = 500  # 每级增加的最低费用（500金币）

    @classmethod
    def get_min_usage_fee(cls, mansion_level: int) -> int:
        """
        根据阴宅等级计算最低使用费用

        Args:
            mansion_level: 阴宅等级

        Returns:
            最低使用费用（金币）
        """
        if mansion_level <= 0:
            return 0

        # 最低费用公式：基础费用 + (等级-1) * 每级增量
        # 1级=1000, 2级=1500, 3级=2000, ..., 10级=5500
        min_fee = cls.BASE_MIN_USAGE_FEE + (mansion_level - 1) * cls.FEE_LEVEL_MULTIPLIER
        return min_fee

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
    async def find_mansion_owner_at_location(cls, session: AsyncSession, x: int, y: int) -> Player | None:
        """
        查找指定位置的阴宅主人

        Args:
            session: 数据库会话
            x: X坐标
            y: Y坐标

        Returns:
            阴宅主人玩家对象，如果没有找到则返回None
        """
        result = await session.execute(
            select(Player).where(
                Player.mansion_x == x,
                Player.mansion_y == y,
                Player.mansion_level > 0,
                Player.mansion_x.isnot(None),
                Player.mansion_y.isnot(None)
            )
        )
        # 现在有了唯一约束，可以安全使用 scalar_one_or_none()
        return result.scalar_one_or_none()

    @classmethod
    async def can_use_mansion(cls, session: AsyncSession, player: Player, mansion_owner: Player) -> tuple[bool, str]:
        """
        检查玩家是否可以使用指定阴宅

        Args:
            session: 数据库会话
            player: 使用者玩家对象
            mansion_owner: 阴宅主人玩家对象

        Returns:
            (是否可以使用, 结果信息)
        """
        # 检查是否是阴宅主人自己
        if player.id == mansion_owner.id:
            return True, "阴宅主人可以免费使用自己的阴宅"

        # 检查阴宅主人是否允许其他玩家使用
        if not mansion_owner.mansion_allow_others:
            return False, "阴宅主人不允许其他玩家使用"

        # 检查使用者是否愿意支付费用使用他人阴宅
        if not player.mansion_willing_to_pay:
            return False, "你已设置不愿意支付费用使用他人阴宅"

        # 检查使用费用
        if player.gold < mansion_owner.mansion_usage_fee:
            return False, f"金币不足，使用此阴宅需要{mansion_owner.mansion_usage_fee:,}金币，当前拥有{player.gold:,}金币"

        return True, "可以使用此阴宅"

    @classmethod
    async def pay_mansion_usage_fee(cls, session: AsyncSession, player: Player, mansion_owner: Player) -> tuple[bool, str]:
        """
        支付阴宅使用费用

        Args:
            session: 数据库会话
            player: 使用者玩家对象
            mansion_owner: 阴宅主人玩家对象

        Returns:
            (是否成功, 结果信息)
        """
        # 如果是阴宅主人自己，无需支付费用
        if player.id == mansion_owner.id:
            return True, ""

        # 检查金币是否足够
        if player.gold < mansion_owner.mansion_usage_fee:
            return False, f"金币不足，使用此阴宅需要{mansion_owner.mansion_usage_fee:,}金币"

        # 扣除使用者金币，增加阴宅主人金币
        player.gold -= mansion_owner.mansion_usage_fee
        mansion_owner.gold += mansion_owner.mansion_usage_fee

        # 保存数据
        session.add(player)
        session.add(mansion_owner)

        return True, f"已支付{mansion_owner.mansion_usage_fee:,}金币给阴宅主人 {mansion_owner.nickname}"

    @classmethod
    async def set_mansion_usage_fee(cls, session: AsyncSession, player: Player, fee: int) -> tuple[bool, str]:
        """
        设置阴宅使用费用

        Args:
            session: 数据库会话
            player: 阴宅主人玩家对象
            fee: 使用费用

        Returns:
            (是否成功, 结果信息)
        """
        # 检查是否拥有阴宅
        if not cls.has_mansion(player):
            return False, "你还没有阴宅，无法设置使用费用"

        # 检查费用范围
        if fee < 0:
            return False, "使用费用不能为负数"

        # 根据阴宅等级计算最低费用要求
        min_fee = cls.get_min_usage_fee(player.mansion_level)
        if fee < min_fee:
            return False, f"使用费用不能低于{min_fee:,}金币（{player.mansion_level}级阴宅最低要求）"

        if fee > cls.MAX_USAGE_FEE:
            return False, f"使用费用不能超过{cls.MAX_USAGE_FEE:,}金币"

        # 设置费用
        old_fee = player.mansion_usage_fee
        player.mansion_usage_fee = fee
        session.add(player)

        result_msg = (
            f"🏚️ 阴宅使用费用设置成功！\n"
            f"━━━━━━━━━━━━━\n"
            f"✧ 原费用：{old_fee:,}金币\n"
            f"✧ 新费用：{fee:,}金币\n"
            f"✧ 阴宅等级：{player.mansion_level}级\n"
            f"✧ 最低要求：{min_fee:,}金币\n"
            f"✧ 阴宅位置：({player.mansion_x}, {player.mansion_y})\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 其他玩家使用你的阴宅需支付{fee:,}金币"
        )

        return True, result_msg

    @classmethod
    async def toggle_mansion_access(cls, session: AsyncSession, player: Player) -> tuple[bool, str]:
        """
        切换阴宅访问权限

        Args:
            session: 数据库会话
            player: 阴宅主人玩家对象

        Returns:
            (是否成功, 结果信息)
        """
        # 检查是否拥有阴宅
        if not cls.has_mansion(player):
            return False, "你还没有阴宅，无法设置访问权限"

        # 切换权限
        player.mansion_allow_others = not player.mansion_allow_others
        session.add(player)

        status = "允许" if player.mansion_allow_others else "禁止"
        result_msg = (
            f"🏚️ 阴宅访问权限设置成功！\n"
            f"━━━━━━━━━━━━━\n"
            f"✧ 访问权限：{status}其他玩家使用\n"
            f"✧ 阴宅位置：({player.mansion_x}, {player.mansion_y})\n"
            f"━━━━━━━━━━━━━\n"
        )

        if player.mansion_allow_others:
            result_msg += f"💡 其他玩家使用你的阴宅需支付{player.mansion_usage_fee:,}金币"
        else:
            result_msg += f"💡 其他玩家无法使用你的阴宅"

        return True, result_msg

    @classmethod
    async def toggle_mansion_payment_willingness(cls, session: AsyncSession, player: Player) -> tuple[bool, str]:
        """
        切换玩家的阴宅付费使用意愿

        Args:
            session: 数据库会话
            player: 玩家对象

        Returns:
            (是否成功, 结果信息)
        """
        # 切换意愿
        player.mansion_willing_to_pay = not player.mansion_willing_to_pay
        session.add(player)

        status = "愿意" if player.mansion_willing_to_pay else "不愿意"
        result_msg = (
            f"🏚️ 阴宅使用意愿设置成功！\n"
            f"━━━━━━━━━━━━━\n"
            f"✧ 使用意愿：{status}支付费用使用他人阴宅\n"
            f"━━━━━━━━━━━━━\n"
        )

        if player.mansion_willing_to_pay:
            result_msg += (
                f"💡 在他人阴宅修炼时会自动支付使用费用\n"
                f"💡 可以享受阴宅修炼效率加成"
            )
        else:
            result_msg += (
                f"💡 在他人阴宅修炼时不会支付费用\n"
                f"💡 无法享受阴宅修炼效率加成\n"
                f"💡 使用【切换阴宅付费意愿】可重新开启"
            )

        return True, result_msg

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

        # 检查并调整使用费用
        new_min_fee = cls.get_min_usage_fee(player.mansion_level)
        old_fee = player.mansion_usage_fee
        fee_adjusted = False

        if player.mansion_usage_fee < new_min_fee:
            player.mansion_usage_fee = new_min_fee
            fee_adjusted = True

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
        )

        if fee_adjusted:
            success_msg += (
                f"✧ 使用费用：{old_fee:,} → {player.mansion_usage_fee:,}金币（自动调整）\n"
            )
        else:
            success_msg += (
                f"✧ 使用费用：{player.mansion_usage_fee:,}金币\n"
            )

        success_msg += f"━━━━━━━━━━━━━"

        if not new_info['is_max_level']:
            next_cost = cls.get_upgrade_cost(player.mansion_level)
            success_msg += f"\n⬇️ 下级升级需要：{next_cost:,}金币"
        else:
            success_msg += f"\n🎉 阴宅已达到最大等级！"

        return True, success_msg
    
    @classmethod
    def calculate_distance(cls, x1: int, y1: int, x2: int, y2: int) -> int:
        """计算两点间的曼哈顿距离"""
        return abs(x1 - x2) + abs(y1 - y2)

    @classmethod
    def calculate_migration_cost(cls, mansion_level: int) -> int:
        """
        计算阴宅迁移费用

        Args:
            mansion_level: 阴宅等级

        Returns:
            迁移费用（当前等级升级费用的50%）
        """
        if mansion_level <= 0:
            return 0

        # 迁移费用 = 当前等级升级费用的50%
        upgrade_cost = cls.get_upgrade_cost(mansion_level)
        migration_cost = int(upgrade_cost * 0.5)
        return migration_cost

    @classmethod
    async def can_migrate_mansion(cls, session: AsyncSession, player: Player, target_x: int, target_y: int) -> tuple[bool, str]:
        """
        检查玩家是否可以迁移阴宅到指定位置

        Args:
            session: 数据库会话
            player: 玩家对象
            target_x: 目标X坐标
            target_y: 目标Y坐标

        Returns:
            (是否可以迁移, 错误信息)
        """
        # 检查是否拥有阴宅
        if not cls.has_mansion(player):
            return False, "你还没有阴宅，无法进行迁移"

        # 检查目标位置是否是原点(0,0)
        if target_x == 0 and target_y == 0:
            return False, "原点(0,0)是新手出生地，不允许迁移阴宅到此位置"

        # 检查目标位置是否与当前位置相同
        if target_x == player.mansion_x and target_y == player.mansion_y:
            return False, f"阴宅已在位置({target_x}, {target_y})，无需迁移"

        # 检查距离城镇市集的限制
        can_build, distance_error = cls.check_distance_from_towns(target_x, target_y)
        if not can_build:
            return False, distance_error

        # 检查目标位置是否已有其他玩家的阴宅
        existing_owner = await cls.find_mansion_owner_at_location(session, target_x, target_y)
        if existing_owner:
            return False, f"位置({target_x}, {target_y})已有玩家{existing_owner.nickname}的阴宅，请选择其他位置"

        # 检查金币是否足够
        migration_cost = cls.calculate_migration_cost(player.mansion_level)
        if player.gold < migration_cost:
            return False, f"金币不足，迁移阴宅需要{migration_cost:,}金币，当前拥有{player.gold:,}金币"

        return True, ""

    @classmethod
    async def migrate_mansion(cls, session: AsyncSession, player: Player, target_x: int, target_y: int) -> tuple[bool, str]:
        """
        执行阴宅迁移

        Args:
            session: 数据库会话
            player: 玩家对象
            target_x: 目标X坐标
            target_y: 目标Y坐标

        Returns:
            (是否成功, 结果信息)
        """
        # 检查是否可以迁移
        can_migrate, error_msg = await cls.can_migrate_mansion(session, player, target_x, target_y)
        if not can_migrate:
            return False, error_msg

        # 记录原位置
        old_x, old_y = player.mansion_x, player.mansion_y

        # 计算迁移费用
        migration_cost = cls.calculate_migration_cost(player.mansion_level)

        # 执行迁移
        player.gold -= migration_cost
        player.mansion_x = target_x
        player.mansion_y = target_y

        # 保存数据
        session.add(player)

        # 格式化成功信息
        success_msg = (
            f"🏚️ 阴宅迁移成功！\n"
            f"━━━━━━━━━━━━━\n"
            f"✧ 阴宅等级：{player.mansion_level}级\n"
            f"✧ 原位置：({old_x}, {old_y})\n"
            f"✧ 新位置：({target_x}, {target_y})\n"
            f"✧ 迁移费用：{migration_cost:,}金币\n"
            f"✧ 剩余金币：{player.gold:,}金币\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 阴宅等级、使用费用、权限设置等属性保持不变\n"
            f"💡 在新位置修炼/闭关可享受{cls.get_efficiency_bonus(player.mansion_level)*100:.0f}%效率加成"
        )

        return True, success_msg

    @classmethod
    def check_distance_from_towns(cls, x: int, y: int) -> tuple[bool, str]:
        """
        检查指定位置是否距离城镇市集过近

        Args:
            x: X坐标
            y: Y坐标

        Returns:
            (是否可以建造, 错误信息)
        """
        # 导入市集和总部坐标
        from ..economy.merchants import MARKETS, HEADQUARTERS_COORD

        min_distance = 20  # 最小距离限制

        # 检查与所有市集的距离
        for market in MARKETS:
            distance = cls.calculate_distance(x, y, market.x, market.y)
            if distance <= min_distance:
                return False, f"距离{market.name}市集过近（{distance}格），阴宅不能在城镇市集{min_distance}格半径范围内建造"

        # 检查与缉邪司总部的距离
        hq_x, hq_y = HEADQUARTERS_COORD
        hq_distance = cls.calculate_distance(x, y, hq_x, hq_y)
        if hq_distance <= min_distance:
            return False, f"距离缉邪司总部过近（{hq_distance}格），阴宅不能在城镇市集{min_distance}格半径范围内建造"

        return True, ""

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

        # 检查是否在原点(0,0)，原点不允许建造阴宅（保护新手）
        if current_x == 0 and current_y == 0:
            return False, "原点(0,0)是新手出生地，不允许建造阴宅。请移动到其他位置后再购买"

        # 检查距离城镇市集的限制
        can_build, distance_error = cls.check_distance_from_towns(current_x, current_y)
        if not can_build:
            return False, distance_error

        # 检查当前位置是否已有其他玩家的阴宅
        existing_owner = await cls.find_mansion_owner_at_location(session, current_x, current_y)
        if existing_owner:
            return False, f"位置({current_x}, {current_y})已有玩家{existing_owner.nickname}的阴宅，请选择其他位置"

        # 执行购买
        player.gold -= purchase_cost
        player.mansion_level = 1
        player.mansion_x = current_x
        player.mansion_y = current_y

        # 设置默认使用费用为1级阴宅的最低要求
        player.mansion_usage_fee = cls.get_min_usage_fee(1)

        # 获取阴宅信息
        mansion_info = cls.get_mansion_info(1)

        success_msg = (
            f"🏚️ 成功购买阴宅！\n"
            f"━━━━━━━━━━━━━\n"
            f"✧ 阴宅等级：1级\n"
            f"✧ 阴宅位置：({current_x}, {current_y})\n"
            f"✧ 修炼效率：+{mansion_info['efficiency_percent']:.1f}%\n"
            f"✧ 使用费用：{player.mansion_usage_fee:,}金币（默认）\n"
            f"✧ 消耗金币：{purchase_cost:,}\n"
            f"✧ 剩余金币：{player.gold:,}\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 只有在阴宅位置修炼才能享受加成\n"
            f"💡 可使用【设置阴宅费用】调整收费\n"
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
            payment_willingness = "愿意" if player.mansion_willing_to_pay else "不愿意"
            return (
                f"🏚️ 阴宅状态\n"
                f"━━━━━━━━━━━━━\n"
                f"✧ 状态：未拥有\n"
                f"✧ 当前位置：({current_x}, {current_y})\n"
                f"✧ 购买费用：{purchase_cost:,}金币\n"
                f"✧ 付费意愿：{payment_willingness}使用他人阴宅\n"
                f"✧ 当前金币：{player.gold:,}金币\n"
                f"━━━━━━━━━━━━━\n"
                f"💡 阴宅将建在当前位置\n"
                f"💡 只有在阴宅位置修炼才有加成\n"
                f"⬇️ 【购买阴宅】开始你的阴宅之旅\n"
                f"⬇️ 【切换阴宅付费意愿】设置是否愿意付费使用他人阴宅"
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

        # 添加阴宅使用费用和权限信息
        access_status = "允许" if player.mansion_allow_others else "禁止"
        payment_willingness = "愿意" if player.mansion_willing_to_pay else "不愿意"
        min_fee = cls.get_min_usage_fee(player.mansion_level)

        status_msg += (
            f"\n✧ 使用费用：{player.mansion_usage_fee:,}金币\n"
            f"✧ 最低要求：{min_fee:,}金币\n"
            f"✧ 他人使用：{access_status}\n"
            f"✧ 付费意愿：{payment_willingness}使用他人阴宅\n"
            f"✧ 当前金币：{player.gold:,}金币\n"
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

        # 添加阴宅管理相关命令提示
        status_msg += (
            f"\n⬇️ 【设置阴宅费用 <金币数>】设置使用费用\n"
            f"⬇️ 【切换阴宅权限】允许/禁止他人使用\n"
            f"⬇️ 【切换阴宅付费意愿】设置是否愿意付费使用他人阴宅"
        )

        return status_msg

    @classmethod
    async def format_location_mansion_info(cls, session: AsyncSession, player: Player) -> str:
        """
        格式化显示当前位置的阴宅信息（供其他玩家查看）

        Args:
            session: 数据库会话
            player: 查看者玩家对象

        Returns:
            格式化的阴宅信息字符串
        """
        current_x, current_y = player.get_current_coordinates()

        # 查找当前位置的阴宅主人
        mansion_owner = await cls.find_mansion_owner_at_location(session, current_x, current_y)

        if not mansion_owner:
            return (
                f"🏚️ 当前位置阴宅信息\n"
                f"━━━━━━━━━━━━━\n"
                f"✧ 位置：({current_x}, {current_y})\n"
                f"✧ 状态：此处没有阴宅\n"
                f"━━━━━━━━━━━━━\n"
                f"💡 只有阴宅主人可以在此建造阴宅"
            )

        mansion_info = cls.get_mansion_info(mansion_owner.mansion_level)

        # 检查是否可以使用
        can_use, use_msg = await cls.can_use_mansion(session, player, mansion_owner)

        # 构建信息
        if player.id == mansion_owner.id:
            # 阴宅主人查看自己的阴宅
            status_info = "你的阴宅"
        else:
            # 其他玩家查看
            status_info = f"{mansion_owner.nickname} 的阴宅"

        access_status = "允许" if mansion_owner.mansion_allow_others else "禁止"
        min_fee = cls.get_min_usage_fee(mansion_owner.mansion_level)

        result_msg = (
            f"🏚️ 当前位置阴宅信息\n"
            f"━━━━━━━━━━━━━\n"
            f"✧ 阴宅主人：{mansion_owner.nickname}[{mansion_owner.uid}]\n"
            f"✧ 阴宅等级：{mansion_info['level']}级"
        )

        if mansion_info['is_max_level']:
            result_msg += " (满级)"

        result_msg += (
            f"\n✧ 修炼效率：+{mansion_info['efficiency_percent']:.1f}%\n"
            f"✧ 使用费用：{mansion_owner.mansion_usage_fee:,}金币\n"
            f"✧ 最低要求：{min_fee:,}金币\n"
            f"✧ 他人使用：{access_status}\n"
            f"✧ 位置：({current_x}, {current_y})\n"
            f"━━━━━━━━━━━━━"
        )

        if player.id != mansion_owner.id:
            if can_use:
                result_msg += (
                    f"\n💡 你可以支付{mansion_owner.mansion_usage_fee:,}金币使用此阴宅\n"
                    f"💡 在此位置修炼/闭关将享受+{mansion_info['efficiency_percent']:.1f}%效率加成"
                )
            else:
                result_msg += f"\n❌ {use_msg}"
        else:
            result_msg += f"\n💡 这是你的阴宅，可以免费享受修炼加成"

        return result_msg
