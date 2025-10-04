"""
材料统计系统 - 管理员专用
用于统计全服材料的数量分布，便于调整爆率和监控材料稀缺度
"""
from nonebot import on_command
from nonebot.permission import SUPERUSER
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select, func
from collections import defaultdict
from typing import Dict, List, Tuple

from ..models.db import safe_session
from ..models.inventory import ItemInstance
from ..models.player import Player
from ..models.guild import GuildWarehouseItem, Guild
from ..utils import message_add_head
from ..config import config


# ==================== 管理员指令：统计材料分布 ====================
material_stats_cmd = on_command("材料统计", aliases={"统计材料", "材料分布"}, block=True, priority=2, permission=SUPERUSER)


@material_stats_cmd.handle()
async def handle_material_stats(event: MessageEvent, args: Message = CommandArg()):
    """
    管理员指令：统计全服材料的数量分布
    用法：
      材料统计 - 统计所有材料
      材料统计 稀有度 - 统计指定稀有度的材料（white/green/blue/purple/orange）
      材料统计 材料名 - 统计指定材料的详细信息
    """
    param = args.extract_plain_text().strip()
    
    async with safe_session() as session:
        # 获取所有材料配置
        materials_config = config.items_config.get("by_type", {}).get("MATERIAL", [])
        
        if not materials_config:
            await material_stats_cmd.finish("⛔ 未找到材料配置")
        
        # 构建材料ID到配置的映射
        material_map = {}
        for item_id in materials_config:
            item_config = config.items_config["by_id"].get(item_id)
            if item_config:
                material_map[item_id] = item_config
        
        # 如果指定了材料名，查询该材料的详细信息
        if param and param not in ["white", "green", "blue", "purple", "orange"]:
            await show_material_detail(session, param, material_map, event)
            return
        
        # 查询玩家背包中所有材料的数量
        player_stmt = select(
            ItemInstance.item_id,
            func.sum(ItemInstance.quantity).label("total_quantity"),
            func.count(ItemInstance.id).label("player_count")
        ).where(
            ItemInstance.item_id.in_(list(material_map.keys())),
            ItemInstance.quantity > 0
        ).group_by(ItemInstance.item_id)

        player_result = await session.execute(player_stmt)
        player_stats = {item_id: (qty, count) for item_id, qty, count in player_result.all()}

        # 查询公会仓库中所有材料的数量
        warehouse_stmt = select(
            GuildWarehouseItem.item_id,
            func.sum(GuildWarehouseItem.quantity).label("total_quantity"),
            func.count(func.distinct(GuildWarehouseItem.guild_id)).label("guild_count")
        ).where(
            GuildWarehouseItem.item_id.in_(list(material_map.keys()))
        ).group_by(GuildWarehouseItem.item_id)

        warehouse_result = await session.execute(warehouse_stmt)
        warehouse_stats = {item_id: (qty, count) for item_id, qty, count in warehouse_result.all()}

        # 合并统计数据
        stats_data = []
        all_item_ids = set(player_stats.keys()) | set(warehouse_stats.keys())
        for item_id in all_item_ids:
            player_qty, player_count = player_stats.get(item_id, (0, 0))
            warehouse_qty, guild_count = warehouse_stats.get(item_id, (0, 0))
            total_qty = player_qty + warehouse_qty
            stats_data.append((item_id, total_qty, player_count, warehouse_qty, guild_count))
        
        # 按稀有度分组统计
        rarity_stats: Dict[str, List[Tuple]] = defaultdict(list)
        total_materials = 0
        total_warehouse_materials = 0
        total_players_holding = set()
        total_guilds_holding = set()

        for item_id, total_qty, player_count, warehouse_qty, guild_count in stats_data:
            item_config = material_map.get(item_id)
            if not item_config:
                continue

            rarity = getattr(item_config, "rarity", "white")
            rarity_stats[rarity].append((item_config, total_qty, player_count, warehouse_qty, guild_count))
            total_materials += total_qty
            total_warehouse_materials += warehouse_qty

            # 获取持有该材料的玩家ID
            player_id_stmt = select(ItemInstance.player_id).where(
                ItemInstance.item_id == item_id,
                ItemInstance.quantity > 0
            ).distinct()
            player_id_result = await session.execute(player_id_stmt)
            for (player_id,) in player_id_result:
                total_players_holding.add(player_id)

            # 获取持有该材料的公会ID
            guild_id_stmt = select(GuildWarehouseItem.guild_id).where(
                GuildWarehouseItem.item_id == item_id
            ).distinct()
            guild_id_result = await session.execute(guild_id_stmt)
            for (guild_id,) in guild_id_result:
                total_guilds_holding.add(guild_id)
        
        # 获取总玩家数和总公会数
        total_players_stmt = select(func.count(Player.id))
        total_players = (await session.execute(total_players_stmt)).scalar_one()

        total_guilds_stmt = select(func.count(Guild.id))
        total_guilds = (await session.execute(total_guilds_stmt)).scalar_one()

        # 如果指定了稀有度，只显示该稀有度的材料
        if param in ["white", "green", "blue", "purple", "orange"]:
            await show_rarity_stats(param, rarity_stats, total_materials, total_warehouse_materials,
                                   total_players, len(total_players_holding),
                                   total_guilds, len(total_guilds_holding), event)
            return

        # 显示总体统计
        await show_overall_stats(rarity_stats, total_materials, total_warehouse_materials,
                                total_players, len(total_players_holding),
                                total_guilds, len(total_guilds_holding), event)


async def show_material_detail(session, material_name: str, material_map: Dict, event: MessageEvent):
    """显示指定材料的详细统计信息"""
    # 查找材料配置
    target_config = None
    target_id = None
    for item_id, item_config in material_map.items():
        if item_config.name == material_name:
            target_config = item_config
            target_id = item_id
            break

    if not target_config:
        await material_stats_cmd.finish(f"⛔ 未找到材料：{material_name}")

    # 查询玩家背包中该材料的详细数据
    player_stmt = select(
        ItemInstance.player_id,
        ItemInstance.quantity
    ).where(
        ItemInstance.item_id == target_id,
        ItemInstance.quantity > 0
    ).order_by(ItemInstance.quantity.desc())

    player_result = await session.execute(player_stmt)
    player_holdings = player_result.all()

    # 查询公会仓库中该材料的数据
    warehouse_stmt = select(
        GuildWarehouseItem.guild_id,
        func.sum(GuildWarehouseItem.quantity).label("total_quantity")
    ).where(
        GuildWarehouseItem.item_id == target_id
    ).group_by(GuildWarehouseItem.guild_id).order_by(func.sum(GuildWarehouseItem.quantity).desc())

    warehouse_result = await session.execute(warehouse_stmt)
    warehouse_holdings = warehouse_result.all()

    # 统计数据
    player_total_qty = sum(qty for _, qty in player_holdings)
    warehouse_total_qty = sum(qty for _, qty in warehouse_holdings)
    total_qty = player_total_qty + warehouse_total_qty

    if total_qty == 0:
        await material_stats_cmd.finish(f"📊 材料详情：{material_name}\n━━━━━━━━━━━━━\n⚠️ 全服无人持有此材料")

    player_count = len(player_holdings)
    guild_count = len(warehouse_holdings)
    avg_qty = player_total_qty / player_count if player_count > 0 else 0
    max_qty = player_holdings[0][1] if player_holdings else 0
    min_qty = player_holdings[-1][1] if player_holdings else 0
    
    # 获取持有量前10的玩家
    top_player_holders = []
    for player_id, qty in player_holdings[:10]:
        player = await session.get(Player, player_id)
        if player:
            top_player_holders.append((player.uid, player.nickname, qty))

    # 获取持有量前5的公会
    top_guild_holders = []
    for guild_id, qty in warehouse_holdings[:5]:
        guild = await session.get(Guild, guild_id)
        if guild:
            top_guild_holders.append((guild.name, qty))

    # 构建消息
    rarity_emoji = {
        "white": "⚪",
        "green": "🟢",
        "blue": "🔵",
        "purple": "🟣",
        "orange": "🟠"
    }
    rarity = getattr(target_config, "rarity", "white")
    emoji = rarity_emoji.get(rarity, "⚪")

    msg_lines = [
        f"📊 材料详情：{emoji} {material_name}",
        "━━━━━━━━━━━━━",
        f"🎯 稀有度：{rarity.upper()}",
        f"💰 价格：{target_config.price} 金币",
        f"📦 总数量：{total_qty:,}",
        f"  ├ 玩家背包：{player_total_qty:,} ({player_total_qty/total_qty*100:.1f}%)",
        f"  └ 公会仓库：{warehouse_total_qty:,} ({warehouse_total_qty/total_qty*100:.1f}%)",
        f"👥 持有人数：{player_count}",
        f"🏛️ 持有公会：{guild_count}",
        f"📈 玩家人均：{avg_qty:.1f}",
        f"🔝 玩家最大：{max_qty:,}",
        f"🔻 玩家最小：{min_qty:,}",
        "━━━━━━━━━━━━━",
        "🏆 玩家持有量排行榜 TOP10："
    ]

    for rank, (uid, nickname, qty) in enumerate(top_player_holders, 1):
        msg_lines.append(f"{rank}. UID{uid} {nickname} - {qty:,}个")

    if top_guild_holders:
        msg_lines.append("━━━━━━━━━━━━━")
        msg_lines.append("🏛️ 公会仓库排行榜 TOP5：")
        for rank, (guild_name, qty) in enumerate(top_guild_holders, 1):
            msg_lines.append(f"{rank}. {guild_name} - {qty:,}个")

    await material_stats_cmd.finish(message_add_head("\n".join(msg_lines), event))


async def show_rarity_stats(rarity: str, rarity_stats: Dict, total_materials: int, total_warehouse_materials: int,
                            total_players: int, players_holding: int,
                            total_guilds: int, guilds_holding: int, event: MessageEvent):
    """显示指定稀有度的材料统计"""
    if rarity not in rarity_stats:
        await material_stats_cmd.finish(f"⛔ 该稀有度暂无材料数据：{rarity.upper()}")

    materials = rarity_stats[rarity]
    # 按总数量降序排序
    materials.sort(key=lambda x: x[1], reverse=True)

    rarity_emoji = {
        "white": "⚪",
        "green": "🟢",
        "blue": "🔵",
        "purple": "🟣",
        "orange": "🟠"
    }
    emoji = rarity_emoji.get(rarity, "⚪")

    rarity_total = sum(qty for _, qty, _, _, _ in materials)
    rarity_warehouse_total = sum(warehouse_qty for _, _, _, warehouse_qty, _ in materials)
    rarity_percentage = (rarity_total / total_materials * 100) if total_materials > 0 else 0

    msg_lines = [
        f"📊 {emoji} {rarity.upper()}品质材料统计",
        "━━━━━━━━━━━━━",
        f"📦 该品质总量：{rarity_total:,} ({rarity_percentage:.1f}%)",
        f"  ├ 玩家背包：{rarity_total - rarity_warehouse_total:,}",
        f"  └ 公会仓库：{rarity_warehouse_total:,}",
        f"🎯 材料种类：{len(materials)}种",
        "━━━━━━━━━━━━━",
        "📋 材料列表（按数量排序）："
    ]

    for item_config, total_qty, player_count, warehouse_qty, guild_count in materials:
        percentage = (total_qty / rarity_total * 100) if rarity_total > 0 else 0
        player_qty = total_qty - warehouse_qty
        avg_per_player = player_qty / player_count if player_count > 0 else 0
        msg_lines.append(
            f"• {item_config.name}\n"
            f"  总量：{total_qty:,} ({percentage:.1f}%)\n"
            f"  玩家：{player_qty:,} | 持有人数：{player_count} | 人均：{avg_per_player:.1f}\n"
            f"  公会：{warehouse_qty:,} | 持有公会：{guild_count}"
        )

    msg_lines.append("━━━━━━━━━━━━━")
    msg_lines.append(f"💡 提示：使用【材料统计 材料名】查看详细信息")

    await material_stats_cmd.finish(message_add_head("\n".join(msg_lines), event))


async def show_overall_stats(rarity_stats: Dict, total_materials: int, total_warehouse_materials: int,
                             total_players: int, players_holding: int,
                             total_guilds: int, guilds_holding: int, event: MessageEvent):
    """显示总体材料统计"""
    rarity_order = ["white", "green", "blue", "purple", "orange"]
    rarity_names = {
        "white": "⚪ 普通",
        "green": "🟢 高级",
        "blue": "🔵 稀有",
        "purple": "🟣 史诗",
        "orange": "🟠 传说"
    }

    player_materials = total_materials - total_warehouse_materials

    msg_lines = [
        "📊 全服材料统计总览",
        "━━━━━━━━━━━━━",
        f"📦 材料总量：{total_materials:,}",
        f"  ├ 玩家背包：{player_materials:,} ({player_materials/total_materials*100:.1f}%)",
        f"  └ 公会仓库：{total_warehouse_materials:,} ({total_warehouse_materials/total_materials*100:.1f}%)",
        f"👥 总玩家数：{total_players}",
        f"🎒 持有材料玩家：{players_holding} ({players_holding/total_players*100:.1f}%)" if total_players > 0 else "🎒 持有材料玩家：0",
        f"📈 玩家人均材料：{player_materials/total_players:.1f}" if total_players > 0 else "📈 玩家人均材料：0",
        f"🏛️ 总公会数：{total_guilds}",
        f"📦 持有材料公会：{guilds_holding} ({guilds_holding/total_guilds*100:.1f}%)" if total_guilds > 0 else "📦 持有材料公会：0",
        "━━━━━━━━━━━━━",
        "🎯 按稀有度分布："
    ]

    for rarity in rarity_order:
        if rarity not in rarity_stats:
            continue

        materials = rarity_stats[rarity]
        rarity_total = sum(qty for _, qty, _, _, _ in materials)
        rarity_warehouse = sum(warehouse_qty for _, _, _, warehouse_qty, _ in materials)
        rarity_player = rarity_total - rarity_warehouse
        rarity_percentage = (rarity_total / total_materials * 100) if total_materials > 0 else 0
        material_count = len(materials)

        msg_lines.append(
            f"{rarity_names[rarity]}\n"
            f"  种类：{material_count}种 | 总量：{rarity_total:,} ({rarity_percentage:.1f}%)\n"
            f"  玩家：{rarity_player:,} | 公会：{rarity_warehouse:,}"
        )

    msg_lines.append("━━━━━━━━━━━━━")
    msg_lines.append("💡 使用方法：")
    msg_lines.append("  【材料统计 稀有度】- 查看指定品质")
    msg_lines.append("  【材料统计 材料名】- 查看详细信息")
    msg_lines.append("  例如：材料统计 purple")
    msg_lines.append("  例如：材料统计 神明之泪")

    await material_stats_cmd.finish(message_add_head("\n".join(msg_lines), event))

