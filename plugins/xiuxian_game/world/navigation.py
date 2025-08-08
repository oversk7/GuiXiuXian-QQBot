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


def _update_nav_position(player: Player, task: NavigationTask | None) -> bool:
    """根据经过时间更新玩家坐标，返回是否到达目标。若无任务返回 False."""
    if not task:
        return False

    now = datetime.now()
    elapsed = (now - task.last_update).total_seconds()
    if elapsed <= 0:
        return False

    speed = _tiles_per_second(player.agility)
    movable_distance = elapsed * speed
    if movable_distance <= 0:
        return False

    cx, cy = player.x, player.y
    tx, ty = task.target_x, task.target_y
    new_x, new_y = _move_towards(cx, cy, tx, ty, movable_distance)

    player.x, player.y = new_x, new_y
    task.last_update = now

    # 判断是否抵达
    if new_x == tx and new_y == ty:
        return True
    return False


@nav_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip().replace(",", " ")
    parts = [p for p in arg_text.split() if p]

    async with safe_session() as session:
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await nav_cmd.finish("⛔ 请先创建角色")

        # 如非现实世界，提示不可导航
        if player.region != REAL_WORLD:
            await nav_cmd.finish("⛔ 诡域中迷雾缭绕，无法使用导航！请使用【上|下|左|右】移动，或【返回】现实世界")

        # 处理已有导航：先更新位置
        task: NavigationTask | None = await session.get(NavigationTask, player.id)
        reached = _update_nav_position(player, task)
        if reached and task:
            # 已到达则删除任务记录
            await session.delete(task)

        # 若未提供坐标 && 有导航，则只是查看进度
        if not parts:
            if not task:
                await nav_cmd.finish(message_add_head(f"🧭 当前位置 {player.region} ({player.x},{player.y})\n暂无导航目标。", event))
            target_x, target_y = task.target_x, task.target_y

            # -------- 计算实时展示坐标 --------
            now_p = datetime.now()
            elapsed_p = (now_p - task.last_update).total_seconds()
            speed_p = _tiles_per_second(player.agility)
            move_distance = elapsed_p * speed_p

            disp_x, disp_y = float(player.x), float(player.y)
            if move_distance > 0 and (player.x != target_x or player.y != target_y):
                dx = target_x - player.x
                dy = target_y - player.y
                current_distance = (dx * dx + dy * dy) ** 0.5

                if current_distance > 0:
                    # 不超越目标
                    actual_move = min(move_distance, current_distance)
                    ratio = actual_move / current_distance
                    disp_x += dx * ratio
                    disp_y += dy * ratio

            disp_x = round(disp_x, 1)
            disp_y = round(disp_y, 1)

            # 速度 & 预计剩余时间（使用欧几里得距离）
            speed_now = _tiles_per_second(player.agility)
            rem_distance = _euclidean_distance(player.x, player.y, target_x, target_y)
            eta_sec = rem_distance / speed_now if speed_now > 0 else 0
            eta_td = timedelta(seconds=int(eta_sec))

            await session.commit()
            await nav_cmd.finish(message_add_head(
                f"🧭 导航中 → 目标 ({target_x},{target_y})\n"
                f"▶️ 当前坐标 ({disp_x},{disp_y})\n"
                f"🕒 速度 {speed_now:.2f} 格/秒  预计剩余 {str(eta_td)}", event))

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
        # 速度与预计时间（使用欧几里得距离）
        speed_now = _tiles_per_second(player.agility)
        rem_distance = _euclidean_distance(player.x, player.y, tx, ty)
        eta_td = timedelta(seconds=int(rem_distance / speed_now)) if speed_now > 0 else timedelta(seconds=0)

        await session.commit()
        await nav_cmd.finish(message_add_head(
            f"⚙️ 指针静默旋转，已开始导航至 ({tx},{ty})。\n"
            "━━━━━━━━━━━━━\n"
            f"✧ 当前坐标 ({player.x},{player.y})\n"
            f"🕒 速度 {speed_now:.2f} 格/秒  预计耗时 {str(eta_td)}\n"
            "━━━━━━━━━━━━━\n⬇️ 【中断导航】停止前进", event))


@stop_nav_cmd.handle()
async def _(event: MessageEvent):
    pid = event.get_user_id()
    async with safe_session() as session:
        player = await session.get(Player, pid)
        task: NavigationTask | None = await session.get(NavigationTask, pid)
        if not task:
            await stop_nav_cmd.finish("ℹ️ 当前未在导航中。")

        _update_nav_position(player, task)
        await session.delete(task)
        await session.commit()
        await stop_nav_cmd.finish(message_add_head(
            f"🛑 指针折断，你停在 ({player.x},{player.y})", event)) 