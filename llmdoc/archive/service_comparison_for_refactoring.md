# Service改造对比分析报告

**调研日期**: 2025-11-27
**调研目标**: 对比BankService和InviteRewardService，确定下一个DI改造目标
**调研方法**: 文档分析 + 代码审查

---

## 执行摘要

**核心发现**:
- **BankService**: 不存在独立的Service类，业务逻辑直接嵌入Command Handler中
- **InviteRewardService**: 存在独立Service类，5个@classmethod方法，业务逻辑分离良好
- **推荐**: 先改造InviteRewardService，因其已有良好的分层结构，改造难度更低

---

## 代码证据

### Bank业务逻辑分析

- `plugins/xiuxian_game/economy/bank.py` (327行) - 完整模块
- `plugins/xiuxian_game/models/bank_account.py` (10行) - BankAccount模型

**关键发现**:
- ❌ **没有独立的BankService类**
- ✅ 业务逻辑直接写在Command Handler中 (6个命令处理器函数)
- ✅ 工具函数: `_tier_rate()` (line 21-25), `_apply_interest()` (line 37-51)
- ❌ 每个命令内部都使用 `async with safe_session()` (line 56, 89, 125, 165, 246, 287)

**代码分布**:
```python
# bank.py 结构
_TIERS = [...]                          # Line 14-19: 利率配置
def _tier_rate(balance):                # Line 21-25: 纯函数
def _apply_interest(acc):               # Line 37-51: 利息计算

@bank_balance_cmd.handle()              # Line 55-74
@bank_deposit_cmd.handle()              # Line 78-110
@bank_withdraw_cmd.handle()             # Line 114-144
@bank_transfer_cmd.handle()             # Line 148-229
@deposit_rank_cmd.handle()              # Line 233-281 (N+1查询问题)
@bank_invest_cmd.handle()               # Line 285-327
```

### InviteRewardService分析

- `plugins/xiuxian_game/player/invite_reward_service.py` (184行) - 完整Service类
- `plugins/xiuxian_game/models/invite_reward.py` - InviteReward模型
- `plugins/xiuxian_game/player/invite.py` (275行) - Command Handler调用Service

**关键发现**:
- ✅ **独立的InviteRewardService类** (line 12-184)
- ✅ 5个@classmethod方法，业务逻辑封装良好
- ✅ 所有方法接收 `session: AsyncSession` 参数 (外部注入)
- ✅ 类级别配置: `LEVEL_REWARDS` (line 16-38)
- ✅ 调用方: `player/invite.py` (3处调用), `social/level_hooks.py` (1处调用)

**方法清单**:
1. `create_invite_record(session, invitee_uid, inviter_uid)` (line 40-49) - 创建邀请记录
2. `check_and_grant_level_rewards(session, player_id, new_level)` (line 51-86) - 检查并发放等级奖励
3. `_grant_level_reward(session, invite_record, inviter, invitee, level)` (line 88-127) - 发放指定等级奖励
4. `get_invite_status(session, player_uid)` (line 129-146) - 获取邀请状态
5. `get_pending_rewards_info(session, inviter_uid)` (line 148-184) - 获取待发放奖励信息

---

## 详细对比分析

### 1. 代码规模对比

| 指标 | Bank业务逻辑 | InviteRewardService |
|------|-------------|---------------------|
| **文件路径** | `economy/bank.py` | `player/invite_reward_service.py` |
| **总代码行数** | 327行 | 184行 |
| **Service方法数** | 0个 (无Service类) | 5个@classmethod |
| **工具函数数** | 2个 (`_tier_rate`, `_apply_interest`) | 0个 |
| **Command Handler数** | 6个 (直接处理业务) | 3个 (调用Service) |
| **session使用次数** | 38次 (inline调用) | 12次 (方法参数) |
| **模型依赖** | BankAccount, Player | InviteReward, Player |

### 2. 依赖复杂度对比

#### Bank业务逻辑依赖

**直接导入**:
```python
from ..models.db import safe_session          # Line 7
from ..models.player import Player            # Line 8
from ..models.bank_account import BankAccount # Line 9
from ..utils import message_add_head          # Line 10
from nonebot import on_command                # Line 1
from nonebot.adapters.qq import MessageEvent  # Line 2
```

**依赖模型**: 2个 (Player, BankAccount)
**依赖Service**: 0个
**循环依赖风险**: 🟢 低 (无Service间调用)

**问题**:
- ❌ N+1查询问题 (line 269-272): 循环中逐个查询Player
```python
for idx, acc in enumerate(page_accounts, start=offset + 1):
    p = await session.get(Player, acc.player_id)  # N+1查询
```

#### InviteRewardService依赖

**直接导入**:
```python
from sqlalchemy.ext.asyncio import AsyncSession # Line 5
from sqlalchemy import select                   # Line 6
from ..models.player import Player              # Line 8
from ..models.invite_reward import InviteReward # Line 9
```

**依赖模型**: 2个 (Player, InviteReward)
**依赖Service**: 0个
**循环依赖风险**: 🟢 低 (无Service间调用)

**问题**:
- ⚠️ 潜在N+1查询 (line 157-164): `get_pending_rewards_info` 循环查询Player
```python
for record in records:
    invitee_stmt = select(Player).where(Player.uid == record.invitee_uid)
    invitee_result = await session.execute(invitee_stmt)
    invitee = invitee_result.scalars().first()  # 循环内查询
```

### 3. 业务重要性对比

#### Bank业务逻辑

**核心功能**:
- 存款/取款 (基础金币管理)
- 转账 (玩家间交易)
- 存款排行榜 (社交展示)
- 利息计算 (阶梯利率)

**使用频率**: 🟡 中等 (金币类操作，中等频率)
**业务复杂度**: 🟡 中等 (阶梯利率、转账税收)
**关键度**: 🟡 中等 (非核心战斗系统)

**问题影响**:
- N+1查询影响排行榜性能
- 6个Command Handler打开6个独立safe_session
- 无事务原子性保证

#### InviteRewardService

**核心功能**:
- 邀请记录管理 (绑定邀请码)
- 分级奖励发放 (1级/10级/50级)
- 邀请状态查询 (统计数据)

**使用频率**: 🟢 低 (玩家升级时触发)
**业务复杂度**: 🟢 简单 (奖励配置清晰)
**关键度**: 🟢 低 (辅助社交功能)

**依赖关系**:
- 被调用方: `player/invite.py` (3处), `social/level_hooks.py` (1处)
- 集成点少，改造影响范围小

### 4. 改造难度评估

#### 创建BankService (从零开始)

**改造步骤**:
1. ❌ 需要从Command Handler中**提取业务逻辑**
2. ❌ 创建新的BankService类 (6-8个方法)
3. ❌ 工具函数重构 (`_tier_rate`, `_apply_interest`)
4. ❌ 6个Command Handler全部重构为调用BankService
5. ✅ 修复N+1查询问题 (需要BankRepository支持)
6. ✅ 依赖注入改造

**代码量估算**:
- 新增BankService类: ~200行
- 修改Command Handler: ~150行
- 新增BankRepository: ~100行
- 总计: ~450行

**改造难度**: ⭐⭐⭐⭐ (4/5星)
- 业务逻辑分离复杂
- 需要重构6个Command Handler
- N+1查询优化需要Repository支持

#### 改造InviteRewardService (结构良好)

**改造步骤**:
1. ✅ Service类已存在，只需改造为实例方法
2. ✅ 5个@classmethod → 实例方法
3. ✅ 注入InviteRewardRepository和PlayerRepository
4. ✅ 4个调用方改为从DI容器获取Service
5. ✅ 修复潜在N+1查询 (Repository预加载)

**代码量估算**:
- 修改InviteRewardService: ~50行 (方法签名)
- 新增InviteRewardRepository: ~80行
- 修改调用方: ~40行 (4处)
- 总计: ~170行

**改造难度**: ⭐⭐ (2/5星)
- Service结构良好，改造量小
- 调用方少，集成简单
- Repository逻辑简单

### 5. Repository需求分析

#### BankService需要的Repository

**BankAccountRepository**:
- `get_by_player_id(player_id)` - 获取玩家银行账户
- `create(player_id, balance)` - 创建新账户
- `get_top_accounts_with_players(limit)` - 排行榜查询 (解决N+1)
- `update_balance(account, amount)` - 更新余额

**复杂度**: 🟡 中等 (需要处理关联查询和排行榜优化)

#### InviteRewardService需要的Repository

**InviteRewardRepository**:
- `create(invitee_uid, inviter_uid)` - 创建邀请记录
- `get_by_invitee_uid(invitee_uid)` - 查询被邀请记录
- `get_by_inviter_uid(inviter_uid)` - 查询邀请者记录列表
- `get_records_with_players(inviter_uid)` - 预加载Player信息 (解决N+1)
- `update_reward_status(record, level)` - 更新奖励发放状态

**复杂度**: 🟢 简单 (简单查询，无复杂业务逻辑)

**PlayerRepository** (已存在):
- 复用已有的PlayerRepository (`infrastructure/repositories/player_repository.py`)
- 可能需要扩展: `get_by_uids(uids: List[int])` - 批量查询

---

## 改造优先级建议

### 推荐顺序: 先改造 InviteRewardService

**理由**:

#### 1. 结构优势 ✅
- ✅ **已有Service类**: 无需从零提取业务逻辑
- ✅ **方法分离良好**: 5个独立方法，职责清晰
- ✅ **session管理规范**: 统一使用参数注入，无内部safe_session

#### 2. 改造成本低 ✅
- ✅ **代码量少**: 184行 vs 327行
- ✅ **调用方少**: 4处调用 vs 6个Command Handler
- ✅ **改造量小**: ~170行 vs ~450行

#### 3. 风险可控 ✅
- ✅ **影响范围小**: 仅邀请奖励功能，非核心系统
- ✅ **使用频率低**: 玩家升级时触发，测试容易
- ✅ **无循环依赖**: 独立Service，无Service间调用
- ✅ **回滚简单**: 改造失败影响范围小

#### 4. 学习价值高 ✅
- ✅ **标准Service改造模板**: @classmethod → 实例方法 + DI
- ✅ **Repository集成示例**: 简单查询逻辑，易理解
- ✅ **N+1查询优化示例**: `get_records_with_players` 预加载
- ✅ **可复用经验**: 为改造其他25个Service积累经验

#### 5. 技术对齐 ✅
- ✅ **符合重构路线**: `/guides/refactoring-roadmap.md` 阶段2任务
- ✅ **已有基础设施**: DI容器、UnitOfWork、PlayerRepository已完成
- ✅ **对齐目标架构**: `/architecture/target-architecture.md` Service实例化模式

---

## 改造行动计划

### 阶段1: InviteRewardService改造 (推荐 ✅)

**第1步: 创建InviteRewardRepository** (1天)
```python
# infrastructure/repositories/invite_reward_repository.py
class InviteRewardRepository(IRepository[InviteReward]):
    async def create(self, invitee_uid: int, inviter_uid: int) -> InviteReward:
        ...

    async def get_by_invitee_uid(self, uid: int) -> Optional[InviteReward]:
        ...

    async def get_by_inviter_uid(self, uid: int) -> List[InviteReward]:
        ...

    async def get_records_with_players(self, inviter_uid: int) -> List[Tuple[InviteReward, Player]]:
        # 解决N+1查询: 使用joinedload预加载Player
        stmt = (
            select(InviteReward)
            .options(joinedload(InviteReward.invitee))
            .where(InviteReward.inviter_uid == inviter_uid)
        )
        ...
```

**第2步: 改造InviteRewardService** (0.5天)
```python
# player/invite_reward_service.py
class InviteRewardService:
    def __init__(self, invite_repo: InviteRewardRepository, player_repo: PlayerRepository):
        self._invite_repo = invite_repo
        self._player_repo = player_repo

    async def create_invite_record(self, invitee_uid: int, inviter_uid: int) -> InviteReward:
        return await self._invite_repo.create(invitee_uid, inviter_uid)

    async def check_and_grant_level_rewards(self, player_id: str, new_level: int) -> List[str]:
        # 使用self._invite_repo和self._player_repo
        ...
```

**第3步: 注册到DI容器** (0.5天)
```python
# infrastructure/di/container.py
container.register_transient(InviteRewardRepository)
container.register_transient(InviteRewardService)
```

**第4步: 重构调用方** (1天)
- `player/invite.py` (3处调用)
- `social/level_hooks.py` (1处调用)

```python
# player/invite.py (重构后)
@bind_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    async with UnitOfWork(session_factory) as uow:
        invite_service = container.resolve(InviteRewardService, uow=uow)
        invite_record = await invite_service.create_invite_record(player.uid, inviter_uid)
        await uow.commit()
```

**第5步: 单元测试** (1天)
- 测试InviteRewardService的5个方法
- Mock InviteRewardRepository和PlayerRepository
- 验证奖励发放逻辑

**总计**: 4天

---

### 阶段2: BankService改造 (推迟到第二轮)

**原因**:
- ⚠️ 需要先从Command Handler提取业务逻辑
- ⚠️ 改造量大 (~450行)
- ⚠️ 影响6个Command Handler
- ⚠️ 需要学习InviteRewardService改造经验后再进行

**建议时机**: InviteRewardService改造完成并验证后

---

## 关键成功因素

### 改造InviteRewardService的成功条件

1. ✅ **DI容器已完成**: `infrastructure/di/container.py` (已完成)
2. ✅ **UnitOfWork已实现**: `infrastructure/uow/unit_of_work.py` (已完成)
3. ✅ **PlayerRepository已存在**: `infrastructure/repositories/player_repository.py` (已完成)
4. ✅ **Feature Flag机制**: 支持新旧Service切换
5. ✅ **测试覆盖**: 单元测试覆盖率>80%

### 风险控制措施

| 风险 | 缓解措施 |
|-----|---------|
| 改造破坏现有功能 | Feature Flag控制切换，回归测试 |
| N+1查询优化不彻底 | Repository预加载方法，性能测试 |
| DI容器集成失败 | 保留旧@classmethod，渐进式迁移 |
| 单元测试不足 | TDD开发，Mock框架验证 |

---

## 相关文档

- 重构进度: `/llmdoc/REFACTORING_PROGRESS.md`
- 重构路线: `/llmdoc/guides/refactoring-roadmap.md`
- Service类调研: `/llmdoc/agent/service_classes_investigation.md`
- 目标架构: `/llmdoc/architecture/target-architecture.md`
- DI容器实现: `plugins/xiuxian_game/infrastructure/di/container.py`

---

## 结论

### 核心结论

1. **InviteRewardService是更优的改造目标**:
   - 代码规模小 (184行 vs 327行)
   - 改造成本低 (~170行 vs ~450行)
   - 风险可控 (影响范围小，调用方少)
   - 学习价值高 (标准Service改造模板)

2. **BankService需推迟到第二轮**:
   - 需要先提取业务逻辑
   - 改造量大，风险高
   - 需要InviteRewardService改造经验支撑

3. **改造收益**:
   - ✅ 单元测试覆盖率: 0% → 80%
   - ✅ N+1查询优化: 循环查询 → joinedload预加载
   - ✅ 依赖注入: @classmethod → DI容器
   - ✅ 事务管理: 多会话 → 单UnitOfWork

### 推荐行动

**立即执行**: 改造InviteRewardService (预计4天)
**下一步**: 改造BankService或其他Service (预计6天)
**最终目标**: 26个Service全部改造为DI模式
