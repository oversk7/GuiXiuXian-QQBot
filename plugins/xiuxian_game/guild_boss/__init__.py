"""
公会镇诡（公会Boss）- 命令入口

指令：
  - 开坛引诡：会长/副会长消耗公会资金召唤诡异（每日1次，限时48小时）
  - 公会Boss / 公会诡异：查看当前诡异状态与讨伐进度
  - 镇诡：对当前诡异出手（每人每场3次，战斗削减理智）
  - 镇诡战报：会内伤害榜与未出手名单

机制：
  - 有限血量击杀制：血量按开坛时全会有效攻击力生成，全员合力镇压
  - 镇压成功全员发奖，公会凶戾度+1（下次更强、开坛更贵）
  - 超时未镇压按削减血量比例折算保底，凶戾度不变
  - 懒结算：超时后任意相关指令触发结算

设计文档：llmdoc/design/specs/2026-07-08-guild-boss-design.md
"""
from datetime import datetime

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent

from ..models.db import safe_session
from ..models.guild import GuildPosition
from ..models.player import Player
from ..platform_utils import require_player
from ..utils_markdown import cmd, build_markdown
from ..battle.battle_log_filter import filter_battle_log, get_player_log_mode
from .service import GuildBossService
from .config import (
    DAILY_SUMMON_LIMIT,
    ATTACKS_PER_INSTANCE,
    DURATION_HOURS,
    BOSS_POOL,
)


# 「镇诡战报」需在「镇诡」之前匹配，priority 更高
report_cmd = on_command("镇诡战报", aliases={"镇诡排行"}, block=True, priority=12)
summon_cmd = on_command("开坛引诡", aliases={"开坛"}, block=True, priority=13)
view_cmd = on_command("公会Boss", aliases={"公会boss", "公会BOSS", "公会诡异"}, block=True, priority=13)
attack_cmd = on_command("镇诡", block=True, priority=13)


# ==================== 展示工具 ====================

def _hp_bar(left: int, total: int, width: int = 10) -> str:
    if total <= 0:
        return "▱" * width
    filled = round(width * left / total)
    filled = max(0, min(width, filled))
    return "▰" * filled + "▱" * (width - filled)


def _fmt_remain(expires_at: datetime) -> str:
    td = expires_at - datetime.now()
    total = max(0, int(td.total_seconds()))
    hours, minutes = total // 3600, (total % 3600) // 60
    return f"{hours}小时{minutes}分" if hours > 0 else f"{minutes}分钟"


def _quote(text: str) -> str:
    return "\n".join(f"> {line}" if line.strip() else ">" for line in text.splitlines())


def _boss_intro(boss_name: str) -> str:
    for b in BOSS_POOL:
        if b["name"] == boss_name:
            return b["intro"]
    return ""


def _sanitize_log(lines) -> str:
    return "\n".join(str(l).replace("```", "'''") for l in lines)


def _build_expired_card(instance, settlement) -> str:
    pct = int(settlement["ratio"] * 100)
    return (
        f"# 🌫 它走了 · {instance.boss_name}\n"
        f"{instance.boss_title} · 凶戾度 {instance.boss_level}\n"
        "***\n"
        f"{_quote(settlement['flavour'])}\n"
        "***\n"
        f"🩸 削减 **{pct}%** 血量（{settlement['damage_done']:,} / {instance.hp_max:,}）\n"
        f"💰 积分按比例折算入账 · 公会经验 +{settlement['guild_exp']}\n"
        f"{cmd('开坛引诡')} | {cmd('镇诡战报')}"
    )


async def _guild_context(session, event, matcher):
    """加载玩家、公会、职位；无公会则终止"""
    player = await require_player(session, event, matcher)
    service = GuildBossService(session)
    guild, position = await service.get_membership(player)
    if not guild:
        await matcher.finish(
            "你还没有加入公会，镇诡是全会合力的事\n"
            "用【公会列表】找个山门，或【创建公会】自立门户"
        )
    return player, guild, position, service


# ==================== 【开坛引诡】 ====================
@summon_cmd.handle()
async def handle_summon(event: MessageEvent):
    async with safe_session() as session:
        player, guild, position, service = await _guild_context(session, event, summon_cmd)

        # 懒结算超时场次
        instance = await service.get_active_instance(guild.id)
        settlement = await service.settle_if_expired(guild, instance)
        if settlement:
            # 上一场刚超时结算，先展示结算卡（卡内含再次开坛入口）
            await summon_cmd.finish(build_markdown(_build_expired_card(instance, settlement)))

        is_leader = position in (GuildPosition.PRESIDENT, GuildPosition.VICE_PRESIDENT) or guild.president_id == player.id
        if not is_leader:
            await summon_cmd.finish("开坛需要会长或副会长主持，你的位分还不够")

        ok, result = await service.summon(guild, player)
        if not ok:
            await summon_cmd.finish(result)

        inst = result["instance"]
        content = (
            "# 🕯 开坛引诡\n"
            f"**{inst.boss_name}**·{inst.boss_title} 循香而至\n"
            "***\n"
            f"{_quote(result['boss']['intro'])}\n"
            "***\n"
            f"🩸 血量 **{inst.hp_max:,}** · 凶戾度 **{inst.boss_level}** · 限时 **{DURATION_HOURS} 小时**\n"
            f"💰 消耗公会资金 {result['cost']:,}（余 {guild.treasury:,}） · 今日 {guild.boss_week_summons}/{DAILY_SUMMON_LIMIT} 次\n"
            f"全员出力，每人 **{ATTACKS_PER_INSTANCE}** 次\n"
            f"{cmd('镇诡')} | {cmd('公会Boss')} | {cmd('镇诡战报')}"
        )
        await summon_cmd.finish(build_markdown(content))


# ==================== 【公会Boss】 ====================
@view_cmd.handle()
async def handle_view(event: MessageEvent):
    async with safe_session() as session:
        player, guild, position, service = await _guild_context(session, event, view_cmd)

        instance = await service.get_active_instance(guild.id)
        settlement = await service.settle_if_expired(guild, instance)
        if settlement:
            await view_cmd.finish(build_markdown(_build_expired_card(instance, settlement)))

        if not instance:
            service.refresh_day_counter(guild)
            cost = service.summon_cost(guild.boss_level)
            idle_line = "山门无事。阵眼空着，坛上积灰。"
            if guild.boss_level > 1:
                idle_line += "\n但它们记得这里。"
            content = (
                "# 👁 公会镇诡\n"
                f"凶戾度 **{guild.boss_level}** · 今日开坛 {guild.boss_week_summons}/{DAILY_SUMMON_LIMIT}\n"
                "***\n"
                f"{_quote(idle_line)}\n"
                "***\n"
                f"🕯 开坛消耗公会资金 **{cost:,}**（现有 {guild.treasury:,}），会长/副会长可主持\n"
                f"{cmd('开坛引诡')} | {cmd('镇诡战报')}"
            )
            await view_cmd.finish(build_markdown(content))

        rows = await service.get_damage_rows(instance.id)
        members = await service.get_member_players(guild.id)
        my_row = next((r for r in rows if r.player_id == player.id), None)
        my_damage = my_row.total_damage if my_row else 0
        my_left = ATTACKS_PER_INSTANCE - (my_row.attacks_used if my_row else 0)

        content = (
            f"# 👁 镇诡 · {instance.boss_name}\n"
            f"{instance.boss_title} · 凶戾度 **{instance.boss_level}**\n"
            "***\n"
            f"{_quote(_boss_intro(instance.boss_name))}\n"
            "***\n"
            f"🩸 {_hp_bar(instance.hp_left, instance.hp_max)} **{instance.hp_left:,}** / {instance.hp_max:,}\n"
            f"⏳ 剩余 **{_fmt_remain(instance.expires_at)}** · 参战 **{len(rows)}**/{len(members)} 人\n"
            f"🗡 我的出力 {my_damage:,} · 余 **{my_left}** 次\n"
            f"{cmd('镇诡')} | {cmd('镇诡战报')}"
        )
        await view_cmd.finish(build_markdown(content))


# ==================== 【镇诡】 ====================
@attack_cmd.handle()
async def handle_attack(event: MessageEvent):
    async with safe_session() as session:
        player, guild, position, service = await _guild_context(session, event, attack_cmd)

        instance = await service.get_active_instance(guild.id)
        settlement = await service.settle_if_expired(guild, instance)
        if settlement:
            await attack_cmd.finish(build_markdown(_build_expired_card(instance, settlement)))

        if not instance:
            await attack_cmd.finish(
                "阵中无诡。会长或副会长可用【开坛引诡】召唤\n"
                "（用【公会Boss】查看开坛条件）"
            )

        ok, result = await service.attack(guild, instance, player)
        if not ok:
            await attack_cmd.finish(result)

        log_mode = get_player_log_mode(player)
        filtered = filter_battle_log(list(result["battle_log"]), log_mode)
        mode_label = "详细" if log_mode == "detailed" else "简洁"
        log_text = _sanitize_log(filtered)

        if result["killed"]:
            st = result["settlement"]
            my_pts = next((p["points"] for p in st["participants"] if p["player_id"] == player.id), 0)
            overflow = result["raw_damage"] - result["applied"]
            overflow_note = f"（实际输出 {result['raw_damage']:,}，溢出 {overflow:,} 不计榜）" if overflow > 0 else ""
            content = (
                f"# ⛓️ 封棺 · {instance.boss_name}\n"
                "```\n"
                f"{log_text}\n"
                "```\n"
                "***\n"
                f"{_quote(st['flavour'])}\n"
                "***\n"
                f"💥 本次出力 **{result['applied']:,}**{overflow_note}\n"
                f"🎉 镇压成功 · 封棺一击：**{player.nickname}**\n"
                f"💰 我的积分 +**{my_pts}**（全员已入账） · 公会经验 +{st['guild_exp']}\n"
                f"👿 凶戾度升至 **{st['new_ferocity']}**——它记住了你们的手段\n"
                f"{cmd('镇诡战报')} | {cmd('日志模式')} | {cmd('公会Boss')}"
            )
            await attack_cmd.finish(build_markdown(content))

        row = result["row"]
        sanity_line = ""
        if result["sanity_damage"] > 0:
            sanity_line = (
                f"🧠 理智 -{result['sanity_damage']}"
                f"（{result['original_mp']} → {player.mp}）\n"
            )
        content = (
            f"# ⚔️ 镇诡 · {instance.boss_name} · 日志：{mode_label}\n"
            "```\n"
            f"{log_text}\n"
            "```\n"
            "***\n"
            f"💥 本次出力 **{result['applied']:,}** · 累计 {row.total_damage:,} · 余 **{ATTACKS_PER_INSTANCE - row.attacks_used}** 次\n"
            f"{sanity_line}"
            f"🩸 {_hp_bar(instance.hp_left, instance.hp_max)} {instance.hp_left:,} / {instance.hp_max:,}\n"
            f"{cmd('镇诡')} | {cmd('日志模式')} | {cmd('镇诡战报')}"
        )
        await attack_cmd.finish(build_markdown(content))


# ==================== 【镇诡战报】 ====================
@report_cmd.handle()
async def handle_report(event: MessageEvent):
    async with safe_session() as session:
        player, guild, position, service = await _guild_context(session, event, report_cmd)

        instance = await service.get_active_instance(guild.id)
        settlement = await service.settle_if_expired(guild, instance)
        if settlement:
            await report_cmd.finish(build_markdown(_build_expired_card(instance, settlement)))

        if not instance:
            instance = await service.get_latest_instance(guild.id)
        if not instance:
            await report_cmd.finish(
                "这个公会还没有开过坛\n"
                "会长或副会长可用【开坛引诡】召唤第一只诡异"
            )

        rows = await service.get_damage_rows(instance.id)

        if instance.status == "active":
            status_line = f"⏳ 进行中 · 剩余 {_fmt_remain(instance.expires_at)}"
        elif instance.status == "subdued":
            status_line = "⛓️ 已镇压"
        else:
            status_line = "🌫 已离去"

        rank_icons = ["🥇", "🥈", "🥉"]
        rank_lines = []
        for i, r in enumerate(rows[:10]):
            p = await session.get(Player, r.player_id)
            nick = p.nickname if p else "（已失踪）"
            icon = rank_icons[i] if i < 3 else f"{i + 1}."
            rank_lines.append(f"{icon} {nick}　**{r.total_damage:,}**（{r.attacks_used}次）")
        if len(rows) > 10:
            rank_lines.append(f"……还有 {len(rows) - 10} 位同门出过手")
        if not rank_lines:
            rank_lines.append("还没有人出手。")

        idle_line = ""
        if instance.status == "active":
            members = await service.get_member_players(guild.id)
            fought_ids = {r.player_id for r in rows}
            idle = [m.nickname for m in members if m.id not in fought_ids]
            if idle:
                shown = "、".join(idle[:10])
                more = f" 等 {len(idle)} 人" if len(idle) > 10 else ""
                idle_line = f"***\n😴 还没出手（{len(idle)}人）：{shown}{more}\n"

        hp_line = (
            f"🩸 {_hp_bar(instance.hp_left, instance.hp_max)} {instance.hp_left:,} / {instance.hp_max:,}\n"
            if instance.status == "active"
            else f"🩸 总血量 {instance.hp_max:,}\n"
        )

        content = (
            f"# 📜 镇诡战报 · {instance.boss_name}\n"
            f"{status_line} · 凶戾度 {instance.boss_level}\n"
            "***\n"
            f"{hp_line}"
            "***\n"
            + "\n".join(rank_lines) + "\n"
            + idle_line
            + f"{cmd('镇诡')} | {cmd('公会Boss')}"
        )
        await report_cmd.finish(build_markdown(content))
