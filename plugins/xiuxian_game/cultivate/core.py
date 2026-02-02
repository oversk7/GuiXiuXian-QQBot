from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams
from nonebot.params import CommandArg
from ..utils import  message_add_head, calculate_level_up_exp, generate_progress_bar, calculate_cultivation_times_needed
from ..models.db import safe_session
from ..models.player import Player
from ..config import config
from datetime import datetime
import random
from sqlalchemy import select as _sel
from ..models.inventory import ItemInstance as _Equip, ItemType
from ..models.monthly_card import get_player_card_benefits

# Feature Flag: 控制是否使用新版MansionService (DI架构)
cfg = config.game_config["cultivate"]

# 修炼文案池 - 增加修炼时的沉浸感和新鲜感
CULTIVATE_FLAVOR_TEXTS = [
    "你在黑焰里看见自己的影子喘息。",
    "怨炁如潮水般涌入你的经脉，灼烧着每一寸血肉。",
    "虚无的低语在耳边回响，诉说着不可名状的真理。",
    "阴冷的力量沿着脊椎攀爬，你感受到灵魂的颤栗。",
    "黑暗中有什么东西在注视着你，但你已无法回头。",
    "血管中流淌的不再是血液，而是纯粹的恶意。",
    "你听见骨骼在重塑的声音，痛苦与力量交织缠绕。",
    "深渊的气息从毛孔中渗出，你正在蜕变成别的存在。",
    "意识在虚空中飘荡，你看见了死亡的另一面。",
    "每一次呼吸都在吞噬光明，每一次心跳都在召唤黑暗。",
    "灵魂深处传来古老的呼唤，那是来自彼岸的邀请。",
    "你的影子开始独立行动，在墙上描绘着诡异的符文。"
]

# 闭关文案池 - 增加闭关时的仪式感
SECLUSION_FLAVOR_TEXTS = [
    "{nickname} 躺入破棺，将最后一枚钉子钉入。",
    "{nickname} 缓缓合上棺盖，黑暗吞噬了最后一丝光明。",
    "{nickname} 在棺材中蜷缩身体，感受死亡的拥抱。",
    "{nickname} 闭上双眼，让意识沉入无尽的深渊。",
    "{nickname} 将自己封印在木棺中，开始漫长的蜕变。",
    "{nickname} 躺在冰冷的棺材里，聆听心跳逐渐微弱。",
    "{nickname} 用钉子封住棺盖，与外界彻底隔绝。",
    "{nickname} 在黑暗中闭关，灵魂开始游离于生死之间。"
]

# 出关文案池 - 增加出关时的重生感
OUT_SECLUSION_FLAVOR_TEXTS = [
    "你推开棺盖，阴灰散落。",
    "棺盖缓缓打开，你从死亡中苏醒。",
    "你破棺而出，带着深渊的气息。",
    "木棺开启，你重新睁开双眼。",
    "你从黑暗中归来，灵魂已然蜕变。",
    "棺材的束缚被打破，你获得了新生。",
    "你推开沉重的棺盖，重见天日。",
    "从死寂中醒来，你感受到力量的涌动。"
]


async def get_coffin_nail_count(session, player_id: str) -> int:
    """获取玩家背包中棺材钉的数量"""
    result = await session.execute(
        _sel(_Equip).where(
            _Equip.player_id == player_id,
            _Equip.item_id == "coffin_nail"
        )
    )
    coffin_nails = result.scalars().all()
    return sum(nail.quantity for nail in coffin_nails)
cultivate = on_command("修炼", block=True, priority=5)
seclusion = on_command("闭关", block=True, priority=5)
out_seclusion = on_command("出关", block=True, priority=5)
breakthrough = on_command("突破", block=True, priority=5)
continuous_breakthrough = on_command("连续突破", aliases={"连突"}, block=True, priority=5)
assign_points = on_command("加点",aliases={"分配"}, block=True, priority=5)
free_reset_points = on_command("免费洗点", aliases={"新手洗点"}, block=True, priority=5)



@cultivate.handle()
async def handle_cultivate(event: MessageEvent):
    """修炼主逻辑"""
    from ..platform_utils import get_unified_player, is_guild_message

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await cultivate.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await cultivate.finish("⛔ 请先使用【注册】命令创建角色")
        
        # 闭关状态检查
        if player.is_secluded:
            await cultivate.finish(message_add_head(
                "⚰️ 钉子阻隔冥修\n"
                "━━━━━━━━━━━━━\n"
                "闭棺期间无法普通修炼。\n"
                "━━━━━━━━━━━━━\n"
                "⬇️ 【出关】推开棺盖 或 等待结算",
                event))
        
        # 冷却时间检查
        if player.last_cultivation and (datetime.now() - player.last_cultivation).seconds < cfg["cool_down"]:
            remaining = cfg["cool_down"] - (datetime.now() - player.last_cultivation).seconds
            await cultivate.finish(message_add_head(
                f"🕒 血火仍在灼烧…剩余 {remaining//60}分{remaining%60}秒，之后再尝试修炼。",
                event
            ))
        
        k = 7 if player.level <= 10 else 6
        # 基础收益计算
        base_gain = cfg["base_exp"] * (1 + player.level / k)
        base_exp_gain = round(base_gain * random.uniform(0.8, 1.2))

        # 获取月卡权益
        from ..models.monthly_card import get_player_card_benefits
        benefits = await get_player_card_benefits(session, player.id)

        # 获取公会修为加成
        guild_cultivation_bonus = 0.0
        if player.guild_id:
            from ..guild.guild_building_service import GuildBuildingService
            guild_bonuses = await GuildBuildingService.get_guild_bonuses(session, player.guild_id)
            guild_cultivation_bonus = guild_bonuses.get("cultivation_bonus", 0.0)

        # 获取阴宅修为加成（支持使用其他玩家的阴宅）
        mansion_cultivation_bonus = 0.0
        mansion_usage_msg = ""

        # 检查当前位置是否有阴宅
        current_x, current_y = player.get_current_coordinates()

        from ..infrastructure.repositories.player_repository import PlayerRepository
        from .mansion_service_new import MansionService

        service = MansionService(
            player_repo=PlayerRepository(session),
        )
        mansion_owner = await service.find_mansion_owner_at_location(current_x, current_y)

        if mansion_owner:
            can_use, use_msg = await service.can_use_mansion(player, mansion_owner)

            if can_use:
                payment_success, payment_msg = await service.pay_mansion_usage_fee(player, mansion_owner)

                if payment_success:
                    mansion_cultivation_bonus = MansionService.get_efficiency_bonus(mansion_owner.mansion_level)
                    if payment_msg:  # 如果有支付信息
                        mansion_usage_msg = f"\n✧ 阴宅费用 💰 {payment_msg}"
                else:
                    # 支付失败，无法使用阴宅加成
                    mansion_cultivation_bonus = 0.0
        # 获取师徒惩罚
        from ..infrastructure.repositories.player_relationship_repository import PlayerRelationshipRepository
        from ..social.mentorship_system_service import MentorshipSystemService

        mentorship_service = MentorshipSystemService(
            player_repo=PlayerRepository(session),
            relationship_repo=PlayerRelationshipRepository(session),
            session=session
        )
        mentorship_penalty_rate = await mentorship_service.get_cultivation_penalty(player.id)
        mentorship_penalty = int(base_exp_gain * mentorship_penalty_rate)

        # 应用师徒惩罚到基础经验
        base_exp_gain_after_penalty = base_exp_gain - mentorship_penalty

        # 分别计算各种加成（都基于惩罚后的基础经验）
        from .reincarnation_service_new import ReincarnationService
        reincarnation_bonus_rate = ReincarnationService.get_cultivation_efficiency_bonus(player.reincarnation_level)

        # 月卡加成
        card_bonus = int(base_exp_gain_after_penalty * benefits["cultivation_efficiency"])
        # 转数加成
        reincarnation_bonus = int(base_exp_gain_after_penalty * reincarnation_bonus_rate)
        # 公会加成
        guild_bonus = int(base_exp_gain_after_penalty * guild_cultivation_bonus)
        # 阴宅加成
        mansion_bonus = int(base_exp_gain_after_penalty * mansion_cultivation_bonus)

        # 总经验 = 惩罚后的基础经验 + 各种加成
        exp_gain = base_exp_gain_after_penalty + card_bonus + reincarnation_bonus + guild_bonus + mansion_bonus

        # 更新数据
        player.last_cultivation = datetime.now()
        player.exp += exp_gain
        session.add(player)
        await session.commit()
        exp_max = calculate_level_up_exp(player.level)

        # 构建简洁版修炼消息（折叠式：主行简洁，加成详情折叠显示）

        # 随机选择修炼文案
        flavor_text = random.choice(CULTIVATE_FLAVOR_TEXTS)

        # 生成进度条
        progress_bar = generate_progress_bar(player.exp, exp_max)

        # 构建加成明细行（折叠式）
        total_bonus = card_bonus + reincarnation_bonus + guild_bonus + mansion_bonus
        bonus_detail_line = ""
        if total_bonus > 0 or mentorship_penalty > 0:
            bonus_percent = (total_bonus / base_exp_gain) * 100 if base_exp_gain > 0 else 0
            bonus_parts = []

            # 按顺序显示有效加成
            if card_bonus > 0:
                bonus_parts.append(f"月卡+{card_bonus}")
            if reincarnation_bonus > 0:
                bonus_parts.append(f"冥返+{reincarnation_bonus}")
            if guild_bonus > 0:
                bonus_parts.append(f"公会+{guild_bonus}")
            if mansion_bonus > 0:
                bonus_parts.append(f"阴宅+{mansion_bonus}")
            if mentorship_penalty > 0:
                apprentice_count = await mentorship_service.get_apprentice_count(player.id)
                bonus_parts.append(f"徒弟-{mentorship_penalty}({apprentice_count}人)")

            bonus_detail = " ".join(bonus_parts)
            bonus_detail_line = f"\n   ↳ 基础+{base_exp_gain} {bonus_detail} (总加成{total_bonus - mentorship_penalty:+d})"

        # 计算还需修炼次数
        cultivation_times = calculate_cultivation_times_needed(player.exp, exp_max, exp_gain)
        hours_needed = (cultivation_times * cfg["cool_down"]) / 3600

        # 智能提示文本
        if player.exp >= exp_max:
            hint_text = f"💡 突破 境界壁垒已松动"
        else:
            if cultivation_times <= 5:
                hint_text = f"💡 还需修炼约{cultivation_times}次可突破 (约{hours_needed:.1f}小时，基于当前加成)"
            else:
                hint_text = f"💡 还需修炼约{cultivation_times}次可突破"

        # 冷却提示（诡异化）
        cooldown_text = f"⏰ 深渊的低语将在{cfg['cool_down']//60}分钟后再次响起"

        msg = (
            f"{flavor_text}\n"
            "━━━━━━━━━━━━━\n"
            f"🔥 汲取怨炁(经验) +{exp_gain} | 怨炁进度 {progress_bar}"
            f"{bonus_detail_line}\n"
            f"{hint_text}\n"
            f"{cooldown_text}"
        )

        # 检查新手任务（在发送消息前）
        from ..quest.novice_quest_service import NoviceQuestService
        quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(
            session, player, "command", {"command": "修炼"}
        )

        if quest_completed and quest_msg:
            # 如果完成了新手任务，在修炼消息后追加任务完成消息
            msg += f"\n\n{quest_msg}"

        # 更新成就统计并检查成就
        from ..achievement.achievement_service import AchievementService
        await AchievementService.update_stat(session, player.id, "cultivation_count")
        achievement_msgs = await AchievementService.check_achievements(session, player)
        if achievement_msgs:
            msg += "\n\n" + "\n\n".join(achievement_msgs)

        # 使用图鉴模版发送修炼结果
        title = "✨ 修炼完成"
        desc = msg.replace("\n", "\r")

        # 获取玩家头像链接
        from ..platform_utils import get_platform_info
        _, user_id = get_platform_info(event)
        avatar_url = f"https://thirdqq.qlogo.cn/qqapp/102499345/{user_id}/0"

        # 快捷操作提示
        hint = "快捷操作: 修炼 | 闭关 | 突破 | 面板 | 背包 | 战力 | 签到 | 帮助"

        template_params = [
            MessageMarkdownParams(key="title", values=[title]),
            MessageMarkdownParams(key="desc", values=[desc]),
            MessageMarkdownParams(key="imgurl", values=[avatar_url]),
            MessageMarkdownParams(key="width", values=["100"]),
            MessageMarkdownParams(key="height", values=["100"]),
            MessageMarkdownParams(key="hint", values=[hint])
        ]

        markdown = MessageMarkdown(
            custom_template_id="102499345_1769178984",
            params=template_params
        )

        await cultivate.finish(MessageSegment.markdown(markdown))

@seclusion.handle()
async def handle_seclusion(event: MessageEvent):
    """闭关逻辑"""
    from ..platform_utils import get_unified_player, is_guild_message

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await seclusion.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await seclusion.finish("⛔ 请先使用【注册】命令创建角色")

        if player.is_secluded:
            await seclusion.finish(message_add_head(
                "⚰️ 棺材已封\n"
                "━━━━━━━━━━━━━\n"
                "你已在闭棺中。\n"
                "━━━━━━━━━━━━━\n"
                "⬇️ 【出关】推开棺盖",
                event))

        # 获取月卡权益
        from ..models.monthly_card import get_player_card_benefits
        benefits = await get_player_card_benefits(session, player.id)

        # 获取公会修为加成
        guild_cultivation_bonus = 0.0
        if player.guild_id:
            from ..guild.guild_building_service import GuildBuildingService
            guild_bonuses = await GuildBuildingService.get_guild_bonuses(session, player.guild_id)
            guild_cultivation_bonus = guild_bonuses.get("cultivation_bonus", 0.0)

        # 获取阴宅修为加成（闭关时只检查是否有阴宅，不支付费用）
        mansion_cultivation_bonus = 0.0

        # 检查当前位置是否有阴宅
        current_x, current_y = player.get_current_coordinates()

        from ..infrastructure.repositories.player_repository import PlayerRepository
        from .mansion_service_new import MansionService

        service = MansionService(
            player_repo=PlayerRepository(session),
        )
        mansion_owner = await service.find_mansion_owner_at_location(current_x, current_y)

        if mansion_owner:
            # 闭关时只检查是否有阴宅加成，不支付费用
            # 如果是自己的阴宅，可以享受加成
            if player.id == mansion_owner.id:
                mansion_cultivation_bonus = MansionService.get_efficiency_bonus(mansion_owner.mansion_level)
            # 如果是他人阴宅，需要检查阴宅主人是否允许使用，以及玩家是否愿意使用他人阴宅
            elif (mansion_owner.mansion_allow_others and
                  mansion_owner.mansion_level > 0 and
                  player.mansion_willing_to_pay):
                mansion_cultivation_bonus = MansionService.get_efficiency_bonus(mansion_owner.mansion_level)
        # 计算棺材钉数量和效率加成（最多100根，50%加成）
        coffin_nail_count = await get_coffin_nail_count(session, player.id)
        effective_coffin_nail_count = min(coffin_nail_count, 100)  # 最多100根有效
        efficiency_bonus = effective_coffin_nail_count * 0.5  # 每个棺材钉提升0.5%效率

        # 获取转数闭关效率加成
        from .reincarnation_service_new import ReincarnationService
        reincarnation_seclusion_bonus = ReincarnationService.get_seclusion_efficiency_bonus(player.reincarnation_level)

        # 获取师徒惩罚
        from ..infrastructure.repositories.player_relationship_repository import PlayerRelationshipRepository
        from ..social.mentorship_system_service import MentorshipSystemService

        mentorship_service = MentorshipSystemService(
            player_repo=PlayerRepository(session),
            relationship_repo=PlayerRelationshipRepository(session),
            session=session
        )
        mentorship_penalty_rate = await mentorship_service.get_cultivation_penalty(player.id)
        mentorship_penalty_percent = mentorship_penalty_rate * 100  # 转换为百分比

        player.is_secluded = True
        player.seclusion_start_time = datetime.now()
        session.add(player)
        await session.commit()

        # 构建简洁版闭关消息（折叠式）
        # 计算总效率
        total_efficiency = efficiency_bonus
        efficiency_parts = []

        if coffin_nail_count > 0:
            effective_count = min(coffin_nail_count, 100)
            if coffin_nail_count > 100:
                efficiency_parts.append(f"棺材钉×{coffin_nail_count}(有效{effective_count})")
            else:
                efficiency_parts.append(f"棺材钉×{coffin_nail_count}")

        if benefits["seclusion_efficiency"] > 0:
            card_efficiency = benefits["seclusion_efficiency"] * 100
            total_efficiency += card_efficiency
            efficiency_parts.append("月卡")

        if reincarnation_seclusion_bonus > 0:
            reincarnation_efficiency = reincarnation_seclusion_bonus * 100
            total_efficiency += reincarnation_efficiency
            efficiency_parts.append("冥返")

        if guild_cultivation_bonus > 0:
            guild_efficiency = guild_cultivation_bonus * 100
            total_efficiency += guild_efficiency
            efficiency_parts.append("公会")

        if mansion_cultivation_bonus > 0:
            mansion_efficiency = mansion_cultivation_bonus * 100
            total_efficiency += mansion_efficiency
            efficiency_parts.append("阴宅")

        if mentorship_penalty_percent > 0:
            apprentice_count = await mentorship_service.get_apprentice_count(player.id)
            total_efficiency -= mentorship_penalty_percent
            efficiency_parts.append(f"徒弟-{mentorship_penalty_percent:.0f}%({apprentice_count}人)")

        seclusion_hours = benefits["seclusion_time_limit"] // 3600

        # 随机选择闭关文案
        seclusion_flavor_text = random.choice(SECLUSION_FLAVOR_TEXTS).format(nickname=player.nickname)

        # 构建加成说明行
        efficiency_detail = ""
        if efficiency_parts:
            efficiency_detail = f"\n   ↳ 效率加成来源: {' + '.join(efficiency_parts)}"

        msg_secl = (
            f"⚰️ {seclusion_flavor_text}\n"
            "━━━━━━━━━━━━━\n"
            f"🔥 离线修炼已开始 | 总效率加成 {total_efficiency:+.1f}%"
            f"{efficiency_detail}\n"
            f"⏰ 时长上限 {seclusion_hours}小时 | 期间无法普通修炼\n"
            "━━━━━━━━━━━━━\n"
            "💡 出关 推开棺盖并结算怨炁"
        )

        # 使用图鉴模版发送闭关开始消息
        title = "⚰️ 闭关开始"
        desc = msg_secl.replace("\n", "\r")

        # 获取玩家头像链接
        from ..platform_utils import get_platform_info
        _, user_id = get_platform_info(event)
        avatar_url = f"https://thirdqq.qlogo.cn/qqapp/102499345/{user_id}/0"

        # 快捷操作提示
        hint = "快捷操作: 出关 | 面板 | 背包 | 战力 | 阴宅 | 签到 | 市集 | 帮助"

        template_params = [
            MessageMarkdownParams(key="title", values=[title]),
            MessageMarkdownParams(key="desc", values=[desc]),
            MessageMarkdownParams(key="imgurl", values=[avatar_url]),
            MessageMarkdownParams(key="width", values=["100"]),
            MessageMarkdownParams(key="height", values=["100"]),
            MessageMarkdownParams(key="hint", values=[hint])
        ]

        markdown = MessageMarkdown(
            custom_template_id="102499345_1769178984",
            params=template_params
        )

        await seclusion.finish(MessageSegment.markdown(markdown))

@out_seclusion.handle()
async def handle_out_seclusion(event: MessageEvent):
    """出关逻辑"""
    from ..platform_utils import get_unified_player, is_guild_message

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await out_seclusion.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await out_seclusion.finish("⛔ 请先使用【注册】命令创建角色")

        if not player.is_secluded:
            await out_seclusion.finish(message_add_head(
                "🕳️ 棺盖早已打开\n"
                "━━━━━━━━━━━━━\n"
                "你当前并未闭棺。\n"
                "━━━━━━━━━━━━━\n"
                "⬇️ 【闭关】钉上棺盖",
                event))

        # 获取月卡权益
        from ..models.monthly_card import get_player_card_benefits
        benefits = await get_player_card_benefits(session, player.id)

        # 获取公会修为加成
        guild_cultivation_bonus = 0.0
        if player.guild_id:
            from ..guild.guild_building_service import GuildBuildingService
            guild_bonuses = await GuildBuildingService.get_guild_bonuses(session, player.guild_id)
            guild_cultivation_bonus = guild_bonuses.get("cultivation_bonus", 0.0)

        # 获取阴宅修为加成（出关时支付使用费用并获得加成）
        mansion_cultivation_bonus = 0.0
        mansion_usage_msg = ""

        # 检查当前位置是否有阴宅
        current_x, current_y = player.get_current_coordinates()

        from ..infrastructure.repositories.player_repository import PlayerRepository
        from .mansion_service_new import MansionService

        service = MansionService(
            player_repo=PlayerRepository(session),
        )
        mansion_owner = await service.find_mansion_owner_at_location(current_x, current_y)

        if mansion_owner:
            can_use, _ = await service.can_use_mansion(player, mansion_owner)

            if can_use:
                payment_success, payment_msg = await service.pay_mansion_usage_fee(player, mansion_owner)

                if payment_success:
                    mansion_cultivation_bonus = MansionService.get_efficiency_bonus(mansion_owner.mansion_level)
                    if payment_msg:  # 如果有支付信息
                        mansion_usage_msg = f"\n✧ 阴宅费用 💰 {payment_msg}"
                else:
                    # 支付失败，无法使用阴宅加成
                    mansion_cultivation_bonus = 0.0
        # 计算棺材钉数量和效率加成（最多100根，50%加成）
        coffin_nail_count = await get_coffin_nail_count(session, player.id)
        effective_coffin_nail_count = min(coffin_nail_count, 100)  # 最多100根有效

        player.is_secluded = False
        k = 7 if player.level <= 10 else 6
        base_gain = cfg["base_exp"] * (1 + player.level / k)
        delta_time = int((datetime.now() - player.seclusion_start_time).total_seconds())

        # 应用月卡时长限制
        max_seclusion_time = benefits["seclusion_time_limit"]
        delta_time = min(delta_time, max_seclusion_time)

        # 计算基础经验
        base_exp_gain = int(delta_time / cfg["cool_down"] * base_gain * 0.5)

        # 获取师徒惩罚
        from ..infrastructure.repositories.player_relationship_repository import PlayerRelationshipRepository
        from ..social.mentorship_system_service import MentorshipSystemService

        mentorship_service = MentorshipSystemService(
            player_repo=PlayerRepository(session),
            relationship_repo=PlayerRelationshipRepository(session),
            session=session
        )
        mentorship_penalty_rate = await mentorship_service.get_cultivation_penalty(player.id)
        mentorship_penalty = int(base_exp_gain * mentorship_penalty_rate)

        # 应用师徒惩罚到基础经验
        base_exp_gain_after_penalty = base_exp_gain - mentorship_penalty

        # 分别计算各种加成（都基于惩罚后的基础经验）
        # 棺材钉加成
        coffin_nail_efficiency = (effective_coffin_nail_count * 0.005)  # 每个棺材钉提升0.5%效率
        coffin_nail_bonus = int(base_exp_gain_after_penalty * coffin_nail_efficiency)

        # 月卡闭关效率加成
        card_bonus = int(base_exp_gain_after_penalty * benefits["seclusion_efficiency"])

        # 转数闭关效率加成
        from .reincarnation_service_new import ReincarnationService
        reincarnation_bonus_rate = ReincarnationService.get_seclusion_efficiency_bonus(player.reincarnation_level)
        reincarnation_exp_bonus = int(base_exp_gain_after_penalty * reincarnation_bonus_rate)

        # 公会修为加成
        guild_bonus = int(base_exp_gain_after_penalty * guild_cultivation_bonus)

        # 阴宅修为加成
        mansion_bonus = int(base_exp_gain_after_penalty * mansion_cultivation_bonus)

        # 总经验 = 惩罚后的基础经验 + 各种加成
        exp_gain = base_exp_gain_after_penalty + coffin_nail_bonus + card_bonus + reincarnation_exp_bonus + guild_bonus + mansion_bonus

        player.exp += exp_gain

        session.add(player)
        await session.commit()
        exp_max2 = calculate_level_up_exp(player.level)

        # 构建简洁版出关消息（折叠式）
        # 随机选择出关文案
        out_seclusion_flavor_text = random.choice(OUT_SECLUSION_FLAVOR_TEXTS)

        # 生成进度条
        progress_bar = generate_progress_bar(player.exp, exp_max2)

        # 构建加成明细（折叠式）
        bonus_parts = []
        if coffin_nail_bonus > 0:
            bonus_parts.append(f"棺材钉+{coffin_nail_bonus}")
        if card_bonus > 0:
            bonus_parts.append(f"月卡+{card_bonus}")
        if reincarnation_exp_bonus > 0:
            bonus_parts.append(f"冥返+{reincarnation_exp_bonus}")
        if guild_bonus > 0:
            bonus_parts.append(f"公会+{guild_bonus}")
        if mansion_bonus > 0:
            bonus_parts.append(f"阴宅+{mansion_bonus}")
        if mentorship_penalty > 0:
            apprentice_count = await mentorship_service.get_apprentice_count(player.id)
            bonus_parts.append(f"徒弟-{mentorship_penalty}({apprentice_count}人)")

        bonus_detail_line = ""
        if bonus_parts:
            total_bonus = coffin_nail_bonus + card_bonus + reincarnation_exp_bonus + guild_bonus + mansion_bonus
            total_effect = total_bonus - mentorship_penalty
            bonus_detail = " ".join(bonus_parts)
            bonus_detail_line = f"\n   ↳ 基础+{base_exp_gain} {bonus_detail} (总加成{total_effect:+d})"

        # 添加阴宅费用提示
        if mansion_usage_msg:
            bonus_detail_line += mansion_usage_msg.replace("\n✧ ", "\n   ↳ ")

        # 计算闭关时长
        seclusion_duration = delta_time // 60  # 转换为分钟
        hours = seclusion_duration // 60
        minutes = seclusion_duration % 60
        if hours > 0:
            duration_str = f"{hours}小时{minutes}分" if minutes > 0 else f"{hours}小时"
        else:
            duration_str = f"{minutes}分钟"

        # 智能提示
        if player.exp >= exp_max2:
            hint_text = "💡 突破 境界壁垒已松动"
        else:
            hint_text = "💡 修炼 继续积累怨炁"

        msg_out = (
            f"🔓 {out_seclusion_flavor_text}\n"
            "━━━━━━━━━━━━━\n"
            f"🔥 累积怨炁 +{exp_gain} | 怨炁进度 {progress_bar}"
            f"{bonus_detail_line}\n"
            f"⏰ 闭关时长 {duration_str}\n"
            f"{hint_text}"
        )

        # 使用图鉴模版发送出关结果
        title = "🔓 出关完成"
        desc = msg_out.replace("\n", "\r")

        # 获取玩家头像链接
        from ..platform_utils import get_platform_info
        _, user_id = get_platform_info(event)
        avatar_url = f"https://thirdqq.qlogo.cn/qqapp/102499345/{user_id}/0"

        # 快捷操作提示
        hint = "快捷操作: 修炼 | 突破 | 面板 | 背包 | 战力 | 闭关 | 签到 | 帮助"

        template_params = [
            MessageMarkdownParams(key="title", values=[title]),
            MessageMarkdownParams(key="desc", values=[desc]),
            MessageMarkdownParams(key="imgurl", values=[avatar_url]),
            MessageMarkdownParams(key="width", values=["100"]),
            MessageMarkdownParams(key="height", values=["100"]),
            MessageMarkdownParams(key="hint", values=[hint])
        ]

        markdown = MessageMarkdown(
            custom_template_id="102499345_1769178984",
            params=template_params
        )

        await out_seclusion.finish(MessageSegment.markdown(markdown))

@breakthrough.handle()
async def handle_breakthrough(event: MessageEvent, args: Message = CommandArg()):
    """突破境界逻辑"""
    from ..platform_utils import get_unified_player, is_guild_message

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await breakthrough.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await breakthrough.finish("⛔ 请先使用【注册】命令创建角色")

        cfg_break = cfg["breakthrough"]
        required_exp = calculate_level_up_exp(player.level)
        
        # 解析参数，若包含"镇厄"则启用保驾护航模式，若包含"棺材钉"则使用棺材钉
        arg_text = args.extract_plain_text().strip().lower() if isinstance(args, Message) else ""
        use_guardian = arg_text in {"护", "镇厄", "镇"}
        use_coffin_nail = "棺材钉" in arg_text

        base_cost = cfg_break.get("guardian_cost_base", cfg_break.get("guardian_cost", 50))
        per_level_inc = cfg_break.get("guardian_cost_per_level", 1)
        guardian_cost = base_cost + player.level * per_level_inc
        
        # 计算成功率
        if player.level < cfg_break["change_level"]:
            success_chance = 1.0
        else:
            base_rate = cfg_break.get("base_success_rate", 0.8)
            decay = cfg_break.get("decay_per_level", 0.005)
            min_rate = cfg_break.get("min_success_rate", 0.05)
            success_chance = max(min_rate, base_rate - decay * (player.level - cfg_break["change_level"]))

            # 失败累加机制
            if cfg_break.get("fail_bonus_enabled", True):
                fail_bonus_rate = cfg_break.get("fail_bonus_rate", 0.01)
                fail_bonus = player.breakthrough_fail_count * fail_bonus_rate
                success_chance += fail_bonus

                # 应用成功率上限
                max_rate = cfg_break.get("fail_bonus_max_rate", 0.95)
                success_chance = min(success_chance, max_rate)

        # 护航或使用棺材钉则必定成功
        if use_guardian or use_coffin_nail:
            success_chance = 1.0

        # 检查是否达到冥返要求等级，如果达到则提示冥返
        from .reincarnation_service_new import ReincarnationService
        required_level = ReincarnationService.get_required_level_for_reincarnation(player.reincarnation_level)
        if player.level >= required_level:
            reincarnation_count = player.reincarnation_level + 1
            await breakthrough.finish(
                f"🌟 你已达到冥返要求 Lv.{required_level}！\n"
                "━━━━━━━━━━━━━\n"
                f"✧ 可进行第{reincarnation_count}次冥返轮回\n"
                "✧ 冥返将重塑根基，获得更强潜力\n"
                "━━━━━━━━━━━━━\n"
                "⬇️ 【冥返】踏入轮回，重铸道基\n"
                "⬇️ 【冥返信息】查看详细信息"
            )

        # 检查经验是否足够
        if player.exp < required_exp:
            await breakthrough.finish(
                f"💢 修为不足！\n"
                f"▫️ 需要修为：{player.exp}/{required_exp}"
            )

        # 如果启用护航，检查怨念值是否足够
        if use_guardian and player.resentment < guardian_cost:
            await breakthrough.finish(f"⛔ 怨念值不足，镇厄需要 {guardian_cost}，当前 {player.resentment}")

        # 如果使用棺材钉，检查是否有足够的棺材钉
        coffin_nail_item = None
        if use_coffin_nail:
            from sqlalchemy import select as _sel
            from ..models.inventory import ItemInstance
            result = await session.execute(
                _sel(ItemInstance).where(
                    ItemInstance.player_id == player.id,
                    ItemInstance.item_id == "coffin_nail",
                    ItemInstance.quantity > 0
                )
            )
            coffin_nail_item = result.scalars().first()
            if not coffin_nail_item:
                await breakthrough.finish("⛔ 你没有棺材钉，无法使用棺材钉镇厄")

        # 消耗怨念值（如果启用护航）或棺材钉
        if use_guardian:
            player.resentment -= guardian_cost
        elif use_coffin_nail:
            # 消耗一根棺材钉
            coffin_nail_item.quantity -= 1
            if coffin_nail_item.quantity <= 0:
                await session.delete(coffin_nail_item)
            else:
                session.add(coffin_nail_item)

        if player.level < cfg_break["change_level"]:
            old_level = player.level
            player.exp -= required_exp
            player.level += 1

            # 根据转数计算属性点获得
            from .reincarnation_service_new import ReincarnationService
            points_gained = ReincarnationService.get_attribute_points_per_level(player.reincarnation_level)
            player.attribute_points += points_gained

            # 触发升级钩子
            from ..social.level_hooks import on_player_level_up
            reward_messages = await on_player_level_up(session, player.id, old_level, player.level)

            cost_msg = ""
            if use_guardian:
                cost_msg = f"✧ 消耗怨念值 {guardian_cost} (剩余{player.resentment})\n"
            elif use_coffin_nail:
                cost_msg = f"✧ 消耗棺材钉 1根⚰️，躁动的灵异被强制稳定，万千冤魂俯首称臣！\n"

            # 构建升级消息
            reward_msg = ""
            if reward_messages:
                reward_msg = "\n" + "\n".join(reward_messages) + "\n"

            msg = (
                f"⛓️‍💥骨裂声回荡，已突破至Lv.{player.level}↑\n"
                "━━━━━━━━━━━━━\n"
                f"✧ 获得属性点 + {points_gained}" + (f" (冥返加成)" if player.reincarnation_level > 0 else "") + "\n"
                f"✧ 剩余修为 {player.exp}\n"
                + cost_msg +
                reward_msg +
                "━━━━━━━━━━━━━\n"
                "⬇️ 【加点】缝合裂隙\n"
                "⬇️ 【修炼】继续喂养怨炁"
            )

            # 检查新手任务（等级提升）
            from ..quest.novice_quest_service import NoviceQuestService
            quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(
                session, player, "level_up", {}
            )

            if quest_completed and quest_msg:
                msg += f"\n\n{quest_msg}"

            # 检查成就（等级提升）
            from ..achievement.achievement_service import AchievementService
            achievement_msgs = await AchievementService.check_achievements(session, player)
            if achievement_msgs:
                msg += "\n\n" + "\n\n".join(achievement_msgs)
        else:
            if random.random() <= success_chance:
                old_level = player.level
                player.exp -= required_exp
                player.level += 1

                # 突破成功，重置失败次数
                player.breakthrough_fail_count = 0

                # 根据转数计算属性点获得
                from .reincarnation_service_new import ReincarnationService
                points_gained = ReincarnationService.get_attribute_points_per_level(player.reincarnation_level)
                player.attribute_points += points_gained

                # 触发升级钩子
                from ..social.level_hooks import on_player_level_up
                reward_messages = await on_player_level_up(session, player.id, old_level, player.level)

                cost_msg = ""
                if use_guardian:
                    cost_msg = f"✧ 消耗怨念值 {guardian_cost} (剩余{player.resentment})\n"
                elif use_coffin_nail:
                    cost_msg = f"✧ 消耗棺材钉 1根⚰️，躁动的灵异被强制稳定，万千冤魂俯首称臣！\n"

                # 构建升级消息
                reward_msg = ""
                if reward_messages:
                    reward_msg = "\n" + "\n".join(reward_messages) + "\n"

                msg = (
                    f"⛓️‍💥骨裂声回荡，已突破至Lv.{player.level}↑\n"
                    "━━━━━━━━━━━━━\n"
                    f"✧ 获得属性点 + {points_gained}" + (f" (冥返加成)" if player.reincarnation_level > 0 else "") + "\n"
                    f"✧ 剩余修为 {player.exp}\n"
                    + cost_msg +
                    reward_msg +
                    "━━━━━━━━━━━━━\n"
                    "⬇️ 【加点】缝合裂隙\n"
                    "⬇️ 【修炼】继续喂养怨炁"
                )

                # 检查新手任务（等级提升）
                from ..quest.novice_quest_service import NoviceQuestService
                quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(
                    session, player, "level_up", {}
                )

                if quest_completed and quest_msg:
                    msg += f"\n\n{quest_msg}"

                # 检查成就（等级提升）
                from ..achievement.achievement_service import AchievementService
                achievement_msgs = await AchievementService.check_achievements(session, player)
                if achievement_msgs:
                    msg += "\n\n" + "\n\n".join(achievement_msgs)
            else:
                # 突破失败
                # 增加失败次数
                player.breakthrough_fail_count += 1

                # 检查月卡权益
                card_benefits = await get_player_card_benefits(session, player.id)
                breakthrough_protection = card_benefits.get("breakthrough_protection", 0)

                # 确定修为保留比例
                if breakthrough_protection > 0:
                    # 有月卡保护，使用月卡的保留比例
                    keep_ratio = breakthrough_protection
                    protection_msg = "💳 月卡保护生效！"
                else:
                    # 没有月卡保护，使用默认比例
                    keep_ratio = cfg_break["fail_keep_ratio"]
                    protection_msg = ""

                player.exp = round(player.exp - required_exp*(1-keep_ratio))

                # 计算下次成功率加成
                next_bonus = 0
                if cfg_break.get("fail_bonus_enabled", True):
                    fail_bonus_rate = cfg_break.get("fail_bonus_rate", 0.01)
                    next_bonus = player.breakthrough_fail_count * fail_bonus_rate

                msg_lines = ["💥 镇厄崩散，修为反噬席卷脏腑。", "━━━━━━━━━━━━━"]
                if protection_msg:
                    msg_lines.append(protection_msg)
                msg_lines.extend([
                    f"✧ 剩余修为 {player.exp}",
                    f"✧ 修为保留 {int(keep_ratio*100)}%",
                    f"✧ 本次理论成功率 {int(success_chance*100)}%",
                    f"✧ 连续失败 {player.breakthrough_fail_count} 次",
                    f"✧ 下次成功率加成 +{int(next_bonus*100)}%",
                    "━━━━━━━━━━━━━",
                    "⬇️ 建议【突破 镇厄】以怨念护体",
                    "⬇️ 或者【突破 棺材钉】消耗棺材钉"
                ])
                msg = "\n".join(msg_lines)

        session.add(player)
        await session.commit()
        await breakthrough.finish(message_add_head(msg, event))

@continuous_breakthrough.handle()
async def handle_continuous_breakthrough(event: MessageEvent, args: Message = CommandArg()):
    """连续突破逻辑"""
    from ..platform_utils import get_unified_player, is_guild_message

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await continuous_breakthrough.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await continuous_breakthrough.finish("⛔ 请先使用【注册】命令创建角色")

        cfg_break = cfg["breakthrough"]

        # 解析参数，若包含"镇厄"则启用保驾护航模式
        arg_text = args.extract_plain_text().strip().lower() if isinstance(args, Message) else ""
        use_guardian = arg_text in {"护", "镇厄", "镇", "怨念"}

        # 检查是否达到冥返要求等级
        from .reincarnation_service_new import ReincarnationService
        required_level = ReincarnationService.get_required_level_for_reincarnation(player.reincarnation_level)
        if player.level >= required_level:
            reincarnation_count = player.reincarnation_level + 1
            await continuous_breakthrough.finish(
                f"🌟 你已达到冥返要求 Lv.{required_level}！\n"
                "━━━━━━━━━━━━━\n"
                f"✧ 可进行第{reincarnation_count}次冥返轮回\n"
                "✧ 冥返将重塑根基，获得更强潜力\n"
                "━━━━━━━━━━━━━\n"
                "⬇️ 【冥返】踏入轮回，重铸道基\n"
                "⬇️ 【冥返信息】查看详细信息"
            )

        # 统计信息
        breakthrough_count = 0
        failed_attempts = 0
        total_resentment_cost = 0
        total_attribute_points = 0
        start_level = player.level
        start_exp = player.exp
        start_resentment = player.resentment
        reached_level_cap = False

        # 连续突破循环
        while True:
            # 达到当前转数对应的等级上限后停止突破
            if player.level >= required_level:
                reached_level_cap = True
                break

            required_exp = calculate_level_up_exp(player.level)

            # 检查经验是否足够
            if player.exp < required_exp:
                break

            # 计算镇厄消耗
            base_cost = cfg_break.get("guardian_cost_base", cfg_break.get("guardian_cost", 50))
            per_level_inc = cfg_break.get("guardian_cost_per_level", 15)
            guardian_cost = base_cost + player.level * per_level_inc

            # 如果启用镇厄，检查怨念值是否足够
            if use_guardian and player.resentment < guardian_cost:
                break

            # 计算成功率
            if player.level < cfg_break["change_level"]:
                success_chance = 1.0
            else:
                base_rate = cfg_break.get("base_success_rate", 0.8)
                decay = cfg_break.get("decay_per_level", 0.005)
                min_rate = cfg_break.get("min_success_rate", 0.05)
                success_chance = max(min_rate, base_rate - decay * (player.level - cfg_break["change_level"]))

                # 失败累加机制
                if cfg_break.get("fail_bonus_enabled", True):
                    fail_bonus_rate = cfg_break.get("fail_bonus_rate", 0.01)
                    fail_bonus = player.breakthrough_fail_count * fail_bonus_rate
                    success_chance += fail_bonus

                    # 应用成功率上限
                    max_rate = cfg_break.get("fail_bonus_max_rate", 0.95)
                    success_chance = min(success_chance, max_rate)

            # 镇厄则必定成功
            if use_guardian:
                success_chance = 1.0

            # 执行突破
            if player.level < cfg_break["change_level"] or random.random() <= success_chance:
                # 突破成功
                old_level = player.level
                player.exp -= required_exp
                player.level += 1
                breakthrough_count += 1

                # 突破成功，重置失败次数
                player.breakthrough_fail_count = 0

                # 消耗怨念值（如果启用镇厄）
                if use_guardian:
                    player.resentment -= guardian_cost
                    total_resentment_cost += guardian_cost

                # 根据转数计算属性点获得
                points_gained = ReincarnationService.get_attribute_points_per_level(player.reincarnation_level)
                player.attribute_points += points_gained
                total_attribute_points += points_gained

                # 触发升级钩子
                from ..social.level_hooks import on_player_level_up
                await on_player_level_up(session, player.id, old_level, player.level)

            else:
                # 突破失败，但不停止连续突破，继续尝试
                player.breakthrough_fail_count += 1

                # 检查月卡权益
                card_benefits = await get_player_card_benefits(session, player.id)
                breakthrough_protection = card_benefits.get("breakthrough_protection", 0)

                # 确定修为保留比例
                if breakthrough_protection > 0:
                    keep_ratio = breakthrough_protection
                else:
                    keep_ratio = cfg_break["fail_keep_ratio"]

                player.exp = round(player.exp - required_exp*(1-keep_ratio))

                # 记录失败信息，但继续循环
                failed_attempts += 1

        session.add(player)
        await session.commit()

        # 构建结果消息
        if breakthrough_count == 0:
            if failed_attempts > 0:
                # 计算下次成功率加成
                next_bonus = 0
                if cfg_break.get("fail_bonus_enabled", True):
                    fail_bonus_rate = cfg_break.get("fail_bonus_rate", 0.01)
                    next_bonus = player.breakthrough_fail_count * fail_bonus_rate
                    max_rate = cfg_break.get("fail_bonus_max_rate", 0.95)
                    next_bonus = min(next_bonus, max_rate)

                msg = (
                    "💥 连续突破失败，修为不足以继续！\n"
                    "━━━━━━━━━━━━━\n"
                    f"✧ 本轮失败 {failed_attempts} 次\n"
                    f"✧ 当前等级 Lv.{player.level}\n"
                    f"✧ 剩余修为 {player.exp}/{calculate_level_up_exp(player.level)}\n"
                    f"✧ 连续失败 {player.breakthrough_fail_count} 次\n"
                    f"✧ 下次成功率加成 +{int(next_bonus*100)}%\n"
                    "━━━━━━━━━━━━━\n"
                    "⬇️ 建议【突破 镇厄】以怨念护体"
                )
            elif player.exp < calculate_level_up_exp(player.level):
                msg = (
                    "💢 修为不足，无法进行突破！\n"
                    "━━━━━━━━━━━━━\n"
                    f"✧ 当前修为 {player.exp}/{calculate_level_up_exp(player.level)}\n"
                    "━━━━━━━━━━━━━\n"
                    "⬇️ 【修炼】继续喂养怨炁"
                )
            elif use_guardian and start_resentment < (cfg_break.get("guardian_cost_base", 50) + player.level * cfg_break.get("guardian_cost_per_level", 15)):
                msg = (
                    "💢 怨念值不足，无法使用镇厄！\n"
                    "━━━━━━━━━━━━━\n"
                    f"✧ 当前怨念值 {player.resentment}\n"
                    f"✧ 镇厄需要 {cfg_break.get('guardian_cost_base', 50) + player.level * cfg_break.get('guardian_cost_per_level', 15)}\n"
                    "━━━━━━━━━━━━━\n"
                    "⬇️ 【献祭】获取怨念值\n"
                    "⬇️ 【连续突破】不使用镇厄"
                )
            else:
                # 计算下次成功率加成
                next_bonus = 0
                if cfg_break.get("fail_bonus_enabled", True):
                    fail_bonus_rate = cfg_break.get("fail_bonus_rate", 0.01)
                    next_bonus = player.breakthrough_fail_count * fail_bonus_rate
                    max_rate = cfg_break.get("fail_bonus_max_rate", 0.95)
                    next_bonus = min(next_bonus, max_rate)

                msg = (
                    "💥 连续突破失败，修为耗尽！\n"
                    "━━━━━━━━━━━━━\n"
                    f"✧ 当前等级 Lv.{player.level}\n"
                    f"✧ 失败次数 {failed_attempts} 次\n"
                    f"✧ 剩余修为 {player.exp}\n"
                    f"✧ 连续失败 {player.breakthrough_fail_count} 次\n"
                    f"✧ 下次成功率加成 +{int(next_bonus*100)}%\n"
                    "━━━━━━━━━━━━━\n"
                    "⬇️ 建议【突破 镇厄】以怨念护体"
                )
        else:
            # 计算消耗的修为
            consumed_exp = start_exp - player.exp

            cost_msg = ""
            if use_guardian and total_resentment_cost > 0:
                cost_msg = f"✧ 消耗怨念值 {total_resentment_cost} (剩余{player.resentment})\n"

            # 构建失败信息
            fail_msg = ""
            if failed_attempts > 0:
                fail_msg = f"✧ 失败次数 {failed_attempts} 次\n"

            msg = (
                f"⛓️‍💥连续突破完成！骨裂声不绝于耳！\n"
                "━━━━━━━━━━━━━\n"
                f"✧ 突破次数 {breakthrough_count} 次\n"
                + fail_msg +
                f"✧ 等级提升 Lv.{start_level} → Lv.{player.level}\n"
                f"✧ 消耗修为 {consumed_exp}\n"
                f"✧ 获得属性点 + {total_attribute_points}" + (f" (冥返加成)" if player.reincarnation_level > 0 else "") + "\n"
                f"✧ 剩余修为 {player.exp}\n"
                + cost_msg +
                (f"✧ 当前已达 Lv.{required_level}，需先进行冥返才能继续突破\n" if reached_level_cap else "") +
                "━━━━━━━━━━━━━\n"
                "⬇️ 【加点】缝合裂隙\n"
                "⬇️ 【修炼】继续喂养怨炁"
            )

        await continuous_breakthrough.finish(message_add_head(msg, event))

# 基础属性映射表
ATTRIBUTE_MAP = {
    "体": "max_hp",
    "智": "max_mp",
    "力": "attack",
    "敏": "agility",
    "运": "luck",
    "防": "defense",
}

@assign_points.handle()
async def handle_assign(event: MessageEvent, args: Message = CommandArg()):
    """分配属性点"""
    user_input = args.extract_plain_text().strip()
    params = user_input.split()

    if len(params) != 2:
        # 检测常见的新手错误输入
        error_msg = "⛔ 加点指令格式错误！\n\n"

        if not user_input:
            error_msg += "🎯 正确格式：加点 属性 点数\n"
        elif len(params) == 1:
            # 可能是连在一起写的，如"运5"
            if any(char.isdigit() for char in params[0]):
                error_msg += "💡 检测到你可能把属性和点数连在一起了\n"
                error_msg += f"❌ 你输入的：{user_input}\n"
                error_msg += "✅ 正确格式：加点 运 5 (中间要有空格)\n"
            else:
                error_msg += f"❌ 你输入的：{user_input}\n"
                error_msg += "✅ 正确格式：加点 运 5 (缺少点数)\n"
        elif len(params) > 2:
            error_msg += f"❌ 你输入的：{user_input}\n"
            error_msg += "✅ 正确格式：加点 运 5 (参数太多了)\n"

        error_msg += "\n📖 使用说明：\n"
        error_msg += "• 格式：加点 属性 点数\n"
        error_msg += "• 例子：加点 力 5 (给力量加5点)\n"
        error_msg += "• 可选属性：体/智/力/敏/防/运\n"
        error_msg += "\n💡 发送【加点帮助】查看属性详解\n"
        error_msg += "💡 发送【新手指引】学习指令格式"

        await assign_points.finish(error_msg)
    
    attr_name, points = params
    try:
        points = int(points)
        if points <= 0:
            raise ValueError
    except ValueError:
        error_msg = f"⛔ 点数格式错误！\n\n"
        error_msg += f"❌ 你输入的点数：{params[1]}\n"
        error_msg += f"✅ 点数必须是正整数（1, 2, 3...）\n\n"
        error_msg += f"💡 正确例子：\n"
        error_msg += f"• 加点 运 1 (加1点)\n"
        error_msg += f"• 加点 力 10 (加10点)\n"
        error_msg += f"• 加点 体 5 (加5点)"
        await assign_points.finish(error_msg)

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await assign_points.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await assign_points.finish("⛔ 请先创建角色")
        
        if attr_name not in ATTRIBUTE_MAP:
            # 提供更友好的属性错误提示
            error_msg = f"⛔ 属性名称错误！\n\n"
            error_msg += f"❌ 你输入的属性：{attr_name}\n"
            error_msg += f"✅ 可用属性：{'/'.join(ATTRIBUTE_MAP.keys())}\n\n"
            error_msg += "📖 属性说明：\n"
            error_msg += "• 体 = 生命值上限\n"
            error_msg += "• 智 = 理智值上限\n"
            error_msg += "• 力 = 攻击力\n"
            error_msg += "• 敏 = 敏捷度\n"
            error_msg += "• 防 = 防御力\n"
            error_msg += "• 运 = 幸运值\n\n"
            error_msg += "💡 例子：加点 运 5 (给幸运值加5点)\n"
            error_msg += "💡 发送【加点帮助】查看详细属性指南"
            await assign_points.finish(error_msg)
        
        if player.attribute_points < points:
            await assign_points.finish(f"💢 属性点不足！当前剩余：{player.attribute_points}✨")
        
        attr_field = ATTRIBUTE_MAP[attr_name]
        inc_val = points * cfg["attributes_base"][attr_field]

        # 记录分配前是否满血满蓝（仅在分配体/智属性时需要）
        was_hp_full = player.hp >= player.max_hp
        was_mp_full = player.mp >= player.max_mp

        # -------- 撤销旧装备 bonus --------
        result_eq = await session.execute(
            _sel(_Equip).where(
                _Equip.player_id == player.id, _Equip.equipped == True,
                _Equip.item_id.in_(config.items_config["by_type"]["EQUIPMENT"])
            )
        )
        equipped_items = result_eq.scalars().all()

        # 1. 先卸下所有装备，恢复基础属性
        for eq in equipped_items:
            # 恢复玩家属性
            delta_prev = (eq.extra_attrs or {}).get("_persist_bonus", {})
            for k, v in delta_prev.items():
                setattr(player, k, getattr(player, k) - v)
            
            # 清除持久化记录并标记未穿戴
            if "_persist_bonus" in (eq.extra_attrs or {}):
                extra_new = {k: v for k, v in eq.extra_attrs.items() if k != "_persist_bonus"}
                eq.extra_attrs = extra_new
            
            eq.equipped = False

        # -------- 更新基础属性 --------
        setattr(player, attr_field, getattr(player, attr_field) + inc_val)
        player.attribute_points -= points

        # -------- 重新计算装备 bonus 根据新基础 --------
        base_attrs_snapshot = {
            "attack": player.attack,
            "defense": player.defense,
            "agility": player.agility,
            "luck": player.luck,
            "max_hp": player.max_hp,
            "max_mp": player.max_mp,
        }

        # 2. 重新穿戴所有装备，每件都基于基础属性计算
        for eq in equipped_items:
            # 标记为已装备
            eq.equipped = True
            
            # 基于基础属性计算装备加成
            attrs_temp = base_attrs_snapshot.copy()
            eq.apply_attr_bonus(attrs_temp, base_attrs_snapshot)
            new_delta = {}
            for k in attrs_temp:
                if k in base_attrs_snapshot:
                    if attrs_temp[k] != base_attrs_snapshot[k]:
                        new_delta[k] = attrs_temp[k] - base_attrs_snapshot[k]
                else:
                    # 对于base_attrs_snapshot中不存在的属性，直接使用新值作为加成
                    if attrs_temp[k] != 0:
                        new_delta[k] = attrs_temp[k]

            # 应用新 delta
            for k, v in new_delta.items():
                setattr(player, k, getattr(player, k) + v)

            # 保存新的持久化bonus
            extra = eq.extra_attrs or {}
            extra["_persist_bonus"] = new_delta
            eq.extra_attrs = extra
            session.add(eq)  # 确保装备的修改被保存

        # 如果分配前是满血满蓝，分配后也应该保持满状态
        if attr_field == "max_hp" and was_hp_full:
            player.hp = player.max_hp
        elif attr_field == "max_mp" and was_mp_full:
            player.mp = player.max_mp
        else:
            # 修正 HP/MP 不超过新上限
            if player.hp > player.max_hp:
                player.hp = player.max_hp
            if player.mp > player.max_mp:
                player.mp = player.max_mp

        session.add(player)
        await session.commit()

        # 展示本次加点带来的实际数值提升（如 体+10 实际 生命上限+30）
        _label_map = {
            "max_hp": "生命上限",
            "max_mp": "理智上限",
            "attack": "攻击",
            "defense": "防御",
            "agility": "敏捷",
            "luck": "幸运",
        }
        _actual_line = f"✧ 实际提升：{_label_map.get(attr_field, attr_field)} +{inc_val}\n"

        msg = (
            "🩸 裂隙缝合\n"
            f"✧ {attr_name} +{points} → {getattr(player, attr_field)}\n"
            f"{_actual_line}"
            "━━━━━━━━━━━━━\n"
            f"✧ 剩余属性点 {player.attribute_points}\n"
            "━━━━━━━━━━━━━\n"
            "⬇️ 【面板】检查残骸"
        )
        if attr_name == '运':
            msg += "\n⬇️ 【幸运榜】查看运气排名"

        # 如果还有属性点，提示查看加点帮助
        if player.attribute_points > 0:
            msg += "\n💡 【加点帮助】查看属性指南"

        # 检查新手任务
        from ..quest.novice_quest_service import NoviceQuestService
        quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(
            session, player, "command", {"command": "加点"}
        )

        if quest_completed and quest_msg:
            msg += f"\n\n{quest_msg}"

        await assign_points.finish(message_add_head(msg, event))


@free_reset_points.handle()
async def handle_free_reset_points(event: MessageEvent):
    """免费洗点处理函数 - 仅限30级以下玩家使用，消耗5点咒抗"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await free_reset_points.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await free_reset_points.finish("⛔ 请先创建角色")

        # 检查等级限制
        if player.level >= 30:
            await free_reset_points.finish(
                "⛔ 免费洗点仅限30级以下的新手使用！\n"
                "━━━━━━━━━━━━━\n"
                f"📊 你的等级：{player.level}级\n"
                "📊 等级限制：30级以下\n"
                "━━━━━━━━━━━━━\n"
                "💡 高级玩家请购买【重启符】洗点\n"
            )

        # 检查咒抗是否足够
        required_stamina = 5
        if player.stamina < required_stamina:
            await free_reset_points.finish(
                f"⛔ 咒抗不足，无法使用免费洗点！\n"
                "━━━━━━━━━━━━━\n"
                f"⚡ 当前咒抗：{player.stamina}\n"
                f"⚡ 需要咒抗：{required_stamina}\n"
                "━━━━━━━━━━━━━\n"
                "💡 每日签到可恢复咒抗\n"
                "💡 发送【签到】恢复咒抗"
            )

        # 执行免费洗点逻辑（复用重启符的逻辑）
        from ..config import config as gcfg
        from sqlalchemy import select
        from ..models.elixir_usage import ElixirUsageLog
        from ..models.inventory import ItemInstance
        from ..models.vip_equipment_bonus import VIPEquipmentBonus

        # 初始基础属性
        INIT = {
            "max_hp": 20,
            "max_mp": 20,
            "attack": 1,
            "defense": 5,
            "agility": 5,
            "luck": 1,
        }

        # 计算丹药加成
        elixir_bonus = {k: 0 for k in INIT}
        # 获取所有丹药使用记录（不限日期，因为丹药效果是永久的）
        stmt = select(ElixirUsageLog).where(ElixirUsageLog.player_id == player.id)
        logs = (await session.execute(stmt)).scalars().all()

        # 统计每种丹药的总使用量
        elixir_usage_total = {}
        for log in logs:
            if log.item_id not in elixir_usage_total:
                elixir_usage_total[log.item_id] = 0
            elixir_usage_total[log.item_id] += log.quantity

        # 计算丹药属性加成
        from ..models.inventory import ItemEffectType
        for item_id, total_qty in elixir_usage_total.items():
            item_cfg = gcfg.items_config["by_id"].get(item_id)
            if item_cfg and item_cfg.effect_type == ItemEffectType.BUFF:
                effect_params = item_cfg.effect_params or {}
                for attr, value in effect_params.items():
                    if attr in elixir_bonus:
                        elixir_bonus[attr] += int(value) * total_qty

        # 获取VIP装备永久加成
        vip_bonus = {k: 0 for k in INIT}
        stmt_vip = select(VIPEquipmentBonus).where(VIPEquipmentBonus.player_id == player.id)
        vip_record = (await session.execute(stmt_vip)).scalars().first()
        if vip_record:
            for attr, value in vip_record.get_total_bonus().items():
                if attr in vip_bonus:
                    vip_bonus[attr] = int(value)

        # 重置属性为基础值 + 丹药加成 + VIP装备永久加成（先不加装备加成）
        for k, base_v in INIT.items():
            total_bonus = elixir_bonus.get(k, 0) + vip_bonus.get(k, 0)
            setattr(player, k, base_v + total_bonus)

        # 重新计算可分配点（考虑转数加成）
        from .reincarnation_service_new import ReincarnationService
        pts_per_lvl = ReincarnationService.get_attribute_points_per_level(player.reincarnation_level)
        player.attribute_points = (player.level - 1) * pts_per_lvl

        # 重新计算装备加成（基于新的基础属性）
        # 获取所有已装备的装备
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(gcfg.items_config["by_type"]["EQUIPMENT"])
        )
        equipped_items = (await session.execute(stmt)).scalars().all()

        # 1. 先卸下所有装备，恢复基础属性
        for eq in equipped_items:
            # 恢复玩家属性
            delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
            for k, v in delta.items():
                setattr(player, k, getattr(player, k) - v)

            # 清除持久化记录并标记未穿戴
            if "_persist_bonus" in (eq.extra_attrs or {}):
                extra_new = {k: v for k, v in eq.extra_attrs.items() if k != "_persist_bonus"}
                eq.extra_attrs = extra_new

            eq.equipped = False

        # 2. 获取玩家基础属性（无装备加成）
        base_attrs = {
            "attack": player.attack,
            "defense": player.defense,
            "agility": player.agility,
            "luck": player.luck,
            "max_hp": player.max_hp,
            "max_mp": player.max_mp,
        }

        # 3. 重新穿戴所有装备，每件都基于基础属性计算
        for eq in equipped_items:
            # 标记为已装备
            eq.equipped = True

            # 基于基础属性计算装备加成
            attrs_temp = base_attrs.copy()
            eq.apply_attr_bonus(attrs_temp, base_attrs)
            new_delta = {}
            for k in attrs_temp:
                if k in base_attrs:
                    if attrs_temp[k] != base_attrs[k]:
                        new_delta[k] = attrs_temp[k] - base_attrs[k]
                else:
                    # 对于base_attrs中不存在的属性，直接使用新值作为加成
                    if attrs_temp[k] != 0:
                        new_delta[k] = attrs_temp[k]

            # 应用到玩家属性
            for k, v in new_delta.items():
                setattr(player, k, getattr(player, k) + v)

            # 保存新的持久化加成
            extra = eq.extra_attrs or {}
            extra["_persist_bonus"] = new_delta
            eq.extra_attrs = extra
            session.add(eq)

        # 保证当前 HP/MP 不超上限
        if player.hp > player.max_hp:
            player.hp = player.max_hp
        if player.mp > player.max_mp:
            player.mp = player.max_mp

        # 扣除咒抗
        player.stamina -= required_stamina

        # 生成详细的重置信息
        bonus_info = []

        # 检查是否有装备加成（重新计算后的）
        has_equipment_bonus = False
        for eq in equipped_items:
            delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
            if any(delta.values()):
                has_equipment_bonus = True
                break

        if has_equipment_bonus:
            bonus_info.append("装备加成已保留")

        if any(elixir_bonus.values()):
            elixir_details = []
            for k, v in elixir_bonus.items():
                if v > 0:
                    attr_name = {"max_hp": "体", "max_mp": "智", "attack": "力", "defense": "防", "agility": "敏", "luck": "运"}.get(k, k)
                    elixir_details.append(f"{attr_name}+{v}")
            if elixir_details:
                bonus_info.append(f"丹药加成已保留({', '.join(elixir_details)})")

        bonus_msg = f"，{', '.join(bonus_info)}" if bonus_info else ""

        session.add(player)
        await session.commit()

        msg = (
            "🆓 新手免费洗点成功！\n"
            "━━━━━━━━━━━━━\n"
            "🔄 属性已重置，所有点数已退还\n"
            f"⚡ 消耗咒抗：{required_stamina} (剩余：{player.stamina})\n"
            f"📊 可分配属性点：{player.attribute_points}\n"
            f"{bonus_msg}\n" if bonus_msg else ""
            "━━━━━━━━━━━━━\n"
            "💡 现在可以重新分配属性点了！\n"
            "💡 发送【加点帮助】查看属性指南\n"
            "━━━━━━━━━━━━━\n"
            "⚠️ 此功能仅限30级以下使用\n"
            "⚠️ 30级后请使用重启符洗点"
        )

        await free_reset_points.finish(message_add_head(msg, event))
