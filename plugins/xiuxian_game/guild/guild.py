from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select, func as _func
from datetime import datetime

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import Inventory
from ..models.guild import Guild
from ..config import config
from ..utils import message_add_head

create_guild_cmd = on_command("创建公会", block=True, priority=5)

@create_guild_cmd.handle()
async def handle_create_guild(event: MessageEvent, args: Message = CommandArg()):
    """消耗会长委任书创建公会：创建公会 公会名"""
    guild_name = args.extract_plain_text().strip()
    if not guild_name:
        await create_guild_cmd.finish("⛔ 格式错误，正确格式：创建公会 [公会名]")
    if len(guild_name) > 16:
        await create_guild_cmd.finish("⛔ 公会名称长度不能超过16个字符")

    async with safe_session() as session:
        # 获取玩家
        player = await session.get(Player, event.get_user_id())
        if not player:
            await create_guild_cmd.finish("⛔ 请先创建角色")
        if player.guild_id is not None:
            await create_guild_cmd.finish("⛔ 你已经加入公会，无法再次创建")

        # 检查会长委任书
        president_cfg = config.items_config["by_name"].get("会长委任书")
        if not president_cfg:
            await create_guild_cmd.finish("⚠️ 配置缺少 会长委任书")

        result = await session.execute(
            select(Inventory).where(
                Inventory.player_id == player.id,
                Inventory.item_id == president_cfg.item_id
            )
        )
        inv = result.scalars().first()
        if not inv or inv.quantity < 1:
            await create_guild_cmd.finish("⛔ 你没有会长委任书")

        # 检查公会名重复
        exist_stmt = select(Guild).where(Guild.name == guild_name)
        if (await session.execute(exist_stmt)).scalars().first():
            await create_guild_cmd.finish("⛔ 已存在同名公会")

        # 创建公会
        new_guild = Guild(name=guild_name, president_id=player.id, created_at=datetime.now())
        session.add(new_guild)
        await session.flush()  # 使 new_guild.id 获得值

        # 更新玩家
        player.guild_id = new_guild.id
        session.add(player)

        # 扣除委任书
        inv.quantity -= 1
        if inv.quantity <= 0:
            await session.delete(inv)

        await session.commit()

        msg = (
            f"🏰 公会『{guild_name}』正式成立！\n"
            f"▫️ 会长：{player.nickname}\n"
            f"▫️ 公会 ID：{new_guild.id}"
        )
        await create_guild_cmd.finish(message_add_head(msg, event))

# ==================== 公会信息 ====================
guild_info_cmd = on_command("公会", aliases={"我的公会", "公会信息"}, block=True, priority=5)

@guild_info_cmd.handle()
async def handle_guild_info(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or player.guild_id is None:
            await guild_info_cmd.finish("⛔ 你尚未加入任何公会")

        guild_obj = await session.get(Guild, player.guild_id)
        if not guild_obj:
            # 数据不一致，修正玩家字段
            player.guild_id = None
            session.add(player)
            await session.commit()
            await guild_info_cmd.finish("⚠️ 公会数据异常，请稍后重试")

        # 会长
        president = await session.get(Player, guild_obj.president_id)
        # 成员统计
        count_stmt = select(_func.count(Player.id)).where(Player.guild_id == guild_obj.id)
        member_count = (await session.execute(count_stmt)).scalar_one()

        msg = (
            f"🏰 公会面板『{guild_obj.name}』\n"
            f"▫️ 公会 ID：{guild_obj.id}\n"
            f"▫️ 会长：{president.nickname if president else '未知'}\n"
            f"▫️ 成员数量：{member_count}\n"
            f"▫️ 创建时间：{guild_obj.created_at.strftime('%Y-%m-%d %H:%M')}"
        )
        await guild_info_cmd.finish(message_add_head(msg, event))

# ==================== 加入公会 ====================
join_guild_cmd = on_command("加入公会", block=True, priority=5)

@join_guild_cmd.handle()
async def handle_join_guild(event: MessageEvent, args: Message = CommandArg()):
    guild_id_str = args.extract_plain_text().strip()
    if not guild_id_str:
        await join_guild_cmd.finish("⛔ 格式错误，正确格式：加入公会 [公会ID]")
    try:
        guild_id = int(guild_id_str)
    except ValueError:
        await join_guild_cmd.finish("⛔ 公会 ID 必须是数字")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await join_guild_cmd.finish("⛔ 请先创建角色")
        if player.guild_id is not None:
            await join_guild_cmd.finish("⛔ 你已经加入公会，无法再次加入")

        guild_obj = await session.get(Guild, guild_id)
        if not guild_obj:
            await join_guild_cmd.finish("⛔ 未找到该公会")

        # 容量检查
        def _capacity(lv: int) -> int:
            return 10 + (lv - 1) * 5
        member_cnt = (await session.execute(select(_func.count(Player.id)).where(Player.guild_id == guild_obj.id))).scalar_one()
        if member_cnt >= _capacity(guild_obj.level):
            await join_guild_cmd.finish("⛔ 该公会人数已满，无法加入")

        # 直接加入（后期可改为申请制）
        player.guild_id = guild_obj.id
        session.add(player)
        await session.commit()

        msg = (
            f"🎉 你已加入公会『{guild_obj.name}』！\n"
            f"▫️ 会长：{(await session.get(Player, guild_obj.president_id)).nickname}"
        )
        await join_guild_cmd.finish(message_add_head(msg, event))

# ==================== 退出公会 ====================
quit_guild_cmd = on_command("退会", aliases={"退出公会"}, block=True, priority=5)

@quit_guild_cmd.handle()
async def handle_quit_guild(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or player.guild_id is None:
            await quit_guild_cmd.finish("⛔ 你未加入任何公会")

        guild_obj = await session.get(Guild, player.guild_id)
        if not guild_obj:
            player.guild_id = None
            session.add(player)
            await session.commit()
            await quit_guild_cmd.finish("⚠️ 公会数据异常，已自动脱离")

        if guild_obj.president_id == player.id:
            await quit_guild_cmd.finish("⛔ 你是会长，不能直接退会，可使用【解散公会】或将会长转让后再退会")

        player.guild_id = None
        session.add(player)
        await session.commit()
        await quit_guild_cmd.finish(message_add_head(f"🚪 你已退出公会『{guild_obj.name}』", event))

# ==================== 解散公会 ====================

dissolve_guild_cmd = on_command("解散公会", block=True, priority=5)

@dissolve_guild_cmd.handle()
async def handle_dissolve_guild(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or player.guild_id is None:
            await dissolve_guild_cmd.finish("⛔ 你未加入公会")

        guild_obj = await session.get(Guild, player.guild_id)
        if not guild_obj:
            player.guild_id = None
            session.add(player)
            await session.commit()
            await dissolve_guild_cmd.finish("⚠️ 公会数据异常，已自动脱离")

        if guild_obj.president_id != player.id:
            await dissolve_guild_cmd.finish("⛔ 只有会长才能解散公会")

        # 将所有成员 guild_id 置空
        await session.execute(
            select(Player).where(Player.guild_id == guild_obj.id)
        )  # We'll fetch players first
        members = (await session.execute(select(Player).where(Player.guild_id == guild_obj.id))).scalars().all()
        for m in members:
            m.guild_id = None
            session.add(m)

        # 删除公会
        await session.delete(guild_obj)
        await session.commit()

        await dissolve_guild_cmd.finish(message_add_head("⚠️ 公会已解散，江湖再见", event))

# ==================== 公会成员列表 ====================
member_list_cmd = on_command("公会成员", aliases={"成员列表"}, block=True, priority=5)

@member_list_cmd.handle()
async def handle_member_list(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or player.guild_id is None:
            await member_list_cmd.finish("⛔ 你未加入任何公会")
        guild_obj = await session.get(Guild, player.guild_id)
        if not guild_obj:
            await member_list_cmd.finish("⚠️ 公会数据异常")

        stmt = select(Player).where(Player.guild_id == guild_obj.id).order_by(Player.guild_contribution.desc(), Player.level.desc())
        members = (await session.execute(stmt)).scalars().all()
        lines = [f"👥 公会成员『{guild_obj.name}』({len(members)}人)", "━━━━━━━━━━"]
        for idx, m in enumerate(members, 1):
            mark = "👑" if m.id == guild_obj.president_id else ""
            lines.append(f"{idx}. {m.nickname}{mark} Lv.{m.level} 贡:{m.guild_contribution}")
        await member_list_cmd.finish(message_add_head("\n".join(lines), event))

# ==================== 捐献金币 ====================
donate_cmd = on_command("捐献金币", aliases={"捐款", "捐献"}, block=True, priority=5)

@donate_cmd.handle()
async def handle_donate(event: MessageEvent, args: Message = CommandArg()):
    amt_str = args.extract_plain_text().strip()
    if not amt_str:
        await donate_cmd.finish("⛔ 格式错误，示例：捐献金币 1000")
    try:
        amt = int(amt_str)
        if amt <= 0:
            raise ValueError
    except ValueError:
        await donate_cmd.finish("⛔ 金额必须为正整数")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or player.guild_id is None:
            await donate_cmd.finish("⛔ 你未加入任何公会")
        if player.gold < amt:
            await donate_cmd.finish("⛔ 金币不足")

        guild_obj = await session.get(Guild, player.guild_id)
        if not guild_obj:
            await donate_cmd.finish("⚠️ 公会数据异常")

        # 计算贡献和公会经验
        player.gold -= amt
        player.guild_contribution += amt
        guild_obj.exp += amt

        # 升级检查：每级需要 level * 1000 经验
        up_need = guild_obj.level * 1000
        leveled = False
        while guild_obj.exp >= up_need:
            guild_obj.exp -= up_need
            guild_obj.level += 1
            leveled = True
            up_need = guild_obj.level * 1000
        session.add_all([player, guild_obj])
        await session.commit()

        msg = (
            f"💰 捐献成功！金币 -{amt}\n"
            f"▫️ 个人贡献：{player.guild_contribution}\n"
            f"▫️ 公会经验：{guild_obj.exp}/{guild_obj.level*1000}\n"
        )
        if leveled:
            msg += f"🎉 公会等级提升至 Lv.{guild_obj.level}!"
        await donate_cmd.finish(message_add_head(msg, event))

# ==================== 转让会长 ====================
transfer_cmd = on_command("转让会长", block=True, priority=5)

@transfer_cmd.handle()
async def handle_transfer(event: MessageEvent, args: Message = CommandArg()):
    uid_str = args.extract_plain_text().strip()
    if not uid_str:
        await transfer_cmd.finish("⛔ 格式错误，示例：转让会长 123")
    try:
        target_uid = int(uid_str)
    except ValueError:
        await transfer_cmd.finish("⛔ UID 必须是数字")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or player.guild_id is None:
            await transfer_cmd.finish("⛔ 你未加入公会")
        guild_obj = await session.get(Guild, player.guild_id)
        if guild_obj.president_id != player.id:
            await transfer_cmd.finish("⛔ 只有会长才能转让职位")

        target_player_stmt = select(Player).where(Player.uid == target_uid, Player.guild_id == guild_obj.id)
        target_player = (await session.execute(target_player_stmt)).scalars().first()
        if not target_player:
            await transfer_cmd.finish("⛔ 未找到目标成员或对方不在本公会")

        guild_obj.president_id = target_player.id
        session.add(guild_obj)
        await session.commit()
        msg = f"👑 会长职位已转让给 {target_player.nickname}[UID:{target_player.uid}]"
        await transfer_cmd.finish(message_add_head(msg, event))

# ==================== 公会列表 ====================
list_guilds_cmd = on_command("公会列表", aliases={"公会排行"}, block=True, priority=5)

@list_guilds_cmd.handle()
async def handle_list_guilds(event: MessageEvent, args: Message = CommandArg()):
    page_size = 10
    arg = args.extract_plain_text().strip()
    try:
        page = int(arg) if arg else 1
    except ValueError:
        page = 1
    page = max(1, page)

    async with safe_session() as session:
        # 统计总数
        total = (await session.execute(select(_func.count(Guild.id)))).scalar_one()
        if total == 0:
            await list_guilds_cmd.finish("暂无公会")
        total_pages = (total - 1) // page_size + 1
        page = min(page, total_pages)

        offset = (page - 1) * page_size
        stmt = (
            select(Guild)
            .order_by(Guild.level.desc(), Guild.exp.desc())
            .offset(offset)
            .limit(page_size)
        )
        guilds = (await session.execute(stmt)).scalars().all()

    # 容量计算公式：基础10人，每级 +5 人
    def _capacity(lv: int) -> int:
        return 10 + (lv - 1) * 5

    lines = [f"🏰 公会排行榜 (第{page}/{total_pages}页)", "━━━━━━━━━━"]
    start_idx = offset + 1
    # 统计成员数量
    for idx, g in enumerate(guilds, start_idx):
        cnt = (await session.execute(select(_func.count(Player.id)).where(Player.guild_id == g.id))).scalar_one()
        cap = _capacity(g.level)
        lines.append(f"{idx}. 『{g.name}』 Lv.{g.level} ({cnt}/{cap}) Exp:{g.exp}")

    await list_guilds_cmd.finish(message_add_head("\n".join(lines), event)) 