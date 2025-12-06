"""
NPC对话历史查看命令
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from .npc_service import NPCService


# ==================== 查看对话历史命令 ====================
dialogue_history_cmd = on_command("对话历史", aliases={"查看对话", "对话记录"}, block=True, priority=5)


@dialogue_history_cmd.handle()
async def handle_dialogue_history(event: MessageEvent, args: Message = CommandArg()):
    """查看与NPC的对话历史"""
    npc_name = args.extract_plain_text().strip()

    if not npc_name:
        await dialogue_history_cmd.finish(
            message_add_head(
                "请指定要查看对话历史的NPC名字\n"
                "格式: 【对话历史 NPC名字】\n"
                "例如: 【对话历史 武安勇】",
                event
            )
        )

    async with safe_session() as session:
        # 获取玩家
        player = await Player.get_player_by_uid(session, event.user_id)
        if not player:
            await dialogue_history_cmd.finish(message_add_head("你还没有创建角色！", event))

        # 查找NPC
        npc_service = NPCService(session)
        npc = await npc_service.get_npc_by_name(npc_name)

        if not npc:
            await dialogue_history_cmd.finish(message_add_head(f"找不到名叫「{npc_name}」的NPC！", event))

        # 获取对话历史
        from ..infrastructure.repositories.npc_dialogue_history_repository import NPCDialogueHistoryRepository
        history_repo = NPCDialogueHistoryRepository(session)
        dialogue_history = await history_repo.get_recent_interactions(
            npc_id=npc.id,
            player_id=player.id,
            limit=10  # 显示最近10条
        )

        if not dialogue_history:
            await dialogue_history_cmd.finish(message_add_head(f"你还没有与{npc.name}对话过。", event))

        # 格式化输出
        lines = [
            f"📖 与{npc.name}的对话历史",
            "━━━━━━━━━━━━━",
            f"显示最近{len(dialogue_history)}条记录：",
            ""
        ]

        for i, history in enumerate(dialogue_history, 1):
            # 格式化时间
            time_str = history.created_at.strftime("%m-%d %H:%M")
            lines.append(f"【{i}. {time_str}】")
            lines.append(f"  你: {history.player_input}")
            lines.append(f"  {npc.name}: {history.npc_response}")
            if history.favorability_change != 0:
                change_str = f"+{history.favorability_change}" if history.favorability_change > 0 else str(history.favorability_change)
                lines.append(f"  好感度: {change_str} → {history.favorability_after}/100")
            lines.append("")

        # 获取当前好感度
        from ..dialogue.npc_favorability_service import NPCFavorabilityService
        fav_service = NPCFavorabilityService(session)
        favorability = await fav_service.get_favorability(npc.id, player.id)

        lines.append("━━━━━━━━━━━━━")
        lines.append(f"当前好感度: {favorability.current_favorability}/100 ({favorability.relationship_level})")
        lines.append(f"总互动次数: {favorability.total_interactions}次")

        await dialogue_history_cmd.finish(message_add_head("\n".join(lines), event))