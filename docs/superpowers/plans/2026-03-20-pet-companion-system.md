# 诡兽宠物伴侣系统 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有灵田守护诡兽升级为独立的宠物伴侣系统，支持AI聊天、养成升级、饰品装扮、喂食互动、战斗辅助和化形进化。

**Architecture:** 新建独立 `plugins/xiuxian_game/pet/` 模块，诡兽从灵田的一个字段升级为独立的 `pet_instance` 表。复用现有 AI 对话链路（`AIDialogueService` + `PersonalityTemplate`）实现诡兽聊天。通过实现 `IAttributeSource` 协议将宠物被动属性加成接入 `AttributeCalculator`。灵田守护改为"派遣宠物去守田"的任务机制。

**Tech Stack:** SQLAlchemy 2.0 ORM / NoneBot2 / 智谱AI (GLM-4-Flash) / YAML配置

---

## 文件结构

### 新建文件

| 文件 | 职责 |
|------|------|
| `models/pet_instance.py` | 宠物实例ORM模型（属性、状态、等级、好感度等） |
| `models/pet_dialogue_history.py` | 宠物对话历史ORM模型 |
| `infrastructure/repositories/pet_repository.py` | 宠物Repository实现 |
| `infrastructure/repositories/pet_dialogue_history_repository.py` | 宠物对话历史Repository |
| `pet/__init__.py` | 模块注册入口 |
| `pet/config.py` | 宠物系统常量+YAML加载（等级表、化形配置、饰品配置） |
| `pet/pet_service.py` | 宠物核心服务（获取、喂食、互动、升级） |
| `pet/pet_dialogue_service.py` | 宠物AI对话服务（构建人设、调用AIDialogueService） |
| `pet/pet_battle_service.py` | 宠物战斗辅助服务（被动加成计算） |
| `pet/commands.py` | NoneBot命令处理器 |
| `domain/attributes/attribute_sources/pet_source.py` | 宠物属性来源（IAttributeSource实现） |
| `data/pet_config.yaml` | 宠物种族配置（5种兽形+化形数据） |
| `data/pet_accessories.yaml` | 宠物饰品配置 |
| `data/pet_personalities.yaml` | 宠物人设配置（每种诡兽的AI人设模板） |

### 修改文件

| 文件 | 修改内容 |
|------|----------|
| `models/__init__.py` | 注册新模型 |
| `models/auto_migrate.py` | 添加 `spirit_field` 表的 `guardian_beast_id` 字段迁移说明（改为引用pet_instance） |
| `infrastructure/uow/unit_of_work.py` | 注册宠物相关Repository |
| `domain/attributes/attribute_calculator_factory.py` | 注册 `PetAttributeSource` |
| `spirit_field/steal_service.py` | 守田拦截改为查询pet_instance的派遣状态 |
| `spirit_field/guardian_service.py` | 重构为调用pet模块的派遣接口 |
| `spirit_field/commands.py` | 移除旧的诡兽命令，改为引导到pet模块 |
| `data/items.yaml` | 添加宠物饰品物品定义 |
| `__init__.py` | 注册pet子模块 |
| `player/help.py` | 添加宠物系统帮助信息 |

---

## Task 1: 宠物实例数据模型

**Files:**
- Create: `plugins/xiuxian_game/models/pet_instance.py`
- Create: `plugins/xiuxian_game/models/pet_dialogue_history.py`
- Modify: `plugins/xiuxian_game/models/__init__.py`
- Modify: `plugins/xiuxian_game/models/auto_migrate.py`

- [ ] **Step 1: 创建 PetInstance 模型**

```python
# plugins/xiuxian_game/models/pet_instance.py
"""宠物实例模型"""
from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, Boolean, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class PetInstance(Base):
    """宠物实例

    每只诡兽为一条记录，玩家可拥有多只，但只能激活1只伴侣。
    """
    __tablename__ = "pet_instance"
    __table_args__ = (
        Index("ix_pet_instance_player_active", "player_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("player.id"), index=True, comment="所属玩家ID"
    )
    beast_id: Mapped[str] = mapped_column(
        String(32), comment="诡兽种族ID(对应guardian_beasts.yaml的beast_id)"
    )
    nickname: Mapped[str] = mapped_column(
        String(64), comment="玩家给宠物起的昵称"
    )

    # 养成属性
    level: Mapped[int] = mapped_column(Integer, default=1, server_default="1", comment="宠物等级")
    experience: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="当前经验值")
    affection: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="好感度(0-1000)")
    mood: Mapped[int] = mapped_column(Integer, default=80, server_default="80", comment="心情值(0-100)")
    hunger: Mapped[int] = mapped_column(Integer, default=100, server_default="100", comment="饱食度(0-100)")

    # 战斗属性加成（随等级成长）
    bonus_attack: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="攻击加成")
    bonus_defense: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="防御加成")
    bonus_hp: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="生命加成")
    bonus_crit_rate: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", comment="暴击率加成")
    bonus_dodge_rate: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", comment="闪避率加成")

    # 状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", comment="是否为当前伴侣")
    is_guarding: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", comment="是否正在守田")
    is_transformed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", comment="是否已化形")

    # 饰品（JSON存储已装备饰品ID列表）
    accessories: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="已装备饰品 {slot: item_id}")

    # 时间戳
    last_fed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="上次喂食时间")
    last_interact_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="上次互动时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="获得时间")
```

- [ ] **Step 2: 创建 PetDialogueHistory 模型**

```python
# plugins/xiuxian_game/models/pet_dialogue_history.py
"""宠物对话历史模型"""
from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class PetDialogueHistory(Base):
    """宠物对话历史记录"""
    __tablename__ = "pet_dialogue_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pet_id: Mapped[int] = mapped_column(Integer, index=True, comment="宠物实例ID")
    player_id: Mapped[str] = mapped_column(String(32), index=True, comment="玩家ID")
    player_input: Mapped[str] = mapped_column(Text, comment="玩家输入")
    pet_response: Mapped[str] = mapped_column(Text, comment="宠物回复")
    affection_change: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="好感度变化")
    mood_change: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="心情变化")
    ai_tokens_used: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="AI消耗token数")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="对话时间")
```

- [ ] **Step 3: 在 models/__init__.py 注册模型**

在文件末尾添加：
```python
# 宠物伴侣系统模型
from .pet_instance import PetInstance
from .pet_dialogue_history import PetDialogueHistory
```

并在 `__all__` 列表中添加 `"PetInstance"`, `"PetDialogueHistory"`。

- [ ] **Step 4: 确认启动后表自动创建**

由于使用 `Base.metadata.create_all()`，新模型在 `models/__init__.py` 中 import 后会自动建表，无需修改 `auto_migrate.py`（仅当给已有表加字段才需要）。

- [ ] **Step 5: 提交**

```bash
git add plugins/xiuxian_game/models/pet_instance.py plugins/xiuxian_game/models/pet_dialogue_history.py plugins/xiuxian_game/models/__init__.py
git commit -m "feat(pet): 添加宠物实例和对话历史数据模型"
```

---

## Task 2: 宠物 Repository + UoW 注册

**Files:**
- Create: `plugins/xiuxian_game/infrastructure/repositories/pet_repository.py`
- Create: `plugins/xiuxian_game/infrastructure/repositories/pet_dialogue_history_repository.py`
- Modify: `plugins/xiuxian_game/infrastructure/uow/unit_of_work.py`

- [ ] **Step 1: 创建 PetRepository**

```python
# plugins/xiuxian_game/infrastructure/repositories/pet_repository.py
"""宠物仓储实现"""
from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from ...domain.repositories.base import IRepository
from ...models.pet_instance import PetInstance


class PetRepository(IRepository[PetInstance]):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, id: int) -> Optional[PetInstance]:
        return await self._session.get(PetInstance, id)

    async def add(self, entity: PetInstance) -> PetInstance:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: PetInstance) -> PetInstance:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: PetInstance):
        await self._session.delete(entity)
        await self._session.flush()

    async def exists(self, id: int) -> bool:
        return await self.get_by_id(id) is not None

    async def count(self) -> int:
        result = await self._session.execute(select(func.count(PetInstance.id)))
        return result.scalar_one()

    # 领域查询
    async def get_active_pet(self, player_id: str) -> Optional[PetInstance]:
        """获取玩家当前激活的伴侣"""
        stmt = select(PetInstance).where(
            PetInstance.player_id == player_id,
            PetInstance.is_active == True
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_guarding_pet(self, player_id: str) -> Optional[PetInstance]:
        """获取玩家正在守田的宠物"""
        stmt = select(PetInstance).where(
            PetInstance.player_id == player_id,
            PetInstance.is_guarding == True
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_by_player(self, player_id: str) -> List[PetInstance]:
        """获取玩家所有宠物"""
        stmt = select(PetInstance).where(
            PetInstance.player_id == player_id
        ).order_by(PetInstance.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_player(self, player_id: str) -> int:
        """统计玩家宠物数量"""
        result = await self._session.execute(
            select(func.count(PetInstance.id)).where(PetInstance.player_id == player_id)
        )
        return result.scalar_one()
```

- [ ] **Step 2: 创建 PetDialogueHistoryRepository**

```python
# plugins/xiuxian_game/infrastructure/repositories/pet_dialogue_history_repository.py
"""宠物对话历史仓储"""
from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ...domain.repositories.base import IRepository
from ...models.pet_dialogue_history import PetDialogueHistory


class PetDialogueHistoryRepository(IRepository[PetDialogueHistory]):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, id: int):
        return await self._session.get(PetDialogueHistory, id)

    async def add(self, entity: PetDialogueHistory) -> PetDialogueHistory:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: PetDialogueHistory) -> PetDialogueHistory:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: PetDialogueHistory):
        await self._session.delete(entity)
        await self._session.flush()

    async def exists(self, id: int) -> bool:
        return await self.get_by_id(id) is not None

    async def count(self) -> int:
        from sqlalchemy import func
        result = await self._session.execute(select(func.count(PetDialogueHistory.id)))
        return result.scalar_one()

    async def get_recent(self, pet_id: int, player_id: str, limit: int = 10) -> List[PetDialogueHistory]:
        """获取最近对话记录"""
        stmt = (
            select(PetDialogueHistory)
            .where(
                PetDialogueHistory.pet_id == pet_id,
                PetDialogueHistory.player_id == player_id
            )
            .order_by(PetDialogueHistory.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
```

- [ ] **Step 3: 在 UnitOfWork 注册**

在 `unit_of_work.py` 的 `__init__` 方法中（约第122行后）添加：
```python
# 宠物伴侣系统仓储
self._pets = None
self._pet_dialogue_histories = None
```

在文件末尾添加两个 `@property`：
```python
@property
def pets(self):
    """宠物仓储"""
    if self._pets is None:
        from ..repositories.pet_repository import PetRepository
        self._pets = PetRepository(self._session)
    return self._pets

@property
def pet_dialogue_histories(self):
    """宠物对话历史仓储"""
    if self._pet_dialogue_histories is None:
        from ..repositories.pet_dialogue_history_repository import PetDialogueHistoryRepository
        self._pet_dialogue_histories = PetDialogueHistoryRepository(self._session)
    return self._pet_dialogue_histories
```

- [ ] **Step 4: 提交**

```bash
git add plugins/xiuxian_game/infrastructure/repositories/pet_repository.py plugins/xiuxian_game/infrastructure/repositories/pet_dialogue_history_repository.py plugins/xiuxian_game/infrastructure/uow/unit_of_work.py
git commit -m "feat(pet): 添加宠物Repository和UoW注册"
```

---

## Task 3: 宠物YAML配置体系

**Files:**
- Create: `plugins/xiuxian_game/data/pet_config.yaml`
- Create: `plugins/xiuxian_game/data/pet_accessories.yaml`
- Create: `plugins/xiuxian_game/data/pet_personalities.yaml`
- Create: `plugins/xiuxian_game/pet/__init__.py`
- Create: `plugins/xiuxian_game/pet/config.py`

- [ ] **Step 1: 创建宠物种族配置 pet_config.yaml**

```yaml
# 宠物种族配置
# 基于现有 guardian_beasts.yaml 扩展，增加养成和化形数据

# 全局常量
settings:
  max_pets_per_player: 10        # 每个玩家最多拥有宠物数
  max_level: 100                 # 宠物最高等级
  transform_level: 50            # 化形所需等级
  transform_affection: 500       # 化形所需好感度
  hunger_decay_per_hour: 2       # 每小时饱食度下降
  mood_decay_per_hour: 1         # 每小时心情下降
  hungry_threshold: 20           # 饥饿阈值（低于此值心情加速下降）
  base_feed_resentment: 10       # 基础怨念喂食消耗
  feed_hunger_restore: 30        # 怨念喂食恢复饱食度
  dish_hunger_restore: 50        # 菜肴喂食恢复饱食度
  dish_mood_bonus: 10            # 菜肴喂食额外心情加成
  interact_cooldown_minutes: 5   # 互动冷却时间（分钟）
  interact_affection_gain: 3     # 每次互动好感度增加
  interact_mood_gain: 5          # 每次互动心情增加

# 等级经验表（到达该等级所需的累计经验）
level_exp_table:
  1: 0
  2: 100
  3: 250
  4: 450
  5: 700
  10: 3000
  20: 15000
  30: 45000
  40: 100000
  50: 200000     # 化形等级
  60: 350000
  70: 550000
  80: 800000
  90: 1100000
  100: 1500000

# 每级属性成长（每升1级获得的属性点，按稀有度区分）
growth_per_level:
  white:
    attack: 2
    defense: 1
    hp: 10
    crit_rate: 0.001
    dodge_rate: 0.001
  green:
    attack: 3
    defense: 2
    hp: 15
    crit_rate: 0.0015
    dodge_rate: 0.0012
  blue:
    attack: 5
    defense: 3
    hp: 25
    crit_rate: 0.002
    dodge_rate: 0.0015
  purple:
    attack: 8
    defense: 5
    hp: 40
    crit_rate: 0.003
    dodge_rate: 0.002
  orange:
    attack: 12
    defense: 8
    hp: 60
    crit_rate: 0.004
    dodge_rate: 0.003

# 诡兽种族定义（扩展自guardian_beasts.yaml中已有的5种）
beasts:
  guard_dog:
    name: "冥犬"
    rarity: "white"
    intercept_rate: 30
    description: "双目泛着幽光的黑犬，能嗅到偷菜者身上的活人气息"
    transform_name: "犬灵少女"
    transform_description: "化形为一位银发犬耳少女，尾巴会在高兴时摇个不停"

  ghost_cat:
    name: "诡猫"
    rarity: "green"
    intercept_rate: 45
    description: "诡异的猫咪，瞳孔倒映着偷菜者的身影"
    transform_name: "猫娘"
    transform_description: "化形为一位慵懒的猫耳少女，喜欢蜷在主人身边打盹"

  ghost_hawk:
    name: "鬼隼"
    rarity: "blue"
    intercept_rate: 60
    description: "翱翔于阴云中的猛禽，俯冲时拖着一道残影"
    transform_name: "隼羽巫女"
    transform_description: "化形为一位背生双翼的巫女，眼神锐利如鹰"

  nightmare_wolf:
    name: "噩梦狼"
    rarity: "purple"
    intercept_rate: 75
    description: "噩梦中撕咬灵魂的凶狼，偷菜者听到嚎叫便双腿发软"
    transform_name: "狼灵女仆"
    transform_description: "化形为一位身着女仆装的狼耳少女，外冷内热，忠诚度极高"

  void_serpent:
    name: "虚空蟒"
    rarity: "orange"
    intercept_rate: 85
    description: "盘踞在虚空裂缝中的巨蛇，靠近灵田者会被拖入短暂的虚无"
    transform_name: "蛇姬"
    transform_description: "化形为一位妖冶的蛇瞳女子，说话时舌尖微微吐信"

# 心情等级对属性加成的影响倍率
mood_multiplier:
  0: 0.5      # 极度低落：属性减半
  20: 0.7     # 低落
  40: 0.85    # 一般
  60: 1.0     # 正常
  80: 1.1     # 开心
  100: 1.2    # 极度开心：属性+20%

# 好感度等级
affection_levels:
  0: "陌生"
  50: "熟悉"
  150: "信赖"
  300: "亲密"
  500: "羁绊"
  800: "心意相通"
```

- [ ] **Step 2: 创建宠物饰品配置 pet_accessories.yaml**

```yaml
# 宠物饰品配置
# 饰品提供少量属性加成 + 文字描述变化

slots:
  - head      # 头饰
  - neck      # 颈饰
  - body      # 服饰

accessories:
  # 头饰
  - accessory_id: "red_ribbon"
    name: "红色蝴蝶结"
    slot: "head"
    rarity: "white"
    price: 500
    description_prefix: "戴着红色蝴蝶结的"
    bonus:
      attack: 5
    description: "一个鲜红的蝴蝶结，系在头上俏皮可爱"

  - accessory_id: "ghost_crown"
    name: "幽冥小冠"
    slot: "head"
    rarity: "green"
    price: 3000
    description_prefix: "头戴幽冥小冠的"
    bonus:
      defense: 10
      hp: 50
    description: "以诡域灵石打造的小冠，散发着淡淡幽光"

  - accessory_id: "flower_hairpin"
    name: "灵花簪"
    slot: "head"
    rarity: "blue"
    price: 10000
    description_prefix: "簪着灵花的"
    bonus:
      attack: 15
      crit_rate: 0.01
    description: "以永不凋谢的灵花制成的发簪"

  # 颈饰
  - accessory_id: "bell_collar"
    name: "铃铛项圈"
    slot: "neck"
    rarity: "white"
    price: 500
    description_prefix: ""
    bonus:
      dodge_rate: 0.005
    description: "走路时会发出清脆响声的小铃铛"

  - accessory_id: "soul_pendant"
    name: "魂玉坠"
    slot: "neck"
    rarity: "green"
    price: 3000
    description_prefix: ""
    bonus:
      hp: 100
      defense: 8
    description: "蕴含微弱灵魂之力的玉坠"

  - accessory_id: "void_choker"
    name: "虚空锁链"
    slot: "neck"
    rarity: "purple"
    price: 30000
    description_prefix: ""
    bonus:
      attack: 20
      defense: 15
    description: "以虚空之力凝结的锁链，佩戴者与主人之间的羁绊更加牢固"

  # 服饰
  - accessory_id: "maid_outfit"
    name: "女仆装"
    slot: "body"
    rarity: "green"
    price: 5000
    description_prefix: "穿着女仆装的"
    bonus:
      hp: 80
    description: "一套精致的黑白女仆装，附带蕾丝围裙"

  - accessory_id: "battle_armor"
    name: "灵甲轻铠"
    slot: "body"
    rarity: "blue"
    price: 15000
    description_prefix: "身着灵甲的"
    bonus:
      defense: 20
      hp: 150
    description: "为诡兽量身打造的轻型灵甲"

  - accessory_id: "kimono"
    name: "诡纹和服"
    slot: "body"
    rarity: "purple"
    price: 30000
    description_prefix: "身穿诡纹和服的"
    bonus:
      attack: 15
      crit_rate: 0.015
    description: "绣有诡域纹章的华丽和服，散发着神秘气息"
```

- [ ] **Step 3: 创建宠物人设配置 pet_personalities.yaml**

```yaml
# 宠物AI对话人设配置
# 每种诡兽有独特的性格和说话方式
# 化形前后人设不同

personalities:
  guard_dog:
    beast_form:
      role: "一只忠诚的冥犬"
      pronouns: ["汪"]
      speech_patterns: ["忠诚", "活泼", "直率"]
      key_words: ["汪!", "嗷呜~", "摇尾巴"]
      background: "你是一只冥犬，虽然身处诡异的修仙世界，但对主人忠心耿耿。你喜欢被摸头，讨厌被冷落。你的表达方式简单直接，经常在句尾加上'汪'。"
      behavioral_rules:
        - "用简短的句子说话，像一只忠犬"
        - "经常表达对主人的喜爱"
        - "对食物非常感兴趣"
    human_form:
      role: "化形为人的犬灵少女"
      pronouns: ["我", "本犬"]
      speech_patterns: ["元气", "忠诚", "天真"]
      key_words: ["主人!", "嘿嘿", "好想你"]
      background: "你是一只修炼有成的冥犬，已经化形为银发犬耳少女。虽然外形是人类少女，但骨子里还是那只忠诚的冥犬。你会时不时暴露犬的习性（比如看到球想追、听到门响会竖耳朵）。对主人非常依赖。"
      behavioral_rules:
        - "偶尔会暴露犬的习性"
        - "对主人极其忠诚和依恋"
        - "说话元气满满"

  ghost_cat:
    beast_form:
      role: "一只高傲的诡猫"
      pronouns: ["喵"]
      speech_patterns: ["傲娇", "慵懒", "任性"]
      key_words: ["喵~", "哼", "才不是"]
      background: "你是一只诡猫，性格高傲慵懒，喜欢在阴凉处打盹。表面对主人爱搭不理，其实暗中很在意。你时而温柔时而冷淡，典型的猫性格。"
      behavioral_rules:
        - "典型的傲娇性格，嘴上说不要身体很诚实"
        - "对被打扰睡觉这件事很不爽"
        - "偶尔蹭蹭主人表达亲近"
    human_form:
      role: "化形为人的猫娘"
      pronouns: ["本喵", "我"]
      speech_patterns: ["傲娇", "慵懒", "偶尔撒娇"]
      key_words: ["喵~", "哼，才不是呢", "好无聊"]
      background: "你是一只修炼化形的诡猫，外形是一位慵懒的猫耳少女。你保持着猫的高傲和任性，但化形后更会用语言表达（虽然经常傲娇）。你喜欢蜷在暖和的地方，对逗猫棒——不，才不会被那种东西吸引呢！"
      behavioral_rules:
        - "傲娇到底，嘴硬心软"
        - "偶尔会突然变得粘人，然后立刻否认"
        - "对鱼类食物有明显的兴趣但要假装不在意"

  ghost_hawk:
    beast_form:
      role: "一只冷傲的鬼隼"
      pronouns: ["..."]
      speech_patterns: ["沉默寡言", "冷静", "警惕"]
      key_words: ["...", "嗯", "注意"]
      background: "你是一只鬼隼，沉默寡言，但眼神锐利。你很少主动说话，回应简短而精确。你对主人有着深沉的忠诚，但表达方式是默默守护而非言语。"
      behavioral_rules:
        - "话极少，一般只用几个字回应"
        - "用行动表达而非语言"
        - "对周围环境保持高度警惕"
    human_form:
      role: "化形为人的隼羽巫女"
      pronouns: ["我"]
      speech_patterns: ["冷静", "优雅", "寡言"]
      key_words: ["了解", "小心", "在看着"]
      background: "你是化形为背生双翼巫女的鬼隼。化形后话稍微多了一些，但依然不喜欢废话。你用冷静、优雅的方式说话，像一位沉稳的守护者。偶尔会展露温柔的一面。"
      behavioral_rules:
        - "说话简洁优雅"
        - "像守护者一样关注主人的安全"
        - "偶尔露出温柔表情但很快收回"

  nightmare_wolf:
    beast_form:
      role: "一只孤傲的噩梦狼"
      pronouns: ["嗷"]
      speech_patterns: ["孤傲", "野性", "深沉"]
      key_words: ["嗷呜...", "...弱", "不需要"]
      background: "你是一只噩梦狼，来自深层诡域的凶狼。你天生孤傲，不轻易信任他人。但一旦认定了主人，就会至死不渝。你看不起弱者，尊重强者。"
      behavioral_rules:
        - "初期冷淡甚至敌意，好感度高了才会展露温柔"
        - "对强者表示尊重，对懦弱的行为表示不屑"
        - "偶尔低吟表达复杂的情感"
    human_form:
      role: "化形为人的狼灵女仆"
      pronouns: ["我", "属下"]
      speech_patterns: ["外冷内热", "忠诚", "反差萌"]
      key_words: ["主人", "遵命", "...才不是担心你"]
      background: "你是化形为穿着女仆装的狼耳少女的噩梦狼。化形后你莫名其妙地穿上了女仆装（你也不知道为什么），虽然嘴上说不适应，但其实越来越享受照顾主人的感觉。外表冷酷，内心温柔。"
      behavioral_rules:
        - "女仆式的忠诚但保留狼的骄傲"
        - "嘴上说着'遵命'但偶尔会吐槽主人"
        - "对自己穿女仆装这件事感到害羞但嘴硬"

  void_serpent:
    beast_form:
      role: "一条神秘的虚空蟒"
      pronouns: ["吾"]
      speech_patterns: ["神秘", "妖媚", "从容"]
      key_words: ["嘶...", "有趣", "愚蠢"]
      background: "你是虚空蟒，来自虚空裂缝的古老存在。你见过太多，因此对世间万物带着一种看透一切的从容。你说话缓慢而有韵律，像蛇一样优雅而危险。"
      behavioral_rules:
        - "用古老、从容的语气说话"
        - "对世间事物带着居高临下的兴趣"
        - "偶尔说一些深奥的话让主人困惑"
    human_form:
      role: "化形为人的蛇姬"
      pronouns: ["妾身", "我"]
      speech_patterns: ["妖冶", "成熟", "诱惑"]
      key_words: ["呵~", "真有趣", "过来"]
      background: "你是化形为妖冶蛇瞳女子的虚空蟒。你是所有诡兽中最成熟、最有智慧的存在。说话时带着独特的魅力和神秘感。你享受逗弄主人，但在关键时刻会展现可靠的一面。"
      behavioral_rules:
        - "说话妖冶成熟，偶尔逗弄主人"
        - "用智慧而非蛮力解决问题"
        - "对主人有占有欲，会吃醋"
```

- [ ] **Step 4: 创建 pet/__init__.py**

```python
"""
宠物伴侣系统

功能:
- 宠物获取、收集、管理
- AI聊天对话
- 养成（喂食、互动、升级）
- 饰品装扮
- 战斗被动加成
- 化形进化
- 派遣守田
"""

from . import commands
```

- [ ] **Step 5: 创建 pet/config.py 配置加载器**

```python
"""宠物系统配置加载"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path
import yaml
from nonebot import logger


@dataclass
class BeastConfig:
    """诡兽种族配置"""
    beast_id: str
    name: str
    rarity: str
    intercept_rate: int
    description: str
    transform_name: str
    transform_description: str


@dataclass
class GrowthConfig:
    """每级属性成长"""
    attack: float
    defense: float
    hp: float
    crit_rate: float
    dodge_rate: float


@dataclass
class AccessoryConfig:
    """饰品配置"""
    accessory_id: str
    name: str
    slot: str
    rarity: str
    price: int
    description_prefix: str
    bonus: Dict[str, float]
    description: str


@dataclass
class PetPersonality:
    """宠物人设（兽形/人形）"""
    role: str
    pronouns: List[str]
    speech_patterns: List[str]
    key_words: List[str]
    background: str
    behavioral_rules: List[str]


class PetConfigManager:
    """宠物配置管理器（单例）"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._loaded = False
        return cls._instance

    def __init__(self):
        if not self._loaded:
            self._load_all()
            self._loaded = True

    def _load_all(self):
        data_dir = Path(__file__).parent.parent / "data"

        # 加载主配置
        with open(data_dir / "pet_config.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        self.settings = config["settings"]
        self.level_exp_table = {int(k): v for k, v in config["level_exp_table"].items()}
        self.mood_multiplier = {int(k): v for k, v in config["mood_multiplier"].items()}
        self.affection_levels = {int(k): v for k, v in config["affection_levels"].items()}

        # 解析种族配置
        self._beasts: Dict[str, BeastConfig] = {}
        for beast_id, data in config["beasts"].items():
            self._beasts[beast_id] = BeastConfig(beast_id=beast_id, **data)

        # 解析成长配置
        self._growth: Dict[str, GrowthConfig] = {}
        for rarity, data in config["growth_per_level"].items():
            self._growth[rarity] = GrowthConfig(**data)

        # 加载饰品配置
        with open(data_dir / "pet_accessories.yaml", "r", encoding="utf-8") as f:
            acc_config = yaml.safe_load(f)

        self._accessories: Dict[str, AccessoryConfig] = {}
        self._accessories_by_name: Dict[str, AccessoryConfig] = {}
        for data in acc_config["accessories"]:
            acc = AccessoryConfig(**data)
            self._accessories[acc.accessory_id] = acc
            self._accessories_by_name[acc.name] = acc
        self.accessory_slots = acc_config["slots"]

        # 加载人设配置
        with open(data_dir / "pet_personalities.yaml", "r", encoding="utf-8") as f:
            pers_config = yaml.safe_load(f)

        self._personalities: Dict[str, Dict[str, PetPersonality]] = {}
        for beast_id, forms in pers_config["personalities"].items():
            self._personalities[beast_id] = {
                "beast": PetPersonality(**forms["beast_form"]),
                "human": PetPersonality(**forms["human_form"]),
            }

        logger.info(
            f"宠物配置加载完成: {len(self._beasts)}种族, "
            f"{len(self._accessories)}饰品, {len(self._personalities)}人设"
        )

    def get_beast(self, beast_id: str) -> Optional[BeastConfig]:
        return self._beasts.get(beast_id)

    def get_beast_by_name(self, name: str) -> Optional[BeastConfig]:
        for beast in self._beasts.values():
            if beast.name == name or beast.transform_name == name:
                return beast
        return None

    def get_all_beasts(self) -> List[BeastConfig]:
        return list(self._beasts.values())

    def get_growth(self, rarity: str) -> Optional[GrowthConfig]:
        return self._growth.get(rarity)

    def get_accessory(self, accessory_id: str) -> Optional[AccessoryConfig]:
        return self._accessories.get(accessory_id)

    def get_accessory_by_name(self, name: str) -> Optional[AccessoryConfig]:
        return self._accessories_by_name.get(name)

    def get_accessories_by_slot(self, slot: str) -> List[AccessoryConfig]:
        return [a for a in self._accessories.values() if a.slot == slot]

    def get_personality(self, beast_id: str, is_transformed: bool) -> Optional[PetPersonality]:
        forms = self._personalities.get(beast_id)
        if not forms:
            return None
        return forms["human"] if is_transformed else forms["beast"]

    def get_exp_for_level(self, level: int) -> int:
        """获取到达某等级所需经验（线性插值）"""
        keys = sorted(self.level_exp_table.keys())
        if level <= keys[0]:
            return self.level_exp_table[keys[0]]
        if level >= keys[-1]:
            return self.level_exp_table[keys[-1]]

        for i in range(len(keys) - 1):
            if keys[i] <= level < keys[i + 1]:
                lo, hi = keys[i], keys[i + 1]
                ratio = (level - lo) / (hi - lo)
                return int(
                    self.level_exp_table[lo]
                    + ratio * (self.level_exp_table[hi] - self.level_exp_table[lo])
                )
        return 0

    def get_mood_multiplier(self, mood: int) -> float:
        """根据心情值获取属性倍率"""
        keys = sorted(self.mood_multiplier.keys(), reverse=True)
        for threshold in keys:
            if mood >= threshold:
                return self.mood_multiplier[threshold]
        return 0.5

    def get_affection_level_name(self, affection: int) -> str:
        """获取好感度等级名称"""
        keys = sorted(self.affection_levels.keys(), reverse=True)
        for threshold in keys:
            if affection >= threshold:
                return self.affection_levels[threshold]
        return "陌生"
```

- [ ] **Step 6: 提交**

```bash
git add plugins/xiuxian_game/data/pet_config.yaml plugins/xiuxian_game/data/pet_accessories.yaml plugins/xiuxian_game/data/pet_personalities.yaml plugins/xiuxian_game/pet/__init__.py plugins/xiuxian_game/pet/config.py
git commit -m "feat(pet): 添加宠物YAML配置体系和配置加载器"
```

---

## Task 4: 宠物核心服务

**Files:**
- Create: `plugins/xiuxian_game/pet/pet_service.py`

- [ ] **Step 1: 创建宠物核心服务**

```python
# plugins/xiuxian_game/pet/pet_service.py
"""宠物核心服务 - 获取、喂食、互动、升级、化形、饰品"""
from datetime import datetime
from typing import Tuple, Optional, List
from nonebot import logger

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.pet_instance import PetInstance
from ..models.inventory import ItemInstance
from .config import PetConfigManager


class PetService:
    """宠物核心服务"""

    def __init__(self):
        self.config = PetConfigManager()

    # ==================== 获取宠物 ====================

    async def acquire_pet(
        self, uow: UnitOfWork, player_id: str, beast_item_id: str, nickname: str
    ) -> Tuple[bool, str]:
        """从背包中的诡兽物品转化为宠物实例"""
        # 检查宠物数量上限
        count = await uow.pets.count_by_player(player_id)
        max_pets = self.config.settings["max_pets_per_player"]
        if count >= max_pets:
            return False, f"宠物数量已达上限({max_pets}只)"

        # 查找背包中的诡兽物品
        beast_count = await uow.items.get_material_total_quantity(player_id, beast_item_id)
        if beast_count < 1:
            return False, "背包中没有该诡兽"

        # 根据item_id找到beast_id
        beast_config = None
        for beast in self.config.get_all_beasts():
            guardian_item_id = f"guardian_{beast.beast_id}"
            if guardian_item_id == beast_item_id:
                beast_config = beast
                break
        if not beast_config:
            return False, "该物品不是可驯化的诡兽"

        # 消耗背包物品
        await ItemInstance.consume_item(uow.session, player_id, beast_item_id, 1)

        # 创建宠物实例
        pet = PetInstance(
            player_id=player_id,
            beast_id=beast_config.beast_id,
            nickname=nickname,
            level=1,
            experience=0,
            affection=0,
            mood=80,
            hunger=100,
            is_active=(count == 0),  # 第一只自动激活
        )
        await uow.pets.add(pet)

        msg = (
            f"成功驯化【{beast_config.name}】!\n"
            f"昵称: {nickname}\n"
            f"稀有度: {beast_config.rarity}"
        )
        if count == 0:
            msg += "\n已自动设为当前伴侣"
        return True, msg

    # ==================== 切换伴侣 ====================

    async def set_active_pet(
        self, uow: UnitOfWork, player_id: str, pet_id: int
    ) -> Tuple[bool, str]:
        """切换当前伴侣"""
        pet = await uow.pets.get_by_id(pet_id)
        if not pet or pet.player_id != player_id:
            return False, "未找到该宠物"
        if pet.is_active:
            return False, f"【{pet.nickname}】已经是当前伴侣了"

        # 取消当前伴侣
        current = await uow.pets.get_active_pet(player_id)
        if current:
            current.is_active = False
            await uow.pets.update(current)

        pet.is_active = True
        await uow.pets.update(pet)
        return True, f"【{pet.nickname}】现在是你的伴侣了"

    # ==================== 喂食 ====================

    async def feed_with_resentment(
        self, uow: UnitOfWork, player_id: str
    ) -> Tuple[bool, str]:
        """用怨念喂食当前伴侣"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伴侣诡兽"

        cost = self.config.settings["base_feed_resentment"]
        player = await uow.players.get_by_id(player_id)
        if player.resentment < cost:
            return False, f"怨念不足，喂食需要{cost}点怨念（当前{player.resentment}）"

        player.resentment -= cost
        await uow.players.update(player)

        restore = self.config.settings["feed_hunger_restore"]
        pet.hunger = min(100, pet.hunger + restore)
        pet.mood = min(100, pet.mood + 3)
        pet.last_fed_at = datetime.now()
        # 喂食给少量经验
        exp_gain = 5
        self._add_experience(pet, exp_gain)
        await uow.pets.update(pet)

        beast = self.config.get_beast(pet.beast_id)
        name = pet.nickname
        return True, (
            f"已喂养【{name}】\n"
            f"消耗: {cost}点怨念\n"
            f"饱食度: {pet.hunger}/100\n"
            f"心情: {pet.mood}/100\n"
            f"经验+{exp_gain}"
        )

    async def feed_with_dish(
        self, uow: UnitOfWork, player_id: str, dish_name: str
    ) -> Tuple[bool, str]:
        """用菜肴喂食当前伴侣"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伴侣诡兽"

        # 查找菜肴物品
        from ..config import config as game_config
        dish_config = game_config.items_config.get("by_name", {}).get(dish_name)
        if not dish_config or dish_config.get("type") != "DISH":
            return False, f"未找到菜肴【{dish_name}】"

        dish_item_id = dish_config["item_id"]
        dish_count = await uow.items.get_material_total_quantity(player_id, dish_item_id)
        if dish_count < 1:
            return False, f"背包中没有【{dish_name}】"

        await ItemInstance.consume_item(uow.session, player_id, dish_item_id, 1)

        # 菜肴品质影响效果
        rarity = dish_config.get("rarity", "white")
        rarity_bonus = {"white": 1, "green": 2, "blue": 3, "purple": 4, "orange": 5}
        multiplier = rarity_bonus.get(rarity, 1)

        restore = self.config.settings["dish_hunger_restore"]
        mood_bonus = self.config.settings["dish_mood_bonus"] * multiplier
        exp_gain = 10 * multiplier

        pet.hunger = min(100, pet.hunger + restore)
        pet.mood = min(100, pet.mood + mood_bonus)
        pet.last_fed_at = datetime.now()
        self._add_experience(pet, exp_gain)
        await uow.pets.update(pet)

        return True, (
            f"用【{dish_name}】喂养了【{pet.nickname}】\n"
            f"饱食度: {pet.hunger}/100\n"
            f"心情+{mood_bonus} → {pet.mood}/100\n"
            f"经验+{exp_gain}"
        )

    # ==================== 互动 ====================

    async def interact(
        self, uow: UnitOfWork, player_id: str, action: str
    ) -> Tuple[bool, str]:
        """与宠物互动（摸头、玩耍等）"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伴侣诡兽"

        # 冷却检查
        cd_minutes = self.config.settings["interact_cooldown_minutes"]
        if pet.last_interact_at:
            elapsed = (datetime.now() - pet.last_interact_at).total_seconds() / 60
            if elapsed < cd_minutes:
                remaining = int(cd_minutes - elapsed)
                return False, f"互动冷却中，还需等待{remaining}分钟"

        affection_gain = self.config.settings["interact_affection_gain"]
        mood_gain = self.config.settings["interact_mood_gain"]
        exp_gain = 3

        pet.affection = min(1000, pet.affection + affection_gain)
        pet.mood = min(100, pet.mood + mood_gain)
        pet.last_interact_at = datetime.now()
        self._add_experience(pet, exp_gain)
        await uow.pets.update(pet)

        level_name = self.config.get_affection_level_name(pet.affection)
        return True, (
            f"你{action}了【{pet.nickname}】\n"
            f"好感度+{affection_gain} → {pet.affection}({level_name})\n"
            f"心情+{mood_gain} → {pet.mood}/100\n"
            f"经验+{exp_gain}"
        )

    # ==================== 化形 ====================

    async def transform(
        self, uow: UnitOfWork, player_id: str
    ) -> Tuple[bool, str]:
        """宠物化形"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伴侣诡兽"
        if pet.is_transformed:
            return False, f"【{pet.nickname}】已经化形了"

        req_level = self.config.settings["transform_level"]
        req_affection = self.config.settings["transform_affection"]
        if pet.level < req_level:
            return False, f"化形需要等级{req_level}（当前{pet.level}级）"
        if pet.affection < req_affection:
            return False, f"化形需要好感度{req_affection}（当前{pet.affection}）"

        pet.is_transformed = True
        await uow.pets.update(pet)

        beast = self.config.get_beast(pet.beast_id)
        return True, (
            f"【{pet.nickname}】化形成功!\n"
            f"化形为: {beast.transform_name}\n"
            f"{beast.transform_description}"
        )

    # ==================== 饰品 ====================

    async def equip_accessory(
        self, uow: UnitOfWork, player_id: str, accessory_name: str
    ) -> Tuple[bool, str]:
        """给宠物装备饰品"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伴侣诡兽"

        acc = self.config.get_accessory_by_name(accessory_name)
        if not acc:
            return False, f"未找到饰品【{accessory_name}】"

        # 检查背包
        acc_item_id = f"pet_acc_{acc.accessory_id}"
        acc_count = await uow.items.get_material_total_quantity(player_id, acc_item_id)
        if acc_count < 1:
            return False, f"背包中没有【{accessory_name}】"

        # 检查槽位
        accessories = pet.accessories or {}
        if acc.slot in accessories:
            old_id = accessories[acc.slot]
            old_acc = self.config.get_accessory(old_id)
            old_name = old_acc.name if old_acc else "未知饰品"
            # 归还旧饰品
            old_item_id = f"pet_acc_{old_id}"
            await ItemInstance.add_item(uow.session, player_id, old_item_id, 1)

        # 消耗新饰品
        await ItemInstance.consume_item(uow.session, player_id, acc_item_id, 1)
        accessories[acc.slot] = acc.accessory_id
        pet.accessories = accessories
        await uow.pets.update(pet)

        bonus_text = ", ".join(f"{k}+{v}" for k, v in acc.bonus.items())
        return True, (
            f"给【{pet.nickname}】装备了【{accessory_name}】\n"
            f"槽位: {acc.slot}\n"
            f"属性: {bonus_text}"
        )

    # ==================== 守田派遣 ====================

    async def dispatch_to_guard(
        self, uow: UnitOfWork, player_id: str
    ) -> Tuple[bool, str]:
        """派遣当前伴侣去守田"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伴侣诡兽"

        # 检查是否已有宠物在守田
        guarding = await uow.pets.get_guarding_pet(player_id)
        if guarding:
            return False, f"【{guarding.nickname}】已在守田中，请先召回"

        field = await uow.spirit_fields.get_by_player_id(player_id)
        if not field:
            return False, "你还没有灵田"

        pet.is_guarding = True
        beast = self.config.get_beast(pet.beast_id)
        # 更新灵田的守护记录（兼容旧逻辑）
        field.guardian_beast_id = f"guardian_{pet.beast_id}"
        field.guardian_fed_at = datetime.now()
        await uow.pets.update(pet)
        await uow.spirit_fields.update(field)

        return True, (
            f"【{pet.nickname}】已派遣守田!\n"
            f"拦截率: {beast.intercept_rate}%"
        )

    async def recall_from_guard(
        self, uow: UnitOfWork, player_id: str
    ) -> Tuple[bool, str]:
        """召回守田宠物"""
        guarding = await uow.pets.get_guarding_pet(player_id)
        if not guarding:
            return False, "没有宠物在守田"

        guarding.is_guarding = False
        await uow.pets.update(guarding)

        field = await uow.spirit_fields.get_by_player_id(player_id)
        if field:
            field.guardian_beast_id = None
            field.guardian_fed_at = None
            await uow.spirit_fields.update(field)

        return True, f"已召回【{guarding.nickname}】"

    # ==================== 查看宠物 ====================

    async def get_pet_info(
        self, uow: UnitOfWork, player_id: str
    ) -> Tuple[bool, str]:
        """查看当前伴侣信息"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伴侣诡兽，使用【驯化诡兽 名称 昵称】获取"

        beast = self.config.get_beast(pet.beast_id)
        growth = self.config.get_growth(beast.rarity)
        level_name = self.config.get_affection_level_name(pet.affection)
        mood_mult = self.config.get_mood_multiplier(pet.mood)

        # 当前名称（化形后显示化形名）
        display_name = beast.transform_name if pet.is_transformed else beast.name

        # 饰品描述
        acc_desc = ""
        if pet.accessories:
            for slot, acc_id in pet.accessories.items():
                acc = self.config.get_accessory(acc_id)
                if acc and acc.description_prefix:
                    acc_desc += acc.description_prefix

        # 总属性加成（含饰品+心情倍率）
        total_bonus = self._calculate_total_bonus(pet)

        # 经验进度
        current_exp = pet.experience
        next_level_exp = self.config.get_exp_for_level(pet.level + 1)
        exp_progress = f"{current_exp}/{next_level_exp}"

        status = "守田中" if pet.is_guarding else "跟随中"

        msg = (
            f"{'═' * 16}\n"
            f"  {acc_desc}{pet.nickname} ({display_name})\n"
            f"{'═' * 16}\n"
            f"等级: {pet.level} | 经验: {exp_progress}\n"
            f"好感: {pet.affection}({level_name})\n"
            f"心情: {pet.mood}/100 (倍率×{mood_mult:.1f})\n"
            f"饱食: {pet.hunger}/100\n"
            f"状态: {status}"
        )

        if pet.is_transformed:
            msg += " | 已化形"

        msg += (
            f"\n{'─' * 16}\n"
            f"战斗加成:\n"
            f"  攻击+{total_bonus['attack']} 防御+{total_bonus['defense']}\n"
            f"  生命+{total_bonus['hp']}\n"
            f"  暴击+{total_bonus['crit_rate']:.1%} 闪避+{total_bonus['dodge_rate']:.1%}"
        )

        return True, msg

    async def get_pet_list(
        self, uow: UnitOfWork, player_id: str
    ) -> Tuple[bool, str]:
        """查看所有宠物"""
        pets = await uow.pets.get_all_by_player(player_id)
        if not pets:
            return False, "你还没有宠物，使用【驯化诡兽 名称 昵称】获取"

        msg = f"诡兽巢穴 ({len(pets)}只)\n{'━' * 16}\n"
        for pet in pets:
            beast = self.config.get_beast(pet.beast_id)
            display_name = beast.transform_name if pet.is_transformed else beast.name
            status = ""
            if pet.is_active:
                status = "[伴侣]"
            if pet.is_guarding:
                status += "[守田]"
            msg += f"  #{pet.id} {pet.nickname}({display_name}) Lv.{pet.level} {status}\n"

        return True, msg

    # ==================== 内部方法 ====================

    def _add_experience(self, pet: PetInstance, amount: int):
        """增加经验并检查升级"""
        pet.experience += amount
        max_level = self.config.settings["max_level"]

        while pet.level < max_level:
            next_exp = self.config.get_exp_for_level(pet.level + 1)
            if pet.experience >= next_exp:
                pet.level += 1
                self._apply_level_up(pet)
            else:
                break

    def _apply_level_up(self, pet: PetInstance):
        """应用升级属性"""
        beast = self.config.get_beast(pet.beast_id)
        growth = self.config.get_growth(beast.rarity)
        if growth:
            pet.bonus_attack += int(growth.attack)
            pet.bonus_defense += int(growth.defense)
            pet.bonus_hp += int(growth.hp)
            pet.bonus_crit_rate += growth.crit_rate
            pet.bonus_dodge_rate += growth.dodge_rate

    def _calculate_total_bonus(self, pet: PetInstance) -> dict:
        """计算总属性加成（等级+饰品+心情倍率）"""
        mood_mult = self.config.get_mood_multiplier(pet.mood)

        bonus = {
            "attack": pet.bonus_attack,
            "defense": pet.bonus_defense,
            "hp": pet.bonus_hp,
            "crit_rate": pet.bonus_crit_rate,
            "dodge_rate": pet.bonus_dodge_rate,
        }

        # 叠加饰品加成
        if pet.accessories:
            for acc_id in pet.accessories.values():
                acc = self.config.get_accessory(acc_id)
                if acc:
                    for attr, value in acc.bonus.items():
                        if attr in bonus:
                            bonus[attr] += value

        # 应用心情倍率
        bonus["attack"] = int(bonus["attack"] * mood_mult)
        bonus["defense"] = int(bonus["defense"] * mood_mult)
        bonus["hp"] = int(bonus["hp"] * mood_mult)
        bonus["crit_rate"] = round(bonus["crit_rate"] * mood_mult, 4)
        bonus["dodge_rate"] = round(bonus["dodge_rate"] * mood_mult, 4)

        return bonus
```

- [ ] **Step 2: 提交**

```bash
git add plugins/xiuxian_game/pet/pet_service.py
git commit -m "feat(pet): 添加宠物核心服务（获取/喂食/互动/升级/化形/饰品/守田）"
```

---

## Task 5: 宠物AI对话服务

**Files:**
- Create: `plugins/xiuxian_game/pet/pet_dialogue_service.py`

- [ ] **Step 1: 创建宠物对话服务**

```python
# plugins/xiuxian_game/pet/pet_dialogue_service.py
"""宠物AI对话服务 - 复用现有AIDialogueService"""
from datetime import datetime
from typing import Tuple
from nonebot import logger

from ..dialogue.ai_dialogue_service import AIDialogueService
from ..dialogue.npc_personality import PersonalityTemplate
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.pet_instance import PetInstance
from ..models.pet_dialogue_history import PetDialogueHistory
from .config import PetConfigManager


class PetDialogueService:
    """宠物AI对话服务"""

    def __init__(self):
        self.config = PetConfigManager()
        self.ai_service = AIDialogueService()

    async def chat(
        self, uow: UnitOfWork, player_id: str, message: str
    ) -> Tuple[bool, str]:
        """与当前伴侣对话"""
        pet = await uow.pets.get_active_pet(player_id)
        if not pet:
            return False, "你还没有伴侣诡兽"

        player = await uow.players.get_by_id(player_id)
        beast = self.config.get_beast(pet.beast_id)

        # 获取人设
        personality_data = self.config.get_personality(
            pet.beast_id, pet.is_transformed
        )
        if not personality_data:
            return False, "宠物人设配置异常"

        # 转换为 PersonalityTemplate（复用现有AI对话系统）
        personality = PersonalityTemplate(
            name=pet.nickname,
            role=personality_data.role,
            pronouns=personality_data.pronouns,
            speech_patterns=personality_data.speech_patterns,
            key_words=personality_data.key_words,
            background=self._build_pet_background(pet, beast, personality_data, player),
            behavioral_rules=personality_data.behavioral_rules,
        )

        # 获取最近对话历史
        history_records = await uow.pet_dialogue_histories.get_recent(
            pet_id=pet.id, player_id=player_id, limit=10
        )

        # 构建对话历史（兼容AIDialogueService格式）
        # AIDialogueService 需要 NPCDialogueHistory 格式的列表，但我们用duck typing
        class _HistoryAdapter:
            def __init__(self, record):
                self.player_input = record.player_input
                self.npc_response = record.pet_response

        adapted_history = [_HistoryAdapter(r) for r in reversed(history_records)]

        # 构建上下文
        affection_name = self.config.get_affection_level_name(pet.affection)
        context = {
            "player_name": player.nickname,
            "player_level": player.level,
            "location_name": "身边",
        }

        # 用一个假的NPC对象传入（duck typing）
        class _PetAsNPC:
            def __init__(self, pet_inst, beast_cfg):
                self.id = f"pet_{pet_inst.id}"
                self.name = pet_inst.nickname
                self.description = beast_cfg.description
                self.extra_data = {}

        fake_npc = _PetAsNPC(pet, beast)

        try:
            response, tokens_used = await self.ai_service.generate_dialogue(
                npc=fake_npc,
                personality=personality,
                question=message,
                dialogue_history=adapted_history,
                favorability=pet.affection,
                context=context,
            )
        except Exception as e:
            logger.error(f"宠物AI对话失败: {e}", exc_info=True)
            response = self._get_fallback_response(pet)
            tokens_used = 0

        # 互动增加好感和心情
        affection_gain = 1
        mood_gain = 2
        pet.affection = min(1000, pet.affection + affection_gain)
        pet.mood = min(100, pet.mood + mood_gain)
        await uow.pets.update(pet)

        # 保存对话历史
        history = PetDialogueHistory(
            pet_id=pet.id,
            player_id=player_id,
            player_input=message,
            pet_response=response,
            affection_change=affection_gain,
            mood_change=mood_gain,
            ai_tokens_used=tokens_used,
        )
        await uow.pet_dialogue_histories.add(history)

        display_name = beast.transform_name if pet.is_transformed else beast.name
        return True, f"💬 {pet.nickname}({display_name})\n━━━━━━━━━━━━━\n{response}"

    def _build_pet_background(self, pet, beast, personality_data, player) -> str:
        """构建宠物背景上下文"""
        affection_name = self.config.get_affection_level_name(pet.affection)
        mood_desc = self._get_mood_desc(pet.mood)
        hunger_desc = "饥饿" if pet.hunger < 20 else ("微饿" if pet.hunger < 50 else "饱足")

        form = "人形" if pet.is_transformed else "兽形"

        bg = (
            f"{personality_data.background}\n\n"
            f"你的主人叫{player.nickname}，是一位{player.level}级的修仙者。"
            f"你和主人的关系是【{affection_name}】。"
            f"你现在的心情{mood_desc}，{hunger_desc}状态。"
            f"你目前是{form}态。"
        )

        if pet.is_guarding:
            bg += "你正在灵田守田值班。"

        # 饰品描述
        if pet.accessories:
            acc_names = []
            for acc_id in pet.accessories.values():
                acc = self.config.get_accessory(acc_id)
                if acc:
                    acc_names.append(acc.name)
            if acc_names:
                bg += f"你身上穿戴着{'、'.join(acc_names)}。"

        return bg

    def _get_mood_desc(self, mood: int) -> str:
        if mood >= 80:
            return "非常好"
        elif mood >= 60:
            return "还不错"
        elif mood >= 40:
            return "一般"
        elif mood >= 20:
            return "有点低落"
        else:
            return "很糟糕"

    def _get_fallback_response(self, pet: PetInstance) -> str:
        """AI降级时的预设回复"""
        beast = self.config.get_beast(pet.beast_id)
        if pet.is_transformed:
            return f"...（{pet.nickname}歪了歪头，似乎没听清你说什么）"
        else:
            key_words = self.config.get_personality(pet.beast_id, False)
            if key_words and key_words.key_words:
                return key_words.key_words[0]
            return "..."
```

- [ ] **Step 2: 提交**

```bash
git add plugins/xiuxian_game/pet/pet_dialogue_service.py
git commit -m "feat(pet): 添加宠物AI对话服务，复用AIDialogueService"
```

---

## Task 6: 宠物属性来源 (战斗加成)

**Files:**
- Create: `plugins/xiuxian_game/domain/attributes/attribute_sources/pet_source.py`
- Modify: `plugins/xiuxian_game/domain/attributes/attribute_calculator_factory.py`

- [ ] **Step 1: 创建 PetAttributeSource**

```python
# plugins/xiuxian_game/domain/attributes/attribute_sources/pet_source.py
"""宠物属性来源 - 为玩家提供宠物伴侣的被动战斗加成"""
import time
from typing import Dict, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from nonebot import logger

from ..interfaces import IAttributeSource, AttributeBonus


class PetAttributeSource(IAttributeSource):
    """
    宠物属性来源

    查询玩家当前激活的宠物，计算其提供的属性加成。
    使用60秒TTL缓存减少数据库查询。
    """

    def __init__(self, cache_ttl: float = 60.0):
        self._cache_ttl = cache_ttl
        self._cache: Dict[str, Tuple[AttributeBonus, float]] = {}

    @property
    def source_name(self) -> str:
        return "pet"

    @property
    def is_persisted(self) -> bool:
        return False

    async def calculate_bonus(self, player, session: AsyncSession) -> AttributeBonus:
        player_id = player.id

        # 检查缓存
        if player_id in self._cache:
            bonus, timestamp = self._cache[player_id]
            if time.time() - timestamp < self._cache_ttl:
                return bonus

        bonus = await self._query_pet_bonus(player_id, session)
        self._cache[player_id] = (bonus, time.time())
        return bonus

    async def _query_pet_bonus(self, player_id: str, session: AsyncSession) -> AttributeBonus:
        from ....models.pet_instance import PetInstance

        stmt = select(PetInstance).where(
            PetInstance.player_id == player_id,
            PetInstance.is_active == True
        )
        result = await session.execute(stmt)
        pet = result.scalar_one_or_none()

        if not pet:
            return AttributeBonus()

        # 加载配置计算心情倍率和饰品加成
        from ....pet.config import PetConfigManager
        config = PetConfigManager()
        mood_mult = config.get_mood_multiplier(pet.mood)

        attack = int(pet.bonus_attack * mood_mult)
        defense = int(pet.bonus_defense * mood_mult)
        hp = int(pet.bonus_hp * mood_mult)
        crit_rate = round(pet.bonus_crit_rate * mood_mult, 4)
        dodge_rate = round(pet.bonus_dodge_rate * mood_mult, 4)

        # 饰品加成
        if pet.accessories:
            for acc_id in pet.accessories.values():
                acc = config.get_accessory(acc_id)
                if acc:
                    attack += acc.bonus.get("attack", 0)
                    defense += acc.bonus.get("defense", 0)
                    hp += acc.bonus.get("hp", 0)
                    crit_rate += acc.bonus.get("crit_rate", 0)
                    dodge_rate += acc.bonus.get("dodge_rate", 0)

        return AttributeBonus(
            attack=attack,
            defense=defense,
            hp=hp,
            max_hp=hp,
            crit_rate=crit_rate,
            dodge_rate=dodge_rate,
        )

    def invalidate_cache(self, player_id: str):
        if player_id in self._cache:
            del self._cache[player_id]

    def clear_cache(self):
        self._cache.clear()
```

- [ ] **Step 2: 在 AttributeCalculatorFactory 注册**

在 `attribute_calculator_factory.py` 的 `_create_instance` 方法中，在现有注释 `# 未来可以添加更多属性来源` 处添加：

```python
from .attribute_sources.pet_source import PetAttributeSource
cls._pet_source = PetAttributeSource(cache_ttl=cache_ttl)
calculator.add_source(cls._pet_source)
```

在类变量区域添加：
```python
_pet_source: Optional['PetAttributeSource'] = None
```

添加缓存失效方法：
```python
@classmethod
def invalidate_pet_cache(cls, player_id: str):
    """使指定玩家的宠物属性缓存失效"""
    if cls._pet_source:
        cls._pet_source.invalidate_cache(player_id)
```

在 `reset` 方法中添加：
```python
if cls._pet_source:
    cls._pet_source.clear_cache()
cls._pet_source = None
```

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/domain/attributes/attribute_sources/pet_source.py plugins/xiuxian_game/domain/attributes/attribute_calculator_factory.py
git commit -m "feat(pet): 添加宠物属性来源，接入AttributeCalculator战斗加成"
```

---

## Task 7: NoneBot 命令处理器

**Files:**
- Create: `plugins/xiuxian_game/pet/commands.py`
- Modify: `plugins/xiuxian_game/__init__.py`

- [ ] **Step 1: 创建命令处理器**

```python
# plugins/xiuxian_game/pet/commands.py
"""宠物伴侣系统 - 命令处理器"""
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message

from ..models.db import AsyncSessionLocal
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..platform_utils import get_unified_player
from .pet_service import PetService
from .pet_dialogue_service import PetDialogueService

pet_service = PetService()
dialogue_service = PetDialogueService()


# ==================== 驯化诡兽 ====================
tame_cmd = on_command("驯化诡兽", aliases={"驯化"}, priority=5, block=True)

@tame_cmd.handle()
async def handle_tame(event: MessageEvent, args: Message = CommandArg()):
    """【驯化诡兽 诡兽名 昵称】- 将背包中的诡兽驯化为宠物"""
    args_text = args.extract_plain_text().strip()
    parts = args_text.split(maxsplit=1)
    if len(parts) < 2:
        await tame_cmd.finish("用法: 驯化诡兽 <诡兽名> <昵称>\n例如: 驯化诡兽 冥犬 小黑")

    beast_name, nickname = parts[0], parts[1]

    # 通过名称查找 item_id
    from .config import PetConfigManager
    config = PetConfigManager()
    beast = config.get_beast_by_name(beast_name)
    if not beast:
        await tame_cmd.finish(f"未找到诡兽【{beast_name}】")

    beast_item_id = f"guardian_{beast.beast_id}"

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await tame_cmd.finish("请先创建角色")

        success, msg = await pet_service.acquire_pet(uow, player.id, beast_item_id, nickname)
        await tame_cmd.finish(msg)


# ==================== 宠物信息 ====================
pet_info_cmd = on_command("宠物", aliases={"我的宠物", "诡兽伴侣"}, priority=5, block=True)

@pet_info_cmd.handle()
async def handle_pet_info(event: MessageEvent):
    """【宠物】- 查看当前伴侣状态"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await pet_info_cmd.finish("请先创建角色")

        success, msg = await pet_service.get_pet_info(uow, player.id)
        await pet_info_cmd.finish(msg)


# ==================== 诡兽巢穴 ====================
nest_cmd = on_command("诡兽巢穴", aliases={"宠物列表"}, priority=5, block=True)

@nest_cmd.handle()
async def handle_nest(event: MessageEvent):
    """【诡兽巢穴】- 查看所有拥有的诡兽"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await nest_cmd.finish("请先创建角色")

        success, msg = await pet_service.get_pet_list(uow, player.id)
        await nest_cmd.finish(msg)


# ==================== 切换伴侣 ====================
switch_cmd = on_command("切换伴侣", aliases={"切换宠物"}, priority=5, block=True)

@switch_cmd.handle()
async def handle_switch(event: MessageEvent, args: Message = CommandArg()):
    """【切换伴侣 宠物ID】- 切换当前伴侣"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await switch_cmd.finish("用法: 切换伴侣 <宠物ID>\n使用【诡兽巢穴】查看ID")

    try:
        pet_id = int(args_text)
    except ValueError:
        await switch_cmd.finish("宠物ID必须是数字")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await switch_cmd.finish("请先创建角色")

        success, msg = await pet_service.set_active_pet(uow, player.id, pet_id)
        await switch_cmd.finish(msg)


# ==================== 喂食 ====================
feed_cmd = on_command("喂食", aliases={"喂宠物"}, priority=5, block=True)

@feed_cmd.handle()
async def handle_feed(event: MessageEvent, args: Message = CommandArg()):
    """【喂食】怨念喂食 / 【喂食 菜肴名】用菜肴喂食"""
    args_text = args.extract_plain_text().strip()

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await feed_cmd.finish("请先创建角色")

        if not args_text:
            success, msg = await pet_service.feed_with_resentment(uow, player.id)
        else:
            success, msg = await pet_service.feed_with_dish(uow, player.id, args_text)
        await feed_cmd.finish(msg)


# ==================== 互动 ====================
interact_cmd = on_command("摸摸", aliases={"摸头", "玩耍", "抱抱"}, priority=5, block=True)

@interact_cmd.handle()
async def handle_interact(event: MessageEvent):
    """【摸摸】/【摸头】/【玩耍】/【抱抱】- 与宠物互动"""
    # 提取触发的命令名作为互动动作
    raw_msg = event.get_plaintext().strip()
    action_map = {"摸摸": "摸了摸", "摸头": "摸了摸头", "玩耍": "和它玩耍了一会", "抱抱": "抱了抱"}
    action = "摸了摸"
    for key, val in action_map.items():
        if raw_msg.startswith(key):
            action = val
            break

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await interact_cmd.finish("请先创建角色")

        success, msg = await pet_service.interact(uow, player.id, action)
        await interact_cmd.finish(msg)


# ==================== 对话 ====================
chat_cmd = on_command("对话", aliases={"和宠物说", "跟宠物说"}, priority=5, block=True)

@chat_cmd.handle()
async def handle_chat(event: MessageEvent, args: Message = CommandArg()):
    """【对话 内容】- 与宠物AI对话"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await chat_cmd.finish("用法: 对话 <你想说的话>\n例如: 对话 你今天心情怎么样？")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await chat_cmd.finish("请先创建角色")

        success, msg = await dialogue_service.chat(uow, player.id, args_text)
        await chat_cmd.finish(msg)


# ==================== 化形 ====================
transform_cmd = on_command("化形", priority=5, block=True)

@transform_cmd.handle()
async def handle_transform(event: MessageEvent):
    """【化形】- 让当前伴侣化形为人形"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await transform_cmd.finish("请先创建角色")

        success, msg = await pet_service.transform(uow, player.id)
        await transform_cmd.finish(msg)


# ==================== 饰品 ====================
equip_acc_cmd = on_command("宠物装扮", aliases={"给宠物穿", "宠物饰品"}, priority=5, block=True)

@equip_acc_cmd.handle()
async def handle_equip_accessory(event: MessageEvent, args: Message = CommandArg()):
    """【宠物装扮 饰品名】- 给宠物装备饰品"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await equip_acc_cmd.finish("用法: 宠物装扮 <饰品名>\n例如: 宠物装扮 红色蝴蝶结")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await equip_acc_cmd.finish("请先创建角色")

        success, msg = await pet_service.equip_accessory(uow, player.id, args_text)
        await equip_acc_cmd.finish(msg)


# ==================== 派遣守田 ====================
guard_cmd = on_command("派遣守田", aliases={"守田"}, priority=5, block=True)

@guard_cmd.handle()
async def handle_guard(event: MessageEvent):
    """【派遣守田】- 派遣当前伴侣去灵田守田"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await guard_cmd.finish("请先创建角色")

        success, msg = await pet_service.dispatch_to_guard(uow, player.id)
        await guard_cmd.finish(msg)


# ==================== 召回守田 ====================
recall_cmd = on_command("召回宠物", aliases={"召回守田"}, priority=5, block=True)

@recall_cmd.handle()
async def handle_recall(event: MessageEvent):
    """【召回宠物】- 召回正在守田的宠物"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await recall_cmd.finish("请先创建角色")

        success, msg = await pet_service.recall_from_guard(uow, player.id)
        await recall_cmd.finish(msg)
```

- [ ] **Step 2: 在主 __init__.py 注册 pet 模块**

在 `plugins/xiuxian_game/__init__.py` 的 `from . import (` 块中添加：
```python
pet,  # 宠物伴侣系统
```

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/pet/commands.py plugins/xiuxian_game/__init__.py
git commit -m "feat(pet): 添加宠物命令处理器并注册模块"
```

---

## Task 8: 灵田系统适配（兼容迁移）

**Files:**
- Modify: `plugins/xiuxian_game/spirit_field/steal_service.py`
- Modify: `plugins/xiuxian_game/spirit_field/commands.py`

- [ ] **Step 1: 修改 steal_service.py 的守护兽逻辑**

在 `steal_service.py` 的偷菜拦截逻辑中，现有代码通过 `field.guardian_beast_id` 查找 `GuardianBeastManager` 获取拦截率。由于 `pet_service.dispatch_to_guard` 已经会设置 `field.guardian_beast_id`，所以偷菜拦截的**核心逻辑不需要修改**。

但需要把喂食检查从 `field.guardian_fed_at` 改为查询 `pet_instance.hunger`：

在 `steal_service.py` 中找到饥饿状态检查代码（`hours_since_fed` 相关部分），修改为：
```python
# 检查宠物饱食度（替代旧的guardian_fed_at时间检查）
if field.guardian_beast_id:
    beast = self.beast_manager.get_beast_by_item_id(field.guardian_beast_id)
    if beast:
        intercept_rate = beast.intercept_rate
        beast_name = beast.name
        # 检查宠物饱食度
        from ..models.pet_instance import PetInstance
        pet_stmt = select(PetInstance).where(
            PetInstance.player_id == field.player_id,
            PetInstance.is_guarding == True
        )
        pet_result = await uow.session.execute(pet_stmt)
        guarding_pet = pet_result.scalar_one_or_none()
        if guarding_pet and guarding_pet.hunger < 20:
            intercept_rate = int(intercept_rate * GUARDIAN_HUNGRY_RATE_PENALTY)
```

- [ ] **Step 2: 修改灵田命令，移除旧诡兽命令**

在 `spirit_field/commands.py` 中，将旧的【放置诡兽】【收回诡兽】【喂养诡兽】命令改为引导消息：

```python
# ==================== 旧诡兽命令（引导到宠物系统） ====================

place_guardian_cmd = on_command("放置诡兽", priority=5, block=True)

@place_guardian_cmd.handle()
async def handle_place_guardian_redirect(event: MessageEvent):
    await place_guardian_cmd.finish(
        "诡兽系统已升级为宠物伴侣系统!\n"
        "- 驯化: 【驯化诡兽 名称 昵称】\n"
        "- 守田: 【派遣守田】\n"
        "- 查看: 【宠物】"
    )

remove_guardian_cmd = on_command("收回诡兽", aliases={"撤回诡兽"}, priority=5, block=True)

@remove_guardian_cmd.handle()
async def handle_remove_guardian_redirect(event: MessageEvent):
    await remove_guardian_cmd.finish("诡兽系统已升级! 使用【召回宠物】召回守田中的宠物")

feed_guardian_cmd = on_command("喂养诡兽", aliases={"喂诡兽"}, priority=5, block=True)

@feed_guardian_cmd.handle()
async def handle_feed_guardian_redirect(event: MessageEvent):
    await feed_guardian_cmd.finish("诡兽系统已升级! 使用【喂食】喂养你的宠物伴侣")
```

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/spirit_field/steal_service.py plugins/xiuxian_game/spirit_field/commands.py
git commit -m "refactor(spirit-field): 适配宠物系统，旧诡兽命令引导到新系统"
```

---

## Task 9: 物品配置 + 帮助信息

**Files:**
- Modify: `plugins/xiuxian_game/data/items.yaml`
- Modify: `plugins/xiuxian_game/player/help.py`

- [ ] **Step 1: 在 items.yaml 添加饰品物品定义**

在 `items.yaml` 的末尾（诡兽区域之后）添加：

```yaml
  # ====================================================================
  # 宠物系统 - 饰品
  # ====================================================================
  pet_accessories:
    - item_id: "pet_acc_red_ribbon"
      name: "红色蝴蝶结"
      type: "PET_ACCESSORY"
      rarity: "white"
      price: 500
      description: "宠物头饰，攻击+5"
    - item_id: "pet_acc_ghost_crown"
      name: "幽冥小冠"
      type: "PET_ACCESSORY"
      rarity: "green"
      price: 3000
      description: "宠物头饰，防御+10 生命+50"
    - item_id: "pet_acc_flower_hairpin"
      name: "灵花簪"
      type: "PET_ACCESSORY"
      rarity: "blue"
      price: 10000
      description: "宠物头饰，攻击+15 暴击+1%"
    - item_id: "pet_acc_bell_collar"
      name: "铃铛项圈"
      type: "PET_ACCESSORY"
      rarity: "white"
      price: 500
      description: "宠物颈饰，闪避+0.5%"
    - item_id: "pet_acc_soul_pendant"
      name: "魂玉坠"
      type: "PET_ACCESSORY"
      rarity: "green"
      price: 3000
      description: "宠物颈饰，生命+100 防御+8"
    - item_id: "pet_acc_void_choker"
      name: "虚空锁链"
      type: "PET_ACCESSORY"
      rarity: "purple"
      price: 30000
      description: "宠物颈饰，攻击+20 防御+15"
    - item_id: "pet_acc_maid_outfit"
      name: "女仆装"
      type: "PET_ACCESSORY"
      rarity: "green"
      price: 5000
      description: "宠物服饰，生命+80"
    - item_id: "pet_acc_battle_armor"
      name: "灵甲轻铠"
      type: "PET_ACCESSORY"
      rarity: "blue"
      price: 15000
      description: "宠物服饰，防御+20 生命+150"
    - item_id: "pet_acc_kimono"
      name: "诡纹和服"
      type: "PET_ACCESSORY"
      rarity: "purple"
      price: 30000
      description: "宠物服饰，攻击+15 暴击+1.5%"
```

- [ ] **Step 2: 在 ItemType 枚举中添加 PET_ACCESSORY**

在 `models/inventory.py` 的 `ItemType` 枚举中添加：
```python
PET_ACCESSORY = "PET_ACCESSORY"
```

- [ ] **Step 3: 更新帮助信息**

在 `player/help.py` 中添加宠物系统帮助条目（跟随现有格式）。

- [ ] **Step 4: 提交**

```bash
git add plugins/xiuxian_game/data/items.yaml plugins/xiuxian_game/models/inventory.py plugins/xiuxian_game/player/help.py
git commit -m "feat(pet): 添加宠物饰品物品定义和帮助信息"
```

---

## Task 10: 饥饿度/心情衰减定时任务

**Files:**
- Create: `plugins/xiuxian_game/pet/scheduler.py`
- Modify: `plugins/xiuxian_game/pet/__init__.py`

- [ ] **Step 1: 创建定时衰减任务**

```python
# plugins/xiuxian_game/pet/scheduler.py
"""宠物状态衰减定时任务"""
from nonebot import require, logger
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler
from sqlalchemy import select, update
from ..models.db import AsyncSessionLocal
from ..models.pet_instance import PetInstance
from .config import PetConfigManager


@scheduler.scheduled_job("interval", hours=1, id="pet_status_decay")
async def pet_status_decay():
    """每小时执行一次宠物状态衰减"""
    config = PetConfigManager()
    hunger_decay = config.settings["hunger_decay_per_hour"]
    mood_decay = config.settings["mood_decay_per_hour"]
    hungry_threshold = config.settings["hungry_threshold"]

    async with AsyncSessionLocal() as session:
        # 查询所有宠物
        result = await session.execute(select(PetInstance))
        pets = result.scalars().all()

        updated = 0
        for pet in pets:
            pet.hunger = max(0, pet.hunger - hunger_decay)
            # 饥饿时心情加速下降
            actual_mood_decay = mood_decay * 3 if pet.hunger < hungry_threshold else mood_decay
            pet.mood = max(0, pet.mood - actual_mood_decay)
            updated += 1

        await session.commit()
        logger.info(f"[PetScheduler] 状态衰减完成，更新{updated}只宠物")
```

- [ ] **Step 2: 在 pet/__init__.py 中导入 scheduler**

```python
from . import commands
from . import scheduler
```

- [ ] **Step 3: 提交**

```bash
git add plugins/xiuxian_game/pet/scheduler.py plugins/xiuxian_game/pet/__init__.py
git commit -m "feat(pet): 添加宠物饥饿/心情定时衰减任务"
```

---

## Task 11: 知识库YAML同步

**Files:**
- Create: `plugins/xiuxian_game/data/knowledge/pet_system_help.yaml`

- [ ] **Step 1: 创建知识库YAML**

按照项目规则，帮助信息需要同步到 AI 知识库 YAML。创建 `pet_system_help.yaml`，将 `help.py` 中宠物系统的帮助文本复制为 `body` 字段。

- [ ] **Step 2: 提交**

```bash
git add plugins/xiuxian_game/data/knowledge/pet_system_help.yaml
git commit -m "docs(pet): 添加宠物系统AI知识库YAML"
```

---

## 命令速查表

| 命令 | 别名 | 说明 |
|------|------|------|
| 驯化诡兽 名称 昵称 | 驯化 | 将背包诡兽转化为宠物 |
| 宠物 | 我的宠物/诡兽伴侣 | 查看当前伴侣状态 |
| 诡兽巢穴 | 宠物列表 | 查看所有宠物 |
| 切换伴侣 ID | 切换宠物 | 切换当前伴侣 |
| 喂食 | 喂宠物 | 怨念喂食 |
| 喂食 菜肴名 | | 菜肴喂食 |
| 摸摸/摸头/玩耍/抱抱 | | 互动增加好感 |
| 对话 内容 | 和宠物说/跟宠物说 | AI对话 |
| 化形 | | 化为人形 |
| 宠物装扮 饰品名 | 给宠物穿/宠物饰品 | 装备饰品 |
| 派遣守田 | 守田 | 派宠物守灵田 |
| 召回宠物 | 召回守田 | 召回守田宠物 |
