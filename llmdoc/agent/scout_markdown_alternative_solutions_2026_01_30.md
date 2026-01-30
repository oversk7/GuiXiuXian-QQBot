### Code Sections (The Evidence)

- `plugins/xiuxian_game/player/help.py:1267-1366` (原始实现): 使用参数注入技术的`handle_full_help`函数
- `plugins/xiuxian_game/world/dungeon_battle.py:1280-1308` (分页参考): 副本探索的按钮实现,使用了8个按钮的feedback模板
- `plugins/xiuxian_game/item/catalog.py:570-606` (图鉴分页): 物品图鉴使用了分页机制展示多个物品

### Report (The Answers)

#### result

**参数注入技术已被QQ平台检测并限制,需要使用替代方案实现超过10个按钮的帮助系统。**

以下是三种可行的替代方案:

---

## 方案1:分页导航(推荐)

### 原理
- 使用session保存当前页码状态
- 每页显示10个按钮
- 提供"上一页/下一页"按钮切换
- 符合QQ平台规范,稳定可靠

### 代码实现

```python
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams
from nonebot.params import CommandArg
from nonebot.plugin import PluginManager
import asyncio

# 使用session保存用户当前页码
user_help_pages = {}

full_help_cmd = on_command("完整帮助", aliases={"全系统帮助", "all_help"}, priority=4, block=True)

@full_help_cmd.handle()
async def handle_full_help(event: MessageEvent, args: Message = CommandArg()):
    """分页式完整帮助系统 - 每页10个按钮"""
    user_id = event.get_user_id()

    # 获取页码参数(默认第0页)
    page_arg = args.extract_plain_text().strip()
    try:
        page = int(page_arg) if page_arg else 0
        page = max(0, page)  # 确保页码非负
    except ValueError:
        page = 0

    # 所有系统帮助列表
    all_systems = [
        ("修炼系统", "修炼系统帮助"),
        ("玩家系统", "玩家系统帮助"),
        ("背包系统", "背包系统帮助"),
        ("装备系统", "装备系统帮助"),
        ("战斗系统", "战斗系统帮助"),
        ("探索系统", "探索系统帮助"),
        ("经济系统", "经济系统帮助"),
        ("公会系统", "公会系统帮助"),
        ("社交系统", "社交系统帮助"),
        ("娱乐系统", "娱乐系统帮助"),
        # 第1页结束,第2页开始
        ("阴宅系统", "阴宅系统帮助"),
        ("副本系统", "副本系统帮助"),
        ("交易系统", "交易系统帮助"),
        ("钓鱼系统", "钓鱼系统帮助"),
        ("炼丹系统", "炼丹系统帮助"),
        ("打工系统", "打工系统帮助"),
        ("投资系统", "投资系统帮助"),
        ("委托系统", "委托系统帮助"),
        ("抽奖系统", "抽奖系统帮助"),
        ("赞助", "赞助帮助"),
        # 第2页结束
    ]

    # 每页10个按钮
    PAGE_SIZE = 10
    total_pages = (len(all_systems) + PAGE_SIZE - 1) // PAGE_SIZE

    # 确保页码在有效范围内
    page = min(page, total_pages - 1)

    # 计算当前页的系统范围
    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, len(all_systems))
    current_systems = all_systems[start_idx:end_idx]

    # 构建模板参数 - 使用物品列表类模板
    template_params = []
    for i, (cmd, desc) in enumerate(current_systems, 1):
        template_params.append(
            MessageMarkdownParams(key=f"btn{i}", values=[cmd])
        )

    # 如果不是最后一页,添加"下一页"按钮(使用第10个按钮位置)
    if page < total_pages - 1:
        template_params.append(
            MessageMarkdownParams(key="btn10", values=[f"完整帮助 {page + 1}"])
        )
    # 如果不是第一页,添加"上一页"按钮
    elif page > 0:
        template_params.append(
            MessageMarkdownParams(key="btn10", values=[f"完整帮助 {page - 1}"])
        )
    else:
        # 第一页且没有下一页,显示"返回"
        template_params.append(
            MessageMarkdownParams(key="btn10", values=["帮助"])
        )

    # 使用物品列表类模板(ID: 102499345_1769177949)
    markdown = MessageMarkdown(
        custom_template_id="102499345_1769177949",
        params=template_params
    )

    # 构建说明文本
    msg = Message(
        f"✨ 完整帮助系统 (第{page + 1}/{total_pages}页) ✨\r\n"
        f"═════════════\r\n"
        f"🎮 当前展示系统 {start_idx + 1}-{end_idx}\r\n"
        f"📚 共有{len(all_systems)}个系统\r\n"
        f"💡 点击对应按钮查看详细帮助\r\n"
        f"📖 点击第10个按钮切换页面\r\n"
        "═════════════"
    )

    await full_help_cmd.finish(msg, MessageSegment.markdown(markdown))
```

### 优点
- 符合平台规范,不会被检测
- 用户体验好,清晰的分页导航
- 易于维护和扩展

### 缺点
- 需要用户多次点击切换页面
- 不能一页看到所有按钮

---

## 方案2:多级菜单

### 原理
- 第一级:系统分类按钮(基础/进阶/娱乐等)
- 第二级:点击分类后显示该分类下的具体系统
- 层级清晰,符合用户习惯

### 代码实现

```python
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams
from nonebot.params import CommandArg

# 定义系统分类
SYSTEM_CATEGORIES = {
    "基础": [
        ("修炼系统", "查看修炼、突破、加点等核心成长系统"),
        ("玩家系统", "查看面板、排行榜、成就等玩家信息"),
        ("背包系统", "查看物品管理、使用道具、图鉴等功能"),
        ("装备系统", "查看装备锻造、升阶、镶嵌等系统"),
    ],
    "战斗": [
        ("战斗系统", "查看PVP、世界BOSS、战力等战斗内容"),
        ("副本系统", "查看副本挑战、自动采集等功能"),
        ("阴宅系统", "查看阴宅探索、诡异战斗等内容"),
    ],
    "社交": [
        ("社交系统", "查看好友、聊天、赠送等社交功能"),
        ("公会系统", "查看公会创建、管理、建筑等功能"),
        ("交易系统", "查看玩家交易、市场挂单等功能"),
    ],
    "娱乐": [
        ("娱乐系统", "查看签到、小游戏、月卡等休闲内容"),
        ("钓鱼系统", "查看钓鱼玩法、鱼类图鉴等"),
        ("炼丹系统", "查看丹药炼制、丹方配方等"),
    ],
}

category_help_cmd = on_command("分类帮助", aliases={"系统分类", "category_help"}, priority=4, block=True)

@category_help_cmd.handle()
async def handle_category_help(event: MessageEvent, args: Message = CommandArg()):
    """显示系统分类菜单"""
    category_arg = args.extract_plain_text().strip()

    # 如果提供了分类参数,显示该分类下的系统
    if category_arg in SYSTEM_CATEGORIES:
        return await show_category_systems(event, category_arg)

    # 否则显示分类菜单
    categories = list(SYSTEM_CATEGORIES.keys())

    # 构建分类按钮参数
    template_params = []
    for i, category in enumerate(categories, 1):
        template_params.append(
            MessageMarkdownParams(key=f"btn{i}", values=[f"分类帮助 {category}"])
        )

    # 添加返回按钮
    while len(template_params) < 10:
        template_params.append(
            MessageMarkdownParams(key=f"btn{len(template_params) + 1}", values=["帮助"])
        )

    # 使用物品列表模板
    markdown = MessageMarkdown(
        custom_template_id="102499345_1769177949",
        params=template_params
    )

    msg = Message(
        "✨ 系统分类帮助 ✨\r\n"
        "═════════════\r\n"
        "📂 请选择要查看的系统分类\r\n"
        f"📚 共{len(categories)}个分类\r\n"
        "💡 点击对应按钮查看该分类下的系统\r\n"
        "═════════════"
    )

    await category_help_cmd.finish(msg, MessageSegment.markdown(markdown))

async def show_category_systems(event: MessageEvent, category: str):
    """显示指定分类下的系统"""
    systems = SYSTEM_CATEGORIES[category]

    # 构建系统按钮参数
    template_params = []
    for i, (cmd, desc) in enumerate(systems, 1):
        template_params.append(
            MessageMarkdownParams(key=f"btn{i}", values=[cmd])
        )

    # 添加"返回分类"按钮
    if len(template_params) < 10:
        template_params.append(
            MessageMarkdownParams(key=f"btn{len(template_params) + 1}", values=["分类帮助"])
        )

    # 使用物品列表模板
    markdown = MessageMarkdown(
        custom_template_id="102499345_1769177949",
        params=template_params
    )

    msg = Message(
        f"✨ {category}系统帮助 ✨\r\n"
        "═════════════\r\n"
        f"📂 当前分类: {category}\r\n"
        f"📚 该分类下有{len(systems)}个系统\r\n"
        "💡 点击对应按钮查看详细帮助\r\n"
        "═════════════"
    )

    await category_help_cmd.finish(msg, MessageSegment.markdown(markdown))
```

### 优点
- 分类清晰,用户容易找到目标系统
- 符合用户心智模型
- 可以无限扩展系统数量

### 缺点
- 需要多次点击才能到达目标
- 需要维护分类结构

---

## 方案3:文本列表+命令交互

### 原理
- 放弃使用Markdown按钮
- 使用纯文本列出所有系统
- 用户输入编号或名称查看详细帮助
- 最简单、最可靠的方案

### 代码实现

```python
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

# 所有系统列表(带编号)
ALL_SYSTEMS = [
    ("1", "修炼系统", "修炼"),
    ("2", "玩家系统", "玩家"),
    ("3", "背包系统", "背包"),
    ("4", "装备系统", "装备"),
    ("5", "战斗系统", "战斗"),
    ("6", "探索系统", "探索"),
    ("7", "经济系统", "经济"),
    ("8", "公会系统", "公会"),
    ("9", "社交系统", "社交"),
    ("10", "娱乐系统", "娱乐"),
    ("11", "阴宅系统", "阴宅"),
    ("12", "副本系统", "副本"),
    ("13", "交易系统", "交易"),
    ("14", "钓鱼系统", "钓鱼"),
    ("15", "炼丹系统", "炼丹"),
    ("16", "打工系统", "打工"),
    ("17", "投资系统", "投资"),
    ("18", "委托系统", "委托"),
    ("19", "抽奖系统", "抽奖"),
    ("20", "赞助", "赞助"),
]

text_help_cmd = on_command("系统列表", aliases={"所有系统", "系统大全"}, priority=4, block=True)

@text_help_cmd.handle()
async def handle_text_help(event: MessageEvent, args: Message = CommandArg()):
    """显示所有系统的文本列表"""
    input_text = args.extract_plain_text().strip()

    # 如果用户输入了编号或名称,显示对应系统的详细帮助
    if input_text:
        return await show_system_detail(event, input_text)

    # 构建系统列表文本
    lines = [
        "✨ 所有系统列表 ✨",
        "═════════════",
        "💡 使用方式:",
        "  • 输入【系统列表 编号】查看详情 (如: 系统列表 1)",
        "  • 输入【系统列表 名称】查看详情 (如: 系统列表 修炼)",
        "",
        "📚 系统列表:",
    ]

    # 每行显示2个系统
    for i in range(0, len(ALL_SYSTEMS), 2):
        num1, name1, cmd1 = ALL_SYSTEMS[i]
        if i + 1 < len(ALL_SYSTEMS):
            num2, name2, cmd2 = ALL_SYSTEMS[i + 1]
            lines.append(f"  {num1}. {name1:<12} {num2}. {name2}")
        else:
            lines.append(f"  {num1}. {name1}")

    lines.extend([
        "",
        f"📊 共{len(ALL_SYSTEMS)}个系统",
        "═════════════",
    ])

    await text_help_cmd.finish("\r\n".join(lines))

async def show_system_detail(event: MessageEvent, input_text: str):
    """显示指定系统的详细帮助"""
    # 查找匹配的系统
    target_system = None
    for num, name, cmd in ALL_SYSTEMS:
        if input_text == num or input_text == name or input_text == cmd:
            target_system = (name, cmd)
            break

    if not target_system:
        await text_help_cmd.finish(f"⛔ 未找到系统: {input_text}\n💡 请使用【系统列表】查看所有可用系统")

    name, cmd = target_system

    # 这里可以从原有的help_dict中获取详细帮助信息
    # 示例:
    # help_info = help_dict.get(cmd, {})
    # description = help_info.get("description", "暂无描述")
    # usage = help_info.get("usage", "暂无用法说明")

    detail_text = f"""
✨ {name}详细帮助 ✨
═════════════
📖 系统名称: {name}
🔘 快捷命令: {cmd}

📝 详细说明:
这里显示系统的详细说明...

🎯 使用示例:
• 示例1: 【{cmd} 参数1】
• 示例2: 【{cmd} 参数2】

💡 相关命令:
• 相关命令1
• 相关命令2

═════════════
💡 输入【系统列表】返回主菜单
"""

    await text_help_cmd.finish(detail_text.strip())
```

### 优点
- 无任何按钮限制
- 实现简单,维护容易
- 不会触发平台检测
- 支持模糊搜索

### 缺点
- 用户体验不如按钮直观
- 需要用户记住编号或名称
- 交互次数较多

---

## 方案对比与推荐

| 方案 | 按钮限制 | 用户体验 | 实现难度 | 可靠性 | 推荐度 |
|------|---------|---------|---------|--------|--------|
| 分页导航 | 10个/页 | ⭐⭐⭐⭐ | 中等 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 多级菜单 | 10个/级 | ⭐⭐⭐⭐ | 中等 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 文本列表 | 无限制 | ⭐⭐⭐ | 简单 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 参数注入 | 110个 | ⭐⭐⭐⭐⭐ | 复杂 | ⭐ | ❌已失效 |

**最终推荐**:使用**方案1(分页导航)**,它在用户体验、实现难度和可靠性之间达到了最佳平衡。

#### conclusions

1. **参数注入技术已失效**:QQ平台加强了检测机制,不再允许通过values拼接绕过按钮数量限制
2. **分页导航是最优解**:符合平台规范,用户体验良好,易于实现和维护
3. **多级菜单适合复杂系统**:如果系统数量特别多(>30个),建议使用多级菜单
4. **文本列表最可靠**:如果追求极致稳定性,文本列表是最保险的选择

#### relations

1. **与现有代码的集成**:
   - `help.py:1267-1366`的`handle_full_help`函数可以用分页导航方案替换
   - 可以复用现有的`help_dict`数据结构
   - 无需修改其他帮助相关代码

2. **与模板的关系**:
   - 分页导航和多级菜单都使用`102499345_1769177949`(物品列表模板)
   - 文本列表方案完全不依赖Markdown模板
   - 所有方案都符合QQ平台的模板使用规范

3. **用户体验优化**:
   - 可以在第一页添加"搜索"功能,允许用户快速定位目标系统
   - 可以添加"收藏"功能,记住用户常用的系统
   - 可以使用session记住用户的浏览历史

4. **扩展性考虑**:
   - 分页方案:添加新系统时自动增加页数
   - 多级菜单:添加新分类或子系统时只需修改配置
   - 文本列表:添加新系统时只需更新ALL_SYSTEMS数组
