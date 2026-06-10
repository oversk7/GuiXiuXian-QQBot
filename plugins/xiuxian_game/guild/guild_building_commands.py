"""
公会建筑与基地命令（公会加成/设置基地/公会建筑/建造/确认建造/移动建筑）

从 guild.py 逐字拆分搬移，零行为变化。
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.guild import Guild
from ..utils import message_add_head
from ..utils_markdown import cmd, build_markdown
from .guild_building_service import GuildBuildingService
from .guild_economy_service import GuildEconomyService
from ..platform_utils import get_unified_player

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

        building_service = GuildBuildingService(
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

        # 装备设施
        if bonuses.get("forge_enabled"):
            forge_discount = bonuses.get("forge_gold_discount", 0.0)
            lines.append(f"⚒️ 基地锻造：开启，金币折扣+{forge_discount*100:.0f}%")
        else:
            lines.append("⚒️ 基地锻造：无")

        upgrade_bonus = bonuses.get("upgrade_success_bonus", 0.0)
        upgrade_discount = bonuses.get("upgrade_gold_discount", 0.0)
        if upgrade_bonus > 0 or upgrade_discount > 0:
            lines.append(f"⭐ 基地升阶：成功率+{upgrade_bonus*100:.0f}%，金币折扣+{upgrade_discount*100:.0f}%")
        else:
            lines.append("⭐ 基地升阶：无")

        adjacency_descriptions = bonuses.get("adjacency_descriptions", [])
        if adjacency_descriptions:
            lines.append("🌀 邻接加成：")
            lines.extend([f"• {desc}" for desc in adjacency_descriptions])
        else:
            lines.append("🌀 邻接加成：暂无")
            lines.append("💡 在【公会建筑】查看布局规则，把相关建筑放到上下左右相邻格")

        lines.append("━━━━━━━━━━")
        lines.append("💡 建造更多建筑可获得更强加成")

        msg = "\n".join(lines)
        await guild_bonuses_cmd.finish(message_add_head(msg, event))

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
            Guild.server_id == player.server_id,
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

        building_service = GuildBuildingService(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            item_repo=None  # get_guild_buildings不需要item_repo
        )
        buildings = await building_service.get_guild_buildings(player.guild_id)

        lines = [
            f"# 🏗️ {guild.name}·建筑",
            "***",
        ]

        building_emojis = {
            "经验神龛": "✨",
            "资金金库": "💰",
            "训练场": "🏋️",
            "传送阵": "🔮",
            "丹房": "🧪",
            "公会仓库": "📦",
            "聚灵阵": "🌀",
            "铸器坊": "⚒️",
            "淬灵台": "⭐",
        }
        if not buildings:
            lines.append("暂无建筑，快去建造吧！")
        else:
            lines.extend(GuildBuildingService.format_layout(buildings))
            lines.append("💡 上下左右相邻触发加成，斜角不触发")
            lines.append("")
            for building in buildings:
                effects_str = GuildBuildingService.format_building_effects(building["effects"])
                bicon = building_emojis.get(building['name'], "🏛️")
                position = "未布局"
                if building.get("plot_x") is not None and building.get("plot_y") is not None:
                    position = f"({building['plot_x']},{building['plot_y']})"
                lines.append(
                    f"{bicon} **{building['name']}** {position} Lv.{building['level']}/{building['max_level']}　{effects_str}"
                )
                if building['level'] < building['max_level']:
                    bname = building['name']
                    lines.append(f"　{cmd('⬆️升级', f'建造 {bname}')}")
                lines.append("")

        lines.append("***")
        lines.extend(GuildBuildingService.get_player_guide_lines())
        lines.append("***")
        lines.append("**可建造建筑：**")
        building_names = GuildBuildingService.get_buildable_names()
        lines.append(" | ".join([f"{building_emojis.get(n, '🏛️')}{cmd(n, f'建造 {n}')}" for n in building_names]))
        lines.append("***")
        lines.append(cmd("公会") + " | " + cmd("公会建筑") + " | " + cmd("帮助"))

        await guild_buildings_cmd.finish(build_markdown("\n".join(lines)))

build_cmd = on_command("建造", aliases={"升级建筑"}, block=True, priority=11)

@build_cmd.handle()
async def handle_build(event: MessageEvent, args: Message = CommandArg()):
    """建造或升级建筑：建造 建筑名 [x y]"""
    parts = args.extract_plain_text().strip().split()
    if not parts:
        await build_cmd.finish(
            "⛔ 格式错误，正确格式：建造 [建筑名] [x y]\n"
            f"可建造：{'、'.join(GuildBuildingService.get_buildable_names())}"
        )

    building_name = parts[0]
    plot_x = None
    plot_y = None
    if len(parts) >= 3:
        try:
            plot_x = int(parts[1])
            plot_y = int(parts[2])
        except ValueError:
            await build_cmd.finish("⛔ 布局坐标必须是数字，例如：建造 铸器坊 2 1")
    elif len(parts) == 2:
        await build_cmd.finish("⛔ 布局坐标需要同时提供 x y，例如：建造 铸器坊 2 1")

    building_type = GuildBuildingService.parse_building_name(building_name)
    if not building_type:
        await build_cmd.finish(f"⛔ 无效的建筑名，可建造：{'、'.join(GuildBuildingService.get_buildable_names())}")

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await build_cmd.finish("⛔ 你未加入任何公会")

        # 获取建造成本
        # 新版：使用DI架构Service
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
        from ..infrastructure.repositories.guild_warehouse_item_repository import GuildWarehouseItemRepository
        from ..infrastructure.repositories.item_repository import ItemRepository

        building_service = GuildBuildingService(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            item_repo=ItemRepository(session),
            warehouse_item_repo=GuildWarehouseItemRepository(session),
        )
        cost = await building_service.get_build_cost(player.guild_id, building_type)
        if not cost:
            await build_cmd.finish("⛔ 该建筑已达到最高等级")

        valid, reason, validation = await building_service.validate_build_or_upgrade(
            player.guild_id, building_type, player.id, plot_x, plot_y
        )
        if not valid:
            await build_cmd.finish(message_add_head(f"⛔ {reason}", event))

        # 显示成本信息（Markdown格式）
        material_lines = []
        for material_name, source in validation["material_sources"].items():
            material_lines.append(
                f"📦 {material_name}×{source['required']} "
                f"(仓库{source['warehouse']} / 背包{source['bag']})"
            )
        cost_lines = [
            f"# 🏗️ 建造确认",
            f"建筑：**{building_name}**",
            f"布局：**{f'({plot_x},{plot_y})' if plot_x is not None and plot_y is not None else '自动放置'}**",
            "***",
            f"💰 金币：**{cost['gold']:,}**",
            "**材料来源：**",
            *material_lines,
            "***",
            cmd(
                "确认建造 " + building_name,
                f"确认建造 {building_name}" + (f" {plot_x} {plot_y}" if plot_x is not None and plot_y is not None else ""),
            ) + " | " + cmd("取消", "公会建筑"),
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
    parts = args.extract_plain_text().strip().split()
    if not parts:
        await confirm_build_with_name_cmd.finish("⛔ 格式错误，正确格式：确认建造 [建筑名] [x y]")

    building_name = parts[0]
    plot_x = None
    plot_y = None
    if len(parts) >= 3:
        try:
            plot_x = int(parts[1])
            plot_y = int(parts[2])
        except ValueError:
            await confirm_build_with_name_cmd.finish("⛔ 布局坐标必须是数字，例如：确认建造 铸器坊 2 1")
    elif len(parts) == 2:
        await confirm_build_with_name_cmd.finish("⛔ 布局坐标需要同时提供 x y，例如：确认建造 铸器坊 2 1")

    building_type = GuildBuildingService.parse_building_name(building_name)
    if not building_type:
        await confirm_build_with_name_cmd.finish(f"⛔ 无效的建筑名，可建造：{'、'.join(GuildBuildingService.get_buildable_names())}")

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await confirm_build_with_name_cmd.finish("⛔ 你未加入任何公会")

        # 执行建造
        # 新版：使用DI架构Service（由调用方控制事务边界）
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.guild_warehouse_item_repository import GuildWarehouseItemRepository

        building_service = GuildBuildingService(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            item_repo=ItemRepository(session),
            warehouse_item_repo=GuildWarehouseItemRepository(session),
        )
        success, message = await building_service.build_or_upgrade(
            player.guild_id, building_type, player.id, plot_x, plot_y
        )
        if success:
            await session.commit()  # 由调用方控制事务边界
            await confirm_build_with_name_cmd.finish(message_add_head(f"🏗️ {message}", event))
        else:
            await confirm_build_with_name_cmd.finish(message_add_head(f"⛔ {message}", event))


move_building_cmd = on_command("移动建筑", aliases={"调整建筑"}, block=True, priority=11)

@move_building_cmd.handle()
async def handle_move_building(event: MessageEvent, args: Message = CommandArg()):
    """移动公会建筑：移动建筑 建筑名 x y"""
    parts = args.extract_plain_text().strip().split()
    if len(parts) != 3:
        await move_building_cmd.finish("⛔ 格式错误，正确格式：移动建筑 [建筑名] [x] [y]")

    building_name = parts[0]
    building_type = GuildBuildingService.parse_building_name(building_name)
    if not building_type:
        await move_building_cmd.finish(f"⛔ 无效的建筑名，可选：{'、'.join(GuildBuildingService.get_buildable_names())}")

    try:
        plot_x = int(parts[1])
        plot_y = int(parts[2])
    except ValueError:
        await move_building_cmd.finish("⛔ 布局坐标必须是数字，例如：移动建筑 铸器坊 2 1")

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await move_building_cmd.finish("⛔ 你未加入任何公会")

        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository

        building_service = GuildBuildingService(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            item_repo=None,
        )
        success, message = await building_service.move_building(
            player.guild_id, building_type, player.id, plot_x, plot_y
        )
        if success:
            await session.commit()
            await move_building_cmd.finish(message_add_head(f"✅ {message}", event))
        await move_building_cmd.finish(message_add_head(f"⛔ {message}", event))



