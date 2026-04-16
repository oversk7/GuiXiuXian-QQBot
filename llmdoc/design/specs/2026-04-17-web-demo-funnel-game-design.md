# 网页引流小游戏 — 诡修仙·命悬一线 设计

> **背景**: 诡修仙2 是 QQ 机器人文字 RPG，通过机器人传播受限（用户要先进群/加机器人、群聊对新人不友好）。为扩大知名度，在 `oversky.online` 上架一个**完全独立的网页小游戏**，作为「世界观试吃」引流到 QQ 机器人注册。
>
> **产品定位**: 这不是机器人的网页版，也不共享玩家数据。是一个 8-15 分钟能玩完的单机 Web 文字冒险，用 诡修仙2 的世界观做外衣，用 永夜庇护所 的美学做底子，结尾把玩家送到 QQ 机器人门口。
>
> **关键原则**: 0 注册摩擦（不要账号、不要 Cookie 追踪）、可分享（手机友好 + 生成可晒图）、低维护（内容 YAML 驱动、故事可热更）、强漏斗（结尾 CTA + 一次性邀请码兑换新手礼包）。

---

## 1. 目标与非目标

### 1.1 目标
1. **拉新**：让没接触过 QQ 群的潜在玩家体验 诡修仙2 的氛围，促成他们去添加机器人
2. **传播**：生成漂亮的"命格结局卡"，激励玩家分享到朋友圈/QQ 空间/微博
3. **留量**：一次性邀请码 → 机器人新手礼包兑换（让"看过"的用户真正进入游戏）
4. **轻维护**：故事内容 YAML 驱动，运营同学（或作者本人）能在不改代码的情况下扩展剧情

### 1.2 非目标（明确不做）
- ❌ 账号登录/绑定（之前被废弃的 P0 方向）
- ❌ 与机器人数据同步（网页结果不影响真实玩家存档）
- ❌ 长期养成（不做 idle，不做排行榜，不做签到）
- ❌ 支付/充值
- ❌ 国际化（只做中文简体）
- ❌ 复杂 UI 框架（React/Vue 一律不上）
- ❌ PNG 图集成（保持 永夜 的纯文字风，节省带宽和维护成本）

---

## 2. 关键决策（已锁定）

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 游戏类型 | 分支文字冒险 + 一次简化回合制战斗 + 一次突破事件 | 展示 诡修仙2 核心钩子（世界观/战斗/突破）的最小切片；开发成本低；符合 永夜 文字驱动风格 |
| 单局时长 | 8-15 min | 够讲一个完整故事、够触发关键体验；短于 QQ 群聊常规会话时长，不会让人中途跑掉 |
| 风格基准 | 沿用 永夜庇护所 的"阴冷 + 希望"基调 + 诡修仙2 的修仙词汇 | 两个 IP 共享 `诡` 字族词典；视觉上不做 PNG，只用 CSS + SVG + 极简动效 |
| 状态持久化 | localStorage（浏览器本地） | 0 后端会话，刷新不丢进度；跨设备不同步是可接受损耗 |
| 结尾 CTA | 命格结局卡 + 一次性邀请码 + 跳转 QQ 机器人 | 邀请码在机器人里兑换「新手礼包」，形成"玩完就想登机器人验收奖励"的闭环 |
| 邀请码机制 | 12 位数字+字母码，机器人端 `/邀请码 xxx` 一次性核销 | 有身份验证价值（每个码可追溯出自哪次通关），新手礼包免费给 |
| 数据分析 | 匿名漏斗：session 开始/到达场景/结局/点击 CTA | IP 级频控，不收集 fingerprint / cookie ID |
| 内容格式 | `data/demo/story.yaml`（一份文件承载所有剧情/选择/结局） | 编辑友好，改文字不用重启（加载走缓存 + reload 端点） |
| 技术栈 | 纯 HTML + 原生 JS + 原生 CSS，挂在 NoneBot2 的 FastAPI 上 | 与现有 `map.html / tower.html` 同风格，无构建链 |
| 可分享产物 | 结局页生成 HTML → html2canvas 转 PNG → 下载/直接复制 | 不依赖服务端渲染；中文字体内嵌 base64 保底 |
| 部署入口 | `/play` (登录页改叫 /login 仅内部使用，这里是对外入口) | 短路径，易传播 |

---

## 3. 故事与玩法设计

### 3.1 剧情蓝图

**剧本名**：《诡修仙 · 命悬一线》

**开场**：
> 荒原上狂风呜咽。你挣扎着从地上坐起，灰褐色的天、龟裂的地，还有三步外那堆即将熄灭的篝火。
>
> 记忆碎片缓缓拼齐：你是陈家的旁支，被族老派来荒原边缘的"诡域裂隙"采集诡血——这是修仙的入门凭证，也是陈家对你的最后一次试炼。
>
> 袋里仅剩三枚诡石、一柄锈剑、半块干粮。夜幕将在 **一炷香**（游戏 12 分钟）后降临。

**场景图**（DAG，不是线性）：

```
                 ┌── 主道·商队遗骸 ──┐
  [启程·三岔口]──┼── 古庙·毒瘴废墟 ──┼──▶ [诡域入口]
                 └── 灰雾·险路孤行 ──┘
                                         │
                    ┌─ 诡物战斗 (必经) ─┘
                    ↓
                 [战斗胜] ──▶ [机缘·意外突破] ──▶ [抉择·三选一]
                    │                              │
                 [战斗败]                          ├─ 带血归城 (生还结局)
                    │                              ├─ 踏雾逐秘 (悲剧结局)
                    ▼                              └─ 同化诡物 (隐藏结局, 需特殊前置)
              [陨落结局]
```

**场景数**（MVP-1）：
- 启程（1）→ 三条探索分支（3）→ 汇流（1）→ 战斗（1）→ 突破机缘（1）→ 抉择（1）→ 结局（4 种）= **总 12 节点，12 段叙事文字**

### 3.2 单场景结构

每个场景包含：

```yaml
- id: scene_01_start
  title: 启程
  text: |
    荒原上狂风呜咽……（120-200 字，半文言）
  choices:
    - id: choice_main_road
      label: "顺主道走"
      goto: scene_02a_main_road
      hint: "稳妥,但陈家族老说荒原入夜必有异动"  # 可选,hover 显示
    - id: choice_temple
      label: "绕去东南的古庙废墟"
      goto: scene_02b_temple
      hint: "有毒瘴,但传闻废墟下有诡血脉"
    - id: choice_mist
      label: "径直钻入西北的灰雾"
      goto: scene_02c_mist
      hint: "凶险至极,非此路不可达诡域裂隙"
      require_flag: []          # 空 = 无前置条件
      grants:                   # 选择这条路会给玩家的属性/flag
        - flag: brave_path
        - item: 灰雾残符
        - stat_delta: {courage: +2, hp: -5}
```

- **state**: 客户端维护一个简单 state obj `{flags: [], items: [], stats: {hp, mp, courage, fortune}}`
- **choice.require_flag**: 若当前 state 不满足，选项置灰或隐藏（用于隐藏结局的前置）
- **text 支持简单占位符**: `{player_name}`, `{courage}` 等，便于剧情个性化

### 3.3 战斗设计（简化回合制）

**战斗不是真实战斗引擎**，而是一段高度简化的演示：

```
回合 1/3:
  ⚔️ 你举起锈剑,向"枯影诡"砍去。
  造成伤害 8 (敏捷判定: 成功)
  枯影诡反噬,撕裂你的肩膀。
  你承受伤害 12

   你: HP 28/40  |  枯影诡: HP 24/32

  [连击普攻]  [防御]  [使用诡石(还剩 2)]
```

- 3 个行动按钮
- 伤害值带小随机（±20%），但胜负结果**预设**（剧情需要的情况下强制胜）
- 玩家 HP ≤ 0 → `scene_ending_fall`（陨落结局）
- 胜利 → 继续走主线

**目的**：让玩家「感受」战斗节奏，而不是真的打一场平衡过的战斗。是 trailer，不是 demo。

### 3.4 突破事件（核心钩子）

战斗后，进入一个独立场景：

```
血从肩膀汩汩而出。你靠着峭壁滑坐下来,本以为会就此死去。

但袋中那枚自诡物身上砍下的诡血脉,忽然发烫——

滚烫的灵气沿着你的经脉倒灌而上,撕裂、重铸,你感到骨骼都在碎裂又重组。

不是死,是——

                ⚡  突   破  ⚡

你的境界从 [凡人·弱不禁风] 跨入 [腐体境·初入](随机)

获得天赋: [{ROLL_TALENT}]
```

- 展示 诡修仙2 的"突破爽感"
- 天赋随机 3-5 种（"铁骨""灵敏""血性""悟性""鬼力"），触发一次抽卡式的期待
- 天赋影响结局文案（并不影响游戏机制，纯文本个性化）

### 3.5 结局设计

四种结局：

| 结局 ID | 名称 | 触发条件 | 文案基调 |
|---------|------|---------|---------|
| `ending_return` | 带血归城 | 战斗胜 + 抉择「稳妥返回」 | 希望 / 踏实，"这只是你修仙之路的第一夜" |
| `ending_fall` | 诡域陨落 | 战斗败 / HP=0 | 悲剧美，"灰雾吞没你最后一丝灵气" |
| `ending_seek` | 踏雾逐秘 | 战斗胜 + 抉择「深入诡域」 | 未竟，"你的足迹消失在灰雾深处……" |
| `ending_taint` | 同化诡物 | 隐藏：三条支线都走过(多周目) + courage ≥ 10 + 战斗胜 + 抉择「吞噬诡血」 | 惊悚暗黑，"你已非人非鬼" |

所有结局都显示**命格结局卡**（§3.6）和 **CTA**。

### 3.6 命格结局卡（可分享）

结局页渲染一张卡片，供玩家截图/下载分享：

```
 ╔════════════════════════════╗
 ║     诡 修 仙 · 命 悬 一 线     ║
 ║                              ║
 ║  [角色头像-纯 CSS 符咒图]     ║
 ║                              ║
 ║  命格: 带血归城              ║
 ║  境界: 腐体境·初入            ║
 ║  天赋: 铁骨                  ║
 ║  选择路径: 主道 → 战斗 → 稳妥 ║
 ║  剩余灵气: 28                ║
 ║                              ║
 ║  ─────────────────           ║
 ║  邀请码: GW7X-Q3FB-5K2M      ║
 ║  在 QQ 机器人 @诡修仙2        ║
 ║  发送  /邀请码 GW7X-Q3FB-5K2M ║
 ║  领取入门礼包                 ║
 ║  ─────────────────           ║
 ║    oversky.online/play       ║
 ╚════════════════════════════╝
```

- 尺寸：竖版 720×1280（适配手机截图/朋友圈九宫格单张）
- 用 html2canvas 或 `<canvas>` 手绘：两种都在 spec 备选，实施时选 html2canvas（简单）
- 下载按钮 + 复制链接按钮
- 旁边独立"复制分享文案"按钮：`我在「诡修仙」活了一夜,带回「带血归城」的命格。邀请码 GW7X-Q3FB-5K2M,你要不要也来试试? oversky.online/play`

### 3.7 CTA（引流漏斗）

结局页底部常驻：

```
━━━━━━━━━━━━━━━━━━━━━━━━━
   你的故事才刚刚开始

   前往 QQ 机器人 @诡修仙2
   发送 /邀请码 GW7X-Q3FB-5K2M
   领取 [新手大礼包 + 首次突破保护符]

   [ 🔗 复制添加指引 ]   [ 📋 复制邀请码 ]
━━━━━━━━━━━━━━━━━━━━━━━━━
```

"复制添加指引" 点击后：
```
诡修仙2 机器人添加方式(三选一):
1. 微信扫码: [二维码图]
2. 点击链接: qun.qq.com/xxxxxx
3. QQ 搜索群号: 123456789
进群后发 "创建角色" 开始游戏
```

具体渠道在 `data/demo/cta.yaml` 配置，随时可改不动代码。

---

## 4. 技术架构

### 4.1 模块划分

全部新建在 `plugins/xiuxian_game/web_demo/`（独立于现有 web/ 与主游戏逻辑）：

```
plugins/xiuxian_game/web_demo/
  __init__.py          # 路由注册
  demo_api.py          # FastAPI 路由: /play, /api/demo/*, /api/invite/*
  story_loader.py      # YAML 解析 + 内存缓存 + /admin/reload 热更
  invite_service.py    # 邀请码生成/核销
  analytics.py         # 匿名漏斗事件记录
  static/
    play.html          # 主页面(含登录入口/故事容器/战斗容器/结局卡)
    play.css           # 样式(永夜风)
    play.js            # 状态机 + 故事渲染 + 战斗模拟 + 结局卡生成
    vendor/
      html2canvas.min.js  # 单文件,10 KB gzip
  data/
    story.yaml         # 剧情/选择/战斗/结局
    cta.yaml           # 添加机器人的渠道配置
```

新增数据库表（通过 `Base.metadata.create_all` 自动建）：

```python
class WebInviteCode(Base):
    __tablename__ = "web_invite_code"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)  # 如 GW7X-Q3FB-5K2M
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    ending_id: Mapped[str] = mapped_column(String(32))  # 记录该码来自哪个结局
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    redeemed_by_player_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("player.id"), nullable=True)
    ip_created: Mapped[str] = mapped_column(String(64), default="")


class WebDemoEvent(Base):
    """漏斗分析匿名事件(IP 已脱敏为 /24)"""
    __tablename__ = "web_demo_event"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    session_id: Mapped[str] = mapped_column(String(32), index=True)  # 客户端随机生成,非用户身份
    event: Mapped[str] = mapped_column(String(32))  # start / scene / battle / ending / invite_generated / cta_clicked
    detail: Mapped[str] = mapped_column(String(120), default="")  # scene_id / ending_id 等
    ip_masked: Mapped[str] = mapped_column(String(32), default="")  # 脱敏到 /24
```

两张表都在 90 天清理（`WebDemoEvent` 可更激进,30 天）。

### 4.2 API 端点

所有端点都无需登录；IP 速率限制沿用现有 `_RateLimiter`。

| Method | Path | 说明 | 速率 |
|--------|------|------|------|
| `GET`  | `/play` | 主页面 HTML（CSP nonce 注入，同现有模式） | 30/min/IP |
| `GET`  | `/api/demo/story` | 返回 `story.yaml` 的 JSON 格式（10 min 缓存） | 30/min/IP |
| `POST` | `/api/demo/event` | 上报漏斗事件 `{session_id, event, detail}` | 60/min/IP |
| `POST` | `/api/demo/invite` | 生成邀请码（body: `{session_id, ending_id, snapshot_json}`） | 5/min/IP，每 session 最多 1 次 |
| `POST` | `/api/invite/redeem` | **机器人端内部使用**，不暴露 public endpoint |  — |

**`/api/demo/invite` 返回**: `{code: "GW7X-Q3FB-5K2M"}`；该码记入 `web_invite_code` 表，未核销状态。

### 4.3 QQ 机器人端：`/邀请码` 命令

新建 `plugins/xiuxian_game/web_demo/invite_commands.py`：

```python
@on_command("邀请码", aliases={"邀请"}).handle()
async def redeem_invite(event: MessageEvent):
    code = extract_code(event.get_plaintext())
    if not code:
        await cmd.finish("用法: /邀请码 GW7X-Q3FB-5K2M")

    async with db_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await cmd.finish("请先创建角色: 发送 /创建角色 <道号>")

        result = await InviteService(session).redeem(code, player)
        await session.commit()

    if result.ok:
        await cmd.finish(
            f"✅ 邀请码兑换成功\n"
            f"🎁 获得新手大礼包 (金币 500 + 灵石 10 + 小还魂丹 ×3)\n"
            f"🛡️ 获得「首次突破保护符」(下次突破失败不扣除修为,仅限一次)"
        )
    else:
        await cmd.finish(f"❌ {result.reason}")
```

**礼包物品定义**（复用现有 items.yaml 与背包系统）：
- 500 金币：直接 `player.gold += 500`
- 10 灵石：直接 `player.spirit_stone += 10`
- 3 个 小还魂丹：`InventoryService.add_item(player, "xiaohuanhun_dan", 3)`
- 突破保护符：在 Player 上加一次性 flag `first_breakthrough_protection: bool`（新字段，走 auto_migrate）

**兑换规则**：
- 每个码一次性，核销后 `redeemed_at / redeemed_by_player_id` 填充，再次兑换返回"此码已使用"
- 每个玩家最多兑换 **3 次**邀请码（防止同一用户通过多次玩 demo 刷礼包；由 `player.demo_invite_redeemed_count` 字段记录，走 auto_migrate）
- 每个码 **30 天有效期**；过期码返回"此码已过期"
- 兑换成功写审计日志（复用 `web_auth_audit` 表概念，或新建 `invite_redeem_log` — 本 spec 倾向于后者，解耦）

### 4.4 前端状态机

`play.js` 核心：

```js
const state = {
  current_scene: "scene_01_start",
  flags: [],                 // ["brave_path", "saw_temple"]
  items: [],                 // [{id:"灰雾残符", name:"..."}]
  stats: {hp:40, mp:20, courage:5, fortune:3},
  choices_history: [],       // ["choice_mist", "choice_fight"]
  session_id: cryptoRandom(16),
}

// 单向流程
render(scene)
  ↓ 用户点击选择
applyGrants(choice.grants)
reportEvent("scene", scene.id)
  ↓
  if scene.type === "battle": enterBattle()
  else: goto(choice.goto)
```

localStorage key: `guixiuxian_demo_state_v1`，保存整个 state obj。加载页面时先尝试 restore，弹窗问"继续上次的冒险吗？"。

### 4.5 前端视觉风格（简述）

- 背景：深灰黑（#1a1820）+ 暗红点缀（#8b3a3a）+ 青铜金（#c9a968）
- 字体：中文 `STKaiti / 思源宋体`（回退到 serif）；英文/数字 `Cinzel`（装饰用）
- 纹理：CSS noise + 轻微 vignette，不加图
- 选项按钮：边框 1px 青铜色，hover 轻微发光 + 符咒纹 SVG 浮现
- 战斗场景：战报用等宽字体 + 淡雾动画（CSS filter）
- 切场景：200ms 淡出 → 200ms 淡入，不用滑动

参考 永夜 的 Markdown 战报美学，但因在浏览器里不受 QQ 富文本限制，可以更大胆用 CSS 效果。

---

## 5. 故事内容骨架（YAML 草稿）

`data/demo/story.yaml` 示例结构，方便后续写作同学接手：

```yaml
meta:
  title: "诡修仙 · 命悬一线"
  version: 1
  author: "默认作者"
  opening: |
    荒原上狂风呜咽。灰褐色的天、龟裂的地、还有三步外那堆即将熄灭的篝火……
    （约 150 字开场,见 §3.1）
  player_stats_init:
    hp: 40
    mp: 20
    courage: 5
    fortune: 3

scenes:
  scene_01_start:
    type: narrative
    text: |
      袋里仅剩三枚诡石、一柄锈剑、半块干粮……
    choices:
      - id: main_road
        label: "顺主道走"
        goto: scene_02a_main
        hint: "稳妥,但族老说荒原入夜必有异动"
      - id: temple
        label: "绕去东南的古庙废墟"
        goto: scene_02b_temple
        grants: {flags: [seen_temple]}
      - id: mist
        label: "径直钻入西北的灰雾"
        goto: scene_02c_mist
        grants: {flags: [brave_path], items: [灰雾残符], stats: {courage: +2, hp: -5}}

  # ... 11 个场景省略 ...

  scene_battle_ghost:
    type: battle
    enemy:
      name: 枯影诡
      hp: 32
      attack: 12
      defense: 2
    rounds_min: 2
    rounds_max: 4
    victory_goto: scene_breakthrough
    defeat_goto: ending_fall
    # 战斗内文本变体池
    attack_variants:
      - "你举起锈剑,向「{enemy}」砍去"
      - "你咬牙突进,剑光撕开雾气"
      # ...
    hit_variants:
      - "「{enemy}」反噬,撕裂你的肩膀"
      # ...

  scene_breakthrough:
    type: breakthrough
    realms_pool:
      - "腐体境·初入"
      - "血咒境·萌芽"  # 罕见,需 courage >= 8
    talents_pool:
      - {id: iron, name: 铁骨, weight: 3}
      - {id: agility, name: 灵敏, weight: 3}
      - {id: blood, name: 血性, weight: 2}
      - {id: wit, name: 悟性, weight: 2}
      - {id: ghost, name: 鬼力, weight: 1}  # 稀有
    goto: scene_final_choice

endings:
  ending_return:
    title: "带血归城"
    text: |
      黎明破开灰雾……
    mood: hope
  ending_fall:
    title: "诡域陨落"
    text: |
      灰雾吞没你最后一丝灵气……
    mood: tragic
  ending_seek:
    title: "踏雾逐秘"
    text: |
      你的足迹消失在灰雾深处……
    mood: unresolved
  ending_taint:
    title: "同化诡物"
    require:
      flags_all: [seen_temple, brave_path, main_road]  # 三条支线都走过
      stats_gte: {courage: 10}
    text: |
      你已非人非鬼……
    mood: horror
```

**撰稿要点**：
- 每段 120-200 字，半文言，引用 诡修仙2 的"境界/灵气/诡血/咒抗"等词汇
- 避免直接引用 《我在永夜建造庇护所》的原文句子（版权稳妥）
- 三条探索支线长度一致，不让玩家后悔选错
- 战斗文字变体池至少 5 条，避免重玩时重复感

---

## 6. 漏斗分析

### 6.1 关键埋点
| 事件 | 触发时机 | 我们想看 |
|------|---------|---------|
| `start` | 进入 /play 页面 | 曝光量 |
| `scene_enter` | 进入每个 scene | 每场景跳出率 |
| `battle_result` | 战斗胜/败 | 胜率、平均回合数 |
| `breakthrough` | 突破结算 | 哪些天赋最常抽到 |
| `ending` | 到达结局 | 四种结局分布 |
| `invite_generated` | 生成邀请码 | 通关率 |
| `cta_clicked` | 点击"复制添加指引"或"复制邀请码" | 意向转化率 |
| `shared` | 点击"生成分享卡"或"复制分享文案" | 病毒系数 |

### 6.2 后台看板
P0 不做可视化看板。运营直接查表：

```sql
-- 漏斗
SELECT event, COUNT(DISTINCT session_id) FROM web_demo_event WHERE ts > NOW() - INTERVAL 7 DAY GROUP BY event;

-- 兑换转化
SELECT COUNT(*) total, COUNT(redeemed_at) redeemed
FROM web_invite_code WHERE created_at > NOW() - INTERVAL 7 DAY;
```

后续真正需要可视化时可以接 Grafana 或做个只读的 `/admin/funnel` 页面。

### 6.3 隐私原则
- 不种 tracking cookie
- 不收集 User-Agent 完整字符串（只存前 120 字用于会话列表，但这里不需要）
- IP 脱敏到 /24 段再入库
- 所有表 90 天内清理（`ts < now - 90d` 硬删）
- 在 /play 页脚加"本页仅记录匿名漏斗数据,不追踪个人身份"一行小字（合规 + 取信）

---

## 7. 安全与滥用防护

| 风险 | 防护 |
|------|------|
| 刷量生成邀请码 | `/api/demo/invite` 每 session 只能调一次 + IP 5/min 限流 |
| 暴力兑换码 | QQ 端 `/邀请码` 每玩家 3 次/天；连错 5 次冷却 10 分钟 |
| XSS（剧情 YAML 被注入脚本） | 前端所有 text 通过 `textContent` 注入，不用 `innerHTML`；YAML 只接受受信来源（仓库内） |
| CSRF | demo 写接口无认证、无副作用（除邀请码生成），不需 CSRF 头 |
| 机器人兑换接口被绕过 | 仅通过 QQ 消息入口触发；无 public HTTP 端点 |
| 邀请码穷举 | 码空间 16^12 ≈ 2.8×10¹⁴，且每日生成量可被速率限制；暴力成本远高于奖励价值 |

---

## 8. 分享卡实现方案

**首选**: `html2canvas`（单文件 <80 KB gzip，MIT 协议，成熟）
1. 结局页渲染一个隐藏的 `<div id="share-card">` 按 720×1280 布局
2. 点击"下载卡片" → `html2canvas(node).then(canvas => canvas.toBlob(download))`
3. "复制到剪贴板"用 `navigator.clipboard.write([new ClipboardItem({'image/png': blob})])`（支持的浏览器）

**降级**：剪贴板写 PNG 不被支持 → 自动变成下载 PNG + 弹出"下载完成,请手动发朋友圈"。

**字体**：中文若不嵌字体会因用户没安装思源宋体/楷体回落成雷人字体。方案：
- 把一个 subset 字体（只含本游戏文案涉及的字，通常 500-1500 字，用 `pyftsubset` 生成，大小 100-300 KB）内嵌或作为 `/static/demo/font.woff2` 加载
- subset 生成脚本在 `data/demo/tools/subset_font.py`（设计内包含但不在 P0 实现里强制，P0 可以先跑系统字体，体验到位再补 subset）

---

## 9. 部署与运维

### 9.1 路由挂载
复用现有 `plugins/xiuxian_game/web/__init__.py` 的 `@driver.on_startup` 钩子：

```python
@driver.on_startup
async def _register_web_routes():
    from nonebot import get_app
    from .map_api import router as map_router
    from .tower_api import router as tower_router
    from ..web_demo.demo_api import router as demo_router

    app = get_app()
    app.include_router(map_router)
    app.include_router(tower_router)
    app.include_router(demo_router)
    logger.success("[Web] 路由已挂载: /map, /tower, /play")
```

### 9.2 启动时自检
- `data/demo/story.yaml` 解析失败 → log 错误但不阻塞启动（bot 本身仍可运行，仅 `/play` 会返回 503）
- `WebInviteCode` / `WebDemoEvent` 表自动创建（通过 `Base.metadata.create_all`）
- 首次部署后：访问 `https://oversky.online/play` 验证页面渲染

### 9.3 内容热更
`/admin/demo/reload` POST 端点（需超级管理员身份，以 `.env` 里的 admin token 校验）：读取 YAML 重新缓存。运营同学改完 YAML → push → 手动打这个接口 → 新剧情立即生效，无需重启 bot。

### 9.4 监控
- bot 日志里新增一行每小时输出：`[Demo] 过去 1h: session=N1, ending=N2, invite=N3, redeem=N4`
- 异常告警: 单 IP 1h 内 > 100 次 session_start → 记警告，不自动 ban（避免误伤校园/公司共享出口）

---

## 10. 验收标准

- [ ] 本地启动 → 访问 `http://localhost:8080/play` 正常渲染
- [ ] 跑一遍完整流程：启程 → 选分支 → 战斗胜 → 突破 → 结局 → 生成邀请码
- [ ] 刷新页面，localStorage 提示"继续冒险"功能正常
- [ ] 结局页"下载卡片"生成 720×1280 PNG，中文渲染不乱码
- [ ] 在真实手机浏览器（iOS Safari + Android Chrome）测试：文字不溢出、按钮可点、卡片生成成功
- [ ] 部署到 oversky.online → HTTPS + CSP 无警告
- [ ] QQ 机器人发 `/邀请码 <生成的码>` → 正确发放礼包 + 一次性核销
- [ ] 再次发同一个码 → 回复"此码已使用"
- [ ] 同一玩家发第 4 个不同的码 → 回复"今日兑换次数已满"
- [ ] `web_demo_event` 表里能看到完整漏斗事件
- [ ] `story.yaml` 改一段文字 → `POST /admin/demo/reload` → 下次访问看到新文字
- [ ] 单元测试：`invite_service.redeem()` 各分支 ≥ 80% 覆盖
- [ ] 新增文档同步到 `llmdoc/overview/` 索引

---

## 11. 与现有代码的集成点

### 11.1 复用
- `plugins/xiuxian_game/models/db.py` 的 `AsyncSessionLocal / Base`
- `plugins/xiuxian_game/platform_utils.get_unified_player`（机器人端 `/邀请码` 命令）
- `plugins/xiuxian_game/infrastructure/unit_of_work`（兑换走 UoW 保证原子性）
- `plugins/xiuxian_game/web/map_api._RateLimiter` + `_secure`（抽出到 `web/rate_limiter.py` + `web/responses.py` 共用——**此重构沿用已废弃 spec §12.1 的建议**，不要只给 demo_api 用）
- `plugins/xiuxian_game/item/InventoryService`（新手礼包里的物品发放）

### 11.2 新增
- `plugins/xiuxian_game/web_demo/` 整个包（见 §4.1）
- 三张新表：`web_invite_code`, `web_demo_event`, `invite_redeem_log`
- Player 新字段：`first_breakthrough_protection: bool`, `demo_invite_redeemed_count: int`, `last_invite_redeem_date: date`（走 `auto_migrate.REQUIRED_FIELDS`）
- `plugins/xiuxian_game/player/help.py` 新增 `/邀请码` 说明
- `plugins/xiuxian_game/data/knowledge/` 对应的知识库 YAML

### 11.3 不动
- 所有现有游戏系统（战斗/经济/公会/市场等）
- 认证 / Cookie / 登录体系（完全不建）
- `web/map_api.py` 和 `web/tower_api.py` 的功能（只改 import 路径）

---

## 12. 考虑过的备选方案

### 12.1 idle/clicker（银河奶牛式）
- ✅ 沉没成本强、粘性好
- ❌ 开发成本翻倍（需要平衡曲线 + UI 组件）
- ❌ 与 诡修仙2 的"文字 RPG"定位不符，demo 给错印象
- **结论**: 不选

### 12.2 战斗 demo（5 场递增战斗）
- ✅ 最直接展示战斗系统
- ❌ 没有世界观铺垫，氛围感弱
- ❌ 回放式战斗让手机玩家觉得"在看",不是"在玩"
- **结论**: 不选（作为 §3.3 嵌入文字冒险内）

### 12.3 roguelike mini dungeon
- ✅ 玩法有深度、可重玩
- ❌ 开发成本最高（房间随机 + 物品系统 + 平衡）
- ❌ 一局可能太长（>20 min）流失风险大
- **结论**: 不选

### 12.4 多章节连续剧（每周放一章）
- ✅ 长线留量
- ❌ 维护成本高、作者产出节奏不稳定
- ❌ P0 范围不应该承担连续剧运营压力
- **结论**: 不选，但 story.yaml 的设计预留了"章节"概念，未来想扩就扩

---

## 13. 落地顺序（给 writing-plans 参考）

1. 抽出 `_RateLimiter` / `_secure` 到共用模块，修改 map_api.py / tower_api.py 的 import，跑回归
2. 新增三张表 + Player 三个字段（走 auto_migrate），启动验证迁移成功
3. `InviteService` 核心 + 单测
4. `/邀请码` QQ 命令 + help.py + knowledge YAML
5. `demo_api.py` 后端路由（/play HTML + /api/demo/*）
6. `story.yaml` 骨架（§5 结构，12 个场景占位文案）
7. `play.html / play.css / play.js` 前端最小可玩版
8. 战斗场景 + 突破场景 + 结局卡
9. html2canvas 分享卡 + 字体 subset（可 P0 后补）
10. 漏斗事件埋点全量接入
11. 内容作者 pass：全量填写 story.yaml 的正式文案
12. 部署到 oversky.online → 真机测试 → 软上线

---

## 14. 未来迭代（明确非 P0）

- **章节化**：第 2/3/4 章（探索不同地域：诡域深处 / 山门派 / 幽冥界），形成"看连载"习惯
- **成就系统**：多次通关解锁隐藏结局、隐藏路径
- **排行榜**：本周玩家热门选择百分比（社交属性）
- **赠送邀请码**：玩家 A 把自己的码给朋友 B 用，A 在机器人里获得反向奖励（推荐人奖励）
- **跨端**：把这个 demo 也打包一份嵌入 QQ 频道的 Mini App

---

**文档状态**: 🟡 草稿，待 spec-document-reviewer 评审 + 用户复核
**上游**: 本 spec 接替已废弃的 `2026-04-17-web-p0-account-binding-design.md`
**下一步**: 评审通过后进入 writing-plans 编写实现计划
