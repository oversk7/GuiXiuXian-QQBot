from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select
from datetime import datetime
from sqlalchemy import func as _func
import re

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
    "翻墙", "VPN", "科学上网","傻逼","傻比","煞笔"
]


def filter_banned_words(content: str) -> str:
    """过滤违禁词，将违禁词替换为**

    Args:
        content: 原始内容

    Returns:
        过滤后的内容
    """
    if not content:
        return content

    filtered_content = content

    # 遍历违禁词列表，进行替换（不区分大小写）
    for banned_word in BANNED_WORDS:
        # 使用正则表达式进行不区分大小写的替换
        pattern = re.compile(re.escape(banned_word), re.IGNORECASE)
        if pattern.search(filtered_content):
            # 将违禁词替换为相同长度的*号
            replacement = "*" * len(banned_word)
            filtered_content = pattern.sub(replacement, filtered_content)

    return filtered_content


def clean_message_content(content: str) -> str:
    """清理消息内容，移除QQ表情源码"""
    # 移除QQ表情源码，格式如：<faceType=1,faceId="13",ext="eyJ0ZXh0Ijoi5ZGy54mZIn0=">
    content = re.sub(r'<faceType=\d+,faceId="[^"]*",ext="[^"]*">', '', content)

    # 移除其他可能的表情源码格式
    content = re.sub(r'<[^>]*faceType[^>]*>', '', content)
    content = re.sub(r'<[^>]*faceId[^>]*>', '', content)

    # 清理多余的空格
    content = re.sub(r'\s+', ' ', content).strip()

    return content


async def has_unread_messages(player_id: str) -> bool:
    """检查玩家是否有未读留言"""
    async with safe_session() as session:
        player = await session.get(Player, player_id)
        if not player:
            return False

        # 如果玩家从未查看过留言板，则检查是否有任何留言
        if not player.last_message_board_check:
            total_messages = (await session.execute(select(_func.count(WorldMessage.id)))).scalar_one()
            return total_messages > 0

        # 检查是否有比最后查看时间更新的留言
        newer_messages = (await session.execute(
            select(_func.count(WorldMessage.id)).where(
                WorldMessage.created_at > player.last_message_board_check
            )
        )).scalar_one()

        return newer_messages > 0


async def mark_messages_as_read(player_id: str):
    """标记玩家已读留言板"""
    async with safe_session() as session:
        player = await session.get(Player, player_id)
        if player:
            player.last_message_board_check = datetime.now()
            await session.commit()

leave_msg_cmd = on_command("留言", block=True, priority=5)
view_board_cmd = on_command("留言板", block=True, priority=5)

# ==================== 最近更新 ====================
latest_update_cmd = on_command("更新",aliases={"最近更新"}, block=True, priority=5)

MAX_LEN = 120
PAGE_SIZE = 10

@leave_msg_cmd.handle()
async def handle_leave_msg(event: MessageEvent, args: Message = CommandArg()):
    raw_content = args.extract_plain_text().strip()
    # 清理表情源码
    content = clean_message_content(raw_content)

    if not content:
        await leave_msg_cmd.finish("⛔ 请输入留言内容，例如：留言 今天好开心！")
    if len(content) > MAX_LEN:
        await leave_msg_cmd.finish(f"⛔ 留言不能超过 {MAX_LEN} 字符")

    # 过滤违禁词
    filtered_content = filter_banned_words(content)

    # 如果内容被过滤了，提醒用户
    if filtered_content != content:
        await leave_msg_cmd.send(message_add_head("⚠️ 检测到敏感词汇，已自动过滤", event))

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await leave_msg_cmd.finish("⛔ 请先创建角色")
        msg_rec = WorldMessage(player_id=player.id, content=filtered_content, created_at=datetime.now())
        session.add(msg_rec)
        await session.commit()

    # 标记玩家已读留言板（因为会显示留言板内容）
    await mark_messages_as_read(event.get_user_id())

    # 第一条：确认
    await leave_msg_cmd.send(message_add_head("✅ 留言已发布！", event))

    # 第二条：刷新第一页留言板
    async with safe_session() as session:
        total = (await session.execute(select(_func.count(WorldMessage.id)))).scalar_one()
        total_pages = (total - 1) // PAGE_SIZE + 1
        page = 1
        stmt = (
            select(WorldMessage).order_by(WorldMessage.created_at.desc()).limit(PAGE_SIZE)
        )
        records = (await session.execute(stmt)).scalars().all()

        lines = [f"🗒️ 世界留言板 (第{page}/{total_pages}页)", "━━━━━━━━━━"]
        for rec in records:
            p = await session.get(Player, rec.player_id)
            if not p:
                continue
            time_str = rec.created_at.strftime("%m-%d %H:%M")
            lines.append(f">{p.nickname}[UID:{p.uid}] ({time_str})\n{rec.content}")

    await leave_msg_cmd.finish(message_add_head("\n".join(lines), event))

@view_board_cmd.handle()
async def handle_view_board(event: MessageEvent, args: Message = CommandArg()):
    # 标记玩家已读留言板
    await mark_messages_as_read(event.get_user_id())

    # 解析页码
    page_text = args.extract_plain_text().strip()
    try:
        page = int(page_text) if page_text else 1
    except ValueError:
        page = 1
    page = max(1, page)

    async with safe_session() as session:
        total = (await session.execute(select(_func.count(WorldMessage.id)))).scalar_one()
        if total == 0:
            await view_board_cmd.finish("🗒️ 留言板空空如也，快来留下第一条留言吧！")

        total_pages = (total - 1) // PAGE_SIZE + 1
        page = min(page, total_pages)

        offset = (page - 1) * PAGE_SIZE
        stmt = (
            select(WorldMessage).order_by(WorldMessage.created_at.desc()).offset(offset).limit(PAGE_SIZE)
        )
        records = (await session.execute(stmt)).scalars().all()

        lines = [f"🗒️ 世界留言板 (第{page}/{total_pages}页)", "━━━━━━━━━━"]
        for rec in records:
            p = await session.get(Player, rec.player_id)
            if not p:
                continue
            time_str = rec.created_at.strftime("%m-%d %H:%M")
            lines.append(f">{p.nickname}[UID:{p.uid}] ({time_str})\n{rec.content}")
        await view_board_cmd.finish(message_add_head("\n".join(lines), event))

@latest_update_cmd.handle()
async def handle_latest_update(event: MessageEvent):
    async with safe_session() as session:
        rec = (await session.execute(
            select(WorldMessage).where(WorldMessage.player_id == 'D6A7BB606845F1AFF40ADA517F7BF306').order_by(WorldMessage.created_at.desc()).limit(1)
        )).scalars().first()
        if not rec:
            await latest_update_cmd.finish("暂无更新记录")
        player = await session.get(Player, rec.player_id)
        time_str = rec.created_at.strftime("%m-%d")
        msg = (
            f"📜 最近更新 ({time_str})\n"
            f"{rec.content}"
        )
        await latest_update_cmd.finish(message_add_head(msg, event)) 