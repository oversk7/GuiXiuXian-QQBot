"""
诡面骰·骰相·乱 —— VIP定制装备「诡面骰」主动技能模块

功能：
- 掷骰        摇动八面骰，随机+100%一项特殊属性（持续一场战斗，每日1次）
- 诡面骰      查看诡面骰状态面板
"""

import copy
import random
from datetime import date
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..platform_utils import get_unified_player, is_guild_message
from ..utils import message_add_head


# ==================== 常量 ====================
EQUIPMENT_ID = "vip_ghost_dice"
DICE_KEY = "dice_roll"  # vip_equipment_data 中的子键
DURABILITY_COST = 5      # 掷骰耐久消耗
DAILY_ROLL_LIMIT = 10    # 每日掷骰次数上限

# Markdown模板
MARKDOWN_TEMPLATE_ID = "102499345_1770445216"
# 诡面骰配图
GHOST_DICE_IMG_URL = "https://wdcdn.qpic.cn/MTMxMDI2NjM3MjM0Njk2MTE_350520_RPoKZCpD58Z3cLIm_1771857949"

# 八面骰对应的8种特殊属性（排除暴击率 critical_rate）
DICE_FACES = [
    {"attribute": "critical_power",   "cn": "暴击伤害", "icon": "💥", "desc": "暴击时伤害翻倍"},
    {"attribute": "combo_rate",       "cn": "连击率",   "icon": "⚡", "desc": "连击触发概率翻倍"},
    {"attribute": "counter_rate",     "cn": "反击率",   "icon": "🛡️", "desc": "反击触发概率翻倍"},
    {"attribute": "dodge_rate",       "cn": "闪避率",   "icon": "💨", "desc": "闪避触发概率翻倍"},
    {"attribute": "accuracy_rate",    "cn": "命中率",   "icon": "🎯", "desc": "命中率翻倍"},
    {"attribute": "skill_crit_rate",  "cn": "灵爆率",   "icon": "🔮", "desc": "灵爆触发概率翻倍"},
    {"attribute": "penetration_rate", "cn": "穿透率",   "icon": "🗡️", "desc": "穿透比例翻倍"},
    {"attribute": "anti_crit_rate",   "cn": "抗暴率",   "icon": "🪨", "desc": "抗暴率翻倍"},
]


# ==================== Markdown发送 ====================

async def _send_dice_markdown(handler, title: str, desc: str, fallback_text: str, event: MessageEvent):
    """使用Markdown模板发送诡面骰反馈，失败时回退到纯文本"""
    try:
        template_params = [
            MessageMarkdownParams(key="title", values=[title]),
            MessageMarkdownParams(key="desc", values=[desc]),
            MessageMarkdownParams(key="imgurl", values=[GHOST_DICE_IMG_URL]),
            MessageMarkdownParams(key="width", values=["360"]),
            MessageMarkdownParams(key="height", values=["201"]),
            MessageMarkdownParams(key="hint", values=["快捷操作"]),
            MessageMarkdownParams(key="t1", values=["诡面骰"]),
            MessageMarkdownParams(key="t2", values=["面板"]),
            MessageMarkdownParams(key="t3", values=["修炼"]),
            MessageMarkdownParams(key="t4", values=["背包"]),
        ]
        markdown_msg = MessageMarkdown(
            custom_template_id=MARKDOWN_TEMPLATE_ID,
            params=template_params
        )
        await handler.finish(MessageSegment.markdown(markdown_msg))
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
roll_dice_cmd = on_command("掷骰", block=True, priority=5)


@roll_dice_cmd.handle()
async def handle_roll_dice(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await roll_dice_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await roll_dice_cmd.finish("⛔ 请先创建角色")

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

        # 检查是否有未消耗的buff
        existing_buff = _get_dice_buff(player)
        if existing_buff:
            attr_cn = existing_buff.get("attribute_cn", "未知")
            await roll_dice_cmd.finish(
                f"⛔ 你还有未消耗的骰子buff：{attr_cn}+100%\n"
                "💡 进入一场战斗后自动生效并消耗"
            )

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
        title = "🎲 诡面骰 · 骰相·乱"
        desc = (
            f"🎲 骰子在指尖旋转，八面诡纹明灭不定。\r"
            f"它停下了——第{DICE_FACES.index(face) + 1}面朝上。\r"
            f"\r"
            f"{face['icon']} 命运指向：{face['cn']}\r"
            f"✨ 下一场战斗中 {face['cn']} +100%\r"
            f"💡 {face['desc']}\r"
            f"\r"
            f"🔋 耐久 -{DURABILITY_COST}（剩余 {dice_item.durability}/360）\r"
            f"💡 今日掷骰 ({used + 1}/{DAILY_ROLL_LIMIT})"
        )
        fallback = (
            "🎲 诡面骰 · 骰相·乱\n"
            "━━━━━━━━━━━━━\n"
            f"骰子停下——第{DICE_FACES.index(face) + 1}面朝上\n\n"
            f"{face['icon']} 命运指向：{face['cn']}\n"
            f"✨ 下一场战斗中 {face['cn']} +100%\n"
            f"💡 {face['desc']}\n"
            "━━━━━━━━━━━━━\n"
            f"🔋 耐久 -{DURABILITY_COST}（剩余 {dice_item.durability}/360）\n"
            f"💡 今日掷骰 ({used + 1}/{DAILY_ROLL_LIMIT})"
        )
        await _send_dice_markdown(roll_dice_cmd, title, desc, fallback, event)


# ==================== 指令：诡面骰（状态面板） ====================
dice_panel_cmd = on_command("诡面骰", block=True, priority=5)


@dice_panel_cmd.handle()
async def handle_dice_panel(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await dice_panel_cmd.finish("⛔ 你还没有创建角色或绑定账号")
            else:
                await dice_panel_cmd.finish("⛔ 请先创建角色")

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

        # ---- 构建Markdown desc ----
        faces_text = "  ".join(f"{f['icon']}{f['cn']}" for f in DICE_FACES)
        title = "🎲 诡面骰 · 八面诡纹"
        desc = (
            f"🎲 八面各刻一道诡纹，掷下时，命运便不再是你的了。\r"
            f"\r"
            f"🔋 耐久：{dice_item.durability}/360\r"
            f"\r"
            f"🎰 骰相·乱：\r"
            f"  掷骰：{roll_text}\r"
            f"  当前buff：{buff_text}\r"
            f"\r"
            f"📊 今日成长：\r"
            f"  骰相·噬：+{kill_cnt * 2}攻击 ({kill_cnt}/20)\r"
            f"\r"
            f"🎲 八面：{faces_text}"
        )

        await _send_dice_markdown(dice_panel_cmd, title, desc, fallback_text, event)
