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
interact_cmd = on_command("交互", aliases={"对话", "找"}, block=True, priority=5)


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
