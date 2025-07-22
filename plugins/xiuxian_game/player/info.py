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
    "噬神境",
]

REALM_THRESHOLDS = [20, 40, 60, 80, 100, 130, 160, 190, 250, 300, 500]

def realm_by_level(level: int) -> str:
    """根据等级返回境界名称"""
    for idx, cap in enumerate(REALM_THRESHOLDS):
        if level <= cap:
            return REALM_NAMES[idx]
    return REALM_NAMES[-1] + "+"

profile = on_command("角色",aliases={"面板","状态"}, block=True, priority=5)
register = on_command("注册", block=True, priority=5)
change_gender = on_command("改性别", aliases={"修改性别"}, block=True, priority=5)


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
            player = await session.get(Player, event.get_user_id())
    if not player:
        await profile.finish("⛔ 你还没有创建角色")

    # -------- 更新坐标（若在自动导航） --------
    async with safe_session() as session_nav:
        task = await session_nav.get(NavigationTask, player.id)
        if task:
            reached = _update_nav_position(player, task)
            if reached:
                await session_nav.delete(task)
            await session_nav.commit()

    # ------- 统计装备加成 -------
    bonus = defaultdict(int)
    async with safe_session() as session2:
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

    # 读取属性并拼接加成
    def fmt(attr_key: str, value: int):
        inc = bonus.get(attr_key, 0)
        return f"{value} (+{inc})" if inc else str(value)

    atk_str = fmt("attack", player.attack)
    def_str = fmt("defense", player.defense)
    agi_str = fmt("agility", player.agility)
    luk_str = fmt("luck", player.luck)
    hp_max_str = fmt("max_hp", player.max_hp)
    mp_max_str = fmt("max_mp", player.max_mp)

    # 若当前 HP/MP 超出新上限，则修正显示
    cur_hp = player.hp
    cur_mp = player.mp

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

    content = (
        f"┏━━ 信息 ━━━━\n"
        f"┃{player.nickname}[UID:{player.uid}]「{player.sex}」\n"
        f"┃ Lv.{player.level} · {realm_name}\n"
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
        f"┃ 📍位置 {player.region} ({player.x},{player.y})\n"
        "┣━━━━━━━━━\n"
        f"┃☞【装备栏】【社交系统】{unread_notice}"
    )
    await profile.finish(message_add_head(content, event))

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

    # 如果直接提供了昵称，直接创建角色（默认性别为男）
    if nickname:
        # 直接创建角色，默认性别为男
        result = await create_player(event, nickname, Gender.MALE)
        await register.finish(message_add_head(result, event))

    # 开始分步注册流程，保存用户ID到状态中
    state["user_id"] = event.get_user_id()


@register.got("nickname", prompt="🀄️ 新人指引  ──────────\n✨ 欢迎来到诡修仙世界！\n👤 请输入你的角色昵称（直接发名字，不要带多余的字，请谨慎对待）：")
async def _(event: MessageEvent, nickname: str = ArgPlainText()):
    if not nickname.strip():
        await register.reject("⛔ 昵称不能为空，请重新输入")

    # 创建角色，默认性别为男
    result = await create_player(event, nickname.strip(), Gender.MALE)
    await register.finish(message_add_head(result, event))


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
            "⬇️ 【修炼】割下第一缕血丝\n"
            "⬇️ 【面板】窥视自己的残骸\n"
            "⬇️ 【改性别 女】女孩子？\n"
            "⬇️ 【签到】领取新手礼包\n"
            "💡 注意【】括号里的才是指令，外面是指令说明！！！\n"
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
        player = await session.get(Player, event.get_user_id())
        if not player:
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
