# 个人摊位（摆摊）系统 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 添加玩家自由定价的直购交易渠道（个人摊位），补充现有挂牌市场（系统定价）和拍卖行（竞价模式）的不足。同时在挂牌市场中禁止GOODS类型物品交易。

**Architecture:** 新建 `plugins/xiuxian_game/stall/` 模块，包含 ORM 模型、Repository、Service、Commands、Scheduler 五层。遵循现有拍卖行模块的架构模式（UnitOfWork + Repository + DI），复用现有的物品冻结、背包操作、月卡查询、城镇判断等基础设施。

**Tech Stack:** SQLAlchemy 2.0 ORM, NoneBot2 命令框架, nonebot_plugin_apscheduler 定时任务

---

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `plugins/xiuxian_game/models/stall.py` | ORM 模型：PlayerStall + StallItem |
| 新建 | `plugins/xiuxian_game/infrastructure/repositories/stall_repository.py` | Repository：摊位和商品的数据查询 |
| 修改 | `plugins/xiuxian_game/infrastructure/uow/unit_of_work.py` | 注册 stall_items / player_stalls 属性 |
| 新建 | `plugins/xiuxian_game/stall/__init__.py` | 模块注册 |
| 新建 | `plugins/xiuxian_game/stall/stall_service.py` | 核心业务逻辑 |
| 新建 | `plugins/xiuxian_game/stall/stall_commands.py` | NoneBot2 命令处理器 |
| 新建 | `plugins/xiuxian_game/stall/stall_scheduler.py` | 到期摊位自动收摊定时任务 |
| 修改 | `plugins/xiuxian_game/__init__.py` | 注册 stall 模块 |
| 修改 | `plugins/xiuxian_game/data/items.yaml` | 添加"摊位令"消耗品 |
| 修改 | `plugins/xiuxian_game/economy/market.py` | 挂牌市场禁止GOODS类型 |
| 修改 | `plugins/xiuxian_game/player/help.py` | 添加摊位系统帮助 + 经济市场菜单加入摊位入口 |
| 新建 | `plugins/xiuxian_game/data/knowledge/stall_system_help.yaml` | AI知识库 |

---

## 核心设计常量

```python
# stall_service.py 顶部常量
MAX_STALL_SLOTS = 5              # 基础摊位格数
BASIC_CARD_BONUS_SLOTS = 2       # 基础月卡额外格数
PREMIUM_CARD_BONUS_SLOTS = 5     # 高级月卡额外格数
STALL_DURATION_HOURS = 24        # 摊位令持续时间（小时）
STALL_TAX_RATE = 0.03            # 基础税率 3%
PREMIUM_TAX_THRESHOLD_5X = 5     # 溢价5倍阈值
PREMIUM_TAX_RATE_5X = 0.15       # 超5倍附加税率 15%
PREMIUM_TAX_THRESHOLD_20X = 20   # 溢价20倍阈值
PREMIUM_TAX_RATE_20X = 0.30      # 超20倍附加税率 30%
STALL_NAME_MAX_LEN = 16          # 摊位名最大长度
SHOUT_MAX_LEN = 32               # 吆喝语最大长度
```

## 税率计算公式

```
系统估价 = item_cfg.price（普通物品） 或 equipment_value_lower_bound（装备）

基础税 = 成交额 × 3%

若 单价 > 系统估价 × 20:
    附加税 = (单价 - 估价×20) × 数量 × 30%
           + (估价×20 - 估价×5) × 数量 × 15%
elif 单价 > 系统估价 × 5:
    附加税 = (单价 - 估价×5) × 数量 × 15%
else:
    附加税 = 0

总税 = 基础税 + 附加税
卖家到手 = 成交额 - 总税
```

---

## Task 1: ORM 模型

**Files:**
- Create: `plugins/xiuxian_game/models/stall.py`

- [ ] **Step 1: 创建 PlayerStall 和 StallItem 模型**

```python
"""
个人摊位数据模型

PlayerStall: 玩家的摊位信息（1个玩家同时只能有1个摊位）
StallItem: 摊位上的商品条目
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from .db import Base


class PlayerStall(Base):
    """玩家摊位

    每个玩家同时只能开设一个摊位，消耗摊位令开摊，持续24小时。
    """

    __tablename__ = "player_stall"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # ==================== 摊主信息 ====================
    player_id: Mapped[str] = mapped_column(
        String(32), index=True, comment="摊主平台ID（player.id）"
    )
    player_uid: Mapped[int] = mapped_column(
        Integer, comment="摊主游戏UID"
    )
    player_name: Mapped[str] = mapped_column(
        String(64), comment="摊主昵称快照"
    )

    # ==================== 摊位信息 ====================
    city_name: Mapped[str] = mapped_column(
        String(32), comment="所在城镇名称"
    )
    stall_name: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="摊位名称（玩家自定义）"
    )
    shout_text: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, comment="吆喝语"
    )

    # ==================== 时间信息 ====================
    opened_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(),
        comment="开摊时间"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, comment="到期时间"
    )

    # ==================== 状态 ====================
    status: Mapped[str] = mapped_column(
        String(16), default="active", server_default="active",
        index=True,
        comment="状态: active(营业中) / closed(已收摊) / expired(已过期)"
    )

    @property
    def is_active(self) -> bool:
        return self.status == "active"


class StallItem(Base):
    """摊位商品条目

    摊位上架的单个商品，支持普通物品和装备实例。
    """

    __tablename__ = "stall_item"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # ==================== 关联信息 ====================
    stall_id: Mapped[int] = mapped_column(
        Integer, index=True, comment="所属摊位ID"
    )
    seller_id: Mapped[str] = mapped_column(
        String(32), index=True, comment="摊主player_id（冗余，方便查询）"
    )

    # ==================== 物品信息 ====================
    item_id: Mapped[str] = mapped_column(
        String(64), comment="物品模板ID（items.yaml）"
    )
    quantity: Mapped[int] = mapped_column(
        Integer, default=1, comment="数量（装备固定为1）"
    )
    unit_price: Mapped[int] = mapped_column(
        BigInteger, comment="单价（金币）- 玩家自由定价"
    )
    is_instance_trade: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0",
        comment="是否为装备/铭文实例交易"
    )
    item_instance_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="装备实例ID（仅装备交易时有效）"
    )
    equipment_summary: Mapped[Optional[str]] = mapped_column(
        String(300), nullable=True, comment="装备摘要文本"
    )

    # ==================== 时间 ====================
    listed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, server_default=func.now(),
        comment="上架时间"
    )
```

- [ ] **Step 2: 确认模型能被 SQLAlchemy 自动建表**

模型继承自 `Base`（定义在 `models/db.py`），SQLAlchemy 在 `init_db()` 时通过 `Base.metadata.create_all()` 自动创建新表。只需确保模型文件被导入即可。

在 `plugins/xiuxian_game/models/__init__.py` 中检查是否有统一导入模式。如果有，在其中添加：
```python
from .stall import PlayerStall, StallItem
```

如果 `__init__.py` 无统一导入，则在 stall 模块的 `__init__.py` 中导入模型即可触发注册。

---

## Task 2: Repository

**Files:**
- Create: `plugins/xiuxian_game/infrastructure/repositories/stall_repository.py`
- Modify: `plugins/xiuxian_game/infrastructure/uow/unit_of_work.py`

- [ ] **Step 1: 创建 StallRepository**

```python
"""摊位系统 Repository"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.stall import PlayerStall, StallItem


class PlayerStallRepository:
    """玩家摊位仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, stall_id: int) -> Optional[PlayerStall]:
        return await self._session.get(PlayerStall, stall_id)

    async def get_active_by_player(self, player_id: str) -> Optional[PlayerStall]:
        """获取玩家当前活跃摊位"""
        stmt = select(PlayerStall).where(
            PlayerStall.player_id == player_id,
            PlayerStall.status == "active",
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def find_active_by_city(self, city_name: str, page: int = 1, page_size: int = 8) -> List[PlayerStall]:
        """查询某城镇的活跃摊位（分页）"""
        stmt = (
            select(PlayerStall)
            .where(PlayerStall.status == "active", PlayerStall.city_name == city_name)
            .order_by(PlayerStall.opened_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def count_active_by_city(self, city_name: str) -> int:
        stmt = select(func.count()).select_from(PlayerStall).where(
            PlayerStall.status == "active", PlayerStall.city_name == city_name
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def find_all_active(self, page: int = 1, page_size: int = 8) -> List[PlayerStall]:
        """查询所有活跃摊位（分页）"""
        stmt = (
            select(PlayerStall)
            .where(PlayerStall.status == "active")
            .order_by(PlayerStall.opened_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def count_all_active(self) -> int:
        stmt = select(func.count()).select_from(PlayerStall).where(
            PlayerStall.status == "active"
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def find_expired_active(self) -> List[PlayerStall]:
        """查找已过期但仍为active状态的摊位"""
        from datetime import datetime
        stmt = select(PlayerStall).where(
            PlayerStall.status == "active",
            PlayerStall.expires_at <= datetime.now(),
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def add(self, entity: PlayerStall) -> PlayerStall:
        self._session.add(entity)
        await self._session.flush()
        return entity


class StallItemRepository:
    """摊位商品仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, item_id: int) -> Optional[StallItem]:
        return await self._session.get(StallItem, item_id)

    async def find_by_stall(self, stall_id: int) -> List[StallItem]:
        """获取摊位上所有商品"""
        stmt = select(StallItem).where(
            StallItem.stall_id == stall_id
        ).order_by(StallItem.listed_at.asc())
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def count_by_stall(self, stall_id: int) -> int:
        stmt = select(func.count()).select_from(StallItem).where(
            StallItem.stall_id == stall_id
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def search_by_item_name(self, item_id: str, page: int = 1, page_size: int = 10) -> List[StallItem]:
        """跨摊位搜索特定物品（按单价升序），仅搜索active摊位"""
        stmt = (
            select(StallItem)
            .join(PlayerStall, StallItem.stall_id == PlayerStall.id)
            .where(
                StallItem.item_id == item_id,
                PlayerStall.status == "active",
            )
            .order_by(StallItem.unit_price.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def count_by_item_name(self, item_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(StallItem)
            .join(PlayerStall, StallItem.stall_id == PlayerStall.id)
            .where(
                StallItem.item_id == item_id,
                PlayerStall.status == "active",
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def add(self, entity: StallItem) -> StallItem:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: StallItem):
        await self._session.delete(entity)
        await self._session.flush()

    async def delete_all_by_stall(self, stall_id: int) -> List[StallItem]:
        """删除摊位所有商品并返回（用于退回物品）"""
        items = await self.find_by_stall(stall_id)
        for item in items:
            await self._session.delete(item)
        await self._session.flush()
        return items
```

- [ ] **Step 2: 在 UnitOfWork 中注册 Repository**

在 `plugins/xiuxian_game/infrastructure/uow/unit_of_work.py` 中：

1. 在 `__init__` 方法的属性初始化区域（拍卖行系统仓储后面）添加：
```python
        # 摊位系统仓储
        self._player_stalls = None
        self._stall_items = None
```

2. 添加属性方法（在 `auction_bid_histories` 属性后面）：
```python
    @property
    def player_stalls(self):
        """摊位仓储"""
        if self._player_stalls is None:
            from ..repositories.stall_repository import PlayerStallRepository
            self._player_stalls = PlayerStallRepository(self._session)
        return self._player_stalls

    @property
    def stall_items(self):
        """摊位商品仓储"""
        if self._stall_items is None:
            from ..repositories.stall_repository import StallItemRepository
            self._stall_items = StallItemRepository(self._session)
        return self._stall_items
```

---

## Task 3: 摊位令道具

**Files:**
- Modify: `plugins/xiuxian_game/data/items.yaml`

- [ ] **Step 1: 在 items.yaml 的 consumables 区域末尾添加摊位令**

```yaml
    - item_id: "stall_permit"
      name: "摊位令"
      description: "允许在城镇开设个人摊位24小时。使用方法：前往城镇后发送【摆摊】"
      type: "CONSUMABLE"
      effect_type: "SPECIAL"
      price: 5000
      rarity: "green"
      no_drop: true
```

> **注意**: `no_drop: true` 标记使其不会从月卡宝箱等随机来源掉落。摊位令来源：打工掉落、NPC商店购买、签到奖励。
> 
> 打工掉落需在打工系统的掉落表中添加（后续可单独做），首期可先通过NPC商店和手动发放。

---

## Task 4: Service 核心业务逻辑

**Files:**
- Create: `plugins/xiuxian_game/stall/stall_service.py`

- [ ] **Step 1: 创建 stall_service.py**

这是最核心的文件。包含以下函数：

1. `get_town_name(x, y, region)` — 获取最近的城镇名
2. `get_max_stall_slots(session, player_id)` — 计算玩家最大摊位格数
3. `calculate_stall_tax(unit_price, quantity, system_estimate)` — 计算摊位税
4. `open_stall(uow, player)` — 开摊（消耗摊位令）
5. `close_stall(uow, player)` — 收摊（退回物品）
6. `list_item(uow, player, item_name, price, quantity, equipment_instance_id)` — 上架物品
7. `unlist_item(uow, player, slot_index)` — 下架物品
8. `buy_item(uow, buyer, seller_uid, slot_index, quantity)` — 购买物品
9. `set_stall_name(uow, player, name)` — 设置摊位名
10. `set_shout(uow, player, text)` — 设置吆喝语
11. `expire_stalls(uow)` — 批量过期处理（定时任务调用）

**关键实现细节：**

- **开摊**: 检查城镇 → 检查无活跃摊位 → 消耗摊位令 → 创建PlayerStall
- **上架**: 检查摊位存在 → 检查格数 → 禁止GOODS → 普通物品消耗/装备冻结 → 创建StallItem
- **购买**: 查找摊位 → 查找商品 → 检查金币 → 扣金币 → 转移物品 → 计算税 → 卖家到账 → 记录TradeRecord → 删除StallItem
- **收摊/过期**: 遍历StallItem → 退回普通物品(add_item)/解冻装备 → 标记stall状态

完整代码详见 Task 4 实现（此处不展开全部代码，以避免计划过长，实现时按上述函数签名逐一实现）。

---

## Task 5: 命令处理器

**Files:**
- Create: `plugins/xiuxian_game/stall/stall_commands.py`

- [ ] **Step 1: 创建命令定义和摆摊/收摊命令**

命令列表及优先级（与拍卖行一致，priority=13）：

```python
# 命令定义
open_stall_cmd = on_command("摆摊", aliases={"开摊"}, block=True, priority=13)
close_stall_cmd = on_command("收摊", aliases={"关摊"}, block=True, priority=13)
list_item_cmd = on_command("上摊", aliases={"摊位上架"}, block=True, priority=13)
unlist_item_cmd = on_command("下摊", aliases={"摊位下架"}, block=True, priority=13)
my_stall_cmd = on_command("我的摊位", block=True, priority=13)
set_name_cmd = on_command("摊位名", aliases={"摊位改名"}, block=True, priority=13)
set_shout_cmd = on_command("吆喝", block=True, priority=13)
browse_cmd = on_command("逛摊", aliases={"逛街"}, block=True, priority=13)
search_cmd = on_command("搜摊", aliases={"搜索摊位"}, block=True, priority=13)
buy_cmd = on_command("买摊", aliases={"摊位购买"}, block=True, priority=13)
view_stall_cmd = on_command("摊位", block=True, priority=13, force_whitespace=True)
```

**命令格式**:
- `摆摊` — 无参数，在当前城镇开摊
- `收摊` — 无参数
- `上摊 物品名 单价 [数量]` — 默认数量1
- `下摊 序号` — 按我的摊位中的序号
- `我的摊位` — 查看自己的摊位状态和商品
- `摊位名 XXX` — 设置名称
- `吆喝 一句话` — 设置吆喝语
- `逛摊 [城镇名]` — 不带参数=当前城镇，带参数=指定城镇
- `搜摊 物品名` — 全服搜索
- `买摊 摊主UID 序号 [数量]` — 购买
- `摊位 UID` — 查看某人摊位

**装备选择流程**: 复用拍卖行的选择模式 — 如果背包有多件同名装备，展示选择列表，玩家回复序号后完成上架。用 `_stall_equipment_selection_state` 字典 + on_message handler。

- [ ] **Step 2: 逐一实现所有命令 handler**

每个 handler 遵循统一模式：
```python
@xxx_cmd.handle()
async def handle_xxx(event: MessageEvent, args: Message = CommandArg()):
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await xxx_cmd.finish(message_add_head("⛔ 请先创建角色", event))
        
        success, msg = await stall_service.xxx(uow, player, ...)
        if success:
            await uow.commit()
        
    await xxx_cmd.finish(message_add_head(msg, event))
    # 或 build_markdown(msg) 对于列表展示
```

---

## Task 6: 定时任务

**Files:**
- Create: `plugins/xiuxian_game/stall/stall_scheduler.py`

- [ ] **Step 1: 创建定时任务（每5分钟检查过期摊位）**

```python
"""
摊位系统定时任务

任务：每5分钟检查过期摊位并自动收摊
"""

from nonebot import get_driver, logger
from nonebot_plugin_apscheduler import scheduler

from ..models.db import AsyncSessionLocal
from ..infrastructure.uow.unit_of_work import UnitOfWork

driver = get_driver()


@scheduler.scheduled_job(
    "interval",
    minutes=5,
    id="stall_expiry_check",
    max_instances=1,
    coalesce=True,
)
async def stall_expiry_check():
    """每5分钟检查并收摊过期摊位"""
    from . import stall_service

    try:
        async with UnitOfWork(AsyncSessionLocal) as uow:
            count = await stall_service.expire_stalls(uow)
            await uow.commit()

        if count > 0:
            logger.info(f"[摊位] 自动收摊 {count} 个过期摊位")

    except Exception as e:
        logger.error(f"[摊位] 定时任务失败: {e}", exc_info=True)


@driver.on_startup
async def on_startup():
    logger.info("🏪 摊位定时任务已注册")
    logger.info("  - 每5分钟：检查过期摊位并自动收摊")
```

---

## Task 7: 模块注册

**Files:**
- Create: `plugins/xiuxian_game/stall/__init__.py`
- Modify: `plugins/xiuxian_game/__init__.py`

- [ ] **Step 1: 创建 stall/__init__.py**

```python
"""
个人摊位系统模块

功能：
- 玩家自由定价的直购交易渠道
- 消耗摊位令在城镇开摊，持续24小时
- 支持装备实例和普通物品
- 超高溢价累进税防止洗金
"""

from . import stall_commands    # 注册命令处理器
from . import stall_scheduler   # 注册定时任务

__all__ = ["stall_commands", "stall_scheduler"]
```

- [ ] **Step 2: 在 __init__.py 中注册模块**

在 `plugins/xiuxian_game/__init__.py` 的 import 区域中，在 `auction` 之后添加：
```python
    stall,  # 个人摊位系统（玩家自由定价直购交易）
```

---

## Task 8: 挂牌市场禁止GOODS

**Files:**
- Modify: `plugins/xiuxian_game/economy/market.py`

- [ ] **Step 1: 在挂牌处理逻辑中添加GOODS检查**

在 `market.py` 的挂牌命令处理函数中，在物品配置查找成功后、资源冻结之前，添加：

```python
    # 禁止挂牌跑商商品
    if item_cfg.type == ItemType.GOODS:
        await list_cmd.finish("⛔ 跑商商品不能在市场挂牌，请前往市集交易")
```

具体位置：在 `cap_hint` 计算之后、`# 资源冻结` 注释之前。

---

## Task 9: 帮助系统更新

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py`
- Create: `plugins/xiuxian_game/data/knowledge/stall_system_help.yaml`

- [ ] **Step 1: 在 help.py 中添加摊位系统帮助命令**

在 help.py 中添加新的帮助模块（在拍卖行帮助附近）：

```python
# 摊位系统
stall_help_cmd = on_command("摊位系统", aliases={"摊位帮助", "摆摊帮助"}, block=True, priority=4)

@stall_help_cmd.handle()
async def handle_stall_help(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 个人摊位系统\n"
        "自由定价，即买即走，你的地盘你做主\n"
        "***\n"
        "**🏪 开摊/收摊**\n"
        f"{cmd('摆摊')} 在当前城镇开摊（消耗摊位令，持续24h）\n"
        f"{cmd('收摊')} 手动收摊，未售物品退回背包\n"
        f"{cmd('我的摊位')} 查看摊位状态和商品\n"
        "***\n"
        "**📦 上架/下架**\n"
        f"{cmd('上摊 物品名 单价 数量', '上摊 ')} 上架物品（自由定价）\n"
        f"{cmd('下摊 序号', '下摊 ')} 下架商品\n"
        "***\n"
        "**🛍️ 逛摊/购买**\n"
        f"{cmd('逛摊')} 浏览当前城镇摊位\n"
        f"{cmd('逛摊 城镇名', '逛摊 ')} 浏览指定城镇\n"
        f"{cmd('搜摊 物品名', '搜摊 ')} 全服搜索物品（按价格排序）\n"
        f"{cmd('摊位 UID', '摊位 ')} 查看某人摊位\n"
        f"{cmd('买摊 摊主UID 序号 数量', '买摊 ')} 购买\n"
        "***\n"
        "**✏️ 摊位装饰**\n"
        f"{cmd('摊位名 名字', '摊位名 ')} 自定义摊位名（最多16字）\n"
        f"{cmd('吆喝 一句话', '吆喝 ')} 设置吆喝语（最多32字）\n"
        "***\n"
        "**💰 税率说明**\n"
        "基础税率：成交额×3%\n"
        "溢价附加税：超系统估价5倍+15%，超20倍+30%\n"
        "***\n"
        "**📋 规则**\n"
        "• 必须在城镇安全区开摊\n"
        "• 消耗1张摊位令，持续24小时\n"
        f"• 基础5格 | 基础月卡+2格 | 高级月卡+5格\n"
        "• 跑商商品不可上摊\n"
        "• 到期自动收摊，物品退回背包\n"
        "***\n"
        f"> {cmd('经济市场')} 更多交易方式 | {cmd('帮助', '帮助')} 返回"
    )
    await stall_help_cmd.finish(build_markdown(content))
```

- [ ] **Step 2: 在经济市场帮助菜单中添加摊位入口**

在 `handle_economy_module` 函数的内容中，在"拍卖行"区域后面添加：

```python
        "**🏪 个人摊位(自由定价)**\n"
        f"{cmd('摆摊')} 在城镇开摊 | {cmd('逛摊')} 浏览 | {cmd('搜摊 物品名', '搜摊 ')} 全服搜索\n"
        "***\n"
```

在底部导航中添加 `{cmd('摊位系统')}`。

- [ ] **Step 3: 创建知识库 YAML**

```yaml
id: "stall_system_help"
title: "个人摊位系统"
keywords:
  - 摊位系统
  - 摊位帮助
  - 摆摊
  - 收摊
  - 上摊
  - 下摊
  - 逛摊
  - 搜摊
  - 买摊
  - 摊位令
  - 自由定价
  - 个人交易
body: |
  🏪 个人摊位系统帮助 🏪
  自由定价、即买即走的玩家交易渠道
  ━━━━━━━━━━━━━
  📋 基本命令：
  【摆摊】 在当前城镇开摊（消耗1张摊位令，持续24小时）
  【收摊】 手动收摊，未售物品退回背包
  【上摊 物品名 单价 [数量]】 上架物品（完全自由定价）
  【下摊 序号】 下架指定商品
  【我的摊位】 查看摊位状态和商品列表
  【摊位名 名称】 自定义摊位名（最多16字）
  【吆喝 内容】 设置吆喝语（最多32字）
  ━━━━━━━━━━━━━
  🛍️ 逛摊和购买：
  【逛摊】 浏览当前城镇所有摊位
  【逛摊 城镇名】 浏览指定城镇的摊位
  【搜摊 物品名】 全服搜索物品（按价格升序）
  【摊位 UID】 查看指定玩家的摊位
  【买摊 摊主UID 序号 [数量]】 直接购买
  ━━━━━━━━━━━━━
  💰 税率说明：
  基础税率：成交额的3%（固定）
  溢价附加税（防洗金）：
  • 单价超过系统估价5倍的部分：额外15%
  • 单价超过系统估价20倍的部分：额外30%
  ━━━━━━━━━━━━━
  📋 摊位规则：
  • 必须在城镇安全区才能开摊
  • 每次开摊消耗1张摊位令
  • 摊位持续24小时，到期自动收摊
  • 基础5格位，基础月卡+2格，高级月卡+5格
  • 跑商商品不可上摊
  • 装备以实例交易（含升阶、宝石、词缀）
  ━━━━━━━━━━━━━
  🎮 快速上手：
  1️⃣ 获得摊位令（商店购买/打工掉落）
  2️⃣ 前往城镇，发送【摆摊】
  3️⃣ 【上摊 物品名 价格】上架
  4️⃣ 等待买家购买，自动到账
  ━━━━━━━━━━━━━
  💡 与其他交易方式的区别：
  • 挂牌市场：系统定价（底价~8倍限制），自动撮合
  • 拍卖行：竞价模式，需等待出价
  • 个人摊位：完全自由定价，即买即走
  ━━━━━━━━━━━━━
  💡 发送【经济市场】查看所有交易方式
```

---

## Task 10: 实现 stall_service.py 完整代码

**Files:**
- Create: `plugins/xiuxian_game/stall/stall_service.py`

- [ ] **Step 1: 实现工具函数（城镇检测、税率计算、格数计算）**

```python
"""
个人摊位核心服务

功能：
1. 开摊     - 消耗摊位令，在城镇开设摊位
2. 收摊     - 手动/自动关闭摊位，退回所有物品
3. 上架     - 上架物品到摊位（自由定价）
4. 下架     - 从摊位移除物品
5. 购买     - 其他玩家直接购买摊位商品
6. 搜索     - 跨城镇搜索摊位商品
7. 过期处理 - 定时任务自动收摊过期摊位
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Tuple

from nonebot import logger

from ..config import config
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.inventory import ItemInstance, ItemType
from ..models.player import Player
from ..models.stall import PlayerStall, StallItem

# ==================== 常量 ====================

MAX_STALL_SLOTS = 5
BASIC_CARD_BONUS_SLOTS = 2
PREMIUM_CARD_BONUS_SLOTS = 5
STALL_DURATION_HOURS = 24
STALL_TAX_RATE = 0.03
PREMIUM_TAX_THRESHOLD_5X = 5
PREMIUM_TAX_RATE_5X = 0.15
PREMIUM_TAX_THRESHOLD_20X = 20
PREMIUM_TAX_RATE_20X = 0.30
STALL_NAME_MAX_LEN = 16
SHOUT_MAX_LEN = 32
STALL_PERMIT_ITEM_ID = "stall_permit"


def get_town_name(x: int, y: int, region: str = "大都会") -> Optional[str]:
    """获取玩家所在城镇名称，不在城镇则返回None"""
    if region != "大都会":
        return None

    from ..economy.merchants import MARKETS, HEADQUARTERS_COORD

    # 市集
    for market in MARKETS:
        distance = abs(x - market.x) + abs(y - market.y)
        if distance <= 5:
            return market.name

    # 缉邪司总部
    hq_distance = abs(x - HEADQUARTERS_COORD[0]) + abs(y - HEADQUARTERS_COORD[1])
    if hq_distance <= 5:
        return "风雪镇"

    # 打工地点
    try:
        from ..economy.part_time_job_service import PartTimeJobService
        for loc_name, loc_data in PartTimeJobService.JOB_LOCATIONS.items():
            distance = abs(x - loc_data['x']) + abs(y - loc_data['y'])
            if distance <= 5:
                return loc_name
    except ImportError:
        pass

    return None


async def get_max_stall_slots(session, player_id: str) -> int:
    """计算玩家最大摊位格数"""
    from ..models.monthly_card import get_player_card_benefits
    benefits = await get_player_card_benefits(session, player_id)

    slots = MAX_STALL_SLOTS
    if benefits["premium_active"]:
        slots += PREMIUM_CARD_BONUS_SLOTS
    elif benefits["basic_active"]:
        slots += BASIC_CARD_BONUS_SLOTS
    return slots


def calculate_stall_tax(unit_price: int, quantity: int, system_estimate: int) -> int:
    """计算摊位交易税

    基础税 = 成交额 × 3%
    超估价5倍部分 +15%
    超估价20倍部分 +30%
    """
    total = unit_price * quantity
    base_tax = int(total * STALL_TAX_RATE)

    surcharge = 0
    if system_estimate > 0:
        threshold_5x = system_estimate * PREMIUM_TAX_THRESHOLD_5X
        threshold_20x = system_estimate * PREMIUM_TAX_THRESHOLD_20X

        if unit_price > threshold_20x:
            surcharge += int((unit_price - threshold_20x) * quantity * PREMIUM_TAX_RATE_20X)
            surcharge += int((threshold_20x - threshold_5x) * quantity * PREMIUM_TAX_RATE_5X)
        elif unit_price > threshold_5x:
            surcharge += int((unit_price - threshold_5x) * quantity * PREMIUM_TAX_RATE_5X)

    return base_tax + surcharge
```

- [ ] **Step 2: 实现开摊/收摊**

```python
async def open_stall(uow: UnitOfWork, player: Player) -> Tuple[bool, str]:
    """开摊"""
    session = uow.session

    # 1. 检查是否在城镇
    region = player.get_current_region() if hasattr(player, 'get_current_region') else "大都会"
    town = get_town_name(player.x, player.y, region)
    if not town:
        return False, "⛔ 只能在城镇安全区摆摊\n💡 请先导航到一个城镇"

    # 2. 检查是否已有活跃摊位
    existing = await uow.player_stalls.get_active_by_player(player.id)
    if existing:
        return False, f"⛔ 你已在「{existing.city_name}」有一个摊位\n💡 先【收摊】再重新开"

    # 3. 消耗摊位令
    try:
        await ItemInstance.consume_item(session, player.id, STALL_PERMIT_ITEM_ID, 1)
    except ValueError:
        return False, "⛔ 你没有摊位令\n💡 可通过打工掉落或NPC商店获取"

    # 4. 创建摊位
    now = datetime.now()
    stall = PlayerStall(
        player_id=player.id,
        player_uid=player.uid,
        player_name=player.nickname,
        city_name=town,
        opened_at=now,
        expires_at=now + timedelta(hours=STALL_DURATION_HOURS),
        status="active",
    )
    await uow.player_stalls.add(stall)

    max_slots = await get_max_stall_slots(session, player.id)
    expire_str = stall.expires_at.strftime("%m-%d %H:%M")
    return True, (
        f"✅ 摊位已在「{town}」开张！\n"
        f"📦 可上架 {max_slots} 件商品\n"
        f"⏰ 有效期至 {expire_str}\n"
        f"💡 使用【上摊 物品名 单价 数量】上架商品"
    )


async def close_stall(uow: UnitOfWork, player: Player) -> Tuple[bool, str]:
    """收摊"""
    session = uow.session

    stall = await uow.player_stalls.get_active_by_player(player.id)
    if not stall:
        return False, "⛔ 你当前没有摊位"

    # 退回所有商品
    returned = await _return_all_stall_items(uow, stall)

    stall.status = "closed"
    session.add(stall)
    await session.flush()

    return True, f"✅ 已收摊，退回 {returned} 件商品到背包"


async def _return_all_stall_items(uow: UnitOfWork, stall: PlayerStall) -> int:
    """退回摊位上所有商品给摊主"""
    session = uow.session
    items = await uow.stall_items.delete_all_by_stall(stall.id)
    count = 0
    for si in items:
        if si.is_instance_trade and si.item_instance_id:
            # 装备：解冻
            equipment = await session.get(ItemInstance, si.item_instance_id)
            if equipment:
                extra = equipment.extra_attrs or {}
                extra.pop("_frozen_for_stall", None)
                equipment.extra_attrs = extra
                session.add(equipment)
        else:
            # 普通物品：退回背包
            try:
                await ItemInstance.add_item(session, stall.player_id, si.item_id, si.quantity)
            except ValueError as e:
                logger.error(f"[摊位] 退回物品失败: {e}")
        count += 1
    return count
```

- [ ] **Step 3: 实现上架/下架**

```python
async def list_item(
    uow: UnitOfWork,
    player: Player,
    item_name: str,
    unit_price: int,
    quantity: int = 1,
    equipment_instance_id: Optional[int] = None,
) -> Tuple[bool, str]:
    """上架物品到摊位"""
    session = uow.session

    # 1. 检查摊位
    stall = await uow.player_stalls.get_active_by_player(player.id)
    if not stall:
        return False, "⛔ 你当前没有摊位\n💡 请先【摆摊】"

    # 2. 检查过期
    if datetime.now() >= stall.expires_at:
        return False, "⛔ 摊位已过期，请重新开摊"

    # 3. 检查格数
    current_count = await uow.stall_items.count_by_stall(stall.id)
    max_slots = await get_max_stall_slots(session, player.id)
    if current_count >= max_slots:
        return False, f"⛔ 摊位已满（{current_count}/{max_slots}）\n💡 先【下摊】腾出位置"

    # 4. 查找物品配置
    item_cfg = config.items_config["by_name"].get(item_name)
    if not item_cfg:
        return False, f"⛔ 未找到物品「{item_name}」"

    # 5. 禁止GOODS
    if item_cfg.type == ItemType.GOODS:
        return False, "⛔ 跑商商品不能上摊"

    # 6. 价格校验
    if unit_price < 1:
        return False, "⛔ 单价至少1金币"

    # 7. 根据物品类型处理
    if item_cfg.type in (ItemType.EQUIPMENT, ItemType.INSCRIPTION):
        return await _list_equipment_item(uow, stall, player, item_cfg, unit_price, equipment_instance_id)
    else:
        return await _list_normal_item(uow, stall, player, item_cfg, unit_price, quantity)


async def _list_normal_item(uow, stall, player, item_cfg, unit_price, quantity):
    """上架普通物品"""
    session = uow.session

    # 从背包扣除
    try:
        await ItemInstance.consume_item(session, player.id, item_cfg.item_id, quantity)
    except ValueError as e:
        return False, f"⛔ 背包物品不足：{e}"

    si = StallItem(
        stall_id=stall.id,
        seller_id=player.id,
        item_id=item_cfg.item_id,
        quantity=quantity,
        unit_price=unit_price,
        is_instance_trade=False,
    )
    await uow.stall_items.add(si)

    item_display = item_cfg.get_display_name()
    return True, (
        f"✅ 已上架到摊位\n"
        f"📦 {item_display} ×{quantity}\n"
        f"💰 单价：{unit_price:,}💰"
    )


async def _list_equipment_item(uow, stall, player, item_cfg, unit_price, equipment_instance_id):
    """上架装备/铭文"""
    session = uow.session
    from sqlalchemy import select
    is_inscription = item_cfg.type == ItemType.INSCRIPTION

    if equipment_instance_id:
        equipment = await session.get(ItemInstance, equipment_instance_id)
        if not equipment or equipment.player_id != player.id:
            return False, "⛔ 物品不存在或不属于你"
        if not is_inscription and equipment.equipped:
            return False, "⛔ 该装备正在穿戴中"
        extra = equipment.extra_attrs or {}
        if extra.get("_frozen_for_trade") or extra.get("_frozen_for_auction") or extra.get("_frozen_for_stall"):
            return False, "⛔ 该物品已在交易中"
    else:
        # 自动选择第一件
        conditions = [
            ItemInstance.player_id == player.id,
            ItemInstance.item_id == item_cfg.item_id,
        ]
        if not is_inscription:
            conditions.append(ItemInstance.equipped == False)
        stmt = select(ItemInstance).where(*conditions)
        result = await session.execute(stmt)
        candidates = result.scalars().all()
        available = [
            e for e in candidates
            if not (e.extra_attrs or {}).get("_frozen_for_trade")
            and not (e.extra_attrs or {}).get("_frozen_for_auction")
            and not (e.extra_attrs or {}).get("_frozen_for_stall")
        ]
        if not available:
            return False, f"⛔ 背包中没有可上架的「{item_cfg.name}」"
        equipment = available[0]

    # 冻结
    extra_attrs = equipment.extra_attrs or {}
    extra_attrs["_frozen_for_stall"] = True
    equipment.extra_attrs = extra_attrs
    session.add(equipment)
    await session.flush()

    # 生成摘要
    from ..economy.equipment_trade_service_new import EquipmentTradeService as ETS_New
    summary = ETS_New.generate_instance_summary(equipment)

    si = StallItem(
        stall_id=stall.id,
        seller_id=player.id,
        item_id=item_cfg.item_id,
        quantity=1,
        unit_price=unit_price,
        is_instance_trade=True,
        item_instance_id=equipment.id,
        equipment_summary=summary,
    )
    await uow.stall_items.add(si)

    item_display = item_cfg.get_display_name()
    return True, (
        f"✅ 已上架到摊位\n"
        f"📦 {item_display}（{summary}）\n"
        f"💰 单价：{unit_price:,}💰"
    )


async def unlist_item(uow: UnitOfWork, player: Player, slot_index: int) -> Tuple[bool, str]:
    """下架指定序号的商品"""
    session = uow.session

    stall = await uow.player_stalls.get_active_by_player(player.id)
    if not stall:
        return False, "⛔ 你当前没有摊位"

    items = await uow.stall_items.find_by_stall(stall.id)
    if slot_index < 1 or slot_index > len(items):
        return False, f"⛔ 无效序号，当前摊位有 {len(items)} 件商品"

    si = items[slot_index - 1]
    item_cfg = config.items_config["by_id"].get(si.item_id)
    item_name = item_cfg.get_display_name() if item_cfg else si.item_id

    # 退回物品
    if si.is_instance_trade and si.item_instance_id:
        equipment = await session.get(ItemInstance, si.item_instance_id)
        if equipment:
            extra = equipment.extra_attrs or {}
            extra.pop("_frozen_for_stall", None)
            equipment.extra_attrs = extra
            session.add(equipment)
    else:
        try:
            await ItemInstance.add_item(session, player.id, si.item_id, si.quantity)
        except ValueError as e:
            return False, f"⛔ 退回物品失败：{e}"

    await uow.stall_items.delete(si)

    return True, f"✅ 已下架「{item_name}」，物品已退回背包"
```

- [ ] **Step 4: 实现购买**

```python
async def buy_item(
    uow: UnitOfWork,
    buyer: Player,
    seller_uid: int,
    slot_index: int,
    quantity: int = 1,
) -> Tuple[bool, str]:
    """购买摊位商品"""
    session = uow.session
    from sqlalchemy import select

    # 1. 查找摊主
    stmt = select(Player).where(Player.uid == seller_uid)
    result = await session.execute(stmt)
    seller = result.scalars().first()
    if not seller:
        return False, f"⛔ 未找到UID为{seller_uid}的玩家"

    if buyer.id == seller.id:
        return False, "⛔ 不能购买自己摊位的商品"

    # 2. 查找摊位
    stall = await uow.player_stalls.get_active_by_player(seller.id)
    if not stall:
        return False, f"⛔ 该玩家没有摆摊"

    # 3. 查找商品
    items = await uow.stall_items.find_by_stall(stall.id)
    if slot_index < 1 or slot_index > len(items):
        return False, f"⛔ 无效序号（该摊位有{len(items)}件商品）"

    si = items[slot_index - 1]
    item_cfg = config.items_config["by_id"].get(si.item_id)
    item_name = item_cfg.get_display_name() if item_cfg else si.item_id

    # 4. 数量校验
    if si.is_instance_trade:
        quantity = 1  # 装备固定1件
    if quantity > si.quantity:
        return False, f"⛔ 库存不足（剩余{si.quantity}件）"
    if quantity < 1:
        return False, "⛔ 购买数量至少1"

    # 5. 计算费用
    total_cost = si.unit_price * quantity
    if buyer.gold < total_cost:
        return False, f"⛔ 金币不足（需要{total_cost:,}💰，你有{buyer.gold:,}💰）"

    # 6. 计算税
    system_estimate = getattr(item_cfg, "price", 0) or 0
    if si.is_instance_trade and si.item_instance_id:
        try:
            from ..economy.equipment_trade_service import EquipmentTradeService
            equipment = await session.get(ItemInstance, si.item_instance_id)
            if equipment:
                min_val, _ = EquipmentTradeService.calculate_equipment_value_range(equipment)
                system_estimate = max(system_estimate, min_val)
        except Exception:
            pass

    tax = calculate_stall_tax(si.unit_price, quantity, system_estimate)
    seller_income = total_cost - tax

    # 7. 扣款 & 卖家到账
    buyer.gold -= total_cost
    seller.gold += seller_income
    session.add(buyer)
    session.add(seller)

    # 8. 转移物品
    if si.is_instance_trade and si.item_instance_id:
        equipment = await session.get(ItemInstance, si.item_instance_id)
        if not equipment:
            return False, "⛔ 物品数据异常"
        extra = equipment.extra_attrs or {}
        extra.pop("_frozen_for_stall", None)
        equipment.extra_attrs = extra
        equipment.player_id = buyer.id
        session.add(equipment)
    else:
        try:
            await ItemInstance.add_item(session, buyer.id, si.item_id, quantity)
        except ValueError as e:
            return False, f"⛔ 背包空间不足：{e}"

    # 9. 更新或删除商品条目
    if quantity >= si.quantity:
        await uow.stall_items.delete(si)
    else:
        si.quantity -= quantity
        session.add(si)

    # 10. 记录交易
    from ..models.trade_record import TradeRecord, TradeType
    for record_data in [
        (buyer.id, TradeType.BUY),
        (seller.id, TradeType.SELL),
    ]:
        record = TradeRecord(
            player_id=record_data[0],
            trade_type=record_data[1],
            market_id=f"stall_{stall.id}",
            item_id=si.item_id,
            quantity=quantity,
            unit_price=si.unit_price,
            total_amount=total_cost,
            trade_time=datetime.now(),
            is_cross_market=False,
        )
        session.add(record)

    await session.flush()

    tax_str = f"（税{tax:,}💰）" if tax > 0 else ""
    equip_info = f"（{si.equipment_summary}）" if si.equipment_summary else ""
    return True, (
        f"✅ 购买成功！\n"
        f"📦 {item_name}{equip_info} ×{quantity}\n"
        f"💰 支付：{total_cost:,}💰{tax_str}\n"
        f"👤 卖家{seller.nickname}到手：{seller_income:,}💰"
    )
```

- [ ] **Step 5: 实现摊位名/吆喝/过期处理**

```python
async def set_stall_name(uow: UnitOfWork, player: Player, name: str) -> Tuple[bool, str]:
    """设置摊位名"""
    stall = await uow.player_stalls.get_active_by_player(player.id)
    if not stall:
        return False, "⛔ 你当前没有摊位"
    if len(name) > STALL_NAME_MAX_LEN:
        return False, f"⛔ 摊位名最多{STALL_NAME_MAX_LEN}个字"
    stall.stall_name = name
    uow.session.add(stall)
    return True, f"✅ 摊位名已设为「{name}」"


async def set_shout(uow: UnitOfWork, player: Player, text: str) -> Tuple[bool, str]:
    """设置吆喝语"""
    stall = await uow.player_stalls.get_active_by_player(player.id)
    if not stall:
        return False, "⛔ 你当前没有摊位"
    if len(text) > SHOUT_MAX_LEN:
        return False, f"⛔ 吆喝语最多{SHOUT_MAX_LEN}个字"
    stall.shout_text = text
    uow.session.add(stall)
    return True, f"✅ 吆喝语已设为：{text}"


async def expire_stalls(uow: UnitOfWork) -> int:
    """批量过期处理（定时任务调用）"""
    expired = await uow.player_stalls.find_expired_active()
    count = 0
    for stall in expired:
        try:
            await _return_all_stall_items(uow, stall)
            stall.status = "expired"
            uow.session.add(stall)
            count += 1
        except Exception as e:
            logger.error(f"[摊位] 过期处理失败 stall_id={stall.id}: {e}")
    return count
```

---

## 实施顺序

1. **Task 1** — ORM 模型（建表基础）
2. **Task 3** — 摊位令道具（items.yaml）
3. **Task 2** — Repository + UoW 注册
4. **Task 10** — Service 完整实现
5. **Task 5** — 命令处理器
6. **Task 6** — 定时任务
7. **Task 7** — 模块注册
8. **Task 8** — 挂牌市场禁止GOODS
9. **Task 9** — 帮助系统 + 知识库

---

## 验证清单

- [ ] Bot启动后 `player_stall` 和 `stall_item` 表自动创建
- [ ] `摆摊` 在城镇消耗摊位令成功开摊
- [ ] `摆摊` 在荒野/诡域被拒绝
- [ ] `上摊 物品名 单价` 成功上架，物品从背包扣除
- [ ] `上摊` 装备时走选择流程（多件）或直接上架（单件）
- [ ] `上摊` GOODS类型被拒绝
- [ ] `下摊 序号` 退回物品
- [ ] `买摊 UID 序号` 扣金币+转移物品+税率正确
- [ ] 超高溢价税率计算正确（5倍/20倍阈值）
- [ ] `逛摊` 显示当前城镇摊位列表
- [ ] `搜摊 物品名` 跨城镇搜索
- [ ] `摊位 UID` 查看他人摊位
- [ ] `收摊` 退回所有物品
- [ ] 24小时后定时任务自动收摊
- [ ] 装备冻结标记 `_frozen_for_stall` 正确设置/清除
- [ ] 挂牌市场 GOODS 物品被拒绝
- [ ] 帮助命令正常显示
