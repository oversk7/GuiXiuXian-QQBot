from __future__ import annotations

"""自动导航功能（现实世界可用）

设定：
1. 仅当玩家位于现实世界（region == "大都市"）时可使用导航。
2. 指令：
   • 导航 x y      → 开启/查看导航进度
   • 前往 地点名   → 快速前往指定地点
   • 中断导航      → 取消当前导航
3. 导航过程中不会主动推送消息，位置更新在玩家下一次触发相关指令时计算。
4. 坐标范围限制：-500 ≤ x,y ≤ 500
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from datetime import datetime, timedelta
from typing import Tuple
from ..models.db import safe_session, AsyncSessionLocal
from ..models.player import Player
from ..utils import message_add_head
from ..utils_markdown import cmd, build_markdown
from ..models.navigation_task import NavigationTask
from ..platform_utils import get_unified_player
from ..infrastructure.uow.unit_of_work import UnitOfWork
from .location_service import LocationService
from .npc_service import NPCService

# ----------------- 持久化模型 -----------------

# ----------------- 常量 -----------------
# 坐标正负范围
MAX_COORD = 2000
REAL_WORLD = "大都会"

# ----------------- 指令：导航 -----------------
nav_cmd = on_command("导航", aliases={"移动"}, block=True, priority=5)
find_npc_cmd = on_command("查找", block=True, priority=5)
check_data_cmd = on_command("检查数据", block=True, priority=5)
stop_nav_cmd = on_command("中断导航", aliases={"停止导航", "取消导航"}, block=True, priority=5)


def _tiles_per_second(agility: int) -> float:
    """敏捷→移动速度（格/秒）

    使用 平方根曲线 + 基础速度 实现前期增幅快、后期递减的效果。
    旧公式: agility / 2500（纯线性，新手极慢）
    新公式: 0.1 + 0.04 * sqrt(agility)

    速度参考（200格路程耗时）:
      敏捷  5  (1级新手)  → 0.19格/秒 ≈ 18分钟
      敏捷 14  (10级)     → 0.25格/秒 ≈ 13分钟
      敏捷 50  (中期)     → 0.38格/秒 ≈ 9分钟
      敏捷 200 (后期)     → 0.67格/秒 ≈ 5分钟
      敏捷 500 (高端)     → 0.99格/秒 ≈ 3.4分钟
      敏捷 1000(极高)     → 1.37格/秒 ≈ 2.4分钟
    """
    return 0.1 + 0.04 * (agility ** 0.5)


def _euclidean_distance(x1: int, y1: int, x2: int, y2: int) -> float:
    """计算欧几里得距离，用于准确的时间预估"""
    return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5


def _format_eta(td: timedelta) -> str:
    """格式化ETA为人性化的时间显示"""
    total_seconds = int(td.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds}秒"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        if seconds > 0:
            return f"{minutes}分{seconds}秒"
        return f"{minutes}分钟"
    else:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        if minutes > 0:
            return f"{hours}小时{minutes}分"
        return f"{hours}小时"



def _move_towards(curr_x: int, curr_y: int, target_x: int, target_y: int, distance: float) -> Tuple[int, int]:
    """沿两点连线方向移动指定距离，返回新的整数坐标。"""
    if distance <= 0:
        return curr_x, curr_y

    dx = target_x - curr_x
    dy = target_y - curr_y
    current_distance = (dx * dx + dy * dy) ** 0.5

    # 如果已经到达或距离很近，直接返回目标
    if current_distance <= distance:
        return target_x, target_y

    # 计算移动比例
    ratio = distance / current_distance
    new_x = curr_x + dx * ratio
    new_y = curr_y + dy * ratio

    return round(new_x), round(new_y)


async def _update_nav_position(player: Player, task: NavigationTask | None, session=None) -> bool:
    """根据经过时间推进现实世界导航进度，返回是否到达目标。

    设计要点：
    - 导航只作用于现实世界坐标。
    - 若玩家在诡域中，则读取/写入 real_world_x, real_world_y，不影响诡域内坐标。
    - 若玩家在现实世界，则更新 x,y，同时同步 real_world_x, real_world_y。
    - 若无任务或无有效时间推进则返回 False。
    """
    if not task:
        return False

    now = datetime.now()
    elapsed = (now - task.last_update).total_seconds()
    if elapsed <= 0:
        return False

    # 获取有效敏捷值（包含临时buff加成）
    effective_agility = player.agility
    if session:
        effective_attrs = await player.get_effective_attributes(session)
        effective_agility = effective_attrs.get("agility", player.agility)

    speed = _tiles_per_second(effective_agility)
    movable_distance = elapsed * speed
    if movable_distance <= 0:
        return False

    # 读取当前用于导航的“现实世界坐标”
    # 无论在哪里，导航都基于现实世界坐标
    cx = (player.real_world_x or 0)
    cy = (player.real_world_y or 0)

    tx, ty = task.target_x, task.target_y
    new_x, new_y = _move_towards(cx, cy, tx, ty, movable_distance)
    distance_moved = _euclidean_distance(cx, cy, new_x, new_y)

    # 若整数化后仍未产生位移，则保留时间累积供下次使用
    if distance_moved == 0:
        return False

    # 写回：更新现实世界坐标，如果在现实世界则同步到x,y
    player.real_world_x = new_x
    player.real_world_y = new_y

    # 如果在现实世界，同步到兼容性字段x,y
    if not (getattr(player, "is_in_dungeon") and player.is_in_dungeon()):
        player.x, player.y = new_x, new_y

    # 将未被利用的时间余额保留，以便累积到下一次更新
    if speed > 0:
        unused_time = (movable_distance - distance_moved) / speed
        task.last_update = now - timedelta(seconds=unused_time)
    else:
        task.last_update = now

    # 判断是否抵达
    return new_x == tx and new_y == ty


@nav_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip().replace(",", " ")
    parts = [p for p in arg_text.split() if p]

    async with safe_session() as session:
        player: Player | None = await get_unified_player(session, event)
        if not player:
            await nav_cmd.finish("⛔ 请先创建角色")

        # 允许在诡域中自由设置与查看导航（导航仅作用于现实世界坐标）

        # 处理已有导航：先更新位置
        task: NavigationTask | None = await session.get(NavigationTask, player.id)
        reached = await _update_nav_position(player, task, session)
        if reached and task:
            # 已到达则删除任务记录并通知
            target_x, target_y = task.target_x, task.target_y
            nav_distance = task.initial_distance or 0

            # 生成并应用导航随机事件
            from .navigation_events import (
                generate_navigation_events,
                apply_navigation_events,
                format_navigation_events,
            )
            nav_events = generate_navigation_events(
                player, nav_distance, target_x, target_y
            )
            if nav_events:
                await apply_navigation_events(session, player, nav_events)

            await session.delete(task)
            await session.commit()

            rx, ry = (player.real_world_x or 0), (player.real_world_y or 0)
            arrival_msg = f"🎯 导航完成！已到达 ({target_x},{target_y})\n"

            # 展示途中见闻
            events_text = format_navigation_events(nav_events)
            if events_text:
                arrival_msg += events_text + "\n"

            arrival_msg += f"📍 当前坐标: ({rx},{ry})\n"
            arrival_msg += "发送【导航】可开启新导航"

            # 检查到达位置是否有地点，记录访问并检查成就
            from ..infrastructure.repositories.location_repository import LocationRepository
            from ..achievement.achievement_service import AchievementService

            location = await LocationService(LocationRepository(session)).get_location_by_coordinates(
                target_x, target_y, player.get_current_region()
            )

            if location:
                # 记录地点访问
                location_key = f"{location.region}:{location.x}:{location.y}"
                await AchievementService.add_visited_location(session, player.id, location_key)

                # 检查探索类成就
                achievement_messages = await AchievementService.check_achievements(session, player)
                if achievement_messages:
                    arrival_msg += "\n\n" + "\n\n".join(achievement_messages)

            # 慧海心元珠「行路明心」：到达新坐标永久+50理智上限（每日5次）
            from ..item.vip_huihai_xinyuan_skill import apply_visit_max_mp
            hh_msg = await apply_visit_max_mp(session, player)
            if hh_msg:
                arrival_msg += f"\n\n{hh_msg}"
                await session.commit()

            await nav_cmd.finish(arrival_msg)

        # 若未提供坐标 && 有导航，则只是查看进度（在诡域时展示现实坐标）
        if not parts:
            # 选取用于展示的现实坐标
            def _real_coords(p: Player) -> tuple[float, float]:
                # 始终返回现实世界坐标
                return float(p.real_world_x or 0), float(p.real_world_y or 0)

            if not task:
                rx, ry = _real_coords(player)
                nav_empty_msg = f"🧭 现实导航未设置\n当前现实坐标 ({rx:.1f},{ry:.1f})\n\n"
                nav_empty_msg += cmd("导航", "导航 ")
                await nav_cmd.finish(build_markdown(nav_empty_msg))

            target_x, target_y = task.target_x, task.target_y

            # -------- 计算实时展示坐标（现实世界） --------
            now_p = datetime.now()
            elapsed_p = (now_p - task.last_update).total_seconds()
            # 获取有效敏捷值（包含临时buff加成）
            effective_attrs = await player.get_effective_attributes(session)
            effective_agility = effective_attrs.get("agility", player.agility)
            speed_p = _tiles_per_second(effective_agility)
            move_distance = elapsed_p * speed_p

            base_x, base_y = _real_coords(player)
            disp_x, disp_y = base_x, base_y
            if move_distance > 0 and ((base_x != target_x) or (base_y != target_y)):
                dx = target_x - base_x
                dy = target_y - base_y
                current_distance = (dx * dx + dy * dy) ** 0.5

                if current_distance > 0:
                    # 不超越目标
                    actual_move = min(move_distance, current_distance)
                    ratio = actual_move / current_distance
                    disp_x += dx * ratio
                    disp_y += dy * ratio

            disp_x = round(disp_x, 1)
            disp_y = round(disp_y, 1)

            # 速度 & 预计剩余时间（使用欧几里得距离，基于现实坐标）
            # 使用已计算的有效敏捷值
            speed_now = speed_p  # 复用上面计算的有效速度
            rem_distance = _euclidean_distance(base_x, base_y, target_x, target_y)
            eta_sec = rem_distance / speed_now if speed_now > 0 else 0
            eta_td = timedelta(seconds=int(eta_sec))

            # 计算进度（如果有初始距离）
            from ..utils import generate_progress_bar
            progress_info = ""

            # 如果initial_distance为空（旧任务），使用剩余距离作为初始距离的下限估计
            if task.initial_distance is None or task.initial_distance <= 0:
                # 对于旧任务，无法准确计算进度，使用剩余距离作为参考
                # 但我们可以保存当前剩余距离，下次查看时就能显示进度了
                task.initial_distance = rem_distance if rem_distance > 0 else 1.0
                progress_info = "📊 进度: [更新中...] 首次查询，下次可显示\n"
            elif task.initial_distance > 0:
                # 已完成距离 = 初始距离 - 剩余距离
                completed_distance = max(0, task.initial_distance - rem_distance)
                progress_percentage = int((completed_distance / task.initial_distance) * 100)
                progress_bar = generate_progress_bar(int(completed_distance), int(task.initial_distance), length=10)
                progress_info = f"📊 进度: {progress_bar}\n"

            await session.commit()

            # 构建导航状态显示
            nav_status = f"🧭 **导航中** → 目标 ({target_x},{target_y})\n\n"
            nav_status += f"📍 当前位置: ({disp_x},{disp_y})\n"

            # 如果在诡域中，额外显示诡域位置
            if player.is_in_dungeon():
                dungeon_x, dungeon_y = player.get_current_coordinates()
                nav_status += f"🌏 诡域位置: {player.get_current_region()} ({dungeon_x},{dungeon_y})\n"

            nav_status += f"📏 剩余距离: **{rem_distance:.1f}** 格\n"
            if progress_info:
                nav_status += progress_info
            nav_status += f"🚀 速度: {speed_now:.2f} 格/秒\n"
            nav_status += f"⏱️ 预计: **{_format_eta(eta_td)}**\n\n"
            nav_status += cmd("刷新", "导航") + " | " + cmd("中断导航")

            await nav_cmd.finish(build_markdown(nav_status))

        # 智能判断：坐标导航 vs 地点导航
        is_coordinate_input = (len(parts) == 2 and all(p.lstrip("-+").isdigit() for p in parts))

        if is_coordinate_input:
            # ========== 坐标导航模式 ==========
            tx, ty = map(int, parts)
            if not (-MAX_COORD <= tx <= MAX_COORD and -MAX_COORD <= ty <= MAX_COORD):
                await nav_cmd.finish(f"⛔ 坐标必须在 { -MAX_COORD }~{ MAX_COORD } 范围内！")

            target_name = f"({tx},{ty})"
        else:
            # ========== 地点导航模式 ==========
            location_name = arg_text  # 使用完整的输入作为地点名

            if not location_name:
                await nav_cmd.finish("⛔ 请输入地点名称或坐标\n💡 示例：导航 上京 或 导航 100 200")

            from ..infrastructure.repositories.location_repository import LocationRepository

            # 实例化LocationService
            location_repo = LocationRepository(session)
            location_service = LocationService(location_repo)

            # 搜索地点（当前区域优先）
            current_region = player.get_current_region()
            locations = await location_service.search_locations_by_name(
                location_name,
                region=current_region,
                limit=5
            )

            # 如果当前区域没找到，再搜索其他区域
            if not locations:
                locations = await location_service.search_locations_by_name(
                    location_name,
                    region=None,
                    limit=5
                )

            # 兜底：打工地点只存在于打工系统的 JOB_LOCATIONS，不在 Location 表
            if not locations:
                from types import SimpleNamespace
                from ..economy.part_time_job_service import PartTimeJobService
                locations = [
                    SimpleNamespace(name=d["name"], x=d["x"], y=d["y"], region=REAL_WORLD)
                    for d in PartTimeJobService.JOB_LOCATIONS.values()
                    if location_name in d["name"]
                ][:5]

            if not locations:
                await nav_cmd.finish(
                    f"⛔ 未找到地点「{location_name}」\n"
                    "💡 提示：尝试输入地点的关键词，如「上京」「市集」等\n"
                    "💡 或使用坐标导航：导航 x y"
                )

            # 如果找到多个地点，优先精确匹配
            if len(locations) > 1:
                exact_matches = [loc for loc in locations if loc.name == location_name]
                if len(exact_matches) == 1:
                    locations = exact_matches
                else:
                    location_list = "\n".join([
                        f"{i+1}. {loc.name} ({loc.x},{loc.y}) [{loc.region}]"
                        for i, loc in enumerate(locations)
                    ])
                    await nav_cmd.finish(
                        f"🔍 找到多个匹配的地点：\n"
                        f"{location_list}\n\n"
                        f"💡 请使用【导航 x y】前往具体坐标"
                    )

            # 找到唯一地点，获取坐标
            target_location = locations[0]
            tx, ty = target_location.x, target_location.y
            target_name = target_location.name

            # 检查坐标范围
            if not (-MAX_COORD <= tx <= MAX_COORD and -MAX_COORD <= ty <= MAX_COORD):
                await nav_cmd.finish(f"⛔ 目标坐标超出导航范围！")

        # 基于现实坐标计算初始距离
        base_x, base_y = float(player.real_world_x or 0), float(player.real_world_y or 0)
        initial_distance = _euclidean_distance(base_x, base_y, tx, ty)

        if task:
            task.target_x = tx
            task.target_y = ty
            task.last_update = datetime.now()
            task.initial_distance = initial_distance
        else:
            task = NavigationTask(
                player_id=player.id,
                target_x=tx,
                target_y=ty,
                last_update=datetime.now(),
                initial_distance=initial_distance
            )
            session.add(task)

        # 速度与预计时间（使用欧几里得距离，基于现实坐标）
        # 获取有效敏捷值（包含临时buff加成）
        effective_attrs = await player.get_effective_attributes(session)
        effective_agility = effective_attrs.get("agility", player.agility)
        speed_now = _tiles_per_second(effective_agility)
        eta_td = timedelta(seconds=int(initial_distance / speed_now)) if speed_now > 0 else timedelta(seconds=0)

        await session.commit()

        # 构建导航开始消息
        rx, ry = (player.real_world_x or 0), (player.real_world_y or 0)

        # 根据是否有地点名显示不同的标题
        if target_name.startswith("("):  # 坐标模式
            nav_msg = f"⚙️ 指针静默旋转，已开始导航至 **{target_name}**\n\n"
        else:  # 地点模式
            nav_msg = f"📍 已设置导航至 **【{target_name}】**\n\n"

        nav_msg += f"📍 起点: ({rx},{ry})\n"
        nav_msg += f"🎯 终点: ({tx},{ty})\n"

        # 如果在诡域中，显示当前诡域位置
        if player.is_in_dungeon():
            dungeon_x, dungeon_y = player.get_current_coordinates()
            nav_msg += f"🌏 诡域位置: {player.get_current_region()} ({dungeon_x},{dungeon_y})\n"

        nav_msg += f"📏 总距离: **{initial_distance:.1f}** 格\n"
        nav_msg += f"🚀 速度: {speed_now:.2f} 格/秒\n"
        nav_msg += f"⏱️ 预计: **{_format_eta(eta_td)}**\n\n"
        nav_msg += cmd("查看进度", "导航") + " | " + cmd("中断导航")

        # 检查新手任务（兼容旧的"前往"命令和新的"导航"命令）
        from ..quest.novice_quest_service import NoviceQuestService
        quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(
            session, player, "command", {"command": "导航"}
        )

        if quest_completed and quest_msg:
            nav_msg += f"\n\n{quest_msg}"

        await nav_cmd.finish(build_markdown(nav_msg))


@stop_nav_cmd.handle()
async def _(event: MessageEvent):
    from ..platform_utils import get_unified_player, require_player

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        player = await require_player(session, event, stop_nav_cmd)

        task: NavigationTask | None = await session.get(NavigationTask, player.id)
        if not task:
            await stop_nav_cmd.finish("ℹ️ 当前未在导航中。")

        await _update_nav_position(player, task, session)
        await session.delete(task)
        await session.commit()
        # 展示现实坐标
        rx, ry = (player.real_world_x or 0), (player.real_world_y or 0)
        stop_msg = f"🛑 指针折断，你停在现实坐标 ({rx},{ry})\n\n"
        stop_msg += cmd("导航", "导航 ")
        await stop_nav_cmd.finish(build_markdown(stop_msg))


@find_npc_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """【查找 NPC名称】查询NPC位置"""
    npc_name = args.extract_plain_text().strip()

    if not npc_name:
        await find_npc_cmd.finish(
            "⛔ 请输入NPC名称，例如：查找 商人\n\n"
            "💡 支持模糊搜索，可以输入名称的一部分"
        )

    # 定义session_factory
    def session_factory():
        return AsyncSessionLocal()

    # 使用UnitOfWork管理会话
    async with UnitOfWork(session_factory) as uow:
        player: Player | None = await get_unified_player(uow.session, event)
        if not player:
            await find_npc_cmd.finish("⛔ 请先创建角色")

        # 实例化Service
        npc_service = NPCService(uow.session, uow.npcs)
        location_service = LocationService(uow.locations)

        # 搜索NPC（不限定地点）
        npcs = await npc_service.find_npc_by_partial_name(npc_name, location_id=None)

        if not npcs:
            await find_npc_cmd.finish(
                f"⛔ 未找到NPC「{npc_name}」\n"
                "💡 提示：尝试输入NPC名称的关键词\n"
                "💡 如果数据库为空，请先执行【初始化地点】命令"
            )

        # 按距离排序（优先显示最近的NPC）
        player_x = player.real_world_x or 0
        player_y = player.real_world_y or 0

        # 获取NPC对应的Location信息并计算距离
        # NPCRepository已经预加载了location，直接使用npc.location
        npc_info_list = []
        for npc in npcs[:10]:  # 最多显示10个结果
            # 使用已预加载的location关系
            location = npc.location
            if not location:
                continue

            # 计算曼哈顿距离
            distance = abs(location.x - player_x) + abs(location.y - player_y)

            npc_info_list.append({
                "npc": npc,
                "location": location,
                "distance": distance
            })

        # 按距离排序
        npc_info_list.sort(key=lambda x: x["distance"])

        # 构建结果消息
        if len(npc_info_list) == 1:
            # 只有一个结果，显示详细信息
            info = npc_info_list[0]
            npc = info["npc"]
            location = info["location"]
            distance = info["distance"]

            result_msg = f"🔍 找到NPC：{npc.name}\n"
            result_msg += "━━━━━━━━━━━━━\n"
            result_msg += f"📍 位置：{location.name}\n"
            result_msg += f"🗺️ 坐标：({location.x},{location.y})\n"
            result_msg += f"🌏 区域：{location.region}\n"
            result_msg += f"📏 距离：{distance} 格\n"
            result_msg += "━━━━━━━━━━━━━\n"
            result_msg += f"💡 【前往 {location.name}】快速导航"

        else:
            # 多个结果，显示列表
            result_msg = f"🔍 找到 {len(npc_info_list)} 个匹配的NPC：\n"
            result_msg += "━━━━━━━━━━━━━\n"

            for i, info in enumerate(npc_info_list[:5], 1):  # 最多显示5个
                npc = info["npc"]
                location = info["location"]
                distance = info["distance"]

                result_msg += f"{i}. {npc.name}\n"
                result_msg += f"   📍 {location.name} ({location.x},{location.y})\n"
                result_msg += f"   📏 {distance} 格 [{location.region}]\n"

            if len(npc_info_list) > 5:
                result_msg += f"\n...还有 {len(npc_info_list) - 5} 个结果\n"

            result_msg += "━━━━━━━━━━━━━\n"
            result_msg += "💡 【前往 地点名】快速导航至指定地点"

        await find_npc_cmd.finish(message_add_head(result_msg, event))


@check_data_cmd.handle()
async def _(event: MessageEvent):
    """【检查数据】调试命令 - 检查Location和NPC数据状态"""
    # 定义session_factory
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        location_service = LocationService(uow.locations)
        npc_service = NPCService(uow.session, uow.npcs)

        # 统计Location数量
        from sqlalchemy import select, func
        from ..models.location import Location
        from ..models.npc import NPC

        loc_count_stmt = select(func.count()).select_from(Location).where(Location.is_active == True)
        loc_count = (await uow.session.execute(loc_count_stmt)).scalar()

        npc_count_stmt = select(func.count()).select_from(NPC).where(NPC.is_active == True)
        npc_count = (await uow.session.execute(npc_count_stmt)).scalar()

        # 获取前5个Location示例
        loc_sample_stmt = select(Location).where(Location.is_active == True).limit(5)
        loc_samples = (await uow.session.execute(loc_sample_stmt)).scalars().all()

        # 获取前5个NPC示例
        npc_sample_stmt = select(NPC).where(NPC.is_active == True).limit(5)
        npc_samples = (await uow.session.execute(npc_sample_stmt)).scalars().all()

        msg = "📊 数据库状态检查\n"
        msg += "━━━━━━━━━━━━━\n"
        msg += f"📍 Location总数: {loc_count}\n"
        msg += f"👤 NPC总数: {npc_count}\n"
        msg += "━━━━━━━━━━━━━\n"

        if loc_samples:
            msg += "📍 Location示例:\n"
            for loc in loc_samples:
                msg += f"  • {loc.name} ({loc.x},{loc.y})\n"
        else:
            msg += "⚠️ 没有Location数据！\n"

        msg += "━━━━━━━━━━━━━\n"

        if npc_samples:
            msg += "👤 NPC示例:\n"
            for npc in npc_samples:
                msg += f"  • {npc.name} [{npc.npc_type.value}]\n"
        else:
            msg += "⚠️ 没有NPC数据！\n"

        msg += "━━━━━━━━━━━━━\n"
        if loc_count == 0 or npc_count == 0:
            msg += "💡 请执行【初始化地点】命令初始化数据"


# ─────────────────────────────────────────────
# 导航到达群提醒（每 2 分钟轮询）
# ─────────────────────────────────────────────

from nonebot import logger as _logger
from nonebot_plugin_apscheduler import scheduler as _scheduler
from sqlalchemy import select as _select


@_scheduler.scheduled_job(
    "interval", minutes=2, id="nav_arrival_push", max_instances=1, coalesce=True
)
async def _check_nav_arrivals():
    """轮询所有导航任务，到达时在最近活跃群 @ 玩家。"""
    from ..models.db import AsyncSessionLocal
    from ..models.player import Player
    from ..notification_service import notify_player
    from .navigation_events import (
        generate_navigation_events,
        apply_navigation_events,
        format_navigation_events,
    )

    try:
        async with AsyncSessionLocal() as session:
            tasks = (await session.execute(_select(NavigationTask))).scalars().all()
            if not tasks:
                return

            for task in tasks:
                try:
                    player: Player | None = await session.get(Player, task.player_id)
                    if not player:
                        await session.delete(task)
                        continue

                    reached = await _update_nav_position(player, task, session)
                    session.add(player)

                    if not reached:
                        continue

                    # 到达：处理随机事件
                    target_x, target_y = task.target_x, task.target_y
                    nav_distance = task.initial_distance or 0
                    nav_events = generate_navigation_events(player, nav_distance, target_x, target_y)
                    if nav_events:
                        await apply_navigation_events(session, player, nav_events)

                    await session.delete(task)

                    # 组织通知文本（群提醒只发送纯文本）
                    rx, ry = player.real_world_x or 0, player.real_world_y or 0
                    lines = [f"🎯 导航完成！已到达 ({target_x},{target_y})"]
                    events_text = format_navigation_events(nav_events) if nav_events else ""
                    if events_text:
                        lines.append(events_text.replace("**", "").replace("*", ""))
                    lines.append(f"📍 当前坐标: ({rx},{ry})")
                    lines.append("发送【导航】可开启新导航")

                    await notify_player(
                        player.id,
                        "\n".join(lines),
                        session,
                    )

                except Exception as e:
                    _logger.warning(f"[Nav] 处理导航任务 {task.player_id} 失败: {e}")

            await session.commit()

    except Exception as e:
        _logger.error(f"[Nav] 导航到达轮询失败: {e}", exc_info=True)
