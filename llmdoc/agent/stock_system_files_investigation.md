# 诡修仙投资系统（股票/气运系统）文件清单

**调查日期**: 2025-12-02
**调查类型**: 代码文件定位
**调查目标**: 查找投资系统所有相关文件的完整路径

---

## Code Sections (The Evidence)

### 数据模型文件

- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\models\stock.py` (Stock/StockHolding/StockTransaction/StockPriceHistory): 股票系统的4个核心数据模型，包括股票基本信息、玩家持仓、交易记录和价格历史
- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\models\market_state.py`: 市场状态相关模型（与股票系统间接相关）
- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\models\bank_account.py`: 银行账户模型（股票交易可使用银行资金）

### 核心业务逻辑文件

- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\economy\stock_price_engine.py` (StockPriceEngine/StockMarketScheduler): 价格波动引擎，实现随机波动、市场情绪、价格回归等算法
- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\economy\stock_service_new.py` (StockService): DI架构的股票交易服务，包含买入、卖出、持仓管理等核心逻辑
- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\economy\stock_service_legacy.py`: 旧版股票服务（静态方法模式，保留用于参考）
- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\economy\stock_service_di_example.py`: DI架构示例文件

### Repository层文件

- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\infrastructure\repositories\stock_repository.py` (StockRepository): 股票数据访问仓储，包含批量查询优化
- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\infrastructure\repositories\stock_holding_repository.py` (StockHoldingRepository): 持仓数据访问仓储，解决N+1查询问题
- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\infrastructure\repositories\stock_transaction_repository.py` (StockTransactionRepository): 交易记录数据访问仓储
- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\infrastructure\repositories\bank_account_repository.py`: 银行账户仓储（股票交易使用）

### 命令处理文件

- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\economy\stock_commands.py`: 股票交易命令处理器，包含9个用户命令（气运行情、投资气运、出售气运、我的投资等）
- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\economy\__init__.py`: 经济系统模块初始化，注册股票相关命令

### 定时任务文件

- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\economy\stock_scheduler.py`: 股票价格更新定时任务调度器，配置12小时备用更新和每日9点更新

### 配置文件

- 注意：项目**不存在** `stocks.yaml` 配置文件
- 股票初始化数据硬编码在 `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\economy\stock_commands.py:397-432` (handle_stock_init函数)
- 手续费、波动率等参数定义在 `stock_service_new.py` 和 `stock_price_engine.py` 中

### 数据库迁移文件

- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\alembic\versions\b72c26056770_initial_baseline.py`: 基线迁移文件（不含股票表）
- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\alembic\versions\316ae6f6d779_check_for_changes.py`: 检查变更迁移
- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\alembic\versions\add_account_ownership_tables.py`: 账号所有权表迁移
- 注意：**不存在**专门的股票表迁移文件，股票表通过ORM模型自动创建

### 文档文件

- `D:\QQbot\GuiXiuXian2\llmdoc\agent\investment_system_investigation.md`: 投资系统详细调查报告（包含银行、股票、打工系统的平衡性分析）
- `D:\QQbot\GuiXiuXian2\llmdoc\design\investment_system_redesign_2025_12_02.md`: 投资系统重设计方案
- `D:\QQbot\GuiXiuXian2\llmdoc\design\investment_anti_arbitrage_redesign.md`: 反套利机制重设计方案

### 其他相关文件

- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\economy\bank.py`: 银行系统（与股票交易资金来源相关）
- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\economy\merchants.py`: 商人系统（经济系统其他组成部分）
- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\player\help.py`: 帮助文档（包含股票相关帮助信息）
- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\player\rankings.py`: 排行榜系统（可能包含股票投资排行）
- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\infrastructure\uow\unit_of_work.py`: UnitOfWork模式实现（股票Service使用）
- `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\ai_guide.py`: AI引导系统（可能包含股票投资指导）

---

## Report (The Answers)

### result

诡修仙项目的投资系统（股票/气运系统）包含以下主要文件：

#### 1. 数据模型（3个核心文件）

- **Stock模型定义**: `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\models\stock.py`
  - 包含4个数据模型：Stock（股票基本信息）、StockHolding（玩家持仓）、StockTransaction（交易记录）、StockPriceHistory（价格历史）
  - 2个枚举类型：StockType（6种股票类型）、TransactionType（买入/卖出）

#### 2. 核心逻辑（3个主要文件）

- **价格计算引擎**: `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\economy\stock_price_engine.py`
  - StockPriceEngine：价格波动算法（随机因子+趋势因子+市场情绪+回归因子）
  - StockMarketScheduler：市场更新调度器

- **Service层（DI架构）**: `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\economy\stock_service_new.py`
  - StockService：股票交易核心服务（买入、卖出、持仓管理、交易记录）
  - 依赖注入5个Repository：PlayerRepository、StockRepository、StockHoldingRepository、StockTransactionRepository、BankAccountRepository

- **Service层（旧版）**: `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\economy\stock_service_legacy.py`
  - 静态方法模式，保留用于参考和回退

#### 3. Repository层（3个核心文件）

- **股票仓储**: `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\infrastructure\repositories\stock_repository.py`
- **持仓仓储**: `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\infrastructure\repositories\stock_holding_repository.py`
- **交易记录仓储**: `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\infrastructure\repositories\stock_transaction_repository.py`

#### 4. 命令处理（1个文件）

- **指令处理器**: `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\economy\stock_commands.py`
  - 9个用户命令：气运行情、投资气运、出售气运、我的投资、投资记录、气运刷新时间、气运历史、气运分析、初始化气运、更新气运价格

#### 5. 定时任务（1个文件）

- **调度器**: `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\economy\stock_scheduler.py`
  - 12小时备用价格更新
  - 每日9点市场更新

#### 6. 配置文件

- **不存在** `stocks.yaml` 配置文件
- 股票初始化数据硬编码在 `stock_commands.py:397-432` 函数中
- 包含12个预定义股票项目（法宝气运、金融气运、灵气气运、丹药气运、医道气运、材料气运）

#### 7. 数据库迁移

- **不存在**专门的股票表迁移文件
- 股票相关的4个数据表（stocks、stock_holdings、stock_transactions、stock_price_history）通过SQLAlchemy ORM模型自动创建
- Alembic迁移文件位于 `D:\QQbot\GuiXiuXian2\plugins\xiuxian_game\alembic\versions\`

---

### conclusions

1. **投资系统采用DI架构**：stock_service_new.py使用依赖注入模式，实现了Service-Repository分层
2. **价格波动算法完善**：stock_price_engine.py实现了包含随机因子、趋势因子、市场情绪和回归因子的复杂价格计算
3. **数据访问层优化**：Repository层通过selectinload预加载关联对象，解决N+1查询问题
4. **命令处理集中**：stock_commands.py包含所有用户交互命令（9个命令）
5. **定时任务被动触发**：股票价格更新采用被动触发机制（玩家查看时触发），定时任务作为备用（12小时间隔）
6. **无配置文件设计**：股票数据硬编码在代码中，初始化通过管理员命令触发
7. **数据模型完整**：4个数据模型覆盖股票基本信息、持仓、交易记录和价格历史
8. **旧版代码保留**：stock_service_legacy.py保留作为回退和参考
9. **银行系统集成**：股票交易支持使用银行账户资金（通过BankAccountRepository）
10. **UnitOfWork事务管理**：Service层通过UnitOfWork模式管理事务边界

---

### relations

#### 数据模型关系

```
Stock (股票基本信息)
    ↓ 一对多
StockHolding (玩家持仓)
    ↓ 多对一
Player (玩家)

Stock
    ↓ 一对多
StockTransaction (交易记录)
    ↓ 多对一
Player

Stock
    ↓ 一对多
StockPriceHistory (价格历史)
```

#### Service层依赖关系

```
stock_commands.py (命令处理器)
    ↓ 调用
StockService (stock_service_new.py)
    ↓ 使用
UnitOfWork (infrastructure/uow/unit_of_work.py)
    ↓ 提供
StockRepository
StockHoldingRepository
StockTransactionRepository
BankAccountRepository
PlayerRepository
    ↓ 操作
Stock/StockHolding/StockTransaction模型
```

#### 价格更新流程关系

```
stock_scheduler.py (定时任务)
    ↓ 调用
StockMarketScheduler.hourly_market_update()
    ↓ 调用
StockPriceEngine.update_all_prices()
    ↓ 读取
Stock模型
    ↓ 计算新价格
StockPriceEngine._calculate_new_price()
    ↓ 写入
Stock.current_price (更新价格)
StockPriceHistory (记录历史)
```

#### 交易流程关系

```
stock_commands.py (投资气运/出售气运命令)
    ↓ 调用
StockService.buy_stock() / sell_stock()
    ↓ 查询
StockRepository.get_by_symbol()
StockHoldingRepository.get_by_player_and_stock()
    ↓ 验证
资金检查（PlayerRepository或BankAccountRepository）
持仓限制检查（MAX_SHARES_PER_STOCK）
    ↓ 更新
StockHolding (更新持仓)
Player.gold 或 BankAccount (更新资金)
    ↓ 记录
StockTransactionRepository.create_transaction()
```

#### 架构集成关系

```
infrastructure/uow/unit_of_work.py (UnitOfWork模式)
    ↓ 管理事务
AsyncSession (SQLAlchemy异步会话)
    ↓ 注入到
各Repository (StockRepository等)
    ↓ 提供给
StockService (stock_service_new.py)
    ↓ 被调用
stock_commands.py (命令处理器)
    ↓ 响应
用户QQ消息
```

---

**调查者**: Scout Agent
**调查日期**: 2025-12-02
**报告版本**: 1.0
