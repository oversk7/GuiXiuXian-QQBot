"""
下位世界命令处理器
包括：降临、镇守、迎战、天灾商店、兑换
"""
import random
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
    BATTLE_COOLDOWN_MINUTES,
    SEAL_DURATION_HOURS,
)
from .hero_generator import hero_from_json
from ..battle.integration_helper import BattleIntegrationHelper
from ..battle.battle_markdown import build_battle_markdown
from ..battle.battle_log_filter import filter_battle_log, get_player_log_mode
from ..utils_markdown import cmd, build_markdown


# ==================== 命令注册 ====================
descend_cmd = on_command("降临", block=True, priority=13)
guard_cmd = on_command("镇守", block=True, priority=13)
battle_hero_cmd = on_command("迎战", block=True, priority=13)
calamity_shop_cmd = on_command("天灾商店", block=True, priority=13)
redeem_cmd = on_command("兑换", block=True, priority=13)
scout_cmd = on_command("侦查", block=True, priority=13)


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

            content = (
                "# 📋 大都会第七分部紧急会议记录\n"
                "***\n"
                "> 敲门诡在第十七区扩散，鬼域裂缝停不下来了。\n"
                "> 再不处理，七十二小时内整个分部都会被吞掉。\n"
                "> \n"
                "> 会长看了一眼数据，说：\n"
                "> 「导流。补偿打账户里。」\n"
                "> \n"
                "> 就这一句话。会议结束了。\n"
                "> \n"
                "> 你收到一条消息——\n"
                "> 「你已被选为第四天灾导流节点，请配合传送。」\n"
                "> \n"
                "> 你还没看完，那些诡异的气息就扑过来了。\n"
                "> 不是来打你的——它们要钻进你身体里。\n"
                "> 它们把你当成了一扇门。\n"
                "> \n"
                "> 然后你就掉下去了。\n"
                "> \n"
                "> 睁开眼，天是另一种颜色。\n"
                "> 有个小孩看见你，大叫一声\"天灾来了\"，\n"
                "> 撒腿就跑，摔了一跤，爬起来继续跑。\n"
                "> \n"
                "> 你低头看自己落脚的地方——\n"
                "> 地面正在龟裂，裂缝里渗出灰色的雾。\n"
                "> 你身后，鬼域已经张开了。\n"
                "> 叩门声从你的影子里传出来，一下一下，\n"
                "> 敲进这片土地。\n"
                "> \n"
                "> 这里的人还不知道，\n"
                "> 大都会把什么东西送过来了。\n"
                "\n"
                "⚠️ 你已降临下位世界，成为「第四天灾」\n"
                "大都会的诡异正通过你持续涌入这个世界\n"
                f"**{WAVE_INTERVAL_HOURS}**小时后，这里的英雄会来找你\n"
                "——大都会那边已经收到你的报酬了\n"
                f"***\n{cmd('镇守')} | {cmd('天灾商店')}"
            )
            await descend_cmd.finish(build_markdown(content))

        # 已建立山寨，显示当前状态
        await _show_stronghold_status(stronghold, player.level)


async def _show_stronghold_status(stronghold, player_level: int, cmd=descend_cmd):
    """显示山寨状态（共用逻辑）"""
    # 检查封印状态
    sealed, remaining = is_sealed(stronghold)
    if sealed:
        msg = (
            "━━━━━━━━━━━━━\n"
            "🏴‍☠️ 下位世界·山寨状态\n"
            f"📍 第 {stronghold.wave_number} 波\n"
            f"💎 天灾点：{stronghold.calamity_points}\n"
            f"🏆 已胜利波次：{stronghold.total_waves_won}\n"
            f"🏅 历史最高：第{stronghold.best_wave or stronghold.wave_number}波\n"
            "\n"
            f"⛓️ 封印中（剩余 {format_time_remaining(remaining)}）\n"
            "\n"
            "你被英雄击败了。\n"
            "他没有趁机补刀，只是说：\n"
            "「今天先到这里。」\n"
            "\n"
            "等封印解除后，会有新的英雄到来。"
        )
        await cmd.finish(msg)

    # 检查是否有待战斗的英雄
    if has_pending_hero(stronghold):
        hero = hero_from_json(stronghold.pending_hero)
        time_since_arrival = datetime.now() - stronghold.next_wave_at
        timeout = stronghold.next_wave_at + timedelta(hours=HERO_TIMEOUT_HOURS)
        remaining_until_timeout = timeout - datetime.now()

        affix_line = ""
        if hero.get("affixes"):
            affix_line = f"🔮 词缀：{'、'.join(hero['affixes'])}\n"

        msg = (
            "━━━━━━━━━━━━━\n"
            "🏴‍☠️ 下位世界·山寨状态\n"
            f"📍 第 {stronghold.wave_number} 波\n"
            f"💎 天灾点：{stronghold.calamity_points}\n"
            f"🏆 已胜利波次：{stronghold.total_waves_won}\n"
            f"🏅 历史最高：第{stronghold.best_wave or stronghold.wave_number}波\n"
            "\n"
            f"⚔️ 英雄已到达：{hero['name']}\n"
            f"🎖️ Lv.{hero['level']}\n"
            f"{affix_line}"
            f"📝 {hero['flavour']}\n"
            "\n"
            f"⏳ {format_time_remaining(remaining_until_timeout)}后撤退\n"
            "\n"
            "使用【迎战】与英雄战斗"
        )
        await cmd.finish(msg)

    # 检查英雄是否已超时撤退，或 next_wave_at 为空（封印结束后尚未安排下一波）
    if not stronghold.next_wave_at or datetime.now() > stronghold.next_wave_at + timedelta(hours=HERO_TIMEOUT_HOURS):
        # 英雄已撤退或尚未安排下一波，立即安排下一波
        def session_factory():
            return AsyncSessionLocal()

        async with UnitOfWork(session_factory) as uow:
            sh = await uow.lower_world_strongholds.get_by_player_id(stronghold.player_id)
            await schedule_next_wave(uow, sh, player_level)
            await uow.commit()

        msg = (
            "━━━━━━━━━━━━━\n"
            "🏴‍☠️ 下位世界·山寨状态\n"
            f"📍 第 {stronghold.wave_number} 波\n"
            f"💎 天灾点：{stronghold.calamity_points}\n"
            f"🏆 已胜利波次：{stronghold.total_waves_won}\n"
            f"🏅 历史最高：第{stronghold.best_wave or stronghold.wave_number}波\n"
            "\n"
            "🚶 英雄等待超时，已撤退\n"
            f"⏳ 下一波英雄将于 {WAVE_INTERVAL_HOURS} 小时后到达"
        )
        await cmd.finish(msg)

    # 正在等待下一波英雄
    time_until_next = stronghold.next_wave_at - datetime.now()
    wave = stronghold.wave_number

    # 按波次呈现不同深度的叙事文案
    if wave <= 5:
        _narratives = [
            "鬼域裂缝才刚刚张开。\n附近有村民绕远路走，不肯从这里经过。",
            "叩门声从你的影子里往外渗，\n地面龟裂处长出了不知名的灰色植物。",
            "有人在你山寨外的土地上画了驱邪符。\n那些符到第二天就自己烂掉了。",
            "你带来的鬼域正在这里生根。\n这里的人还不知道，这只是开始。",
        ]
    elif wave <= 10:
        _narratives = [
            "下位世界的人把这里叫做「灾地」。\n村子里已经有人说：墙壁会动。",
            "附近的牲畜开始不安。\n鸟不往这边飞了。方圆三里内安静得不对劲。",
            "有人来这里立碑，碑上刻着诅咒。\n第二天碑不见了——不是被人搬走的。",
            "诡异已经漫过了山寨的边界。\n你听见的叩门声，现在附近的人也听得见了。",
        ]
    elif wave <= 20:
        _narratives = [
            "这里的孩子已经不哭了。\n他们从小就知道，哭声会引来东西。",
            "有人组建了讨伐队来过，没有人回去。\n不是被你打死的——你不记得见过他们。",
            "鬼域的叩门声已经成了这里的背景音。\n有个老人说：还不如以前的风声好听。",
            "你在这里待得越久，\n这个世界接受你的速度就越快。\n这是好事还是坏事，你说不清。",
        ]
    else:
        _narratives = [
            "他们开始叫你「那个」。\n不是天灾，不是怪物——只是「那个」。\n有些词，说出来才会变成真的。",
            "有年轻的骑士专门来挑战你，\n说这是他们的成人礼。\n不是每一个都能活着回去。",
            "下位世界已经有了「天灾朝圣路」。\n地图上标着你的山寨，旁边注着：不要独行。",
            "鬼域和这里的土地已经分不清边界了。\n你站在山寨里，脚下是两个世界。",
        ]

    narrative = random.choice(_narratives)

    msg = (
        "━━━━━━━━━━━━━\n"
        "🏴‍☠️ 下位世界·山寨状态\n"
        f"📍 第 {wave} 波\n"
        f"💎 天灾点：{stronghold.calamity_points}\n"
        f"🏆 已胜利波次：{stronghold.total_waves_won}\n"
        "\n"
        f"{narrative}\n"
        "\n"
        f"⏳ 下一波英雄将于 {format_time_remaining(time_until_next)} 后到达"
    )
    await cmd.finish(msg)


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
        await _show_stronghold_status(stronghold, player.level, cmd=guard_cmd)


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
                if not stronghold.next_wave_at:
                    # 封印结束后 next_wave_at 为 None，立即安排下一波
                    await schedule_next_wave(uow, stronghold, player.level)
                    await uow.commit()
                    await battle_hero_cmd.finish(
                        f"⏳ 封印已解除，下一波英雄将于 {WAVE_INTERVAL_HOURS} 小时后到达\n"
                        "请耐心等待。"
                    )
                time_until_next = stronghold.next_wave_at - datetime.now()
                await battle_hero_cmd.finish(
                    f"⏳ 下一波英雄将于 {format_time_remaining(time_until_next)} 后到达\n"
                    "请耐心等待。"
                )

        # 获取英雄数据
        hero = hero_from_json(stronghold.pending_hero)

        # ── 战斗冷却检查（5分钟）──
        if stronghold.last_battle_at:
            elapsed = datetime.now() - stronghold.last_battle_at
            cooldown = timedelta(minutes=BATTLE_COOLDOWN_MINUTES)
            if elapsed < cooldown:
                remaining_cd = cooldown - elapsed
                remaining_cd_min = int(remaining_cd.total_seconds() // 60)
                remaining_cd_sec = int(remaining_cd.total_seconds() % 60)
                cd_str = f"{remaining_cd_min}分{remaining_cd_sec}秒" if remaining_cd_min > 0 else f"{remaining_cd_sec}秒"
                await battle_hero_cmd.finish(
                    f"鬼域的余波还未散去，你需要稍作恢复。\n"
                    f"（{BATTLE_COOLDOWN_MINUTES}分钟内只能迎战一次，还剩 {cd_str}）"
                )

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
        # 记录本次迎战时间（冷却用）
        stronghold.last_battle_at = datetime.now()
        uow.session.add(player)
        uow.session.add(stronghold)

        # 消耗战意加持buff（1场战斗即消耗）
        from ..models.temporary_buff import TemporaryBuff
        from sqlalchemy import select as _sel_cb
        _cb_stmt = _sel_cb(TemporaryBuff).where(
            TemporaryBuff.player_id == player.id,
            TemporaryBuff.buff_id == "lower_world_combat_boost",
            TemporaryBuff.is_active == True,
            TemporaryBuff.expires_at > datetime.now(),
        )
        _combat_buff = (await uow.session.execute(_cb_stmt)).scalars().first()
        if _combat_buff:
            _combat_buff.is_active = False
            _combat_buff.expires_at = datetime.now()
            uow.session.add(_combat_buff)

        # 处理战斗结果
        if victory:
            # 胜利
            points = await process_battle_victory(uow, stronghold, player.level)
            await uow.commit()

            # 代词判断（按女性名字列表）
            _female_names = {"席拉", "伊莲娜", "芙蕾雅", "奥尔加", "米雷亚", "艾莉丝", "薇薇安"}
            pronoun = "她" if any(fn in hero["name"] for fn in _female_names) else "他"

            # 普通英雄（1-10波）vs 勇者（11+波）使用不同文案池
            if stronghold.wave_number <= 10:
                victory_endings = [
                    (
                        f"……{hero['name']} 倒下了。\n"
                        "\n"
                        f"{pronoun}望着你，没有仇恨，只是问：\n"
                        "「你们那边……也会有人哭吗？」\n"
                        "\n"
                        "你没有回答。\n"
                        "你身后，诡异继续往外涌。"
                    ),
                    (
                        f"……{hero['name']} 跪倒在地。\n"
                        "\n"
                        "剑没有落下。\n"
                        f"{pronoun}只是沉默地看着远处的鬼域。\n"
                        "「我保护的那些人，现在还安全吗。」\n"
                        "\n"
                        "不是问你，只是问自己。"
                    ),
                    (
                        f"……战斗结束了。\n"
                        "\n"
                        f"{hero['name']} 靠在断壁上，抬头看天。\n"
                        "「你有名字吗，天灾？」\n"
                        "\n"
                        "你没有回答。\n"
                        "天空是另一种颜色。这里没有你认识的星座。"
                    ),
                    (
                        f"……{hero['name']} 的武器落地，发出沉重的声响。\n"
                        "\n"
                        f"{pronoun}抬头，只说了一句：\n"
                        "「下次……我会更强的。」\n"
                        "\n"
                        "你不知道下次是什么时候。\n"
                        "你们都不知道。"
                    ),
                    (
                        f"……{hero['name']} 倒下之前，低声说了一个名字。\n"
                        "\n"
                        "不是你的名字。\n"
                        f"然后{pronoun}闭上眼，等了很久，睁开。\n"
                        "「原来还活着。」\n"
                        f"{pronoun}自己也没想到。"
                    ),
                    (
                        f"你站在原地，看着 {hero['name']} 缓缓坐起来。\n"
                        "\n"
                        f"{pronoun}没有看你，只是把地上的武器拾起，轻轻放好。\n"
                        "最后说了一句：\n"
                        "「谢谢你手下留情。」\n"
                        "\n"
                        "——然后你意识到，你并没有。"
                    ),
                    (
                        f"战斗结束。{hero['name']} 没有立刻离开，\n"
                        f"只是坐在山寨门口，看了很久的鬼域。\n"
                        "\n"
                        f"最后{pronoun}站起来，没有回头，走了。"
                    ),
                    (
                        f"……{hero['name']} 在倒下前，把腰间的水囊递了过来。\n"
                        "\n"
                        "你没有接。\n"
                        f"{pronoun}就放在地上了。\n"
                        "\n"
                        "「那边的人……过得好吗。」\n"
                        "你不知道怎么回答。"
                    ),
                ]
            else:
                # 勇者文案池（11+波，史诗感更强，内疚更深）
                victory_endings = [
                    (
                        f"……{hero['name']} 倒下了。\n"
                        "\n"
                        f"{pronoun}抬起头：\n"
                        "「所以天灾……也会感到疲倦吗。」\n"
                        "\n"
                        "你没有回答。\n"
                        "你身后，诡异继续往外涌。"
                    ),
                    (
                        f"战斗的尘埃落定。\n"
                        f"{hero['name']} 没有倒，只是站在那里，像一棵被雷劈过的树。\n"
                        "\n"
                        "「召唤我的那些人说——击败天灾，世界就得救了。」\n"
                        f"{pronoun}停顿了一下。\n"
                        "「但我赢不了你。」"
                    ),
                    (
                        f"……{hero['name']} 跪下的一瞬间，手里还握着武器。\n"
                        "\n"
                        "没有松开，只是膝盖软了。\n"
                        "良久，轻声问：\n"
                        "「鬼域那边的世界……和这里一样吗？\n"
                        " 有村子吗？有人种田吗？」"
                    ),
                    (
                        f"传说击败勇者会带来诅咒。\n"
                        "\n"
                        "没有。\n"
                        f"你只是站在那里，{hero['name']} 倒在地上，\n"
                        "两个人都没有说话。\n"
                        "\n"
                        "风吹过，诡异继续往外渗。\n"
                        "什么都没有改变——什么都会改变。"
                    ),
                    (
                        f"{hero['name']} 抬头。\n"
                        f"圣光还在{pronoun}身上燃烧，缓缓熄灭。\n"
                        "\n"
                        "「这是命运吗。」\n"
                        "你不知道。\n"
                        "「……还是运气不好。」\n"
                        f"{pronoun}笑了一下，声音很轻。"
                    ),
                    (
                        f"武器落在地面的声音传出去很远。\n"
                        f"{hero['name']} 闭着眼，像是在等什么。\n"
                        "\n"
                        "然后发现什么都没来。\n"
                        f"{pronoun}睁开眼，撑着地面站起来，走了。\n"
                        "一步都没有回头。"
                    ),
                    (
                        f"「我知道我赢不了。」\n"
                        f"{hero['name']} 在战斗最开始就说了这句话。\n"
                        "\n"
                        "你以为是场面话。\n"
                        "「但我要试过才算。\n"
                        " 不是为了赢，是为了——」\n"
                        "\n"
                        "最后一个字没说出来。"
                    ),
                    (
                        f"鬼域的叩门声在 {hero['name']} 倒下的一刻暂停了一秒，\n"
                        "然后继续。\n"
                        "\n"
                        "好像什么都没发生。\n"
                        "好像这场战斗对整个世界毫无意义。\n"
                        "\n"
                        "也许真的没有。"
                    ),
                ]

            victory_ending = random.choice(victory_endings)
            lw_log_mode = get_player_log_mode(player)
            filtered_bl = filter_battle_log(list(battle_log), lw_log_mode)
            log_lines = filtered_bl + [
                "━━━━━━━━━━━━━",
                victory_ending,
                "",
                f"+{points}天灾点（当前：{stronghold.calamity_points}点）",
                "「大都会那边有人因此平安了。",
                " 他们不知道你的名字。」",
                "",
                f"⏳ 下一波英雄将于 {WAVE_INTERVAL_HOURS} 小时后到达",
            ]
            lw_mode_label = "详细模式" if lw_log_mode == "detailed" else "简洁模式"
            await battle_hero_cmd.finish(build_battle_markdown(
                title=f"🏰 {hero['name']} 倒下！",
                battle_log=log_lines,
                hint=f"+{points}天灾点 | {lw_mode_label}",
                btn1="迎战",
                btn2="日志模式",
                btn3="天灾商店",
            ))
        else:
            # 失败
            wave_dropped = await process_battle_defeat(uow, stronghold)
            await uow.commit()

            _female_names = {"席拉", "伊莲娜", "芙蕾雅", "奥尔加", "米雷亚", "艾莉丝", "薇薇安"}
            pronoun = "她" if any(fn in hero["name"] for fn in _female_names) else "他"

            if stronghold.wave_number <= 10:
                defeat_endings = [
                    (
                        f"{hero['name']} 没有趁机补刀，只是站在原地，\n"
                        "把武器插回剑鞘。\n"
                        "\n"
                        "「走吧，天灾。\n"
                        " 今天先到这里。」"
                    ),
                    (
                        f"地面是另一种触感。\n"
                        f"{hero['name']} 蹲下来看了你一眼，\n"
                        "没有鄙视，只是说：\n"
                        "「下次我还会来的。」\n"
                        "\n"
                        "然后转身走了。"
                    ),
                    (
                        f"{hero['name']} 没有说话。\n"
                        "只是从腰间取出一小瓶药水，放在你手边。\n"
                        "然后站起来，背对着你，\n"
                        "长久地望着鬼域的方向。\n"
                        "\n"
                        "最后离开了。"
                    ),
                    (
                        f"你听见 {hero['name']} 的脚步声渐渐远去。\n"
                        "\n"
                        "没有庆祝，没有欢呼。\n"
                        "只有风吹过鬼域裂缝，\n"
                        "发出低沉的叩门声。"
                    ),
                    (
                        f"{hero['name']} 扶了你一下，然后放开了手。\n"
                        "\n"
                        "什么都没说，走了。\n"
                        f"你不知道{pronoun}为什么要扶你，\n"
                        f"{pronoun}大概也不知道。"
                    ),
                    (
                        f"{hero['name']} 在你倒下的地方放了一块石头。\n"
                        "\n"
                        "不知道是记号还是悼念，\n"
                        "或者只是顺手捡的。\n"
                        "然后离开了。"
                    ),
                    (
                        f"临走前，{hero['name']} 回头看了你一眼，欲言又止。\n"
                        "\n"
                        "「你……不是坏人吧？」\n"
                        f"然后{pronoun}自己摇了摇头：「算了。」\n"
                        "\n"
                        "走了。"
                    ),
                    (
                        f"{hero['name']} 没有庆祝，\n"
                        "在山寨外站了一会——\n"
                        "大概是确认你还活着——\n"
                        "然后才离开。"
                    ),
                ]
            else:
                # 勇者失败文案（沉重、命运感）
                defeat_endings = [
                    (
                        f"{hero['name']} 收起武器，轻轻说：\n"
                        "「就这样吧。我们都没有选择。」\n"
                        "\n"
                        "然后离开了。"
                    ),
                    (
                        "传说勇者击败天灾后会得到鲜花和欢呼。\n"
                        "\n"
                        f"没有。{hero['name']} 走进风里，\n"
                        "没有人知道这里发生了什么。"
                    ),
                    (
                        f"{hero['name']} 赢了。\n"
                        f"但{pronoun}没有高兴。\n"
                        "只是站在鬼域边缘，看了很久。\n"
                        "\n"
                        "最后说了一声：\n"
                        "「下次……再战。」\n"
                        "声音里听不出任何情绪。"
                    ),
                    (
                        f"你倒下时，最后看到的是 {hero['name']} 的背影——\n"
                        f"{pronoun}已经朝着鬼域的方向走去，在研究什么。\n"
                        "\n"
                        "像是在寻找答案。\n"
                        f"{pronoun}大概不会找到。"
                    ),
                    (
                        f"胜负已分。{hero['name']} 把封印刻在你额头，\n"
                        "手很稳，字迹工整。\n"
                        "\n"
                        f"然后{pronoun}站起来，低声说了一句你听不懂的祈祷词。"
                    ),
                    (
                        f"「我本来以为，击败你，世界就会变好。」\n"
                        f"{hero['name']} 停顿了一下，转身走了。\n"
                        "\n"
                        "没有说后半句。\n"
                        "你也不需要听后半句。"
                    ),
                    (
                        f"{hero['name']} 在离开前，看了一眼你身后的鬼域。\n"
                        "\n"
                        "那道缝还在，叩门声还在。\n"
                        "什么都没有停下。\n"
                        f"{pronoun}叹了口气，背起武器，走了。"
                    ),
                    (
                        f"你听见远处有人在喊 {hero['name']} 的名字。\n"
                        "\n"
                        f"{pronoun}回头望了一眼，然后快步离开，\n"
                        "没有再看你。\n"
                        "\n"
                        f"有人在等{pronoun}回去。"
                    ),
                ]

            defeat_ending = random.choice(defeat_endings)
            lw_log_mode2 = get_player_log_mode(player)
            filtered_bl2 = filter_battle_log(list(battle_log), lw_log_mode2)
            log_lines = filtered_bl2 + [
                "━━━━━━━━━━━━━",
                "你倒下了。",
                "",
                defeat_ending,
                "",
                f"⛓️ 你被封印{SEAL_DURATION_HOURS}小时" + (f"，波次降低{wave_dropped}波（当前第{stronghold.wave_number}波）" if wave_dropped > 0 else ""),
            ]
            lw_mode_label2 = "详细模式" if lw_log_mode2 == "detailed" else "简洁模式"
            await battle_hero_cmd.finish(build_battle_markdown(
                title=f"🏰 被 {hero['name']} 击倒",
                battle_log=log_lines,
                hint=f"封印{SEAL_DURATION_HOURS}小时" + (f" · 降{wave_dropped}波" if wave_dropped > 0 else "") + f" | {lw_mode_label2}",
                btn1="迎战",
                btn2="日志模式",
                btn3="天灾商店",
            ))


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

        # ─── 实装各商品效果（先检查重复，通过后再扣天灾点）───
        from ..models.temporary_buff import TemporaryBuff
        from sqlalchemy import select as _sel

        if item["id"] == "cultivate_boost":
            # 先检查是否已有未过期的修炼加速buff
            existing_stmt = _sel(TemporaryBuff).where(
                TemporaryBuff.player_id == player.id,
                TemporaryBuff.buff_id == "lower_world_cultivate_boost",
                TemporaryBuff.is_active == True,
                TemporaryBuff.expires_at > datetime.now(),
            )
            existing = (await uow.session.execute(existing_stmt)).scalars().first()
            if existing:
                remaining_min = existing.get_remaining_minutes()
                await redeem_cmd.finish(
                    f"你已有「修炼加速」效果，剩余 {remaining_min} 分钟\n"
                    "无法叠加，天灾点未扣除。"
                )

            stronghold.calamity_points -= item["price"]
            uow.session.add(stronghold)
            buff = TemporaryBuff(
                player_id=player.id,
                buff_id="lower_world_cultivate_boost",
                buff_name="天灾修炼加速",
                attribute_bonuses={},
                duration_minutes=120,
                expires_at=datetime.now() + timedelta(minutes=120),
                source_item_id="lower_world_cultivate_boost",
                source_description="天灾商店：修炼加速（2小时）",
                extra_data={"cultivation_efficiency": 0.5},
            )
            uow.session.add(buff)
            await uow.commit()
            msg = (
                "✅ 兑换成功！\n"
                "「大都会的账款已到位。」\n"
                "\n"
                "🌀 修炼效率+50%（持续2小时）\n"
                "下次修炼时自动生效，不需要额外操作。"
            )

        elif item["id"] == "battle_boost":
            # 先检查是否已有未过期的战意加持buff
            existing_stmt = _sel(TemporaryBuff).where(
                TemporaryBuff.player_id == player.id,
                TemporaryBuff.buff_id == "lower_world_combat_boost",
                TemporaryBuff.is_active == True,
                TemporaryBuff.expires_at > datetime.now(),
            )
            existing = (await uow.session.execute(existing_stmt)).scalars().first()
            if existing:
                remaining_min = existing.get_remaining_minutes()
                await redeem_cmd.finish(
                    f"你已有「战意加持」效果，剩余 {remaining_min} 分钟\n"
                    "无法叠加，天灾点未扣除。"
                )

            # 计算10%属性加成（固定值）
            atk_bonus = max(1, int(player.attack * 0.10))
            def_bonus = max(1, int(player.defense * 0.10))
            agi_bonus = max(1, int(player.agility * 0.10))
            hp_bonus = max(1, int(player.max_hp * 0.10))
            stronghold.calamity_points -= item["price"]
            uow.session.add(stronghold)
            buff = TemporaryBuff(
                player_id=player.id,
                buff_id="lower_world_combat_boost",
                buff_name="天灾战意加持",
                attribute_bonuses={
                    "attack": atk_bonus,
                    "defense": def_bonus,
                    "agility": agi_bonus,
                    "max_hp": hp_bonus,
                },
                duration_minutes=10,
                expires_at=datetime.now() + timedelta(minutes=10),
                source_item_id="lower_world_combat_boost",
                source_description="天灾商店：战意加持（1场）",
                extra_data={"single_battle": True},
            )
            uow.session.add(buff)
            await uow.commit()
            msg = (
                "✅ 兑换成功！\n"
                "「战意已传输完毕。」\n"
                "\n"
                f"⚔️ 全属性+10%（10分钟内1场战斗）\n"
                f"力+{atk_bonus} 防+{def_bonus} 敏+{agi_bonus} 体+{hp_bonus}\n"
                "使用【迎战】后自动消耗。"
            )

        elif item["id"] == "unseal":
            # 检查是否处于封印状态
            sealed, remaining = is_sealed(stronghold)
            if not sealed:
                await redeem_cmd.finish(
                    "你当前没有被封印，无需使用解封令。\n"
                    "天灾点未扣除。"
                )

            stronghold.calamity_points -= item["price"]
            stronghold.sealed_until = None
            uow.session.add(stronghold)
            # 立即安排下一波
            await schedule_next_wave(uow, stronghold, player.level)
            await uow.commit()
            msg = (
                "✅ 兑换成功！\n"
                "「大都会紧急解除了封印协议。」\n"
                "\n"
                "⛓️ 封印已解除\n"
                f"⏳ 下一波英雄将于 {WAVE_INTERVAL_HOURS} 小时后到达"
            )

        elif item["id"] == "scout_intel":
            # 侦查情报：直接提示使用【侦查】命令
            await redeem_cmd.finish(
                "💡 请直接使用【侦查】命令查看下一波英雄情报\n"
                "（消耗10天灾点，无需提前购买）"
            )

        elif item["id"] == "title_calamity":
            # 先检查是否已拥有称号
            from ..event.knocker_event import KnockerEventService
            from sqlalchemy.orm.attributes import flag_modified

            title_name = "第四天灾"
            pdata = KnockerEventService._get_player_data(player)
            owned_titles = pdata.get("owned_titles", [])

            if title_name in owned_titles:
                await redeem_cmd.finish(
                    f"你已拥有称号「{title_name}」\n"
                    "天灾点未扣除。\n"
                    "💡 使用【切换称号 第四天灾】重新佩戴。"
                )

            stronghold.calamity_points -= item["price"]
            uow.session.add(stronghold)
            owned_titles.append(title_name)
            pdata["owned_titles"] = owned_titles
            pdata["title"] = title_name  # 自动设为当前称号
            KnockerEventService._set_player_data(player, pdata)
            uow.session.add(player)
            await uow.commit()
            msg = (
                "✅ 兑换成功！\n"
                "\n"
                "「你的存在已被记录。\n"
                " 大都会第七分部永久备案：\n"
                " 第四天灾·导流节点·永久认证。」\n"
                "\n"
                "🏷️ 称号「第四天灾」已佩戴\n"
                "💡 使用【切换称号】管理所有称号"
            )

        else:
            stronghold.calamity_points -= item["price"]
            uow.session.add(stronghold)
            await uow.commit()
            msg = (
                f"✅ 兑换成功！\n"
                f"获得：{item['name']}\n"
                f"剩余天灾点：{stronghold.calamity_points}\n"
                "\n"
                f"📝 {item['desc']}"
            )

        await redeem_cmd.finish(msg)


# 侦查消耗的天灾点
SCOUT_COST = 10


# ==================== 【侦查】 ====================
@scout_cmd.handle()
async def handle_scout(event: MessageEvent):
    """
    【侦查】- 消耗10天灾点查看下一波英雄的属性
    """
    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await scout_cmd.finish("请先【注册】后再使用该功能")

        stronghold = await uow.lower_world_strongholds.get_by_player_id(player.id)
        if not stronghold:
            await scout_cmd.finish("你还未建立山寨。使用【降临】开始下位世界之旅")

        # 检查封印状态
        sealed, remaining = is_sealed(stronghold)
        if sealed:
            await scout_cmd.finish(
                f"⛓️ 你被封印中，剩余 {format_time_remaining(remaining)}\n"
                "封印期间无法侦查。"
            )

        # 检查天灾点
        if stronghold.calamity_points < SCOUT_COST:
            await scout_cmd.finish(
                f"天灾点不足！侦查需要 {SCOUT_COST} 点\n"
                f"当前：{stronghold.calamity_points} 点"
            )

        # 如果已有待挑战英雄，直接展示当前英雄的详细属性
        if has_pending_hero(stronghold):
            hero = hero_from_json(stronghold.pending_hero)
            stronghold.calamity_points -= SCOUT_COST
            uow.session.add(stronghold)
            await uow.commit()

            affix_line = ""
            if hero.get("affixes"):
                affix_line = f"🔮 词缀：{'、'.join(hero['affixes'])}\n"

            special_lines = []
            if hero.get("crit_rate"):
                special_lines.append(f"💥 暴击率：{hero['crit_rate']}%")
            if hero.get("combo_rate"):
                special_lines.append(f"⚡ 连击率：{hero['combo_rate']}%")
            if hero.get("counter_rate"):
                special_lines.append(f"🛡️ 反击率：{hero['counter_rate']}%")
            if hero.get("lifesteal"):
                special_lines.append(f"🧡 吸血：{hero['lifesteal']}%")
            if hero.get("ignore_defense"):
                special_lines.append(f"☂️ 穿透：{hero['ignore_defense']}%")
            special_str = "\n".join(special_lines) + "\n" if special_lines else ""

            msg = (
                f"🔍 侦查报告 （-{SCOUT_COST}天灾点）\n"
                "━━━━━━━━━━━━━\n"
                f"⚔️ {hero['name']}\n"
                f"🎖️ Lv.{hero['level']}\n"
                f"{affix_line}"
                f"❤️ HP：{hero['hp']:,}\n"
                f"⚔️ 攻击：{hero['attack']:,}\n"
                f"🛡️ 防御：{hero['defense']:,}\n"
                f"👟 敏捷：{hero['agility']:,}\n"
                f"{special_str}"
                "━━━━━━━━━━━━━\n"
                f"📝 {hero['flavour']}\n"
                "\n"
                f"💎 剩余天灾点：{stronghold.calamity_points}"
            )
            await scout_cmd.finish(msg)

        # 没有待挑战英雄：预览下一波英雄（不消耗，只展示预测）
        from .hero_generator import generate_hero as _gen_hero
        preview_hero = _gen_hero(player.level, stronghold.wave_number)
        stronghold.calamity_points -= SCOUT_COST
        uow.session.add(stronghold)
        await uow.commit()

        msg = (
            f"🔍 侦查预测 （-{SCOUT_COST}天灾点）\n"
            "━━━━━━━━━━━━━\n"
            f"📍 第{stronghold.wave_number}波预计英雄强度：\n"
            f"🎖️ 预估等级：Lv.{preview_hero['level']}\n"
            f"❤️ HP范围：~{preview_hero['hp']:,}\n"
            f"⚔️ 攻击范围：~{preview_hero['attack']:,}\n"
            f"🛡️ 防御范围：~{preview_hero['defense']:,}\n"
            "━━━━━━━━━━━━━\n"
            "⚠️ 英雄未到达，属性仅供参考\n"
            "\n"
            f"💎 剩余天灾点：{stronghold.calamity_points}"
        )
        await scout_cmd.finish(msg)
