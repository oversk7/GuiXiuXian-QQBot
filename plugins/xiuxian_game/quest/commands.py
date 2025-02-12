from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from ..data.db import safe_session
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from ..models.quest import PlayerQuest, Quest
from ..utils import create_rich_message
from ..config import config

quest_cmd = on_command("任务", block=True, priority=5)

@quest_cmd.handle()
async def show_quests(event: MessageEvent):
    async with safe_session() as session:
        # 使用selectinload预加载quest关系
        player_quests = await session.execute(
            select(PlayerQuest)
            .options(selectinload(PlayerQuest.quest))
            .join(Quest)
            .where(PlayerQuest.player_id == event.get_user_id())
            .order_by(Quest.quest_type)
        )
        
        msg = ["📜 当前任务"]
        for pq in player_quests.scalars():
            status = "✅" if pq.is_completed else f"{pq.progress}/{pq.quest.condition_params.get('required', 1)}"
            # 美化奖励显示
            rewards = []
            if "gold" in pq.quest.rewards:
                rewards.append(f"💰{pq.quest.rewards['gold']}金币")
            if "exp" in pq.quest.rewards:
                rewards.append(f"✨{pq.quest.rewards['exp']}经验")
            if "items" in pq.quest.rewards:
                items = [f"{config.items_config['by_id'][item_id].name}×{qty}" 
                        for item_id, qty in pq.quest.rewards["items"]]
                rewards.append("🎁" + "、".join(items))
            
            msg.append(
                f"🔹 {pq.quest.title} ({pq.quest.quest_type})\n"
                f"▫️ 进度：{status}\n"
                f"▫️ 奖励：{' '.join(rewards)}"
            )
        
        await quest_cmd.finish(create_rich_message("\n".join(msg), event)) 