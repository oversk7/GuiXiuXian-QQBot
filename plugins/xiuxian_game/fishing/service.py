"""
钓鱼系统核心服务类 (DI架构版本)

实现钓鱼概率计算、鱼类获取逻辑等核心功能
"""
import random
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta

from ..config import config
from ..models.fishing_record import FishingRecord, FishingStats
from ..models.inventory import ItemInstance
from ..models.player import Player
from ..infrastructure.repositories.fishing_record_repository import FishingRecordRepository
from ..infrastructure.repositories.fishing_stats_repository import FishingStatsRepository
from ..infrastructure.repositories.item_repository import ItemRepository


class FishingService:
    """钓鱼服务类 - DI架构版本

    通过构造函数注入所需的Repository，不再使用静态方法
    """

    # 鱼类稀有度配置
    FISH_RARITY_CONFIG = {
        "white": {
            "weight": 55,  # 55%概率（降低5%）
            "fish_list": [
                "common_carp", "crucian_carp", "grass_carp",
                "silver_carp", "catfish"
            ]
        },
        "green": {
            "weight": 28,  # 28%概率（提高3%）
            "fish_list": [
                "bass", "mandarin_fish", "yellow_croaker",
                "pomfret", "snapper"
            ]
        },
        "blue": {
            "weight": 14,  # 14%概率（提高2%）
            "fish_list": [
                "salmon", "tuna", "grouper", "eel", "turbot"
            ]
        },
        "purple": {
            "weight": 2.5,  # 2.5%概率（保持不变，运气加成更强）
            "fish_list": [
                "chinese_sturgeon", "arowana", "giant_catfish", "bluefin_tuna"
            ]
        },
        "orange": {
            "weight": 0.5,  # 0.5%概率（保持不变，运气加成更强）
            "fish_list": [
                "golden_dragon_fish", "phoenix_fish", "void_fish"
            ]
        }
    }

    # 钓鱼冷却时间（分钟）
    FISHING_COOLDOWN = 5

    # 每日钓鱼次数限制
    DAILY_FISHING_LIMIT = 50

    def __init__(
        self,
        fishing_record_repo: FishingRecordRepository,
        fishing_stats_repo: FishingStatsRepository,
        item_repo: ItemRepository
    ):
        """
        初始化钓鱼服务

        Args:
            fishing_record_repo: 钓鱼记录仓储
            fishing_stats_repo: 钓鱼统计仓储
            item_repo: 物品仓储
        """
        self._fishing_record_repo = fishing_record_repo
        self._fishing_stats_repo = fishing_stats_repo
        self._item_repo = item_repo

    async def can_fishing(self, player: Player) -> Tuple[bool, str]:
        """检查玩家是否可以钓鱼

        Args:
            player: 玩家对象

        Returns:
            (can_fish, reason): 是否可以钓鱼和原因

        对应原代码:
            fishing/service.py Line 62-88
        """
        # 检查冷却时间
        can_fish_cooldown = await self._fishing_record_repo.can_fishing(player.id, self.FISHING_COOLDOWN)
        if not can_fish_cooldown:
            last_time = await self._fishing_record_repo.get_last_fishing_time(player.id)
            if last_time:
                next_time = last_time + timedelta(minutes=self.FISHING_COOLDOWN)
                remaining_seconds = max(0, int((next_time - datetime.now()).total_seconds()))
                minutes = remaining_seconds // 60
                seconds = remaining_seconds % 60
                return False, f"钓鱼冷却中，还需等待 {minutes}分{seconds}秒"

        # 检查每日钓鱼次数限制
        stats = await self._fishing_record_repo.get_player_fishing_stats(player.id)
        if stats["today_fishing_count"] >= self.DAILY_FISHING_LIMIT:
            return False, f"今日钓鱼次数已达上限（{self.DAILY_FISHING_LIMIT}次），明天再来吧！"

        # 检查背包空间（通过计算当前使用情况）
        # 注意：鱼类不占用背包空间，所以不需要检查背包容量
        # 钓鱼系统使用独立的鱼栏存储，类似装备栏

        return True, ""

    @staticmethod
    def calculate_fish_rarity(player: Player) -> str:
        """根据玩家属性计算钓到鱼的稀有度

        Args:
            player: 玩家对象

        Returns:
            稀有度字符串

        对应原代码:
            fishing/service.py Line 91-133
        """
        # 基础概率
        weights = []
        rarities = []

        for rarity, config in FishingService.FISH_RARITY_CONFIG.items():
            base_weight = config["weight"]

            # 运气值影响稀有鱼概率（分段加成机制，解决高幸运值边际递减问题）
            from ..utils import luck_prob_tiered
            luck_factor = luck_prob_tiered(player.luck)

            if rarity == "orange":
                # 橙色传说鱼：运气加成最大，最多增加原概率的300%
                # 高幸运值玩家通过分段机制可获得更高倍率
                luck_multiplier = 1 + luck_factor * 3.0
                base_weight *= luck_multiplier
            elif rarity == "purple":
                # 紫色稀有鱼：运气加成较大，最多增加原概率的200%
                luck_multiplier = 1 + luck_factor * 2.0
                base_weight *= luck_multiplier
            elif rarity == "blue":
                # 蓝色精品鱼：运气加成中等，最多增加原概率的100%
                luck_multiplier = 1 + luck_factor * 1.0
                base_weight *= luck_multiplier
            elif rarity == "green":
                # 绿色优良鱼：运气加成较小，最多增加原概率的50%
                luck_multiplier = 1 + luck_factor * 0.5
                base_weight *= luck_multiplier
            # 白色普通鱼不受运气影响，保持基础概率

            weights.append(base_weight)
            rarities.append(rarity)

        # 随机选择稀有度
        return random.choices(rarities, weights=weights)[0]

    @staticmethod
    def get_random_fish(rarity: str) -> str:
        """根据稀有度随机获取鱼类ID

        Args:
            rarity: 稀有度

        Returns:
            鱼类物品ID

        对应原代码:
            fishing/service.py Line 136-146
        """
        fish_list = FishingService.FISH_RARITY_CONFIG[rarity]["fish_list"]
        return random.choice(fish_list)

    @staticmethod
    def calculate_fish_quantity(player: Player, rarity: str) -> int:
        """计算钓到鱼的数量

        Args:
            player: 玩家对象
            rarity: 鱼类稀有度

        Returns:
            鱼的数量

        对应原代码:
            fishing/service.py Line 149-194
        """
        base_quantity = 1

        # 稀有度越低，可能钓到的数量越多
        if rarity == "white":
            # 白色品质：1-3条
            base_quantity = random.randint(1, 3)
        elif rarity == "green":
            # 绿色品质：1-2条
            base_quantity = random.randint(1, 2)
        else:
            # 蓝色及以上：固定1条
            base_quantity = 1

        # 运气值影响数量（分段加成机制，高幸运值玩家获得更高概率）
        luck_bonus = 0
        from ..utils import luck_prob_tiered
        luck_factor = luck_prob_tiered(player.luck)

        # 根据稀有度和运气值计算额外数量
        if rarity == "white":
            # 白色鱼：高运气时有更高概率获得额外数量
            # 分段机制让高幸运值玩家获得超100%的概率加成
            if random.random() < min(1.0, luck_factor * 0.4):  # 最高可达59.8%概率
                luck_bonus += 1
            if random.random() < min(1.0, luck_factor * 0.2):  # 最高可达29.9%概率
                luck_bonus += 1
        elif rarity == "green":
            # 绿色鱼：中等概率获得额外数量
            if random.random() < min(1.0, luck_factor * 0.3):  # 最高可达44.9%概率
                luck_bonus += 1
        elif rarity == "blue":
            # 蓝色鱼：较低概率获得额外数量
            if random.random() < min(1.0, luck_factor * 0.2):  # 最高可达29.9%概率
                luck_bonus += 1
        # 紫色和橙色鱼保持稀缺性，不增加数量

        return base_quantity + luck_bonus

    async def do_fishing(self, player: Player) -> Dict:
        """执行钓鱼操作

        Args:
            player: 玩家对象

        Returns:
            钓鱼结果字典

        对应原代码:
            fishing/service.py Line 197-256
        """
        # 检查是否可以钓鱼
        can_fish, reason = await self.can_fishing(player)
        if not can_fish:
            return {"success": False, "message": reason}

        # 计算鱼类稀有度
        rarity = self.calculate_fish_rarity(player)

        # 获取具体鱼类
        fish_id = self.get_random_fish(rarity)

        # 计算数量
        quantity = self.calculate_fish_quantity(player, rarity)

        # 获取鱼类配置
        fish_config = config.items_config["by_id"].get(fish_id)
        if not fish_config:
            return {"success": False, "message": "鱼类配置错误"}

        try:
            # 添加鱼类到背包
            await self._item_repo.add_item(player.id, fish_id, quantity)

            # 记录钓鱼活动
            current_x, current_y = player.get_current_coordinates()
            await self._fishing_record_repo.record_fishing(player.id, fish_id, quantity, current_x, current_y)

            # 更新钓鱼统计
            fishing_stats = await self._fishing_stats_repo.get_or_create(player.id)
            await self._fishing_stats_repo.update_stats(fishing_stats, fish_config.price, rarity, quantity)

            # P0问题修复：移除内部commit，由调用方控制事务
            # 原代码 Line 239: await session.commit() - 已移除

            return {
                "success": True,
                "fish_name": fish_config.name,
                "fish_id": fish_id,
                "quantity": quantity,
                "rarity": rarity,
                "value": fish_config.price * quantity,
                "rarity_display": fish_config.get_rarity_display()
            }

        except ValueError as e:
            return {"success": False, "message": f"钓鱼失败：{e}"}
        except Exception as e:
            return {"success": False, "message": f"钓鱼过程中发生错误：{e}"}

    async def get_fishing_leaderboard(self, limit: int = 10, server_id: int = 1) -> List[Dict]:
        """获取钓鱼排行榜（按区服隔离）

        Args:
            limit: 返回数量限制
            server_id: 区服ID

        Returns:
            排行榜列表

        对应原代码:
            fishing/service.py Line 259-290
        """
        # 使用Repository方法，自动预加载Player信息
        leaderboard_data = await self._fishing_stats_repo.get_leaderboard(limit, server_id)
        leaderboard = []

        for stats, nickname, uid in leaderboard_data:
            leaderboard.append({
                "nickname": nickname,
                "uid": uid,
                "total_fishing_count": stats.total_fishing_count,
                "total_fish_caught": stats.total_fish_caught,
                "total_fish_value": stats.total_fish_value,
                "rare_fish_caught": stats.rare_fish_caught,
                "legendary_fish_caught": stats.legendary_fish_caught,
                "best_fish_value": stats.best_fish_value
            })

        return leaderboard

    @staticmethod
    def calculate_fishing_probabilities(player: Player) -> Dict[str, Dict[str, float]]:
        """计算玩家钓到各品阶鱼的概率

        Args:
            player: 玩家对象

        Returns:
            各品阶鱼的详细概率信息:
            {
                "white": {"base_rate": 55.0, "actual_rate": 55.0, "multiplier": 1.0},
                "green": {"base_rate": 28.0, "actual_rate": 42.0, "multiplier": 1.5},
                ...
            }

        示例:
            >>> service = FishingService(...)
            >>> probs = service.calculate_fishing_probabilities(player)
            >>> print(probs["orange"]["actual_rate"])  # 例如: 2.75
        """
        from ..utils import luck_prob_tiered

        luck_factor = luck_prob_tiered(player.luck)
        probabilities = {}

        # 计算各品阶的概率
        for rarity, config in FishingService.FISH_RARITY_CONFIG.items():
            base_weight = config["weight"]

            # 计算倍率 (与calculate_fish_rarity方法中的逻辑一致)
            if rarity == "orange":
                luck_multiplier = 1 + luck_factor * 3.0
            elif rarity == "purple":
                luck_multiplier = 1 + luck_factor * 2.0
            elif rarity == "blue":
                luck_multiplier = 1 + luck_factor * 1.0
            elif rarity == "green":
                luck_multiplier = 1 + luck_factor * 0.5
            else:  # white
                luck_multiplier = 1.0

            # 计算加成后的权重
            adjusted_weight = base_weight * luck_multiplier

            probabilities[rarity] = {
                "base_rate": base_weight,  # 基础概率
                "multiplier": luck_multiplier,  # 运气倍率
                "adjusted_weight": adjusted_weight  # 加成后权重
            }

        # 计算总权重
        total_weight = sum(prob["adjusted_weight"] for prob in probabilities.values())

        # 计算实际百分比概率
        for rarity in probabilities:
            adjusted_weight = probabilities[rarity]["adjusted_weight"]
            actual_rate = (adjusted_weight / total_weight) * 100
            probabilities[rarity]["actual_rate"] = actual_rate

        return probabilities
