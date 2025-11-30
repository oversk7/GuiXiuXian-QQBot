# 账号切换系统使用指南

## 概述

账号切换系统允许一个真实玩家（platform_id）拥有多个游戏账号（Player），并支持账号切换和私下交易功能。

## 核心概念

- **真实玩家**: 通过platform_id标识（QQ号、频道ID等）
- **游戏账号**: Player实体，一个游戏角色
- **账号所有权**: AccountOwnership记录，表示谁拥有哪个游戏账号
- **激活状态**: 同一时间只能有一个账号处于激活状态
- **转让密钥**: 6位数字密钥，用于账号私下交易

## 部署步骤

### 1. 环境准备

确保已安装所需依赖：
```bash
pip install aiomysql pymysql sqlalchemy alembic
```

### 2. 运行数据迁移

#### 方式1: 使用Alembic（推荐）

```bash
cd plugins/xiuxian_game
alembic upgrade head
```

#### 方式2: 使用手动迁移脚本

如果Alembic环境有问题，可以使用手动迁移脚本：
```bash
cd plugins/xiuxian_game
python migrate_account_ownership.py
```

### 3. 验证部署

迁移成功后，数据库会新增两个表：
- `account_ownership` - 账号所有权表
- `account_transfer_logs` - 转让历史表

所有现有玩家会自动创建所有权记录，`display_name`为"主号"，`is_active`为TRUE。

### 4. 启动机器人

重启机器人后，账号切换功能会自动加载。

## 用户命令

### 1. 查看账号列表

```
我的账号
```
或
```
账号列表
```

**功能**: 查看当前拥有的所有游戏账号

**返回信息**:
- 账号激活状态
- 账号备注名
- 角色名和境界
- 等级
- 账号ID
- 获得方式

**示例输出**:
```
👤 我的游戏账号
━━━━━━━━━━
✅ 激活中 主号
   角色名: 张三 | 金丹期
   等级: Lv.50
   账号ID: user_123_main
   获得方式: created
━━━━━━━━━━
⚪ 未激活 小号
   角色名: 李四 | 筑基期
   等级: Lv.30
   账号ID: user_123_alt
   获得方式: transferred
━━━━━━━━━━
共 2 个账号

💡 提示: 使用「切换账号 账号ID」切换账号
```

### 2. 切换账号

```
切换账号 <账号ID>
```

**功能**: 切换到指定的游戏账号

**参数**:
- `<账号ID>`: 要切换到的账号ID（可从"我的账号"命令中查看）

**限制**:
- 只能切换到自己拥有的账号
- 账号必须存在

**示例**:
```
切换账号 user_123_alt
```

**成功返回**:
```
✅ 切换成功
```

### 3. 重命名账号

```
重命名账号 <账号ID> <新名称>
```

**功能**: 为账号设置备注名（方便识别）

**参数**:
- `<账号ID>`: 要重命名的账号ID
- `<新名称>`: 新的备注名称（最长32字符）

**限制**:
- 只能重命名自己拥有的账号
- 备注名最长32字符

**示例**:
```
重命名账号 user_123_alt 打金小号
```

**成功返回**:
```
✅ 重命名成功
```

### 4. 生成转让密钥

```
生成转让密钥 <账号ID>
```
或
```
转让账号 <账号ID>
```

**功能**: 生成账号转让密钥，用于账号交易

**参数**:
- `<账号ID>`: 要转让的账号ID

**限制**:
- 只能转让自己拥有的账号
- 不能转让当前激活的账号（需先切换到其他账号）

**安全提示**:
- 任何获得密钥的人都可以接收此账号
- 转让后无法撤回
- 请确保在安全的环境下进行交易

**示例**:
```
生成转让密钥 user_123_alt
```

**成功返回**:
```
🔑 转让密钥生成成功
━━━━━━━━━━
账号ID: user_123_alt
转让密钥: 123456
━━━━━━━━━━
⚠️ 请妥善保管此密钥
⚠️ 任何获得密钥的人都可以接收此账号
⚠️ 转让后无法撤回

💡 提示: 使用「取消转让 账号ID」取消转让
```

### 5. 接收账号

```
接收账号 <转让密钥>
```
或
```
使用转让密钥 <转让密钥>
```

**功能**: 使用转让密钥接收账号

**参数**:
- `<转让密钥>`: 6位数字转让密钥

**限制**:
- 不能接收自己的账号
- 密钥必须有效
- 密钥只能使用一次

**示例**:
```
接收账号 123456
```

**成功返回**:
```
🎉 账号接收成功
━━━━━━━━━━
成功接收账号 user_123_alt
━━━━━━━━━━
💡 提示: 使用「我的账号」查看所有账号
💡 提示: 使用「切换账号 账号ID」激活新账号
```

### 6. 取消转让

```
取消转让 <账号ID>
```

**功能**: 取消之前生成的转让密钥

**参数**:
- `<账号ID>`: 要取消转让的账号ID

**限制**:
- 只能取消自己账号的转让密钥
- 账号必须已生成转让密钥

**示例**:
```
取消转让 user_123_alt
```

**成功返回**:
```
✅ 已取消转让密钥
```

### 7. 查看转让历史

```
转让历史
```
或
```
账号交易历史
```

**功能**: 查看账号买入/卖出历史（最近10条）

**返回信息**:
- 买入/接收记录
- 卖出/转让记录
- 转让类型（买卖/赠送/管理员操作）
- 转让时间

**示例输出**:
```
📊 账号转让历史
━━━━━━━━━━
🛒 买入/接收:
  买入 账号 user_456_main
  来自: platform_789
  时间: 2025-11-30 10:00
━━━━━━━━━━
💰 卖出/转让:
  卖出 账号 user_123_alt
  给: platform_999
  时间: 2025-11-29 15:30
```

## 使用场景

### 场景1: 创建小号

1. 使用另一个平台ID创建新角色
2. 生成转让密钥
3. 使用主号接收小号

### 场景2: 账号交易

**卖家操作**:
1. 确保不是当前激活账号（如果是，先切换到其他账号）
2. 生成转让密钥: `生成转让密钥 <账号ID>`
3. 将密钥私下发送给买家
4. 收到付款后，等待买家接收

**买家操作**:
1. 确认交易安全
2. 完成付款
3. 接收账号: `接收账号 <转让密钥>`
4. 激活账号: `切换账号 <账号ID>`

### 场景3: 多账号管理

1. 查看所有账号: `我的账号`
2. 重命名账号便于识别: `重命名账号 <ID> 打金号`
3. 随时切换: `切换账号 <ID>`

## 技术架构

### 数据模型

#### AccountOwnership表
- `owner_platform_id`: 拥有者的平台ID（真实玩家）
- `player_id`: 游戏账号ID（外键到players表）
- `is_active`: 是否激活
- `display_name`: 账号备注名
- `transfer_key`: 转让密钥
- `acquired_type`: 获得方式（created/transferred/purchased/gift）

#### AccountTransferLog表
- `player_id`: 被转让的账号ID
- `from_platform_id`: 原拥有者
- `to_platform_id`: 新拥有者
- `transfer_type`: 转让类型（sale/gift/admin）
- `transfer_time`: 转让时间
- `transfer_key_used`: 使用的转让密钥

### 业务规则

1. **唯一性约束**: 每个Player只能有一个拥有者
2. **激活约束**: 同一拥有者只能有一个激活账号
3. **转让保护**: 不能转让当前激活的账号
4. **自我转让防护**: 不能将账号转让给自己
5. **密钥单次使用**: 转让密钥使用后自动清除
6. **审计日志**: 所有转让操作都有完整记录

### 安全特性

1. **所有权验证**: 每个操作都会验证用户权限
2. **密钥加密**: 使用secrets模块生成安全随机密钥
3. **完整审计**: 所有转让记录永久保存
4. **防止欺诈**: 转让历史可追溯

## 管理员功能

管理员可以使用Service层的`admin_force_transfer`方法强制转让账号：

```python
from plugins.xiuxian_game.social.account_switching_service import AccountSwitchingService
from plugins.xiuxian_game.infrastructure.repositories.account_ownership_repository import AccountOwnershipRepository
from plugins.xiuxian_game.infrastructure.repositories.account_transfer_log_repository import AccountTransferLogRepository
from plugins.xiuxian_game.infrastructure.repositories.player_repository import PlayerRepository

async with safe_session() as session:
    service = AccountSwitchingService(
        ownership_repo=AccountOwnershipRepository(session),
        transfer_log_repo=AccountTransferLogRepository(session),
        player_repo=PlayerRepository(session)
    )

    success, message = await service.admin_force_transfer(
        player_id="problematic_account",
        to_platform_id="new_owner",
        notes="管理员介入处理纠纷"
    )

    if success:
        await session.commit()
```

## 故障排除

### 问题1: 命令无响应

**可能原因**: 机器人未重启
**解决方法**: 重启机器人，确保新命令被加载

### 问题2: 提示账号不存在

**可能原因**: 账号ID错误
**解决方法**: 使用"我的账号"命令查看正确的账号ID

### 问题3: 无法切换账号

**可能原因**: 账号不属于当前用户
**解决方法**: 确认账号所有权，只能切换自己的账号

### 问题4: 生成转让密钥失败

**可能原因**: 尝试转让激活的账号
**解决方法**: 先切换到其他账号，再生成转让密钥

### 问题5: 转让密钥无效

**可能原因**:
- 密钥已被使用
- 密钥已被取消
- 密钥输入错误

**解决方法**: 联系卖家确认密钥状态

## 开发者文档

### 添加新的账号相关功能

1. 在`AccountSwitchingService`中添加新方法
2. 在`account_switching.py`中添加命令处理器
3. 更新本文档

### 扩展转让类型

在`AccountTransferLog.transfer_type`字段中添加新类型，并更新Service逻辑。

### 自定义验证规则

在`AccountSwitchingService`的方法中添加自定义验证逻辑。

## 更新日志

### v1.0.0 (2025-11-30)
- ✅ 初始版本发布
- ✅ 支持多账号管理
- ✅ 支持账号切换
- ✅ 支持账号转让
- ✅ 完整的审计日志
- ✅ 7个用户命令
- ✅ 完整的权限验证

## 联系支持

如有问题或建议，请提交Issue或联系开发团队。
