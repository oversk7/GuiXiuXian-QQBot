# 斗法天梯 实施计划

**对应设计**: [2026-04-10-dharma-ladder-pvp-design.md](../specs/2026-04-10-dharma-ladder-pvp-design.md)
**日期**: 2026-04-10
**类型**: 实现计划

---

## 0. 前置研究结论

| 领域 | 结论 |
|------|------|
| **数据库迁移** | 新模型加到 `models/__init__.py` 即可，由 `Base.metadata.create_all` 自动建表 |
| **战斗引擎** | 直接复用 `BattleIntegrationHelper.compact_player_vs_player_battle(p1, p2, session, seed, max_rounds=30)` 返回 `(victory, log, p1_dmg, p2_dmg)` |
| **赛季调度** | 采用 world_boss 同款 **懒加载** 模式，无需 APScheduler |
| **关系排除** | 查询 `player_relationship` 表 type 为 mentorship/sworn/marriage |
| **月卡判断** | `MonthlyCard.get_active_benefits(player_id)` 返回 dict 含 `premium_active` |
| **称号** | 暂用 player 表新字段 `titles` (JSON 数组) 或借鉴现有 |
| **YAML 知识库** | 1:1 对应 help.py 的 handler，复制 msg 到 body |

---

## 1. 文件结构

```
plugins/xiuxian_game/
├── models/
│   ├── ladder.py                    [新建] LadderRating/LadderMatchLog/LadderSeason
│   └── __init__.py                  [修改] 注册新模型
├── battle/
│   └── ladder/                      [新建目录]
│       ├── __init__.py              [新建] 命令注册入口
│       ├── service.py               [新建] LadderRatingService
│       ├── shop.py                  [新建] LadderShopService + SHOP_ITEMS
│       └── commands.py              [新建] 7 个命令处理器
├── player/
│   └── help.py                      [修改] 加入斗法天梯帮助命令
└── data/
    └── knowledge/
        └── ladder_help.yaml         [新建] AI 知识库
```

> 选择 `battle/ladder/` 子目录而不是顶层 `ladder/`，因为它本质是一种 PvP 玩法，归类到 battle 下与现有 `pvp_commands.py` 同级。

---

## 2. 模型层实现 (Step 1)

**文件**: `plugins/xiuxian_game/models/ladder.py`

```python
from __future__ import annotations
from datetime import datetime, date
from sqlalchemy import String, Integer, BigInteger, Boolean, DateTime, Date, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from .db import Base


class LadderRating(Base):
    """玩家天梯档案 - ELO 评分、段位、魂晶、统计"""
    __tablename__ = "ladder_rating"

    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), primary_key=True)
    rating: Mapped[int] = mapped_column(Integer, default=1000, server_default="1000")
    rank_tier: Mapped[str] = mapped_column(String(16), default="九品", server_default="九品")
    matches_played: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    wins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    losses: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    draws: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    win_streak: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    best_rating: Mapped[int] = mapped_column(Integer, default=1000, server_default="1000")
    season_id: Mapped[int] = mapped_column(Integer, default=0, server_default="0", index=True)

    daily_matches: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    daily_defense_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    daily_reset_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    daily_first_win_claimed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    matchmaking_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    soul_crystals: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    last_match_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


Index("idx_ladder_rating_value", LadderRating.rating.desc())
Index("idx_ladder_season_rating", LadderRating.season_id, LadderRating.rating.desc())


class LadderMatchLog(Base):
    """天梯对战记录"""
    __tablename__ = "ladder_match_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(Integer, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)

    attacker_id: Mapped[str] = mapped_column(String(32), index=True)
    defender_id: Mapped[str] = mapped_column(String(32), index=True)
    attacker_uid: Mapped[int] = mapped_column(Integer, default=0)
    defender_uid: Mapped[int] = mapped_column(Integer, default=0)
    attacker_name: Mapped[str] = mapped_column(String(32), default="")
    defender_name: Mapped[str] = mapped_column(String(32), default="")

    result: Mapped[str] = mapped_column(String(16))  # attacker_win / defender_win / draw
    attacker_rating_before: Mapped[int] = mapped_column(Integer)
    attacker_rating_after: Mapped[int] = mapped_column(Integer)
    attacker_rating_change: Mapped[int] = mapped_column(Integer)
    defender_rating_before: Mapped[int] = mapped_column(Integer)
    defender_rating_after: Mapped[int] = mapped_column(Integer)
    defender_rating_change: Mapped[int] = mapped_column(Integer)

    defender_notified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", index=True)


Index("idx_ladder_match_attacker_ts", LadderMatchLog.attacker_id, LadderMatchLog.timestamp.desc())
Index("idx_ladder_match_defender_ts", LadderMatchLog.defender_id, LadderMatchLog.timestamp.desc())
Index("idx_ladder_match_defender_unnotified", LadderMatchLog.defender_id, LadderMatchLog.defender_notified)


class LadderSeason(Base):
    """天梯赛季"""
    __tablename__ = "ladder_season"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_number: Mapped[int] = mapped_column(Integer, unique=True)
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / settling / ended
    rewards_distributed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

**修改 `models/__init__.py`**：
```python
from .ladder import LadderRating, LadderMatchLog, LadderSeason
```
并加到 `__all__`。

---

## 3. 核心服务层 (Step 2)

**文件**: `plugins/xiuxian_game/battle/ladder/service.py`

主要职责：
- 档案 CRUD
- ELO 计算（静态方法）
- 段位换算
- 异步匹配
- 跑战斗 + 更新评分 + 发奖
- 赛季懒加载/结算

### 3.1 段位常量

```python
RANK_TIERS: List[Tuple[int, str]] = [
    (0,    "散修"),
    (1000, "九品"),
    (1150, "八品"),
    (1300, "七品"),
    (1450, "六品"),
    (1600, "五品"),
    (1750, "四品"),
    (1900, "三品"),
    (2050, "二品"),
    (2200, "一品"),
    (2350, "道君"),
]

MIN_LEVEL = 30
DEFAULT_RATING = 1000
DAILY_MATCHES_BASE = 5
DAILY_MATCHES_PREMIUM_BONUS = 3
DAILY_DEFENSE_LIMIT = 10
SAME_OPPONENT_COOLDOWN_HOURS = 6
MATCH_INTERVAL_SECONDS = 60
WIN_STREAK_DECAY_THRESHOLD = 10
RATING_RANGE_PRIMARY = 150
RATING_RANGE_FALLBACK = 300
```

### 3.2 ELO 计算

```python
@staticmethod
def calculate_elo_change(rating_a: int, rating_b: int, result_a: float, k_factor: int) -> int:
    expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
    return round(k_factor * (result_a - expected_a))

@staticmethod
def get_k_factor(rating: LadderRating) -> int:
    if rating.matches_played < 30:
        return 40
    if rating.rating >= 2350:
        return 16
    return 24
```

### 3.3 匹配实现

```python
async def find_opponent(self, attacker: Player, attacker_rating: LadderRating) -> Optional[Player]:
    excluded_ids = await self._get_relationship_excluded(attacker.id)
    excluded_ids.add(attacker.id)
    excluded_ids.update(await self._get_recent_opponent_ids(attacker.id, hours=SAME_OPPONENT_COOLDOWN_HOURS))

    for rating_range in (RATING_RANGE_PRIMARY, RATING_RANGE_FALLBACK):
        candidates = await self._query_candidates(
            attacker_rating.rating, rating_range, excluded_ids
        )
        if candidates:
            return random.choice(candidates)
    return None
```

`_query_candidates` SQL：
```sql
SELECT p.* FROM player p
INNER JOIN ladder_rating lr ON p.id = lr.player_id
WHERE lr.matchmaking_enabled = TRUE
  AND lr.daily_defense_count < :defense_limit
  AND lr.rating BETWEEN :rating_low AND :rating_high
  AND p.level >= 30
  AND p.id NOT IN :excluded_ids
  AND (p.last_active_at IS NULL OR p.last_active_at > NOW() - INTERVAL 30 DAY)
LIMIT 20
```

### 3.4 跑战斗

```python
async def run_match(self, attacker: Player) -> dict:
    # 1) 获取/创建评分
    a_rating = await self.get_or_create_rating(attacker.id)
    await self.reset_daily_counters_if_needed(a_rating)

    # 2) 校验
    self._validate_can_match(attacker, a_rating)

    # 3) 找对手
    defender = await self.find_opponent(attacker, a_rating)
    if not defender:
        raise LadderMatchError("当前没有找到合适的对手，稍后再试")
    d_rating = await self.get_or_create_rating(defender.id)
    await self.reset_daily_counters_if_needed(d_rating)

    # 4) 跑战斗
    seed = f"LADDER_{attacker.id}_{defender.id}_{int(time.time()*1000)}"
    victory, battle_log, _, _ = await BattleIntegrationHelper.compact_player_vs_player_battle(
        attacker, defender, self.session, seed=seed, max_rounds=30
    )

    # 5) 计算 ELO
    result_a = 1.0 if victory else 0.0
    k_a = self.get_k_factor(a_rating)
    k_d = self.get_k_factor(d_rating)
    raw_change = self.calculate_elo_change(a_rating.rating, d_rating.rating, result_a, k_a)

    # 连胜衰减
    if victory and a_rating.win_streak >= WIN_STREAK_DECAY_THRESHOLD:
        raw_change = max(1, raw_change // 2)

    a_rating.rating += raw_change
    d_rating.rating -= raw_change  # 对称变化（守方扣等量）
    # 对调 d_rating 时使用守方自己的 K 计算更精确，但简单起见用对称
    # （未来如有不公平问题再优化）

    # 6) 段位刷新
    a_rating.rank_tier = self.get_rank_tier(a_rating.rating)
    d_rating.rank_tier = self.get_rank_tier(d_rating.rating)

    # 7) 战绩
    a_rating.matches_played += 1
    d_rating.matches_played += 1
    if victory:
        a_rating.wins += 1; a_rating.win_streak += 1
        d_rating.losses += 1; d_rating.win_streak = 0
    else:
        a_rating.losses += 1; a_rating.win_streak = 0
        d_rating.wins += 1; d_rating.win_streak += 1

    a_rating.best_rating = max(a_rating.best_rating, a_rating.rating)
    d_rating.best_rating = max(d_rating.best_rating, d_rating.rating)

    # 8) 计数器
    a_rating.daily_matches += 1
    d_rating.daily_defense_count += 1
    a_rating.last_match_at = datetime.now()

    # 9) 魂晶
    if victory:
        soul_attack = 100
        if not a_rating.daily_first_win_claimed:
            soul_attack += 200
            a_rating.daily_first_win_claimed = True
        a_rating.soul_crystals += soul_attack
        d_rating.soul_crystals += 30
    else:
        a_rating.soul_crystals += 30
        soul_def = 100
        if not d_rating.daily_first_win_claimed:
            soul_def += 200
            d_rating.daily_first_win_claimed = True
        d_rating.soul_crystals += soul_def

    # 10) 写日志
    await self._log_match(season_id=..., ...)

    # 11) 返回结果
    return {
        "victory": victory,
        "battle_log": battle_log,
        "defender": defender,
        "rating_change": raw_change,
        "new_rating": a_rating.rating,
        "new_rank": a_rating.rank_tier,
        "soul_earned": soul_attack if victory else 30,
    }
```

### 3.5 赛季懒加载

```python
async def get_or_create_active_season(self) -> LadderSeason:
    stmt = select(LadderSeason).where(LadderSeason.status == "active").order_by(LadderSeason.id.desc())
    season = (await self.session.execute(stmt)).scalars().first()

    now = datetime.now()
    if season and season.end_at > now:
        return season  # 仍在赛季内

    # 需要结算
    if season:
        await self.settle_season(season)

    # 创建新赛季
    new_number = (season.season_number + 1) if season else 1
    start = datetime(now.year, now.month, 1)
    next_month = start.replace(day=28) + timedelta(days=4)
    end = next_month - timedelta(days=next_month.day)
    end = end.replace(hour=23, minute=59, second=59)

    new_season = LadderSeason(
        season_number=new_number,
        start_at=start,
        end_at=end,
        status="active",
    )
    self.session.add(new_season)
    await self.session.flush()
    return new_season

async def settle_season(self, season: LadderSeason):
    season.status = "settling"
    # 查 top 100，按段位发奖
    # 软重置所有玩家积分：rating > 1500 → 1500 + (rating-1500)*0.3
    # ...
    season.status = "ended"
    season.rewards_distributed = True
```

---

## 4. 商店实现 (Step 3)

**文件**: `plugins/xiuxian_game/battle/ladder/shop.py`

```python
LADDER_SHOP_ITEMS: Dict[str, dict] = {
    "斗法令": {
        "price": 50,
        "description": "立即增加 1 次今日匹配次数",
        "max_per_day": 5,
        "type": "consumable_immediate",
        "effect": "add_daily_match",
    },
    "神识符": {
        "price": 100,
        "description": "下次匹配时重新匹配一次对手",
        "max_per_day": 3,
        "type": "item",
        "item_id": "shen_shi_fu",
    },
    "稳定水晶": {
        "price": 800,
        "description": "装备升阶用稳定水晶 ×1",
        "type": "item",
        "item_id": "stable_crystal",
    },
    "灵气补给": {
        "price": 200,
        "description": "立即获得 50 香火",
        "type": "currency",
        "field": "incense",
        "amount": 50,
    },
    "称号·斗法新秀": {
        "price": 1000,
        "description": "获得永久称号「斗法新秀」",
        "type": "title",
        "title_id": "ladder_rookie",
    },
    "称号·斗法狂徒": {
        "price": 3000,
        "description": "获得永久称号「斗法狂徒」",
        "type": "title",
        "title_id": "ladder_madman",
    },
}
```

`LadderShopService.redeem(player, rating, item_name, qty)` 处理各 type。

> **Phase 2 简化**：先实现 `斗法令` / `灵气补给` / `稳定水晶` 三种最简单的；称号、神识符可后续。

---

## 5. 命令处理器 (Step 4)

**文件**: `plugins/xiuxian_game/battle/ladder/commands.py`

```python
ladder_main_cmd = on_command("斗法天梯", aliases={"天梯", "斗法"}, block=True, priority=8)

@ladder_main_cmd.handle()
async def handle_ladder(event, args=CommandArg()):
    text = args.extract_plain_text().strip()

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await ladder_main_cmd.finish("⛔ 请先创建角色")

        service = LadderRatingService(session)
        season = await service.get_or_create_active_season()

        if not text:
            # 主页
            return await _show_home(player, service, season, event)

        sub = text.split()[0]
        if sub == "匹配":
            return await _do_match(player, service, season, event)
        if sub == "排行":
            return await _show_ranking(player, service, season, event)
        if sub == "历史":
            return await _show_history(player, service, season, event)
        if sub in ("开启", "开"):
            return await _toggle_matchmaking(player, service, True, event)
        if sub in ("关闭", "关"):
            return await _toggle_matchmaking(player, service, False, event)

        await ladder_main_cmd.finish("⛔ 未知子命令，可用：匹配/排行/历史/开启/关闭")


shop_cmd = on_command("斗法商店", block=True, priority=8)
redeem_cmd = on_command("斗法兑换", block=True, priority=8)
```

---

## 6. 推送钩子

在 `_show_home` 和 `_show_history` 末尾调用：
```python
notifications = await service.get_pending_notifications(player.id)
if notifications:
    lines.append("\n━━━ 离线对战通知 ━━━")
    for log in notifications[:5]:
        lines.append(f"· {log.timestamp:%m-%d %H:%M} 被 {log.attacker_name} 挑战，结果：{...}, 积分 {log.defender_rating_change:+d}")
    await service.mark_notifications_seen(player.id)
```

---

## 7. help.py 更新 (Step 5)

在 `战斗挑战` 模块卡片末尾加：
```python
"**🏆 斗法天梯**\n"
f"{cmd('斗法天梯')} 主页 | {cmd('斗法天梯 匹配', '斗法天梯 匹配')} 进行天梯赛 | {cmd('斗法商店')} 魂晶商店\n"
```

新增独立帮助命令 `斗法天梯帮助`：
```python
ladder_help_cmd = on_command("斗法天梯帮助", aliases={"天梯帮助"}, priority=4, block=True)
```

---

## 8. AI 知识库 (Step 6)

**文件**: `plugins/xiuxian_game/data/knowledge/ladder_help.yaml`

复制帮助内容到 body 字段。

---

## 9. 注册入口

**文件**: `plugins/xiuxian_game/battle/ladder/__init__.py`

```python
from . import commands  # 触发命令注册
```

NoneBot 通过 `pyproject.toml` 自动加载 `xiuxian_game` 插件，battle 子目录会被递归导入。需要在某处导入 `from .battle import ladder`，最简单的方式是直接在 `battle/__init__.py` 中加 `from . import ladder` 或者新增 `pvp_commands` 同级的 `import ladder.commands`。

> 检查 `battle/__init__.py` 当前是否导入子模块，决定如何接入。

---

## 10. 验证步骤

1. **语法检查**：`python -m py_compile` 所有新文件
2. **启动检查**：本地 mock session 检查 import 路径是否正确
3. **功能测试**（手动）：
   - 创建两个测试玩家
   - 设置 level=30
   - 一方发起匹配
   - 检查 rating 是否更新
   - 检查 LadderMatchLog 是否写入
4. **数据库检查**：启动 bot 后用 `.schema ladder_*` (sqlite) 或 `DESC` (mysql) 验证表已创建

---

## 11. 实施顺序（自上而下）

1. ✅ 设计文档
2. ✅ 实施计划（本文件）
3. ⬜ 模型层（`models/ladder.py` + `__init__.py`）
4. ⬜ 服务层（`battle/ladder/service.py`）
5. ⬜ 商店（`battle/ladder/shop.py`）
6. ⬜ 命令（`battle/ladder/commands.py` + `__init__.py`）
7. ⬜ 注册入口（`battle/__init__.py` 调整）
8. ⬜ help.py 更新
9. ⬜ knowledge YAML
10. ⬜ 语法检查与代码审查
