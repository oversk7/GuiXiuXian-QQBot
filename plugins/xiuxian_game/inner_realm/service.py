"""
里界系统核心服务
"""
import json
import random
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List
from nonebot import logger

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.inner_realm import InnerRealmSession, InnerRealmTile
from ..models.player import Player
from .config import InnerRealmConfig


class DiceRollResult:
    """骰子判定结果"""

    def __init__(
        self,
        dice1: int,
        dice2: int,
        base_total: int,
        modifier: int,
        time_bonus: int,
        final_total: int,
        result_level: str,
        result_label: str
    ):
        self.dice1 = dice1
        self.dice2 = dice2
        self.base_total = base_total
        self.modifier = modifier
        self.time_bonus = time_bonus
        self.final_total = final_total
        self.result_level = result_level
        self.result_label = result_label


class InnerRealmService:
    """里界系统核心服务"""

    def __init__(self, uow: UnitOfWork):
        """
        初始化里界服务

        Args:
            uow: 工作单元
        """
        self.uow = uow

    # ==================== 骰子判定系统 ====================

    def roll_2d6(self, attribute_modifier: int = 0, time_bonus: int = 0) -> DiceRollResult:
        """
        执行2D6骰子判定

        Args:
            attribute_modifier: 属性修正值
            time_bonus: 时间加成

        Returns:
            骰子判定结果
        """
        # 投掷两个D6骰子
        dice1 = random.randint(1, 6)
        dice2 = random.randint(1, 6)
        base_total = dice1 + dice2

        # 计算最终结果
        final_total = base_total + attribute_modifier + time_bonus

        # 判断结果等级
        dice_config = InnerRealmConfig.get_dice_results_config()
        result_level = "normal_success"
        result_label = "⚖️ 普通成功"

        for level, config in dice_config.items():
            if config["min"] <= final_total <= config["max"]:
                result_level = level
                result_label = config["label"]
                break

        return DiceRollResult(
            dice1=dice1,
            dice2=dice2,
            base_total=base_total,
            modifier=attribute_modifier,
            time_bonus=time_bonus,
            final_total=final_total,
            result_level=result_level,
            result_label=result_label
        )

    def calculate_attribute_modifier(
        self,
        player: Player,
        action_type: str
    ) -> int:
        """
        计算属性修正值

        Args:
            player: 玩家对象
            action_type: 行动类型（search/intimidate/assassination/decipher/stealth）

        Returns:
            属性修正值
        """
        attr_modifiers = InnerRealmConfig.get_attribute_modifiers()

        if action_type not in attr_modifiers:
            return 0

        modifier_config = attr_modifiers[action_type]
        primary_attr = modifier_config["primary"]
        scale = modifier_config["scale"]

        # 获取玩家对应属性值
        attr_value = 0
        if primary_attr == "luck":
            attr_value = player.luck
        elif primary_attr == "attack":
            attr_value = player.attack
        elif primary_attr == "agility":
            attr_value = player.agility
        elif primary_attr == "intelligence":
            attr_value = player.intelligence

        # 计算修正值
        return int(attr_value * scale)

    def get_time_bonus(self, action_type: str) -> int:
        """
        获取当前时间的加成

        Args:
            action_type: 行动类型

        Returns:
            时间加成值
        """
        time_config = InnerRealmConfig.get_time_system_config()
        current_hour = datetime.now().hour

        # 判断当前时段
        for period_name, period_config in time_config.items():
            start_hour = period_config["start_hour"]
            end_hour = period_config["end_hour"]

            # 处理跨日情况（如22:00-6:00）
            if start_hour > end_hour:
                if current_hour >= start_hour or current_hour < end_hour:
                    bonuses = period_config.get("bonuses", {})
                    if action_type == "search":
                        return bonuses.get("search", 0)
                    elif action_type in ["intimidate", "assassination"]:
                        return bonuses.get("combat", 0)
            else:
                if start_hour <= current_hour < end_hour:
                    bonuses = period_config.get("bonuses", {})
                    if action_type == "search":
                        return bonuses.get("search", 0)
                    elif action_type in ["intimidate", "assassination"]:
                        return bonuses.get("combat", 0)

        return 0

    def format_dice_roll_message(
        self,
        action_name: str,
        result: DiceRollResult,
        description: str = ""
    ) -> str:
        """
        格式化骰子判定消息

        Args:
            action_name: 行动名称
            result: 判定结果
            description: 结果描述

        Returns:
            格式化的消息
        """
        lines = [
            f"🎲 {action_name}",
            "━━━━━━━━━━━━━",
            f"骰子: [{result.dice1}] + [{result.dice2}] = {result.base_total}"
        ]

        if result.modifier != 0:
            lines.append(f"属性修正: {result.modifier:+d}")
        if result.time_bonus != 0:
            lines.append(f"时间加成: {result.time_bonus:+d}")

        lines.extend([
            "━━━━━━━━━━━━━",
            f"最终: {result.final_total} {result.result_label}",
            "━━━━━━━━━━━━━"
        ])

        if description:
            lines.append(f"「{description}」")

        return "\n".join(lines)

    # ==================== 里界管理 ====================

    async def get_available_realms(self, player: Player) -> List[Dict[str, Any]]:
        """
        获取玩家可进入的里界列表

        Args:
            player: 玩家对象

        Returns:
            可进入的里界列表
        """
        all_realms = InnerRealmConfig.get_all_realms()
        available = []

        for realm_name, realm_config in all_realms.items():
            level_req = realm_config.get("level_requirement", 0)

            available.append({
                "realm_name": realm_name,
                "display_name": realm_config.get("display_name", realm_name),
                "description": realm_config.get("description", ""),
                "level_requirement": level_req,
                "can_enter": player.level >= level_req
            })

        return available

    async def get_active_session(
        self,
        player_id: str,
        realm_name: str
    ) -> Optional[InnerRealmSession]:
        """
        获取玩家在指定里界的活跃会话

        Args:
            player_id: 玩家ID
            realm_name: 里界名称

        Returns:
            活跃会话，不存在则返回None
        """
        return await self.uow.inner_realm_sessions.get_active_session(
            player_id, realm_name
        )

    async def enter_realm(
        self,
        player: Player,
        realm_name: str
    ) -> Tuple[bool, str, Optional[InnerRealmSession]]:
        """
        玩家进入里界

        Args:
            player: 玩家对象
            realm_name: 里界名称

        Returns:
            (是否成功, 消息, 会话对象)
        """
        # 检查里界是否存在
        realm_config = InnerRealmConfig.get_realm_config(realm_name)
        if not realm_config:
            return False, f"⛔ 里界 '{realm_name}' 不存在", None

        # 检查等级要求
        level_req = realm_config.get("level_requirement", 0)
        if player.level < level_req:
            return False, f"⛔ 进入 {realm_config['display_name']} 需要 {level_req} 级", None

        # 检查是否已有活跃会话
        existing_session = await self.get_active_session(player.id, realm_name)
        if existing_session:
            return True, f"📍 你已经在 {realm_config['display_name']} 中了", existing_session

        # 创建新会话
        new_session = InnerRealmSession(
            player_id=player.id,
            realm_name=realm_name,
            entered_at=datetime.now(),
            last_refresh=datetime.now(),
            killed_count=0,
            saved_count=0,
            clue_collected="[]",
            x=0,
            y=0,
            state="{}",
            is_settled=False
        )

        await self.uow.inner_realm_sessions.add(new_session)
        await self.uow.commit()

        # 生成地图
        await self._generate_map(new_session, realm_config)
        await self.uow.commit()

        logger.info(f"玩家 {player.id} 进入里界 {realm_name}")

        return True, f"🚪 成功进入 {realm_config['display_name']}", new_session

    async def _generate_map(
        self,
        session: InnerRealmSession,
        realm_config: Dict[str, Any]
    ):
        """
        生成里界地图

        Args:
            session: 会话对象
            realm_config: 里界配置
        """
        map_size = realm_config.get("size", 25)
        event_weights = realm_config.get("event_weights", {})

        # 创建事件类型池
        event_pool = []
        for event_type, weight in event_weights.items():
            event_pool.extend([event_type] * weight)

        tiles = []
        for x in range(map_size):
            for y in range(map_size):
                # 起点固定为EMPTY
                if x == 0 and y == 0:
                    event_type = "EMPTY"
                else:
                    event_type = random.choice(event_pool)

                tile = InnerRealmTile(
                    session_id=session.id,
                    x=x,
                    y=y,
                    event_type=event_type,
                    state="{}",
                    is_triggered=False,
                    refreshed_at=datetime.now()
                )
                tiles.append(tile)

        # 批量添加地块
        await self.uow.inner_realm_tiles.batch_add(tiles)

        logger.info(f"为会话 {session.id} 生成了 {len(tiles)} 个地块")

    async def get_current_tile(
        self,
        session: InnerRealmSession
    ) -> Optional[InnerRealmTile]:
        """
        获取当前位置的地块

        Args:
            session: 会话对象

        Returns:
            当前地块，不存在则返回None
        """
        return await self.uow.inner_realm_tiles.get_by_position(
            session.id, session.x, session.y
        )

    async def move_in_realm(
        self,
        session: InnerRealmSession,
        dx: int,
        dy: int,
        realm_config: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        在里界中移动

        Args:
            session: 会话对象
            dx: X方向移动量
            dy: Y方向移动量
            realm_config: 里界配置

        Returns:
            (是否成功, 消息)
        """
        new_x = session.x + dx
        new_y = session.y + dy
        map_size = realm_config.get("size", 25)

        # 检查边界
        if not (0 <= new_x < map_size and 0 <= new_y < map_size):
            return False, "⛔ 超出地图边界"

        # 更新位置
        session.x = new_x
        session.y = new_y
        await self.uow.commit()

        # 获取新位置的地块信息
        tile = await self.get_current_tile(session)
        if not tile:
            return True, f"📍 移动到 ({new_x}, {new_y})"

        # 根据事件类型返回提示
        event_desc = {
            "EMPTY": "这里一片寂静...",
            "NPC": "你发现了一个人影...",
            "LOOT": "这里似乎有什么东西...",
            "CLUE": "你注意到了一些可疑的痕迹...",
            "BOSS": "⚠️ 一股强大的压迫感袭来！",
            "SURVIVOR": "你听到了微弱的呼救声..."
        }.get(tile.event_type, "...")

        return True, f"📍 移动到 ({new_x}, {new_y})\n{event_desc}"

    # ==================== 结局结算 ====================

    async def settle_ending(
        self,
        session: InnerRealmSession,
        realm_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        结算里界结局

        Args:
            session: 会话对象
            realm_config: 里界配置

        Returns:
            结局信息字典
        """
        endings = realm_config.get("endings", {})
        state = json.loads(session.state) if session.state else {}
        boss_defeated = state.get("boss_defeated", False)
        clue_count = len(json.loads(session.clue_collected))

        # 优先级：毁灭 > 猎人 > 屠夫 > 真相 > 救世
        matched_ending = None

        # 毁灭结局（最高优先级）
        if "annihilation" in endings:
            ending = endings["annihilation"]
            if session.killed_count >= 20 and boss_defeated:
                matched_ending = ("annihilation", ending)

        # 猎人结局
        if not matched_ending and "hunter" in endings:
            ending = endings["hunter"]
            if boss_defeated:
                matched_ending = ("hunter", ending)

        # 屠夫结局
        if not matched_ending and "butcher" in endings:
            ending = endings["butcher"]
            if session.killed_count >= 20:
                matched_ending = ("butcher", ending)

        # 真相结局
        if not matched_ending and "truth" in endings:
            ending = endings["truth"]
            if clue_count >= 5:
                matched_ending = ("truth", ending)

        # 救世结局
        if not matched_ending and "rescue" in endings:
            ending = endings["rescue"]
            if session.saved_count >= 3:
                matched_ending = ("rescue", ending)

        # 标记会话已结算
        session.is_settled = True
        await self.uow.commit()

        if matched_ending:
            ending_key, ending_config = matched_ending
            return {
                "ending_key": ending_key,
                "display_name": ending_config.get("display_name", "未知结局"),
                "description": ending_config.get("description", ""),
                "rewards": ending_config.get("rewards", [])
            }
        else:
            # 默认结局
            return {
                "ending_key": "default",
                "display_name": "离开",
                "description": "你离开了这个诡异的地方...",
                "rewards": []
            }
