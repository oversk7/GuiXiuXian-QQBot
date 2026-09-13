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
from typing import Optional, Dict, Tuple
from datetime import datetime
from ..utils_markdown import cmd
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
        if existing_quest.scalars().first():
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
        if existing.scalars().first():
            return False

        session.add(cls._make_quest(player.id, chain_id, steps[0]))
        return True

    @staticmethod
    def _make_quest(player_id: str, chain_id: str, first_step: Dict) -> DailyTask:
        return DailyTask(
            player_id=player_id,
            task_type=TaskType.TUTORIAL.value,
            title=first_step["title"],
            description=first_step["description"],
            target_region="新手区",
            target_x=0,
            target_y=0,
            quest_chain_id=chain_id,
            quest_step=first_step["step"],
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

    @staticmethod
    def is_eligible(player: Player) -> bool:
        return player.level < 30 and (player.reincarnation_level or 0) == 0

    @classmethod
    async def get_current_quest(cls, session: AsyncSession, player_id: str) -> Optional[DailyTask]:
        """恢复新手未完成的教程，按配置顺序选择步骤，保留完成记录。"""
        player = await session.get(Player, player_id)
        if player is None or not cls.is_eligible(player):
            return None
        # 调用方可能已修改修炼/突破收益；先刷新，再获取玩家锁，不能覆盖这些修改。
        await session.flush()
        player = (await session.execute(
            select(Player).where(Player.id == player_id).with_for_update()
            .execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if player is None or not cls.is_eligible(player):
            return None
        quests = list((await session.execute(
            select(DailyTask)
            .where(DailyTask.player_id == player_id, DailyTask.is_tutorial == True)
            .order_by(DailyTask.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )).scalars().all())
        if not quests and player.level > 1:
            return None

        for quest in quests:
            if quest.status.startswith("TaskStatus."):
                quest.status = quest.status.removeprefix("TaskStatus.").lower()
            quest.task_type = TaskType.TUTORIAL.value
            if quest.status == TaskStatus.ACCEPTED.value:
                quest.status = TaskStatus.AVAILABLE.value

        chain_id = cls._get_first_chain_id()
        while chain_id:
            chain = cls._get_chain_config(chain_id)
            if not chain:
                return None
            chain_quests = [q for q in quests if (q.quest_chain_id or "novice_basic") == chain_id]
            completed_steps = {
                q.quest_step for q in chain_quests if q.status == TaskStatus.COMPLETED.value
            }
            # step 是持久化身份；教学顺序由配置数组决定，调整顺序不重复发已领奖励。
            for step in chain.get("steps", []):
                if step["step"] in completed_steps:
                    continue
                candidates = [q for q in chain_quests if q.quest_step == step["step"]]
                current = candidates[-1] if candidates else cls._make_quest(player_id, chain_id, step)
                current.quest_chain_id = chain_id
                current.title = step["title"]
                current.description = step["description"]
                current.status = TaskStatus.ACCEPTED.value
                session.add(current)
                return current
            chain_id = cls._get_next_chain_id(chain_id)
        return None

    @classmethod
    def format_current_quest(cls, quest: DailyTask, player: Player) -> str:
        chain = cls._get_chain_config(quest.quest_chain_id)
        step = next(s for s in chain["steps"] if s["step"] == quest.quest_step)
        progress = ""
        if step["completion_type"] == "command_count":
            progress = f"（{quest.quest_progress or 0}/{step['completion_count']}）"
        guide_command = step.get("guide_command") or (
            "突破" if step["completion_type"] == "level_up" else step["completion_target"]
        )
        if guide_command == "导航":
            from ..economy.merchant_service import MARKETS
            x, y = player.real_world_x or 0, player.real_world_y or 0
            destination = min(
                (market for market in MARKETS if (market.x, market.y) != (x, y)),
                key=lambda market: (market.x - x) ** 2 + (market.y - y) ** 2,
            )
            guide_command = f"导航 {destination.name}"
        if step["completion_type"] == "level_up" and player.level == 1:
            from ..utils import calculate_level_up_exp
            if player.exp < calculate_level_up_exp(1, player.server_id):
                guide_command = "睁开眼" if player.prologue_step < 2 else "修炼"
        if player.is_in_dungeon() and guide_command.split()[0] in {"观察", "导航", "打工", "市集"}:
            guide_command = "返回"
        return (
            f"🎯 **{quest.title}{progress}**\n"
            f"{step['description']}\n"
            f"下一步：{cmd(guide_command)}\n"
            f"> {cmd('新手任务')} 随时查看进度"
        )

    @classmethod
    async def check_and_advance_quest(
        cls,
        session: AsyncSession,
        player: Player,
        action_type: str,
        action_data: Optional[Dict] = None
    ) -> Tuple[bool, Optional[str]]:
        """推进当前动作和已达成的状态；奖励与进度交由调用方一起提交。"""
        if not cls.is_eligible(player):
            return False, None
        action_data = action_data or {}
        current = await cls.get_current_quest(session, player.id)
        completed_any = False
        messages = []
        while current:
            chain_id = current.quest_chain_id
            chain = cls._get_chain_config(chain_id)
            step = next(s for s in chain["steps"] if s["step"] == current.quest_step)
            if (
                step["completion_type"] == "command_count"
                and action_type == "command"
                and cls._commands_match(action_data.get("command"), step["completion_target"])
            ):
                current.quest_progress = (current.quest_progress or 0) + 1
                action_data = {**action_data, "progress": current.quest_progress}
            if not cls._check_completion(step, action_type, action_data, player):
                break

            step_messages = []
            try:
                # 单步和整链奖励共同回滚，保留调用方已完成的指令操作。
                async with session.begin_nested():
                    current.complete_task()
                    reward = await cls._give_rewards(session, player, step["rewards"])
                    step_messages.append(f"✨ 完成：{current.title}\n{reward}")
                    next_quest = await cls.get_current_quest(session, player.id)
                    if next_quest is None or next_quest.quest_chain_id != chain_id:
                        reward = await cls._give_rewards(session, player, chain.get("completion_reward", {}))
                        step_messages.append(f"🎊 「{chain['name']}」已完成\n{reward}")
            except ValueError as exc:
                if str(exc) != "背包空间不足":
                    raise
                await session.refresh(player)
                messages.append("🎁 背包空间不足，新手任务奖励暂未领取。整理背包后重试，奖励与任务进度已保留。")
                return completed_any, "\n\n".join(messages)
            messages.extend(step_messages)
            completed_any = True
            current = next_quest
            # 同一指令只计一次；下一步仅回填等级、签到等已有状态。
            action_type, action_data = "state", {}

        if current:
            messages.append(cls.format_current_quest(current, player))
        elif completed_any:
            messages.append(f"🌟 新手引导已完成。{cmd('帮助')} | {cmd('观察')}")
        return completed_any, "\n\n".join(messages) or None

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
            if completion_target == "签到" and getattr(player, "last_sign", None):
                if player.last_sign.date() == datetime.now().date():
                    return True
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
            return player.level >= completion_target

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
            player.attribute_points += rewards["attribute_points"]
            reward_parts.append(f"属性点+{rewards['attribute_points']}")

        # 物品奖励
        if "items" in rewards:
            for item_reward in rewards["items"]:
                item_id = item_reward["item_id"]
                quantity = item_reward["quantity"]
                await ItemInstance.add_item(session, player.id, item_id, quantity)

                # 获取物品名称
                item_config = config.items_config["by_id"][item_id]
                item_name = item_config.name
                reward_parts.append(f"{item_name}×{quantity}")

        session.add(player)

        return "🎁 奖励：" + " ".join(reward_parts) if reward_parts else ""
