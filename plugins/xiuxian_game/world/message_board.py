from enum import Enum
import re
from datetime import datetime, timedelta

from nonebot import on_command, logger
import requests
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import and_, or_, select
from sqlalchemy import func as _func

from ..models.db import safe_session
from ..models.player import Player
from ..models.world_message import WorldMessage
from ..models.message_blacklist import MessageBoardBlacklist
from ..utils import message_add_head
from ..platform_utils import get_unified_player
from ..ai_guide import is_admin
from ..config import Config


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
MIN_LEVEL_TO_POST = 10  # 最低发言等级，可以在config.yaml中配置

leave_msg_cmd = on_command("留言", block=True, priority=5)
view_board_cmd = on_command("留言板", block=True, priority=5)
private_msg_cmd = on_command("私信", aliases={"私聊"}, block=True, priority=5)

# ==================== 管理员命令 ====================
ban_cmd = on_command("禁言", block=True, priority=5)
unban_cmd = on_command("解禁", block=True, priority=5)
blacklist_cmd = on_command("黑名单", aliases={"黑名单列表"}, block=True, priority=5)
delete_msg_cmd = on_command("删除留言", block=True, priority=5)

# ==================== 最近更新 ====================
latest_update_cmd = on_command("更新", aliases={"最近更新"}, block=True, priority=5)


async def check_prohibited_content(text: str) -> tuple[bool, list, str, str]:
    """
    使用API检测违禁内容

    Args:
        text: 待检测的文本

    Returns:
        (is_prohibited, words, label_desc, sub_label_desc):
        是否违禁, 违禁词列表, 标签描述, 子标签描述
    """
    if not text:
        return False, [], "", ""

    try:
        url = f"https://api.lolimi.cn/API/wjc/api.php?msg={requests.utils.quote(text)}"

        response = requests.get(url, timeout=5)
        response.raise_for_status()

        data = response.json()

        # API响应格式:
        # 正常: {"code": 200, "message": "合规", "words": [], ...}
        # 违禁: {"code": -200, "message": "不合规", "words": [...], "labelDesc": "...", "subLabelDesc": "..."}
        code = data.get("code", 0)

        if code == -200:
            # 检测到违禁内容
            words = data.get("words", [])
            label_desc = data.get("labelDesc", "")
            sub_label_desc = data.get("subLabelDesc", "")
            return True, words, label_desc, sub_label_desc
        elif code == 200:
            # 正常内容
            return False, [], "", ""
        else:
            # 未知状态码
            logger.warning(f"违禁词API返回未知状态码: {code}, 数据: {data}")
            return False, [], "", ""

    except requests.RequestException as e:
        logger.error(f"违禁词检测API请求失败: {e}")
        # API失败时返回False,不阻止用户发言
        return False, [], "", ""
    except Exception as e:
        logger.error(f"违禁词检测出现异常: {e}")
        return False, [], "", ""


def filter_banned_words(content: str) -> str:
    """
    过滤违禁词,将违禁词替换为 *
    保留此函数以兼容旧代码,但功能已改为使用API检测
    注意: 此函数是同步的,实际检测应使用 check_prohibited_content
    """
    # 此函数保留仅用于向后兼容
    # 实际使用时应该调用 check_prohibited_content
    return content


def clean_message_content(content: str) -> str:
    """清理消息内容，移除 QQ 表情源码"""

    content = re.sub(r'<faceType=\d+,faceId="[^"]*",ext="[^"]*">', '', content)
    content = re.sub(r'<[^>]*faceType[^>]*>', '', content)
    content = re.sub(r'<[^>]*faceId[^>]*>', '', content)
    content = re.sub(r"\s+", " ", content).strip()
    return content


async def check_blacklist(player_id: str) -> tuple[bool, str | None]:
    """
    检查玩家是否在黑名单中

    Returns:
        (is_banned, remaining_time): 是否被禁言，剩余禁言时间描述
    """
    async with safe_session() as session:
        stmt = select(MessageBoardBlacklist).where(
            MessageBoardBlacklist.target_player_id == player_id,
            MessageBoardBlacklist.is_active == True
        )
        record = (await session.execute(stmt)).scalars().first()

        if not record:
            return False, None

        # 检查是否过期
        if record.is_expired():
            # 自动解禁
            record.is_active = False
            await session.commit()
            return False, None

        # 在 session context 内部提取所有需要的信息，避免在 context 外部访问数据库对象
        remaining_time = record.get_remaining_time()

    # 在 session context 外部返回结果，确保连接已正确关闭
    return True, remaining_time


def check_level_requirement(player_level: int) -> tuple[bool, str]:
    """
    检查玩家等级是否满足发言要求

    Returns:
        (is_allowed, message): 是否允许发言，提示信息
    """
    if player_level < MIN_LEVEL_TO_POST:
        return False, f"⛔ 等级不足！需要达到{MIN_LEVEL_TO_POST}级才能发言"
    return True, ""


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
        time_str = rec.created_at.strftime("%m-%d %H:%M")

        # 特殊处理：系统消息（player_id == "SYSTEM"）
        if rec.player_id == "SYSTEM":
            if scope is MessageScope.WORLD:
                lines.append(
                    f">📢 系统消息 ({time_str})\n{rec.content}"
                )
            continue

        sender = players.get(rec.player_id)
        if not sender:
            continue
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

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await leave_msg_cmd.finish("⛔ 请先创建角色")

        # 检查等级限制
        is_allowed, level_msg = check_level_requirement(player.level)
        if not is_allowed:
            await leave_msg_cmd.finish(level_msg)

        # 检查黑名单
        is_banned, remaining_time = await check_blacklist(player.id)
        if is_banned:
            await leave_msg_cmd.finish(f"⛔ 你已被禁言，剩余时间：{remaining_time}")

        # 使用新API检测违禁内容
        is_prohibited, words, label_desc, sub_label_desc = await check_prohibited_content(content)
        if is_prohibited:
            # 如果检测到违禁内容,直接拒绝发布
            words_info = f"违禁词: {', '.join(words[:5])}" if words else ""  # 最多显示5个
            label_info = f"\n类型: {label_desc}" if label_desc else ""
            sub_label_info = f" - {sub_label_desc}" if sub_label_desc else ""

            await leave_msg_cmd.finish(
                f"⛔ 检测到违规内容,留言发布失败\n"
                f"{words_info}{label_info}{sub_label_info}\n"
                f"请修改后重试"
            )

        msg_rec = WorldMessage(
            player_id=player.id,
            recipient_id=None,
            content=content,
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

    sender_last_check = None
    async with safe_session() as session:
        sender = await get_unified_player(session, event)
        if not sender:
            await private_msg_cmd.finish("⛔ 请先创建角色")

        # 检查等级限制
        is_allowed, level_msg = check_level_requirement(sender.level)
        if not is_allowed:
            await private_msg_cmd.finish(level_msg)

        # 检查黑名单
        is_banned, remaining_time = await check_blacklist(sender.id)
        if is_banned:
            await private_msg_cmd.finish(f"⛔ 你已被禁言，剩余时间：{remaining_time}")

        # 使用新API检测违禁内容
        is_prohibited, words, label_desc, sub_label_desc = await check_prohibited_content(message_body)
        if is_prohibited:
            # 如果检测到违禁内容,直接拒绝发送
            words_info = f"违禁词: {', '.join(words[:5])}" if words else ""  # 最多显示5个
            label_info = f"\n类型: {label_desc}" if label_desc else ""
            sub_label_info = f" - {sub_label_desc}" if sub_label_desc else ""

            await private_msg_cmd.finish(
                f"⛔ 检测到违规内容,私信发送失败\n"
                f"{words_info}{label_info}{sub_label_info}\n"
                f"请修改后重试"
            )

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
            content=message_body,
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


# ==================== 管理员命令处理器 ====================

@ban_cmd.handle()
async def handle_ban(event: MessageEvent, args: Message = CommandArg()):
    """禁言命令：【禁言 UID [原因] [时长]】"""
    if not is_admin(event.get_user_id()):
        await ban_cmd.finish("⛔ 权限不足，该命令仅限管理员使用")

    raw_text = args.extract_plain_text().strip()
    if not raw_text:
        await ban_cmd.finish("⛔ 用法：【禁言 UID】或【禁言 UID 原因】或【禁言 UID 原因 时长】\n时长格式：3d（3天）、24h（24小时）、永久")

    parts = raw_text.split(maxsplit=2)
    target_uid_text = parts[0]
    reason = parts[1] if len(parts) > 1 else "违反社区规定"
    duration_text = parts[2] if len(parts) > 2 else "永久"

    try:
        target_uid = int(target_uid_text)
    except ValueError:
        await ban_cmd.finish("⛔ UID 格式错误，请输入数字")

    # 解析时长
    expires_at = None
    if duration_text != "永久":
        if duration_text.endswith('d'):
            days = int(duration_text[:-1])
            expires_at = datetime.now() + timedelta(days=days)
        elif duration_text.endswith('h'):
            hours = int(duration_text[:-1])
            expires_at = datetime.now() + timedelta(hours=hours)
        else:
            await ban_cmd.finish("⛔ 时长格式错误，请使用：3d（3天）、24h（24小时）或永久")

    async with safe_session() as session:
        # 获取管理员信息
        admin = await get_unified_player(session, event)
        if not admin:
            await ban_cmd.finish("⛔ 请先创建角色")

        # 获取目标玩家
        target = (
            await session.execute(select(Player).where(Player.uid == target_uid))
        ).scalars().first()
        if not target:
            await ban_cmd.finish(f"⛔ 未找到 UID 为 {target_uid} 的玩家")

        # 检查是否已在黑名单
        existing = (
            await session.execute(
                select(MessageBoardBlacklist).where(
                    MessageBoardBlacklist.target_player_id == target.id,
                    MessageBoardBlacklist.is_active == True
                )
            )
        ).scalars().first()

        if existing:
            # 更新现有记录
            existing.reason = reason
            existing.expires_at = expires_at
            existing.admin_id = admin.id
            existing.created_at = datetime.now()
        else:
            # 创建新记录
            blacklist_record = MessageBoardBlacklist(
                target_player_id=target.id,
                admin_id=admin.id,
                reason=reason,
                expires_at=expires_at,
                is_active=True
            )
            session.add(blacklist_record)

        await session.commit()

    duration_str = duration_text if duration_text == "永久" else duration_text
    msg = f"✅ 已禁言玩家【{target.nickname}】(UID:{target_uid})\n原因：{reason}\n时长：{duration_str}"
    await ban_cmd.finish(message_add_head(msg, event))


@unban_cmd.handle()
async def handle_unban(event: MessageEvent, args: Message = CommandArg()):
    """解禁命令：【解禁 UID】"""
    if not is_admin(event.get_user_id()):
        await unban_cmd.finish("⛔ 权限不足，该命令仅限管理员使用")

    raw_text = args.extract_plain_text().strip()
    if not raw_text:
        await unban_cmd.finish("⛔ 用法：【解禁 UID】")

    try:
        target_uid = int(raw_text)
    except ValueError:
        await unban_cmd.finish("⛔ UID 格式错误，请输入数字")

    async with safe_session() as session:
        # 获取目标玩家
        target = (
            await session.execute(select(Player).where(Player.uid == target_uid))
        ).scalars().first()
        if not target:
            await unban_cmd.finish(f"⛔ 未找到 UID 为 {target_uid} 的玩家")

        # 查找黑名单记录
        record = (
            await session.execute(
                select(MessageBoardBlacklist).where(
                    MessageBoardBlacklist.target_player_id == target.id,
                    MessageBoardBlacklist.is_active == True
                )
            )
        ).scalars().first()

        if not record:
            await unban_cmd.finish(f"⛔ 玩家【{target.nickname}】(UID:{target_uid}) 不在黑名单中")

        # 解禁
        record.is_active = False
        await session.commit()

    msg = f"✅ 已解除玩家【{target.nickname}】(UID:{target_uid}) 的禁言"
    await unban_cmd.finish(message_add_head(msg, event))


@blacklist_cmd.handle()
async def handle_blacklist(event: MessageEvent):
    """查看黑名单列表"""
    if not is_admin(event.get_user_id()):
        await blacklist_cmd.finish("⛔ 权限不足，该命令仅限管理员使用")

    async with safe_session() as session:
        records = (
            await session.execute(
                select(MessageBoardBlacklist)
                .where(MessageBoardBlacklist.is_active == True)
                .order_by(MessageBoardBlacklist.created_at.desc())
            )
        ).scalars().all()

        if not records:
            await blacklist_cmd.finish(message_add_head("📋 当前黑名单为空", event))

        # 获取所有相关玩家信息
        player_ids = set()
        for rec in records:
            player_ids.add(rec.target_player_id)
            player_ids.add(rec.admin_id)

        players = {}
        for pid in player_ids:
            players[pid] = await session.get(Player, pid)

    lines = ["📋 留言板黑名单", "━━━━━━━━━━"]
    for rec in records:
        target_player = players.get(rec.target_player_id)
        admin_player = players.get(rec.admin_id)

        if not target_player:
            continue

        time_str = rec.created_at.strftime("%m-%d")
        remaining = rec.get_remaining_time()
        admin_name = admin_player.nickname if admin_player else "未知"

        lines.append(
            f">【{target_player.nickname}】UID:{target_player.uid}\n"
            f" 原因：{rec.reason or '无'}\n"
            f" 剩余：{remaining} | 操作员：{admin_name} | 时间：{time_str}"
        )

    await blacklist_cmd.finish(message_add_head("\n".join(lines), event))


@delete_msg_cmd.handle()
async def handle_delete_message(event: MessageEvent, args: Message = CommandArg()):
    """删除留言命令：【删除留言 留言ID】"""
    if not is_admin(event.get_user_id()):
        await delete_msg_cmd.finish("⛔ 权限不足，该命令仅限管理员使用")

    raw_text = args.extract_plain_text().strip()
    if not raw_text:
        await delete_msg_cmd.finish("⛔ 用法：【删除留言 留言ID】")

    try:
        message_id = int(raw_text)
    except ValueError:
        await delete_msg_cmd.finish("⛔ 留言ID格式错误，请输入数字")

    async with safe_session() as session:
        admin = await get_unified_player(session, event)
        if not admin:
            await delete_msg_cmd.finish("⛔ 请先创建角色")

        # 查找留言
        message = await session.get(WorldMessage, message_id)
        if not message:
            await delete_msg_cmd.finish(f"⛔ 未找到ID为 {message_id} 的留言")

        # 软删除（如果字段存在）
        # 由于WorldMessage模型可能还没有软删除字段，我们暂时直接删除
        # TODO: 等数据库迁移完成后，改为软删除
        sender = await session.get(Player, message.player_id)
        sender_name = sender.nickname if sender else "未知"

        await session.delete(message)
        await session.commit()

    msg = f"✅ 已删除留言 ID:{message_id}\n发送者：{sender_name}"
    await delete_msg_cmd.finish(message_add_head(msg, event))


# ==================== 最近更新 ====================

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

