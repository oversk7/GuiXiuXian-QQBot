from enum import Enum
import re
from datetime import datetime, timedelta

from nonebot import on_command, logger
import aiohttp
from urllib.parse import quote as url_quote
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import and_, or_, select
from sqlalchemy import func as _func

from ..models.db import safe_session
from ..models.player import Player
from ..models.world_message import WorldMessage
from ..models.message_blacklist import MessageBoardBlacklist
from ..models.guild import Guild
from ..utils import message_add_head
from ..utils_markdown import cmd, build_markdown
from ..platform_utils import get_unified_player, require_player
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
    """消息频道类型"""

    WORLD = "world"
    PRIVATE = "private"
    SYSTEM = "system"
    GUILD = "guild"


MAX_LEN = 120
PAGE_SIZE = 10
MIN_LEVEL_TO_POST = 10  # 最低发言等级，可以在config.yaml中配置

send_msg_cmd = on_command("发消息", aliases={"留言"}, block=True, priority=5)
view_board_cmd = on_command("消息", aliases={"留言板"}, block=True, priority=5)
private_msg_cmd = on_command("私信", aliases={"私聊"}, block=True, priority=5)

# ==================== 管理员命令 ====================
ban_cmd = on_command("禁言", block=True, priority=5)
unban_cmd = on_command("解禁", block=True, priority=5)
blacklist_cmd = on_command("黑名单", aliases={"黑名单列表"}, block=True, priority=5)
delete_msg_cmd = on_command("删除留言", block=True, priority=5)



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
        url = f"https://api.lolimi.cn/API/wjc/api.php?msg={url_quote(text)}"

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as http_session:
            async with http_session.get(url) as response:
                response.raise_for_status()
                data = await response.json()

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

    except aiohttp.ClientError as e:
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


async def get_unread_message_status(player_id: str) -> tuple[bool, bool, bool, bool]:
    """检查玩家各频道未读状态，返回 (world, private, system, guild)"""

    async with safe_session() as session:
        player = await session.get(Player, player_id)
        if not player:
            return False, False, False, False

        # 世界频道
        world_query = select(_func.count(WorldMessage.id)).where(
            WorldMessage.scope == "world"
        )
        if player.last_message_board_check:
            world_query = world_query.where(
                WorldMessage.created_at > player.last_message_board_check
            )
        world_count = (await session.execute(world_query)).scalar_one()

        # 私信
        private_query = select(_func.count(WorldMessage.id)).where(
            WorldMessage.scope == "private",
            WorldMessage.recipient_id == player_id,
        )
        if player.last_private_message_check:
            private_query = private_query.where(
                WorldMessage.created_at > player.last_private_message_check
            )
        private_count = (await session.execute(private_query)).scalar_one()

        # 系统频道
        system_query = select(_func.count(WorldMessage.id)).where(
            WorldMessage.scope == "system"
        )
        last_system = getattr(player, "last_system_check", None)
        if last_system:
            system_query = system_query.where(
                WorldMessage.created_at > last_system
            )
        system_count = (await session.execute(system_query)).scalar_one()

        # 公会频道
        guild_count = 0
        if player.guild_id:
            guild_query = select(_func.count(WorldMessage.id)).where(
                WorldMessage.scope == "guild",
                WorldMessage.guild_id == player.guild_id,
            )
            last_guild = getattr(player, "last_guild_check", None)
            if last_guild:
                guild_query = guild_query.where(
                    WorldMessage.created_at > last_guild
                )
            guild_count = (await session.execute(guild_query)).scalar_one()

        return world_count > 0, private_count > 0, system_count > 0, guild_count > 0


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


async def _get_message_page(
    scope: MessageScope, viewer_id: str, page: int, guild_id: int | None = None
):
    """获取指定频道的消息分页数据"""

    async with safe_session() as session:
        viewer = await session.get(Player, viewer_id)

        if scope is MessageScope.WORLD:
            filter_expr = WorldMessage.scope == "world"
        elif scope is MessageScope.PRIVATE:
            filter_expr = and_(
                WorldMessage.scope == "private",
                or_(
                    WorldMessage.recipient_id == viewer_id,
                    WorldMessage.player_id == viewer_id,
                ),
            )
        elif scope is MessageScope.SYSTEM:
            filter_expr = WorldMessage.scope == "system"
        elif scope is MessageScope.GUILD:
            if guild_id:
                target_guild_id = guild_id
            elif viewer and viewer.guild_id:
                target_guild_id = viewer.guild_id
            else:
                return 0, 0, page, [], {}
            filter_expr = WorldMessage.guild_id == target_guild_id
        else:
            filter_expr = WorldMessage.scope == "world"

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
            if rec.player_id and rec.player_id != "SYSTEM":
                player_ids.add(rec.player_id)
            if rec.recipient_id:
                player_ids.add(rec.recipient_id)

        players: dict[str, Player | None] = {}
        for pid in player_ids:
            players[pid] = await session.get(Player, pid)

        return total, total_pages, page, records, players


_SCOPE_NAMES = {
    MessageScope.WORLD: "世界",
    MessageScope.PRIVATE: "私信",
    MessageScope.SYSTEM: "系统",
    MessageScope.GUILD: "公会",
}


def _format_message_lines(
    scope: MessageScope,
    page: int,
    total_pages: int,
    records: list[WorldMessage],
    players: dict[str, Player | None],
    viewer_id: str,
    last_check: datetime | None = None,
    guild_name: str | None = None,
) -> str:
    """格式化消息列表为 Markdown，用分隔线清晰区分每条消息"""

    titles = {
        MessageScope.WORLD: "🌐 世界频道",
        MessageScope.PRIVATE: "📬 私信",
        MessageScope.SYSTEM: "📢 系统公告",
        MessageScope.GUILD: f"🏯 {guild_name}·公会频道" if guild_name else "🏯 公会频道",
    }
    title = titles.get(scope, "📋 消息")

    lines = [f"# {title}"]
    if total_pages > 0:
        lines.append(f"第{page}/{total_pages}页")

    msg_count = 0
    for rec in records:
        time_str = rec.created_at.strftime("%m-%d %H:%M")
        new_flag = "🆕 " if (last_check and rec.created_at > last_check) else ""

        lines.append("***")

        if scope is MessageScope.SYSTEM or rec.player_id == "SYSTEM":
            lines.append(f"📢 **系统公告**　{time_str}")
            lines.append(rec.content)
            msg_count += 1
            continue

        if scope is MessageScope.GUILD:
            sender = players.get(rec.player_id)
            if sender:
                lines.append(f"{new_flag}**{sender.nickname}** [UID:{sender.uid}]　{time_str}")
                lines.append(rec.content)
                msg_count += 1
            continue

        if scope is MessageScope.WORLD:
            sender = players.get(rec.player_id)
            if sender:
                lines.append(f"{new_flag}**{sender.nickname}** [UID:{sender.uid}]　{time_str}")
                lines.append(rec.content)
                msg_count += 1
            continue

        # 私信
        sender = players.get(rec.player_id)
        recipient = players.get(rec.recipient_id) if rec.recipient_id else None
        if not sender or not recipient:
            continue

        if rec.recipient_id == viewer_id:
            lines.append(f"{new_flag}📥 来自 **{sender.nickname}** [UID:{sender.uid}]　{time_str}")
            lines.append(rec.content)
        elif rec.player_id == viewer_id:
            lines.append(f"📤 发给 **{recipient.nickname}** [UID:{recipient.uid}]　{time_str}")
            lines.append(rec.content)
        msg_count += 1

    if msg_count == 0:
        empty_msgs = {
            MessageScope.WORLD: "世界频道空空如也，快来留下第一条消息吧！",
            MessageScope.PRIVATE: "暂无私信",
            MessageScope.SYSTEM: "暂无系统公告",
            MessageScope.GUILD: "暂无公会消息",
        }
        lines.append("***")
        lines.append(empty_msgs.get(scope, "暂无消息"))

    # ── 底部导航 ──
    lines.append("***")

    # 翻页
    nav = []
    scope_name = _SCOPE_NAMES.get(scope, "世界")
    if page > 1:
        nav.append(cmd(f"⬅️第{page - 1}页", f"消息 {scope_name} {page - 1}"))
    if page < total_pages:
        nav.append(cmd(f"➡️第{page + 1}页", f"消息 {scope_name} {page + 1}"))
    if nav:
        lines.append(" | ".join(nav))

    # 频道切换
    channels = []
    for s, label in [
        (MessageScope.WORLD, "🌐世界"),
        (MessageScope.PRIVATE, "📬私信"),
        (MessageScope.GUILD, "🏯公会"),
        (MessageScope.SYSTEM, "📢系统"),
    ]:
        if s != scope:
            channels.append(cmd(label, f"消息 {_SCOPE_NAMES[s]}"))
    lines.append(" | ".join(channels))

    # 快捷操作
    if scope is MessageScope.WORLD:
        lines.append(cmd("📝发消息", "发消息 ") + " | " + cmd("💬私信", "私信 "))
    elif scope is MessageScope.GUILD:
        lines.append(cmd("📝发公会消息", "发消息 公会 "))
    elif scope is MessageScope.PRIVATE:
        lines.append(cmd("💬发私信", "私信 "))

    return "\n".join(lines)


async def mark_scope_messages_as_read(player_id: str, scope: MessageScope):
    """标记指定频道的消息为已读"""
    async with safe_session() as session:
        player = await session.get(Player, player_id)
        if not player:
            return

        now = datetime.now()
        if scope is MessageScope.WORLD:
            player.last_message_board_check = now
        elif scope is MessageScope.PRIVATE:
            player.last_private_message_check = now
        elif scope is MessageScope.SYSTEM:
            player.last_system_check = now
        elif scope is MessageScope.GUILD:
            player.last_guild_check = now

        await session.commit()


def _parse_board_args(raw_text: str) -> tuple[MessageScope, int]:
    """解析消息命令参数，返回(频道, 页码)"""

    tokens = [token for token in re.split(r"\s+", raw_text) if token]
    scope = MessageScope.WORLD
    page = 1

    if tokens:
        first = tokens[0]
        if first in {"私信", "私聊", "信箱"}:
            scope = MessageScope.PRIVATE
            tokens = tokens[1:]
        elif first in {"系统", "系统消息", "公告"}:
            scope = MessageScope.SYSTEM
            tokens = tokens[1:]
        elif first in {"公会", "宗门", "帮派"}:
            scope = MessageScope.GUILD
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


@send_msg_cmd.handle()
async def handle_send_msg(event: MessageEvent, args: Message = CommandArg()):
    raw_text = args.extract_plain_text().strip()

    # 解析频道前缀
    tokens = re.split(r"\s+", raw_text, maxsplit=1)
    scope = MessageScope.WORLD
    content_raw = raw_text

    if tokens:
        first = tokens[0]
        if first in {"公会", "宗门", "帮派"}:
            scope = MessageScope.GUILD
            content_raw = tokens[1] if len(tokens) > 1 else ""
        elif first in {"系统"}:
            scope = MessageScope.SYSTEM
            content_raw = tokens[1] if len(tokens) > 1 else ""
        elif first in {"世界", "公共"}:
            scope = MessageScope.WORLD
            content_raw = tokens[1] if len(tokens) > 1 else ""

    content = clean_message_content(content_raw)

    if not content:
        await send_msg_cmd.finish(
            "⛔ 请输入消息内容\n"
            "格式：【发消息 内容】\n"
            "或指定频道：【发消息 世界/公会/系统 内容】"
        )
    if len(content) > MAX_LEN:
        await send_msg_cmd.finish(f"⛔ 消息不能超过 {MAX_LEN} 字符")

    player_guild_id = None
    player_guild_name = None

    async with safe_session() as session:
        player = await require_player(session, event, send_msg_cmd)

        # 系统频道：仅管理员
        if scope is MessageScope.SYSTEM:
            if not is_admin(event.get_user_id()):
                await send_msg_cmd.finish("⛔ 权限不足，系统频道仅管理员可用")

        # 公会频道：必须有公会
        elif scope is MessageScope.GUILD:
            if not player.guild_id:
                await send_msg_cmd.finish("⛔ 你未加入任何公会，无法发送公会消息")
            player_guild_id = player.guild_id
            guild = await session.get(Guild, player_guild_id)
            player_guild_name = guild.name if guild else None

        # 世界频道：等级 + 黑名单
        else:
            is_allowed, level_msg = check_level_requirement(player.level)
            if not is_allowed:
                await send_msg_cmd.finish(level_msg)

            is_banned, remaining_time = await check_blacklist(player.id)
            if is_banned:
                await send_msg_cmd.finish(f"⛔ 你已被禁言，剩余时间：{remaining_time}")

        # 违禁词检查（管理员发系统消息跳过）
        if scope is not MessageScope.SYSTEM:
            is_prohibited, words, label_desc, sub_label_desc = await check_prohibited_content(content)
            if is_prohibited:
                words_info = f"违禁词: {', '.join(words[:5])}" if words else ""
                label_info = f"\n类型: {label_desc}" if label_desc else ""
                sub_label_info = f" - {sub_label_desc}" if sub_label_desc else ""
                await send_msg_cmd.finish(
                    f"⛔ 检测到违规内容，消息发送失败\n"
                    f"{words_info}{label_info}{sub_label_info}\n"
                    f"请修改后重试"
                )

        msg_rec = WorldMessage(
            player_id=player.id,
            recipient_id=None,
            scope=scope.value,
            guild_id=player_guild_id,
            content=content,
            created_at=datetime.now(),
        )
        session.add(msg_rec)
        await session.commit()

    channel_names = {
        MessageScope.WORLD: "世界频道",
        MessageScope.GUILD: "公会频道",
        MessageScope.SYSTEM: "系统频道",
    }
    channel_name = channel_names.get(scope, "世界频道")

    await mark_scope_messages_as_read(player.id, scope)
    await send_msg_cmd.send(message_add_head(f"✅ 消息已发送至{channel_name}！", event))

    total, total_pages, page, records, players_map = await _get_message_page(
        scope, player.id, 1, guild_id=player_guild_id
    )
    if total == 0:
        await send_msg_cmd.finish(f"📭 {channel_name}暂无消息")

    lines = _format_message_lines(
        scope,
        page,
        total_pages,
        records,
        players_map,
        player.id,
        None,
        player_guild_name,
    )
    await send_msg_cmd.finish(build_markdown(lines))


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
            scope="private",
            content=message_body,
            created_at=datetime.now(),
        )
        session.add(msg_rec)
        await session.commit()

    # 主动群 @ 提醒收信人（失败不影响主流程）
    from ..notification_service import notify_player
    sender_name = sender.nickname
    await notify_player(target.id, f"📬 你有一条来自「{sender_name}」的新私信，发送【消息】查看！")

    await private_msg_cmd.send(message_add_head("✅ 私信已发送！", event))

    total, total_pages, page, records, players = await _get_message_page(
        MessageScope.PRIVATE, sender.id, 1
    )
    lines = _format_message_lines(
        MessageScope.PRIVATE,
        page,
        total_pages,
        records,
        players,
        sender.id,
        sender_last_check,
    )
    await private_msg_cmd.finish(build_markdown(lines))


@view_board_cmd.handle()
async def handle_view_board(event: MessageEvent, args: Message = CommandArg()):
    scope, page = _parse_board_args(args.extract_plain_text().strip())

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        guild_name = None
        if scope is MessageScope.GUILD and player and player.guild_id:
            guild = await session.get(Guild, player.guild_id)
            guild_name = guild.name if guild else None
    if not player:
        await view_board_cmd.finish("⛔ 请先创建角色")

    player_id = player.id
    await mark_scope_messages_as_read(player_id, scope)

    total, total_pages, page, records, players = await _get_message_page(
        scope, player_id, page
    )

    last_check = None
    if scope is MessageScope.PRIVATE:
        last_check = player.last_private_message_check
    elif scope is MessageScope.SYSTEM:
        last_check = getattr(player, "last_system_check", None)
    elif scope is MessageScope.GUILD:
        last_check = getattr(player, "last_guild_check", None)

    lines = _format_message_lines(
        scope,
        page,
        total_pages,
        records,
        players,
        player_id,
        last_check,
        guild_name,
    )
    await view_board_cmd.finish(build_markdown(lines))


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
