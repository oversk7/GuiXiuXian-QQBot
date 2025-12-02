"""
NPC交互命令

处理玩家与NPC的交互，包括商人交易、工匠锻造、雇主打工、鬼怪战斗等
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..models.db import safe_session
from ..models.player import Player
from ..models.npc import NPCType
from ..utils import message_add_head
from .location_service import LocationService
from .npc_service import NPCService

# 使用DI架构的NPCService和LocationService


# ==================== NPC交互命令 ====================
interact_cmd = on_command("交互", aliases={"对话", "找"}, block=True, priority=5)


@interact_cmd.handle()
async def handle_npc_interaction(event: MessageEvent, args: Message = CommandArg()):
    """处理NPC交互命令"""
    args_text = args.extract_plain_text().strip()

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
        npc = await npc_service.get_npc_by_name(args_text, location.id)
        if not npc:
            # 尝试智能匹配（支持带点号的名字）
            from .attack_command import find_npc_by_smart_match
            possible_npcs = await find_npc_by_smart_match(session, args_text, location.id)

            if not possible_npcs:
                await interact_cmd.finish(f"⛔ 在当前位置找不到名为'{args_text}'的NPC")
            elif len(possible_npcs) == 1:
                npc = possible_npcs[0]
            else:
                # 多个匹配结果，给出友好提示
                npc_list = []
                for n in possible_npcs[:5]:  # 最多显示5个
                    npc_list.append(f"• {n.name}")

                msg = (
                    f"🔍 找到多个匹配'{args_text}'的NPC：\n"
                    "━━━━━━━━━━━━━\n" +
                    "\n".join(npc_list) +
                    ("\n..." if len(possible_npcs) > 5 else "") +
                    "\n━━━━━━━━━━━━━\n"
                    "💡 请使用更具体的名称，如：\n"
                    f"• 【交互 {possible_npcs[0].name.split('·')[-1]}】\n"
                    f"• 【交互 {possible_npcs[0].name}】"
                )
                await interact_cmd.finish(message_add_head(msg, event))

        # 获取NPC交互信息
        interaction_info = await npc_service.get_npc_interaction_info(npc)
        if not interaction_info["can_interact"]:
            await interact_cmd.finish(f"⛔ {interaction_info['message']}")

        # 根据NPC类型处理交互
        await handle_npc_type_interaction(session, player, npc, interaction_info, event)


async def handle_npc_type_interaction(session, player: Player, npc, interaction_info: dict, event: MessageEvent):
    """根据NPC类型处理具体交互"""
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
    else:
        await handle_generic_interaction(session, player, npc, event)


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
        f"💀 {npc.name}发出阴森的笑声，散发着不祥的气息...",
        f"⚔️ 等级：{npc.level}",
        f"❤️ 血量：{npc.hp}/{npc.max_hp}",
        f"⚡ 攻击：{npc.attack}",
        f"🛡️ 防御：{npc.defense}",
        "",
        "⚔️ 可用操作：",
        "• 【攻击 {npc.name}】与鬼怪战斗",
        "",
        "⚠️ 警告：战斗可能造成伤亡，请谨慎行事！"
    ]

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


async def handle_generic_interaction(session, player: Player, npc, event: MessageEvent):
    """处理普通NPC交互"""
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
        await handle_generic_interaction(session, player, npc, event)
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
