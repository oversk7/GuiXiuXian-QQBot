from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select, func as _func
from datetime import datetime, date

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..models.guild import Guild
from ..config import config
from ..utils import message_add_head
from ..models.guild_application import GuildApplication as _GA
from ..models.donation_log import PlayerDonationLog
from ..models.guild_teleport_log import GuildTeleportLog
from ..models.navigation_task import NavigationTask

# ===== 工具函数 =====
# 翻译大数字为 w（万）单位，保留 1 位小数，10w 以下不显示 w
def _fmt_w(num: int | float) -> str:
    if num < 100000:
        return f"{num}"
    return f"{num / 10000:.1f}w"

# ---- 公会升级经验表 ----
def _need_exp_for_level(level: int) -> int:
    """返回当前等级升到下一等级所需经验"""
    if level <= 5:
        return 1000 * (5 ** (level - 1))
    else:
        return 1000 * 250 * (level - 5)

# ---------------- 捐献金币配置 ----------------
_DONATE_DAILY_LIMIT = 70_000                 # 每人每日可捐最大金币
_DONATE_GOLD_TO_POINT_RATIO = 0.8           # 金币转积分折扣率

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
            select(ItemInstance).where(
                ItemInstance.player_id == player.id,
                ItemInstance.item_id == president_cfg.item_id
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
        # 容量计算函数
        def _capacity(lv: int) -> int:
            return 10 + (lv - 1) * 5
        capacity = _capacity(guild_obj.level)
        # 经验显示：当前 / 升级所需（均转换为 w 单位一位小数）
        exp_current = _fmt_w(guild_obj.exp)
        exp_need = _fmt_w(_need_exp_for_level(guild_obj.level))

        # 基地信息
        base_info = ""
        if guild_obj.base_x is not None and guild_obj.base_y is not None:
            base_info = (
                f"▫️ 基地坐标：({guild_obj.base_x}, {guild_obj.base_y})\n"
                f"▫️ 势力范围：{guild_obj.territory_range}×{guild_obj.territory_range}\n"
            )
        elif guild_obj.level >= 5:
            base_info = f"▫️ 基地坐标：未设置（可使用【设置基地】命令）\n"

        msg = (
            f"🏰 公会面板\n"
            f"▫️『{guild_obj.name}』[ID:{guild_obj.id}] Lv.{guild_obj.level}\n"
            f"▫️ 会长：{president.nickname if president else '未知'}\n"
            f"▫️ 人数：{member_count}/{capacity}\n"
            f"▫️ 经验：{exp_current}/{exp_need}\n"
            f"▫️ 创建时间：{guild_obj.created_at.strftime('%Y-%m-%d')}\n"
            f"{base_info}"
            f"▫️ 公告：{guild_obj.notice or '暂无公告'}"
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

        # 容量计算函数
        def _capacity(lv: int) -> int:
            return 10 + (lv - 1) * 5

        # 是否已申请
        exist_app = (await session.execute(
            select(_GA).where(_GA.player_id == player.id, _GA.guild_id == guild_obj.id, _GA.status == "PENDING")
        )).scalars().first()
        if exist_app:
            await join_guild_cmd.finish("⚠️ 你已提交申请，请等待会长审核")

        # 容量预检查：如果已满，拒绝申请
        member_cnt = (await session.execute(select(_func.count(Player.id)).where(Player.guild_id == guild_obj.id))).scalar_one()
        if member_cnt >= _capacity(guild_obj.level):
            await join_guild_cmd.finish("⛔ 该公会人数已满，无法申请")

        # 创建申请记录
        app = _GA(guild_id=guild_obj.id, player_id=player.id)
        session.add(app)
        await session.commit()

        await join_guild_cmd.finish(message_add_head(f"✅ 已向『{guild_obj.name}』提交入会申请，等待审核", event))

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
            lines.append(f"{idx}. {m.nickname}{mark} Lv.{m.level} 贡:{_fmt_w(m.guild_contribution)}")
        await member_list_cmd.finish(message_add_head("\n".join(lines), event))

# ==================== 捐献金币 ====================
donate_cmd = on_command("捐献金币", aliases={"贡献", "捐献","上供"}, block=True, priority=5)

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

        # 当日捐献额度校验
        donated_today_stmt = select(_func.coalesce(_func.sum(PlayerDonationLog.amount), 0)).where(
            PlayerDonationLog.player_id == player.id,
            PlayerDonationLog.donate_date == date.today(),
        )
        donated_today = (await session.execute(donated_today_stmt)).scalar_one()
        if donated_today + amt > _DONATE_DAILY_LIMIT:
            remain = _DONATE_DAILY_LIMIT - donated_today
            await donate_cmd.finish(f"⛔ 今日还可捐献 {remain} 金币（每日上限 {_DONATE_DAILY_LIMIT}）")

        guild_obj = await session.get(Guild, player.guild_id)
        if not guild_obj:
            await donate_cmd.finish("⚠️ 公会数据异常")

        # ---------------- 扣款 & 积分 ----------------
        player.gold -= amt
        donate_points = int(amt * _DONATE_GOLD_TO_POINT_RATIO)
        player.gold2 += donate_points  # 积分增加

        # 贡献与公会经验累计（贡献不再消耗）
        player.guild_contribution += amt
        guild_obj.exp += amt

        # 写入捐献日志
        session.add(PlayerDonationLog(player_id=player.id, donate_date=date.today(), amount=amt))

        # 升级检查
        up_need = _need_exp_for_level(guild_obj.level)
        leveled = False
        while guild_obj.exp >= up_need:
            guild_obj.exp -= up_need
            guild_obj.level += 1
            leveled = True
            up_need = _need_exp_for_level(guild_obj.level)

        session.add_all([player, guild_obj])
        await session.commit()

        exp_current_str = _fmt_w(guild_obj.exp)
        exp_need_str = _fmt_w(_need_exp_for_level(guild_obj.level))

        msg = (
            f"💰 捐献成功！金币 -{amt}\n"
            f"✨ 获得积分：+{donate_points}\n"
            f"▫️ 个人贡献：{_fmt_w(player.guild_contribution)}\n"
            f"▫️ 公会经验：{exp_current_str}/{exp_need_str}\n"
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
        base_info = ""
        if g.base_x is not None and g.base_y is not None:
            base_info = f" 基地:({g.base_x},{g.base_y}) 势力:{g.territory_range}"
        lines.append(f"{idx}. 『{g.name}』 Lv.{g.level} ({cnt}/{cap}){base_info}")

    await list_guilds_cmd.finish(message_add_head("\n".join(lines), event))

# ==================== 申请列表 ====================
application_list_cmd = on_command("申请列表", block=True, priority=5)

@application_list_cmd.handle()
async def handle_app_list(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or player.guild_id is None:
            await application_list_cmd.finish("⛔ 你未加入公会")
        guild_obj = await session.get(Guild, player.guild_id)
        if guild_obj.president_id != player.id:
            await application_list_cmd.finish("⛔ 只有会长可查看申请列表")

        apps = (await session.execute(
            select(_GA).where(_GA.guild_id == guild_obj.id, _GA.status == "PENDING")
        )).scalars().all()
        if not apps:
            await application_list_cmd.finish("暂无待处理申请")

        lines = ["📑 待处理入会申请", "━━━━━━━━━━"]
        for a in apps:
            applicant = await session.get(Player, a.player_id)
            lines.append(f"UID:{applicant.uid} {applicant.nickname} Lv.{applicant.level} 贡献:{applicant.guild_contribution}")
        await application_list_cmd.finish(message_add_head("\n".join(lines), event))

# ==================== 同意/拒绝申请 ====================
approve_cmd = on_command("同意入会", block=True, priority=5)
reject_cmd = on_command("拒绝入会", block=True, priority=5)

async def _process_application(event: MessageEvent, args: Message, approve: bool):
    uid_str = args.extract_plain_text().strip()
    if not uid_str:
        await (approve_cmd if approve else reject_cmd).finish("格式：同意入会 UID 或 拒绝入会 UID")
    try:
        target_uid = int(uid_str)
    except ValueError:
        await (approve_cmd if approve else reject_cmd).finish("UID 必须为数字")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or player.guild_id is None:
            await (approve_cmd if approve else reject_cmd).finish("⛔ 你未加入公会")
        guild_obj = await session.get(Guild, player.guild_id)
        if guild_obj.president_id != player.id:
            await (approve_cmd if approve else reject_cmd).finish("⛔ 只有会长可操作")

        applicant = (await session.execute(select(Player).where(Player.uid == target_uid))).scalars().first()
        if not applicant:
            await (approve_cmd if approve else reject_cmd).finish("⛔ 未找到该 UID")

        app = (await session.execute(
            select(_GA).where(_GA.guild_id == guild_obj.id, _GA.player_id == applicant.id, _GA.status == "PENDING")
        )).scalars().first()
        if not app:
            await (approve_cmd if approve else reject_cmd).finish("⛔ 无待处理申请")

        if approve:
            # 若申请人已加入其他公会，则不能同意
            if applicant.guild_id is not None and applicant.guild_id != guild_obj.id:
                app.status = "REJECTED"
                session.add(app)
                await session.commit()
                await (approve_cmd if approve else reject_cmd).finish(message_add_head("⛔ 该玩家已加入其他公会，无法同意", event))

            # 容量检查
            def _capacity(lv:int):
                return 10 + (lv - 1) * 5
            cnt = (await session.execute(select(_func.count(Player.id)).where(Player.guild_id == guild_obj.id))).scalar_one()
            if cnt >= _capacity(guild_obj.level):
                await (approve_cmd if approve else reject_cmd).finish("⛔ 公会人数已满，无法同意")
            applicant.guild_id = guild_obj.id
            app.status = "APPROVED"

            # 将该玩家其他待处理申请全部标记为 REJECTED
            await session.execute(
                _GA.__table__.update()
                .where(_GA.player_id == applicant.id, _GA.status == "PENDING", _GA.id != app.id)
                .values(status="REJECTED")
            )

            result_msg = f"✅ 已同意 {applicant.nickname}[UID:{target_uid}] 加入公会"
        else:
            app.status = "REJECTED"
            result_msg = f"🚫 已拒绝 {applicant.nickname}[UID:{target_uid}] 的申请"
        session.add_all([app, applicant])
        await session.commit()
        await (approve_cmd if approve else reject_cmd).finish(message_add_head(result_msg, event))

@approve_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    await _process_application(event, args, True)

@reject_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    await _process_application(event, args, False)

# ==================== 公会公告 ====================
notice_cmd = on_command("公会公告", aliases={"公告"}, block=True, priority=5)

@notice_cmd.handle()
async def handle_notice(event: MessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or player.guild_id is None:
            await notice_cmd.finish("⛔ 你未加入公会")
        guild_obj = await session.get(Guild, player.guild_id)
        if not text:
            await notice_cmd.finish(message_add_head(f"📰 当前公告：{guild_obj.notice or '暂无公告'}", event))

        # 设置公告，需会长权限
        if guild_obj.president_id != player.id:
            await notice_cmd.finish("⛔ 只有会长可以修改公告")

        if len(text) > 120:
            await notice_cmd.finish("⛔ 公告不能超过120字符")

        if text in {"清空", "删除", "无"}:
            guild_obj.notice = None
            action_msg = "已清空公会公告"
        else:
            guild_obj.notice = text
            action_msg = "公告已更新"
        session.add(guild_obj)
        await session.commit()
        await notice_cmd.finish(message_add_head(f"✅ {action_msg}", event))

# ==================== 设置公会基地 ====================
set_base_cmd = on_command("设置基地", block=True, priority=5)

@set_base_cmd.handle()
async def handle_set_base(event: MessageEvent, args: Message = CommandArg()):
    """会长设置公会基地坐标：设置基地 x y"""
    arg_text = args.extract_plain_text().strip().replace(",", " ")
    parts = [p for p in arg_text.split() if p]

    if len(parts) != 2 or not all(p.lstrip("-+").isdigit() for p in parts):
        await set_base_cmd.finish("⛔ 格式错误，正确格式：设置基地 x y （示例：设置基地 100 200）")

    base_x, base_y = map(int, parts)

    # 坐标范围检查（与导航系统保持一致）
    MAX_COORD = 500
    if not (-MAX_COORD <= base_x <= MAX_COORD and -MAX_COORD <= base_y <= MAX_COORD):
        await set_base_cmd.finish(f"⛔ 坐标必须在 {-MAX_COORD}~{MAX_COORD} 范围内！")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or player.guild_id is None:
            await set_base_cmd.finish("⛔ 你未加入任何公会")

        guild_obj = await session.get(Guild, player.guild_id)
        if not guild_obj:
            await set_base_cmd.finish("⚠️ 公会数据异常")

        # 检查是否为会长
        if guild_obj.president_id != player.id:
            await set_base_cmd.finish("⛔ 只有会长才能设置公会基地")

        # 检查公会等级
        if guild_obj.level < 5:
            await set_base_cmd.finish(f"⛔ 公会等级需达到5级才能设置基地，当前等级：{guild_obj.level}")

        # 检查是否已经设置过基地
        if guild_obj.base_x is not None and guild_obj.base_y is not None:
            await set_base_cmd.finish(f"⛔ 公会基地已设置在坐标({guild_obj.base_x}, {guild_obj.base_y})，不允许重复设置")

        # 检查势力范围冲突
        territory_range = guild_obj.territory_range
        conflict_stmt = select(Guild).where(
            Guild.id != guild_obj.id,
            Guild.base_x.isnot(None),
            Guild.base_y.isnot(None),
            # 检查两个正方形是否重叠：如果两个中心点的距离小于等于两个势力范围之和的一半，则重叠
            (_func.abs(Guild.base_x - base_x) <= (Guild.territory_range + territory_range) / 2) &
            (_func.abs(Guild.base_y - base_y) <= (Guild.territory_range + territory_range) / 2)
        )
        conflict_guild = (await session.execute(conflict_stmt)).scalars().first()
        if conflict_guild:
            await set_base_cmd.finish(
                f"⛔ 坐标({base_x}, {base_y})与公会『{conflict_guild.name}』的势力范围冲突！\n"
                f"▫️ 冲突公会基地：({conflict_guild.base_x}, {conflict_guild.base_y})\n"
                f"▫️ 冲突公会势力范围：{conflict_guild.territory_range}\n"
                f"▫️ 本公会势力范围：{territory_range}\n"
                f"▫️ 请选择其他坐标设置基地"
            )

        # 设置基地坐标
        guild_obj.base_x = base_x
        guild_obj.base_y = base_y
        session.add(guild_obj)
        await session.commit()

        msg = (
            f"🏰 公会基地设置成功！\n"
            f"▫️ 基地坐标：({base_x}, {base_y})\n"
            f"▫️ 势力范围：{guild_obj.territory_range}×{guild_obj.territory_range}\n"
            f"▫️ 公会成员现在可以使用【传送公会】或【传送 公会】传送到基地"
        )
        await set_base_cmd.finish(message_add_head(msg, event))

# ==================== 公会传送 ====================
guild_teleport_cmd = on_command("传送公会", aliases={"公会传送"}, block=True, priority=4)

@guild_teleport_cmd.handle()
async def handle_guild_teleport(event: MessageEvent):
    """公会成员传送到基地，每日限使用一次"""

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or player.guild_id is None:
            await guild_teleport_cmd.finish("⛔ 你未加入任何公会")

        guild_obj = await session.get(Guild, player.guild_id)
        if not guild_obj:
            await guild_teleport_cmd.finish("⚠️ 公会数据异常")

        # 检查公会是否设置了基地
        if guild_obj.base_x is None or guild_obj.base_y is None:
            await guild_teleport_cmd.finish("⛔ 公会尚未设置基地，请联系会长设置基地坐标")

        # 检查今日是否已使用过传送
        today = date.today()
        usage_stmt = select(GuildTeleportLog).where(
            GuildTeleportLog.player_id == player.id,
            GuildTeleportLog.teleport_date == today
        )
        usage_log = (await session.execute(usage_stmt)).scalars().first()

        if usage_log:
            await guild_teleport_cmd.finish("⛔ 你今日已使用过传送公会，每日限使用一次")

        # 检查玩家是否在现实世界
        if player.region != "大都会":
            await guild_teleport_cmd.finish("⛔ 只能在现实世界使用传送公会")

        # 执行传送
        player.x = guild_obj.base_x
        player.y = guild_obj.base_y
        session.add(player)

        # 清除导航任务（如果有的话）
        nav_task = await session.get(NavigationTask, player.id)
        if nav_task:
            await session.delete(nav_task)

        # 记录使用日志
        teleport_log = GuildTeleportLog(
            player_id=player.id,
            guild_id=guild_obj.id,
            teleport_date=today
        )
        session.add(teleport_log)

        await session.commit()

        msg = (
            f"🌟 传送成功！\n"
            f"▫️ 已传送到公会『{guild_obj.name}』基地\n"
            f"▫️ 当前坐标：({guild_obj.base_x}, {guild_obj.base_y})\n"
            f"▫️ 已停止导航任务，今日不可再传送公会"
        )
        await guild_teleport_cmd.finish(message_add_head(msg, event))


# ==================== 兼容性：传送 公会 ====================
legacy_guild_teleport_cmd = on_command("传送", block=False, priority=3)

@legacy_guild_teleport_cmd.handle()
async def handle_legacy_guild_teleport(event: MessageEvent, args: Message = CommandArg()):
    """兼容旧的"传送 公会"指令格式"""
    target = args.extract_plain_text().strip()

    # 只处理 "传送 公会" 的情况，其他情况不处理（让其他传送指令处理）
    if target != "公会":
        return

    # 调用公会传送处理逻辑
    await handle_guild_teleport(event)