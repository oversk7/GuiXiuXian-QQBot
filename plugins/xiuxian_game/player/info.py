from nonebot import on_command
from nonebot.params import CommandArg, ArgPlainText
from nonebot.adapters.qq import MessageEvent, Message, MessageSegment
from nonebot.adapters.qq.models import MessageMarkdown, MessageMarkdownParams
from nonebot.typing import T_State
from ..models.db import safe_session, AsyncSessionLocal
from ..models.player import Player
from sqlalchemy import select, func
from ..models.player import Gender
from ..utils import message_add_head, calculate_level_up_exp
from datetime import datetime
from ..models.inventory import ItemInstance, ItemType
from collections import defaultdict
from ..models.guild import Guild
import random
from ..models.navigation_task import NavigationTask
from ..world.navigation import _update_nav_position
from ..platform_utils import get_unified_player, format_platform_message, is_guild_message
from ..config import config
from ..infrastructure.uow import UnitOfWork
from ..domain.attributes import get_effective_attributes_v2
from ..infrastructure.repositories.account_transfer_log_repository import AccountTransferLogRepository
from ..queries.player_queries import query_player_profile


def _format_player_location(player: Player) -> str:
    """格式化玩家位置信息，区分现实世界和诡域坐标"""
    if player.is_in_dungeon():
        # 在诡域中：显示诡域坐标和现实世界坐标
        dungeon_x, dungeon_y = player.get_current_coordinates()
        real_x = player.real_world_x or 0
        real_y = player.real_world_y or 0
        return f"{player.get_current_region()} ({dungeon_x},{dungeon_y}) | 现实 ({real_x},{real_y})"
    else:
        # 在现实世界：只显示现实世界坐标
        real_x, real_y = player.get_current_coordinates()
        return f"{player.get_current_region()} ({real_x},{real_y})"
from ..config import config
from ..world.message_board import get_unread_message_status

# 从独立模块导入境界相关函数，避免循环导入
from .realm_utils import realm_by_level, realm_by_level_and_reincarnation, number_to_chinese



profile = on_command("角色",aliases={"面板","状态"}, block=True, priority=5)
register = on_command("注册", block=True, priority=5)
change_gender = on_command("改性别", aliases={"修改性别"}, block=True, priority=5)
newbie_guide = on_command("新手指引", aliases={"指令格式", "指令帮助", "新手教程"}, block=True, priority=5)
attribute_guide = on_command("加点帮助", aliases={"属性帮助", "加点指南", "属性说明"}, block=True, priority=5)


@profile.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    # 解析参数：如果提供了 UID，则查询对应玩家面板
    arg_text = args.extract_plain_text().strip()
    target_uid: int | None = None
    if arg_text:
        try:
            target_uid = int(arg_text)
        except ValueError:
            await profile.finish("⛔ UID 必须为数字")

    quest_extra = ""  # 存储任务/成就检查结果

    # ===== 查看他人面板：纯只读路径 =====
    if target_uid is not None:
        profile_data = await query_player_profile(target_uid)
        if not profile_data:
            await profile.finish("⛔ 未找到该 UID")
        player = profile_data.player
        effective_attrs = profile_data.effective_attrs
        bonus = profile_data.equipment_bonus
        guild_name = profile_data.guild_name
    else:
        # ===== 查看自己面板：保留 UoW 路径（含导航更新等写操作） =====
        async with UnitOfWork(AsyncSessionLocal) as uow:
            player = await get_unified_player(uow.session, event)

            if not player:
                if is_guild_message(event):
                    await profile.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
                else:
                    await profile.finish("⛔ 你还没有创建角色")

            # 更新坐标（若在自动导航）
            player_upd = await uow.session.get(Player, player.id)
            task = await uow.session.get(NavigationTask, player.id)
            if player_upd and task:
                reached = await _update_nav_position(player_upd, task, uow.session)
                if reached:
                    await uow.session.delete(task)
                await uow.commit()
                if not player.is_in_dungeon():
                    player.x = player_upd.x
                    player.y = player_upd.y
                if hasattr(player, "real_world_x"):
                    player.real_world_x = player_upd.real_world_x
                    player.real_world_y = player_upd.real_world_y

            effective_attrs = await get_effective_attributes_v2(player, uow.session)

            bonus = defaultdict(int)
            equip_ids = config.items_config["by_type"]["EQUIPMENT"]
            eq_stmt = select(ItemInstance).where(
                ItemInstance.player_id == player.id,
                ItemInstance.equipped == True,
                ItemInstance.item_id.in_(equip_ids)
            )
            equiped_list = (await uow.session.execute(eq_stmt)).scalars().all()
            for eq in equiped_list:
                delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
                for k, v in delta.items():
                    bonus[k] += int(v)

            guild_name = "无所属"
            if player.guild_id:
                g_obj = await uow.session.get(Guild, player.guild_id)
                if g_obj:
                    guild_name = g_obj.name

            # 新手任务和成就检查（需要活跃的 session）
            from ..quest.novice_quest_service import NoviceQuestService
            quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(
                uow.session, player, "command", {"command": "角色"}
            )
            if quest_completed and quest_msg:
                quest_extra = f"\n\n{quest_msg}"

            from ..achievement.achievement_service import AchievementService
            achievement_msgs = await AchievementService.check_achievements(uow.session, player)
            if achievement_msgs:
                quest_extra += "\n\n" + "\n".join(achievement_msgs)

    # 7. 格式化属性显示
    def fmt(attr_key: str, effective_value: int):
        inc = bonus.get(attr_key, 0)
        return f"{effective_value} (+{inc})" if inc else str(effective_value)

    atk_str = fmt("attack", effective_attrs["attack"])
    def_str = fmt("defense", effective_attrs["defense"])
    agi_str = fmt("agility", effective_attrs["agility"])
    luk_str = fmt("luck", effective_attrs["luck"])
    hp_max_str = fmt("max_hp", effective_attrs["max_hp"])
    mp_max_str = fmt("max_mp", effective_attrs["max_mp"])

    # 若当前 HP/MP 超出新上限，则修正显示
    cur_hp = min(player.hp, effective_attrs["max_hp"])
    cur_mp = min(player.mp, effective_attrs["max_mp"])

    realm_name = realm_by_level_and_reincarnation(player.level, player.reincarnation_level)
    exp_max = calculate_level_up_exp(player.level)

    # 获取活动称号（如有）
    from ..event.knocker_event import KnockerEventService
    player_title = KnockerEventService.get_player_title(player)
    display_name = player.nickname  # 称号不再拼接到昵称，单独展示
    title_line = f"🏅称号 「{player_title}」" if player_title else ""

    # 检查未读的留言板与私信状态
    has_world_unread, has_private_unread = await get_unread_message_status(player.id)
    unread_notice = ""
    notice_lines: list[str] = []
    if has_private_unread:
        notice_lines.append("📬 有新私信未读！输入【留言板 私信】查看")
    if has_world_unread:
        notice_lines.append("🗒️ 世界留言板有新内容！输入【留言板】查看")
    if notice_lines:
        unread_notice = "".join(f"\n┃{line}" for line in notice_lines)

    content = (
        f"┏━━ 信息 ━━━━\n"
        f"┃{display_name}[UID:{player.uid}]「{player.sex}」\n"
        f"┃ Lv.{player.level} · {realm_name}\n"
        f"┃ Exp {player.exp}/{exp_max}\n"
        "┣━━ 状态 ━━━━\n"
        f"┃ ❤️生命 {cur_hp}/{hp_max_str}\n"
        f"┃ 🧠理智 {cur_mp}/{mp_max_str}\n"
        f"┃ ⚔力 {atk_str}   🛡防 {def_str}\n"
        f"┃ 👟敏 {agi_str}   🍀运 {luk_str}\n"
        f"┃ 🔮咒抗 {player.stamina}\n"
        "┣━━ 其他 ━━━━\n"
        f"┃ 🪙金币 {player.gold}  💎积分 {player.gold2}\n"
        f"┃ 🕯️诡烛 {player.gui_zhu}\n"
        f"┃ 💀怨念 {player.resentment} ✨点数 {player.attribute_points}\n"
        f"┃ ☯公会 {guild_name}\n"
        f"┃ 📍位置 {_format_player_location(player)}\n"
        "┣━━━━━━━━━\n"
        f"┃☞【装备栏】【社交系统】{unread_notice}"
    )

    # 附加任务/成就检查结果（仅查看自己面板时有值）
    content += quest_extra

    # 使用图鉴类模板美化显示（仅在QQ平台且查看自己面板时使用）
    if target_uid is None and hasattr(event, 'get_user_id'):
        try:
            # 获取玩家QQ官方ID（用于头像）
            qq_openid = event.get_user_id()

            # 调试日志
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"[面板MD] 尝试发送MD模板，qq_openid={qq_openid}")

            # 构建图鉴模板参数
            title = f"{display_name} [UID:{player.uid}]"

            # 描述信息（所有玩家信息，使用\r换行）
            desc_lines = [
                f"Lv.{player.level} · {realm_name} | {player.sex}",
            ]
            if title_line:
                desc_lines.append(title_line)
            desc_lines.extend([
                f"☯公会 {guild_name}",
                f"Exp {player.exp}/{exp_max}",
                f"━━━ 状态 ━━━",
                f"❤️生命 {cur_hp}/{hp_max_str}",
                f"🧠理智 {cur_mp}/{mp_max_str}",
                f"⚔力 {atk_str}  🛡防 {def_str}",
                f"👟敏 {agi_str}  🍀运 {luk_str}",
                f"🔮咒抗 {player.stamina}",
                f"━━━ 资产 ━━━",
                f"🪙金币 {player.gold}  💎积分 {player.gold2}",
                f"🕯️诡烛 {player.gui_zhu}",
                f"💀怨念 {player.resentment}  ✨点数 {player.attribute_points}",
                f"━━━ 位置 ━━━",
                f"📍{_format_player_location(player)}",
            ])
            desc = "\r".join(desc_lines)

            # 玩家头像URL
            avatar_url = f"https://thirdqq.qlogo.cn/qqapp/102499345/{qq_openid}/0"

            # 提示信息（留言板状态，使用\r换行）
            hint = "☞【装备栏】【社交系统】"

            # 添加未读消息提示
            if unread_notice:
                clean_notice = unread_notice.replace('\n', '\r')
                hint += f"\r{clean_notice}"

            # 清理所有参数中的\n换行符，确保只使用\r
            title = title.replace('\n', '\r')
            desc = desc.replace('\n', '\r')
            hint = hint.replace('\n', '\r')

            # 构建模板参数
            template_params = [
                MessageMarkdownParams(key="title", values=[title]),
                MessageMarkdownParams(key="desc", values=[desc]),
                MessageMarkdownParams(key="width", values=["32"]),
                MessageMarkdownParams(key="height", values=["32"]),
                MessageMarkdownParams(key="imgurl", values=[avatar_url]),
                MessageMarkdownParams(key="hint", values=[hint])
            ]

            # 使用图鉴类Markdown模版
            markdown_msg = MessageMarkdown(
                custom_template_id="102499345_1769178984",
                params=template_params
            )
            await profile.finish(MessageSegment.markdown(markdown_msg))
        except Exception as e:
            # 如果模板发送失败，回退到文字版本
            # formatted_content = format_platform_message(content, event)
            # await profile.finish(message_add_head(formatted_content, event))
            raise  # 重新抛出异常，让用户看到错误
    else:
        # 查看他人面板时也使用MD版本
        # 注释掉文字版，保留代码
        # formatted_content = format_platform_message(content, event)
        # await profile.finish(message_add_head(formatted_content, event))

        # 查看他人面板时，使用对方的UID获取头像
        try:
            # 如果是查看他人，使用目标玩家的ID（openid）
            if target_uid:
                qq_openid = player.id
            else:
                qq_openid = event.get_user_id() if hasattr(event, 'get_user_id') else "default"

            # 构建图鉴模板参数
            title = f"{display_name} [UID:{player.uid}]"

            # 描述信息（所有玩家信息，使用\r换行）
            desc_lines = [
                f"Lv.{player.level} · {realm_name} | {player.sex}",
            ]
            if title_line:
                desc_lines.append(title_line)
            desc_lines.extend([
                f"☯公会 {guild_name}",
                f"Exp {player.exp}/{exp_max}",
                f"━━━ 状态 ━━━",
                f"❤️生命 {cur_hp}/{hp_max_str}",
                f"🧠理智 {cur_mp}/{mp_max_str}",
                f"⚔力 {atk_str}  🛡防 {def_str}",
                f"👟敏 {agi_str}  🍀运 {luk_str}",
                f"🔮咒抗 {player.stamina}",
                f"━━━ 资产 ━━━",
                f"🪙金币 {player.gold}  💎积分 {player.gold2}",
                f"🕯️诡烛 {player.gui_zhu}",
                f"💀怨念 {player.resentment}  ✨点数 {player.attribute_points}",
                f"━━━ 位置 ━━━",
                f"📍{_format_player_location(player)}",
            ])
            desc = "\r".join(desc_lines)

            # 玩家头像URL（16x16小头像）
            avatar_url = f"https://thirdqq.qlogo.cn/qqapp/102499345/{qq_openid}/0"

            # 提示信息（留言板状态，使用\r换行）
            hint = "☞【装备栏】【社交系统】"

            # 查看他人面板时不显示未读消息
            # if unread_notice:
            #     clean_notice = unread_notice.replace('\n', '\r')
            #     hint += f"\r{clean_notice}"

            # 清理所有参数中的\n换行符，确保只使用\r
            title = title.replace('\n', '\r')
            desc = desc.replace('\n', '\r')
            hint = hint.replace('\n', '\r')

            # 构建模板参数
            template_params = [
                MessageMarkdownParams(key="title", values=[title]),
                MessageMarkdownParams(key="desc", values=[desc]),
                MessageMarkdownParams(key="width", values=["16"]),
                MessageMarkdownParams(key="height", values=["16"]),
                MessageMarkdownParams(key="imgurl", values=[avatar_url]),
                MessageMarkdownParams(key="hint", values=[hint])
            ]

            # 使用图鉴类Markdown模版
            markdown_msg = MessageMarkdown(
                custom_template_id="102499345_1769178984",
                params=template_params
            )

            await profile.finish(MessageSegment.markdown(markdown_msg))
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"[面板MD] 查看他人面板MD发送失败: {e}", exc_info=True)
            raise  # 重新抛出异常

@register.handle()
async def _(event: MessageEvent, state: T_State, args: Message = CommandArg()):
    # 检查是否已有角色
    async with safe_session() as session:
        result = await session.execute(
            select(Player).where(Player.id == event.get_user_id())
        )
        if result.scalars().first():
            await register.finish("⛔ 你已经创建过角色了")

    arg_text = args.extract_plain_text().strip()
    if arg_text in ["男", "女"]:
        gender = Gender.MALE if arg_text == "男" else Gender.FEMALE
        async with safe_session() as session:
            nickname = await generate_random_nickname(session)
        result = await create_player(event, nickname, gender)
        await register.finish(result)

    if arg_text:
        await register.finish(
            "⛔ 格式错误\n💡 用法：【注册 男】或【注册 女】\n"
            "或直接发送【注册】按提示选择"
        )
    state["user_id"] = event.get_user_id()


@register.got("gender", prompt=(
    "🀄️ 欢迎来到诡修仙世界！\n"
    "──────────────\n"
    "⚧️ 请选择你的性别，回复 【男】 或 【女】："
))
async def _(event: MessageEvent, gender_input: str = ArgPlainText("gender")):
    gender_input = gender_input.strip()
    if gender_input not in ["男", "女"]:
        await register.reject("⛔ 请回复「男」或「女」")
    gender = Gender.MALE if gender_input == "男" else Gender.FEMALE
    async with safe_session() as session:
        nickname = await generate_random_nickname(session)
    result = await create_player(event, nickname, gender)
    await register.finish(result)


def _clean_nickname_input(nickname: str) -> str:
    """清理昵称输入，移除常见的误输入前缀"""
    nickname = nickname.strip()

    # 常见的误输入模式
    patterns_to_remove = [
        "/注册",
        "注册",
        "/修炼系统",
        "/世界系统",
        "/帮助",
        "/面板",
        "/修炼"
    ]

    # 移除这些前缀（不区分大小写）
    for pattern in patterns_to_remove:
        if nickname.lower().startswith(pattern.lower()):
            nickname = nickname[len(pattern):].strip()
            break

    # 移除可能的分隔符
    separators = [" ", "　", "\t", "-", "_", ":", "：", "|", "｜"]
    for sep in separators:
        if nickname.startswith(sep):
            nickname = nickname[1:].strip()
            break

    return nickname


async def generate_random_nickname(session) -> str:
    """生成随机修仙风格昵称，保证与数据库现有玩家不重复"""
    SURNAMES = [
        "李", "王", "张", "刘", "陈", "杨", "黄", "周", "吴", "徐",
        "孙", "马", "朱", "林", "何", "郭", "罗", "梁", "宋", "唐",
        "叶", "慕", "夜", "冥", "玄", "凌", "沈", "裴", "顾", "白",
        "苍", "幽", "魂", "灰", "霜", "寒", "暗", "虚", "骸", "煞",
    ]
    DARK_CHARS = [
        "玄", "冥", "幽", "魂", "骸", "殇", "焰", "渊", "墟", "炁",
        "寂", "祸", "蛊", "苍", "枯", "暗", "影", "刃", "戾", "邪",
        "厄", "咒", "逝", "灭", "荒", "孽", "怨", "狱", "伐", "屠",
        "陨", "腐", "瘴", "噩", "孤", "悸", "蛮", "契", "乱", "煞",
    ]
    NORMAL_CHARS = [
        "伟", "明", "强", "敏", "峰", "云", "风", "月", "雪", "星",
        "阳", "龙", "凤", "飞", "涛", "雨", "洁", "文", "武", "晨",
    ]
    for _ in range(10):
        surname = random.choice(SURNAMES)
        r = random.random()
        if r < 0.15:   # 15% 三字名（姓+暗黑字+暗黑字）
            c1 = random.choice(DARK_CHARS)
            c2 = random.choice([c for c in DARK_CHARS if c != c1])
            nickname = surname + c1 + c2
        elif r < 0.35:  # 20% 普通字
            nickname = surname + random.choice(NORMAL_CHARS)
        else:           # 65% 修仙暗黑字
            nickname = surname + random.choice(DARK_CHARS)
        existing = await session.execute(select(Player).where(Player.nickname == nickname))
        if not existing.scalars().first():
            return nickname
    return nickname + str(random.randint(10, 99))  # 兜底：加后缀


async def create_player(event: MessageEvent, nickname: str, gender: Gender) -> Message:
    """创建新玩家角色，返回Markdown卡片消息"""
    async with safe_session() as session:
        # 再次检查是否已有角色（防止在会话过程中创建）
        result = await session.execute(
            select(Player).where(Player.id == event.get_user_id())
        )
        if result.scalars().first():
            return Message("⛔ 你已经创建过角色了")

        # 检查是否有账号转让历史（防止转让后重复创建）
        transfer_log_repo = AccountTransferLogRepository(session)
        transfer_history = await transfer_log_repo.find_by_from_platform(
            event.get_user_id(),
            limit=1
        )
        if transfer_history:
            return Message(
                "⛔ 你的账号曾有转让记录，无法再次创建角色\n"
                "💡 如果这是误操作，请联系管理员"
            )

        # 获取当前最大UID
        max_uid_result = await session.execute(
            select(func.max(Player.uid))
        )
        max_uid = max_uid_result.scalar() or 99

        new_player = Player(
            id=event.get_user_id(),
            uid=max_uid + 1,
            nickname=nickname,
            sex=gender,
            created_at=datetime.now()
        )

        session.add(new_player)
        await session.commit()

        # 💡 改名卡由首次签到时赠送，见 entertainment/sign.py

        # 初始化新手任务
        from ..quest.novice_quest_service import NoviceQuestService
        await NoviceQuestService.init_novice_quests(session, new_player)

        card_type = random.choice(('🎲','🀄️','🀃','🀅','🀆','🀀','🀁','🀂','🀒','🀚','🀣'))

        # 使用反馈类模版 (102499345_1769177016)
        title = f"⚰️ 棺盖移位，黑暗替你呼吸——欢迎回到人间"

        result_text = (
            f"┌── 🃏新牌出世🃏 ──┐\r"
            f"🪬 道号  : {card_type}{nickname}\r"
            f"🆔 UID   : {new_player.uid}\r"
            f"⚧️ 性别  : {new_player.sex.value}\r"
            f"━━━━━━━━━━━━━\r"
            f"📜 你的第一天路线：\r"
            f"1. 【修炼】提升等级 → 攒够经验后【突破】\r"
            f"2. 【打工】赚金币 → 用来买装备和药品\r"
            f"3. 【签到】领每日奖励\r"
            f"4. 【面板】查看自己的状态\r"
            f"━━━━━━━━━━━━━\r"
            f"💡 系统为你生成了道号，可签到后用改名卡修改\r"
            f"💡 新手任务已开启，跟着做就能快速变强！\r"
            f"💡 发送【新手指引】查看完整成长路线\r"
            f"💡 指令不要带【】括号，空格不能少"
        )

        # 构建Markdown模板参数
        template_params = [
            MessageMarkdownParams(key="title", values=[title]),
            MessageMarkdownParams(key="result", values=[result_text]),
            MessageMarkdownParams(key="btn1", values=["修炼"]),
            MessageMarkdownParams(key="btn2", values=["打工"]),
            MessageMarkdownParams(key="btn3", values=["签到"]),
            MessageMarkdownParams(key="btn4", values=["面板"]),
            MessageMarkdownParams(key="btn5", values=["新手指引"]),
            MessageMarkdownParams(key="btn6", values=["突破"]),
            MessageMarkdownParams(key="btn7", values=["背包"]),
            MessageMarkdownParams(key="btn8", values=["帮助"]),
        ]

        markdown = MessageMarkdown(
            custom_template_id="102499345_1769177016",
            params=template_params
        )

        # 构建消息
        msg = Message("🎉 角色创建成功")
        msg.append(MessageSegment.markdown(markdown))
        return msg


@change_gender.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """修改角色性别"""
    gender_str = args.extract_plain_text().strip()

    if not gender_str:
        await change_gender.finish("⛔ 请指定性别，格式：改性别 男/女")

    try:
        gender = Gender(gender_str)
    except ValueError:
        await change_gender.finish(f"⛔ 无效的性别，可选：{Gender.MALE.value}/{Gender.FEMALE.value}")

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await change_gender.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await change_gender.finish("⛔ 请先创建角色")

        if player.sex == gender:
            await change_gender.finish(f"⛔ 你的性别已经是{gender.value}了")

        old_gender = player.sex
        player.sex = gender
        session.add(player)
        await session.commit()

        # 获取活动称号（如有）
        from ..event.knocker_event import KnockerEventService
        player_title = KnockerEventService.get_player_title(player)
        display_name = f"{player.nickname}·{player_title}" if player_title else player.nickname

        await change_gender.finish(message_add_head(
            f"✨ 性别修改成功！\n"
            f"🔄 {old_gender} → {gender.value}\n"
            f"👤 {display_name}[UID:{player.uid}]",
            event
        ))


@newbie_guide.handle()
async def _(event: MessageEvent):
    """新手指引 - 教会新手如何正确使用指令格式"""

    # 检查是否已有角色
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await newbie_guide.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await newbie_guide.finish("⛔ 请先创建角色，发送【注册】开始游戏")

    content = (
        "📜 新手指引 - 你该干什么\n"
        "━━━━━━━━━━━━━\n"
        "\n"
        "🔰 第一天（立刻做）：\n"
        "【修炼】 获取经验（5分钟冷却）\n"
        "【突破】 经验够了就突破升级\n"
        "【加点 属性 点数】 突破后分配属性点\n"
        "【签到】 每日签到领奖励\n"
        "【打工】 赚金币（到工作地点后使用）\n"
        "💡 加点不会？发【加点帮助】看推荐方案\n"
        "\n"
        "⚔️ 站稳脚跟（1-30级）：\n"
        "【每日委托】 接取缉邪任务赚经验金币\n"
        "【进入 1层诡域】 刷副本获取材料\n"
        "【锻造列表】 查看可锻造的装备\n"
        "【丹方】 查看可炼制的丹药\n"
        "【闭关】 离线挂机修炼（最长9-12小时）\n"
        "\n"
        "📈 进阶发展（30级+）：\n"
        "【市集】 跑商低买高卖赚差价\n"
        "【投资行情】 气运投资（高风险高回报）\n"
        "【公会列表】 加入公会享受建筑加成\n"
        "【购买阴宅】 拥有阴宅大幅提升修炼效率\n"
        "【钓鱼】 钓鱼获取食材\n"
        "\n"
        "━━━━━━━━━━━━━\n"
        "💎 核心循环：\n"
        "变强 = 修炼突破 + 装备锻造 + 丹药炼制\n"
        "赚钱 = 打工(稳) + 跑商(中) + 投资(险)\n"
        "刷材料 = 诡域副本 + 每日委托 + 探索\n"
        "\n"
        "━━━━━━━━━━━━━\n"
        "📖 指令格式提醒：\n"
        "• 【】里的是指令，不要把括号打出来\n"
        "• 指令和参数之间用空格隔开\n"
        "• 例：加点 力 5（给力量加5点）\n"
        "\n"
        "🆘 还是不懂？\n"
        "• 发送【帮助】查看所有系统\n"
        "• 加官群：962494679 问老玩家\n"
        "• 教程：https://Tutorials.Bossjlb.Top"
    )

    await newbie_guide.finish(message_add_head(content, event))


@attribute_guide.handle()
async def _(event: MessageEvent):
    """加点帮助 - 详细说明各个属性的作用和推荐加点方案"""

    # 检查是否已有角色
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await attribute_guide.finish("⛔ 请先创建角色，发送【注册】开始游戏")

    content = (
        "🔮 加点帮助 - 属性详解与推荐\n"
        "━━━━━━━━━━━━━\n"
        "📊 基础属性说明：\n"
        "\n"
        "🩸 体力 (体)：\n"
        "• 作用：增加生命值上限\n"
        "• 每点+3生命值上限\n"
        "• 重要性：★★★★☆\n"
        "• 适合：新手、坦克流、生存流\n"
        "\n"
        "🧠 理智 (智)：\n"
        "• 作用：增加理智值上限\n"
        "• 每点+1理智值上限\n"
        "• 重要性：★★★★★\n"
        "• 适合：探索流、副本流\n"
        "• 说明：理智用于诡域探索移动，讨伐世界boss\n"
        "\n"
        "⚔️ 力量 (力)：\n"
        "• 作用：增加攻击力\n"
        "• 每点+1攻击力\n"
        "• 重要性：★★★★☆\n"
        "• 适合：输出流、PVP流、刷怪流\n"
        "• 说明：战斗核心属性，影响伤害\n"
        "\n"
        "🛡️ 防御 (防)：\n"
        "• 作用：减少受到的伤害\n"
        "• 每点+1防御力\n"
        "• 重要性：★★★☆☆\n"
        "• 适合：坦克流、生存流\n"
        "• 说明：防御越高，免伤率越高\n"
        "\n"
        "👟 敏捷 (敏)：\n"
        "• 作用：影响移动速度和战斗顺序\n"
        "• 每点+1敏捷度\n"
        "• 重要性：★★★★☆\n"
        "• 适合：跑商流、探索流\n"
        "• 说明：影响导航速度和先后手，与闪避无关\n"
        "\n"
        "🍀 运气 (运)：\n"
        "• 作用：影响发现材料时的翻倍率，签到奖励翻倍率，装备/镶嵌物升阶成功率\n"
        "• 每点+1运气值\n"
        "• 重要性：★★★☆☆\n"
        "• 适合：所有流派，特别是升阶流\n"
        "• 说明：影响收益和升阶成功率，升阶时最多提供20%成功率加成\n"
        "\n"
        "━━━━━━━━━━━━━\n"
        "🎮 相关指令：\n"
        "• 【加点 智 5】- 给理智加5点\n"
        "• 【面板】- 查看当前属性\n"
        "• 【战力】- 查看详细战斗属性\n"
        "\n"
        "🆘 需要帮助？发送【新手指引】学习指令格式"
    )

    await attribute_guide.finish(message_add_head(content, event))


# 完整面板命令
complete_profile = on_command("完整面板", block=True, priority=5)


@complete_profile.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    """查看完整面板（包含战力信息和注册时间）"""
    # 解析参数：如果提供了 UID，则查询对应玩家面板
    arg_text = args.extract_plain_text().strip()
    target_uid: int | None = None
    if arg_text:
        try:
            target_uid = int(arg_text)
        except ValueError:
            await complete_profile.finish("⛔ UID 必须为数字")

    # 使用UnitOfWork统一所有查询，确保事务原子性
    async with UnitOfWork(AsyncSessionLocal) as uow:
        # 1. 获取玩家
        if target_uid is not None:
            stmt = select(Player).where(Player.uid == target_uid)
            result = await uow.session.execute(stmt)
            player = result.scalars().first()
            if not player:
                await complete_profile.finish("⛔ 未找到该 UID")
        else:
            # 使用跨平台工具获取玩家数据
            player = await get_unified_player(uow.session, event)

        if not player:
            if is_guild_message(event):
                await complete_profile.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await complete_profile.finish("⛔ 你还没有创建角色")

        # 2. 更新坐标（若在自动导航）
        player_upd = await uow.session.get(Player, player.id)
        task = await uow.session.get(NavigationTask, player.id)
        if player_upd and task:
            reached = await _update_nav_position(player_upd, task, uow.session)
            if reached:
                await uow.session.delete(task)
            await uow.commit()  # 立即提交导航更新
            # 同步内存对象用于展示
            if not player.is_in_dungeon():
                player.x = player_upd.x
                player.y = player_upd.y
            # 始终同步现实世界坐标
            if hasattr(player, "real_world_x"):
                player.real_world_x = player_upd.real_world_x
                player.real_world_y = player_upd.real_world_y

        # 3. 获取有效属性（使用AttributeCalculator v2）
        effective_attrs = await get_effective_attributes_v2(player, uow.session)

        # 4. 统计装备加成用于显示
        bonus = defaultdict(int)
        equip_ids = config.items_config["by_type"]["EQUIPMENT"]
        eq_stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(equip_ids)
        )
        equiped_list = (await uow.session.execute(eq_stmt)).scalars().all()
        for eq in equiped_list:
            delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
            for k, v in delta.items():
                bonus[k] += int(v)

        # 5. 获取公会信息
        guild_name = "无所属"
        if player.guild_id:
            g_obj = await uow.session.get(Guild, player.guild_id)
            if g_obj:
                guild_name = g_obj.name

        # 6. 获取战斗属性显示
        from ..battle.integration_helper import BattleIntegrationHelper
        battle_attr_display = await BattleIntegrationHelper.get_battle_attribute_display_async(player, uow.session)

        # 7. 检查是否有临时buff
        from ..models.temporary_buff import TemporaryBuff
        active_buffs = await TemporaryBuff.get_active_buffs(uow.session, player.id)

    # 8. 格式化属性显示
    def fmt(attr_key: str, effective_value: int):
        inc = bonus.get(attr_key, 0)
        return f"{effective_value} (+{inc})" if inc else str(effective_value)

    atk_str = fmt("attack", effective_attrs["attack"])
    def_str = fmt("defense", effective_attrs["defense"])
    agi_str = fmt("agility", effective_attrs["agility"])
    luk_str = fmt("luck", effective_attrs["luck"])
    hp_max_str = fmt("max_hp", effective_attrs["max_hp"])
    mp_max_str = fmt("max_mp", effective_attrs["max_mp"])

    # 若当前 HP/MP 超出新上限，则修正显示
    cur_hp = min(player.hp, effective_attrs["max_hp"])
    cur_mp = min(player.mp, effective_attrs["max_mp"])

    realm_name = realm_by_level_and_reincarnation(player.level, player.reincarnation_level)
    exp_max = calculate_level_up_exp(player.level)

    # 获取活动称号（如有）
    from ..event.knocker_event import KnockerEventService
    player_title = KnockerEventService.get_player_title(player)
    display_name_full = player.nickname  # 称号不再拼接到昵称，单独展示
    title_line_full = f"┃ 🏅称号 「{player_title}」\n" if player_title else ""

    # 9. 格式化注册时间
    created_at = player.created_at
    if created_at:
        created_str = created_at.strftime("%Y-%m-%d %H:%M")
        # 计算注册天数
        days_since_created = (datetime.now() - created_at).days
        created_info = f"{created_str} ({days_since_created}天)"
    else:
        created_info = "未知"

    # 10. 检查未读的留言板与私信状态
    has_world_unread, has_private_unread = await get_unread_message_status(player.id)
    unread_notice = ""
    notice_lines: list[str] = []
    if has_private_unread:
        notice_lines.append("📬 有新私信未读！输入【留言板 私信】查看")
    if has_world_unread:
        notice_lines.append("🗒️ 世界留言板有新内容！输入【留言板】查看")
    if notice_lines:
        unread_notice = "".join(f"\n┃{line}" for line in notice_lines)

    # 11. 组装完整面板内容
    content = (
        f"┏━━ 信息 ━━━━\n"
        f"┃{display_name_full}[UID:{player.uid}]「{player.sex}」\n"
        f"┃ Lv.{player.level} · {realm_name}\n"
        f"{title_line_full}"
        f"┃ Exp {player.exp}/{exp_max}\n"
        f"┃ 📅注册 {created_info}\n"
        "┣━━ 状态 ━━━━\n"
        f"┃ ❤️生命 {cur_hp}/{hp_max_str}\n"
        f"┃ 🧠理智 {cur_mp}/{mp_max_str}\n"
        f"┃ ⚔力 {atk_str}   🛡防 {def_str}\n"
        f"┃ 👟敏 {agi_str}   🍀运 {luk_str}\n"
        f"┃ 🔮咒抗 {player.stamina}\n"
        "┣━━ 战斗属性 ━━\n"
    )

    # 12. 添加战斗属性（去除第一行的"战斗属性："标题，因为已在面板中显示）
    battle_lines = battle_attr_display.strip().split('\n')
    # 跳过战斗属性的标题行，只保留具体属性行
    for line in battle_lines[1:]:  # 跳过第一行"战斗属性："
        if line.strip():
            content += f"┃ {line.strip()}\n"

    # 13. 添加其他信息
    content += (
        "┣━━ 其他 ━━━━\n"
        f"┃ 🪙金币 {player.gold}  💎积分 {player.gold2}\n"
        f"┃ 🕯️诡烛 {player.gui_zhu}\n"
        f"┃ 💀怨念 {player.resentment} ✨点数 {player.attribute_points}\n"
        f"┃ ☯公会 {guild_name}\n"
        f"┃ 📍位置 {_format_player_location(player)}\n"
    )

    # 14. 添加Buff状态提示
    if active_buffs:
        content += f"┃ ✨增益 {len(active_buffs)}个 (输入【增益状态】查看)\n"

    content += f"┣━━━━━━━━━\n"
    content += f"┃☞【装备栏】【社交系统】{unread_notice}"

    # 15. 检查新手任务（仅检查自己的面板，不检查查询他人）
    if target_uid is None:
        from ..quest.novice_quest_service import NoviceQuestService
        quest_completed, quest_msg = await NoviceQuestService.check_and_advance_quest(
            uow.session, player, "command", {"command": "完整面板"}
        )

        if quest_completed and quest_msg:
            content += f"\n\n{quest_msg}"

    # 16. 使用平台格式化工具
    formatted_content = format_platform_message(content, event)
    await complete_profile.finish(message_add_head(formatted_content, event))
