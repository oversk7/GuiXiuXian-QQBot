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

    # 诡域诡鱼稀有度配置（诡域中垂钓时替换普通鱼池，权重与现实世界一致）
    GHOST_FISH_RARITY_CONFIG = {
        "white": {
            "weight": 55,
            "fish_list": ["pale_scale_fish", "blind_cave_fish", "well_minnow"]
        },
        "green": {
            "weight": 28,
            "fish_list": ["sobbing_fish", "mist_gill_fish", "wax_face_fish"]
        },
        "blue": {
            "weight": 14,
            "fish_list": ["faceless_fish", "shadow_eel", "mirror_scale_fish"]
        },
        "purple": {
            "weight": 2.5,
            "fish_list": ["well_pupil", "human_face_sturgeon"]
        },
        "orange": {
            "weight": 0.5,
            "fish_list": ["void_fish", "corpse_lantern_fish"]
        }
    }

    # 沿海特色钓点（城市名 -> 专属鱼ID），坐标取自 economy.merchant_service.MARKET_CONFIGS
    COASTAL_FISHING_SPOTS = {
        "舟山": "zhoushan_tide_fish",
        "海门": "haimen_lighthouse_fish",
        "鹭岛": "ludao_seawind_fish",
        "荔湾镇": "liwan_drowner_bass",
        "鹏城": "pengcheng_flying_fish",
        "琼崖": "qiongya_coconut_grouper",
    }
    # 判定处于钓点的曼哈顿距离
    FISHING_SPOT_RADIUS = 8
    # 钓点稀有度权重加成（白色不加成）
    SPOT_RARITY_BONUS = {"green": 1.25, "blue": 1.5, "purple": 2.0, "orange": 2.0}
    # 钓点钓出蓝色品质时替换为该城专属鱼的概率
    SPOT_EXCLUSIVE_CHANCE = 0.3

    # 打捞杂物概率（上钩的不是鱼）
    JUNK_CATCH_CHANCE = 0.08
    # 现实世界打捞池 (item_id, 权重, 最小数量, 最大数量)
    REAL_WORLD_SALVAGE_POOL = [
        ("empty_drift_bottle", 16, 1, 1),
        ("bloated_diary_page", 15, 1, 1),
        ("soaked_doll", 14, 1, 1),
        ("waterweed_frame", 13, 1, 1),
        ("pale_denture", 12, 1, 1),
        ("rusted_pocket_watch", 10, 1, 1),
        ("bone_fragment", 8, 1, 2),
        ("ash_powder", 6, 1, 2),
        ("iron_rust", 6, 1, 2),
    ]
    # 诡域打捞池：里界剧本遗留战利品，钓鱼打捞是其稳定来源
    # 注意 flickering_night_light 怨念值300远超同稀有度，权重刻意压到紫色以下
    DUNGEON_SALVAGE_POOL = [
        ("bloodstained_room_card", 30, 1, 1),
        ("broken_id", 25, 1, 1),
        ("faceless_skin", 15, 1, 1),
        ("scalpel", 12, 1, 1),
        ("visitor_pass", 8, 1, 1),
        ("human_tooth_collection", 4, 1, 1),
        ("headless_ghost_nail", 3, 1, 1),
        ("flickering_night_light", 1.5, 1, 1),
        ("freezer_woman_flesh", 1, 1, 1),
        ("liwan_time_fragment", 0.5, 1, 1),
    ]

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
    def get_fishing_spot(player: Player) -> Optional[str]:
        """返回玩家所处的沿海钓点城市名，不在钓点（或在诡域）返回None"""
        if (player.dungeon_level or 0) > 0:
            return None
        from ..economy.merchant_service import MARKET_CONFIGS
        px, py = player.get_current_coordinates()
        for market_cfg in MARKET_CONFIGS.values():
            city_name = market_cfg["name"]
            if city_name not in FishingService.COASTAL_FISHING_SPOTS:
                continue
            mx, my = market_cfg["coord"]
            if abs(px - mx) + abs(py - my) <= FishingService.FISHING_SPOT_RADIUS:
                return city_name
        return None

    @staticmethod
    def calculate_fish_rarity(player: Player, spot: Optional[str] = None, in_dungeon: bool = False) -> str:
        """根据玩家属性计算钓到鱼的稀有度

        Args:
            player: 玩家对象
            spot: 所处沿海钓点城市名（None表示不在钓点）
            in_dungeon: 是否在诡域中垂钓

        Returns:
            稀有度字符串

        对应原代码:
            fishing/service.py Line 91-133
        """
        # 基础概率
        weights = []
        rarities = []

        rarity_config = (
            FishingService.GHOST_FISH_RARITY_CONFIG if in_dungeon
            else FishingService.FISH_RARITY_CONFIG
        )
        for rarity, config in rarity_config.items():
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

            # 沿海钓点加成
            if spot:
                base_weight *= FishingService.SPOT_RARITY_BONUS.get(rarity, 1.0)

            weights.append(base_weight)
            rarities.append(rarity)

        # 随机选择稀有度
        return random.choices(rarities, weights=weights)[0]

    @staticmethod
    def get_random_fish(rarity: str, spot: Optional[str] = None, in_dungeon: bool = False) -> str:
        """根据稀有度随机获取鱼类ID

        Args:
            rarity: 稀有度
            spot: 所处沿海钓点城市名（钓出蓝色品质时有概率替换为专属鱼）
            in_dungeon: 是否在诡域中垂钓（使用诡鱼池）

        Returns:
            鱼类物品ID

        对应原代码:
            fishing/service.py Line 136-146
        """
        if spot and rarity == "blue" and random.random() < FishingService.SPOT_EXCLUSIVE_CHANCE:
            return FishingService.COASTAL_FISHING_SPOTS[spot]
        rarity_config = (
            FishingService.GHOST_FISH_RARITY_CONFIG if in_dungeon
            else FishingService.FISH_RARITY_CONFIG
        )
        fish_list = rarity_config[rarity]["fish_list"]
        return random.choice(fish_list)

    @staticmethod
    def roll_salvage(in_dungeon: bool = False) -> Tuple[str, int]:
        """从打捞池中随机一件杂物，返回 (item_id, 数量)"""
        pool = (
            FishingService.DUNGEON_SALVAGE_POOL if in_dungeon
            else FishingService.REAL_WORLD_SALVAGE_POOL
        )
        item_id, _, min_qty, max_qty = random.choices(pool, weights=[p[1] for p in pool])[0]
        return item_id, random.randint(min_qty, max_qty)

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

        # 坐标联动上下文：诡域/沿海钓点
        in_dungeon = (player.dungeon_level or 0) > 0
        spot = self.get_fishing_spot(player)
        current_x, current_y = player.get_current_coordinates()
        dungeon_level = player.dungeon_level or 0

        # 打捞杂物：上钩的不是鱼
        if random.random() < self.JUNK_CATCH_CHANCE:
            junk_id, junk_qty = self.roll_salvage(in_dungeon)
            junk_config = config.items_config["by_id"].get(junk_id)
            if junk_config:
                try:
                    added = await self._item_repo.add_item(player.id, junk_id, junk_qty)
                    # 杂物同样消耗一次钓鱼（计入冷却与每日次数），但不计入鱼类统计
                    await self._fishing_record_repo.record_fishing(
                        player.id, junk_id, junk_qty, current_x, current_y, dungeon_level
                    )
                    fishing_stats = await self._fishing_stats_repo.get_or_create(player.id)
                    fishing_stats.total_fishing_count += 1
                    await self._fishing_stats_repo.update(fishing_stats)

                    return {
                        "success": True,
                        "is_junk": True,
                        "junk_added": bool(added),
                        "fish_name": junk_config.name,
                        "fish_id": junk_id,
                        "quantity": junk_qty,
                        "rarity": junk_config.rarity or "white",
                        "value": junk_config.price * junk_qty,
                        "spot": spot,
                        "in_dungeon": in_dungeon,
                    }
                except ValueError as e:
                    return {"success": False, "message": f"钓鱼失败：{e}"}
            # 杂物配置缺失时回落到正常钓鱼流程

        # 计算鱼类稀有度
        rarity = self.calculate_fish_rarity(player, spot=spot, in_dungeon=in_dungeon)

        # 获取具体鱼类
        fish_id = self.get_random_fish(rarity, spot=spot, in_dungeon=in_dungeon)

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
            await self._fishing_record_repo.record_fishing(
                player.id, fish_id, quantity, current_x, current_y, dungeon_level
            )

            # 更新钓鱼统计
            fishing_stats = await self._fishing_stats_repo.get_or_create(player.id)
            await self._fishing_stats_repo.update_stats(
                fishing_stats, fish_config.price, rarity, quantity, dungeon_level=dungeon_level
            )

            # P0问题修复：移除内部commit，由调用方控制事务
            # 原代码 Line 239: await session.commit() - 已移除

            return {
                "success": True,
                "is_junk": False,
                "fish_name": fish_config.name,
                "fish_id": fish_id,
                "quantity": quantity,
                "rarity": rarity,
                "value": fish_config.price * quantity,
                "rarity_display": fish_config.get_rarity_display(),
                "spot": spot,
                "in_dungeon": in_dungeon,
                "is_exclusive": fish_id in self.COASTAL_FISHING_SPOTS.values(),
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
    def calculate_fishing_probabilities(player: Player, spot: Optional[str] = None, in_dungeon: bool = False) -> Dict[str, Dict[str, float]]:
        """计算玩家钓到各品阶鱼的概率

        Args:
            player: 玩家对象
            spot: 所处沿海钓点城市名（None表示不在钓点）
            in_dungeon: 是否在诡域中垂钓

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

        rarity_config = (
            FishingService.GHOST_FISH_RARITY_CONFIG if in_dungeon
            else FishingService.FISH_RARITY_CONFIG
        )
        # 计算各品阶的概率
        for rarity, config in rarity_config.items():
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

            # 沿海钓点加成（并入展示倍率）
            if spot:
                luck_multiplier *= FishingService.SPOT_RARITY_BONUS.get(rarity, 1.0)

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
