# ❌ 已废弃 — 网页版 P0 — 账号绑定与会话认证设计

> **状态**: ⛔ **DEPRECATED (2026-04-17)** — 产品方向已变更
>
> **废弃原因**: 网页版的产品目标从"与机器人数据互通的完全对等工具"改为"独立引流小游戏"。账号绑定/会话认证系统不再需要。
>
> **接替文档**: `2026-04-17-web-demo-funnel-game-design.md`
>
> **保留此文档**: 仅作为设计沿革的历史记录（其中的 CSRF / Cookie / 速率限制设计可能在未来需要用户账号体系时再被借鉴）。

---

## 以下内容仅供归档参考

# 网页版 P0 — 账号绑定与会话认证设计

> **背景**: 玩家希望诡修仙2 有一个精美的网页版（参考银河奶牛），与 QQ 机器人数据互通。整个网页版工作量极大，需要分阶段实施。本 spec 是 **P0 阶段**：搭建账号绑定 + Web 会话认证的地基，是后续所有阶段的前置。
>
> **定位**: 网页与群聊「完全对等」——Web 最终要能执行所有破坏性动作（挂牌、战斗、赠送、花灵石），因此 P0 的认证方案必须按生产级安全标准设计。
>
> **范围纪律**: P0 只做认证基建 + 最小可见的「已登录仪表盘」。任何游戏功能（背包、修炼、战斗、市场）都不在 P0 内，留给 P1+。

---

## 1. 目标与非目标

### 1.1 P0 目标
1. **建立 Web 身份系统**：QQ 账号 ↔ Web 会话的安全绑定链路
2. **建立生产级会话管理**：多设备 × 滑动 30 天 × 用户自助踢人
3. **建立 CSRF / 速率限制 / 审计日志等安全基线**：为 P1+ 的写入型 API 铺路
4. **提供最小仪表盘**：玩家打开网页能看到自己的基本数据（境界/HP/灵力/金币/灵石/位置），验证绑定成功 + 给产品一个能展示给玩家的交付物

### 1.2 P0 非目标（明确留给后续阶段）
- ❌ 任何改变游戏状态的 Web 操作（修炼/战斗/交易/装备）
- ❌ WebSocket 实时推送（P6 专项）
- ❌ 前端框架升级（P0 继续用原生 HTML + 原生 JS，与现有 `map.html` 同风格）
- ❌ 移动端自适应的精细打磨（能用即可，P1+ 再优化）
- ❌ 第三方 OAuth（如 QQ 互联）

---

## 2. 关键设计决策（已锁定）

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 绑定方式 | 机器人发 6 位数验证码 + 网页输入 UID + 验证码 | 用户体验简洁、无需密码管理、安全性足够、实现复杂度低 |
| 绑定命令频道 | **仅限私聊** | 避免验证码在群里被他人读到；群聊中发命令回提示「请私聊」 |
| **绑定主体** | **Session 永久绑定到 `Player.id`（不跟随 QQ 激活号切换）** | 见 §2.1 |
| 会话模型 | 多设备 × 滑动 30 天 × 最多 5 个并发 × 自助踢人 | 手机+电脑自由切换，30 天免重登；5 个上限防会话列表爆炸 |
| 会话存储 | 服务端 DB 表（不用 JWT） | 可即时撤销；QQ 机器人能直接查看/踢掉；审计友好 |
| Cookie 标志 | `HttpOnly; Secure; SameSite=Lax; Path=/` | JS 不可读（防 XSS 盗取）、HTTPS 专属、跨站 POST 过不来 |
| CSRF 防护 | SameSite=Lax + `Origin` 头校验 + 自定义头 `X-CSRF-Guard: 1` | 三重防护，无需额外 token 表 |
| 验证码存储 | DB 表 + HMAC 哈希（非明文） | 即便 DB 被拖库也不暴露未使用的验证码 |
| 前端技术栈 | 原生 HTML + 原生 JS（沿用 `map.html` 风格） | P0 不引入构建链；一个 `<script>` 搞定，快速迭代 |
| 审计与日志 | 所有登录尝试 + 会话创建/撤销 → DB 审计表 | 可供玩家追溯、管理员排查 |

### 2.1 账号切换语义（关键）

本项目有 `AccountOwnership` 系统：一个 QQ 号（platform_id）可以拥有多个 Player（主号/小号），QQ 侧任意时刻只有一个"激活账号"被命令操作。Web 会话必须在这套机制下给出确定性行为。

**规则**:

1. **Session 绑定到 `Player.id`，一经签发永不改变。**
   - 当玩家在 QQ 私聊发 `/绑定网页` 时，使用"当时激活的 Player"作为绑定主体
   - 之后玩家即使在 QQ 里切换主号 ↔ 小号，已有的 Web 会话仍然只能看到/操作原来那个 Player
   - 想用 Web 控制另一个号？→ 切到对应激活号后**再跑一次** `/绑定网页`，会得到第二个 Web 会话

2. **`/网页会话` 默认只列当前激活 Player 的会话**（与项目其他命令"默认作用于激活账号"的惯例一致）
   - 附加子命令 `/网页会话 全部` 列出该 platform_id 名下**所有 Player** 的会话（紧急止损场景）
   - `/踢网页 <n>` 编号在当前列表上下文内有效

3. **为什么不让 Web session 跟随激活号切换**:
   - 跨号动作会造成不可预测的安全事件（Web 正在操作号 A 时，QQ 切换到号 B，Web 的下一个请求打到 B）
   - Web 会话作为"对某个角色的授权凭证"语义更干净，也更方便审计
   - 如果 P1+ 后续需要"Web 内切号"，再开 `POST /api/auth/switch-player`（需二次验证），P0 不做

4. **AccountOwnership 转让场景**: 若账号被转让，`account_ownership.owner_platform_id` 变化时，**主动撤销该 `player_id` 的所有 web_session**（由转让流程调用 `WebAuthService.revoke_all_for_player(player_id, reason="transferred")`），避免前主人继续通过 Web 控制。这条改动加在 P0 范围内的 `account_transfer` 服务钩子里。

---

## 3. 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                          QQ 机器人(NoneBot2)                      │
│                                                                 │
│  /绑定网页 (私聊)  ──► WebAuthService.issue_code()              │
│  /网页会话         ──► WebAuthService.list_sessions()           │
│  /踢网页 <n|全>    ──► WebAuthService.revoke_session()          │
│                                                                 │
└────────────────────────┬────────────────────────────────────────┘
                         │ (共享 DB 会话 / Repository)
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  WebAuthService (新建)                            │
│  - issue_code(player_id)       → 生成+哈希+入库                   │
│  - verify_and_login(uid, code) → 校验+消耗+建 session             │
│  - evict_if_exceeds(player_id, max=5)                           │
│  - revoke_session(session_id)                                    │
│  - list_sessions(player_id)                                      │
│  - get_session_player(token)    → P0 提供给 /api/auth/me         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                 FastAPI(NoneBot2 共用)                            │
│                                                                 │
│  GET  /login                       ── 登录页 HTML                 │
│  POST /api/auth/login              ── 验证码登录                  │
│  POST /api/auth/logout             ── 退当前设备                  │
│  POST /api/auth/logout-all         ── 退所有设备                  │
│  GET  /api/auth/me                 ── 当前会话玩家信息             │
│  GET  /api/auth/sessions           ── 我的会话列表                │
│  DELETE /api/auth/sessions/{id}    ── 踢指定会话                  │
│  GET  /home                        ── 登录后仪表盘 HTML            │
│                                                                 │
│  中间件: AuthMiddleware (Cookie → Player) + CSRFMiddleware       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 数据模型

### 4.1 新增表

#### `web_login_code` — 登录验证码
用 ORM `Base.metadata.create_all` 自动建表，不需要写进 `auto_migrate.py`。

```python
class WebLoginCode(Base):
    __tablename__ = "web_login_code"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), comment="HMAC-SHA256(code, SECRET) 的 hex 小写")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True, comment="5 分钟后")
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="非空表示已使用")
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default='0')

    __table_args__ = (
        Index("idx_web_login_code_pending", "player_id", "consumed_at", "expires_at"),
    )
```

**说明**:
- `code_hash` 是 HMAC-SHA256(code, 服务器密钥)，hex 统一用**小写**（`.hexdigest()` 默认）。校验时两侧都走同一个函数生成，再用 `hmac.compare_digest` 比对。
- `failed_attempts` 用于单条验证码级别的尝试限制（同一条验证码错 5 次就失效）。
- `issue_code` 内部先把该 player 所有 pending (consumed_at IS NULL) 的旧码设为 consumed_at=now（标记作废）再插入新的。这样即便并发两次 issue_code 出现短暂两条 pending，后到的那条也会通过再次调用作废前一条；且查询 pending 时总按 `created_at DESC LIMIT 1` 取最新，额外用事务串行化即可彻底避免。P0 并发极低，不强制加 partial unique index。
- 后台定时任务 (daily) 清理 `expires_at < now - 1 day` 的旧记录。

#### `web_session` — Web 会话
```python
class WebSession(Base):
    __tablename__ = "web_session"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, comment="sha256(token) 的 hex，token 本身只回 Cookie")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_active_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True, comment="last_active + 30 天")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 辅助信息(用于会话列表展示)
    ip: Mapped[str] = mapped_column(String(64), default="", server_default="")
    user_agent_short: Mapped[str] = mapped_column(String(120), default="", server_default="", comment="UA 前 120 字")
    created_from: Mapped[str] = mapped_column(String(16), default="login", server_default="login", comment="login/transfer")

    __table_args__ = (
        Index("idx_web_session_player_active", "player_id", "revoked_at"),
    )
```

**说明**:
- Cookie 值是 32 字节 url-safe 随机串（`secrets.token_urlsafe(32)`）。数据库只存 `sha256(token)`，避免 DB 泄漏直接被接管所有会话。
- `revoked_at` 软撤销，方便审计；定期任务清理 revoked 或过期 90 天以上的记录。

#### `web_auth_audit` — 审计日志
```python
class WebAuthAudit(Base):
    __tablename__ = "web_auth_audit"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    player_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    event: Mapped[str] = mapped_column(String(24), comment="issue_code/login_ok/login_fail/logout/session_revoked/rate_limited")
    ip: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[str] = mapped_column(String(200), default="")
```

90 天后可清。

---

## 5. 认证流程

### 5.1 绑定并登录

```
┌─ QQ 私聊 ────────────────────┐       ┌─ 浏览器 ──────────────────────┐
│                              │       │                              │
│ 玩家: /绑定网页                │       │                              │
│                              │       │                              │
│ Bot:                         │       │                              │
│   校验 event 为私聊 ✓         │       │                              │
│   player = 当前激活玩家       │       │                              │
│   速率限制: 该玩家 1h < 5 次  │       │                              │
│   code = 6 位随机数字         │       │                              │
│   DB.insert web_login_code   │       │                              │
│                              │       │                              │
│ Bot:                         │       │                              │
│   "验证码: 482193 (5 分钟)    │       │                              │
│    仅在 oversky.online/login │       │                              │
│    使用, 切勿转发"             │       │                              │
│                              │       │                              │
│                              │       │  打开 oversky.online/login    │
│                              │       │  输入 UID: 123, 验证码: 482193│
│                              │       │                              │
│                              │       │  POST /api/auth/login         │
│                              │       │  {uid:123, code:"482193"}    │
│                              │       │                              │
│                              │       │  服务器:                      │
│                              │       │    IP 速率: 30/min ✓          │
│                              │       │    查 Player by uid           │
│                              │       │    查 web_login_code pending  │
│                              │       │    HMAC 比对 constant-time    │
│                              │       │    标记 consumed              │
│                              │       │    token = token_urlsafe(32)  │
│                              │       │    插入 web_session (token_hash)│
│                              │       │    若 >5 活跃: 撤销最老        │
│                              │       │    审计: login_ok             │
│                              │       │                              │
│                              │       │  Set-Cookie: session=<token>; │
│                              │       │    HttpOnly; Secure;          │
│                              │       │    SameSite=Lax; Max-Age=30d  │
│                              │       │  200 JSON {ok:true, player}   │
│                              │       │                              │
│                              │       │  前端: location.href='/home' │
└──────────────────────────────┘       └──────────────────────────────┘
```

### 5.2 每次后续请求

```
请求 → AuthMiddleware:
  从 Cookie 拿 token
  hash = sha256(token)
  查 web_session where token_hash=hash AND revoked_at IS NULL AND expires_at > now
  命中则:
    session.last_active_at = now
    session.expires_at = now + 30d     # 滑动续期
    request.state.player_id = session.player_id
  未命中:
    清 Cookie
    若是 /api/*: 401 JSON
    若是 HTML 页: 302 /login
```

### 5.3 机器人侧命令

| 命令 | 场景 | 行为 |
|------|------|------|
| `/绑定网页` | 仅私聊 | 发验证码 |
| `/绑定网页` | 群聊 | 回复"请私聊我发送此命令，以防验证码在群里被看到" |
| `/网页会话` | 私聊/群聊均可 | 列出当前玩家所有活跃会话：`#1 IP:1.2.3.4 UA:Chrome 上次活跃:5分钟前` |
| `/踢网页 <n>` | 同上 | 踢掉第 n 个会话 |
| `/踢网页 全` | 同上 | 踢掉所有会话（紧急止损） |

---

## 6. API 端点（P0 全量）

所有 `/api/*` 返回 JSON。Security headers 继续复用现有 `_secure()` helper。

| Method | Path | 鉴权 | 说明 |
|--------|------|------|------|
| `GET`  | `/login` | 无 | 登录页 HTML（注入 CSP nonce，同 map.html 风格） |
| `POST` | `/api/auth/login` | 无 | Body: `{uid:int, code:str}` → Set-Cookie + `{ok:true, player:{...}}` |
| `GET`  | `/api/auth/me` | Cookie | 返回登录玩家的基本信息 |
| `GET`  | `/api/auth/sessions` | Cookie | 返回自己的活跃会话列表 |
| `DELETE` | `/api/auth/sessions/{id}` | Cookie + CSRF | 踢指定会话（必须是自己的） |
| `POST` | `/api/auth/logout` | Cookie + CSRF | 踢当前会话 |
| `POST` | `/api/auth/logout-all` | Cookie + CSRF | 踢当前玩家全部会话 |
| `GET`  | `/home` | Cookie | 登录后首页 HTML，前端从 /api/auth/me 拉数据 |

**`/api/auth/me` 返回字段（P0 最小）**:
```json
{
  "player_id": "9a2f...",    // 内部 id, 前端不显示
  "uid": 123,
  "nickname": "苏慕雪",
  "level": 47,
  "realm_name": "金丹三重",  // 若系统里有境界名则附带
  "hp": 1820,
  "max_hp": 2400,
  "mp": 380,
  "max_mp": 500,
  "gold": 125000,
  "spirit_stone": 380,
  "region": "长安",
  "coord": [−500, −280],
  "last_active_at": "2026-04-17T13:21:08Z"
}
```

注意：故意不暴露 `platform_id`（QQ 号），只回 `uid/nickname`。隐私保护基线与 `map_api.py` 一致。

---

## 7. 安全设计

### 7.1 CSRF 三重防护
所有 **非 GET** 的 `/api/auth/*` 必须满足：
1. `SameSite=Lax` Cookie（浏览器层，阻挡大部分跨站 POST）
2. `Origin` 或 `Referer` 头必须在 allow-list（`https://oversky.online`、开发期可加 `http://localhost`）
3. 请求头必须带 `X-CSRF-Guard: 1`（纯 custom header，跨站 AJAX 会被浏览器 preflight 拦）

前端所有 mutating fetch() 统一封装，自动带上这个 header。

### 7.2 速率限制
- **IP 级** (沿用现有 `_RateLimiter`): `/api/auth/login` 30 req/min/IP
- **玩家级** (新增轻量计数): `/绑定网页` 每玩家每小时最多 5 次
- **验证码级**: 单条验证码错 5 次即标记 consumed（视为失败），避免暴力破解

超限返回 429 + 审计 `rate_limited`。

### 7.3 Constant-time 比对
`hmac.compare_digest(computed_hash, stored_hash)`，防止侧信道。

### 7.4 密钥管理
- `WEB_AUTH_SECRET` (用于 HMAC 验证码) 读取自 `.env`
- 启动时若未设置则自动生成一个并写入 `.env`（仅开发环境）；生产环境缺密钥直接拒启
- 密钥轮换时需清空 `web_login_code` 表（未使用的验证码会作废，可接受）
- **`WebSession.token_hash` 使用纯 SHA-256(token)，不掺密钥**，因此密钥轮换**不影响**已有 Web 会话，无需踢人

### 7.5 日志
- **不记录** 验证码明文、token 明文、Cookie 值
- **记录** 事件类型、player_id、IP、UA 摘要
- 审计表 90 天自动清理

---

## 8. 机器人命令详细设计

### 8.1 `/绑定网页`
**文件**: `plugins/xiuxian_game/web/auth_commands.py` (新建)

```python
async def handle_bind_web(event: MessageEvent):
    if not is_private_message(event):
        await cmd.finish("⚠️ 为了安全,请私聊我发送此命令(避免验证码在群里被看到)")

    async with db_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await cmd.finish("❌ 你还没有角色,请先在群里创建角色")

        svc = WebAuthService(session)
        code, expires = await svc.issue_code(player.id, ip=event_ip(event))
        await session.commit()

    await cmd.finish(
        f"🔐 网页登录验证码: {code}\n"
        f"⏱ 有效期 5 分钟\n"
        f"🔗 请在 oversky.online/login 输入:\n"
        f"   UID: {player.uid}\n"
        f"   验证码: {code}\n"
        f"⚠️ 仅在登录页使用,切勿转发"
    )
```

**issue_code 内部**:
1. 检查玩家级速率限制（1h ≤ 5）；超限抛 `WebAuthRateLimited`
2. 生成 `code = "{:06d}".format(secrets.randbelow(1000000))`
3. `code_hash = hmac_sha256(code, SECRET)`
4. 撤销（删除）该 player 的所有 pending 验证码（仅保留最新一条）
5. Insert `web_login_code`, `expires = now + 5min`
6. 审计 `issue_code`

### 8.2 `/网页会话`
```
📱 你的网页登录设备 (3 / 5)

  #1  2026-04-17 13:20  IP:220.181.x.x  Chrome/Win
      上次活跃: 3 分钟前  ← 当前设备(如适用)
  #2  2026-04-15 09:08  IP:117.144.x.x  Safari/iPhone
      上次活跃: 2 小时前
  #3  2026-04-10 22:15  IP:220.181.x.x  Edge/Win
      上次活跃: 6 天前

  /踢网页 <编号>  踢掉指定设备
  /踢网页 全      踢掉所有设备
```

- IP 显示脱敏到 /24 段（如 `220.181.x.x`），保护玩家隐私。
- 「当前设备」标记只在 Web 端的 `/sessions` 页展示：前端调 `GET /api/auth/sessions` 时，后端根据当前请求 Cookie 的 `sha256(token)` 与列表每行的 `token_hash` 对比，命中则给该行打 `is_current: true` 字段。QQ 机器人侧的 `/网页会话` 没有"当前设备"概念（机器人不是 Web 客户端），不显示此标记。
- 命令触发场景: `/网页会话` 不要求私聊，群里执行也合理（没有敏感信息泄漏风险，IP 已脱敏）。

### 8.3 `/踢网页 <n|全>`
简单校验数字是否在列表范围内；`全` 就全部 revoke；成功后返回剩余会话数。

---

## 9. 前端（P0 最小）

### 9.1 文件结构
```
plugins/xiuxian_game/web/static/
  login.html        ← 新建：登录页
  home.html         ← 新建：登录后仪表盘
  map.html          ← 已存在
  tower.html        ← 已存在
```

### 9.2 登录页 `login.html`
- 羊皮纸风格（与图鉴/地图同调），修仙主题 + 淡淡的诡异感
- 两个输入框：UID（数字）、验证码（6 位数字）
- 提交按钮 → `fetch('/api/auth/login', {...})` → 成功后 `location.href='/home'`
- 错误用单行 alert 红条显示
- 底部文字提示：「在 QQ 私聊机器人发送『绑定网页』获取验证码」

### 9.3 仪表盘 `home.html`
一个 section 的卡片，内容全部来自 `/api/auth/me`:

```
┌─────────────────────────────────┐
│  苏慕雪  UID 123                 │
│  金丹三重  Lv.47                 │
│                                  │
│  ❤️ HP   1820 / 2400            │
│  💧 灵力 380 / 500               │
│                                  │
│  📍 长安 (-500, -280)            │
│  💰 125,000    💠 380            │
│                                  │
│  ─────────────────               │
│  [会话管理]  [退出登录]           │
└─────────────────────────────────┘
```

右上角菜单：`[地图] [爬塔] [会话管理] [退出]`（地图/爬塔复用现有页面，只要在 P0 把入口加上）。

### 9.4 会话管理页 `sessions.html`
用 `/api/auth/sessions` 渲染卡片列表，每张卡片带「踢出」按钮 → `DELETE /api/auth/sessions/{id}`。

---

## 10. 错误处理

| 场景 | 状态码 | 返回 |
|------|--------|------|
| UID 不存在 或 验证码错误 | 400 | `{error:"UID 或验证码错误"}` (统一文案,不泄露哪个错) |
| 验证码过期 | 400 | `{error:"验证码已过期,请重新获取"}` |
| 验证码已使用 | 400 | `{error:"该验证码已使用"}` |
| 同一验证码错误次数超限 | 400 | `{error:"该验证码已失效,请重新获取"}` |
| IP 速率超限 | 429 | `{error:"请求过于频繁,请稍后再试"}` |
| 玩家级速率超限 (QQ 侧) | — | "1 小时内最多获取 5 次验证码" |
| Session 失效 | 401 | `{error:"未登录或会话已过期"}` → 前端跳 `/login` |
| CSRF 失败 | 403 | `{error:"请求来源非法"}` |
| DB 异常 | 503 | `{error:"服务暂时不可用"}` |

所有错误响应继续走 `_secure(...)` 套安全头。

---

## 11. 测试策略

### 11.1 单元测试
`tests/test_web_auth_service.py`:
- `issue_code` 正常/速率限制/多次覆盖旧码
- `verify_and_login` 成功/错误/过期/已消耗/错误次数达上限
- `evict_if_exceeds` 第 6 个会话时最老的被撤销
- `revoke_session` 只能撤自己的；撤不存在 id 返回 false

### 11.2 集成测试
`tests/test_web_auth_api.py` (用 FastAPI TestClient):
- 端到端: issue_code → login → /api/auth/me 返回玩家信息
- 未登录访问 /api/auth/me → 401
- 登出后 Cookie 失效
- CSRF: 缺 `X-CSRF-Guard` header → 403
- Origin 不在 allow-list → 403

### 11.3 安全 / 模糊测试
- HMAC 比对用 `compare_digest` (人工审查)
- SQL 注入: `code` 字段用参数化查询 (SQLAlchemy 默认防护)
- XSS: 所有 HTML 用 CSP nonce + Jinja2 自动转义 (或原生字符串不插入未转义用户数据)
- 超长输入: UID > 2^31, code > 20 字符 → 422

覆盖率目标 ≥ 80% for 新增模块。

---

## 12. 与现有代码的集成点

### 12.1 复用
- `plugins/xiuxian_game/models/db.py` 的 `AsyncSessionLocal` 和 `Base`
- `plugins/xiuxian_game/models/player.py` (通过 uid 查 Player)
- `plugins/xiuxian_game/platform_utils.get_unified_player` (私聊时拿 active player)
- `plugins/xiuxian_game/web/map_api._RateLimiter` (抽出到 `web/rate_limiter.py` 共用)
- `plugins/xiuxian_game/web/map_api._secure` (同上，抽出到 `web/responses.py`)

> 抽取重构时**必须**同步把 `map_api.py` 与 `tower_api.py` 里原来的 import 改为新路径（并跑一遍现有地图/爬塔页面验证回归），避免 planning 时遗漏。

### 12.2 新增
```
plugins/xiuxian_game/web/
  auth_api.py               # FastAPI 路由 (/login, /api/auth/*)
  auth_commands.py          # QQ 机器人命令 (/绑定网页 等)
  auth_service.py           # WebAuthService 业务逻辑
  middleware.py             # AuthMiddleware + CSRFMiddleware
  rate_limiter.py           # 从 map_api.py 抽取
  responses.py              # _secure 抽取
  static/
    login.html
    home.html
    sessions.html
    web.css                 # 共用样式
    web.js                  # 共用 fetch 封装(自动带 CSRF 头)

plugins/xiuxian_game/models/
  web_auth.py               # WebLoginCode + WebSession + WebAuthAudit
```

### 12.3 迁移
- 新表通过 `Base.metadata.create_all` 自动创建，**不需要**动 `auto_migrate.py` 的 `REQUIRED_FIELDS`
- 但要在 `models/__init__.py` 确保三个新 model 被导入，否则不会被 `metadata.create_all` 看到

### 12.4 帮助信息同步
- `plugins/xiuxian_game/player/help.py` 加三个新命令的说明
- `plugins/xiuxian_game/data/knowledge/` 加对应 YAML（遵循项目规则）

### 12.5 Web 路由挂载
修改 `web/__init__.py` 的 `_register_web_routes`，增加 `auth_api.router`，并注入 AuthMiddleware/CSRFMiddleware 到 FastAPI app。

---

## 13. 考虑过的备选方案（为什么没选）

### 13.1 JWT 无状态会话
- ✅ 优点: 无需查 DB
- ❌ 缺点: 撤销困难 (要维护 JTI 黑名单表, 反而不如直接用会话表); 机器人侧无法直接「踢人」
- **结论**: 我们需要即时撤销和机器人侧操作，JWT 不合适

### 13.2 Magic Link (邮件式链接)
- ❌ 风险: QQ 消息被截图或转发后链接直接被别人点就登录
- ❌ 不符合玩家习惯 (QQ 不像邮件那样被视作私密信道)
- **结论**: 验证码方式更稳

### 13.3 密码登录
- ❌ 多一套密码管理 (重置/强度/哈希/盐等),产品价值低
- **结论**: QQ 是身份源，无需自建密码体系

### 13.4 二维码扫码
- ✅ 体验好
- ❌ 需要服务端轮询或长连接 + 二维码库 + 移动端配合
- **结论**: P0 不做，P6 WebSocket 上线后可作为体验优化考虑

### 13.5 SameSite=Strict
- ✅ CSRF 最强
- ❌ 用户从 QQ 链接跳转到 oversky.online/home 时, strict 模式 Cookie 不会发送，看起来像「明明登录了但还是跳登录页」
- **结论**: 用 Lax + 额外 Origin 校验 + custom header，兼顾安全与体验

---

## 14. 未来阶段的前向兼容性检查

P0 的设计要不给 P1+ 埋坑：

| 未来阶段 | 对 P0 的要求 | P0 是否已满足 |
|---------|------------|--------------|
| P1 角色面板 | `GET /api/auth/me` 可扩展返回更多字段 | ✅ 字段独立，加就加 |
| P2 修炼实时循环 | 后端能识别「是哪个 player 在请求」 | ✅ AuthMiddleware 注入 request.state.player_id |
| P6 WebSocket | WS 鉴权复用 Cookie | ✅ HttpOnly Cookie 在 WS 握手时自动带上 |
| PvP 反作弊 | 能审计 Web 发起的操作 | ✅ audit 表可扩 event 类型 |
| 移动 APP | 将来给原生 APP 签发相同 session | ✅ 只要 APP 在 HTTPS + Cookie 语义下工作即可 |
| 第三方 OAuth | 不冲突 | ✅ 走另一条发 Cookie 的路径即可 |

---

## 15. 落地顺序建议（给 writing-plans 参考）

1. 新增三张表 + models (先让 DB 就位)
2. 抽出 `_RateLimiter` / `_secure` 到共用模块
3. `WebAuthService` + 单元测试
4. AuthMiddleware + CSRFMiddleware
5. `/api/auth/*` 全套端点 + 集成测试
6. QQ 机器人命令 `/绑定网页` / `/网页会话` / `/踢网页`
7. 前端 `login.html` / `home.html` / `sessions.html`
8. `help.py` + knowledge YAML 更新
9. 路由挂载 + 安全头 + CSP 调通
10. 端到端联调（本地）+ 部署验证

---

## 16. 验收标准

- [ ] 在本地启动 bot → 访问 `/login` 页面正常渲染
- [ ] 私聊发 `/绑定网页` → 收到验证码
- [ ] 用 UID + 验证码成功登录 → 跳到 `/home` 看到自己的数据
- [ ] 同一浏览器关闭再打开 → 仍然是登录态（30 天内）
- [ ] 手机上登录第二次 → `/网页会话` 能看到两条
- [ ] `/踢网页 1` → 对应设备立即 401，下次请求被踢出
- [ ] CSRF: 从控制台手动发无 `X-CSRF-Guard` 的 POST → 403
- [ ] 连续错 10 次验证码 → 被限流 429
- [ ] 部署到生产 oversky.online → HTTPS + Cookie Secure 生效
- [ ] 新增单元/集成测试覆盖率 ≥ 80%
- [ ] help.py + knowledge/*.yaml 已更新

---

## 附录 A: 前端 `web.js` 的 fetch 封装骨架

```js
// 所有写请求必须走这个封装,自动带 X-CSRF-Guard 头
async function api(method, path, body) {
  const resp = await fetch(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Guard": "1",
    },
    credentials: "same-origin",
    body: body ? JSON.stringify(body) : undefined,
  });
  if (resp.status === 401) {
    location.href = "/login";
    return;
  }
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.error || "请求失败");
  return data;
}
```

## 附录 B: 审计事件类型定义

| event | 何时触发 | detail 示例 |
|-------|----------|-------------|
| `issue_code` | `/绑定网页` 成功下发 | (空) |
| `issue_code_rate_limited` | 玩家 1h 内第 6 次 | (空) |
| `login_ok` | 验证码登录成功 | `session_id=42` |
| `login_fail` | UID 或验证码错误 | `reason=wrong_code` 或 `reason=expired` |
| `login_ip_rate_limited` | IP 30/min 超限 | (空) |
| `logout` | 主动退出 | `session_id=42` |
| `session_revoked` | 被踢 | `by=owner_command` / `by=eviction` |

---

**文档状态**: 🟡 草稿，待 spec-document-reviewer 评审 + 用户复核
**下一步**: 评审通过后进入 writing-plans 编写实现计划
