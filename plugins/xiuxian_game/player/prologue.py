"""新手序章：注册后 60 秒内的首段怪谈体验。

流程：注册成功卡【睁开眼】→ 遭遇食殓者【反抗/装死】→ 必胜首战 →
奖励（白骨护甲+首次突破经验+金币）→ 按钮接入签到/突破/新手任务。
一次性剧情，prologue_step 记进度（0未开始/1已睁眼/2已完成），可重入不可重刷。
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from sqlalchemy import update

from ..models.db import safe_session
from ..infrastructure.locking import lock_row
from ..models.inventory import ItemInstance
from ..models.player import Player
from ..platform_utils import require_player
from ..utils import calculate_level_up_exp
from ..utils_markdown import build_markdown, cmd

PROLOGUE_GOLD = 500
PROLOGUE_ARMOR_ID = "bone_armor"

# 按钮 data 必须是纯指令文本，emoji 只能放 label（keyboard() 的 data 会原样作为消息发出）
OPEN_EYES_BUTTONS = [[("🤜 反抗", "反抗"), ("🪦 装死", "装死")], [("新手任务", "新手任务")]]
FINISH_BUTTONS = [[("首次突破", "突破")], [("新手任务", "新手任务")]]


def build_onboarding_resume(player: Player, intro: str = ""):
    """仅根据已有角色状态提供入口，不修改进度或补发奖励。"""
    if player.prologue_step == 0:
        hint = f"继续 {cmd('睁开眼')}，接上序章。"
        buttons = [[("睁开眼", "睁开眼")]]
    elif player.prologue_step == 1:
        hint = f"食殓者还在眼前，点击 {cmd('反抗')} 或 {cmd('装死')}。"
        buttons = [[("反抗", "反抗"), ("装死", "装死")]]
    elif player.level == 1:
        hint = f"序章奖励已领取。点击 {cmd('突破')}，完成首次突破。"
        buttons = [[("首次突破", "突破")]]
    elif player.attribute_points > 0:
        points = min(5, player.attribute_points)
        command = f"加点 力 {points}"
        hint = f"你有 {player.attribute_points} 点属性可分配，可先 {cmd(command)}。"
        buttons = [[("分配属性", command)]]
    else:
        hint = f"点击 {cmd('面板')} 查看成长，再 {cmd('观察')} 周围。"
        buttons = [[("查看面板", "面板"), ("观察周围", "观察")]]
    buttons.append([("新手任务", "新手任务")])
    content = (
        f"{intro}当前角色：**{player.nickname}**（UID:{player.uid}）\n"
        f"{hint}\n"
        f"> {cmd('新手任务')} 可找回下一步。"
    )
    return build_markdown(content, buttons=buttons, button_enter=True)

open_eyes = on_command("睁开眼", priority=5, block=True)
fight_back = on_command("反抗", priority=5, block=True)
play_dead = on_command("装死", priority=5, block=True)


@open_eyes.handle()
async def handle_open_eyes(event: MessageEvent):
    async with safe_session() as session:
        player = await require_player(session, event, open_eyes)

        if player.prologue_step >= 2:
            await open_eyes.finish(build_onboarding_resume(
                player, "🌑 你早已睁开过眼。那间殓房的门，不会再为你打开。\n"
            ))

        if player.prologue_step == 0:
            player.prologue_step = 1

        content = (
            "# 👁️ 你睁开眼\n"
            "殓房的白炽灯管闪了三下，灭了。\n"
            "你听见心跳声。不对——是**两个**心跳。\n"
            "***\n"
            "一张灰白的脸从棺沿探进来。它没有眼睛，鼻孔一张一合，正嗅着你。\n"
            "**食殓者**。守尸人最怕的东西，专挑刚醒过来的下手。\n"
            "它咧开嘴。\n"
            "***\n"
            "👇 你只有一次机会"
        )
        await open_eyes.finish(build_markdown(content, buttons=OPEN_EYES_BUTTONS, button_enter=True))


async def _finish_prologue(matcher, event: MessageEvent, intro: str):
    async with safe_session() as session:
        player = await require_player(session, event, matcher)
        player = await lock_row(session, Player, player.id)

        if player.prologue_step >= 2:
            await matcher.finish(build_onboarding_resume(
                player, "🌑 它早就退回黑暗里了。地上的刮痕还在。\n"
            ))
        if player.prologue_step == 0:
            await matcher.finish(build_markdown(
                f"四下无声，还没有需要反抗的东西。先 {cmd('睁开眼')} 看看。",
                buttons=[[("睁开眼", "睁开眼")], [("新手任务", "新手任务")]],
                button_enter=True,
            ))

        # 原子置完成位：连点/并发时只有第一个请求发奖
        claimed = await session.execute(
            update(Player)
            .where(
                Player.id == player.id,
                Player.prologue_step == 1,
                Player.version_id == player.version_id,
            )
            .values(prologue_step=2, version_id=Player.version_id + 1)
            .execution_options(autoflush=False)
        )
        if claimed.rowcount == 0:
            await session.refresh(player)
            await matcher.finish(build_onboarding_resume(player))
        player.prologue_step = 2

        exp_gain = calculate_level_up_exp(1, player.server_id)
        player.exp += exp_gain
        player.gold += PROLOGUE_GOLD
        await ItemInstance.add_item(session, player.id, PROLOGUE_ARMOR_ID, 1)

        breakthrough_hint = "（正好够第一次突破）" if player.level == 1 else ""

        content = (
            f"{intro}"
            "你抡过去。骨头砸进那张脸，像砸进一团湿棉花。\n"
            "食殓者发出婴儿般的啼哭，缩回黑暗，指甲在地上刮出一串火星。\n"
            "它退走了。这种东西杀不死——但它记住了，你不好惹。\n"
            "***\n"
            "🎁 **战利品**\n"
            "🦴 白骨护甲 ×1（那根骨头上还挂着别的碎骨，拼一拼正好）\n"
            f"✨ 经验 +{exp_gain}{breakthrough_hint}\n"
            f"💰 金币 +{PROLOGUE_GOLD}\n"
            "***\n"
            "**接下来只做一件事**\n"
            f"点击 {cmd('突破')}，用刚获得的经验完成首次突破。\n"
            f"然后 {cmd('加点')} → {cmd('面板')} → {cmd('观察')}。\n"
            f"> {cmd('新手任务')} 可随时找回下一步。"
        )
        await session.commit()
        await matcher.finish(build_markdown(content, buttons=FINISH_BUTTONS, button_enter=True))


@fight_back.handle()
async def handle_fight_back(event: MessageEvent):
    intro = (
        "# 🩸 你抄起了手边的东西\n"
        "一根白骨。不知道是谁的，够长，也够硬。\n"
        "***\n"
    )
    await _finish_prologue(fight_back, event, intro)


@play_dead.handle()
async def handle_play_dead(event: MessageEvent):
    intro = (
        "# 🪦 你屏住呼吸，装死\n"
        "它凑得更近，鼻息喷在你脸上，像化开的冻肉。\n"
        "一秒。两秒。它忽然张嘴咬向你的肩膀——**死人不会出汗，你会。**\n"
        "求生的本能炸开，你摸到手边一根白骨——\n"
        "***\n"
    )
    await _finish_prologue(play_dead, event, intro)
