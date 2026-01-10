# Git 协作规范

## 1. 核心摘要

项目采用单分支(main)开发模式,使用简洁的中文提交消息。所有数据库迁移通过 `auto_migrate.py` 自动处理,禁止手动执行 Alembic 命令。

## 2. 分支策略

- **主分支**: `main` - 唯一长期分支,所有开发直接在 main 进行
- **分支保护**: 无特殊分支保护规则
- **协作模式**: 小型团队直接提交到 main 分支

## 3. 提交消息格式

基于实际 commit 历史,项目使用以下格式:

### 3.1 标准格式

```
<type>: <简短描述>

<可选的详细说明>

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

### 3.2 类型标签 (type)

- `fix:` - Bug 修复 (例如: `fix: 修复试炼结局占位符显示问题`)
- `feat:` - 新功能 (例如: `feat: 添加圣诞节限定道具`)
- `refactor:` - 代码重构 (例如: `refactor: 删除废弃的enhanced_player_vs_monster_battle方法`)
- `docs:` - 文档更新 (例如: `docs: 清理临时性bug修复文档`)
- 无标签 - 直接描述 (例如: `试炼不能重复奖励`, `新试炼:婚契`)

### 3.3 消息示例

```bash
# 带 type 标签
fix: 修复一键嗑药命令中user_id未定义的错误
feat: 禁止临时buff叠加,验证耐药性机制
refactor: 道具名称改为"圣诞裂隙"

# 简洁描述(无 type)
新试炼：婚契
ace工具添加
鬼怪npc太多导致的观察问题
```

## 4. 数据库迁移规范

### 4.1 必须遵守

- ✅ **使用**: `plugins/xiuxian_game/models/auto_migrate.py`
- ✅ **操作**: 在 `REQUIRED_FIELDS` 字典中添加字段定义
- ✅ **验证**: 重启 bot,查看自动迁移日志

### 4.2 严格禁止

- ❌ **禁止**: 使用 Alembic 命令 (`alembic upgrade head` 等)
- ❌ **禁止**: 手动编写 SQL 迁移脚本
- ❌ **禁止**: 直接修改生产数据库结构

### 4.3 迁移流程

1. 在 `auto_migrate.py:25-58` 的 `REQUIRED_FIELDS` 中添加字段定义
2. 在 `auto_migrate.py:270-288` 的 `REQUIRED_ENUMS` 中添加 ENUM 定义(如需要)
3. 在 `auto_migrate.py:260-264` 的 `REQUIRED_INDEXES` 中添加索引(如需要)
4. 重启 bot,自动迁移会在启动时执行
5. 查看日志确认迁移成功

## 5. 协作工作流程

### 5.1 开发流程

1. 拉取最新代码: `git pull origin main`
2. 开发并测试功能
3. 提交变更(遵循上述提交格式)
4. 推送到远程: `git push origin main`

### 5.2 代码审查

- 小型团队采用信任提交模式
- 关键功能建议进行代码审查
- 使用 GitHub PR 进行代码审查(如需要)

### 5.3 冲突解决

```bash
# 拉取最新代码
git pull origin main

# 如有冲突,手动解决后
git add .
git commit -m "fix: 解决合并冲突"
git push origin main
```

## 6. .gitignore 规范

项目已配置完整的 `.gitignore`,主要忽略:
- Python 缓存 (`__pycache__/`, `*.pyc`)
- 数据库文件 (`*.db`, `*.sqlite3`)
- 日志文件 (`logs/`)
- 环境配置 (`.env`, `venv/`)
- 数据库配置 (`plugins/xiuxian_game/config/database.yaml`)
- 临时文件 (`.ace-tool/`)

## 7. 源代码参考

- **自动迁移模块**: `plugins/xiuxian_game/models/auto_migrate.py` - 数据库结构自动迁移
- **帮助信息**: `plugins/xiuxian_game/player/help.py` - 命令帮助文档(添加命令时同步更新)
- **项目配置**: `.gitignore` - Git 忽略规则

## 8. 外部参考

- **Conventional Commits**: https://www.conventionalcommits.org/ - 提交消息规范参考
- **Git 官方文档**: https://git-scm.com/doc - Git 命令参考
