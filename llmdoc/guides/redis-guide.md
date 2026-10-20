# Redis 地图缓存与共享限流

## 使用范围

Redis 用于 `/api/map/data` 的公开地图快照、QQ 指令入口额度与 Web IP 额度，红包的领取判断与入账消息、世界BOSS伤害排行、签到日历（见文末各节）。其余金币、物品、拍卖等业务数据仍由数据库事务处理。

地图接口保留原有 JSON 字段及响应头：`ts`、`cities`、`players`、`mansions`、`guilds`。浏览器不缓存响应，服务端复用短期快照。诡域塔 API 只接入共享限流，本轮不缓存其分页数据。

## 配置

安装更新后的项目依赖，并在实际运行环境使用的 `.env` 文件或环境变量中配置；NoneBot 通过 `get_plugin_config(RedisSettings)` 读取这些值。修改配置后需重启应用。

```dotenv
GUIX_REDIS_URL=redis://127.0.0.1:6379/0
GUIX_REDIS_PREFIX=guixiuxian2:prod
GUIX_REDIS_TIMEOUT_SECONDS=0.2
GUIX_REDIS_RETRY_SECONDS=10
GUIX_MAP_CACHE_TTL_SECONDS=5
```

| 配置 | 默认值 | 含义 |
|---|---|---|
| `GUIX_REDIS_URL` | 未配置 | 不连接 Redis，使用进程内缓存和限流 |
| `GUIX_REDIS_PREFIX` | `guixiuxian2` | 同一部署的实例使用相同前缀，不同环境使用不同前缀或 Redis DB |
| `GUIX_REDIS_TIMEOUT_SECONDS` | `0.2` | 单次 Redis 调用的等待上限，包含等待连接额度 |
| `GUIX_REDIS_RETRY_SECONDS` | `10` | Redis 错误后的本地冷却时间 |
| `GUIX_MAP_CACHE_TTL_SECONDS` | `5` | 新生成地图快照的缓存秒数，必须是有限正数 |

客户端懒初始化，最多 32 条连接，调用并发受相同上限控制；应用退出时关闭连接池。Redis 可使用受保护的独立缓存实例，连接凭据不写入仓库。

本机体验可启动项目隔离测试服务：

```sh
docker compose -f compose.test.yaml up -d --wait mysql redis
```

它将 Redis 暴露在 `127.0.0.1:16379`。本机开发应用可将 `GUIX_REDIS_URL` 指向 `redis://127.0.0.1:16379/0`，使用单独的开发前缀。测试 fixture 使用 `/15` 和随机前缀；不要将此临时实例作为长期运行服务，它关闭了持久化。

## 地图读取流程

1. 先检查 Web IP 限流，缓存命中也计入请求额度。
2. 本进程自己生成的快照尚未过期时直接使用。
3. 否则读取 Redis 的 `<prefix>:web:map:snapshot:v1`。
4. 未命中时取得进程内锁并再次检查缓存，只有仍未命中的请求回源。
5. 在 `safe_session()` 中执行原有三次查询，退出事务后进行导航位置插值、组装 JSON 并写入缓存。

缓存命中保留原生成时间 `ts`；读取不会延长 TTL。从 Redis 读取的快照不会再被保存为一份具有完整新 TTL 的本地快照，避免临近过期的数据被续存。过期后重新查询并计算导航位置。玩家看到的是短期位置快照，实际位置以群内查询为准。

进程内锁只合并同一进程的并发回源。多个实例在同一时刻首次未命中时，仍可能各回源一次；这里没有使用跨实例回源锁。

Redis 未配置或失败时，地图仍可回源，并将成功结果保留在本进程的短期缓存中。坏 JSON 或缺少必要字段的缓存按未命中处理。数据库失败仍返回 503，不将错误缓存为有效快照；取消或回源异常会释放锁。

## 共享滑动窗口

`SharedSlidingWindowRateLimiter` 使用一段 Lua 脚本完成 Redis 服务端取时、移除窗口外记录、计数、记录获准请求和设置过期时间。每个获准请求有独立标识，不会因同毫秒到达而覆盖。被拒绝的请求不追加记录，也不延长过期时间。

| 作用域 | 参与者 | 额度来源 |
|---|---|---|
| `command` | 平台用户 ID | `data/config.yaml` 的 `command_ingress`，沿用既有窗口及额度 |
| `command-notice` | 平台用户 ID | 同配置中的提示冷却时间，窗口内最多提示一次 |
| `web-ip` | `request.client.host` | 地图与诡域塔共用每 IP 每分钟 30 次 |

Redis key 对参与者 ID 做哈希，作用域之间互不消耗额度。普通聊天、其他插件与重复事件的现有入口过滤继续生效。由于 Redis 操作会让出执行权，同一 QQ 事件内使用共享锁，确保多个 matcher 只消费一次入口额度。

Web 接口继续使用 `request.client.host`，应用代码不直接信任请求里的 `X-Forwarded-For`。反向代理的可信来源应在部署层正确配置。

## 故障与边界

Redis 连接、协议或超时错误触发一次带 `[Redis]` 标记的日志，内容包含异常类型但不包含 URL、密码或异常原文。冷却期间不继续连接 Redis；之后下一次请求重新尝试。任务取消原样向上传播。

Redis 正常允许的请求会同步记录到本机窗口。Redis 不可用时根据这个本机窗口限流，因此不会简单地将近期本机额度清空。但故障期间各实例无法共享新计数；恢复或 Redis 重启时也不能宣称跨实例额度严格连续。这里的限流用于控制请求量，不能代替资产事务、业务幂等或分布式资金锁。

## 验证与观察

```sh
docker compose -f compose.test.yaml run --rm --build tests -q -ra --require-redis tests/test_redis_services.py tests/test_map_cache.py tests/test_map_api.py tests/test_command_guard.py
```

测试覆盖：共享快照、TTL 到期、坏缓存、数据库异常、进程内并发回源合并、共享窗口原子额度、提示冷却、同事件多个 matcher、Redis 超时及恢复。真实 Redis 用例通过 `redis_backend_factory` 隔离，不会清空 Redis DB。

本地已提供的 HTTP 回归使用受控查询替身计算回源次数；它能证明重复请求减少查询调用，不等同于线上延迟或吞吐量压测。上线后可结合 Redis 命中数据、已有 `[Perf]` 日志及地图接口延迟观察实际收益。

## 红包

### 背景

2026-08 红包曾被并发领取：同一份红包多人同时读到"剩余 1 份"，每人都拿走全额（提交 `6457c4e8` 改为行锁 + 同群串行）。行锁版本结果正确，但同群抢红包全部排队，且排队请求占用所有指令共用的数据库连接池（20 + 10）。现在把"能不能抢、抢多少"移到 Redis，数据库只负责记账。

### 前提与旧数据

红包功能依赖 Redis：未配置 `GUIX_REDIS_URL` 时发红包、抢红包直接提示不可用，后台任务不启动。份数上限 500，领取记录写入 `red_envelope_grab`，`(envelope_id, player_id)` 唯一。

抢红包在进入 Redis 前要开一次会话读玩家和本群红包。这一步用进程内信号量限制为 3 个并发（`GRAB_DB_CONCURRENCY`）：本机压测 200 人同时抢时，不限并发会占满 10+5 的连接池，同时段普通指令 p50 从约 30ms 涨到约 450ms；限为 3 后回到约 30ms，抢红包 p95 仍比改造前的同群串行快约 3 倍。

改造前的旧红包：
- `grab_records` JSON 与最佳手气字段保留为历史数据，【红包记录】在新表没有记录时回退读取 JSON。
- 自动迁移新增的 `reconcile_state` 对旧行为 `NULL`，不参与对账；新红包由 ORM 写入 0。否则对账会把历史红包的全部领取当成"少发"再退一遍。
- 上线时仍在进行中的旧红包没有 Redis 状态，抢红包提示"还在准备中"；过期后关闭任务按 `min(数据库剩余金额, 实发金额 − 已入账总额)` 退款，旧红包取到的是数据库剩余金额。

### Key

| Key | 类型 | 内容 |
|---|---|---|
| `<prefix>:red_envelope:{id}` | Hash | `status`（active/finished/closed）、`remain_gold`、`remain_count`、`sender`、`expire_ms`、`keep_ms` |
| `<prefix>:red_envelope:{id}:grabs` | Hash | 玩家 ID → 领取金额 |
| `<prefix>:red_envelope:settle` | Stream | 入账消息 `grab` / `finished`，消费者组 `settler`，消费者 `bot` |

红包 Hash 与领取 Hash 保留到过期后一天。Stream 消息确认后立即删除，Stream 中只剩未处理的消息。

### 流程

1. **发红包**：数据库事务扣款、插入红包并提交，再执行初始化脚本。Redis 失败时 `cancel_uninitialized` 关闭红包并全额退回（含散财税）。
2. **抢红包**：会话内只读玩家与活跃红包（不加锁），算好分配系数后离开会话，执行抢红包脚本：查是否抢过 → 状态与过期（Redis 服务端时间）→ 不能抢自己的 → 按"剩余均值 × 系数"计算份额（至少 1，给后面每人留 1）→ 扣减 → 记录领取人 → `XADD` 入账消息；最后一份同时写 `finished` 消息。玩家立即看到结果，金币稍后到账。Redis 调用失败或超时时提示结果未确认，再抢一次是安全的，抢过的会直接返回金额。
3. **入账**：`RedEnvelopeSettler` 随进程启动，抢红包成功会唤醒它，空闲时每秒检查一次。每条 `grab` 消息一个事务：插入领取记录 + `gold = gold + amount, version_id = version_id + 1`。提交后确认；唯一约束冲突说明已入账，直接确认。处理失败的消息留在待确认列表，每 30 秒重试；投递达到 5 次记死信日志并确认。启动时先处理重启前未确认的消息。
4. **关闭退款**（每分钟）：对已过期的红包执行关闭脚本，返回 Redis 剩余金额与份数；数据库以 `status='active'` 条件更新并退款，重复执行只退一次。Redis 不可用时本轮跳过；Redis 状态缺失时按 `min(数据库剩余金额, 实发金额 − 已入账总额)` 退款。
5. **对账**（每 5 分钟）：过期 10 分钟以上、已关闭的红包核对"已入账总额 + 退款 = 实发金额"。少了把差额退给发送者（`reconcile_state=2`）；多了只记错误日志（`reconcile_state=3`），留给人工处理。

### 边界

- 份额在 Lua 中用双精度计算，单个红包上限 `10^15`，远小于 2^53。
- 入账和展示存在短暂延迟：进行中的红包在【红包记录】里显示的是已到账人数。
- 单个 Stream、单个消费者，依赖单实例部署。多实例时需要不同消费者名，并用 `XAUTOCLAIM` 认领超时消息。
- Redis 数据丢失（例如 AOF 未开启或丢失最后一秒）可能导致少发或多发，由对账发现。生产 Redis 建议开启 `appendonly yes`、`appendfsync everysec`。

### 验证

```sh
GUIX_REDIS_TEST_URL=redis://127.0.0.1:6379/15 pytest -q tests/test_red_envelope_redis.py tests/test_red_envelope_settlement.py tests/test_red_envelope_concurrency.py
```

覆盖：600 个并发请求抢 500 份红包不超份数、不超金额；同一玩家并发只成功一次；1 份红包多人同时抢只有一人成功；关闭与抢红包竞争时金额守恒；10^15 金额精确；消息重复投递只入账一次；失败消息重试后进死信并由对账补偿；入账前关闭仍按 Redis 剩余退款；Redis 状态缺失时退款；超发只告警；初始化失败全额退回；上线前进行中的旧红包按数据库剩余退款、历史红包不参与对账；入账推进版本号，旧快照写入会冲突。设置 `GUIX_MYSQL_TEST_URL` 时结算测试使用真实 MySQL，否则使用临时 SQLite。

## 世界BOSS伤害排行

伤害真账在 `world_boss_damage`，发奖（`_settle_cycle`）只读 MySQL。Redis 只负责【BOSS排行】的展示：各段位前十、段位人数和"我的名次"。

### Key

| Key | 类型 | 内容 | 过期 |
|---|---|---|---|
| `world_boss:{期数ID}:{区服}:{段位}` | ZSet | 成员为玩家 ID，分数为本期累计伤害 | 本期结束后 1 天 |
| `world_boss:{期数ID}:{区服}:ready` | String | 本期本区已从 MySQL 重建过 | 同上 |

伤害目前最高约 1.6×10^11，远小于 2^53，ZSet 的双精度分数能精确表示。

### 流程

1. **攻击**：处理函数在会话里完成战斗和伤害累加，取出 `RankingEntry`（累计伤害、段位）；离开会话（事务已提交）后由 `sync_ranking` 执行写入脚本，再回复玩家。先写 Redis 的话，数据库回滚会让排行多出伤害。
2. **写入脚本**：写累计伤害的绝对值，只有比现有分数大才更新（等价于 Redis 6.2 的 `ZADD GT`，生产是 6.0 所以用 Lua）。重试、写入顺序颠倒都不会让旧值覆盖新值。段位只升不降：更高段位已有该玩家时跳过这次写入，否则先从更低段位删掉，处理周期中途转生升段。
3. **查询**：`ready` 不存在（首次上线、Redis 重启）或本进程写入失败过时，在进程内锁下从 MySQL 读出本期记录重建，再标记 `ready`。之后每个段位 `ZCARD` + `ZREVRANGE 0 9 WITHSCORES`，前十的昵称按主键批量查一次；"我的名次"用 `ZREVRANK`。总参与人数和总伤害用一条 SQL 聚合。
4. **回退**：Redis 未配置或读取失败时，改用原来的整期查询 + 代码分组，结果与 Redis 路径一致。

## 签到日历

`sign:{玩家ID}:{yyyyMM}` 是 BitMap，第 N 天签到就把第 N−1 位置 1，保留 400 天。发奖、"今天签没签过"、连续天数仍以 `player.last_sign` / `sign_streak` 为准。数据库没有签到历史，BitMap 是这份数据的唯一存储，依赖 AOF。

1. **签到**：事务提交后用一条 `BITFIELD` 写入以今天结尾、连续 `sign_streak` 天的这一段（只写本月），可重复执行。这样上线前已经在连签的玩家也能看到本月这段，Redis 数据丢了下一次签到也会补回来。
2. **【签到日历】**：本月 key 不存在、而上次签到在本月时，先按 `last_sign` 和 `sign_streak` 补上那一段（只在 key 不存在时补，避免"拨针·签到"临时把 `last_sign` 改成昨天时补错）。然后 `BITFIELD GET u{本月天数} 0` 一次取出整月，`BITCOUNT` 得到本月签到天数。
3. 写入失败只记日志，不影响签到；读取失败提示稍后再试。

### 验证

```sh
GUIX_REDIS_TEST_URL=redis://127.0.0.1:6379/15 pytest -q tests/test_world_boss_ranking.py tests/test_sign_calendar.py
```

覆盖：Redis 路径与 MySQL 路径生成的排行榜逐字一致（含旧快照、零伤害、跨区服）；首次查询重建；攻击后增量写入、中途转生搬段；旧值不覆盖新值；写入失败后下次查询重建；读取失败回退数据库；Redis 被改乱不影响发奖；签到连续段只写本月、可重复执行、跨月与短月；日历按星期对齐；查看日历时补回上线前的连签。
