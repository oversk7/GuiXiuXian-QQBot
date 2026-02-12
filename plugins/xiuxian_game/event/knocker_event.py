"""
除夕叩门活动 — 核心逻辑

诡事刷新 / 击杀回调 / 活动进度 / 排行 / 商店兑换
"""

import json
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from nonebot import logger
from sqlalchemy import select, func, desc

from ..models.player import Player
from ..models.npc import NPC, NPCType
from ..models.inventory import ItemInstance
from ..models.world_message import WorldMessage
from ..daily_task.service_new import DailyTaskService

from .knocker_config import (
    GHOST_EVENT_TYPES, GhostEventType,
    GHOST_NAMES, CITY_NAMES,
    REFRESH_INTERVAL_MINUTES, SPAWN_COUNT_RANGE, MAX_ACTIVE_EVENTS,
    COORD_RANGE, EVENT_LIFETIME_MINUTES,
    BASE_EXP, EXP_PER_LEVEL, BASE_GOLD, GOLD_PER_LEVEL,
    SHOP_ITEMS, ShopItem,
    BROADCAST_SPAWN, BROADCAST_BOSS_KILL,
    DEFAULT_DURATION_HOURS,
    TELEPORT_MAX_DISTANCE, TELEPORT_COOLDOWN, TELEPORT_COORD_RANGE,
    TELEPORT_TEXT,
    LEVEL_OFFSET_BY_TIER,
    TITLE_ITEMS,  # 称号映射表
)


# ==================== 活动状态文件路径 ====================
_STATE_FILE = Path(__file__).parent.parent / "data" / "knocker_event_state.json"


# ==================== 活动诡事点内存缓存 ====================
@dataclass
class ActiveGhostEvent:
    """活动中的诡事点"""
    event_id: str          # 唯一ID
    type_id: str           # 诡事类型ID
    npc_id: str            # NPC唯一标识(用于查找NPC)
    npc_name: str          # NPC名称
    x: int                 # X坐标
    y: int                 # Y坐标
    city_name: str         # 地名
    narrative: str         # 叙事文本
    spawn_time: float      # 生成时间戳
    level: int             # 鬼怪等级（新增）
    tier_id: str           # 等级段ID: low/mid/high（新增）
    is_alive: bool = True  # 是否存活

    @property
    def type_config(self) -> GhostEventType:
        return GHOST_EVENT_TYPES[self.type_id]

    def is_expired(self) -> bool:
        """是否已过期(超过存活时间)"""
        return time.time() - self.spawn_time > EVENT_LIFETIME_MINUTES * 60


class KnockerEventService:
    """除夕叩门活动核心服务"""

    # 类级别活动状态(内存)
    _is_active: bool = False
    _start_time: float = 0
    _end_time: float = 0
    _active_events: Dict[str, ActiveGhostEvent] = {}  # event_id -> ActiveGhostEvent
    _last_refresh_time: float = 0
    _event_counter: int = 0  # 用于生成唯一event_id

    @classmethod
    def _load_state(cls):
        """从文件加载活动状态"""
        if _STATE_FILE.exists():
            try:
                data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
                cls._is_active = data.get("is_active", False)
                cls._start_time = data.get("start_time", 0)
                cls._end_time = data.get("end_time", 0)
                cls._event_counter = data.get("event_counter", 0)
                # 检查活动是否已过期
                if cls._is_active and time.time() > cls._end_time:
                    cls._is_active = False
                    cls._save_state()
                logger.info(f"[叩门活动] 已加载状态: active={cls._is_active}")
            except Exception as e:
                logger.error(f"[叩门活动] 加载状态失败: {e}")

    @classmethod
    def _save_state(cls):
        """保存活动状态到文件"""
        try:
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "is_active": cls._is_active,
                "start_time": cls._start_time,
                "end_time": cls._end_time,
                "event_counter": cls._event_counter,
            }
            _STATE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.error(f"[叩门活动] 保存状态失败: {e}")

    # ==================== 活动开关 ====================

    @classmethod
    async def start_event(cls, duration_hours: int = DEFAULT_DURATION_HOURS, session=None) -> str:
        """开启活动

        Args:
            duration_hours: 活动持续时间(小时)
            session: 数据库会话,用于立即刷新诡事点(可选)

        Returns:
            活动开启播报文本
        """
        now = time.time()
        cls._is_active = True
        cls._start_time = now
        cls._end_time = now + duration_hours * 3600
        cls._active_events.clear()
        cls._last_refresh_time = 0
        cls._save_state()
        end_dt = datetime.fromtimestamp(cls._end_time).strftime("%m月%d日 %H:%M")

        broadcast = (
            "咚...咚...咚...\n"
            "━━━━━━━━━━━━━\n"
            "缉邪司甲级通报：除夕夜，大都会多处出现异常诡象！\n"
            f"活动将持续 {duration_hours} 小时，至 {end_dt}\n"
            "━━━━━━━━━━━━━\n"
            "所有修士即刻响应！\n"
            "使用【除夕活动】查看详情"
        )

        # 如果提供了session,立即刷新一波诡事点
        if session is not None:
            try:
                spawn_broadcast = await cls.refresh_events(session)
                if spawn_broadcast:
                    broadcast += "\n\n" + spawn_broadcast
            except Exception as e:
                logger.error(f"[叩门活动] 开启活动时立即刷新失败: {e}")

        return broadcast

    @classmethod
    def stop_event(cls) -> str:
        """关闭活动"""
        cls._is_active = False
        cls._active_events.clear()
        cls._save_state()
        return (
            "━━━━━━━━━━━━━\n"
            "缉邪司通报：除夕叩门活动已结束。\n"
            "所有诡事点已清除。感谢各位修士的付出！\n"
            "━━━━━━━━━━━━━"
        )

    @classmethod
    def is_active(cls) -> bool:
        """检查活动是否正在进行"""
        if not cls._is_active:
            return False
        if time.time() > cls._end_time:
            cls._is_active = False
            cls._active_events.clear()
            cls._save_state()
            return False
        return True

    @classmethod
    def get_remaining_time(cls) -> str:
        """获取活动剩余时间(文本)"""
        if not cls.is_active():
            return "活动未开启"
        remaining = cls._end_time - time.time()
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        return f"{hours}小时{minutes}分钟"

    # ==================== 诡事刷新 ====================

    @classmethod
    def should_refresh(cls) -> bool:
        """检查是否需要刷新诡事"""
        if not cls.is_active():
            return False
        now = time.time()
        return now - cls._last_refresh_time >= REFRESH_INTERVAL_MINUTES * 60

    @classmethod
    async def refresh_player_events(cls, session, player: Player) -> int:
        """为单个玩家刷新诡事点（个人独立模式）

        Args:
            session: 数据库会话
            player: 玩家对象

        Returns:
            本次刷新生成的鬼怪数量
        """
        if not cls.is_active():
            return 0

        # 获取玩家活动数据
        pdata = cls._get_player_data(player)
        last_refresh = pdata.get("last_refresh", 0)
        personal_events = pdata.get("personal_events", {})

        # 检查刷新冷却（10分钟）
        now = time.time()
        if now - last_refresh < REFRESH_INTERVAL_MINUTES * 60:
            return 0

        # 清理已过期的诡事
        to_remove = []
        for event_id, ev_data in personal_events.items():
            spawn_time = ev_data.get("spawn_time", 0)
            if now - spawn_time > EVENT_LIFETIME_MINUTES * 60:
                to_remove.append(event_id)
        for event_id in to_remove:
            del personal_events[event_id]

        # 统计未过期且未击杀的鬼怪数量
        alive_count = sum(1 for ev in personal_events.values()
                         if not ev.get("killed", False))

        if alive_count >= MAX_ACTIVE_EVENTS:
            pdata["last_refresh"] = now
            cls._set_player_data(player, pdata)
            return 0

        # 计算本波生成数量
        max_spawn = MAX_ACTIVE_EVENTS - alive_count
        spawn_count = min(random.randint(*SPAWN_COUNT_RANGE), max_spawn)
        if spawn_count <= 0:
            pdata["last_refresh"] = now
            cls._set_player_data(player, pdata)
            return 0

        # 按权重随机选择鬼怪类型
        type_ids = list(GHOST_EVENT_TYPES.keys())
        type_weights = [GHOST_EVENT_TYPES[t].weight for t in type_ids]

        # 获取玩家等级
        player_level = player.level

        # 生成新鬼怪（只保存数据，不创建NPC对象）
        new_count = 0
        for _ in range(spawn_count):
            # 随机选择诡事类型
            type_id = random.choices(type_ids, weights=type_weights, k=1)[0]
            ghost_type = GHOST_EVENT_TYPES[type_id]

            # 根据强度动态计算鬼怪等级（基于玩家等级）
            tier = ghost_type.tier
            offset_range = LEVEL_OFFSET_BY_TIER.get(tier, (0, 10))
            level_offset = random.randint(offset_range[0], offset_range[1])
            ghost_level = max(1, player_level + level_offset)  # 至少1级

            # 生成坐标
            x = random.randint(-COORD_RANGE, COORD_RANGE)
            y = random.randint(-COORD_RANGE, COORD_RANGE)

            # 选择城市和名字
            city = random.choice(CITY_NAMES)
            ghost_name = random.choice(GHOST_NAMES)
            npc_display_name = f"{ghost_type.npc_prefix}·{ghost_name}"

            # 选择叙事
            narrative_template = random.choice(ghost_type.narratives)
            narrative = narrative_template.replace("{地名}", city)

            # 生成唯一ID（玩家ID + 时间戳 + 随机数）
            event_id = f"p{player.id}_t{int(now)}_{random.randint(1000, 9999)}"

            # 计算鬼怪属性（存储为字典）
            base_stats = DailyTaskService._calculate_enemy_stats(ghost_level)
            stats = {
                "hp": int(base_stats["hp"] * ghost_type.hp_mult),
                "attack": int(base_stats["attack"] * ghost_type.atk_mult),
                "defense": int(base_stats["defense"] * ghost_type.def_mult),
                "agility": int(base_stats["agility"] * ghost_type.agi_mult),
            }

            # 保存到玩家个人数据（不创建NPC，战斗时再动态创建）
            personal_events[event_id] = {
                "type_id": type_id,
                "tier_id": ghost_type.tier,  # 新增：保存强度等级，方便判断是否为BOSS
                "npc_name": npc_display_name,
                "ghost_name": ghost_name,  # 保存原始名字
                "x": x,
                "y": y,
                "city_name": city,
                "narrative": narrative,
                "spawn_time": now,
                "level": ghost_level,
                "stats": stats,  # 保存属性
                "shard_reward": ghost_type.shard_reward,
                "reward_mult": ghost_type.reward_mult,
                "material_drop_rate": ghost_type.material_drop_rate,
                "special_mechanic": ghost_type.special_mechanic if ghost_type.special_mechanic else None,
                "killed": False,
            }
            new_count += 1

        # 更新玩家数据
        pdata["personal_events"] = personal_events
        pdata["last_refresh"] = now
        cls._set_player_data(player, pdata)
        cls._event_counter += new_count
        cls._save_state()

        return new_count

    @classmethod
    async def refresh_events(cls, session) -> Optional[str]:
        """【已废弃】旧的全服刷新逻辑，保留以兼容旧代码调用"""
        return None

    @classmethod
    def _cleanup_expired(cls):
        """清理已过期的诡事（个人事件模式：已移至refresh_player_events内部）"""
        to_remove = []
        for eid, ev in cls._active_events.items():
            if ev.is_expired():
                to_remove.append(eid)
        for eid in to_remove:
            del cls._active_events[eid]

    @classmethod
    async def _get_median_player_level(cls, session) -> int:
        """获取全服活跃玩家中位等级"""
        # 取最近7天活跃的玩家
        cutoff = datetime.now() - timedelta(days=7)
        stmt = select(Player.level).where(
            Player.last_cultivation != None,
            Player.last_cultivation >= cutoff,
            Player.level > 0
        ).order_by(Player.level)
        result = await session.execute(stmt)
        levels = [r[0] for r in result.all()]
        if not levels:
            return 30  # 默认值
        return levels[len(levels) // 2]

    # ==================== 活动信息查询 ====================

    @classmethod
    def get_player_active_events(cls, player: Player) -> List[dict]:
        """获取玩家个人的活跃诡事列表（未过期且未击杀）

        Returns:
            鬼怪数据字典列表，每个字典包含event_id和鬼怪信息
        """
        pdata = cls._get_player_data(player)
        personal_events = pdata.get("personal_events", {})
        now = time.time()

        active_list = []
        for event_id, ev_data in personal_events.items():
            # 过滤已过期或已击杀的
            spawn_time = ev_data.get("spawn_time", 0)
            if now - spawn_time > EVENT_LIFETIME_MINUTES * 60:
                continue
            if ev_data.get("killed", False):
                continue

            # 添加event_id到字典
            ev_with_id = dict(ev_data)
            ev_with_id["event_id"] = event_id
            active_list.append(ev_with_id)

        return active_list

    @classmethod
    async def get_event_status(cls, session, player) -> str:
        """获取活动状态文本(含个人进度，自动触发刷新)"""
        if not cls.is_active():
            return "━━━━━━━━━━━━━\n除夕叩门活动当前未开启\n━━━━━━━━━━━━━"

        # 自动刷新玩家个人诡事
        new_count = await cls.refresh_player_events(session, player)
        refresh_tip = f"\n🆕 刷新了{new_count}个新诡事" if new_count > 0 else ""

        # 获取玩家活动数据
        pdata = cls._get_player_data(player)
        shards = pdata.get("shards", 0)
        kills = pdata.get("kills", 0)

        # 获取玩家个人的诡事列表
        active_events = cls.get_player_active_events(player)

        # 按距离排序
        px, py = player.real_world_x or 0, player.real_world_y or 0

        def distance(ev):
            return abs(ev["x"] - px) + abs(ev["y"] - py)

        active_events.sort(key=distance)

        # 鬼怪类型强度标识
        def get_type_icon(type_id: str) -> str:
            """根据鬼怪类型获取强度图标"""
            ghost_type = GHOST_EVENT_TYPES.get(type_id)
            if not ghost_type:
                return "⚪"
            tier = ghost_type.tier
            if tier == "boss":
                return "🔴"
            elif tier == "elite":
                return "🟣"
            elif tier == "medium":
                return "🔵"
            else:  # basic
                return "🟢"

        lines = [
            "咚...咚...咚...",
            "━━ 除夕叩门·缉邪令 ━━",
            f"⏰ 剩余时间: {cls.get_remaining_time()}",
            f"🔮 封门符碎片: {shards}",
            f"💀 已解决诡事: {kills}",
        ]

        if refresh_tip:
            lines.append(refresh_tip)

        lines.append("")

        if active_events:
            # 分类显示：优先显示距离近的
            lines.append(f"🎯 你的诡事列表 ({len(active_events)}个):")
            for ev in active_events[:15]:  # 最多显示15个
                type_icon = get_type_icon(ev["type_id"])
                dist = distance(ev)
                lines.append(f"  ⚔️{type_icon}{ev['npc_name']}(Lv.{ev['level']}) ({ev['x']},{ev['y']}) 距{dist}格")
                lines.append(f"     {ev['narrative']}")
                lines.append("")
        else:
            lines.append("📍 当前无活跃诡事点")
            lines.append("   十分钟后可刷新新的诡事...")

        lines.extend([
            "",
            "━━━━━━━━━━━━━",
            "💡 鬼怪强度标识：",
            "   🟢普通（等级±5） 🔵精英（等级+0~10）",
            "   🟣头目（等级+5~15） 🔴BOSS（等级+10~25）",
            "",
            "💡 【鬼域瞬移 x y】快速移动",
            "💡 【攻击 鬼怪名】击杀鬼怪（需距离≤2格）",
            "💡 【活动商店】碎片兑换奖励",
            "💡 【叩门排行】查看排名",
            "",
            "⚠️ 注意：鬼怪刷新后10分钟内未击杀将自动消失",
        ])

        return "\n".join(lines)

    # ==================== 击杀回调 ====================

    @classmethod
    def find_player_ghost_by_name(cls, player: Player, npc_name: str) -> Optional[dict]:
        """通过鬼怪名字查找玩家个人鬼怪（支持部分匹配）

        Args:
            player: 玩家对象
            npc_name: 鬼怪名字（支持完整名称或部分名称，如"守岁者"可匹配"鬼仆·守岁者"）

        Returns:
            鬼怪数据字典（包含event_id），如果未找到或已击杀则返回None
        """
        pdata = cls._get_player_data(player)
        personal_events = pdata.get("personal_events", {})
        now = time.time()

        # 清理输入名称
        clean_target = npc_name.strip().lower()

        # 收集所有有效的匹配候选
        candidates = []

        for event_id, ev_data in personal_events.items():
            # 检查是否已过期
            spawn_time = ev_data.get("spawn_time", 0)
            if now - spawn_time > EVENT_LIFETIME_MINUTES * 60:
                continue

            # 检查是否已击杀
            if ev_data.get("killed", False):
                continue

            # 获取鬼怪名称并进行智能匹配
            ghost_name = ev_data.get("npc_name", "")
            ghost_name_lower = ghost_name.lower()

            # 匹配优先级（数字越小优先级越高）
            priority = None

            # 1. 精确匹配（优先级最高）
            if ghost_name_lower == clean_target:
                priority = 0
            # 2. 完整包含目标名称
            elif clean_target in ghost_name_lower:
                priority = 1
            # 3. 点号后匹配（如"守岁者"匹配"鬼仆·守岁者"）
            elif f"·{clean_target}" in ghost_name_lower:
                priority = 2
            # 4. 点号前匹配（如"鬼仆"匹配"鬼仆·守岁者"）
            elif f"{clean_target}·" in ghost_name_lower:
                priority = 3

            if priority is not None:
                result = dict(ev_data)
                result["event_id"] = event_id
                candidates.append((priority, result))

        # 如果找到匹配，返回优先级最高的
        if candidates:
            candidates.sort(key=lambda x: x[0])
            return candidates[0][1]

        return None

    @classmethod
    def mark_player_ghost_killed(cls, player: Player, event_id: str):
        """标记玩家个人鬼怪为已击杀

        Args:
            player: 玩家对象
            event_id: 鬼怪事件ID
        """
        pdata = cls._get_player_data(player)
        personal_events = pdata.get("personal_events", {})

        if event_id in personal_events:
            personal_events[event_id]["killed"] = True

        pdata["personal_events"] = personal_events
        pdata["shards"] = pdata.get("shards", 0)
        pdata["kills"] = pdata.get("kills", 0)
        cls._set_player_data(player, pdata)

    @classmethod
    def create_temp_npc_from_ghost_data(cls, ghost_data: dict, session) -> NPC:
        """从鬼怪数据动态创建临时NPC对象（用于战斗）

        Args:
            ghost_data: 鬼怪数据字典（来自个人诡事）
            session: 数据库会话

        Returns:
            临时NPC对象（不持久化到数据库）
        """
        stats = ghost_data["stats"]
        event_id = ghost_data["event_id"]
        type_id = ghost_data["type_id"]

        # 创建临时NPC对象
        npc = NPC(
            npc_id=f"temp_{event_id}",
            name=ghost_data["npc_name"],
            npc_type=NPCType.GHOST,
            level=ghost_data["level"],
            hp=stats["hp"],
            max_hp=stats["hp"],
            attack=stats["attack"],
            defense=stats["defense"],
            agility=stats["agility"],
            location_id=None,  # 临时对象不需要位置
        )
        npc.extra_data = {
            "knocker_event_id": event_id,
            "knocker_type": type_id,
            "shard_reward": ghost_data["shard_reward"],
            "reward_mult": ghost_data["reward_mult"],
            "material_drop_rate": ghost_data["material_drop_rate"],
        }
        if ghost_data.get("special_mechanic"):
            npc.extra_data["special_mechanic"] = ghost_data["special_mechanic"]

        return npc

    @classmethod
    def is_knocker_npc(cls, npc: NPC) -> bool:
        """检查NPC是否为活动鬼怪"""
        if not cls.is_active():
            return False
        extra = npc.extra_data or {}
        return "knocker_event_id" in extra

    @classmethod
    async def on_ghost_killed(cls, session, player: Player, event_id: str, ghost_data: dict) -> List[str]:
        """活动鬼怪被击杀的回调（个人事件模式）

        Args:
            session: 数据库会话
            player: 玩家对象
            event_id: 鬼怪事件ID
            ghost_data: 鬼怪数据字典

        Returns:
            附加的结果行列表
        """
        if not cls.is_active():
            return []

        type_id = ghost_data.get("type_id")
        shard_reward = ghost_data.get("shard_reward", 1)
        reward_mult = ghost_data.get("reward_mult", 1.0)
        material_drop_rate = ghost_data.get("material_drop_rate", 0.05)

        ghost_type = GHOST_EVENT_TYPES.get(type_id)
        if not ghost_type:
            return []

        result_lines = []

        # 标记为已击杀
        cls.mark_player_ghost_killed(player, event_id)

        # 更新击杀计数
        pdata = cls._get_player_data(player)
        pdata["shards"] = pdata.get("shards", 0) + shard_reward
        pdata["kills"] = pdata.get("kills", 0) + 1
        cls._set_player_data(player, pdata)

        # 计算奖励
        exp_reward = int((BASE_EXP + player.level * EXP_PER_LEVEL) * reward_mult)
        gold_reward = int((BASE_GOLD + player.level * GOLD_PER_LEVEL) * reward_mult)

        # 检查是否为BOSS，给予额外奖励
        tier_id = ghost_data.get("tier_id", "")
        is_boss = tier_id == "boss"

        if is_boss:
            # BOSS额外奖励：经验和金币翻倍
            bonus_exp = exp_reward
            bonus_gold = gold_reward
            exp_reward += bonus_exp
            gold_reward += bonus_gold

        # 发放经验和金币
        player.exp += exp_reward
        player.gold += gold_reward

        # 关键修复: 明确标记player对象需要更新
        session.add(player)

        result_lines.append("")
        if is_boss:
            result_lines.append("🔴 BOSS击杀·特殊奖励 🔴")
        else:
            result_lines.append("🎆 除夕叩门·缉邪奖励")
        result_lines.append(f"  ✨ 经验 +{exp_reward}")
        result_lines.append(f"  💰 金币 +{gold_reward}")
        result_lines.append(f"  🔮 封门符碎片 +{shard_reward}")

        if is_boss:
            result_lines.append("")
            result_lines.append("  💥 BOSS击杀奖励已翻倍！")

        # 材料掉落判定
        if random.random() < material_drop_rate:
            material_id = cls._get_level_material(player.level)
            if material_id:
                try:
                    # BOSS材料掉落数量翻倍
                    material_count = 2 if is_boss else 1
                    await ItemInstance.add_item(session, player.id, material_id, material_count)
                    from ..config import config
                    item_cfg = config.items_config["by_id"].get(material_id)
                    if item_cfg:
                        if material_count > 1:
                            result_lines.append(f"  💎 掉落: {item_cfg.get_display_name()} x{material_count}")
                        else:
                            result_lines.append(f"  💎 掉落: {item_cfg.get_display_name()}")
                except ValueError:
                    result_lines.append("  📦 背包已满,材料掉落失败")

        result_lines.append(f"  💀 已解决诡事: {pdata['kills']}")
        result_lines.append(f"  🔮 碎片总计: {pdata['shards']}")

        return result_lines

    @classmethod
    def get_boss_kill_broadcast(cls, player: Player, npc: NPC) -> Optional[str]:
        """获取Boss击杀全服播报(仅boss级)"""
        extra = npc.extra_data or {}
        type_id = extra.get("knocker_type")
        if not type_id:
            return None
        ghost_type = GHOST_EVENT_TYPES.get(type_id)
        if not ghost_type or ghost_type.tier != "boss":
            return None

        city = extra.get("knocker_city", "未知地点")
        return BROADCAST_BOSS_KILL.format(
            player_name=player.nickname,
            location=city,
            npc_name=npc.name,
        )

    # ==================== 排行榜 ====================

    @classmethod
    async def get_ranking(cls, session, top_n: int = 20) -> str:
        """获取叩门排行榜"""
        if not cls.is_active():
            return "━━━━━━━━━━━━━\n除夕叩门活动当前未开启\n━━━━━━━━━━━━━"

        # 查询所有玩家, 筛选有活动数据的
        stmt = select(Player).where(Player.level > 0)
        result = await session.execute(stmt)
        players = result.scalars().all()

        # 提取活动数据并排序
        ranking_data = []
        for p in players:
            pdata = cls._get_player_data(p)
            kills = pdata.get("kills", 0)
            if kills > 0:
                ranking_data.append((p.nickname, kills, pdata.get("shards", 0)))

        ranking_data.sort(key=lambda x: x[1], reverse=True)

        lines = [
            "🏆 除夕叩门·缉邪排行 🏆",
            "━━━━━━━━━━━━━",
        ]

        if not ranking_data:
            lines.append("暂无修士参与")
        else:
            medals = ["🥇", "🥈", "🥉"]
            for i, (name, kills, shards) in enumerate(ranking_data[:top_n]):
                prefix = medals[i] if i < 3 else f"#{i + 1}"
                lines.append(f"{prefix} {name} — {kills}次 ({shards}碎片)")

        lines.append("━━━━━━━━━━━━━")
        return "\n".join(lines)

    # ==================== 活动商店 ====================

    @classmethod
    async def handle_shop_view(cls, player: Player) -> str:
        """查看活动商店"""
        if not cls.is_active():
            return "━━━━━━━━━━━━━\n除夕叩门活动当前未开启\n━━━━━━━━━━━━━"

        pdata = cls._get_player_data(player)
        shards = pdata.get("shards", 0)
        purchased = pdata.get("purchased", {})

        # 稀有度图标映射
        rarity_icons = {
            "white": "⚪",
            "green": "🟢",
            "blue": "🔵",
            "purple": "🟣",
            "orange": "🟠",
            "red": "❤️",
        }

        # 分类装饰图标
        category_icons = {
            "日用补给": "📦",
            "成长加速": "⚡",
            "稀有宝物": "💎",
            "食谱解锁": "📜",
            "限定收藏": "🌟",
            "称号收藏": "🏅",
        }

        lines = [
            "🏪 除夕叩门·活动商店",
            f"🔮 封门符碎片: {shards}",
            "━━━━━━━━━━━━━",
        ]

        current_category = ""
        today_str = datetime.now().strftime("%Y%m%d")

        for item in SHOP_ITEMS:
            # 分区标题(带装饰)
            if item.category != current_category:
                current_category = item.category
                category_icon = category_icons.get(current_category, "📍")
                lines.append(f"\n{category_icon} 【{current_category}】")

            # 从config中获取物品配置以读取稀有度
            from ..config import config
            item_config = config.items_config["by_id"].get(item.item_id)
            rarity = getattr(item_config, 'rarity', 'white') if item_config else 'white'
            rarity_icon = rarity_icons.get(rarity, "⚪")

            # 计算已购数量
            item_purchased = purchased.get(item.item_id, {})
            daily_bought = item_purchased.get(f"daily_{today_str}", 0)
            event_bought = item_purchased.get("event_total", 0)

            # 判断是否可购买
            sold_out = False
            limit_text = ""
            if item.daily_limit > 0:
                remaining = item.daily_limit - daily_bought
                if remaining <= 0:
                    sold_out = True
                limit_text = f"日限{item.daily_limit}"
            if item.event_limit > 0:
                remaining_event = item.event_limit - event_bought
                if remaining_event <= 0:
                    sold_out = True
                limit_text = f"活动限{item.event_limit}"

            # 构建展示行
            status = "售罄" if sold_out else f"{item.shard_cost}碎片"
            status_icon = "❌" if sold_out else "✨"

            # 特殊标记:限定收藏区的物品
            special_mark = ""
            if item.category == "限定收藏":
                special_mark = "🎁 "

            lines.append(f"  {status_icon} {rarity_icon} {special_mark}{item.name}")
            lines.append(f"     💰 {status} • 📊 {limit_text}")

        lines.extend([
            "",
            "━━━━━━━━━━━━━",
            "💡 【活动商店 兑换 物品名】购买",
            "💡 【活动商店 兑换 物品名 数量】批量购买",
            "💡 【切换称号 称号名】切换已拥有的称号",
            "💡 【卸下称号】取消称号展示",
        ])

        return "\n".join(lines)

    @classmethod
    async def handle_shop_buy(cls, session, player: Player, item_name: str, quantity: int = 1) -> Tuple[bool, str]:
        """商店购买

        Returns:
            (成功, 结果消息)
        """
        if not cls.is_active():
            return False, "活动未开启"

        # 查找商品
        shop_item: Optional[ShopItem] = None
        for si in SHOP_ITEMS:
            if si.name == item_name:
                shop_item = si
                break

        if not shop_item:
            return False, f"商品「{item_name}」不存在，请检查名称"

        pdata = cls._get_player_data(player)
        shards = pdata.get("shards", 0)
        purchased = pdata.get("purchased", {})
        today_str = datetime.now().strftime("%Y%m%d")

        item_purchased = purchased.get(shop_item.item_id, {})
        daily_bought = item_purchased.get(f"daily_{today_str}", 0)
        event_bought = item_purchased.get("event_total", 0)

        # 检查限购
        if shop_item.daily_limit > 0:
            max_buy = shop_item.daily_limit - daily_bought
            if max_buy <= 0:
                return False, f"「{item_name}」今日已达限购上限"
            quantity = min(quantity, max_buy)

        if shop_item.event_limit > 0:
            max_buy_event = shop_item.event_limit - event_bought
            if max_buy_event <= 0:
                return False, f"「{item_name}」活动期间已达限购上限"
            quantity = min(quantity, max_buy_event)

        # 检查碎片
        total_cost = shop_item.shard_cost * quantity
        if shards < total_cost:
            return False, f"碎片不足! 需要 {total_cost} 碎片, 当前 {shards}"

        # 特殊处理: 称号（使用TITLE_ITEMS映射表统一处理所有称号）
        if shop_item.item_id in TITLE_ITEMS:
            title_name = TITLE_ITEMS[shop_item.item_id]
            # 称号直接记录到活动数据
            pdata["title"] = title_name
            # 记录到已拥有称号列表
            owned_titles = pdata.get("owned_titles", [])
            if title_name not in owned_titles:
                owned_titles.append(title_name)
            pdata["owned_titles"] = owned_titles
            pdata["shards"] = shards - total_cost
            if shop_item.item_id not in purchased:
                purchased[shop_item.item_id] = {}
            purchased[shop_item.item_id]["event_total"] = event_bought + quantity
            purchased[shop_item.item_id][f"daily_{today_str}"] = daily_bought + quantity
            pdata["purchased"] = purchased
            cls._set_player_data(player, pdata)
            return True, (
                f"兑换成功! 获得限定称号「{title_name}」\n"
                f"已自动装备为当前称号\n"
                f"💡 使用【切换称号】查看和切换已有称号\n"
                f"🔮 剩余碎片: {pdata['shards']}"
            )

        # 特殊处理: 永久属性丹(使用VIPEquipmentBonus记录,确保轮回后保留)
        attr_items = {
            "knocker_bone_elixir": {"attack": 2, "defense": 2},
            "knocker_wish_elixir": {"agility": 2, "luck": 2},
            "knocker_silence_elixir": {"max_hp": 3, "max_mp": 3},
        }
        if shop_item.item_id in attr_items:
            from ..models.vip_equipment_bonus import VIPEquipmentBonus

            attrs = attr_items[shop_item.item_id]

            # 使用VIPEquipmentBonus表持久化,确保轮回后不会丢失
            vip_bonus = await VIPEquipmentBonus.get_or_create(session, player.id)
            for attr, val in attrs.items():
                total_add = val * quantity
                # 记录到VIPEquipmentBonus表
                vip_bonus.add_bonus(attr, total_add)
                # 同时增加当前属性
                current = getattr(player, attr, 0)
                setattr(player, attr, current + total_add)

            session.add(vip_bonus)  # 确保保存

            pdata["shards"] = shards - total_cost
            if shop_item.item_id not in purchased:
                purchased[shop_item.item_id] = {}
            purchased[shop_item.item_id]["event_total"] = event_bought + quantity
            purchased[shop_item.item_id][f"daily_{today_str}"] = daily_bought + quantity
            pdata["purchased"] = purchased
            cls._set_player_data(player, pdata)

            attr_text = ", ".join(f"{k}+{v * quantity}" for k, v in attrs.items())
            return True, f"兑换成功! 永久属性提升: {attr_text} (轮回后保留)\n🔮 剩余碎片: {pdata['shards']}"

        # 通用物品: 添加到背包
        try:
            await ItemInstance.add_item(session, player.id, shop_item.item_id, quantity)
        except ValueError as e:
            return False, f"兑换失败: {str(e)}"

        # 扣除碎片并记录购买
        pdata["shards"] = shards - total_cost
        if shop_item.item_id not in purchased:
            purchased[shop_item.item_id] = {}
        purchased[shop_item.item_id]["event_total"] = event_bought + quantity
        purchased[shop_item.item_id][f"daily_{today_str}"] = daily_bought + quantity
        pdata["purchased"] = purchased
        cls._set_player_data(player, pdata)

        return True, f"兑换成功! 获得 {item_name} x{quantity}\n🔮 剩余碎片: {pdata['shards']}"

    # ==================== 鬼域瞬移 ====================

    @classmethod
    def handle_teleport(cls, session, player: Player, target_x: int, target_y: int) -> Tuple[bool, str]:
        """处理鬼域瞬移

        Args:
            session: 数据库会话(用于标记player对象需要更新)
            player: 玩家对象
            target_x: 目标X坐标
            target_y: 目标Y坐标

        Returns:
            (成功, 结果消息)
        """
        if not cls.is_active():
            return False, "活动未开启，无法使用鬼域瞬移"

        # 检查是否在大都会
        if player.is_in_dungeon():
            return False, "你正在诡域中，无法使用鬼域瞬移"

        # 检查HP
        if player.hp <= 0:
            return False, "你已重伤倒地，无法使用鬼域瞬移"

        # 检查坐标范围
        if not (-TELEPORT_COORD_RANGE <= target_x <= TELEPORT_COORD_RANGE and
                -TELEPORT_COORD_RANGE <= target_y <= TELEPORT_COORD_RANGE):
            return False, f"坐标超出范围，必须在 {-TELEPORT_COORD_RANGE}~{TELEPORT_COORD_RANGE} 内"

        # 检查曼哈顿距离
        px = player.real_world_x or player.x or 0
        py = player.real_world_y or player.y or 0
        distance = abs(target_x - px) + abs(target_y - py)
        if distance > TELEPORT_MAX_DISTANCE:
            return False, f"距离过远! 曼哈顿距离(x距离+y距离)不能超过{TELEPORT_MAX_DISTANCE} 格，当前{distance} 格)"

        # 检查冷却
        pdata = cls._get_player_data(player)
        last_tp = pdata.get("last_teleport", 0)
        now = time.time()
        if now - last_tp < TELEPORT_COOLDOWN:
            remaining = int(TELEPORT_COOLDOWN - (now - last_tp))
            return False, f"瞬移冷却中，还需 {remaining} 秒"

        # 执行瞬移
        player.x = target_x
        player.y = target_y
        player.real_world_x = target_x
        player.real_world_y = target_y

        # 记录冷却
        pdata["last_teleport"] = now
        cls._set_player_data(player, pdata)

        # 关键修复: 标记player对象需要更新,确保坐标和冷却时间都保存到数据库
        session.add(player)

        text = TELEPORT_TEXT.format(x=target_x, y=target_y)
        return True, text

    # ==================== 玩家活动数据 ====================

    @classmethod
    def _get_player_data(cls, player: Player) -> dict:
        """获取玩家活动数据(从extra_attrs)"""
        extra = player.extra_attrs if hasattr(player, 'extra_attrs') and player.extra_attrs else {}
        return extra.get("knocker_event", {})

    @classmethod
    def _set_player_data(cls, player: Player, data: dict):
        """设置玩家活动数据(写入extra_attrs)"""
        from sqlalchemy.orm.attributes import flag_modified

        if not hasattr(player, 'extra_attrs') or player.extra_attrs is None:
            player.extra_attrs = {}
        # 触发SQLAlchemy变更检测
        extra = dict(player.extra_attrs)
        extra["knocker_event"] = data
        player.extra_attrs = extra

        # 显式标记JSON字段已修改,确保SQLAlchemy跟踪变化
        flag_modified(player, "extra_attrs")

    # ==================== 辅助方法 ====================

    @classmethod
    async def _send_system_message(cls, session, content: str):
        """发送系统消息到留言板（全服可见）

        Args:
            session: 数据库会话
            content: 消息内容
        """
        try:
            # 使用特殊ID "SYSTEM" 作为系统发送者
            msg = WorldMessage(
                player_id="SYSTEM",
                recipient_id=None,  # None表示世界留言板（全服可见）
                content=content,
                created_at=datetime.now(),
            )
            session.add(msg)
            await session.flush()
            logger.info(f"[叩门活动] 系统消息已发送到留言板: {content[:50]}...")
        except Exception as e:
            logger.error(f"[叩门活动] 发送系统消息失败: {e}")

    @classmethod
    def _get_level_material(cls, player_level: int) -> Optional[str]:
        """根据玩家等级获取对应材料ID"""
        # 按等级段选材料(对应items.yaml中已有的材料ID)
        if player_level <= 20:
            materials = ["bone_fragment", "ash_powder", "spirit_bone", "iron_rust",
                         "ghost_tears", "rotten_core", "cursed_silk", "grave_soil"]
        elif player_level <= 50:
            materials = ["yin_essence", "nightmare_silk", "drowned_scale",
                         "corrupted_bandage", "school_bell_fragment", "withered_flower"]
        elif player_level <= 100:
            materials = ["flesh_crystal", "soul_crystal", "cursed_mirror_shard", "phantom_thread"]
        else:
            materials = ["demon_heart", "void_essence", "wanted_poster", "medical_record"]

        return random.choice(materials) if materials else None

    @classmethod
    def get_player_title(cls, player: Player) -> Optional[str]:
        """获取玩家活动称号(如果有)"""
        pdata = cls._get_player_data(player)
        return pdata.get("title")

    @classmethod
    def get_owned_titles(cls, player: Player) -> List[str]:
        """获取玩家已拥有的所有称号"""
        pdata = cls._get_player_data(player)
        owned = pdata.get("owned_titles", [])
        # 兼容旧数据：如果有title但owned_titles为空，补充进去
        current_title = pdata.get("title")
        if current_title and current_title not in owned:
            owned.append(current_title)
        return owned

    @classmethod
    def handle_title_switch(cls, player: Player, title_name: str) -> Tuple[bool, str]:
        """切换称号

        Args:
            player: 玩家对象
            title_name: 要切换的称号名，空字符串表示卸下

        Returns:
            (成功, 结果消息)
        """
        pdata = cls._get_player_data(player)
        owned_titles = cls.get_owned_titles(player)

        if not owned_titles:
            return False, "你还没有任何称号，请在【活动商店】兑换"

        # 卸下称号
        if not title_name:
            if not pdata.get("title"):
                return False, "当前没有装备称号"
            pdata["title"] = ""
            cls._set_player_data(player, pdata)
            return True, "已卸下称号"

        # 检查是否拥有该称号
        if title_name not in owned_titles:
            titles_str = "、".join(f"「{t}」" for t in owned_titles)
            return False, f"你没有称号「{title_name}」\n已拥有: {titles_str}"

        # 检查是否已经是当前称号
        if pdata.get("title") == title_name:
            return False, f"「{title_name}」已经是你的当前称号"

        # 切换称号
        pdata["title"] = title_name
        cls._set_player_data(player, pdata)
        return True, f"称号已切换为「{title_name}」"

    @classmethod
    def handle_title_list(cls, player: Player) -> str:
        """查看已拥有的称号列表"""
        owned_titles = cls.get_owned_titles(player)
        pdata = cls._get_player_data(player)
        current_title = pdata.get("title", "")

        lines = [
            "🏅 我的称号收藏",
            "━━━━━━━━━━━━━",
        ]

        if not owned_titles:
            lines.append("暂无称号，请在【活动商店】兑换")
        else:
            for t in owned_titles:
                mark = " ◀ 当前" if t == current_title else ""
                lines.append(f"  🏷️ 「{t}」{mark}")

        lines.extend([
            "━━━━━━━━━━━━━",
            "💡 【切换称号 称号名】切换展示",
            "💡 【卸下称号】取消展示",
        ])

        return "\n".join(lines)

    @classmethod
    def get_ghost_narrative(cls, npc: NPC) -> Optional[str]:
        """获取活动鬼怪的叙事文本

        Args:
            npc: NPC对象

        Returns:
            叙事文本,如果不是活动鬼怪则返回None
        """
        if not cls.is_active():
            return None

        extra = npc.extra_data or {}
        event_id = extra.get("knocker_event_id")
        if not event_id or event_id not in cls._active_events:
            return None

        active_event = cls._active_events[event_id]
        return active_event.narrative


# 启动时加载状态
KnockerEventService._load_state()
