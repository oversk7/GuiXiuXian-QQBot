from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime
from ..models.db import safe_session
from ..models.quest import Quest, PlayerQuest
from ..models.player import Player
from ..models.inventory import Inventory

async def check_quest_progress(player_id: str, condition_type: str, value: int = 1):
    """通用任务进度检查"""
    async with safe_session() as session:
        # 获取玩家所有未完成任务（使用selectinload预加载quest关系）
        player_quests = await session.execute(
            select(PlayerQuest)
            .options(selectinload(PlayerQuest.quest))  # 添加预加载
            .join(Quest)
            .where(PlayerQuest.player_id == player_id)
            .where(PlayerQuest.is_completed == False)
            .where(Quest.condition_type == condition_type)
        )
        
        for pq in player_quests.scalars():
            # 不同类型任务的条件检查
            if pq.quest.condition_type == "CULTIVATE":
                pq.progress += value
            elif pq.quest.condition_type == "KILL_MONSTER":
                if pq.quest.condition_params["monster"] == value:
                    pq.progress += 1
            
            # 检查是否完成
            if pq.progress >= pq.quest.condition_params.get("required", 1):
                await complete_quest(session, pq)
            await session.commit()

async def complete_quest(session, player_quest: PlayerQuest):
    """完成任务并发放奖励"""
    # 通过预加载的关系直接访问，无需额外查询
    quest = player_quest.quest
    
    # 发放奖励
    player = await session.get(Player, player_quest.player_id)
    player.gold += quest.rewards.get("gold", 0)
    player.exp += quest.rewards.get("exp", 0)
    
    # 添加物品奖励
    for item_id, quantity in quest.rewards.get("items", []):
        inv = await session.execute(
            select(Inventory)
            .where(Inventory.player_id == player.id)
            .where(Inventory.item_id == item_id)
        )
        if inv := inv.scalars().first():
            inv.quantity += quantity
        else:
            session.add(Inventory(
                player_id=player.id,
                item_id=item_id,
                quantity=quantity
            ))
    
    player_quest.is_completed = True
    player_quest.completed_at = datetime.now()

async def check_daily_quests(player_id: str):
    """每日任务自动接取"""
    async with safe_session() as session:
        # 获取所有每日类型任务
        daily_quests = (await session.execute(
            select(Quest).where(Quest.quest_type == "DAILY")
        )).scalars().all()
        
        # 检查玩家是否已有该任务
        for quest in daily_quests:
            exists = await session.execute(
                select(PlayerQuest)
                .where(PlayerQuest.player_id == player_id)
                .where(PlayerQuest.quest_id == quest.id)
            )
            if not exists.scalars().first():
                session.add(PlayerQuest(
                    player_id=player_id,
                    quest_id=quest.id,
                    progress=0
                ))
        await session.commit() 