"""
场景节点引擎 - 管理里界中的场景节点移动和状态

替代旧的坐标网格系统，提供命名场景间的跳转。
每个场景是一个命名节点，有固定的连接关系和事件。
"""
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from ..models.inner_realm import InnerRealmSession


@dataclass
class SceneNode:
    """场景节点定义"""
    id: str
    display_name: str
    description: str
    first_visit_text: str = ""
    connections: List[str] = field(default_factory=list)
    outdoor: bool = False
    searchable: bool = False
    loot_table: Dict[str, Any] = field(default_factory=dict)
    search_attribute: str = "luck"
    events: List[Dict] = field(default_factory=list)
    required_items: List[str] = field(default_factory=list)
    danger_level: str = "safe"
    clue_on_observe: str = ""
    observe_text: str = ""
    auto_trigger: bool = False
    entry_from_event: bool = False
    npcs: List[str] = field(default_factory=list)
    node_type: str = "main"  # main / branch
    rest_sanity: int = 0  # 休息恢复理智量
    max_rest_count: int = 0  # 最大休息次数


class SceneEngine:
    """
    场景引擎 - 管理玩家在场景节点间的移动

    从 YAML 配置加载场景，提供：
    - 场景查找（by ID / by display_name）
    - 可前往目的地列表（考虑入夜、道具需求等）
    - 移动合法性检查
    - 场景进入和描述生成
    """

    def __init__(self, realm_config: Dict[str, Any]):
        """
        初始化场景引擎

        Args:
            realm_config: 里界配置字典（从 inner_realms.yaml 加载）
        """
        self.realm_config = realm_config
        self.scenes: Dict[str, SceneNode] = {}
        self._load_scenes()

    def _load_scenes(self):
        """从配置加载所有场景节点"""
        scenes_config = self.realm_config.get("scenes", {})
        for scene_id, config in scenes_config.items():
            self.scenes[scene_id] = SceneNode(
                id=scene_id,
                display_name=config.get("display_name", scene_id),
                description=config.get("description", ""),
                first_visit_text=config.get("first_visit_text", ""),
                connections=config.get("connections", []),
                outdoor=config.get("outdoor", False),
                searchable=config.get("searchable", False),
                loot_table=config.get("loot_table", {}),
                search_attribute=config.get("search_attribute", "luck"),
                events=config.get("events", []),
                required_items=config.get("required_items", []),
                danger_level=config.get("danger_level", "safe"),
                clue_on_observe=config.get("clue_on_observe", ""),
                observe_text=config.get("observe_text", ""),
                auto_trigger=config.get("auto_trigger", False),
                entry_from_event=config.get("entry_from_event", False),
                npcs=config.get("npcs", []),
                node_type=config.get("type", "main"),
                rest_sanity=config.get("rest_sanity", 0),
                max_rest_count=config.get("max_rest_count", 0),
            )

    def get_scene(self, scene_id: str) -> Optional[SceneNode]:
        """获取场景节点"""
        return self.scenes.get(scene_id)

    def get_current_scene(self, session: InnerRealmSession) -> Optional[SceneNode]:
        """获取玩家当前所在场景"""
        if not session.current_scene:
            return None
        return self.scenes.get(session.current_scene)

    def get_scene_by_display_name(self, display_name: str) -> Optional[SceneNode]:
        """通过显示名查找场景"""
        for scene in self.scenes.values():
            if scene.display_name == display_name:
                return scene
        return None

    def get_max_dusk_moves(self) -> int:
        """获取黄昏阶段最大移动次数"""
        return self.realm_config.get("phases", {}).get(
            "dusk", {}
        ).get("max_moves", 5)

    def is_night(self, session: InnerRealmSession) -> bool:
        """判断是否已入夜"""
        return session.move_count >= self.get_max_dusk_moves()

    def get_session_inventory(self, session: InnerRealmSession) -> Dict[str, int]:
        """获取会话内道具字典"""
        if not session.inventory:
            return {}
        try:
            return json.loads(session.inventory)
        except (json.JSONDecodeError, TypeError):
            return {}

    def get_visited_scenes(self, session: InnerRealmSession) -> List[str]:
        """获取已访问场景列表"""
        if not session.visited_scenes:
            return []
        try:
            return json.loads(session.visited_scenes)
        except (json.JSONDecodeError, TypeError):
            return []

    def get_available_destinations(
        self, session: InnerRealmSession
    ) -> List[SceneNode]:
        """
        获取当前可前往的场景列表

        过滤规则：
        - 排除 auto_trigger 和 entry_from_event 的节点
        - 入夜后排除 outdoor 节点
        - 检查 required_items 道具需求
        """
        current = self.get_current_scene(session)
        if not current:
            return []

        inventory = self.get_session_inventory(session)
        night = self.is_night(session)

        destinations = []
        for conn_id in current.connections:
            scene = self.scenes.get(conn_id)
            if not scene:
                continue

            # 跳过自动触发和事件进入的节点
            if scene.auto_trigger or scene.entry_from_event:
                continue

            # 入夜后不能去户外
            if night and scene.outdoor:
                continue

            # 检查道具需求（缺少道具的也显示，但标记锁定）
            destinations.append(scene)

        return destinations

    def can_enter_scene(
        self, session: InnerRealmSession, target_id: str
    ) -> Tuple[bool, str]:
        """
        检查是否可以进入目标场景

        Returns:
            (可否进入, 失败原因)
        """
        target = self.scenes.get(target_id)
        if not target:
            return False, "⛔ 没有这个地方"

        current = self.get_current_scene(session)
        if not current:
            return False, "⛔ 当前位置异常"

        # 检查连通性
        if target_id not in current.connections:
            return False, f"⛔ 从「{current.display_name}」无法前往「{target.display_name}」"

        # 检查是否为事件专属入口
        if target.auto_trigger or target.entry_from_event:
            return False, f"⛔ 「{target.display_name}」无法直接前往"

        # 检查入夜后的户外限制
        if self.is_night(session) and target.outdoor:
            return False, (
                "天已经完全黑了。你踏出建筑的那一刻，"
                "黑暗中伸出无数只手——\n\n💀 试炼失败"
            )

        # 检查道具需求
        if target.required_items:
            inventory = self.get_session_inventory(session)
            missing = [
                item for item in target.required_items
                if inventory.get(item, 0) <= 0
            ]
            if missing:
                return False, "⛔ 你缺少必要的道具"

        return True, ""

    def enter_scene(
        self,
        session: InnerRealmSession,
        target_id: str,
        is_first_playthrough: bool = False,
    ) -> str:
        """
        进入目标场景，更新会话状态

        Args:
            session: 会话
            target_id: 目标场景ID
            is_first_playthrough: 是否为首次通关模式（控制叙事文本）

        Returns:
            场景描述文本
        """
        scene = self.scenes[target_id]

        # 记录旧已访问列表（用于判断是否首次到达）
        visited = self.get_visited_scenes(session)
        first_time_here = target_id not in visited

        # 更新会话状态
        session.current_scene = target_id
        session.move_count += 1

        if first_time_here:
            visited.append(target_id)
            session.visited_scenes = json.dumps(visited)

        # 构建描述文本
        lines = [
            f"📍 {scene.display_name}",
            "━━━━━━━━━━━━━",
            scene.description,
        ]

        # 首次通关模式 + 首次到达该场景时显示额外叙事
        if is_first_playthrough and first_time_here and scene.first_visit_text:
            lines.append("")
            lines.append(f"💭 {scene.first_visit_text}")

        # 阶段提示
        if not self.is_night(session):
            remaining = self.get_max_dusk_moves() - session.move_count
            if remaining <= 2 and remaining > 0:
                lines.append("")
                lines.append(f"⚠️ 天色渐暗，你还能在户外移动 {remaining} 次")
            elif remaining <= 0:
                lines.append("")
                lines.append("🌙 夜幕降临。天黑后，不要在街上停留。")

        # 显示可用操作提示
        hints = []
        if scene.searchable:
            hints.append("【搜刮】")
        if scene.clue_on_observe or scene.observe_text:
            hints.append("【观察】")
        if scene.npcs:
            hints.append("【交谈/威吓/处决】")
        if scene.rest_sanity > 0:
            hints.append("【休息】")

        if hints:
            lines.append("━━━━━━━━━━━━━")
            lines.append(f"💡 可操作: {' '.join(hints)}")

        # 显示可前往地点
        dests = self.get_available_destinations(session)
        if dests:
            dest_names = [d.display_name for d in dests]
            lines.append(f"🚪 可前往: {' | '.join(dest_names)}")

        return "\n".join(lines)

    def format_destinations_list(
        self, session: InnerRealmSession
    ) -> str:
        """格式化可前往地点列表"""
        dests = self.get_available_destinations(session)
        if not dests:
            return "⛔ 当前没有可前往的地方"

        inventory = self.get_session_inventory(session)

        lines = [
            "🚪 可前往地点",
            "━━━━━━━━━━━━━",
        ]

        for dest in dests:
            # 检查道具需求
            locked = False
            if dest.required_items:
                missing = [
                    item for item in dest.required_items
                    if inventory.get(item, 0) <= 0
                ]
                locked = len(missing) > 0

            danger_icon = {
                "safe": "🟢",
                "low": "🟡",
                "medium": "🟠",
                "high": "🔴",
                "deadly": "💀",
            }.get(dest.danger_level, "⚪")

            if locked:
                lines.append(f"🔒 {dest.display_name} {danger_icon} (需要道具)")
            else:
                lines.append(f"  {dest.display_name} {danger_icon}")

        lines.extend([
            "━━━━━━━━━━━━━",
            "💡 使用【前往 地点名】移动",
        ])

        return "\n".join(lines)
