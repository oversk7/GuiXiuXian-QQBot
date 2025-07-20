"""鬼怪镇压系统指令处理"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select, and_

from ..models.db import safe_session
from ..models.player import Player
from ..models.ghost_invasion import GhostInvasion
from ..models.player_ghost import PlayerGhost
from ..models.inventory import ItemInstance
from ..utils import message_add_head
from ..config import config
from .service import GhostSuppressionService
from .daily_refresh import DailyGhostRefresh


# ==================== 查看鬼怪入侵 ====================
ghost_invasions_cmd = on_command("鬼怪入侵", aliases={"入侵列表", "鬼怪列表"}, block=True, priority=5)

@ghost_invasions_cmd.handle()
async def handle_ghost_invasions(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await ghost_invasions_cmd.finish("⛔ 请先创建角色")
        
        # 确保今日已刷新
        await DailyGhostRefresh.refresh_daily_invasions(session)
        
        # 获取入侵摘要
        summary = await DailyGhostRefresh.get_invasion_summary(session)
        
        await ghost_invasions_cmd.finish(message_add_head(summary, event))


# ==================== 镇压鬼怪 ====================
suppress_ghost_cmd = on_command("镇压", aliases={"镇压鬼怪"}, block=True, priority=5)

@suppress_ghost_cmd.handle()
async def handle_suppress_ghost(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    use_coffin_nail = "棺材钉" in arg_text
    
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await suppress_ghost_cmd.finish("⛔ 请先创建角色")
        
        # 检查当前位置是否有鬼怪入侵
        invasion = await GhostSuppressionService.get_invasion_at_location(
            session, player.region, player.x, player.y
        )
        
        if not invasion:
            await suppress_ghost_cmd.finish("⛔ 当前位置没有鬼怪入侵事件")
        
        # 如果使用棺材钉，检查并消耗
        if use_coffin_nail:
            result = await session.execute(
                select(ItemInstance).where(
                    and_(
                        ItemInstance.player_id == player.id,
                        ItemInstance.item_id == "coffin_nail",
                        ItemInstance.quantity > 0
                    )
                )
            )
            coffin_nail_item = result.scalars().first()
            
            if not coffin_nail_item:
                await suppress_ghost_cmd.finish("⛔ 你没有棺材钉，无法强制压制灵异规则")
            
            # 消耗棺材钉
            coffin_nail_item.quantity -= 1
            if coffin_nail_item.quantity <= 0:
                await session.delete(coffin_nail_item)
            else:
                session.add(coffin_nail_item)
        
        # 尝试镇压
        success, description, drops = await GhostSuppressionService.attempt_suppression(
            session, player, invasion, use_coffin_nail
        )
        
        await session.commit()
        
        await suppress_ghost_cmd.finish(message_add_head(description, event))


# ==================== 驾驭鬼怪 ====================
control_ghost_cmd = on_command("驾驭", aliases={"驾驭鬼怪", "切换鬼怪"}, block=True, priority=5)

@control_ghost_cmd.handle()
async def handle_control_ghost(event: MessageEvent, args: Message = CommandArg()):
    ghost_name = args.extract_plain_text().strip()
    
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await control_ghost_cmd.finish("⛔ 请先创建角色")
        
        if not ghost_name:
            # 显示当前驾驭的鬼怪和可用列表
            current_ghost = await GhostSuppressionService.get_player_active_ghost(session, player.id)
            all_ghosts = await GhostSuppressionService.get_player_ghosts(session, player.id)
            
            msg_lines = ["👻 鬼怪驾驭状态"]
            msg_lines.append("━━━━━━━━━━━━━")
            
            if current_ghost:
                ghost_config = config.ghosts_config["by_id"].get(current_ghost.ghost_id, {})
                ghost_display_name = ghost_config.get("name", current_ghost.ghost_id)
                prestige_level = GhostSuppressionService.calculate_prestige_level(ghost_config, player)
                msg_lines.append(f"🔥 当前驾驭: {ghost_display_name} (威压等级: {prestige_level})")
            else:
                msg_lines.append("🔥 当前驾驭: 无")
            
            msg_lines.append("")
            msg_lines.append("📋 可驾驭鬼怪:")
            
            if not all_ghosts:
                msg_lines.append("暂无可驾驭的鬼怪")
            else:
                for i, ghost in enumerate(all_ghosts, 1):
                    ghost_config = config.ghosts_config["by_id"].get(ghost.ghost_id, {})
                    ghost_display_name = ghost_config.get("name", ghost.ghost_id)
                    status = "✅" if ghost.is_active else "⭕"
                    msg_lines.append(f"{status} {i}. {ghost_display_name}")
            
            msg_lines.append("━━━━━━━━━━━━━")
            msg_lines.append("💡 使用 【驾驭 鬼怪名称】 来切换驾驭的鬼怪")
            
            await control_ghost_cmd.finish(message_add_head("\n".join(msg_lines), event))
        
        # 查找指定名称的鬼怪
        target_ghost = None
        all_ghosts = await GhostSuppressionService.get_player_ghosts(session, player.id)
        
        for ghost in all_ghosts:
            ghost_config = config.ghosts_config["by_id"].get(ghost.ghost_id, {})
            if ghost_config.get("name") == ghost_name or ghost.ghost_id == ghost_name:
                target_ghost = ghost
                break
        
        if not target_ghost:
            await control_ghost_cmd.finish(f"⛔ 你没有名为 {ghost_name} 的鬼怪")
        
        # 取消所有鬼怪的激活状态
        for ghost in all_ghosts:
            ghost.deactivate()
            session.add(ghost)
        
        # 激活目标鬼怪
        target_ghost.activate()
        session.add(target_ghost)
        
        await session.commit()
        
        ghost_config = config.ghosts_config["by_id"].get(target_ghost.ghost_id, {})
        ghost_display_name = ghost_config.get("name", target_ghost.ghost_id)
        prestige_level = GhostSuppressionService.calculate_prestige_level(ghost_config, player)
        
        msg = (
            f"👻 驾驭成功！\n"
            f"🔥 当前驾驭: {ghost_display_name}\n"
            f"⚡ 威压等级: {prestige_level}\n"
            f"💡 现在可以使用这只鬼怪进行镇压了"
        )
        
        await control_ghost_cmd.finish(message_add_head(msg, event))


# ==================== 合成鬼怪 ====================
craft_ghost_cmd = on_command("合成鬼怪", aliases={"合成", "鬼怪合成"}, block=True, priority=5)

@craft_ghost_cmd.handle()
async def handle_craft_ghost(event: MessageEvent, args: Message = CommandArg()):
    ghost_name = args.extract_plain_text().strip()
    
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await craft_ghost_cmd.finish("⛔ 请先创建角色")
        
        if not ghost_name:
            # 显示可合成的鬼怪列表
            msg_lines = ["🔮 鬼怪合成列表"]
            msg_lines.append("━━━━━━━━━━━━━")
            
            for ghost_config in config.ghosts_config["all"]:
                fragment_id = ghost_config["fragment_item_id"]
                required_count = ghost_config["fragments_to_complete"]
                
                # 检查玩家拥有的碎片数量
                result = await session.execute(
                    select(ItemInstance).where(
                        and_(
                            ItemInstance.player_id == player.id,
                            ItemInstance.item_id == fragment_id
                        )
                    )
                )
                fragment_item = result.scalars().first()
                current_count = fragment_item.quantity if fragment_item else 0
                
                status = "✅" if current_count >= required_count else "❌"
                msg_lines.append(
                    f"{status} {ghost_config['name']}: {current_count}/{required_count} 碎片"
                )
            
            msg_lines.append("━━━━━━━━━━━━━")
            msg_lines.append("💡 使用 【合成鬼怪 鬼怪名称】 来合成指定鬼怪")
            
            await craft_ghost_cmd.finish(message_add_head("\n".join(msg_lines), event))
        
        # 查找指定鬼怪配置
        target_config = None
        for ghost_config in config.ghosts_config["all"]:
            if ghost_config["name"] == ghost_name or ghost_config["ghost_id"] == ghost_name:
                target_config = ghost_config
                break
        
        if not target_config:
            await craft_ghost_cmd.finish(f"⛔ 不存在名为 {ghost_name} 的鬼怪")
        
        # 检查碎片数量
        fragment_id = target_config["fragment_item_id"]
        required_count = target_config["fragments_to_complete"]
        
        result = await session.execute(
            select(ItemInstance).where(
                and_(
                    ItemInstance.player_id == player.id,
                    ItemInstance.item_id == fragment_id
                )
            )
        )
        fragment_item = result.scalars().first()
        current_count = fragment_item.quantity if fragment_item else 0
        
        if current_count < required_count:
            await craft_ghost_cmd.finish(
                f"⛔ 碎片不足！需要 {required_count} 个，当前拥有 {current_count} 个"
            )
        
        # 检查是否已经拥有该鬼怪
        result = await session.execute(
            select(PlayerGhost).where(
                and_(
                    PlayerGhost.player_id == player.id,
                    PlayerGhost.ghost_id == target_config["ghost_id"]
                )
            )
        )
        existing_ghost = result.scalars().first()
        
        if existing_ghost:
            await craft_ghost_cmd.finish(f"⛔ 你已经拥有 {ghost_name} 了")
        
        # 消耗碎片
        fragment_item.quantity -= required_count
        if fragment_item.quantity <= 0:
            await session.delete(fragment_item)
        else:
            session.add(fragment_item)
        
        # 创建鬼怪
        new_ghost = PlayerGhost(
            player_id=player.id,
            ghost_id=target_config["ghost_id"]
        )
        session.add(new_ghost)
        
        await session.commit()
        
        msg = (
            f"🎉 合成成功！\n"
            f"👻 获得鬼怪: {target_config['name']}\n"
            f"💎 消耗碎片: {required_count} 个\n"
            f"💡 使用 【驾驭 {target_config['name']}】 来驾驭这只鬼怪"
        )
        
        await craft_ghost_cmd.finish(message_add_head(msg, event))
