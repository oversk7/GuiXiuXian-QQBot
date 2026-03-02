"""
剧情引擎 - 处理剧情逻辑的核心模块
"""
import json
import os
import random
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.story_session import StorySession
from ..models.player import Player

from ..config import config


class StoryEngine:
    """剧情状态机处理器"""

    def __init__(self):
        self._story_index: Dict[str, Path] = {}          # story_id -> 文件路径
        self._story_meta: Dict[str, Dict[str, str]] = {} # story_id -> {title, description}
        self.story_dir = Path(__file__).parent.parent / "data" / "stories"
        self._build_index()

    def _build_index(self):
        """扫描剧情目录，只读取元数据建立索引，不加载完整内容"""
        print(f"[StoryEngine] 剧情目录: {self.story_dir}")
        if not self.story_dir.exists():
            print(f"[StoryEngine] [ERROR] 剧情目录不存在，创建目录: {self.story_dir}")
            self.story_dir.mkdir(parents=True, exist_ok=True)
            return

        json_files = list(self.story_dir.glob("*.json"))
        print(f"[StoryEngine] 找到 {len(json_files)} 个剧情文件，建立索引中...")

        for file_path in json_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    story_data = json.load(f)
                story_id = story_data.get('id')
                if story_id:
                    self._story_index[story_id] = file_path
                    self._story_meta[story_id] = {
                        "title": story_data.get("title", "未命名剧情"),
                        "description": story_data.get("description", "暂无描述"),
                    }
                    print(f"[StoryEngine] 已索引: {story_id}")
                else:
                    print(f"[StoryEngine] [WARNING] 剧情文件缺少ID: {file_path}")
            except Exception as e:
                print(f"[StoryEngine] [ERROR] 索引剧情文件失败 {file_path}: {e}")

        print(f"[StoryEngine] 索引完成，共 {len(self._story_index)} 个剧情: {list(self._story_index.keys())}")

    def get_story_list(self) -> List[Dict[str, str]]:
        """获取可用剧情列表（只用元数据，无需加载完整内容）"""
        stories = [{"id": story_id, **meta} for story_id, meta in self._story_meta.items()]
        stories.sort(key=lambda s: (0 if s["id"] == "ghost_town" else 1))
        return stories

    def get_story(self, story_id: str) -> Optional[Dict[str, Any]]:
        """获取指定剧情（每次从磁盘读取，访问频率低无需缓存）"""
        file_path = self._story_index.get(story_id)
        if not file_path:
            return None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[StoryEngine] [ERROR] 加载剧情失败 {file_path}: {e}")
            return None
    
    def evaluate_condition(self, condition: Dict[str, Any], player: Player, variables: Dict[str, Any]) -> bool:
        """
        评估条件是否满足

        支持格式:
        1. 简单条件(默认 and): {"player_level": {">=": 10}, "story_key": {"==": true}}
        2. and 逻辑: {"and": [cond1, cond2, ...]}
        3. or 逻辑: {"or": [cond1, cond2, ...]}
        4. 嵌套组合: {"or": [{"and": [cond1, cond2]}, cond3]}
        """
        # 检查是否包含逻辑运算符
        if "and" in condition:
            # and 逻辑 - 所有条件都必须满足
            conditions_list = condition["and"]
            if not isinstance(conditions_list, list):
                return False
            return all(self.evaluate_condition(cond, player, variables) for cond in conditions_list)

        elif "or" in condition:
            # or 逻辑 - 至少一个条件满足
            conditions_list = condition["or"]
            if not isinstance(conditions_list, list):
                return False
            return any(self.evaluate_condition(cond, player, variables) for cond in conditions_list)

        else:
            # 简单条件检查(默认 and)
            for key, check in condition.items():
                if key.startswith("player_"):
                    # 玩家属性检查
                    attr_name = key[7:]  # 去掉 "player_" 前缀

                    # 特殊处理 completed_trials
                    if attr_name == "completed_trials":
                        import json
                        completed_trials = player.get_completed_trials()
                        # 检查是否包含指定的试炼ID
                        if "contains" in check:
                            required_id = check["contains"]
                            player_value = required_id in completed_trials
                        else:
                            player_value = completed_trials
                    else:
                        player_value = getattr(player, attr_name, 0)

                    if not self._check_value(player_value, check):
                        return False
                elif key.startswith("story_"):
                    # 剧情变量检查
                    var_name = key[6:]  # 去掉 "story_" 前缀
                    var_value = variables.get(var_name)
                    if not self._check_value(var_value, check):
                        return False
                else:
                    # 直接变量检查
                    var_value = variables.get(key)
                    if not self._check_value(var_value, check):
                        return False
            return True
    
    def _check_value(self, value: Any, check: Dict[str, Any]) -> bool:
        """检查单个值是否满足条件"""
        for operator, expected in check.items():
            if operator == "==":
                return value == expected
            elif operator == "!=":
                return value != expected
            elif operator == ">":
                return value > expected
            elif operator == ">=":
                return value >= expected
            elif operator == "<":
                return value < expected
            elif operator == "<=":
                return value <= expected
            elif operator == "in":
                return value in expected
            elif operator == "not_in":
                return value not in expected
        return True

    def resolve_next(self, next_field: Any, player: Player, variables: Dict[str, Any]) -> Optional[str]:
        """
        解析 next 字段,支持条件跳转

        支持格式:
        1. 简单字符串: "node_2"
        2. 条件跳转数组: [
             {"if": condition, "goto": "node_a"},
             {"if": condition, "goto": "node_b"},
             {"goto": "default_node"}  // 默认分支(无 if)
           ]

        返回:
            目标节点ID,如果没有匹配的条件则返回 None
        """
        # 简单字符串格式(向后兼容)
        if isinstance(next_field, str):
            return next_field

        # 条件跳转数组格式
        if isinstance(next_field, list):
            for branch in next_field:
                if not isinstance(branch, dict):
                    continue

                # 检查是否有条件
                if "if" in branch:
                    condition = branch["if"]
                    # 评估条件
                    if self.evaluate_condition(condition, player, variables):
                        return branch.get("goto")
                else:
                    # 无条件分支(默认分支)
                    return branch.get("goto")

        # 无效格式或没有匹配的条件
        return None
    
    def apply_effects(self, effects: Dict[str, Any], player: Player, variables: Dict[str, Any]) -> Tuple[Player, Dict[str, Any]]:
        """应用效果到玩家和变量"""
        # 应用玩家属性变化
        if "player" in effects:
            for attr, change in effects["player"].items():
                current_value = getattr(player, attr, 0)
                if isinstance(change, str) and change.startswith(("+", "-")):
                    # 相对变化
                    delta = int(change)
                    setattr(player, attr, current_value + delta)
                else:
                    # 绝对值
                    setattr(player, attr, change)
        
        # 应用变量变化
        if "variables" in effects:
            for var_name, change in effects["variables"].items():
                if isinstance(change, str) and change.startswith(("+", "-")):
                    # 相对变化
                    current_value = variables.get(var_name, 0)
                    delta = int(change)
                    variables[var_name] = current_value + delta
                else:
                    # 绝对值
                    variables[var_name] = change
        
        return player, variables

    async def apply_special_effects(self, effects: Dict[str, Any], player: Player, variables: Dict[str, Any], session: AsyncSession) -> Tuple[Player, Dict[str, Any], str]:
        """应用特殊效果，如首次试炼奖励"""
        reward_message = ""

        # 处理试炼通关记录
        if "trial_success" in effects and effects["trial_success"]:
            story_id = variables.get("current_story_id", "")
            if story_id:
                # 检查是否完美结局
                is_perfect = variables.get("perfect_ending", False)
                trial_id = f"{story_id}_完美" if is_perfect else story_id
                player.add_completed_trial(trial_id)

        # 处理首次试炼奖励
        if "first_trial_reward" in effects and effects["first_trial_reward"]:
            reward_msg = await self._handle_first_trial_reward(session, player)
            if reward_msg:
                reward_message = f"\n\n{reward_msg}"

        return player, variables, reward_message

    async def _handle_first_trial_reward(self, session: AsyncSession, player: Player) -> str:
        """处理首次试炼奖励 - 已移除鬼怪系统"""
        # 鬼怪系统已下架，不再给予鬼怪奖励
        return ""

    def format_content(self, content: str, player: Player, variables: Dict[str, Any]) -> str:
        """格式化内容，替换变量"""
        # 替换玩家基本信息
        content = content.replace("{player_name}", player.nickname)
        content = content.replace("{player_uid}", str(player.uid))
        content = content.replace("{player_level}", str(player.level))
        content = content.replace("{player_sex}", player.sex)
        content = content.replace("{player_region}", player.region)

        # 替换玩家属性
        content = content.replace("{player_exp}", str(player.exp))
        content = content.replace("{player_hp}", str(player.hp))
        content = content.replace("{player_max_hp}", str(player.max_hp))
        content = content.replace("{player_mp}", str(player.mp))
        content = content.replace("{player_max_mp}", str(player.max_mp))
        content = content.replace("{player_attack}", str(player.attack))
        content = content.replace("{player_defense}", str(player.defense))
        content = content.replace("{player_agility}", str(player.agility))
        content = content.replace("{player_stamina}", str(player.stamina))
        content = content.replace("{player_luck}", str(player.luck))
        content = content.replace("{player_resentment}", str(player.resentment))

        # 替换玩家财富
        content = content.replace("{player_gold}", str(player.gold))
        content = content.replace("{player_gold2}", str(player.gold2))
        content = content.replace("{player_vip}", str(player.vip))

        # 替换玩家位置（使用当前活跃坐标）
        current_x, current_y = player.get_current_coordinates()
        content = content.replace("{player_x}", str(current_x))
        content = content.replace("{player_y}", str(current_y))

        # 替换公会信息
        content = content.replace("{player_guild_id}", str(player.guild_id or "无"))
        content = content.replace("{player_guild_contribution}", str(player.guild_contribution))

        # 替换其他信息
        content = content.replace("{player_attribute_points}", str(player.attribute_points))
        content = content.replace("{player_sign_streak}", str(player.sign_streak))

        # 替换剧情变量
        for var_name, var_value in variables.items():
            content = content.replace(f"{{{var_name}}}", str(var_value))

        return content
    
    def get_current_node(self, story_session: StorySession, player: Player) -> Optional[Dict[str, Any]]:
        """获取当前节点信息"""
        story = self.get_story(story_session.story_id)
        if not story:
            return None
        
        nodes = story.get("nodes", {})
        current_node = nodes.get(story_session.current_node)
        if not current_node:
            return None
        
        variables = story_session.get_variables()
        
        # 格式化内容
        if "content" in current_node:
            current_node = current_node.copy()
            current_node["content"] = self.format_content(current_node["content"], player, variables)
        
        # 过滤选项（检查条件）
        if current_node.get("type") == "choice" and "options" in current_node:
            filtered_options = []
            for option in current_node["options"]:
                if "conditions" in option:
                    if self.evaluate_condition(option["conditions"], player, variables):
                        filtered_options.append(option)
                else:
                    filtered_options.append(option)
            current_node = current_node.copy()
            current_node["options"] = filtered_options
        
        return current_node
    
    def process_choice(self, story_session: StorySession, player: Player, choice_id: int) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """处理玩家选择"""
        story = self.get_story(story_session.story_id)
        if not story:
            return False, "剧情不存在", None

        current_node = story["nodes"].get(story_session.current_node)
        if not current_node or current_node.get("type") != "choice":
            return False, "当前不是选择节点", None

        # 查找选择的选项
        selected_option = None
        for option in current_node.get("options", []):
            if option.get("id") == choice_id:
                selected_option = option
                break

        if not selected_option:
            return False, "无效的选择", None

        variables = story_session.get_variables()

        # 检查选项条件
        if "conditions" in selected_option:
            if not self.evaluate_condition(selected_option["conditions"], player, variables):
                return False, "不满足选择条件", None

        # 应用选项效果
        if "effects" in selected_option:
            player, variables = self.apply_effects(selected_option["effects"], player, variables)
            story_session.set_variables(variables)

        # 使用条件跳转解析下一个节点
        next_node_id = self.resolve_next(selected_option.get("next"), player, variables)
        if next_node_id:
            story_session.current_node = next_node_id

        return True, "选择成功", self.get_current_node(story_session, player)
