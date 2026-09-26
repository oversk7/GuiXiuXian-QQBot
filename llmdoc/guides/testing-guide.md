# 自动化测试与 MySQL、Redis 回归

## 测试范围

测试入口统一为 `python -m pytest tests/`，不会启动机器人 driver 或连接 QQ。

- 普通回归使用 Mock 或临时 SQLite，覆盖业务计算、指令回复、查询组织等行为。
- 使用 `mysql_session_factory` 的用例自动标记为 `mysql`，包括经 `auction_db` 等中间 fixture 间接依赖它的用例。它们验证 MySQL 的行锁、隔离级别、版本冲突、事务回滚和并发结算。
- 使用 `redis_backend_factory` 的用例自动标记为 `redis`，验证跨客户端缓存共享、原子限流与过期行为。
- SQLite 和 Mock 通过不等于 MySQL 或 Redis 集成验证通过；本地测试也不代表已经压测生产环境。

`--require-mysql` 和 `--require-redis` 用于完整验证：分别要求设置 `GUIX_MYSQL_TEST_URL`、`GUIX_REDIS_TEST_URL`，缺少时启动即报配置错误，避免静默跳过。默认不加这些开关，未配置服务时仍可运行普通回归，对应集成用例会显示为 skipped。

## Docker 完整测试环境

需要 Docker Engine / Docker Desktop 和 Docker Compose。仓库根目录执行：

```sh
docker compose -f compose.test.yaml run --rm --build tests
```

Compose 自动启动 MySQL 8.0.46 和 Redis 8.6.3（镜像摘要固定），等待两个服务健康检查成功，再使用 Python 3.12 和 `requirements-ci.txt` 构建的容器运行完整测试。退出码就是 pytest 结果；JUnit 报告在宿主机 `test-results/pytest.xml`。

只运行 MySQL 回归：

```sh
docker compose -f compose.test.yaml run --rm --build tests -q -ra --require-mysql -m mysql --junitxml=test-results/mysql.xml tests/
```

只运行 Redis 集成回归：

```sh
docker compose -f compose.test.yaml run --rm --build tests -q -ra --require-redis -m redis --junitxml=test-results/redis.xml tests/
```

缓存、限流的故障回退等普通测试不带 `redis` 标记；完整专项命令见 [Redis 指南](/llmdoc/guides/redis-guide.md)。

单独验证拍卖：

```sh
docker compose -f compose.test.yaml run --rm --build tests -q -ra --require-mysql tests/test_auction_concurrency.py
```

验证 AI 问答事务边界和回复格式：

```sh
docker compose -f compose.test.yaml run --rm --build tests -q tests/test_ai_guide_transactions.py tests/test_ai_guide_markdown.py
```

问答事务用例使用临时 SQLite 和仅一条连接的连接池，在模拟模型等待时检查其他查询仍可取得连接，同时覆盖元数据提交、提交失败、未注册、超时和取消等路径；不调用真实模型或 QQ API。

停止并移除本项目的测试容器和网络：

```sh
docker compose -f compose.test.yaml down
```

MySQL 数据目录使用 tmpfs，Redis 关闭持久化，不保存长期数据。测试代码和游戏定义复制进测试镜像；修改它们后需要保留 `--build`。镜像不启动 `bot.py`，不复制 `.env*`、游戏数据库配置、数据库文件、日志及运行时存档。

## 使用本机 Python 调试

启动测试服务：

```sh
docker compose -f compose.test.yaml up -d --wait mysql redis
```

安装依赖后运行；以下使用 Windows PowerShell：

```powershell
python -m pip install -r requirements-ci.txt
$env:GUIX_MYSQL_TEST_URL = 'mysql+aiomysql://root:guix_test_only@127.0.0.1:13316'
$env:GUIX_REDIS_TEST_URL = 'redis://127.0.0.1:16379/15'
python -m pytest -q -ra --require-mysql --require-redis tests/
```

Linux / macOS：

```sh
python -m pip install -r requirements-ci.txt
export GUIX_MYSQL_TEST_URL='mysql+aiomysql://root:guix_test_only@127.0.0.1:13316'
export GUIX_REDIS_TEST_URL='redis://127.0.0.1:16379/15'
python -m pytest -q -ra --require-mysql --require-redis tests/
```

仅运行普通回归：

```sh
python -m pytest -q -m "not mysql and not redis" tests/
```

默认宿主机端口为 MySQL `127.0.0.1:13316`、Redis `127.0.0.1:16379`。如有冲突，在启动前设置 `GUIX_MYSQL_TEST_PORT`、`GUIX_REDIS_TEST_PORT`，并同步修改本机测试 URL 的端口。Redis 与测试容器都使用 MySQL 容器的网络命名空间，所以两个宿主机端口统一发布在 Compose 的 mysql 服务上；容器内使用 `127.0.0.1:3306` 和 `127.0.0.1:6379`，无须放宽 fixture 的本机连接限制。

## 数据库隔离与权限

`tests/mysql_helpers.py` 只允许本机的 `mysql+aiomysql` 连接，不接受 URL 查询参数覆盖连接目标。每个用例创建随机命名的 `guixiuxian2_test_<uuid>` 数据库，以 `REPEATABLE READ` 隔离级别运行，并在退出时删除该库。测试连接用户需要创建及删除这些测试库的权限。

Compose 和 CI 中的 `guix_test_only` 是独立临时实例的公开测试密码，不来自生产配置。不要将测试 URL 指向游戏使用的 MySQL 实例。异常中止后可直接移除测试容器，清理临时数据库。

Redis fixture 只允许无查询参数的本机 `redis://` 地址，每个用例使用随机前缀，多个客户端在同一前缀下验证共享行为。结束时只删除该用例的键并关闭客户端，不执行 `FLUSHDB`。`GUIX_REDIS_TEST_URL` 与应用运行使用的 `GUIX_REDIS_URL` 独立；完整测试不会自动启用应用的共享 Redis 状态。

## CI

`.github/workflows/ci.yml` 在 push main 或 Pull Request 时执行：

1. 启动 MySQL 8.0.46 与 Redis 服务并等待健康检查。
2. 全量语法编译检查。
3. 安装 `requirements-ci.txt`。
4. 配置两个测试服务 URL，带 `--require-mysql --require-redis` 运行完整 pytest 回归。
5. 无论测试成功或失败，尝试上传 JUnit 报告 `pytest-results`。
6. 测试成功后执行帮助文档一致性检查。

增加集成用例时直接依赖 `mysql_session_factory` 或 `redis_backend_factory`，不需要手工维护额外的 CI 文件清单。服务无法连接、缺少测试权限或用例失败均应使 CI 失败。
