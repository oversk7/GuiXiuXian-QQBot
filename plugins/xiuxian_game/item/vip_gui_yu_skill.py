"""
归雨·鬼域雨钉 —— VIP定制装备「归雨」主动技能模块

功能：
- 锚点 设置 <名称>   在当前位置钉下"雨钉"（最多3个）
- 锚点 传送 <编号>   踏入伞影即走（CD5分钟，消耗5%最大理智）
- 锚点 携带 <UID> <编号>  将对方一并送走（对方需回复【同意传送】）
- 锚点 删除 <编号>   拔除指定雨钉
- 锚点              查看锚点列表
"""

import copy
from datetime import datetime, timedelta
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..platform_utils import get_unified_player, is_guild_message
from ..utils import message_add_head

# ==================== 常量 ====================
MAX_ANCHORS = 3          # 最多锚点数
TELEPORT_CD_SECONDS = 300  # 传送冷却5分钟
MP_COST_RATIO = 0.05     # 消耗5%最大理智
CARRY_TIMEOUT_SECONDS = 120  # 携带传送等待超时2分钟

# 临时存储：等待确认的携带传送请求
# 格式: {target_player_id: {"from_id": str, "anchor": dict, "expire": datetime}}
_pending_carry_requests: dict = {}


# ==================== 辅助函数 ====================

async def _get_gui_yu_instance(session, player_id: str) -> ItemInstance | None:
    """查找玩家已装备的归雨"""
    stmt = select(ItemInstance).where(
        ItemInstance.player_id == player_id,
        ItemInstance.equipped == True,
        ItemInstance.item_id == "vip_gui_yu",
    )
    return (await session.execute(stmt)).scalars().first()


def _get_anchors(player: Player) -> list[dict]:
    """获取玩家的锚点列表（返回深拷贝，避免意外修改MutableDict内部数据）"""
    data = player.vip_equipment_data or {}
    return copy.deepcopy(data.get("gui_yu_anchors", []))


def _set_anchors(player: Player, anchors: list[dict]):
    """设置玩家的锚点列表（通过重建整个dict确保SQLAlchemy检测到变更）"""
    data = dict(player.vip_equipment_data or {})
    data["gui_yu_anchors"] = copy.deepcopy(anchors)
    player.vip_equipment_data = data


def _get_teleport_cd(player: Player) -> datetime | None:
    """获取传送冷却结束时间"""
    cd_data = player.vip_skill_cooldown or {}
    cd_str = cd_data.get("gui_yu_teleport")
    if cd_str:
        try:
            return datetime.fromisoformat(cd_str)
        except (ValueError, TypeError):
            pass
    return None


def _set_teleport_cd(player: Player):
    """设置传送冷却"""
    cd_data = dict(player.vip_skill_cooldown or {})
    cd_data["gui_yu_teleport"] = (datetime.now() + timedelta(seconds=TELEPORT_CD_SECONDS)).isoformat()
    player.vip_skill_cooldown = cd_data


def _format_anchor(idx: int, anchor: dict) -> str:
    """格式化单个锚点信息"""
    name = anchor.get("name", "未命名")
    region = anchor.get("region", "未知")
    x, y = anchor.get("x", 0), anchor.get("y", 0)
    # 如果是诡域锚点
    dungeon_level = anchor.get("dungeon_level", 0)
    if dungeon_level > 0:
        return f"  [{idx}] 📍 {name} — {dungeon_level}层诡域 ({x},{y})"
    else:
        return f"  [{idx}] 📍 {name} — 大都会 ({x},{y})"


def _teleport_player_to_anchor(player: Player, anchor: dict):
    """将玩家传送到指定锚点"""
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


# ==================== 指令：锚点 ====================
anchor_cmd = on_command("锚点", block=True, priority=5)


@anchor_cmd.handle()
async def handle_anchor(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await anchor_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await anchor_cmd.finish("⛔ 请先创建角色")

        # 检查是否装备了归雨
        gui_yu = await _get_gui_yu_instance(session, player.id)
        if not gui_yu:
            await anchor_cmd.finish("⛔ 你未装备「归雨」，无法使用锚点技能")

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
            # 默认：显示锚点列表
            await _handle_list_anchors(player, event)


async def _handle_list_anchors(player: Player, event: MessageEvent):
    """显示锚点列表"""
    anchors = _get_anchors(player)
    if not anchors:
        await anchor_cmd.finish(message_add_head(
            "☂️ 鬼域雨钉\n━━━━━━━━━━━━━\n暂无锚点\n\n💡 使用【锚点 设置 名称】在当前位置钉下雨钉",
            event
        ))

    lines = ["☂️ 鬼域雨钉", "━━━━━━━━━━━━━"]
    for idx, anchor in enumerate(anchors, 1):
        lines.append(_format_anchor(idx, anchor))
    lines.append(f"━━━━━━━━━━━━━")
    lines.append(f"📌 已设置 {len(anchors)}/{MAX_ANCHORS} 个锚点")

    # 冷却状态
    cd_end = _get_teleport_cd(player)
    if cd_end and cd_end > datetime.now():
        remaining = int((cd_end - datetime.now()).total_seconds())
        lines.append(f"⏱️ 传送冷却：{remaining}秒")
    else:
        lines.append("✅ 传送就绪")

    lines.append("")
    lines.append("💡 操作：")
    lines.append("【锚点 设置 名称】钉下雨钉")
    lines.append("【锚点 传送 编号】传送到锚点")
    lines.append("【锚点 携带 UID 编号】携带他人传送")
    lines.append("【锚点 删除 编号】拔除雨钉")

    await anchor_cmd.finish(message_add_head("\n".join(lines), event))


async def _handle_set_anchor(session, player: Player, parts: list, event: MessageEvent):
    """设置锚点"""
    if len(parts) < 2:
        await anchor_cmd.finish("⛔ 格式：锚点 设置 <名称>\n例如：锚点 设置 总部门口")

    name = parts[1].strip()
    if len(name) > 10:
        await anchor_cmd.finish("⛔ 锚点名称最多10个字符")

    anchors = _get_anchors(player)
    if len(anchors) >= MAX_ANCHORS:
        await anchor_cmd.finish(f"⛔ 锚点已满（{MAX_ANCHORS}/{MAX_ANCHORS}），请先删除旧锚点\n💡 使用【锚点 删除 编号】拔除雨钉")

    # 检查重名
    for a in anchors:
        if a.get("name") == name:
            await anchor_cmd.finish(f"⛔ 已存在同名锚点「{name}」，请换个名称")

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
        f"☂️ 雨钉落地——「{name}」\n📍 {pos_info}\n💡 使用【锚点 传送 {len(anchors)}】踏入伞影即走",
        event
    ))


async def _handle_teleport(session, player: Player, parts: list, event: MessageEvent):
    """传送到锚点"""
    if len(parts) < 2:
        await anchor_cmd.finish("⛔ 格式：锚点 传送 <编号>\n例如：锚点 传送 1")

    try:
        idx = int(parts[1])
    except ValueError:
        await anchor_cmd.finish("⛔ 请输入锚点编号（数字）")

    anchors = _get_anchors(player)
    if idx < 1 or idx > len(anchors):
        await anchor_cmd.finish(f"⛔ 锚点编号无效，当前有 {len(anchors)} 个锚点")

    # 检查冷却
    cd_end = _get_teleport_cd(player)
    if cd_end and cd_end > datetime.now():
        remaining = int((cd_end - datetime.now()).total_seconds())
        await anchor_cmd.finish(f"⛔ 传送冷却中，还需 {remaining} 秒")

    # 检查理智消耗
    mp_cost = int(player.max_mp * MP_COST_RATIO)
    if player.mp < mp_cost:
        await anchor_cmd.finish(f"⛔ 理智不足，需要 {mp_cost}（最大理智的5%），当前 {player.mp}")

    anchor = anchors[idx - 1]

    # 如果目标是诡域，检查是否已解锁该层级
    target_dungeon = anchor.get("dungeon_level", 0)
    if target_dungeon > 0 and not player.can_enter_dungeon_level(target_dungeon):
        await anchor_cmd.finish(f"⛔ 你尚未解锁{target_dungeon}层诡域，无法传送")

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

    await anchor_cmd.finish(message_add_head(
        f"☂️ 你踏入伞影，身形消散——\n"
        f"📍 {from_region} ({from_x},{from_y}) → {to_region} ({to_x},{to_y})\n"
        f"🎯 抵达锚点「{anchor['name']}」\n"
        f"💧 消耗理智 {mp_cost}，剩余 {player.mp}/{player.max_mp}\n"
        f"⏱️ 冷却 {TELEPORT_CD_SECONDS // 60} 分钟",
        event
    ))


async def _handle_carry(session, player: Player, parts: list, event: MessageEvent):
    """携带他人传送"""
    if len(parts) < 3:
        await anchor_cmd.finish("⛔ 格式：锚点 携带 <对方UID> <编号>\n例如：锚点 携带 1001 2")

    try:
        target_uid = int(parts[1])
        idx = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        await anchor_cmd.finish("⛔ UID和编号必须为数字")

    anchors = _get_anchors(player)
    if idx < 1 or idx > len(anchors):
        await anchor_cmd.finish(f"⛔ 锚点编号无效，当前有 {len(anchors)} 个锚点")

    # 检查冷却
    cd_end = _get_teleport_cd(player)
    if cd_end and cd_end > datetime.now():
        remaining = int((cd_end - datetime.now()).total_seconds())
        await anchor_cmd.finish(f"⛔ 传送冷却中，还需 {remaining} 秒")

    # 检查理智消耗（携带传送消耗双倍）
    mp_cost = int(player.max_mp * MP_COST_RATIO * 2)
    if player.mp < mp_cost:
        await anchor_cmd.finish(f"⛔ 理智不足，携带传送需要 {mp_cost}（最大理智的10%），当前 {player.mp}")

    # 查找目标玩家
    stmt = select(Player).where(Player.uid == target_uid)
    target = (await session.execute(stmt)).scalar_one_or_none()
    if not target:
        await anchor_cmd.finish(f"⛔ 找不到UID为 {target_uid} 的玩家")

    if target.id == player.id:
        await anchor_cmd.finish("⛔ 不能携带自己，请直接使用【锚点 传送 编号】")

    # 检查目标距离（需要在附近3格以内）
    px, py = player.get_current_coordinates()
    tx, ty = target.get_current_coordinates()
    p_region = player.get_current_region()
    t_region = target.get_current_region()

    if p_region != t_region:
        await anchor_cmd.finish(f"⛔ {target.nickname} 与你不在同一区域")

    distance = abs(px - tx) + abs(py - ty)
    if distance > 3:
        await anchor_cmd.finish(f"⛔ {target.nickname} 距离过远（距离{distance}格），需要在3格以内")

    anchor = anchors[idx - 1]

    # 创建携带传送请求
    _pending_carry_requests[target.id] = {
        "from_id": player.id,
        "from_name": player.nickname,
        "target_id": target.id,
        "anchor": anchor,
        "anchor_idx": idx,
        "mp_cost": mp_cost,
        "expire": datetime.now() + timedelta(seconds=CARRY_TIMEOUT_SECONDS),
    }

    await anchor_cmd.finish(message_add_head(
        f"☂️ 你向 {target.nickname}[UID:{target_uid}] 伸出伞下的手——\n"
        f"🎯 目的地：「{anchor['name']}」\n"
        f"💡 对方需在{CARRY_TIMEOUT_SECONDS}秒内回复【同意传送】\n"
        f"⚠️ 携带传送消耗理智 {mp_cost}（最大理智的10%）",
        event
    ))


async def _handle_delete_anchor(session, player: Player, parts: list, event: MessageEvent):
    """删除锚点"""
    if len(parts) < 2:
        await anchor_cmd.finish("⛔ 格式：锚点 删除 <编号>\n例如：锚点 删除 1")

    try:
        idx = int(parts[1])
    except ValueError:
        await anchor_cmd.finish("⛔ 请输入锚点编号（数字）")

    anchors = _get_anchors(player)
    if idx < 1 or idx > len(anchors):
        await anchor_cmd.finish(f"⛔ 锚点编号无效，当前有 {len(anchors)} 个锚点")

    removed = anchors.pop(idx - 1)
    _set_anchors(player, anchors)
    session.add(player)
    await session.commit()

    await anchor_cmd.finish(message_add_head(
        f"☂️ 雨钉拔除——「{removed['name']}」已消散\n📌 剩余 {len(anchors)}/{MAX_ANCHORS} 个锚点",
        event
    ))


# ==================== 指令：同意传送 / 拒绝传送 ====================
accept_carry_cmd = on_command("同意传送", block=True, priority=5)
reject_carry_cmd = on_command("拒绝传送", block=True, priority=5)


@accept_carry_cmd.handle()
async def handle_accept_carry(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await accept_carry_cmd.finish("⛔ 请先创建角色")

        # 查找是否有待处理的携带请求
        request = _pending_carry_requests.get(player.id)
        if not request:
            await accept_carry_cmd.finish("⛔ 没有待处理的传送邀请")

        # 检查是否超时
        if datetime.now() > request["expire"]:
            _pending_carry_requests.pop(player.id, None)
            await accept_carry_cmd.finish("⛔ 传送邀请已超时")

        # 查找发起者
        from_player = await session.get(Player, request["from_id"])
        if not from_player:
            _pending_carry_requests.pop(player.id, None)
            await accept_carry_cmd.finish("⛔ 发起者已离线")

        # 检查发起者是否仍装备归雨
        gui_yu = await _get_gui_yu_instance(session, from_player.id)
        if not gui_yu:
            _pending_carry_requests.pop(player.id, None)
            await accept_carry_cmd.finish("⛔ 发起者已卸下「归雨」，传送取消")

        # 检查发起者冷却
        cd_end = _get_teleport_cd(from_player)
        if cd_end and cd_end > datetime.now():
            _pending_carry_requests.pop(player.id, None)
            await accept_carry_cmd.finish("⛔ 发起者的传送技能处于冷却中")

        # 检查发起者理智
        mp_cost = request["mp_cost"]
        if from_player.mp < mp_cost:
            _pending_carry_requests.pop(player.id, None)
            await accept_carry_cmd.finish(f"⛔ 发起者理智不足（需{mp_cost}），传送取消")

        anchor = request["anchor"]

        # 如果目标是诡域，检查双方是否已解锁
        target_dungeon = anchor.get("dungeon_level", 0)
        if target_dungeon > 0:
            if not from_player.can_enter_dungeon_level(target_dungeon):
                _pending_carry_requests.pop(player.id, None)
                await accept_carry_cmd.finish(f"⛔ 发起者尚未解锁{target_dungeon}层诡域")
            if not player.can_enter_dungeon_level(target_dungeon):
                _pending_carry_requests.pop(player.id, None)
                await accept_carry_cmd.finish(f"⛔ 你尚未解锁{target_dungeon}层诡域，无法被传送")

        # 消耗发起者理智
        from_player.mp -= mp_cost

        # 传送双方
        _teleport_player_to_anchor(from_player, anchor)
        _teleport_player_to_anchor(player, anchor)

        # 设置冷却
        _set_teleport_cd(from_player)

        session.add(from_player)
        session.add(player)
        await session.commit()

        # 清理请求
        _pending_carry_requests.pop(player.id, None)

        to_region = anchor.get("region", "未知")
        to_x, to_y = anchor.get("x", 0), anchor.get("y", 0)

        await accept_carry_cmd.finish(message_add_head(
            f"☂️ 伞影笼罩两人，身形一同消散——\n"
            f"🎯 抵达「{anchor['name']}」— {to_region} ({to_x},{to_y})\n"
            f"👥 {request['from_name']} 携带 {player.nickname} 一同传送\n"
            f"💧 消耗 {request['from_name']} 理智 {mp_cost}",
            event
        ))


@reject_carry_cmd.handle()
async def handle_reject_carry(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await reject_carry_cmd.finish("⛔ 请先创建角色")

        request = _pending_carry_requests.pop(player.id, None)
        if not request:
            await reject_carry_cmd.finish("⛔ 没有待处理的传送邀请")

        await reject_carry_cmd.finish(message_add_head(
            f"☂️ 你推开了伸来的伞——传送已拒绝",
            event
        ))
