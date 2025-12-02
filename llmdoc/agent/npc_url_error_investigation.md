<!-- NPC URL Error Investigation Report -->

### Code Sections (The Evidence)

**核心问题代码**:
- `plugins/xiuxian_game/world/npc_interaction.py:197-214` (`handle_ghost_interaction`) - 鬼怪交互处理函数，第209行存在格式化字符串错误

**相关工具函数**:
- `plugins/xiuxian_game/utils.py:11-16` (`message_add_head`) - 消息头添加工具，将消息内容包装为QQ Message对象后发送

**数据模型**:
- `plugins/xiuxian_game/models/npc.py:34-90` (`NPC` 类) - NPC数据模型，包含name、description、level等属性

**其他交互处理函数**（对照组，正确使用f-string）:
- `plugins/xiuxian_game/world/npc_interaction.py:135-148` (`handle_merchant_interaction`) - 商人交互，所有行正确使用f-string
- `plugins/xiuxian_game/world/npc_interaction.py:153-175` (`handle_craftsman_interaction`) - 工匠交互，所有行正确使用f-string
- `plugins/xiuxian_game/world/npc_interaction.py:178-194` (`handle_employer_interaction`) - 雇主交互，所有行正确使用f-string

### Report (The Answers)

#### result

**错误原因**：
`plugins/xiuxian_game/world/npc_interaction.py:209` 行存在字符串格式化错误，导致QQ官方API误判为包含URL而拒绝发送。

**具体问题**：
```python
# 第209行（错误代码）
"• 【攻击 {npc.name}】与鬼怪战斗",
```

这行字符串**缺少 f-string 前缀**，导致：
1. `{npc.name}` 没有被Python解析和替换
2. 最终发送的消息中包含字面文本 `{npc.name}`
3. QQ官方API将 `npc.name` 识别为类似域名的URL模式（如 `example.com`）
4. 触发安全机制，返回错误：`code=40054010, message=消息发送失败, 不允许发送url npc.name`

**错误发生位置**：
- 文件：`plugins/xiuxian_game/world/npc_interaction.py`
- 函数：`handle_ghost_interaction` (第197-214行)
- 错误行：第209行
- 调用路径：`handle_npc_interaction` → `handle_ghost_interaction` → `interact_cmd.finish(message_add_head(...))`

**消息构建流程**：
```
1. handle_ghost_interaction() 构建 lines 列表
   ├─ 第200行: f"👻 {npc.name}"  ✅ 正确使用f-string
   ├─ 第202行: f"💀 {npc.name}发出..." ✅ 正确使用f-string
   └─ 第209行: "• 【攻击 {npc.name}】..." ❌ 缺少f前缀
2. "\n".join(lines) 合并所有行
3. message_add_head(...) 添加消息头『诡修仙』
4. Message() 包装为QQ消息对象
5. interact_cmd.finish() 发送消息 → QQ API拒绝
```

**被误判为URL的字符串模式**：
- `{npc.name}` - 包含点号的模式，类似域名格式
- QQ API的URL检测机制可能匹配的模式：`*.name`、`npc.*`、`{domain.tld}`

#### conclusions

1. **根本原因**：字符串格式化不一致，第209行忘记使用f-string前缀，导致变量未被替换
2. **触发条件**：当玩家执行 `交互 <鬼怪NPC名称>` 命令时，系统调用 `handle_ghost_interaction` 函数
3. **错误类型**：QQ官方API的URL安全检测机制被触发，而非代码逻辑错误
4. **影响范围**：仅影响鬼怪类型NPC的交互，其他类型NPC（商人、工匠、雇主）未受影响
5. **代码质量问题**：同一函数内混用f-string和普通字符串，缺乏一致性检查

#### relations

**代码关系**：
```
handle_npc_interaction (主命令处理器)
├─ 获取玩家数据 (get_unified_player)
├─ 获取NPC数据 (npc_service.get_npc_by_name)
└─ 根据NPC类型分发处理
    ├─ NPCType.MERCHANT → handle_merchant_interaction ✅
    ├─ NPCType.CRAFTSMAN → handle_craftsman_interaction ✅
    ├─ NPCType.EMPLOYER → handle_employer_interaction ✅
    ├─ NPCType.GHOST → handle_ghost_interaction ❌ (第209行问题)
    ├─ NPCType.SPECIAL_VENDOR → handle_special_vendor_interaction ✅
    └─ 其他 → handle_generic_interaction ✅
```

**字符串格式化对比**：
- **正确示例**（第200-206行）：所有行都使用f-string前缀
  ```python
  f"👻 {npc.name}"
  f"💀 {npc.name}发出阴森的笑声..."
  f"⚔️ 等级：{npc.level}"
  ```
- **错误示例**（第209行）：缺少f前缀
  ```python
  "• 【攻击 {npc.name}】与鬼怪战斗"
  ```

**修复建议**：
1. **立即修复**（必须）：为第209行添加f-string前缀
   ```python
   # 修改前
   "• 【攻击 {npc.name}】与鬼怪战斗",

   # 修改后
   f"• 【攻击 {npc.name}】与鬼怪战斗",
   ```

2. **代码审查**（推荐）：检查项目中所有包含 `{...}` 模式的字符串，确认是否需要f-string
   ```bash
   # 搜索可疑字符串
   grep -rn '"{[^"]*}"' plugins/xiuxian_game/ | grep -v 'f"'
   ```

3. **测试验证**（必须）：
   - 创建测试用鬼怪NPC
   - 执行 `交互 <鬼怪名称>` 命令
   - 验证消息正确显示NPC名称，而非 `{npc.name}`

4. **防御性编程**（可选）：添加字符串格式化检查工具
   - 使用pylint规则检测未使用f-string的格式化字符串
   - 添加pre-commit钩子，自动检测此类问题

**不需要的修复方案**（错误方向）：
- ❌ URL转义或字符替换 - 这不是真正的URL问题
- ❌ 消息格式调整 - 消息格式本身没问题
- ❌ 修改QQ API配置 - API行为是正确的安全机制

**修复难度**：⭐ (非常简单，只需添加一个字符 `f`)

**风险评估**：✅ 零风险，修复后不会影响其他功能

---

**调查完成时间**：2025-12-02
**调查者**：scout agent
**报告类型**：代码缺陷调查报告
**优先级**：P1 高优先级（影响鬼怪NPC的所有交互）
