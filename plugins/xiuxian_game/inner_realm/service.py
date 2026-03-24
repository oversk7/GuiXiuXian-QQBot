"""
里界系统核心服务 — 场景节点版
"""
import json
import random
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List
from nonebot import logger

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.inner_realm import InnerRealmSession
from ..models.player import Player
from .config import InnerRealmConfig
from .scene_engine import SceneEngine


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

    # ==================== 冷却系统 ====================

    def check_action_cooldown(self, session: InnerRealmSession, action: str) -> Tuple[bool, int]:
        """
        检查操作冷却。

        Args:
            session: 会话对象
            action: 操作类型（search/intimidate/assassination/move/battle）

        Returns:
            (是否可操作, 剩余秒数)
        """
        cooldowns_config = InnerRealmConfig.get_global_config().get("cooldowns", {})
        cooldown_seconds = cooldowns_config.get(action, 0)
        if cooldown_seconds <= 0:
            return True, 0

        state = json.loads(session.state) if session.state else {}
        last_action_times = state.get("last_action_time", {})
        last_time_str = last_action_times.get(action)

        if not last_time_str:
            return True, 0

        last_time = datetime.fromisoformat(last_time_str)
        elapsed = (datetime.now() - last_time).total_seconds()
        remaining = cooldown_seconds - elapsed

        if remaining > 0:
            return False, int(remaining) + 1
        return True, 0

    async def update_action_cooldown(self, session: InnerRealmSession, action: str):
        """
        更新操作冷却时间戳。

        Args:
            session: 会话对象
            action: 操作类型
        """
        state = json.loads(session.state) if session.state else {}
        if "last_action_time" not in state:
            state["last_action_time"] = {}
        state["last_action_time"][action] = datetime.now().isoformat()
        session.state = json.dumps(state, ensure_ascii=False)

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

    def calculate_mortal_modifier(self, player: Player) -> int:
        """凡人状态属性修正（修为被压制后的固定加成）"""
        return min(3, player.level // 100)

    def get_time_bonus(self, action_type: str, session: InnerRealmSession = None) -> int:
        """
        获取当前时间的加成

        Args:
            action_type: 行动类型
            session: 会话对象（可选）

        Returns:
            时间加成值
        """
        time_config = InnerRealmConfig.get_time_system_config()
        current_hour = datetime.now().hour

        # 判断当前时段并返回加成
        for period_name, period_config in time_config.items():
            start_hour = period_config["start_hour"]
            end_hour = period_config["end_hour"]

            in_period = False
            if start_hour > end_hour:
                if current_hour >= start_hour or current_hour < end_hour:
                    in_period = True
            else:
                if start_hour <= current_hour < end_hour:
                    in_period = True

            if in_period:
                bonuses = period_config.get("bonuses", {})
                if action_type == "search":
                    bonus = bonuses.get("search", 0)
                elif action_type in ["intimidate", "assassination"]:
                    bonus = bonuses.get("combat", 0)
                else:
                    bonus = 0

                return bonus

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

    # ==================== 场景引擎集成 ====================

    def _get_scene_engine(self, realm_name: str) -> SceneEngine:
        """获取指定里界的场景引擎"""
        realm_config = InnerRealmConfig.get_realm_config(realm_name)
        if not realm_config:
            raise ValueError(f"里界配置不存在: {realm_name}")
        return SceneEngine(realm_config)

    # ==================== 进入/离开里界 ====================

    async def get_available_realms(self, player: Player) -> List[Dict[str, Any]]:
        """获取玩家可进入的里界列表"""
        all_realms = InnerRealmConfig.get_all_realms()
        result = []
        for key, config in all_realms.items():
            level_req = config.get("level_requirement", 1)
            result.append({
                "key": key,
                "display_name": config.get("display_name", key),
                "description": config.get("description", ""),
                "level_requirement": level_req,
                "can_enter": player.level >= level_req
            })
        return result

    async def enter_realm(
        self,
        player: Player,
        realm_key: str
    ) -> Tuple[bool, str, Optional[InnerRealmSession]]:
        """
        进入里界 -- 创建新会话

        Returns:
            (success, message, session)
        """
        realm_config = InnerRealmConfig.get_realm_config(realm_key)
        if not realm_config:
            return False, "⛔ 里界不存在", None

        level_req = realm_config.get("level_requirement", 1)
        if player.level < level_req:
            return False, f"⛔ 等级不足，需要 Lv.{level_req}", None

        if player.inner_realm:
            return False, "⛔ 你已经在一个里界中了", None

        # 检查是否首次通关
        clears: Dict[str, Any] = {}
        if hasattr(player, 'inner_realm_clears') and player.inner_realm_clears:
            try:
                clears = json.loads(player.inner_realm_clears)
            except (json.JSONDecodeError, TypeError):
                clears = {}

        is_first = not clears.get(realm_key, {}).get("cleared", False)

        # 清理已结算的旧会话
        from sqlalchemy import select, and_
        stmt = select(InnerRealmSession).where(
            and_(
                InnerRealmSession.player_id == player.id,
                InnerRealmSession.realm_name == realm_key,
                InnerRealmSession.is_settled == True
            )
        )
        result = await self.uow.session.execute(stmt)
        old_sessions = result.scalars().all()
        for old_session in old_sessions:
            await self.uow.session.delete(old_session)
        if old_sessions:
            await self.uow.session.flush()

        # 创建新会话
        session = InnerRealmSession(
            player_id=player.id,
            realm_name=realm_key,
            killed_count=0,
            saved_count=0,
            sanity=100,
            clue_collected='[]',
            current_scene="town_entrance_dusk",
            visited_scenes='["town_entrance_dusk"]',
            inventory='{}',
            is_first_clear=0,
            move_count=0,
            state=json.dumps({
                "scene_states": {},
                "npc_states": {},
                "events_triggered": [],
                "phase": "dusk",
                "pending_rewards": {"items": [], "gold": 0},
                "is_first_playthrough": is_first,
            }, ensure_ascii=False),
        )

        self.uow.session.add(session)
        player.inner_realm = realm_key
        await self.uow.commit()

        # 生成入场描述
        engine = self._get_scene_engine(realm_key)
        scene_text = engine.enter_scene(session, "town_entrance_dusk", is_first)

        # 修正为0因为这是初始进入（enter_scene 会递增 move_count）
        session.move_count = 0
        await self.uow.commit()

        display_name = realm_config.get("display_name", realm_key)
        suppress = realm_config.get("suppress_cultivation", False)

        lines = [f"🌌 进入 {display_name}"]
        if suppress:
            lines.append("⚠️ 你的修为被压制，在这里你和凡人无异")
        lines.append("")
        lines.append(scene_text)

        return True, "\n".join(lines), session

    async def get_active_session(
        self,
        player_id: str,
        realm_name: str
    ) -> Optional[InnerRealmSession]:
        """获取玩家的活跃会话"""
        return await self.uow.inner_realm_sessions.get_active_session(
            player_id, realm_name
        )

    # ==================== 场景移动 ====================

    async def move_to_scene(
        self,
        player: Player,
        session: InnerRealmSession,
        target_display_name: str
    ) -> Tuple[bool, str]:
        """
        前往指定场景

        Returns:
            (success, message)
        """
        engine = self._get_scene_engine(session.realm_name)

        # 先检查理智
        if session.sanity <= 0:
            return False, self._sanity_collapse_text()

        # 通过显示名查找场景
        target = engine.get_scene_by_display_name(target_display_name)
        if not target:
            # 尝试模糊匹配
            for scene in engine.scenes.values():
                if target_display_name in scene.display_name:
                    target = scene
                    break

        if not target:
            return False, f"⛔ 找不到「{target_display_name}」\n💡 使用【前往】查看可前往地点"

        # 检查是否可以进入
        can_enter, reason = engine.can_enter_scene(session, target.id)
        if not can_enter:
            # 入夜户外=死亡
            if "试炼失败" in reason:
                await self._handle_death(player, session, "outdoor_night")
            return False, reason

        # 执行移动
        state = json.loads(session.state) if session.state else {}
        is_first = state.get("is_first_playthrough", False)

        scene_text = engine.enter_scene(session, target.id, is_first)
        await self.uow.commit()

        return True, scene_text

    # ==================== 观察 ====================

    async def observe_scene(
        self,
        player: Player,
        session: InnerRealmSession
    ) -> str:
        """
        观察当前场景 -- 发现隐藏细节和线索

        Returns:
            观察结果文本
        """
        engine = self._get_scene_engine(session.realm_name)
        scene = engine.get_current_scene(session)
        if not scene:
            return "⛔ 当前位置异常"

        lines = [
            f"👁️ 仔细观察 · {scene.display_name}",
            "━━━━━━━━━━━━━",
        ]

        # 显示观察文本
        if scene.observe_text:
            lines.append(scene.observe_text)
        else:
            lines.append("你仔细看了看四周，没有发现什么特别的东西。")

        # 触发线索
        if scene.clue_on_observe:
            clue_id = scene.clue_on_observe
            realm_config = InnerRealmConfig.get_realm_config(session.realm_name)
            clues = realm_config.get("clues", [])

            clue_config = None
            for c in clues:
                if c["id"] == clue_id:
                    clue_config = c
                    break

            if clue_config:
                # 检查是否已收集
                collected = json.loads(session.clue_collected) if session.clue_collected else []
                if clue_id not in collected:
                    collected.append(clue_id)
                    session.clue_collected = json.dumps(collected)

                    # 保存到全局记录
                    await self._save_clue_globally(player, session.realm_name, clue_id)

                    lines.append("")
                    lines.append(f"📖 发现线索：{clue_config['name']}")
                    lines.append(f"💡 {clue_config.get('reveal', '')}")

                    await self.uow.commit()

        # 显示可前往地点
        lines.append("━━━━━━━━━━━━━")
        dests = engine.get_available_destinations(session)
        if dests:
            dest_names = [d.display_name for d in dests]
            lines.append(f"🚪 可前往: {' | '.join(dest_names)}")

        return "\n".join(lines)

    # ==================== 搜刮 ====================

    async def perform_search(
        self,
        player: Player,
        session: InnerRealmSession
    ) -> Tuple[bool, str]:
        """
        搜刮当前场景

        Returns:
            (success, message)
        """
        engine = self._get_scene_engine(session.realm_name)
        scene = engine.get_current_scene(session)
        if not scene:
            return False, "⛔ 当前位置异常"

        if not scene.searchable:
            return False, "⛔ 这里没有什么可搜刮的"

        # 检查是否已搜刮
        state = json.loads(session.state) if session.state else {}
        scene_states = state.get("scene_states", {})
        if scene_states.get(scene.id, {}).get("searched", False):
            return False, "⛔ 你已经搜过这里了"

        # 检查冷却
        can_act, remaining = self.check_action_cooldown(session, "search")
        if not can_act:
            return False, f"⏳ 搜刮冷却中，还需等待 {remaining} 秒"

        # 骰子判定
        modifier = self.calculate_mortal_modifier(player)
        time_bonus = self.get_time_bonus("search", session)
        result = self.roll_2d6(modifier, time_bonus)

        # 根据判定结果获取掉落
        loot_table = scene.loot_table
        if result.result_level == "critical_success":
            loot = loot_table.get("critical_success", {})
        elif result.result_level == "success":
            loot = loot_table.get("success", {})
        elif result.result_level == "normal_success":
            loot = loot_table.get("normal", {})
        elif result.result_level == "failure":
            loot = loot_table.get("failure", {})
        else:  # critical_failure
            loot = loot_table.get("failure", {})

        # 标记已搜刮
        if scene.id not in scene_states:
            scene_states[scene.id] = {}
        scene_states[scene.id]["searched"] = True
        state["scene_states"] = scene_states
        session.state = json.dumps(state, ensure_ascii=False)

        await self.update_action_cooldown(session, "search")

        # 处理掉落结果
        reward_lines = []

        # 发放物品
        items = loot.get("items", [])
        for item_info in items:
            item_id = item_info.get("id", "")
            qty = item_info.get("qty", 1)
            is_key = item_info.get("is_key_item", False)

            if is_key:
                # 关键道具存到session.inventory
                inventory = engine.get_session_inventory(session)
                inventory[item_id] = inventory.get(item_id, 0) + qty
                session.inventory = json.dumps(inventory, ensure_ascii=False)

                # 获取道具名称
                realm_config = InnerRealmConfig.get_realm_config(session.realm_name)
                key_items = realm_config.get("key_items", {})
                item_name = key_items.get(item_id, {}).get("name", item_id)
                reward_lines.append(f"🔑 获得关键道具：{item_name} x{qty}")

                # 检查是否获得房卡（触发线索2）
                if item_id == "room_card_4":
                    collected = json.loads(session.clue_collected) if session.clue_collected else []
                    if "clue_2" not in collected:
                        collected.append("clue_2")
                        session.clue_collected = json.dumps(collected)
                        await self._save_clue_globally(player, session.realm_name, "clue_2")
                        reward_lines.append("📖 发现线索：房卡上的字")
            else:
                # 普通材料记录到pending_rewards
                await self._add_pending_reward(session, item_id=item_id, qty=qty)
                # 获取物品名称
                from ..config import config as game_config
                item_config = game_config.items_config["by_id"].get(item_id)
                item_name = item_config.name if item_config else item_id
                reward_lines.append(f"📦 获得：{item_name} x{qty}")

        # 发放金币
        gold = loot.get("gold", 0)
        if gold > 0:
            await self._add_pending_reward(session, gold=gold)
            reward_lines.append(f"💰 获得：{gold} 金币")

        # 处理失败后果
        sanity_loss = loot.get("sanity", 0)
        if sanity_loss < 0:
            await self.modify_sanity(session, sanity_loss, "搜刮失败")

        failure_text = loot.get("text", "")
        death_result = loot.get("result", "")

        # 构建消息
        result_text = ""
        if result.result_level in ("critical_failure", "failure"):
            if failure_text:
                result_text = failure_text
            else:
                result_text = "什么也没找到..."
            if sanity_loss < 0:
                result_text += f"\n🧠 理智 {sanity_loss}"
        else:
            if reward_lines:
                result_text = "\n".join(reward_lines)
            else:
                result_text = "搜索了一番，没有发现有价值的东西。"

        await self.uow.commit()

        msg = self.format_dice_roll_message("搜刮检定", result, result_text)

        # 检查是否死亡
        if death_result == "death":
            await self._handle_death(player, session, "search_trap")
            msg += "\n\n💀 试炼失败"

        return True, msg

    # ==================== 威吓 ====================

    async def perform_intimidation(
        self,
        player: Player,
        session: InnerRealmSession,
        npc_name: str = None
    ) -> Tuple[bool, str]:
        """威吓NPC"""
        engine = self._get_scene_engine(session.realm_name)
        scene = engine.get_current_scene(session)
        if not scene:
            return False, "⛔ 当前位置异常"

        if not scene.npcs:
            return False, "⛔ 这里没有可以威吓的对象"

        # 查找NPC
        npc = self._find_npc_in_scene(session, scene, npc_name)
        if not npc:
            return False, "⛔ 找不到目标NPC"

        if not npc.get("can_intimidate", False):
            return False, f"⛔ {npc['name']} 不是你能威吓的对象"

        # 检查NPC是否存活
        state = json.loads(session.state) if session.state else {}
        npc_states = state.get("npc_states", {})
        if not npc_states.get(npc["id"], {}).get("alive", True):
            return False, f"⛔ {npc['name']} 已经死了"

        # 检查冷却
        can_act, remaining = self.check_action_cooldown(session, "intimidate")
        if not can_act:
            return False, f"⏳ 威吓冷却中，还需等待 {remaining} 秒"

        # 骰子判定
        modifier = self.calculate_mortal_modifier(player)
        difficulty = npc.get("intimidate_difficulty", 8)
        time_bonus = self.get_time_bonus("intimidate", session)
        result = self.roll_2d6(modifier, time_bonus)

        await self.update_action_cooldown(session, "intimidate")

        if result.final_total >= difficulty:
            # 威吓成功
            result_text = f"「{npc['name']}」被你的气势震慑，交出了身上的财物。"
            # 发放部分掉落
            for loot_item in npc.get("death_loot", [])[:1]:
                item_id = loot_item.get("id", "")
                qty = loot_item.get("qty", 1)
                is_key = loot_item.get("is_key_item", False)
                if is_key:
                    inventory = engine.get_session_inventory(session)
                    inventory[item_id] = inventory.get(item_id, 0) + qty
                    session.inventory = json.dumps(inventory, ensure_ascii=False)
                    realm_config = InnerRealmConfig.get_realm_config(session.realm_name)
                    key_items = realm_config.get("key_items", {})
                    item_name = key_items.get(item_id, {}).get("name", item_id)
                    result_text += f"\n🔑 获得：{item_name}"
                else:
                    await self._add_pending_reward(session, item_id=item_id, qty=qty)
                    from ..config import config as game_config
                    item_config = game_config.items_config["by_id"].get(item_id)
                    item_name = item_config.name if item_config else item_id
                    result_text += f"\n📦 获得：{item_name} x{qty}"
        else:
            result_text = f"「{npc['name']}」不为所动，冷冷地看着你。"
            await self.modify_sanity(session, -3, "威吓失败")
            result_text += "\n🧠 理智 -3"

        await self.uow.commit()
        return True, self.format_dice_roll_message("威吓检定", result, result_text)

    # ==================== 处决 ====================

    async def perform_assassination(
        self,
        player: Player,
        session: InnerRealmSession,
        npc_name: str = None
    ) -> Tuple[bool, str]:
        """处决NPC"""
        engine = self._get_scene_engine(session.realm_name)
        scene = engine.get_current_scene(session)
        if not scene:
            return False, "⛔ 当前位置异常"

        if not scene.npcs:
            return False, "⛔ 这里没有可以处决的对象"

        npc = self._find_npc_in_scene(session, scene, npc_name)
        if not npc:
            return False, "⛔ 找不到目标NPC"

        if not npc.get("can_execute", False):
            return False, f"⛔ {npc['name']} 无法被处决"

        state = json.loads(session.state) if session.state else {}
        npc_states = state.get("npc_states", {})
        if not npc_states.get(npc["id"], {}).get("alive", True):
            return False, f"⛔ {npc['name']} 已经死了"

        can_act, remaining = self.check_action_cooldown(session, "assassination")
        if not can_act:
            return False, f"⏳ 处决冷却中，还需等待 {remaining} 秒"

        modifier = self.calculate_mortal_modifier(player)
        difficulty = npc.get("execute_difficulty", 9)
        time_bonus = self.get_time_bonus("assassination", session)
        result = self.roll_2d6(modifier, time_bonus)

        await self.update_action_cooldown(session, "assassination")

        if result.final_total >= difficulty:
            # 处决成功
            npc_states[npc["id"]] = {"alive": False}
            state["npc_states"] = npc_states
            session.state = json.dumps(state, ensure_ascii=False)
            session.killed_count += 1

            result_text = f"你无声地解决了「{npc['name']}」。"

            # 发放掉落
            for loot_item in npc.get("death_loot", []):
                prob = loot_item.get("probability", 1.0)
                if random.random() > prob:
                    continue
                item_id = loot_item.get("id", "")
                qty = loot_item.get("qty", 1)
                is_key = loot_item.get("is_key_item", False)
                if is_key:
                    inventory = engine.get_session_inventory(session)
                    inventory[item_id] = inventory.get(item_id, 0) + qty
                    session.inventory = json.dumps(inventory, ensure_ascii=False)
                    realm_config = InnerRealmConfig.get_realm_config(session.realm_name)
                    key_items = realm_config.get("key_items", {})
                    item_name = key_items.get(item_id, {}).get("name", item_id)
                    result_text += f"\n🔑 获得：{item_name}"

                    if item_id == "room_card_4":
                        collected = json.loads(session.clue_collected) if session.clue_collected else []
                        if "clue_2" not in collected:
                            collected.append("clue_2")
                            session.clue_collected = json.dumps(collected)
                            await self._save_clue_globally(player, session.realm_name, "clue_2")
                            result_text += "\n📖 发现线索：房卡上的字"
                else:
                    await self._add_pending_reward(session, item_id=item_id, qty=qty)
                    from ..config import config as game_config
                    item_config = game_config.items_config["by_id"].get(item_id)
                    item_name = item_config.name if item_config else item_id
                    result_text += f"\n📦 获得：{item_name} x{qty}"

            # 理智损失（杀人代价）
            await self.modify_sanity(session, -3, "击杀")
            result_text += "\n🧠 理智 -3"
        else:
            result_text = f"处决失败！「{npc['name']}」发现了你的意图！"
            await self.modify_sanity(session, -5, "处决失败")
            result_text += "\n🧠 理智 -5"

        await self.uow.commit()
        return True, self.format_dice_roll_message("处决检定", result, result_text)

    # ==================== 交谈 ====================

    async def talk_to_npc(
        self,
        player: Player,
        session: InnerRealmSession,
        npc_name: str = None
    ) -> Tuple[bool, str]:
        """与NPC交谈"""
        engine = self._get_scene_engine(session.realm_name)
        scene = engine.get_current_scene(session)
        if not scene:
            return False, "⛔ 当前位置异常"

        if not scene.npcs:
            return False, "⛔ 这里没有可以交谈的对象"

        npc = self._find_npc_in_scene(session, scene, npc_name)
        if not npc:
            return False, "⛔ 找不到目标NPC"

        if not npc.get("can_talk", False):
            return False, f"⛔ {npc['name']} 不想和你说话"

        state = json.loads(session.state) if session.state else {}
        npc_states = state.get("npc_states", {})
        if not npc_states.get(npc["id"], {}).get("alive", True):
            return False, f"⛔ {npc['name']} 已经死了，无法交谈"

        # 对话树 -- 根据交谈次数递进
        talk_key = f"talk_count_{npc['id']}"
        talk_count = state.get(talk_key, 0)

        dialogues = npc.get("dialogue", [])
        if not dialogues:
            return False, f"⛔ {npc['name']} 沉默不语"

        # 选择对应的对话
        if talk_count < len(dialogues):
            dialogue = dialogues[talk_count]
        else:
            dialogue = dialogues[-1]  # 重复最后一句

        state[talk_key] = talk_count + 1
        session.state = json.dumps(state, ensure_ascii=False)
        await self.uow.commit()

        text = dialogue.get("text", "") if isinstance(dialogue, dict) else str(dialogue)

        lines = [
            f"💬 与「{npc['name']}」交谈",
            "━━━━━━━━━━━━━",
            text,
        ]

        return True, "\n".join(lines)

    # ==================== 使用道具 ====================

    async def use_item(
        self,
        player: Player,
        session: InnerRealmSession,
        item_name: str
    ) -> Tuple[bool, str]:
        """使用里界内道具"""
        engine = self._get_scene_engine(session.realm_name)
        inventory = engine.get_session_inventory(session)

        # 获取道具配置
        realm_config = InnerRealmConfig.get_realm_config(session.realm_name)
        key_items = realm_config.get("key_items", {})

        # 通过名称查找道具ID
        target_id = None
        for kid, kconfig in key_items.items():
            if kconfig.get("name", "") == item_name or kid == item_name:
                target_id = kid
                break

        if not target_id:
            return False, f"⛔ 没有叫「{item_name}」的道具"

        if inventory.get(target_id, 0) <= 0:
            return False, f"⛔ 你没有「{key_items[target_id]['name']}」"

        item_config = key_items[target_id]

        # 处理使用效果
        use_effect = item_config.get("use_effect", {})
        lines = [
            f"🎒 使用「{item_config['name']}」",
            "━━━━━━━━━━━━━",
        ]

        # 理智恢复/损失
        sanity_change = use_effect.get("sanity", 0)
        if sanity_change != 0:
            await self.modify_sanity(session, sanity_change, f"使用{item_config['name']}")
            if sanity_change > 0:
                lines.append(f"🧠 理智 +{sanity_change} (当前: {session.sanity})")
            else:
                lines.append(f"🧠 理智 {sanity_change} (当前: {session.sanity})")

        # 触发线索
        grant_clue = use_effect.get("grant_clue", "")
        if grant_clue:
            collected = json.loads(session.clue_collected) if session.clue_collected else []
            if grant_clue not in collected:
                collected.append(grant_clue)
                session.clue_collected = json.dumps(collected)
                await self._save_clue_globally(player, session.realm_name, grant_clue)

                clues = realm_config.get("clues", [])
                clue_config = next((c for c in clues if c["id"] == grant_clue), None)
                if clue_config:
                    lines.append(f"📖 发现线索：{clue_config['name']}")

        # 消耗道具
        inventory[target_id] = inventory.get(target_id, 0) - 1
        if inventory[target_id] <= 0:
            del inventory[target_id]
        session.inventory = json.dumps(inventory, ensure_ascii=False)

        # 检查场景特殊事件（如楼道使用针线引诱厂服男）
        scene = engine.get_current_scene(session)
        if scene:
            for event in scene.events:
                if event.get("trigger") == "on_use_item" and event.get("required_item") == target_id:
                    lines.append("")
                    lines.append(event.get("description", ""))
                    if event.get("result_text"):
                        lines.append(event["result_text"])
                    if event.get("unlock_search"):
                        state = json.loads(session.state) if session.state else {}
                        scene_states = state.get("scene_states", {})
                        if scene.id not in scene_states:
                            scene_states[scene.id] = {}
                        scene_states[scene.id]["event_unlocked"] = True
                        state["scene_states"] = scene_states
                        session.state = json.dumps(state, ensure_ascii=False)

        await self.uow.commit()
        return True, "\n".join(lines)

    # ==================== 道具查看 ====================

    async def get_inventory_display(self, session: InnerRealmSession) -> str:
        """显示里界内道具列表"""
        inventory = json.loads(session.inventory) if session.inventory else {}
        realm_config = InnerRealmConfig.get_realm_config(session.realm_name)
        key_items = realm_config.get("key_items", {})

        if not inventory:
            return "🎒 背包空空如也\n💡 搜刮场景可获得道具"

        lines = [
            "🎒 里界道具",
            "━━━━━━━━━━━━━",
        ]

        for item_id, qty in inventory.items():
            item_config = key_items.get(item_id, {})
            name = item_config.get("name", item_id)
            desc = item_config.get("description", "")
            lines.append(f"  {name} x{qty}")
            if desc:
                lines.append(f"    {desc}")

        lines.extend([
            "━━━━━━━━━━━━━",
            "💡 使用【使用 道具名】来使用道具",
        ])

        return "\n".join(lines)

    # ==================== 结局结算 ====================

    async def settle_ending(
        self,
        player: Player,
        session: InnerRealmSession,
        realm_config: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        结算结局

        Returns:
            dict with display_name, description, reward_desc
        """
        state = json.loads(session.state) if session.state else {}
        npc_states = state.get("npc_states", {})
        collected = json.loads(session.clue_collected) if session.clue_collected else []
        is_first = state.get("is_first_playthrough", False)

        endings = realm_config.get("endings", {})

        # 按优先级排序，选择最高优先级的结局
        sorted_endings = sorted(endings.items(), key=lambda x: x[1].get("priority", 99))

        chosen_ending = None
        for ending_key, ending_config in sorted_endings:
            condition = ending_config.get("condition", "")

            if condition == "all_clues_and_survived":
                total_clues = len(realm_config.get("clues", []))
                # 检查全局线索
                clears: Dict[str, Any] = {}
                if hasattr(player, 'inner_realm_clears') and player.inner_realm_clears:
                    try:
                        clears = json.loads(player.inner_realm_clears)
                    except (json.JSONDecodeError, TypeError):
                        clears = {}
                global_clues = clears.get(session.realm_name, {}).get("clues_found", [])
                if len(global_clues) >= total_clues:
                    chosen_ending = ending_config
                    break

            elif condition == "all_humans_killed_and_survived":
                required_kills = ending_config.get("required_kills", [])
                all_killed = all(
                    not npc_states.get(npc_id, {}).get("alive", True)
                    for npc_id in required_kills
                )
                if all_killed and session.killed_count >= len(required_kills):
                    chosen_ending = ending_config
                    break

            elif condition == "reached_dawn":
                if session.current_scene == "town_entrance_dawn":
                    chosen_ending = ending_config
                    break

        # 默认结局
        if not chosen_ending:
            chosen_ending = endings.get("dawn_survivor", list(endings.values())[0])

        # 发放奖励
        multiplier = chosen_ending.get("reward_multiplier", 1.0)
        reward_desc = "无"

        if multiplier > 0:
            reward_desc = await self._deliver_rewards(player, session, multiplier)

            # 额外奖励
            for bonus in chosen_ending.get("bonus_items", []):
                item_id = bonus.get("id", "")
                qty = bonus.get("qty", 1)
                from ..item.inventory import add_item_to_inventory
                await add_item_to_inventory(self.uow.session, player, item_id, qty)
                from ..config import config as game_config
                item_config = game_config.items_config["by_id"].get(item_id)
                item_name = item_config.name if item_config else item_id
                reward_desc += f"\n🎁 额外：{item_name} x{qty}"

            # 首次通关额外奖励
            if is_first and chosen_ending.get("first_clear_bonus"):
                fc_bonus = chosen_ending["first_clear_bonus"]
                fc_gold = fc_bonus.get("gold", 0)
                if fc_gold > 0:
                    player.gold += fc_gold
                    reward_desc += f"\n🏆 首通金币：{fc_gold}"
                for fc_item in fc_bonus.get("items", []):
                    item_id = fc_item.get("id", "")
                    qty = fc_item.get("qty", 1)
                    from ..item.inventory import add_item_to_inventory
                    await add_item_to_inventory(self.uow.session, player, item_id, qty)
                    from ..config import config as game_config
                    item_config = game_config.items_config["by_id"].get(item_id)
                    item_name = item_config.name if item_config else item_id
                    reward_desc += f"\n🏆 首通：{item_name} x{qty}"

                # 标记已通关
                clears = {}
                if hasattr(player, 'inner_realm_clears') and player.inner_realm_clears:
                    try:
                        clears = json.loads(player.inner_realm_clears)
                    except (json.JSONDecodeError, TypeError):
                        clears = {}
                if session.realm_name not in clears:
                    clears[session.realm_name] = {}
                clears[session.realm_name]["cleared"] = True
                player.inner_realm_clears = json.dumps(clears, ensure_ascii=False)

        # 清理会话
        session.is_settled = True
        player.inner_realm = None
        await self.uow.commit()

        return {
            "display_name": f"{chosen_ending.get('icon', '🎬')} {chosen_ending['display_name']}",
            "description": chosen_ending.get("description", ""),
            "reward_desc": reward_desc,
        }

    # ==================== 特殊事件选择 ====================

    async def resolve_special_event(
        self,
        player: Player,
        session: InnerRealmSession,
        choice_text: str
    ) -> Tuple[bool, str]:
        """处理特殊事件中的选择"""
        engine = self._get_scene_engine(session.realm_name)
        scene = engine.get_current_scene(session)
        if not scene:
            return False, "⛔ 当前位置异常"

        state = json.loads(session.state) if session.state else {}
        pending_event = state.get("pending_event")
        if not pending_event:
            return False, "⛔ 当前没有待处理的事件"

        choices = pending_event.get("choices", [])
        chosen = None
        for c in choices:
            if c.get("label", "") == choice_text or c.get("id", "") == choice_text:
                chosen = c
                break

        if not chosen:
            labels = [c.get("label", "") for c in choices]
            return False, f"⛔ 无效选择\n可选: {' | '.join(labels)}"

        # 处理选择结果
        lines = [chosen.get("text", "")]

        # 理智变化
        sanity_change = chosen.get("sanity_change", 0)
        if sanity_change != 0:
            await self.modify_sanity(session, sanity_change, "事件选择")
            lines.append(f"\n🧠 理智 {sanity_change:+d}")

        # 死亡结果
        if chosen.get("result") == "death":
            await self._handle_death(player, session, "event_choice")
            lines.append("\n💀 试炼失败")

        # 自动移动
        auto_move = chosen.get("auto_move_to")
        if auto_move:
            scene_text = engine.enter_scene(session, auto_move, state.get("is_first_playthrough", False))
            lines.append(f"\n{scene_text}")

        # 发放道具
        grant_item = chosen.get("grant_item")
        if grant_item:
            item_id = grant_item.get("id", "")
            qty = grant_item.get("qty", 1)
            await self._add_pending_reward(session, item_id=item_id, qty=qty)
            from ..config import config as game_config
            item_config = game_config.items_config["by_id"].get(item_id)
            item_name = item_config.name if item_config else item_id
            lines.append(f"\n📦 获得：{item_name} x{qty}")

        # 清除待处理事件
        state.pop("pending_event", None)
        session.state = json.dumps(state, ensure_ascii=False)
        await self.uow.commit()

        return True, "\n".join(lines)

    # ==================== 内部辅助方法 ====================

    def _find_npc_in_scene(
        self,
        session: InnerRealmSession,
        scene,
        npc_name: str = None
    ):
        """在场景中查找NPC"""
        realm_config = InnerRealmConfig.get_realm_config(session.realm_name)
        all_npcs = {n["id"]: n for n in realm_config.get("npcs", [])}

        for npc_id in scene.npcs:
            npc = all_npcs.get(npc_id)
            if not npc:
                continue
            if npc_name and npc_name not in npc.get("name", ""):
                continue
            return npc

        # 如果没指定名字，返回第一个
        if not npc_name and scene.npcs:
            first_id = scene.npcs[0]
            return all_npcs.get(first_id)

        return None

    async def _handle_death(self, player: Player, session: InnerRealmSession, cause: str):
        """处理玩家死亡"""
        session.is_settled = True
        player.inner_realm = None

        state = json.loads(session.state) if session.state else {}
        state["death_cause"] = cause
        session.state = json.dumps(state, ensure_ascii=False)

        await self.uow.commit()

    async def _add_pending_reward(self, session: InnerRealmSession, item_id=None, qty=0, gold=0):
        """记录待发放奖励"""
        state = json.loads(session.state) if session.state else {}
        pending = state.get("pending_rewards", {"items": [], "gold": 0})

        if item_id and qty > 0:
            # 检查是否已有同类物品，合并数量
            found = False
            for item in pending["items"]:
                if item["id"] == item_id:
                    item["qty"] += qty
                    found = True
                    break
            if not found:
                pending["items"].append({"id": item_id, "qty": qty})

        if gold > 0:
            pending["gold"] += gold

        state["pending_rewards"] = pending
        session.state = json.dumps(state, ensure_ascii=False)

    async def _deliver_rewards(self, player: Player, session: InnerRealmSession, multiplier: float) -> str:
        """存活结算时发放奖励"""
        state = json.loads(session.state) if session.state else {}
        pending = state.get("pending_rewards", {"items": [], "gold": 0})

        lines = []

        # 发放金币
        gold = int(pending.get("gold", 0) * multiplier)
        if gold > 0:
            player.gold += gold
            lines.append(f"💰 金币: {gold} (x{multiplier})")

        # 发放物品
        from ..item.inventory import add_item_to_inventory
        from ..config import config as game_config

        for item_info in pending.get("items", []):
            item_id = item_info.get("id", "")
            qty = int(item_info.get("qty", 0) * multiplier)
            if qty <= 0:
                continue
            await add_item_to_inventory(self.uow.session, player, item_id, qty)
            item_config = game_config.items_config["by_id"].get(item_id)
            item_name = item_config.name if item_config else item_id
            lines.append(f"📦 {item_name} x{qty}")

        return "\n".join(lines) if lines else "无"

    async def _save_clue_globally(self, player: Player, realm_name: str, clue_id: str):
        """将线索保存到玩家全局记录"""
        clears: Dict[str, Any] = {}
        if hasattr(player, 'inner_realm_clears') and player.inner_realm_clears:
            try:
                clears = json.loads(player.inner_realm_clears)
            except (json.JSONDecodeError, TypeError):
                clears = {}

        if realm_name not in clears:
            clears[realm_name] = {"cleared": False, "clues_found": []}

        clues = clears[realm_name].get("clues_found", [])
        if clue_id not in clues:
            clues.append(clue_id)
            clears[realm_name]["clues_found"] = clues
            player.inner_realm_clears = json.dumps(clears, ensure_ascii=False)

    def _sanity_collapse_text(self) -> str:
        """理智崩溃文本"""
        return (
            "你蹲在地上，双手抱头。周围的一切都在旋转——\n"
            "墙壁在呼吸，地板在蠕动，天花板上的裂缝组成了一张笑脸。\n"
            "你发出一声大笑，然后什么都不记得了。\n"
            "━━━━━━━━━━━━━\n"
            "🧠 理智崩溃 · 试炼失败"
        )

    async def check_sanity_zero(self, player: Player, session: InnerRealmSession) -> bool:
        """检查理智是否归零，如果归零则处理死亡"""
        if session.sanity <= 0:
            await self._handle_death(player, session, "sanity_zero")
            return True
        return False
