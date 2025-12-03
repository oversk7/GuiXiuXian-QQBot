"""
成就系统服务
处理成就解锁、进度追踪和奖励发放
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from ..models.player import Player
from ..models.achievement import PlayerAchievement, PlayerStats
from ..models.inventory import ItemInstance
from ..config import config
from typing import Optional, Dict, List
import yaml
from pathlib import Path
from datetime import datetime, timedelta


class AchievementService:
    """成就系统服务"""

    # 缓存配置文件
    _achievement_config: Optional[Dict] = None

    @classmethod
    def _load_achievement_config(cls) -> Dict:
        """加载成就配置（缓存）"""
        if cls._achievement_config is None:
            config_path = Path(__file__).parent.parent / "data" / "achievements.yaml"
            with open(config_path, "r", encoding="utf-8") as f:
                cls._achievement_config = yaml.safe_load(f)
        return cls._achievement_config

    @classmethod
    async def init_player_stats(cls, session: AsyncSession, player_id: str):
        """
        初始化玩家统计数据

        对于老玩家，会根据当前游戏状态估算历史统计数据

        Args:
            session: 数据库会话
            player_id: 玩家ID
        """
        from ..models.player import Player
        from ..models.inventory import ItemInstance

        # 检查是否已存在
        result = await session.execute(
            select(PlayerStats).where(PlayerStats.player_id == player_id)
        )
        existing = result.scalar_one_or_none()

        if not existing:
            # 获取玩家对象以估算历史数据
            player_result = await session.execute(
                select(Player).where(Player.id == player_id)
            )
            player = player_result.scalar_one_or_none()

            if not player:
                # 玩家不存在，创建空统计
                stats = PlayerStats(player_id=player_id)
                session.add(stats)
                await session.commit()
                return

            # 估算历史统计数据
            estimated_stats = {
                "cultivation_count": 0,
                "total_battles": 0,
                "total_wins": 0,
                "total_kills": 0,
                "equipment_obtained": 0,
            }

            # 1. 根据等级估算修炼次数（每级约需5-10次修炼，取平均7.5）
            if player.level > 1:
                estimated_stats["cultivation_count"] = int((player.level - 1) * 7.5)

            # 2. 使用 Player 模型中的战斗统计（如果有）
            if hasattr(player, 'total_battles'):
                estimated_stats["total_battles"] = player.total_battles or 0
            if hasattr(player, 'total_wins'):
                estimated_stats["total_wins"] = player.total_wins or 0
                estimated_stats["total_kills"] = player.total_wins or 0  # 估算击杀数=胜利数

            # 3. 统计玩家已拥有的装备数量（包括已装备和背包中的）
            inventory_result = await session.execute(
                select(ItemInstance).where(
                    ItemInstance.player_id == player_id,
                    ItemInstance.item_type.in_(["weapon", "armor", "accessory", "artifact"])
                )
            )
            inventory_items = inventory_result.scalars().all()
            if inventory_items:
                estimated_stats["equipment_obtained"] = sum(item.quantity for item in inventory_items)

            # 创建统计记录
            stats = PlayerStats(
                player_id=player_id,
                cultivation_count=estimated_stats["cultivation_count"],
                total_battles=estimated_stats["total_battles"],
                total_wins=estimated_stats["total_wins"],
                total_kills=estimated_stats["total_kills"],
                equipment_obtained=estimated_stats["equipment_obtained"]
            )
            session.add(stats)
            await session.commit()

    @classmethod
    async def update_stat(
        cls,
        session: AsyncSession,
        player_id: str,
        stat_name: str,
        increment: int = 1
    ):
        """
        更新玩家统计数据

        Args:
            session: 数据库会话
            player_id: 玩家ID
            stat_name: 统计项名称
            increment: 增量值（默认1）
        """
        # 确保统计数据存在
        await cls.init_player_stats(session, player_id)

        # 更新统计
        result = await session.execute(
            select(PlayerStats).where(PlayerStats.player_id == player_id)
        )
        stats = result.scalar_one()

        # 根据统计类型更新
        if hasattr(stats, stat_name):
            current_value = getattr(stats, stat_name)
            setattr(stats, stat_name, current_value + increment)
            session.add(stats)
            await session.commit()

    @classmethod
    async def update_login_streak(cls, session: AsyncSession, player_id: str):
        """
        更新登录连续天数

        Args:
            session: 数据库会话
            player_id: 玩家ID
        """
        await cls.init_player_stats(session, player_id)

        result = await session.execute(
            select(PlayerStats).where(PlayerStats.player_id == player_id)
        )
        stats = result.scalar_one()

        today = datetime.now().date()
        last_login = stats.last_login_date.date() if stats.last_login_date else None

        if last_login:
            # 计算天数差
            days_diff = (today - last_login).days

            if days_diff == 0:
                # 今天已经登录过
                return
            elif days_diff == 1:
                # 连续登录
                stats.consecutive_login_days += 1
            else:
                # 中断了，重新开始
                stats.consecutive_login_days = 1
        else:
            # 第一次登录
            stats.consecutive_login_days = 1

        stats.last_login_date = datetime.now()
        stats.total_login_days += 1
        session.add(stats)
        await session.commit()

    @classmethod
    async def add_visited_location(
        cls,
        session: AsyncSession,
        player_id: str,
        location_key: str
    ):
        """
        添加访问过的地点

        Args:
            session: 数据库会话
            player_id: 玩家ID
            location_key: 地点唯一标识（如"region:x:y"）
        """
        await cls.init_player_stats(session, player_id)

        result = await session.execute(
            select(PlayerStats).where(PlayerStats.player_id == player_id)
        )
        stats = result.scalar_one()

        # 解析已访问地点列表
        visited_list = stats.locations_visited_list.split(",") if stats.locations_visited_list else []

        if location_key not in visited_list:
            visited_list.append(location_key)
            stats.locations_visited_list = ",".join(visited_list)
            stats.locations_visited = len(visited_list)
            session.add(stats)
            await session.commit()

    @classmethod
    async def check_achievements(cls, session: AsyncSession, player: Player) -> List[str]:
        """
        检查并解锁新成就

        Args:
            session: 数据库会话
            player: 玩家对象

        Returns:
            List[str]: 新解锁的成就消息列表
        """
        # 加载配置
        config_data = cls._load_achievement_config()
        achievements = config_data.get("basic_achievements", {})

        # 获取玩家统计数据
        result = await session.execute(
            select(PlayerStats).where(PlayerStats.player_id == player.id)
        )
        stats = result.scalar_one_or_none()

        if not stats:
            return []

        # 获取已解锁的成就
        result = await session.execute(
            select(PlayerAchievement).where(
                and_(
                    PlayerAchievement.player_id == player.id,
                    PlayerAchievement.is_completed == True
                )
            )
        )
        unlocked_achievements = {ach.achievement_id for ach in result.scalars().all()}

        messages = []

        # 检查每个成就
        for achievement_id, achievement_data in achievements.items():
            # 跳过已解锁的成就
            if achievement_id in unlocked_achievements:
                continue

            # 检查条件
            condition_type = achievement_data.get("condition_type")
            condition_value = achievement_data.get("condition_value", 0)
            is_unlocked = False

            if condition_type == "command_count":
                # 修炼次数
                is_unlocked = stats.cultivation_count >= condition_value
            elif condition_type == "level_up" or condition_type == "level_reached":
                # 等级达成
                is_unlocked = player.level >= condition_value
            elif condition_type == "battle_win":
                # 战斗胜利
                is_unlocked = stats.total_wins >= condition_value
            elif condition_type == "kill_count":
                # 击杀数
                is_unlocked = stats.total_kills >= condition_value
            elif condition_type == "equipment_obtained":
                # 装备获得
                is_unlocked = stats.equipment_obtained >= condition_value
            elif condition_type == "gold_total":
                # 金币总额
                is_unlocked = stats.gold_earned_total >= condition_value
            elif condition_type == "locations_visited":
                # 地点探索
                is_unlocked = stats.locations_visited >= condition_value
            elif condition_type == "login_streak":
                # 连续登录
                is_unlocked = stats.consecutive_login_days >= condition_value

            # 如果达成条件，解锁成就
            if is_unlocked:
                unlock_msg = await cls.unlock_achievement(session, player, achievement_id)
                messages.append(unlock_msg)

        return messages

    @classmethod
    async def unlock_achievement(
        cls,
        session: AsyncSession,
        player: Player,
        achievement_id: str
    ) -> str:
        """
        解锁成就并发放奖励

        Args:
            session: 数据库会话
            player: 玩家对象
            achievement_id: 成就ID

        Returns:
            str: 成就解锁消息
        """
        # 加载配置
        config_data = cls._load_achievement_config()
        achievements = config_data.get("basic_achievements", {})
        achievement_data = achievements.get(achievement_id)

        if not achievement_data:
            return ""

        # 检查是否已解锁
        result = await session.execute(
            select(PlayerAchievement).where(
                and_(
                    PlayerAchievement.player_id == player.id,
                    PlayerAchievement.achievement_id == achievement_id
                )
            )
        )
        existing = result.scalar_one_or_none()

        if existing and existing.is_completed:
            return ""  # 已解锁，跳过

        # 创建成就记录
        if existing:
            existing.is_completed = True
            existing.reward_claimed = True
            existing.unlocked_at = datetime.now()
            session.add(existing)
        else:
            achievement_record = PlayerAchievement(
                player_id=player.id,
                achievement_id=achievement_id,
                is_completed=True,
                reward_claimed=True,
                unlocked_at=datetime.now()
            )
            session.add(achievement_record)

        # 发放奖励
        rewards = achievement_data.get("rewards", {})
        reward_parts = []

        if "exp" in rewards and rewards["exp"] > 0:
            player.exp += rewards["exp"]
            reward_parts.append(f"怨炁+{rewards['exp']}")

        if "gold" in rewards and rewards["gold"] > 0:
            player.gold += rewards["gold"]
            reward_parts.append(f"金币+{rewards['gold']}")

        if "attribute_points" in rewards and rewards["attribute_points"] > 0:
            player.attribute_points += rewards["attribute_points"]
            reward_parts.append(f"属性点+{rewards['attribute_points']}")

        session.add(player)
        await session.commit()

        # 构建解锁消息
        icon = achievement_data.get("icon", "🏆")
        title = achievement_data.get("title", "未知成就")
        description = achievement_data.get("description", "")
        flavor_text = achievement_data.get("flavor_text", "")

        message = (
            f"✨ 成就解锁！\n"
            f"━━━━━━━━━━━━━\n"
            f"{icon} {title}\n"
            f"💬 {description}\n"
        )

        if reward_parts:
            message += f"🎁 奖励：{' '.join(reward_parts)}\n"

        if flavor_text:
            message += f"🌙 {flavor_text}\n"

        message += "━━━━━━━━━━━━━"

        return message

    @classmethod
    async def get_player_achievements(
        cls,
        session: AsyncSession,
        player_id: str
    ) -> Dict:
        """
        获取玩家成就列表

        Args:
            session: 数据库会话
            player_id: 玩家ID

        Returns:
            Dict: 包含已解锁和未解锁成就信息的字典
        """
        # 加载配置
        config_data = cls._load_achievement_config()
        achievements = config_data.get("basic_achievements", {})

        # 获取已解锁的成就
        result = await session.execute(
            select(PlayerAchievement).where(
                and_(
                    PlayerAchievement.player_id == player_id,
                    PlayerAchievement.is_completed == True
                )
            )
        )
        unlocked_ids = {ach.achievement_id for ach in result.scalars().all()}

        # 获取玩家统计数据
        result = await session.execute(
            select(PlayerStats).where(PlayerStats.player_id == player_id)
        )
        stats = result.scalar_one_or_none()

        # 获取玩家信息（用于等级检查）
        result = await session.execute(
            select(Player).where(Player.id == player_id)
        )
        player = result.scalar_one_or_none()

        unlocked = []
        locked = []
        progress_data = {}

        for achievement_id, achievement_data in achievements.items():
            achievement_info = {
                "id": achievement_id,
                "icon": achievement_data.get("icon", "🏆"),
                "title": achievement_data.get("title", "未知成就"),
                "description": achievement_data.get("description", ""),
                "condition_value": achievement_data.get("condition_value", 0)
            }

            if achievement_id in unlocked_ids:
                unlocked.append(achievement_info)
            else:
                locked.append(achievement_info)

                # 计算进度
                if stats:
                    condition_type = achievement_data.get("condition_type")
                    current_progress = 0

                    if condition_type == "command_count":
                        current_progress = stats.cultivation_count
                    elif condition_type == "level_up" or condition_type == "level_reached":
                        current_progress = player.level if player else 0
                    elif condition_type == "battle_win":
                        current_progress = stats.total_wins
                    elif condition_type == "kill_count":
                        current_progress = stats.total_kills
                    elif condition_type == "equipment_obtained":
                        current_progress = stats.equipment_obtained
                    elif condition_type == "gold_total":
                        current_progress = stats.gold_earned_total
                    elif condition_type == "locations_visited":
                        current_progress = stats.locations_visited
                    elif condition_type == "login_streak":
                        current_progress = stats.consecutive_login_days

                    progress_data[achievement_id] = current_progress

        return {
            "unlocked": unlocked,
            "locked": locked,
            "progress": progress_data
        }
