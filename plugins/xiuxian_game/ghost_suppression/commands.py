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
ghost_invasions_cmd = on_command("入侵事件", aliases={"入侵列表"}, block=True, priority=5)

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
        
        # 检查是否已过18点（鬼怪入侵时间）
        if not DailyGhostRefresh.should_refresh_today():
            from datetime import datetime
            now = datetime.now()
            current_time_str = now.strftime("%H:%M")
            await suppress_ghost_cmd.finish(
                f"⛔ 鬼怪尚未入侵现实世界\n"
                f"🕐 当前时间: {current_time_str}\n"
                f"⏰ 请等待18:00后再尝试镇压"
            )

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
        
        # 第一阶段：威压判定
        prestige_result = await GhostSuppressionService.check_prestige_phase(
            session, player, invasion, use_coffin_nail
        )

        if not prestige_result["success"]:
            await suppress_ghost_cmd.finish(message_add_head(prestige_result["message"], event))

        # 发送第一阶段结果，增加仪式感
        await suppress_ghost_cmd.send(message_add_head(prestige_result["message"], event))

        # 第二阶段：战斗阶段
        battle_result = await GhostSuppressionService.execute_battle_phase(
            session, player, invasion
        )

        await session.commit()

        await suppress_ghost_cmd.finish(message_add_head(battle_result["message"], event))


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
                attrs = current_ghost.get_actual_attributes()
                msg_lines.append(f"🔥 当前驾驭: {ghost_display_name} Lv.{current_ghost.level}")
                msg_lines.append(f"   威压等级: {prestige_level} | HP: {attrs['hp']} | 攻击: {attrs['attack']}")
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
                    attrs = ghost.get_actual_attributes()
                    msg_lines.append(f"{status} {i}. {ghost_display_name} Lv.{ghost.level}")
                    msg_lines.append(f"      HP: {attrs['hp']} | 攻击: {attrs['attack']} | 防御: {attrs['defense']}")
            
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


# ==================== 升级鬼怪 ====================
upgrade_ghost_cmd = on_command("升级鬼怪", aliases={"鬼怪升级", "升级"}, block=True, priority=5)

@upgrade_ghost_cmd.handle()
async def handle_upgrade_ghost(event: MessageEvent, args: Message = CommandArg()):
    ghost_name = args.extract_plain_text().strip()

    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await upgrade_ghost_cmd.finish("⛔ 请先创建角色")

        if not ghost_name:
            # 显示可升级的鬼怪列表
            all_ghosts = await GhostSuppressionService.get_player_ghosts(session, player.id)

            if not all_ghosts:
                await upgrade_ghost_cmd.finish("⛔ 你还没有任何鬼怪")

            msg_lines = ["👻 鬼怪升级列表"]
            msg_lines.append("━━━━━━━━━━━━━")
            msg_lines.append(f"💀 当前怨念值: {player.resentment}")
            msg_lines.append("")

            for i, ghost in enumerate(all_ghosts, 1):
                ghost_config = config.ghosts_config["by_id"].get(ghost.ghost_id, {})
                ghost_display_name = ghost_config.get("name", ghost.ghost_id)
                upgrade_cost = ghost.get_upgrade_cost()
                can_upgrade = ghost.can_upgrade(player.resentment)
                status = "✅" if can_upgrade else "❌"

                msg_lines.append(f"{status} {i}. {ghost_display_name} Lv.{ghost.level}")
                msg_lines.append(f"   升级消耗: {upgrade_cost} 怨念值")

                # 显示属性提升预览
                current_attrs = ghost.get_actual_attributes()
                next_level_attrs = ghost_config and config.ghosts_config["by_id"][ghost.ghost_id]
                if next_level_attrs:
                    from .ghost_utils import GhostUtils
                    next_attrs = GhostUtils.calculate_ghost_attributes(ghost_config, ghost.level + 1)
                    hp_gain = next_attrs["hp"] - current_attrs["hp"]
                    attack_gain = next_attrs["attack"] - current_attrs["attack"]
                    msg_lines.append(f"   属性提升: HP+{hp_gain}, 攻击+{attack_gain}")
                msg_lines.append("")

            msg_lines.append("━━━━━━━━━━━━━")
            msg_lines.append("💡 使用 【升级鬼怪 鬼怪名称】 来升级指定鬼怪")

            await upgrade_ghost_cmd.finish(message_add_head("\n".join(msg_lines), event))

        # 查找指定名称的鬼怪
        target_ghost = None
        all_ghosts = await GhostSuppressionService.get_player_ghosts(session, player.id)

        for ghost in all_ghosts:
            ghost_config = config.ghosts_config["by_id"].get(ghost.ghost_id, {})
            if ghost_config.get("name") == ghost_name or ghost.ghost_id == ghost_name:
                target_ghost = ghost
                break

        if not target_ghost:
            await upgrade_ghost_cmd.finish(f"⛔ 你没有名为 {ghost_name} 的鬼怪")

        # 检查是否可以升级
        if not target_ghost.can_upgrade(player.resentment):
            upgrade_cost = target_ghost.get_upgrade_cost()
            await upgrade_ghost_cmd.finish(
                f"⛔ 怨念值不足！需要 {upgrade_cost}，当前拥有 {player.resentment}"
            )

        # 执行升级
        upgrade_cost = target_ghost.upgrade()
        player.resentment -= upgrade_cost

        session.add(target_ghost)
        session.add(player)
        await session.commit()

        ghost_config = config.ghosts_config["by_id"].get(target_ghost.ghost_id, {})
        ghost_display_name = ghost_config.get("name", target_ghost.ghost_id)
        new_attrs = target_ghost.get_actual_attributes()

        msg = (
            f"🎉 升级成功！\n"
            f"👻 {ghost_display_name} 升级到 Lv.{target_ghost.level}\n"
            f"💀 消耗怨念值: {upgrade_cost}\n"
            f"⚡ 当前属性: HP {new_attrs['hp']}, 攻击 {new_attrs['attack']}, 防御 {new_attrs['defense']}, 敏捷 {new_attrs['agility']}\n"
            f"💀 剩余怨念值: {player.resentment}"
        )

        await upgrade_ghost_cmd.finish(message_add_head(msg, event))
