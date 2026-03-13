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

    # EMPTY 地块随机遭遇文本池（按理智分级）
    EMPTY_ENCOUNTERS = {
        "high": [  # 理智 > 50
            "走廊尽头传来若有若无的脚步声...",
            "你看到墙上有一道奇怪的划痕",
            "天花板上的灯管闪烁了一下",
            "风从不知道哪里吹来，带着消毒水的味道",
            "地板上有一串干涸的脚印，延伸向远处",
            "你踩到了什么东西——是一颗掉落的纽扣",
            "墙上的挂钟还在走动。但秒针每走一格都要停顿两秒",
            "护士站签到表上最后一个日期是三年前。但墨水看起来是湿的",
            "走廊里的饮水机发出咕噜声，水箱里还有大半桶水。这不应该",
            "你经过一间病房，七张床七个枕头上都有凹陷的头印",
        ],
        "medium": [  # 理智 30-50
            "你确信刚才有人在你身后，但转身后什么也没有...",
            "墙壁上的涂鸦似乎在变化...",
            "远处传来金属碰撞的声音，像是有人在拖拽什么",
            "你闻到一股若有若无的血腥味...",
            "走廊的灯光突然变成了暗红色，几秒后恢复正常",
            "你的影子似乎比平时更长了...",
            "广播系统突然播报：'三号病房的患者请回到床位。' 声音听起来像是你自己的",
            "你数了一下走廊两侧的门——去的时候十二扇，回来的时候变成了十三扇",
            "有人在护士站留了一杯咖啡。杯壁是温热的。但这层楼除了你没有活人",
            "地板上的脚印突然中断了。你低头看了看自己的脚——你也没有留下脚印",
        ],
        "low": [  # 理智 < 30
            "地面在你脚下蠕动...",
            "你听到了自己的名字，但声音是从你体内传来的...",
            "墙壁开始流血...不，那只是生锈的水管...",
            "你看到了另一个自己站在走廊尽头，对你微笑...",
            "天花板上的裂缝组成了一张脸，正在对你说话...",
            "你的手指开始变得透明...摇了摇头，恢复了正常",
            "你发现手术台上躺着的人穿着跟你一模一样的衣服。你没有走近去看脸",
            "手机显示一条未读消息：'别回头。' 发送者是你自己，发送时间是明天",
            "你走过一面镜子，镜子里的你没有跟着走。它站在原地，慢慢转过头来看着你",
            "电梯门开了，里面站满了人，全都面朝墙壁。你按下关门键，电梯开始下行——但这栋楼没有地下室",
        ],
    }

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

    def roll_2d6(self, attribute_modifier: int = 0, time_bonus: int = 0, session: InnerRealmSession = None) -> DiceRollResult:
        """
        执行2D6骰子判定

        Args:
            attribute_modifier: 属性修正值
            time_bonus: 时间加成
            session: 会话对象（可选，用于检查身份混淆）

        Returns:
            骰子判定结果
        """
        # 投掷两个D6骰子
        dice1 = random.randint(1, 6)
        dice2 = random.randint(1, 6)
        base_total = dice1 + dice2

        # 身份混淆惩罚：-3
        identity_penalty = 0
        if session:
            state = json.loads(session.state) if session.state else {}
            if state.get("identity_confused") and state.get("identity_confusion_uses", 0) > 0:
                identity_penalty = -3
                state["identity_confusion_uses"] -= 1
                if state["identity_confusion_uses"] <= 0:
                    state["identity_confused"] = False
                    del state["identity_confusion_uses"]
                session.state = json.dumps(state, ensure_ascii=False)

        # 计算最终结果
        final_total = base_total + attribute_modifier + time_bonus + identity_penalty

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

    def get_time_bonus(self, action_type: str, session: InnerRealmSession = None) -> int:
        """
        获取当前时间的加成

        Args:
            action_type: 行动类型
            session: 会话对象（可选，用于检查时间错乱）

        Returns:
            时间加成值
        """
        time_config = InnerRealmConfig.get_time_system_config()
        current_hour = datetime.now().hour

        # 时间错乱效果：反转时间加成
        time_dilated = False
        if session:
            state = json.loads(session.state) if session.state else {}
            time_dilated = state.get("time_dilated", False)

        # 收集所有时段的加成
        day_bonus = 0
        night_bonus = 0

        for period_name, period_config in time_config.items():
            bonuses = period_config.get("bonuses", {})
            if action_type == "search":
                bonus_val = bonuses.get("search", 0)
            elif action_type in ["intimidate", "assassination"]:
                bonus_val = bonuses.get("combat", 0)
            else:
                bonus_val = 0

            if period_name == "day":
                day_bonus = bonus_val
            elif period_name == "night":
                night_bonus = bonus_val

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

                # 时间错乱：反转加成（白天给夜晚bonus，夜晚给白天bonus）
                if time_dilated and bonus != 0:
                    if period_name == "day":
                        return night_bonus
                    elif period_name == "night":
                        return day_bonus

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

    # ==================== 里界管理 ====================

    async def check_and_refresh_session(self, session: InnerRealmSession):
        """
        检查并执行每日刷新（被动检查模式）。
        比较 session.last_refresh 与今天日期，跨天则重置可重复资源。

        Args:
            session: 会话对象
        """
        from datetime import date

        last_date = session.last_refresh.date() if session.last_refresh else None
        today = date.today()

        if last_date and last_date >= today:
            return  # 今天已刷新过

        logger.info(f"会话 {session.id} 跨天刷新: {last_date} -> {today}")

        # 获取该会话的所有地块
        from sqlalchemy import select
        stmt = select(InnerRealmTile).where(InnerRealmTile.session_id == session.id)
        result = await self.uow.session.execute(stmt)
        tiles = result.scalars().all()

        refreshed_count = 0
        for tile in tiles:
            tile_state = json.loads(tile.state) if tile.state else {}

            if tile.event_type == "LOOT" and tile_state.get("looted"):
                # 重置 LOOT 地块
                tile_state["looted"] = False
                tile.state = json.dumps(tile_state, ensure_ascii=False)
                tile.is_triggered = False
                refreshed_count += 1

            elif tile.event_type == "NPC" and not tile_state.get("alive", True):
                # 复活 NPC
                tile_state["alive"] = True
                tile_state["hp"] = tile_state.get("max_hp", 100)
                tile.state = json.dumps(tile_state, ensure_ascii=False)
                tile.is_triggered = False
                refreshed_count += 1

            elif tile.event_type == "SURVIVOR":
                if tile_state.get("saved") or tile_state.get("killed"):
                    # 重置幸存者
                    tile_state["saved"] = False
                    tile_state["killed"] = False
                    tile.state = json.dumps(tile_state, ensure_ascii=False)
                    tile.is_triggered = False
                    refreshed_count += 1

            elif tile.event_type == "COGNITION_TAMPER" and tile_state.get("triggered"):
                # 重置认知篡改触发点
                tile_state["triggered"] = False
                tile.state = json.dumps(tile_state, ensure_ascii=False)
                tile.is_triggered = False
                refreshed_count += 1

            # 注意：CLUE 和 BOSS 不重置（保留进度）

        # 更新刷新时间
        session.last_refresh = datetime.now()

        # 清除冷却记录和认知篡改状态
        state = json.loads(session.state) if session.state else {}
        state.pop("last_action_time", None)
        # 清除所有认知篡改标记
        for key in ["phantom_npc_active", "memory_altered",
                     "sensory_distorted", "sensory_remaining_steps",
                     "time_dilated", "time_dilation_remaining_steps",
                     "identity_confused", "identity_confusion_uses",
                     "truth_inverted", "truth_inversion_remaining_steps",
                     "tamper_cooldown",
                     "pending_special_event", "triggered_special_events"]:
            state.pop(key, None)
        session.state = json.dumps(state, ensure_ascii=False)

        await self.uow.commit()
        logger.info(f"会话 {session.id} 刷新完成，重置了 {refreshed_count} 个地块")

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
            # 检查每日刷新
            await self.check_and_refresh_session(existing_session)
            return True, f"📍 你已经在 {realm_config['display_name']} 中了", existing_session

        # 清理已结算的旧会话（唯一索引 player_id+realm_name 不含 is_settled）
        from sqlalchemy import select, and_
        stmt = select(InnerRealmSession).where(
            and_(
                InnerRealmSession.player_id == player.id,
                InnerRealmSession.realm_name == realm_name,
                InnerRealmSession.is_settled == True
            )
        )
        result = await self.uow.session.execute(stmt)
        old_sessions = result.scalars().all()
        for old_session in old_sessions:
            await self.uow.session.delete(old_session)
        if old_sessions:
            await self.uow.session.flush()

        # 获取初始理智值
        sanity_config = InnerRealmConfig.get_global_config().get("sanity_system", {})
        initial_sanity = sanity_config.get("initial_sanity", 100)

        # 创建新会话
        # 初始化state，包含已访问坐标集合
        initial_state = {"visited": ["0,0"]}

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
            state=json.dumps(initial_state, ensure_ascii=False),
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

        # 创建事件类型池（排除 BOSS，BOSS 单独放置）
        event_pool = []
        for event_type, weight in event_weights.items():
            if event_type == "BOSS":
                continue  # BOSS 不进入随机池
            event_pool.extend([event_type] * weight)

        # BOSS 固定生成在远角区域 (18-24, 18-24)
        boss_x = random.randint(18, min(24, map_size - 1))
        boss_y = random.randint(18, min(24, map_size - 1))

        # 将 BOSS 坐标存入 session state 以供线索引导使用
        state = json.loads(session.state) if session.state else {}
        state["boss_position"] = {"x": boss_x, "y": boss_y}
        session.state = json.dumps(state, ensure_ascii=False)

        tiles = []

        for x in range(map_size):
            for y in range(map_size):
                # 起点固定为EMPTY
                if x == 0 and y == 0:
                    event_type = "EMPTY"
                    state_data = {}
                # BOSS 固定位置
                elif x == boss_x and y == boss_y:
                    event_type = "BOSS"
                    state_data = self._generate_event_data(event_type, realm_config)
                else:
                    event_type = random.choice(event_pool)
                    state_data = self._generate_event_data(event_type, realm_config)

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

        logger.info(f"为会话 {session.id} 生成了 {len(tiles)} 个地块，BOSS位置: ({boss_x}, {boss_y})")

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
            # 根据里界等级和位置生成不同品质的物品
            items = []

            # 基础奖励：金币
            gold_amount = random.randint(100, 300)

            # 随机材料奖励（1-2个）- 仅使用里界专属物品
            material_pool = [
                {"item_id": "broken_id", "quantity": random.randint(1, 3), "probability": 0.8},  # 白色 - 破损证件
                {"item_id": "stained_infusion_bag", "quantity": 1, "probability": 0.5},  # 绿色 - 污染绷带（里界材料）
                {"item_id": "scalpel", "quantity": 1, "probability": 0.6},  # 绿色 - 手术刀（里界专属）
                {"item_id": "visitor_pass", "quantity": 1, "probability": 0.4},  # 绿色 - 访客通行证
            ]

            # 稀有材料（低概率）- 仅使用里界专属物品
            rare_pool = [
                {"item_id": "discolored_meal_tray", "quantity": 1, "probability": 0.2},  # 蓝色 - 扭曲血肉（里界专属）
                {"item_id": "cracked_specimen_jar", "quantity": 1, "probability": 0.15},  # 紫色 - 腐化之心（里界专属）
                {"item_id": "medical_record_key", "quantity": 1, "probability": 0.1},  # 蓝色 - 病历室钥匙
                {"item_id": "surgery_notes", "quantity": 1, "probability": 0.08},  # 蓝色 - 手术笔记
            ]

            # 添加金币奖励
            items.append({"gold": gold_amount})

            # 添加1-2个普通材料
            selected_materials = random.sample(material_pool, k=min(2, len(material_pool)))
            items.extend(selected_materials)

            # 有概率添加稀有材料
            if random.random() < 0.3:  # 30%概率
                rare_item = random.choice(rare_pool)
                items.append(rare_item)

            return {
                "looted": False,
                "items": items
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

        # 检查移动冷却
        can_act, remaining = self.check_action_cooldown(session, "move")
        if not can_act:
            return False, f"⏳ 移动冷却中，还需等待 {remaining} 秒"

        # 更新位置
        session.x = new_x
        session.y = new_y

        # 追踪已访问坐标
        state = json.loads(session.state) if session.state else {}
        visited = set(state.get("visited", []))
        visited.add(f"{new_x},{new_y}")
        state["visited"] = list(visited)

        # 认知篡改步数递减
        # 感官扭曲递减
        if state.get("sensory_distorted") and "sensory_remaining_steps" in state:
            state["sensory_remaining_steps"] -= 1
            if state["sensory_remaining_steps"] <= 0:
                state["sensory_distorted"] = False
                del state["sensory_remaining_steps"]
        # 时间错乱递减
        if state.get("time_dilated") and "time_dilation_remaining_steps" in state:
            state["time_dilation_remaining_steps"] -= 1
            if state["time_dilation_remaining_steps"] <= 0:
                state["time_dilated"] = False
                del state["time_dilation_remaining_steps"]
        # 真相反转消退
        if state.get("truth_inverted") and "truth_inversion_remaining_steps" in state:
            state["truth_inversion_remaining_steps"] -= 1
            if state["truth_inversion_remaining_steps"] <= 0:
                state["truth_inverted"] = False
                del state["truth_inversion_remaining_steps"]
        # 认知篡改触发冷却递减
        if state.get("tamper_cooldown", 0) > 0:
            state["tamper_cooldown"] -= 1

        session.state = json.dumps(state, ensure_ascii=False)

        # 更新移动冷却
        await self.update_action_cooldown(session, "move")

        await self.uow.commit()

        # 获取新位置的地块信息
        tile = await self.get_current_tile(session)
        if not tile:
            return True, f"📍 移动到 ({new_x}, {new_y})"

        # 根据事件类型返回提示
        # 感官扭曲效果：交换事件类型显示
        display_event_type = tile.event_type
        session_state_check = json.loads(session.state) if session.state else {}
        if session_state_check.get("sensory_distorted"):
            swap_map = {
                "LOOT": "CLUE", "CLUE": "LOOT",
                "NPC": "EMPTY", "EMPTY": "NPC",
                "SURVIVOR": "LOOT",
            }
            display_event_type = swap_map.get(tile.event_type, tile.event_type)

        event_desc = {
            "NPC": "你发现了一个人影...",
            "LOOT": "这里似乎有什么东西...",
            "CLUE": "你注意到了一些可疑的痕迹...",
            "BOSS": "⚠️ 一股强大的压迫感袭来！",
            "SURVIVOR": "你听到了微弱的呼救声..."
        }.get(display_event_type, "...")

        # EMPTY 地块 30% 概率触发随机氛围文本
        if tile.event_type == "EMPTY":
            # 幻影 NPC 效果：EMPTY 伪装成 NPC
            if session_state_check.get("phantom_npc_active"):
                event_desc = "你发现了一个人影..."
            elif random.random() < 0.3:
                if session.sanity < 30:
                    tier = "low"
                elif session.sanity < 50:
                    tier = "medium"
                else:
                    tier = "high"
                event_desc = random.choice(self.EMPTY_ENCOUNTERS[tier])
            else:
                event_desc = "这里一片寂静..."

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
        # 理智雪崩保护：理智为0时不再触发新篡改
        if session.sanity <= 0:
            return None

        state = json.loads(session.state) if session.state else {}

        # 触发冷却检查
        if state.get("tamper_cooldown", 0) > 0:
            return None

        # 统计当前已激活的篡改效果数量，最多同时2种
        active_tamper_count = 0
        active_tamper_ids = set()
        if state.get("phantom_npc_active"):
            active_tamper_count += 1
            active_tamper_ids.add("phantom_npc")
        if state.get("memory_altered"):
            active_tamper_count += 1
            active_tamper_ids.add("memory_alteration")
        if state.get("sensory_distorted"):
            active_tamper_count += 1
            active_tamper_ids.add("sensory_distortion")
        if state.get("time_dilated"):
            active_tamper_count += 1
            active_tamper_ids.add("time_dilation")
        if state.get("identity_confused"):
            active_tamper_count += 1
            active_tamper_ids.add("identity_confusion")
        if state.get("truth_inverted"):
            active_tamper_count += 1
            active_tamper_ids.add("truth_inversion")

        if active_tamper_count >= 2:
            return None

        cognition_config = InnerRealmConfig.get_global_config().get("cognition_tamper_system", {})
        tamper_types = cognition_config.get("tamper_types", {})

        # 根据理智值过滤可触发的篡改
        available_tampers = []
        for tamper_id, tamper_config in tamper_types.items():
            # 跳过已激活的同类型篡改
            if tamper_id in active_tamper_ids:
                continue

            # 检查是否是极度危险的篡改（只在理智<30时触发）
            is_critical = tamper_config.get("critical", False)
            if is_critical and session.sanity >= 30:
                continue

            # 检查触发概率
            trigger_chance = tamper_config.get("trigger_chance", 0)

            # 理智值越低，触发概率越高（降低倍率防止雪崩）
            sanity_multiplier = 1.0
            if session.sanity < 30:
                sanity_multiplier = 1.8
            elif session.sanity < 50:
                sanity_multiplier = 1.3

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
            # 标记感官扭曲，持续5步
            state["sensory_distorted"] = True
            state["sensory_remaining_steps"] = 5

        elif tamper_id == "time_dilation":
            # 标记时间错乱，持续3步
            state["time_dilated"] = True
            state["time_dilation_remaining_steps"] = 3

        elif tamper_id == "identity_confusion":
            # 身份混淆（最恐怖）- 下一次判定骰子 -3
            state["identity_confused"] = True
            state["identity_confusion_uses"] = 1  # 使用一次后消失

        elif tamper_id == "truth_inversion":
            # 真相反转（增加消退步数）
            state["truth_inverted"] = True
            state["truth_inversion_remaining_steps"] = 10

        # 设置触发冷却（3步内不再触发新篡改）
        state["tamper_cooldown"] = 3

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

    # ==================== 特殊事件系统 ====================

    async def check_special_event(
        self,
        session: InnerRealmSession,
        tile: InnerRealmTile
    ) -> Optional[Dict[str, Any]]:
        """
        检查EMPTY地块是否触发特殊事件

        Args:
            session: 会话对象
            tile: 当前地块

        Returns:
            触发的特殊事件配置，未触发返回None
        """
        # 只在EMPTY地块触发
        if tile.event_type != "EMPTY":
            return None

        # 获取里界配置
        realm_config = InnerRealmConfig.get_realm_config(session.realm_name)
        if not realm_config:
            return None

        special_events = realm_config.get("special_events", [])
        if not special_events:
            return None

        state = json.loads(session.state) if session.state else {}
        triggered_events = state.get("triggered_special_events", [])

        for event in special_events:
            event_id = event["id"]

            # once_per_session 检查
            if event.get("once_per_session", True) and event_id in triggered_events:
                continue

            # 理智阈值检查
            sanity_threshold = event.get("sanity_threshold", 999)
            if session.sanity >= sanity_threshold:
                continue

            # 概率触发
            trigger_chance = event.get("trigger_chance", 0)
            if random.random() < trigger_chance:
                return event

        return None

    async def present_special_event(
        self,
        session: InnerRealmSession,
        event: Dict[str, Any]
    ) -> str:
        """
        展示特殊事件描述和选项，将待处理事件存入session.state

        Args:
            session: 会话对象
            event: 事件配置

        Returns:
            事件描述和选项提示文本
        """
        state = json.loads(session.state) if session.state else {}
        state["pending_special_event"] = event["id"]
        session.state = json.dumps(state, ensure_ascii=False)
        await self.uow.commit()

        lines = [
            "━━━━━━━━━━━━━",
            f"🔮 {event['name']}",
            "━━━━━━━━━━━━━",
            event.get("description", ""),
            "",
            "你要怎么做？"
        ]

        for choice in event.get("choices", []):
            lines.append(f"  ▸ 【选择 {choice['label']}】")

        return "\n".join(lines)

    async def resolve_special_event(
        self,
        player: Player,
        session: InnerRealmSession,
        choice_label: str
    ) -> Tuple[bool, str]:
        """
        解析特殊事件选择，应用效果

        Args:
            player: 玩家对象
            session: 会话对象
            choice_label: 玩家选择的标签

        Returns:
            (成功与否, 结果描述)
        """
        state = json.loads(session.state) if session.state else {}
        pending_event_id = state.get("pending_special_event")

        if not pending_event_id:
            return False, "⛔ 当前没有待处理的事件"

        # 获取事件配置
        realm_config = InnerRealmConfig.get_realm_config(session.realm_name)
        if not realm_config:
            return False, "⛔ 配置错误"

        special_events = realm_config.get("special_events", [])
        event = None
        for e in special_events:
            if e["id"] == pending_event_id:
                event = e
                break

        if not event:
            return False, "⛔ 事件不存在"

        # 查找匹配的选项
        matched_choice = None
        for choice in event.get("choices", []):
            if choice["label"] == choice_label:
                matched_choice = choice
                break

        if not matched_choice:
            available = "、".join([c["label"] for c in event.get("choices", [])])
            return False, f"⛔ 无效选择，可选项：{available}"

        # 清除pending状态
        del state["pending_special_event"]

        # 记录已触发事件
        triggered_events = state.get("triggered_special_events", [])
        if pending_event_id not in triggered_events:
            triggered_events.append(pending_event_id)
            state["triggered_special_events"] = triggered_events

        # 应用理智变化
        sanity_change = matched_choice.get("sanity_change", 0)
        if sanity_change != 0:
            await self.modify_sanity(session, sanity_change, f"特殊事件：{event['name']}")

        # 应用认知篡改效果
        effect = matched_choice.get("effect")
        if effect:
            if effect == "identity_confusion":
                state["identity_confused"] = True
                state["identity_confusion_uses"] = 1

        # 应用物品奖励
        item_desc = ""
        item_reward_id = matched_choice.get("item_reward")
        if item_reward_id:
            from ..models.inventory import ItemInstance
            from ..config import config

            item_data = config.get_item_by_id(item_reward_id)
            if item_data:
                item_instance = ItemInstance(
                    player_id=player.id,
                    item_id=item_reward_id,
                    quantity=1,
                    is_equipped=False
                )
                self.uow.session.add(item_instance)
                item_desc = f"\n📦 获得：{item_data.get('name', item_reward_id)} x1"

        # 应用额外线索
        clue_desc = ""
        bonus_clue = matched_choice.get("bonus_clue")
        if bonus_clue:
            clue_collected = json.loads(session.clue_collected) if session.clue_collected else []
            if bonus_clue not in clue_collected:
                clue_collected.append(bonus_clue)
                session.clue_collected = json.dumps(clue_collected, ensure_ascii=False)
                # 查找线索名称
                clues = realm_config.get("clues", [])
                clue_name = bonus_clue
                for c in clues:
                    if c["id"] == bonus_clue:
                        clue_name = c["name"]
                        break
                clue_desc = f"\n🔍 发现线索：{clue_name}"

        session.state = json.dumps(state, ensure_ascii=False)
        await self.uow.commit()

        # 构建结果消息
        result_text = matched_choice.get("text", "...")
        sanity_text = ""
        if sanity_change > 0:
            sanity_text = f"\n💚 理智 +{sanity_change}"
        elif sanity_change < 0:
            sanity_text = f"\n💔 理智 {sanity_change}"

        lines = [
            "━━━━━━━━━━━━━",
            f"🔮 {event['name']} — {matched_choice['label']}",
            "━━━━━━━━━━━━━",
            result_text,
            sanity_text,
            item_desc,
            clue_desc
        ]

        return True, "\n".join([l for l in lines if l])

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

        # 发放结局奖励
        if matched_ending:
            ending_key, ending_config = matched_ending
            rewards_config = ending_config.get("rewards", [])
            reward_desc, total_gold, items_obtained = await self._distribute_loot(
                player, rewards_config, multiplier=1.0
            )
        else:
            ending_key = "default"
            reward_desc, total_gold, items_obtained = "无", 0, []

        # 标记会话已结算
        session.is_settled = True

        # 清空玩家的里界标记
        player.inner_realm = None
        self.uow.session.add(player)

        await self.uow.commit()

        if matched_ending:
            return {
                "ending_key": ending_key,
                "display_name": ending_config.get("display_name", "未知结局"),
                "description": ending_config.get("description", ""),
                "reward_desc": reward_desc,
            }
        else:
            # 默认结局
            return {
                "ending_key": "default",
                "display_name": "离开",
                "description": "你离开了这个诡异的地方...",
                "reward_desc": reward_desc,
            }

    # ==================== 奖励发放系统 ====================

    async def _distribute_loot(
        self,
        player: Player,
        loot_config: list,
        multiplier: float = 1.0
    ) -> Tuple[str, int, list]:
        """
        发放奖励物品和金币

        Args:
            player: 玩家对象
            loot_config: 奖励配置列表，格式：[{"item_id": "xxx", "quantity": 1, "probability": 0.5}, {"gold": 100}]
            multiplier: 奖励倍数（大成功时使用）

        Returns:
            (奖励描述文本, 金币总计, 物品列表)
        """
        from ..models.inventory import ItemInstance
        from ..config import config

        rewards_text = []
        total_gold = 0
        items_obtained = []

        for reward in loot_config:
            # 检查概率
            probability = reward.get("probability", 1.0)
            if random.random() > probability:
                continue

            # 金币奖励
            if "gold" in reward:
                gold_amount = int(reward["gold"] * multiplier)
                player.gold += gold_amount
                total_gold += gold_amount
                rewards_text.append(f"💰 {gold_amount} 金币")

                # 更新财富成就统计
                from ..achievement.achievement_service import AchievementService
                await AchievementService.update_stat(
                    self.uow.session,
                    player.id,
                    "gold_earned_total",
                    increment=gold_amount,
                    auto_commit=False
                )

            # 物品奖励
            elif "item_id" in reward:
                item_id = reward["item_id"]
                quantity = int(reward.get("quantity", 1) * multiplier)

                # 检查物品是否存在
                item_config = config.items_config["by_id"].get(item_id)
                if not item_config:
                    logger.warning(f"奖励物品不存在: {item_id}")
                    continue

                try:
                    # 添加物品到背包
                    await ItemInstance.add_item(self.uow.session, player.id, item_id, quantity)
                    items_obtained.append({"item_id": item_id, "quantity": quantity})

                    # 格式化物品名称（带稀有度标识）
                    item_display_name = item_config.get_display_name()
                    rewards_text.append(f"📦 {item_display_name} x{quantity}")

                except ValueError as e:
                    # 背包满了，记录但不阻止流程
                    logger.warning(f"发放奖励失败（背包满）: {item_id} x{quantity}")
                    rewards_text.append(f"⚠️ 背包已满，无法获得 {item_config.name} x{quantity}")

        # 保存玩家数据变更
        self.uow.session.add(player)

        reward_desc = "\n".join(rewards_text) if rewards_text else "什么也没得到..."
        return reward_desc, total_gold, items_obtained

    # ==================== 战斗系统集成 ====================

    async def start_battle_with_npc(
        self,
        player: Player,
        tile: InnerRealmTile,
        session: InnerRealmSession
    ) -> Tuple[bool, list[str], list[str], dict]:
        """
        与NPC/BOSS发起战斗

        Args:
            player: 玩家对象
            tile: 地块对象
            session: 里界会话

        Returns:
            (是否胜利, 战斗日志行列表, 结果行列表, 战斗奖励)
        """
        from ..battle.integration_helper import BattleIntegrationHelper
        import time

        state = json.loads(tile.state) if tile.state else {}

        # 获取敌人信息
        enemy_name = state.get("name", "未知敌人")
        enemy_hp = state.get("hp", 100)
        enemy_max_hp = state.get("max_hp", enemy_hp)
        enemy_attack = state.get("attack", 30)
        enemy_defense = state.get("defense", 10)
        enemy_agility = state.get("agility", 10)
        is_boss = tile.event_type == "BOSS"

        # 构建敌人属性
        monster_stats = {
            "hp": enemy_hp,
            "attack": enemy_attack,
            "defense": enemy_defense,
            "agility": enemy_agility
        }

        # 创建战斗种子
        battle_timestamp = int(time.time() * 1000)
        seed = f"InnerRealm_{session.id}:{tile.x}:{tile.y}:{battle_timestamp}"

        # 执行战斗
        victory, battle_log, damage_taken, post_effects = await BattleIntegrationHelper.enhanced_player_vs_monster_battle_v2(
            player, monster_stats, enemy_name, self.uow.session, seed=seed, max_rounds=30
        )

        # 更新玩家血量
        player.hp = max(0, player.hp - damage_taken)
        self.uow.session.add(player)

        # 构建战斗结果
        result_lines = []
        rewards = {}

        if victory:
            # 战斗胜利
            result_lines.extend([
                "━━━━━━━━━━━━━",
                "✅ 战斗胜利！",
                "━━━━━━━━━━━━━"
            ])

            # 标记敌人已死亡
            state["alive"] = False
            tile.state = json.dumps(state, ensure_ascii=False)
            tile.is_triggered = True

            # 增加击杀计数
            session.killed_count += 1

            # 发放战利品
            loot_items = state.get("loot", [])
            reward_desc, total_gold, items = await self._distribute_loot(
                player, loot_items, multiplier=1.0
            )
            rewards = {"description": reward_desc, "gold": total_gold, "items": items}

            if reward_desc != "什么也没得到...":
                result_lines.append(f"🎁 获得战利品：\n{reward_desc}")

            # BOSS击败额外处理
            if is_boss:
                state_obj = json.loads(session.state) if session.state else {}
                state_obj["boss_defeated"] = True
                session.state = json.dumps(state_obj, ensure_ascii=False)
                await self.trigger_sanity_recovery(session, "defeat_boss")
                result_lines.append("\n🏆 击败了核心BOSS！理智恢复+15")

        else:
            # 战斗失败
            result_lines.extend([
                "━━━━━━━━━━━━━",
                "💀 战斗失败...",
                f"💔 受到 {damage_taken} 点伤害",
                "━━━━━━━━━━━━━"
            ])

            # 理智损失
            if is_boss:
                await self.trigger_sanity_loss(session, "encounter_boss")
                result_lines.append("🧠 遭遇强大的诡异，理智严重受损...")

        await self.uow.commit()

        return victory, list(battle_log), list(result_lines), rewards

    # ==================== 事件触发系统（原有代码）====================

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
        # 检查搜刮冷却
        can_act, remaining = self.check_action_cooldown(session, "search")
        if not can_act:
            return False, f"⏳ 搜刮冷却中，还需等待 {remaining} 秒"

        # 幻影 NPC 检查：EMPTY 地块上操作时发现是幻觉
        if tile.event_type == "EMPTY":
            session_state = json.loads(session.state) if session.state else {}
            if session_state.get("phantom_npc_active"):
                session_state["phantom_npc_active"] = False
                session.state = json.dumps(session_state, ensure_ascii=False)
                await self.modify_sanity(session, -3, "幻影消散")
                await self.update_action_cooldown(session, "search")
                return False, "👻 你伸手触碰那个身影，但手穿过了它——那只是一个幻觉...\n🧠 理智 -3"

        # 检查地块类型
        if tile.event_type == "EMPTY":
            return False, "⛔ 这里一片荒芜，没有什么可以搜刮的..."

        if tile.event_type == "LOOT":
            state = json.loads(tile.state) if tile.state else {}
            if state.get("looted"):
                return False, "⛔ 这里已经被搜刮过了，什么都没剩下..."

            # 执行2D6+幸运判定
            modifier = self.calculate_attribute_modifier(player, "search")
            time_bonus = self.get_time_bonus("search", session)
            result = self.roll_2d6(modifier, time_bonus, session)

            # 根据判定结果给予奖励
            if result.result_level == "critical_failure":
                # 大失败：触发陷阱，损失理智
                await self.modify_sanity(session, -10, "搜刮触发陷阱")
                await self.update_action_cooldown(session, "search")
                return False, self.format_dice_roll_message(
                    "搜刮检定",
                    result,
                    "你触发了陷阱！一股黑雾涌出，侵蚀着你的理智... (理智-10)"
                )

            elif result.result_level == "failure":
                # 失败：没找到东西
                await self.update_action_cooldown(session, "search")
                return False, self.format_dice_roll_message(
                    "搜刮检定",
                    result,
                    "你翻遍了这里，但什么也没找到..."
                )

            else:
                # 成功：获得物品
                loot_items = state.get("items", [])

                # 大成功获得双倍奖励
                multiplier = 2.0 if result.result_level == "critical_success" else 1.0

                # 发放奖励
                reward_desc, total_gold, items = await self._distribute_loot(
                    player, loot_items, multiplier
                )

                # 标记为已搜刮
                state["looted"] = True
                tile.state = json.dumps(state, ensure_ascii=False)
                tile.is_triggered = True
                await self.update_action_cooldown(session, "search")
                await self.uow.commit()

                # 构建结果消息
                result_text = reward_desc if reward_desc != "什么也没得到..." else "你翻遍了这里，但什么也没找到..."
                if result.result_level == "critical_success" and reward_desc != "什么也没得到...":
                    result_text = f"🌟 大成功！发现了隐藏的宝箱！\n\n获得奖励（双倍）：\n{reward_desc}"
                elif reward_desc != "什么也没得到...":
                    result_text = f"获得奖励：\n{reward_desc}"

                return True, self.format_dice_roll_message(
                    "搜刮检定",
                    result,
                    result_text
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
        # 检查威吓冷却
        can_act, remaining = self.check_action_cooldown(session, "intimidate")
        if not can_act:
            return False, f"⏳ 威吓冷却中，还需等待 {remaining} 秒"

        # 幻影 NPC 检查
        if tile.event_type == "EMPTY":
            session_state = json.loads(session.state) if session.state else {}
            if session_state.get("phantom_npc_active"):
                session_state["phantom_npc_active"] = False
                session.state = json.dumps(session_state, ensure_ascii=False)
                await self.modify_sanity(session, -3, "幻影消散")
                await self.update_action_cooldown(session, "intimidate")
                return False, "👻 你对着那个身影大声呵斥，但它像烟雾一样消散了...\n🧠 理智 -3"

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
        time_bonus = self.get_time_bonus("intimidate", session)
        result = self.roll_2d6(modifier, time_bonus, session)

        if result.result_level == "critical_failure":
            # 大失败：目标逃跑或变异
            if target_type == "disguised":
                # 伪装者暴露真身并攻击 - 进入战斗
                reveal_desc = state.get("reveal_description", "目标突然暴露真身！")

                # 自动进入战斗
                battle_msg = self.format_dice_roll_message(
                    "威吓检定",
                    result,
                    f"{reveal_desc}\n⚠️ 战斗开始！"
                )

                # 发起战斗
                victory, log_lines, result_lines, rewards = await self.start_battle_with_npc(
                    player, tile, session
                )

                battle_result = "\n".join(log_lines + result_lines)
                return victory, f"{battle_msg}\n\n{battle_result}"
            else:
                # 普通NPC逃跑或惊动其他人
                威吓_fail = state.get("威吓_fail", f"{target_name}惊恐地逃走了，惊动了周围的其他人！")
                return False, self.format_dice_roll_message(
                    "威吓检定",
                    result,
                    威吓_fail
                )

        elif result.result_level == "failure":
            # 失败：目标拒绝，可能会攻击 - 进入战斗
            # 只有特殊NPC和伪装者会反击
            if target_type in ["special", "disguised"]:
                battle_msg = self.format_dice_roll_message(
                    "威吓检定",
                    result,
                    f"{target_name}没有被吓倒，开始反击！\n⚠️ 战斗开始！"
                )

                # 发起战斗
                victory, log_lines, result_lines, rewards = await self.start_battle_with_npc(
                    player, tile, session
                )

                battle_result = "\n".join(log_lines + result_lines)
                return victory, f"{battle_msg}\n\n{battle_result}"
            else:
                return False, self.format_dice_roll_message(
                    "威吓检定",
                    result,
                    f"{target_name}没有被吓倒，反而更加警惕了..."
                )

        else:
            # 成功：目标屈服，交出物品/信息
            威吓_success = state.get("威吓_success", f"{target_name}颤抖着交出了一些东西...")
            loot_items = state.get("loot", [])

            # 大成功获得双倍奖励
            multiplier = 2.0 if result.result_level == "critical_success" else 1.0

            # 发放奖励
            reward_desc, total_gold, items = await self._distribute_loot(
                player, loot_items, multiplier
            )

            # 标记为已威吓
            tile.is_triggered = True
            await self.update_action_cooldown(session, "intimidate")
            await self.uow.commit()

            # 构建结果消息
            result_text = 威吓_success
            if reward_desc != "什么也没得到...":
                if result.result_level == "critical_success":
                    result_text += f"\n\n🌟 大成功！获得双倍奖励：\n{reward_desc}"
                else:
                    result_text += f"\n\n获得：\n{reward_desc}"

            return True, self.format_dice_roll_message(
                "威吓检定",
                result,
                result_text
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
        # 检查处决冷却
        can_act, remaining = self.check_action_cooldown(session, "assassination")
        if not can_act:
            return False, f"⏳ 处决冷却中，还需等待 {remaining} 秒"

        # 幻影 NPC 检查
        if tile.event_type == "EMPTY":
            session_state = json.loads(session.state) if session.state else {}
            if session_state.get("phantom_npc_active"):
                session_state["phantom_npc_active"] = False
                session.state = json.dumps(session_state, ensure_ascii=False)
                await self.modify_sanity(session, -3, "幻影消散")
                await self.update_action_cooldown(session, "assassination")
                return False, "👻 你的刀刃划过那个身影——什么也没有切到，那只是虚无...\n🧠 理智 -3"

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
        time_bonus = self.get_time_bonus("assassination", session)
        result = self.roll_2d6(modifier, time_bonus, session)

        if result.result_level == "critical_failure":
            # 大失败：目标惨叫，惊动所有人
            await self.modify_sanity(session, -5, "处决失败")
            await self.update_action_cooldown(session, "assassination")
            return False, self.format_dice_roll_message(
                "处决检定",
                result,
                f"{target_name}发出了凄厉的惨叫，惊动了整个区域！(理智-5)\n⚠️ 所有附近的敌人都察觉到你了！"
            )

        elif result.result_level == "failure":
            # 失败：目标挣扎，进入战斗
            await self.update_action_cooldown(session, "assassination")
            battle_msg = self.format_dice_roll_message(
                "处决检定",
                result,
                f"{target_name}察觉到危险，开始挣扎！\n⚠️ 战斗开始！"
            )

            # 发起战斗
            victory, log_lines, result_lines, rewards = await self.start_battle_with_npc(
                player, tile, session
            )

            battle_result = "\n".join(log_lines + result_lines)
            return victory, f"{battle_msg}\n\n{battle_result}"

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

            # 发放战利品
            loot_items = state.get("loot", [])
            multiplier = 1.5 if result.result_level == "critical_success" else 1.0
            reward_desc, total_gold, items = await self._distribute_loot(
                player, loot_items, multiplier
            )

            await self.update_action_cooldown(session, "assassination")
            await self.uow.commit()

            # 构建结果消息
            success_desc = f"你悄无声息地解决了{target_name}..."
            if result.result_level == "critical_success":
                success_desc = f"完美！你如鬼魅般抹去了{target_name}的生命，没有留下任何痕迹！"

            if reward_desc != "什么也没得到...":
                if result.result_level == "critical_success":
                    success_desc += f"\n\n🌟 搜刮尸体，获得额外奖励（×1.5）：\n{reward_desc}"
                else:
                    success_desc += f"\n\n搜刮尸体，获得：\n{reward_desc}"

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
            # 真相反转效果
            session_state_for_truth = json.loads(session.state) if session.state else {}
            if session_state_for_truth.get("truth_inverted"):
                clue_reveal = f"（以上是谎言）{clue_reveal}"
            lines.extend([
                "",
                "━━━━━━━━━━━━━",
                f"💡 真相揭示：{clue_reveal}"
            ])

        if recovered > 0:
            lines.append(f"\n🧠 理智恢复 +{recovered}")

        # BOSS 方位暗示（根据已收集线索数量递进提示）
        clue_count = len(clue_list)
        session_state = json.loads(session.state) if session.state else {}
        boss_pos = session_state.get("boss_position")
        if boss_pos and clue_count >= 2:
            lines.append("")
            if clue_count == 2:
                lines.append("🔮 你感觉到东南方向有一股强大的气息...")
            elif clue_count == 3:
                lines.append("🔮 那股力量来自地图的右下角区域...")
            elif clue_count == 4:
                lines.append("🔮 你已经很接近了，BOSS似乎在坐标 (18-24, 18-24) 范围内")
            elif clue_count >= 5:
                lines.append(f"🔮 完整的真相指向了一个确切位置... ({boss_pos['x']}, {boss_pos['y']})")

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

        # 发放幸存者奖励
        save_rewards = state.get("save_reward", [])
        reward_desc, total_gold, items = await self._distribute_loot(
            player, save_rewards, multiplier=1.0
        )

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

        # 显示奖励
        if reward_desc != "什么也没得到...":
            lines.append(f"\n🎁 获得感谢礼物：\n{reward_desc}")

        lines.append("\n💡 提示: 救助幸存者会影响最终结局")

        return True, "\n".join(lines)

    # ==================== 迷你地图与环境感知系统 ====================

    def _get_tile_emoji(self, tile: InnerRealmTile, visited: set) -> str:
        """
        根据地块类型和状态返回对应emoji

        Args:
            tile: 地块对象
            visited: 已访问坐标集合

        Returns:
            对应的emoji字符
        """
        coord_key = f"{tile.x},{tile.y}"

        # 未访问过的地块显示迷雾
        if coord_key not in visited:
            return "▪️"

        state = json.loads(tile.state) if tile.state else {}

        if tile.event_type == "EMPTY":
            return "▫️"

        elif tile.event_type == "NPC":
            if state.get("alive", True):
                return "👤"
            else:
                return "💀"

        elif tile.event_type == "LOOT":
            if state.get("looted", False):
                return "◽"
            else:
                return "📦"

        elif tile.event_type == "CLUE":
            if state.get("collected", False):
                return "✅"
            else:
                return "📜"

        elif tile.event_type == "BOSS":
            if state.get("alive", True):
                return "👹"
            else:
                return "🏆"

        elif tile.event_type == "SURVIVOR":
            if state.get("saved", False) or state.get("killed", False):
                return "◽"
            else:
                return "🆘"

        elif tile.event_type == "COGNITION_TAMPER":
            # 伪装成空地
            return "▫️"

        return "▫️"

    async def _render_minimap(
        self,
        session: InnerRealmSession,
        realm_config: Dict[str, Any]
    ) -> str:
        """
        渲染5x5迷你地图

        Args:
            session: 会话对象
            realm_config: 里界配置

        Returns:
            渲染后的地图字符串
        """
        map_size = realm_config.get("size", 25)
        cx, cy = session.x, session.y

        # 获取已访问坐标
        state = json.loads(session.state) if session.state else {}
        visited = set(state.get("visited", []))

        # 获取5x5范围内的地块 (radius=2)
        nearby_tiles = await self.uow.inner_realm_tiles.get_nearby_tiles(
            session.id, cx, cy, radius=2
        )

        # 构建坐标到地块的映射
        tile_map = {(t.x, t.y): t for t in nearby_tiles}

        rows = []
        for dy in range(-2, 3):
            row_emojis = []
            for dx in range(-2, 3):
                tx, ty = cx + dx, cy + dy

                # 当前位置
                if tx == cx and ty == cy:
                    row_emojis.append("🧭")
                # 超出地图边界
                elif not (0 <= tx < map_size and 0 <= ty < map_size):
                    row_emojis.append("⬛")
                # 有地块数据
                elif (tx, ty) in tile_map:
                    row_emojis.append(self._get_tile_emoji(tile_map[(tx, ty)], visited))
                # 未知区域（迷雾）
                else:
                    row_emojis.append("▪️")

            rows.append("".join(row_emojis))

        return "\n".join(rows)

    def _calc_direction(self, cx: int, cy: int, tx: int, ty: int) -> str:
        """
        计算目标相对于中心的8方向文字

        Args:
            cx, cy: 中心坐标
            tx, ty: 目标坐标

        Returns:
            方向文字
        """
        dx = tx - cx
        dy = ty - cy

        if dx == 0 and dy < 0:
            return "北方"
        elif dx == 0 and dy > 0:
            return "南方"
        elif dx > 0 and dy == 0:
            return "东方"
        elif dx < 0 and dy == 0:
            return "西方"
        elif dx > 0 and dy < 0:
            return "东北方"
        elif dx < 0 and dy < 0:
            return "西北方"
        elif dx > 0 and dy > 0:
            return "东南方"
        elif dx < 0 and dy > 0:
            return "西南方"

        return "附近"

    def _get_direction_hints(
        self,
        session: InnerRealmSession,
        nearby_tiles: List[InnerRealmTile],
        max_hints: int = 3
    ) -> List[str]:
        """
        生成方向提示

        Args:
            session: 会话对象
            nearby_tiles: 附近地块列表
            max_hints: 最大提示数量

        Returns:
            方向提示列表
        """
        cx, cy = session.x, session.y
        state = json.loads(session.state) if session.state else {}
        visited = set(state.get("visited", []))

        hints = []

        for tile in nearby_tiles:
            # 跳过当前位置和空地
            if (tile.x == cx and tile.y == cy) or tile.event_type == "EMPTY":
                continue

            # 跳过认知篡改地块（伪装成空地）
            if tile.event_type == "COGNITION_TAMPER":
                continue

            tile_state = json.loads(tile.state) if tile.state else {}
            coord_key = f"{tile.x},{tile.y}"
            direction = self._calc_direction(cx, cy, tile.x, tile.y)
            distance = abs(tile.x - cx) + abs(tile.y - cy)

            # 已访问区域给明确提示
            if coord_key in visited:
                # 已处理的事件跳过
                if tile.event_type == "NPC" and not tile_state.get("alive", True):
                    continue
                if tile.event_type == "LOOT" and tile_state.get("looted", False):
                    continue
                if tile.event_type == "CLUE" and tile_state.get("collected", False):
                    continue
                if tile.event_type == "BOSS" and not tile_state.get("alive", True):
                    continue
                if tile.event_type == "SURVIVOR" and (tile_state.get("saved") or tile_state.get("killed")):
                    continue

                name = tile_state.get("name", "")
                if tile.event_type == "NPC":
                    hint = f"👤 {direction}有{name}" if name else f"👤 {direction}有一个人"
                elif tile.event_type == "LOOT":
                    hint = f"📦 {direction}有可搜刮的物资"
                elif tile.event_type == "CLUE":
                    hint = f"📜 {direction}有{name}" if name else f"📜 {direction}有线索"
                elif tile.event_type == "BOSS":
                    hint = f"👹 {direction}有{name}！" if name else f"👹 {direction}有强大的存在！"
                elif tile.event_type == "SURVIVOR":
                    hint = f"🆘 {direction}有{name}" if name else f"🆘 {direction}有幸存者"
                else:
                    continue
            else:
                # 未访问区域给模糊感知提示
                if tile.event_type == "NPC":
                    hint = f"👤 {direction}隐约有人影"
                elif tile.event_type == "LOOT":
                    hint = f"📦 {direction}似乎有什么东西"
                elif tile.event_type == "CLUE":
                    hint = f"📜 {direction}有可疑的痕迹"
                elif tile.event_type == "BOSS":
                    hint = f"👹 {direction}传来强烈的压迫感！"
                elif tile.event_type == "SURVIVOR":
                    hint = f"🆘 {direction}传来微弱呼救声"
                else:
                    continue

            hints.append((distance, hint))

        # 按距离排序，取最多max_hints条
        hints.sort(key=lambda x: x[0])
        return [h[1] for h in hints[:max_hints]]

    def _generate_atmosphere_description(
        self,
        tile: InnerRealmTile,
        sanity: int
    ) -> str:
        """
        根据事件类型和理智值生成氛围描述

        Args:
            tile: 当前地块
            sanity: 当前理智值

        Returns:
            氛围描述文字
        """
        tile_state = json.loads(tile.state) if tile.state else {}

        # EMPTY类型
        if tile.event_type == "EMPTY":
            if sanity < 30:
                descriptions = [
                    "墙壁在蠕动...不，是你的错觉...吗？",
                    "地板上的影子似乎在移动，它们不属于任何物体...",
                    "你听到了自己的心跳声，不，那不是你的心跳...",
                    "空气中弥漫着腐烂的甜味，你的手在不受控制地颤抖...",
                ]
            elif sanity < 50:
                descriptions = [
                    "走廊里隐约传来脚步声，但回头看时什么都没有...",
                    "灯光忽明忽暗，墙上的污渍看起来像是文字...",
                    "这里的空气沉重而压抑，呼吸变得困难...",
                    "你总感觉有什么东西在角落里注视着你...",
                ]
            else:
                descriptions = [
                    "这里一片寂静...",
                    "空荡荡的走廊延伸向远处...",
                    "这里弥漫着刺鼻的消毒水味...",
                    "天花板上的日光灯发出微弱的嗡嗡声...",
                    "地板上有拖拽过的痕迹，已经干涸...",
                    "墙壁上的油漆已经剥落，露出灰色的水泥...",
                ]
            return random.choice(descriptions)

        # NPC类型
        elif tile.event_type == "NPC":
            name = tile_state.get("name", "一个人影")
            if not tile_state.get("alive", True):
                descriptions = [
                    f"{name}的尸体倒在地上，空洞的眼神凝视着天花板...",
                    f"这里残留着{name}最后的气息...",
                    f"一具已经冰冷的尸体，曾经是{name}...",
                ]
            else:
                desc = tile_state.get("description", "")
                if desc:
                    return desc
                descriptions = [
                    f"{name}正在这里...",
                    f"你看到了{name}的身影...",
                ]
            return random.choice(descriptions)

        # LOOT类型
        elif tile.event_type == "LOOT":
            if tile_state.get("looted", False):
                descriptions = [
                    "这里已经被翻过了，只剩下散落的碎屑...",
                    "空空如也，所有有价值的东西都已经被拿走了...",
                ]
            else:
                descriptions = [
                    "角落里有一个落满灰尘的储物柜，似乎还没人打开过...",
                    "这里散落着一些物品，看起来还有可用的东西...",
                    "桌子上放着一个箱子，上面还带着锁...",
                    "地上有一个被遗弃的医疗包...",
                ]
            return random.choice(descriptions)

        # CLUE类型
        elif tile.event_type == "CLUE":
            if tile_state.get("collected", False):
                return "你已经收集过这里的线索了..."
            else:
                name = tile_state.get("name", "")
                descriptions = [
                    f"这里有一份引人注目的文件——{name}..." if name else "这里有可疑的痕迹...",
                    "墙上贴着一张已经泛黄的纸条...",
                    "地板下面似乎藏着什么东西...",
                ]
                return random.choice(descriptions)

        # BOSS类型
        elif tile.event_type == "BOSS":
            name = tile_state.get("name", "未知存在")
            if not tile_state.get("alive", True):
                return f"⚠️ {name}的残骸散落在地，威胁已经解除..."
            else:
                desc = tile_state.get("description", "")
                if desc:
                    return f"⚠️ {desc}"
                return f"⚠️ {name}在这里！空气中充满了杀意！"

        # SURVIVOR类型
        elif tile.event_type == "SURVIVOR":
            name = tile_state.get("name", "幸存者")
            if tile_state.get("saved") or tile_state.get("killed"):
                return f"{name}已经离开了这里..."
            else:
                desc = tile_state.get("description", "")
                if desc:
                    return desc
                return f"{name}蜷缩在角落里，浑身颤抖..."

        # COGNITION_TAMPER
        elif tile.event_type == "COGNITION_TAMPER":
            if sanity < 50:
                descriptions = [
                    "空气突然变得粘稠，你的视线开始模糊...",
                    "你感到一阵眩晕，世界开始扭曲...",
                ]
                return random.choice(descriptions)
            return "这里一片寂静..."

        return "..."

    def _get_current_time_period(self) -> Tuple[str, str]:
        """
        获取当前时段信息

        Returns:
            (时段名称, 时段emoji)
        """
        time_config = InnerRealmConfig.get_time_system_config()
        current_hour = datetime.now().hour

        for period_name, period_config in time_config.items():
            start_hour = period_config["start_hour"]
            end_hour = period_config["end_hour"]

            if start_hour > end_hour:
                if current_hour >= start_hour or current_hour < end_hour:
                    if period_name == "night":
                        return "深夜", "🌙"
                    return period_name, "🌙"
            else:
                if start_hour <= current_hour < end_hour:
                    if period_name == "day":
                        return "白昼", "☀️"
                    elif period_name == "dusk":
                        return "黄昏", "🌅"
                    return period_name, "🌅"

        return "未知", "❓"

    async def generate_move_feedback(
        self,
        session: InnerRealmSession,
        realm_config: Dict[str, Any]
    ) -> str:
        """
        生成移动后的完整反馈信息

        Args:
            session: 会话对象
            realm_config: 里界配置

        Returns:
            完整的移动反馈消息
        """
        display_name = realm_config.get("display_name", "未知里界")

        # 获取当前地块
        tile = await self.get_current_tile(session)

        # 解析会话状态
        clue_count = len(json.loads(session.clue_collected) if session.clue_collected else [])

        # 理智状态指示器
        sanity_icon = "🟢"
        if session.sanity <= 10:
            sanity_icon = "💀"
        elif session.sanity <= 30:
            sanity_icon = "🔴"
        elif session.sanity <= 50:
            sanity_icon = "🟡"

        # 渲染迷你地图
        minimap = await self._render_minimap(session, realm_config)

        # 获取方向提示
        nearby_tiles = await self.uow.inner_realm_tiles.get_nearby_tiles(
            session.id, session.x, session.y, radius=2
        )
        direction_hints = self._get_direction_hints(session, nearby_tiles, max_hints=3)

        # 生成氛围描述
        atmosphere = ""
        if tile:
            atmosphere = self._generate_atmosphere_description(tile, session.sanity)

        # 组装完整消息
        lines = [
            f"🌌 {display_name} · ({session.x}, {session.y})",
            "━━━━━━━━━━━━━",
            minimap,
            "━━━━━━━━━━━━━",
            f"{sanity_icon} 理智:{session.sanity} | ⚔️{session.killed_count} | 🛡️{session.saved_count} | 📖{clue_count}/5",
        ]

        # 添加方向提示
        if direction_hints:
            lines.append("━━━━━━━━━━━━━")
            for hint in direction_hints:
                lines.append(hint)

        # 添加氛围描述
        if atmosphere:
            lines.append("━━━━━━━━━━━━━")
            lines.append(atmosphere)

        return "\n".join(lines)

    async def observe_surroundings(
        self,
        session: InnerRealmSession,
        realm_config: Dict[str, Any]
    ) -> str:
        """
        观察周围环境（比移动反馈更详细）

        Args:
            session: 会话对象
            realm_config: 里界配置

        Returns:
            详细的观察信息
        """
        display_name = realm_config.get("display_name", "未知里界")
        time_period_name, time_emoji = self._get_current_time_period()

        # 获取当前地块
        tile = await self.get_current_tile(session)

        # 解析会话状态
        session_state = json.loads(session.state) if session.state else {}
        clue_count = len(json.loads(session.clue_collected) if session.clue_collected else [])
        boss_defeated = session_state.get("boss_defeated", False)

        # 理智状态指示器
        sanity_icon = "🟢"
        if session.sanity <= 10:
            sanity_icon = "💀"
        elif session.sanity <= 30:
            sanity_icon = "🔴"
        elif session.sanity <= 50:
            sanity_icon = "🟡"

        # 渲染迷你地图
        minimap = await self._render_minimap(session, realm_config)

        # 获取方向提示（增加到4条）
        nearby_tiles = await self.uow.inner_realm_tiles.get_nearby_tiles(
            session.id, session.x, session.y, radius=2
        )
        direction_hints = self._get_direction_hints(session, nearby_tiles, max_hints=4)

        # 生成氛围描述
        atmosphere = ""
        if tile:
            atmosphere = self._generate_atmosphere_description(tile, session.sanity)

        # 组装详细观察消息
        lines = [
            f"🌌 {display_name} · ({session.x}, {session.y})",
            f"{time_emoji} 时段：{time_period_name}",
            "━━━━━━━━━━━━━",
            minimap,
            "━━━━━━━━━━━━━",
            f"{sanity_icon} 理智:{session.sanity}/100 | ⚔️击杀:{session.killed_count} | 🛡️救出:{session.saved_count} | 📖线索:{clue_count}/5",
        ]

        if boss_defeated:
            lines.append("🏆 核心BOSS已击败")

        # 当前位置可交互目标
        if tile:
            tile_state = json.loads(tile.state) if tile.state else {}
            interact_lines = self._get_interaction_options(tile, tile_state)
            if interact_lines:
                lines.append("━━━━━━━━━━━━━")
                lines.append("🎯 当前位置：")
                lines.extend(interact_lines)

        # 添加方向提示
        if direction_hints:
            lines.append("━━━━━━━━━━━━━")
            lines.append("📡 周围感知：")
            for hint in direction_hints:
                lines.append(f"  {hint}")

        # 添加氛围描述
        if atmosphere:
            lines.append("━━━━━━━━━━━━━")
            lines.append(atmosphere)

        # 可用操作提示
        lines.append("━━━━━━━━━━━━━")
        lines.append("💡 可用命令：【上/下/左/右】移动 | 【里界信息】查看进度 | 【返回】离开")

        return "\n".join(lines)

    def _get_interaction_options(
        self,
        tile: InnerRealmTile,
        tile_state: Dict[str, Any]
    ) -> List[str]:
        """
        获取当前位置的可交互选项

        Args:
            tile: 当前地块
            tile_state: 地块状态

        Returns:
            交互选项文字列表
        """
        options = []

        if tile.event_type == "NPC":
            name = tile_state.get("name", "未知NPC")
            if tile_state.get("alive", True):
                hp = tile_state.get("hp", 0)
                max_hp = tile_state.get("max_hp", hp)
                options.append(f"  👤 {name} (HP:{hp}/{max_hp})")
                options.append("  → 【交谈】【威吓】【处决】【攻击】")
            else:
                options.append(f"  💀 {name} (已死亡)")

        elif tile.event_type == "LOOT":
            if tile_state.get("looted", False):
                options.append("  ◽ 已搜刮完毕")
            else:
                options.append("  📦 可搜刮的物资")
                options.append("  → 【搜刮】")

        elif tile.event_type == "CLUE":
            name = tile_state.get("name", "线索")
            if tile_state.get("collected", False):
                options.append(f"  ✅ {name} (已收集)")
            else:
                options.append(f"  📜 {name}")
                options.append("  → 【搜刮】收集线索")

        elif tile.event_type == "BOSS":
            name = tile_state.get("name", "核心BOSS")
            if tile_state.get("alive", True):
                hp = tile_state.get("hp", 0)
                max_hp = tile_state.get("max_hp", hp)
                options.append(f"  👹 {name} (HP:{hp}/{max_hp})")
                options.append("  → 【攻击】【交谈】【威吓】")
            else:
                options.append(f"  🏆 {name} (已击败)")

        elif tile.event_type == "SURVIVOR":
            name = tile_state.get("name", "幸存者")
            if tile_state.get("saved") or tile_state.get("killed"):
                options.append(f"  ◽ {name} (已处理)")
            else:
                options.append(f"  🆘 {name}")
                options.append("  → 【救助】【交谈】【处决】")

        elif tile.event_type == "EMPTY":
            options.append("  ▫️ 空旷区域")

        return options