from __future__ import annotations

"""自动导航功能（现实世界可用）

设定：
1. 仅当玩家位于现实世界（region == "大都市"）时可使用导航。
2. 指令：
   • 导航 x y      → 开启/查看导航进度
   • 中断导航      → 取消当前导航
3. 导航过程中不会主动推送消息，位置更新在玩家下一次触发相关指令时计算。
4. 速度公式：tiles_per_second = max(0.2, player.agility / 30)
5. 坐标范围限制：0 ≤ x,y ≤ 1000
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from datetime import datetime
from typing import Dict, Any, Tuple
from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head

# ----------------- 全局导航状态 -----------------
# { player_id: {"target":(tx,ty), "last":datetime } }
NAV_STATES: Dict[str, Dict[str, Any]] = {}

# ----------------- 常量 -----------------
MAX_COORD = 1000
REAL_WORLD = "大都市"

# ----------------- 指令：导航 -----------------
nav_cmd = on_command("导航", block=True, priority=5)
stop_nav_cmd = on_command("中断导航", aliases={"停止导航", "取消导航"}, block=True, priority=5)


def _tiles_per_second(agility: int) -> float:
    return max(0.01, agility / 1500)


def _step_towards(curr_x: int, curr_y: int, target_x: int, target_y: int, steps: int) -> Tuple[int, int]:
    """沿两点连线方向移动 steps 格，使用 Bresenham 算法近似直线。"""
    x, y = curr_x, curr_y
    if steps <= 0:
        return x, y

    dx_total = abs(target_x - x)
    dy_total = abs(target_y - y)
    sx = 1 if target_x > x else -1 if target_x < x else 0
    sy = 1 if target_y > y else -1 if target_y < y else 0

    err = dx_total - dy_total

    while steps > 0 and (x != target_x or y != target_y):
        e2 = err * 2
        if e2 > -dy_total:
            err -= dy_total
            x += sx
            steps -= 1
            if steps == 0 or (x == target_x and y == target_y):
                break
        if e2 < dx_total and steps > 0:
            err += dx_total
            y += sy
            steps -= 1
    return x, y


def _update_nav_position(player: Player) -> bool:
    """根据经过时间更新玩家坐标，返回是否到达目标。"""
    state = NAV_STATES.get(player.id)
    if not state:
        return False

    now = datetime.now()
    elapsed = (now - state["last"]).total_seconds()
    if elapsed <= 0:
        return False

    speed = _tiles_per_second(player.agility)
    movable = int(elapsed * speed)
    if movable <= 0:
        return False

    cx, cy = player.x, player.y
    tx, ty = state["target"]
    new_x, new_y = _step_towards(cx, cy, tx, ty, movable)

    player.x, player.y = new_x, new_y
    state["last"] = now

    # 判断是否抵达
    if new_x == tx and new_y == ty:
        NAV_STATES.pop(player.id, None)
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
            await nav_cmd.finish("⛔ 诡域中迷雾缭绕，无法使用导航！请使用 [移动] 或 [探索]。")

        # 处理已有导航：先更新位置
        reached = _update_nav_position(player)

        # 若未提供坐标 && 有导航，则只是查看进度
        if not parts:
            if player.id not in NAV_STATES:
                await nav_cmd.finish(message_add_head(f"🧭 当前位置 {player.region} ({player.x},{player.y})\n暂无导航目标。", event))
            target_x, target_y = NAV_STATES[player.id]["target"]

            # -------- 计算带小数的展示坐标 --------
            state = NAV_STATES[player.id]
            now_p = datetime.now()
            elapsed_p = (now_p - state["last"]).total_seconds()
            speed_p = _tiles_per_second(player.agility)
            frac_move = elapsed_p * speed_p  # 可能小于1

            disp_x, disp_y = float(player.x), float(player.y)
            if frac_move > 0 and (player.x != target_x or player.y != target_y):
                dx_r = target_x - player.x
                dy_r = target_y - player.y
                steps_rem = max(abs(dx_r), abs(dy_r))
                if steps_rem > 0:
                    unit_x = dx_r / steps_rem
                    unit_y = dy_r / steps_rem
                    # 不超越目标
                    move_dist = min(frac_move, steps_rem)
                    disp_x += unit_x * move_dist
                    disp_y += unit_y * move_dist
            disp_x = round(disp_x, 1)
            disp_y = round(disp_y, 1)

            await session.commit()
            await nav_cmd.finish(message_add_head(
                f"🧭 导航中 → 目标 ({target_x},{target_y})\n▶️ 当前坐标 ({disp_x},{disp_y})", event))

        # 若提供坐标，则尝试开启/重设导航
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            await nav_cmd.finish("⛔ 格式错误，正确用法：导航 x y  （示例：导航 100 200）")
        tx, ty = map(int, parts)
        if not (0 <= tx <= MAX_COORD and 0 <= ty <= MAX_COORD):
            await nav_cmd.finish(f"⛔ 坐标必须在 0~{MAX_COORD} 范围内！")

        NAV_STATES[player.id] = {"target": (tx, ty), "last": datetime.now()}
        await session.commit()
        await nav_cmd.finish(message_add_head(
            f"⚙️ 指针静默旋转，已开始导航至 ({tx},{ty})。\n━━━━━━━━━━━━━\n✧ 当前坐标 ({player.x},{player.y})\n━━━━━━━━━━━━━\n⬇️ 【中断导航】停止前进", event))


@stop_nav_cmd.handle()
async def _(event: MessageEvent):
    pid = event.get_user_id()
    if pid in NAV_STATES:
        async with safe_session() as session:
            player = await session.get(Player, pid)
            # 先根据经过时间更新一次坐标，走多少算多少
            _update_nav_position(player)
            # 移除导航状态
            NAV_STATES.pop(pid, None)
            await session.commit()
        await stop_nav_cmd.finish(message_add_head(
            f"🛑 指针折断，你停在 ({player.x},{player.y})", event))
    else:
        await stop_nav_cmd.finish("ℹ️ 当前未在导航中。") 