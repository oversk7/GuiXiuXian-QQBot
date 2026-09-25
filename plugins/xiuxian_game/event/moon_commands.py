"""月蚀祭指令。业务规则集中在 moon_festival.py。"""

from nonebot import on_command
from nonebot.adapters.qq import Message, MessageEvent
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from ..models.db import safe_session
from ..platform_utils import require_player
from ..utils import message_add_head
from .moon_festival import MoonFestivalService


status_cmd = on_command("月蚀祭", aliases={"中秋活动"}, priority=13, block=True)
challenge_cmd = on_command("守月", priority=13, block=True)
shop_cmd = on_command("月华商店", priority=13, block=True)
start_cmd = on_command("开启月蚀祭", priority=4, block=True, permission=SUPERUSER)
stop_cmd = on_command("关闭月蚀祭", priority=4, block=True, permission=SUPERUSER)


@status_cmd.handle()
async def show_status(event: MessageEvent):
    async with safe_session() as session:
        player = await require_player(session, event, status_cmd)
        text = MoonFestivalService.status(player)
    await status_cmd.finish(message_add_head(text, event))


@challenge_cmd.handle()
async def challenge(event: MessageEvent):
    async with safe_session() as session:
        player = await require_player(session, event, challenge_cmd)
        text = await MoonFestivalService.challenge(session, player)
    await challenge_cmd.finish(message_add_head(text, event))


@shop_cmd.handle()
async def shop(event: MessageEvent, args: Message = CommandArg()):
    argument = args.extract_plain_text().strip()
    if argument.startswith("兑换"):
        product = argument[2:].strip()
        if not product:
            await shop_cmd.finish("用法：月华商店 兑换 物品名 [数量]")
        parts = product.rsplit(" ", 1)
        name, quantity = (parts[0].strip(), int(parts[1])) if len(parts) == 2 and parts[1].isdigit() else (product, 1)
        async with safe_session() as session:
            player = await require_player(session, event, shop_cmd)
            text = await MoonFestivalService.buy(session, player, name, quantity)
    else:
        async with safe_session() as session:
            player = await require_player(session, event, shop_cmd)
            text = MoonFestivalService.shop(player)
    await shop_cmd.finish(message_add_head(text, event))


@start_cmd.handle()
async def start_event():
    await start_cmd.finish(MoonFestivalService.start())


@stop_cmd.handle()
async def stop_event():
    await stop_cmd.finish(MoonFestivalService.stop())
