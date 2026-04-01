# 荔湾鬼镇 · 里界系统重构 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将里界系统从网格探索重构为场景节点制，以荔湾鬼镇试炼故事为首个里界内容

**Architecture:** 删除第三病栋内容和网格系统，新建场景引擎（`scene_engine.py`），重写 `service.py` 和 `commands.py`。场景配置全部在 `inner_realms.yaml` 中定义。数据模型新增字段通过 `auto_migrate.py` 自动迁移。

**Tech Stack:** NoneBot2 + SQLAlchemy 2.0 (async) + YAML配置 + 2D6骰子判定

**Spec:** `docs/superpowers/specs/2026-03-24-liwan-ghost-town-inner-realm-design.md`

---

## 文件结构总览

| 文件 | 操作 | 职责 |
|------|------|------|
| `plugins/xiuxian_game/models/auto_migrate.py` | 修改 | 新增 DB 字段 |
| `plugins/xiuxian_game/models/inner_realm.py` | 修改 | 新增 ORM 字段映射 |
| `plugins/xiuxian_game/data/items.yaml` | 修改 | 删除旧物品、新增6种专属材料 |
| `plugins/xiuxian_game/data/inner_realms.yaml` | 重写 | 删除第三病栋、新增荔湾鬼镇完整配置 |
| `plugins/xiuxian_game/inner_realm/scene_engine.py` | 新建 | 场景节点引擎核心 |
| `plugins/xiuxian_game/inner_realm/service.py` | 重写 | 基于场景的判定逻辑 |
| `plugins/xiuxian_game/inner_realm/commands.py` | 重写 | 场景节点命令处理 |
| `plugins/xiuxian_game/inner_realm/config.py` | 修改 | 适配新配置结构 |
| `plugins/xiuxian_game/player/help.py` | 修改 | 更新帮助信息 |
| `plugins/xiuxian_game/data/knowledge/inner_realm_help.yaml` | 修改 | 同步AI知识库 |

---

### Task 1: 数据库迁移 — 新增字段

**Files:**
- Modify: `plugins/xiuxian_game/models/auto_migrate.py:74-79`
- Modify: `plugins/xiuxian_game/models/inner_realm.py`

- [ ] **Step 1: 在 `auto_migrate.py` 的 `REQUIRED_FIELDS` 中添加新字段**

在 `inner_realm_session` 条目中添加：

```python
"inner_realm_session": {
    "sanity": "INT DEFAULT 100 COMMENT '当前理智值(0-100)'",
    "clue_collected": "TEXT COMMENT '已收集的线索ID列表(JSON数组)'",
    "state": "TEXT COMMENT '探索状态(JSON对象,存储自定义数据)'",
    # 场景节点系统新增字段
    "current_scene": "VARCHAR(50) NULL COMMENT '当前场景节点ID'",
    "visited_scenes": "TEXT DEFAULT '[]' COMMENT '已访问场景列表(JSON)'",
    "inventory": "TEXT DEFAULT '{}' COMMENT '里界内道具(JSON)'",
    "is_first_clear": "INT DEFAULT 0 COMMENT '是否首次通关(0/1)'",
    "move_count": "INT DEFAULT 0 COMMENT '移动次数(控制黄昏→入夜)'",
},
```

在 `player` 条目中添加：

```python
"inner_realm_clears": "TEXT NULL COMMENT '里界通关记录(JSON)'",
```

- [ ] **Step 2: 在 `inner_realm.py` 的 `InnerRealmSession` 类中添加 ORM 映射**

在 `is_settled` 字段后面添加：

```python
# 场景节点系统字段
current_scene: Mapped[str] = mapped_column(
    String(50), nullable=True, comment="当前场景节点ID"
)
visited_scenes: Mapped[str] = mapped_column(
    Text, default='[]', comment="已访问场景列表(JSON)"
)
inventory: Mapped[str] = mapped_column(
    Text, default='{}', comment="里界内道具(JSON)"
)
is_first_clear: Mapped[bool] = mapped_column(
    Integer, default=0, server_default='0', comment="是否首次通关(0/1)"
)
move_count: Mapped[int] = mapped_column(
    Integer, default=0, server_default='0', comment="移动次数"
)
```

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/models/auto_migrate.py plugins/xiuxian_game/models/inner_realm.py
git commit -m "feat(inner_realm): 新增场景节点系统数据库字段"
```

---

### Task 2: 清理第三病栋 — 删除旧物品和配置

**Files:**
- Modify: `plugins/xiuxian_game/data/items.yaml` (删除3个物品定义)
- Modify: `plugins/xiuxian_game/data/inner_realms.yaml` (删除 `third_ward` 配置块)

- [ ] **Step 1: 从 `items.yaml` 删除第三病栋专属物品**

搜索并删除以下3个物品条目（每个条目包含 item_id 到下一个 `- item_id` 之间的所有行）：
- `stained_infusion_bag`（发黄的输液袋）
- `discolored_meal_tray`（变色的病号餐）
- `cracked_specimen_jar`（碎裂的标本瓶）

**注意：保留 `cursed_mirror_shard`（诅咒镜片），它被多个装备配方引用。**

- [ ] **Step 2: 从 `inner_realms.yaml` 删除 `third_ward` 配置**

删除 `realms:` 下的 `third_ward:` 整块配置（约从第168行到第500行，包括所有NPC、线索、BOSS、结局、特殊事件配置）。

保留文件开头的全局设置（`global:`、`time_system:`、`cognition_tamper_system:`）和文件末尾的 `attribute_modifiers:`、`dice_results:` 配置。

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/data/items.yaml plugins/xiuxian_game/data/inner_realms.yaml
git commit -m "cleanup: 删除第三病栋配置和专属物品"
```

---

### Task 3: 新增荔湾鬼镇专属材料

**Files:**
- Modify: `plugins/xiuxian_game/data/items.yaml` (在 `materials:` 区块末尾添加)

- [ ] **Step 1: 在 `items.yaml` 的 `materials:` 区块末尾添加6种新材料**

```yaml
    # ========== 里界专属材料（荔湾鬼镇）==========
    - item_id: "bloodstained_room_card"
      name: "血迹房卡"
      description: "旅馆的房卡，背面有指甲刮出的痕迹。每一张都属于一个再也没有退房的客人"
      type: "MATERIAL"
      rarity: "white"
      price: 100
      grudge_value: 10
      tags: ["inner_realm_exclusive"]

    - item_id: "faceless_skin"
      name: "无脸人皮"
      description: "一张完整的人脸皮肤，五官处光滑如蛋壳。不知道它原来的主人是谁——也许它就是主人"
      type: "MATERIAL"
      rarity: "green"
      price: 200
      grudge_value: 20
      tags: ["inner_realm_exclusive"]

    - item_id: "human_tooth_collection"
      name: "拔下的牙齿"
      description: "用红绳串在一起的十几颗人类牙齿，根部带着干涸血肉，说明是活着时被拔下的"
      type: "MATERIAL"
      rarity: "blue"
      price: 450
      grudge_value: 35
      tags: ["inner_realm_exclusive"]

    - item_id: "headless_ghost_nail"
      name: "提头女鬼的指甲"
      description: "漆黑如墨的指甲，边缘锋利如刀片。断面还嵌着一小片人类衣物的纤维"
      type: "MATERIAL"
      rarity: "blue"
      price: 450
      grudge_value: 40
      tags: ["inner_realm_exclusive"]

    - item_id: "freezer_woman_flesh"
      name: "冰箱怪物的腐肉"
      description: "蠕动的灰白色肉块，低温也无法阻止它的生长。切开后内部纹理像人类胃壁组织"
      type: "MATERIAL"
      rarity: "purple"
      price: 1600
      grudge_value: 80
      tags: ["inner_realm_exclusive"]

    - item_id: "liwan_time_fragment"
      name: "荔湾时间碎片"
      description: "凝固时空裂隙坍缩时剥落的碎片，里面封存着三十年前的某一秒"
      type: "MATERIAL"
      rarity: "orange"
      price: 5000
      grudge_value: 200
      tags: ["inner_realm_exclusive"]
```

- [ ] **Step 2: 验证 YAML 语法**

```bash
cd D:/QQbot/GuiXiuXian2 && python -c "import yaml; yaml.safe_load(open('plugins/xiuxian_game/data/items.yaml', encoding='utf-8')); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/data/items.yaml
git commit -m "feat(inner_realm): 新增荔湾鬼镇6种专属材料"
```

---

### Task 4: 编写荔湾鬼镇完整 YAML 配置

**Files:**
- Modify: `plugins/xiuxian_game/data/inner_realms.yaml` (在 `realms:` 下新增 `liwan_ghost_town`)

这是最大的内容任务。需要在 `inner_realms.yaml` 的 `realms:` 下添加完整的荔湾鬼镇配置，包含：

- [ ] **Step 1: 添加基础信息和阶段配置**

在 `realms:` 下添加：

```yaml
  liwan_ghost_town:
    display_name: "荔湾鬼镇"
    description: "诡域深处的凝固时空，三十年前荔湾镇被吞噬的瞬间被永久定格"
    level_requirement: 50
    narrative_type: "survival"
    suppress_cultivation: true

    phases:
      dusk:
        max_moves: 5
        outdoor_allowed: true
      night:
        outdoor_allowed: false
```

- [ ] **Step 2: 添加全部20个场景节点配置**

每个场景节点的格式：

```yaml
    scenes:
      town_entrance_dusk:
        display_name: "镇口·黄昏"
        type: "main"
        outdoor: true
        description: "天色将暗，你踏入了这片凝固的时空。荔湾镇的轮廓在暮色中显现——歪斜的路灯、褪色的招牌、空无一人的街道。一块残破的告示牌上写着：「天黑后，请勿在室外逗留。」"
        first_visit_text: "修为被一股无形的力量压制，你感到自己变得和凡人一样脆弱。这片凝固时空中的一切都是三十年前的残影——但危险是真实的。"
        connections: ["apartment_ground", "crossroads", "clinic", "convenience_store"]
        searchable: true
        loot_table:
          critical_success: {items: [{id: "bloodstained_room_card", qty: 2}], gold: 300}
          success: {items: [{id: "bloodstained_room_card", qty: 1}], gold: 150}
          normal: {gold: 100}
          failure: {}
        events: []
        clue_on_observe: "clue_8"  # 告示牌背面
        danger_level: "safe"
```

对spec中的20个节点（12主线+8分支）逐一编写完整配置。参照spec第2节的节点表和第5节的掉落表。关键节点配置要点：

- `hallway`：需要 `required_items: ["needle_thread"]` 来触发引诱厂服男事件
- `hotel_lobby`：需要 `required_items: ["room_card_4"]` 来进入四号房
- `lobby_midnight`：设置 `auto_trigger: true`，不可自由前往，由room_4事件触发
- `room_1`：设置 `entry_from_event: true`，只能从宵夜事件进入
- `kitchen_secret`：需要从room_1进入
- 所有户外节点设置 `outdoor: true`
- 所有分支节点设置 `type: "branch"`

- [ ] **Step 3: 添加NPC配置**

```yaml
    npcs:
      - id: "raincoat_man"
        name: "雨衣男"
        type: "human_hostile"
        location: "hallway"
        can_talk: false
        can_intimidate: false
        can_execute: true
        execute_difficulty: 11  # 2D6+敏捷(11+)
        execute_attribute: "agility"
        hp: 200
        attack: 80
        defense: 30
        description: "穿着黑色雨衣的男人，看不清脸。左手小指缺了一节，雨衣下摆沾着暗红色的东西"
        death_loot: [{id: "room_card_4", qty: 1, probability: 1.0}]
        dialogue: []
        # ... 更多NPC
```

对spec第3节的7个凡人NPC和7个鬼怪逐一配置。

- [ ] **Step 4: 添加线索配置**

```yaml
    clues:
      - id: "clue_1"
        name: "雨衣男的身份"
        obtain_method: "observe"
        obtain_scene: "home"
        description: "继父左手小指缺了一节——和电梯里那个雨衣男一模一样。继父身上有两处刀伤，但现场只有一把刀"
        reveal: "雨衣男和继父之间有某种关联。也许他们是同一个人？"
      # ... 8条线索全部配置
```

- [ ] **Step 5: 添加结局配置**

```yaml
    endings:
      dawn_survivor:
        display_name: "黎明幸存者"
        icon: "☀️"
        condition: "reached_dawn"
        description: "你利用冰箱怪物与提头女鬼的厮杀，趁乱逃出旅馆。天色蒙蒙亮，你回头看了一眼——荔湾镇的轮廓在晨光中消散，像是从未存在过。凝固时空裂隙关闭。你的衣角沾着不属于这个时代的灰尘"
        reward_multiplier: 1.5
        bonus_items: [{id: "bloodstained_room_card", qty: 5}]
        first_clear_bonus: {gold: 2000, items: [{id: "bloodstained_room_card", qty: 10}, {id: "faceless_skin", qty: 10}]}
      # ... 5个结局全部配置
```

- [ ] **Step 6: 验证 YAML 并提交**

```bash
cd D:/QQbot/GuiXiuXian2 && python -c "import yaml; yaml.safe_load(open('plugins/xiuxian_game/data/inner_realms.yaml', encoding='utf-8')); print('OK')"
git add plugins/xiuxian_game/data/inner_realms.yaml
git commit -m "feat(inner_realm): 添加荔湾鬼镇完整YAML配置（20个场景节点）"
```

---

### Task 5: 新建场景引擎 `scene_engine.py`

**Files:**
- Create: `plugins/xiuxian_game/inner_realm/scene_engine.py`

这是核心新模块，负责场景节点的加载、移动、状态管理。

- [ ] **Step 1: 编写 `SceneNode` 数据类和 `SceneEngine` 类**

```python
"""
场景节点引擎 - 管理里界中的场景节点移动和状态

替代旧的坐标网格系统，提供命名场景间的跳转。
"""
import json
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from ..models.inner_realm import InnerRealmSession
from .config import InnerRealmConfig


@dataclass
class SceneNode:
    """场景节点"""
    id: str
    display_name: str
    description: str
    first_visit_text: str = ""
    connections: List[str] = field(default_factory=list)
    outdoor: bool = False
    searchable: bool = False
    loot_table: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict] = field(default_factory=list)
    required_items: List[str] = field(default_factory=list)
    danger_level: str = "safe"
    clue_on_observe: str = ""
    auto_trigger: bool = False
    entry_from_event: bool = False
    npcs: List[str] = field(default_factory=list)  # NPC ID 列表
    type: str = "main"  # main / branch


class SceneEngine:
    """场景引擎 - 管理玩家在场景节点间的移动"""

    def __init__(self, realm_config: Dict[str, Any]):
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
                events=config.get("events", []),
                required_items=config.get("required_items", []),
                danger_level=config.get("danger_level", "safe"),
                clue_on_observe=config.get("clue_on_observe", ""),
                auto_trigger=config.get("auto_trigger", False),
                entry_from_event=config.get("entry_from_event", False),
                npcs=config.get("npcs", []),
                type=config.get("type", "main"),
            )

    def get_scene(self, scene_id: str) -> Optional[SceneNode]:
        """获取场景节点"""
        return self.scenes.get(scene_id)

    def get_current_scene(self, session: InnerRealmSession) -> Optional[SceneNode]:
        """获取玩家当前所在场景"""
        if not session.current_scene:
            return None
        return self.scenes.get(session.current_scene)

    def get_available_destinations(
        self, session: InnerRealmSession
    ) -> List[SceneNode]:
        """
        获取当前可前往的场景列表

        Rules:
        - 过滤掉 auto_trigger 和 entry_from_event 的节点
        - 入夜后过滤掉 outdoor 节点
        - 检查 required_items
        """
        current = self.get_current_scene(session)
        if not current:
            return []

        state = json.loads(session.state) if session.state else {}
        inventory = json.loads(session.inventory) if session.inventory else {}
        is_night = session.move_count >= self.realm_config.get("phases", {}).get("dusk", {}).get("max_moves", 5)

        destinations = []
        for conn_id in current.connections:
            scene = self.scenes.get(conn_id)
            if not scene:
                continue

            # 跳过自动触发和事件进入的节点
            if scene.auto_trigger or scene.entry_from_event:
                continue

            # 入夜后不能去户外
            if is_night and scene.outdoor:
                continue

            # 检查道具需求
            if scene.required_items:
                has_all = all(
                    inventory.get(item, 0) > 0 for item in scene.required_items
                )
                if not has_all:
                    continue

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
        max_dusk_moves = self.realm_config.get("phases", {}).get("dusk", {}).get("max_moves", 5)
        is_night = session.move_count >= max_dusk_moves
        if is_night and target.outdoor:
            return False, "天已经完全黑了。你踏出建筑的那一刻，黑暗中伸出无数只手——\n\n💀 试炼失败"

        # 检查道具需求
        if target.required_items:
            inventory = json.loads(session.inventory) if session.inventory else {}
            missing = [
                item for item in target.required_items
                if inventory.get(item, 0) <= 0
            ]
            if missing:
                return False, "⛔ 你缺少必要的道具"

        return True, ""

    def enter_scene(
        self, session: InnerRealmSession, target_id: str, is_first_ever: bool = False
    ) -> str:
        """
        进入目标场景，更新会话状态

        Args:
            session: 会话
            target_id: 目标场景ID
            is_first_ever: 是否为该玩家首次通关（控制叙事文本）

        Returns:
            场景描述文本
        """
        scene = self.scenes[target_id]
        session.current_scene = target_id
        session.move_count += 1

        # 更新已访问列表
        visited = json.loads(session.visited_scenes) if session.visited_scenes else []
        if target_id not in visited:
            visited.append(target_id)
            session.visited_scenes = json.dumps(visited)

        # 构建描述
        lines = [
            f"📍 {scene.display_name}",
            "━━━━━━━━━━━━━",
            scene.description,
        ]

        # 首次通关模式下显示额外叙事
        if is_first_ever and scene.first_visit_text and target_id not in visited[:-1]:
            lines.append("")
            lines.append(f"💭 {scene.first_visit_text}")

        # 显示可用操作提示
        hints = []
        if scene.searchable:
            hints.append("【搜刮】")
        if scene.clue_on_observe:
            hints.append("【观察】")
        if scene.npcs:
            hints.append("【交谈/威吓/处决】")

        if hints:
            lines.append("━━━━━━━━━━━━━")
            lines.append(f"💡 可操作: {' '.join(hints)}")

        return "\n".join(lines)

    def get_scene_by_display_name(self, display_name: str) -> Optional[SceneNode]:
        """通过显示名查找场景"""
        for scene in self.scenes.values():
            if scene.display_name == display_name:
                return scene
        return None
```

- [ ] **Step 2: 提交**

```bash
git add plugins/xiuxian_game/inner_realm/scene_engine.py
git commit -m "feat(inner_realm): 新建场景节点引擎 scene_engine.py"
```

---

### Task 6: 重写 `config.py` — 适配新配置结构

**Files:**
- Modify: `plugins/xiuxian_game/inner_realm/config.py`

- [ ] **Step 1: 添加新方法支持场景配置加载**

在 `InnerRealmConfig` 类中新增方法：

```python
@classmethod
def get_scenes_config(cls, realm_name: str) -> Dict[str, Any]:
    """获取指定里界的场景节点配置"""
    realm = cls.get_realm_config(realm_name)
    if not realm:
        return {}
    return realm.get("scenes", {})

@classmethod
def get_npcs_config(cls, realm_name: str) -> List[Dict[str, Any]]:
    """获取指定里界的NPC配置"""
    realm = cls.get_realm_config(realm_name)
    if not realm:
        return []
    return realm.get("npcs", [])

@classmethod
def get_clues_config(cls, realm_name: str) -> List[Dict[str, Any]]:
    """获取指定里界的线索配置"""
    realm = cls.get_realm_config(realm_name)
    if not realm:
        return []
    return realm.get("clues", [])

@classmethod
def get_endings_config(cls, realm_name: str) -> Dict[str, Any]:
    """获取指定里界的结局配置"""
    realm = cls.get_realm_config(realm_name)
    if not realm:
        return {}
    return realm.get("endings", {})

@classmethod
def get_phases_config(cls, realm_name: str) -> Dict[str, Any]:
    """获取指定里界的阶段配置"""
    realm = cls.get_realm_config(realm_name)
    if not realm:
        return {}
    return realm.get("phases", {})
```

- [ ] **Step 2: 提交**

```bash
git add plugins/xiuxian_game/inner_realm/config.py
git commit -m "feat(inner_realm): config.py 添加场景/NPC/线索/结局配置加载方法"
```

---

### Task 7: 重写 `service.py` — 基于场景的核心逻辑

**Files:**
- Rewrite: `plugins/xiuxian_game/inner_realm/service.py`

这是最大的代码任务。保留骰子判定系统（`roll_2d6`、`DiceRollResult`、`format_dice_roll_message`），删除网格相关逻辑，新增场景相关方法。

- [ ] **Step 1: 重写 service.py 框架**

保留的方法（可能需要微调）：
- `DiceRollResult` 类
- `roll_2d6()` — 保留，修改属性修正计算（使用凡人公式）
- `format_dice_roll_message()` — 保留
- `get_time_bonus()` — 保留
- `check_action_cooldown()` / `update_action_cooldown()` — 保留
- `modify_sanity()` / `trigger_sanity_loss()` / `trigger_sanity_recovery()` — 保留

删除的方法：
- `EMPTY_ENCOUNTERS` 文本池
- `move_in_realm()` — 坐标移动
- `_render_minimap()` — 迷你地图
- `get_current_tile()` — 地块获取
- `generate_move_feedback()` — 坐标移动反馈
- `check_and_refresh_session()` — 每日刷新（不再需要）
- 所有依赖 `InnerRealmTile` 的方法

新增的方法：

```python
def calculate_mortal_modifier(self, player: Player) -> int:
    """凡人状态属性修正（spec 7.8）"""
    return min(3, player.level // 100)

async def enter_realm(self, player: Player, realm_key: str) -> Tuple[bool, str, Optional[InnerRealmSession]]:
    """进入里界 — 创建新会话，初始化场景引擎"""

async def move_to_scene(self, player: Player, session: InnerRealmSession, target_display_name: str) -> Tuple[bool, str]:
    """前往指定场景"""

async def observe_scene(self, player: Player, session: InnerRealmSession) -> str:
    """观察当前场景 — 发现隐藏细节和线索"""

async def perform_search(self, player: Player, session: InnerRealmSession) -> Tuple[bool, str]:
    """搜刮当前场景"""

async def perform_intimidation(self, player: Player, session: InnerRealmSession, npc_name: str = None) -> Tuple[bool, str]:
    """威吓NPC"""

async def perform_assassination(self, player: Player, session: InnerRealmSession, npc_name: str = None) -> Tuple[bool, str]:
    """处决NPC"""

async def talk_to_npc(self, player: Player, session: InnerRealmSession, npc_name: str = None) -> Tuple[bool, str]:
    """与NPC交谈 — 对话树，多次交谈解锁不同信息"""

async def use_item(self, player: Player, session: InnerRealmSession, item_name: str) -> Tuple[bool, str]:
    """使用里界内道具"""

async def get_inventory_display(self, session: InnerRealmSession) -> str:
    """显示里界内道具列表"""

async def settle_ending(self, player: Player, session: InnerRealmSession) -> Dict[str, Any]:
    """结算结局 — 根据条件判定结局类型，发放奖励"""

async def check_sanity_zero(self, session: InnerRealmSession) -> bool:
    """检查理智是否归零（下次操作时触发）"""

async def add_pending_reward(self, session: InnerRealmSession, item_id: str = None, qty: int = 0, gold: int = 0):
    """记录待发放奖励到 session.state["pending_rewards"]"""

async def deliver_rewards(self, player: Player, session: InnerRealmSession, multiplier: float):
    """存活结算时将 pending_rewards 发放到玩家背包"""

async def save_clue_globally(self, player: Player, realm_name: str, clue_id: str):
    """将线索保存到玩家全局记录"""
```

- [ ] **Step 2: 实现各方法的完整逻辑**

每个方法的实现要参照spec对应章节。关键逻辑：

1. `enter_realm`：检查等级、创建会话、设置 `current_scene = "town_entrance_dusk"`
2. `move_to_scene`：调用 `SceneEngine.can_enter_scene` 检查，调用 `enter_scene` 移动
3. `perform_search`：基于场景 `loot_table` 而非 tile，使用凡人修正公式
4. `settle_ending`：按spec第4节的5个结局条件判定，发放奖励使用 `deliver_rewards`
5. `save_clue_globally`：读取/写入 `player.inner_realm_clears` JSON

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/inner_realm/service.py
git commit -m "feat(inner_realm): 重写service.py为场景节点系统"
```

---

### Task 8: 重写 `commands.py` — 场景节点命令

**Files:**
- Rewrite: `plugins/xiuxian_game/inner_realm/commands.py`

- [ ] **Step 1: 删除旧命令，注册新命令**

删除：`up_cmd`, `down_cmd`, `left_cmd`, `right_cmd`, `move_cmd`

修改：
- `enter_realm_cmd` — 传送到里界（保留，微调入口叙事）
- `realm_info_cmd` — 里界信息（保留，改为显示场景名而非坐标）
- `exit_realm_cmd` — 返回/结算（保留）
- `search_cmd` — 搜刮（保留，改调用新service方法）
- `intimidate_cmd` — 威吓（保留）
- `assassination_cmd` — 处决（保留）
- `talk_cmd` — 交谈（保留）
- `observe_cmd` — 观察（保留，改功能为场景细节检查）
- `view_clues_cmd` — 查看线索（保留，改为读全局记录）
- `choose_cmd` — 选择（保留）

新增：
- `goto_cmd = on_command("前往", rule=in_inner_realm_rule, block=True, priority=4)` — 场景间移动
- `use_item_cmd = on_command("使用", rule=in_inner_realm_rule, block=True, priority=4)` — 使用道具
- `inventory_cmd = on_command("道具", rule=in_inner_realm_rule, block=True, priority=4)` — 查看道具

- [ ] **Step 2: 实现【前往】命令处理器**

```python
@goto_cmd.handle()
async def handle_goto(event: MessageEvent, args: Message = CommandArg()):
    """前往指定场景"""
    target_name = args.extract_plain_text().strip()
    if not target_name:
        # 显示可前往列表
        # ...
        return

    # 调用 service.move_to_scene(player, session, target_name)
    # ...
```

- [ ] **Step 3: 实现所有命令处理器**

所有处理器遵循项目规范：
- 不使用 `except Exception`（spec project-rules）
- UnitOfWork 外部调用 finish()
- 使用 `get_unified_player` 获取玩家

- [ ] **Step 4: 移除 SUPERUSER 权限限制**

所有命令的 `permission=SUPERUSER` 改为不限制权限（删除 `permission` 参数），因为系统即将上线给所有玩家。

- [ ] **Step 5: 提交**

```bash
git add plugins/xiuxian_game/inner_realm/commands.py
git commit -m "feat(inner_realm): 重写commands.py为场景节点命令系统"
```

---

### Task 9: 更新帮助信息和AI知识库

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py:2369-2492`
- Modify: `plugins/xiuxian_game/data/knowledge/inner_realm_help.yaml`

- [ ] **Step 1: 更新 `help.py` 中的里界帮助文本**

替换 `handle_inner_realm_help` 中的整个 msg 字符串，更新为荔湾鬼镇的命令和玩法说明。要点：
- 删除「迭代开发中/仅管理员」的提示
- 删除坐标移动命令（上/下/左/右/移动）
- 新增【前往 场景名】【使用 道具名】【道具】
- 更新首批里界列表为只有「荔湾鬼镇(Lv.50)」
- 更新已实现功能列表

- [ ] **Step 2: 更新 `inner_realm_help.yaml`**

将 `help.py` 的新 msg 文本复制到 yaml 的 `body` 字段中。更新 keywords 列表。

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/player/help.py plugins/xiuxian_game/data/knowledge/inner_realm_help.yaml
git commit -m "docs: 更新里界系统帮助信息和AI知识库"
```

---

### Task 10: 集成测试和最终验证

- [ ] **Step 1: 验证 YAML 配置可正确加载**

```bash
cd D:/QQbot/GuiXiuXian2 && python -c "
import yaml
with open('plugins/xiuxian_game/data/inner_realms.yaml', encoding='utf-8') as f:
    config = yaml.safe_load(f)
    realms = config.get('realms', {})
    print(f'Realms: {list(realms.keys())}')
    liwan = realms.get('liwan_ghost_town', {})
    scenes = liwan.get('scenes', {})
    print(f'Scenes: {len(scenes)}')
    print(f'Scene IDs: {list(scenes.keys())}')
"
```

Expected: 20个场景节点ID

- [ ] **Step 2: 验证物品配置正确加载**

```bash
cd D:/QQbot/GuiXiuXian2 && python -c "
import yaml
with open('plugins/xiuxian_game/data/items.yaml', encoding='utf-8') as f:
    items = yaml.safe_load(f)
    materials = items['items']['materials']
    inner_realm_items = [m for m in materials if 'inner_realm_exclusive' in m.get('tags', [])]
    print(f'Inner realm exclusive materials: {len(inner_realm_items)}')
    for item in inner_realm_items:
        print(f'  - {item[\"item_id\"]}: {item[\"name\"]} ({item[\"rarity\"]})')
"
```

Expected: 6个专属材料

- [ ] **Step 3: 验证模块导入无报错**

```bash
cd D:/QQbot/GuiXiuXian2 && python -c "
import sys; sys.path.insert(0, '.')
from plugins.xiuxian_game.inner_realm.scene_engine import SceneEngine, SceneNode
print('scene_engine import OK')
"
```

- [ ] **Step 4: 验证旧物品确已删除**

```bash
cd D:/QQbot/GuiXiuXian2 && python -c "
import yaml
with open('plugins/xiuxian_game/data/items.yaml', encoding='utf-8') as f:
    items = yaml.safe_load(f)
    all_ids = set()
    for cat in items['items'].values():
        for item in cat:
            all_ids.add(item['item_id'])
    deleted = ['stained_infusion_bag', 'discolored_meal_tray', 'cracked_specimen_jar']
    for d in deleted:
        status = 'STILL EXISTS (ERROR!)' if d in all_ids else 'deleted OK'
        print(f'  {d}: {status}')
    kept = 'cursed_mirror_shard'
    status = 'preserved OK' if kept in all_ids else 'MISSING (ERROR!)'
    print(f'  {kept}: {status}')
"
```

- [ ] **Step 5: 最终提交**

```bash
git add -A
git status
git commit -m "feat(inner_realm): 荔湾鬼镇里界系统完整实现"
```
