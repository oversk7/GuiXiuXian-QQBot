"""
龙影闪·虚界锚钉 —— VIP定制装备「龙影闪」主动技能模块

功能：
- 锚钉 设置 <名称>   在当前位置撕开虚界裂隙设锚钉（最多3个）
- 锚钉 传送 <编号>   穿越虚界传送（CD5分钟，消耗5%最大理智）
- 锚钉 携带 <UID> <编号>  拉对方一同穿越（对方需回复【同意穿越】）
- 锚钉 删除 <编号>   缝合裂隙拔除锚钉
- 锚钉              查看龙影闪状态面板（含锚钉列表）
"""

import copy
from datetime import datetime, timedelta, date
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..platform_utils import require_player
from ..utils import message_add_head
from ..utils_markdown import build_markdown, cmd, color_text

# ==================== 常量 ====================
EQUIPMENT_ID = "vip_longying_flash"
MAX_ANCHORS = 3          # 最多锚钉数
TELEPORT_CD_SECONDS = 300  # 传送冷却5分钟
MP_COST_RATIO = 0.05     # 消耗5%最大理智
CARRY_TIMEOUT_SECONDS = 120  # 携带穿越等待超时2分钟

# 龙影闪配图
LONGYING_IMG_URL = "https://wdcdn.qpic.cn/MTMxMDI2NjM3MjM0Njk2MTE_885885_Y_YQIqWr8ubL6pAL_1771136869"

# 临时存储：等待确认的携带穿越请求（独立于归雨的字典）
# 格式: {target_player_id: {"from_id": str, "anchor": dict, "expire": datetime}}
_pending_carry_requests_longying: dict = {}


async def _send_longying_markdown(handler, content: str, fallback_text: str, event: MessageEvent):
    """使用原生Markdown发送龙影闪反馈，失败时回退到纯文本"""
    try:
        await handler.finish(build_markdown(content))
    except (ValueError, TypeError, KeyError):
        # Markdown构建失败，回退到纯文本
        await handler.finish(message_add_head(fallback_text, event))


# ==================== 辅助函数 ====================

async def _get_longying_instance(session, player_id: str) -> ItemInstance | None:
    """查找玩家已装备的龙影闪"""
    stmt = select(ItemInstance).where(
        ItemInstance.player_id == player_id,
        ItemInstance.equipped == True,
        ItemInstance.item_id == EQUIPMENT_ID,
    )
    return (await session.execute(stmt)).scalars().first()


def _get_anchors(player: Player) -> list[dict]:
    """获取玩家的锚钉列表（返回深拷贝，避免意外修改MutableDict内部数据）"""
    data = player.vip_equipment_data or {}
    return copy.deepcopy(data.get("longying_anchors", []))


def _set_anchors(player: Player, anchors: list[dict]):
    """设置玩家的锚钉列表（通过重建整个dict确保SQLAlchemy检测到变更）"""
    data = dict(player.vip_equipment_data or {})
    data["longying_anchors"] = copy.deepcopy(anchors)
    player.vip_equipment_data = data


def _get_teleport_cd(player: Player) -> datetime | None:
    """获取传送冷却结束时间"""
    cd_data = player.vip_skill_cooldown or {}
    cd_str = cd_data.get("longying_teleport")
    if cd_str:
        try:
            return datetime.fromisoformat(cd_str)
        except (ValueError, TypeError):
            pass
    return None


def _set_teleport_cd(player: Player):
    """设置传送冷却"""
    cd_data = dict(player.vip_skill_cooldown or {})
    cd_data["longying_teleport"] = (datetime.now() + timedelta(seconds=TELEPORT_CD_SECONDS)).isoformat()
    player.vip_skill_cooldown = cd_data


def _format_anchor(idx: int, anchor: dict) -> str:
    """格式化单个锚钉信息"""
    name = anchor.get("name", "未命名")
    region = anchor.get("region", "未知")
    x, y = anchor.get("x", 0), anchor.get("y", 0)
    # 如果是诡域锚钉
    dungeon_level = anchor.get("dungeon_level", 0)
    if dungeon_level > 0:
        return f"  [{idx}] 📍 {name} — {dungeon_level}层诡域 ({x},{y})"
    else:
        return f"  [{idx}] 📍 {name} — 大都会 ({x},{y})"


def _teleport_player_to_anchor(player: Player, anchor: dict):
    """将玩家传送到指定锚钉"""
    dungeon_level = anchor.get("dungeon_level", 0)
    target_x = anchor.get("x", 0)
    target_y = anchor.get("y", 0)

    if dungeon_level > 0:
        # 传送到诡域
        if not player.is_in_dungeon():
            # 从现实世界传送到诡域：需要先保存现实坐标
            player.enter_dungeon(dungeon_level)
        elif player.dungeon_level != dungeon_level:
            # 跨诡域层传送
            player.dungeon_level = dungeon_level
            player.region = f"{dungeon_level}层诡域"
        # 设置诡域坐标
        player.dungeon_x = target_x
        player.dungeon_y = target_y
        player.x = target_x
        player.y = target_y
    else:
        # 传送到现实世界
        if player.is_in_dungeon():
            player.exit_dungeon()
        # 设置现实世界坐标
        player.real_world_x = target_x
        player.real_world_y = target_y
        player.x = target_x
        player.y = target_y


# ==================== 指令：锚钉 ====================
anchor_cmd = on_command("锚钉", block=True, priority=9)


@anchor_cmd.handle()
async def handle_anchor(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()

    async with safe_session() as session:
        player = await require_player(session, event, anchor_cmd)

        # 检查是否装备了龙影闪
        longying = await _get_longying_instance(session, player.id)
        if not longying:
            await anchor_cmd.finish("⛔ 你未装备「龙影闪」，无法使用锚钉技能")

        # 解析子命令
        parts = arg.split(None, 2) if arg else []
        sub_cmd = parts[0] if parts else ""

        if sub_cmd == "设置":
            await _handle_set_anchor(session, player, parts, event)
        elif sub_cmd == "传送":
            await _handle_teleport(session, player, parts, event)
        elif sub_cmd == "携带":
            await _handle_carry(session, player, parts, event)
        elif sub_cmd == "删除":
            await _handle_delete_anchor(session, player, parts, event)
        else:
            # 默认：显示锚钉列表
            await _handle_list_anchors(player, event)


async def _handle_list_anchors(player: Player, event: MessageEvent):
    """显示锚钉列表"""
    anchors = _get_anchors(player)
    if not anchors:
        await anchor_cmd.finish(message_add_head(
            "🌀 虚界锚钉\n━━━━━━━━━━━━━\n暂无锚钉\n\n💡 使用【锚钉 设置 名称】在当前位置撕开裂隙设锚钉",
            event
        ))

    lines = ["🌀 虚界锚钉", "━━━━━━━━━━━━━"]
    for idx, anchor in enumerate(anchors, 1):
        lines.append(_format_anchor(idx, anchor))
    lines.append(f"━━━━━━━━━━━━━")
    lines.append(f"📌 已设置 {len(anchors)}/{MAX_ANCHORS} 个锚钉")

    # 冷却状态
    cd_end = _get_teleport_cd(player)
    if cd_end and cd_end > datetime.now():
        remaining = int((cd_end - datetime.now()).total_seconds())
        lines.append(f"⏱️ 穿越冷却：{remaining}秒")
    else:
        lines.append("✅ 穿越就绪")

    lines.append("")
    lines.append("💡 操作：")
    lines.append("【锚钉 设置 名称】撕开裂隙设锚钉")
    lines.append("【锚钉 传送 编号】穿越虚界传送")
    lines.append("【锚钉 携带 UID 编号】拉对方一同穿越")
    lines.append("【锚钉 删除 编号】缝合裂隙拔除锚钉")

    await anchor_cmd.finish(message_add_head("\n".join(lines), event))


async def _handle_set_anchor(session, player: Player, parts: list, event: MessageEvent):
    """设置锚钉"""
    if len(parts) < 2:
        await anchor_cmd.finish("⛔ 格式：锚钉 设置 <名称>\n例如：锚钉 设置 总部门口")

    name = parts[1].strip()
    if len(name) > 10:
        await anchor_cmd.finish("⛔ 锚钉名称最多10个字符")

    anchors = _get_anchors(player)
    if len(anchors) >= MAX_ANCHORS:
        await anchor_cmd.finish(f"⛔ 锚钉已满（{MAX_ANCHORS}/{MAX_ANCHORS}），请先删除旧锚钉\n💡 使用【锚钉 删除 编号】缝合裂隙拔除锚钉")

    # 检查重名
    for a in anchors:
        if a.get("name") == name:
            await anchor_cmd.finish(f"⛔ 已存在同名锚钉「{name}」，请换个名称")

    # 获取当前坐标
    x, y = player.get_current_coordinates()
    region = player.get_current_region()
    dungeon_level = player.dungeon_level if player.is_in_dungeon() else 0

    new_anchor = {
        "name": name,
        "x": x,
        "y": y,
        "region": region,
        "dungeon_level": dungeon_level,
        "created_at": datetime.now().isoformat(),
    }
    anchors.append(new_anchor)
    _set_anchors(player, anchors)
    session.add(player)
    await session.commit()

    pos_info = f"{region} ({x},{y})"
    await anchor_cmd.finish(message_add_head(
        f"🌀 虚界裂隙撕开——锚钉「{name}」钉入\n📍 {pos_info}\n💡 使用【锚钉 传送 {len(anchors)}】穿越虚界即达",
        event
    ))


async def _handle_teleport(session, player: Player, parts: list, event: MessageEvent):
    """传送到锚钉"""
    if len(parts) < 2:
        await anchor_cmd.finish("⛔ 格式：锚钉 传送 <编号>\n例如：锚钉 传送 1")

    try:
        idx = int(parts[1])
    except ValueError:
        await anchor_cmd.finish("⛔ 请输入锚钉编号（数字）")

    anchors = _get_anchors(player)
    if idx < 1 or idx > len(anchors):
        await anchor_cmd.finish(f"⛔ 锚钉编号无效，当前有 {len(anchors)} 个锚钉")

    # 检查冷却
    cd_end = _get_teleport_cd(player)
    if cd_end and cd_end > datetime.now():
        remaining = int((cd_end - datetime.now()).total_seconds())
        await anchor_cmd.finish(f"⛔ 穿越冷却中，还需 {remaining} 秒")

    # 检查理智消耗
    mp_cost = int(player.max_mp * MP_COST_RATIO)
    if player.mp < mp_cost:
        await anchor_cmd.finish(f"⛔ 理智不足，需要 {mp_cost}（最大理智的5%），当前 {player.mp}")

    anchor = anchors[idx - 1]

    # 如果目标是诡域，检查是否已解锁该层级
    target_dungeon = anchor.get("dungeon_level", 0)
    if target_dungeon > 0 and not player.can_enter_dungeon_level(target_dungeon):
        await anchor_cmd.finish(f"⛔ 你尚未解锁{target_dungeon}层诡域，无法穿越")

    # 消耗理智
    player.mp -= mp_cost

    # 记录出发坐标
    from_x, from_y = player.get_current_coordinates()
    from_region = player.get_current_region()

    # 执行传送
    _teleport_player_to_anchor(player, anchor)

    # 设置冷却
    _set_teleport_cd(player)

    session.add(player)
    await session.commit()

    to_x, to_y = player.get_current_coordinates()
    to_region = player.get_current_region()

    # 使用原生Markdown发送传送反馈
    try:
        content = (
            f"# 🌀 龙影闪 · 虚界穿越\n"
            f"![龙影闪 #360px #201px]({LONGYING_IMG_URL})\n"
            f"> 虚界裂隙撕开，空间扭曲折叠。你踏入裂隙的一瞬，世界在你身后碎成残影。\n"
            f"***\n"
            f"📍 {from_region} ({from_x},{from_y}) → **{to_region} ({to_x},{to_y})**\n"
            f"🎯 抵达锚钉「{color_text(anchor['name'], '#FFB000')}」\n"
            f"💧 消耗理智 **{mp_cost}**，剩余 **{player.mp}/{player.max_mp}**\n"
            f"⏱️ 冷却 **{TELEPORT_CD_SECONDS // 60}** 分钟\n"
            f"***\n"
            f"{cmd('锚钉')} | {cmd('面板')} | {cmd('修炼')} | {cmd('背包')}"
        )

        await anchor_cmd.finish(build_markdown(content))
    except (ValueError, TypeError, KeyError):
        # Markdown构建失败，回退到纯文本
        await anchor_cmd.finish(message_add_head(
            f"🌀 虚界裂隙撕开，你的身影穿越而过——\n"
            f"📍 {from_region} ({from_x},{from_y}) → {to_region} ({to_x},{to_y})\n"
            f"🎯 抵达锚钉「{anchor['name']}」\n"
            f"💧 消耗理智 {mp_cost}，剩余 {player.mp}/{player.max_mp}\n"
            f"⏱️ 冷却 {TELEPORT_CD_SECONDS // 60} 分钟",
            event
        ))


async def _handle_carry(session, player: Player, parts: list, event: MessageEvent):
    """携带他人穿越"""
    if len(parts) < 3:
        await anchor_cmd.finish("⛔ 格式：锚钉 携带 <对方UID> <编号>\n例如：锚钉 携带 1001 2")

    try:
        target_uid = int(parts[1])
        idx = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        await anchor_cmd.finish("⛔ UID和编号必须为数字")

    anchors = _get_anchors(player)
    if idx < 1 or idx > len(anchors):
        await anchor_cmd.finish(f"⛔ 锚钉编号无效，当前有 {len(anchors)} 个锚钉")

    # 检查冷却
    cd_end = _get_teleport_cd(player)
    if cd_end and cd_end > datetime.now():
        remaining = int((cd_end - datetime.now()).total_seconds())
        await anchor_cmd.finish(f"⛔ 穿越冷却中，还需 {remaining} 秒")

    # 检查理智消耗（携带穿越消耗双倍）
    mp_cost = int(player.max_mp * MP_COST_RATIO * 2)
    if player.mp < mp_cost:
        await anchor_cmd.finish(f"⛔ 理智不足，携带穿越需要 {mp_cost}（最大理智的10%），当前 {player.mp}")

    # 查找目标玩家
    stmt = select(Player).where(
        Player.uid == target_uid,
        Player.server_id == player.server_id
    )
    target = (await session.execute(stmt)).scalar_one_or_none()
    if not target:
        await anchor_cmd.finish(f"⛔ 找不到UID为 {target_uid} 的玩家")

    if target.id == player.id:
        await anchor_cmd.finish("⛔ 不能携带自己，请直接使用【锚钉 传送 编号】")

    anchor = anchors[idx - 1]

    # 创建携带穿越请求
    _pending_carry_requests_longying[target.id] = {
        "from_id": player.id,
        "from_name": player.nickname,
        "target_id": target.id,
        "anchor": anchor,
        "anchor_idx": idx,
        "mp_cost": mp_cost,
        "expire": datetime.now() + timedelta(seconds=CARRY_TIMEOUT_SECONDS),
    }

    await anchor_cmd.finish(message_add_head(
        f"🌀 你向 {target.nickname}[UID:{target_uid}] 撕开一道虚界裂隙——\n"
        f"🎯 目的地：「{anchor['name']}」\n"
        f"💡 对方需在{CARRY_TIMEOUT_SECONDS}秒内回复【同意穿越】\n"
        f"⚠️ 携带穿越消耗理智 {mp_cost}（最大理智的10%）",
        event
    ))


async def _handle_delete_anchor(session, player: Player, parts: list, event: MessageEvent):
    """删除锚钉"""
    if len(parts) < 2:
        await anchor_cmd.finish("⛔ 格式：锚钉 删除 <编号>\n例如：锚钉 删除 1")

    try:
        idx = int(parts[1])
    except ValueError:
        await anchor_cmd.finish("⛔ 请输入锚钉编号（数字）")

    anchors = _get_anchors(player)
    if idx < 1 or idx > len(anchors):
        await anchor_cmd.finish(f"⛔ 锚钉编号无效，当前有 {len(anchors)} 个锚钉")

    removed = anchors.pop(idx - 1)
    _set_anchors(player, anchors)
    session.add(player)
    await session.commit()

    await anchor_cmd.finish(message_add_head(
        f"🌀 裂隙缝合——锚钉「{removed['name']}」已消散\n📌 剩余 {len(anchors)}/{MAX_ANCHORS} 个锚钉",
        event
    ))


# ==================== 指令：同意穿越 / 拒绝穿越 ====================
accept_carry_cmd = on_command("同意穿越", block=True, priority=9)
reject_carry_cmd = on_command("拒绝穿越", block=True, priority=9)


@accept_carry_cmd.handle()
async def handle_accept_carry(event: MessageEvent):
    async with safe_session() as session:
        player = await require_player(session, event, accept_carry_cmd)

        # 查找是否有待处理的携带请求
        request = _pending_carry_requests_longying.get(player.id)
        if not request:
            await accept_carry_cmd.finish("⛔ 没有待处理的穿越邀请")

        # 检查是否超时
        if datetime.now() > request["expire"]:
            _pending_carry_requests_longying.pop(player.id, None)
            await accept_carry_cmd.finish("⛔ 穿越邀请已超时")

        # 查找发起者
        from_player = await session.get(Player, request["from_id"])
        if not from_player:
            _pending_carry_requests_longying.pop(player.id, None)
            await accept_carry_cmd.finish("⛔ 发起者已离线")

        # 检查发起者是否仍装备龙影闪
        longying = await _get_longying_instance(session, from_player.id)
        if not longying:
            _pending_carry_requests_longying.pop(player.id, None)
            await accept_carry_cmd.finish("⛔ 发起者已卸下「龙影闪」，穿越取消")

        # 检查发起者冷却
        cd_end = _get_teleport_cd(from_player)
        if cd_end and cd_end > datetime.now():
            _pending_carry_requests_longying.pop(player.id, None)
            await accept_carry_cmd.finish("⛔ 发起者的穿越技能处于冷却中")

        # 检查发起者理智
        mp_cost = request["mp_cost"]
        if from_player.mp < mp_cost:
            _pending_carry_requests_longying.pop(player.id, None)
            await accept_carry_cmd.finish(f"⛔ 发起者理智不足（需{mp_cost}），穿越取消")

        anchor = request["anchor"]

        # 如果目标是诡域，检查发起者是否已解锁
        target_dungeon = anchor.get("dungeon_level", 0)
        carried_to_max = False
        carried_level = 0
        if target_dungeon > 0:
            if not from_player.can_enter_dungeon_level(target_dungeon):
                _pending_carry_requests_longying.pop(player.id, None)
                await accept_carry_cmd.finish(f"⛔ 发起者尚未解锁{target_dungeon}层诡域")
            if not player.can_enter_dungeon_level(target_dungeon):
                # 被携带者未解锁目标层，自动送到其已达最高层
                carried_to_max = True
                carried_level = max(player.max_dungeon_level or 0, 1)

        # 消耗发起者理智
        from_player.mp -= mp_cost

        # 传送发起者到锚点
        _teleport_player_to_anchor(from_player, anchor)

        # 传送被携带者
        if carried_to_max:
            # 被携带者送到其最高已解锁层的起始位置(0,0)
            carried_anchor = dict(anchor)
            carried_anchor["dungeon_level"] = carried_level
            carried_anchor["x"] = 0
            carried_anchor["y"] = 0
            _teleport_player_to_anchor(player, carried_anchor)
        else:
            _teleport_player_to_anchor(player, anchor)

        # 设置冷却
        _set_teleport_cd(from_player)

        session.add(from_player)
        session.add(player)
        await session.commit()

        # 清理请求
        _pending_carry_requests_longying.pop(player.id, None)

        to_region = anchor.get("region", "未知")
        to_x, to_y = anchor.get("x", 0), anchor.get("y", 0)

        if carried_to_max:
            await accept_carry_cmd.finish(message_add_head(
                f"🌀 虚界裂隙吞没两人，但空间在中途分岔——\n"
                f"🎯 {request['from_name']} → 「{anchor['name']}」— {to_region} ({to_x},{to_y})\n"
                f"🎯 {player.nickname} → 第{carried_level}重诡域 (0,0)（已达最深层）\n"
                f"⚠️ {player.nickname} 未解锁第{target_dungeon}重诡域，已自动送至最深探索层\n"
                f"💧 消耗 {request['from_name']} 理智 {mp_cost}",
                event
            ))
        else:
            await accept_carry_cmd.finish(message_add_head(
                f"🌀 虚界裂隙吞没两人，空间折叠重合——\n"
                f"🎯 抵达「{anchor['name']}」— {to_region} ({to_x},{to_y})\n"
                f"👥 {request['from_name']} 携带 {player.nickname} 一同穿越\n"
                f"💧 消耗 {request['from_name']} 理智 {mp_cost}",
                event
            ))


@reject_carry_cmd.handle()
async def handle_reject_carry(event: MessageEvent):
    async with safe_session() as session:
        player = await require_player(session, event, reject_carry_cmd)

        request = _pending_carry_requests_longying.pop(player.id, None)
        if not request:
            await reject_carry_cmd.finish("⛔ 没有待处理的穿越邀请")

        await reject_carry_cmd.finish(message_add_head(
            f"🌀 你避开了虚界裂隙——穿越已拒绝",
            event
        ))


# ==================== 指令：龙影闪（状态面板） ====================
longying_panel_cmd = on_command("龙影闪", block=True, priority=9)


@longying_panel_cmd.handle()
async def handle_longying_panel(event: MessageEvent):
    async with safe_session() as session:
        player = await require_player(session, event, longying_panel_cmd)

        # 检查是否装备了龙影闪
        longying = await _get_longying_instance(session, player.id)
        if not longying:
            await longying_panel_cmd.finish("⛔ 你未装备「龙影闪」")

        # ---- 锚钉列表 ----
        anchors = _get_anchors(player)
        if anchors:
            anchor_lines = []
            for idx, anchor in enumerate(anchors, 1):
                anchor_lines.append(_format_anchor(idx, anchor))
            anchor_text = "\n".join(anchor_lines)
        else:
            anchor_text = "  暂无锚钉"

        # ---- 冷却状态 ----
        cd_end = _get_teleport_cd(player)
        if cd_end and cd_end > datetime.now():
            remaining = int((cd_end - datetime.now()).total_seconds())
            cd_text = f"⏱️ 穿越冷却：{remaining}秒"
        else:
            cd_text = "✅ 穿越就绪"

        # ---- 构建纯文本面板 ----
        lines = [
            "🌀 龙影闪",
            "━━━━━━━━━━━━━",
            f"🔋 耐久：{longying.durability}/360",
            "━━━━━━━━━━━━━",
            "📍 虚界锚钉：",
            anchor_text,
            f"  📌 已设置 {len(anchors)}/{MAX_ANCHORS} 个锚钉",
            f"  {cd_text}",
            "━━━━━━━━━━━━━",
            "💡 操作：",
            "【锚钉 设置 名称】撕开裂隙设锚钉",
            "【锚钉 传送 编号】穿越虚界传送",
            "【锚钉 携带 UID 编号】拉对方一同穿越",
            "【锚钉 删除 编号】缝合裂隙拔除锚钉",
        ]
        fallback_text = "\n".join(lines)

        # ---- 构建原生Markdown卡片 ----
        content = (
            f"# 🌀 龙影闪 · 虚界裂隙\n"
            f"![龙影闪 #360px #201px]({LONGYING_IMG_URL})\n"
            f"{color_text('★ VIP定制装备', '#FFB000')}\n"
            f"> 你踏出的那一步，已经不在这个世界了。\n"
            f"***\n"
            f"🔋 耐久 **{longying.durability}/360**\n"
            f"***\n"
            f"## 📍 虚界锚钉\n"
            f"{anchor_text}\n"
            f"📌 已设置 **{len(anchors)}/{MAX_ANCHORS}** 个锚钉\n"
            f"{cd_text}\n"
            f"***\n"
            f"**⚙️ 操作**\n"
            f"- 【锚钉 设置 名称】撕开裂隙设锚钉\n"
            f"- 【锚钉 传送 编号】穿越虚界传送\n"
            f"- 【锚钉 携带 UID 编号】拉对方一同穿越\n"
            f"- 【锚钉 删除 编号】缝合裂隙拔除锚钉\n"
            f"***\n"
            f"{cmd('锚钉')} | {cmd('面板')} | {cmd('签到')} | {cmd('修炼')}"
        )

        await _send_longying_markdown(longying_panel_cmd, content, fallback_text, event)
