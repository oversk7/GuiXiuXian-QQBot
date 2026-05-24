# 主动 C2C 私信通知系统

## Goal

利用已验证的 `bot.send_to_c2c(openid, message)` 能力，在关键游戏事件发生时主动私信通知相关玩家，减少"不知道发生了什么"的体验断层。

## Requirements

### 核心工具：notification_service.py
- `notify_player(player_id, message, session)` — 统一入口
  - 从 `AccountOwnership` 查 `owner_platform_id`，兜底用 `player.id`
  - 调用 `get_bot().send_to_c2c(openid=..., message=...)`
  - 所有异常静默处理（用户未开 C2C 权限 / 群主未开权限均不影响主流程）

### 通知点 A：留言板私信
- 触发：有人发出私信（`private_msg_cmd`）
- 接收人：被私信的玩家
- 内容：`📬 你有一条来自「{sender}」的私信，快去留言板查看吧！`

### 通知点 B：恶魔轮盘预知道具（放大镜/电话）
- 触发：使用放大镜 or 电话后 `success=True`
- 接收人：使用道具的玩家（= 当前 event 的 member_openid）
- 内容：直接把预知结果推过去（`🔍 放大镜结果：第X发是实弹/空包弹`）
- 说明：去掉"请私聊机器人"，改为主动推送；保留群内回复"已私信预知结果"

### 通知点 C：拍卖行结算
- 触发：`_settle_auction` 成功结算
- 成交：通知买家（`🎉 你竞得了 {item}，已入背包`）+ 通知卖家（`💰 {item} 成交，到手 {income}💰`）
- 流拍：通知卖家（`📋 {item} 流拍，已退回背包`）

### 通知点 D：炼丹完成
- 触发：APScheduler 每 5 分钟轮询
- 条件：`claimed=False`, `notified=False`, `started_at + duration_minutes <= now`
- 接收人：`player_id` 对应玩家
- 内容：`⚗️ 你的炼丹已完成！{qty}炉「{item}」静待领取，发送【领取丹药】即可`
- 需要：`alchemy_record` 加 `notified TINYINT DEFAULT 0`（via auto_migrate）

### 通知点 E：灵田成熟
- 触发：APScheduler 每 15 分钟轮询
- 条件：`mature_at <= now`, `mature_notified=False`, `crop_id IS NOT NULL`
- 接收人：通过 `SpiritField.player_id` 关联
- 内容：`🌾 你的灵田有作物已成熟，快去收获吧！`
- 需要：`spirit_field_plot` 加 `mature_notified TINYINT DEFAULT 0`（via auto_migrate）

## Acceptance Criteria

- [ ] 发私信 → 收信人收到 C2C 推送
- [ ] 使用放大镜/电话 → 群内提示"已私信" + C2C 立即推送预知结果
- [ ] 拍卖成交/流拍 → 买卖双方各收到 C2C 通知
- [ ] 炼丹完成后 5 分钟内收到 C2C 通知（不重复推送）
- [ ] 灵田成熟后 15 分钟内收到 C2C 通知（不重复推送）
- [ ] 任意通知失败不影响主流程

## Technical Approach

**notification_service.py** 放在 `plugins/xiuxian_game/notification_service.py`：
- 依赖：`AccountOwnership`, `get_bot()`, `nonebot.adapters.qq.Bot`
- 不依赖任何游戏业务逻辑，纯工具层

**owner_platform_id 查找逻辑：**
1. 查 `AccountOwnership` where `player_id=player_id AND is_active=True` → `owner_platform_id`
2. 兜底：直接用 `player_id`（老玩家无 ownership 记录）

**拍卖行修改：** `_settle_auction` 函数内，成交后追加 `notify_player` 调用；session 已存在直接传入。

**轮盘修改：** `use_item_cmd` handler 里，magnifier/phone 成功后，从 `game_state["magnifier_info"]` / `game_state["phone_info"]` 读取结果，直接 `send_to_c2c`（此时有 bot/event 上下文，不需要走 notify_player）。

**炼丹/灵田调度器：** 加在各自的 scheduler.py 里，复用 `notify_player`。

## Definition of Done

- 所有通知点接入
- 主流程无异常（notify 出错只 logger.warning）
- auto_migrate 字段已添加

## Out of Scope

- 世界 Boss 刷新（群消息，不是私信场景）
- 每日重置提醒（属于群广播，另一个任务）
- 通知开关（玩家设置 on/off）— 暂不做

## Technical Notes

- `send_to_c2c` 参数：`openid: str, message: str`（无需 msg_id/event_id，即主动模式）
- 已验证：`member_openid` 可直接作为 C2C openid 使用
- `get_bot()` 可在调度器/服务层直接调用，返回第一个可用 bot
- 适配器版本：`nonebot-adapter-qq==1.6.2`，`send_to_c2c` 已存在
