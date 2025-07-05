from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select
from datetime import datetime
from sqlalchemy import func as _func

from ..models.db import safe_session
from ..models.player import Player
from ..models.world_message import WorldMessage
from ..utils import message_add_head

leave_msg_cmd = on_command("留言", block=True, priority=5)
view_board_cmd = on_command("留言板", block=True, priority=5)

MAX_LEN = 120
PAGE_SIZE = 10

@leave_msg_cmd.handle()
async def handle_leave_msg(event: MessageEvent, args: Message = CommandArg()):
    content = args.extract_plain_text().strip()
    if not content:
        await leave_msg_cmd.finish("⛔ 请输入留言内容，例如：留言 今天好开心！")
    if len(content) > MAX_LEN:
        await leave_msg_cmd.finish(f"⛔ 留言不能超过 {MAX_LEN} 字符")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await leave_msg_cmd.finish("⛔ 请先创建角色")
        msg_rec = WorldMessage(player_id=player.id, content=content, created_at=datetime.now())
        session.add(msg_rec)
        await session.commit()
    await leave_msg_cmd.finish(message_add_head("✅ 留言已发布！", event))

@view_board_cmd.handle()
async def handle_view_board(event: MessageEvent, args: Message = CommandArg()):
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
            lines.append(f"{p.nickname}[UID:{p.uid}] ({time_str})\n{rec.content}")
        await view_board_cmd.finish(message_add_head("\n".join(lines), event)) 