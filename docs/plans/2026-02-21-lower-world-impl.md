# 下位世界·第四天灾入侵 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 新增独立模块 `lower_world/`，实现玩家化身天灾、坐镇山寨、抵御英雄波次的玩法。

**Architecture:** 全新独立模块，不改动现有系统。数据库表 `lower_world_stronghold` 通过 SQLAlchemy ORM 模型自动创建。战斗复用 `BattleIntegrationHelper.enhanced_player_vs_monster_battle_v2`。定时任务使用 APScheduler。

**Tech Stack:** NoneBot2, SQLAlchemy 2.0 (async ORM), APScheduler, 现有 UnitOfWork + Repository 架构。

---

## 关键知识（执行前必读）

### NoneBot2 异常处理规范（项目强制要求）
```python
# ✅ 正确：finish() 在 try-except 外调用
if not player:
    await cmd.finish("⛔ 请先创建角色")  # 可安全调用

try:
    result = some_risky_operation()
except ValueError as e:
    await cmd.finish(f"参数错误: {e}")

# ❌ 错误：绝对不能用 except Exception 包住整个处理器
try:
    await cmd.finish("...")  # FinishedException 会被捕获，导致死循环
except Exception:
    pass
```

### 战斗引擎调用方式
```python
# enhanced_player_vs_monster_battle_v2 返回 4 个值
victory, battle_log, damage_taken, post_effects = await BattleIntegrationHelper.enhanced_player_vs_monster_battle_v2(
    player=player,
    monster_stats={"hp": 4200, "attack": 380, "defense": 150, "agility": 120},
    monster_name="剑勇者·艾伦",
    session=uow.session,   # 注意：传 uow.session，不是 uow
    seed=f"LW:{player.id}:{timestamp}",
    max_rounds=30
)
```

### 数据库模型注册方式
ORM 模型继承 `Base` 后，需要在 `models/__init__.py`（或 `lower_world/__init__.py`）中 import，`init_db()` 会自动 CREATE TABLE。

### safe_session 用法（参考 dungeon_battle.py）
```python
from ..models.db import safe_session
async with safe_session() as session:
    player = await get_unified_player(session, event)
```

### UnitOfWork 用法
```python
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.db import AsyncSessionLocal

async with UnitOfWork(AsyncSessionLocal) as uow:
    # uow.session 是共享的 AsyncSession
    await uow.commit()
```

---

## Task 1: 数据库模型

**Files:**
- Create: `plugins/xiuxian_game/models/lower_world.py`
- Modify: `plugins/xiuxian_game/models/__init__.py`（添加 import）

**Step 1: 创建 ORM 模型文件**

```python
# plugins/xiuxian_game/models/lower_world.py
"""
下位世界·天灾山寨数据模型
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class LowerWorldStronghold(Base):
    """玩家天灾山寨"""
    __tablename__ = "lower_world_stronghold"

    player_id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="玩家ID"
    )
    calamity_points: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="天灾点（专属货币）"
    )
    wave_number: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", comment="当前波次"
    )
    next_wave_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="下一波英雄抵达时间"
    )
    pending_hero: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="待挑战英雄数据（JSON）"
    )
    sealed_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="封印截止时间（失败后24小时）"
    )
    total_waves_won: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="历史总胜场"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, comment="首次降临时间"
    )
```

**Step 2: 在 models/__init__.py 中注册模型**

找到 `plugins/xiuxian_game/models/__init__.py`，在已有 import 列表末尾添加：
```python
from . import lower_world  # noqa: F401 — 触发 Base 注册，使 init_db 能建表
```

**Step 3: 确认 Bot 能建表（手动验证，无自动化测试）**

重启 Bot，观察启动日志是否有报错。然后用 SQLite 工具或命令确认表存在：
```bash
# 在项目根目录执行
python -c "
import asyncio
import sys
sys.path.insert(0, '.')
from plugins.xiuxian_game.models.db import engine
from plugins.xiuxian_game.models.lower_world import LowerWorldStronghold
from sqlalchemy import inspect, text

async def check():
    async with engine.begin() as conn:
        result = await conn.execute(text(\"SELECT name FROM sqlite_master WHERE type='table' AND name='lower_world_stronghold'\"))
        row = result.fetchone()
        print('表存在' if row else '表不存在')

asyncio.run(check())
"
```
预期输出：`表存在`

**Step 4: Commit**
```bash
git add plugins/xiuxian_game/models/lower_world.py plugins/xiuxian_game/models/__init__.py
git commit -m "feat(lower-world): 添加天灾山寨数据库模型"
```

---

## Task 2: Repository + UnitOfWork 集成

**Files:**
- Create: `plugins/xiuxian_game/infrastructure/repositories/lower_world_repository.py`
- Modify: `plugins/xiuxian_game/infrastructure/uow/unit_of_work.py`

**Step 1: 创建 Repository**

```python
# plugins/xiuxian_game/infrastructure/repositories/lower_world_repository.py
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ...models.lower_world import LowerWorldStronghold


class LowerWorldRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_player_id(self, player_id: str) -> Optional[LowerWorldStronghold]:
        result = await self._session.execute(
            select(LowerWorldStronghold).where(LowerWorldStronghold.player_id == player_id)
        )
        return result.scalar_one_or_none()

    async def create(self, stronghold: LowerWorldStronghold) -> LowerWorldStronghold:
        self._session.add(stronghold)
        await self._session.flush()
        return stronghold

    async def get_all_active(self):
        """获取所有有待挑战英雄的山寨（用于定时任务推送）"""
        result = await self._session.execute(
            select(LowerWorldStronghold).where(
                LowerWorldStronghold.pending_hero.isnot(None)
            )
        )
        return result.scalars().all()
```

**Step 2: 在 UnitOfWork 中注册**

打开 `plugins/xiuxian_game/infrastructure/uow/unit_of_work.py`，找到其他 Repository 的注册模式，仿照添加：

在 `__init__` 的 import 区域或 property 区域添加 `lower_world_strongholds` 属性，仿照其他 repository 的懒加载模式。

具体操作：搜索文件中 `@property` 和 `Repository` 的用法，在末尾追加：
```python
@property
def lower_world_strongholds(self) -> LowerWorldRepository:
    if not hasattr(self, '_lower_world_strongholds'):
        from ..repositories.lower_world_repository import LowerWorldRepository
        self._lower_world_strongholds = LowerWorldRepository(self.session)
    return self._lower_world_strongholds
```

**Step 3: Commit**
```bash
git add plugins/xiuxian_game/infrastructure/repositories/lower_world_repository.py
git add plugins/xiuxian_game/infrastructure/uow/unit_of_work.py
git commit -m "feat(lower-world): 添加 Repository 和 UnitOfWork 集成"
```

---

## Task 3: 英雄生成器

**Files:**
- Create: `plugins/xiuxian_game/lower_world/hero_generator.py`

**Step 1: 创建英雄生成器**

```python
# plugins/xiuxian_game/lower_world/hero_generator.py
"""
下位世界英雄生成器
根据玩家等级和当前波次，生成对应强度的英雄
"""
import random
import json
from typing import Dict

# ==================== 数据池 ====================

KINGDOMS = [
    "莱纳斯王国", "阿尔托帝国", "圣光教廷", "银月联盟",
    "东境共和国", "龙脊山城邦", "碧海商会", "暮光公国",
]

FIRST_NAMES = [
    "艾伦", "莱昂哈特", "席拉", "伊莲娜", "托尔",
    "芙蕾雅", "奥尔加", "克劳德", "米雷亚", "赛勒斯",
    "艾莉丝", "加文", "罗伦", "薇薇安", "赫克托",
]

# 普通英雄（1-10波）
NORMAL_HERO_CLASSES = [
    {"title": "骑士", "flavour_pool": [
        "他加入骑士团已经十年，从未想过有一天会面对这种存在。",
        "她的盾牌上刻着父亲的名字，那是家族三代人的传承。",
        "他在出发前，把仅剩的积蓄寄回了老家的妻子那里。",
    ]},
    {"title": "圣女", "flavour_pool": [
        "她以为祈祷能带来庇护。来了以后，她只是沉默地握紧了权杖。",
        "教会说这是神圣的试炼。她不知道神有没有在看。",
        "她今年十七岁，是本届最年轻的圣女候选人。",
    ]},
    {"title": "魔导士", "flavour_pool": [
        "他花了二十年研究魔法，没想到第一次实战是这种场合。",
        "她的导师说：力量是为了保护。她一直记着这句话。",
        "他带来了三本魔法书，出发前烧掉了其中两本——减轻重量。",
    ]},
    {"title": "骑士团长", "flavour_pool": [
        "她带领三百骑士出征，只有她一个人走到了这里。",
        "他说不害怕是假的。但他是团长，他不能表现出来。",
        "她在出发前，对着部下说：你们回去。剩下的交给我。",
    ]},
    {"title": "龙骑士", "flavour_pool": [
        "他的坐骑在两天前落下了，他一个人走完了剩下的路。",
        "她和龙一起长大，现在龙不在了，她感觉少了一半的自己。",
        "他说：龙不需要理由，人才需要。他的理由是：我的孩子还等着我回去。",
    ]},
    {"title": "大法师", "flavour_pool": [
        "他活了九十七岁，见过太多东西。见过这个，还是第一次。",
        "她的魔力已经快耗尽了。她知道，但她没有退路。",
        "他带着一个任务：弄清楚天灾是什么。他现在站在这里，还是不明白。",
    ]},
]

# 勇者系（11波以上）
HERO_CLASSES = [
    {
        "title": "剑勇者",
        "atk_mult": 1.4, "def_mult": 1.0, "agi_mult": 1.1, "hp_mult": 1.0,
        "crit_rate": 20,
        "flavour_pool": [
            "召唤仪式结束时，他还穿着打铁的围裙。",
            "她说：我不想当英雄。但没有人问过她。",
            "他接过圣剑时，手在抖。没有人知道，因为他一直握得很紧。",
        ],
    },
    {
        "title": "盾勇者",
        "atk_mult": 0.7, "def_mult": 2.0, "agi_mult": 0.8, "hp_mult": 1.5,
        "crit_rate": 5,
        "flavour_pool": [
            "盾是最重的武器，她扛着它走了三天三夜。",
            "他们说盾勇者是最弱的。他默默记住了每一个说这话的人的名字。",
            "她的盾上有一道裂缝，那是上一个天灾留下的。",
        ],
    },
    {
        "title": "枪勇者",
        "atk_mult": 1.1, "def_mult": 0.9, "agi_mult": 1.5, "hp_mult": 1.0,
        "combo_rate": 25,
        "flavour_pool": [
            "他在马戏团学过杂技，现在枪法比任何人都快。",
            "她的目标是：活着回去，然后再也不来。",
            "他说：快比力气更重要。他活到现在，靠的就是这个。",
        ],
    },
    {
        "title": "弓勇者",
        "atk_mult": 1.2, "def_mult": 0.8, "agi_mult": 1.3, "hp_mult": 0.9,
        "ignore_defense": 20,
        "flavour_pool": [
            "她从小在山里长大，学会射箭比学会说话还早。",
            "他在最远的距离命中过目标，但那次他的手没有抖。这次抖了。",
            "她的箭只剩三支了。她数过，够了。",
        ],
    },
    {
        "title": "棍勇者",
        "atk_mult": 1.0, "def_mult": 1.0, "agi_mult": 1.0, "hp_mult": 1.2,
        "counter_rate": 20,
        "flavour_pool": [
            "他的棍法来自一个游方僧，那个僧人说：棍是生命的节拍。",
            "她一个人打败过一整队山贼，现在面对的是另一个量级。",
            "他说他不害怕。他媳妇说：你脸都白了。他说：那只是光线问题。",
        ],
    },
    {
        "title": "炮勇者",
        "atk_mult": 2.0, "def_mult": 0.8, "agi_mult": 0.5, "hp_mult": 1.1,
        "crit_rate": 10,
        "flavour_pool": [
            "她的大炮重两百斤，她一个人扛着走来的。",
            "他研究火药三十年，第一次把成果用在这种地方。",
            "她说：我只需要命中一次。一次就够了。",
        ],
    },
    {
        "title": "书勇者",
        "atk_mult": 1.0, "def_mult": 1.0, "agi_mult": 1.0, "hp_mult": 1.0,
        "has_debuff": True,
        "flavour_pool": [
            "他翻遍了所有古籍，没有找到天灾的记录。所以他来亲眼看看。",
            "她的书里夹着一张纸，上面写着她女儿的名字。",
            "他说：知识是最强的武器。她同伴说：你先把书放下，举起剑。",
        ],
    },
    {
        "title": "镰勇者",
        "atk_mult": 1.1, "def_mult": 0.9, "agi_mult": 1.1, "hp_mult": 1.0,
        "lifesteal": 15,
        "flavour_pool": [
            "她的镰刀是从一个死神那里抢来的，那个死神比她还弱。",
            "他说他不怕死，因为他已经死过一次了。",
            "她越打越勇，血越少力气越大——没有人知道为什么，包括她自己。",
        ],
    },
]


def calculate_hero_level(player_level: int, wave_number: int) -> int:
    """计算英雄等级"""
    ratio = 0.6 + wave_number * 0.04
    return max(1, int(player_level * ratio))


def calculate_hero_stats(hero_level: int, hero_class: Dict) -> Dict:
    """根据英雄等级和职业计算属性"""
    base_hp = int(hero_level * 42 * hero_class.get("hp_mult", 1.0))
    base_atk = int(hero_level * 3.8 * hero_class.get("atk_mult", 1.0))
    base_def = int(hero_level * 1.5 * hero_class.get("def_mult", 1.0))
    base_agi = int(hero_level * 1.2 * hero_class.get("agi_mult", 1.0))

    stats = {
        "hp": base_hp,
        "attack": base_atk,
        "defense": base_def,
        "agility": base_agi,
    }
    # 特殊属性
    if "crit_rate" in hero_class:
        stats["crit_rate"] = hero_class["crit_rate"]
    if "combo_rate" in hero_class:
        stats["combo_rate"] = hero_class["combo_rate"]
    if "counter_rate" in hero_class:
        stats["counter_rate"] = hero_class["counter_rate"]

    return stats


def generate_hero(player_level: int, wave_number: int) -> Dict:
    """
    生成一个英雄，返回包含完整信息的字典（将被 JSON 存储）

    Returns:
        {
            "name": str,           # 完整名称，如"莱纳斯王国召唤的剑勇者·艾伦"
            "title": str,          # 职称，如"剑勇者"
            "level": int,
            "hp": int,
            "attack": int,
            "defense": int,
            "agility": int,
            "flavour": str,        # 一句话背景
            ... 其他特殊属性
        }
    """
    hero_level = calculate_hero_level(player_level, wave_number)

    if wave_number <= 10:
        # 普通英雄
        hero_class = random.choice(NORMAL_HERO_CLASSES)
        kingdom = random.choice(KINGDOMS)
        name_part = random.choice(FIRST_NAMES)
        full_name = f"{kingdom}的{hero_class['title']}·{name_part}"
        title = hero_class["title"]
        # 普通英雄用默认属性
        stats = calculate_hero_stats(hero_level, {"hp_mult": 1.0, "atk_mult": 1.0,
                                                   "def_mult": 1.0, "agi_mult": 1.0})
    else:
        # 勇者系
        hero_class = random.choice(HERO_CLASSES)
        kingdom = random.choice(KINGDOMS)
        name_part = random.choice(FIRST_NAMES)
        full_name = f"{kingdom}召唤的{hero_class['title']}·{name_part}"
        title = hero_class["title"]
        stats = calculate_hero_stats(hero_level, hero_class)

    flavour = random.choice(hero_class["flavour_pool"])

    return {
        "name": full_name,
        "title": title,
        "level": hero_level,
        "flavour": flavour,
        **stats,
    }


def hero_to_json(hero: Dict) -> str:
    return json.dumps(hero, ensure_ascii=False)


def hero_from_json(data: str) -> Dict:
    return json.loads(data)
```

**Step 2: Commit**
```bash
git add plugins/xiuxian_game/lower_world/
git commit -m "feat(lower-world): 添加英雄生成器"
```

---

## Task 4: 业务逻辑 Service

**Files:**
- Create: `plugins/xiuxian_game/lower_world/service.py`

**Step 1: 创建 Service**

```python
# plugins/xiuxian_game/lower_world/service.py
"""
下位世界业务逻辑服务
"""
import time
import json
from datetime import datetime, timedelta
from typing import Tuple, Optional

from ..models.lower_world import LowerWorldStronghold
from ..infrastructure.uow.unit_of_work import UnitOfWork
from .hero_generator import generate_hero, hero_to_json, hero_from_json

# 波次间隔（2小时）
WAVE_INTERVAL_HOURS = 2
# 英雄等待超时（4小时后自动撤退）
HERO_TIMEOUT_HOURS = 4
# 封印时长（24小时）
SEAL_DURATION_HOURS = 24

# 波次奖励天灾点
def get_wave_reward(wave_number: int) -> int:
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
        remaining = stronghold.sealed_until - now
        return True, remaining
    return False, None


def has_pending_hero(stronghold: LowerWorldStronghold) -> bool:
    """是否有待挑战的英雄"""
    if not stronghold.pending_hero:
        return False
    hero = hero_from_json(stronghold.pending_hero)
    # 检查是否超时撤退（4小时）
    if stronghold.next_wave_at:
        arrival = stronghold.next_wave_at
        if datetime.now() > arrival + timedelta(hours=HERO_TIMEOUT_HOURS):
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
    """为山寨安排下一波英雄"""
    next_time = datetime.now() + timedelta(hours=WAVE_INTERVAL_HOURS)
    hero = generate_hero(player_level, stronghold.wave_number)
    stronghold.next_wave_at = next_time
    stronghold.pending_hero = hero_to_json(hero)
    uow.session.add(stronghold)


async def process_battle_victory(uow: UnitOfWork, stronghold: LowerWorldStronghold, player_level: int) -> int:
    """
    处理战斗胜利：增加天灾点，波次+1，清除当前英雄，安排下一波
    返回获得的天灾点
    """
    points = get_wave_reward(stronghold.wave_number)
    stronghold.calamity_points += points
    stronghold.total_waves_won += 1
    stronghold.wave_number += 1
    stronghold.pending_hero = None  # 清除当前英雄
    stronghold.sealed_until = None
    await schedule_next_wave(uow, stronghold, player_level)
    uow.session.add(stronghold)
    return points


async def process_battle_defeat(uow: UnitOfWork, stronghold: LowerWorldStronghold):
    """处理战斗失败：封印24小时，清除当前英雄"""
    stronghold.sealed_until = datetime.now() + timedelta(hours=SEAL_DURATION_HOURS)
    stronghold.pending_hero = None
    stronghold.next_wave_at = None
    uow.session.add(stronghold)


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
        "id": "title_calamity",
        "name": "称号「第四天灾」",
        "desc": "永久专属称号，一次性购买",
        "price": 200,
    },
]


def get_shop_display() -> str:
    lines = ["🏪 天灾商店（大都会支付给你的代价）", "━━━━━━━━━━━━━"]
    for item in SHOP_ITEMS:
        lines.append(f"• {item['name']} — {item['price']}天灾点")
        lines.append(f"  {item['desc']}")
    lines.append("━━━━━━━━━━━━━")
    lines.append("使用【兑换 商品名】购买")
    return "\n".join(lines)
```

**Step 2: Commit**
```bash
git add plugins/xiuxian_game/lower_world/service.py
git commit -m "feat(lower-world): 添加业务逻辑 Service"
```

---

## Task 5: 命令处理器

**Files:**
- Create: `plugins/xiuxian_game/lower_world/commands.py`

**Step 1: 创建命令文件**

```python
# plugins/xiuxian_game/lower_world/commands.py
"""
下位世界命令处理器

命令列表：
- 【降临】: 初次建立山寨 / 已建立则显示状态
- 【镇守】: 查看山寨状态
- 【迎战】: 与当前波次英雄战斗
- 【天灾商店】: 查看商店
- 【兑换 XXX】: 购买商品
"""
import time
from datetime import datetime, timedelta

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent

from ..models.db import AsyncSessionLocal
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..utils import get_unified_player
from .service import (
    get_or_create_stronghold, is_sealed, has_pending_hero,
    schedule_next_wave, process_battle_victory, process_battle_defeat,
    format_time_remaining, hero_from_json, get_shop_display, SHOP_ITEMS,
    WAVE_INTERVAL_HOURS,
)

# ==================== 命令注册 ====================

descend_cmd = on_command("降临", aliases={"降临下位世界"}, priority=5, block=True)
guard_cmd = on_command("镇守", priority=5, block=True)
battle_cmd = on_command("迎战", priority=5, block=True)
shop_cmd = on_command("天灾商店", priority=5, block=True)
redeem_cmd = on_command("兑换", priority=5, block=True)


# ==================== 【降临】 ====================

@descend_cmd.handle()
async def handle_descend(event: MessageEvent):
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await descend_cmd.finish("⛔ 请先创建角色")

        stronghold, is_new = await get_or_create_stronghold(uow, player.id)

        if is_new:
            # 首次降临：安排第一波英雄
            await schedule_next_wave(uow, stronghold, player.level)
            await uow.commit()
            await descend_cmd.finish(
                "📋 大都会第七分部紧急会议记录\n\n"
                "敲门诡在第十七区扩散，鬼域裂缝停不下来了。\n"
                "再不处理，七十二小时内整个分部都会被吞掉。\n\n"
                "会长看了一眼数据，说：\n"
                "「导流。补偿打账户里。」\n\n"
                "就这一句话。会议结束了。\n\n"
                "你收到一条消息——\n"
                "「你已被选为第四天灾导流节点，请配合传送。」\n\n"
                "你还没看完，那些诡异的气息就扑过来了。\n"
                "不是来打你的——它们要钻进你身体里。\n"
                "它们把你当成了一扇门。\n\n"
                "然后你就掉下去了。\n\n"
                "睁开眼，天是另一种颜色。\n"
                "有个小孩看见你，大叫一声\"天灾来了\"，\n"
                "撒腿就跑，摔了一跤，爬起来继续跑。\n\n"
                "你低头看自己落脚的地方——\n"
                "地面正在龟裂，裂缝里渗出灰色的雾。\n"
                "你身后，鬼域已经张开了。\n"
                "叩门声从你的影子里传出来，一下一下，\n"
                "敲进这片土地。\n\n"
                "这里的人还不知道，\n"
                "大都会把什么东西送过来了。\n\n"
                "⚠️ 你已降临下位世界，成为「第四天灾」\n"
                "   大都会的诡异正通过你持续涌入这个世界\n"
                f"  {WAVE_INTERVAL_HOURS}小时后，这里的英雄会来找你\n"
                "   ——大都会那边已经收到你的报酬了"
            )
        else:
            # 已有山寨，跳转到镇守视角
            await _show_guard_status(guard_cmd, stronghold)


# ==================== 【镇守】 ====================

@guard_cmd.handle()
async def handle_guard(event: MessageEvent):
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await guard_cmd.finish("⛔ 请先创建角色")

        stronghold = await uow.lower_world_strongholds.get_by_player_id(player.id)
        if not stronghold:
            await guard_cmd.finish("⛔ 你还未降临下位世界\n⬇️ 使用【降临】开始")

        await _show_guard_status(guard_cmd, stronghold)


async def _show_guard_status(cmd, stronghold):
    """显示山寨状态（复用于降临和镇守）"""
    # 封印检查
    sealed, remaining = is_sealed(stronghold)
    if sealed:
        await cmd.finish(
            f"⛓️ 你被封印了（剩余：{format_time_remaining(remaining)}）\n\n"
            "圣光骑士把封印刻在你额头时说：\n"
            "「你不是坏人，对吧。」\n"
            "「但我们也没有别的选择。」\n\n"
            "你们都沉默着。"
        )

    lines = [
        "📡 山寨状态",
        f"天灾点：{stronghold.calamity_points}  |  当前波次：第{stronghold.wave_number}波",
        f"历史胜场：{stronghold.total_waves_won}场",
        "",
        "鬼域裂缝已在山寨周围蔓延。",
        "叩门声在石墙里流动——你带来的东西正在这里生根。",
        "",
        "「下位世界的人把这里叫做'灾地'。",
        " 村子里已经有人说：墙壁会动。」",
        "",
    ]

    # 英雄状态
    if has_pending_hero(stronghold):
        hero = hero_from_json(stronghold.pending_hero)
        lines.append(f"⚔️ 英雄已抵达！【迎战】应战")
        lines.append(f"   {hero['name']}（Lv.{hero['level']}）")
    elif stronghold.next_wave_at:
        now = datetime.now()
        if stronghold.next_wave_at > now:
            remaining_td = stronghold.next_wave_at - now
            lines.append(f"⏳ 下一波英雄将在 {format_time_remaining(remaining_td)} 后抵达")
        else:
            lines.append("⚔️ 英雄应已抵达，使用【迎战】查看")
    else:
        lines.append("⏳ 等待英雄到来中……")

    await cmd.finish("\n".join(lines))


# ==================== 【迎战】 ====================

@battle_cmd.handle()
async def handle_battle(event: MessageEvent):
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await battle_cmd.finish("⛔ 请先创建角色")

        stronghold = await uow.lower_world_strongholds.get_by_player_id(player.id)
        if not stronghold:
            await battle_cmd.finish("⛔ 你还未降临下位世界\n⬇️ 使用【降临】开始")

        sealed, remaining = is_sealed(stronghold)
        if sealed:
            await battle_cmd.finish(
                f"⛓️ 你被封印了，无法迎战（剩余：{format_time_remaining(remaining)}）"
            )

        if not has_pending_hero(stronghold):
            if stronghold.next_wave_at and datetime.now() > stronghold.next_wave_at + timedelta(hours=4):
                # 英雄超时撤退
                stronghold.pending_hero = None
                await schedule_next_wave(uow, stronghold, player.level)
                await uow.commit()
                await battle_cmd.finish(
                    "……英雄撤退了。\n"
                    "他们在山寨外等了很久，没有看到你。\n"
                    "他们回去了。\n\n"
                    f"⏳ 下一波英雄将在 {WAVE_INTERVAL_HOURS} 小时后到来"
                )
            await battle_cmd.finish(
                "⏳ 还没有英雄到来\n"
                "使用【镇守】查看下一波时间"
            )

        hero = hero_from_json(stronghold.pending_hero)

        # 恢复玩家HP用于战斗（不影响真实HP）
        original_hp = player.hp
        if player.hp <= 0:
            player.hp = max(1, int(player.max_hp * 0.3))

        # 执行战斗
        from ..battle.integration_helper import BattleIntegrationHelper
        battle_timestamp = int(time.time() * 1000)
        seed = f"LW:{player.id}:{battle_timestamp}"

        monster_stats = {
            "hp": hero["hp"],
            "attack": hero["attack"],
            "defense": hero["defense"],
            "agility": hero["agility"],
        }
        if "crit_rate" in hero:
            monster_stats["crit_rate"] = hero["crit_rate"]
        if "combo_rate" in hero:
            monster_stats["combo_rate"] = hero["combo_rate"]
        if "counter_rate" in hero:
            monster_stats["counter_rate"] = hero["counter_rate"]

        victory, battle_log, damage_taken, post_effects = await BattleIntegrationHelper.enhanced_player_vs_monster_battle_v2(
            player=player,
            monster_stats=monster_stats,
            monster_name=hero["name"],
            session=uow.session,
            seed=seed,
            max_rounds=30,
        )

        # 恢复原HP（天灾玩法不扣真实HP）
        player.hp = original_hp

        lines = ["━━━━━━━━━━━━━"]
        lines.extend(battle_log)
        lines.append("━━━━━━━━━━━━━")

        if victory:
            points = await process_battle_victory(uow, stronghold, player.level)
            await uow.commit()
            lines += [
                "",
                f"……{hero['name']} 倒下了。",
                "",
                "他/她望着你，没有仇恨，只是问：",
                "「你们那边……也会有人哭吗？」",
                "",
                "你没有回答。",
                "你身后，诡异继续往外涌。",
                "",
                f"+{points}天灾点（当前：{stronghold.calamity_points}点）",
                "「大都会那边有人因此平安了。",
                " 他们不知道你的名字。」",
            ]
        else:
            await process_battle_defeat(uow, stronghold)
            await uow.commit()
            lines += [
                "",
                "你倒下了。",
                "",
                f"{hero['name']} 没有趁机补刀，只是站在原地，",
                "把武器插回剑鞘。",
                "",
                "「走吧，天灾。",
                " 今天先到这里。」",
                "",
                "⛓️ 你被封印24小时",
            ]

        await battle_cmd.finish("\n".join(lines))


# ==================== 【天灾商店】 ====================

@shop_cmd.handle()
async def handle_shop(event: MessageEvent):
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await shop_cmd.finish("⛔ 请先创建角色")

        stronghold = await uow.lower_world_strongholds.get_by_player_id(player.id)
        if not stronghold:
            await shop_cmd.finish("⛔ 你还未降临下位世界")

        msg = get_shop_display()
        msg += f"\n\n当前天灾点：{stronghold.calamity_points}点"
        await shop_cmd.finish(msg)


# ==================== 【兑换】 ====================

@redeem_cmd.handle()
async def handle_redeem(event: MessageEvent):
    args = str(event.get_message()).strip()
    if not args:
        await redeem_cmd.finish("⛔ 请指定商品名，例如：【兑换 修炼加速（2小时）】")

    # 匹配商品
    item = next((i for i in SHOP_ITEMS if i["name"] in args or i["id"] in args), None)
    if not item:
        await redeem_cmd.finish(f"⛔ 未找到商品「{args}」\n使用【天灾商店】查看商品列表")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await redeem_cmd.finish("⛔ 请先创建角色")

        stronghold = await uow.lower_world_strongholds.get_by_player_id(player.id)
        if not stronghold:
            await redeem_cmd.finish("⛔ 你还未降临下位世界")

        if stronghold.calamity_points < item["price"]:
            await redeem_cmd.finish(
                f"⛔ 天灾点不足\n"
                f"需要 {item['price']} 点，当前 {stronghold.calamity_points} 点"
            )

        stronghold.calamity_points -= item["price"]
        uow.session.add(stronghold)

        # 简易效果应用（后续可扩展）
        effect_msg = f"✅ 兑换成功：{item['name']}\n{item['desc']}"
        if item["id"] == "title_calamity":
            effect_msg += "\n\n（称号功能待接入称号系统）"

        await uow.commit()
        await redeem_cmd.finish(
            f"{effect_msg}\n剩余天灾点：{stronghold.calamity_points}点"
        )
```

**Step 2: Commit**
```bash
git add plugins/xiuxian_game/lower_world/commands.py
git commit -m "feat(lower-world): 添加命令处理器（降临/镇守/迎战/天灾商店/兑换）"
```

---

## Task 6: 定时任务 Scheduler

**Files:**
- Create: `plugins/xiuxian_game/lower_world/scheduler.py`

**Step 1: 创建 Scheduler**

```python
# plugins/xiuxian_game/lower_world/scheduler.py
"""
下位世界定时任务

功能：
- 每2小时：为山寨推送新英雄，并发送 QQ 通知
"""
from datetime import datetime, timedelta
from nonebot import get_driver, logger, get_bot
from nonebot_plugin_apscheduler import scheduler

from ..models.db import AsyncSessionLocal
from ..infrastructure.uow.unit_of_work import UnitOfWork
from .service import has_pending_hero, schedule_next_wave

driver = get_driver()


@scheduler.scheduled_job("interval", hours=2, id="lower_world_wave_push")
async def push_hero_waves():
    """
    每2小时检查所有山寨，为没有待挑战英雄的山寨推送新英雄，
    并通过 QQ 消息通知玩家。
    """
    logger.info("[下位世界] 开始推送英雄波次...")
    try:
        bot = get_bot()
    except Exception:
        logger.warning("[下位世界] 无法获取 Bot，跳过本次推送")
        return

    try:
        async with UnitOfWork(AsyncSessionLocal) as uow:
            from sqlalchemy import select
            from ..models.lower_world import LowerWorldStronghold
            from ..models.player import Player

            # 查询所有未封印且没有待挑战英雄的山寨
            result = await uow.session.execute(select(LowerWorldStronghold))
            all_strongholds = result.scalars().all()

            pushed_count = 0
            for stronghold in all_strongholds:
                # 跳过封印中的
                if stronghold.sealed_until and datetime.now() < stronghold.sealed_until:
                    continue
                # 跳过已有英雄的
                if has_pending_hero(stronghold):
                    continue
                # 跳过最近刚结束战斗的（next_wave_at 还没到的）
                if stronghold.next_wave_at and datetime.now() < stronghold.next_wave_at:
                    continue

                # 获取玩家等级
                player_result = await uow.session.execute(
                    select(Player).where(Player.id == stronghold.player_id)
                )
                player = player_result.scalar_one_or_none()
                if not player:
                    continue

                await schedule_next_wave(uow, stronghold, player.level)
                pushed_count += 1

                # 发送 QQ 通知（私聊）
                try:
                    hero_data = __import__('json').loads(stronghold.pending_hero)
                    await bot.send_private_msg(
                        user_id=int(player.user_id),
                        message=(
                            f"⚔️ 第{stronghold.wave_number}波英雄已抵达你的山寨！\n"
                            f"   {hero_data['name']}（Lv.{hero_data['level']}）\n"
                            f"使用【迎战】应战"
                        )
                    )
                except Exception as e:
                    logger.debug(f"[下位世界] 通知玩家 {player.user_id} 失败: {e}")

            await uow.commit()
            logger.info(f"[下位世界] 英雄波次推送完成，共推送 {pushed_count} 个山寨")

    except Exception as e:
        logger.error(f"[下位世界] 英雄波次推送任务失败: {e}")


@driver.on_startup
async def on_startup():
    logger.info("[下位世界] 定时任务已注册：每2小时推送英雄波次")
```

**Step 2: Commit**
```bash
git add plugins/xiuxian_game/lower_world/scheduler.py
git commit -m "feat(lower-world): 添加定时任务，每2小时推送英雄波次"
```

---

## Task 7: 模块入口 + 注册

**Files:**
- Create: `plugins/xiuxian_game/lower_world/__init__.py`
- Modify: `plugins/xiuxian_game/__init__.py`（添加模块加载）

**Step 1: 创建 `__init__.py`**

```python
# plugins/xiuxian_game/lower_world/__init__.py
"""
下位世界·第四天灾入侵模块

玩家化身天灾坐镇山寨，抵御下位世界英雄的挑战。
"""
from . import commands   # noqa: F401 — 注册命令
from . import scheduler  # noqa: F401 — 注册定时任务
```

**Step 2: 在游戏主 `__init__.py` 加载模块**

打开 `plugins/xiuxian_game/__init__.py`，找到其他子模块的加载位置（如 `inner_realm`），在末尾添加：
```python
from . import lower_world  # noqa: F401
```

**Step 3: Commit**
```bash
git add plugins/xiuxian_game/lower_world/__init__.py
git add plugins/xiuxian_game/__init__.py
git commit -m "feat(lower-world): 注册下位世界模块到游戏主入口"
```

---

## Task 8: 更新帮助信息

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py`

**Step 1: 在 help.py 中找到帮助字典，添加新命令**

打开 `help.py`，找到帮助数据结构，添加：

```python
"降临": {
    "usage": "降临",
    "description": "降临下位世界，成为第四天灾。首次使用建立山寨，已建立则查看状态。",
    "examples": ["降临"],
},
"镇守": {
    "usage": "镇守",
    "description": "查看天灾山寨状态：当前波次、天灾点、下一波英雄到来时间、封印状态。",
    "examples": ["镇守"],
},
"迎战": {
    "usage": "迎战",
    "description": "与当前波次的英雄战斗。英雄每2小时到来一波，需在4小时内应战，否则英雄撤退。",
    "examples": ["迎战"],
},
"天灾商店": {
    "usage": "天灾商店",
    "description": "查看可用天灾点兑换的专属福利（修炼加速、战意加持、专属称号等）。",
    "examples": ["天灾商店"],
},
"兑换": {
    "usage": "兑换 <商品名>",
    "description": "花费天灾点购买天灾商店中的商品。",
    "examples": ["兑换 修炼加速（2小时）", "兑换 称号「第四天灾」"],
},
```

**Step 2: Commit**
```bash
git add plugins/xiuxian_game/player/help.py
git commit -m "docs(lower-world): 更新帮助信息，添加天灾玩法命令说明"
```

---

## Task 9: 烟雾测试（手动）

重启 Bot，按以下顺序测试：

1. 发送 `降临` → 应显示完整降临文案，末尾有"2小时后英雄会来找你"
2. 发送 `镇守` → 应显示山寨状态，天灾点0，波次第1波，显示下一波时间
3. 修改数据库 `lower_world_stronghold` 中的 `next_wave_at` 为过去时间，手动注入一个英雄 JSON 到 `pending_hero`
4. 发送 `迎战` → 应显示英雄信息和战斗过程，胜利后+天灾点
5. 发送 `天灾商店` → 应显示商品列表和当前天灾点
6. 发送 `兑换 修炼加速（2小时）` → 扣除天灾点，显示兑换成功
7. 修改 `sealed_until` 为未来时间 → `迎战`/`镇守` 应显示封印状态

---

## 完成标准

- [ ] Bot 启动无报错
- [ ] `lower_world_stronghold` 表自动创建
- [ ] 【降临】首次使用显示完整文案
- [ ] 【镇守】正确显示状态/封印
- [ ] 【迎战】完成完整战斗流程，胜利/失败各有对应文案
- [ ] 【天灾商店】显示正确
- [ ] 【兑换】扣点成功
- [ ] 定时任务注册成功（Bot 日志显示注册信息）
