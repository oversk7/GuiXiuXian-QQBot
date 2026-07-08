"""
下位世界业务逻辑服务
"""
import json
from datetime import datetime, timedelta
from typing import Tuple, Optional

from ..models.lower_world import LowerWorldStronghold
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..utils_markdown import cmd
from .hero_generator import generate_hero, hero_to_json, hero_from_json

# 波次间隔（2小时）
WAVE_INTERVAL_HOURS = 2
# 英雄等待超时（4小时后自动撤退）
HERO_TIMEOUT_HOURS = 4
# 封印时长（24小时）
SEAL_DURATION_HOURS = 12
# 战斗冷却（5分钟）
BATTLE_COOLDOWN_MINUTES = 5


def get_wave_reward(wave_number: int) -> int:
    """根据波次返回天灾点奖励"""
    if wave_number <= 5:
        return 5
    elif wave_number <= 10:
        return 10
    elif wave_number <= 20:
        return 20
    else:
        return 30


async def get_or_create_stronghold(uow: UnitOfWork, player_id: str) -> Tuple[LowerWorldStronghold, bool]:
    """获取或创建玩家山寨，返回 (山寨对象, 是否刚创建)"""
    stronghold = await uow.lower_world_strongholds.get_by_player_id(player_id)
    if stronghold:
        return stronghold, False

    stronghold = LowerWorldStronghold(
        player_id=player_id,
        calamity_points=0,
        wave_number=1,
        total_waves_won=0,
        created_at=datetime.now(),
    )
    await uow.lower_world_strongholds.create(stronghold)
    return stronghold, True


def is_sealed(stronghold: LowerWorldStronghold) -> Tuple[bool, Optional[timedelta]]:
    """检查是否处于封印状态，返回 (是否封印, 剩余时间)"""
    if not stronghold.sealed_until:
        return False, None
    now = datetime.now()
    if now < stronghold.sealed_until:
        return True, stronghold.sealed_until - now
    return False, None


def has_pending_hero(stronghold: LowerWorldStronghold) -> bool:
    """是否有待挑战的（未超时的）英雄"""
    if not stronghold.pending_hero:
        return False
    if stronghold.next_wave_at:
        timeout = stronghold.next_wave_at + timedelta(hours=HERO_TIMEOUT_HOURS)
        if datetime.now() > timeout:
            return False  # 已超时撤退
    return True


def format_time_remaining(td: timedelta) -> str:
    """将时间差格式化为可读字符串"""
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    if hours > 0:
        return f"{hours}小时{minutes}分"
    return f"{minutes}分钟"


async def schedule_next_wave(uow: UnitOfWork, stronghold: LowerWorldStronghold, player_level: int):
    """为山寨安排下一波英雄（生成英雄数据，设置到达时间）"""
    next_time = datetime.now() + timedelta(hours=WAVE_INTERVAL_HOURS)
    hero = generate_hero(player_level, stronghold.wave_number)
    stronghold.next_wave_at = next_time
    stronghold.pending_hero = hero_to_json(hero)
    uow.session.add(stronghold)


async def process_battle_victory(uow: UnitOfWork, stronghold: LowerWorldStronghold, player_level: int) -> int:
    """
    处理战斗胜利：
    - 增加天灾点
    - 波次+1
    - 清除当前英雄
    - 安排下一波
    返回获得的天灾点数
    """
    points = get_wave_reward(stronghold.wave_number)
    stronghold.calamity_points += points
    stronghold.total_waves_won += 1
    stronghold.wave_number += 1
    stronghold.best_wave = max(stronghold.best_wave or 1, stronghold.wave_number)
    stronghold.pending_hero = None
    stronghold.sealed_until = None
    await schedule_next_wave(uow, stronghold, player_level)
    uow.session.add(stronghold)
    return points


async def process_battle_defeat(uow: UnitOfWork, stronghold: LowerWorldStronghold) -> int:
    """
    处理战斗失败：
    - 封印12小时
    - 波次 -3（最低回到1）
    - 清除当前英雄
    返回降低的波次数
    """
    stronghold.sealed_until = datetime.now() + timedelta(hours=SEAL_DURATION_HOURS)
    old_wave = stronghold.wave_number
    stronghold.wave_number = max(1, stronghold.wave_number - 3)
    wave_dropped = old_wave - stronghold.wave_number
    stronghold.pending_hero = None
    stronghold.next_wave_at = None
    uow.session.add(stronghold)
    return wave_dropped


# ==================== 天灾商店 ====================

SHOP_ITEMS = [
    {
        "id": "cultivate_boost",
        "name": "修炼加速（2小时）",
        "desc": "修炼效率+50%，持续2小时",
        "price": 50,
    },
    {
        "id": "battle_boost",
        "name": "战意加持（1场）",
        "desc": "下一场战斗全属性+10%",
        "price": 30,
    },
    {
        "id": "unseal",
        "name": "解封令",
        "desc": "立即解除封印状态",
        "price": 40,
    },
    {
        "id": "scout_intel",
        "name": "侦查情报（1次）",
        "desc": "查看下一波英雄的详细属性",
        "price": 10,
    },
    {
        "id": "title_calamity",
        "name": "称号「第四天灾」",
        "desc": "永久专属称号，一次性购买",
        "price": 200,
    },
]


def get_shop_display() -> str:
    """商店 Markdown 卡片主体（不含页脚，由调用方拼接天灾点余额）"""
    lines = [
        "# 🏪 天灾商店",
        "> 大都会把报酬换算成天灾点，按月结清。",
        "> 他们管这叫补偿。补偿的是谁，没有人细问。",
        "***",
    ]
    for item in SHOP_ITEMS:
        lines.append(f"{cmd(item['name'], '兑换 ' + item['name'])} — **{item['price']}** 天灾点")
        lines.append(f"　{item['desc']}")
    lines.append("***")
    lines.append("点击商品名即可兑换")
    return "\n".join(lines)
