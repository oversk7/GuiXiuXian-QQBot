from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from ..data.db import safe_session
from ..models.player import Player
from sqlalchemy import select, func
from ..models.player import Gender

profile = on_command("角色", block=True, priority=5)
register = on_command("注册", block=True, priority=5)


@profile.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        result = await session.execute(
            select(Player).where(Player.id == event.get_user_id())
        )
        player = result.scalars().first()
    
    if not player:
        await profile.finish("⛔ 你还没有创建角色")
    
    content = f"""
┌─── 诡修面板 ───
│ {player.nickname}[UID:{player.uid}]「{player.sex}」
├───────────
│ Lv.{player.level} Exp：{player.exp}
│ 生命：{player.hp}/{player.max_hp} ❤️
│ 理智：{player.mp}/{player.max_mp} 🧠
│ 位置：{player.position} 
├──【属性】──
│ ⚔力 {player.attack}  🛡防 {player.defense}  👟敏 {player.agility}
│ 😱恐抗 {player.fear_resistance}  🍀幸运 {player.luck}
├──【资源】──
│ 金币：{player.gold}  | 属性点：{player.attribute_points}✨
└───────────
"""
    await profile.finish(content)

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
        max_uid = max_uid_result.scalar() or 100
        
        new_player = Player(
            id=event.get_user_id(),
            uid=max_uid + 1,
            nickname=nickname,
            sex=gender
        )
        
        session.add(new_player)
        await session.commit()

        content = f"""
        😇恭喜你踏上诡修之路！
        ▫️ 道号：{nickname}[UID:{new_player.uid}]「{new_player.sex}」
        """
        await register.finish(content)