"""
诡面骰·骰相·乱 —— VIP定制装备「诡面骰」主动技能模块

功能：
- 掷骰        摇动八面骰，随机+100%点一项特殊属性（持续一场战斗，每日10次）
- 诡面骰      查看诡面骰状态面板
"""

import copy
import random
from datetime import date
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
from ..utils_markdown import build_markdown, cmd, color_text


# ==================== 常量 ====================
EQUIPMENT_ID = "vip_ghost_dice"
DICE_KEY = "dice_roll"  # vip_equipment_data 中的子键
DURABILITY_COST = 5      # 掷骰耐久消耗
DAILY_ROLL_LIMIT = 10    # 每日掷骰次数上限

# 诡面骰配图
GHOST_DICE_IMG_URL = "https://wdcdn.qpic.cn/MTMxMDI2NjM3MjM0Njk2MTE_350520_RPoKZCpD58Z3cLIm_1771857949"

# 八面骰对应的8种特殊属性（排除灵爆率 skill_crit_rate）
DICE_FACES = [
    {"attribute": "critical_power",   "cn": "暴击伤害", "icon": "💥", "desc": "暴击力翻倍（×2）"},
    {"attribute": "combo_rate",       "cn": "连击率",   "icon": "⚡", "desc": "连击率+100%"},
    {"attribute": "counter_rate",     "cn": "反击率",   "icon": "🛡️", "desc": "反击率+100%"},
    {"attribute": "dodge_rate",       "cn": "闪避率",   "icon": "💨", "desc": "闪避率+100%"},
    {"attribute": "accuracy_rate",    "cn": "命中率",   "icon": "🎯", "desc": "命中率+100%"},
    {"attribute": "critical_rate",    "cn": "暴击率",   "icon": "🔮", "desc": "暴击率+100%"},
    {"attribute": "penetration_rate", "cn": "穿透率",   "icon": "🗡️", "desc": "穿透率+100%"},
    {"attribute": "anti_crit_rate",   "cn": "抗暴率",   "icon": "🪨", "desc": "抗暴率+100%"},
]


# ==================== Markdown发送 ====================

async def _send_dice_markdown(handler, content: str, fallback_text: str, event: MessageEvent):
    """使用原生Markdown发送诡面骰反馈，失败时回退到纯文本"""
    try:
        await handler.finish(build_markdown(content))
    except (ValueError, TypeError, KeyError):
        await handler.finish(message_add_head(fallback_text, event))


# ==================== 辅助函数 ====================

async def _get_dice_instance(session: AsyncSession, player_id: str) -> ItemInstance | None:
    """查找玩家已装备的诡面骰"""
    stmt = select(ItemInstance).where(
        ItemInstance.player_id == player_id,
        ItemInstance.equipped == True,
        ItemInstance.item_id == EQUIPMENT_ID,
    )
    return (await session.execute(stmt)).scalars().first()


def _get_dice_data(player: Player) -> dict:
    """获取掷骰数据（自动按日期重置）"""
    data = player.vip_equipment_data or {}
    roll = data.get(DICE_KEY, {})
    today_str = date.today().isoformat()

    if roll.get("date") != today_str:
        roll = {"date": today_str, "used": 0}

    return roll


def _set_dice_data(player: Player, roll_data: dict):
    """保存掷骰数据"""
    data = dict(player.vip_equipment_data or {})
    data[DICE_KEY] = copy.deepcopy(roll_data)
    player.vip_equipment_data = data
    flag_modified(player, "vip_equipment_data")


def _get_dice_buff(player: Player) -> dict | None:
    """获取当前未消耗的骰子buff"""
    data = player.vip_equipment_data or {}
    buff = data.get("dice_buff")
    if buff and not buff.get("consumed"):
        return buff
    return None


def _set_dice_buff(player: Player, attribute: str, attribute_cn: str, icon: str):
    """设置骰子buff（下一场战斗生效）"""
    data = dict(player.vip_equipment_data or {})
    data["dice_buff"] = {
        "attribute": attribute,
        "attribute_cn": attribute_cn,
        "icon": icon,
        "consumed": False,
    }
    player.vip_equipment_data = data
    flag_modified(player, "vip_equipment_data")


# ==================== 指令：掷骰 ====================
roll_dice_cmd = on_command("掷骰", block=True, priority=9)


@roll_dice_cmd.handle()
async def handle_roll_dice(event: MessageEvent):
    async with safe_session() as session:
        player = await require_player(session, event, roll_dice_cmd)

        # 检查是否装备了诡面骰
        dice_item = await _get_dice_instance(session, player.id)
        if not dice_item:
            await roll_dice_cmd.finish("⛔ 你未装备「诡面骰」，无法使用掷骰技能")

        # 检查耐久
        if dice_item.durability < DURABILITY_COST:
            await roll_dice_cmd.finish(
                f"⛔ 诡面骰耐久不足（需要{DURABILITY_COST}，当前{dice_item.durability}）\n"
                "💡 使用【修理装备】恢复耐久"
            )

        # 检查今日是否已用
        roll_data = _get_dice_data(player)
        used = roll_data.get("used", 0)
        if used >= DAILY_ROLL_LIMIT:
            await roll_dice_cmd.finish(f"⛔ 今日掷骰次数已用完（{DAILY_ROLL_LIMIT}/{DAILY_ROLL_LIMIT}）\n💡 明日重置")

        # 检查是否有未消耗的buff（有则覆盖，给出提示）
        existing_buff = _get_dice_buff(player)

        # 掷骰！
        face = random.choice(DICE_FACES)

        # 标记已用
        roll_data["used"] = used + 1
        _set_dice_data(player, roll_data)

        # 设置buff
        _set_dice_buff(player, face["attribute"], face["cn"], face["icon"])

        # 扣耐久
        dice_item.durability = max(0, dice_item.durability - DURABILITY_COST)
        session.add(dice_item)
        session.add(player)
        await session.commit()

        # 反馈
        content = (
            f"# 🎲 诡面骰 · 骰相·乱\n"
            f"![诡面骰 #360px #201px]({GHOST_DICE_IMG_URL})\n"
            f"> 骰子在指尖旋转，八面诡纹明灭不定。它停下了——第{DICE_FACES.index(face) + 1}面朝上。\n"
            f"***\n"
            f"{face['icon']} 命运指向：{color_text(face['cn'], '#FFB000')}\n"
            f"✨ 下一场战斗中 **{face['cn']} +100%**\n"
            f"💡 {face['desc']}\n"
            + (f"⚠️ 已覆盖：{existing_buff.get('attribute_cn','')}+100%\n" if existing_buff else "")
            + f"***\n"
            f"🔋 耐久 **-{DURABILITY_COST}**（剩余 **{dice_item.durability}/360**）\n"
            f"🎯 今日掷骰 **{used + 1}/{DAILY_ROLL_LIMIT}**\n"
            f"***\n"
            f"{cmd('诡面骰')} | {cmd('面板')} | {cmd('修炼')} | {cmd('背包')}"
        )
        fallback = (
            "🎲 诡面骰 · 骰相·乱\n"
            "━━━━━━━━━━━━━\n"
            f"骰子停下——第{DICE_FACES.index(face) + 1}面朝上\n\n"
            f"{face['icon']} 命运指向：{face['cn']}\n"
            f"✨ 下一场战斗中 {face['cn']} +100%\n"
            f"💡 {face['desc']}\n"
            "━━━━━━━━━━━━━\n"
            + (f"⚠️ 已覆盖：{existing_buff.get('attribute_cn','')}\n" if existing_buff else "")
            + f"🔋 耐久 -{DURABILITY_COST}（剩余 {dice_item.durability}/360）\n"
            f"💡 今日掷骰 ({used + 1}/{DAILY_ROLL_LIMIT})"
        )
        await _send_dice_markdown(roll_dice_cmd, content, fallback, event)


# ==================== 指令：诡面骰（状态面板） ====================
dice_panel_cmd = on_command("诡面骰", block=True, priority=9)


@dice_panel_cmd.handle()
async def handle_dice_panel(event: MessageEvent):
    async with safe_session() as session:
        player = await require_player(session, event, dice_panel_cmd)

        # 检查是否装备了诡面骰
        dice_item = await _get_dice_instance(session, player.id)
        if not dice_item:
            await dice_panel_cmd.finish("⛔ 你未装备「诡面骰」")

        # ---- 掷骰状态 ----
        roll_data = _get_dice_data(player)
        roll_used = roll_data.get("used", 0)
        if roll_used >= DAILY_ROLL_LIMIT:
            roll_text = f"❌ 已用完 ({roll_used}/{DAILY_ROLL_LIMIT})"
        else:
            roll_text = f"✅ 可用 ({roll_used}/{DAILY_ROLL_LIMIT})"

        # ---- 骰子buff状态 ----
        dice_buff = _get_dice_buff(player)
        if dice_buff:
            buff_icon = dice_buff.get("icon", "🎲")
            buff_cn = dice_buff.get("attribute_cn", "未知")
            buff_text = f"{buff_icon} {buff_cn} +100%（待消耗）"
        else:
            buff_text = "无（已消耗或未掷骰）"

        # ---- 每日成长（骰相·噬：+2攻击/次，每日20次） ----
        extra = dice_item.extra_attrs or {}
        today_str = date.today().isoformat()
        kill_cnt = 0
        if extra.get("gd_kill_day") == today_str:
            kill_cnt = int(extra.get("gd_kill_cnt", 0))

        # ---- 构建纯文本面板 ----
        lines = [
            "🎲 诡面骰",
            "━━━━━━━━━━━━━",
            f"🔋 耐久：{dice_item.durability}/360",
            "━━━━━━━━━━━━━",
            "🎰 骰相·乱：",
            f"  掷骰：{roll_text}",
            f"  当前buff：{buff_text}",
            "━━━━━━━━━━━━━",
            "📊 今日成长：",
            f"  骰相·噬：+{kill_cnt * 2}攻击 ({kill_cnt}/20)",
            "━━━━━━━━━━━━━",
            "🎲 八面骰对应属性：",
        ]
        for i, face in enumerate(DICE_FACES):
            lines.append(f"  [{i + 1}] {face['icon']} {face['cn']}")
        lines.extend([
            "━━━━━━━━━━━━━",
            "💡 操作：",
            "【掷骰】摇动命运（每日10次，耐久-5）",
        ])
        fallback_text = "\n".join(lines)

        # ---- 构建原生Markdown卡片 ----
        faces_text = "  ".join(f"{f['icon']}{f['cn']}" for f in DICE_FACES)
        content = (
            f"# 🎲 诡面骰 · 八面诡纹\n"
            f"![诡面骰 #360px #201px]({GHOST_DICE_IMG_URL})\n"
            f"{color_text('★ VIP定制装备', '#FFB000')}\n"
            f"> 八面各刻一道诡纹，掷下时，命运便不再是你的了。\n"
            f"***\n"
            f"🔋 耐久 **{dice_item.durability}/360**\n"
            f"***\n"
            f"## 🎰 骰相·乱\n"
            f"- 掷骰：{roll_text}\n"
            f"- 当前buff：{buff_text}\n"
            f"***\n"
            f"## 📊 今日成长\n"
            f"- 骰相·噬：**+{kill_cnt * 2}攻击** ({kill_cnt}/20)\n"
            f"***\n"
            f"🎲 八面：{faces_text}\n"
            f"> 💡 {cmd('掷骰')} 摇动命运（每日10次，耐久-5）\n"
            f"***\n"
            f"{cmd('诡面骰')} | {cmd('面板')} | {cmd('修炼')} | {cmd('背包')}"
        )

        await _send_dice_markdown(dice_panel_cmd, content, fallback_text, event)
