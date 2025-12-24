# 留言板黑名单功能调研报告

**调研日期**: 2025-12-24
**调研目标**: 为留言板系统添加黑名单功能的技术准备
**调研范围**: 管理员权限、等级系统、黑名单机制、数据库迁移、留言板实现

---

### Code Sections (The Evidence)

#### 1. 管理员权限检查机制

- `plugins/xiuxian_game/ai_guide.py` (`is_admin()` 函数): 20-24行，统一的管理员权限检查函数，从config读取admin_ids列表
- `plugins/xiuxian_game/data/config.yaml` (`admin` 配置节): 86-90行，管理员配置，包含admin_ids和sub_admin_ids两个列表
- `plugins/xiuxian_game/dialogue/admin_commands.py` (使用示例): 9行导入is_admin，22/76/112/161/268行使用权限检查
- `plugins/xiuxian_game/admin/lottery_commands.py` (复合权限检查): 21-35行，定义is_admin和is_authorized函数（admin或sub_admin）

#### 2. 玩家等级系统

- `plugins/xiuxian_game/models/player.py` (`level` 字段): 18行，Integer类型，默认值1，comment="等级"
- `plugins/xiuxian_game/data/config.yaml` (`max_level` 配置): 3行，最大等级300
- `plugins/xiuxian_game/admin/lottery_commands.py` (等级检查示例): 252-263行，抽奖系统的等级范围检查（min_level, max_level）

#### 3. 现有黑名单机制

- **结论**: 项目中**不存在**任何黑名单相关的数据表或代码
- 搜索关键词 "ban", "block", "blacklist", "deleted", "is_deleted", "soft_delete" 均无相关结果
- 唯一相关的是留言板的**违禁词过滤**机制（非黑名单）

#### 4. 留言板违禁词过滤机制（现有功能）

- `plugins/xiuxian_game/world/message_board.py` (`BANNED_WORDS` 列表): 19-28行，定义28个违禁词
- `plugins/xiuxian_game/world/message_board.py` (`filter_banned_words()` 函数): 49-61行，将违禁词替换为*号

#### 5. 数据库迁移机制

- `plugins/xiuxian_game/models/auto_migrate.py` (自动迁移系统): 完整的自动迁移框架
- `plugins/xiuxian_game/models/auto_migrate.py` (`REQUIRED_FIELDS` 字典): 25-46行，添加缺失字段的配置
- `plugins/xiuxian_game/models/auto_migrate.py` (`REQUIRED_TABLES` 字典): 51-210行，创建缺失表的DDL配置
- `plugins/xiuxian_game/models/auto_migrate.py` (`auto_migrate()` 函数): 248-279行，自动迁移主逻辑，支持表创建、字段添加、索引创建、ENUM修复
- **重要**: 项目**不使用Alembic**，采用自动迁移机制，在bot启动时自动检测并应用

#### 6. 留言板WorldMessage模型

- `plugins/xiuxian_game/models/world_message.py` (`WorldMessage` 模型): 5-14行，完整模型定义
  - `id`: 主键，自增
  - `player_id`: 发送者平台ID，String(32)，索引
  - `recipient_id`: 收信人平台ID，String(32)，索引，NULL表示世界频道
  - `content`: 留言内容，String(200)
  - `created_at`: 创建时间，DateTime，默认值func.now()
- **关键发现**: 模型中**没有软删除字段**（如is_deleted），删除功能需要新增

#### 7. 留言板命令处理流程

- `plugins/xiuxian_game/world/message_board.py` (命令注册): 41-43行，三个命令：留言、留言板、私信
- `plugins/xiuxian_game/world/message_board.py` (`handle_leave_msg()`): 245-291行，发布世界留言的处理流程
- `plugins/xiuxian_game/world/message_board.py` (`handle_private_message()`): 294-362行，发送私信的处理流程
- `plugins/xiuxian_game/world/message_board.py` (`handle_view_board()`): 365-398行，查看留言板的处理流程
- **关键发现**: 目前**没有留言删除功能**

#### 8. Player模型的留言板相关字段

- `plugins/xiuxian_game/models/player.py` (`last_message_board_check`): 187行，最后查看世界留言时间，DateTime，nullable
- `plugins/xiuxian_game/models/player.py` (`last_private_message_check`): 188行，最后查看私信时间，DateTime，nullable
- 这两个字段用于标记未读消息，在查看时自动更新

#### 9. 统一玩家访问接口

- `plugins/xiuxian_game/platform_utils.py` (`get_unified_player()`): 66-99行，统一的玩家数据访问接口，支持账号切换和管理员临时切换
- **建议**: 留言板命令已经使用此接口（message_board.py:260行），黑名单功能也应使用

#### 10. 配置管理系统

- `plugins/xiuxian_game/config.py` (`Config` 类): 6-11行，配置文件路径管理
- `plugins/xiuxian_game/config.py` (`game_config` 属性): 14-17行，动态加载config.yaml
- **用法**: `Config().game_config.get("admin", {}).get("admin_ids", [])`

---

### Report (The Answers)

#### result

**1. 管理员权限检查机制**:
- 项目有**统一的管理员权限检查函数** `is_admin(user_id: str)` 位于 `ai_guide.py:20-24`
- 管理员配置在 `data/config.yaml` 的 `admin.admin_ids` 列表中，目前有2个主管理员
- 还有子管理员配置 `admin.sub_admin_ids`，目前有1个子管理员
- 检查方式：`return user_id in admin_ids`（平台ID字符串比较）
- **推荐用法**: `from ..ai_guide import is_admin` 然后调用 `if is_admin(user_id): ...`

**2. 等级系统**:
- 玩家等级存储在 `Player.level` 字段，类型为 Integer，默认值1
- 等级范围: 1-300（配置在 `config.yaml` 的 `game.max_level`）
- **没有通用的等级检查函数**，需要直接比较 `player.level >= min_level`
- 示例参考：`admin/lottery_commands.py:252-263` 的等级检查逻辑

**3. 现有黑名单机制**:
- 项目中**不存在任何黑名单相关的数据表或代码**
- **不存在禁言、封禁等功能**
- 唯一相关的是**违禁词过滤**机制（替换为*号），位于 `message_board.py:19-61`
- **结论**: 需要从零实现黑名单功能

**4. 数据库迁移机制**:
- 项目**不使用Alembic**，采用**自动迁移机制**
- 核心文件: `plugins/xiuxian_game/models/auto_migrate.py`
- 迁移方式:
  1. 在 `REQUIRED_FIELDS` 字典中添加字段定义
  2. 在 `REQUIRED_TABLES` 字典中添加新表DDL（如果需要新表）
  3. Bot启动时自动检测并应用迁移
- **重要提示**: 系统提示中明确说明"ALWAYS use auto_migrate.py for database schema changes. NEVER use Alembic commands manually."

**5. 留言板当前实现的完整分析**:

**WorldMessage 模型字段**:
- `id`: 主键
- `player_id`: 发送者ID
- `recipient_id`: 收信人ID（NULL=世界频道）
- `content`: 留言内容（最多200字符）
- `created_at`: 创建时间

**命令流程**:
- `【留言 内容】`: 发布世界留言
- `【留言板】`: 查看世界留言板（分页，10条/页）
- `【留言板 私信】`: 查看私信箱
- `【私信 UID 内容】`: 发送私信

**软删除机制**: **不存在**，需要新增
**留言删除功能**: **不存在**，需要新增

**违禁词过滤**:
- 发送时自动过滤28个违禁词
- 被过滤时显示提示："⚠️ 检测到敏感词汇，已自动过滤"

---

#### conclusions

1. **管理员权限体系完善**: 有统一的 `is_admin()` 函数，配置在YAML中，易于扩展
2. **等级系统简单明确**: `Player.level` 字段，范围1-300，无额外封装
3. **无现有黑名单机制**: 需要从零实现黑名单表和相关逻辑
4. **自动迁移机制成熟**: 无需手动执行SQL或Alembic，只需修改配置字典
5. **留言板无删除功能**: 当前实现仅支持发布和查看，无删除、软删除机制
6. **违禁词过滤已存在**: 可以作为黑名单功能的补充，但不能替代黑名单

---

#### relations

**数据依赖关系**:
- `WorldMessage.player_id` → `Player.id` (外键关系，虽未在模型中显式定义)
- `WorldMessage.recipient_id` → `Player.id` (外键关系，仅私信时)
- `Player.last_message_board_check` ← `message_board.py` 更新（标记已读）
- `Player.last_private_message_check` ← `message_board.py` 更新（标记已读）

**代码调用关系**:
- `message_board.py` → `get_unified_player()` (获取玩家数据)
- `message_board.py` → `safe_session()` (数据库会话管理)
- `message_board.py` → `filter_banned_words()` (违禁词过滤)
- 管理员命令 → `ai_guide.is_admin()` (权限检查)
- `auto_migrate.py` ← `bot.py` (启动时调用)

**配置依赖关系**:
- `is_admin()` → `config.yaml:admin.admin_ids` (读取管理员列表)
- `MAX_LEN` (120) → 硬编码常量 (留言长度限制)
- `PAGE_SIZE` (10) → 硬编码常量 (分页大小)

---

## 实施建议

### 1. 黑名单表设计建议

基于调研结果，建议在 `auto_migrate.py` 的 `REQUIRED_TABLES` 中添加：

```sql
CREATE TABLE IF NOT EXISTS message_board_blacklist (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
    target_player_id VARCHAR(32) NOT NULL COMMENT '被禁言玩家ID',
    admin_id VARCHAR(32) NOT NULL COMMENT '操作管理员ID',
    reason VARCHAR(200) NULL COMMENT '禁言原因',
    min_level INT DEFAULT 0 COMMENT '最低等级限制（0表示无限制）',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    expires_at DATETIME NULL COMMENT '过期时间（NULL表示永久）',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否生效中',
    UNIQUE INDEX idx_target_player (target_player_id),
    INDEX idx_admin_id (admin_id),
    INDEX idx_is_active (is_active),
    FOREIGN KEY (target_player_id) REFERENCES player(id) ON DELETE CASCADE,
    FOREIGN KEY (admin_id) REFERENCES player(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='留言板黑名单表'
```

### 2. 功能优先级建议

**P0 核心功能**:
1. 黑名单表和模型创建
2. 管理员添加/移除黑名单命令
3. 发送留言时检查黑名单

**P1 扩展功能**:
1. 查看黑名单列表命令
2. 等级限制功能（低于X级禁言）
3. 临时禁言（带过期时间）

**P2 优化功能**:
1. 软删除留言功能（添加is_deleted字段）
2. 管理员删除任意留言命令
3. 黑名单历史记录

### 3. 关键注意事项

1. **必须使用 auto_migrate.py 进行数据库迁移**
2. **管理员权限检查使用 `is_admin(user_id)` 函数**
3. **玩家数据获取使用 `get_unified_player(session, event)`**
4. **数据库操作使用 `safe_session()` 上下文管理器**
5. **留言板命令处理需要调用 `message_add_head()` 格式化消息**

---

**调研完成时间**: 2025-12-24
**文档版本**: 1.0
**调研人**: scout agent
