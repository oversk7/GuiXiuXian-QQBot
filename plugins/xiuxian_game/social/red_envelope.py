"""
红包命令处理器

命令列表：
- 发红包 <金额> <份数> [留言]
- 抢红包
- 红包记录
"""

import asyncio
import json
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..models.db import safe_session
from ..models.red_envelope import RedEnvelopeStatus
from ..utils import message_add_head
from ..platform_utils import require_player
from ..infrastructure.redis_service import RedisUnavailable
from ..infrastructure.repositories.red_envelope_repository import RedEnvelopeRepository
from ..infrastructure.repositories.player_repository import PlayerRepository
from .red_envelope_service import (
    MAX_COUNT,
    GrabPlan,
    RedEnvelopeService,
    get_red_envelope_group_lock,
)
from .red_envelope_settlement import cancel_uninitialized, get_settler
from .red_envelope_store import GrabStatus, get_red_envelope_store

UNAVAILABLE_MESSAGE = "❌ 红包功能暂未开放（未配置 Redis）"

# 抢红包读库阶段的并发上限：连接池只有 10+5，大量玩家同时抢时给其他指令留出连接
GRAB_DB_CONCURRENCY = 3
_grab_db_slots = asyncio.Semaphore(GRAB_DB_CONCURRENCY)


def _format_gold(gold: int) -> str:
    """格式化金币数量显示"""
    if gold >= 100000000:
        return f"{gold / 100000000:.2f}亿"
    elif gold >= 10000:
        return f"{gold / 10000:.1f}万"
    return str(gold)


# ==================== 发红包 ====================

send_envelope_cmd = on_command("发红包", block=True, priority=11)


@send_envelope_cmd.handle()
async def handle_send_envelope(event: MessageEvent, args: Message = CommandArg()):
    """发红包命令"""
    session_id = event.get_session_id()
    if not session_id.startswith("group_"):
        await send_envelope_cmd.finish("红包功能只能在群聊中使用")

    group_id = session_id.split("_")[1]

    args_text = args.extract_plain_text().strip()
    if not args_text:
        help_msg = (
            "🧧 红包系统\n"
            "━━━━━━━━━━━━━\n"
            "📝 发送红包：\n"
            "【发红包 金额 份数】\n"
            "【发红包 金额 份数 留言】\n"
            "━━━━━━━━━━━━━\n"
            "📝 抢红包：\n"
            "【抢红包】 抢当前群的红包\n"
            "━━━━━━━━━━━━━\n"
            "📝 查看记录：\n"
            "【红包记录】 最近5个红包\n"
            "━━━━━━━━━━━━━\n"
            f"💡 份数范围：1-{MAX_COUNT}份\n"
            "💡 每份最低1金币\n"
            "💡 红包10分钟后过期退还\n"
            "💡 不能抢自己的红包\n"
            "━━━━━━━━━━━━━\n"
            "💸 散财税率：\n"
            "≤1万: 0% | 1万-10万: 3%\n"
            "10万-100万: 5% | 100万-1000万: 8%\n"
            ">1000万: 12%"
        )
        await send_envelope_cmd.finish(message_add_head(help_msg, event))

    parts = args_text.split(maxsplit=2)
    if len(parts) < 2:
        await send_envelope_cmd.finish("格式：发红包 金额 份数 [留言]")

    # 解析金额
    try:
        total_gold = int(parts[0])
    except ValueError:
        await send_envelope_cmd.finish("金额必须为正整数")

    # 解析份数
    try:
        count = int(parts[1])
    except ValueError:
        await send_envelope_cmd.finish("份数必须为正整数")

    # 解析留言（可选）
    msg_text = parts[2] if len(parts) > 2 else None

    store = get_red_envelope_store()
    if not store.configured:
        await send_envelope_cmd.finish(UNAVAILABLE_MESSAGE)

    async with get_red_envelope_group_lock(group_id):
        async with safe_session() as session:
            player = await require_player(session, event, send_envelope_cmd)

            service = RedEnvelopeService(
                envelope_repo=RedEnvelopeRepository(session),
                player_repo=PlayerRepository(session)
            )

            success, msg, envelope = await service.send_red_envelope(
                sender_id=player.id,
                group_id=group_id,
                total_gold=total_gold,
                count=count,
                message=msg_text,
            )

            if not success:
                await send_envelope_cmd.finish(message_add_head(f"❌ {msg}", event))

        # 先提交（扣款和红包记录落库），再初始化 Redis；失败就原路全额退回
        try:
            await store.init_envelope(envelope)
        except RedisUnavailable:
            await cancel_uninitialized(envelope.id)
            await send_envelope_cmd.finish(message_add_head(
                "❌ 红包服务暂时不可用，金币已全额退回，请稍后再发", event
            ))

        # 构建发送成功消息
        result_lines = [
            "🧧 红包来啦！",
            "━━━━━━━━━━━━━",
            f"👤 {player.nickname} 发了一个红包",
        ]

        if msg_text:
            result_lines.append(f"💬 {msg_text}")

        result_lines.extend([
            "━━━━━━━━━━━━━",
            f"💰 总金额：{_format_gold(total_gold)}金币",
        ])

        if envelope.tax_amount > 0:
            result_lines.append(f"💸 散财税：{_format_gold(envelope.tax_amount)}金币")
            result_lines.append(f"🧧 实际红包：{_format_gold(envelope.actual_gold)}金币")

        result_lines.extend([
            f"📦 共{count}份",
            f"⏰ {envelope.expires_at.strftime('%H:%M')}过期",
            "━━━━━━━━━━━━━",
            "发送【抢红包】来抢！"
        ])

        await send_envelope_cmd.finish(message_add_head("\n".join(result_lines), event))


# ==================== 抢红包 ====================

grab_envelope_cmd = on_command("抢红包", block=True, priority=11)


@grab_envelope_cmd.handle()
async def handle_grab_envelope(event: MessageEvent):
    """抢红包命令"""
    session_id = event.get_session_id()
    if not session_id.startswith("group_"):
        await grab_envelope_cmd.finish("红包功能只能在群聊中使用")

    group_id = session_id.split("_")[1]

    if not get_red_envelope_store().configured:
        await grab_envelope_cmd.finish(UNAVAILABLE_MESSAGE)

    # 会话里只做普通读取，离开会话后再访问 Redis：抢红包不加锁、不写库
    async with _grab_db_slots, safe_session() as session:
        player = await require_player(session, event, grab_envelope_cmd)
        service = RedEnvelopeService(
            envelope_repo=RedEnvelopeRepository(session),
            player_repo=PlayerRepository(session)
        )
        plan = await service.prepare_grab(player, group_id)
    if plan is None:
        await grab_envelope_cmd.finish(message_add_head("❌ 当前群本区没有可抢的红包", event))
    await grab_envelope_cmd.finish(message_add_head(await _grab_from_redis(plan), event))


_GRAB_FAILURES = {
    GrabStatus.CLOSED: "❌ 红包已经被抢完了",
    GrabStatus.EXPIRED: "❌ 红包已过期",
    GrabStatus.OWN_ENVELOPE: "❌ 不能抢自己发的红包",
    GrabStatus.MISSING: "❌ 红包还在准备中，请稍后再试",
}


async def _grab_from_redis(plan: GrabPlan) -> str:
    try:
        result = await get_red_envelope_store().grab(
            plan.envelope_id, plan.player_id, plan.nickname, plan.factor
        )
    except RedisUnavailable:
        # 超时不代表脚本没执行；再抢一次是安全的，抢过的会直接返回结果
        return "⚠️ 红包服务繁忙，本次结果未确认。稍后再发一次【抢红包】即可确认，不会重复领取"

    if result.status == GrabStatus.ALREADY_GRABBED:
        return f"❌ 你已经抢过了，获得了{_format_gold(result.amount)}金币"
    if result.status != GrabStatus.OK:
        return _GRAB_FAILURES[result.status]

    settler = get_settler()
    if settler is not None:
        settler.wake()

    lines = [
        f"🧧 {plan.nickname} 抢到了红包！",
        "━━━━━━━━━━━━━",
        f"💰 获得 {_format_gold(result.amount)} 金币（稍后到账）",
    ]
    if result.remaining_count == 0:
        lines.extend(["━━━━━━━━━━━━━", "🎉 红包已被抢完！发送【红包记录】查看手气"])
    else:
        lines.extend([
            f"📦 还剩{result.remaining_count}份",
            f"💰 剩余{_format_gold(result.remaining_gold)}金币",
        ])
    return "\n".join(lines)


# ==================== 红包记录 ====================

envelope_record_cmd = on_command("红包记录", block=True, priority=11)


@envelope_record_cmd.handle()
async def handle_envelope_record(event: MessageEvent):
    """查看群内最近红包记录"""
    session_id = event.get_session_id()
    if not session_id.startswith("group_"):
        await envelope_record_cmd.finish("红包功能只能在群聊中使用")

    group_id = session_id.split("_")[1]

    async with safe_session() as session:
        player = await require_player(session, event, envelope_record_cmd)

        service = RedEnvelopeService(
            envelope_repo=RedEnvelopeRepository(session),
            player_repo=PlayerRepository(session)
        )

        envelopes = await service.get_recent_records(group_id, player.server_id)

        if not envelopes:
            await envelope_record_cmd.finish(message_add_head("📭 本群暂无红包记录", event))

        result_lines = [
            "🧧 最近红包记录",
            "━━━━━━━━━━━━━",
        ]

        for env in envelopes:
            # 获取发送者信息
            sender = await PlayerRepository(session).get_by_id(env.sender_id)
            sender_name = sender.nickname if sender else "未知"

            # 状态标识
            status_map = {
                RedEnvelopeStatus.ACTIVE.value: "🟢进行中",
                RedEnvelopeStatus.FINISHED.value: "✅已抢完",
                RedEnvelopeStatus.EXPIRED.value: "⏰已过期",
            }
            status_text = status_map.get(env.status, env.status)

            # 抢红包人数与最佳手气；入账是异步的，进行中的红包显示的是已到账的人数
            grabbed_count, best = await RedEnvelopeRepository(session).grab_summary(env.id)
            lucky = (best.nickname or "未知", best.amount) if best else None
            if grabbed_count == 0 and env.grab_records not in (None, "", "[]"):
                # 改造前的旧红包，领取记录在 JSON 里
                grabbed_count = len(json.loads(env.grab_records))
                lucky = None
                if env.best_luck_player_id and grabbed_count > 0:
                    lucky_player = await PlayerRepository(session).get_by_id(env.best_luck_player_id)
                    lucky = (lucky_player.nickname if lucky_player else "未知", env.best_luck_amount)

            result_lines.append(
                f"📍 {sender_name} | {_format_gold(env.total_gold)}金 "
                f"| {grabbed_count}/{env.total_count}份 | {status_text}"
            )

            if lucky:
                result_lines.append(f"  👑 最佳手气: {lucky[0]} ({_format_gold(lucky[1])}金)")

            result_lines.append(f"  ⏰ {env.created_at.strftime('%m-%d %H:%M')}")
            result_lines.append("")

        await envelope_record_cmd.finish(message_add_head("\n".join(result_lines), event))
