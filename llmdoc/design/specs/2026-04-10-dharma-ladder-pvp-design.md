# 斗法天梯 (Dharma Ladder) 设计规格

**日期**: 2026-04-10
**作者**: AI Agent + 用户讨论
**状态**: 已批准
**类型**: 新功能 (PvP 玩法)

---

## 1. 背景与动机

### 现状
游戏现有 PvP 玩法：
- **切磋 (`切磋 UID`)**：无损失，纯模拟，无奖励，无排名
- **野外死斗 (`攻击 UID`)**：荒野/诡域生效，掉物品，恶意大
- **世界 BOSS**：本质 PvE，全服竞争伤害排名

### 缺口
- 缺乏**长期竞技目标**（无 ELO/排名）
- 缺乏**低恶意 PvP 奖励循环**（切磋无奖励，死斗太惨烈）
- 100-300 级中后期玩家**没有刷分的感觉**

### 玩家诉求
玩家明确反馈：野外死斗恶意大，需要一个**有趣且适合**的 PvP 玩法。

---

## 2. 设计目标

| 目标 | 说明 |
|------|------|
| **零物品损失** | 神识投影对决，不掉装备/物品/HP |
| **异步友好** | QQ Bot 是异步环境，不能依赖双方同时在线 |
| **进度感** | 段位 + ELO 提供清晰的成长曲线 |
| **公平匹配** | 评分接近的玩家配对，避免越级虐杀 |
| **防滥用** | 多重限制防止刷分、虐菜、关系户带 |
| **奖励驱动** | 单场 + 赛季双层奖励，新货币魂晶专属 PvP |

---

## 3. 核心玩法

### 3.1 玩法循环
```
玩家发送「斗法天梯 匹配」
  ↓
系统按评分查找一名对手快照
  ↓
立即调用 BattleIntegrationHelper.compact_player_vs_player_battle 模拟对战
  ↓
更新双方 ELO + 段位 + 魂晶 + 战绩
  ↓
攻方立即看到结果；守方下次上线收到推送
```

### 3.2 段位系统（诡道九品）

| 段位 | 积分区间 | 说明 |
|------|---------|------|
| 散修 | < 1000 | 入门段位，新玩家起点 |
| 九品 | 1000-1149 | |
| 八品 | 1150-1299 | |
| 七品 | 1300-1449 | |
| 六品 | 1450-1599 | |
| 五品 | 1600-1749 | |
| 四品 | 1750-1899 | |
| 三品 | 1900-2049 | |
| 二品 | 2050-2199 | |
| 一品 | 2200-2349 | |
| **道君** | ≥ 2350 | 顶尖段位（每月赛季前 100 上墙） |

**新玩家起点**：1000 分（九品入口）。
**参赛门槛**：玩家等级 ≥ 30。

### 3.3 ELO 算法

标准 ELO，K 因子动态：
| 状态 | K 因子 | 说明 |
|------|-------|------|
| 定位赛（前 30 场） | 40 | 快速定位真实段位 |
| 常规 | 24 | 主要游戏阶段 |
| 道君段位 | 16 | 顶尖玩家避免大涨大跌 |

公式：
```
expected_a = 1 / (1 + 10^((rating_b - rating_a) / 400))
change_a = round(K * (result_a - expected_a))
其中 result_a ∈ {1: 胜, 0.5: 平, 0: 负}
```

**对称变化**：守方与攻方积分变化幅度相同（公平且防止匹配池稀释）。

### 3.4 异步匹配机制

由于 QQ Bot 玩家不会同时在线，采用**异步快照匹配**：

1. 攻方点匹配，系统在 LadderRating 表中按以下规则筛选对手：
   - 评分差 ±150 内（无解时阶梯放宽到 ±300）
   - 30 天内有活跃记录（last_active_at）
   - 等级 ≥ 30
   - 不是自己
   - 6 小时内未对战过该玩家
   - 不是结义/婚姻/师徒关系
   - 守方匹配开关为 True
   - 守方今日被匹配次数 < 10
2. 锁定后调用 `BattleIntegrationHelper.compact_player_vs_player_battle(attacker, defender, session)`
3. 战斗结束后更新双方评分、段位、魂晶、战绩
4. 写入 LadderMatchLog
5. 守方在下次任意命令调用时收到推送（通过 LadderMatchLog 查找未通知记录）

### 3.5 限制与防滥用

| 维度 | 数值 | 原因 |
|------|------|------|
| 每日匹配 | 5 场 | 主要限制 |
| 高级月卡加成 | +3 场/天 | 月卡权益 |
| 匹配间隔 | 60 秒 | 防止快速刷分 |
| 同对手冷却 | 6 小时 | 防止针对性刷 |
| 守方被匹配 | 10 次/天上限 | 保护离线玩家 |
| 关系排除 | 婚姻/结义/师徒 | 防止关系户带 |
| 连胜衰减 | 10 连胜后 ELO 收益 -50% | 防止超长连胜 |
| 每日重置 | 0:00 | 标准 |
| 退出匹配池 | `斗法天梯 关闭` | 玩家自主权 |

---

## 4. 奖励系统

### 4.1 单场奖励

| 结果 | ELO | 魂晶 |
|------|-----|------|
| 胜 | +ELO | 100 |
| 负 | -ELO | 30 |
| 平 | 0 | 60 |

**每日首胜额外奖励**：+200 魂晶。

### 4.2 赛季奖励（每月底自动结算）

| 排名 | 奖励 |
|------|------|
| 第 1 名 | 限定称号「斗法道君」+ 1000 香火 + 5 稳定水晶 |
| 第 2-3 名 | 称号「天梯争锋者」+ 500 香火 + 3 稳定水晶 |
| 第 4-10 名 | 称号「天梯名宿」+ 300 香火 + 2 稳定水晶 |
| 第 11-50 名 | 称号「天梯高手」+ 100 香火 + 1 稳定水晶 |
| 第 51-100 名 | 50 香火 + 1 随机宝石 |
| 100 名后参与 | 20 香火 |

**软重置规则**：
```python
if rating > 1500:
    new_rating = 1500 + (rating - 1500) * 0.3
else:
    new_rating = rating  # 不动
```
> 防止断崖式下跌，但削弱长期固化。

### 4.3 新货币：魂晶

魂晶 (`soul_crystals`) 是 PvP 专属货币，**不与游戏内其他货币互换**。

**获取**：仅天梯对战。
**保存位置**：LadderRating 表上的 `soul_crystals` 字段（不污染 player 表）。

### 4.4 斗法商店

通过 `斗法商店` 命令查看，`斗法兑换 物品名 [数量]` 兑换。

| 物品 | 价格 | 效果 |
|------|------|------|
| 斗法令 | 50 魂晶 | 立即增加 1 次今日匹配次数 |
| 神识符 | 100 魂晶 | 下次匹配时重新滚一次对手 |
| 稳定水晶 | 800 魂晶 | 装备升阶用稳定水晶 |
| 随机高级宝石 | 600 魂晶 | 蓝/紫品质宝石随机 |
| 改名卡 | 1500 魂晶 | 改名功能 |
| 称号「斗法新秀」 | 1000 魂晶 | 永久称号 |
| 称号「斗法狂徒」 | 3000 魂晶 | 永久称号 |
| 灵气补给 | 200 魂晶 | 50 香火 |

> 商品列表后续可拓展，先实现核心 5-8 件。

---

## 5. 命令清单

| 命令 | 作用 |
|------|------|
| `斗法天梯` | 主页：当前段位、积分、本月排名、剩余匹配次数 |
| `斗法天梯 匹配` | 进行一场天梯对战 |
| `斗法天梯 排行` | 查看本赛季 TOP 50 |
| `斗法天梯 历史` | 查看自己最近 20 场战绩 |
| `斗法天梯 开启` / `斗法天梯 关闭` | 是否进入匹配池（默认开启） |
| `斗法商店` | 查看魂晶商店 |
| `斗法兑换 物品名 [数量]` | 兑换商店物品 |

---

## 6. 数据模型

### 6.1 LadderRating（玩家天梯档案）

```python
class LadderRating(Base):
    __tablename__ = "ladder_rating"

    player_id: str (PK, FK→player.id)
    rating: int (default=1000)        # ELO 评分
    rank_tier: str (default="九品")    # 当前段位（缓存）
    matches_played: int               # 总场次
    wins: int
    losses: int
    draws: int
    win_streak: int                   # 当前连胜
    best_rating: int                  # 历史最高
    season_id: int                    # 当前赛季 id

    daily_matches: int                # 今日已用次数（攻方）
    daily_defense_count: int          # 今日被匹配次数（守方保护）
    daily_reset_at: date              # 上次重置日期
    daily_first_win_claimed: bool     # 今日首胜奖励是否领过

    matchmaking_enabled: bool (default=True)
    soul_crystals: BigInteger         # 魂晶余额
    last_match_at: datetime           # 防匹配间隔
```

### 6.2 LadderMatchLog（对战记录）

```python
class LadderMatchLog(Base):
    __tablename__ = "ladder_match_log"

    id: int (PK, autoincrement)
    season_id: int (index)
    timestamp: datetime (default=now)

    attacker_id: str (index, FK→player.id)
    defender_id: str (index, FK→player.id)
    attacker_uid: int
    defender_uid: int
    attacker_name: str
    defender_name: str

    result: str  # "attacker_win" / "defender_win" / "draw"
    attacker_rating_before: int
    attacker_rating_after: int
    attacker_rating_change: int
    defender_rating_before: int
    defender_rating_after: int
    defender_rating_change: int

    defender_notified: bool (default=False)  # 守方是否已收到推送
```

### 6.3 LadderSeason（赛季管理）

```python
class LadderSeason(Base):
    __tablename__ = "ladder_season"

    id: int (PK, autoincrement)
    season_number: int                # 第 N 赛季
    start_at: datetime
    end_at: datetime                  # 赛季结束时间
    status: str                       # "active" / "ended" / "settling"
    rewards_distributed: bool (default=False)
```

---

## 7. 服务架构

### 7.1 LadderRatingService

核心业务逻辑封装：

```python
class LadderRatingService:
    # ===== 档案管理 =====
    async def get_or_create_rating(player_id) -> LadderRating
    async def reset_daily_counters_if_needed(rating: LadderRating)

    # ===== 段位/积分计算 =====
    @staticmethod
    def get_rank_tier(rating: int) -> str
    @staticmethod
    def calculate_elo_change(rating_a, rating_b, result_a, k_factor) -> int

    # ===== 匹配 =====
    async def find_opponent(attacker: Player, attacker_rating: LadderRating) -> Optional[Player]

    # ===== 跑战斗 =====
    async def run_match(attacker: Player) -> dict
        # 返回结构化结果：win/loss/draw, battle_log, rating_changes, rewards

    # ===== 赛季 =====
    async def get_or_create_active_season() -> LadderSeason
    async def maybe_settle_season() -> Optional[LadderSeason]
    async def settle_season(season: LadderSeason)

    # ===== 推送 =====
    async def get_pending_notifications(player_id) -> List[LadderMatchLog]
    async def mark_notifications_seen(player_id)
```

### 7.2 LadderShopService

```python
class LadderShopService:
    SHOP_ITEMS: Dict[str, Dict]  # 商店静态配置

    @classmethod
    def list_items(cls) -> List[dict]

    @classmethod
    async def redeem(cls, player: Player, rating: LadderRating, item_name: str, quantity: int) -> Tuple[bool, str]
```

### 7.3 推送钩子

由于 QQ Bot 没有主动推送，采用**被动推送**：
- 在 `斗法天梯` 主页与 `斗法天梯 历史` 命令结尾，自动检查 LadderMatchLog 中 `defender_id == player.id AND defender_notified == False` 的记录
- 显示给玩家后标记为 `defender_notified=True`
- 也可以在常用命令（如 `面板`）中加钩子，但优先级低，不影响其他命令

---

## 8. 与现有系统的整合

| 系统 | 接入方式 |
|------|---------|
| **战斗引擎** | 直接复用 `BattleIntegrationHelper.compact_player_vs_player_battle` |
| **玩家关系** | 查询 `player_relationship` 表排除师徒/婚姻/结义 |
| **月卡** | 查询 `MonthlyCard` 的 premium_active 来决定 +3 匹配次数 |
| **背包/物品** | 商店奖励通过现有 `add_item_to_inventory` 工具 |
| **称号系统** | 复用现有称号机制（如果有）或加 player.title 字段 |
| **AI 知识库** | 在 `data/knowledge/` 添加 `ladder_help.yaml` |

---

## 9. 实施分阶段

### Phase 1：核心闭环（必须）
- 数据模型：LadderRating / LadderMatchLog / LadderSeason
- LadderRatingService：匹配、跑战斗、ELO 更新、赛季懒加载
- 命令：`斗法天梯`、`斗法天梯 匹配`、`斗法天梯 历史`、`斗法天梯 开关`

### Phase 2：奖励循环
- 魂晶单场发放
- LadderShopService + `斗法商店` + `斗法兑换` 命令
- 商店初始 5-8 件物品配置

### Phase 3：竞争氛围
- `斗法天梯 排行` 命令
- 赛季懒加载结算 + 奖励分发
- 称号系统（用 player.titles JSON 字段或新建 player_title 表）

### Phase 4：体验完善
- 守方推送钩子
- help.py 加入斗法天梯帮助
- knowledge YAML
- 玩家攻略

---

## 10. 验收标准

- [ ] 玩家可发起匹配并立即看到对战结果
- [ ] 双方 ELO 正确更新
- [ ] 守方下次上线能看到通知
- [ ] 关系户（婚姻/结义/师徒）不会被匹配
- [ ] 连胜衰减生效
- [ ] 每日匹配次数限制生效（含月卡加成）
- [ ] 魂晶正确发放与扣除
- [ ] 商店兑换正常
- [ ] 月底赛季自动结算并发奖
- [ ] 软重置正确执行
- [ ] 排行榜正确显示
- [ ] 帮助文档与 AI 知识库同步

---

## 11. 风险与对策

| 风险 | 对策 |
|------|------|
| **匹配池过小** | 阶梯放宽评分差至 ±300；新玩家起点统一 1000 |
| **守方虐杀** | 守方 10 次/天上限 + 可关闭匹配 |
| **魂晶通胀** | 商店物品稀有，单场奖励小步发放 |
| **赛季漏结算** | 懒加载机制，每次访问自动补算 |
| **战斗模拟一致性** | 复用现有引擎，与切磋一致 |

---

## 12. 后续可拓展

- 双人/三人组队天梯
- 周末天梯赛事（基于天梯积分门槛进入淘汰赛）
- 天梯观战系统
- 天梯赛季主题（每个赛季换段位皮肤/称号）
- 天梯 API 暴露给前端排行展示
