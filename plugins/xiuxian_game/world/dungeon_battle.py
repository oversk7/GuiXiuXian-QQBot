from __future__ import annotations

"""世界与坐标系统
1. 传送 <区域名> 切换区域，但坐标与现实世界相同
2. 前往 <上|下|左|右|x,y> 改变坐标（同区域内移动）
3. get_or_create_tile: 按天刷新、确定性种子生成事件
"""

from nonebot import on_command, on_regex
from nonebot.matcher import Matcher
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams
from nonebot.params import CommandArg
from typing import Tuple, Dict
from datetime import datetime, date, timedelta
import base64
import os
from pathlib import Path

from sqlalchemy import select, func
from ..models.db import safe_session, retry_session
from ..models.player import Player
from ..models.world_tile import WorldTile
from ..models.monthly_card import get_player_card_benefits
from ..config import config
from ..utils import message_add_head
from ..utils_markdown import cmd, build_markdown
from ..platform_utils import get_unified_player, require_player
from .dungeon_battle_service import (
    BattleResult,
    EVENT_HANDLERS,
    _build_dungeon_minimap,
    _handle_material,
    _handle_treasure,
    _query_explored_coords,
    generate_player_centered_overview_image,
    generate_region_overview_image,
)
from .dungeon_generation_service import get_or_create_tile


# ----------------- 常量 -----------------
DIRECTIONS: Dict[str, Tuple[int, int]] = {
    "上": (0, 1),
    "下": (0, -1),
    "左": (-1, 0),
    "右": (1, 0),
}


# ----------------- 指令：移动 -----------------
move_cmd = on_regex(r"^\s*(上|下|左|右)\s*$", block=True, priority=5)

@move_cmd.handle()
async def _(event: MessageEvent):
    direction = event.get_plaintext().strip()
    user_id = event.get_user_id()

    async with retry_session() as session:
        player: Player | None = await get_unified_player(session, event)
        if not player:
            await move_cmd.finish("⛔ 请先创建角色")

        if not player.is_in_dungeon():
            await move_cmd.finish("⛔ 单格移动只能在诡域使用\n⬇️ 【导航 <x> <y>】在现实世界移动")

        # 解析方向
        if direction not in DIRECTIONS:
            await move_cmd.finish("⛔ 无效的方向")
        dx, dy = DIRECTIONS[direction]

        # 使用新的移动系统（自动处理坐标限制）
        old_x, old_y = player.dungeon_x, player.dungeon_y
        player.move_in_current_world(dx, dy)
        new_x, new_y = player.dungeon_x, player.dungeon_y

        # 检查是否真的移动了（可能被边界限制）
        if old_x == new_x and old_y == new_y:
            await move_cmd.finish(f"⛔ 无法向{direction}移动，已到达诡域边界\n📍 当前坐标范围：(-5,-5) 到 (5,5)")

        # 根据诡域层级获取配置并扣除理智
        dungeon_config = config.map_config.get("dungeon_levels", {}).get(player.dungeon_level)
        if not dungeon_config:
            # 动态生成超过100层的配置
            dungeon_config = config._generate_dungeon_level_config(
                player.dungeon_level, config.map_config.get("dungeon_generation_rules", {})
            )
        mp_cost = dungeon_config.get("mp_cost", 1)  # 默认消耗1点理智

        if player.mp < mp_cost:
            # 移动失败，恢复原坐标
            player.dungeon_x, player.dungeon_y = old_x, old_y
            player.x, player.y = old_x, old_y
            await move_cmd.finish(f"⛔ 理智不足以在此诡域移动，需要 {mp_cost} 点理智，当前 {player.mp}")

        player.mp = max(0, player.mp - mp_cost)
        if player.mp == 0 and player.hp > 0:
            player.hp = 0  # 理智耗尽即"疯狂身亡"

        # 获取当前位置事件格
        tile = await get_or_create_tile(session, player.get_current_region(), new_x, new_y, player.server_id)

        # 清除全视之眼预览标记（玩家已实际到达此格子）
        if (tile.state or {}).get("preview"):
            state = tile.state or {}
            state.pop("preview", None)
            tile.state = state

        # 检查月卡权限是否支持自动采集
        benefits = await get_player_card_benefits(session, player.id)
        auto_collect = benefits.get("auto_collect", False)

        auto_collect_msg = ""

        # 如果有月卡自动采集权限，自动触发收集
        if auto_collect:
            if tile.event_type == "MATERIAL":
                # 自动采集材料
                if player.id not in tile.state.get("looted_by", []) and not tile.state.get("looted"):
                    collect_result = await _handle_material(session, tile, player)
                    auto_collect_msg = f"\n💳 月卡自动采集：\n{collect_result}"
            elif tile.event_type == "TREASURE":
                # 自动收集宝藏
                if not tile.state.get("looted"):
                    collect_result = await _handle_treasure(session, tile, player)
                    auto_collect_msg = f"\n💳 月卡自动收集：\n{collect_result}"

        session.add_all([player, tile])
        await session.commit()  # 提交数据库事务

        # 构造事件描述
        def describe_tile(t: WorldTile) -> str:
            """根据 tile 类型生成可读描述，在移动后提示玩家下一步操作。"""
            if t.event_type == "MATERIAL":
                item_cfg = config.items_config["by_id"].get(t.state.get("item_id"))
                item_name = item_cfg.get_display_name() if item_cfg else "未知材料"
                qty = t.state.get("quantity", "?")
                looted_by = t.state.get("looted_by", [])
                if player.id in looted_by or t.state.get("looted"):
                    return f"🪨 这里曾经散落着 {item_name} ✖️{qty}，但已被搜刮一空。"
                return f"✨ 你发现了材料 {item_name} ✖️{qty}，可输入 【收集】 获取。"
            elif t.event_type == "TREASURE":
                if t.state.get("looted"):
                    return "🪨 破碎的宝箱静静躺在尘埃中，没有任何价值。"
                return "🎁 你注意到一个尘封宝箱，输入 【探索】 能打开它。"
            elif t.event_type == "EMPTY":
                if player.id in t.state.get("defeated_by", []):
                    return "🪨 这里只剩下诡异的残骸，散发着淡淡的血腥味。"
                monster = t.state.get("name")
                monster_level = t.state.get("level", 1)

                # 为200级以后的诡异显示特殊属性提示
                special_info = ""
                if monster_level >= 200:
                    special_attrs = []
                    if t.state.get("crit_rate", 0) > 0:
                        special_attrs.append(f"💥暴击{t.state['crit_rate']:.1f}%")
                    if t.state.get("combo_rate", 0) > 0:
                        special_attrs.append(f"🔄连击{t.state['combo_rate']:.1f}%")
                    if t.state.get("counter_rate", 0) > 0:
                        special_attrs.append(f"⚡反击{t.state['counter_rate']:.1f}%")
                    if t.state.get("anti_crit_rate", 0) > 0:
                        special_attrs.append(f"🛡️抗暴{t.state['anti_crit_rate']:.1f}%")
                    if t.state.get("defense", 0) > 0:
                        special_attrs.append(f"🪨防{t.state['defense']}")
                    if t.state.get("true_damage_rate", 0) > 0:
                        special_attrs.append(f"🗡️真伤{t.state['true_damage_rate']:.1f}%")

                    if special_attrs:
                        special_info = f"\n🔥 特殊能力：{' '.join(special_attrs)}"

                return f"🌫️ 空间扭曲中传来异响，似乎有 {monster}(Lv{monster_level}) 在此游荡。{special_info}\n若想挑战，可输入 【探索】 进行调查。"
            elif t.event_type == "REST":
                return "🌫️ 你发现了一家驿站，可输入 【探索】 恢复生命。"
            elif t.event_type == "MERCHANT":
                if player.id in t.state.get("visited_by", []):
                    return "🏪 卖货郎已经离开了，只留下空荡荡的摊位。"
                return "🏪 你遇到了神秘卖货郎，输入 【探索】 查看他的商品。"
            elif t.event_type == "ELITE":
                if player.id in t.state.get("defeated_by", []):
                    return "⚰️ 精英诡异的残骸散落一地，散发着不祥的气息。"
                monster_name = t.state.get("name", "精英诡异")
                monster_level = t.state.get("level", 1)

                # 为200级以后的精英诡异显示特殊属性提示
                special_info = ""
                if monster_level >= 200:
                    special_attrs = []
                    if t.state.get("crit_rate", 0) > 0:
                        special_attrs.append(f"💥暴击{t.state['crit_rate']:.1f}%")
                    if t.state.get("combo_rate", 0) > 0:
                        special_attrs.append(f"🔄连击{t.state['combo_rate']:.1f}%")
                    if t.state.get("counter_rate", 0) > 0:
                        special_attrs.append(f"⚡反击{t.state['counter_rate']:.1f}%")
                    if t.state.get("anti_crit_rate", 0) > 0:
                        special_attrs.append(f"🛡️抗暴{t.state['anti_crit_rate']:.1f}%")
                    if t.state.get("defense", 0) > 0:
                        special_attrs.append(f"🪨防{t.state['defense']}")
                    if t.state.get("true_damage_rate", 0) > 0:
                        special_attrs.append(f"🗡️真伤{t.state['true_damage_rate']:.1f}%")

                    if special_attrs:
                        special_info = f"\n🔥 特殊能力：{' '.join(special_attrs)}"

                return f"⚔️ 空间深处传来恶意的窥视，{monster_name}(Lv{monster_level}) 作为这重诡域的诡异存在正盯着你！{special_info}\n输入 【探索】 迎战。"
            return "⁉️ 未知事件。"

        event_desc = describe_tile(tile)

        # 获取含buff/宠物的有效属性，保持与面板一致
        effective_attrs = await player.get_effective_attributes(session)
        eff_max_hp = effective_attrs.get("max_hp", player.max_hp)
        eff_max_mp = effective_attrs.get("max_mp", player.max_mp)

        status_line = (
            f"🧭 **{player.get_current_region()}** ({new_x},{new_y})　"
            f"❤️ **{player.hp}**/{eff_max_hp}　"
            f"🧠 **{player.mp}**/{eff_max_mp}"
        )

        lines = [
            "# 🚶 诡域移动",
            status_line,
            "***",
            event_desc,
        ]
        if auto_collect_msg:
            lines.append(auto_collect_msg)
        lines += [
            "***",
            f"{cmd('↑上', '上')} | {cmd('↓下', '下')} | {cmd('←左', '左')} | {cmd('→右', '右')} | {cmd('🗡️探索', '探索')}",
            f"{cmd('上一层')} | {cmd('下一层')} | {cmd('一键嗑药')} | {cmd('俯瞰')}",
        ]

        await move_cmd.finish(build_markdown("\n".join(lines)))

# ----------------- 指令：战斗 -----------------
explore_cmd = on_command("探索", aliases={"战斗", "收集"}, block=True, priority=5)


@explore_cmd.handle()
async def _(event: MessageEvent):
    user_id = event.get_user_id()

    async with safe_session() as session:
        player: Player | None = await get_unified_player(session, event)
        if not player:
            await explore_cmd.finish("⛔ 请先创建角色")

        if not player.is_in_dungeon():
            await explore_cmd.finish("⛔ 你已经返回现实\n⬇️ 【传送 N层诡域】进入诡域探索")

        if player.hp <= 0:
            await explore_cmd.finish("💀 你已死亡，返回现实吧，或者你有复活道具..."
                                     "\n⬇️ 【返回】 退出副本"
                                     "\n⬇️ 【使用 还魂丹】 原地复活，继续副本")

        # 使用新的坐标系统获取当前位置
        current_x, current_y = player.get_current_coordinates()
        current_region = player.get_current_region()
        tile = await get_or_create_tile(session, current_region, current_x, current_y, player.server_id)

        # 清除全视之眼预览标记（玩家已实际探索此格子）
        if (tile.state or {}).get("preview"):
            state = tile.state or {}
            state.pop("preview", None)
            tile.state = state

        log = await EVENT_HANDLERS[tile.event_type](session, tile, player)

        # 更新探索统计（用于公会任务）
        if player.guild_id:
            from ..guild.guild_task_service import GuildTaskService
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.guild_repository import GuildRepository
            from ..infrastructure.repositories.player_task_stats_repository import PlayerTaskStatsRepository
            from ..infrastructure.repositories.guild_task_record_repository import GuildTaskRecordRepository
            from ..infrastructure.repositories.player_donation_log_repository import PlayerDonationLogRepository
            from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository

            task_service = GuildTaskService(
                player_repo=PlayerRepository(session),
                guild_repo=GuildRepository(session),
                player_task_stats_repo=PlayerTaskStatsRepository(session),
                guild_task_record_repo=GuildTaskRecordRepository(session),
                player_donation_log_repo=PlayerDonationLogRepository(session),
                guild_building_repo=GuildBuildingRepository(session),
            )
            await task_service.update_exploration_stats(player.id)

            # 尝试自动完成任务
            completed_tasks = await task_service.try_auto_complete_tasks(player.id)
            if completed_tasks:
                if isinstance(log, BattleResult):
                    log.log_lines.append("")
                    log.log_lines.append("🎉 公会任务完成：")
                    log.log_lines.extend(completed_tasks)
                else:
                    log += "\n\n🎉 公会任务完成：\n" + "\n".join(completed_tasks)
        # 获取含buff/宠物的有效属性，保持与面板一致
        effective_attrs = await player.get_effective_attributes(session)
        eff_max_hp = effective_attrs.get("max_hp", player.max_hp)
        eff_max_mp = effective_attrs.get("max_mp", player.max_mp)

        # 查询已探索坐标（用于战斗后的小地图）
        explored_coords: set[tuple[int, int]] = set()
        if isinstance(log, BattleResult):
            explored_coords = await _query_explored_coords(session, current_region, player.server_id)

        await session.commit()

    status_line = (
        f"🧭 **{current_region}** ({current_x},{current_y})　"
        f"❤️ **{player.hp}**/{eff_max_hp}　"
        f"🧠 **{player.mp}**/{eff_max_mp}"
    )

    nav_row1 = f"{cmd('↑上', '上')} | {cmd('↓下', '下')} | {cmd('←左', '左')} | {cmd('→右', '右')} | {cmd('🗡️探索', '探索')}"
    nav_row2 = f"{cmd('上一层')} | {cmd('下一层')} | {cmd('一键嗑药')} | {cmd('俯瞰')}"

    if isinstance(log, BattleResult):
        # 战斗日志用 bash 代码块包裹；小地图放在代码块外面
        mini_map = _build_dungeon_minimap(current_x, current_y, explored_coords)
        battle_title = f"⚔️ **击杀 {log.monster_display}**" if log.victory else f"⚔️ **对战 {log.monster_display}**"
        battle_text = "\n".join(str(l) for l in log.log_lines)
        lines = [
            "# 🌀 诡域探索",
            status_line,
            "***",
            "🗺️ **小地图**　🟨你　🟩已探索　⬜未探索",
            mini_map,
            "***",
            battle_title,
            "```bash",
            battle_text,
            "```",
            "***",
            nav_row1,
            nav_row2,
        ]
    else:
        lines = [
            "# 🌀 诡域探索",
            status_line,
            "***",
            log,
            "***",
            nav_row1,
            nav_row2,
        ]

    await explore_cmd.finish(build_markdown("\n".join(lines)))

# ==================== 购买指令 ====================
dungeon_buy_cmd = on_command("购买", block=False, priority=5)

@dungeon_buy_cmd.handle()
async def handle_buy(matcher: Matcher, event: MessageEvent, args: Message = CommandArg()):
    """从卖货郎处购买商品（仅副本内生效，参数为纯数字序号）"""
    arg_text = args.extract_plain_text().strip()
    # 仅处理纯数字参数（副本卖货郎用序号），其他格式放行给跑商购买
    if not arg_text or not arg_text.isdigit():
        return
    item_index = int(arg_text)

    async with safe_session() as session:
        player = await require_player(session, event, dungeon_buy_cmd)

        # 大都会玩家不处理，放行给跑商购买命令
        if player.region == "大都会":
            return
        # 非大都会且参数为纯数字时，视为诡域卖货郎购买，阻断后续「购买」命令
        matcher.stop_propagation()

        # 获取当前位置的格子 - 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        tile = await get_or_create_tile(session, player.region, current_x, current_y, player.server_id)

        if tile.event_type != "MERCHANT":
            await dungeon_buy_cmd.finish("⛔ 这里没有卖货郎")

        if player.id not in tile.state.get("visited_by", []):
            await dungeon_buy_cmd.finish("⛔ 你还没有与卖货郎交谈，请先【探索】")

        # 检查玩家是否已经购买过商品
        purchased_by = tile.state.get("purchased_by", [])
        if player.id in purchased_by:
            await dungeon_buy_cmd.finish("⛔ 你已经从这个卖货郎处购买过商品了，每人只能购买一次")

        goods = tile.state.get("goods", [])
        if not goods or item_index < 1 or item_index > len(goods):
            await dungeon_buy_cmd.finish("⛔ 商品序号无效")

        good = goods[item_index - 1]
        item_config = config.items_config["by_id"].get(good["item_id"])
        if not item_config:
            await dungeon_buy_cmd.finish("⛔ 商品不存在")

        # 检查金币是否足够
        if player.gold < good["price"]:
            await dungeon_buy_cmd.finish(f"⛔ 金币不足，需要 {good['price']}💰，当前 {player.gold}💰")

        # 购买商品
        try:
            from ..models.inventory import ItemInstance
            await ItemInstance.add_item(session, player.id, good["item_id"], good["quantity"])
            player.gold -= good["price"]

            # 移除已购买的商品
            goods.pop(item_index - 1)
            tile.state["goods"] = goods

            # 标记玩家已购买，防止重复购买
            tile.state.setdefault("purchased_by", []).append(player.id)

            session.add_all([player, tile])
            await session.commit()

            msg = (
                f"💰 购买成功！\n"
                f"▫️ 获得：{item_config.get_display_name()} ✖️{good['quantity']}\n"
                f"▫️ 花费：{good['price']}💰\n"
                f"▫️ 剩余金币：{player.gold}💰\n"
                f"⚠️ 你已经从这个卖货郎处购买过商品，无法再次购买"
            )
            await dungeon_buy_cmd.finish(message_add_head(msg, event))

        except ValueError as e:
            await dungeon_buy_cmd.finish(f"⛔ 购买失败：{e}")


teleport_list = on_command("诡域", aliases={"副本列表"}, block=True, priority=5)
@teleport_list.handle()
async def handle_teleport_list(event: MessageEvent):
    """显示无限层诡域爬塔进度"""
    async with safe_session() as session:
        # 检查玩家是否存在
        player = await require_player(session, event, teleport_list)

        # 获取玩家爬塔进度
        max_level = player.max_dungeon_level or 0
        accessible_levels = player.get_accessible_dungeon_levels()
        current_level = player.dungeon_level if player.is_in_dungeon() else 0

        # 显示当前可访问的层级（最多显示5层）
        display_levels = accessible_levels[-5:] if len(accessible_levels) > 5 else accessible_levels

        locations = []
        for level in display_levels:
            # 动态生成层级配置
            dungeon_config = config._generate_dungeon_level_config(
                level, config.map_config.get("dungeon_generation_rules", {})
            )

            mp_cost = dungeon_config.get("mp_cost", 1)
            level_range = dungeon_config.get("level_range", [level*5-2, level*5+2])

            # 状态标识
            if level <= max_level:
                status = "✅"  # 已通过
            elif level == max_level + 1:
                status = "🎯"  # 下一个挑战
            else:
                status = "🔒"  # 未解锁

            # 当前所在层级
            current_marker = " 📍**当前**" if level == current_level else ""
            level_name = f"{level}层诡域"

            if level <= max_level + 1:
                # 可进入的层：点击直接传送
                locations.append(
                    f"{status} {cmd(level_name, f'传送 {level_name}')}　"
                    f"⚡理智-{mp_cost}　👹诡异Lv.{level_range[0]}-{level_range[1]}{current_marker}"
                )
            else:
                locations.append(
                    f"{status} **{level_name}**　"
                    f"⚡理智-{mp_cost}　👹诡异Lv.{level_range[0]}-{level_range[1]}"
                )

        # 格式化消息
        msg_lines = [
            "# 🌀 无限重诡域探索系统",
            "***",
            f"🏆 最深探索：**第{max_level}重**诡域",
            f"🎯 下一目标：**第{max_level + 1}重**诡域",
            f"📊 总可访问：**{len(accessible_levels)}重**",
        ]

        if current_level > 0:
            msg_lines.append(f"📍 当前位置：**第{current_level}重**诡域")

        msg_lines.extend([
            "***",
            "💡 每重诡域都是独立的10x10空间",
            "⚔️ 诡异等级 = 诡域深度 × 5（±2波动）",
            "🔓 击败诡异解锁更深的诡域",
            "***",
        ])

        if locations:
            msg_lines.append("**📋 可访问深度（最近5重）：**")
            msg_lines.extend(locations)

        msg_lines.extend([
            "***",
            "✅已探索　🎯下一目标　🔒未解锁",
            f"{cmd('俯瞰')} | {cmd('返回')} | {cmd('帮助')}",
        ])

        await teleport_list.finish(build_markdown("\n".join(msg_lines)))


# ==================== 诡域探索概览图片生成 ====================
region_overview_cmd = on_command("俯瞰", aliases={"感知"}, block=True, priority=5)


@region_overview_cmd.handle()
async def handle_region_overview(event: MessageEvent, args: Message = CommandArg()):
    """生成诡域探索概览图片"""
    async with safe_session() as session:
        player = await require_player(session, event, region_overview_cmd)

        # 获取参数
        arg_text = args.extract_plain_text().strip()

        # 如果没有指定诡域，俯瞰当前区域
        if not arg_text:
            try:
                current_x, current_y = player.get_current_coordinates()
                current_region = player.get_current_region()

                # 检查当前区域是否为诡域（层级制诡域）
                if current_region.endswith("层诡域"):
                    # 全视之眼赞助特权：预生成所有格子
                    from ..sponsor.service import SponsorShopService
                    if SponsorShopService.is_privilege_active(player, "premium_vision_until"):
                        # 记录已存在的格子坐标（玩家实际探索过的）
                        from sqlalchemy import and_
                        today = date.today()
                        today_start = datetime.combine(today, datetime.min.time())
                        tomorrow_start = today_start + timedelta(days=1)
                        existing_stmt = select(WorldTile.x, WorldTile.y).where(
                            and_(
                                WorldTile.region == current_region,
                                WorldTile.server_id == player.server_id,
                                WorldTile.refreshed_at >= today_start,
                                WorldTile.refreshed_at < tomorrow_start
                            )
                        )
                        existing_result = await session.execute(existing_stmt)
                        existing_coords = {(r[0], r[1]) for r in existing_result}
                        # 预生成所有格子，新格子标记为预览
                        for tx in range(-5, 6):
                            for ty in range(-5, 6):
                                if (tx, ty) not in existing_coords:
                                    tile = await get_or_create_tile(session, current_region, tx, ty, player.server_id)
                                    # 标记为预览格子
                                    state = tile.state or {}
                                    state["preview"] = True
                                    tile.state = state
                        await session.flush()
                    # 诡域内：生成固定的10x10地图（-5到5的范围），以(0,0)为中心但显示玩家实际位置
                    img_data, (min_x, max_x, min_y, max_y) = await generate_player_centered_overview_image(
                        current_region, session, 0, 0, 11, 11, current_x, current_y, player.server_id  # 以(0,0)为中心的11x11地图，但显示玩家在(current_x,current_y)的位置
                    )
                    map_desc = f"🗺️ {current_region} 今日探索情况"
                    coord_desc = f"📍 你的位置：({current_x},{current_y})"
                    range_desc = f"📍 诡域范围：(-5,-5) 到 (5,5)"
                else:
                    # 现实世界：生成以玩家为中心的大范围俯瞰图
                    img_data, (min_x, max_x, min_y, max_y) = await generate_player_centered_overview_image(
                        current_region, session, current_x, current_y, 500, 500, current_x, current_y, player.server_id
                    )
                    map_desc = f"🗺️ {current_region} 以你为中心的俯瞰图"
                    coord_desc = f"📍 中心位置：({current_x},{current_y})"
                    range_desc = f"📍 坐标范围：X({min_x}~{max_x}) Y({min_y}~{max_y})"

                # 转换为base64
                img_b64 = base64.b64encode(img_data).decode('utf-8')

                # 构建说明文字
                msg_lines = [
                    map_desc,
                    "━━━━━━━━━━━━━",
                    coord_desc,
                    range_desc,
                    "━━━━━━━━━━━━━",
                    "🟢 绿色：材料格子",
                    "🟡 金色：宝藏格子",
                    "🔴 红色：诡异格子",
                    "🔵 蓝色：休息格子",
                    "🟣 紫色：商人格子",
                    "🟠 橙色：精英怪格子",
                    "⬛ 灰色：未探索区域",
                    "🔲 暗色：全视之眼揭示（未探索）",
                    f"🟡 亮黄圆圈：你的位置 ({current_x},{current_y})",
                ]

                msg_text = "\n".join(msg_lines)

                # 发送图片和文字
                img_segment = MessageSegment.file_image(img_b64)
                message = Message(msg_text).append(img_segment)

                await region_overview_cmd.finish(message_add_head(message, event))

            except ValueError as e:
                await region_overview_cmd.finish(f"⛔ 生成俯瞰图失败：{str(e)}")
        else:
            # 指定了诡域名称，支持层级制诡域
            region = arg_text

            # 检查是否为层级诡域格式
            if region.endswith("层诡域"):
                try:
                    level_str = region.replace("层诡域", "")
                    # 兼容"第N层诡域"格式，移除开头的"第"字
                    if level_str.startswith("第"):
                        level_str = level_str[1:]
                    dungeon_level = int(level_str)
                    # 优先从预生成配置获取，如果不存在则动态生成（支持无限层）
                    dungeon_config = config.map_config.get("dungeon_levels", {}).get(dungeon_level)
                    if not dungeon_config:
                        # 动态生成超过100层的配置
                        dungeon_config = config._generate_dungeon_level_config(
                            dungeon_level, config.map_config.get("dungeon_generation_rules", {})
                        )
                except ValueError:
                    await region_overview_cmd.finish("⛔ 诡域层级格式错误，请使用：俯瞰 1层诡域 或 俯瞰 第1层诡域")
            else:
                # 兼容旧的命名诡域
                if region not in config.map_config.get("regions", {}):
                    await region_overview_cmd.finish("⛔ 未知的诡域名称，请使用：俯瞰 N层诡域")
                dungeon_config = config.map_config["regions"].get(region, {})

            try:
                # 生成概览图片，传入玩家坐标（如果玩家在当前诡域）
                player_x, player_y = None, None
                current_region = player.get_current_region()
                if current_region == region:
                    player_x, player_y = player.get_current_coordinates()

                # 检查是否为诡域，如果是则使用固定范围
                if region.endswith("层诡域"):
                    # 全视之眼赞助特权：预生成所有格子
                    from ..sponsor.service import SponsorShopService
                    if SponsorShopService.is_privilege_active(player, "premium_vision_until"):
                        # 记录已存在的格子坐标（玩家实际探索过的）
                        from sqlalchemy import and_
                        today = date.today()
                        today_start = datetime.combine(today, datetime.min.time())
                        tomorrow_start = today_start + timedelta(days=1)
                        existing_stmt = select(WorldTile.x, WorldTile.y).where(
                            and_(
                                WorldTile.region == region,
                                WorldTile.server_id == player.server_id,
                                WorldTile.refreshed_at >= today_start,
                                WorldTile.refreshed_at < tomorrow_start
                            )
                        )
                        existing_result = await session.execute(existing_stmt)
                        existing_coords = {(r[0], r[1]) for r in existing_result}
                        # 预生成所有格子，新格子标记为预览
                        for tx in range(-5, 6):
                            for ty in range(-5, 6):
                                if (tx, ty) not in existing_coords:
                                    tile = await get_or_create_tile(session, region, tx, ty, player.server_id)
                                    # 标记为预览格子
                                    state = tile.state or {}
                                    state["preview"] = True
                                    tile.state = state
                        await session.flush()
                    # 诡域使用固定的10x10范围（-5到5），如果玩家在当前诡域则以玩家为中心
                    center_x, center_y = 0, 0  # 默认以(0,0)为中心
                    if current_region == region and player_x is not None and player_y is not None:
                        center_x, center_y = player_x, player_y  # 如果玩家在当前诡域，以玩家位置为中心
                    img_data, (min_x, max_x, min_y, max_y) = await generate_player_centered_overview_image(
                        region, session, center_x, center_y, 11, 11, player_x, player_y, player.server_id  # 以计算出的中心位置生成11x11地图，显示玩家实际位置
                    )
                else:
                    # 其他区域使用原有的今日探索逻辑
                    img_data, (min_x, max_x, min_y, max_y) = await generate_region_overview_image(region, session, player_x, player_y, player.server_id)

                # 转换为base64
                img_b64 = base64.b64encode(img_data).decode('utf-8')

                # 构建消息
                tier = dungeon_config.get("tier", 1)
                level_range = dungeon_config.get("level_range", [1, 1])

                # 构建说明文字
                if region.endswith("层诡域"):
                    msg_lines = [
                        f"🗺️ {region} 今日探索小地图",
                        "━━━━━━━━━━━━━",
                        f"📊 诡域等级：Tier {tier}",
                        f"⚔️ 诡异等级：{level_range[0]}-{level_range[1]}级",
                        "📍 诡域范围：(-5,-5) 到 (5,5)"
                    ]
                else:
                    msg_lines = [
                        f"🗺️ {region} 今日探索小地图",
                        "━━━━━━━━━━━━━",
                        f"📊 诡域等级：Tier {tier}",
                        f"⚔️ 诡异等级：{level_range[0]}-{level_range[1]}级",
                        f"📍 坐标范围：X({min_x}~{max_x}) Y({min_y}~{max_y})"
                    ]

                msg_lines.extend([
                    "━━━━━━━━━━━━━",
                    "🟢 绿色：材料格子",
                    "🟡 金色：宝藏格子",
                    "🔴 红色：诡异格子",
                    "🔵 蓝色：休息格子",
                    "🟣 紫色：商人格子",
                    "🟠 橙色：精英怪格子",
                    "⬛ 灰色：未探索区域",
                    "🔲 暗色：全视之眼揭示（未探索）"
                ])

                # 如果玩家在当前诡域，添加位置说明
                if current_region == region:
                    current_x, current_y = player.get_current_coordinates()
                    msg_lines.append(f"🟡 亮黄圆圈：你的位置 ({current_x},{current_y})")

                msg_lines.append("🔢 图片边缘显示坐标数字")

                msg_text = "\n".join(msg_lines)

                # 发送图片和文字
                img_segment = MessageSegment.file_image(img_b64)
                message = Message(msg_text).append(img_segment)

                await region_overview_cmd.finish(message_add_head(message, event))

            except ValueError as e:
                await region_overview_cmd.finish(f"⛔ 生成概览图片失败：{str(e)}")
