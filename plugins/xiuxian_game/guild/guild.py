from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select, func as _func, delete as sql_delete
from datetime import datetime, date

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..models.guild import Guild, GuildMember, GuildPosition, BuildingType, GuildWarehouseItem, GuildAlchemyProduction, GuildTeleportLog
from ..models.guild_task_record import GuildTaskRecord
from ..config import config
from ..utils import message_add_head
from ..utils_markdown import cmd, build_markdown
from ..models.social_application import SocialApplication, ApplicationType, ApplicationStatus
from ..models.donation_log import PlayerDonationLog
from ..models.navigation_task import NavigationTask
from .guild_application_service_new import GuildApplicationService as GuildApplicationServiceNew  # DI版本
from .guild_service_new import GuildService as GuildServiceNew  # DI版本
from .guild_permission import GuildPermission
from .guild_economy_service import GuildEconomyService
from .guild_economy_service_new import GuildEconomyService as GuildEconomyServiceNew  # DI版本
from .guild_building_service import GuildBuildingService
from .guild_building_service_new import GuildBuildingService as GuildBuildingServiceNew  # DI版本
from .guild_task_service import GuildTaskService
from .guild_task_service_new import GuildTaskService as GuildTaskServiceNew  # DI版本
from .guild_facility_service import GuildFacilityService
from .guild_facility_service_new import GuildFacilityService as GuildFacilityServiceNew  # DI版本
from .guild_daily_tasks import GuildDailyTasks
from ..platform_utils import get_unified_player

# 使用DI架构的各种Guild Service

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

create_guild_cmd = on_command("创建公会", block=True, priority=11)

@create_guild_cmd.handle()
async def handle_create_guild(event: MessageEvent, args: Message = CommandArg()):
    """消耗会长委任书创建公会：创建公会 公会名"""
    guild_name = args.extract_plain_text().strip()
    if not guild_name:
        await create_guild_cmd.finish("⛔ 格式错误，正确格式：创建公会 [公会名]")
    if len(guild_name) > 16:
        await create_guild_cmd.finish("⛔ 公会名称长度不能超过16个字符")

    # 新版本: 使用DI架构，所有操作在同一个UoW事务中
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        # 1. 获取玩家（使用UoW的session）
        player = await get_unified_player(uow.session, event)
        if not player:
            await create_guild_cmd.finish("⛔ 请先创建角色")
        if player.guild_id is not None:
            await create_guild_cmd.finish("⛔ 你已经加入公会，无法再次创建")

        # 2. 检查会长委任书
        president_cfg = config.items_config["by_name"].get("会长委任书")
        if not president_cfg:
            await create_guild_cmd.finish("⚠️ 配置缺少 会长委任书")

        result = await uow.session.execute(
            select(ItemInstance).where(
                ItemInstance.player_id == player.id,
                ItemInstance.item_id == president_cfg.item_id
            )
        )
        inv = result.scalars().first()
        if not inv or inv.quantity < 1:
            await create_guild_cmd.finish("⛔ 你没有会长委任书")

        # 3. 检查公会名重复（使用UoW的仓储）
        existing_guild = await uow.guilds.get_by_name(guild_name)
        if existing_guild:
            await create_guild_cmd.finish("⛔ 已存在同名公会")

        # 4. 使用UoW的仓储创建Service
        guild_service = GuildServiceNew(
            player_repo=uow.players,
            guild_repo=uow.guilds,
            uow=uow
        )

        # 5. 创建公会
        success, message, new_guild = await guild_service.create_guild(
            player_id=player.id,
            guild_name=guild_name
        )

        if not success:
            await create_guild_cmd.finish(f"⛔ {message}")

        # 6. 扣除委任书（在同一个事务中）
        inv.quantity -= 1
        if inv.quantity <= 0:
            await uow.session.delete(inv)

        # 7. UoW会在__aexit__中自动commit所有操作

    # 8. 返回成功消息
    msg = (
        f"🏰 公会『{guild_name}』正式成立！\n"
        f"▫️ 会长：{player.nickname}\n"
        f"▫️ 公会 ID：{new_guild.id}\n"
        f"▫️ 职位：{GuildPermission.get_position_display_name(GuildPosition.PRESIDENT)}"
    )
    await create_guild_cmd.finish(message_add_head(msg, event))
# ==================== 公会信息 ====================
guild_info_cmd = on_command("公会", aliases={"我的公会", "公会信息"}, block=True, priority=11,force_whitespace=True)

@guild_info_cmd.handle()
async def handle_guild_info(event: MessageEvent):
    # 新版本: 使用DI架构
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal
    from .guild_service_new import GuildService as GuildServiceNew

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player or player.guild_id is None:
            await guild_info_cmd.finish("⛔ 你尚未加入任何公会")

        guild_obj = await uow.session.get(Guild, player.guild_id)
        if not guild_obj:
            # 数据不一致，修正玩家字段
            player.guild_id = None
            uow.session.add(player)
            await uow.commit()
            await guild_info_cmd.finish("⚠️ 公会数据异常，请稍后重试")

        # 触发公会每日刷新（静默执行，不显示结果）
        await GuildDailyTasks.trigger_guild_daily_refresh(uow.session, player.guild_id)

        # 获取玩家职位
        player_position = await GuildPermission.get_member_position(uow.session, player.id, guild_obj.id)
        position_name = GuildPermission.get_position_display_name(player_position) if player_position else "未知"

        # 会长信息
        president = await uow.session.get(Player, guild_obj.president_id)

        # 创建GuildService实例
        guild_service = GuildServiceNew(
            player_repo=uow.players,
            guild_repo=uow.guilds,
            uow=uow
        )

        # 成员统计 (使用新版本)
        member_count = await guild_service.get_member_count(guild_obj.id)
        capacity = guild_service.get_guild_capacity(guild_obj.level)

        # 经验和升级信息
        exp_current = GuildEconomyService.format_large_number(guild_obj.exp)
        upgrade_cost = GuildEconomyService.get_guild_upgrade_cost(guild_obj.level)
        exp_need = GuildEconomyService.format_large_number(upgrade_cost["exp"])

        # 资金信息
        treasury = GuildEconomyService.format_large_number(guild_obj.treasury)

        # 建筑加成信息（在UnitOfWork内部使用uow的Repository）
        building_service = GuildBuildingServiceNew(
            guild_repo=uow.guilds,
            building_repo=uow.guild_buildings,
            item_repo=None  # get_guild_bonuses不需要item_repo
        )
        bonuses = await building_service.get_guild_bonuses(guild_obj.id)
        exp_multiplier = bonuses.get("exp_multiplier", 1.0)
        cultivation_bonus = bonuses.get("cultivation_bonus", 0.0)

    # 构建Markdown格式公会面板
    lines = [
        f"# 🏰 {guild_obj.name}",
        f"ID:{guild_obj.id}　Lv.**{guild_obj.level}**　创建于 {guild_obj.created_at.strftime('%Y-%m-%d')}",
        "***",
        f"👑 会长：**{president.nickname if president else '未知'}**",
        f"📛 你的职位：**{position_name}**",
        f"👥 人数：**{member_count}**/{capacity}",
        f"📊 经验：**{exp_current}**/{exp_need}",
        f"💰 资金库：**{treasury}**",
        f"✨ 经验倍率：**{exp_multiplier:.1f}x**",
    ]
    if cultivation_bonus > 0:
        lines.append(f"🏋️ 修为加成：**+{cultivation_bonus*100:.1f}%**")

    # 基地信息
    if guild_obj.base_x is not None and guild_obj.base_y is not None:
        lines.append(f"📍 基地：({guild_obj.base_x}, {guild_obj.base_y})　范围 {guild_obj.territory_range}×{guild_obj.territory_range}")
    elif guild_obj.level >= 2:
        lines.append(f"📍 基地：未设置　{cmd('设置基地')}")

    lines.append(f"📰 公告：{guild_obj.notice or '暂无公告'}")
    lines.append("***")

    # 快捷操作按钮
    lines.append(
        f"{cmd('公会成员')} | {cmd('公会建筑')} | {cmd('公会加成')}"
    )
    lines.append(
        f"{cmd('捐献金币')} | {cmd('公会丹房')} | {cmd('公会仓库')}"
    )
    lines.append(
        f"{cmd('公会传送')} | {cmd('公会列表')} | {cmd('帮助')}"
    )

    await guild_info_cmd.finish(build_markdown("\n".join(lines)))

# ==================== 公会加成 ====================
guild_bonuses_cmd = on_command("公会加成", aliases={"加成效果"}, block=True, priority=11)

@guild_bonuses_cmd.handle()
async def handle_guild_bonuses(event: MessageEvent):
    """查看公会建筑提供的所有加成效果"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await guild_bonuses_cmd.finish("⛔ 你未加入任何公会")

        guild = await session.get(Guild, player.guild_id)

        # 新版：使用DI架构Service
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository

        building_service = GuildBuildingServiceNew(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            item_repo=None  # get_guild_bonuses不需要item_repo
        )
        bonuses = await building_service.get_guild_bonuses(player.guild_id)
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
join_guild_cmd = on_command("加入公会", block=True, priority=11)

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
        player = await get_unified_player(session, event)
        if not player:
            await join_guild_cmd.finish("⛔ 请先创建角色")

        # 新版：使用DI架构Service（修复P0问题：移除内部commit）
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository

        service = GuildApplicationServiceNew(
            player_repo=PlayerRepository(session),
            guild_repo=GuildRepository(session),
            application_repo=SocialApplicationRepository(session)
        )

        # 检查是否可以申请加入公会
        can_apply, reason = await service.can_apply_guild(player.id, guild_id)
        if not can_apply:
            await join_guild_cmd.finish(f"⛔ {reason}")

        # 获取公会信息
        guild_obj = await session.get(Guild, guild_id)

        # 创建申请记录
        await service.create_guild_application(player.id, guild_id)
        await session.commit()  # 由调用方控制事务边界

        # 新手任务钩子
        from ..quest.novice_quest_service import NoviceQuestService
        quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(session, player, "command", {"command": "加入公会"})

        join_msg = f"✅ 已向『{guild_obj.name}』提交入会申请，等待审核"
        if quest_completed and quest_msg:
            join_msg += f"\n\n{quest_msg}"

        await join_guild_cmd.finish(message_add_head(join_msg, event))

# ==================== 退出公会 ====================
quit_guild_cmd = on_command("退会", aliases={"退出公会"}, block=True, priority=11)

@quit_guild_cmd.handle()
async def handle_quit_guild(event: MessageEvent):
    # 新版本: 使用DI架构
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal
    from .guild_service_new import GuildService as GuildServiceNew

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player or player.guild_id is None:
            await quit_guild_cmd.finish("⛔ 你未加入任何公会")

        guild_obj = await uow.session.get(Guild, player.guild_id)
        guild_name = guild_obj.name if guild_obj else "未知公会"

        # 创建GuildService实例
        guild_service = GuildServiceNew(
            player_repo=uow.players,
            guild_repo=uow.guilds,
            uow=uow
        )

        # 使用新版本退出公会
        success, message = await guild_service.leave_guild(player.id)

        if not success:
            await quit_guild_cmd.finish(f"⛔ {message}")

        # UoW会在__aexit__中自动commit
        await quit_guild_cmd.finish(message_add_head(f"🚪 你已退出公会『{guild_name}』，个人积分和贡献已清空", event))
# ==================== 解散公会 ====================

dissolve_guild_cmd = on_command("解散公会", block=True, priority=11)

@dissolve_guild_cmd.handle()
async def handle_dissolve_guild(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or player.guild_id is None:
            await dissolve_guild_cmd.finish("⛔ 你未加入公会")

        guild_obj = await session.get(Guild, player.guild_id)
        if not guild_obj:
            player.guild_id = None
            session.add(player)
            await session.commit()
            await dissolve_guild_cmd.finish("⚠️ 公会数据异常，已自动脱离")

        # 通过 GuildMember 表检查职位（权威来源），同时兼容 president_id 直接比较
        member_position = await GuildPermission.get_member_position(session, player.id, guild_obj.id)
        is_president = (member_position == GuildPosition.PRESIDENT) or (guild_obj.president_id == player.id)
        if not is_president:
            await dissolve_guild_cmd.finish("⛔ 只有会长才能解散公会")

        # 将所有成员 guild_id 置空
        members = (await session.execute(select(Player).where(Player.guild_id == guild_obj.id))).scalars().all()
        for m in members:
            m.guild_id = None
            session.add(m)

        # 删除无 cascade 的关联记录（避免 MySQL 外键约束报错）
        await session.execute(sql_delete(GuildTaskRecord).where(GuildTaskRecord.guild_id == guild_obj.id))
        await session.execute(sql_delete(GuildWarehouseItem).where(GuildWarehouseItem.guild_id == guild_obj.id))
        await session.execute(sql_delete(GuildAlchemyProduction).where(GuildAlchemyProduction.guild_id == guild_obj.id))
        await session.execute(sql_delete(GuildTeleportLog).where(GuildTeleportLog.guild_id == guild_obj.id))

        # 删除公会（GuildMember 和 GuildBuilding 由 cascade 自动删除）
        await session.delete(guild_obj)
        await session.commit()

        await dissolve_guild_cmd.finish(message_add_head("⚠️ 公会已解散，江湖再见", event))

# ==================== 公会成员列表 ====================
member_list_cmd = on_command("公会成员", aliases={"成员列表"}, block=True, priority=11)

@member_list_cmd.handle()
async def handle_member_list(event: MessageEvent, args: Message = CommandArg()):
    page_size = 20
    arg = args.extract_plain_text().strip()
    try:
        page = int(arg) if arg else 1
    except ValueError:
        page = 1
    page = max(1, page)

    # 新版本: 使用DI架构
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal
    from .guild_service_new import GuildService as GuildServiceNew

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player or player.guild_id is None:
            await member_list_cmd.finish("⛔ 你未加入任何公会")
        guild_obj = await uow.session.get(Guild, player.guild_id)
        if not guild_obj:
            await member_list_cmd.finish("⚠️ 公会数据异常")

        # 创建GuildService实例
        guild_service = GuildServiceNew(
            player_repo=uow.players,
            guild_repo=uow.guilds,
            uow=uow
        )

        # 使用新版本获取成员列表
        all_members = await guild_service.get_guild_members(guild_obj.id)
    # 计算分页 (两个版本共享)
    total_members = len(all_members)
    if total_members == 0:
        await member_list_cmd.finish("⛔ 公会暂无成员")

    total_pages = (total_members - 1) // page_size + 1
    page = min(page, total_pages)

    # 获取当前页的成员
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    members = all_members[start_idx:end_idx]

    # 职位图标
    position_icons = {
        GuildPosition.PRESIDENT: "👑",
        GuildPosition.VICE_PRESIDENT: "⭐",
        GuildPosition.CORE_MEMBER: "🔸",
        GuildPosition.MEMBER: ""
    }

    lines = [
        f"# 👥 {guild_obj.name}",
        f"共**{total_members}**人　第**{page}**/{total_pages}页",
        "***",
    ]
    today = date.today()
    for idx, member in enumerate(members, start_idx + 1):
        icon = position_icons.get(member["position"], "")
        sign_mark = "✅" if (member.get("last_sign") and member["last_sign"].date() == today) else "⬜"
        nick_display = cmd(member['nickname'], f"面板 {member['uid']}")
        lines.append(
            f"{idx}. {sign_mark}{icon}{nick_display} Lv.{member['level']}　"
            f"{member['position_name']}　"
            f"贡献:{GuildEconomyService.format_large_number(member['contribution'])}"
        )

    lines.append("***")

    # 分页导航
    nav_parts = []
    if page > 1:
        nav_parts.append(cmd("上一页", f"公会成员 {page - 1}"))
    if page < total_pages:
        nav_parts.append(cmd("下一页", f"公会成员 {page + 1}"))
    if nav_parts:
        lines.append(" | ".join(nav_parts))

    lines.append(cmd("公会") + " | " + cmd("公会成员") + " | " + cmd("帮助"))

    await member_list_cmd.finish(build_markdown("\n".join(lines)))

# ==================== 捐献金币 ====================
donate_cmd = on_command("捐献金币", aliases={"贡献", "捐献","上供"}, block=True, priority=11)

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
        # 使用跨平台工具获取玩家数据（支持多账户）
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await donate_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await donate_cmd.finish("⛔ 请先创建角色")

        # 使用经济服务处理捐献
        # 新版：使用DI架构Service
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
        from ..infrastructure.repositories.player_donation_log_repository import PlayerDonationLogRepository

        economy_service = GuildEconomyServiceNew(
            guild_repo=GuildRepository(session),
            player_repo=PlayerRepository(session),
            donation_log_repo=PlayerDonationLogRepository(session),
            building_repo=GuildBuildingRepository(session)
        )
        success, message, result = await economy_service.donate_gold(player.id, amt)
        if not success:
            await donate_cmd.finish(f"⛔ {message}")

        # 检查并完成每日捐献任务
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.player_task_stats_repository import PlayerTaskStatsRepository
        from ..infrastructure.repositories.guild_task_record_repository import GuildTaskRecordRepository
        from ..infrastructure.repositories.player_donation_log_repository import PlayerDonationLogRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository

        task_service = GuildTaskServiceNew(
            player_repo=PlayerRepository(session),
            guild_repo=GuildRepository(session),
            player_task_stats_repo=PlayerTaskStatsRepository(session),
            guild_task_record_repo=GuildTaskRecordRepository(session),
            player_donation_log_repo=PlayerDonationLogRepository(session),
            guild_building_repo=GuildBuildingRepository(session),
        )
        task_success, task_message, task_result = await task_service.complete_daily_donation_task(player.id)
        await session.commit()  # 由调用方控制事务边界

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
guild_upgrade_cmd = on_command("公会升级", aliases={"升级公会"}, block=True, priority=11)

@guild_upgrade_cmd.handle()
async def handle_guild_upgrade(event: MessageEvent):
    """公会升级"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await guild_upgrade_cmd.finish("⛔ 你未加入任何公会")

        # 新版：使用DI架构Service
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
        from ..infrastructure.repositories.player_donation_log_repository import PlayerDonationLogRepository

        economy_service = GuildEconomyServiceNew(
            guild_repo=GuildRepository(session),
            player_repo=PlayerRepository(session),
            donation_log_repo=PlayerDonationLogRepository(session),
            building_repo=GuildBuildingRepository(session)
        )
        success, message = await economy_service.upgrade_guild(player.guild_id, player.id)
        if not success:
            await guild_upgrade_cmd.finish(f"⛔ {message}")

        await session.commit()  # 由调用方控制事务边界
        await guild_upgrade_cmd.finish(message_add_head(f"🎉 {message}", event))

# ==================== 转让会长 ====================
transfer_cmd = on_command("转让会长", block=True, priority=11)

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
        player = await get_unified_player(session, event)
        if not player or player.guild_id is None:
            await transfer_cmd.finish("⛔ 你未加入公会")
        guild_obj = await session.get(Guild, player.guild_id)
        if not guild_obj:
            await transfer_cmd.finish("⛔ 公会数据异常")

        # 通过 GuildMember 表检查职位（权威来源），同时兼容 president_id 直接比较
        member_position = await GuildPermission.get_member_position(session, player.id, guild_obj.id)
        is_president = (member_position == GuildPosition.PRESIDENT) or (guild_obj.president_id == player.id)
        if not is_president:
            await transfer_cmd.finish("⛔ 只有会长才能转让职位")

        target_player_stmt = select(Player).where(Player.uid == target_uid, Player.guild_id == guild_obj.id)
        target_player = (await session.execute(target_player_stmt)).scalars().first()
        if not target_player:
            await transfer_cmd.finish("⛔ 未找到目标成员或对方不在本公会")

        # 更新公会会长ID
        guild_obj.president_id = target_player.id
        session.add(guild_obj)

        # 同步更新 GuildMember 职位（保持两表一致）
        from sqlalchemy import update as sql_update
        await session.execute(
            sql_update(GuildMember)
            .where(GuildMember.guild_id == guild_obj.id, GuildMember.player_id == player.id)
            .values(position=GuildPosition.VICE_PRESIDENT)
        )
        await session.execute(
            sql_update(GuildMember)
            .where(GuildMember.guild_id == guild_obj.id, GuildMember.player_id == target_player.id)
            .values(position=GuildPosition.PRESIDENT)
        )

        await session.commit()
        msg = f"👑 会长职位已转让给 {target_player.nickname}[UID:{target_player.uid}]"
        await transfer_cmd.finish(message_add_head(msg, event))

# ==================== 公会列表 ====================
list_guilds_cmd = on_command("公会列表", aliases={"查看公会", "所有公会"}, block=True, priority=11)

@list_guilds_cmd.handle()
async def handle_list_guilds(event: MessageEvent, args: Message = CommandArg()):
    """
    公会列表指令：查看所有公会（按活跃度排序）

    用法：【公会列表】或【查看公会】或【所有公会】

    - 每日首次查看时自动检查：会长30天未登录则自动继承，全员不活跃则解散
    - 列表按成员活跃度排序，活跃公会排前面
    """
    from .guild_activity import maybe_run_activity_check, get_guilds_sorted_by_activity

    # 分页参数
    arg = args.extract_plain_text().strip()
    try:
        page = int(arg) if arg else 1
    except ValueError:
        page = 1
    page = max(1, page)

    page_size = 20

    # 使用 DI 架构
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        # 每日自动检查：会长继承 / 僵尸公会解散
        activity_logs = await maybe_run_activity_check(uow.session)

        # 按活跃度排序查询公会
        guild_rows = await get_guilds_sorted_by_activity(uow.session)

        if not guild_rows:
            await list_guilds_cmd.finish(message_add_head("📋 当前没有任何公会", event))

        # 分页
        total_guilds = len(guild_rows)
        total_pages = (total_guilds + page_size - 1) // page_size
        page = min(page, total_pages)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_rows = guild_rows[start_idx:end_idx]

        # 构建Markdown格式消息
        lines = [
            f"# 📋 公会列表",
            f"第**{page}**/{total_pages}页 | 共**{total_guilds}**个公会",
            "***",
        ]

        # 如果本次触发了活跃度清理，显示摘要
        if activity_logs:
            for log in activity_logs:
                lines.append(f"> {log}")
            lines.append("***")

        for guild, _latest_active in page_rows:
            # 获取会长信息
            president = await uow.session.get(Player, guild.president_id)
            president_name = president.nickname if president else "未知"

            # 获取成员数量
            member_count = await uow.guilds.get_member_count(guild.id)
            max_members = 10 + (guild.level - 1) * 5

            lines.append(
                f"🏰 **{guild.name}** Lv.{guild.level}│"
                f"{member_count}/{max_members}人│"
                f"💰{guild.treasury:,}"
            )
            president_uid = president.uid if president else 0
            lines.append(
                f"👑 会长：{cmd(president_name, f'面板 {president_uid}')}　"
                f"{cmd('⚔️加入', f'加入公会 {guild.id}')}"
            )
            lines.append("")

        lines.append("***")

        # 分页导航
        nav_parts = []
        if page > 1:
            nav_parts.append(cmd(f"上一页", f"公会列表 {page - 1}"))
        if page < total_pages:
            nav_parts.append(cmd(f"下一页", f"公会列表 {page + 1}"))
        if nav_parts:
            lines.append(" | ".join(nav_parts))

        lines.append(cmd("公会列表") + " | " + cmd("帮助"))

    await list_guilds_cmd.finish(build_markdown("\n".join(lines)))

# ==================== 申请列表 ====================
application_list_cmd = on_command("申请列表", block=True, priority=11)

@application_list_cmd.handle()
async def handle_app_list(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or player.guild_id is None:
            await application_list_cmd.finish("⛔ 你未加入公会")

        # 检查是否有管理权限（会长和副会长）
        from .guild_permission import GuildPermission
        can_manage, reason = await GuildPermission.can_manage_guild(session, player.id, player.guild_id)
        if not can_manage:
            await application_list_cmd.finish(f"⛔ {reason}")

        # 新版：使用DI架构Service
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
        service = GuildApplicationServiceNew(
            player_repo=PlayerRepository(session),
            guild_repo=GuildRepository(session),
            application_repo=SocialApplicationRepository(session)
        )
        apps = await service.get_pending_applications(player.guild_id)
        if not apps:
            await application_list_cmd.finish("暂无待处理申请")

        lines = [
            "# 📑 待处理入会申请",
            f"共**{len(apps)}**条",
            "***",
        ]
        for a in apps:
            applicant = await session.get(Player, a.applicant_id)
            lines.append(
                f"👤 {cmd(applicant.nickname, f'面板 {applicant.uid}')} Lv.{applicant.level}　"
                f"{cmd('✅同意', f'同意入会 {applicant.uid}')} | "
                f"{cmd('❌拒绝', f'拒绝入会 {applicant.uid}')}"
            )

        lines.append("***")
        lines.append(cmd("申请列表") + " | " + cmd("公会") + " | " + cmd("帮助"))
        await application_list_cmd.finish(build_markdown("\n".join(lines)))

# ==================== 同意/拒绝申请 ====================
approve_cmd = on_command("同意入会", block=True, priority=11)
reject_cmd = on_command("拒绝入会", block=True, priority=11)

async def _process_application(event: MessageEvent, args: Message, approve: bool):
    uid_str = args.extract_plain_text().strip()
    if not uid_str:
        await (approve_cmd if approve else reject_cmd).finish("格式：同意入会 UID 或 拒绝入会 UID")
    try:
        target_uid = int(uid_str)
    except ValueError:
        await (approve_cmd if approve else reject_cmd).finish("UID 必须为数字")

    # 新版本: 使用DI架构
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal
    from .guild_service_new import GuildService as GuildServiceNew

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player or player.guild_id is None:
            await (approve_cmd if approve else reject_cmd).finish("⛔ 你未加入公会")

        # 检查是否有管理权限（会长和副会长）
        from .guild_permission import GuildPermission
        can_manage, reason = await GuildPermission.can_manage_guild(uow.session, player.id, player.guild_id)
        if not can_manage:
            await (approve_cmd if approve else reject_cmd).finish(f"⛔ {reason}")

        guild_obj = await uow.session.get(Guild, player.guild_id)
        applicant = (await uow.session.execute(select(Player).where(Player.uid == target_uid))).scalars().first()
        if not applicant:
            await (approve_cmd if approve else reject_cmd).finish("⛔ 未找到该 UID")

        # 使用DI架构GuildApplicationService
        app_service = GuildApplicationServiceNew(
            player_repo=uow.players,
            guild_repo=uow.guilds,
            application_repo=uow.social_applications
        )
        app = await app_service.get_application_by_player_and_guild(applicant.id, guild_obj.id)

        if not app:
            await (approve_cmd if approve else reject_cmd).finish("⛔ 无待处理申请")

        if approve:
            # 创建GuildService实例
            guild_service = GuildServiceNew(
                player_repo=uow.players,
                guild_repo=uow.guilds,
                uow=uow
            )

            # 使用新版本加入公会
            success, reason = await guild_service.join_guild(applicant.id, guild_obj.id)
            if not success:
                await (approve_cmd if approve else reject_cmd).finish(message_add_head(f"⛔ {reason}", event))

            # 使用DI架构Service批准申请（检查返回值）
            approve_success, approve_reason = await app_service.approve_application(app, guild_obj)
            if not approve_success:
                # 批准申请失败，但玩家已经加入公会了，这是一个不一致的状态
                # 记录警告并继续（因为玩家实际上已经加入了）
                from nonebot import logger
                logger.warning(f"⚠️ [公会] 玩家 {applicant.nickname}[{target_uid}] 已加入公会，但批准申请失败: {approve_reason}")
                # 仍然显示成功消息，因为玩家已经实际加入了公会
                result_msg = f"✅ 已同意 {applicant.nickname}[UID:{target_uid}] 加入公会（申请状态更新异常）"
            else:
                result_msg = f"✅ 已同意 {applicant.nickname}[UID:{target_uid}] 加入公会"
        else:
            # 使用DI架构Service拒绝申请
            await app_service.reject_application(app)
            result_msg = f"🚫 已拒绝 {applicant.nickname}[UID:{target_uid}] 的申请"

        # 显式提交事务（确保数据库更新）
        await uow.commit()

        await (approve_cmd if approve else reject_cmd).finish(message_add_head(result_msg, event))
@approve_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    await _process_application(event, args, True)

@reject_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    await _process_application(event, args, False)

# ==================== 公会公告 ====================
notice_cmd = on_command("公会公告", aliases={"公告"}, block=True, priority=11)

@notice_cmd.handle()
async def handle_notice(event: MessageEvent, args: Message = CommandArg()):
    text = args.extract_plain_text().strip()
    async with safe_session() as session:
        player = await get_unified_player(session, event)
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
set_base_cmd = on_command("设置基地", block=True, priority=11)

@set_base_cmd.handle()
async def handle_set_base(event: MessageEvent):
    """设置公会基地：设置基地"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
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

        # 检查坐标范围（使用导航系统的坐标限制） - 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        MAX_COORD = 2000
        if not (-MAX_COORD <= current_x <= MAX_COORD and -MAX_COORD <= current_y <= MAX_COORD):
            await set_base_cmd.finish(f"⛔ 当前坐标超出有效范围（{-MAX_COORD}~{MAX_COORD}）")

        # 检查是否已有其他公会在此位置设置基地
        stmt = select(Guild).where(
            Guild.base_x == current_x,
            Guild.base_y == current_y,
            Guild.id != guild.id
        )
        existing_guild = (await session.execute(stmt)).scalars().first()
        if existing_guild:
            await set_base_cmd.finish(f"⛔ 坐标({current_x}, {current_y})已被公会『{existing_guild.name}』占据")
        
        # 检查是否已经设置过基地
        if guild.base_x is not None and guild.base_y is not None:
            await set_base_cmd.finish(f"⛔ 公会基地已经设置，无法更改\n当前基地坐标：({guild.base_x}, {guild.base_y})")

        # 设置基地坐标 - 使用正确的当前坐标
        guild.base_x = current_x
        guild.base_y = current_y
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
set_position_cmd = on_command("设置职位", block=True, priority=11)

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

    # 新版本: 使用DI架构
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal
    from .guild_service_new import GuildService as GuildServiceNew

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player or not player.guild_id:
            await set_position_cmd.finish("⛔ 你未加入任何公会")

        # 查找目标玩家
        target_stmt = select(Player).where(Player.uid == int(target_uid))
        target_player = (await uow.session.execute(target_stmt)).scalars().first()
        if not target_player:
            await set_position_cmd.finish("⛔ 未找到该UID的玩家")

        if target_player.guild_id != player.guild_id:
            await set_position_cmd.finish("⛔ 该玩家不在你的公会中")

        # 创建GuildService实例
        guild_service = GuildServiceNew(
            player_repo=uow.players,
            guild_repo=uow.guilds,
            uow=uow
        )

        # 使用新版本设置职位
        success, message = await guild_service.set_member_position(
            player.id, player.guild_id, target_player.id, new_position
        )

        if not success:
            await set_position_cmd.finish(f"⛔ {message}")

        # UoW会在__aexit__中自动commit
        await set_position_cmd.finish(message_add_head(f"✅ {message}", event))
# ==================== 踢出公会成员 ====================
kick_member_cmd = on_command("踢出公会", aliases={"踢出成员"}, block=True, priority=11)

@kick_member_cmd.handle()
async def handle_kick_member(event: MessageEvent, args: Message = CommandArg()):
    """踢出公会成员：踢出公会 UID"""
    uid_str = args.extract_plain_text().strip()
    if not uid_str:
        await kick_member_cmd.finish("⛔ 格式错误，正确格式：踢出公会 [UID]")

    try:
        target_uid = int(uid_str)
    except ValueError:
        await kick_member_cmd.finish("⛔ UID 必须是数字")

    # 新版本: 使用DI架构
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal
    from .guild_service_new import GuildService as GuildServiceNew

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player or not player.guild_id:
            await kick_member_cmd.finish("⛔ 你未加入任何公会")

        # 创建GuildService实例
        guild_service = GuildServiceNew(
            player_repo=uow.players,
            guild_repo=uow.guilds,
            uow=uow
        )

        # 使用新版本踢出成员
        success, message = await guild_service.kick_member(
            player.id, player.guild_id, target_uid
        )

        if not success:
            await kick_member_cmd.finish(f"⛔ {message}")

        # UoW会在__aexit__中自动commit
        await kick_member_cmd.finish(message_add_head(f"🚪 {message}", event))
# ==================== 公会建筑管理 ====================
guild_buildings_cmd = on_command("公会建筑", aliases={"建筑列表"}, block=True, priority=11)

@guild_buildings_cmd.handle()
async def handle_guild_buildings(event: MessageEvent):
    """查看公会建筑列表"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await guild_buildings_cmd.finish("⛔ 你未加入任何公会")

        guild = await session.get(Guild, player.guild_id)

        # 新版：使用DI架构Service
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository

        building_service = GuildBuildingServiceNew(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            item_repo=None  # get_guild_buildings不需要item_repo
        )
        buildings = await building_service.get_guild_buildings(player.guild_id)

        lines = [
            f"# 🏗️ {guild.name}·建筑",
            "***",
        ]

        building_emojis = {"经验神龛": "✨", "资金金库": "💰", "训练场": "🏋️", "传送阵": "🔮", "丹房": "🧪", "公会仓库": "📦"}
        if not buildings:
            lines.append("暂无建筑，快去建造吧！")
        else:
            for building in buildings:
                effects_str = GuildBuildingServiceNew.format_building_effects(building["effects"])
                bicon = building_emojis.get(building['name'], "🏛️")
                lines.append(
                    f"{bicon} **{building['name']}** Lv.{building['level']}/{building['max_level']}　{effects_str}"
                )
                if building['level'] < building['max_level']:
                    bname = building['name']
                    lines.append(f"　{cmd('⬆️升级', f'建造 {bname}')}")
                lines.append("")

        lines.append("***")
        lines.append("**可建造建筑：**")
        building_names = ["经验神龛", "资金金库", "训练场", "传送阵", "丹房", "公会仓库"]
        lines.append(" | ".join([f"{building_emojis.get(n, '🏛️')}{cmd(n, f'建造 {n}')}" for n in building_names]))
        lines.append("***")
        lines.append(cmd("公会") + " | " + cmd("公会建筑") + " | " + cmd("帮助"))

        await guild_buildings_cmd.finish(build_markdown("\n".join(lines)))

build_cmd = on_command("建造", aliases={"升级建筑"}, block=True, priority=11)

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
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await build_cmd.finish("⛔ 你未加入任何公会")

        # 获取建造成本
        # 新版：使用DI架构Service
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository

        building_service = GuildBuildingServiceNew(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            item_repo=None  # get_build_cost不需要item_repo
        )
        cost = await building_service.get_build_cost(player.guild_id, building_type)
        if not cost:
            await build_cmd.finish("⛔ 该建筑已达到最高等级")

        # 显示成本信息（Markdown格式）
        materials_str = "、".join([f"{k}×{v}" for k, v in cost["materials"].items()])
        cost_lines = [
            f"# 🏗️ 建造确认",
            f"建筑：**{building_name}**",
            "***",
            f"💰 金币：**{cost['gold']:,}**",
            f"📦 材料：{materials_str}",
            "***",
            cmd("确认建造 " + building_name, f"确认建造 {building_name}") + " | " + cmd("取消", "公会建筑"),
        ]

        await build_cmd.send(build_markdown("\n".join(cost_lines)))

# ==================== 确认建造 ====================
confirm_build_cmd = on_command("确认", block=True, priority=11)

@confirm_build_cmd.handle()
async def handle_confirm_build(event: MessageEvent):
    """确认建造建筑"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await confirm_build_cmd.finish("⛔ 你未加入任何公会")

        # 这里需要一个临时存储机制来记住用户要建造的建筑类型
        # 由于没有会话状态管理，我们需要重新设计这个流程
        # 暂时返回提示信息，建议用户使用完整命令
        await confirm_build_cmd.finish("⛔ 请使用完整命令格式：确认建造 [建筑名]")

# ==================== 确认建造（带建筑名） ====================
confirm_build_with_name_cmd = on_command("确认建造", block=True, priority=11)

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
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await confirm_build_with_name_cmd.finish("⛔ 你未加入任何公会")

        # 执行建造
        # 新版：使用DI架构Service（由调用方控制事务边界）
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
        from ..infrastructure.repositories.item_repository import ItemRepository

        building_service = GuildBuildingServiceNew(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            item_repo=ItemRepository(session)  # build_or_upgrade需要item_repo消耗材料
        )
        success, message = await building_service.build_or_upgrade(
            player.guild_id, building_type, player.id
        )
        if success:
            await session.commit()  # 由调用方控制事务边界
            await confirm_build_with_name_cmd.finish(message_add_head(f"🏗️ {message}", event))
        else:
            await confirm_build_with_name_cmd.finish(message_add_head(f"⛔ {message}", event))



# ==================== 公会传送阵 ====================
guild_teleport_cmd = on_command("公会传送", aliases={"传送到公会"}, block=True, priority=11)

@guild_teleport_cmd.handle()
async def handle_guild_teleport(event: MessageEvent, args: Message = CommandArg()):
    """使用传送阵传送到公会基地或势力范围内的指定坐标"""
    args_text = args.extract_plain_text().strip()

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await guild_teleport_cmd.finish("⛔ 你未加入任何公会")

        # 检查是否在现实世界
        if player.region != "大都会":
            await guild_teleport_cmd.finish("⛔ 只能在现实世界使用传送阵")

        guild = await session.get(Guild, player.guild_id)
        if not guild:
            await guild_teleport_cmd.finish("⛔ 公会数据异常")

        # 如果没有参数，传送到公会基地
        if not args_text:
            from ..infrastructure.repositories.guild_repository import GuildRepository
            from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.item_repository import ItemRepository
            from ..infrastructure.repositories.guild_teleport_log_repository import GuildTeleportLogRepository
            from ..infrastructure.repositories.guild_alchemy_production_repository import GuildAlchemyProductionRepository
            from ..infrastructure.repositories.guild_warehouse_item_repository import GuildWarehouseItemRepository

            facility_service = GuildFacilityServiceNew(
                guild_repo=GuildRepository(session),
                building_repo=GuildBuildingRepository(session),
                player_repo=PlayerRepository(session),
                item_repo=ItemRepository(session),
                teleport_log_repo=GuildTeleportLogRepository(session),
                alchemy_production_repo=GuildAlchemyProductionRepository(session),
                warehouse_item_repo=GuildWarehouseItemRepository(session),
            )
            success, message = await facility_service.teleport_to_guild(player.id, player.guild_id)
            if success:
                await session.commit()
                await guild_teleport_cmd.finish(message_add_head(f"✨ {message}", event))
            else:
                await guild_teleport_cmd.finish(message_add_head(f"⛔ {message}", event))

        # 如果有参数，解析坐标并传送到势力范围内
        else:
            # 检查是否在公会基地
            current_x, current_y = player.get_current_coordinates()
            if guild.base_x is None or guild.base_y is None:
                await guild_teleport_cmd.finish("⛔ 公会尚未设置基地")

            if current_x != guild.base_x or current_y != guild.base_y:
                await guild_teleport_cmd.finish("⛔ 只有在公会基地才能传送到势力范围内的坐标")

            # 解析坐标参数
            coords = args_text.split()
            if len(coords) != 2:
                await guild_teleport_cmd.finish("⛔ 格式错误，正确格式：公会传送 x y")

            try:
                target_x = int(coords[0])
                target_y = int(coords[1])
            except ValueError:
                await guild_teleport_cmd.finish("⛔ 坐标必须是数字")

            # 检查目标坐标是否在势力范围内
            base_x, base_y = guild.base_x, guild.base_y
            territory_range = guild.territory_range

            # 势力范围是以基地为中心的正方形区域
            half_range = territory_range // 2
            min_x = base_x - half_range
            max_x = base_x + half_range
            min_y = base_y - half_range
            max_y = base_y + half_range

            if not (min_x <= target_x <= max_x and min_y <= target_y <= max_y):
                await guild_teleport_cmd.finish(
                    f"⛔ 目标坐标({target_x}, {target_y})超出公会势力范围\n"
                    f"势力范围：X({min_x}~{max_x}) Y({min_y}~{max_y})"
                )

            # 执行传送（不消耗传送次数）
            player.real_world_x = target_x
            player.real_world_y = target_y
            player.x = target_x
            player.y = target_y
            session.add(player)
            await session.commit()

            await guild_teleport_cmd.finish(message_add_head(
                f"✨ 传送成功！从公会基地({base_x}, {base_y})传送到({target_x}, {target_y})", event
            ))

# ==================== 公会丹房 ====================
guild_alchemy_cmd = on_command("公会丹房", aliases={"丹房", "丹药兑换"}, block=True, priority=11)

@guild_alchemy_cmd.handle()
async def handle_guild_alchemy(event: MessageEvent):
    """查看公会丹房产出"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await guild_alchemy_cmd.finish("⛔ 你未加入任何公会")

        guild = await session.get(Guild, player.guild_id)

        # 触发丹房产出检查和生成
        refresh_result = await GuildDailyTasks.trigger_guild_daily_refresh(session, player.guild_id)

        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.guild_teleport_log_repository import GuildTeleportLogRepository
        from ..infrastructure.repositories.guild_alchemy_production_repository import GuildAlchemyProductionRepository
        from ..infrastructure.repositories.guild_warehouse_item_repository import GuildWarehouseItemRepository

        facility_service = GuildFacilityServiceNew(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            player_repo=PlayerRepository(session),
            item_repo=ItemRepository(session),
            teleport_log_repo=GuildTeleportLogRepository(session),
            alchemy_production_repo=GuildAlchemyProductionRepository(session),
            warehouse_item_repo=GuildWarehouseItemRepository(session),
        )
        productions = await facility_service.get_alchemy_production_grouped(player.guild_id)
        # 提交丹房产出的更改
        await session.commit()

        lines = [
            f"# 🧪 {guild.name}·丹房",
            f"💰 你的积分：**{player.gold2}**",
        ]

        # 如果有新产出或存储已满，显示提示
        if refresh_result["alchemy_generated"] > 0:
            lines.append(f"✨ {refresh_result['message']}")
        elif refresh_result["alchemy_generated"] == -1:
            lines.append(f"{refresh_result['message']}")

        lines.append("***")

        if not productions:
            lines.append("暂无可兑换的丹药")
        else:
            for idx, prod in enumerate(productions, 1):
                pname = prod['item_name']
                lines.append(
                    f"💊 **{pname}**×{prod['total_quantity']}　"
                    f"💎{prod['points_cost']}积分/个　"
                    f"{cmd('🔄兑换', f'兑换丹药 {pname} 1')}"
                )

        lines.append("***")
        lines.append(cmd("公会") + " | " + cmd("公会丹房") + " | " + cmd("帮助"))

        await guild_alchemy_cmd.finish(build_markdown("\n".join(lines)))

# ==================== 兑换丹药 ====================
exchange_pill_cmd = on_command("兑换丹药", block=True, priority=11)

@exchange_pill_cmd.handle()
async def handle_exchange_pill(event: MessageEvent, args: Message = CommandArg()):
    """兑换丹房产出的丹药"""
    params = args.extract_plain_text().strip().split()
    if not params:
        await exchange_pill_cmd.finish("⛔ 格式错误，正确格式：兑换丹药 [丹药名称] [数量]")

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await exchange_pill_cmd.finish("⛔ 你未加入任何公会")

        # 触发丹房产出检查和生成
        await GuildDailyTasks.trigger_guild_daily_refresh(session, player.guild_id)

        # 创建facility_service实例（新旧两个版本都可能需要）
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.guild_teleport_log_repository import GuildTeleportLogRepository
        from ..infrastructure.repositories.guild_alchemy_production_repository import GuildAlchemyProductionRepository
        from ..infrastructure.repositories.guild_warehouse_item_repository import GuildWarehouseItemRepository

        facility_service = GuildFacilityServiceNew(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            player_repo=PlayerRepository(session),
            item_repo=ItemRepository(session),
            teleport_log_repo=GuildTeleportLogRepository(session),
            alchemy_production_repo=GuildAlchemyProductionRepository(session),
            warehouse_item_repo=GuildWarehouseItemRepository(session),
        )

        # 模式1：纯数字序号 "兑换丹药 1"
        if len(params) == 1 and params[0].isdigit():
            try:
                index = int(params[0])

                productions = await facility_service.get_alchemy_production(player.guild_id)

                if not productions or index < 1 or index > len(productions):
                    await exchange_pill_cmd.finish("⛔ 无效的序号")

                selected_prod = productions[index - 1]

                # 计算积分成本
                item_config = config.items_config["by_id"].get(selected_prod["item_id"])
                if not item_config:
                    await exchange_pill_cmd.finish("⛔ 物品配置错误")

                points_cost = max(1, item_config.price // 100)

                success, message = await facility_service.claim_alchemy_item(
                    player.id, player.guild_id, selected_prod["id"], points_cost
                )
            except ValueError:
                await exchange_pill_cmd.finish("⛔ 序号必须是数字")
            if success:
                await session.commit()
                await exchange_pill_cmd.finish(message_add_head(f"✅ {message}", event))
            else:
                await exchange_pill_cmd.finish(message_add_head(f"⛔ {message}", event))

        # 模式2：名称+数量 "兑换丹药 仿制还魂丹 5"
        elif len(params) >= 2:
            try:
                quantity = int(params[-1])  # 最后一个参数是数量
                item_name = " ".join(params[:-1])  # 前面的都是名称

                success, message = await facility_service.claim_alchemy_item_by_name(
                    player.id, player.guild_id, item_name, quantity
                )

                if success:
                    await session.commit()
                    await exchange_pill_cmd.finish(message_add_head(f"✅ {message}", event))
                else:
                    await exchange_pill_cmd.finish(message_add_head(f"⛔ {message}", event))
            except ValueError:
                await exchange_pill_cmd.finish("⛔ 数量必须是数字")

        # 模式3：参数格式不符合两种模式
        else:
            await exchange_pill_cmd.finish("⛔ 格式错误，支持两种方式：\n"
                "方式1：兑换丹药 [序号]\n"
                "方式2：兑换丹药 [丹药名称] [数量]")

# ==================== 公会仓库 ====================
guild_warehouse_cmd = on_command("公会仓库", aliases={"仓库"}, block=True, priority=11)

@guild_warehouse_cmd.handle()
async def handle_guild_warehouse(event: MessageEvent):
    """查看公会仓库"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await guild_warehouse_cmd.finish("⛔ 你未加入任何公会")

        # 检查是否在公会基地
        guild = await session.get(Guild, player.guild_id)
        if guild.base_x is None or guild.base_y is None:
            await guild_warehouse_cmd.finish("⛔ 公会尚未设置基地")

        if player.x != guild.base_x or player.y != guild.base_y:
            await guild_warehouse_cmd.finish("⛔ 只有在公会基地才能访问仓库")

        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.guild_teleport_log_repository import GuildTeleportLogRepository
        from ..infrastructure.repositories.guild_alchemy_production_repository import GuildAlchemyProductionRepository
        from ..infrastructure.repositories.guild_warehouse_item_repository import GuildWarehouseItemRepository

        facility_service = GuildFacilityServiceNew(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            player_repo=PlayerRepository(session),
            item_repo=ItemRepository(session),
            teleport_log_repo=GuildTeleportLogRepository(session),
            alchemy_production_repo=GuildAlchemyProductionRepository(session),
            warehouse_item_repo=GuildWarehouseItemRepository(session),
        )
        capacity = await facility_service.get_warehouse_capacity(player.guild_id)
        if capacity == 0:
            await guild_warehouse_cmd.finish("⛔ 公会尚未建造仓库")
        items = await facility_service.get_warehouse_items(player.guild_id)
        # 获取实际占用的格子数（数据库中的记录数，每个记录代表一个堆叠）
        stmt = select(_func.count(GuildWarehouseItem.id)).where(GuildWarehouseItem.guild_id == player.guild_id)
        current_slots_used = (await session.execute(stmt)).scalar_one() or 0

        lines = [
            f"# 📦 {guild.name}·仓库",
            f"格子：**{current_slots_used}**/{capacity}",
            "***",
        ]

        if not items:
            lines.append("暂无物品")
        else:
            for idx, item in enumerate(items, 1):
                iname = item['item_name']
                lines.append(
                    f"📦 **{iname}**×{item['quantity']}　"
                    f"👤存入者:{item['deposited_by']}　"
                    f"{cmd('⬆️取出', f'取出仓库 {iname} 1')}"
                )

        lines.append("***")
        lines.append(cmd("仓库记录") + " | " + cmd("公会") + " | " + cmd("帮助"))

        await guild_warehouse_cmd.finish(build_markdown("\n".join(lines)))

# ==================== 存入仓库 ====================
deposit_warehouse_cmd = on_command("存入仓库", block=True, priority=11)

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
        player = await get_unified_player(session, event)
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

        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.guild_teleport_log_repository import GuildTeleportLogRepository
        from ..infrastructure.repositories.guild_alchemy_production_repository import GuildAlchemyProductionRepository
        from ..infrastructure.repositories.guild_warehouse_item_repository import GuildWarehouseItemRepository
        from ..infrastructure.repositories.guild_warehouse_log_repository import GuildWarehouseLogRepository

        facility_service = GuildFacilityServiceNew(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            player_repo=PlayerRepository(session),
            item_repo=ItemRepository(session),
            teleport_log_repo=GuildTeleportLogRepository(session),
            alchemy_production_repo=GuildAlchemyProductionRepository(session),
            warehouse_item_repo=GuildWarehouseItemRepository(session),
            warehouse_log_repo=GuildWarehouseLogRepository(session),
        )
        success, message = await facility_service.deposit_to_warehouse(
            player.id, player.guild_id, item_config.item_id, quantity
        )
        if success:
            await session.commit()
            await deposit_warehouse_cmd.finish(message_add_head(f"✅ {message}", event))
        else:
            await deposit_warehouse_cmd.finish(message_add_head(f"⛔ {message}", event))

# ==================== 取出仓库 ====================
withdraw_warehouse_cmd = on_command("取出仓库", block=True, priority=11)

@withdraw_warehouse_cmd.handle()
async def handle_withdraw_warehouse(event: MessageEvent, args: Message = CommandArg()):
    """从公会仓库取出物品，支持物品名或序号"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await withdraw_warehouse_cmd.finish("⛔ 格式错误，正确格式：取出仓库 [物品名] [数量] 或 取出仓库 [序号] [数量]")

    parts = args_text.rsplit(maxsplit=1)
    if len(parts) < 2:
        await withdraw_warehouse_cmd.finish("⛔ 格式错误，正确格式：取出仓库 [物品名] [数量] 或 取出仓库 [序号] [数量]")

    # 解析数量（最后一个参数）
    try:
        quantity = int(parts[1])
        if quantity <= 0:
            raise ValueError
    except ValueError:
        await withdraw_warehouse_cmd.finish("⛔ 数量必须是正整数")

    # 判断第一个参数是序号还是物品名
    item_name = None
    index = None
    try:
        index = int(parts[0])
        if index <= 0:
            raise ValueError
    except ValueError:
        # 不是数字，当作物品名处理
        item_name = parts[0]

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await withdraw_warehouse_cmd.finish("⛔ 你未加入任何公会")

        # 检查是否在公会基地
        guild = await session.get(Guild, player.guild_id)
        if guild.base_x is None or guild.base_y is None:
            await withdraw_warehouse_cmd.finish("⛔ 公会尚未设置基地")

        if player.x != guild.base_x or player.y != guild.base_y:
            await withdraw_warehouse_cmd.finish("⛔ 只有在公会基地才能访问仓库")

        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.guild_teleport_log_repository import GuildTeleportLogRepository
        from ..infrastructure.repositories.guild_alchemy_production_repository import GuildAlchemyProductionRepository
        from ..infrastructure.repositories.guild_warehouse_item_repository import GuildWarehouseItemRepository
        from ..infrastructure.repositories.guild_warehouse_log_repository import GuildWarehouseLogRepository

        facility_service = GuildFacilityServiceNew(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            player_repo=PlayerRepository(session),
            item_repo=ItemRepository(session),
            teleport_log_repo=GuildTeleportLogRepository(session),
            alchemy_production_repo=GuildAlchemyProductionRepository(session),
            warehouse_item_repo=GuildWarehouseItemRepository(session),
            warehouse_log_repo=GuildWarehouseLogRepository(session),
        )

        if item_name:
            # 按物品名取出
            success, message = await facility_service.withdraw_from_warehouse_by_name(
                player.id, player.guild_id, item_name, quantity
            )
        else:
            # 按序号取出
            success, message = await facility_service.withdraw_from_warehouse(
                player.id, player.guild_id, index, quantity
            )
        if success:
            await session.commit()
            await withdraw_warehouse_cmd.finish(message_add_head(f"✅ {message}", event))
        else:
            await withdraw_warehouse_cmd.finish(message_add_head(f"⛔ {message}", event))

# ==================== 仓库记录 ====================
warehouse_log_cmd = on_command("仓库记录", block=True, priority=11)

@warehouse_log_cmd.handle()
async def handle_warehouse_log(event: MessageEvent, args: Message = CommandArg()):
    """查看公会仓库的存取操作记录"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await warehouse_log_cmd.finish("⛔ 你未加入任何公会")

        guild = await session.get(Guild, player.guild_id)

        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.guild_teleport_log_repository import GuildTeleportLogRepository
        from ..infrastructure.repositories.guild_alchemy_production_repository import GuildAlchemyProductionRepository
        from ..infrastructure.repositories.guild_warehouse_item_repository import GuildWarehouseItemRepository
        from ..infrastructure.repositories.guild_warehouse_log_repository import GuildWarehouseLogRepository

        facility_service = GuildFacilityServiceNew(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            player_repo=PlayerRepository(session),
            item_repo=ItemRepository(session),
            teleport_log_repo=GuildTeleportLogRepository(session),
            alchemy_production_repo=GuildAlchemyProductionRepository(session),
            warehouse_item_repo=GuildWarehouseItemRepository(session),
            warehouse_log_repo=GuildWarehouseLogRepository(session),
        )

        logs = await facility_service.get_warehouse_logs(player.guild_id, limit=20)

        if not logs:
            await warehouse_log_cmd.finish(message_add_head(
                f"📋 公会『{guild.name}』仓库记录\n━━━━━━━━━━\n暂无操作记录", event
            ))

        lines = [f"📋 公会『{guild.name}』仓库记录", "━━━━━━━━━━"]
        for log in logs:
            time_str = log["operated_at"].strftime("%m-%d %H:%M")
            op_icon = "📥" if log["operation"] == "存入" else "📤"
            lines.append(
                f"{op_icon} {time_str} {log['player_name']} "
                f"{log['operation']} {log['item_name']}×{log['quantity']}"
            )
        lines.append("━━━━━━━━━━")
        lines.append("💡 显示最近20条记录")

        await warehouse_log_cmd.finish(message_add_head("\n".join(lines), event))
