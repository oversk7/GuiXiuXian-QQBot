"""
折光年·拨针系统 —— VIP定制装备「折光年」主动技能模块

功能：
- 拨针 签到     重置签到，可再签一次（每日1次）
- 拨针 闭关     闭关立即按上限时长结算出关（每日1次）
- 拨针 讨伐     世界BOSS攻击次数+1（每日1次）
- 拨针 委托     额外刷新一个每日委托（每日1次）
- 折光年        查看怀表状态面板
"""

import copy
from datetime import datetime, timedelta, date
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
EQUIPMENT_ID = "vip_chrono_watch"
DIAL_KEY = "chrono_dial"  # vip_equipment_data 中的子键

# 每个拨针子技能的耐久消耗
DURABILITY_COST = {
    "sign": 3,
    "seclusion": 5,
    "boss": 5,
    "task": 3,
}

# 子技能中文映射
DIAL_NAMES = {
    "sign": "签到",
    "seclusion": "闭关",
    "boss": "讨伐",
    "task": "委托",
}

# 折光年配图
CHRONO_WATCH_IMG_URL = "https://wdcdn.qpic.cn/MTMxMDI2NjM3MjM0Njk2MTE_994029_sMhbTp-Np0a2gakM_1771007639"
MARKDOWN_TEMPLATE_ID = "102499345_1770445216"


async def _send_chrono_markdown(handler, title: str, desc: str, fallback_text: str, event: MessageEvent):
    """使用Markdown模板发送折光年反馈，失败时回退到纯文本"""
    try:
        template_params = [
            MessageMarkdownParams(key="title", values=[title]),
            MessageMarkdownParams(key="desc", values=[desc]),
            MessageMarkdownParams(key="imgurl", values=[CHRONO_WATCH_IMG_URL]),
            MessageMarkdownParams(key="width", values=["360"]),
            MessageMarkdownParams(key="height", values=["201"]),
            MessageMarkdownParams(key="hint", values=["快捷操作"]),
            MessageMarkdownParams(key="t1", values=["折光年"]),
            MessageMarkdownParams(key="t2", values=["面板"]),
            MessageMarkdownParams(key="t3", values=["修炼"]),
            MessageMarkdownParams(key="t4", values=["签到"]),
        ]

        markdown_msg = MessageMarkdown(
            custom_template_id=MARKDOWN_TEMPLATE_ID,
            params=template_params
        )

        await handler.finish(MessageSegment.markdown(markdown_msg))
    except (ValueError, TypeError, KeyError):
        # Markdown构建失败，回退到纯文本
        await handler.finish(message_add_head(fallback_text, event))


# ==================== 辅助函数 ====================

async def _get_chrono_watch_instance(session: AsyncSession, player_id: str) -> ItemInstance | None:
    """查找玩家已装备的折光年"""
    stmt = select(ItemInstance).where(
        ItemInstance.player_id == player_id,
        ItemInstance.equipped == True,
        ItemInstance.item_id == EQUIPMENT_ID,
    )
    return (await session.execute(stmt)).scalars().first()


def _get_dial_data(player: Player) -> dict:
    """获取拨针数据（自动按日期重置）"""
    data = player.vip_equipment_data or {}
    dial = data.get(DIAL_KEY, {})
    today_str = date.today().isoformat()

    # 检查每个子技能是否需要按日期重置
    for key in DIAL_NAMES:
        entry = dial.get(key, {})
        if entry.get("date") != today_str:
            dial[key] = {"date": today_str, "used": 0}

    return dial


def _set_dial_data(player: Player, dial: dict):
    """保存拨针数据（通过重建dict + flag_modified确保SQLAlchemy一定写入数据库）"""
    data = dict(player.vip_equipment_data or {})
    data[DIAL_KEY] = copy.deepcopy(dial)
    player.vip_equipment_data = data
    # 强制标记字段为已修改，防止MutableDict/JSON变更检测失败导致数据未持久化
    flag_modified(player, "vip_equipment_data")


def _check_dial_available(dial: dict, skill_key: str) -> bool:
    """检查指定拨针技能今日是否可用"""
    entry = dial.get(skill_key, {})
    return entry.get("used", 0) < 1


def _mark_dial_used(dial: dict, skill_key: str):
    """标记拨针技能已使用"""
    today_str = date.today().isoformat()
    dial[skill_key] = {"date": today_str, "used": 1}


async def _deduct_durability(session: AsyncSession, player_id: str, amount: int) -> bool:
    """扣除折光年耐久度，返回是否成功"""
    watch = await _get_chrono_watch_instance(session, player_id)
    if not watch:
        return False
    if watch.durability < amount:
        return False
    watch.durability = max(0, watch.durability - amount)
    session.add(watch)
    return True


# ==================== 指令：拨针 ====================
dial_cmd = on_command("拨针", block=True, priority=5)


@dial_cmd.handle()
async def handle_dial(event: MessageEvent, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await dial_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await dial_cmd.finish("⛔ 请先创建角色")

        # 检查是否装备了折光年
        watch = await _get_chrono_watch_instance(session, player.id)
        if not watch:
            await dial_cmd.finish("⛔ 你未装备「折光年」，无法使用拨针技能")

        if not arg:
            await dial_cmd.finish(
                "⛔ 请指定拨针类型\n"
                "━━━━━━━━━━━━━\n"
                "【拨针 签到】重置签到\n"
                "【拨针 闭关】立即出关（按上限时长结算）\n"
                "【拨针 讨伐】世界BOSS攻击次数+1\n"
                "【拨针 委托】额外刷新一个委托\n"
                "━━━━━━━━━━━━━\n"
                "💡 使用【折光年】查看怀表状态"
            )

        if arg == "签到":
            await _handle_dial_sign(session, player, watch, event)
        elif arg == "闭关":
            await _handle_dial_seclusion(session, player, watch, event)
        elif arg == "讨伐":
            await _handle_dial_boss(session, player, watch, event)
        elif arg == "委托":
            await _handle_dial_task(session, player, watch, event)
        else:
            await dial_cmd.finish(
                f"⛔ 未知的拨针类型「{arg}」\n"
                "可用：签到、闭关、讨伐、委托"
            )


# ==================== 拨针·签到 ====================

async def _handle_dial_sign(session: AsyncSession, player: Player, watch: ItemInstance, event: MessageEvent):
    """拨针·签到：重置签到，允许再签一次"""
    dial = _get_dial_data(player)

    if not _check_dial_available(dial, "sign"):
        await dial_cmd.finish("⛔ 今日「拨针·签到」已使用 (1/1)")

    # 检查耐久
    cost = DURABILITY_COST["sign"]
    if watch.durability < cost:
        await dial_cmd.finish(f"⛔ 折光年耐久不足（需要{cost}，当前{watch.durability}）\n💡 请先修理装备")

    # 检查今日是否已签到（只有已签到才有重置意义）
    today = date.today()
    last_sign_date = player.last_sign.date() if player.last_sign else None
    if last_sign_date != today:
        await dial_cmd.finish("⛔ 你今天还没签到，无需拨针\n💡 请先使用【签到】")

    # 执行：将 last_sign 设为昨天，使签到系统允许再次签到
    player.last_sign = datetime.now() - timedelta(days=1)

    # 设置标记，让签到系统识别"拨针重置"，不增加连续签到天数
    data = dict(player.vip_equipment_data or {})
    data["dial_sign_reset"] = True
    player.vip_equipment_data = data

    # 标记已用 + 扣耐久
    _mark_dial_used(dial, "sign")
    _set_dial_data(player, dial)
    watch.durability = max(0, watch.durability - cost)

    session.add(player)
    session.add(watch)
    await session.commit()

    title = "⏱️ 折光年 · 拨针·签到"
    desc = (
        f"🕰️ 指针逆转，秒针走过的路被一一抹去。\r"
        f"怀表表面泛起淡淡光晕——今天，重新来过。\r"
        f"\r"
        f"✅ 签到已重置，可再次【签到】\r"
        f"⚠️ 不会额外增加连续签到天数\r"
        f"🔋 耐久 -{cost}（剩余 {watch.durability}/360）\r"
        f"💡 今日拨针·签到 (1/1)"
    )
    fallback = (
        "⏱️ 怀表指针逆转——今天重新开始了\n"
        "━━━━━━━━━━━━━\n"
        "✅ 签到已重置，可再次【签到】\n"
        "⚠️ 不会额外增加连续签到天数\n"
        f"🔋 耐久 -{cost}（剩余 {watch.durability}/360）\n"
        "━━━━━━━━━━━━━\n"
        "💡 今日拨针·签到 (1/1)"
    )
    await _send_chrono_markdown(dial_cmd, title, desc, fallback, event)


# ==================== 拨针·闭关 ====================

async def _handle_dial_seclusion(session: AsyncSession, player: Player, watch: ItemInstance, event: MessageEvent):
    """拨针·闭关：立即按上限时长结算出关"""
    dial = _get_dial_data(player)

    if not _check_dial_available(dial, "seclusion"):
        await dial_cmd.finish("⛔ 今日「拨针·闭关」已使用 (1/1)")

    # 检查耐久
    cost = DURABILITY_COST["seclusion"]
    if watch.durability < cost:
        await dial_cmd.finish(f"⛔ 折光年耐久不足（需要{cost}，当前{watch.durability}）\n💡 请先修理装备")

    # 检查是否在闭关中
    if not player.is_secluded:
        await dial_cmd.finish("⛔ 你当前未在闭关中\n💡 请先使用【闭关】进入闭关状态")

    # 获取月卡权益以确定闭关时长上限
    from ..models.monthly_card import get_player_card_benefits
    benefits = await get_player_card_benefits(session, player.id)
    max_seclusion_time = benefits["seclusion_time_limit"]  # 秒

    # 核心逻辑：将闭关开始时间往前拨到上限，使出关结算按满时长计算
    player.seclusion_start_time = datetime.now() - timedelta(seconds=max_seclusion_time)

    # 标记已用 + 扣耐久
    _mark_dial_used(dial, "seclusion")
    _set_dial_data(player, dial)
    watch.durability = max(0, watch.durability - cost)

    session.add(player)
    session.add(watch)
    await session.commit()

    seclusion_hours = max_seclusion_time // 3600

    title = "⏱️ 折光年 · 拨针·闭关"
    desc = (
        f"🕰️ 齿轮疯转，时间被拧成一条细线。\r"
        f"你睁眼时，功法已在体内走完了全部周天。\r"
        f"\r"
        f"⏩ 闭关时间加速至上限（{seclusion_hours}小时）\r"
        f"✅ 现在使用【出关】即可按满时长结算\r"
        f"🔋 耐久 -{cost}（剩余 {watch.durability}/360）\r"
        f"💡 今日拨针·闭关 (1/1)"
    )
    fallback = (
        "⏱️ 怀表疯狂旋转——时间被压缩了\n"
        "━━━━━━━━━━━━━\n"
        f"⏩ 闭关时间已加速至上限（{seclusion_hours}小时）\n"
        "✅ 现在使用【出关】即可按满时长结算\n"
        f"🔋 耐久 -{cost}（剩余 {watch.durability}/360）\n"
        "━━━━━━━━━━━━━\n"
        "💡 今日拨针·闭关 (1/1)"
    )
    await _send_chrono_markdown(dial_cmd, title, desc, fallback, event)


# ==================== 拨针·讨伐 ====================

async def _handle_dial_boss(session: AsyncSession, player: Player, watch: ItemInstance, event: MessageEvent):
    """拨针·讨伐：世界BOSS攻击次数+1"""
    dial = _get_dial_data(player)

    if not _check_dial_available(dial, "boss"):
        await dial_cmd.finish("⛔ 今日「拨针·讨伐」已使用 (1/1)")

    # 检查耐久
    cost = DURABILITY_COST["boss"]
    if watch.durability < cost:
        await dial_cmd.finish(f"⛔ 折光年耐久不足（需要{cost}，当前{watch.durability}）\n💡 请先修理装备")

    # 查找当前世界BOSS周期和玩家伤害记录
    from ..infrastructure.repositories.world_boss_cycle_repository import WorldBossCycleRepository
    from ..infrastructure.repositories.world_boss_damage_repository import WorldBossDamageRepository
    from ..models.world_boss import WorldBossDamage

    cycle_repo = WorldBossCycleRepository(session)
    damage_repo = WorldBossDamageRepository(session)

    # 获取当前活跃周期
    current_cycle = await cycle_repo.get_current_cycle()
    if not current_cycle:
        await dial_cmd.finish("⛔ 当前没有活跃的世界BOSS\n💡 等待下次世界BOSS刷新")

    # 获取或创建伤害记录
    damage_record = await damage_repo.get_or_create(current_cycle.id, player.id)

    # 检查今日日期重置
    today_str = datetime.now().strftime("%Y-%m-%d")
    if damage_record.attacks_reset_date != today_str:
        damage_record.attacks_today = 0
        damage_record.attacks_reset_date = today_str

    # 检查是否已有剩余次数（如果还没用完就不需要拨针）
    from ..world_boss.service_new import WorldBossService
    if damage_record.attacks_today < WorldBossService.DAILY_ATTACK_LIMIT:
        remaining = WorldBossService.DAILY_ATTACK_LIMIT - damage_record.attacks_today
        await dial_cmd.finish(
            f"⛔ 你今日还有 {remaining} 次攻击机会\n"
            "💡 请先用完再使用拨针·讨伐"
        )

    # 恢复1次攻击次数
    damage_record.attacks_today = max(0, damage_record.attacks_today - 1)
    await damage_repo.update(damage_record)

    # 标记已用 + 扣耐久
    _mark_dial_used(dial, "boss")
    _set_dial_data(player, dial)
    watch.durability = max(0, watch.durability - cost)

    session.add(player)
    session.add(watch)
    await session.commit()

    title = "⏱️ 折光年 · 拨针·讨伐"
    desc = (
        f"🕰️ 分针拨回一格，那场战斗从记忆中褪去。\r"
        f"怀表嗡鸣一声——又多了一次机会。\r"
        f"\r"
        f"✅ 世界BOSS攻击次数 +1\r"
        f"🎯 当前剩余：1/{WorldBossService.DAILY_ATTACK_LIMIT}\r"
        f"🔋 耐久 -{cost}（剩余 {watch.durability}/360）\r"
        f"💡 今日拨针·讨伐 (1/1)"
    )
    fallback = (
        "⏱️ 怀表拨回了一场战斗的时间\n"
        "━━━━━━━━━━━━━\n"
        "✅ 世界BOSS攻击次数 +1\n"
        f"🎯 当前剩余：1/{WorldBossService.DAILY_ATTACK_LIMIT}\n"
        f"🔋 耐久 -{cost}（剩余 {watch.durability}/360）\n"
        "━━━━━━━━━━━━━\n"
        "💡 今日拨针·讨伐 (1/1)"
    )
    await _send_chrono_markdown(dial_cmd, title, desc, fallback, event)


# ==================== 拨针·委托 ====================

async def _handle_dial_task(session: AsyncSession, player: Player, watch: ItemInstance, event: MessageEvent):
    """拨针·委托：额外刷新一个每日委托（无视3个上限）"""
    dial = _get_dial_data(player)

    if not _check_dial_available(dial, "task"):
        await dial_cmd.finish("⛔ 今日「拨针·委托」已使用 (1/1)")

    # 检查耐久
    cost = DURABILITY_COST["task"]
    if watch.durability < cost:
        await dial_cmd.finish(f"⛔ 折光年耐久不足（需要{cost}，当前{watch.durability}）\n💡 请先修理装备")

    # 强制生成新任务（无视上限，VIP特权）
    from ..infrastructure.repositories.daily_task_repository import DailyTaskRepository
    from ..daily_task.service_new import DailyTaskService

    task_repo = DailyTaskRepository(session)

    # 获取今日已有任务数（用于显示）——直接用 repo 查询，无需完整 Service
    today = date.today()
    existing_tasks = await task_repo.find_all_by_player_and_date(player.id, today)
    current_count = len(existing_tasks)

    # 强制生成（即使达到上限也生成，这是VIP特权）
    # 直接调用内部生成逻辑，跳过上限检查
    import random
    from ..models.daily_task import DailyTask, TaskType

    target_x = random.randint(-200, 200)
    target_y = random.randint(-200, 200)
    city_name = random.choice(DailyTaskService.CITY_NAMES)
    ghost_name = random.choice(DailyTaskService.GHOST_NAMES)
    selected_task_type = random.choice(list(TaskType))

    task_descriptions = DailyTaskService._get_task_descriptions_by_type(selected_task_type, city_name, ghost_name)
    description = random.choice(task_descriptions)

    enemy_level = max(1, player.level + random.randint(-5, 5))
    enemy_stats = DailyTaskService._calculate_enemy_stats(enemy_level, player)
    rewards = DailyTaskService._calculate_rewards(player.level, enemy_level, selected_task_type)
    task_title, enemy_name = DailyTaskService._generate_task_title_and_enemy(
        selected_task_type, city_name, ghost_name
    )

    new_task = DailyTask(
        player_id=player.id,
        task_type=selected_task_type,
        title=task_title,
        description=description,
        target_region="大都会",
        target_x=target_x,
        target_y=target_y,
        enemy_name=enemy_name,
        enemy_level=enemy_level,
        enemy_hp=enemy_stats["hp"],
        enemy_attack=enemy_stats["attack"],
        enemy_defense=enemy_stats["defense"],
        enemy_agility=enemy_stats["agility"],
        exp_reward=rewards["exp"],
        gold_reward=rewards["gold"],
        guild_points_reward=rewards["guild_points"],
        task_date=today,
    )
    session.add(new_task)

    # 标记已用 + 扣耐久
    _mark_dial_used(dial, "task")
    _set_dial_data(player, dial)
    watch.durability = max(0, watch.durability - cost)

    session.add(player)
    session.add(watch)
    await session.commit()

    title = "⏱️ 折光年 · 拨针·委托"
    desc = (
        f"🕰️ 齿轮咬合的声响中，一条新的因果线浮现。\r"
        f"怀表指向了某个本不该存在的方向。\r"
        f"\r"
        f"✅ 已刷新一个额外的每日委托\r"
        f"📋 委托{current_count + 1}：{task_title}\r"
        f"📍 目标：大都会 ({target_x},{target_y})\r"
        f"👹 敌人：{enemy_name} Lv.{enemy_level}\r"
        f"💰 奖励：{new_task.get_reward_summary(bool(player.guild_id))}\r"
        f"🔋 耐久 -{cost}（剩余 {watch.durability}/360）\r"
        f"💡 使用【接取任务 {current_count + 1}】接取此委托"
    )
    fallback = (
        "⏱️ 怀表齿轮转动——新的因果浮现\n"
        "━━━━━━━━━━━━━\n"
        f"✅ 已刷新一个额外的每日委托\n"
        f"📋 委托{current_count + 1}：{task_title}\n"
        f"📍 目标：大都会 ({target_x},{target_y})\n"
        f"👹 敌人：{enemy_name} Lv.{enemy_level}\n"
        f"💰 奖励：{new_task.get_reward_summary(bool(player.guild_id))}\n"
        f"🔋 耐久 -{cost}（剩余 {watch.durability}/360）\n"
        "━━━━━━━━━━━━━\n"
        f"💡 使用【接取任务 {current_count + 1}】接取此委托\n"
        "💡 今日拨针·委托 (1/1)"
    )
    await _send_chrono_markdown(dial_cmd, title, desc, fallback, event)


# ==================== 指令：折光年（状态面板） ====================
panel_cmd = on_command("折光年", block=True, priority=5)


@panel_cmd.handle()
async def handle_panel(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await panel_cmd.finish("⛔ 你还没有创建角色或绑定账号")
            else:
                await panel_cmd.finish("⛔ 请先创建角色")

        # 检查是否装备了折光年
        watch = await _get_chrono_watch_instance(session, player.id)
        if not watch:
            await panel_cmd.finish("⛔ 你未装备「折光年」")

        # 获取拨针数据
        dial = _get_dial_data(player)

        # 构建面板
        lines = [
            "⏱️ 折光年",
            "━━━━━━━━━━━━━",
            f"🔋 耐久：{watch.durability}/360",
            "━━━━━━━━━━━━━",
            "⏳ 今日拨针：",
        ]

        for key, name in DIAL_NAMES.items():
            entry = dial.get(key, {})
            used = entry.get("used", 0)
            if used >= 1:
                lines.append(f"  {name}：❌ 已用 (1/1)")
            else:
                lines.append(f"  {name}：✅ 可用 (0/1)")

        # 今日成长统计（从折光年装备的 extra_attrs 读取）
        # 战后持久化写入 cw_hp_cnt / cw_atk_cnt
        extra = watch.extra_attrs or {}
        today_str = date.today().isoformat()

        hp_gains_today = 0
        atk_gains_today = 0

        if extra.get("cw_hp_day") == today_str:
            hp_gains_today = int(extra.get("cw_hp_cnt", 0))
        if extra.get("cw_atk_day") == today_str:
            atk_gains_today = int(extra.get("cw_atk_cnt", 0))

        lines.extend([
            "━━━━━━━━━━━━━",
            "📊 今日成长：",
            f"  时间掠夺：+{hp_gains_today * 2}体质 ({hp_gains_today}/20)",
            f"  终焉铭刻：+{atk_gains_today * 2}攻击 ({atk_gains_today}/20)",
            "━━━━━━━━━━━━━",
            "💡 操作：",
            "【拨针 签到】重置签到",
            "【拨针 闭关】立即满时长出关",
            "【拨针 讨伐】BOSS次数+1",
            "【拨针 委托】额外刷新委托",
        ])

        fallback_text = "\n".join(lines)

        # 构建Markdown desc
        dial_status_parts = []
        for key, name in DIAL_NAMES.items():
            entry = dial.get(key, {})
            used = entry.get("used", 0)
            if used >= 1:
                dial_status_parts.append(f"  {name}：❌ 已用 (1/1)")
            else:
                dial_status_parts.append(f"  {name}：✅ 可用 (0/1)")
        dial_status = "\r".join(dial_status_parts)

        title = "⏱️ 折光年 · 怀表状态"
        desc = (
            f"🕰️ 光会拐弯，时间也会。\r"
            f"\r"
            f"🔋 耐久：{watch.durability}/360\r"
            f"\r"
            f"⏳ 今日拨针：\r"
            f"{dial_status}\r"
            f"\r"
            f"📊 今日成长：\r"
            f"  时间掠夺：+{hp_gains_today * 2}体质 ({hp_gains_today}/20)\r"
            f"  终焉铭刻：+{atk_gains_today * 2}攻击 ({atk_gains_today}/20)"
        )

        await _send_chrono_markdown(panel_cmd, title, desc, fallback_text, event)
