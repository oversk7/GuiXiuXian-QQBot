from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select, delete as sql_delete
from datetime import datetime

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..models.guild import Guild, GuildPosition, BuildingType, GuildWarehouseItem, GuildAlchemyProduction, GuildTeleportLog
from ..models.guild_task_record import GuildTaskRecord
from ..config import config
from ..utils import message_add_head
from ..utils_markdown import cmd, build_markdown
from ..models.social_application import SocialApplication, ApplicationType, ApplicationStatus
from ..models.donation_log import PlayerDonationLog
from ..models.navigation_task import NavigationTask
from .guild_application_service import GuildApplicationService  # DI版本
from .guild_service import GuildService  # DI版本
from .guild_permission import GuildPermission
from .guild_economy_service import GuildEconomyService
from .guild_building_service import GuildBuildingService
from .guild_task_service import GuildTaskService
from .guild_daily_tasks import GuildDailyTasks
from ..platform_utils import get_unified_player, require_player

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
        player = await require_player(uow.session, event, create_guild_cmd)
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
        existing_guild = await uow.guilds.get_by_name(guild_name, player.server_id)
        if existing_guild:
            await create_guild_cmd.finish("⛔ 已存在同名公会")

        # 4. 使用UoW的仓储创建Service
        guild_service = GuildService(
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
    from .guild_service import GuildService

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
        guild_service = GuildService(
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
        building_service = GuildBuildingService(
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
        player = await require_player(session, event, join_guild_cmd)

        # 新版：使用DI架构Service（修复P0问题：移除内部commit）
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository

        service = GuildApplicationService(
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
    from .guild_service import GuildService

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player or player.guild_id is None:
            await quit_guild_cmd.finish("⛔ 你未加入任何公会")

        guild_obj = await uow.session.get(Guild, player.guild_id)
        guild_name = guild_obj.name if guild_obj else "未知公会"

        # 创建GuildService实例
        guild_service = GuildService(
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
        from ..platform_utils import get_unified_player, require_player
        player = await require_player(session, event, donate_cmd)

        # 使用经济服务处理捐献
        # 新版：使用DI架构Service
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
        from ..infrastructure.repositories.player_donation_log_repository import PlayerDonationLogRepository

        economy_service = GuildEconomyService(
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

        task_service = GuildTaskService(
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
        points_line = f"✨ 获得积分：+{result['points_gained']}"
        if result["points_limit_reached"]:
            points_line += "（今日捐献积分已达上限）"

        msg_lines = [
            f"💰 捐献成功！金币 -{amt}",
            points_line,
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

        economy_service = GuildEconomyService(
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

    from sqlalchemy import func

    async with safe_session() as session:
        # 每日自动检查：会长继承 / 僵尸公会解散
        viewer = await get_unified_player(session, event)
        server_id = viewer.server_id if viewer else 1

        activity_logs = await maybe_run_activity_check(session, server_id=server_id)
        total_guilds = (await session.execute(
            select(func.count()).select_from(Guild).where(Guild.server_id == server_id)
        )).scalar_one()
        total_pages = max(1, (total_guilds + page_size - 1) // page_size)
        page = min(page, total_pages)
        page_rows = await get_guilds_sorted_by_activity(
            session, server_id=server_id, page=page, page_size=page_size,
        )

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

        for guild in page_rows:
            president_name = guild.president_name if guild.president_uid is not None else "未知"
            member_count = guild.member_count
            max_members = 10 + (guild.level - 1) * 5

            lines.append(
                f"🏰 **{guild.name}** Lv.{guild.level}│"
                f"{member_count}/{max_members}人│"
                f"💰{guild.treasury:,}"
            )
            president_uid = guild.president_uid if guild.president_uid is not None else 0
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

    if not total_guilds:
        await list_guilds_cmd.finish(message_add_head("📋 当前没有任何公会", event))
    await list_guilds_cmd.finish(build_markdown("\n".join(lines)))

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

