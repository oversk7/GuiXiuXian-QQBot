from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select, func as _func
from datetime import datetime, date

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..models.guild import Guild, GuildMember, GuildPosition, BuildingType
from ..config import config
from ..utils import message_add_head
from ..models.social_application import SocialApplication, ApplicationType, ApplicationStatus
from ..models.donation_log import PlayerDonationLog
from ..models.navigation_task import NavigationTask
from .guild_application_service import GuildApplicationService
from .guild_service import GuildService
from .guild_permission import GuildPermission
from .guild_economy_service import GuildEconomyService
from .guild_building_service import GuildBuildingService
from .guild_task_service import GuildTaskService
from .guild_facility_service import GuildFacilityService
from .guild_daily_tasks import GuildDailyTasks

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

        # 使用新的公会服务创建公会
        success, message, new_guild = await GuildService.create_guild(session, player.id, guild_name)

        if not success:
            await create_guild_cmd.finish(f"⛔ {message}")

        # 扣除委任书
        inv.quantity -= 1
        if inv.quantity <= 0:
            await session.delete(inv)

        await session.commit()

        msg = (
            f"🏰 公会『{guild_name}』正式成立！\n"
            f"▫️ 会长：{player.nickname}\n"
            f"▫️ 公会 ID：{new_guild.id}\n"
            f"▫️ 职位：{GuildPermission.get_position_display_name(GuildPosition.PRESIDENT)}"
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

        # 触发公会每日刷新（静默执行，不显示结果）
        await GuildDailyTasks.trigger_guild_daily_refresh(session, player.guild_id)

        # 获取玩家职位
        player_position = await GuildPermission.get_member_position(session, player.id, guild_obj.id)
        position_name = GuildPermission.get_position_display_name(player_position) if player_position else "未知"

        # 会长信息
        president = await session.get(Player, guild_obj.president_id)

        # 成员统计
        member_count = await GuildService.get_member_count(session, guild_obj.id)
        capacity = GuildService.get_guild_capacity(guild_obj.level)

        # 经验和升级信息
        exp_current = GuildEconomyService.format_large_number(guild_obj.exp)
        upgrade_cost = GuildEconomyService.get_guild_upgrade_cost(guild_obj.level)
        exp_need = GuildEconomyService.format_large_number(upgrade_cost["exp"])

        # 资金信息
        treasury = GuildEconomyService.format_large_number(guild_obj.treasury)

        # 建筑加成信息
        bonuses = await GuildBuildingService.get_guild_bonuses(session, guild_obj.id)
        exp_multiplier = bonuses.get("exp_multiplier", 1.0)
        cultivation_bonus = bonuses.get("cultivation_bonus", 0.0)

        # 基地信息
        base_info = ""
        if guild_obj.base_x is not None and guild_obj.base_y is not None:
            base_info = (
                f"▫️ 基地坐标：({guild_obj.base_x}, {guild_obj.base_y})\n"
                f"▫️ 势力范围：{guild_obj.territory_range}×{guild_obj.territory_range}\n"
            )
        elif guild_obj.level >= 2:
            base_info = f"▫️ 基地坐标：未设置（可使用【设置基地】命令）\n"

        # 加成信息
        bonus_info = f"▫️ 经验倍率：{exp_multiplier:.1f}x\n"
        if cultivation_bonus > 0:
            bonus_info += f"▫️ 修为加成：+{cultivation_bonus*100:.1f}%\n"

        msg = (
            f"🏰 公会面板\n"
            f"▫️『{guild_obj.name}』[ID:{guild_obj.id}] Lv.{guild_obj.level}\n"
            f"▫️ 会长：{president.nickname if president else '未知'}\n"
            f"▫️ 你的职位：{position_name}\n"
            f"▫️ 人数：{member_count}/{capacity}\n"
            f"▫️ 经验：{exp_current}/{exp_need}\n"
            f"▫️ 资金库：{treasury}\n"
            f"{bonus_info}"
            f"▫️ 创建时间：{guild_obj.created_at.strftime('%Y-%m-%d')}\n"
            f"{base_info}"
            f"▫️ 公告：{guild_obj.notice or '暂无公告'}"
        )
        await guild_info_cmd.finish(message_add_head(msg, event))

# ==================== 公会加成 ====================
guild_bonuses_cmd = on_command("公会加成", aliases={"加成效果"}, block=True, priority=5)

@guild_bonuses_cmd.handle()
async def handle_guild_bonuses(event: MessageEvent):
    """查看公会建筑提供的所有加成效果"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or not player.guild_id:
            await guild_bonuses_cmd.finish("⛔ 你未加入任何公会")

        guild = await session.get(Guild, player.guild_id)
        bonuses = await GuildBuildingService.get_guild_bonuses(session, player.guild_id)

        lines = [f"🎯 公会『{guild.name}』加成效果", "━━━━━━━━━━"]

        # 经验倍率
        exp_multiplier = bonuses.get("exp_multiplier", 1.0)
        if exp_multiplier > 1.0:
            lines.append(f"✨ 公会经验倍率：{exp_multiplier:.1f}x")
        else:
            lines.append(f"✨ 公会经验倍率：{exp_multiplier:.1f}x（基础）")

        # 修为加成
        cultivation_bonus = bonuses.get("cultivation_bonus", 0.0)
        if cultivation_bonus > 0:
            lines.append(f"🏋️ 修炼效率加成：+{cultivation_bonus*100:.1f}%")
        else:
            lines.append(f"🏋️ 修炼效率加成：无")

        # 资金上限
        treasury_limit = bonuses.get("treasury_limit", 100000)
        lines.append(f"💰 资金库上限：{GuildEconomyService.format_large_number(treasury_limit)}")

        # 全属性加成
        all_attributes = bonuses.get("all_attributes", 0.0)
        if all_attributes > 0:
            lines.append(f"⚔️ 全属性加成：+{all_attributes*100:.1f}%")
        else:
            lines.append(f"⚔️ 全属性加成：无")

        # 防御加成
        defense_bonus = bonuses.get("defense_bonus", 0.0)
        if defense_bonus > 0:
            lines.append(f"🛡️ 防御力加成：+{defense_bonus*100:.1f}%")
        else:
            lines.append(f"🛡️ 防御力加成：无")

        # 传送阵效果
        teleport_range = bonuses.get("teleport_range", 0)
        daily_teleport_uses = bonuses.get("daily_teleport_uses", 0)
        if teleport_range > 0:
            lines.append(f"✨ 传送范围：{teleport_range}格，每日{daily_teleport_uses}次")
        else:
            lines.append(f"✨ 传送功能：无")

        # 丹房效果
        daily_alchemy = bonuses.get("daily_alchemy_production", 0)
        if daily_alchemy > 0:
            lines.append(f"🧪 丹房产出：每日{daily_alchemy}个丹药")
        else:
            lines.append(f"🧪 丹房产出：无")

        # 仓库容量
        warehouse_capacity = bonuses.get("warehouse_capacity", 0)
        if warehouse_capacity > 0:
            lines.append(f"📦 仓库格子：{warehouse_capacity}格")
        else:
            lines.append(f"📦 仓库格子：无")

        lines.append("━━━━━━━━━━")
        lines.append("💡 建造更多建筑可获得更强加成")

        msg = "\n".join(lines)
        await guild_bonuses_cmd.finish(message_add_head(msg, event))

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

        # 检查是否可以申请加入公会
        can_apply, reason = await GuildApplicationService.can_apply_guild(session, player.id, guild_id)
        if not can_apply:
            await join_guild_cmd.finish(f"⛔ {reason}")

        # 获取公会信息
        guild_obj = await session.get(Guild, guild_id)

        # 创建申请记录
        await GuildApplicationService.create_guild_application(session, player.id, guild_id)

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
        guild_name = guild_obj.name if guild_obj else "未知公会"

        # 使用新的公会服务退出公会
        success, message = await GuildService.leave_guild(session, player.id)

        if not success:
            await quit_guild_cmd.finish(f"⛔ {message}")

        await session.commit()
        await quit_guild_cmd.finish(message_add_head(f"🚪 你已退出公会『{guild_name}』，个人积分和贡献已清空", event))

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

        # 使用新的公会服务获取成员列表
        members = await GuildService.get_guild_members(session, guild_obj.id)

        lines = [f"👥 公会成员『{guild_obj.name}』({len(members)}人)", "━━━━━━━━━━"]
        for idx, member in enumerate(members, 1):
            # 职位图标
            position_icons = {
                GuildPosition.PRESIDENT: "👑",
                GuildPosition.VICE_PRESIDENT: "⭐",
                GuildPosition.CORE_MEMBER: "🔸",
                GuildPosition.MEMBER: ""
            }
            icon = position_icons.get(member["position"], "")

            lines.append(
                f"{idx}. {member['nickname']}[{member['uid']}]{icon} "
                f"Lv.{member['level']} "
                f"{member['position_name']} "
                f"贡:{GuildEconomyService.format_large_number(member['contribution'])}"
            )

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
        # 使用新的经济服务处理捐献
        success, message, result = await GuildEconomyService.donate_gold(session, event.get_user_id(), amt)

        if not success:
            await donate_cmd.finish(f"⛔ {message}")

        # 检查并完成每日捐献任务
        task_success, task_message, task_result = await GuildTaskService.complete_daily_donation_task(session, event.get_user_id())

        await session.commit()

        # 构建返回消息
        msg_lines = [
            f"💰 捐献成功！金币 -{amt}",
            f"✨ 获得积分：+{result['points_gained']}",
            f"🏰 公会经验：+{result['exp_gained']}",
            f"💎 资金库：+{result['treasury_added']}",
            f"▫️ 个人贡献：{GuildEconomyService.format_large_number(result['new_contribution'])}",
            f"▫️ 公会经验：{GuildEconomyService.format_large_number(result['guild_exp'])}"
        ]

        # 如果完成了每日捐献任务，添加任务奖励信息
        if task_success:
            msg_lines.append(f"🎁 {task_message}")

        # 检查是否可以升级
        if result['can_upgrade']:
            cost = result['upgrade_cost']
            msg_lines.append(f"🎯 公会可升级！需要经验{cost['exp']}、资金{cost['gold']}")

        msg = "\n".join(msg_lines)
        await donate_cmd.finish(message_add_head(msg, event))

# ==================== 公会升级 ====================
guild_upgrade_cmd = on_command("公会升级", aliases={"升级公会"}, block=True, priority=5)

@guild_upgrade_cmd.handle()
async def handle_guild_upgrade(event: MessageEvent):
    """公会升级"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or not player.guild_id:
            await guild_upgrade_cmd.finish("⛔ 你未加入任何公会")

        success, message = await GuildEconomyService.upgrade_guild(session, player.guild_id, player.id)

        if not success:
            await guild_upgrade_cmd.finish(f"⛔ {message}")

        await session.commit()
        await guild_upgrade_cmd.finish(message_add_head(f"🎉 {message}", event))

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

        # 检查是否有管理权限（会长和副会长）
        from .guild_permission import GuildPermission
        can_manage, reason = await GuildPermission.can_manage_guild(session, player.id, player.guild_id)
        if not can_manage:
            await application_list_cmd.finish(f"⛔ {reason}")

        apps = await GuildApplicationService.get_pending_applications(session, player.guild_id)
        if not apps:
            await application_list_cmd.finish("暂无待处理申请")

        lines = ["📑 待处理入会申请", "━━━━━━━━━━"]
        for a in apps:
            applicant = await session.get(Player, a.applicant_id)
            lines.append(f"UID:{applicant.uid} {applicant.nickname} Lv.{applicant.level}")
        lines.append("━━━━━━━━━━━━━\n"
            "⬇️ 【同意入会 <UID>】\n"
            "❌ 【拒绝入会 <UID>】")
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

        # 检查是否有管理权限（会长和副会长）
        from .guild_permission import GuildPermission
        can_manage, reason = await GuildPermission.can_manage_guild(session, player.id, player.guild_id)
        if not can_manage:
            await (approve_cmd if approve else reject_cmd).finish(f"⛔ {reason}")

        guild_obj = await session.get(Guild, player.guild_id)
        applicant = (await session.execute(select(Player).where(Player.uid == target_uid))).scalars().first()
        if not applicant:
            await (approve_cmd if approve else reject_cmd).finish("⛔ 未找到该 UID")

        app = await GuildApplicationService.get_application_by_player_and_guild(session, applicant.id, guild_obj.id)
        if not app:
            await (approve_cmd if approve else reject_cmd).finish("⛔ 无待处理申请")

        if approve:
            # 使用新的公会服务加入公会
            success, reason = await GuildService.join_guild(session, applicant.id, guild_obj.id)
            if not success:
                await (approve_cmd if approve else reject_cmd).finish(message_add_head(f"⛔ {reason}", event))

            # 标记申请为已批准
            app.status = ApplicationStatus.APPROVED
            app.processed_at = datetime.now()
            session.add(app)

            result_msg = f"✅ 已同意 {applicant.nickname}[UID:{target_uid}] 加入公会"
        else:
            await GuildApplicationService.reject_application(session, app)
            result_msg = f"🚫 已拒绝 {applicant.nickname}[UID:{target_uid}] 的申请"

        # 提交事务
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

        # 设置公告，需管理权限（会长和副会长）
        can_manage, reason = await GuildPermission.can_manage_guild(session, player.id, player.guild_id)
        if not can_manage:
            await notice_cmd.finish(f"⛔ {reason}")

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

# ==================== 公会基地管理 ====================
set_base_cmd = on_command("设置基地", block=True, priority=5)

@set_base_cmd.handle()
async def handle_set_base(event: MessageEvent):
    """设置公会基地：设置基地"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or not player.guild_id:
            await set_base_cmd.finish("⛔ 你未加入任何公会")

        # 检查权限（只有会长可以设置基地）
        guild = await session.get(Guild, player.guild_id)
        if not guild:
            await set_base_cmd.finish("⛔ 公会数据异常")

        if guild.president_id != player.id:
            await set_base_cmd.finish("⛔ 只有会长才能设置公会基地")

        # 检查公会等级
        if guild.level < 2:
            await set_base_cmd.finish(f"⛔ 公会等级不足，需要达到2级才能设置基地（当前{guild.level}级）")

        # 检查是否在现实世界
        if player.region != "大都会":
            await set_base_cmd.finish("⛔ 只能在现实世界（大都会）设置公会基地")

        # 检查坐标范围（使用导航系统的坐标限制）
        MAX_COORD = 1000
        if not (-MAX_COORD <= player.x <= MAX_COORD and -MAX_COORD <= player.y <= MAX_COORD):
            await set_base_cmd.finish(f"⛔ 当前坐标超出有效范围（{-MAX_COORD}~{MAX_COORD}）")

        # 检查是否已有其他公会在此位置设置基地
        stmt = select(Guild).where(
            Guild.base_x == player.x,
            Guild.base_y == player.y,
            Guild.id != guild.id
        )
        existing_guild = (await session.execute(stmt)).scalars().first()
        if existing_guild:
            await set_base_cmd.finish(f"⛔ 坐标({player.x}, {player.y})已被公会『{existing_guild.name}』占据")
        
        # 检查是否已经设置过基地
        if guild.base_x is not None and guild.base_y is not None:
            await set_base_cmd.finish(f"⛔ 公会基地已经设置，无法更改\n当前基地坐标：({guild.base_x}, {guild.base_y})")

        # 设置基地坐标
        guild.base_x = player.x
        guild.base_y = player.y
        session.add(guild)
        await session.commit()

        msg = (
            f"🏰 公会基地设立成功！\n"
            f"━━━━━━━━━━━━━\n"
            f"▫️ 基地坐标：({guild.base_x}, {guild.base_y})\n"
            f"▫️ 势力范围：{guild.territory_range}×{guild.territory_range}\n"
            f"━━━━━━━━━━━━━\n"
            f"💡 公会成员可以使用【公会传送】在一定范围内传送到基地\n"
            f"⚠️ 基地位置一旦设置无法更改，请谨慎选择"
        )
        await set_base_cmd.finish(message_add_head(msg, event))

# ==================== 公会职位管理 ====================
set_position_cmd = on_command("设置职位", block=True, priority=5)

@set_position_cmd.handle()
async def handle_set_position(event: MessageEvent, args: Message = CommandArg()):
    """设置成员职位：设置职位 UID 职位名"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await set_position_cmd.finish("⛔ 格式错误，正确格式：设置职位 [UID] [职位名]\n可用职位：副会长、核心成员、普通成员")

    parts = args_text.split()
    if len(parts) != 2:
        await set_position_cmd.finish("⛔ 格式错误，正确格式：设置职位 [UID] [职位名]")

    target_uid, position_name = parts

    # 职位名映射
    position_map = {
        "副会长": GuildPosition.VICE_PRESIDENT,
        "核心成员": GuildPosition.CORE_MEMBER,
        "普通成员": GuildPosition.MEMBER
    }

    if position_name not in position_map:
        await set_position_cmd.finish("⛔ 无效的职位名，可用职位：副会长、核心成员、普通成员")

    new_position = position_map[position_name]

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or not player.guild_id:
            await set_position_cmd.finish("⛔ 你未加入任何公会")

        # 查找目标玩家
        target_stmt = select(Player).where(Player.uid == int(target_uid))
        target_player = (await session.execute(target_stmt)).scalars().first()
        if not target_player:
            await set_position_cmd.finish("⛔ 未找到该UID的玩家")

        if target_player.guild_id != player.guild_id:
            await set_position_cmd.finish("⛔ 该玩家不在你的公会中")

        # 设置职位
        success, message = await GuildService.set_member_position(
            session, player.id, player.guild_id, target_player.id, new_position
        )

        if not success:
            await set_position_cmd.finish(f"⛔ {message}")

        await session.commit()
        await set_position_cmd.finish(message_add_head(f"✅ {message}", event))

# ==================== 公会建筑管理 ====================
guild_buildings_cmd = on_command("公会建筑", aliases={"建筑列表"}, block=True, priority=5)

@guild_buildings_cmd.handle()
async def handle_guild_buildings(event: MessageEvent):
    """查看公会建筑列表"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or not player.guild_id:
            await guild_buildings_cmd.finish("⛔ 你未加入任何公会")

        guild = await session.get(Guild, player.guild_id)
        buildings = await GuildBuildingService.get_guild_buildings(session, player.guild_id)

        if not buildings:
            msg = f"🏗️ 公会『{guild.name}』建筑列表\n━━━━━━━━━━\n暂无建筑"
        else:
            lines = [f"🏗️ 公会『{guild.name}』建筑列表", "━━━━━━━━━━"]
            for building in buildings:
                # 使用建筑服务的格式化方法
                effects_str = GuildBuildingService.format_building_effects(building["effects"])
                lines.append(f"▫️ {building['name']} Lv.{building['level']}/{building['max_level']}")
                lines.append(f"   效果：{effects_str}")
            msg = "\n".join(lines)

        await guild_buildings_cmd.finish(message_add_head(msg, event))

build_cmd = on_command("建造", aliases={"升级建筑"}, block=True, priority=5)

@build_cmd.handle()
async def handle_build(event: MessageEvent, args: Message = CommandArg()):
    """建造或升级建筑：建造 建筑名"""
    building_name = args.extract_plain_text().strip()
    if not building_name:
        await build_cmd.finish("⛔ 格式错误，正确格式：建造 [建筑名]\n可建造：经验神龛、资金金库、训练场、传送阵、丹房、公会仓库")

    # 建筑名映射（灵塔和防御城墙暂时下架）
    building_map = {
        "经验神龛": BuildingType.EXPERIENCE_SHRINE,
        "资金金库": BuildingType.TREASURY_VAULT,
        "训练场": BuildingType.TRAINING_GROUND,
        "传送阵": BuildingType.TELEPORT_ARRAY,
        "丹房": BuildingType.ALCHEMY_ROOM,
        "公会仓库": BuildingType.GUILD_WAREHOUSE,
        # "灵塔": BuildingType.SPIRIT_TOWER,  # 暂时下架
        # "防御城墙": BuildingType.DEFENSE_WALL  # 暂时下架
    }

    if building_name not in building_map:
        await build_cmd.finish("⛔ 无效的建筑名，可建造：经验神龛、资金金库、训练场、传送阵、丹房、公会仓库")

    building_type = building_map[building_name]

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or not player.guild_id:
            await build_cmd.finish("⛔ 你未加入任何公会")

        # 获取建造成本
        cost = await GuildBuildingService.get_build_cost(session, player.guild_id, building_type)
        if not cost:
            await build_cmd.finish("⛔ 该建筑已达到最高等级")

        # 显示成本信息
        materials_str = ", ".join([f"{k}×{v}" for k, v in cost["materials"].items()])
        cost_msg = f"建造{building_name}需要：\n▫️ 金币：{cost['gold']}\n▫️ 材料：{materials_str}\n\n确认建造请使用命令：确认建造 {building_name}"

        await build_cmd.send(message_add_head(cost_msg, event))

# ==================== 确认建造 ====================
confirm_build_cmd = on_command("确认", block=True, priority=5)

@confirm_build_cmd.handle()
async def handle_confirm_build(event: MessageEvent):
    """确认建造建筑"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or not player.guild_id:
            await confirm_build_cmd.finish("⛔ 你未加入任何公会")

        # 这里需要一个临时存储机制来记住用户要建造的建筑类型
        # 由于没有会话状态管理，我们需要重新设计这个流程
        # 暂时返回提示信息，建议用户使用完整命令
        await confirm_build_cmd.finish("⛔ 请使用完整命令格式：确认建造 [建筑名]")

# ==================== 确认建造（带建筑名） ====================
confirm_build_with_name_cmd = on_command("确认建造", block=True, priority=5)

@confirm_build_with_name_cmd.handle()
async def handle_confirm_build_with_name(event: MessageEvent, args: Message = CommandArg()):
    """确认建造指定建筑"""
    building_name = args.extract_plain_text().strip()
    if not building_name:
        await confirm_build_with_name_cmd.finish("⛔ 格式错误，正确格式：确认建造 [建筑名]")

    # 建筑名映射（灵塔和防御城墙暂时下架）
    building_map = {
        "经验神龛": BuildingType.EXPERIENCE_SHRINE,
        "资金金库": BuildingType.TREASURY_VAULT,
        "训练场": BuildingType.TRAINING_GROUND,
        "传送阵": BuildingType.TELEPORT_ARRAY,
        "丹房": BuildingType.ALCHEMY_ROOM,
        "公会仓库": BuildingType.GUILD_WAREHOUSE,
        # "灵塔": BuildingType.SPIRIT_TOWER,  # 暂时下架
        # "防御城墙": BuildingType.DEFENSE_WALL  # 暂时下架
    }

    if building_name not in building_map:
        await confirm_build_with_name_cmd.finish("⛔ 无效的建筑名，可建造：经验神龛、资金金库、训练场、传送阵、丹房、公会仓库")

    building_type = building_map[building_name]

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or not player.guild_id:
            await confirm_build_with_name_cmd.finish("⛔ 你未加入任何公会")

        # 执行建造
        success, message = await GuildBuildingService.build_or_upgrade(
            session, player.guild_id, building_type, player.id
        )

        if success:
            await session.commit()
            await confirm_build_with_name_cmd.finish(message_add_head(f"🏗️ {message}", event))
        else:
            await confirm_build_with_name_cmd.finish(message_add_head(f"⛔ {message}", event))

# ==================== 公会任务系统 ====================
guild_tasks_cmd = on_command("公会任务", aliases={"任务列表"}, block=True, priority=5)

@guild_tasks_cmd.handle()
async def handle_guild_tasks(event: MessageEvent):
    """查看公会任务列表"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or not player.guild_id:
            await guild_tasks_cmd.finish("⛔ 你未加入任何公会")

        tasks = await GuildTaskService.get_available_tasks(session, player.id)

        lines = ["📋 公会任务列表", "━━━━━━━━━━"]
        for task in tasks:
            status = "✅已完成" if task["completed"] else "⏳进行中"
            lines.append(f"▫️ {task['name']} ({task['type']}) {status}")
            lines.append(f"   {task['description']}")
            lines.append(f"   奖励：{task['points_reward']}积分")

        msg = "\n".join(lines)
        await guild_tasks_cmd.finish(message_add_head(msg, event))

# ==================== 公会传送阵 ====================
guild_teleport_cmd = on_command("公会传送", aliases={"传送到公会"}, block=True, priority=5)

@guild_teleport_cmd.handle()
async def handle_guild_teleport(event: MessageEvent):
    """使用传送阵传送到公会基地"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or not player.guild_id:
            await guild_teleport_cmd.finish("⛔ 你未加入任何公会")

        # 检查是否在现实世界
        if player.region != "大都会":
            await guild_teleport_cmd.finish("⛔ 只能在现实世界使用传送阵")

        success, message = await GuildFacilityService.teleport_to_guild(session, player.id, player.guild_id)

        if success:
            await session.commit()
            await guild_teleport_cmd.finish(message_add_head(f"✨ {message}", event))
        else:
            await guild_teleport_cmd.finish(message_add_head(f"⛔ {message}", event))

# ==================== 公会丹房 ====================
guild_alchemy_cmd = on_command("公会丹房", aliases={"丹房", "丹药兑换"}, block=True, priority=5)

@guild_alchemy_cmd.handle()
async def handle_guild_alchemy(event: MessageEvent):
    """查看公会丹房产出"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or not player.guild_id:
            await guild_alchemy_cmd.finish("⛔ 你未加入任何公会")

        guild = await session.get(Guild, player.guild_id)

        # 触发丹房产出检查和生成
        refresh_result = await GuildDailyTasks.trigger_guild_daily_refresh(session, player.guild_id)

        productions = await GuildFacilityService.get_alchemy_production(session, player.guild_id)

        # 提交丹房产出的更改
        await session.commit()

        if not productions:
            msg = f"🧪 公会『{guild.name}』丹房\n━━━━━━━━━━\n暂无可兑换的丹药"
            # 如果有新产出，显示提示
            if refresh_result["alchemy_generated"] > 0:
                msg += f"\n✨ {refresh_result['message']}"
        else:
            lines = [f"🧪 公会『{guild.name}』丹房", "━━━━━━━━━━"]
            lines.append(f"💰 你的积分：{player.gold2}")

            # 如果有新产出，显示提示
            if refresh_result["alchemy_generated"] > 0:
                lines.append(f"✨ {refresh_result['message']}")

            lines.append("━━━━━━━━━━")

            for idx, prod in enumerate(productions, 1):
                # 根据丹药价值计算积分成本
                item_config = config.items_config["by_id"].get(prod["item_id"])
                if item_config:
                    points_cost = max(1, item_config.price // 100)  # 价格的1%作为积分成本
                    lines.append(f"{idx}. {prod['item_name']}×{prod['quantity']} - {points_cost}积分")

            lines.append("━━━━━━━━━━")
            lines.append("💡 使用【兑换丹药 序号】来兑换")
            msg = "\n".join(lines)

        await guild_alchemy_cmd.finish(message_add_head(msg, event))

# ==================== 兑换丹药 ====================
exchange_pill_cmd = on_command("兑换丹药", block=True, priority=5)

@exchange_pill_cmd.handle()
async def handle_exchange_pill(event: MessageEvent, args: Message = CommandArg()):
    """兑换丹房产出的丹药"""
    index_str = args.extract_plain_text().strip()
    if not index_str:
        await exchange_pill_cmd.finish("⛔ 格式错误，正确格式：兑换丹药 [序号]")

    try:
        index = int(index_str)
    except ValueError:
        await exchange_pill_cmd.finish("⛔ 序号必须是数字")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or not player.guild_id:
            await exchange_pill_cmd.finish("⛔ 你未加入任何公会")

        # 触发丹房产出检查和生成
        await GuildDailyTasks.trigger_guild_daily_refresh(session, player.guild_id)

        productions = await GuildFacilityService.get_alchemy_production(session, player.guild_id)

        if not productions or index < 1 or index > len(productions):
            await exchange_pill_cmd.finish("⛔ 无效的序号")

        selected_prod = productions[index - 1]

        # 计算积分成本
        item_config = config.items_config["by_id"].get(selected_prod["item_id"])
        if not item_config:
            await exchange_pill_cmd.finish("⛔ 物品配置错误")

        points_cost = max(1, item_config.price // 100)

        success, message = await GuildFacilityService.claim_alchemy_item(
            session, player.id, player.guild_id, selected_prod["id"], points_cost
        )

        if success:
            await session.commit()
            await exchange_pill_cmd.finish(message_add_head(f"✅ {message}", event))
        else:
            await exchange_pill_cmd.finish(message_add_head(f"⛔ {message}", event))

# ==================== 公会仓库 ====================
guild_warehouse_cmd = on_command("公会仓库", aliases={"仓库"}, block=True, priority=5)

@guild_warehouse_cmd.handle()
async def handle_guild_warehouse(event: MessageEvent):
    """查看公会仓库"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or not player.guild_id:
            await guild_warehouse_cmd.finish("⛔ 你未加入任何公会")

        # 检查是否在公会基地
        guild = await session.get(Guild, player.guild_id)
        if guild.base_x is None or guild.base_y is None:
            await guild_warehouse_cmd.finish("⛔ 公会尚未设置基地")

        if player.x != guild.base_x or player.y != guild.base_y:
            await guild_warehouse_cmd.finish("⛔ 只有在公会基地才能访问仓库")

        capacity = await GuildFacilityService.get_warehouse_capacity(session, player.guild_id)
        if capacity == 0:
            await guild_warehouse_cmd.finish("⛔ 公会尚未建造仓库")

        items = await GuildFacilityService.get_warehouse_items(session, player.guild_id)
        current_slots_used = len(items)  # 格子数等于实际的堆叠数量

        if not items:
            msg = f"📦 公会『{guild.name}』仓库\n━━━━━━━━━━\n格子：{current_slots_used}/{capacity}\n暂无物品\n━━━━━━━━━━\n使用【存入仓库 <物品名> <数量>】存入物品"
        else:
            lines = [f"📦 公会『{guild.name}』仓库", "━━━━━━━━━━"]
            lines.append(f"格子：{current_slots_used}/{capacity}")
            lines.append("━━━━━━━━━━")

            for idx, item in enumerate(items, 1):
                lines.append(f"{idx}. {item['item_name']}×{item['quantity']} (存入者:{item['deposited_by']})")

            lines.append("━━━━━━━━━━")
            lines.append("💡 使用【存入仓库 <物品名> <数量>】存入物品")
            lines.append("💡 使用【取出仓库 <序号> <数量>】取出物品")
            msg = "\n".join(lines)

        await guild_warehouse_cmd.finish(message_add_head(msg, event))

# ==================== 存入仓库 ====================
deposit_warehouse_cmd = on_command("存入仓库", block=True, priority=5)

@deposit_warehouse_cmd.handle()
async def handle_deposit_warehouse(event: MessageEvent, args: Message = CommandArg()):
    """存入物品到公会仓库"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await deposit_warehouse_cmd.finish("⛔ 格式错误，正确格式：存入仓库 [物品名] [数量]")

    parts = args_text.split()
    if len(parts) < 2:
        await deposit_warehouse_cmd.finish("⛔ 格式错误，正确格式：存入仓库 [物品名] [数量]")

    item_name = parts[0]
    try:
        quantity = int(parts[1])
        if quantity <= 0:
            raise ValueError
    except ValueError:
        await deposit_warehouse_cmd.finish("⛔ 数量必须是正整数")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or not player.guild_id:
            await deposit_warehouse_cmd.finish("⛔ 你未加入任何公会")

        # 检查是否在公会基地
        guild = await session.get(Guild, player.guild_id)
        if guild.base_x is None or guild.base_y is None:
            await deposit_warehouse_cmd.finish("⛔ 公会尚未设置基地")

        if player.x != guild.base_x or player.y != guild.base_y:
            await deposit_warehouse_cmd.finish("⛔ 只有在公会基地才能访问仓库")

        # 查找物品ID
        item_config = config.items_config["by_name"].get(item_name)
        if not item_config:
            await deposit_warehouse_cmd.finish("⛔ 未找到该物品")

        success, message = await GuildFacilityService.deposit_to_warehouse(
            session, player.id, player.guild_id, item_config.item_id, quantity
        )

        if success:
            await session.commit()
            await deposit_warehouse_cmd.finish(message_add_head(f"✅ {message}", event))
        else:
            await deposit_warehouse_cmd.finish(message_add_head(f"⛔ {message}", event))

# ==================== 取出仓库 ====================
withdraw_warehouse_cmd = on_command("取出仓库", block=True, priority=5)

@withdraw_warehouse_cmd.handle()
async def handle_withdraw_warehouse(event: MessageEvent, args: Message = CommandArg()):
    """从公会仓库取出物品"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await withdraw_warehouse_cmd.finish("⛔ 格式错误，正确格式：取出仓库 [序号] [数量]")

    parts = args_text.split()
    if len(parts) < 2:
        await withdraw_warehouse_cmd.finish("⛔ 格式错误，正确格式：取出仓库 [序号] [数量]")

    try:
        index = int(parts[0])
        quantity = int(parts[1])
        if index <= 0 or quantity <= 0:
            raise ValueError
    except ValueError:
        await withdraw_warehouse_cmd.finish("⛔ 序号和数量必须是正整数")

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player or not player.guild_id:
            await withdraw_warehouse_cmd.finish("⛔ 你未加入任何公会")

        # 检查是否在公会基地
        guild = await session.get(Guild, player.guild_id)
        if guild.base_x is None or guild.base_y is None:
            await withdraw_warehouse_cmd.finish("⛔ 公会尚未设置基地")

        if player.x != guild.base_x or player.y != guild.base_y:
            await withdraw_warehouse_cmd.finish("⛔ 只有在公会基地才能访问仓库")

        success, message = await GuildFacilityService.withdraw_from_warehouse(
            session, player.id, player.guild_id, index, quantity
        )

        if success:
            await session.commit()
            await withdraw_warehouse_cmd.finish(message_add_head(f"✅ {message}", event))
        else:
            await withdraw_warehouse_cmd.finish(message_add_head(f"⛔ {message}", event))



