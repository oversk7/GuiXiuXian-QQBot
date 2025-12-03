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
from ..models.navigation_task import NavigationTask
from ..platform_utils import get_unified_player
from ..infrastructure.uow.unit_of_work import UnitOfWork
from .location_service_new import LocationService
from .npc_service_new import NPCService

# ----------------- 持久化模型 -----------------

# ----------------- 常量 -----------------
# 坐标正负范围
MAX_COORD = 500
REAL_WORLD = "大都会"

# ----------------- 指令：导航 -----------------
nav_cmd = on_command("导航", block=True, priority=5)
goto_location_cmd = on_command("前往", block=True, priority=5)
find_npc_cmd = on_command("查找", block=True, priority=5)
check_data_cmd = on_command("检查数据", block=True, priority=5)
stop_nav_cmd = on_command("中断导航", aliases={"停止导航", "取消导航"}, block=True, priority=5)


def _tiles_per_second(agility: int) -> float:
    return max(0.01, agility / 2500)


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
            await session.delete(task)
            await session.commit()

            rx, ry = (player.real_world_x or 0), (player.real_world_y or 0)
            arrival_msg = f"🎯 已到达目标位置 ({target_x},{target_y})\n"
            arrival_msg += "━━━━━━━━━━━━━\n"
            arrival_msg += f"📍 当前坐标: ({rx},{ry})\n"
            arrival_msg += "✅ 导航任务已完成"

            await nav_cmd.finish(message_add_head(arrival_msg, event))

        # 若未提供坐标 && 有导航，则只是查看进度（在诡域时展示现实坐标）
        if not parts:
            # 选取用于展示的现实坐标
            def _real_coords(p: Player) -> tuple[float, float]:
                # 始终返回现实世界坐标
                return float(p.real_world_x or 0), float(p.real_world_y or 0)

            if not task:
                rx, ry = _real_coords(player)
                await nav_cmd.finish(message_add_head(
                    f"🧭 现实导航未设置\n当前现实坐标 ({rx:.1f},{ry:.1f})", event))

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
                progress_info = "📊 进度: [更新中...] (旧任务重新计算)\n"
            elif task.initial_distance > 0:
                # 已完成距离 = 初始距离 - 剩余距离
                completed_distance = max(0, task.initial_distance - rem_distance)
                progress_percentage = int((completed_distance / task.initial_distance) * 100)
                progress_bar = generate_progress_bar(int(completed_distance), int(task.initial_distance), length=10)
                progress_info = f"📊 进度: {progress_bar}\n"

            await session.commit()

            # 构建导航状态显示
            nav_status = f"🧭 导航中 → 目标 ({target_x},{target_y})\n"
            nav_status += "━━━━━━━━━━━━━\n"
            nav_status += f"📍 当前位置: ({disp_x},{disp_y})\n"

            # 如果在诡域中，额外显示诡域位置
            if player.is_in_dungeon():
                dungeon_x, dungeon_y = player.get_current_coordinates()
                nav_status += f"🌏 诡域位置: {player.get_current_region()} ({dungeon_x},{dungeon_y})\n"

            nav_status += f"📏 剩余距离: {rem_distance:.1f} 格\n"
            if progress_info:
                nav_status += progress_info
            nav_status += f"🚀 速度: {speed_now:.2f} 格/秒\n"
            nav_status += f"⏱️ 预计: {_format_eta(eta_td)}\n"
            nav_status += "━━━━━━━━━━━━━\n"
            nav_status += "💡 【中断导航】停止前进"

            await nav_cmd.finish(message_add_head(nav_status, event))

        # 若提供坐标，则尝试开启/重设导航
        if len(parts) != 2 or not all(p.lstrip("-+").isdigit() for p in parts):
            await nav_cmd.finish("⛔ 格式错误，正确用法：导航 x y  （示例：导航 100 200）")
        tx, ty = map(int, parts)
        if not (-MAX_COORD <= tx <= MAX_COORD and -MAX_COORD <= ty <= MAX_COORD):
            await nav_cmd.finish(f"⛔ 坐标必须在 { -MAX_COORD }~{ MAX_COORD } 范围内！")

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
        nav_msg = f"⚙️ 指针静默旋转，已开始导航至 ({tx},{ty})\n"
        nav_msg += "━━━━━━━━━━━━━\n"
        nav_msg += f"📍 起点: ({rx},{ry})\n"
        nav_msg += f"🎯 终点: ({tx},{ty})\n"

        # 如果在诡域中，显示当前诡域位置
        if player.is_in_dungeon():
            dungeon_x, dungeon_y = player.get_current_coordinates()
            nav_msg += f"🌏 诡域位置: {player.get_current_region()} ({dungeon_x},{dungeon_y})\n"

        nav_msg += f"📏 总距离: {initial_distance:.1f} 格\n"
        nav_msg += f"🚀 速度: {speed_now:.2f} 格/秒\n"
        nav_msg += f"⏱️ 预计: {_format_eta(eta_td)}\n"
        nav_msg += "━━━━━━━━━━━━━\n"
        nav_msg += "💡 【导航】查看进度 | 【中断导航】停止前进"

        await nav_cmd.finish(message_add_head(nav_msg, event))


@stop_nav_cmd.handle()
async def _(event: MessageEvent):
    from ..platform_utils import get_unified_player, is_guild_message

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await stop_nav_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await stop_nav_cmd.finish("⛔ 请先创建角色")

        task: NavigationTask | None = await session.get(NavigationTask, player.id)
        if not task:
            await stop_nav_cmd.finish("ℹ️ 当前未在导航中。")

        await _update_nav_position(player, task, session)
        await session.delete(task)
        await session.commit()
        # 展示现实坐标
        rx, ry = (player.real_world_x or 0), (player.real_world_y or 0)
        await stop_nav_cmd.finish(message_add_head(
            f"🛑 指针折断，你停在现实坐标 ({rx},{ry})", event))


@goto_location_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """【前往 地点名】快速导航到指定地点"""
    location_name = args.extract_plain_text().strip()

    if not location_name:
        await goto_location_cmd.finish("⛔ 请输入地点名称，例如：前往 上京")

    # 定义session_factory
    def session_factory():
        return AsyncSessionLocal()

    # 使用UnitOfWork管理会话和LocationService
    async with UnitOfWork(session_factory) as uow:
        player: Player | None = await get_unified_player(uow.session, event)
        if not player:
            await goto_location_cmd.finish("⛔ 请先创建角色")

        # 实例化LocationService
        location_service = LocationService(uow.locations)

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

        if not locations:
            await goto_location_cmd.finish(
                f"⛔ 未找到地点「{location_name}」\n"
                "💡 提示：尝试输入地点的关键词，如「上京」「市集」等\n"
                "💡 如果数据库为空，请先执行【初始化地点】命令"
            )

        # 如果找到多个地点，显示选项让用户确认
        if len(locations) > 1:
            location_list = "\n".join([
                f"{i+1}. {loc.name} ({loc.x},{loc.y}) [{loc.region}]"
                for i, loc in enumerate(locations)
            ])
            await goto_location_cmd.finish(
                f"🔍 找到多个匹配的地点：\n"
                f"{location_list}\n\n"
                f"💡 请使用【导航 x y】前往具体坐标"
            )

        # 找到唯一地点，开始导航
        target_location = locations[0]
        tx, ty = target_location.x, target_location.y

        # 检查坐标范围
        if not (-MAX_COORD <= tx <= MAX_COORD and -MAX_COORD <= ty <= MAX_COORD):
            await goto_location_cmd.finish(f"⛔ 目标坐标超出导航范围！")

        # 基于现实坐标计算初始距离
        base_x, base_y = float(player.real_world_x or 0), float(player.real_world_y or 0)
        initial_distance = _euclidean_distance(base_x, base_y, tx, ty)

        # 创建或更新导航任务
        task: NavigationTask | None = await uow.session.get(NavigationTask, player.id)
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
            uow.session.add(task)

        # 计算距离和预计时间
        effective_attrs = await player.get_effective_attributes(uow.session)
        effective_agility = effective_attrs.get("agility", player.agility)
        speed_now = _tiles_per_second(effective_agility)
        eta_td = timedelta(seconds=int(initial_distance / speed_now)) if speed_now > 0 else timedelta(seconds=0)

        # 提交事务
        await uow.commit()

        # 构建导航消息
        rx, ry = (player.real_world_x or 0), (player.real_world_y or 0)
        nav_msg = f"📍 已设置导航至【{target_location.name}】\n"
        nav_msg += "━━━━━━━━━━━━━\n"
        nav_msg += f"📍 起点: ({rx},{ry})\n"
        nav_msg += f"🎯 终点: ({tx},{ty})\n"

        # 如果在诡域中，显示诡域位置
        if player.is_in_dungeon():
            dungeon_x, dungeon_y = player.get_current_coordinates()
            nav_msg += f"🌏 诡域位置: {player.get_current_region()} ({dungeon_x},{dungeon_y})\n"

        nav_msg += f"📏 总距离: {initial_distance:.1f} 格\n"
        nav_msg += f"🚀 速度: {speed_now:.2f} 格/秒\n"
        nav_msg += f"⏱️ 预计: {_format_eta(eta_td)}\n"
        nav_msg += "━━━━━━━━━━━━━\n"
        nav_msg += "💡 【导航】查看进度 | 【中断导航】停止前进"

        await goto_location_cmd.finish(message_add_head(nav_msg, event))


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

        await check_data_cmd.finish(message_add_head(msg, event))