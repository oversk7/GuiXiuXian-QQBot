"""斗法天梯 - 命令处理器

提供 7 个命令：
- 斗法天梯 / 天梯 / 斗法           主页
- 斗法天梯 匹配                    进行一场对战
- 斗法天梯 排行                    查看本赛季排行榜
- 斗法天梯 历史                    查看自己最近 20 场战绩
- 斗法天梯 开启 / 斗法天梯 关闭     匹配池开关
- 斗法商店                         查看魂晶商店
- 斗法兑换 物品名 [数量]            兑换商店物品
"""
from __future__ import annotations

import logging

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ...models.db import safe_session
from ...platform_utils import get_unified_player, is_guild_message, require_player
from ...utils import message_add_head
from ...utils_markdown import build_markdown, cmd
from ..battle_markdown import build_battle_markdown
from ..battle_log_filter import filter_battle_log, get_player_log_mode
from .service import (
    LadderRatingService,
    LadderError,
    LadderMatchError,
    DAILY_MATCHES_BASE,
)
from .shop import LadderShopService, SHOP_ITEMS

logger = logging.getLogger(__name__)


# ==================== 命令注册 ====================

ladder_main_cmd = on_command(
    "斗法天梯",
    aliases={"天梯", "斗法"},
    block=True,
    priority=8,
)

shop_cmd = on_command("斗法商店", block=True, priority=8)
redeem_cmd = on_command("斗法兑换", block=True, priority=8)


# ==================== 主命令路由 ====================

@ladder_main_cmd.handle()
async def handle_ladder(event: MessageEvent, args: Message = CommandArg()):
    """斗法天梯主命令路由"""
    text = args.extract_plain_text().strip()

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await ladder_main_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            await ladder_main_cmd.finish("⛔ 请先创建角色")

        service = LadderRatingService(session)

        if not text:
            return await _show_home(event, session, player, service)

        # 子命令路由
        parts = text.split()
        sub = parts[0]

        if sub in ("匹配", "对战", "开战"):
            return await _do_match(event, session, player, service)
        if sub in ("排行", "排行榜", "ranking"):
            return await _show_ranking(event, session, player, service)
        if sub in ("历史", "战绩", "记录"):
            return await _show_history(event, session, player, service)
        if sub in ("开启", "开"):
            return await _toggle_matchmaking(event, session, player, service, True)
        if sub in ("关闭", "关"):
            return await _toggle_matchmaking(event, session, player, service, False)
        if sub in ("帮助", "help"):
            return await _show_help(event)

        await ladder_main_cmd.finish(
            f"⛔ 未知子命令「{sub}」\n"
            f"💡 可用：匹配 / 排行 / 历史 / 开启 / 关闭 / 帮助"
        )


# ==================== 主页 ====================

async def _show_home(event: MessageEvent, session, player, service: LadderRatingService):
    """显示天梯主页"""
    season = await service.get_or_create_active_season()
    rating = await service.get_or_create_rating(player.id)
    await service.reset_daily_counters_if_needed(rating)

    quota = await service.get_daily_match_quota(player.id, rating)
    next_tier_name, points_to_next = service.get_next_tier_info(rating.rating)

    # 计算胜率
    if rating.matches_played > 0:
        win_rate = f"{rating.wins * 100 / rating.matches_played:.1f}%"
    else:
        win_rate = "—"

    # 排名
    rank = await service.get_player_rank_in_season(player.id, season.id)
    rank_str = f"#{rank}" if rank else "未上榜"

    # 连胜提示
    streak_hint = f" 🔥{rating.win_streak}连胜" if rating.win_streak >= 3 else ""

    lines = [
        f"# ⚔️ 斗法天梯 · 第{season.season_number}赛季\n",
        f"**段位**: 【{rating.rank_tier}】 {rating.rating} 凶名{streak_hint}\n",
        f"**排名**: {rank_str} | **历史最高**: {rating.best_rating}\n",
    ]

    if next_tier_name:
        lines.append(f"**下一段位**: {next_tier_name} (差 {points_to_next} 凶名)\n")
    else:
        lines.append("**已达顶尖段位** 道君\n")

    lines.append("***\n")
    lines.append(f"**战绩**: {rating.wins}胜 {rating.losses}负 {rating.draws}平 (胜率 {win_rate})\n")
    lines.append(f"**今日**: 已用 {rating.daily_matches}/{quota} 场\n")
    lines.append(f"**魂晶**: 💎 {rating.soul_crystals}\n")

    enabled_text = "✅ 已现身" if rating.matchmaking_enabled else "❌ 已隐匿"
    lines.append(f"**匹配池**: {enabled_text}\n")
    lines.append("***\n")

    lines.append(f"{cmd('斗法天梯 匹配', '斗法天梯 匹配')} 进行对战\n")
    lines.append(f"{cmd('斗法天梯 排行', '斗法天梯 排行')} 排行榜 | {cmd('斗法天梯 历史', '斗法天梯 历史')} 战绩\n")
    lines.append(f"{cmd('斗法商店')} 魂晶商店\n")

    if rating.matchmaking_enabled:
        lines.append(f"{cmd('斗法天梯 关闭', '斗法天梯 关闭')} 退出匹配池\n")
    else:
        lines.append(f"{cmd('斗法天梯 开启', '斗法天梯 开启')} 加入匹配池\n")

    # 守方推送钩子
    await _append_pending_notifications(lines, service, player.id)

    await ladder_main_cmd.finish(build_markdown("".join(lines)))


# ==================== 匹配 ====================

async def _do_match(event: MessageEvent, session, player, service: LadderRatingService):
    """进行一场天梯对战"""
    # 校验和匹配（异常会被 finish() 终止流程）
    result: dict | None = None
    error_msg: str | None = None
    try:
        result = await service.run_match(player)
    except LadderMatchError as e:
        error_msg = str(e)
    except LadderError as e:
        logger.error(f"斗法天梯异常: {e}", exc_info=True)
        error_msg = f"⛔ 斗法天梯异常：{e}"

    if error_msg is not None:
        await ladder_main_cmd.finish(message_add_head(error_msg, event))

    # 此时 result 必定非 None（finish() 已抛出 FinishedException 终止函数）
    assert result is not None

    # 渲染战斗结果（safe_session 会在 finish 时自动 commit）
    victory = result["victory"]
    defender = result["defender"]
    rating_change = result["rating_change"]
    new_rating = result["new_rating"]
    new_rank = result["new_rank"]
    soul_earned = result["soul_earned"]
    first_win_bonus = result["first_win_bonus"]
    win_streak = result["win_streak"]
    used = result["daily_matches_used"]
    quota = result["daily_quota"]
    unchallenged = result.get("unchallenged", False)

    if unchallenged:
        title = "👑 独孤求败 · 无人敢应战"
        filtered_log = ["斗法场中无人胆敢应战，天梯魁首不战而胜。"]
    else:
        log_mode = get_player_log_mode(player)
        filtered_log = filter_battle_log(result["battle_log"], log_mode)
        if victory:
            title = f"⚔️ 斩败 {defender.nickname} 之残魂！"
        else:
            title = f"🛡️ 残魂溃散，败于 {defender.nickname}"

    # 提示信息
    hint_parts = [
        f"凶名 {new_rating}",
        f"段位 {new_rank}",
        f"💎+{soul_earned}",
    ]
    if not unchallenged:
        sign = "+" if rating_change > 0 else ""
        hint_parts.insert(0, f"{sign}{rating_change} 凶名")
    if first_win_bonus:
        hint_parts.append("🎉首胜")
    if victory and win_streak >= 3:
        hint_parts.append(f"🔥{win_streak}连胜")
    hint_parts.append(f"今日 {used}/{quota}")
    hint = " | ".join(hint_parts)

    await ladder_main_cmd.finish(build_battle_markdown(
        title=title,
        battle_log=filtered_log,
        hint=hint,
        btn1="斗法天梯 匹配",
        btn2="斗法天梯",
        btn3="斗法商店",
    ))


# ==================== 排行榜 ====================

async def _show_ranking(event: MessageEvent, session, player, service: LadderRatingService):
    """显示赛季排行榜（TOP 30）"""
    season = await service.get_or_create_active_season()
    top = await service.get_top_rankings(season.id, limit=30)

    if not top:
        await ladder_main_cmd.finish(message_add_head("📭 本赛季暂无玩家上榜", event))

    lines = [
        f"# 🏆 斗法天梯排行榜 · 第{season.season_number}赛季\n",
        f"截止时间: {season.end_at:%Y-%m-%d}\n",
        "***\n",
    ]

    medals = ["🥇", "🥈", "🥉"]
    for idx, (rt, p) in enumerate(top, start=1):
        prefix = medals[idx - 1] if idx <= 3 else f"{idx}."
        win_rate = (rt.wins * 100 / rt.matches_played) if rt.matches_played else 0
        lines.append(
            f"{prefix} **{p.nickname}** [{rt.rank_tier}] **{rt.rating}** 凶名 ({rt.wins}/{rt.matches_played} 胜率{win_rate:.0f}%)\n"
        )

    # 显示自己的排名
    lines.append("***\n")
    my_rank = await service.get_player_rank_in_season(player.id, season.id)
    my_rating = await service.get_or_create_rating(player.id)
    if my_rank:
        lines.append(f"📍 你的排名: **#{my_rank}** [{my_rating.rank_tier}] {my_rating.rating} 凶名\n")
    else:
        lines.append("📍 你尚未现身斗法场，先打一场试试\n")
    lines.append(f"{cmd('斗法天梯 匹配', '斗法天梯 匹配')} 进行对战 | {cmd('斗法天梯')} 主页\n")

    await ladder_main_cmd.finish(build_markdown("".join(lines)))


# ==================== 历史战绩 ====================

async def _show_history(event: MessageEvent, session, player, service: LadderRatingService):
    """显示玩家最近 20 场战绩"""
    matches = await service.get_recent_matches(player.id, limit=20)

    if not matches:
        # 即使没战绩也要尝试推送守方通知（safe_session 会在 finish 时自动 commit）
        notif_lines: list = []
        await _append_pending_notifications(notif_lines, service, player.id)
        await ladder_main_cmd.finish(message_add_head(
            "📭 残魂尚未出鞘\n"
            f"💡 {cmd('斗法天梯 匹配', '斗法天梯 匹配')} 去试试手" + "".join(notif_lines),
            event
        ))

    lines = ["# 📜 斗煞战绩 · 最近 20 场\n", "***\n"]

    for log in matches:
        is_attacker = log.attacker_id == player.id
        opponent_name = log.defender_name if is_attacker else log.attacker_name
        opponent_uid = log.defender_uid if is_attacker else log.attacker_uid

        if log.result == "attacker_win":
            won = is_attacker
        elif log.result == "defender_win":
            won = not is_attacker
        else:
            won = None

        change = log.attacker_rating_change if is_attacker else log.defender_rating_change
        sign = "+" if change > 0 else ""

        if won is True:
            icon = "✅"
        elif won is False:
            icon = "❌"
        else:
            icon = "🤝"

        side = "袭魂" if is_attacker else "护魂"
        lines.append(
            f"{icon} {log.timestamp:%m-%d %H:%M} [{side}] vs **{opponent_name}** ({opponent_uid}) {sign}{change}\n"
        )

    lines.append("***\n")
    lines.append(f"{cmd('斗法天梯')} 主页 | {cmd('斗法天梯 匹配', '斗法天梯 匹配')} 再来一场\n")

    # 推送守方未读通知（safe_session 会在 finish 时自动 commit）
    await service.mark_notifications_seen(player.id)

    await ladder_main_cmd.finish(build_markdown("".join(lines)))


# ==================== 匹配池开关 ====================

async def _toggle_matchmaking(
    event: MessageEvent, session, player, service: LadderRatingService, enabled: bool
):
    """开启/关闭匹配池"""
    rating = await service.get_or_create_rating(player.id)
    rating.matchmaking_enabled = enabled
    # safe_session 会在 finish 时自动 commit

    if enabled:
        msg = "✅ 残魂已显\n他人可凭凶名寻你斗法，胜可得魂晶"
    else:
        msg = (
            "❌ 残魂已隐\n"
            "他人无法锁定你的残魂发起挑战\n"
            "💡 你仍可主动出手斗法"
        )
    await ladder_main_cmd.finish(message_add_head(msg, event))


# ==================== 帮助 ====================

async def _show_help(event: MessageEvent):
    content = (
        "# ⚔️ 斗法天梯帮助\n"
        "残魂相搏，肉身不损，唯以凶名论高下\n"
        "***\n"
        "**🎯 玩法核心**\n"
        "凶名相当的修士自动配对，以现有装备属性进行残魂对决\n"
        "胜利涨凶名 + 魂晶；失败有参与奖\n"
        "***\n"
        "**📋 命令清单**\n"
        f"{cmd('斗法天梯')} 主页（段位/凶名/战绩）\n"
        f"{cmd('斗法天梯 匹配', '斗法天梯 匹配')} 进行一场对战\n"
        f"{cmd('斗法天梯 排行', '斗法天梯 排行')} 赛季排行榜\n"
        f"{cmd('斗法天梯 历史', '斗法天梯 历史')} 最近 20 场战绩\n"
        f"{cmd('斗法天梯 开启', '斗法天梯 开启')} / {cmd('斗法天梯 关闭', '斗法天梯 关闭')} 匹配池开关\n"
        f"{cmd('斗法商店')} 魂晶商店 | {cmd('斗法兑换 斗法令', '斗法兑换 斗法令')} 兑换\n"
        "***\n"
        "**📊 段位 (诡道九品)**\n"
        "散修 → 九品 → 八品 → ... → 一品 → **道君**\n"
        "***\n"
        f"**⚙️ 限制**: 30级以上 | 每日 {DAILY_MATCHES_BASE} 场（高级月卡 +3）\n"
        "**🛡️ 防虐**: 同对手 6h 冷却 | 守方每日上限 10\n"
        "***\n"
        "**🏆 赛季**: 每月一赛季，TOP 100 上墙获得专属奖励\n"
        "***\n"
        f"{cmd('斗法天梯')} 返回主页"
    )
    await ladder_main_cmd.finish(build_markdown(content))


# ==================== 守方推送钩子 ====================

async def _append_pending_notifications(lines: list, service: LadderRatingService, player_id: str):
    """将未推送的守方通知追加到消息行尾"""
    notifs = await service.get_pending_notifications(player_id, limit=5)
    if not notifs:
        return

    lines.append("***\n")
    lines.append("📨 **残魂受袭通知**\n")
    for log in notifs:
        # 守方视角的胜负
        if log.result == "attacker_win":
            outcome = "❌ 魂散"
        elif log.result == "defender_win":
            outcome = "✅ 护体"
        else:
            outcome = "🤝 僵持"
        change = log.defender_rating_change
        sign = "+" if change > 0 else ""
        lines.append(
            f"{outcome} {log.timestamp:%m-%d %H:%M} 被 **{log.attacker_name}** 袭魂 {sign}{change} 凶名\n"
        )
    await service.mark_notifications_seen(player_id)


# ==================== 斗法商店 ====================

@shop_cmd.handle()
async def handle_shop(event: MessageEvent, args: Message = CommandArg()):
    """显示魂晶商店"""
    async with safe_session() as session:
        player = await require_player(session, event, shop_cmd)

        service = LadderRatingService(session)
        rating = await service.get_or_create_rating(player.id)

        items = LadderShopService.list_items()

        lines = [
            "# 💎 斗法商店\n",
            "以魂晶换取秘物 (魂晶唯在斗法场中得)\n",
            f"**当前魂晶**: {rating.soul_crystals}\n",
            "***\n",
        ]

        for item in items:
            limit_text = ""
            if item["daily_limit"]:
                limit_text = f" (每日限购 {item['daily_limit']})"
            item_name = item["name"]
            redeem_text = f"斗法兑换 {item_name}"
            lines.append(
                f"💠 **{item_name}** - {item['price']} 魂晶{limit_text}\n"
                f"  · {item['description']}\n"
                f"  · {cmd('兑换 ' + item_name, redeem_text)}\n"
                "\n"
            )

        lines.append("***\n")
        lines.append("💡 用法: `斗法兑换 物品名 [数量]`\n")
        lines.append(f"💡 单次最多购买 5 个，部分物品有每日上限\n")
        lines.append(f"{cmd('斗法天梯')} 返回主页 | {cmd('斗法天梯 匹配', '斗法天梯 匹配')} 赚魂晶\n")

        await shop_cmd.finish(build_markdown("".join(lines)))


# ==================== 斗法兑换 ====================

@redeem_cmd.handle()
async def handle_redeem(event: MessageEvent, args: Message = CommandArg()):
    """兑换商店物品"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await redeem_cmd.finish(
            "⛔ 用法: `斗法兑换 物品名 [数量]`\n"
            f"💡 例: `斗法兑换 斗法令 3`\n"
            f"💡 {cmd('斗法商店')} 查看可兑换物品"
        )

    parts = args_text.split()
    item_name = parts[0]
    quantity = 1
    if len(parts) >= 2:
        try:
            quantity = int(parts[1])
        except ValueError:
            await redeem_cmd.finish("⛔ 数量必须是数字，例如：斗法兑换 斗法令 3")

    if item_name not in SHOP_ITEMS:
        await redeem_cmd.finish(
            f"⛔ 商店中没有「{item_name}」\n"
            f"💡 {cmd('斗法商店')} 查看可兑换物品"
        )

    async with safe_session() as session:
        player = await require_player(session, event, redeem_cmd)

        service = LadderRatingService(session)
        rating = await service.get_or_create_rating(player.id)

        success, msg = await LadderShopService.redeem(
            session, player, rating, item_name, quantity
        )

        # 失败时回滚以清理潜在的部分修改；成功时由 safe_session 自动 commit
        if not success:
            await session.rollback()

        await redeem_cmd.finish(message_add_head(msg, event))
