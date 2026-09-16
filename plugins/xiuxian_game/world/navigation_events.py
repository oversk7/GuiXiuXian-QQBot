"""导航随机事件系统

普通事件在导航到达时结算；灵异事件在途经遭遇位置时结算。
- 路程事件：每30-80格随机间隔触发一次
- 到达事件：50%概率额外触发
- 使用确定性种子保证同一次导航结果不变
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from ..models.player import Player
from ..utils_markdown import color_text

# 灵泉恢复咒抗每日限制
_STAMINA_RESTORE_DAILY_LIMIT = 3
_stamina_restore_counter: Dict[str, tuple[str, int]] = {}  # {player_id: (date_str, count)}


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
    is_supernatural: bool = False
    fatal: bool = False


# ==================== 事件模板 ====================

def _good_events(player: Player, rng: random.Random) -> List[dict]:
    """好事模板列表（60%总概率中随机选一个）"""
    gold_amount = rng.randint(100, 500)
    stamina_amount = rng.randint(2, 5)

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
            "weight": 2,
            "_stamina_restore": True,  # 标记，用于每日限次检查
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
    hp_loss_pct = rng.randint(5, 10) / 100.0  # 5%-10%

    return [
        {
            "icon": "💰",
            "description": f"遭遇山贼伏击，被抢走了 {gold_loss} 金币",
            "gold": -gold_loss,
            "weight": 35,
        },
        {
            "icon": "🌫️",
            "description": f"误入迷雾区域，被诡异气息侵蚀，损失了 {int(hp_loss_pct*100)}% 生命值",
            "hp_percent": -hp_loss_pct,
            "weight": 35,
        },
        {
            "icon": "🐺",
            "description": "遭遇野兽袭击，虽然击退了它，但衣物有些破损",
            "weight": 29,
        },
        {
            "icon": "👻",
            "description": (
                "灵异事件·保险鬼\n"
                "一个穿西装的男人走过来，递给你一张保单。\n"
                "“你好，我是幸福保险公司的。”\n"
                "“购买我们公司保险的人，都会得到幸福。”\n"
                "你摆摆手：“我没钱。”\n"
                "男人脸上的笑容没了。\n"
                "“你的意思是，你不打算买保险是吗？”\n"
                "“我没钱。”你又说了一遍。"
            ),
            "is_supernatural": True,
            "weight": 1,
        },
    ]


def _resolve_random_material(rng: random.Random) -> tuple[Optional[str], str]:
    """解析随机材料，返回 (item_id, item_name)"""
    from ..config import config
    from .dungeon_generation_service import get_materials_by_rarity

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


def _check_stamina_restore_limit(player_id: str) -> bool:
    """检查灵泉恢复咒抗是否达到每日上限"""
    today = date.today().isoformat()
    if player_id in _stamina_restore_counter:
        d, count = _stamina_restore_counter[player_id]
        if d == today:
            return count >= _STAMINA_RESTORE_DAILY_LIMIT
    return False


def _increment_stamina_restore(player_id: str):
    """记录一次灵泉恢复"""
    today = date.today().isoformat()
    if player_id in _stamina_restore_counter:
        d, count = _stamina_restore_counter[player_id]
        if d == today:
            _stamina_restore_counter[player_id] = (today, count + 1)
        else:
            _stamina_restore_counter[player_id] = (today, 1)
    else:
        _stamina_restore_counter[player_id] = (today, 1)


def _pick_event(player: Player, rng: random.Random) -> NavigationEvent:
    """根据概率选一个事件"""
    is_good = rng.random() < 0.6

    templates = _good_events(player, rng) if is_good else _bad_events(player, rng)

    # 如果灵泉恢复达到每日上限，移除该选项
    if _check_stamina_restore_limit(player.id):
        templates = [t for t in templates if not t.get("_stamina_restore")]
        if not templates:
            # 极端情况：所有好事都被过滤了（不会发生，但防御性处理）
            templates = _bad_events(player, rng)

    # 加权随机
    weights = [t["weight"] for t in templates]
    chosen = rng.choices(templates, weights=weights, k=1)[0]

    # 如果选中了灵泉恢复，记录次数
    if chosen.get("_stamina_restore"):
        _increment_stamina_restore(player.id)

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

    is_supernatural = chosen.get("is_supernatural", False)
    fatal = is_supernatural and rng.random() < 0.9
    if is_supernatural:
        if fatal:
            description += (
                "\n你想绕开他，嘴角却自己往上翘了起来。"
                "\n你伸手去抢他的笔，嘴里不停地说："
                "\n“买保险，嘻嘻嘻……我要买保险！”"
                "\n“我要买一百年保险！哈哈哈哈哈哈哈哈哈！”"
                "\n你笑得浑身发抖，连气都喘不上来。"
                "\n笔尖划了几下，你直挺挺地倒在了路边。"
                "\n男人收好保单，拨通了下一个号码。"
                "\n“你好，我是幸福保险公司的……”"
                "\n你已当场死亡，导航中止。"
            )
        else:
            description += (
                "\n你正想再解释，他的手机响了。"
                "\n他低头接电话，你赶紧走开。"
                "\n过了街口你才敢回头，他还站在那里。"
                "\n它刚才卖的是生存保险，买保险的人必须活到到规定时间才能够领取保险金。假如买保险的人中途死亡，保险金将与他无关，谁让他活不到约定好的年龄呢。"
                "\n手心里全是汗。你没敢停，继续赶路。"
            )

    return NavigationEvent(
        icon=chosen["icon"],
        description=description,
        gold=chosen.get("gold", 0),
        exp=chosen.get("exp", 0),
        stamina=chosen.get("stamina", 0),
        hp_percent=chosen.get("hp_percent", 0),
        item_id=item_id if item_id != "_random_material_" else None,
        item_qty=item_qty,
        is_supernatural=is_supernatural,
        fatal=fatal,
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
    """根据距离生成到达时结算的普通事件列表

    Args:
        player: 玩家对象
        distance: 导航总距离
        target_x: 目标X坐标
        target_y: 目标Y坐标

    Returns:
        事件列表
    """
    events = []
    for _, rng in _navigation_checkpoints(player.id, distance, target_x, target_y):
        event = _pick_event(player, rng)
        if not event.is_supernatural:
            events.append(event)
    return events


def _navigation_checkpoints(player_id: str, distance: float, target_x: int, target_y: int):
    seed = _make_seed(player_id, target_x, target_y, distance)
    rng = random.Random(seed)
    checkpoints = []
    traveled = 0.0
    next_trigger = rng.randint(30, 80)
    while traveled + next_trigger <= distance and len(checkpoints) < 5:
        traveled += next_trigger
        checkpoints.append(traveled)
        next_trigger = rng.randint(30, 80)
    if rng.random() < 0.5:
        checkpoints.append(distance)
    for index, checkpoint in enumerate(checkpoints):
        yield checkpoint, random.Random(f"{seed}:{index}")


def generate_supernatural_encounters(
    player: Player, distance: float, target_x: int, target_y: int,
) -> List[tuple[float, NavigationEvent]]:
    """生成固定的灵异遭遇位置和生死结果，每趟导航至多一次。"""
    encounters = []
    for checkpoint, rng in _navigation_checkpoints(player.id, distance, target_x, target_y):
        state = rng.getstate()
        if rng.random() < 0.6:
            continue
        rng.setstate(state)
        event = _pick_event(player, rng)
        if event.is_supernatural:
            encounters.append((checkpoint, event))
            break
    return encounters


async def apply_navigation_events(
    session,
    player: Player,
    events: List[NavigationEvent],
) -> None:
    """将事件效果应用到玩家"""
    from ..models.inventory import ItemInstance

    for ev in events:
        if ev.fatal:
            player.hp = 0
            player.dungeon_kill_streak = 0
            break

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
        description_lines = ev.description.split("\n")
        if ev.is_supernatural:
            description_lines = [
                line[start:start + 15]
                for line in description_lines
                for start in range(0, max(1, len(line)), 15)
            ]
            description_lines = [color_text(line, "#FF5C6C") for line in description_lines]
        lines.append(f"  {ev.icon} {description_lines[0]}")
        lines.extend(f"  {line}" for line in description_lines[1:])
        if ev.fatal:
            break

    return "\n".join(lines)
