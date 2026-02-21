"""
下位世界命令处理器
包括：降临、镇守、迎战、天灾商店、兑换
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from datetime import datetime, timedelta

from ..platform_utils import get_unified_player
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.db import AsyncSessionLocal
from .service import (
    get_or_create_stronghold,
    is_sealed,
    has_pending_hero,
    format_time_remaining,
    schedule_next_wave,
    process_battle_victory,
    process_battle_defeat,
    get_shop_display,
    SHOP_ITEMS,
    WAVE_INTERVAL_HOURS,
    HERO_TIMEOUT_HOURS,
)
from .hero_generator import hero_from_json
from ..battle.integration_helper import BattleIntegrationHelper


# ==================== 命令注册 ====================
descend_cmd = on_command("降临", block=True, priority=5)
guard_cmd = on_command("镇守", block=True, priority=5)
battle_hero_cmd = on_command("迎战", block=True, priority=5)
calamity_shop_cmd = on_command("天灾商店", block=True, priority=5)
redeem_cmd = on_command("兑换", block=True, priority=5)


# ==================== 【降临】 ====================
@descend_cmd.handle()
async def handle_descend(event: MessageEvent):
    """
    【降临】- 首次建立山寨显示降临文案，已建立则显示状态
    """
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await descend_cmd.finish("请先【注册】后再使用该功能")

        stronghold, is_new = await get_or_create_stronghold(uow, player.id)

        if is_new:
            # 首次降临：安排第一波英雄
            await schedule_next_wave(uow, stronghold, player.level)
            await uow.commit()

            msg = (
                "━━━━━━━━━━━━━━━━\n"
                "你在裂缝边缘停下。\n"
                "\n"
                "从这里往下看，诡异如潮水一样向外涌，\n"
                "目的地是一座叫「大都会」的城市。\n"
                "\n"
                "你想过关闭裂缝，\n"
                "但试过三次后发现没有用。\n"
                "诡异会继续出现，直到这个世界被淹没。\n"
                "\n"
                "「关不掉的话，那就换个做法。」\n"
                "\n"
                "你在这里建立了一个山寨。\n"
                "把自己当成天灾，\n"
                "把那些来阻止你的英雄当成敌人。\n"
                "\n"
                "你不是坏人。\n"
                "你只是站在不同的一边。\n"
                "\n"
                "━━━━━━━━━━━━━━━━\n"
                "🏴‍☠️ 下位世界·山寨已建立\n"
                f"📍 第 {stronghold.wave_number} 波\n"
                f"⏳ 下一波英雄将于 {WAVE_INTERVAL_HOURS} 小时后到达\n"
                "\n"
                "使用【镇守】查看状态\n"
                "使用【迎战】与英雄战斗"
            )
            await descend_cmd.finish(msg)

        # 已建立山寨，显示当前状态
        await _show_stronghold_status(stronghold, player.level)


async def _show_stronghold_status(stronghold, player_level: int):
    """显示山寨状态（共用逻辑）"""
    # 检查封印状态
    sealed, remaining = is_sealed(stronghold)
    if sealed:
        msg = (
            "━━━━━━━━━━━━━━━━\n"
            "🏴‍☠️ 下位世界·山寨状态\n"
            f"📍 第 {stronghold.wave_number} 波\n"
            f"💎 天灾点：{stronghold.calamity_points}\n"
            f"🏆 已胜利波次：{stronghold.total_waves_won}\n"
            "\n"
            f"⛓️ 封印中（剩余 {format_time_remaining(remaining)}）\n"
            "\n"
            "你被英雄击败了。\n"
            "他没有趁机补刀，只是说：\n"
            "「今天先到这里。」\n"
            "\n"
            "等封印解除后，会有新的英雄到来。"
        )
        await descend_cmd.finish(msg)

    # 检查是否有待战斗的英雄
    if has_pending_hero(stronghold):
        hero = hero_from_json(stronghold.pending_hero)
        time_since_arrival = datetime.now() - stronghold.next_wave_at
        timeout = stronghold.next_wave_at + timedelta(hours=HERO_TIMEOUT_HOURS)
        remaining_until_timeout = timeout - datetime.now()

        msg = (
            "━━━━━━━━━━━━━━━━\n"
            "🏴‍☠️ 下位世界·山寨状态\n"
            f"📍 第 {stronghold.wave_number} 波\n"
            f"💎 天灾点：{stronghold.calamity_points}\n"
            f"🏆 已胜利波次：{stronghold.total_waves_won}\n"
            "\n"
            f"⚔️ 英雄已到达：{hero['name']}\n"
            f"🎖️ Lv.{hero['level']}\n"
            f"📝 {hero['flavour']}\n"
            "\n"
            f"⏳ {format_time_remaining(remaining_until_timeout)}后撤退\n"
            "\n"
            "使用【迎战】与英雄战斗"
        )
        await descend_cmd.finish(msg)

    # 检查英雄是否已超时撤退
    if stronghold.next_wave_at and datetime.now() > stronghold.next_wave_at + timedelta(hours=HERO_TIMEOUT_HOURS):
        # 英雄已撤退，安排下一波
        def session_factory():
            return AsyncSessionLocal()

        async with UnitOfWork(session_factory) as uow:
            sh = await uow.lower_world_strongholds.get_by_player_id(stronghold.player_id)
            await schedule_next_wave(uow, sh, player_level)
            await uow.commit()

        msg = (
            "━━━━━━━━━━━━━━━━\n"
            "🏴‍☠️ 下位世界·山寨状态\n"
            f"📍 第 {stronghold.wave_number} 波\n"
            f"💎 天灾点：{stronghold.calamity_points}\n"
            f"🏆 已胜利波次：{stronghold.total_waves_won}\n"
            "\n"
            "🚶 英雄等待超时，已撤退\n"
            f"⏳ 下一波英雄将于 {WAVE_INTERVAL_HOURS} 小时后到达"
        )
        await descend_cmd.finish(msg)

    # 正在等待下一波英雄
    time_until_next = stronghold.next_wave_at - datetime.now()
    msg = (
        "━━━━━━━━━━━━━━━━\n"
        "🏴‍☠️ 下位世界·山寨状态\n"
        f"📍 第 {stronghold.wave_number} 波\n"
        f"💎 天灾点：{stronghold.calamity_points}\n"
        f"🏆 已胜利波次：{stronghold.total_waves_won}\n"
        "\n"
        f"⏳ 下一波英雄将于 {format_time_remaining(time_until_next)} 后到达"
    )
    await descend_cmd.finish(msg)


# ==================== 【镇守】 ====================
@guard_cmd.handle()
async def handle_guard(event: MessageEvent):
    """
    【镇守】- 查看山寨状态
    """
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await guard_cmd.finish("请先【注册】后再使用该功能")

        stronghold = await uow.lower_world_strongholds.get_by_player_id(player.id)
        if not stronghold:
            await guard_cmd.finish("你还未建立山寨。使用【降临】开始下位世界之旅")

        # 共用状态显示逻辑
        await _show_stronghold_status(stronghold, player.level)


# ==================== 【迎战】 ====================
@battle_hero_cmd.handle()
async def handle_battle_hero(event: MessageEvent):
    """
    【迎战】- 与当前波次英雄战斗（1v1，使用战斗引擎）
    """
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await battle_hero_cmd.finish("请先【注册】后再使用该功能")

        stronghold = await uow.lower_world_strongholds.get_by_player_id(player.id)
        if not stronghold:
            await battle_hero_cmd.finish("你还未建立山寨。使用【降临】开始下位世界之旅")

        # 检查封印状态
        sealed, remaining = is_sealed(stronghold)
        if sealed:
            await battle_hero_cmd.finish(
                f"⛓️ 你被封印中，剩余 {format_time_remaining(remaining)}\n"
                "等封印解除后才能继续战斗。"
            )

        # 检查是否有待战斗的英雄
        if not has_pending_hero(stronghold):
            # 检查是否超时撤退
            if stronghold.next_wave_at and datetime.now() > stronghold.next_wave_at + timedelta(hours=HERO_TIMEOUT_HOURS):
                await schedule_next_wave(uow, stronghold, player.level)
                await uow.commit()
                await battle_hero_cmd.finish(
                    "🚶 英雄等待超时，已撤退\n"
                    f"⏳ 下一波英雄将于 {WAVE_INTERVAL_HOURS} 小时后到达"
                )
            else:
                time_until_next = stronghold.next_wave_at - datetime.now()
                await battle_hero_cmd.finish(
                    f"⏳ 下一波英雄将于 {format_time_remaining(time_until_next)} 后到达\n"
                    "请耐心等待。"
                )

        # 获取英雄数据
        hero = hero_from_json(stronghold.pending_hero)

        # 临时保存玩家HP（天灾玩法不消耗真实HP）
        original_hp = player.hp

        # 构建怪物属性
        monster_stats = {
            "hp": hero["hp"],
            "attack": hero["attack"],
            "defense": hero["defense"],
            "agility": hero["agility"],
        }
        # 添加特殊属性
        for key in ("crit_rate", "combo_rate", "counter_rate", "lifesteal", "ignore_defense"):
            if key in hero:
                monster_stats[key] = hero[key]

        # 执行战斗
        timestamp = int(datetime.now().timestamp())
        victory, battle_log, damage_taken, post_effects = await BattleIntegrationHelper.enhanced_player_vs_monster_battle_v2(
            player=player,
            monster_stats=monster_stats,
            monster_name=hero["name"],
            session=uow.session,
            seed=f"LW:{player.id}:{timestamp}",
            max_rounds=30,
        )

        # 恢复玩家HP
        player.hp = original_hp
        uow.session.add(player)

        # 处理战斗结果
        if victory:
            # 胜利
            points = await process_battle_victory(uow, stronghold, player.level)
            await uow.commit()

            # 使用 he/she 代词
            pronoun = "他" if "男" in hero.get("title", "") or any(x in hero["name"] for x in ["艾伦", "托尔", "克劳德", "赛勒斯", "加文", "罗伦", "赫克托"]) else "她"

            msg = (
                f"{battle_log}\n"
                "\n"
                "━━━━━━━━━━━━━━━━\n"
                f"……{hero['name']} 倒下了。\n"
                "\n"
                f"{pronoun}望着你,没有仇恨,只是问:\n"
                "「你们那边……也会有人哭吗?」\n"
                "\n"
                "你没有回答。\n"
                "你身后,诡异继续往外涌。\n"
                "\n"
                f"+{points}天灾点(当前:{stronghold.calamity_points}点)\n"
                "「大都会那边有人因此平安了。\n"
                " 他们不知道你的名字。」\n"
                "\n"
                f"⏳ 下一波英雄将于 {WAVE_INTERVAL_HOURS} 小时后到达"
            )
            await battle_hero_cmd.finish(msg)
        else:
            # 失败
            await process_battle_defeat(uow, stronghold)
            await uow.commit()

            msg = (
                f"{battle_log}\n"
                "\n"
                "━━━━━━━━━━━━━━━━\n"
                "你倒下了。\n"
                "\n"
                f"{hero['name']} 没有趁机补刀,只是站在原地,\n"
                "把武器插回剑鞘。\n"
                "\n"
                "「走吧,天灾。\n"
                " 今天先到这里。」\n"
                "\n"
                "⛓️ 你被封印24小时"
            )
            await battle_hero_cmd.finish(msg)


# ==================== 【天灾商店】 ====================
@calamity_shop_cmd.handle()
async def handle_calamity_shop(event: MessageEvent):
    """
    【天灾商店】- 查看商品列表
    """
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await calamity_shop_cmd.finish("请先【注册】后再使用该功能")

        stronghold = await uow.lower_world_strongholds.get_by_player_id(player.id)
        if not stronghold:
            await calamity_shop_cmd.finish("你还未建立山寨。使用【降临】开始下位世界之旅")

        msg = (
            f"{get_shop_display()}\n"
            f"\n"
            f"💎 你的天灾点：{stronghold.calamity_points}"
        )
        await calamity_shop_cmd.finish(msg)


# ==================== 【兑换】 ====================
@redeem_cmd.handle()
async def handle_redeem(event: MessageEvent, args: Message = CommandArg()):
    """
    【兑换 XXX】- 购买商品
    """
    item_name = args.extract_plain_text().strip()
    if not item_name:
        await redeem_cmd.finish("请指定要兑换的商品，如【兑换 修炼加速（2小时）】")

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await redeem_cmd.finish("请先【注册】后再使用该功能")

        stronghold = await uow.lower_world_strongholds.get_by_player_id(player.id)
        if not stronghold:
            await redeem_cmd.finish("你还未建立山寨。使用【降临】开始下位世界之旅")

        # 查找商品
        item = None
        for shop_item in SHOP_ITEMS:
            if shop_item["name"] == item_name or shop_item["id"] == item_name:
                item = shop_item
                break

        if not item:
            await redeem_cmd.finish(
                f"未找到商品「{item_name}」\n"
                "使用【天灾商店】查看可兑换的商品"
            )

        # 检查天灾点是否足够
        if stronghold.calamity_points < item["price"]:
            await redeem_cmd.finish(
                f"天灾点不足！\n"
                f"需要：{item['price']}点\n"
                f"当前：{stronghold.calamity_points}点"
            )

        # 扣除天灾点
        stronghold.calamity_points -= item["price"]
        uow.session.add(stronghold)

        # TODO: 根据商品ID发放奖励（需要在后续任务实现）
        # 这里仅作为占位符，实际效果需要与buff系统、称号系统集成
        msg = (
            f"✅ 兑换成功！\n"
            f"获得：{item['name']}\n"
            f"剩余天灾点：{stronghold.calamity_points}\n"
            "\n"
            f"📝 {item['desc']}\n"
            "\n"
            "⚠️ 商品效果将在后续版本中实装"
        )

        await uow.commit()
        await redeem_cmd.finish(msg)
