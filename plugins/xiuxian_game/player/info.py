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
    
    # 读取已穿戴装备，计算最终属性
    atk_str = str(player.attack)
    def_str = str(player.defense)
    agi_str = str(player.agility)
    luk_str = str(player.luck)
    hp_max_str = str(player.max_hp)
    mp_max_str = str(player.max_mp)

    # 若当前 HP/MP 超出新上限，则修正显示
    cur_hp = player.hp
    cur_mp = player.mp

    content = f"""
┌─── 诡修面板 ───
│ {player.nickname}[UID:{player.uid}]「{player.sex}」
├───────────
│ Lv.{player.level} Exp：{player.exp}/{calculate_level_up_exp(player.level)}
│ 生命：{cur_hp}/{hp_max_str} ❤️
│ 理智：{cur_mp}/{mp_max_str} 🧠
│ 位置：{player.region} ({player.x},{player.y}) 
├──【属性】──
│ ⚔力 {atk_str}  🛡防 {def_str} 
│ 👟敏 {agi_str}  🍀运 {luk_str}
├──【资源】──
│ 金币：{player.gold}  | 点数：{player.attribute_points}✨
│ 怨念：{player.resentment}
└───────────
"""
    await profile.finish(message_add_head(content, event))

@register.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    params = args.extract_plain_text().strip().split()
    if len(params) < 2:
        await register.finish("⛔ 请输入道号和性别，例如：/注册 道爷 男")

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

        content = f"""
        😇恭喜你踏上诡修之路！
道号：{nickname}[UID:{new_player.uid}]「{new_player.sex.value}」
        """
        await register.finish(message_add_head(content, event))