# 如何部署Service DI重构

## 前置条件检查

在开始部署前，确认以下条件已满足：

1. **代码已提交**: 所有修改已推送到main分支
2. **Feature Flag已启用**: 27/27个Feature Flag = True
3. **Repository导入路径已修复**: 38个文件已从`..domain`改为`...domain`
4. **SQL脚本已修正**: 表名从`players`改为`player`
5. **PlatformBinding已清理**: 相关引用已移除

## 步骤1: 拉取最新代码

### 1.1 SSH登录服务器

```bash
ssh user@your-server
```

### 1.2 进入项目目录

```bash
cd /path/to/GuiXiuXian2
```

### 1.3 拉取代码

```bash
# 查看当前状态
git status

# 拉取最新代码
git pull origin main

# 验证最新commit
git log -1
# 应该看到: commit a3747fa "fix: 修复SQL脚本表名"或更新的commit
```

## 步骤2: 备份数据库（必须）

### 2.1 备份整个数据库

```bash
# 创建带时间戳的备份
mysqldump -u root -p xiuxian_game > backup_$(date +%Y%m%d_%H%M%S).sql

# 验证备份文件大小
ls -lh backup_*.sql
```

### 2.2 记录备份文件名

```bash
# 记录备份文件路径，以便回滚时使用
echo "备份文件: $(pwd)/backup_XXXXXX.sql"
```

**重要**: 保留此备份至少7天，直到确认新架构稳定运行

## 步骤3: 执行数据库迁移

### 3.1 验证迁移脚本

```bash
# 检查迁移脚本是否存在
ls -l migrate_account_ownership.sql

# 查看脚本内容（可选）
cat migrate_account_ownership.sql
```

**预期内容**:
- 创建`account_ownership`表
- 创建`account_transfer_logs`表
- 为所有现有玩家创建所有权记录

### 3.2 执行迁移

```bash
# 方法A: 直接执行SQL脚本
mysql -u root -p xiuxian_game < migrate_account_ownership.sql

# 方法B: 使用Python脚本（如果提供）
# source .venv/bin/activate
# python migrate_account_ownership.py
```

### 3.3 验证迁移结果

```bash
# 登录MySQL
mysql -u root -p xiuxian_game

# 验证表是否创建
SHOW TABLES LIKE 'account_%';
# 应该看到: account_ownership, account_transfer_logs

# 验证数据是否迁移
SELECT COUNT(*) FROM account_ownership;
# 应该等于玩家总数

# 退出MySQL
EXIT;
```

**预期输出**:
- `account_ownership`: N条记录（N = 玩家总数）
- `account_transfer_logs`: 0条记录

## 步骤4: 重启服务

### 4.1 重启Bot服务

**方法A: systemd**
```bash
# 重启服务
sudo systemctl restart xiuxian_bot

# 查看状态
sudo systemctl status xiuxian_bot

# 查看日志
sudo journalctl -u xiuxian_bot -f
```

**方法B: pm2**
```bash
# 重启服务
pm2 restart xiuxian_bot

# 查看状态
pm2 status

# 查看日志
pm2 logs xiuxian_bot
```

**方法C: 手动**
```bash
# 查找并停止旧进程
ps aux | grep bot.py
kill <PID>

# 启动新进程
python bot.py &

# 或使用nohup
nohup python bot.py > bot.log 2>&1 &
```

### 4.2 验证启动成功

```bash
# 查看日志最后几行
tail -f bot.log
# 或
journalctl -u xiuxian_bot -n 50
```

**预期日志**:
- 看到Nonebot2启动信息
- 看到"WebSocket连接成功"
- 没有导入错误或数据库连接错误

## 步骤5: 功能验证

### 5.1 测试新启用的Service

**EquipmentTradeService（装备交易）**:
```
在QQ中发送命令:
> 挂牌出售
> 求购装备
> 查看市场
```

**DailyTaskService（每日任务）**:
```
> 每日委托
> 领取奖励
```

**RussianRouletteService（俄罗斯轮盘）**:
```
> 创建房间
> 加入房间
```

**LocationService（地点探索）**:
```
> 观察
> 附近
```

### 5.2 测试AccountSwitching系统

```
> 我的账号              # 查看拥有的账号
> 生成转让密钥 <UID>    # 生成转让密钥
> 取消转让 <UID>        # 取消转让
```

### 5.3 测试基础功能

确保原有功能正常运行：
```
> 我的状态
> 修炼
> 公会信息
> 装备
```

## 步骤6: 监控观察

### 6.1 错误日志监控

```bash
# 实时查看日志
tail -f bot.log | grep -i error

# 或使用journalctl
journalctl -u xiuxian_bot -f | grep -i error
```

**关注要点**:
- Repository导入错误
- 数据库连接错误
- Feature Flag相关错误
- UnitOfWork事务错误

### 6.2 性能监控

```bash
# 查看进程资源占用
top -p $(pgrep -f bot.py)

# 查看数据库连接数
mysql -u root -p -e "SHOW PROCESSLIST;" | wc -l
```

**关注指标**:
- CPU使用率（应与部署前相近）
- 内存使用（可能略有增加，因为多了Repository实例）
- 数据库连接数（应该减少，因为UoW统一会话）

### 6.3 玩家反馈收集

观察以下渠道：
- QQ群聊反馈
- 私聊反馈
- 错误日志中的异常

## 回滚方案

如果遇到严重问题，按以下步骤回滚：

### 方案A: Feature Flag快速回滚（推荐）

**适用场景**: 功能异常但数据完整

```bash
# 1. SSH登录服务器
ssh user@your-server
cd /path/to/GuiXiuXian2

# 2. 编辑5个文件，将Feature Flag改为False
# economy/market.py
sed -i 's/USE_NEW_EQUIPMENT_TRADE_SERVICE = True/USE_NEW_EQUIPMENT_TRADE_SERVICE = False/' plugins/xiuxian_game/economy/market.py

# daily_task/commands.py
sed -i 's/USE_NEW_DAILY_TASK_SERVICE = True/USE_NEW_DAILY_TASK_SERVICE = False/' plugins/xiuxian_game/daily_task/commands.py

# entertainment/russian_roulette.py
sed -i 's/USE_NEW_RUSSIAN_ROULETTE_SERVICE = True/USE_NEW_RUSSIAN_ROULETTE_SERVICE = False/' plugins/xiuxian_game/entertainment/russian_roulette.py

# world/real_world_explore.py
sed -i 's/USE_NEW_LOCATION_SERVICE = True/USE_NEW_LOCATION_SERVICE = False/' plugins/xiuxian_game/world/real_world_explore.py

# world/npc_interaction.py
sed -i 's/USE_NEW_LOCATION_SERVICE = True/USE_NEW_LOCATION_SERVICE = False/' plugins/xiuxian_game/world/npc_interaction.py

# 3. 重启服务
sudo systemctl restart xiuxian_bot
# 或: pm2 restart xiuxian_bot
```

**预期结果**: 使用旧版本Service实现，新架构代码不运行

### 方案B: 数据库回滚（慎用）

**适用场景**: 数据损坏或迁移失败

```bash
# 1. 停止服务
sudo systemctl stop xiuxian_bot

# 2. 恢复数据库
mysql -u root -p xiuxian_game < backup_XXXXXX.sql

# 3. 启动服务
sudo systemctl start xiuxian_bot
```

**注意**: 回滚数据库会丢失回滚期间的玩家数据变更

### 方案C: 代码回滚（最后手段）

**适用场景**: Feature Flag回滚无效

```bash
# 1. 回滚到重构前的commit
git reset --hard 9f3b5de  # "开始重构"之前的commit

# 2. 重启服务
sudo systemctl restart xiuxian_bot
```

**注意**: 这将丢失所有重构代码，需要重新部署

## 部署后清理（可选）

部署稳定运行1周后，可考虑以下清理工作：

### 1. 移除旧版本Service代码

```bash
# 删除所有*_legacy.py文件
find plugins/xiuxian_game -name "*_legacy.py" -delete

# 删除Feature Flag判断代码（需手动编辑）
# 保留USE_NEW_*_SERVICE = True的分支，删除else分支
```

### 2. 移除Feature Flag常量

在各命令处理文件中：
```python
# 删除这一行
USE_NEW_GUILD_SERVICE = True

# 删除if判断，只保留新版本代码
# if USE_NEW_GUILD_SERVICE:
#     # 新版本代码
# else:
#     # 旧版本代码（删除）
```

### 3. 清理备份文件

```bash
# 保留最新的3个备份
ls -t backup_*.sql | tail -n +4 | xargs rm
```

## 常见问题

### Q1: 启动时报错"No module named 'infrastructure'"

**原因**: Python路径配置问题

**解决**:
```bash
# 确保在项目根目录启动
cd /path/to/GuiXiuXian2
python bot.py
```

### Q2: 数据库连接错误

**原因**: database.yaml配置问题

**解决**:
```bash
# 检查配置文件
cat plugins/xiuxian_game/data/database.yaml

# 确认MySQL服务运行
sudo systemctl status mysql
```

### Q3: Repository导入错误

**原因**: 导入路径未修复

**解决**:
```bash
# 验证是否拉取了最新代码（commit ad8013f）
git log --oneline -5 | grep "fix: 修复所有repository"
```

### Q4: 某个功能报错，其他正常

**方案**: 单独回滚该功能的Feature Flag
```python
# 只修改出错功能的Flag为False
USE_NEW_XXX_SERVICE = False
```

---

**相关文档**:
- 部署准备: `/READY_TO_DEPLOY.md`
- 重构完成: `/llmdoc/overview/service-di-completion.md`
- DI架构: `/llmdoc/architecture/service-di-architecture.md`
