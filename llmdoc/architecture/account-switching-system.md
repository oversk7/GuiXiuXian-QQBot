# 账号切换系统架构

## 1. Identity

- **What it is:** 允许玩家拥有多个游戏账号并在它们之间切换的系统，支持账号转让和管理员临时切换调试功能。
- **Purpose:** 实现多账号管理、账号交易、管理员调试等功能，将真实玩家（platform_id）与游戏账号（Player）解耦。

## 2. Core Components

- `plugins/xiuxian_game/models/account_ownership.py` (AccountOwnership): 账号所有权模型，记录玩家拥有哪些游戏账号，支持账号激活状态、转让密钥、获得方式等属性。
- `plugins/xiuxian_game/social/account_switching_service.py` (AccountSwitchingService): 账号切换核心业务逻辑，包含账号管理（列表/切换/重命名）、账号转让（生成密钥/接收/取消）、历史查询等功能。
- `plugins/xiuxian_game/social/account_switching.py`: 命令处理器，处理9个账号相关命令（6个玩家命令+3个管理员命令）。
- `plugins/xiuxian_game/platform_utils.py` (get_unified_player, admin_temp_switch_*): 统一玩家数据访问接口，支持账号切换和管理员临时切换的优先级判断。
- `plugins/xiuxian_game/infrastructure/repositories/account_ownership_repository.py` (AccountOwnershipRepository): 账号所有权数据仓储，提供查询激活账号、拥有者账号列表等方法。
- `plugins/xiuxian_game/infrastructure/repositories/account_transfer_log_repository.py` (AccountTransferLogRepository): 账号转让历史仓储，记录所有转让操作的审计日志。

## 3. Execution Flow (LLM Retrieval Map)

### 3.1 玩家查看账号列表

- **1. 命令触发**: `plugins/xiuxian_game/social/account_switching.py:40-76` 处理"我的账号"命令。
- **2. 服务调用**: 调用 `AccountSwitchingService.list_owned_accounts()` (`plugins/xiuxian_game/social/account_switching_service.py:50-84`)。
- **3. 数据查询**: `AccountOwnershipRepository.find_all_by_owner()` 查询所有拥有的账号，使用 `joinedload(player)` 预加载玩家数据避免N+1查询。
- **4. 结果返回**: 返回包含账号ID、UID、昵称、等级、激活状态、获得方式等信息的列表。

### 3.2 玩家切换账号

- **1. 命令触发**: `plugins/xiuxian_game/social/account_switching.py:80-118` 处理"切换账号"命令，接收UID参数。
- **2. UID转Player ID**: 通过 `PlayerRepository.get_by_uid()` 将UID转换为player_id。
- **3. 切换操作**: 调用 `AccountSwitchingService.switch_account()` (`plugins/xiuxian_game/social/account_switching_service.py:86-116`)。
- **4. 状态更新**:
  - 将所有账号的 `is_active` 设置为 False
  - 将目标账号的 `is_active` 设置为 True
  - 提交数据库事务
- **5. 后续影响**: 下次调用 `get_unified_player()` 时会返回新激活的账号。

### 3.3 账号转让流程

**生成转让密钥（卖方/赠与方）**:
- **1. 命令触发**: `plugins/xiuxian_game/social/account_switching.py:168-212` 处理"生成转让密钥"命令（管理员权限）。
- **2. 权限检查**: `AccountSwitchingService.generate_transfer_key()` 检查 `is_admin` 参数，管理员可跳过所有权验证 (`plugins/xiuxian_game/social/account_switching_service.py:180-212`)。
- **3. 密钥生成**: 使用 `AccountOwnership.generate_transfer_key()` 生成6位数字密钥，存储到 `transfer_key` 字段。
- **4. 返回密钥**: 返回密钥供卖方私下交易使用。

**接收账号（买方/受赠方）**:
- **1. 命令触发**: `plugins/xiuxian_game/social/account_switching.py:215-254` 处理"接收账号"命令（管理员权限）。
- **2. 密钥验证**: `AccountSwitchingService.accept_transfer()` 查询 `transfer_key` 是否存在且有效。
- **3. 所有权转移**:
  - 更新 `owner_platform_id` 为新拥有者
  - 清除 `transfer_key` 和 `transfer_key_created_at`
  - 设置 `acquired_type` 为 "transferred"
  - 记录转让日志到 `account_transfer_log` 表
- **4. 事务提交**: 原子性完成所有权转移。

### 3.4 管理员临时切换（2025-12-01新增）

**临时切换到账号**:
- **1. 命令触发**: `plugins/xiuxian_game/social/account_switching.py:358-397` 处理"临时切换"命令（仅SUPERUSER）。
- **2. 账号验证**: 通过 `PlayerRepository.get_by_uid()` 验证目标UID是否存在。
- **3. 内存记录**: 调用 `admin_temp_switch_to()` 将临时切换状态记录到内存字典 `_admin_temp_switch` (`plugins/xiuxian_game/platform_utils.py:104-112`)。
- **4. 后续影响**: `get_unified_player()` 优先检查临时切换状态，返回临时切换的目标账号 (`plugins/xiuxian_game/platform_utils.py:84-89`)。

**退出临时切换**:
- **1. 命令触发**: `plugins/xiuxian_game/social/account_switching.py:401-432` 处理"退出临时切换"命令。
- **2. 状态清除**: 调用 `admin_exit_temp_switch()` 从内存字典中删除临时切换记录 (`plugins/xiuxian_game/platform_utils.py:115-128`)。
- **3. 恢复账号**: 下次调用 `get_unified_player()` 时按正常优先级（账号切换 > 默认账号）返回玩家数据。

### 3.5 统一玩家数据访问

- **核心入口**: `get_unified_player()` (`plugins/xiuxian_game/platform_utils.py:66-99`) 是所有玩家数据访问的统一入口。
- **优先级判断**:
  1. **最高优先级**: 检查 `_admin_temp_switch` 字典，如果管理员正在临时切换，返回临时切换的账号。
  2. **中优先级**: 调用 `PlayerRepository.get_active_by_platform_id()` 查询 `is_active=True` 的账号。
  3. **默认优先级**: 如果未使用账号切换系统，直接查询 `Player` 表 (`player_id == platform_id`)。
- **一致性保证**: 所有游戏命令使用此统一入口，确保账号切换和临时切换在所有功能中生效。

## 4. Design Rationale

### 4.1 数据模型设计

**AccountOwnership模型** (`plugins/xiuxian_game/models/account_ownership.py`):
- **一对多关系**: 一个 `owner_platform_id` 可拥有多个 `player_id`，但每个 `player_id` 只能有一个拥有者（UniqueConstraint）。
- **激活状态**: `is_active` 字段标识当前激活的账号，同一拥有者同一时间只能有一个激活账号。
- **转让密钥**: `transfer_key` 字段存储6位数字密钥，永久有效直到使用，支持账号私下交易。
- **审计信息**: `acquired_type`, `acquired_at` 记录账号来源，支持追溯账号历史。

### 4.2 管理员权限增强（2025-12-01修复）

**问题**: 原 `generate_transfer_key()` 方法只允许账号拥有者生成转让密钥，管理员无法为其他玩家的账号生成密钥。

**解决方案** (`plugins/xiuxian_game/social/account_switching_service.py:180-212`):
- 添加 `is_admin` 参数，管理员调用时跳过所有权验证（line 203）。
- 命令处理器 `generate_transfer_key_cmd` 设置 `permission=SUPERUSER`，确保只有管理员可调用。
- 设计原则：通过参数控制权限检查，而非修改底层逻辑，保持代码清晰。

### 4.3 临时切换设计（2025-12-01新增）

**核心特点**:
- **内存存储**: 使用模块级字典 `_admin_temp_switch` 存储临时切换状态，重启后自动清除，避免遗留状态（`plugins/xiuxian_game/platform_utils.py:12-14`）。
- **所有权不变**: 临时切换不修改 `AccountOwnership` 表，账号所有权和激活状态保持不变。
- **优先级最高**: `get_unified_player()` 优先检查临时切换状态，确保管理员可以调试任何账号。
- **安全性**: 仅SUPERUSER可使用，通过 `permission=SUPERUSER` 限制命令权限。

**使用场景**:
- 管理员调试玩家反馈的bug，需要以玩家视角操作游戏。
- 管理员测试某个账号的特定状态（如高等级账号测试副本平衡性）。
- 临时操作后退出，不改变账号归属，避免污染数据。

### 4.4 N+1查询优化

**优化点** (`plugins/xiuxian_game/social/account_switching_service.py:72`):
- 使用 `joinedload(AccountOwnership.player)` 预加载玩家数据，避免循环中逐个查询Player。
- 单次SQL查询获取所有账号及关联的Player数据，显著提升性能。

### 4.5 事务一致性

**转让操作**: `accept_transfer()` 方法包含多个数据库写操作（更新所有权、清除密钥、记录日志），依赖外部事务管理（命令处理器中的 `safe_session()` 和 `session.commit()`），确保原子性。

