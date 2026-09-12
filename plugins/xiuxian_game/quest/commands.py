from nonebot import on_command
from nonebot.adapters.qq import MessageEvent

from ..models.db import safe_session
from ..platform_utils import require_player
from ..utils_markdown import build_markdown, cmd
from .novice_quest_service import NoviceQuestService


novice_quest_cmd = on_command("新手任务", aliases={"新手进度"}, block=True, priority=5)


@novice_quest_cmd.handle()
async def handle_novice_quest(event: MessageEvent):
    async with safe_session() as session:
        player = await require_player(session, event, novice_quest_cmd)
        _, message = await NoviceQuestService.check_and_advance_quest(
            session, player, "state"
        )
        if message is None:
            message = f"当前没有待完成的新手任务。\n{cmd('新手任务帮助')} | {cmd('帮助')}"
        await novice_quest_cmd.finish(build_markdown(message))
