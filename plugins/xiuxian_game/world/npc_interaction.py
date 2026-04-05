"""
NPC交互命令

处理玩家与NPC的交互，包括商人交易、工匠锻造、雇主打工、鬼怪战斗等
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from nonebot.exception import FinishedException
from nonebot.log import logger

from ..models.db import safe_session
from ..models.player import Player
from ..models.npc import NPC, NPCType
from ..utils import message_add_head
from .location_service import LocationService
from .npc_service import NPCService

# 使用DI架构的NPCService和LocationService


# ==================== NPC交互命令 ====================
interact_cmd = on_command("交互", aliases={"找"}, block=True, priority=5)


@interact_cmd.handle()
async def handle_npc_interaction(event: MessageEvent, args: Message = CommandArg()):
    """处理NPC交互命令"""
    args_text = args.extract_plain_text().strip()

    # 分离NPC名字和对话内容（用于AI对话）
    # 格式: "交互 NPC名" 或 "交互 NPC名 对话内容"
    npc_name = args_text
    dialogue_content = None

    # 尝试分割（只在有空格时）
    if ' ' in args_text:
        parts = args_text.split(' ', 1)  # 只分割一次
        potential_npc_name = parts[0]
        potential_dialogue = parts[1] if len(parts) > 1 else None

        # 先尝试用完整文本匹配，如果失败再用分割后的
        npc_name = args_text  # 默认用完整文本
        dialogue_content = potential_dialogue  # 记录可能的对话内容

    if not args_text:
        help_msg = (
            "🤖 NPC交互系统\n"
            "━━━━━━━━━━━━━\n"
            "🎯 使用方法：\n"
            "【交互 <NPC名称>】与指定NPC交互\n"
            "━━━━━━━━━━━━━\n"
            "💡 可交互的NPC类型：\n"
            "• 商人 - 物品交易\n"
            "• 工匠 - 装备锻造、升阶、镶嵌\n"
            "• 雇主 - 打工服务\n"
            "• 鬼怪 - 战斗\n"
            "• 中立NPC - 怪谈风格对话，了解世界观\n"
            "━━━━━━━━━━━━━\n"
            "🌟 示例：交互 铁匠老王\n"
            "👻 提示：中立NPC会分享神秘的故事和传说"
        )
        await interact_cmd.finish(message_add_head(help_msg, event))

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player: Player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await interact_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await interact_cmd.finish("⛔ 请先创建角色")

        if player.is_in_dungeon():
            await interact_cmd.finish("⛔ 你在诡域中，无法与现实世界的NPC交互")

        # 初始化NPC服务
        from ..infrastructure.repositories.npc_repository import NPCRepository
        from .npc_service_new import NPCService as NPCServiceNew
        npc_service = NPCServiceNew(session=session, npc_repo=NPCRepository(session))

        # 获取当前位置
        current_x, current_y = player.get_current_coordinates()
        current_region = player.get_current_region()

        # 查找当前位置的地点
        location = await LocationService.get_location_by_coordinates(
        session, current_x, current_y, current_region
        )

        if not location:
            await interact_cmd.finish("⛔ 当前位置没有NPC可以交互")

        # 查找指定名称的NPC
        npc = await npc_service.get_npc_by_name(npc_name, location.id)

        if not npc:
            # 尝试智能匹配（支持带点号的名字）
            from .attack_command import find_npc_by_smart_match
            possible_npcs = await find_npc_by_smart_match(session, npc_name, location.id)

            # 如果完整文本匹配失败，且包含空格，尝试用第一个词匹配（支持"交互 司长 你好"）
            if not possible_npcs and ' ' in args_text:
                potential_npc_name = args_text.split(' ', 1)[0]
                npc = await npc_service.get_npc_by_name(potential_npc_name, location.id)
                if not npc:
                    possible_npcs = await find_npc_by_smart_match(session, potential_npc_name, location.id)
                if npc:
                    # 找到了！更新dialogue_content
                    if ' ' in args_text:
                        dialogue_content = args_text.split(' ', 1)[1]

            # 如果还是找不到，尝试模糊匹配（关键词匹配）
            if not possible_npcs and not npc:
                # 获取当前位置所有NPC，进行关键词匹配
                from sqlalchemy import select
                stmt = select(NPC).where(
                    NPC.location_id == location.id,
                    NPC.is_active == True
                )
                result = await session.execute(stmt)
                all_npcs = list(result.scalars().all())

                # 关键词匹配：NPC名字包含输入的关键词
                search_keyword = npc_name.lower()
                matched_npcs = [n for n in all_npcs if search_keyword in n.name.lower()]

                if matched_npcs:
                    possible_npcs = matched_npcs

            # 处理匹配结果
            if not possible_npcs and not npc:
                await interact_cmd.finish(f"⛔ 在当前位置找不到名为'{args_text}'的NPC")
            elif npc:
                # 已经找到了精确匹配的NPC，继续处理
                pass
            elif len(possible_npcs) == 1:
                # 只有一个匹配结果，直接使用
                npc = possible_npcs[0]
                # 如果原始输入包含空格，提取对话内容
                if ' ' in args_text and not dialogue_content:
                    # 尝试从原始输入中分离NPC名和对话内容
                    dialogue_content = args_text.split(' ', 1)[1] if ' ' in args_text else None
            elif len(possible_npcs) > 1:
                # 多个匹配结果，给出友好提示
                npc_list = []
                for n in possible_npcs[:5]:  # 最多显示5个
                    npc_list.append(f"• {n.name}")

                # 安全地获取示例名称
                example_name = possible_npcs[0].name
                short_name = example_name.split('·')[-1] if '·' in example_name else example_name

                msg = (
                    f"🔍 找到多个匹配'{args_text}'的NPC：\n"
                    "━━━━━━━━━━━━━\n" +
                    "\n".join(npc_list) +
                    ("\n..." if len(possible_npcs) > 5 else "") +
                    "\n━━━━━━━━━━━━━\n"
                    "💡 请使用更具体的名称，如：\n"
                    f"• 交互 {short_name}\n"
                    f"• 交互 {example_name}"
                )
                await interact_cmd.finish(message_add_head(msg, event))

        # 获取NPC交互信息
        interaction_info = await npc_service.get_npc_interaction_info(npc)
        if not interaction_info["can_interact"]:
            await interact_cmd.finish(f"⛔ {interaction_info['message']}")

        # 根据NPC类型处理交互
        await handle_npc_type_interaction(session, player, npc, interaction_info, event, dialogue_content)


async def handle_npc_type_interaction(session, player: Player, npc, interaction_info: dict, event: MessageEvent, dialogue_content: str = None):
    """根据NPC类型处理具体交互"""
    # 优先检查是否启用AI对话（适用于所有类型的NPC）
    if npc.extra_data and npc.extra_data.get("ai_enabled"):
        try:
            await handle_ai_dialogue_interaction(session, player, npc, event, question=dialogue_content)
            return
        except FinishedException:
            # FinishedException是正常的流程控制，直接抛出
            raise
        except Exception as e:
            logger.error(f"AI对话失败 - NPC: {npc.name}, 玩家: {player.id}, 错误: {e}", exc_info=True)
            # 降级处理：显示友好提示
            await interact_cmd.finish(
                f"💬 {npc.name}\n"
                f"━━━━━━━━━━━━━\n"
                f"抱歉，{npc.name}暂时无法交谈。请稍后再试。\n\n"
                f"💡 提示：如果问题持续，请联系管理员。"
            )
            return

    npc_type = npc.npc_type

    if npc_type == NPCType.MERCHANT:
        await handle_merchant_interaction(session, player, npc, event)
    elif npc_type == NPCType.CRAFTSMAN:
        await handle_craftsman_interaction(session, player, npc, event)
    elif npc_type == NPCType.EMPLOYER:
        await handle_employer_interaction(session, player, npc, event)
    elif npc_type == NPCType.GHOST:
        await handle_ghost_interaction(session, player, npc, event)
    elif npc_type == NPCType.SPECIAL_VENDOR:
        await handle_special_vendor_interaction(session, player, npc, event)
    elif npc.has_function("social_agent"):
        # 社交代理优先匹配（同时拥有matchmaker/sworn_ceremony/mentorship，走统一菜单）
        await handle_social_agent_interaction(session, player, npc, event, dialogue_content)
    elif npc.has_function("intelligence_dealer"):
        await handle_intelligence_dealer_interaction(session, player, npc, event)
    elif npc.has_function("station_master"):
        await handle_station_master_interaction(session, player, npc, event)
    elif npc.has_function("matchmaker"):
        await handle_matchmaker_interaction(session, player, npc, event, dialogue_content)
    elif npc.has_function("sworn_ceremony"):
        await handle_sworn_envoy_interaction(session, player, npc, event, dialogue_content)
    elif npc.has_function("mentorship"):
        await handle_mentor_envoy_interaction(session, player, npc, event, dialogue_content)
    else:
        await handle_generic_interaction(session, player, npc, event, dialogue_content)


async def handle_merchant_interaction(session, player: Player, npc, event: MessageEvent):
    """处理商人交互"""
    lines = [
        f"🏪 商人 {npc.name}",
        "━━━━━━━━━━━━━",
        f"💬 {npc.name}：欢迎光临！我这里有各种商品。",
        "",
        "🛒 可用服务：",
        "• 【市集】查看商品列表",
        "• 【购买 <物品名> <数量>】购买物品",
        "• 【出售 <物品名> <数量>】出售物品",
        "",
        "💡 提示：使用【市集】命令查看当前位置的市场"
    ]

    await interact_cmd.finish(message_add_head("\n".join(lines), event))


async def handle_craftsman_interaction(session, player: Player, npc, event: MessageEvent):
    """处理工匠交互"""
    lines = [
        f"⚒️ 工匠 {npc.name}",
        "━━━━━━━━━━━━━",
        f"💬 {npc.name}：需要锻造或升阶装备吗？我的手艺可是一流的！",
        "",
        "🔨 可用服务：",
        "• 【锻造】查看可锻造的装备",
        "• 【锻造列表】查看本城可锻造清单",
        "• 【配方 <装备名称>】查看锻造配方",

        "• 【升阶 <编号/名称>】升阶装备",
        "• 【升阶信息 <编号/名称>】查看升阶需求与成功率",
        "• 【升阶列表】查看可升阶装备",

        "• 【镶嵌 <编号/名称> <镶嵌物名称>】镶嵌宝石/佛珠/符文",
        "• 【孔位 <编号/名称>】查看装备孔位",
        "",
        "💡 提示：锻造需要消耗材料和金币"
    ]

    await interact_cmd.finish(message_add_head("\n".join(lines), event))


async def handle_employer_interaction(session, player: Player, npc, event: MessageEvent):
    """处理雇主交互"""
    lines = [
        f"💼 雇主 {npc.name}",
        "━━━━━━━━━━━━━",
        f"💬 {npc.name}：正在找工作吗？我这里有不错的机会！",
        "",
        "💰 可用服务：",
        "• 【打工】查看工作机会",
        "• 【打工 <工作类型>】开始工作",
        "• 【收工】完成当前工作",
        "• 【工作状态】查看工作进度",
        "",
        "💡 提示：不同工作有不同的时长和收入"
    ]

    await interact_cmd.finish(message_add_head("\n".join(lines), event))


async def handle_ghost_interaction(session, player: Player, npc, event: MessageEvent):
    """处理鬼怪交互"""
    lines = [
        f"👻 {npc.name}",
        "━━━━━━━━━━━━━",
    ]

    # 检查是否为活动鬼怪,如果是则展示叙事文本
    from ..event.knocker_event import KnockerEventService
    narrative = KnockerEventService.get_ghost_narrative(npc)
    if narrative:
        lines.append(f"🎆 除夕诡象·缉邪通报")
        lines.append(narrative)
        lines.append("")

    lines.extend([
        f"💀 {npc.name}发出阴森的笑声，散发着不祥的气息...",
        f"⚔️ 等级：{npc.level}",
        f"❤️ 血量：{npc.hp}/{npc.max_hp}",
        f"⚡ 攻击：{npc.attack}",
        f"🛡️ 防御：{npc.defense}",
        "",
        "⚔️ 可用操作：",
        f"• 【攻击 {npc.name}】与鬼怪战斗",
        "",
        "⚠️ 警告：战斗可能造成伤亡，请谨慎行事！"
    ])

    await interact_cmd.finish(message_add_head("\n".join(lines), event))


async def handle_special_vendor_interaction(session, player: Player, npc, event: MessageEvent):
    """处理特殊商贩交互"""
    lines = [
        f"🏛️ 特殊商贩 {npc.name}",
        "━━━━━━━━━━━━━",
        f"💬 {npc.name}：我这里有一些特殊的商品和服务。",
        "",
        "✨ 可用服务：",
        "• 【总部商店】查看特殊商品（如果是缉邪司）",
        "• 【兑换】查看可兑换物品",
        "",
        "💡 提示：特殊商贩通常需要特殊货币或积分"
    ]

    await interact_cmd.finish(message_add_head("\n".join(lines), event))


async def handle_matchmaker_interaction(session, player: Player, npc, event: MessageEvent, dialogue_content: str = None):
    """处理月老NPC交互"""
    from ..social.npc_matchmaker import handle_matchmaker_interaction as handle_matchmaker

    # 调用月老处理器,传递所有参数
    message = await handle_matchmaker(session, player, npc, event, dialogue_content or "")
    await interact_cmd.finish(message_add_head(message, event))


async def handle_sworn_envoy_interaction(session, player: Player, npc, event: MessageEvent, dialogue_content: str = None):
    """处理结义使者NPC交互"""
    from ..social.npc_sworn_envoy import handle_sworn_envoy_interaction as handle_sworn_envoy

    # 调用结义使者处理器,传递所有参数
    message = await handle_sworn_envoy(session, player, npc, event, dialogue_content or "")
    await interact_cmd.finish(message_add_head(message, event))


async def handle_mentor_envoy_interaction(session, player: Player, npc, event: MessageEvent, dialogue_content: str = None):
    """处理师徒使者NPC交互"""
    from ..social.npc_mentor import handle_mentor_interaction
    from ..utils_markdown import build_markdown

    # 调用师徒使者处理器,传递所有参数
    result = await handle_mentor_interaction(session, player, npc, event, dialogue_content or "")

    # 支持返回 (message, is_markdown) 元组
    if isinstance(result, tuple):
        message, is_markdown = result
        if is_markdown:
            await interact_cmd.finish(build_markdown(message))
        else:
            await interact_cmd.finish(message_add_head(message, event))
    else:
        await interact_cmd.finish(message_add_head(result, event))


async def handle_social_agent_interaction(session, player: Player, npc, event: MessageEvent, dialogue_content: str = None):
    """处理社交代理NPC交互 - 提供求婚/结义/拜师三合一服务"""
    from ..utils_markdown import cmd

    # 如果玩家指定了具体功能，直接路由
    if dialogue_content:
        content = dialogue_content.strip()
        if "婚" in content or "姻缘" in content or "求婚" in content:
            await handle_matchmaker_interaction(session, player, npc, event, dialogue_content)
            return
        elif "结义" in content or "义" in content or "兄弟" in content:
            await handle_sworn_envoy_interaction(session, player, npc, event, dialogue_content)
            return
        elif "师" in content or "拜师" in content or "收徒" in content or "香火" in content or "食谱" in content:
            await handle_mentor_envoy_interaction(session, player, npc, event, dialogue_content)
            return

    # 未指定功能，显示菜单
    lines = [
        f"🏛️ {npc.name}",
        "━━━━━━━━━━━━━",
        f"💬 「需要什么帮助？我可以代办以下事务。」",
        "",
        f"💕 {cmd('姻缘', f'交互 {npc.name} 姻缘')} — 求婚·结婚·离婚",
        f"🤝 {cmd('结义', f'交互 {npc.name} 结义')} — 结拜·断义",
        f"📖 {cmd('师徒', f'交互 {npc.name} 拜师')} — 拜师·收徒·香火商店·食谱",
        "━━━━━━━━━━━━━",
        "💡 点击上方按钮或输入【交互 " + npc.name + " 姻缘/结义/拜师】",
    ]
    from ..utils_markdown import build_markdown
    await interact_cmd.finish(build_markdown("\n".join(lines)))


async def handle_intelligence_dealer_interaction(session, player: Player, npc, event: MessageEvent):
    """处理情报贩子NPC交互 - 显示本集群物价对比和跑商建议"""
    from ..economy.merchants import MARKETS, CITY_CLUSTERS, CITY_TO_CLUSTER
    from ..economy.merchants import _price_for, LIMITED_GOODS
    from ..config import config as game_config

    location = npc.location
    if not location:
        await interact_cmd.finish("⛔ 情报贩子所在地点异常")

    city_name = location.name
    cluster_name = CITY_TO_CLUSTER.get(city_name, "未知")
    cluster_cities = CITY_CLUSTERS.get(cluster_name, [])

    # 收集本集群各城市的物价信息
    price_data = {}  # {city_name: {item_id: (sell_price, buy_price)}}

    for market in MARKETS:
        if market.name not in cluster_cities:
            continue
        city_prices = {}
        for item_id in market.sellable_items:
            if item_id not in LIMITED_GOODS:
                continue  # 只显示跑商商品
            try:
                sell_price, buy_price = await _price_for(session, market, item_id)
                city_prices[item_id] = (sell_price, buy_price)
            except ValueError:
                continue
        price_data[market.name] = city_prices

    # 寻找最佳跑商路线（本集群内）
    best_routes = []
    for src_name, src_prices in price_data.items():
        for dst_name, dst_prices in price_data.items():
            if src_name == dst_name:
                continue
            # 在src买、在dst卖
            for item_id, (sell_price, _) in src_prices.items():
                # 检查dst是否收购此商品
                dst_market = None
                for m in MARKETS:
                    if m.name == dst_name:
                        dst_market = m
                        break
                if not dst_market or not dst_market.can_buy_from_player(item_id):
                    continue
                try:
                    _, dst_buy_price = await _price_for(session, dst_market, item_id)
                except ValueError:
                    continue
                profit = dst_buy_price - sell_price
                if profit > 0:
                    item_cfg = game_config.items_config["by_id"].get(item_id)
                    item_name = item_cfg.name if item_cfg else item_id
                    profit_rate = round(profit / sell_price * 100)
                    best_routes.append((item_name, src_name, dst_name, sell_price, dst_buy_price, profit, profit_rate))

    # 按利润率排序，取前5
    best_routes.sort(key=lambda x: x[6], reverse=True)

    lines = [
        f"🕵️ {npc.name}",
        "━━━━━━━━━━━━━",
        f"💬 「嘘...{cluster_name}的行情，都在这了。」",
        "",
    ]

    if best_routes:
        lines.append(f"**📊 {cluster_name}今日跑商推荐：**")
        for item_name, src, dst, buy_p, sell_p, profit, rate in best_routes[:5]:
            lines.append(
                f"  💰 {item_name}: {src}买({buy_p}💎)→{dst}卖({sell_p}💎) 利润{profit}💎({rate}%)"
            )
    else:
        lines.append("💬 「今天行情不好，没什么赚头...」")

    # 本城物价概览
    if city_name in price_data and price_data[city_name]:
        lines.append("")
        lines.append(f"**🏪 {city_name}今日出售价：**")
        city_prices = price_data[city_name]
        for item_id, (sell_price, _) in sorted(city_prices.items(), key=lambda x: x[1][0], reverse=True)[:8]:
            item_cfg = game_config.items_config["by_id"].get(item_id)
            item_name = item_cfg.name if item_cfg else item_id
            lines.append(f"  {item_name}: {sell_price}💎")

    lines.append("━━━━━━━━━━━━━")
    lines.append("💡 价格每日09:00刷新")

    await interact_cmd.finish(message_add_head("\n".join(lines), event))


async def handle_station_master_interaction(session, player: Player, npc, event: MessageEvent):
    """处理驿丞NPC交互 - 显示本城信息、NPC列表、集群导航"""
    from ..economy.merchants import MARKETS, MARKET_BY_COORD, CITY_CLUSTERS, CITY_TO_CLUSTER
    from ..utils_markdown import cmd
    from sqlalchemy import select as sa_select

    # 获取NPC所在地点
    location = npc.location
    if not location:
        await interact_cmd.finish("⛔ 驿丞所在地点异常")

    city_name = location.name
    cluster_name = CITY_TO_CLUSTER.get(city_name, "未知")

    # 1. 本城NPC列表（直接查询）
    stmt = sa_select(NPC).where(NPC.location_id == location.id, NPC.is_active == True)
    result = await session.execute(stmt)
    local_npcs = result.scalars().all()

    npc_lines = []
    for local_npc in local_npcs:
        if local_npc.npc_id == npc.npc_id:
            continue  # 不显示驿丞自己
        if not local_npc.is_active:
            continue
        # 根据NPC类型显示图标
        icon = "👤"
        if local_npc.npc_type == NPCType.MERCHANT:
            icon = "🏪"
        elif local_npc.npc_type == NPCType.CRAFTSMAN:
            icon = "🔨"
        elif local_npc.npc_type == NPCType.EMPLOYER:
            icon = "💼"
        elif local_npc.npc_type == NPCType.SPECIAL_VENDOR:
            icon = "🎖️"
        elif local_npc.has_function("matchmaker"):
            icon = "💕"
        elif local_npc.has_function("sworn_ceremony"):
            icon = "🤝"
        elif local_npc.has_function("mentorship"):
            icon = "📖"
        elif local_npc.has_function("social_agent"):
            icon = "🏛️"
        elif local_npc.has_function("intelligence_dealer"):
            icon = "🕵️"
        npc_lines.append(f"  {icon} {cmd(local_npc.name, f'交互 {local_npc.name}')}")

    # 2. 集群内其他城市
    cluster_cities = CITY_CLUSTERS.get(cluster_name, [])
    player_x = player.real_world_x or 0
    player_y = player.real_world_y or 0

    cluster_lines = []
    for market in MARKETS:
        if market.name in cluster_cities and market.name != city_name:
            dist = abs(market.x - player_x) + abs(market.y - player_y)
            cluster_lines.append(
                f"  📍 {cmd(market.name, f'导航 {market.name}')} ({market.x},{market.y}) — {dist}格"
            )

    # 3. 最近的其他集群城市（取每个外集群最近的1个）
    other_cluster_lines = []
    cluster_nearest = {}
    for market in MARKETS:
        m_cluster = CITY_TO_CLUSTER.get(market.name, "")
        if m_cluster == cluster_name or m_cluster == "":
            continue
        dist = abs(market.x - player_x) + abs(market.y - player_y)
        if m_cluster not in cluster_nearest or dist < cluster_nearest[m_cluster][1]:
            cluster_nearest[m_cluster] = (market, dist)

    for c_name, (market, dist) in sorted(cluster_nearest.items(), key=lambda x: x[1][1]):
        other_cluster_lines.append(
            f"  🗺️ {c_name} → {cmd(market.name, f'导航 {market.name}')} ({dist}格)"
        )

    # 组装输出
    lines = [
        f"🏛️ {npc.name}",
        "━━━━━━━━━━━━━",
        f"📍 {city_name}（{cluster_name}）({location.x},{location.y})",
        "",
        f"**本城NPC：**",
    ]
    if npc_lines:
        lines.extend(npc_lines)
    else:
        lines.append("  （暂无其他NPC）")

    lines.append("")
    lines.append(f"**{cluster_name}集群城市：**")
    if cluster_lines:
        lines.extend(cluster_lines)
    else:
        lines.append("  （无其他城市）")

    if other_cluster_lines:
        lines.append("")
        lines.append("**最近的其他集群：**")
        lines.extend(other_cluster_lines)

    lines.append("━━━━━━━━━━━━━")
    lines.append(f"💡 输入【查找 NPC名】搜索全地图NPC")

    from ..utils_markdown import build_markdown
    await interact_cmd.finish(build_markdown("\n".join(lines)))


async def handle_generic_interaction(session, player: Player, npc, event: MessageEvent, dialogue_content: str = None):
    """处理普通NPC交互"""
    # 注意：AI对话检查已在 handle_npc_type_interaction 中统一处理

    # 检查是否是中立NPC（有特殊对话）
    if npc.extra_data and npc.extra_data.get("is_neutral") and npc.extra_data.get("dialogues"):
        await handle_neutral_npc_interaction(session, player, npc, event)
        return

    lines = [
        f"👤 {npc.name}",
        "━━━━━━━━━━━━━",
        f"💬 {npc.name}：{npc.description or '你好，有什么可以帮助你的吗？'}",
        "",
        "ℹ️ 这是一个普通的NPC，暂时没有特殊功能。"
    ]

    await interact_cmd.finish(message_add_head("\n".join(lines), event))


async def handle_neutral_npc_interaction(session, player: Player, npc, event: MessageEvent):
    """处理中立NPC交互，显示怪谈风格对话"""
    import random

    dialogues = npc.extra_data.get("dialogues", [])
    if not dialogues:
        await handle_generic_interaction(session, player, npc, event, dialogue_content=None)
        return

    # 随机选择一句对话，或者按顺序循环
    dialogue_index = npc.extra_data.get("dialogue_index", 0)

    # 30%概率随机选择，70%概率按顺序
    if random.random() < 0.3:
        selected_dialogue = random.choice(dialogues)
    else:
        selected_dialogue = dialogues[dialogue_index % len(dialogues)]
        # 更新对话索引
        npc.extra_data["dialogue_index"] = (dialogue_index + 1) % len(dialogues)

    # 根据NPC类型添加不同的氛围描述
    atmosphere_descriptions = [
        "周围的空气似乎变得阴冷...",
        "你感到一阵莫名的寒意...",
        "远处传来若有若无的叹息声...",
        "风中似乎夹杂着什么奇怪的味道...",
        "你觉得有什么东西在暗中观察着你...",
        "空气中弥漫着一股说不出的诡异感...",
        "你的心跳不由自主地加快了..."
    ]

    atmosphere = random.choice(atmosphere_descriptions)

    lines = [
        f"👤 {npc.name}",
        "━━━━━━━━━━━━━",
        f"🌫️ {atmosphere}",
        "",
        selected_dialogue,
        "",
        "━━━━━━━━━━━━━",
        "💭 这个NPC似乎知道一些不为人知的秘密...",
        "🔄 再次交互可能会听到不同的话语"
    ]

    await interact_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== NPC列表命令 ====================
npc_list_cmd = on_command("NPC列表", aliases={"npc列表", "查看NPC"}, block=True, priority=5)


@npc_list_cmd.handle()
async def handle_npc_list(event: MessageEvent):
    """显示当前位置的NPC列表"""
    from ..platform_utils import get_unified_player

    async with safe_session() as session:
        player: Player = await get_unified_player(session, event)
        if not player:
            await npc_list_cmd.finish("⛔ 请先创建角色")

        if player.is_in_dungeon():
            await npc_list_cmd.finish("⛔ 你在诡域中，无法查看现实世界的NPC")

        # 获取当前位置
        current_x, current_y = player.get_current_coordinates()
        current_region = player.get_current_region()

        # 查找当前位置的地点
        location = await LocationService.get_location_by_coordinates(
            session, current_x, current_y, current_region
        )

        if not location:
            await npc_list_cmd.finish("⛔ 当前位置没有NPC")

        # 获取地点的NPC
        npcs = await NPCService.get_npcs_by_location(session, location.id, include_dead=True)

        if not npcs:
            await npc_list_cmd.finish("⛔ 当前地点没有NPC")

        lines = [
            f"🤖 {location.name} - NPC列表",
            "━━━━━━━━━━━━━"
        ]

        # 按类型分组显示
        npcs_by_type = {}
        for npc in npcs:
            npc_type = npc.npc_type.value
            if npc_type not in npcs_by_type:
                npcs_by_type[npc_type] = []
            npcs_by_type[npc_type].append(npc)

        type_names = {
            "merchant": "🏪 商人",
            "craftsman": "⚒️ 工匠",
            "employer": "💼 雇主",
            "ghost": "👻 鬼怪",
            "special_vendor": "🏛️ 特殊商贩",
            "guard": "🛡️ 守卫",
            "normal": "👤 普通NPC"
        }

        for npc_type, type_npcs in npcs_by_type.items():
            type_name = type_names.get(npc_type, f"🔧 {npc_type}")
            lines.append(f"{type_name}：")

            for npc in type_npcs:
                status = ""
                if npc.is_dead():
                    status = " [已死亡]"
                elif npc.is_respawning():
                    remaining = npc.respawn_time - npc.death_time
                    minutes = int(remaining.total_seconds() / 60)
                    status = f" [复活中:{minutes}分钟]"

                hint = npc.get_interaction_hint()
                lines.append(f"• {npc.name}{status}{hint}")

            lines.append("")

        lines.extend([
            "━━━━━━━━━━━━━",
            "💡 使用【交互 <NPC名称>】与NPC交互"
        ])

        await npc_list_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== AI对话处理 ====================
async def handle_ai_dialogue_interaction(session, player: Player, npc, event: MessageEvent, question: str = None):
    """
    处理启用AI的NPC交互

    Args:
        session: 数据库会话
        player: 玩家对象
        npc: NPC对象
        event: 消息事件
        question: 玩家的问题/对话内容（可选，默认为打招呼）
    """
    import time
    import logging
    from ..dialogue.ai_dialogue_service import AIDialogueService
    from ..dialogue.npc_favorability_service import NPCFavorabilityService
    from ..dialogue.npc_personality import PersonalityManager
    from ..infrastructure.repositories.npc_dialogue_history_repository import NPCDialogueHistoryRepository
    from ..models.npc_dialogue_history import NPCDialogueHistory

    logger = logging.getLogger(__name__)

    start_time = time.time()

    try:
        # 初始化服务
        ai_service = AIDialogueService()
        fav_service = NPCFavorabilityService(session)
        history_repo = NPCDialogueHistoryRepository(session)

        # 获取NPC人设
        personality = PersonalityManager.get_personality(npc.name)
        if not personality:
            # 如果没有预设人设，使用默认配置
            from ..dialogue.npc_personality import PersonalityTemplate
            personality = PersonalityTemplate(
                name=npc.name,
                role=npc.description or "神秘的NPC",
                pronouns=["我"],
                speech_patterns=["友好"],
                key_words=[],
                background=npc.description or ""
            )

        # 获取或创建好感度记录
        favorability = await fav_service.get_favorability(
            npc_id=npc.id,
            player_id=player.id,
            initial_favorability=npc.extra_data.get("base_favorability", 50)
        )

        # 获取最近对话历史
        dialogue_history = await history_repo.get_recent_interactions(
            npc_id=npc.id,
            player_id=player.id,
            limit=10
        )

        # 分析玩家对话的情感
        sentiment = fav_service.analyze_dialogue_sentiment(question) if question else "neutral"

        # 获取长期记忆上下文
        from ..dialogue.dialogue_summarization_service import DialogueSummarizationService
        from ..infrastructure.repositories.npc_long_term_memory_repository import NPCLongTermMemoryRepository

        memory_repo = NPCLongTermMemoryRepository(session)
        summary_service = DialogueSummarizationService(memory_repo, history_repo)
        long_term_memory = await summary_service.get_long_term_context(
            npc_id=npc.id,
            player_id=player.id,
            include_summaries=3,  # 最近3次总结
            include_events=5  # 最近5个重要事件
        )

        # 构建上下文，包含情感分析结果和长期记忆
        current_x, current_y = player.get_current_coordinates()
        context = {
            "location_name": npc.location.name if npc.location else "未知地点",
            "player_name": player.nickname,
            "player_level": player.level,
            "coordinates": f"({current_x}, {current_y})",
            "player_sentiment": sentiment,  # 传递情感分析结果
            "sentiment_hint": {
                "very_negative": "玩家正在辱骂或攻击你，你应该表现出愤怒、委屈或拒绝交流",
                "negative": "玩家态度不友好，你应该表现出不高兴或疏远",
                "positive": "玩家态度友好，你应该表现出开心和亲切",
                "neutral": "玩家态度中立，正常交流即可"
            }.get(sentiment, ""),
            "long_term_memory": long_term_memory  # 传递长期记忆
        }

        # 生成AI对话（默认的自然对话场景）
        if not question:
            question = "你好"  # 默认问候

        await interact_cmd.send(message_add_head(f"🤖 {npc.name}正在思考...", event))

        npc_response, tokens_used = await ai_service.generate_dialogue(
            npc=npc,
            personality=personality,
            question=question,
            dialogue_history=dialogue_history,
            favorability=favorability.current_favorability,
            context=context
        )

        # 解析并处理NPC礼物
        from ..dialogue.npc_gift_service import parse_npc_gift, apply_npc_gift
        npc_response, gift_item_id, gift_qty, gift_name = parse_npc_gift(npc, player.id, npc_response)
        gift_given = False
        if gift_item_id:
            gift_given = await apply_npc_gift(session, npc, player, gift_item_id, gift_qty, gift_name)
            if gift_given:
                # 更新NPC赠礼成就统计
                from ..achievement.achievement_service import AchievementService
                await AchievementService.update_stat(session, player.id, "npc_gifts_received", auto_commit=False)

        # 根据对话内容更新好感度（使用之前分析的sentiment）
        fav_delta = fav_service.get_favorability_change_by_interaction_type(
            "dialogue",
            dialogue_content=question,  # 传入玩家的对话内容用于情感分析
            current_favorability=favorability.current_favorability  # 传入当前好感度以计算递减
        )

        # 记录情感分析结果（用于日志）
        logger.info(f"对话情感分析: '{question}' -> {sentiment} -> 好感度变化: {fav_delta:+d}")

        favorability = await fav_service.add_interaction(
            npc_id=npc.id,
            player_id=player.id,
            interaction_type="dialogue",
            favorability_delta=fav_delta,
            event_description=f"与{player.nickname}交谈 ({sentiment})"
        )

        # 保存对话历史
        dialogue_duration = int(time.time() - start_time)
        ai_cost = ai_service.calculate_cost(tokens_used)

        history = NPCDialogueHistory(
            npc_id=npc.id,
            player_id=player.id,
            dialogue_type="natural_dialogue",
            player_input=question,
            npc_response=npc_response,
            favorability_change=fav_delta,
            favorability_after=favorability.current_favorability,
            dialogue_duration_seconds=dialogue_duration,
            ai_tokens_used=tokens_used,
            ai_cost=ai_cost
        )
        await history_repo.save(history)
        await session.commit()

        # 异步触发对话总结（不阻塞用户交互）
        import asyncio
        from ..dialogue.dialogue_summarization_service import DialogueSummarizationService
        from ..infrastructure.repositories.npc_long_term_memory_repository import NPCLongTermMemoryRepository

        async def trigger_summary_async():
            """后台异步总结任务"""
            try:
                # 创建新的session用于后台任务
                from ..models.db import safe_session
                async with safe_session() as bg_session:
                    memory_repo = NPCLongTermMemoryRepository(bg_session)
                    bg_history_repo = NPCDialogueHistoryRepository(bg_session)
                    summary_service = DialogueSummarizationService(memory_repo, bg_history_repo)

                    # 检查并执行总结
                    await summary_service.summarize_dialogues(
                        npc_id=npc.id,
                        player_id=player.id,
                        npc_name=npc.name,
                        force=False  # 不强制，按阈值触发
                    )
                    await bg_session.commit()
                    logger.info(f"后台总结任务完成 - NPC: {npc.name}, 玩家: {player.id}")
            except Exception as e:
                logger.error(f"后台总结任务失败 - NPC: {npc.name}, 错误: {e}", exc_info=True)

        # 创建后台任务（不等待完成）
        asyncio.create_task(trigger_summary_async())


        # 格式化输出，包含对话历史
        lines = [
            f"💬 【{npc.name}】",
            "━━━━━━━━━━━━━",
        ]

        # 只显示上一条对话历史（如果有）
        if dialogue_history:
            last_dialogue = dialogue_history[-1]  # 只取最后一条
            # 截取部分内容避免太长
            player_text = last_dialogue.player_input[:30] + "..." if len(last_dialogue.player_input) > 30 else last_dialogue.player_input
            npc_text = last_dialogue.npc_response[:40] + "..." if len(last_dialogue.npc_response) > 40 else last_dialogue.npc_response
            lines.append("📜 上次对话：")
            lines.append(f"  【你】: {player_text}")
            lines.append(f"  【{npc.name}】: {npc_text}")
            lines.append("━━━━━━━━━━━━━")

        # 显示当前对话
        lines.append("🗨️ 当前对话：")
        lines.append(f"  【你】: {question}")
        lines.append(f"  【{npc.name}】: {npc_response}")
        if gift_given:
            lines.append(f"  🎁 {npc.name} 赠送了你 {gift_name}×{gift_qty}")
            # 检查NPC赠礼相关成就
            from ..achievement.achievement_service import AchievementService
            achievement_msgs = await AchievementService.check_achievements(session, player)
            if achievement_msgs:
                lines.extend([""] + achievement_msgs)
        lines.append("")

        # 显示好感度变化（带情感指示）
        if fav_delta > 0:
            change_icon = "📈"
            change_text = f"+{fav_delta}"
        elif fav_delta < 0:
            change_icon = "📉"
            change_text = str(fav_delta)
        else:
            change_icon = "➖"
            change_text = "±0"

        lines.append(f"❤️ 好感度: {favorability.current_favorability}/100 ({change_icon} {change_text})")
        lines.append(f"🔗 关系等级: {favorability.relationship_level}")
        lines.append(f"🔄 互动次数: {favorability.total_interactions}次")

        # 提示门槛突破信息
        thresholds = {
            20: ("熟识", "需要更多交流才能成为朋友"),
            40: ("友好", "需要赠送礼物或完成任务才能更进一步"),
            60: ("亲密", "需要共同战斗或完成重要任务才能建立亲密关系"),
            80: ("知心", "需要经历生死考验才能成为知心好友")
        }

        for threshold, (level_name, hint) in thresholds.items():
            # 如果好感度接近门槛（差2点以内）
            if threshold - 3 <= favorability.current_favorability < threshold:
                lines.append(f"💡 提示: 即将突破至【{level_name}】关系，{hint}")
                break

        # 如果好感度很高但变化很小
        if favorability.current_favorability >= 60 and abs(fav_delta) <= 1:
            if fav_delta == 0:
                lines.append("⚠️ 日常对话已无法增进关系，需要特殊互动")

        await interact_cmd.finish(message_add_head("\n".join(lines), event))

    except FinishedException:
        # FinishedException是正常的流程控制，直接抛出
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"AI对话处理失败: {type(e).__name__}: {str(e)}", exc_info=True)

        # 降级到普通对话
        lines = [
            f"👤 {npc.name}",
            "━━━━━━━━━━━━━",
            f"💬 {npc.name}：{npc.description or '你好，有什么可以帮助你的吗？'}",
            "",
            "⚠️ AI对话服务暂时不可用，使用预设对话。"
        ]
        await interact_cmd.finish(message_add_head("\n".join(lines), event))
