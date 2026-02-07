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

        # 获取初始理智值
        sanity_config = InnerRealmConfig.get_global_config().get("sanity_system", {})
        initial_sanity = sanity_config.get("initial_sanity", 100)

        # 创建新会话
        new_session = InnerRealmSession(
            player_id=player.id,
            realm_name=realm_name,
            entered_at=datetime.now(),
            last_refresh=datetime.now(),
            killed_count=0,
            saved_count=0,
            sanity=initial_sanity,
            clue_collected="[]",
            x=0,
            y=0,
            state="{}",
            is_settled=False
        )

        await self.uow.inner_realm_sessions.add(new_session)

        # 标记玩家进入里界
        player.inner_realm = realm_name
        self.uow.session.add(player)

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
        boss_placed = False  # 确保只生成一个BOSS

        for x in range(map_size):
            for y in range(map_size):
                # 起点固定为EMPTY
                if x == 0 and y == 0:
                    event_type = "EMPTY"
                    state_data = {}
                else:
                    event_type = random.choice(event_pool)

                    # 如果是BOSS且已经放置过,改为EMPTY
                    if event_type == "BOSS" and boss_placed:
                        event_type = "EMPTY"

                    # 为不同事件类型生成具体数据
                    state_data = self._generate_event_data(event_type, realm_config)

                    if event_type == "BOSS":
                        boss_placed = True

                tile = InnerRealmTile(
                    session_id=session.id,
                    x=x,
                    y=y,
                    event_type=event_type,
                    state=json.dumps(state_data, ensure_ascii=False),
                    is_triggered=False,
                    refreshed_at=datetime.now()
                )
                tiles.append(tile)

        # 批量添加地块
        await self.uow.inner_realm_tiles.batch_add(tiles)

        logger.info(f"为会话 {session.id} 生成了 {len(tiles)} 个地块")

    def _generate_event_data(
        self,
        event_type: str,
        realm_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        为事件类型生成具体数据

        Args:
            event_type: 事件类型
            realm_config: 里界配置

        Returns:
            事件状态数据
        """
        if event_type == "EMPTY":
            return {}

        elif event_type == "NPC":
            # 从配置中随机选择一个NPC
            npcs = realm_config.get("npcs", [])
            if not npcs:
                return {}

            npc = random.choice(npcs)
            return {
                "npc_id": npc["id"],
                "name": npc["name"],
                "type": npc["type"],
                "hp": npc["hp"],
                "max_hp": npc["hp"],
                "attack": npc.get("attack", 0),
                "defense": npc.get("defense", 0),
                "description": npc.get("description", ""),
                "dialogue": npc.get("dialogue", []),
                "loot": npc.get("loot", []),
                "alive": True,
                "威吓_success": npc.get("威吓_success", ""),
                "威吓_fail": npc.get("威吓_fail", ""),
                "reveal_description": npc.get("reveal_description", "")  # 伪装者暴露描述
            }

        elif event_type == "LOOT":
            # 生成随机物品
            # 这里暂时返回空,等后续实现物品系统
            return {
                "looted": False,
                "items": []  # 后续填充物品列表
            }

        elif event_type == "CLUE":
            # 从配置中随机选择一个线索
            clues = realm_config.get("clues", [])
            if not clues:
                return {}

            clue = random.choice(clues)
            return {
                "clue_id": clue["id"],
                "name": clue["name"],
                "description": clue.get("description", ""),
                "reveal": clue.get("reveal", ""),
                "collected": False
            }

        elif event_type == "BOSS":
            # 生成BOSS
            boss = realm_config.get("boss", {})
            if not boss:
                return {}

            return {
                "boss_id": boss["id"],
                "name": boss["name"],
                "hp": boss["hp"],
                "max_hp": boss["hp"],
                "attack": boss["attack"],
                "defense": boss["defense"],
                "description": boss.get("description", ""),
                "dialogue": boss.get("dialogue", []),
                "special_skills": boss.get("special_skills", []),
                "loot": boss.get("loot", []),
                "alive": True
            }

        elif event_type == "SURVIVOR":
            # 从配置中随机选择一个幸存者
            survivors = realm_config.get("survivors", [])
            if not survivors:
                return {}

            survivor = random.choice(survivors)
            return {
                "survivor_id": survivor["id"],
                "name": survivor["name"],
                "description": survivor.get("description", ""),
                "dialogue": survivor.get("dialogue", []),
                "save_reward": survivor.get("save_reward", []),
                "saved": False,
                "killed": False
            }

        elif event_type == "COGNITION_TAMPER":
            # 认知篡改触发点,暂时返回空
            return {
                "triggered": False
            }

        return {}

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

    # ==================== 理智系统 ====================

    async def modify_sanity(
        self,
        session: InnerRealmSession,
        amount: int,
        reason: str = ""
    ) -> Tuple[int, str]:
        """
        修改玩家理智值

        Args:
            session: 会话对象
            amount: 修改量（正数恢复，负数损失）
            reason: 修改原因

        Returns:
            (新理智值, 警告信息)
        """
        sanity_config = InnerRealmConfig.get_global_config().get("sanity_system", {})
        max_sanity = sanity_config.get("max_sanity", 100)

        old_sanity = session.sanity
        session.sanity = max(0, min(max_sanity, session.sanity + amount))
        await self.uow.commit()

        # 生成警告信息
        warning = ""
        if session.sanity <= sanity_config.get("critical_threshold", 10):
            warning = "💀 极度危险！你的理智接近崩溃！"
        elif session.sanity <= sanity_config.get("danger_threshold", 30):
            warning = "🔴 危险！你的理智严重损坏！"
        elif session.sanity <= sanity_config.get("warning_threshold", 50):
            warning = "🟡 警告！你的理智开始不稳定！"

        log_msg = f"理智值变化: {old_sanity} -> {session.sanity}"
        if reason:
            log_msg += f" ({reason})"
        if warning:
            log_msg += f" [{warning}]"

        logger.info(log_msg)
        return session.sanity, warning

    async def trigger_sanity_loss(
        self,
        session: InnerRealmSession,
        trigger_type: str
    ) -> Tuple[int, str]:
        """
        触发理智损失

        Args:
            session: 会话对象
            trigger_type: 触发类型（witness_death/read_disturbing_clue等）

        Returns:
            (理智损失量, 描述)
        """
        cognition_config = InnerRealmConfig.get_global_config().get("cognition_tamper_system", {})
        triggers = cognition_config.get("sanity_loss_triggers", {})

        if trigger_type not in triggers:
            return 0, ""

        trigger_config = triggers[trigger_type]
        amount = trigger_config.get("amount", 0)
        description = trigger_config.get("description", "")

        await self.modify_sanity(session, amount, description)

        return abs(amount), description

    async def trigger_sanity_recovery(
        self,
        session: InnerRealmSession,
        recovery_type: str
    ) -> Tuple[int, str]:
        """
        触发理智恢复

        Args:
            session: 会话对象
            recovery_type: 恢复类型（rescue_survivor/reveal_truth等）

        Returns:
            (理智恢复量, 描述)
        """
        cognition_config = InnerRealmConfig.get_global_config().get("cognition_tamper_system", {})
        recoveries = cognition_config.get("sanity_recovery", {})

        if recovery_type not in recoveries:
            return 0, ""

        recovery_config = recoveries[recovery_type]
        amount = recovery_config.get("amount", 0)
        description = recovery_config.get("description", "")

        await self.modify_sanity(session, amount, description)

        return amount, description

    async def check_cognition_tamper(
        self,
        session: InnerRealmSession
    ) -> Optional[Dict[str, Any]]:
        """
        检查是否触发认知篡改

        Args:
            session: 会话对象

        Returns:
            触发的篡改事件配置，未触发返回None
        """
        cognition_config = InnerRealmConfig.get_global_config().get("cognition_tamper_system", {})
        tamper_types = cognition_config.get("tamper_types", {})

        # 根据理智值过滤可触发的篡改
        available_tampers = []
        for tamper_id, tamper_config in tamper_types.items():
            # 检查是否是极度危险的篡改（只在理智<30时触发）
            is_critical = tamper_config.get("critical", False)
            if is_critical and session.sanity >= 30:
                continue

            # 检查触发概率
            trigger_chance = tamper_config.get("trigger_chance", 0)

            # 理智值越低，触发概率越高
            sanity_multiplier = 1.0
            if session.sanity < 30:
                sanity_multiplier = 2.0
            elif session.sanity < 50:
                sanity_multiplier = 1.5

            adjusted_chance = min(1.0, trigger_chance * sanity_multiplier)

            if random.random() < adjusted_chance:
                available_tampers.append({
                    "id": tamper_id,
                    "config": tamper_config
                })

        # 随机选择一个篡改事件
        if available_tampers:
            selected = random.choice(available_tampers)
            logger.info(f"触发认知篡改: {selected['id']}")
            return selected

        return None

    async def apply_cognition_tamper(
        self,
        session: InnerRealmSession,
        tamper_event: Dict[str, Any]
    ) -> str:
        """
        应用认知篡改效果

        Args:
            session: 会话对象
            tamper_event: 篡改事件配置

        Returns:
            篡改效果描述
        """
        tamper_id = tamper_event["id"]
        tamper_config = tamper_event["config"]

        name = tamper_config.get("name", "未知篡改")
        description = tamper_config.get("description", "")
        sanity_cost = tamper_config.get("sanity_cost", 0)
        effects = tamper_config.get("effects", [])

        # 应用理智损失
        await self.modify_sanity(session, sanity_cost, name)

        # 根据篡改类型应用特殊效果
        state = json.loads(session.state) if session.state else {}

        if tamper_id == "phantom_npc":
            # 标记生成幻影NPC
            state["phantom_npc_active"] = True

        elif tamper_id == "memory_alteration":
            # 篡改击杀记录
            delta = random.randint(-3, 3)
            old_count = session.killed_count
            session.killed_count = max(0, session.killed_count + delta)
            state["memory_altered"] = True
            state["kill_count_delta"] = delta
            logger.info(f"记忆篡改: 击杀数 {old_count} -> {session.killed_count}")

        elif tamper_id == "sensory_distortion":
            # 标记感官扭曲
            state["sensory_distorted"] = True

        elif tamper_id == "time_dilation":
            # 标记时间错乱
            state["time_dilated"] = True

        elif tamper_id == "identity_confusion":
            # 身份混淆（最恐怖）
            state["identity_confused"] = True

        elif tamper_id == "truth_inversion":
            # 真相反转
            state["truth_inverted"] = True

        # 保存状态
        session.state = json.dumps(state, ensure_ascii=False)
        await self.uow.commit()

        # 构建消息
        lines = [
            "━━━━━━━━━━━━━",
            f"⚠️ {name}",
            "━━━━━━━━━━━━━",
            description,
            "",
            "效果："
        ]
        lines.extend([f"  • {effect}" for effect in effects])

        return "\n".join(lines)

    # ==================== 结局结算 ====================

    async def settle_ending(
        self,
        player: Player,
        session: InnerRealmSession,
        realm_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        结算里界结局

        Args:
            player: 玩家对象
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

        # 清空玩家的里界标记
        player.inner_realm = None
        self.uow.session.add(player)

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

    # ==================== 事件触发系统 ====================

    async def perform_search(
        self,
        player: Player,
        session: InnerRealmSession,
        tile: InnerRealmTile
    ) -> Tuple[bool, str]:
        """
        执行搜刮判定

        Args:
            player: 玩家对象
            session: 会话对象
            tile: 当前地块

        Returns:
            (是否成功, 结果描述)
        """
        # 检查地块类型
        if tile.event_type == "EMPTY":
            return False, "⛔ 这里一片荒芜，没有什么可以搜刮的..."

        if tile.event_type == "LOOT":
            state = json.loads(tile.state) if tile.state else {}
            if state.get("looted"):
                return False, "⛔ 这里已经被搜刮过了，什么都没剩下..."

            # 执行2D6+幸运判定
            modifier = self.calculate_attribute_modifier(player, "search")
            time_bonus = self.get_time_bonus("search")
            result = self.roll_2d6(modifier, time_bonus)

            # 根据判定结果给予奖励
            if result.result_level == "critical_failure":
                # 大失败：触发陷阱，损失理智
                await self.modify_sanity(session, -10, "搜刮触发陷阱")
                return False, self.format_dice_roll_message(
                    "搜刮检定",
                    result,
                    "你触发了陷阱！一股黑雾涌出，侵蚀着你的理智... (理智-10)"
                )

            elif result.result_level == "failure":
                # 失败：没找到东西
                return False, self.format_dice_roll_message(
                    "搜刮检定",
                    result,
                    "你翻遍了这里，但什么也没找到..."
                )

            else:
                # 成功：获得物品
                # TODO: 后续实现物品系统后，这里会发放实际物品
                state["looted"] = True
                tile.state = json.dumps(state, ensure_ascii=False)
                tile.is_triggered = True
                await self.uow.commit()

                reward_desc = "获得了一些物品"  # 暂时占位
                if result.result_level == "critical_success":
                    reward_desc = "发现了隐藏的宝箱！获得了大量物品！"

                return True, self.format_dice_roll_message(
                    "搜刮检定",
                    result,
                    reward_desc
                )

        elif tile.event_type == "CLUE":
            # 线索直接收集，不需要判定
            return await self.collect_clue(player, session, tile)

        return False, "⛔ 这里无法进行搜刮"

    async def perform_intimidation(
        self,
        player: Player,
        session: InnerRealmSession,
        tile: InnerRealmTile,
        npc_name: str = None
    ) -> Tuple[bool, str]:
        """
        执行威吓判定

        Args:
            player: 玩家对象
            session: 会话对象
            tile: 当前地块
            npc_name: NPC名称（可选）

        Returns:
            (是否成功, 结果描述)
        """
        # 检查地块类型
        if tile.event_type not in ["NPC", "BOSS", "SURVIVOR"]:
            return False, "⛔ 这里没有可以威吓的目标..."

        state = json.loads(tile.state) if tile.state else {}

        # NPC已死亡或已处理
        if tile.event_type == "NPC" and not state.get("alive"):
            return False, "⛔ 这里只剩下一具尸体..."

        if tile.event_type == "SURVIVOR" and (state.get("saved") or state.get("killed")):
            return False, "⛔ 这个幸存者已经离开了..."

        # 获取目标信息
        target_name = state.get("name", "未知目标")
        target_type = state.get("type", "civilian")

        # 执行2D6+攻击判定
        modifier = self.calculate_attribute_modifier(player, "intimidate")
        time_bonus = self.get_time_bonus("intimidate")
        result = self.roll_2d6(modifier, time_bonus)

        if result.result_level == "critical_failure":
            # 大失败：目标逃跑或变异
            if target_type == "disguised":
                # 伪装者暴露真身并攻击
                reveal_desc = state.get("reveal_description", "目标突然暴露真身！")
                return False, self.format_dice_roll_message(
                    "威吓检定",
                    result,
                    f"{reveal_desc}\n⚠️ 进入战斗状态！（战斗系统待实现）"
                )
            else:
                # 普通NPC逃跑或惊动其他人
                威吓_fail = state.get("威吓_fail", f"{target_name}惊恐地逃走了，惊动了周围的其他人！")
                return False, self.format_dice_roll_message(
                    "威吓检定",
                    result,
                    威吓_fail
                )

        elif result.result_level == "failure":
            # 失败：目标拒绝，可能会攻击
            return False, self.format_dice_roll_message(
                "威吓检定",
                result,
                f"{target_name}没有被吓倒，反而更加警惕了..."
            )

        else:
            # 成功：目标屈服，交出物品/信息
            威吓_success = state.get("威吓_success", f"{target_name}颤抖着交出了一些东西...")

            # TODO: 后续实现物品系统后，这里会发放实际物品
            loot_items = state.get("loot", [])

            # 标记为已威吓
            tile.is_triggered = True
            await self.uow.commit()

            bonus_desc = ""
            if result.result_level == "critical_success":
                bonus_desc = "\n🌟 大成功！获得了双倍物品！"

            return True, self.format_dice_roll_message(
                "威吓检定",
                result,
                f"{威吓_success}{bonus_desc}"
            )

    async def perform_assassination(
        self,
        player: Player,
        session: InnerRealmSession,
        tile: InnerRealmTile,
        npc_name: str = None
    ) -> Tuple[bool, str]:
        """
        执行处决判定（静默击杀）

        Args:
            player: 玩家对象
            session: 会话对象
            tile: 当前地块
            npc_name: NPC名称（可选）

        Returns:
            (是否成功, 结果描述)
        """
        # 检查地块类型
        if tile.event_type not in ["NPC", "SURVIVOR"]:
            return False, "⛔ 这里没有可以处决的目标..."

        state = json.loads(tile.state) if tile.state else {}

        # NPC已死亡
        if not state.get("alive"):
            return False, "⛔ 这里只剩下一具尸体..."

        target_name = state.get("name", "未知目标")
        target_type = state.get("type", "civilian")

        # 执行2D6+敏捷判定
        modifier = self.calculate_attribute_modifier(player, "assassination")
        time_bonus = self.get_time_bonus("assassination")
        result = self.roll_2d6(modifier, time_bonus)

        if result.result_level == "critical_failure":
            # 大失败：目标惨叫，惊动所有人
            await self.modify_sanity(session, -5, "处决失败")
            return False, self.format_dice_roll_message(
                "处决检定",
                result,
                f"{target_name}发出了凄厉的惨叫，惊动了整个区域！(理智-5)\n⚠️ 所有附近的敌人都察觉到你了！"
            )

        elif result.result_level == "failure":
            # 失败：目标挣扎，进入战斗
            return False, self.format_dice_roll_message(
                "处决检定",
                result,
                f"{target_name}察觉到危险，开始挣扎！\n⚠️ 进入战斗状态！（战斗系统待实现）"
            )

        else:
            # 成功：无声击杀
            state["alive"] = False
            if tile.event_type == "SURVIVOR":
                state["killed"] = True

            tile.state = json.dumps(state, ensure_ascii=False)
            tile.is_triggered = True

            # 增加击杀计数
            session.killed_count += 1

            # 根据目标类型触发理智损失
            if target_type == "civilian" or tile.event_type == "SURVIVOR":
                await self.trigger_sanity_loss(session, "kill_innocent")

            await self.uow.commit()

            success_desc = f"你悄无声息地解决了{target_name}..."
            if result.result_level == "critical_success":
                success_desc = f"完美！你如鬼魅般抹去了{target_name}的生命，没有留下任何痕迹！"

            # 获得战利品（TODO: 后续实现）
            return True, self.format_dice_roll_message(
                "处决检定",
                result,
                success_desc
            )

    async def talk_to_npc(
        self,
        player: Player,
        session: InnerRealmSession,
        tile: InnerRealmTile,
        npc_name: str = None
    ) -> Tuple[bool, str]:
        """
        与NPC交谈

        Args:
            player: 玩家对象
            session: 会话对象
            tile: 当前地块
            npc_name: NPC名称（可选）

        Returns:
            (是否成功, 对话内容)
        """
        # 检查地块类型
        if tile.event_type not in ["NPC", "BOSS", "SURVIVOR"]:
            return False, "⛔ 这里没有可以交谈的对象..."

        state = json.loads(tile.state) if tile.state else {}

        # NPC已死亡
        if tile.event_type in ["NPC", "BOSS"] and not state.get("alive"):
            return False, "⛔ 死人是不会说话的..."

        if tile.event_type == "SURVIVOR" and (state.get("saved") or state.get("killed")):
            return False, "⛔ 这个人已经离开了..."

        target_name = state.get("name", "未知目标")
        description = state.get("description", "")
        dialogues = state.get("dialogue", [])

        if not dialogues:
            return False, f"⛔ {target_name}沉默不语..."

        # 随机选择一句对话
        dialogue = random.choice(dialogues)

        lines = [
            f"💬 与 {target_name} 交谈",
            "━━━━━━━━━━━━━",
            f"📝 {description}",
            "",
            f"💭 {target_name}：「{dialogue}」"
        ]

        return True, "\n".join(lines)

    async def collect_clue(
        self,
        player: Player,
        session: InnerRealmSession,
        tile: InnerRealmTile
    ) -> Tuple[bool, str]:
        """
        收集线索

        Args:
            player: 玩家对象
            session: 会话对象
            tile: 当前地块

        Returns:
            (是否成功, 结果描述)
        """
        if tile.event_type != "CLUE":
            return False, "⛔ 这里没有线索..."

        state = json.loads(tile.state) if tile.state else {}

        if state.get("collected"):
            return False, "⛔ 你已经收集过这个线索了..."

        clue_id = state.get("clue_id", "")
        clue_name = state.get("name", "未知线索")
        clue_desc = state.get("description", "")
        clue_reveal = state.get("reveal", "")

        # 标记为已收集
        state["collected"] = True
        tile.state = json.dumps(state, ensure_ascii=False)
        tile.is_triggered = True

        # 添加到会话的线索列表
        clue_list = json.loads(session.clue_collected) if session.clue_collected else []
        if clue_id not in clue_list:
            clue_list.append(clue_id)
            session.clue_collected = json.dumps(clue_list, ensure_ascii=False)

        # 触发理智恢复
        recovered, _ = await self.trigger_sanity_recovery(session, "reveal_truth")

        await self.uow.commit()

        lines = [
            "📖 收集线索",
            "━━━━━━━━━━━━━",
            f"📝 {clue_name}",
            "",
            f"「{clue_desc}」"
        ]

        if clue_reveal:
            lines.extend([
                "",
                "━━━━━━━━━━━━━",
                f"💡 真相揭示：{clue_reveal}"
            ])

        if recovered > 0:
            lines.append(f"\n🧠 理智恢复 +{recovered}")

        return True, "\n".join(lines)

    async def save_survivor(
        self,
        player: Player,
        session: InnerRealmSession,
        tile: InnerRealmTile
    ) -> Tuple[bool, str]:
        """
        救助幸存者

        Args:
            player: 玩家对象
            session: 会话对象
            tile: 当前地块

        Returns:
            (是否成功, 结果描述)
        """
        if tile.event_type != "SURVIVOR":
            return False, "⛔ 这里没有幸存者..."

        state = json.loads(tile.state) if tile.state else {}

        if state.get("saved"):
            return False, "⛔ 你已经救过这个幸存者了..."

        if state.get("killed"):
            return False, "⛔ 你已经杀死了这个幸存者..."

        survivor_name = state.get("name", "幸存者")
        survivor_desc = state.get("description", "")
        dialogues = state.get("dialogue", [])

        # 标记为已救助
        state["saved"] = True
        tile.state = json.dumps(state, ensure_ascii=False)
        tile.is_triggered = True

        # 增加救出计数
        session.saved_count += 1

        # 触发理智恢复
        recovered, _ = await self.trigger_sanity_recovery(session, "rescue_survivor")

        await self.uow.commit()

        # 随机选择一句感激的话
        thanks = random.choice(dialogues) if dialogues else "谢谢你救了我..."

        lines = [
            "🛡️ 救助幸存者",
            "━━━━━━━━━━━━━",
            f"📝 {survivor_desc}",
            "",
            f"💭 {survivor_name}：「{thanks}」",
            "",
            "━━━━━━━━━━━━━",
            "✅ 幸存者已安全离开"
        ]

        if recovered > 0:
            lines.append(f"🧠 理智恢复 +{recovered}")

        # TODO: 后续实现奖励发放
        lines.append("\n💡 提示: 救助幸存者会影响最终结局")

        return True, "\n".join(lines)
