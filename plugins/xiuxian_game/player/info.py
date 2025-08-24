from nonebot import on_command
from nonebot.params import CommandArg, ArgPlainText
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.typing import T_State
from ..models.db import safe_session
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
from ..platform_utils import get_unified_player, get_player_platform_display, format_platform_message, is_guild_message
from ..config import config


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
from ..world.message_board import has_unread_messages

REALM_NAMES = [
    "凡人",
    "腐体境",
    "血咒境",
    "怨魂境",
    "阴祟境",
    "鬼啸境",
    "恐魇境",
    "绝念境",
    "诡天境",
    "灾厄境",
]

REALM_THRESHOLDS = [20, 40, 60, 80, 100, 130, 160, 190, 250, 300]

def number_to_chinese(num: int) -> str:
    """将阿拉伯数字转换为中文数字"""
    if num == 0:
        return "零"

    # 中文数字映射
    chinese_digits = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]

    if num < 10:
        return chinese_digits[num]
    elif num < 20:
        if num == 10:
            return "十"
        else:
            return "十" + chinese_digits[num % 10]
    elif num < 100:
        tens = num // 10
        ones = num % 10
        if ones == 0:
            return chinese_digits[tens] + "十"
        else:
            return chinese_digits[tens] + "十" + chinese_digits[ones]
    elif num < 1000:
        hundreds = num // 100
        remainder = num % 100
        result = chinese_digits[hundreds] + "百"
        if remainder == 0:
            return result
        elif remainder < 10:
            return result + "零" + chinese_digits[remainder]
        else:
            return result + number_to_chinese(remainder)
    elif num < 10000:
        thousands = num // 1000
        remainder = num % 1000
        result = chinese_digits[thousands] + "千"
        if remainder == 0:
            return result
        elif remainder < 100:
            return result + "零" + number_to_chinese(remainder)
        else:
            return result + number_to_chinese(remainder)
    else:
        # 处理万以上的数字
        wan = num // 10000
        remainder = num % 10000
        result = number_to_chinese(wan) + "万"
        if remainder == 0:
            return result
        elif remainder < 1000:
            return result + "零" + number_to_chinese(remainder)
        else:
            return result + number_to_chinese(remainder)

def realm_by_level(level: int) -> str:
    """根据等级返回境界名称"""
    for idx, cap in enumerate(REALM_THRESHOLDS):
        if level <= cap:
            return REALM_NAMES[idx]
    return REALM_NAMES[-1] + "+"

profile = on_command("角色",aliases={"面板","状态"}, block=True, priority=5)
register = on_command("注册", block=True, priority=5)
change_gender = on_command("改性别", aliases={"修改性别"}, block=True, priority=5)
newbie_guide = on_command("新手指引", aliases={"指令格式", "指令帮助", "新手教程"}, block=True, priority=5)
attribute_guide = on_command("加点帮助", aliases={"属性帮助", "加点指南", "属性说明"}, block=True, priority=5)


@profile.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    async with safe_session() as session:
        arg_text = args.extract_plain_text().strip()
        # 如果提供了 UID，则查询对应玩家面板
        target_uid: int | None = None
        if arg_text:
            try:
                target_uid = int(arg_text)
            except ValueError:
                await profile.finish("⛔ UID 必须为数字")

        if target_uid is not None:
            stmt = select(Player).where(Player.uid == target_uid)
            result = await session.execute(stmt)
            player = result.scalars().first()
            if not player:
                await profile.finish("⛔ 未找到该 UID")
        else:
            # 使用跨平台工具获取玩家数据
            player = await get_unified_player(session, event)
    if not player:
        if is_guild_message(event):
            await profile.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
        else:
            await profile.finish("⛔ 你还没有创建角色")

    # -------- 更新坐标（若在自动导航） --------
    async with safe_session() as session_nav:
        player_upd = await session_nav.get(Player, player.id)
        task = await session_nav.get(NavigationTask, player.id)
        if player_upd and task:
            reached = await _update_nav_position(player_upd, task, session_nav)
            if reached:
                await session_nav.delete(task)
            await session_nav.commit()
            # 同步内存对象用于展示
            # 只有在现实世界时才同步x,y坐标，在副本中保持副本坐标
            if not player.is_in_dungeon():
                player.x = player_upd.x
                player.y = player_upd.y
            # 始终同步现实世界坐标
            if hasattr(player, "real_world_x"):
                player.real_world_x = player_upd.real_world_x
                player.real_world_y = player_upd.real_world_y

    # ------- 获取包含临时buff的有效属性 -------
    async with safe_session() as session2:
        # 获取有效属性（包含装备、丹药和临时buff加成）
        effective_attrs = await player.get_effective_attributes(session2)

        # 统计装备加成用于显示
        bonus = defaultdict(int)
        from sqlalchemy import select as sel
        equip_ids = config.items_config["by_type"]["EQUIPMENT"]
        eq_stmt = sel(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(equip_ids)
        )
        equiped_list = (await session2.execute(eq_stmt)).scalars().all()
        for eq in equiped_list:
            delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
            for k, v in delta.items():
                bonus[k] += int(v)

    # 读取有效属性并拼接装备加成显示
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

    # 公会名称
    guild_name = "无所属"
    if player.guild_id:
        async with safe_session() as session_g:
            g_obj = await session_g.get(Guild, player.guild_id)
            if g_obj:
                guild_name = g_obj.name

    realm_name = realm_by_level(player.level)

    exp_max = calculate_level_up_exp(player.level)

    # 检查是否有未读留言
    has_unread = await has_unread_messages(player.id)
    unread_notice = ""
    if has_unread:
        unread_notice = "\n┃📬 有新留言未读！输入【留言板】查看"

    # 转数信息（只有冥返过才显示）
    reincarnation_info = ""
    if player.reincarnation_level > 0:
        chinese_reincarnation = number_to_chinese(player.reincarnation_level)
        reincarnation_info = f" · {chinese_reincarnation}转"

    # 获取平台显示信息
    async with safe_session() as session_platform:
        platform_info = await get_player_platform_display(session_platform, player)

    content = (
        f"┏━━ 信息 ━━━━\n"
        f"┃{player.nickname}[UID:{player.uid}]「{player.sex}」\n"
        f"┃ Lv.{player.level}{reincarnation_info} · {realm_name}\n"
        f"┃ Exp {player.exp}/{exp_max}\n"
        "┣━━ 状态 ━━━━\n"
        f"┃ ❤️生命 {cur_hp}/{hp_max_str}\n"
        f"┃ 🧠理智 {cur_mp}/{mp_max_str}\n"
        f"┃ ⚔力 {atk_str}   🛡防 {def_str}\n"
        f"┃ 👟敏 {agi_str}   🍀运 {luk_str}\n"
        f"┃ 🔮咒抗 {player.stamina}\n"
        "┣━━ 其他 ━━━━\n"
        f"┃ 🪙金币 {player.gold}\n"
        f"┃ 💀怨念 {player.resentment} ✨点数 {player.attribute_points}\n"
        f"┃ ☯公会 {guild_name}\n"
        f"┃ 📍位置 {_format_player_location(player)}\n"
        f"┃ 🌐平台 {platform_info}\n"
        "┣━━━━━━━━━\n"
        f"┃☞【装备栏】【社交系统】{unread_notice}"
    )
    # 使用平台格式化工具
    formatted_content = format_platform_message(content, event)
    await profile.finish(message_add_head(formatted_content, event))

@register.handle()
async def _(event: MessageEvent, state: T_State, args: Message = CommandArg()):
    # 检查是否已有角色
    async with safe_session() as session:
        result = await session.execute(
            select(Player).where(Player.id == event.get_user_id())
        )
        if result.scalars().first():
            await register.finish("⛔ 你已经创建过角色了")

    # 获取参数
    nickname = args.extract_plain_text().strip()

    # 如果直接提供了昵称，直接创建角色
    if nickname:
        # 检查是否为旧格式：昵称 性别
        parsed_nickname, parsed_gender = _parse_nickname_and_gender(nickname)

        # 清理可能的误输入
        cleaned_nickname = _clean_nickname_input(parsed_nickname)

        # 检查清理后的昵称是否有效
        if not cleaned_nickname or len(cleaned_nickname) < 2:
            await register.finish(
                "⛔ 昵称格式错误\n"
                "💡 正确格式：/注册 [昵称] 或 /注册 [昵称] [男/女] 或直接发送 /注册 然后按提示输入\n"
                "📝 例如：/注册 张三 或 /注册 张三 女\n"
                "⚠️ 昵称长度至少2个字符"
            )

        # 如果清理了输入，给出提示
        if cleaned_nickname != parsed_nickname:
            result = await create_player(event, cleaned_nickname, parsed_gender)
            success_msg = f"✅ 已自动识别并清理输入，你的角色昵称为：{cleaned_nickname}，性别：{parsed_gender.value}\n{result}"
            await register.finish(message_add_head(success_msg, event))
        else:
            # 正常情况，直接创建角色
            result = await create_player(event, cleaned_nickname, parsed_gender)
            # 如果检测到了性别参数，给出提示
            if parsed_gender != Gender.MALE or ' ' in nickname:
                success_msg = f"✅ 角色创建成功！昵称：{cleaned_nickname}，性别：{parsed_gender.value}\n{result}"
                await register.finish(message_add_head(success_msg, event))
            else:
                await register.finish(message_add_head(result, event))

    # 开始分步注册流程，保存用户ID到状态中
    state["user_id"] = event.get_user_id()


@register.got("nickname", prompt="🀄️ 新人指引  ──────────\n✨ 欢迎来到诡修仙世界！\n👤 请输入你的角色昵称（直接发名字，不要带多余的字，请谨慎对待）：")
async def _(event: MessageEvent, nickname: str = ArgPlainText()):
    nickname = nickname.strip()

    if not nickname or nickname in ["修炼"]:
        await register.reject("⛔ 昵称不能为空或者是指令，请重新输入")

    # 检查并处理常见的误输入情况
    cleaned_nickname = _clean_nickname_input(nickname)
    if cleaned_nickname != nickname:
        # 如果清理后的昵称为空或过短，提示重新输入
        if not cleaned_nickname or len(cleaned_nickname) < 2:
            await register.reject(
                "⛔ 检测到你可能误输入了指令前缀\n"
                "💡 请只输入角色昵称，不要包含 /注册 等指令前缀\n"
                "📝 例如：直接输入「张三」而不是「/注册 张三」\n"
                "🔄 请重新输入你的角色昵称："
            )
        else:
            # 提示用户我们已经自动清理了输入
            result = await create_player(event, cleaned_nickname, Gender.MALE)
            success_msg = f"✅ 已自动识别并清理输入，你的角色昵称为：{cleaned_nickname}\n{result}"
            await register.finish(message_add_head(success_msg, event))

    # 正常情况，直接创建角色
    result = await create_player(event, nickname, Gender.MALE)
    await register.finish(message_add_head(result, event))


def _parse_nickname_and_gender(input_text: str) -> tuple[str, Gender]:
    """解析输入文本，分离昵称和性别

    支持格式：
    - "昵称 男" -> ("昵称", Gender.MALE)
    - "昵称 女" -> ("昵称", Gender.FEMALE)
    - "昵称" -> ("昵称", Gender.MALE)  # 默认男性

    Args:
        input_text: 用户输入的文本

    Returns:
        tuple: (昵称, 性别)
    """
    input_text = input_text.strip()

    # 检查是否包含空格
    if ' ' in input_text:
        parts = input_text.split()
        if len(parts) >= 2:
            # 最后一个部分可能是性别
            potential_gender = parts[-1]
            if potential_gender in ['男', '女']:
                # 昵称是除了最后一个部分的所有内容
                nickname = ' '.join(parts[:-1])
                gender = Gender.MALE if potential_gender == '男' else Gender.FEMALE
                return nickname, gender

    # 如果没有检测到性别，返回原文本和默认性别
    return input_text, Gender.MALE


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


async def create_player(event: MessageEvent, nickname: str, gender: Gender) -> str:
    """创建新玩家角色，返回成功消息"""
    async with safe_session() as session:
        # 再次检查是否已有角色（防止在会话过程中创建）
        result = await session.execute(
            select(Player).where(Player.id == event.get_user_id())
        )
        if result.scalars().first():
            return "⛔ 你已经创建过角色了"

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
        card_type = random.choice(('🎲','🀄️','🀃','🀅','🀆','🀀','🀁','🀂','🀒','🀚','🀣'))
        content = (
            "⚰️ 棺盖移位，黑暗替你呼吸——欢迎回到人间。\n"
            "━━━━━━━━━━━━━\n"
            f"┌── 🃏新牌出世🃏 ──┐\n"
            f"🪬 道号  : {card_type}{nickname}\n"
            f"🆔 UID   : {new_player.uid}\n"
            f"⚧️ 性别  : {new_player.sex.value}\n"
            "━━━━━━━━━━━━━\n"
            "🔰 新手必读 - 指令格式说明：\n"
            "💡 【】括号里的才是指令，外面是指令说明！\n"
            "💡 括号不要一起发出来，有的空格不能少！\n"
            "💡 例如'加点 力 5'表示给力量属性加5点\n"
            "━━━━━━━━━━━━━\n"
            "⬇️ 【修炼】割下第一缕血丝\n"
            "⬇️ 【面板】窥视自己的残骸\n"
            "⬇️ 【加点帮助】了解属性加点\n"
            "⬇️ 【改性别 女】女孩子？\n"
            "⬇️ 【签到】领取新手礼包\n"
            "⬇️ 【新手指引】还不会用指令？\n"
            "💡 更多指令请输入【帮助】"
        )
        return content


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

        await change_gender.finish(message_add_head(
            f"✨ 性别修改成功！\n"
            f"🔄 {old_gender} → {gender.value}\n"
            f"👤 {player.nickname}[UID:{player.uid}]",
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
        "🔰 新手指引 - 指令格式详解\n"
        "━━━━━━━━━━━━━\n"
        "📖 基础知识：\n"
        "• 【】方括号里的是指令名称\n"
        "• <> 尖括号表示必填参数\n"
        "• [] 方括号表示选填参数\n"
        "• 指令和参数之间用空格分隔\n"
        "\n"
        "🎯 常见错误示例：\n"
        "❌ 加点运5 (缺少空格)\n"
        "❌ 加点［属性］［点数］加点运5 (照抄帮助格式)\n"
        "❌ 加点[属性运][点数5] (照抄帮助格式)\n"
        "❌ 【加点 运 5】(不要输入方括号)\n"
        "\n"
        "✅ 正确示例：\n"
        "✅ 加点 运 5 (给运气加5点)\n"
        "✅ 加点 力 3 (给力量加3点)\n"
        "✅ 面板 560 (查看UID为560的玩家)\n"
        "✅ 面板 (查看自己的面板)\n"
        "\n"
        "🎮 实战练习：\n"
        "现在试试发送：加点 智 1\n"
        "如果你有属性点的话，这会给你的理智+1\n"
        "\n"
        "💡 记住：看到帮助文档中的【指令 <参数>】格式时\n"
        "只需要输入：指令 参数值 (中间用空格分开)\n"
        "\n"
        "🆘 如果还是不会，可以：\n"
        "• 发送【加点帮助】查看属性加点指南\n"
        "• 发送【修炼系统】查看修炼相关指令\n"
        "• 发送【帮助】查看所有系统\n"
        "• 加入官群：962494679 询问其他玩家"
    )

    await newbie_guide.finish(message_add_head(content, event))


@attribute_guide.handle()
async def _(event: MessageEvent):
    """加点帮助 - 详细说明各个属性的作用和推荐加点方案"""

    # 检查是否已有角色
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await attribute_guide.finish("⛔ 请先创建角色，发送【注册】开始游戏")

    content = (
        "🔮 加点帮助 - 属性详解与推荐\n"
        "━━━━━━━━━━━━━\n"
        "📊 基础属性说明：\n"
        "\n"
        "🩸 体力 (体)：\n"
        "• 作用：增加生命值上限\n"
        "• 每点+1生命值上限\n"
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
