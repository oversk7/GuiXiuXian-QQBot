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
    async def refresh_events(cls, session) -> Optional[str]:
        """刷新诡事点, 返回全服播报文本"""
        if not cls.is_active():
            return None

        # 清理已过期或已死亡的诡事
        cls._cleanup_expired()

        # 检查是否达到上限
        alive_count = sum(1 for e in cls._active_events.values() if e.is_alive and not e.is_expired())
        if alive_count >= MAX_ACTIVE_EVENTS:
            cls._last_refresh_time = time.time()
            return None

        # 计算本波生成数量
        max_spawn = MAX_ACTIVE_EVENTS - alive_count
        spawn_count = min(random.randint(*SPAWN_COUNT_RANGE), max_spawn)
        if spawn_count <= 0:
            cls._last_refresh_time = time.time()
            return None

        # 按权重随机选择类型
        type_ids = list(GHOST_EVENT_TYPES.keys())
        weights = [GHOST_EVENT_TYPES[t].weight for t in type_ids]

        new_events: List[ActiveGhostEvent] = []
        for _ in range(spawn_count):
            type_id = random.choices(type_ids, weights=weights, k=1)[0]
            ghost_type = GHOST_EVENT_TYPES[type_id]

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

            # 生成唯一ID
            cls._event_counter += 1
            event_id = f"knocker_{cls._event_counter}"
            npc_id = f"knocker_ghost_{cls._event_counter}"

            # 计算鬼怪属性(基于全服活跃玩家中位等级)
            median_level = await cls._get_median_player_level(session)
            base_stats = DailyTaskService._calculate_enemy_stats(median_level)
            stats = {
                "hp": int(base_stats["hp"] * ghost_type.hp_mult),
                "attack": int(base_stats["attack"] * ghost_type.atk_mult),
                "defense": int(base_stats["defense"] * ghost_type.def_mult),
                "agility": int(base_stats["agility"] * ghost_type.agi_mult),
            }

            # 创建NPC
            # 先查找或创建地点
            from ..world.location_service_new import LocationService
            from ..infrastructure.repositories.location_repository import LocationRepository
            from ..infrastructure.repositories.npc_repository import NPCRepository

            loc_repo = LocationRepository(session)
            npc_repo = NPCRepository(session)
            loc_service = LocationService(loc_repo)
            npc_service_inst = __import__(
                "plugins.xiuxian_game.world.npc_service_new",
                fromlist=["NPCService"]
            )

            # 查找或创建地点
            location_id_str = f"knocker_loc_{x}_{y}"
            location = await loc_service.get_location_by_id(location_id_str)
            if not location:
                location = await loc_service.create_location(
                    location_id=location_id_str,
                    name=f"{city}({x},{y})",
                    x=x, y=y,
                    location_type="normal",
                    description="除夕夜出现诡象的地点...",
                    region="大都会"
                )

            # 创建鬼怪NPC
            npc = NPC.create_ghost(
                npc_id=npc_id,
                name=npc_display_name,
                location_id=location.id,
                level=median_level,
                hp=stats["hp"],
                attack=stats["attack"],
                defense=stats["defense"],
                agility=stats["agility"],
            )
            npc.extra_data = {
                "knocker_event_id": event_id,
                "knocker_type": type_id,
                "knocker_city": city,
                "shard_reward": ghost_type.shard_reward,
                "reward_mult": ghost_type.reward_mult,
                "material_drop_rate": ghost_type.material_drop_rate,
            }
            if ghost_type.special_mechanic:
                npc.extra_data["special_mechanic"] = ghost_type.special_mechanic

            session.add(npc)
            await session.flush()

            # 添加到内存缓存
            active_event = ActiveGhostEvent(
                event_id=event_id,
                type_id=type_id,
                npc_id=npc_id,
                npc_name=npc_display_name,
                x=x, y=y,
                city_name=city,
                narrative=narrative,
                spawn_time=time.time(),
            )
            cls._active_events[event_id] = active_event
            new_events.append(active_event)

        cls._last_refresh_time = time.time()
        cls._save_state()

        if not new_events:
            return None

        # 构建播报文本
        event_list_lines = []
        for e in new_events:
            tier_icon = {"basic": "🔹", "medium": "🔸", "elite": "⚡", "boss": "💀"}.get(
                e.type_config.tier, "🔹"
            )
            event_list_lines.append(f"· {tier_icon}{e.type_config.name} — ({e.x},{e.y})")

        broadcast = BROADCAST_SPAWN.format(
            count=len(new_events),
            event_list="\n".join(event_list_lines) + "\n",
        )
        return broadcast

    @classmethod
    def _cleanup_expired(cls):
        """清理已过期或已死亡的诡事"""
        to_remove = []
        for eid, ev in cls._active_events.items():
            if not ev.is_alive or ev.is_expired():
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
    def get_active_events_list(cls) -> List[ActiveGhostEvent]:
        """获取当前存活的诡事列表"""
        cls._cleanup_expired()
        return [e for e in cls._active_events.values() if e.is_alive]

    @classmethod
    def get_event_status(cls, player) -> str:
        """获取活动状态文本(含个人进度)"""
        if not cls.is_active():
            return "━━━━━━━━━━━━━\n除夕叩门活动当前未开启\n━━━━━━━━━━━━━"

        # 获取玩家活动数据
        pdata = cls._get_player_data(player)
        shards = pdata.get("shards", 0)
        kills = pdata.get("kills", 0)

        # 当前诡事列表
        active_events = cls.get_active_events_list()

        # 按距离排序(基于玩家坐标)
        px, py = player.real_world_x or 0, player.real_world_y or 0

        def distance(ev):
            return abs(ev.x - px) + abs(ev.y - py)

        active_events.sort(key=distance)

        lines = [
            "咚...咚...咚...",
            "━━ 除夕叩门·缉邪令 ━━",
            f"⏰ 剩余时间: {cls.get_remaining_time()}",
            f"🔮 封门符碎片: {shards}",
            f"💀 已解决诡事: {kills}",
            "",
        ]

        if active_events:
            lines.append(f"📍 当前诡事点 ({len(active_events)}个):")
            for ev in active_events[:15]:
                tier_icon = {"basic": "🔹", "medium": "🔸", "elite": "⚡", "boss": "💀"}.get(
                    ev.type_config.tier, "🔹"
                )
                dist = abs(ev.x - px) + abs(ev.y - py)
                lines.append(f"  {tier_icon}{ev.npc_name} ({ev.x},{ev.y}) 距{dist}格")
        else:
            lines.append("📍 当前无活跃诡事点")
            lines.append(f"   下波刷新于{REFRESH_INTERVAL_MINUTES}分钟内")

        lines.extend([
            "",
            "━━━━━━━━━━━━━",
            "💡 【鬼域瞬移 x y】快速移动",
            "💡 【攻击 NPC名】击杀鬼怪",
            "💡 【活动商店】碎片兑换奖励",
            "💡 【叩门排行】查看排名",
        ])

        return "\n".join(lines)

    # ==================== 击杀回调 ====================

    @classmethod
    def is_knocker_npc(cls, npc: NPC) -> bool:
        """检查NPC是否为活动鬼怪"""
        if not cls.is_active():
            return False
        extra = npc.extra_data or {}
        return "knocker_event_id" in extra

    @classmethod
    async def on_ghost_killed(cls, session, player: Player, npc: NPC) -> List[str]:
        """活动鬼怪被击杀的回调

        Returns:
            附加的结果行列表
        """
        if not cls.is_active():
            return []

        extra = npc.extra_data or {}
        event_id = extra.get("knocker_event_id")
        type_id = extra.get("knocker_type")
        shard_reward = extra.get("shard_reward", 1)
        reward_mult = extra.get("reward_mult", 1.0)
        material_drop_rate = extra.get("material_drop_rate", 0.05)

        if not event_id or not type_id:
            return []

        ghost_type = GHOST_EVENT_TYPES.get(type_id)
        if not ghost_type:
            return []

        result_lines = []

        # 标记诡事为已完成
        if event_id in cls._active_events:
            cls._active_events[event_id].is_alive = False

        # 计算奖励
        exp_reward = int((BASE_EXP + player.level * EXP_PER_LEVEL) * reward_mult)
        gold_reward = int((BASE_GOLD + player.level * GOLD_PER_LEVEL) * reward_mult)

        # 发放经验和金币
        player.exp += exp_reward
        player.gold += gold_reward

        # 发放碎片(更新player活动数据)
        pdata = cls._get_player_data(player)
        pdata["shards"] = pdata.get("shards", 0) + shard_reward
        pdata["kills"] = pdata.get("kills", 0) + 1
        cls._set_player_data(player, pdata)

        result_lines.append("")
        result_lines.append("🎆 除夕叩门·缉邪奖励")
        result_lines.append(f"  ✨ 经验 +{exp_reward}")
        result_lines.append(f"  💰 金币 +{gold_reward}")
        result_lines.append(f"  🔮 封门符碎片 +{shard_reward}")

        # 材料掉落判定
        if random.random() < material_drop_rate:
            material_id = cls._get_level_material(player.level)
            if material_id:
                try:
                    await ItemInstance.add_item(session, player.id, material_id, 1)
                    from ..config import config
                    item_cfg = config.items_config["by_id"].get(material_id)
                    if item_cfg:
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

        lines = [
            "🏪 除夕叩门·活动商店",
            f"🔮 封门符碎片: {shards}",
            "━━━━━━━━━━━━━",
        ]

        current_category = ""
        today_str = datetime.now().strftime("%Y%m%d")

        for item in SHOP_ITEMS:
            # 分区标题
            if item.category != current_category:
                current_category = item.category
                lines.append(f"\n【{current_category}】")

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

            status = "售罄" if sold_out else f"{item.shard_cost}碎片"
            lines.append(f"  {'❌' if sold_out else '·'} {item.name} — {status} [{limit_text}]")

        lines.extend([
            "",
            "━━━━━━━━━━━━━",
            "💡 【活动商店 兑换 物品名】购买",
            "💡 【活动商店 兑换 物品名 数量】批量购买",
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

        # 特殊处理: 称号
        if shop_item.item_id == "knocker_title":
            # 称号直接记录到活动数据
            pdata["title"] = "封门人"
            pdata["shards"] = shards - total_cost
            if shop_item.item_id not in purchased:
                purchased[shop_item.item_id] = {}
            purchased[shop_item.item_id]["event_total"] = event_bought + quantity
            purchased[shop_item.item_id][f"daily_{today_str}"] = daily_bought + quantity
            pdata["purchased"] = purchased
            cls._set_player_data(player, pdata)
            return True, f"兑换成功! 获得限定称号「封门人」\n🔮 剩余碎片: {pdata['shards']}"

        # 特殊处理: 永久属性丹(直接加属性)
        attr_items = {
            "knocker_bone_elixir": {"attack": 2, "defense": 2},
            "knocker_wish_elixir": {"agility": 2, "luck": 2},
            "knocker_silence_elixir": {"max_hp": 3, "max_mp": 3},
        }
        if shop_item.item_id in attr_items:
            attrs = attr_items[shop_item.item_id]
            for attr, val in attrs.items():
                current = getattr(player, attr, 0)
                setattr(player, attr, current + val * quantity)

            pdata["shards"] = shards - total_cost
            if shop_item.item_id not in purchased:
                purchased[shop_item.item_id] = {}
            purchased[shop_item.item_id]["event_total"] = event_bought + quantity
            purchased[shop_item.item_id][f"daily_{today_str}"] = daily_bought + quantity
            pdata["purchased"] = purchased
            cls._set_player_data(player, pdata)

            attr_text = ", ".join(f"{k}+{v * quantity}" for k, v in attrs.items())
            return True, f"兑换成功! 永久属性提升: {attr_text}\n🔮 剩余碎片: {pdata['shards']}"

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
    def handle_teleport(cls, player: Player, target_x: int, target_y: int) -> Tuple[bool, str]:
        """处理鬼域瞬移

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
            return False, f"距离过远! 曼哈顿距离 {distance} 格(上限 {TELEPORT_MAX_DISTANCE} 格)"

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
        if not hasattr(player, 'extra_attrs') or player.extra_attrs is None:
            player.extra_attrs = {}
        # 触发SQLAlchemy变更检测
        extra = dict(player.extra_attrs)
        extra["knocker_event"] = data
        player.extra_attrs = extra

    # ==================== 辅助方法 ====================

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


# 启动时加载状态
KnockerEventService._load_state()
