"""导航随机事件系统

导航到达时根据路程触发随机事件（奖惩混合），统一展示。
- 路程事件：每30-80格随机间隔触发一次
- 到达事件：50%概率额外触发
- 使用确定性种子保证同一次导航结果不变
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import List, Optional

from ..models.player import Player


@dataclass
class NavigationEvent:
    """一次导航事件的结果"""
    icon: str
    description: str
    # 效果
    gold: int = 0           # 正数=获得，负数=损失
    exp: int = 0
    stamina: int = 0        # 咒抗变化
    hp_percent: float = 0   # HP百分比变化（负数=扣血，如-0.08表示扣8%）
    item_id: Optional[str] = None
    item_qty: int = 0


# ==================== 事件模板 ====================

def _good_events(player: Player, rng: random.Random) -> List[dict]:
    """好事模板列表（60%总概率中随机选一个）"""
    gold_amount = rng.randint(100, 500)
    stamina_amount = rng.randint(10, 30)

    # 经验基于玩家等级：低级少给，高级多给，保持"有感知"
    base_exp = max(20, player.level * 3)
    exp_amount = rng.randint(base_exp, base_exp * 2)

    return [
        {
            "icon": "🍀",
            "description": f"路过一座荒废道观，在香炉下发现了 {gold_amount} 金币",
            "gold": gold_amount,
            "weight": 30,
        },
        {
            "icon": "🌿",
            "description": "在路旁发现了一株灵草",
            "item_id": "_random_material_",  # 特殊标记，运行时替换
            "item_qty": rng.randint(1, 3),
            "weight": 20,
        },
        {
            "icon": "⚔️",
            "description": f"偶遇游方散修切磋，你从中领悟，获得 {exp_amount} 经验",
            "exp": exp_amount,
            "weight": 20,
        },
        {
            "icon": "💧",
            "description": f"发现一处灵泉，饮用后恢复了 {stamina_amount} 点咒抗",
            "stamina": stamina_amount,
            "weight": 15,
        },
        {
            "icon": "🎁",
            "description": f"遇到一位感恩的商旅，赠你 {gold_amount + 100} 金币作为谢礼",
            "gold": gold_amount + 100,
            "weight": 15,
        },
    ]


def _bad_events(player: Player, rng: random.Random) -> List[dict]:
    """坏事模板列表（40%总概率中随机选一个）"""
    gold_loss = rng.randint(50, 200)
    stamina_loss = rng.randint(2, 5)
    hp_loss_pct = rng.randint(5, 10) / 100.0  # 5%-10%

    return [
        {
            "icon": "💰",
            "description": f"遭遇山贼伏击，被抢走了 {gold_loss} 金币",
            "gold": -gold_loss,
            "weight": 30,
        },
        {
            "icon": "🌫️",
            "description": f"误入迷雾区域，被诡异气息侵蚀，损失了 {int(hp_loss_pct*100)}% 生命值",
            "hp_percent": -hp_loss_pct,
            "weight": 25,
        },
        {
            "icon": "👻",
            "description": f"途经阴气汇聚之地，咒抗被削弱了 {stamina_loss} 点",
            "stamina": -stamina_loss,
            "weight": 25,
        },
        {
            "icon": "🐺",
            "description": "遭遇野兽袭击，虽然击退了它，但衣物有些破损",
            "weight": 20,
        },
    ]


def _resolve_random_material(rng: random.Random) -> tuple[Optional[str], str]:
    """解析随机材料，返回 (item_id, item_name)"""
    from ..config import config
    from .dungeon_battle import get_materials_by_rarity

    # 80%白色，20%绿色
    rarity = "white" if rng.random() < 0.8 else "green"
    materials = get_materials_by_rarity(rarity)

    if not materials:
        return None, ""

    item_id = rng.choice(materials)
    item_config = config.items_config["by_id"].get(item_id)
    if not item_config:
        return None, ""

    return item_id, item_config.name


def _pick_event(player: Player, rng: random.Random) -> NavigationEvent:
    """根据概率选一个事件"""
    is_good = rng.random() < 0.6

    templates = _good_events(player, rng) if is_good else _bad_events(player, rng)

    # 加权随机
    weights = [t["weight"] for t in templates]
    chosen = rng.choices(templates, weights=weights, k=1)[0]

    # 处理随机材料
    item_id = chosen.get("item_id")
    item_qty = chosen.get("item_qty", 0)
    description = chosen["description"]

    if item_id == "_random_material_":
        real_item_id, item_name = _resolve_random_material(rng)
        if real_item_id:
            item_id = real_item_id
            description = f"在路旁发现了一株灵草，获得【{item_name}】×{item_qty}"
        else:
            # 回退为金币奖励
            fallback_gold = rng.randint(100, 300)
            item_id = None
            item_qty = 0
            description = f"在路旁发现了一些散落的金币，共 {fallback_gold} 枚"
            chosen["gold"] = fallback_gold

    return NavigationEvent(
        icon=chosen["icon"],
        description=description,
        gold=chosen.get("gold", 0),
        exp=chosen.get("exp", 0),
        stamina=chosen.get("stamina", 0),
        hp_percent=chosen.get("hp_percent", 0),
        item_id=item_id if item_id != "_random_material_" else None,
        item_qty=item_qty,
    )


def _make_seed(player_id: str, target_x: int, target_y: int, distance: float) -> int:
    """生成确定性种子（基于导航的不可变参数）"""
    raw = f"{player_id}:{target_x}:{target_y}:{distance:.2f}"
    return int(hashlib.md5(raw.encode()).hexdigest()[:8], 16)


def generate_navigation_events(
    player: Player,
    distance: float,
    target_x: int,
    target_y: int,
) -> List[NavigationEvent]:
    """根据距离生成导航事件列表

    Args:
        player: 玩家对象
        distance: 导航总距离
        target_x: 目标X坐标
        target_y: 目标Y坐标

    Returns:
        事件列表
    """
    seed = _make_seed(player.id, target_x, target_y, distance)
    rng = random.Random(seed)
    events: List[NavigationEvent] = []

    # 路程事件：每30-80格触发一次
    if distance >= 30:
        traveled = 0.0
        next_trigger = rng.randint(30, 80)
        while traveled + next_trigger <= distance:
            traveled += next_trigger
            events.append(_pick_event(player, rng))
            next_trigger = rng.randint(30, 80)

    # 到达事件：50%概率
    if rng.random() < 0.5:
        events.append(_pick_event(player, rng))

    return events


async def apply_navigation_events(
    session,
    player: Player,
    events: List[NavigationEvent],
) -> None:
    """将事件效果应用到玩家"""
    from ..models.inventory import ItemInstance

    for ev in events:
        if ev.gold != 0:
            player.gold = max(0, player.gold + ev.gold)

        if ev.exp > 0:
            player.exp += ev.exp

        if ev.stamina != 0:
            player.stamina = max(0, player.stamina + ev.stamina)
            # 不超过上限
            if hasattr(player, "max_stamina") and player.stamina > player.max_stamina:
                player.stamina = player.max_stamina

        if ev.hp_percent != 0:
            hp_change = int(player.max_hp * ev.hp_percent)
            player.hp = max(1, player.hp + hp_change)  # 至少保留1HP

        if ev.item_id and ev.item_qty > 0:
            try:
                await ItemInstance.add_item(session, player.id, ev.item_id, ev.item_qty)
            except (ValueError, Exception):
                # 背包满或物品不存在，转换为金币
                player.gold += 150


def format_navigation_events(events: List[NavigationEvent]) -> str:
    """格式化事件为展示文本"""
    if not events:
        return ""

    lines = ["📖 途中见闻："]
    for ev in events:
        lines.append(f"  {ev.icon} {ev.description}")

    return "\n".join(lines)
