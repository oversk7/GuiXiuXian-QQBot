from __future__ import annotations

"""自动导航功能（现实世界可用）

设定：
1. 仅当玩家位于现实世界（region == "大都市"）时可使用导航。
2. 指令：
   • 导航 x y      → 开启/查看导航进度
   • 中断导航      → 取消当前导航
3. 导航过程中不会主动推送消息，位置更新在玩家下一次触发相关指令时计算。
4. 坐标范围限制：-500 ≤ x,y ≤ 500
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from datetime import datetime, timedelta
from typing import Tuple
from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from ..models.navigation_task import NavigationTask
from ..platform_utils import get_unified_player

# ----------------- 持久化模型 -----------------

# ----------------- 常量 -----------------
# 坐标正负范围
MAX_COORD = 500
REAL_WORLD = "大都会"

# ----------------- 指令：导航 -----------------
nav_cmd = on_command("导航", block=True, priority=5)
stop_nav_cmd = on_command("中断导航", aliases={"停止导航", "取消导航"}, block=True, priority=5)


def _tiles_per_second(agility: int) -> float:
    return max(0.01, agility / 2500)


def _euclidean_distance(x1: int, y1: int, x2: int, y2: int) -> float:
    """计算欧几里得距离，用于准确的时间预估"""
    return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5



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
            # 已到达则删除任务记录
            await session.delete(task)

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

            await session.commit()

            # 构建导航状态显示
            nav_status = f"🧭 导航中 → 目标 ({target_x},{target_y})\n"
            nav_status += f"▶️ 现实坐标 ({disp_x},{disp_y})\n"

            # 如果在诡域中，额外显示诡域位置
            if player.is_in_dungeon():
                dungeon_x, dungeon_y = player.get_current_coordinates()
                nav_status += f"🌏 当前位置 {player.get_current_region()} ({dungeon_x},{dungeon_y})\n"

            nav_status += f"🕒 速度 {speed_now:.2f} 格/秒  预计剩余 {str(eta_td)}"

            await nav_cmd.finish(message_add_head(nav_status, event))

        # 若提供坐标，则尝试开启/重设导航
        if len(parts) != 2 or not all(p.lstrip("-+").isdigit() for p in parts):
            await nav_cmd.finish("⛔ 格式错误，正确用法：导航 x y  （示例：导航 100 200）")
        tx, ty = map(int, parts)
        if not (-MAX_COORD <= tx <= MAX_COORD and -MAX_COORD <= ty <= MAX_COORD):
            await nav_cmd.finish(f"⛔ 坐标必须在 { -MAX_COORD }~{ MAX_COORD } 范围内！")

        if task:
            task.target_x = tx
            task.target_y = ty
            task.last_update = datetime.now()
        else:
            task = NavigationTask(player_id=player.id, target_x=tx, target_y=ty, last_update=datetime.now())
            session.add(task)
        # 速度与预计时间（使用欧几里得距离，基于现实坐标）
        # 获取有效敏捷值（包含临时buff加成）
        effective_attrs = await player.get_effective_attributes(session)
        effective_agility = effective_attrs.get("agility", player.agility)
        speed_now = _tiles_per_second(effective_agility)
        # 基于现实坐标计算剩余距离
        base_x, base_y = float(player.real_world_x or 0), float(player.real_world_y or 0)
        rem_distance = _euclidean_distance(base_x, base_y, tx, ty)
        eta_td = timedelta(seconds=int(rem_distance / speed_now)) if speed_now > 0 else timedelta(seconds=0)

        await session.commit()

        # 构建导航开始消息
        rx, ry = (player.real_world_x or 0), (player.real_world_y or 0)
        nav_msg = f"⚙️ 指针静默旋转，已开始导航至 ({tx},{ty})。\n"
        nav_msg += "━━━━━━━━━━━━━\n"
        nav_msg += f"✧ 现实坐标 ({rx},{ry})\n"

        # 如果在诡域中，显示当前诡域位置
        if player.is_in_dungeon():
            dungeon_x, dungeon_y = player.get_current_coordinates()
            nav_msg += f"🌏 当前位置 {player.get_current_region()} ({dungeon_x},{dungeon_y})\n"

        nav_msg += f"🕒 速度 {speed_now:.2f} 格/秒  预计耗时 {str(eta_td)}\n"
        nav_msg += "━━━━━━━━━━━━━\n⬇️ 【中断导航】停止前进"

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