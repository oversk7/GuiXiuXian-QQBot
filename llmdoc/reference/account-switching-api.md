# 账号切换系统API参考

## 1. Core Summary

本文档提供账号切换系统的API概览，包括数据模型、服务方法、命令处理器、辅助函数等核心接口。详细实现请参考源代码文件。

## 2. Source of Truth

### 2.1 数据模型

- **AccountOwnership**: `plugins/xiuxian_game/models/account_ownership.py` - 账号所有权模型，记录玩家拥有哪些游戏账号。
  - 字段：`id`, `owner_platform_id`, `player_id`, `is_active`, `display_name`, `transfer_key`, `transfer_key_created_at`, `acquired_at`, `acquired_type`
  - 约束：`player_id` 唯一（每个账号只能有一个拥有者）
  - 索引：`owner_platform_id` + `is_active` 复合索引，快速查找激活账号

- **AccountTransferLog**: `plugins/xiuxian_game/models/account_transfer_log.py` - 账号转让历史日志。
  - 字段：`id`, `player_id`, `from_platform_id`, `to_platform_id`, `transfer_key`, `transferred_at`

### 2.2 核心服务

- **AccountSwitchingService**: `plugins/xiuxian_game/social/account_switching_service.py` - 账号切换核心业务逻辑。
  - 方法列表：
    - `list_owned_accounts(owner_platform_id: str)` - 查询拥有的所有账号
    - `switch_account(owner_platform_id: str, player_id: str)` - 切换到指定账号
    - `rename_account(owner_platform_id: str, player_id: str, display_name: str)` - 重命名账号备注
    - `generate_transfer_key(owner_platform_id: str, player_id: str, is_admin: bool = False)` - 生成转让密钥（支持管理员权限）
    - `accept_transfer(recipient_platform_id: str, transfer_key: str)` - 接收账号转让
    - `cancel_transfer(owner_platform_id: str, player_id: str)` - 取消转让密钥
    - `get_transfer_history(platform_id: str)` - 查询转让历史

### 2.3 数据仓储

- **AccountOwnershipRepository**: `plugins/xiuxian_game/infrastructure/repositories/account_ownership_repository.py` - 账号所有权仓储。
  - 关键方法：
    - `find_by_player_id(player_id: str)` - 根据player_id查询所有权记录
    - `find_all_by_owner(owner_platform_id: str)` - 查询某人拥有的所有账号（使用joinedload预加载player）
    - `find_active_by_owner(owner_platform_id: str)` - 查询当前激活的账号
    - `find_by_transfer_key(transfer_key: str)` - 根据转让密钥查询账号

- **AccountTransferLogRepository**: `plugins/xiuxian_game/infrastructure/repositories/account_transfer_log_repository.py` - 转让历史仓储。
  - 关键方法：
    - `find_history_by_platform_id(platform_id: str, limit: int = 50)` - 查询某人的转让历史

### 2.4 命令处理器

- **玩家命令**: `plugins/xiuxian_game/social/account_switching.py`
  - `我的账号` / `账号列表` (line 40-76) - 查看拥有的所有游戏账号
  - `切换账号 <UID>` (line 80-118) - 切换到指定账号
  - `重命名账号 <UID> <新名称>` (line 121-164) - 重命名账号备注
  - `转让历史` (line 327-354) - 查看账号买入/卖出历史

- **管理员命令** (`permission=SUPERUSER`): `plugins/xiuxian_game/social/account_switching.py`
  - `生成转让密钥 <UID>` / `转让账号 <UID>` (line 168-212) - 为任意账号生成转让密钥
  - `接收账号 <转让密钥>` (line 215-254) - 使用密钥接收账号
  - `取消转让 <UID>` (line 257-324) - 取消账号的转让密钥
  - `临时切换 <UID>` (line 358-397) - 管理员临时切换到指定账号（不改变所有权）
  - `退出临时切换` (line 401-432) - 退出临时切换状态
  - `临时切换状态` (line 436-467) - 查看当前临时切换状态

### 2.5 统一玩家访问接口

- **get_unified_player**: `plugins/xiuxian_game/platform_utils.py:66-99` - 统一的玩家数据访问入口，按优先级返回玩家对象。
  - 优先级：临时切换（管理员）> 账号切换（is_active）> 默认账号（player_id == platform_id）
  - 所有游戏命令应使用此接口获取玩家数据，而非直接查询Player表

### 2.6 管理员临时切换辅助函数

- **临时切换管理**: `plugins/xiuxian_game/platform_utils.py:12-154`
  - `admin_temp_switch_to(admin_platform_id: str, target_player_id: str)` (line 104-112) - 记录临时切换状态
  - `admin_exit_temp_switch(admin_platform_id: str) -> bool` (line 115-128) - 退出临时切换
  - `is_admin_temp_switching(admin_platform_id: str) -> bool` (line 131-141) - 检查是否在临时切换状态
  - `get_admin_temp_switch_target(admin_platform_id: str) -> Optional[str]` (line 144-154) - 获取临时切换目标账号ID

## 3. Key API Changes (2025-12-01)

### 3.1 管理员权限增强 - 生成转让密钥

**变更**: `AccountSwitchingService.generate_transfer_key()` 添加 `is_admin` 参数，管理员可跳过所有权验证（`plugins/xiuxian_game/social/account_switching_service.py:202-204`）。命令设置 `permission=SUPERUSER` 确保安全性。

### 3.2 新增管理员临时切换功能

**功能描述**: 管理员可以临时切换到任何账号进行调试，不改变账号所有权。

**核心设计**:
- **内存存储**: 使用模块级字典 `_admin_temp_switch` 存储状态，重启后自动清除
- **优先级最高**: `get_unified_player()` 优先检查临时切换状态
- **所有权不变**: 不修改 `AccountOwnership` 表，账号归属和激活状态保持不变

**新增API**:
1. `admin_temp_switch_to()` - 记录临时切换状态到内存
2. `admin_exit_temp_switch()` - 清除临时切换状态
3. `is_admin_temp_switching()` - 检查是否在临时切换状态
4. `get_admin_temp_switch_target()` - 获取临时切换目标账号

**新增命令**: `临时切换 <UID>`, `退出临时切换`, `临时切换状态`（均为SUPERUSER权限）

**安全性**: 内存存储，重启自动清除；不修改数据库，账号所有权保持不变。

## 4. Related Architecture

- `/llmdoc/architecture/account-switching-system.md` - 账号切换系统完整架构文档
- `/llmdoc/architecture/service-di-architecture.md` - Service DI架构（AccountSwitchingService遵循此架构）
- `/llmdoc/reference/data-models.md` - 完整数据模型参考

## 5. Usage Notes

### 5.1 玩家命令使用注意事项

- **账号ID vs UID**: 所有命令使用UID（用户友好的数字ID），内部通过 `PlayerRepository.get_by_uid()` 转换为player_id。
- **UID转换**: UID必须是整数，非数字输入会被拒绝。
- **账号激活**: 切换账号后，新账号的 `is_active` 设置为True，旧账号设置为False。
- **首次使用**: 未使用账号切换系统的玩家，`get_unified_player()` 会回退到直接查询Player表。

### 5.2 管理员命令使用注意事项

- 所有管理员命令使用 `permission=SUPERUSER` 权限限制
- 临时切换优先级最高，覆盖账号切换状态
- 临时切换状态存储在内存，重启后自动清除
- 转让操作需在事务中执行，确保原子性

### 5.3 开发者集成指南

**统一玩家访问**: 所有游戏命令应使用 `get_unified_player(session, event)` 获取玩家对象。

**服务创建**: 使用AccountSwitchingService需注入AccountOwnershipRepository、AccountTransferLogRepository、PlayerRepository三个仓储。

