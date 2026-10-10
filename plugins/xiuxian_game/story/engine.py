"""剧情引擎 - 处理剧情持久化与在线状态流转。"""
import json
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.story_session import StorySession
from ..models.player import Player
from .runtime import (
    StoryRuntime,
    apply_variable_effects,
    effect_changes,
    record_trial_success,
)


class StoryEngine(StoryRuntime):
    """剧情状态机处理器，共享纯运行逻辑。"""

    def __init__(self):
        self._story_index: Dict[str, Path] = {}
        self._story_meta: Dict[str, Dict[str, str]] = {}
        self.story_dir = Path(__file__).parent.parent / "data" / "stories"
        self._build_index()

    def _build_index(self):
        """扫描剧情目录，只读取元数据建立索引，不加载完整内容。"""
        print(f"[StoryEngine] 剧情目录: {self.story_dir}")
        if not self.story_dir.exists():
            print(f"[StoryEngine] [ERROR] 剧情目录不存在，创建目录: {self.story_dir}")
            self.story_dir.mkdir(parents=True, exist_ok=True)
            return

        json_files = list(self.story_dir.glob("*.json"))
        print(f"[StoryEngine] 找到 {len(json_files)} 个剧情文件，建立索引中...")
        for file_path in json_files:
            try:
                with open(file_path, 'r', encoding='utf-8-sig') as f:
                    story_data = json.load(f)
                if not isinstance(story_data, dict):
                    print(f"[StoryEngine] [WARNING] 剧情文件不是对象: {file_path}")
                    continue
                story_id = story_data.get('id')
                if isinstance(story_id, str) and story_id:
                    self._story_index[story_id] = file_path
                    self._story_meta[story_id] = {
                        "title": story_data.get("title", "未命名剧情"),
                        "description": story_data.get("description", "暂无描述"),
                    }
                    print(f"[StoryEngine] 已索引: {story_id}")
                else:
                    print(f"[StoryEngine] [WARNING] 剧情文件缺少ID: {file_path}")
            except (OSError, ValueError) as e:
                print(f"[StoryEngine] [ERROR] 索引剧情文件失败 {file_path}: {e}")
        print(f"[StoryEngine] 索引完成，共 {len(self._story_index)} 个剧情: {list(self._story_index.keys())}")

    def get_story_list(self) -> List[Dict[str, str]]:
        """获取可用剧情列表（只用元数据，无需加载完整内容）。"""
        stories = [{"id": story_id, **meta} for story_id, meta in self._story_meta.items()]
        stories.sort(key=lambda s: (0 if s["id"] == "荔湾鬼镇" else 1))
        return stories

    def get_story(self, story_id: str) -> Optional[Dict[str, Any]]:
        """获取指定剧情（每次从磁盘读取，访问频率低无需缓存）。"""
        file_path = self._story_index.get(story_id)
        if not file_path:
            return None
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                story = json.load(f)
            return story if isinstance(story, dict) else None
        except (OSError, ValueError) as e:
            print(f"[StoryEngine] [ERROR] 加载剧情失败 {file_path}: {e}")
            return None

    async def apply_effects(self, effects: Dict[str, Any], player: Player, variables: Dict[str, Any], session=None) -> Tuple[Player, Dict[str, Any]]:
        """永久属性走既有会话与统一记账入口，其余字段直接修改。"""
        if "player" in effects:
            changes = effects["player"]
            current_values = {attr: getattr(player, attr, 0) for attr in changes}
            new_values = effect_changes(changes, current_values)
            permanent_deltas = {}
            for attr, new_value in new_values.items():
                if session is not None and attr in Player.INIT_ATTRS:
                    permanent_deltas[attr] = int(new_value) - int(current_values[attr])
                else:
                    setattr(player, attr, new_value)
            if permanent_deltas:
                from ..domain.attributes.permanent_change import (
                    LEDGER_STORY_REWARD,
                    apply_permanent_change,
                )
                await apply_permanent_change(
                    session, player, permanent_deltas,
                    ledger_item_id=LEDGER_STORY_REWARD,
                )
        variables = apply_variable_effects(effects, variables)
        return player, variables

    async def apply_special_effects(self, effects: Dict[str, Any], player: Player, variables: Dict[str, Any], session: AsyncSession) -> Tuple[Player, Dict[str, Any], str]:
        """应用特殊效果，如首次试炼奖励。"""
        reward_message = ""
        record_trial_success(effects, player, variables)
        if "first_trial_reward" in effects and effects["first_trial_reward"]:
            reward_msg = await self._handle_first_trial_reward(session, player)
            if reward_msg:
                reward_message = f"\n\n{reward_msg}"
        return player, variables, reward_message

    async def _handle_first_trial_reward(self, session: AsyncSession, player: Player) -> str:
        """处理首次试炼奖励 - 已移除鬼怪系统。"""
        return ""

    def get_current_node(self, story_session: StorySession, player: Player) -> Optional[Dict[str, Any]]:
        """获取当前节点信息。"""
        story = self.get_story(story_session.story_id)
        if not isinstance(story, dict):
            return None
        nodes = story.get("nodes", {})
        if not isinstance(nodes, dict):
            return None
        current_node = nodes.get(story_session.current_node)
        if not isinstance(current_node, dict) or not current_node:
            return None
        variables = story_session.get_variables()
        current_node = current_node.copy()
        if "content" in current_node:
            current_node["content"] = self.format_content(current_node["content"], player, variables)
        if current_node.get("type") == "choice" and "options" in current_node:
            current_node["options"] = self.visible_options(current_node, player, variables)
        return current_node

    async def process_choice(self, story_session: StorySession, player: Player, choice_id: int, session=None) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """处理玩家选择，保持既有选项效果触发时机。"""
        story = self.get_story(story_session.story_id)
        if not isinstance(story, dict):
            return False, "剧情不存在", None
        nodes = story.get("nodes", {})
        current_node = nodes.get(story_session.current_node) if isinstance(nodes, dict) else None
        if not isinstance(current_node, dict) or current_node.get("type") != "choice":
            return False, "当前不是选择节点", None
        options = current_node.get("options", [])
        if not isinstance(options, list):
            return False, "无效的选择", None
        selected_option = next((option for option in options
                                if isinstance(option, dict) and option.get("id") == choice_id), None)
        if not selected_option:
            return False, "无效的选择", None
        variables = story_session.get_variables()
        if "conditions" in selected_option:
            if not self.evaluate_condition(selected_option["conditions"], player, variables):
                return False, "不满足选择条件", None
        if "effects" in selected_option:
            player, variables = await self.apply_effects(selected_option["effects"], player, variables, session=session)
            story_session.set_variables(variables)
        next_node_id = self.resolve_next(selected_option.get("next"), player, variables)
        if next_node_id:
            story_session.current_node = next_node_id
        return True, "选择成功", self.get_current_node(story_session, player)
