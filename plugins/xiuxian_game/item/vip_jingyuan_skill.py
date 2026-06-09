"""
镜怨披风·怨灵拾荒 —— VIP定制装备「镜怨披风」主动技能模块

功能：
- 怨灵拾荒     派出怨灵在周围拾荒，2小时后返回带回随机材料和金币（每日1次）
- 镜怨披风     查看镜怨披风状态面板
"""

import copy
import random
from datetime import datetime, timedelta, date
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..platform_utils import require_player
from ..utils import message_add_head


# ==================== 常量 ====================
EQUIPMENT_ID = "vip_robe_jingyuanzhiyi"
SCAVENGE_KEY = "grudge_scavenge"  # vip_equipment_data 中的子键
DURABILITY_COST = 3  # 每次拾荒消耗耐久
SCAVENGE_HOURS = 2  # 怨灵外出时长（小时）

# 拾荒掉落表：(材料ID列表, 数量范围, 权重)
# 以白色/绿色材料为主，偶尔蓝色
SCAVENGE_LOOT_TABLE = [
    # 白色材料 - 高概率
    {"rarity": "white", "weight": 60, "qty_range": (2, 5)},
    # 绿色材料 - 中概率
    {"rarity": "green", "weight": 30, "qty_range": (1, 3)},
    # 蓝色材料 - 低概率
    {"rarity": "blue", "weight": 10, "qty_range": (1, 1)},
]

# 金币奖励范围
GOLD_RANGE = (80000, 120000)


# ==================== 辅助函数 ====================

async def _get_equipment_instance(session: AsyncSession, player_id: str) -> ItemInstance | None:
    """查找玩家已装备的镜怨披风"""
    stmt = select(ItemInstance).where(
        ItemInstance.player_id == player_id,
        ItemInstance.equipped == True,
        ItemInstance.item_id == EQUIPMENT_ID,
    )
    return (await session.execute(stmt)).scalars().first()


def _get_scavenge_data(player: Player) -> dict:
    """获取拾荒数据（自动按日期重置）"""
    data = player.vip_equipment_data or {}
    scavenge = data.get(SCAVENGE_KEY, {})
    today_str = date.today().isoformat()

    # 日期不同则重置
    if scavenge.get("date") != today_str:
        scavenge = {"date": today_str, "state": "idle", "sent_at": None}

    return scavenge


def _set_scavenge_data(player: Player, scavenge: dict):
    """保存拾荒数据"""
    data = dict(player.vip_equipment_data or {})
    data[SCAVENGE_KEY] = copy.deepcopy(scavenge)
    player.vip_equipment_data = data
    flag_modified(player, "vip_equipment_data")


def _generate_loot() -> tuple[list[tuple[str, str, int]], int]:
    """
    生成拾荒战利品

    Returns:
        ([(item_id, display_name, quantity), ...], gold)
    """
    from ..config import config
    from ..world.dungeon_battle import get_materials_by_rarity

    loot_items = []

    # 掷骰决定掉几种材料（1-2种）
    num_drops = random.randint(1, 2)

    for _ in range(num_drops):
        # 按权重选择稀有度
        roll = random.randint(1, 100)
        cumulative = 0
        selected_tier = SCAVENGE_LOOT_TABLE[0]
        for tier in SCAVENGE_LOOT_TABLE:
            cumulative += tier["weight"]
            if roll <= cumulative:
                selected_tier = tier
                break

        rarity = selected_tier["rarity"]
        qty_min, qty_max = selected_tier["qty_range"]
        quantity = random.randint(qty_min, qty_max)

        # 从该稀有度材料中随机选一个
        materials = get_materials_by_rarity(rarity)
        if not materials:
            continue

        material_id = random.choice(materials)
        item_cfg = config.items_config["by_id"].get(material_id)
        if item_cfg:
            display_name = item_cfg.get_display_name()
            loot_items.append((material_id, display_name, quantity))

    # 金币奖励
    gold = random.randint(*GOLD_RANGE)

    return loot_items, gold


# ==================== 指令：怨灵拾荒 ====================
scavenge_cmd = on_command("怨灵拾荒", block=True, priority=9)


@scavenge_cmd.handle()
async def handle_scavenge(event: MessageEvent):
    async with safe_session() as session:
        player = await require_player(session, event, scavenge_cmd)

        # 检查是否装备了镜怨披风
        equipment = await _get_equipment_instance(session, player.id)
        if not equipment:
            await scavenge_cmd.finish("⛔ 你未装备「镜怨披风」，无法使用怨灵拾荒")

        scavenge = _get_scavenge_data(player)
        state = scavenge.get("state", "idle")

        if state == "done":
            # 今日已拾荒完毕
            await scavenge_cmd.finish(
                "🪞 今日怨灵已归来，不愿再出去了\n"
                "💡 明日再来 (1/1)"
            )

        elif state == "sent":
            # 怨灵已派出，检查是否已返回
            sent_at_str = scavenge.get("sent_at")
            if not sent_at_str:
                # 数据异常，重置
                scavenge["state"] = "idle"
                _set_scavenge_data(player, scavenge)
                session.add(player)
                await session.commit()
                await scavenge_cmd.finish("⛔ 数据异常，已重置，请重新使用【怨灵拾荒】")

            sent_at = datetime.fromisoformat(sent_at_str)
            return_at = sent_at + timedelta(hours=SCAVENGE_HOURS)

            if datetime.now() < return_at:
                # 还没回来
                remaining = return_at - datetime.now()
                remaining_mins = int(remaining.total_seconds() / 60)
                hours = remaining_mins // 60
                mins = remaining_mins % 60

                if hours > 0:
                    time_str = f"{hours}小时{mins}分钟"
                else:
                    time_str = f"{mins}分钟"

                await scavenge_cmd.finish(
                    f"🪞 怨灵正在外面游荡拾荒...\n"
                    f"⏳ 预计 {time_str} 后归来\n"
                    f"💡 稍后再试"
                )

            # 怨灵已返回！生成战利品
            loot_items, gold = _generate_loot()

            # 发放战利品
            loot_lines = []
            for item_id, display_name, quantity in loot_items:
                try:
                    await ItemInstance.add_item(session, player.id, item_id, quantity)
                    loot_lines.append(f"  💎 {display_name} x{quantity}")
                except ValueError:
                    loot_lines.append(f"  📦 {display_name} x{quantity}（背包满，已丢弃）")

            player.gold += gold
            loot_lines.append(f"  💰 {gold} 金币")

            # 标记完成
            scavenge["state"] = "done"
            _set_scavenge_data(player, scavenge)

            session.add(player)
            await session.commit()

            msg = (
                "🪞 怨灵拾荒 · 归来\n"
                "━━━━━━━━━━━━━\n"
                "你的倒影从镜面中走出，\n"
                "手里多了些不知从哪捡来的东西。\n"
                "━━━━━━━━━━━━━\n"
                "📦 战利品：\n"
                + "\n".join(loot_lines)
                + "\n━━━━━━━━━━━━━\n"
                "💡 明日可再次派出怨灵"
            )
            await scavenge_cmd.finish(message_add_head(msg, event))

        else:
            # idle状态：派出怨灵
            # 检查耐久
            if equipment.durability < DURABILITY_COST:
                await scavenge_cmd.finish(
                    f"⛔ 镜怨披风耐久不足（需要{DURABILITY_COST}，当前{equipment.durability}）\n"
                    "💡 请先修理装备"
                )

            # 扣除耐久
            equipment.durability = max(0, equipment.durability - DURABILITY_COST)

            # 记录派出
            scavenge["state"] = "sent"
            scavenge["sent_at"] = datetime.now().isoformat()
            _set_scavenge_data(player, scavenge)

            session.add(player)
            session.add(equipment)
            await session.commit()

            msg = (
                "🪞 怨灵拾荒 · 出发\n"
                "━━━━━━━━━━━━━\n"
                "你的倒影从镜面中缓缓剥离，\n"
                "化作一道若有若无的残影消失在角落。\n"
                "━━━━━━━━━━━━━\n"
                f"⏳ 怨灵将在 {SCAVENGE_HOURS} 小时后归来\n"
                f"🔋 耐久 -{DURABILITY_COST}（剩余 {equipment.durability}/300）\n"
                "💡 稍后再次使用【怨灵拾荒】领取战利品"
            )
            await scavenge_cmd.finish(message_add_head(msg, event))


# ==================== 指令：镜怨披风（状态面板） ====================
panel_cmd = on_command("镜怨披风", block=True, priority=9)


@panel_cmd.handle()
async def handle_panel(event: MessageEvent):
    async with safe_session() as session:
        player = await require_player(session, event, panel_cmd)

        # 检查是否装备了镜怨披风
        equipment = await _get_equipment_instance(session, player.id)
        if not equipment:
            await panel_cmd.finish("⛔ 你未装备「镜怨披风」")

        scavenge = _get_scavenge_data(player)
        state = scavenge.get("state", "idle")

        # 拾荒状态文本
        if state == "done":
            scavenge_status = "❌ 已完成 (1/1)"
        elif state == "sent":
            sent_at_str = scavenge.get("sent_at")
            if sent_at_str:
                sent_at = datetime.fromisoformat(sent_at_str)
                return_at = sent_at + timedelta(hours=SCAVENGE_HOURS)
                if datetime.now() >= return_at:
                    scavenge_status = "📦 怨灵已归来，待领取！"
                else:
                    remaining = return_at - datetime.now()
                    remaining_mins = int(remaining.total_seconds() / 60)
                    hours = remaining_mins // 60
                    mins = remaining_mins % 60
                    if hours > 0:
                        scavenge_status = f"🔄 拾荒中...（{hours}小时{mins}分钟后归来）"
                    else:
                        scavenge_status = f"🔄 拾荒中...（{mins}分钟后归来）"
            else:
                scavenge_status = "✅ 可用 (0/1)"
        else:
            scavenge_status = "✅ 可用 (0/1)"

        # 今日成长统计（自噬：gain_attack on_death）
        extra = equipment.extra_attrs or {}
        today_str = date.today().strftime("%Y%m%d")
        atk_gains_today = 0
        if extra.get("jy_atk_day") == today_str:
            atk_gains_today = int(extra.get("jy_atk_cnt", 0))

        lines = [
            "🪞 镜怨披风",
            "━━━━━━━━━━━━━",
            f"🔋 耐久：{equipment.durability}/300",
            "━━━━━━━━━━━━━",
            "👻 怨灵拾荒：",
            f"  {scavenge_status}",
            "━━━━━━━━━━━━━",
            "📊 今日成长：",
            f"  自噬：+{atk_gains_today * 2}攻击 ({atk_gains_today}/10)",
            "━━━━━━━━━━━━━",
            "💡 操作：",
            "【怨灵拾荒】派出怨灵/领取战利品",
        ]

        await panel_cmd.finish(message_add_head("\n".join(lines), event))
