# Redis 地图缓存与共享限流

## 使用范围

Redis 用于 `/api/map/data` 的公开地图快照、QQ 指令入口额度与 Web IP 额度。金币、物品、拍卖等业务数据仍由数据库事务处理。

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
