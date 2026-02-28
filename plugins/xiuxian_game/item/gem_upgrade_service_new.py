"""
镶嵌物升级系统服务 (DI架构版本)

改造说明:
- 混合模式设计：10个纯计算方法保持@staticmethod + 4个数据访问方法转为实例方法
- 通过构造函数注入ItemRepository和PlayerRepository依赖
- 移除内部rollback()调用，异常直接抛出由外层safe_session()处理
- 保持业务逻辑完全一致
"""

import random
from typing import Dict, Tuple, Optional
from ..models.player import Player
from ..config import config
from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.repositories.player_repository import PlayerRepository


class GemUpgradeService:
    """镶嵌物升级服务类 (DI架构版本)"""

    # 升级成功率配置
    SUCCESS_RATES = {
        1: 0.95,   # 1->2级 95%
        2: 0.90,   # 2->3级 90%
        3: 0.85,   # 3->4级 85%
        4: 0.80,   # 4->5级 80%
        5: 0.75,   # 5->6级 75%
        6: 0.70,   # 6->7级 70%
        7: 0.65,   # 7->8级 65%
        8: 0.60,   # 8->9级 60%
        9: 0.50,   # 9->10级 50%
    }

    # 升级金币消耗
    UPGRADE_GOLD_COSTS = {
        1: 5000,   2: 8000,   3: 12000,
        4: 18000,  5: 25000,  6: 35000,
        7: 50000,  8: 70000,  9: 100000
    }

    def __init__(
        self,
        item_repo: ItemRepository,
        player_repo: PlayerRepository,
    ):
        """
        初始化镶嵌物升级服务

        Args:
            item_repo: 物品仓储
            player_repo: 玩家仓储
        """
        self._item_repo = item_repo
        self._player_repo = player_repo

    # ==================== 静态方法（纯计算，无数据访问） ====================

    @staticmethod
    def is_upgradeable_gem(item_id: str) -> bool:
        """
        检查物品是否是可升级的镶嵌物

        Args:
            item_id: 物品ID

        Returns:
            是否可升级

        对应原代码:
            gem_upgrade_service.py Line 44-60
        """
        item_config = config.items_config["by_id"].get(item_id)
        if not item_config or item_config.type.value != "GEM":
            return False

        # 检查是否是分级镶嵌物（包含_数字后缀）
        parts = item_id.split('_')
        if len(parts) < 3:  # 例如：strength_gem_1
            return False

        try:
            level = int(parts[-1])
            return 1 <= level <= 10
        except ValueError:
            return False

    @staticmethod
    def get_gem_level(item_id: str) -> int:
        """
        获取镶嵌物等级

        Args:
            item_id: 物品ID

        Returns:
            等级（0表示不可升级）

        对应原代码:
            gem_upgrade_service.py Line 62-72
        """
        if not GemUpgradeService.is_upgradeable_gem(item_id):
            return 0

        parts = item_id.split('_')
        try:
            return int(parts[-1])
        except (ValueError, IndexError):
            return 0

    @staticmethod
    def get_gem_base_type(item_id: str) -> str:
        """
        获取镶嵌物基础类型（不含等级）

        Args:
            item_id: 物品ID

        Returns:
            基础类型（如"strength_gem"），空字符串表示无效

        对应原代码:
            gem_upgrade_service.py Line 74-83
        """
        if not GemUpgradeService.is_upgradeable_gem(item_id):
            return ""

        parts = item_id.split('_')
        if len(parts) >= 3:
            return '_'.join(parts[:-1])  # 去掉最后的等级数字
        return ""

    @staticmethod
    def get_next_level_gem_id(item_id: str) -> Optional[str]:
        """
        获取下一级镶嵌物的ID

        Args:
            item_id: 当前镶嵌物ID

        Returns:
            下一级ID，None表示已达最高等级或无效

        对应原代码:
            gem_upgrade_service.py Line 85-101
        """
        current_level = GemUpgradeService.get_gem_level(item_id)
        if current_level == 0 or current_level >= 10:
            return None

        base_type = GemUpgradeService.get_gem_base_type(item_id)
        if not base_type:
            return None

        next_gem_id = f"{base_type}_{current_level + 1}"

        # 验证下一级镶嵌物是否存在
        if config.items_config["by_id"].get(next_gem_id):
            return next_gem_id
        return None

    @staticmethod
    def get_previous_level_gem_id(item_id: str) -> Optional[str]:
        """
        获取前一级镶嵌物的ID

        Args:
            item_id: 当前镶嵌物ID

        Returns:
            前一级ID，None表示已是最低等级或无效

        对应原代码:
            gem_upgrade_service.py Line 103-119
        """
        current_level = GemUpgradeService.get_gem_level(item_id)
        if current_level <= 1:
            return None  # 1级镶嵌物没有前一级

        base_type = GemUpgradeService.get_gem_base_type(item_id)
        if not base_type:
            return None

        prev_gem_id = f"{base_type}_{current_level - 1}"

        # 验证前一级镶嵌物是否存在
        if config.items_config["by_id"].get(prev_gem_id):
            return prev_gem_id
        return None

    @staticmethod
    def get_upgrade_materials(current_level: int) -> Dict[str, int]:
        """
        获取升级所需升阶石材料

        Args:
            current_level: 当前等级

        Returns:
            材料字典 {material_id: quantity}

        对应原代码:
            gem_upgrade_service.py Line 121-140
        """
        if current_level >= 10:
            return {}  # 已达最高等级

        target_level = current_level + 1
        materials = {}

        # 根据目标等级确定所需升阶石
        if target_level <= 3:
            materials["upgrade_stone_low"] = target_level
        elif target_level <= 6:
            materials["upgrade_stone_mid"] = target_level - 3
        elif target_level <= 9:
            materials["upgrade_stone_high"] = target_level - 6
        else:  # target_level == 10
            materials["upgrade_stone_supreme"] = 1

        return materials

    @staticmethod
    def get_required_gem_count(current_level: int) -> int:
        """
        获取升级所需的相同镶嵌物数量

        Args:
            current_level: 当前等级

        Returns:
            所需数量（包括自己）

        对应原代码:
            gem_upgrade_service.py Line 142-156
        """
        if current_level >= 10:
            return 0

        # 升级需要的镶嵌物数量（包括自己）
        if current_level <= 3:
            return 2  # 需要2个相同镶嵌物
        elif current_level <= 6:
            return 3  # 需要3个相同镶嵌物
        elif current_level <= 9:
            return 4  # 需要4个相同镶嵌物
        else:
            return 5  # 9->10级需要5个

    @staticmethod
    def get_upgrade_gold_cost(current_level: int) -> int:
        """
        获取升级所需金币

        Args:
            current_level: 当前等级

        Returns:
            所需金币

        对应原代码:
            gem_upgrade_service.py Line 158-161
        """
        return GemUpgradeService.UPGRADE_GOLD_COSTS.get(current_level, 0)

    @staticmethod
    def get_success_rate(current_level: int, use_protection: bool = False, player_luck: int = 0) -> float:
        """
        获取升级成功率

        Args:
            current_level: 当前等级
            use_protection: 是否使用稳定水晶
            player_luck: 玩家运气值

        Returns:
            成功率（0.0-1.0）

        对应原代码:
            gem_upgrade_service.py Line 163-175
        """
        base_rate = GemUpgradeService.SUCCESS_RATES.get(current_level, 0.0)

        # 运气加成（最多20%）
        from ..utils import luck_prob
        luck_bonus = luck_prob(player_luck) * 0.2  # 运气值转换为0-20%的加成
        base_rate = min(1.0, base_rate + luck_bonus)

        if use_protection:
            base_rate = min(1.0, base_rate + 0.2)  # 稳定水晶增加20%成功率
        return base_rate

    @staticmethod
    def get_gem_display_info(gem_id: str, player_luck: int = 0) -> Dict[str, any]:
        """
        获取镶嵌物显示信息

        Args:
            gem_id: 镶嵌物ID
            player_luck: 玩家运气值

        Returns:
            显示信息字典

        对应原代码:
            gem_upgrade_service.py Line 327-357
        """
        if not GemUpgradeService.is_upgradeable_gem(gem_id):
            return {}

        current_level = GemUpgradeService.get_gem_level(gem_id)
        next_gem_id = GemUpgradeService.get_next_level_gem_id(gem_id)

        gem_config = config.items_config["by_id"].get(gem_id)
        if not gem_config:
            return {}

        info = {
            "current_level": current_level,
            "current_name": gem_config.name,
            "can_upgrade": current_level < 10 and next_gem_id is not None,
            "required_gem_count": GemUpgradeService.get_required_gem_count(current_level),
            "required_materials": GemUpgradeService.get_upgrade_materials(current_level),
            "required_gold": GemUpgradeService.get_upgrade_gold_cost(current_level),
            "success_rate": GemUpgradeService.get_success_rate(current_level, False, player_luck),
            "success_rate_with_protection": GemUpgradeService.get_success_rate(current_level, True, player_luck)
        }

        if next_gem_id:
            next_gem_config = config.items_config["by_id"].get(next_gem_id)
            if next_gem_config:
                info["next_level"] = current_level + 1
                info["next_name"] = next_gem_config.name

        return info

    # ==================== 实例方法（数据访问） ====================

    async def _has_enough_material(self, player_id: str, material_id: str, required_qty: int) -> bool:
        """
        检查是否有足够的材料

        Args:
            player_id: 玩家ID
            material_id: 材料ID
            required_qty: 所需数量

        Returns:
            是否足够

        对应原代码:
            gem_upgrade_service.py Line 177-186
        """
        owned_qty = await self._item_repo.get_material_total_quantity(player_id, material_id)
        return owned_qty >= required_qty

    async def _has_enough_gems(self, player_id: str, gem_id: str, required_qty: int) -> bool:
        """
        检查是否有足够的镶嵌物

        Args:
            player_id: 玩家ID
            gem_id: 镶嵌物ID
            required_qty: 所需数量

        Returns:
            是否足够

        对应原代码:
            gem_upgrade_service.py Line 188-197
        """
        owned_qty = await self._item_repo.get_material_total_quantity(player_id, gem_id)
        return owned_qty >= required_qty

    async def can_upgrade_gem(self, gem_id: str, player: Player, use_protection: bool = False) -> Tuple[bool, str]:
        """
        检查是否可以升级镶嵌物

        Args:
            gem_id: 镶嵌物ID
            player: 玩家对象
            use_protection: 是否使用稳定水晶

        Returns:
            (是否可升级, 提示信息)

        对应原代码:
            gem_upgrade_service.py Line 199-236
        """
        if not self.is_upgradeable_gem(gem_id):
            return False, "该物品不是可升级的镶嵌物"

        current_level = self.get_gem_level(gem_id)
        if current_level >= 10:
            return False, "镶嵌物已达最高等级"

        next_gem_id = self.get_next_level_gem_id(gem_id)
        if not next_gem_id:
            return False, "找不到下一级镶嵌物配置"

        # 检查镶嵌物数量
        required_gem_count = self.get_required_gem_count(current_level)
        if not await self._has_enough_gems(player.id, gem_id, required_gem_count):
            return False, f"镶嵌物数量不足，需要 {required_gem_count} 个"

        # 检查升阶石材料
        required_materials = self.get_upgrade_materials(current_level)
        for material_id, required_qty in required_materials.items():
            if not await self._has_enough_material(player.id, material_id, required_qty):
                material_config = config.items_config["by_id"].get(material_id)
                material_name = material_config.name if material_config else material_id
                return False, f"缺少材料：{material_name} x{required_qty}"

        # 检查稳定水晶（如果使用）
        if use_protection:
            if not await self._has_enough_material(player.id, "stabilizer_crystal", 1):
                return False, "缺少稳定水晶"

        # 检查金币
        required_gold = self.get_upgrade_gold_cost(current_level)
        if player.gold < required_gold:
            return False, f"金币不足，需要 {required_gold} 金币"

        return True, "可以升级"

    async def upgrade_gem(self, gem_id: str, player: Player, use_protection: bool = False) -> Tuple[bool, str, Dict[str, int]]:
        """
        升级镶嵌物

        Args:
            gem_id: 镶嵌物ID
            player: 玩家对象
            use_protection: 是否使用稳定水晶

        Returns:
            (成功标志, 消息, 消耗的材料字典)

        对应原代码:
            gem_upgrade_service.py Line 238-325

        改造点:
            - 移除内部rollback()调用（Line 261, 269, 277, 298）
            - 异常由外层safe_session()处理
            - 使用Repository方法替代ItemInstance静态方法
        """
        # 检查是否可以升级
        can_upgrade, reason = await self.can_upgrade_gem(gem_id, player, use_protection)
        if not can_upgrade:
            return False, reason, {}

        current_level = self.get_gem_level(gem_id)
        next_gem_id = self.get_next_level_gem_id(gem_id)
        required_gem_count = self.get_required_gem_count(current_level)
        required_materials = self.get_upgrade_materials(current_level)
        required_gold = self.get_upgrade_gold_cost(current_level)

        # 消耗金币
        player.gold -= required_gold
        await self._player_repo.update(player)

        # 消耗镶嵌物
        gem_success = await self._item_repo.consume_item(player.id, gem_id, required_gem_count)
        if not gem_success:
            # 改造点: 移除rollback，直接抛出异常由外层处理
            raise ValueError("扣除镶嵌物失败")

        # 消耗升阶石材料
        consumed_materials = {}
        for material_id, required_qty in required_materials.items():
            success = await self._item_repo.consume_item(player.id, material_id, required_qty)
            if not success:
                # 改造点: 移除rollback，直接抛出异常由外层处理
                raise ValueError("扣除材料失败")
            consumed_materials[material_id] = required_qty

        # 消耗稳定水晶（如果使用）
        if use_protection:
            protection_success = await self._item_repo.consume_item(player.id, "stabilizer_crystal", 1)
            if not protection_success:
                # 改造点: 移除rollback，直接抛出异常由外层处理
                raise ValueError("缺少稳定水晶")
            consumed_materials["stabilizer_crystal"] = 1

        # 计算成功率并判定结果
        success_rate = self.get_success_rate(current_level, use_protection, player.luck)
        is_success = random.random() < success_rate

        gem_config = config.items_config["by_id"].get(gem_id)
        gem_name = gem_config.name if gem_config else gem_id

        if is_success:
            # 升级成功，给予下一级镶嵌物
            try:
                await self._item_repo.add_item(player.id, next_gem_id, 1)
                next_gem_config = config.items_config["by_id"].get(next_gem_id)
                next_gem_name = next_gem_config.name if next_gem_config else next_gem_id

                message = f"🎉 升级成功！\n✨ {gem_name} → {next_gem_name}\n💰 消耗金币: {required_gold}"
                return True, message, consumed_materials
            except ValueError as e:
                # 改造点: 移除rollback，直接抛出异常由外层处理
                raise ValueError(f"升级成功但添加物品失败：{e}")
        else:
            # 升级失败
            if use_protection:
                # 使用了稳定水晶，返还一个原等级镶嵌物
                try:
                    await self._item_repo.add_item(player.id, gem_id, 1)
                    message = f"💔 升级失败！\n🛡️ 稳定水晶保护生效，返还 {gem_name}\n💰 消耗金币: {required_gold}"
                except ValueError:
                    message = f"💔 升级失败！\n⚠️ 背包空间不足，{gem_name} 丢失了\n💰 消耗金币: {required_gold}"
            else:
                # 没有保护：1-3级失败不降阶，4级以上降阶
                if current_level <= 3:
                    # 低阶保护：返还一个当前等级宝石，不降阶
                    try:
                        await self._item_repo.add_item(player.id, gem_id, 1)
                        message = f"💔 升级失败！\n📊 {gem_name} 等级不变（低阶保护）\n💰 消耗金币: {required_gold}"
                    except ValueError:
                        message = f"💔 升级失败！\n⚠️ 背包空间不足，{gem_name} 丢失了\n💰 消耗金币: {required_gold}"
                else:
                    # 高阶：镶嵌物降阶
                    prev_gem_id = self.get_previous_level_gem_id(gem_id)
                    if prev_gem_id:
                        try:
                            await self._item_repo.add_item(player.id, prev_gem_id, 1)
                            prev_gem_config = config.items_config["by_id"].get(prev_gem_id)
                            prev_gem_name = prev_gem_config.name if prev_gem_config else prev_gem_id
                            message = f"💔 升级失败！\n📉 {gem_name} 降阶为 {prev_gem_name}\n💰 消耗金币: {required_gold}"
                        except ValueError:
                            message = f"💔 升级失败！\n⚠️ 背包空间不足，镶嵌物丢失了\n💰 消耗金币: {required_gold}"
                    else:
                        # 已经是1级，无法降阶，直接消失
                        message = f"💔 升级失败！\n💀 {gem_name} 已是最低等级，升级失败后消失\n💰 消耗金币: {required_gold}"

            return False, message, consumed_materials
