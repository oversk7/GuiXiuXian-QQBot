from enum import Enum
import re
from datetime import datetime

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import and_, or_, select
from sqlalchemy import func as _func

from ..models.db import safe_session
from ..models.player import Player
from ..models.world_message import WorldMessage
from ..utils import message_add_head


# 违禁词列表 - 可根据需要扩展
BANNED_WORDS = [
    # 常见敏感词（精简版，避免过度过滤）
    "色情", "黄色", "裸体", "性交", "做爱", "约炮", "援交", "卖淫", "嫖娼",
    "赌博", "赌钱", "赌场", "博彩", "下注", "投注",
    "毒品", "大麻", "海洛因", "冰毒", "吸毒", "贩毒",
    "诈骗", "骗钱", "传销", "洗钱", "假币",
    "杀人", "谋杀", "自杀", "爆炸", "炸弹", "恐怖",
    "法轮功", "邪教", "反政府", "颠覆",
    "翻墙", "VPN", "科学上网", "傻逼", "傻比", "煞笔",
]


class MessageScope(str, Enum):
    """留言范围类型"""

    WORLD = "world"
    PRIVATE = "private"


MAX_LEN = 120
PAGE_SIZE = 10

leave_msg_cmd = on_command("留言", block=True, priority=5)
view_board_cmd = on_command("留言板", block=True, priority=5)
private_msg_cmd = on_command("私信", aliases={"私聊"}, block=True, priority=5)

# ==================== 最近更新 ====================
latest_update_cmd = on_command("更新", aliases={"最近更新"}, block=True, priority=5)


def filter_banned_words(content: str) -> str:
    """过滤违禁词，将违禁词替换为 *"""

    if not content:
        return content

    filtered_content = content
    for banned_word in BANNED_WORDS:
        pattern = re.compile(re.escape(banned_word), re.IGNORECASE)
        if pattern.search(filtered_content):
            replacement = "*" * len(banned_word)
            filtered_content = pattern.sub(replacement, filtered_content)
    return filtered_content


def clean_message_content(content: str) -> str:
    """清理消息内容，移除 QQ 表情源码"""

    content = re.sub(r'<faceType=\d+,faceId="[^"]*",ext="[^"]*">', '', content)
    content = re.sub(r'<[^>]*faceType[^>]*>', '', content)
    content = re.sub(r'<[^>]*faceId[^>]*>', '', content)
    content = re.sub(r"\s+", " ", content).strip()
    return content


async def get_unread_message_status(player_id: str) -> tuple[bool, bool]:
    """检查玩家的世界留言板与私信的未读状态"""

    async with safe_session() as session:
        player = await session.get(Player, player_id)
        if not player:
            return False, False

        world_query = select(_func.count(WorldMessage.id)).where(
            WorldMessage.recipient_id.is_(None)
        )
        if player.last_message_board_check:
            world_query = world_query.where(
                WorldMessage.created_at > player.last_message_board_check
            )
        world_count = (await session.execute(world_query)).scalar_one()

        private_query = select(_func.count(WorldMessage.id)).where(
            WorldMessage.recipient_id == player_id
        )
        if player.last_private_message_check:
            private_query = private_query.where(
                WorldMessage.created_at > player.last_private_message_check
            )
        private_count = (await session.execute(private_query)).scalar_one()

        return world_count > 0, private_count > 0


async def mark_scope_messages_as_read(player_id: str, scope: MessageScope):
    """标记指定范围的消息为已读"""

    async with safe_session() as session:
        player = await session.get(Player, player_id)
        if not player:
            return

        now = datetime.now()
        if scope is MessageScope.WORLD:
            player.last_message_board_check = now
        elif scope is MessageScope.PRIVATE:
            player.last_private_message_check = now
        await session.commit()


async def _get_message_page(scope: MessageScope, viewer_id: str, page: int):
    """获取指定范围的消息分页数据"""

    async with safe_session() as session:
        if scope is MessageScope.WORLD:
            filter_expr = WorldMessage.recipient_id.is_(None)
        else:
            filter_expr = and_(
                WorldMessage.recipient_id.is_not(None),
                or_(
                    WorldMessage.recipient_id == viewer_id,
                    WorldMessage.player_id == viewer_id,
                ),
            )

        total = (
            await session.execute(
                select(_func.count(WorldMessage.id)).where(filter_expr)
            )
        ).scalar_one()
        if total == 0:
            return total, 0, page, [], {}

        total_pages = (total - 1) // PAGE_SIZE + 1
        page = min(max(1, page), total_pages)
        offset = (page - 1) * PAGE_SIZE
        stmt = (
            select(WorldMessage)
            .where(filter_expr)
            .order_by(WorldMessage.created_at.desc())
            .offset(offset)
            .limit(PAGE_SIZE)
        )
        records = (await session.execute(stmt)).scalars().all()

        player_ids: set[str] = set()
        for rec in records:
            if rec.player_id:
                player_ids.add(rec.player_id)
            if rec.recipient_id:
                player_ids.add(rec.recipient_id)

        players: dict[str, Player | None] = {}
        for pid in player_ids:
            players[pid] = await session.get(Player, pid)

        return total, total_pages, page, records, players


def _format_message_lines(
    scope: MessageScope,
    page: int,
    total_pages: int,
    records: list[WorldMessage],
    players: dict[str, Player | None],
    viewer_id: str,
    last_private_check: datetime | None,
) -> str:
    """格式化消息列表"""

    if scope is MessageScope.WORLD:
        title = "🗒️ 世界留言板"
    else:
        title = "📬 私信箱"

    lines = [f"{title} (第{page}/{total_pages}页)", "━━━━━━━━━━"]

    for rec in records:
        sender = players.get(rec.player_id)
        if not sender:
            continue
        time_str = rec.created_at.strftime("%m-%d %H:%M")
        if scope is MessageScope.WORLD:
            lines.append(
                f">{sender.nickname}[UID:{sender.uid}] ({time_str})\n{rec.content}"
            )
            continue

        recipient = players.get(rec.recipient_id) if rec.recipient_id else None
        if not recipient:
            # 如果收件人不存在，跳过这条记录
            continue

        if rec.recipient_id == viewer_id:
            new_flag = "🆕 " if (not last_private_check or rec.created_at > last_private_check) else ""
            lines.append(
                f">{new_flag}📥 来自 {sender.nickname}[UID:{sender.uid}] ({time_str})\n{rec.content}"
            )
        elif rec.player_id == viewer_id:
            lines.append(
                f">📤 发给 {recipient.nickname}[UID:{recipient.uid}] ({time_str})\n{rec.content}"
            )

    if len(lines) == 2:
        if scope is MessageScope.WORLD:
            return "🗒️ 留言板空空如也，快来留下第一条留言吧！"
        return "📭 暂无任何私信。发送【私信 UID 内容】与他人沟通吧！"

    return "\n".join(lines)


def _parse_board_args(raw_text: str) -> tuple[MessageScope, int]:
    """解析留言板命令参数"""

    tokens = [token for token in re.split(r"\s+", raw_text) if token]
    scope = MessageScope.WORLD
    page = 1

    if tokens:
        first = tokens[0]
        if first in {"私信", "私聊", "信箱"}:
            scope = MessageScope.PRIVATE
            tokens = tokens[1:]
        elif first in {"世界", "公共", "世界频道"}:
            scope = MessageScope.WORLD
            tokens = tokens[1:]

    if tokens:
        try:
            page = int(tokens[0])
        except ValueError:
            page = 1

    return scope, max(1, page)


@leave_msg_cmd.handle()
async def handle_leave_msg(event: MessageEvent, args: Message = CommandArg()):
    raw_content = args.extract_plain_text().strip()
    content = clean_message_content(raw_content)

    if not content:
        await leave_msg_cmd.finish("⛔ 请输入留言内容，例如：留言 今天好开心！")
    if len(content) > MAX_LEN:
        await leave_msg_cmd.finish(f"⛔ 留言不能超过 {MAX_LEN} 字符")

    filtered_content = filter_banned_words(content)
    if filtered_content != content:
        await leave_msg_cmd.send(message_add_head("⚠️ 检测到敏感词汇，已自动过滤", event))

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await leave_msg_cmd.finish("⛔ 请先创建角色")
        msg_rec = WorldMessage(
            player_id=player.id,
            recipient_id=None,
            content=filtered_content,
            created_at=datetime.now(),
        )
        session.add(msg_rec)
        await session.commit()

    await mark_scope_messages_as_read(event.get_user_id(), MessageScope.WORLD)

    await leave_msg_cmd.send(message_add_head("✅ 留言已发布！", event))

    total, total_pages, page, records, players = await _get_message_page(
        MessageScope.WORLD, event.get_user_id(), 1
    )
    if total == 0:
        await leave_msg_cmd.finish("🗒️ 留言板空空如也，快来留下第一条留言吧！")

    lines = _format_message_lines(
        MessageScope.WORLD,
        page,
        total_pages,
        records,
        players,
        event.get_user_id(),
        None,
    )
    await leave_msg_cmd.finish(message_add_head(lines, event))


@private_msg_cmd.handle()
async def handle_private_message(event: MessageEvent, args: Message = CommandArg()):
    raw_text = args.extract_plain_text().strip()
    content = clean_message_content(raw_text)

    if not content:
        await private_msg_cmd.finish("⛔ 请输入私信内容，例如：私信 10001 你好！")

    parts = content.split(maxsplit=1)
    if len(parts) < 2:
        await private_msg_cmd.finish("⛔ 私信格式错误，应为：私信 [目标UID] [内容]")

    target_uid_text, message_body = parts
    if not message_body:
        await private_msg_cmd.finish("⛔ 私信内容不能为空")

    if len(message_body) > MAX_LEN:
        await private_msg_cmd.finish(f"⛔ 私信不能超过 {MAX_LEN} 字符")

    try:
        target_uid = int(target_uid_text)
    except ValueError:
        await private_msg_cmd.finish("⛔ 目标 UID 格式错误，请输入数字")

    filtered_content = filter_banned_words(message_body)
    if filtered_content != message_body:
        await private_msg_cmd.send(message_add_head("⚠️ 检测到敏感词汇，已自动过滤", event))

    sender_last_check = None
    async with safe_session() as session:
        sender = await session.get(Player, event.get_user_id())
        if not sender:
            await private_msg_cmd.finish("⛔ 请先创建角色")

        sender_last_check = sender.last_private_message_check

        target = (
            await session.execute(select(Player).where(Player.uid == target_uid))
        ).scalars().first()
        if not target:
            await private_msg_cmd.finish("⛔ 未找到对应 UID 的修士")

        if target.id == sender.id:
            await private_msg_cmd.finish("⛔ 无法给自己发送私信")

        msg_rec = WorldMessage(
            player_id=sender.id,
            recipient_id=target.id,
            content=filtered_content,
            created_at=datetime.now(),
        )
        session.add(msg_rec)
        await session.commit()

    await private_msg_cmd.send(message_add_head("✅ 私信已发送！", event))

    total, total_pages, page, records, players = await _get_message_page(
        MessageScope.PRIVATE, event.get_user_id(), 1
    )
    lines = _format_message_lines(
        MessageScope.PRIVATE,
        page,
        total_pages,
        records,
        players,
        event.get_user_id(),
        sender_last_check,
    )
    await private_msg_cmd.finish(message_add_head(lines, event))


@view_board_cmd.handle()
async def handle_view_board(event: MessageEvent, args: Message = CommandArg()):
    player_id = event.get_user_id()
    scope, page = _parse_board_args(args.extract_plain_text().strip())

    async with safe_session() as session:
        player = await session.get(Player, player_id)
    if not player:
        await view_board_cmd.finish("⛔ 请先创建角色")

    if scope is MessageScope.WORLD:
        await mark_scope_messages_as_read(player_id, MessageScope.WORLD)
    else:
        await mark_scope_messages_as_read(player_id, MessageScope.PRIVATE)

    total, total_pages, page, records, players = await _get_message_page(
        scope, player_id, page
    )

    if total == 0:
        if scope is MessageScope.WORLD:
            await view_board_cmd.finish("🗒️ 留言板空空如也，快来留下第一条留言吧！")
        await view_board_cmd.finish("📭 暂无任何私信。发送【私信 UID 内容】与他人沟通吧！")

    lines = _format_message_lines(
        scope,
        page,
        total_pages,
        records,
        players,
        player_id,
        player.last_private_message_check,
    )
    await view_board_cmd.finish(message_add_head(lines, event))


@latest_update_cmd.handle()
async def handle_latest_update(event: MessageEvent):
    async with safe_session() as session:
        rec = (
            await session.execute(
                select(WorldMessage)
                .where(
                    WorldMessage.player_id == 'D6A7BB606845F1AFF40ADA517F7BF306',
                    WorldMessage.recipient_id.is_(None),
                )
                .order_by(WorldMessage.created_at.desc())
                .limit(1)
            )
        ).scalars().first()
        if not rec:
            await latest_update_cmd.finish("暂无更新记录")
        player = await session.get(Player, rec.player_id)
        if not player:
            await latest_update_cmd.finish("暂无更新记录")
        time_str = rec.created_at.strftime("%m-%d")
        msg = f"📜 最近更新 ({time_str})\n{rec.content}"
        await latest_update_cmd.finish(message_add_head(msg, event))

