"""钓鱼系统核心服务类

实现钓鱼概率计算、鱼类获取逻辑等核心功能
"""

import random
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta

from ..config import config
from ..models.fishing_record import FishingRecord, FishingStats
from ..models.inventory import ItemInstance
from ..models.player import Player


class FishingService:
    """钓鱼服务类"""
    
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
    
    @classmethod
    async def can_fishing(cls, session, player: Player) -> Tuple[bool, str]:
        """检查玩家是否可以钓鱼
        
        Returns:
            (can_fish, reason): 是否可以钓鱼和原因
        """
        # 检查冷却时间
        can_fish_cooldown = await FishingRecord.can_fishing(session, player.id, cls.FISHING_COOLDOWN)
        if not can_fish_cooldown:
            last_time = await FishingRecord.get_last_fishing_time(session, player.id)
            if last_time:
                next_time = last_time + timedelta(minutes=cls.FISHING_COOLDOWN)
                remaining = next_time - datetime.now()
                minutes = int(remaining.total_seconds() // 60)
                seconds = int(remaining.total_seconds() % 60)
                return False, f"钓鱼冷却中，还需等待 {minutes}分{seconds}秒"
        
        # 检查每日钓鱼次数限制
        stats = await FishingRecord.get_player_fishing_stats(session, player.id)
        if stats["today_fishing_count"] >= cls.DAILY_FISHING_LIMIT:
            return False, f"今日钓鱼次数已达上限（{cls.DAILY_FISHING_LIMIT}次），明天再来吧！"
        
        # 检查背包空间（通过计算当前使用情况）
        # 注意：鱼类不占用背包空间，所以不需要检查背包容量
        # 钓鱼系统使用独立的鱼栏存储，类似装备栏
        
        return True, ""
    
    @classmethod
    def calculate_fish_rarity(cls, player: Player) -> str:
        """根据玩家属性计算钓到鱼的稀有度

        Args:
            player: 玩家对象

        Returns:
            稀有度字符串
        """
        # 基础概率
        weights = []
        rarities = []

        for rarity, config in cls.FISH_RARITY_CONFIG.items():
            base_weight = config["weight"]

            # 运气值影响稀有鱼概率（分层加成，让高运气玩家感受明显提升）
            from ..utils import luck_prob
            luck_factor = luck_prob(player.luck)

            if rarity == "orange":
                # 橙色传说鱼：运气加成最大，最多增加原概率的300%
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
    
    @classmethod
    def get_random_fish(cls, rarity: str) -> str:
        """根据稀有度随机获取鱼类ID
        
        Args:
            rarity: 稀有度
            
        Returns:
            鱼类物品ID
        """
        fish_list = cls.FISH_RARITY_CONFIG[rarity]["fish_list"]
        return random.choice(fish_list)
    
    @classmethod
    def calculate_fish_quantity(cls, player: Player, rarity: str) -> int:
        """计算钓到鱼的数量
        
        Args:
            player: 玩家对象
            rarity: 鱼类稀有度
            
        Returns:
            鱼的数量
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
        
        # 运气值影响数量（优化后的数量加成机制）
        luck_bonus = 0
        from ..utils import luck_prob
        luck_factor = luck_prob(player.luck)

        # 根据稀有度和运气值计算额外数量
        if rarity == "white":
            # 白色鱼：高运气时有更高概率获得额外数量
            if random.random() < luck_factor * 0.4:  # 最高40%概率
                luck_bonus += 1
            if random.random() < luck_factor * 0.2:  # 最高20%概率
                luck_bonus += 1
        elif rarity == "green":
            # 绿色鱼：中等概率获得额外数量
            if random.random() < luck_factor * 0.3:  # 最高30%概率
                luck_bonus += 1
        elif rarity == "blue":
            # 蓝色鱼：较低概率获得额外数量
            if random.random() < luck_factor * 0.2:  # 最高20%概率
                luck_bonus += 1
        # 紫色和橙色鱼保持稀缺性，不增加数量
        
        return base_quantity + luck_bonus
    
    @classmethod
    async def do_fishing(cls, session, player: Player) -> Dict:
        """执行钓鱼操作
        
        Args:
            session: 数据库会话
            player: 玩家对象
            
        Returns:
            钓鱼结果字典
        """
        # 检查是否可以钓鱼
        can_fish, reason = await cls.can_fishing(session, player)
        if not can_fish:
            return {"success": False, "message": reason}
        
        # 计算鱼类稀有度
        rarity = cls.calculate_fish_rarity(player)
        
        # 获取具体鱼类
        fish_id = cls.get_random_fish(rarity)
        
        # 计算数量
        quantity = cls.calculate_fish_quantity(player, rarity)
        
        # 获取鱼类配置
        fish_config = config.items_config["by_id"].get(fish_id)
        if not fish_config:
            return {"success": False, "message": "鱼类配置错误"}
        
        try:
            # 添加鱼类到背包
            await ItemInstance.add_item(session, player.id, fish_id, quantity)
            
            # 记录钓鱼活动
            current_x, current_y = player.get_current_coordinates()
            await FishingRecord.record_fishing(session, player.id, fish_id, quantity, current_x, current_y)
            
            # 更新钓鱼统计
            fishing_stats = await FishingStats.get_or_create(session, player.id)
            await fishing_stats.update_stats(session, fish_config.price, rarity, quantity)
            
            # 提交事务
            await session.commit()
            
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
            await session.rollback()
            return {"success": False, "message": f"钓鱼失败：{e}"}
        except Exception as e:
            await session.rollback()
            return {"success": False, "message": f"钓鱼过程中发生错误：{e}"}
    
    @classmethod
    async def get_fishing_leaderboard(cls, session, limit: int = 10) -> List[Dict]:
        """获取钓鱼排行榜

        Args:
            session: 数据库会话
            limit: 返回数量限制

        Returns:
            排行榜列表
        """
        from sqlalchemy import select, desc

        stmt = select(FishingStats, Player.nickname, Player.uid).join(
            Player, FishingStats.player_id == Player.id
        ).order_by(desc(FishingStats.total_fish_value)).limit(limit)

        result = await session.execute(stmt)
        leaderboard = []

        for stats, nickname, uid in result:
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
