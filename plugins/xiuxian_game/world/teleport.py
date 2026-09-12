"""
传送系统模块

处理玩家在现实世界和诡域之间的传送功能
支持无限层诡域爬塔系统
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..models.db import safe_session
from ..models.player import Player
from ..models.navigation_task import NavigationTask
from ..config import config
from ..utils import message_add_head
from ..utils_markdown import build_markdown
from .navigation import format_navigation_interruption
from .navigation_events import format_navigation_events
from ..platform_utils import require_player
from sqlalchemy import select


# 传送指令
teleport_cmd = on_command("传送", block=True, priority=5)
enter_cmd = on_command("进入", block=True, priority=5)
revive_cmd = on_command("返回", aliases={"复活"}, block=True, priority=5)
# 层级切换指令
prev_level_cmd = on_command("上一层", aliases={"上层"}, block=True, priority=5)
next_level_cmd = on_command("下一层", aliases={"下层"}, block=True, priority=5)
rest_cmd = on_command("休息", block=True, priority=5)


async def get_tile_description(session, player: Player, region: str, x: int, y: int) -> str:
    """获取指定位置格子的描述信息（文案单一来源见 dungeon_battle_service.describe_tile）"""
    from .dungeon_generation_service import get_or_create_tile
    from .dungeon_battle_service import describe_tile
    tile = await get_or_create_tile(session, region, x, y, player.server_id)
    return describe_tile(tile, player)


@teleport_cmd.handle()
async def handle_teleport(event: MessageEvent, args: Message = CommandArg()):
    """处理传送指令，支持进入层级制诡域"""
    target_region = args.extract_plain_text().strip()
    if not target_region:
        await teleport_cmd.finish("⛔ 请指定目标，例如：传送 1层诡域 或 传送 第1层诡域")

    # 调用共同的传送处理函数
    await _handle_teleport_logic(event, target_region, teleport_cmd)


@enter_cmd.handle()
async def handle_enter(event: MessageEvent, args: Message = CommandArg()):
    """处理进入指令，支持进入层级制诡域"""
    target_region = args.extract_plain_text().strip()
    if not target_region:
        await enter_cmd.finish("⛔ 请指定目标，例如：进入 1层诡域 或 进入 第1层诡域")

    # 调用共同的传送处理函数
    await _handle_teleport_logic(event, target_region, enter_cmd)


async def _handle_teleport_logic(event: MessageEvent, target_region: str, cmd_handler):
    """共同的传送处理逻辑"""
    # 兼容"鬼域"别名（玩家常见笔误）
    target_region = target_region.replace("鬼域", "诡域")

    # 检查是否为层级诡域格式
    if target_region.endswith("层诡域"):
        try:
            level_str = target_region.replace("层诡域", "")
            # 兼容"第N层诡域"格式，移除开头的"第"字
            if level_str.startswith("第"):
                level_str = level_str[1:]
            dungeon_level = int(level_str)
        except ValueError:
            await cmd_handler.finish("⛔ 诡域层级格式错误，请使用：1层诡域 或 第1层诡域")

        # 验证层级范围
        if dungeon_level <= 0:
            await cmd_handler.finish("⛔ 诡域层级必须大于0")
        
        # 动态生成层级配置（支持无限层）
        dungeon_config = config._generate_dungeon_level_config(
            dungeon_level, 
            config.map_config.get("dungeon_generation_rules", {})
        )
    else:
        # 兼容旧的命名诡域（如果还有的话）
        valid_regions = list(config.map_config.get("regions", {}).keys())
        if target_region not in valid_regions:
            await cmd_handler.finish("⛔ 目的地不存在，请使用：N层诡域")
        dungeon_level = None
        dungeon_config = config.map_config["regions"].get(target_region)

    STAM_COST = 1  # 咒抗消耗

    async with safe_session() as session:
        player = await require_player(session, event, cmd_handler)

        # 判断是否已在诡域中（诡域内跳转免咒抗）
        already_in_dungeon = player.is_in_dungeon()

        # 检查层级解锁限制（爬塔系统）
        if dungeon_level:
            # 已在诡域中且目标层就是当前层，提示无需跳转
            if already_in_dungeon and player.dungeon_level == dungeon_level:
                await cmd_handler.finish(f"📍 你已经在第{dungeon_level}重诡域了")

            if not player.can_enter_dungeon_level(dungeon_level):
                max_level = player.max_dungeon_level or 0
                await cmd_handler.finish(
                    f"⛔ 无法进入第{dungeon_level}重诡域！\n"
                    f"━━━━━━━━━━━━━\n"
                    f"📊 当前最深探索：第{max_level}重诡域\n"
                    f"━━━━━━━━━━━━━\n"
                    f"💡 需要逐重击败诡异解锁更深的诡域\n"
                    f"⬇️ 【进入 {max_level + 1}层诡域】探索下一重空间"
                )
        else:
            # 兼容旧系统的等级检查
            if dungeon_config:
                required_level = dungeon_config.get("required_level", 1)
                if player.level < required_level:
                    await cmd_handler.finish(f"⛔ 你的修为不足以进入『{target_region}』，需要达到 Lv.{required_level}")

        nav_task = None
        went_mad = False
        if already_in_dungeon and dungeon_level:
            # 已在诡域中跳转到其他层级：免咒抗，但消耗目标层理智
            _tele_cfg = config.map_config.get("dungeon_levels", {}).get(dungeon_level)
            if not _tele_cfg:
                _tele_cfg = config._generate_dungeon_level_config(
                    dungeon_level, config.map_config.get("dungeon_generation_rules", {})
                )
            _mp_cost = _tele_cfg.get("mp_cost", 1)
            if player.mp < _mp_cost:
                await cmd_handler.finish(
                    f"⛔ 理智不足以穿越空间裂隙！需要 {_mp_cost} 点理智，当前 {player.mp}"
                )
            player.mp = max(0, player.mp - _mp_cost)
            if player.mp == 0 and player.hp > 0:
                player.hp = 0  # 理智耗尽即"疯狂身亡"
                player.dungeon_kill_streak = 0
                went_mad = True
        else:
            # 从现实世界进入诡域：消耗咒抗
            if player.stamina < STAM_COST:
                await cmd_handler.finish(f"⛔ 你的咒抗不足以在传送过程中维持清醒，需要 {STAM_COST}，当前 {player.stamina}")
            if player.hp < 5:
                await cmd_handler.finish(f"⛔ 你的生命值过低：当前 {player.hp}/{player.max_hp}")

            # 查询是否存在导航任务
            nav_task = await session.get(NavigationTask, player.id)

            # 在进入诡域前，若存在导航，则推进至当前时间（作用于现实世界坐标）
            if nav_task:
                from ..world.navigation import _update_nav_position
                update = await _update_nav_position(player, nav_task, session)
                if update.interrupted:
                    await session.commit()
                    await cmd_handler.finish(build_markdown(format_navigation_interruption(player, update)))
                if update.events:
                    await session.commit()
                    await cmd_handler.send(build_markdown(format_navigation_events(update.events)))
                # 不删除任务，保留以便返回后继续/完成

            # 扣除咒抗
            player.stamina -= STAM_COST

        # 使用新的双层坐标系统
        if dungeon_level:
            current_level_before = player.dungeon_level if already_in_dungeon else None
            # 进入层级诡域（enter_dungeon 会保存当前现实世界坐标至 real_world_x/y）
            player.enter_dungeon(dungeon_level)
            target_name = f"{dungeon_level}层诡域"
            current_pos = f"({player.dungeon_x},{player.dungeon_y})"
        else:
            current_level_before = None
            # 兼容旧系统
            player.region = target_region
            target_name = target_region
            current_pos = f"({player.x},{player.y})"

        session.add(player)
        await session.commit()

        # 新手任务钩子
        from ..quest.novice_quest_service import NoviceQuestService
        quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(
            session, player, "command", {"command": "传送"}
        )

        # 获取当前位置格子描述，并检查月卡自动采集
        tile_desc = None
        auto_collect_msg = ""
        sense_msg = None
        if dungeon_level:
            from .dungeon_generation_service import get_or_create_tile, sense_level_elites
            from .dungeon_battle_service import _handle_material, _handle_treasure
            from ..models.monthly_card import get_player_card_benefits

            if not went_mad:
                sense_msg = await sense_level_elites(session, dungeon_level, player.server_id, player.id)

            tile = await get_or_create_tile(session, target_name, player.dungeon_x, player.dungeon_y, player.server_id)
            benefits = await get_player_card_benefits(session, player.id)
            if benefits.get("auto_collect", False):
                if tile.event_type == "MATERIAL":
                    if player.id not in tile.state.get("looted_by", []) and not tile.state.get("looted"):
                        collect_result = await _handle_material(session, tile, player)
                        auto_collect_msg = f"\n💳 月卡自动采集：\n{collect_result}"
                elif tile.event_type == "TREASURE":
                    if not tile.state.get("looted"):
                        collect_result = await _handle_treasure(session, tile, player)
                        auto_collect_msg = f"\n💳 月卡自动收集：\n{collect_result}"

            tile_desc = await get_tile_description(session, player, target_name, player.dungeon_x, player.dungeon_y)

    # 构建响应消息
    if already_in_dungeon and dungeon_level:
        # 诡域内跳转：不同的提示文案
        msg_lines = [
            f"🌀 你穿越空间裂隙，从第{current_level_before}重诡域跳转到第{dungeon_level}重诡域（消耗理智 {_mp_cost}）",
            f"📍 当前位置：{target_name} {current_pos}",
        ]
    else:
        msg_lines = [
            f"🚪 你耗费 {STAM_COST} 咒抗跨越裂隙，抵达『{target_name}』",
            f"当前位置：{target_name} {current_pos}",
        ]
        if nav_task:
            msg_lines.insert(1, "🧭 现实世界导航仍在静默进行中")

    if dungeon_level:
        from .dungeon_battle_service import get_tier_theme
        theme_name, theme_line = get_tier_theme(dungeon_level)
        msg_lines.append("━━━━━━━━━━━━━")
        msg_lines.append(f"🩸 『{theme_name}』——{theme_line}")
        if sense_msg:
            msg_lines.append(sense_msg)
        if went_mad:
            msg_lines.append("💀 理智在穿越途中耗尽，你在无人的黑暗里笑出了声——疯狂身亡")
            msg_lines.append("⬇️ 【返回】回到现实 | 【使用 还魂丹】原地复活")

        # 添加当前位置格子描述
        if tile_desc:
            msg_lines.append("━━━━━━━━━━━━━")
            msg_lines.append(tile_desc)
        if auto_collect_msg:
            msg_lines.append(auto_collect_msg)
        msg_lines.append("🧭 【上下左右】移动 | 【探索】调查当前格")
        msg_lines.append("⬆️【上一层】 ⬇️【下一层】 🚀【传送 N层诡域】 🏠【返回】")

        # 检查是否有可领取的深渊探索者宝箱
        if dungeon_level % 10 == 0:
            from ..models.dungeon_chest_record import DungeonChestRecord
            from sqlalchemy import select

            stmt = select(DungeonChestRecord).where(
                DungeonChestRecord.player_id == player.id,
                DungeonChestRecord.dungeon_level == dungeon_level
            )
            existing_record = (await session.execute(stmt)).scalar_one_or_none()

            if not existing_record:
                msg_lines.append("━━━━━━━━━━━━━")
                msg_lines.append("🎁 征服这层就可以再领取一个探索者宝箱了！")
                msg_lines.append("💎 【领取宝箱】一键领取所有可领取的宝箱")

    if quest_completed and quest_msg:
        msg_lines.append("")
        msg_lines.append(quest_msg)

    msg = "\n".join(msg_lines)
    await cmd_handler.finish(build_markdown(f"『诡修仙』\n{msg}"))


@revive_cmd.handle()
async def handle_revive(event: MessageEvent):
    """处理返回指令，退出诡域返回现实世界"""
    async with safe_session() as session:
        player = await require_player(session, event, revive_cmd)

        if not player.is_in_dungeon():
            await revive_cmd.finish("⛔ 你已经在现实世界了，无法使用返回指令\n💡 请使用【休息】指令恢复状态")

        # 记录返回前的位置信息
        was_in_dungeon = player.is_in_dungeon()
        dungeon_level = player.dungeon_level if was_in_dungeon else 0

        # 使用新的双层坐标系统退出诡域
        # 退出前推进现实世界的导航进度，使返回位置为“导航后的最新位置”
        from ..models.navigation_task import NavigationTask
        from ..world.navigation import _update_nav_position
        nav_task = await session.get(NavigationTask, player.id)
        nav_events = []
        if nav_task and player.hp <= 0:
            await session.delete(nav_task)
        elif nav_task:
            reached = await _update_nav_position(player, nav_task, session)
            if reached.interrupted:
                await session.commit()
                await revive_cmd.finish(build_markdown(format_navigation_interruption(player, reached)))
            if reached.events:
                await session.commit()
                await revive_cmd.send(build_markdown(format_navigation_events(reached.events)))
            if reached:
                # 到达时静默应用导航随机事件
                from .navigation_events import (
                    generate_navigation_events,
                    apply_navigation_events,
                )
                nav_events = generate_navigation_events(
                    player,
                    nav_task.initial_distance or 0,
                    nav_task.target_x,
                    nav_task.target_y,
                )
                await session.delete(nav_task)

        # 恢复满状态(包含临时buff加成)
        effective_attrs = await player.get_effective_attributes(session)
        player.hp = effective_attrs.get('max_hp', player.max_hp)
        player.mp = effective_attrs.get('max_mp', player.max_mp)
        if nav_events:
            await apply_navigation_events(session, player, nav_events)

        player.exit_dungeon()

        session.add(player)
        await session.commit()
        
        # 构建返回消息
        msg_lines = [
            "✨ 你从破碎的黑梦中惊醒，踏入『现实世界』。",
            "━━━━━━━━━━━━━",
            "✧ 生命与理智完全恢复",
        ]
        
        if was_in_dungeon:
            msg_lines.append(f"✧ 已从第{dungeon_level}重诡域穿越回表世界")
            msg_lines.append(f"✧ 恢复表世界坐标：({player.x},{player.y})")
        else:
            msg_lines.append("✧ 但你的精神状态可能不太好...")
            msg_lines.append(f"✧ 当前坐标：({player.x},{player.y})")

        msg_lines.extend([
            "━━━━━━━━━━━━━",
            "⬇️ 【导航 <x> <y>】劳逸结合，现实经商",
            "⬇️ 【传送 N层诡域】知诡才能制诡，继续探索"
        ])
        
        msg = "\n".join(msg_lines)
        await revive_cmd.finish(message_add_head(msg, event))


@prev_level_cmd.handle()
async def handle_prev_level(event: MessageEvent):
    """处理上一层指令，切换到上一层诡域"""
    async with safe_session() as session:
        player = await require_player(session, event, prev_level_cmd)

        # 检查是否在诡域中
        if not player.is_in_dungeon():
            await prev_level_cmd.finish("⛔ 你不在诡域中，无法使用层级切换功能\n💡 请先【进入 N层诡域】进入任意层诡域")

        current_level = player.dungeon_level or 0
        target_level = current_level - 1

        # 检查是否已经在第1层
        if target_level < 1:
            await prev_level_cmd.finish("⛔ 你已经在第1重诡域，无法再向上")

        # 检查是否可以进入目标层级
        if not player.can_enter_dungeon_level(target_level):
            await prev_level_cmd.finish(f"⛔ 无法进入第{target_level}重诡域，你尚未解锁该层级")

        # 计算目标层理智消耗并检查是否足够
        _prev_cfg = config.map_config.get("dungeon_levels", {}).get(target_level)
        if not _prev_cfg:
            _prev_cfg = config._generate_dungeon_level_config(
                target_level, config.map_config.get("dungeon_generation_rules", {})
            )
        mp_cost = _prev_cfg.get("mp_cost", 1)
        if player.mp < mp_cost:
            await prev_level_cmd.finish(
                f"⛔ 理智不足以穿越空间裂隙！需要 {mp_cost} 点理智，当前 {player.mp}"
            )

        # 扣除理智
        player.mp = max(0, player.mp - mp_cost)
        went_mad = False
        if player.mp == 0 and player.hp > 0:
            player.hp = 0  # 理智耗尽即"疯狂身亡"
            player.dungeon_kill_streak = 0
            went_mad = True

        # 切换到目标层级
        player.enter_dungeon(target_level)
        session.add(player)
        await session.commit()

        # 检查月卡自动采集
        from .dungeon_generation_service import get_or_create_tile, sense_level_elites
        from .dungeon_battle_service import _handle_material, _handle_treasure, get_tier_theme
        from ..models.monthly_card import get_player_card_benefits

        region_name = f"{target_level}层诡域"
        tile = await get_or_create_tile(session, region_name, player.dungeon_x, player.dungeon_y, player.server_id)
        benefits = await get_player_card_benefits(session, player.id)
        auto_collect_msg = ""
        if benefits.get("auto_collect", False):
            if tile.event_type == "MATERIAL":
                if player.id not in tile.state.get("looted_by", []) and not tile.state.get("looted"):
                    collect_result = await _handle_material(session, tile, player)
                    auto_collect_msg = f"\n💳 月卡自动采集：\n{collect_result}"
            elif tile.event_type == "TREASURE":
                if not tile.state.get("looted"):
                    collect_result = await _handle_treasure(session, tile, player)
                    auto_collect_msg = f"\n💳 月卡自动收集：\n{collect_result}"

        # 获取当前位置格子描述
        tile_desc = await get_tile_description(session, player, region_name, player.dungeon_x, player.dungeon_y)
        sense_msg = None if went_mad else await sense_level_elites(session, target_level, player.server_id, player.id)

        theme_name, theme_line = get_tier_theme(target_level)
        msg_lines = [
            f"🌀 你穿越空间裂隙，从第{current_level}重诡域来到第{target_level}重诡域（消耗理智 {mp_cost}）",
            f"📍 当前位置：{target_level}层诡域 ({player.dungeon_x},{player.dungeon_y})",
            "━━━━━━━━━━━━━",
            f"🩸 『{theme_name}』——{theme_line}",
        ]
        if sense_msg:
            msg_lines.append(sense_msg)
        if went_mad:
            msg_lines.append("💀 理智在穿越途中耗尽，你在无人的黑暗里笑出了声——疯狂身亡")
            msg_lines.append("⬇️ 【返回】回到现实 | 【使用 还魂丹】原地复活")
        msg_lines += [
            "🧭 【上下左右】移动 | 【探索】调查当前格",
            "⬆️【上一层】 ⬇️【下一层】 🚀【传送 N层诡域】 🏠【返回】",
            "━━━━━━━━━━━━━",
            tile_desc,
        ]
        if auto_collect_msg:
            msg_lines.append(auto_collect_msg)

        msg = "\n".join(msg_lines)
        await prev_level_cmd.finish(message_add_head(msg, event))


@next_level_cmd.handle()
async def handle_next_level(event: MessageEvent):
    """处理下一层指令，切换到下一层诡域"""
    async with safe_session() as session:
        player = await require_player(session, event, next_level_cmd)

        # 检查是否在诡域中
        if not player.is_in_dungeon():
            await next_level_cmd.finish("⛔ 你不在诡域中，无法使用层级切换功能\n💡 请先【进入 N层诡域】进入任意层诡域")

        current_level = player.dungeon_level or 0
        target_level = current_level + 1

        # 检查是否可以进入目标层级
        if not player.can_enter_dungeon_level(target_level):
            max_level = player.max_dungeon_level or 0
            await next_level_cmd.finish(
                f"⛔ 无法进入第{target_level}重诡域！\n"
                f"━━━━━━━━━━━━━\n"
                f"📊 当前最深探索：第{max_level}重诡域\n"
                f"━━━━━━━━━━━━━\n"
                f"💡 需要在当前层击败诡异解锁更深的诡域"
            )

        # 计算目标层理智消耗并检查是否足够
        _next_cfg = config.map_config.get("dungeon_levels", {}).get(target_level)
        if not _next_cfg:
            _next_cfg = config._generate_dungeon_level_config(
                target_level, config.map_config.get("dungeon_generation_rules", {})
            )
        mp_cost = _next_cfg.get("mp_cost", 1)
        if player.mp < mp_cost:
            await next_level_cmd.finish(
                f"⛔ 理智不足以穿越空间裂隙！需要 {mp_cost} 点理智，当前 {player.mp}"
            )

        # 扣除理智
        player.mp = max(0, player.mp - mp_cost)
        went_mad = False
        if player.mp == 0 and player.hp > 0:
            player.hp = 0  # 理智耗尽即"疯狂身亡"
            player.dungeon_kill_streak = 0
            went_mad = True

        # 切换到目标层级
        player.enter_dungeon(target_level)
        session.add(player)
        await session.commit()

        # 检查月卡自动采集
        from .dungeon_generation_service import get_or_create_tile, sense_level_elites
        from .dungeon_battle_service import _handle_material, _handle_treasure, get_tier_theme
        from ..models.monthly_card import get_player_card_benefits

        region_name = f"{target_level}层诡域"
        tile = await get_or_create_tile(session, region_name, player.dungeon_x, player.dungeon_y, player.server_id)
        benefits = await get_player_card_benefits(session, player.id)
        auto_collect_msg = ""
        if benefits.get("auto_collect", False):
            if tile.event_type == "MATERIAL":
                if player.id not in tile.state.get("looted_by", []) and not tile.state.get("looted"):
                    collect_result = await _handle_material(session, tile, player)
                    auto_collect_msg = f"\n💳 月卡自动采集：\n{collect_result}"
            elif tile.event_type == "TREASURE":
                if not tile.state.get("looted"):
                    collect_result = await _handle_treasure(session, tile, player)
                    auto_collect_msg = f"\n💳 月卡自动收集：\n{collect_result}"

        # 获取当前位置格子描述
        tile_desc = await get_tile_description(session, player, region_name, player.dungeon_x, player.dungeon_y)
        sense_msg = None if went_mad else await sense_level_elites(session, target_level, player.server_id, player.id)

        theme_name, theme_line = get_tier_theme(target_level)
        msg_lines = [
            f"🌀 你穿越空间裂隙，从第{current_level}重诡域来到第{target_level}重诡域（消耗理智 {mp_cost}）",
            f"📍 当前位置：{target_level}层诡域 ({player.dungeon_x},{player.dungeon_y})",
            "━━━━━━━━━━━━━",
            f"🩸 『{theme_name}』——{theme_line}",
        ]
        if sense_msg:
            msg_lines.append(sense_msg)
        if went_mad:
            msg_lines.append("💀 理智在穿越途中耗尽，你在无人的黑暗里笑出了声——疯狂身亡")
            msg_lines.append("⬇️ 【返回】回到现实 | 【使用 还魂丹】原地复活")
        msg_lines += [
            "🧭 【上下左右】移动 | 【探索】调查当前格",
            "⬆️【上一层】 ⬇️【下一层】 🚀【传送 N层诡域】 🏠【返回】",
            "━━━━━━━━━━━━━",
            tile_desc,
        ]
        if auto_collect_msg:
            msg_lines.append(auto_collect_msg)

        msg = "\n".join(msg_lines)
        await next_level_cmd.finish(message_add_head(msg, event))


@rest_cmd.handle()
async def handle_rest(event: MessageEvent):
    async with safe_session() as session:
        player = await require_player(session, event, rest_cmd)

        if player.is_in_dungeon():
            await _handle_dungeon_rest(session, player, event, rest_cmd)
        else:
            await _handle_reality_rest(session, player, event, rest_cmd)


async def _handle_dungeon_rest(session, player: Player, event: MessageEvent, cmd_handler):
    from .dungeon_generation_service import get_or_create_tile

    region_name = f"{player.dungeon_level}层诡域"
    tile = await get_or_create_tile(session, region_name, player.dungeon_x, player.dungeon_y, player.server_id)

    if tile.event_type != "REST":
        msg_lines = [
            "⛔ 这里不是驿站，无法休息",
            "━━━━━━━━━━━━━",
            "🌫️ 你需要找到【驿站】格子才能休息恢复生命",
            "🧭 使用【上下左右】移动探索",
        ]
        msg = "\n".join(msg_lines)
        await cmd_handler.finish(message_add_head(msg, event))

    effective_attrs = await player.get_effective_attributes(session)
    effective_max_hp = effective_attrs.get('max_hp', player.max_hp)
    player.hp = effective_max_hp
    session.add(player)
    await session.commit()

    msg_lines = [
        "🏮 你在驿站睡了一晚。醒来时床脚的灰尘上多了一圈脚印，而你的伤都好了。",
        "━━━━━━━━━━━━━",
        f"✧ 生命值：{player.hp}/{effective_max_hp}",
        "🧭 继续探索诡域吧！",
    ]
    msg = "\n".join(msg_lines)
    await cmd_handler.finish(message_add_head(msg, event))


_reality_rest_history: dict = {}  # {user_id: deque[timestamp]}

async def _handle_reality_rest(session, player: Player, event: MessageEvent, cmd_handler):
    import time
    from collections import deque

    # 现实世界休息限频：3600秒内最多10次
    user_id = event.get_user_id()
    now = time.monotonic()
    if user_id not in _reality_rest_history:
        _reality_rest_history[user_id] = deque()
    history = _reality_rest_history[user_id]
    # 清理过期记录
    while history and history[0] < now - 3600:
        history.popleft()
    if len(history) >= 10:
        await cmd_handler.finish("⚠️ 现实世界休息过于频繁，请在1小时内最多休息10次")
    history.append(now)

    effective_attrs = await player.get_effective_attributes(session)
    effective_max_hp = effective_attrs.get('max_hp', player.max_hp)
    effective_max_mp = effective_attrs.get('max_mp', player.max_mp)
    player.hp = effective_max_hp
    player.mp = effective_max_mp
    # stamina 是固定属性（咒抗），不需要恢复

    session.add(player)
    await session.commit()

    msg_lines = [
        "💤 你在现实世界好好休息了一觉，精力充沛。",
        "━━━━━━━━━━━━━",
        f"✧ 生命值：{player.hp}/{effective_max_hp}",
        f"✧ 法力值：{player.mp}/{effective_max_mp}",
        f"✧ 咒抗：{player.stamina}",
        "━━━━━━━━━━━━━",
        "🧭 使用【导航 <x> <y>】开始经商",
        "🌌 使用【传送 N层诡域】进入诡域探索",
    ]
    msg = "\n".join(msg_lines)
    await cmd_handler.finish(message_add_head(msg, event))
