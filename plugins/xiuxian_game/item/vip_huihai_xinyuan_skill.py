"""
慧海心元珠 —— VIP定制装备「慧海心元珠」技能模块

功能：
- 行路明心：每抵达地图上一处新坐标，永久+50理智上限（每日5次）
- 静修凝神：每次修炼，永久+50理智上限（每日5次）
- 胜负归元：每次战斗胜利，永久+30理智上限（每日8次）
- 慧海心元珠：查看状态面板

hooks 在 navigation.py / cultivate/core.py / attack_command.py / dungeon_battle.py 中调用本模块的 apply_* 函数。
"""

from datetime import date
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db import safe_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..models.vip_equipment_bonus import VIPEquipmentBonus
from ..platform_utils import get_unified_player, is_guild_message
from ..utils import message_add_head

# ==================== 常量 ====================
EQUIPMENT_ID = "vip_huihai_xinyuan"

# 行路明心：每次+50理智上限，每日5次
VISIT_BONUS = 50
VISIT_DAILY_LIMIT = 5
# 静修凝神：每次+50理智上限，每日5次
CULTIVATE_BONUS = 50
CULTIVATE_DAILY_LIMIT = 5
# 胜负归元：每次+30理智上限，每日8次
KILL_BONUS = 30
KILL_DAILY_LIMIT = 8

# 面板配图（复用已有素材）
HUIHAI_IMG_URL = "https://wdcdn.qpic.cn/MTMxMDI2NjM3MjM0Njk2MTE_59001_A9dXjBV6LK2wDOCq_1770915268"
MARKDOWN_TEMPLATE_ID = "102499345_1770445216"


# ==================== 辅助函数 ====================

def _today_key() -> str:
    return date.today().isoformat()


async def _get_equipped_instance(session: AsyncSession, player_id: str) -> ItemInstance | None:
    """查找玩家已装备的慧海心元珠"""
    stmt = select(ItemInstance).where(
        ItemInstance.player_id == player_id,
        ItemInstance.equipped == True,
        ItemInstance.item_id == EQUIPMENT_ID,
    )
    return (await session.execute(stmt)).scalars().first()


async def _apply_max_mp_growth(
    session: AsyncSession,
    player: Player,
    day_key: str,
    cnt_key: str,
    bonus: int,
    daily_limit: int,
    effect_name: str,
) -> str | None:
    """
    通用成长逻辑：检查装备、校验日限、累加 VIPEquipmentBonus.max_mp、更新 player.max_mp、写回计数。

    Returns:
        成长反馈文案；未装备/达上限时返回相应提示或 None（未装备时返回 None 完全静默）
    """
    inst = await _get_equipped_instance(session, player.id)
    if not inst:
        return None

    extra = dict(inst.extra_attrs or {})
    today = _today_key()
    if extra.get(day_key) != today:
        extra[day_key] = today
        extra[cnt_key] = 0

    current_cnt = int(extra.get(cnt_key, 0))
    if current_cnt >= daily_limit:
        # 已达上限：静默不刷屏（与夺伞步的达上限提示风格一致：仅在真正触发时返回文案）
        return None

    # 累加 VIP 装备加成表
    vip_bonus = await VIPEquipmentBonus.get_or_create(session, player.id)
    vip_bonus.add_bonus("max_mp", bonus)

    # 同步更新玩家当前 max_mp（后续 recalculate_attributes 会重新计算，但即时更新更稳）
    player.max_mp = (player.max_mp or 0) + bonus

    extra[cnt_key] = current_cnt + 1
    inst.extra_attrs = extra
    session.add(inst)
    session.add(player)

    total_today = extra[cnt_key] * bonus
    total_cap = daily_limit * bonus
    return (
        f"🌊 {effect_name}：慧光沉入神海，理智上限+{bonus}"
        f"（今日 +{total_today}/{total_cap}）"
    )


# ==================== 对外接口：三种成长钩子 ====================

async def apply_visit_max_mp(session: AsyncSession, player: Player) -> str | None:
    """行路明心：到达新坐标时调用"""
    return await _apply_max_mp_growth(
        session, player,
        day_key="hh_visit_day",
        cnt_key="hh_visit_cnt",
        bonus=VISIT_BONUS,
        daily_limit=VISIT_DAILY_LIMIT,
        effect_name="行路明心",
    )


async def apply_cultivate_max_mp(session: AsyncSession, player: Player) -> str | None:
    """静修凝神：修炼完成后调用"""
    return await _apply_max_mp_growth(
        session, player,
        day_key="hh_cultivate_day",
        cnt_key="hh_cultivate_cnt",
        bonus=CULTIVATE_BONUS,
        daily_limit=CULTIVATE_DAILY_LIMIT,
        effect_name="静修凝神",
    )


async def apply_kill_max_mp(session: AsyncSession, player: Player) -> str | None:
    """胜负归元：战斗胜利时调用"""
    return await _apply_max_mp_growth(
        session, player,
        day_key="hh_kill_day",
        cnt_key="hh_kill_cnt",
        bonus=KILL_BONUS,
        daily_limit=KILL_DAILY_LIMIT,
        effect_name="胜负归元",
    )


# ==================== 指令：慧海心元珠（状态面板） ====================
huihai_panel_cmd = on_command("慧海心元珠", block=True, priority=9)


@huihai_panel_cmd.handle()
async def handle_huihai_panel(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await huihai_panel_cmd.finish("⛔ 你还没有创建角色或绑定账号")
            else:
                await huihai_panel_cmd.finish("⛔ 请先创建角色")

        inst = await _get_equipped_instance(session, player.id)
        if not inst:
            await huihai_panel_cmd.finish("⛔ 你未装备「慧海心元珠」")

        extra = inst.extra_attrs or {}
        today = _today_key()

        def _today_cnt(day_key: str, cnt_key: str) -> int:
            if extra.get(day_key) == today:
                return int(extra.get(cnt_key, 0))
            return 0

        visit_cnt = _today_cnt("hh_visit_day", "hh_visit_cnt")
        cultivate_cnt = _today_cnt("hh_cultivate_day", "hh_cultivate_cnt")
        kill_cnt = _today_cnt("hh_kill_day", "hh_kill_cnt")

        # 累计加成
        vip_bonus = await VIPEquipmentBonus.get_or_create(session, player.id)
        total_mp_bonus = int(vip_bonus.get_total_bonus().get("max_mp", 0))

        # ---- 构建纯文本面板 ----
        lines = [
            "🌊 慧海心元珠",
            "━━━━━━━━━━━━━",
            f"🔋 耐久：{inst.durability}/360",
            f"💎 累计理智上限加成：+{total_mp_bonus}",
            "━━━━━━━━━━━━━",
            "📊 今日成长：",
            f"  🌊 行路明心：+{visit_cnt * VISIT_BONUS}/{VISIT_DAILY_LIMIT * VISIT_BONUS}（{visit_cnt}/{VISIT_DAILY_LIMIT}次）",
            f"  🧘 静修凝神：+{cultivate_cnt * CULTIVATE_BONUS}/{CULTIVATE_DAILY_LIMIT * CULTIVATE_BONUS}（{cultivate_cnt}/{CULTIVATE_DAILY_LIMIT}次）",
            f"  ⚔️ 胜负归元：+{kill_cnt * KILL_BONUS}/{KILL_DAILY_LIMIT * KILL_BONUS}（{kill_cnt}/{KILL_DAILY_LIMIT}次）",
            "━━━━━━━━━━━━━",
            "💡 行路/修炼/胜利皆化慧光沉入神海",
            "💡 每日 0 点刷新计数",
        ]
        fallback_text = "\n".join(lines)

        # ---- 构建 Markdown desc ----
        title = "🌊 慧海心元珠 · 神海澄明"
        desc = (
            f"🌊 海纳万象，心藏元珠；一念归澄，慧光不灭。\r"
            f"\r"
            f"🔋 耐久：{inst.durability}/360\r"
            f"💎 累计理智上限加成：+{total_mp_bonus}\r"
            f"\r"
            f"📊 今日成长：\r"
            f"  🌊 行路明心：+{visit_cnt * VISIT_BONUS}/{VISIT_DAILY_LIMIT * VISIT_BONUS}（{visit_cnt}/{VISIT_DAILY_LIMIT}次）\r"
            f"  🧘 静修凝神：+{cultivate_cnt * CULTIVATE_BONUS}/{CULTIVATE_DAILY_LIMIT * CULTIVATE_BONUS}（{cultivate_cnt}/{CULTIVATE_DAILY_LIMIT}次）\r"
            f"  ⚔️ 胜负归元：+{kill_cnt * KILL_BONUS}/{KILL_DAILY_LIMIT * KILL_BONUS}（{kill_cnt}/{KILL_DAILY_LIMIT}次）"
        )

        try:
            template_params = [
                MessageMarkdownParams(key="title", values=[title]),
                MessageMarkdownParams(key="desc", values=[desc]),
                MessageMarkdownParams(key="imgurl", values=[HUIHAI_IMG_URL]),
                MessageMarkdownParams(key="width", values=["360"]),
                MessageMarkdownParams(key="height", values=["201"]),
                MessageMarkdownParams(key="hint", values=["快捷操作"]),
                MessageMarkdownParams(key="t1", values=["修炼"]),
                MessageMarkdownParams(key="t2", values=["面板"]),
                MessageMarkdownParams(key="t3", values=["签到"]),
                MessageMarkdownParams(key="t4", values=["背包"]),
            ]
            markdown_msg = MessageMarkdown(
                custom_template_id=MARKDOWN_TEMPLATE_ID,
                params=template_params
            )
            await huihai_panel_cmd.finish(MessageSegment.markdown(markdown_msg))
        except (ValueError, TypeError, KeyError):
            await huihai_panel_cmd.finish(message_add_head(fallback_text, event))
