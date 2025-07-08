from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.qq import MessageEvent, Message
from ..models.db import safe_session
from ..models.player import Player
from sqlalchemy import select, func
from ..models.player import Gender
from ..utils import message_add_head, calculate_level_up_exp
from datetime import datetime
from ..models.equipment import EquipmentInstance
from collections import defaultdict
from ..models.guild import Guild
import random

# 每10级对应一个境界，诡异修仙风格
# 境界名称与等级区间映射（10,10,20,20,20,20,30,30,30,50 累积）
REALM_NAMES = [
    "腐体境",  # 1-10
    "血咒境",  # 11-20
    "怨魂境",  # 21-40
    "阴祟境",  # 41-60
    "鬼啸境",  # 61-80
    "恐魇境",  # 81-100
    "噬神境",  # 101-130
    "诡天境",  # 131-160
    "灾厄境",  # 161-190
    "绝念境",  # 191-240
]

REALM_THRESHOLDS = [10, 20, 40, 60, 80, 100, 130, 160, 190, 240]

def realm_by_level(level: int) -> str:
    """根据等级返回境界名称"""
    for idx, cap in enumerate(REALM_THRESHOLDS):
        if level <= cap:
            return REALM_NAMES[idx]
    return REALM_NAMES[-1] + "+"

profile = on_command("角色",aliases={"面板","状态"}, block=True, priority=5)
register = on_command("注册", block=True, priority=5)


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
    
    # ------- 统计装备加成 -------
    bonus = defaultdict(int)
    async with safe_session() as session2:
        from sqlalchemy import select as sel
        eq_stmt = sel(EquipmentInstance).where(
            EquipmentInstance.player_id == player.id,
            EquipmentInstance.equipped == True
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

    content = f"""
┌─── 诡修面板 ───
│ {player.nickname}[UID:{player.uid}]「{player.sex}」
│ Lv.{player.level}『{realm_name}』
├───────────
│ 经验：{player.exp}/{calculate_level_up_exp(player.level)} ⚡
│ 生命：{cur_hp}/{hp_max_str} ❤️
│ 理智：{cur_mp}/{mp_max_str} 🧠
│ 公会：{guild_name} ☯
│ 位置：{player.region} ({player.x},{player.y}) 
├──【属性】──
│ ⚔力 {atk_str}  🛡防 {def_str} 
│ 👟敏 {agi_str}  🍀运 {luk_str}
├──【资源】──
│ 金币：{player.gold}  | 点数：{player.attribute_points}✨
│ 积分：{player.gold2}  | 怨念：{player.resentment} 💀
└───────────
"""
    await profile.finish(content)

@register.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    params = args.extract_plain_text().strip().split()
    if len(params) < 2:
        await register.finish(
            message_add_head(
                "🀄️ 新人指引  ──────────\n"
                "> 注册格式:【注册 [昵称] [性别]】\n"
                "> 示       例: 注册 道爷 男\n"
                "> 性别可选: 男 / 女\n"
                "💡 后续所有指令都可省略斜杠",
                event)
            )
    nickname, gender = params[0], params[1]
    try:
        gender = Gender(gender)
    except ValueError:
        await register.finish(f"⛔ 无效的性别，可选：{Gender.MALE.value}/{Gender.FEMALE.value}")

    async with safe_session() as session:
        # 检查是否已有角色
        result = await session.execute(
            select(Player).where(Player.id == event.get_user_id())
        )
        if result.scalars().first():
            await register.finish("⛔ 你已经创建过角色了")
        
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
            "💡 更多指令请输入【帮助】"
        )
        await register.finish(message_add_head(content, event))