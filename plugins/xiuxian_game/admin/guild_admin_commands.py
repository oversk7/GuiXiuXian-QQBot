"""
公会管理命令
仅限管理员使用 - 全面删除公会
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import AsyncSessionLocal
from ..models.player import Player
from ..models.guild import Guild
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..guild.guild_service_new import GuildService
from ..utils import message_add_head
from ..ai_guide import is_admin


# ==================== 全面删除公会 ====================
delete_guild_cmd = on_command("删除公会", block=True, priority=5)


@delete_guild_cmd.handle()
async def handle_delete_guild(event: MessageEvent, args: Message = CommandArg()):
    """
    管理员指令：全面删除公会

    用法：
    1. 【删除公会 公会ID】 - 通过公会ID删除
    2. 【删除公会 公会名称】 - 通过公会名称删除

    此命令会:
    - 清空所有成员的公会相关数据 (guild_id, guild_contribution, gold2)
    - 删除公会成员记录
    - 删除公会丹房产出记录
    - 删除公会任务记录
    - 删除公会建筑记录
    - 删除公会主记录

    ⚠️ 警告：此操作不可逆，请谨慎使用！
    """
    # 权限检查
    if not is_admin(event.get_user_id()):
        await delete_guild_cmd.finish("⛔ 权限不足，该命令仅限管理员使用")

    # 获取参数
    raw_text = args.extract_plain_text().strip()
    if not raw_text:
        await delete_guild_cmd.finish(
            "⛔ 用法：【删除公会 公会ID】或【删除公会 公会名称】\n"
            "⚠️ 警告：此操作将全面删除公会及其所有相关数据，不可恢复！"
        )

    # 使用 DI 架构
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        # 判断输入的是ID还是名称
        guild = None

        # 尝试作为ID解析
        if raw_text.isdigit():
            guild_id = int(raw_text)
            guild = await uow.guilds.get_by_id(guild_id)
        else:
            # 作为名称查找
            guild = await uow.guilds.get_by_name(raw_text)

        if not guild:
            await delete_guild_cmd.finish(f"⛔ 未找到公会: {raw_text}")

        guild_id = guild.id
        guild_name = guild.name

        # 获取成员数量
        member_count = await uow.guilds.get_member_count(guild_id)

        # 创建服务实例
        guild_service = GuildService(
            player_repo=uow.players,
            guild_repo=uow.guilds,
            uow=uow
        )

        # 执行全面删除
        success, message = await guild_service.completely_delete_guild(guild_id)

        if not success:
            await delete_guild_cmd.finish(f"⛔ {message}")

        # UoW会在__aexit__中自动commit

    # 返回成功消息
    msg = (
        f"✅ 公会已全面删除\n"
        f"公会名称：{guild_name}\n"
        f"公会 ID：{guild_id}\n"
        f"成员数量：{member_count} 人\n"
        f"操作结果：{message}\n"
        f"⚠️ 数据库中已无任何相关记录"
    )
    await delete_guild_cmd.finish(message_add_head(msg, event))


# ==================== 查看所有公会 ====================
list_guilds_cmd = on_command("公会列表", aliases={"查看公会", "所有公会"}, block=True, priority=5)


@list_guilds_cmd.handle()
async def handle_list_guilds(event: MessageEvent, args: Message = CommandArg()):
    """
    管理员指令：查看所有公会列表

    用法：【公会列表】或【查看公会】

    显示所有公会的ID、名称、会长、等级、成员数量等信息
    """
    # 权限检查
    if not is_admin(event.get_user_id()):
        await list_guilds_cmd.finish("⛔ 权限不足，该命令仅限管理员使用")

    # 分页参数
    arg = args.extract_plain_text().strip()
    try:
        page = int(arg) if arg else 1
    except ValueError:
        page = 1
    page = max(1, page)

    page_size = 20

    # 使用 DI 架构
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        # 查询所有公会
        from sqlalchemy import select, desc

        stmt = select(Guild).order_by(desc(Guild.level), Guild.id)
        result = await uow.session.execute(stmt)
        guilds = result.scalars().all()

        if not guilds:
            await list_guilds_cmd.finish(message_add_head("📋 当前没有任何公会", event))

        # 分页
        total_guilds = len(guilds)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        guilds_page = guilds[start_idx:end_idx]

        # 构建消息 - 优化版，信息密度最大化
        lines = [f"📋 公会列表 (第{page}/{(total_guilds + page_size - 1) // page_size}页 | 共{total_guilds}个)"]
        lines.append("━━━━━━━━━━━━━")

        for guild in guilds_page:
            # 获取会长信息
            president = await uow.session.get(Player, guild.president_id)
            president_name = president.nickname if president else "未知"
            president_uid = president.uid if president else "N/A"

            # 获取成员数量
            member_count = await uow.guilds.get_member_count(guild.id)
            max_members = 10 + (guild.level - 1) * 5

            # 紧凑格式，所有信息在一行显示
            lines.append(
                f"🏰{guild.name} | Lv{guild.level} | {member_count}/{max_members}人 | "
                f"💰{guild.treasury:,} | ⭐{guild.exp:,}\n"
                f"   会长: {president_name}[UID:{president_uid}]"
            )

        lines.append("━━━━━━━━━━━━━")
        lines.append("💡 玩家可通过UID联系会长申请加入")
        if total_guilds > page_size:
            lines.append(f"💡 查看更多: 【公会列表 {page + 1}】")

    await list_guilds_cmd.finish(message_add_head("\n".join(lines), event))
