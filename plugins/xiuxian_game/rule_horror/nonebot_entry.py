"""规则怪谈玩法 - NoneBot2 命令入口与消息适配。

原插件为 MaiBot SDK 编写，本模块承担三件事：
1. 注册【rg/怪谈】命令并解析「动作 + 参数」，转交原命令处理层执行；
2. 覆写消息出口：群消息走被动回复（超时/超限时降级主动消息），
   多人身份卡改投私信信箱（WorldMessage，玩家用【消息】查看）；
3. 轻度经济挂钩：开局收金币门票、结局按品级发奖励、每群每日局数上限。
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import date

from nonebot import get_bot, logger, on_command
from nonebot.adapters.qq import Bot, Message, MessageEvent, MessageSegment
from nonebot_plugin_apscheduler import scheduler
from nonebot.adapters.qq.exception import (
    ActionFailed,
    AuditException,
    NetworkError,
    RateLimitException,
    UnauthorizedException,
)
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from sqlalchemy.exc import SQLAlchemyError

from ..models.db import safe_session
from ..models.player import Player
from ..models.world_message import WorldMessage
from ..platform_utils import require_player
from ..utils_markdown import build_markdown
from .commands.handler import RuleHorrorCommand
from .common import GameModes
from .core import GameStateManager, GameStatus, SaveManager
from .host import RuleHorrorHost, get_host

SEND_EXCEPTIONS = (
    ActionFailed,
    AuditException,
    NetworkError,
    RateLimitException,
    UnauthorizedException,
    ValueError,
)

# 私信信箱 content 列上限 200，预留分片前缀空间
MAIL_CHUNK_SIZE = 160

# QQ 官方 Bot 每条消息的被动回复上限（msg_seq 1-5），超出后走主动消息
PASSIVE_REPLY_LIMIT = 5

DEFAULT_TICKET_CANDLES_NEW = 10    # 全新生成剧本（6 次 LLM 调用）
DEFAULT_TICKET_CANDLES_REUSE = 5   # 库存剧本复用/重置进度（仅 1 次开场调用）
DEFAULT_FREE_GAMES_PER_PLAYER = 1  # 每人每日免费体验局数
DEFAULT_DAILY_LIMIT = 3
REWARD_CHEST_ITEM_ID = "rule_horror_chest"  # 怪谈稀有宝箱
DEFAULT_REWARDS = {"perfect": 3, "success": 2, "cleared": 1, "failed": 0}  # 宝箱个数
ENDING_LABELS = {"perfect": "完美结局", "success": "成功结局", "cleared": "通关结局", "failed": "失败结局"}


class NoneBotRuleHorrorCommand(RuleHorrorCommand):
    """覆写原命令处理器的全部对外 IO 出口。"""

    def __init__(
        self,
        host: RuleHorrorHost,
        matcher: Matcher,
        bot: Bot,
        event: MessageEvent,
        *,
        group_id: str,
        user_id: str,
        user_name: str,
        raw_text: str,
        matched_groups: dict[str, str],
    ) -> None:
        self._matcher = matcher
        self._bot = bot
        self._event = event
        self._host = host
        self._passive_sent = 0
        super().__init__(
            plugin=host,
            stream_id=group_id,
            group_id=group_id,
            user_id=user_id,
            user_name=user_name,
            raw_text=raw_text,
            matched_groups=matched_groups,
            plugin_config=host.get_plugin_config_data(),
        )

    async def send_text(self, content: str) -> bool:
        return await self._send_message(Message(str(content)))

    async def send_image(self, image_base64: str) -> bool:
        return await self._send_message(Message([MessageSegment.file_image(image_base64)]))

    async def send_image_with_text(self, image_base64: str, text: str = "") -> bool:
        """图片与文字合并为一条消息，节省被动回复条数。"""
        message = Message(text) if text else Message()
        message.append(MessageSegment.file_image(image_base64))
        return await self._send_message(message)

    async def send_card(self, content: str) -> bool:
        """用 QQ 原生 Markdown 卡片发送长文本（代码块展示，免图片渲染等待）。"""
        return await self._send_message(Message([build_markdown(str(content))]))

    async def _send_message(self, message: Message) -> bool:
        if self._passive_sent >= PASSIVE_REPLY_LIMIT:
            logger.info("[规则怪谈] 被动回复条数已用尽，直接走主动消息")
            return await self._send_active(message)
        try:
            await self._matcher.send(message)
            self._passive_sent += 1
            return True
        except SEND_EXCEPTIONS as exc:
            # 被动回复超限或超过 5 分钟时效后，降级为主动群消息
            logger.info(f"[规则怪谈] 被动回复失败({exc})，尝试主动消息兜底")
            return await self._send_active(message)

    async def _send_active(self, message: Message) -> bool:
        group_openid = getattr(self._event, "group_openid", "")
        if not group_openid:
            logger.warning("[规则怪谈] 无群 openid，消息发送失败")
            return False
        try:
            await self._bot.send_to_group(group_openid=group_openid, message=message)
            return True
        except SEND_EXCEPTIONS as exc:
            logger.warning(f"[规则怪谈] 主动消息兜底失败: {exc}")
            return False

    async def _send_private_text(self, target_user_id: str, target_user_name: str, content: str) -> bool:
        """多人身份卡等私密信息改投私信信箱（玩家用【消息】查看）。"""
        uid = str(target_user_id or "").strip()
        text = str(content or "").strip()
        if not uid or not text:
            return False

        chunks = [text[i : i + MAIL_CHUNK_SIZE] for i in range(0, len(text), MAIL_CHUNK_SIZE)]
        total = len(chunks)
        try:
            async with safe_session() as db:
                for idx, chunk in enumerate(chunks, start=1):
                    prefix = f"[规则怪谈 {idx}/{total}] " if total > 1 else "[规则怪谈] "
                    db.add(
                        WorldMessage(
                            player_id="SYSTEM",
                            recipient_id=uid,
                            scope="private",
                            content=prefix + chunk,
                        )
                    )
        except (OSError, ValueError, SQLAlchemyError) as exc:
            logger.error(f"[规则怪谈] 投递私信信箱失败 uid={uid}: {exc}", exc_info=True)
            return False

        await self.send_text(f"{target_user_name} 的专属信息已投递至私信信箱，使用【消息】命令查看。")
        return True

    async def _on_game_ended(self, session, player, ending) -> None:
        """结局钩子：回写剧本战绩，并按品级给全体参与者发放怪谈稀有宝箱。"""
        _ = player
        scenario_id = None
        if isinstance(getattr(session, "world_flags", None), dict):
            scenario_id = session.world_flags.get("scenario_id")
        if scenario_id:
            from . import scenario_library

            scenario_library.record_result(int(scenario_id), str(getattr(ending, "ending_type", "") or "unknown"))

        rewards_cfg = dict(DEFAULT_REWARDS)
        custom = self._host.get_game_setting("rewards", {})
        if isinstance(custom, dict):
            rewards_cfg.update({str(k): int(v) for k, v in custom.items()})

        ending_type = str(getattr(ending, "ending_type", "") or "failed")
        amount = int(rewards_cfg.get(ending_type, 0) or 0)
        label = ENDING_LABELS.get(ending_type, ending_type)
        if amount <= 0:
            return

        from ..models.inventory import ItemInstance

        player_ids = [str(pid) for pid in session.players.keys() if str(pid)]
        rewarded: list[str] = []
        bag_full: list[str] = []
        async with safe_session() as db:
            for pid in player_ids:
                p = await db.get(Player, pid)
                if p is None:
                    continue
                name = getattr(p, "nickname", None) or pid
                try:
                    await ItemInstance.add_item(db, p.id, REWARD_CHEST_ITEM_ID, amount)
                    rewarded.append(name)
                except ValueError:
                    # 背包空间不足时折算金币，奖励不落空
                    p.gold = int(p.gold or 0) + 3000 * amount
                    bag_full.append(name)

        lines = []
        if rewarded:
            lines.append(f"【{label}】结算奖励：{'、'.join(rewarded)} 各获得 怪谈稀有宝箱×{amount}，用【使用 怪谈稀有宝箱】开启。")
        if bag_full:
            lines.append(f"{'、'.join(bag_full)} 背包已满，宝箱折算为金币×{3000 * amount}。")
        if lines:
            await self.send_text("\n".join(lines))


# ---------------- 每日局数限制 ----------------


def _daily_limit_file(host: RuleHorrorHost) -> str:
    return os.path.join(host.data_dir, "daily_limits.json")


def _load_daily_data(host: RuleHorrorHost) -> dict[str, dict[str, int]]:
    """当日开局记录：counts 按群计（每群局数上限），user_plays 按玩家计（免费名额）。"""
    today = date.today().isoformat()
    try:
        with open(_daily_limit_file(host), encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") == today:
            counts = data.get("counts") if isinstance(data.get("counts"), dict) else {}
            user_plays = data.get("user_plays") if isinstance(data.get("user_plays"), dict) else {}
            return {
                "counts": {str(k): int(v) for k, v in counts.items()},
                "user_plays": {str(k): int(v) for k, v in user_plays.items()},
            }
    except (OSError, ValueError):
        pass
    return {"counts": {}, "user_plays": {}}


def _bump_daily_data(host: RuleHorrorHost, group_id: str, user_id: str) -> None:
    data = _load_daily_data(host)
    data["counts"][group_id] = data["counts"].get(group_id, 0) + 1
    data["user_plays"][user_id] = data["user_plays"].get(user_id, 0) + 1
    try:
        with open(_daily_limit_file(host), "w", encoding="utf-8") as f:
            json.dump({"date": date.today().isoformat(), **data}, f, ensure_ascii=False)
    except OSError as exc:
        logger.warning(f"[规则怪谈] 写入每日局数记录失败: {exc}")


def _generation_kind(action: str, rest_input: str) -> str | None:
    """判定这次命令会开一局什么（收门票、计局数的时机）。

    返回 "new"（全新生成，贵）/ "reuse"（库存剧本，便宜）/ None（不开局）。
    单人开始直接生成；重置进度用同一剧本重开，按复用价收；
    多人只有「开始 多人 开始」才生成，单纯建大厅/加入不收费。
    """
    if action == "重置进度":
        return "reuse"
    if action != "开始":
        return None
    raw = (rest_input or "").strip()
    if not raw:
        return "new"  # 默认单人新剧本
    m = re.match(rf"^({GameModes.SINGLE.value}|{GameModes.MULTI.value})\s*(.*)$", raw)
    if not m:
        return None
    mode_rest = (m.group(2) or "").strip()
    if m.group(1) == GameModes.SINGLE.value:
        return "reuse" if re.match(r"^剧本\s*#?\d+$", mode_rest) else "new"
    return "new" if "开始" in mode_rest else None


# ---------------- 闲置自动挂起 ----------------

IDLE_SUSPEND_SAVE_NAME = "自动挂起"
DEFAULT_IDLE_TIMEOUT_MINUTES = 10

# 各群最近一次 /rg 命令时间（进程内即可：重启后内存态本就为空，需恢复才继续）
_last_activity: dict[str, float] = {}


@scheduler.scheduled_job("interval", minutes=1, id="rule_horror_idle_suspend")
async def _idle_suspend_sweep():
    """闲置怪谈自动挂起：超时的活跃局存为「自动挂起」并腾出本群，等待中的大厅直接解散。"""
    host = get_host()
    if not getattr(host, "_started", False):
        return
    timeout_min = int(host.get_game_setting("idle_timeout_minutes", DEFAULT_IDLE_TIMEOUT_MINUTES) or 0)
    if timeout_min <= 0:
        return
    timeout_s = timeout_min * 60

    state_manager = GameStateManager()
    save_manager = SaveManager()
    for group_id in list(state_manager.get_all_group_ids()):
        last = _last_activity.get(group_id)
        if last is None or time.time() - last < timeout_s:
            continue
        try:
            state = await state_manager.get(group_id)
        except RuntimeError:
            continue
        if state is None:
            continue

        scene_name = ""
        suspended = False
        dissolved = False
        try:
            session = state.session
            if session is None:
                continue
            # 拿到锁后再核对一次，避免与刚执行完的命令竞态
            if time.time() - _last_activity.get(group_id, 0) < timeout_s:
                continue
            if session.status == GameStatus.ACTIVE:
                scene_name = str(getattr(session, "scene_name", "") or "")
                await save_manager.save_with_name(group_id, session, IDLE_SUSPEND_SAVE_NAME)
                suspended = True
            elif session.status == GameStatus.WAITING:
                dissolved = True
            else:
                continue
            await state_manager.remove(group_id)
            await save_manager.delete(group_id)
        finally:
            state.release()

        _last_activity.pop(group_id, None)
        logger.info(f"[规则怪谈] 闲置超时自动{'挂起' if suspended else '解散'}: {group_id}")

        if group_id.startswith("c2c_"):
            continue
        try:
            bot = get_bot()
            if suspended:
                msg = (
                    f"🕯️ 《{scene_name}》已经 {timeout_min} 分钟没有动静，已自动挂起并腾出本群。\n"
                    f"想接着玩：`/rg 读取 {IDLE_SUSPEND_SAVE_NAME}`；现在也可以直接开一局新的怪谈。"
                )
            else:
                msg = f"多人大厅 {timeout_min} 分钟没人动静，已自动解散。"
            await bot.send_to_group(group_openid=group_id, message=Message(msg))
        except SEND_EXCEPTIONS as exc:
            logger.warning(f"[规则怪谈] 闲置挂起通知发送失败 {group_id}: {exc}")


# ---------------- 命令入口 ----------------

USAGE_BRIEF = (
    "【规则怪谈】文字冒险，输入【rg 帮助】查看全部命令。\n"
    "快速开始：【rg 开始 单人】，之后用【rg 行动 你的行动描述】推进。\n"
    "提示：开局生成需要一到几分钟，请耐心等待。"
)

rg_cmd = on_command("rg", aliases={"怪谈", "规则怪谈"}, priority=5, block=True)


@rg_cmd.handle()
async def handle_rg(bot: Bot, event: MessageEvent, matcher: Matcher, args: Message = CommandArg()):
    host = get_host()
    await host.ensure_started()

    if not host.get_game_setting("enabled", True):
        await matcher.finish("规则怪谈玩法暂未开放。")

    text = args.extract_plain_text().strip()
    if not text:
        await matcher.finish(USAGE_BRIEF)

    parts = text.split(maxsplit=1)
    action = parts[0].strip()
    rest_input = parts[1].strip() if len(parts) > 1 else ""

    group_id = str(getattr(event, "group_openid", "") or "").strip()

    async with safe_session() as db:
        player = await require_player(db, event, matcher)
        user_id = str(player.id)
        user_name = getattr(player, "nickname", None) or f"道友{user_id[-4:]}"
        candles = int(player.gui_zhu or 0)
    if not group_id:
        group_id = f"c2c_{user_id}"

    _last_activity[group_id] = time.time()

    kind = _generation_kind(action, rest_input)
    daily_limit = int(host.get_game_setting("daily_games_per_group", DEFAULT_DAILY_LIMIT) or 0)
    free_quota = int(host.get_game_setting("free_games_per_player", DEFAULT_FREE_GAMES_PER_PLAYER) or 0)

    ticket_cost = 0
    if kind:
        daily = _load_daily_data(host)
        if daily_limit > 0 and daily["counts"].get(group_id, 0) >= daily_limit:
            await matcher.finish(f"本群今日的怪谈局数已达上限（{daily_limit} 局），明日再来吧。")
        is_free = daily["user_plays"].get(user_id, 0) < free_quota
        if not is_free:
            if kind == "reuse":
                ticket_cost = int(host.get_game_setting("ticket_candles_reuse", DEFAULT_TICKET_CANDLES_REUSE) or 0)
            else:
                ticket_cost = int(host.get_game_setting("ticket_candles_new", DEFAULT_TICKET_CANDLES_NEW) or 0)
            if ticket_cost > 0 and candles < ticket_cost:
                await matcher.finish(
                    f"你今日的免费体验已用完，这局需要门票诡烛×{ticket_cost}"
                    f"（新剧本 {int(host.get_game_setting('ticket_candles_new', DEFAULT_TICKET_CANDLES_NEW) or 0)}"
                    f"，已有剧本 {int(host.get_game_setting('ticket_candles_reuse', DEFAULT_TICKET_CANDLES_REUSE) or 0)}），"
                    "你的诡烛不足。可在【赞助商店】获取诡烛。"
                )

    command = NoneBotRuleHorrorCommand(
        host,
        matcher,
        bot,
        event,
        group_id=group_id,
        user_id=user_id,
        user_name=user_name,
        raw_text=text,
        matched_groups={"action": action, "rest": rest_input},
    )
    success, _msg, _code = await command.execute()
    # 命令执行完再记一次：开局生成耗时较长，闲置计时应从生成完成后起算
    _last_activity[group_id] = time.time()

    # 开局成功后才收门票、计名额；失败不扣费不占免费次数
    if kind and success:
        if ticket_cost > 0:
            async with safe_session() as db:
                p = await db.get(Player, user_id)
                if p is not None:
                    p.gui_zhu = max(0, int(p.gui_zhu or 0) - ticket_cost)
            await command.send_text(f"（已收取本局门票：诡烛×{ticket_cost}）")
        else:
            await command.send_text("（已使用你今日的免费体验名额）")
        _bump_daily_data(host, group_id, user_id)
