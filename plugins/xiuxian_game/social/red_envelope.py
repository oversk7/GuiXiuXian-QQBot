"""
红包命令处理器

命令列表：
- 发红包 <金额> <份数> [留言]
- 抢红包
- 红包记录
"""

import json
from datetime import datetime
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..models.db import safe_session
from ..models.red_envelope import RedEnvelopeStatus
from ..utils import message_add_head
from ..platform_utils import get_unified_player
from ..infrastructure.repositories.red_envelope_repository import RedEnvelopeRepository
from ..infrastructure.repositories.player_repository import PlayerRepository
from .red_envelope_service import RedEnvelopeService


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
            "💡 份数范围：1-20份\n"
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

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await send_envelope_cmd.finish("请先创建角色")

        service = RedEnvelopeService(
            envelope_repo=RedEnvelopeRepository(session),
            player_repo=PlayerRepository(session)
        )

        success, msg, envelope = await service.send_red_envelope(
            sender_id=player.id,
            group_id=group_id,
            total_gold=total_gold,
            count=count,
            message=msg_text
        )

        if not success:
            await send_envelope_cmd.finish(message_add_head(f"❌ {msg}", event))

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

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await grab_envelope_cmd.finish("请先创建角色")

        service = RedEnvelopeService(
            envelope_repo=RedEnvelopeRepository(session),
            player_repo=PlayerRepository(session)
        )

        success, msg, grab_info = await service.grab_red_envelope(
            player_id=player.id,
            group_id=group_id
        )

        if not success:
            await grab_envelope_cmd.finish(message_add_head(f"❌ {msg}", event))

        envelope = grab_info["envelope"]
        amount = grab_info["amount"]
        is_last = grab_info["is_last"]

        # 获取发送者信息
        sender = await PlayerRepository(session).get_by_id(envelope.sender_id)
        sender_name = sender.nickname if sender else "未知"

        result_lines = [
            f"🧧 {player.nickname} 抢到了红包！",
            "━━━━━━━━━━━━━",
            f"💰 获得 {_format_gold(amount)} 金币",
        ]

        if is_last:
            # 红包抢完了，展示完整记录
            result_lines.append("━━━━━━━━━━━━━")
            result_lines.append(f"🎉 {sender_name} 的红包已被抢完！")

            records = json.loads(envelope.grab_records)
            result_lines.append("━━━━━━━━━━━━━")
            for i, record in enumerate(records, 1):
                line = f"  {record['nickname']}: {_format_gold(record['amount'])}金"
                if record.get("is_lucky"):
                    line += " 👑最佳手气"
                result_lines.append(line)
        else:
            result_lines.extend([
                f"📦 还剩{envelope.remaining_count}份",
                f"💰 剩余{_format_gold(envelope.remaining_gold)}金币",
            ])

        await grab_envelope_cmd.finish(message_add_head("\n".join(result_lines), event))


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
        player = await get_unified_player(session, event)
        if not player:
            await envelope_record_cmd.finish("请先创建角色")

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

            # 抢红包人数
            records = json.loads(env.grab_records)
            grabbed_count = len(records)

            result_lines.append(
                f"📍 {sender_name} | {_format_gold(env.total_gold)}金 "
                f"| {grabbed_count}/{env.total_count}份 | {status_text}"
            )

            # 显示最佳手气
            if env.best_luck_player_id and grabbed_count > 0:
                lucky_player = await PlayerRepository(session).get_by_id(env.best_luck_player_id)
                lucky_name = lucky_player.nickname if lucky_player else "未知"
                result_lines.append(
                    f"  👑 最佳手气: {lucky_name} ({_format_gold(env.best_luck_amount)}金)"
                )

            result_lines.append(f"  ⏰ {env.created_at.strftime('%m-%d %H:%M')}")
            result_lines.append("")

        await envelope_record_cmd.finish(message_add_head("\n".join(result_lines), event))
