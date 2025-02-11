from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from nonebot.params import CommandArg
from ..data.db import safe_session
from ..models.player import Player
from .core import BattleInstance, generate_enemy_by_region, send_battle_ui

explore_cmd = on_command("探索", block=True, priority=5)

@explore_cmd.handle()
async def handle_explore(event: MessageEvent, args: Message = CommandArg()):
    region_name = args.extract_plain_text().strip()
    user_id = event.get_user_id()
    
    async with safe_session() as session:
        player = await session.get(Player, user_id)
        if not player:
            await explore_cmd.finish("⛔ 请先创建角色")
            
        try:
            enemies = await generate_enemy_by_region(region_name, player.level)
            battle = BattleInstance(BattleType.SOLO, [player], enemies, event)
            await send_battle_ui(battle, event)
            
            # 更新玩家位置
            player.position = region_name
            session.add(player)
            await session.commit()
            
        except ValueError as e:
            await explore_cmd.finish(str(e)) 