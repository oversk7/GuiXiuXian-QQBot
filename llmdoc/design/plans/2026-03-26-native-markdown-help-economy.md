# 原生Markdown全面改造：帮助系统 + 经济系统

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将帮助系统（8大模块 + 26子系统）和经济系统（银行/跑商/股票/市场/打工/理财）从纯文本全面迁移到 QQ 原生 Markdown，最大化利用 `<qqbot-cmd-input>` 蓝字交互减少用户打字操作。

**Architecture:** 逐系统手工设计，每个系统根据内容特点定制 Markdown 排版。所有用户可能想操作的命令都做成可点击蓝字。利用 `show` 与 `text` 不一致的技巧，显示友好文本、输入实际命令。

**Tech Stack:** NoneBot2 QQ Adapter + `MessageMarkdown(content=...)` 原生 Markdown + `<qqbot-cmd-input>` 交互标签

---

## 核心技术约定

### 原生 Markdown 发送方式
```python
from nonebot.adapters.qq import MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown

content = "# 标题\r正文\r> 提示"
markdown = MessageMarkdown(content=content)
await cmd.finish(MessageSegment.markdown(markdown))
```

### 换行规则
- **必须用 `\r`** 代替 `\n`，QQ 原生 Markdown 不识别 `\n`

### 交互蓝字语法
```
<qqbot-cmd-input text="实际发送的命令" show="用户看到的蓝字" reference="false"/>
```
- `text`: 点击后实际输入到聊天框的文字
- `show`: 用户在消息中看到的蓝色可点击文字
- `reference="false"`: 不引用原消息（默认 false 可省略）

### 蓝字设计原则
1. **所有命令都做成蓝字** — 用户能点的绝不让用户打字
2. **show 简洁，text 完整** — 如 `show="签到"` `text="签到"`；`show="查看市集"` `text="市集"`
3. **带参数命令展示完整语法** — 如 `show="存 金额"` `text="存 "`（末尾留空让用户补参数）
4. **下一步操作要给蓝字** — 每个消息末尾提供 2-4 个常用后续操作蓝字

### 辅助函数（新建 `plugins/xiuxian_game/utils_markdown.py`）
```python
def cmd(show: str, text: str = "") -> str:
    """生成蓝字交互标签"""
    actual = text or show
    return f'<qqbot-cmd-input text="{actual}" show="{show}" reference="false"/>'

def build_markdown(content: str) -> MessageSegment:
    """构建原生 Markdown MessageSegment"""
    from nonebot.adapters.qq import MessageSegment
    from nonebot.adapters.qq.models.common import MessageMarkdown
    md = MessageMarkdown(content=content.replace('\n', '\r'))
    return MessageSegment.markdown(md)
```

---

## Phase 1: 帮助系统改造

### 文件变动总览

| 操作 | 文件路径 | 说明 |
|------|---------|------|
| Create | `plugins/xiuxian_game/utils_markdown.py` | 原生 Markdown 工具函数 |
| Modify | `plugins/xiuxian_game/player/help.py` | 改造所有帮助处理器 |

---

### Task 1: 创建 Markdown 工具模块

**Files:**
- Create: `plugins/xiuxian_game/utils_markdown.py`

- [ ] **Step 1: 创建工具文件**

```python
"""
原生 Markdown 工具函数

QQ 原生 Markdown 通用构建器，提供蓝字交互标签和消息构建。
"""
from nonebot.adapters.qq import MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown


def cmd(show: str, text: str = "") -> str:
    """
    生成 QQ 原生 Markdown 蓝字交互标签

    Args:
        show: 用户看到的蓝色可点击文字
        text: 点击后实际输入的命令（默认与 show 相同）

    Returns:
        <qqbot-cmd-input> 标签字符串
    """
    actual = (text or show).replace('"', '&quot;')
    show_safe = show.replace('"', '&quot;')
    return f'<qqbot-cmd-input text="{actual}" show="{show_safe}" reference="false"/>'


def build_markdown(content: str) -> MessageSegment:
    """
    构建原生 Markdown MessageSegment

    自动将 \\n 替换为 \\r（QQ 原生 Markdown 换行要求）

    Args:
        content: Markdown 正文

    Returns:
        MessageSegment 可直接 finish/send
    """
    md = MessageMarkdown(content=content.replace('\r\n', '\r').replace('\n', '\r'))
    return MessageSegment.markdown(md)
```

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/utils_markdown.py
git commit -m "feat: 新增原生Markdown工具模块(cmd蓝字+build_markdown)"
```

---

### Task 2: 改造主帮助菜单

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py:24-57` (handle_help)

**设计目标：** 8 大模块名全部做成蓝字，底部常用操作也做成蓝字。

- [ ] **Step 1: 改造 handle_help**

将 `handle_help` 函数中的纯文本 `msg` 替换为原生 Markdown：

```python
from ..utils_markdown import cmd, build_markdown

@help_cmd.handle()
async def handle_help(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 诡修仙 · 帮助菜单\n"
        "📚 点击模块名查看详细指令\n"
        "***\n"
        f"{cmd('新手上路')} 注册/修炼/突破/加点/签到\n"
        f"{cmd('成长核心')} 装备/锻造/炼丹/升阶/阴宅\n"
        f"{cmd('资源获取')} 打工/钓鱼/灵田/副本/委托\n"
        f"{cmd('战斗挑战')} PVE/PVP/世界BOSS/战力\n"
        f"{cmd('经济市场')} 跑商/银行/投资/挂牌/拍卖行\n"
        f"{cmd('社交公会')} 送礼/结婚/师徒/公会\n"
        f"{cmd('图鉴记录')} 物品图鉴/排行榜/成就\n"
        f"{cmd('福利娱乐')} 签到/月卡/小游戏/天灾\n"
        "***\n"
        f"💡 新手？点 {cmd('新手指引')} 看成长路线\n"
        f"💡 有疑问？点 {cmd('问 你的问题', '问 ')} 询问AI\n"
        f"💡 {cmd('完整帮助')} | {cmd('赞助商店')} | {cmd('切换称号')}\n"
        f"💡 [加入官群【꧁༺诡修仙༻꧂】](https://qun.qq.com/universal-share/share?ac=1&authKey=fBfQXvfkDK92gotOtEFTjwLD4R3qKy%2BV79jJCyMLKqTWKmazq23NO3miCxBir7aL&busi_data=eyJncm91cENvZGUiOiI5NjI0OTQ2NzkiLCJ0b2tlbiI6IjdSUURicDczVGpFclVUUDRFRFh4R1lYaXdzMmtyTEgvU040UlJyUkhjVUxXUGZyb0NHR3Iwa1VIZnAranpqQTQiLCJ1aW4iOiIyNjk4NTk1MTE1In0%3D&data=lTl1gOtgo5gvdmyaAmJGiAZBK6oI7nGH1jr_AuHfsltlCDUTpIdA7qvXh5k5Yj0uidZilU_og4nQXsr8cflTzA&svctype=4&tempid=h5_group_info)"
    )
    await help_cmd.finish(build_markdown(content))
```

- [ ] **Step 2: 验证**

启动 Bot，发送【帮助】，确认：
1. 标题显示为 Markdown 一级标题
2. 模块名显示为蓝色可点击文字
3. 点击蓝字能正确输入对应命令
4. 官群链接可点击跳转

- [ ] **Step 3: Commit**

```bash
git add plugins/xiuxian_game/player/help.py
git commit -m "feat(help): 主帮助菜单改用原生Markdown蓝字交互"
```

---

### Task 3: 改造「新手上路」模块

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py:72-108` (handle_newbie_module)

- [ ] **Step 1: 改造 handle_newbie_module**

```python
@newbie_module_cmd.handle()
async def handle_newbie_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 新手上路\n"
        "注册角色，迈出修仙第一步\n"
        "***\n"
        "**👤 注册与角色**\n"
        f"{cmd('注册 男', '注册 ')} 创建角色（系统自动生成道号）\n"
        f"{cmd('面板')} 查看自己的状态\n"
        f"{cmd('改名 新名字', '改名 ')} 改名（需改名卡）\n"
        "***\n"
        "**🧘 修炼成长**\n"
        f"{cmd('修炼')} 获取经验（5分钟冷却）\n"
        f"{cmd('闭关')} 离线挂机修炼\n"
        f"{cmd('出关')} 结束闭关领收益\n"
        f"{cmd('突破')} 经验满后升级境界\n"
        f"{cmd('突破 镇厄')} 消耗怨念确保突破成功\n"
        f"{cmd('冥返')} 轮回转生（等级重置获永久加成）\n"
        f"{cmd('冥返信息')} 查看冥返要求和转数加成\n"
        "***\n"
        "**📊 属性加点**\n"
        f"{cmd('加点 力 10', '加点 ')} 分配属性点（力/体/敏/智/运/防）\n"
        f"{cmd('加点帮助')} 查看详细加点推荐\n"
        "***\n"
        "**🎯 每日必做**\n"
        f"{cmd('签到')} 每日签到领奖 → {cmd('修炼')} 提升修为 → {cmd('闭关')} 睡前挂机\n"
        "***\n"
        "> 💡 30级前突破100%成功，大胆突破！\n"
        f"> {cmd('新手指引')} 查看完整成长路线 | {cmd('帮助', '帮助')} 返回主菜单"
    )
    await newbie_module_cmd.finish(build_markdown(content))
```

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/player/help.py
git commit -m "feat(help): 新手上路模块改用原生Markdown蓝字交互"
```

---

### Task 4: 改造「成长核心」模块

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py:111-152` (handle_growth_module)

- [ ] **Step 1: 改造 handle_growth_module**

```python
@growth_module_cmd.handle()
async def handle_growth_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 成长核心\n"
        "装备、锻造、炼丹、阴宅——战力怎么涨\n"
        "***\n"
        "**🎽 装备线**\n"
        f"{cmd('装备栏')} 查看已穿戴装备\n"
        f"{cmd('装备 编号', '装备 ')} 穿戴 | {cmd('卸下 编号', '卸下 ')} 卸下 | {cmd('修理 编号', '修理 ')} 修理\n"
        f"{cmd('锻造列表')} 查看可锻造装备\n"
        f"{cmd('锻造 装备名', '锻造 ')} 在工坊附近锻造\n"
        f"{cmd('升阶 编号', '升阶 ')} 升阶强化装备\n"
        "***\n"
        "**💎 镶嵌系统**\n"
        f"{cmd('孔位 编号', '孔位 ')} 查看装备孔位\n"
        f"{cmd('镶嵌物品')} 查看可镶嵌物品\n"
        f"{cmd('镶嵌 编号 孔位 镶嵌物', '镶嵌 ')} 镶嵌宝石\n"
        "***\n"
        "**🧪 炼丹线**\n"
        f"{cmd('丹方')} 查看配方 → {cmd('炼丹 丹方名 数量', '炼丹 ')} 炼制 → {cmd('收获丹药')} 收获 → {cmd('使用 丹药名', '使用 ')} 服用\n"
        "***\n"
        "**💀 怨念系统**\n"
        f"{cmd('献祭 材料名 数量', '献祭 ')} 献祭材料获取怨念（用于 {cmd('突破 镇厄')} 确保成功）\n"
        "***\n"
        "**🏠 阴宅（修炼基地）**\n"
        f"{cmd('阴宅')} 查看状态 | {cmd('购买阴宅')} 购买(1000万) | {cmd('升级阴宅')} 升级\n"
        f"{cmd('阴宅仓库')} 个人存储空间（在阴宅位置使用）\n"
        "***\n"
        "> 💡 卡境界→先突破 | 战力低→先装备 | 药不够→炼丹或市场买\n"
        f"> {cmd('装备系统')} | {cmd('炼丹系统')} | {cmd('阴宅系统')} | {cmd('帮助', '帮助')} 返回"
    )
    await growth_module_cmd.finish(build_markdown(content))
```

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/player/help.py
git commit -m "feat(help): 成长核心模块改用原生Markdown蓝字交互"
```

---

### Task 5: 改造「资源获取」模块

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py:155-202` (handle_resource_module)

- [ ] **Step 1: 改造 handle_resource_module**

```python
@resource_module_cmd.handle()
async def handle_resource_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 资源获取\n"
        "钱和材料从哪来？统统在这里\n"
        "***\n"
        "**💼 稳定收入 - 打工**\n"
        f"{cmd('打工')} 查看可用工作 → {cmd('打工 工作名', '打工 ')} 开始 → {cmd('收工')} 领钱\n"
        f"{cmd('工作地点')} 查看所有工作地点\n"
        "***\n"
        "**📋 任务奖励 - 委托**\n"
        f"{cmd('每日委托')} 查看今日委托 → {cmd('接取委托 编号', '接取委托 ')} → {cmd('完成委托')}\n"
        "***\n"
        "**🌀 副本掉落 - 诡域**\n"
        f"{cmd('进入 1层诡域', '进入 ')} 进入副本 → {cmd('探索')} 探索格子 → {cmd('领取宝箱')} 领奖\n"
        f"{cmd('返回')} 回到现实世界\n"
        "***\n"
        "**🗺️ 地图探索**\n"
        f"{cmd('地图')} 查看地点 | {cmd('导航 地点名', '导航 ')} 前往 | {cmd('观察')} 查看周围\n"
        "***\n"
        "**🎣 钓鱼** {cmd('钓鱼')} (5分钟冷却) | {cmd('鱼栏')} 查看存量\n"
        f"**🍳 餐厅** {cmd('创建餐厅')} 开店 | {cmd('餐厅')} 查看状态\n"
        f"**🌱 灵田** {cmd('灵田')} 查看 | {cmd('收菜')} 收获 | {cmd('菜市场')} 查看市价\n"
        "***\n"
        "> 💡 缺钱→打工/跑商 | 缺材料→副本/委托 | 缺药→炼丹/买\n"
        f"> {cmd('打工系统')} | {cmd('副本系统')} | {cmd('钓鱼系统')} | {cmd('灵田系统')} | {cmd('宠物系统')} | {cmd('帮助', '帮助')} 返回"
    )
    await resource_module_cmd.finish(build_markdown(content))
```

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/player/help.py
git commit -m "feat(help): 资源获取模块改用原生Markdown蓝字交互"
```

---

### Task 6: 改造「战斗挑战」模块

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py:205-235` (handle_battle_module)

- [ ] **Step 1: 改造 handle_battle_module**

```python
@battle_module_cmd.handle()
async def handle_battle_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 战斗挑战\n"
        "打谁、掉什么、风险是什么\n"
        "***\n"
        "**⚔️ PVE - 打怪**\n"
        f"{cmd('攻击 NPC名', '攻击 ')} 攻击怪物/NPC\n"
        "荒野/诡域：真实战斗，死亡掉落 | 城镇安全区：只能切磋\n"
        "***\n"
        "**🤝 PVP - 对战**\n"
        f"{cmd('切磋 UID', '切磋 ')} 友好切磋（无损失）\n"
        f"{cmd('攻击 UID', '攻击 ')} 真实战斗（荒野/诡域限定）\n"
        "***\n"
        "**🌟 世界BOSS**\n"
        f"{cmd('世界BOSS')} 查看信息 | {cmd('讨伐BOSS')} 攻击(每日3次) | {cmd('BOSS排行')} 排行\n"
        "***\n"
        "**📊 查看战力**\n"
        f"{cmd('战力')} 完整战斗属性 | {cmd('战力说明')} 属性作用 | {cmd('死斗日志')} 战斗记录\n"
        "***\n"
        "> 💡 战斗核心：攻击/防御/暴击/连击/闪避/反击，装备和丹药是关键\n"
        f"> {cmd('战斗系统')} 详细说明 | {cmd('帮助', '帮助')} 返回"
    )
    await battle_module_cmd.finish(build_markdown(content))
```

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/player/help.py
git commit -m "feat(help): 战斗挑战模块改用原生Markdown蓝字交互"
```

---

### Task 7: 改造「经济市场」帮助模块

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py:238-289` (handle_economy_module)

- [ ] **Step 1: 改造 handle_economy_module**

```python
@economy_module_cmd.handle()
async def handle_economy_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 经济市场\n"
        "所有跟钱有关的，都在这里\n"
        "***\n"
        "**🏦 银行**\n"
        f"{cmd('存 金额', '存 ')} 存入 | {cmd('取 金额', '取 ')} 取出 | {cmd('余额')} 查询 | {cmd('转账 UID 金额', '转账 ')} 转账(3%手续费)\n"
        "***\n"
        "**🏪 跑商**\n"
        f"{cmd('市集')} 当前市场 | {cmd('市价 物品名', '市价 ')} 比价 | {cmd('跑商推荐')} 盈利路线\n"
        f"{cmd('购买 物品 数量', '购买 ')} 买入 | {cmd('出售 物品 数量', '出售 ')} 卖出 | {cmd('自动出售')} 一键卖\n"
        f"{cmd('市集列表')} 所有市集 | {cmd('黑市')} 特殊商品 | {cmd('交易限制')} 冷却状态\n"
        "***\n"
        "**📈 气运投资（高风险）**\n"
        f"{cmd('投资行情')} 查看价格 | {cmd('我的投资')} 持仓\n"
        f"{cmd('投资气运 代码 数量', '投资气运 ')} 买入 | {cmd('出售气运 代码 数量', '出售气运 ')} 卖出\n"
        "***\n"
        "**💎 银行理财**\n"
        f"{cmd('定期理财')} 七日定存(5%周利率) | {cmd('购买定期 金额', '购买定期 ')} 买入 | {cmd('我的定期')} 持仓\n"
        f"{cmd('理财产品')} 活期理财 | {cmd('购买理财 金额', '购买理财 ')} 买入 | {cmd('我的理财')} 持仓\n"
        "***\n"
        "**🔄 玩家交易（挂牌市场）**\n"
        f"{cmd('交易清单')} 在售物品 | {cmd('我的挂牌')} 我的牌子\n"
        f"{cmd('挂牌 出售 物品 单价 数量', '挂牌 ')} 挂牌 | {cmd('撤牌 ID', '撤牌 ')} 撤回\n"
        "***\n"
        "**🏛️ 拍卖行**\n"
        f"{cmd('拍卖行')} 查看拍卖 | {cmd('出价 拍卖ID 金额', '出价 ')} 竞价\n"
        "***\n"
        "> 💡 新手赚钱推荐：{cmd('打工')}(稳) → {cmd('跑商推荐', '跑商推荐')}(中) → {cmd('投资行情', '投资行情')}(险)\n"
        f"> {cmd('经济系统')} | {cmd('投资系统')} | {cmd('拍卖行系统')} | {cmd('帮助', '帮助')} 返回"
    )
    await economy_module_cmd.finish(build_markdown(content))
```

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/player/help.py
git commit -m "feat(help): 经济市场帮助模块改用原生Markdown蓝字交互"
```

---

### Task 8: 改造「社交公会」模块

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py:292-337` (handle_social_module)

- [ ] **Step 1: 改造 handle_social_module**

```python
@social_module_cmd.handle()
async def handle_social_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 社交公会\n"
        "结伴江湖，建立羁绊\n"
        "***\n"
        "**🎁 送礼系统**\n"
        f"{cmd('礼物商店')} 查看 → {cmd('买礼物 礼物名 数量', '买礼物 ')} 购买 → {cmd('赠礼 UID 礼物名 数量', '赠礼 ')} 赠送\n"
        f"{cmd('好感度 UID', '好感度 ')} 查看好感度\n"
        "***\n"
        "**💒 结婚/结义/师徒**（需前往上京(0,0)找NPC）\n"
        f"{cmd('交互 月老 求婚 UID', '交互 月老 求婚 ')} 求婚\n"
        f"{cmd('交互 结义使者 结义 UID', '交互 结义使者 结义 ')} 结义\n"
        f"{cmd('交互 师徒使者 拜师 UID', '交互 师徒使者 拜师 ')} 拜师\n"
        "***\n"
        "**🕯️ 香火商店** {cmd('香火商店')} | {cmd('买食谱 食谱名', '买食谱 ')} 购买食谱\n"
        "***\n"
        "**🏰 公会**\n"
        f"{cmd('公会列表')} 查看 | {cmd('加入公会 ID', '加入公会 ')} 申请 | {cmd('我的公会')} 信息\n"
        f"{cmd('公会建筑')} 建筑加成 | {cmd('捐献金币 金额', '捐献金币 ')} 捐献获积分\n"
        "***\n"
        "**💬 消息** {cmd('消息')} 世界频道 | {cmd('发消息 内容', '发消息 ')} 发言 | {cmd('私信 UID 内容', '私信 ')} 私信\n"
        f"**🧧 红包** {cmd('发红包 金额 份数', '发红包 ')} 发红包 | {cmd('抢红包')} 抢红包\n"
        "***\n"
        "> 💡 好感度5000可结婚/结义\n"
        f"> {cmd('社交系统')} | {cmd('公会系统')} | {cmd('帮助', '帮助')} 返回"
    )
    await social_module_cmd.finish(build_markdown(content))
```

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/player/help.py
git commit -m "feat(help): 社交公会模块改用原生Markdown蓝字交互"
```

---

### Task 9: 改造「图鉴记录」模块

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py:340-370` (handle_info_module)

- [ ] **Step 1: 改造 handle_info_module**

```python
@info_module_cmd.handle()
async def handle_info_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 图鉴记录\n"
        "查看数据、排行榜、收集图鉴\n"
        "***\n"
        "**📚 物品图鉴**\n"
        f"{cmd('图鉴 物品名', '图鉴 ')} 查看物品信息 | {cmd('钓鱼图鉴')} 鱼类图鉴\n"
        "***\n"
        "**🏆 排行榜** {cmd('排行榜')} 总览\n"
        f"{cmd('财富榜')} | {cmd('修为榜')} | {cmd('幸运榜')} | {cmd('探索榜')}\n"
        f"{cmd('敏捷榜')} | {cmd('魅力榜')} | {cmd('钓鱼排行')} | {cmd('BOSS排行')}\n"
        "***\n"
        "**🎯 成就系统**\n"
        f"{cmd('成就')} 查看所有成就 | {cmd('成就 成就名', '成就 ')} 查看详情（自动触发，达成即解锁）\n"
        "***\n"
        "**📊 个人记录**\n"
        f"{cmd('面板')} 角色面板 | {cmd('完整面板')} 详细面板\n"
        f"{cmd('打工记录')} | {cmd('钓鱼记录')} | {cmd('投资记录')} | {cmd('委托统计')} | {cmd('打工统计')}\n"
        "***\n"
        f"> {cmd('玩家系统')} 更多指令 | {cmd('帮助', '帮助')} 返回"
    )
    await info_module_cmd.finish(build_markdown(content))
```

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/player/help.py
git commit -m "feat(help): 图鉴记录模块改用原生Markdown蓝字交互"
```

---

### Task 10: 改造「福利娱乐」模块

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py:373-415` (handle_fun_module)

- [ ] **Step 1: 改造 handle_fun_module**

```python
@fun_module_cmd.handle()
async def handle_fun_module(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 福利娱乐\n"
        "签到、小游戏、休闲玩法\n"
        "***\n"
        "**🎯 每日福利**\n"
        f"{cmd('签到')} 每日签到领奖 | {cmd('月卡')} 月卡状态 | {cmd('邀请码')} 邀请好友\n"
        "***\n"
        "**🎮 小游戏**\n"
        f"{cmd('抽签 你的问题', '抽签 ')} 观音灵签 | {cmd('答案之书 你的问题', '答案之书 ')} 宇宙智慧\n"
        f"{cmd('驾考题目')} 随机驾考题 | {cmd('恶魔轮盘帮助')} PVP博弈\n"
        f"{cmd('猜拳 石头 金额', '猜拳 ')} 猜拳鬼(仅周六) | {cmd('试炼列表')} 互动剧情\n"
        "***\n"
        "**🎉 休闲功能**\n"
        f"{cmd('每日一言')} 名言 | {cmd('今天吃什么')} 随机食谱 | {cmd('微博热搜')} 热搜\n"
        "***\n"
        "**🎁 抽奖** {cmd('参与抽奖 ID', '参与抽奖 ')} 参与 | {cmd('我的抽奖')} 记录\n"
        "***\n"
        "**🏰 天灾玩法**\n"
        f"{cmd('降临')} 降临下位世界 | {cmd('镇守')} 山寨状态 | {cmd('迎战')} 与英雄战斗\n"
        f"{cmd('侦查')} 查看英雄(消耗10天灾点) | {cmd('天灾商店')} 兑换福利\n"
        "***\n"
        f"> {cmd('娱乐系统')} | {cmd('抽奖系统')} | {cmd('天灾系统')} | {cmd('帮助', '帮助')} 返回"
    )
    await fun_module_cmd.finish(build_markdown(content))
```

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/player/help.py
git commit -m "feat(help): 福利娱乐模块改用原生Markdown蓝字交互"
```

---

### Task 11: 改造二级帮助 —「经济系统」详细帮助

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py:418-471` (handle_economy)

- [ ] **Step 1: 改造 handle_economy**

```python
@economy_cmd.handle()
async def handle_economy(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 经济系统\n"
        "管理金币、跑商赚钱、银行理财\n"
        "***\n"
        "## 🏦 银行系统\n"
        f"{cmd('存 金额', '存 ')} 存入冥行（不产生利息）\n"
        f"{cmd('取 金额', '取 ')} 取出存款\n"
        f"{cmd('余额')} 查询存款余额\n"
        f"{cmd('转账 UID 金额', '转账 ')} 银行转账（手续费3%）\n"
        "***\n"
        "## 🏪 跑商系统\n"
        f"{cmd('市集')} 当前市场商品价格 | {cmd('市集列表')} 所有市集坐标\n"
        f"{cmd('市价 物品名', '市价 ')} 各市集买卖价格 | {cmd('市集详情', '市集详情 ')} 指定市集报价\n"
        f"{cmd('购买 物品名 数量', '购买 ')} 购买 | {cmd('出售 物品名 数量', '出售 ')} 出售 | {cmd('自动出售')} 一键卖出\n"
        f"{cmd('跑商推荐')} 盈利路线 | {cmd('跑商记录')} 交易历史 | {cmd('交易限制')} 冷却状态\n"
        f"{cmd('黑市')} 特殊商品\n"
        "***\n"
        "**⚠️ 跑商机制**\n"
        "- 同一地点买的商品4小时内不能原地卖\n"
        "- 市集每6小时自动补货\n"
        "- 同商品买越多越贵(50个后加价)\n"
        "- 每日前3笔跑商奖励10%，之后递减\n"
        "***\n"
        "## 💎 理财产品\n"
        f"{cmd('理财产品')} 活期理财（随存随取） | {cmd('我的理财')} 持仓\n"
        f"{cmd('购买理财 金额', '购买理财 ')} 买入活期 | {cmd('赎回理财 编号', '赎回理财 ')} 赎回\n"
        f"{cmd('定期理财')} 七日定存(5%周利率) | {cmd('我的定期')} 持仓\n"
        f"{cmd('购买定期 金额', '购买定期 ')} 买入定存(锁7天) | {cmd('赎回定期 编号', '赎回定期 ')} 赎回\n"
        "***\n"
        "> 💡 新手快速赚钱：{cmd('打工')}(稳) → {cmd('跑商推荐', '跑商推荐')}(中) → 副本探索(材料)\n"
        f"> {cmd('投资系统')} 高风险投资 | {cmd('经济市场')} 返回 | {cmd('帮助', '帮助')} 主菜单"
    )
    await economy_cmd.finish(build_markdown(content))
```

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/player/help.py
git commit -m "feat(help): 经济系统详细帮助改用原生Markdown蓝字交互"
```

---

### Task 12: 改造二级帮助 —「投资系统」详细帮助

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py:474-531` (handle_investment)

- [ ] **Step 1: 改造 handle_investment**

```python
@investment_cmd.handle()
async def handle_investment(event: MessageEvent, args: Message = CommandArg()):
    content = (
        "# 气运投资系统\n"
        "修仙界的气运交易，高风险高收益\n"
        "***\n"
        "## 📋 基本命令\n"
        f"{cmd('投资行情')} 所有气运及灵力指数\n"
        f"{cmd('投资刷新时间')} 价格刷新时间\n"
        f"{cmd('投资气运 代码 数量', '投资气运 ')} 买入（末尾加\"银行\"从银行扣款）\n"
        f"{cmd('出售气运 代码 数量', '出售气运 ')} 卖出\n"
        f"{cmd('我的投资')} 持仓和灵力预警\n"
        f"{cmd('投资记录')} 交易记录 | {cmd('气运事件')} 黑天鹅事件\n"
        "***\n"
        "## 🎮 新手快速入门（3步）\n"
        f"1. {cmd('投资行情')} 找灵力充沛的(绿光🟢)\n"
        f"2. {cmd('投资气运 代码 10', '投资气运 ')} 买10份试水(100金币以内)\n"
        "3. 等1小时价格涨了就卖，跌了等等看\n"
        "***\n"
        "## ⚠️ 风险必读\n"
        "**灵力指数系统**\n"
        "- 🟢 绿光(70-100) 灵力充沛，可投资\n"
        "- 🟡 黄光(30-69) 灵力不稳，需谨慎\n"
        "- 🔴 红光(0-29) 濒临枯竭，快出手！\n"
        "- 💀 灵力归零 = 气运消散，钱全没了\n"
        "\n"
        "**费用**\n"
        "- 💸 保管费：每天0.1%（1000金扣1金）\n"
        "- 💰 手续费：买+卖总共1%\n"
        "- 🌪 黑天鹅：每周15%概率暴跌40-50%\n"
        "***\n"
        "## 💡 防坑指南\n"
        "- ❌ 别all in！只用愿意输的钱\n"
        "- ❌ 别只买一种！分散投资降风险\n"
        "- ✅ 红光🔴赶紧出手 | 赚了就跑别贪心\n"
        "- ✅ 短期(1-2周)比长持好\n"
        "***\n"
        f"> {cmd('经济系统')} 银行/跑商 | {cmd('经济市场')} 返回 | {cmd('帮助', '帮助')} 主菜单"
    )
    await investment_cmd.finish(build_markdown(content))
```

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/player/help.py
git commit -m "feat(help): 投资系统详细帮助改用原生Markdown蓝字交互"
```

---

### Task 13: 改造剩余二级帮助模块（批量）

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py` — 剩余所有二级帮助 handler

需要改造的剩余二级帮助（约 20 个），每个 handler 的改造模式相同：
1. 将 `msg = (...)` 中的纯文本改为原生 Markdown
2. 所有 `【命令】` 替换为 `cmd('命令')` 蓝字
3. 末尾添加返回导航蓝字
4. `finish(Message(msg))` 改为 `finish(build_markdown(content))`

**需改造的 handler 列表**：

| handler 函数 | 触发命令 | help.py 大致行号 |
|-------------|---------|----------------|
| handle_fishing | 钓鱼系统 | ~534 |
| handle_cooking | 烹饪系统 | ~584 |
| handle_equip_help | 装备系统 | 需查找 |
| handle_alchemy | 炼丹系统 | 需查找 |
| handle_mansion | 阴宅系统 | 需查找 |
| handle_battle_system | 战斗系统 | 需查找 |
| handle_social_system | 社交系统 | 需查找 |
| handle_guild_system | 公会系统 | 需查找 |
| handle_dungeon | 副本系统 | 需查找 |
| handle_parttime | 打工系统 | 需查找 |
| handle_spirit_field | 灵田系统 | 需查找 |
| handle_pet | 宠物系统 | 需查找 |
| handle_lottery | 抽奖系统 | 需查找 |
| handle_disaster | 天灾系统 | 需查找 |
| handle_inner_realm | 里界系统 | 需查找 |
| handle_entertainment | 娱乐系统 | 需查找 |
| handle_trade_system | 交易系统 | 需查找 |
| handle_auction_system | 拍卖行系统 | 需查找 |
| handle_player_system | 玩家系统 | 需查找 |
| handle_newbie_guide | 新手指引 | 需查找 |

- [ ] **Step 1: 逐个改造所有剩余 handler**

对每个 handler，遵循相同模式：
- 标题用 `#`
- 分组用 `##` 或 `**粗体**`
- 分隔用 `***`
- 命令用 `cmd()` 蓝字
- 带参数命令 `text` 末尾留空
- 末尾用 `>` 引用提供导航蓝字

- [ ] **Step 2: 整体验证**

逐个发送所有帮助命令，确认格式和蓝字正常。

- [ ] **Step 3: Commit**

```bash
git add plugins/xiuxian_game/player/help.py
git commit -m "feat(help): 所有二级帮助模块全面改用原生Markdown蓝字交互"
```

---

## Phase 2: 经济系统改造

### 文件变动总览

| 操作 | 文件路径 | 说明 |
|------|---------|------|
| Modify | `plugins/xiuxian_game/economy/bank.py` | 银行系统 |
| Modify | `plugins/xiuxian_game/economy/bank_fund_commands.py` | 理财产品 |
| Modify | `plugins/xiuxian_game/economy/stock_commands.py` | 股票投资 |
| Modify | `plugins/xiuxian_game/economy/market.py` | 交易市场 |
| Modify | `plugins/xiuxian_game/economy/merchants.py` | 跑商系统 |
| Modify | `plugins/xiuxian_game/economy/part_time_job_commands.py` | 打工系统 |
| Modify | `plugins/xiuxian_game/economy/token_exchange.py` | 代币兑换 |

### 经济系统 Markdown 设计原则

1. **数字数据用加粗** — `**1,500** 金币` 而非普通文本
2. **操作结果后给后续蓝字** — 买完股票后给"查看持仓"蓝字
3. **列表数据保持整齐** — 用无序列表或表格展示
4. **错误消息也要蓝字** — 余额不足时给"余额"蓝字查看
5. **商品名即蓝字** — 列表中每个商品/股票名本身就是蓝字，点击后直接补全购买命令（如 `show="金表"` `text="购买 金表 "`），用户只需补数量。同理出售、投资等场景都遵循此原则。所有出现实体名称的地方（商品、股票代码、牌子ID、工作名）都应做成蓝字，点击后自动填充对应操作命令。

---

### Task 14: 改造银行系统

**Files:**
- Modify: `plugins/xiuxian_game/economy/bank.py`

- [ ] **Step 1: 添加 import**

在文件顶部添加：
```python
from ..utils_markdown import cmd, build_markdown
```

- [ ] **Step 2: 改造余额查询**

将余额输出改为原生 Markdown：
```python
# 余额查询结果
content = (
    f"# 🏦 冥界银行\n"
    f"***\n"
    f"💰 当前存款：**{balance:,}** 金币\n"
    f"***\n"
    f"{cmd('存 金额', '存 ')} | {cmd('取 金额', '取 ')} | {cmd('转账 UID 金额', '转账 ')} | {cmd('银行投资')}\n"
)
await balance_cmd.finish(build_markdown(content))
```

- [ ] **Step 3: 改造存款/取款**

成功消息末尾添加后续操作蓝字：
```python
content = (
    f"# 🏦 存款成功\n"
    f"***\n"
    f"💰 存入：**{amt:,}** 金币\n"
    f"💳 当前存款：**{balance:,}** 金币\n"
    f"***\n"
    f"{cmd('余额')} | {cmd('取 金额', '取 ')} | {cmd('转账 UID 金额', '转账 ')} | {cmd('帮助', '帮助')}\n"
)
```

- [ ] **Step 4: 改造转账**

```python
content = (
    f"# 💸 转账成功\n"
    f"***\n"
    f"💰 转账金额：**{amt:,}** 金币\n"
    f"💸 手续费：**{tax:,}** 金币 (3%)\n"
    f"💎 实际到账：**{actual:,}** 金币\n"
    f"👤 收款人：{receiver.nickname}[UID:{receiver.uid}]\n"
    f"💳 剩余存款：**{balance:,}** 金币\n"
    f"***\n"
    f"{cmd('余额')} | {cmd('存 金额', '存 ')} | {cmd('帮助', '帮助')}\n"
)
```

- [ ] **Step 5: 改造存款榜**

```python
content = (
    f"# 🏦 存款排行榜\n"
    f"你的排名：第 **{rank}** 名\n"
    f"***\n"
    # 循环生成排名行
    f"{medal} {nickname}[UID:{uid}] - **{balance:,}** 💰\n"
    # ...
    f"***\n"
    f"{cmd('存款榜 2', '存款榜 ')} 下一页 | {cmd('余额')} | {cmd('帮助', '帮助')}\n"
)
```

- [ ] **Step 6: Commit**

```bash
git add plugins/xiuxian_game/economy/bank.py
git commit -m "feat(economy): 银行系统改用原生Markdown蓝字交互"
```

---

### Task 15: 改造跑商系统

**Files:**
- Modify: `plugins/xiuxian_game/economy/merchants.py`

- [ ] **Step 1: 添加 import**

- [ ] **Step 2: 改造市集命令**

市集商品展示，**每个商品名本身就是蓝字，点击直接补全购买命令**：
```python
# 动态生成商品行：商品名蓝字 → 点击输入 "购买 金表 "
# 用户只需补数量即可完成购买
items_lines = []
for item_name, price, stock in goods:
    stock_icon = "🟢充足" if stock > 10 else "🟡有限" if stock > 0 else "🔴售罄"
    items_lines.append(
        f"- {cmd(item_name, f'购买 {item_name} ')} | 售价 **{price}** | 库存({stock}){stock_icon}"
    )

# 收购商品行：商品名蓝字 → 点击输入 "出售 玉镯 "
sell_lines = []
for item_name, buy_price in buy_goods:
    sell_lines.append(
        f"- {cmd(item_name, f'出售 {item_name} ')} | 收价 **{buy_price}**"
    )

content = (
    f"# 🏪 {market_name} ({x},{y})\n"
    f"***\n"
    f"**📦 可购买商品**（点击商品名直接购买）\n"
    + "\n".join(items_lines) + "\n"
    f"***\n"
    f"**💰 收购商品**（点击商品名直接出售）\n"
    + "\n".join(sell_lines) + "\n"
    f"***\n"
    f"{cmd('自动出售')} 一键卖 | {cmd('市集列表')} | {cmd('跑商推荐')} | {cmd('经济市场')}\n"
)
```

**核心技巧**：`cmd('金表', '购买 金表 ')` — 用户看到蓝字"金表"，点击后输入框出现 `购买 金表 `，只需补数量回车。出售同理：`cmd('玉镯', '出售 玉镯 ')`。

- [ ] **Step 3: 改造跑商推荐**

盈利路线展示，**商品名蓝字点击即购买/出售，目的地蓝字点击即导航**：
```python
content = (
    f"# 📊 跑商推荐\n"
    f"***\n"
    # 每条路线
    f"**路线{i}** 利润 **{profit}** 金\n"
    f"在 {cmd(from_market, f'导航 {from_market}')} 买 {cmd(item, f'购买 {item} ')}\n"
    f"到 {cmd(to_market, f'导航 {to_market}')} 卖 {cmd(item, f'出售 {item} ')}\n"
)
```

**效果**：用户看到 `在 [上京] 买 [金表]`，点"上京"→输入 `导航 上京`，点"金表"→输入 `购买 金表 `。

- [ ] **Step 4: 改造购买/出售结果**

购买成功后提供"导航到推荐出售市集"蓝字 + "自动出售"蓝字。
出售成功后提供"继续购买"蓝字 + "查看余额"蓝字。

- [ ] **Step 5: 改造其他命令**（市集列表、市价、跑商记录、交易限制、黑市、自动出售）

**市集列表**：每个市集名做成蓝字 → 点击输入 `导航 市集名`
**市价**：每行市集名做成蓝字 → 点击导航过去
**黑市**：商品名蓝字 → 点击输入 `购买 商品名 `

每个命令末尾提供相关后续操作蓝字。

- [ ] **Step 6: Commit**

```bash
git add plugins/xiuxian_game/economy/merchants.py
git commit -m "feat(economy): 跑商系统改用原生Markdown蓝字交互"
```

---

### Task 16: 改造股票投资系统

**Files:**
- Modify: `plugins/xiuxian_game/economy/stock_commands.py`

- [ ] **Step 1: 添加 import**

- [ ] **Step 2: 改造气运行情**

**股票名称本身就是蓝字，点击直接补全投资命令**：
```python
# 动态生成行情行：股票名蓝字 → 点击输入 "投资气运 XAI "
stock_lines = []
for symbol, name, price, trend_icon, health_icon in stocks:
    stock_lines.append(
        f"{cmd(name, f'投资气运 {symbol} ')} `{symbol}` "
        f"💰 **{price}** 金 {trend_icon} {health_icon} "
        f"| {cmd('历史', f'气运历史 {symbol}')}"
    )

content = (
    f"# 💎 气运投资行情\n"
    f"🔄 价格已更新（点击气运名直接投资）\n"
    f"***\n"
    + "\n".join(stock_lines) + "\n"
    f"***\n"
    f"{cmd('我的投资')} | {cmd('投资刷新时间')} | {cmd('气运事件')} | {cmd('经济市场')}\n"
)
```

**效果**：用户看到蓝字"法宝气运"，点击后输入框出现 `投资气运 XAI `，只需补数量回车。

- [ ] **Step 3: 改造我的投资**

**持仓股票名蓝字点击即出售**：
```python
# 股票名蓝字 → 点击输入 "出售气运 XAI "
f"{cmd(name, f'出售气运 {symbol} ')} `{symbol}` "
f"📦 **{shares}** 股 | 成本 **{avg_cost}** | 现价 **{price}** | 浮盈 **{profit}**\n"
```

- [ ] **Step 4: 改造其他命令**（投资/出售结果、投资记录、刷新时间、气运历史、气运分析、气运事件）

- [ ] **Step 5: Commit**

```bash
git add plugins/xiuxian_game/economy/stock_commands.py
git commit -m "feat(economy): 股票投资系统改用原生Markdown蓝字交互"
```

---

### Task 17: 改造交易市场系统

**Files:**
- Modify: `plugins/xiuxian_game/economy/market.py`

- [ ] **Step 1: 添加 import**

- [ ] **Step 2: 改造挂牌命令**

挂牌成功后提供查看/撤回蓝字：
```python
content = (
    f"# 📈 挂牌成功\n"
    f"***\n"
    f"🆔 {order_id} | 📤 出售 {item_name} | 💰 {price} | 📦 {qty}\n"
    f"***\n"
    f"{cmd('我的挂牌')} | {cmd(f'撤牌 {order_id}')} 撤回 | {cmd('交易清单')} | {cmd('经济市场')}\n"
)
```

- [ ] **Step 3: 改造查牌/交易清单**

**牌子ID蓝字点击查看详情，物品名蓝字点击直接购买/出售**：
```python
# 出售牌子：物品名蓝字 → 点击输入 "购买 回春散 "（从卖家处购买）
f"📤 {cmd(item_name, f'购买 {item_name} ')} 🆔{cmd(str(order_id), f'挂牌详情 {order_id}')} | 💰 **{price}** | 📦 {qty}\n"

# 收购牌子：物品名蓝字 → 点击输入 "出售 还魂丹 "（卖给买家）
f"📥 {cmd(item_name, f'出售 {item_name} ')} 🆔{cmd(str(order_id), f'挂牌详情 {order_id}')} | 💰 **{price}** | 📦 {qty}\n"
```

**效果**：用户看到 `📤 [回春散] 🆔[123]`，点"回春散"→输入 `购买 回春散 `，点"123"→输入 `挂牌详情 123`。

- [ ] **Step 4: 改造其他命令**（撤牌、挂牌详情、我的挂牌、税率、估价）

- [ ] **Step 5: Commit**

```bash
git add plugins/xiuxian_game/economy/market.py
git commit -m "feat(economy): 交易市场系统改用原生Markdown蓝字交互"
```

---

### Task 18: 改造打工系统

**Files:**
- Modify: `plugins/xiuxian_game/economy/part_time_job_commands.py`

- [ ] **Step 1: 添加 import**

- [ ] **Step 2: 改造打工列表**

**工作名本身就是蓝字，点击直接开始打工**：
```python
# 动态生成工作列表：工作名蓝字 → 点击输入 "打工 便利店收银员"
job_lines = []
for job_name, income, duration, desc in available_jobs:
    job_lines.append(
        f"- {cmd(job_name, f'打工 {job_name}')} 💰 **{income}** 金 | ⏰ {duration}"
    )

content = (
    f"# 💼 {location_name} ({x},{y})\n"
    f"***\n"
    f"**可用工作**（点击工作名直接开始）\n"
    + "\n".join(job_lines) + "\n"
    f"***\n"
    f"{cmd('工作地点')} | {cmd('打工记录')} | {cmd('打工统计')} | {cmd('帮助', '帮助')}\n"
)
```

**效果**：用户看到蓝字"便利店收银员"，点击后直接输入 `打工 便利店收银员`，无需打字。

- [ ] **Step 3: 改造打工/收工结果**

打工成功后给 {cmd('收工')} 蓝字 + {cmd('工作状态')} 蓝字。
收工后给 {cmd('打工')} 再来一次蓝字 + {cmd('余额')} 查看金币蓝字。

- [ ] **Step 4: 改造其他命令**（工作状态、工作地点、打工记录、打工统计）

- [ ] **Step 5: Commit**

```bash
git add plugins/xiuxian_game/economy/part_time_job_commands.py
git commit -m "feat(economy): 打工系统改用原生Markdown蓝字交互"
```

---

### Task 19: 改造理财产品系统

**Files:**
- Modify: `plugins/xiuxian_game/economy/bank_fund_commands.py`

- [ ] **Step 1: 添加 import**

- [ ] **Step 2: 改造所有 handler**

理财产品列表、购买/赎回结果、我的持仓 — 全部改用原生 Markdown，关键数字加粗，操作做蓝字。

- [ ] **Step 3: Commit**

```bash
git add plugins/xiuxian_game/economy/bank_fund_commands.py
git commit -m "feat(economy): 理财产品系统改用原生Markdown蓝字交互"
```

---

### Task 20: 改造代币兑换系统

**Files:**
- Modify: `plugins/xiuxian_game/economy/token_exchange.py`

- [ ] **Step 1: 改造 handler**

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/economy/token_exchange.py
git commit -m "feat(economy): 代币兑换系统改用原生Markdown蓝字交互"
```

---

### Task 21: 同步更新帮助信息和知识库

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py` — 如有遗漏
- Modify: `plugins/xiuxian_game/data/knowledge/economy_system_help.yaml`
- Modify: `plugins/xiuxian_game/data/knowledge/investment_help.yaml`
- Modify: 其他受影响的 YAML 知识库文件

- [ ] **Step 1: 同步帮助文本到 YAML 知识库**

按照 project-rules，更新对应 YAML 文件的 `body` 字段。注意：YAML 中存的是纯文本供 AI 检索，不需要包含 `<qqbot-cmd-input>` 标签，保持人类可读的命令格式即可。

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/data/knowledge/
git commit -m "docs: 同步经济系统帮助文本到AI知识库YAML"
```

---

## 注意事项

### QQ 原生 Markdown 已知限制
1. **换行必须用 `\r`** — `build_markdown()` 已自动处理
2. **部分 Markdown 语法可能不渲染** — 表格、代码块、数学公式需实际测试确认
3. **`<qqbot-cmd-input>` 标签中不能有换行** — 每个标签必须在一行内
4. **内容长度可能有限制** — 超长消息需考虑分页

### 测试检查清单
- [ ] 所有蓝字点击后输入正确命令
- [ ] 带参数命令蓝字点击后光标在末尾，用户可直接输入参数
- [ ] Markdown 标题、加粗、分割线、引用正常渲染
- [ ] 链接可点击跳转
- [ ] 无序列表正常渲染
- [ ] 消息不超长导致发送失败

---

**预计工作量**：21 个 Task，帮助系统 13 个 + 经济系统 8 个
**预计文件变动**：约 10 个文件，~3000 行代码改动
