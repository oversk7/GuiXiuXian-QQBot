# QQ 单聊主动私信（主动消息）参考

> **背景**：QQ 开放平台近期才开放单聊主动消息能力（此前 bot 只能被动回复）。
> 本文记录官方规则与 NoneBot2 + adapter-qq 的调用方式。调研日期：2026-07-24。

## 平台规则

单聊消息按发送时携带的凭据字段区分类型，**没有单独的"主动消息 API"**，
都走同一个接口 `POST /v2/users/{openid}/messages`：

| 类型 | 特征 | 说明 |
|---|---|---|
| 主动消息 | 不带 `msg_id`/`event_id` | 无前置条件即可发；但用户可在 QQ 客户端关闭「允许主动发送」开关，关闭后一律发送失败（错误码 11255） |
| 被动消息（回复用户） | 带 `msg_id` | 用户消息 60 分钟内有效，同一条最多回 4 次（`msg_seq` 递增） |
| 被动消息（响应事件） | 带 `event_id` | 对事件的回复 |
| 互动召回消息 | `is_wakeup=true` | 用户主动对话后 30 天内分 4 个周期（当天 / 1-3天 / 3-7天 / 7-30天）各可发 1 条 |

### 主动消息频控（单聊，HTTP 接口）

| 认证类型 | Bot 维度 | 单用户维度 | 每日上限 |
|---|---|---|---|
| 企业/个人认证 | 10 qps | 20 qpm | 1000 条/用户 |
| 未认证 | 5 qps & 30 qpm | 20 qpm | 1000 条/用户 |

- `msg_type`：0 文本、2 markdown、7 富媒体（需先上传拿 `file_info`）。
- 注意与「频道私信」（DMS，每天 2 条/用户）是两套完全不同的接口，勿混淆。

## adapter-qq 调用方式（1.7.1 已验证）

高层封装 `Bot.send_to_c2c()`（内部自动判断 `msg_type`、富媒体自动上传）：

```python
import nonebot
from nonebot.adapters.qq import Bot

bot: Bot = nonebot.get_bot()
# 不传 msg_id / event_id 即为主动消息
await bot.send_to_c2c(openid=user_openid, message="你的灵田熟了，快来收菜")
```

低层 API：`bot.post_c2c_messages(openid=..., msg_type=0, content=...)`。

- **openid 来源**：`C2CMessageCreateEvent.get_user_id()`（即 `author.user_openid`）；
  群聊事件的 `member_openid` 在同一 bot 下与单聊 openid 一致，可存库复用。
- `msg_seq` 仅被动多次回复需要，主动消息不传。
- `is_wakeup`（互动召回）adapter-qq 1.7.1 **未封装**，需自行构造 `Request`。

## 工程注意事项

1. 发送必须容错：用户未加过 bot 或关闭了主动接收会失败（11255），
   失败应静默丢弃或落库待用户上线补发，不要让异常炸掉调度任务。
2. bot 需在 QQ 开放平台后台开通单聊能力（消息列表可搜索添加）。
3. 离线/定时场景用 `nonebot.get_bot()` 取实例，openid 提前存到玩家表。

## 玩法启示

日限 1000 条/用户，足以支撑离线通知类玩法：挂机产出提醒、拍卖到期、
体力回满、活动开启推送等。真正的约束是用户侧开关与添加关系，
而非平台频控。
