# 2026-10-07 数据更新冲突调查

## 结论与范围

查阅生产服务器 `guixiuxian-bot` 的近 24 小时 journal。集中故障发生于 23:13:34—23:15:54，共 9 次 MySQL 1205（锁等待超时），全部涉及血修罗（UID 5258）。地图命令存在确定的事务边界缺陷：玩家消息上下文更新取得行锁后，在事务内等待 QQ 图片上传与消息发送，网络等待期间不释放行锁。

生产日志时间线、等待 SQL 和代码执行链一致，强烈指向 23:12:24 开始的地图请求为本轮阻塞源。事故结束后没有取得当时的 InnoDB 阻塞事务快照，不能提供逐次等待的阻塞事务 ID。应用数据库账号没有 PROCESS 权限，未修改生产权限。

## 生产证据

服务器时区 CST，生产代码 HEAD 为 `7357612e`。

| 时间 | 事件 |
| --- | --- |
| 23:11:49 | 玩家首次发送地图；该次请求最终于 23:18:21 失败，总耗时 392.711 秒。 |
| 23:12:17—23:12:18 | 同一玩家闭关正常完成，说明不能将首个地图请求的全部时长都认定为持锁时间。 |
| 23:12:24 | 同一玩家再次发送地图。 |
| 23:13:34—23:15:54 | 9 次锁等待超时，涉及地图、休息、迎战、出关及普通聊天的故事处理；各次等待约 50 秒。 |
| 23:16:11 | 23:12:24 的地图请求失败，总耗时 226.843 秒，堆栈经过 `post_group_files`，底层为 `httpcore.ReadError` / `httpx.ReadError`，适配器封装为 `NetworkError`。同秒另一个已等约 46.8 秒的故事处理结束。 |
| 23:17:30 | 后续地图请求正常完成，总耗时 10.419 秒。 |
| 23:18:21 | 首个地图请求报 QQ 40034005：回复消息 msg_id 已过期。 |

锁等待 SQL 为：

```sql
UPDATE player
SET last_active_at = CASE
  WHEN player.last_active_at IS NULL OR player.last_active_at < %s
  THEN %s ELSE player.last_active_at
END
WHERE player.id = %s;
```

这不是资产业务版本校验失败。`command_errors.py` 将 MySQL 1205、1213、3572 及 `StaleDataError` 都映射为“数据已被其他操作更新”，因此玩家提示无法直接区分锁超时与版本冲突。近 24 小时另有 18:38 的导航 `StaleDataError`，属于单独的版本冲突，不能归入这 9 次锁超时。

## 代码因果链

1. `world/map_locations.py` 原地图处理器在 `safe_session()` 内调用默认 `get_unified_player()`。
2. `platform_utils.py` 默认身份识别更新活跃时间及群信息，玩家 ORM 对象产生待写上下文字段。
3. `world/map_visualizer.py:generate_map()` 查询玩家和地图数据。SQLAlchemy 默认 autoflush 会先刷新待写对象。
4. `models/player.py:_save_context_only_update()` 执行上述按主键 UPDATE。上下文写入不递增业务版本，但仍取得 MySQL 行锁，锁属于当前事务。
5. 原处理器在同一事务内执行图片渲染和 `visual_map_cmd.finish(msg)`。NoneBot 的 `finish()` 先等待 `send()` 完成，再抛出 `FinishedException`；QQ 适配器先上传文件，再发送消息。
6. 因此 QQ 请求挂起时，`safe_session()` 尚未退出，持锁事务不能提交或回滚。后续操作更新同一玩家上下文时排队，等满 MySQL 锁超时后失败。
7. 网络异常冒出后，`safe_session()` 才回滚并关闭会话。排队操作随后能够继续。

仅修改上下文的专用 UPDATE 避免了无关业务版本冲突，但不等于无锁写入。单独延长等待或重试无法消除本次长事务问题。

`附近地点` / `周边` 在查询阴宅时也可能 autoflush，原来同样在事务内发送文字回复。它具有相同缺陷，虽然通常网络等待更短。网页 `/api/map/data` 未发现这条上下文写入与 QQ 发送链。

## 本地修复与验证

`world/map_locations.py` 将数据库内的回复准备拆为 `_prepare_visual_map()` / `_prepare_nearby_locations()`，所有正常、未注册、区域限制及地图生成错误分支先返回消息。外层处理器在 `safe_session()` 成功提交并关闭后才调用 `finish()`，上传失败不再延长数据库事务。

保留原有活跃与群信息更新。地图渲染仍在准备事务内；本次修复切断的是数分钟网络等待持锁的问题，没有拆分整个地图渲染架构。

新增 `tests/test_map_command_transactions.py`：

- 临时 SQLite 单连接池验证发送开始时上下文已提交，发送过程中另一会话可获取连接并写入；覆盖正常地图、生成错误、未注册及区域限制。
- 独立 Docker MySQL 验证先 flush 真实 Player 上下文写入后，模拟回复仍在等待时，同一玩家另一任务的资产更新可在 2 秒内提交；覆盖地图和附近地点入口。
- 提交失败时不发送回复。

验证命令：

```powershell
$env:GUIX_MYSQL_TEST_URL = 'mysql+aiomysql://root:guix_test_only@127.0.0.1:13316'
.venv/Scripts/python.exe -m pytest -q -ra --require-mysql --basetemp D:/QQbot/GuiXiuXian2/.pytest-tmp-map-mysql tests/test_map_command_transactions.py tests/test_map_api.py tests/test_player_context_updates.py tests/test_session_transactions.py
```

结果：37 passed；包含 MySQL 并发验证，没有跳过 MySQL 用例。一次默认临时目录运行因 Windows pytest-current 权限在清理阶段失败，改用独立 basetemp 后正常退出。

此次操作只读取生产日志与角色信息，没有修改线上数据库、部署代码或重启服务。修复目前仅在本地。QQ 上传读取错误究竟发生于服务器链路还是 QQ 接口，现有日志无法进一步区分；事务边界修复可防止这类外部故障再次拖住该玩家后续更新。
