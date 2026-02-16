---
# 📊 架构审计报告 - GuiXiuXian2
## 总体评分
| 维度     | 评分      | 说明                                  |
| -------- | --------- | ------------------------------------- |
| **架构设计** | ⭐⭐⭐⭐☆ | DDD分层清晰，无循环依赖               |
| **代码质量** | ⭐⭐⭐☆☆  | 39个大文件(>500行)，存在上帝函数      |
| **性能**     | ⭐⭐⭐☆☆  | N+1查询问题，30+仓库缺少eager loading |
| **安全**     | ⭐⭐☆☆☆   | API密钥泄露，AI-SQL注入风险           |
| **可维护性** | ⭐⭐⭐☆☆  | 双轨Service迁移中，部分反模式         |
---
🔴 紧急问题 (需立即修复)
1. API密钥泄露
位置: plugins/xiuxian_game/data/config.yaml
风险: 智谱AI、302.ai密钥已提交到Git
修复步骤:
1. 立即轮换两个API密钥
2. 将 data/config.yaml 加入 .gitignore
3. 创建 config.yaml.example 模板
2. AI-SQL注入风险
位置: plugins/xiuxian_game/ai_guide.py:508-531
风险: 用户输入→AI生成SQL→直接执行
修复: 使用参数化查询或白名单限制
3. 连接泄漏
位置: plugins/xiuxian_game/player/invite.py
问题: 在UoW上下文内调用finish()，导致连接泄漏
修复: 将所有 finish() 移到 async with UnitOfWork() 外部
---
🟠 性能问题
N+1查询 (高影响)
| 文件              | 行号             | 问题                |
| ----------------- | ---------------- | ------------------- |
| player/invite.py  | 258-262, 292-294 | 循环内查询Player    |
| cultivate/core.py | 1443-1489        | 同一玩家3次独立查询 |
缺少索引 (中影响)
| 模型          | 列          | 影响           |
| ------------- | ----------- | -------------- |
| GuildMember   | guild_id    | 宗门成员查询慢 |
| GuildBuilding | guild_id    | 建筑查询慢     |
| NPC           | location_id | NPC位置查询慢  |
缺少Eager Loading (30+仓库)
只有9/35个仓库使用 joinedload/selectinload，其他存在懒加载N+1风险。
---
🟡 代码质量问题
上帝函数 (>100行)
| 文件                      | 函数                       | 行数 | 建议            |
| ------------------------- | -------------------------- | ---- | --------------- |
| battle/enhanced_engine.py | _execute_enhanced_attack() | 496  | 拆分为10+子函数 |
| cultivate/core.py         | handle_breakthrough()      | 252  | 提取验证逻辑    |
| cultivate/core.py         | handle_cultivate()         | 213  | 提取奖励计算    |
重复代码
core.py 中 handle_cultivate(), handle_seclusion(), handle_out_seclusion() 共享相同的奖励计算逻辑，应提取为 CultivationBonusCalculator。
大文件需要拆分
| 文件                    | 行数 | 建议拆分                       |
| ----------------------- | ---- | ------------------------------ |
| inner_realm/service.py  | 2573 | 按功能域拆分                   |
| world/dungeon_battle.py | 2160 | movement/combat/drops/merchant |
| guild/guild.py          | 1650 | 按命令类型拆分                 |
---
🟢 架构优点
1. DDD分层完美 - domain层纯净，不依赖infrastructure
2. 无循环依赖 - 依赖关系清晰向下
3. UoW模式正确 - 事务管理集中在UnitOfWork
4. 双轨迁移有序 - 20/51服务已迁移到DI模式
5. ORM使用规范 - 201处查询均使用参数化
---
📋 优化建议优先级
| 优先级 | 任务                           | 预估工时 | ROI             |
| ------ | ------------------------------ | -------- | --------------- |
| P0     | 轮换API密钥 + gitignore        | 30分钟   | 🔴 安全关键     |
| P0     | 修复invite.py连接泄漏          | 1小时    | 🔴 稳定性关键   |
| P1     | 添加数据库索引                 | 2小时    | 🟠 性能提升显著 |
| P1     | 修复N+1查询(invite.py)         | 2小时    | 🟠 性能提升显著 |
| P2     | 拆分_execute_enhanced_attack() | 4小时    | 🟡 可维护性     |
| P2     | 提取CultivationBonusCalculator | 3小时    | 🟡 减少重复     |
| P3     | 拆分dungeon_battle.py          | 8小时    | 🟢 长期可维护性 |
| P3     | 继续Service DI迁移(31个)       | 20小时   | 🟢 架构一致性   |
---
结论
当前状态: 可以运行，但需要优化
你的项目架构基础很好 (DDD分层、UoW模式、无循环依赖)，但存在：
- 2个安全漏洞需要立即修复
- 3个性能问题影响用户体验
- 若干代码质量问题影响长期维护