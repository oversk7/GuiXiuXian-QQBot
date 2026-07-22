"""
新手任务链服务
处理新手玩家的引导任务系统，支持多章节任务链
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from ..models.player import Player
from ..models.daily_task import DailyTask, TaskType, TaskStatus
from ..models.inventory import ItemInstance
from ..config import config
from typing import Optional, Dict, List, Tuple
import yaml
from pathlib import Path


class NoviceQuestService:
    """新手任务链服务（支持多章节）"""

    # 缓存配置文件
    _quest_config: Optional[Dict] = None

    @classmethod
    def _load_quest_config(cls) -> Dict:
        """加载新手任务配置"""
        if cls._quest_config is None:
            config_path = Path(__file__).parent.parent / "data" / "novice_quests.yaml"
            with open(config_path, "r", encoding="utf-8") as f:
                cls._quest_config = yaml.safe_load(f)
        return cls._quest_config

    @classmethod
    def _get_chain_config(cls, chain_id: str) -> Optional[Dict]:
        """根据 chain_id 查找链配置"""
        config_data = cls._load_quest_config()
        chains = config_data.get("chains", [])
        for chain in chains:
            if chain["chain_id"] == chain_id:
                return chain
        # 向后兼容：旧格式 novice_basic_chain
        if chain_id == "novice_basic" and "novice_basic_chain" in config_data:
            return config_data["novice_basic_chain"]
        return None

    @classmethod
    def _get_first_chain_id(cls) -> str:
        """获取第一章的 chain_id"""
        config_data = cls._load_quest_config()
        chains = config_data.get("chains", [])
        if chains:
            # 找 unlock_after 为 null 的链
            for chain in chains:
                if chain.get("unlock_after") is None:
                    return chain["chain_id"]
            return chains[0]["chain_id"]
        # 向后兼容
        return "novice_basic"

    @classmethod
    def _get_next_chain_id(cls, current_chain_id: str) -> Optional[str]:
        """查找当前链完成后应解锁的下一条链"""
        config_data = cls._load_quest_config()
        chains = config_data.get("chains", [])
        for chain in chains:
            if chain.get("unlock_after") == current_chain_id:
                return chain["chain_id"]
        return None

    @classmethod
    async def init_novice_quests(cls, session: AsyncSession, player: Player) -> bool:
        """
        为新玩家初始化新手任务链（第一章）

        Args:
            session: 数据库会话
            player: 玩家对象

        Returns:
            bool: 是否成功初始化
        """
        # 只有1级新手且没有任何新手任务时才初始化
        if player.level > 1:
            return False

        # 检查是否已有新手任务
        existing_quest = await session.execute(
            select(DailyTask).where(
                and_(
                    DailyTask.player_id == player.id,
                    DailyTask.is_tutorial == True
                )
            )
        )
        if existing_quest.scalar_one_or_none():
            return False  # 已有新手任务，不重复初始化

        first_chain_id = cls._get_first_chain_id()
        return await cls._init_chain(session, player, first_chain_id)

    @classmethod
    async def _init_chain(cls, session: AsyncSession, player: Player, chain_id: str) -> bool:
        """初始化指定的任务链（创建第一个任务）"""
        chain_config = cls._get_chain_config(chain_id)
        if not chain_config:
            return False

        steps = chain_config.get("steps", [])
        if not steps:
            return False

        # 检查该链是否已有任务（防止重复初始化）
        existing = await session.execute(
            select(DailyTask).where(
                and_(
                    DailyTask.player_id == player.id,
                    DailyTask.quest_chain_id == chain_id,
                    DailyTask.is_tutorial == True
                )
            )
        )
        if existing.scalar_one_or_none():
            return False

        first_step = steps[0]
        quest = DailyTask(
            player_id=player.id,
            task_type=TaskType.TUTORIAL.value,
            title=first_step["title"],
            description=first_step["description"],
            target_region="新手区",
            target_x=0,
            target_y=0,
            quest_chain_id=chain_id,
            quest_step=1,
            quest_progress=0,
            is_tutorial=True,
            auto_accept=first_step.get("auto_accept", False),
            exp_reward=first_step["rewards"].get("exp", 0),
            gold_reward=first_step["rewards"].get("gold", 0),
            status=TaskStatus.ACCEPTED.value if first_step.get("auto_accept") else TaskStatus.AVAILABLE.value,
            enemy_name="",
            enemy_level=0,
            enemy_hp=0,
            enemy_attack=0,
            enemy_defense=0,
            enemy_agility=0
        )

        session.add(quest)
        return True

    @classmethod
    async def get_current_quest(cls, session: AsyncSession, player_id: str) -> Optional[DailyTask]:
        """
        获取玩家当前的新手任务（任意章节）

        Args:
            session: 数据库会话
            player_id: 玩家ID

        Returns:
            当前激活的新手任务，如果没有则返回None
        """
        result = await session.execute(
            select(DailyTask).where(
                and_(
                    DailyTask.player_id == player_id,
                    DailyTask.is_tutorial == True,
                    DailyTask.status == TaskStatus.ACCEPTED.value
                )
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def check_and_advance_quest(
        cls,
        session: AsyncSession,
        player: Player,
        action_type: str,
        action_data: Optional[Dict] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        检查是否完成当前新手任务，并自动推进到下一步

        Args:
            session: 数据库会话
            player: 玩家对象
            action_type: 动作类型 ("command", "command_count", "level_up")
            action_data: 动作数据，如 {"command": "修炼"}

        Returns:
            (是否完成任务, 完成消息)
        """
        action_data = action_data or {}

        # 获取当前任务
        current_quest = await cls.get_current_quest(session, player.id)
        if not current_quest:
            return False, None

        chain_id = current_quest.quest_chain_id or "novice_basic"

        # 加载链配置
        chain_config = cls._get_chain_config(chain_id)
        if not chain_config:
            return False, None

        steps = chain_config.get("steps", [])

        # 找到当前步骤配置
        current_step_config = None
        for step in steps:
            if step["step"] == current_quest.quest_step:
                current_step_config = step
                break

        if not current_step_config:
            return False, None

        # 检查完成条件；累计型任务先记录本次匹配动作的进度
        if current_step_config.get("completion_type") == "command_count":
            command = action_data.get("command")
            target = current_step_config.get("completion_target")
            if cls._commands_match(command, target):
                current_quest.quest_progress = (current_quest.quest_progress or 0) + 1
            else:
                return False, None
            action_data = {**action_data, "progress": current_quest.quest_progress}

        completed = cls._check_completion(current_step_config, action_type, action_data, player)

        if not completed:
            return False, None

        # 完成当前任务
        current_quest.complete_task()

        # 发放奖励
        reward_msg = await cls._give_rewards(session, player, current_step_config["rewards"])

        # 生成下一步任务
        next_step = current_quest.quest_step + 1
        next_task = None
        chain_completed = False
        chain_name = chain_config.get("name", "")

        if next_step <= len(steps):
            # 本链还有下一步
            next_step_config = steps[next_step - 1]
            next_task = DailyTask(
                player_id=player.id,
                task_type=TaskType.TUTORIAL.value,
                title=next_step_config["title"],
                description=next_step_config["description"],
                target_region="新手区",
                target_x=0,
                target_y=0,
                quest_chain_id=chain_id,
                quest_step=next_step,
                quest_progress=0,
                is_tutorial=True,
                auto_accept=next_step_config.get("auto_accept", False),
                exp_reward=next_step_config["rewards"].get("exp", 0),
                gold_reward=next_step_config["rewards"].get("gold", 0),
                status=TaskStatus.ACCEPTED.value if next_step_config.get("auto_accept") else TaskStatus.AVAILABLE.value,
                enemy_name="",
                enemy_level=0,
                enemy_hp=0,
                enemy_attack=0,
                enemy_defense=0,
                enemy_agility=0
            )
            session.add(next_task)
        else:
            # 本链已完成
            chain_completed = True

            # 发放章节完成奖励
            completion_reward = chain_config.get("completion_reward", {})
            if completion_reward:
                chain_reward_msg = await cls._give_rewards(session, player, completion_reward)
            else:
                chain_reward_msg = ""

            # 尝试解锁下一条链
            next_chain_id = cls._get_next_chain_id(chain_id)
            if next_chain_id:
                await cls._init_chain(session, player, next_chain_id)

        await session.commit()

        # 构建完成消息
        flavor_text = current_step_config.get("flavor_text", "")
        completion_msg = (
            f"✨ 新手任务完成！\n"
            f"━━━━━━━━━━━━━\n"
            f"📋 {current_quest.title}\n"
            f"{reward_msg}\n"
        )

        if not chain_completed:
            # 本链还有下一步
            completion_msg += (
                f"━━━━━━━━━━━━━\n"
                f"🎯 新任务：{next_task.title}\n"
                f"💬 {next_task.description}\n"
            )
            if flavor_text:
                completion_msg += f"🌙 {flavor_text}"
        else:
            # 章节完成
            completion_reward = chain_config.get("completion_reward", {})
            achievement_title = completion_reward.get("achievement_title", "")
            completion_msg += (
                f"━━━━━━━━━━━━━\n"
                f"🎊 「{chain_name}」全部完成！\n"
            )
            if chain_reward_msg:
                completion_msg += f"{chain_reward_msg}\n"
            if achievement_title:
                completion_msg += f"🏆 获得称号：{achievement_title}\n"

            # 提示下一章
            next_chain_id = cls._get_next_chain_id(chain_id)
            if next_chain_id:
                next_chain_config = cls._get_chain_config(next_chain_id)
                if next_chain_config:
                    next_chain_name = next_chain_config.get("name", "")
                    next_steps = next_chain_config.get("steps", [])
                    if next_steps:
                        completion_msg += (
                            f"━━━━━━━━━━━━━\n"
                            f"📖 新篇章解锁：「{next_chain_name}」\n"
                            f"🎯 第一个任务：{next_steps[0]['title']}\n"
                            f"💬 {next_steps[0]['description']}"
                        )
            else:
                completion_msg += "🌟 所有新手引导已完成，自由探索诡异世界吧！"

        return True, completion_msg

    @staticmethod
    def _commands_match(command: Optional[str], target: Optional[str]) -> bool:
        """判断玩家指令是否命中新手任务目标，兼容已公开的旧别名。"""
        if not command or not target:
            return False
        if target == "前往":
            return command in {"前往", "导航"}
        return command == target

    @classmethod
    def _check_completion(
        cls,
        step_config: Dict,
        action_type: str,
        action_data: Dict,
        player: Player
    ) -> bool:
        """检查任务完成条件"""
        completion_type = step_config.get("completion_type")
        completion_target = step_config.get("completion_target")

        if completion_type == "command":
            # 单次指令完成
            return action_type == "command" and cls._commands_match(
                action_data.get("command"), completion_target
            )

        elif completion_type == "command_count":
            # 累计指令完成，进度由当前新手任务记录持久化
            return (
                action_type == "command"
                and cls._commands_match(action_data.get("command"), completion_target)
                and action_data.get("progress", 0) >= step_config.get("completion_count", 1)
            )

        elif completion_type == "level_up":
            # 等级达成
            return action_type == "level_up" and player.level >= completion_target

        return False

    @classmethod
    async def _give_rewards(
        cls,
        session: AsyncSession,
        player: Player,
        rewards: Dict
    ) -> str:
        """发放任务奖励"""
        reward_parts = []

        # 经验奖励
        if "exp" in rewards and rewards["exp"] > 0:
            player.exp += rewards["exp"]
            reward_parts.append(f"怨炁+{rewards['exp']}")

        # 金币奖励
        if "gold" in rewards and rewards["gold"] > 0:
            player.gold += rewards["gold"]
            # 更新财富成就统计
            from ..achievement.achievement_service import AchievementService
            await AchievementService.update_stat(session, player.id, "gold_earned_total", increment=rewards["gold"], auto_commit=False)
            reward_parts.append(f"金币+{rewards['gold']}")

        # 属性点奖励
        if "attribute_points" in rewards and rewards["attribute_points"] > 0:
            player.unused_points += rewards["attribute_points"]
            reward_parts.append(f"属性点+{rewards['attribute_points']}")

        # 物品奖励
        if "items" in rewards:
            for item_reward in rewards["items"]:
                item_id = item_reward["item_id"]
                quantity = item_reward["quantity"]
                await ItemInstance.add_item(session, player.id, item_id, quantity)

                # 获取物品名称
                item_config = config.items_config.get(item_id, {})
                item_name = item_config.get("name", item_id)
                reward_parts.append(f"{item_name}×{quantity}")

        session.add(player)

        return "🎁 奖励：" + " ".join(reward_parts) if reward_parts else ""
