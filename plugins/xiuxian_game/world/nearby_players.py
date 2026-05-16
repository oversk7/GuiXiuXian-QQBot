from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg

from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from ..player.realm_utils import realm_by_level_and_reincarnation
from ..platform_utils import get_unified_player

# ----------------- 指令：附近玩家 -----------------
# 查看当前区域距离自己最近的前 5 位玩家
nearby_cmd = on_command("附近玩家", aliases={"附近人"}, block=True, priority=5)


@nearby_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        # 获取当前玩家
        player: Player | None = await get_unified_player(session, event)
        if not player:
            await nearby_cmd.finish("⛔ 请先创建角色")

        # 查询同区域其他玩家
        stmt = select(Player).where(
            Player.region == player.region,
            Player.server_id == player.server_id,
            Player.id != player.id  # 排除自己
        )
        others = (await session.execute(stmt)).scalars().all()

        if not others:
            await nearby_cmd.finish(message_add_head("📭 附近暂无其他玩家", event))

        # 按曼哈顿距离排序 - 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        def _dist(p: Player) -> int:
            # 其他玩家也需要使用正确的坐标进行比较
            other_x, other_y = p.get_current_coordinates()
            return abs(other_x - current_x) + abs(other_y - current_y)

        others.sort(key=_dist)
        top5 = others[:5]

        # 使用境界映射函数

        # 构造回复 - 使用正确的当前坐标
        current_x, current_y = player.get_current_coordinates()
        current_region = player.get_current_region()
        header = f"📍 当前位置：{current_region} ({current_x},{current_y})"
        lines = [header, "🧑‍🤝‍🧑 附近玩家："]
        for idx, p in enumerate(top5, 1):
            gender_val = p.sex.value if hasattr(p.sex, "value") else str(p.sex)
            gender_icon = "♂" if gender_val == "男" else "♀"
            realm_name = realm_by_level_and_reincarnation(p.level, p.reincarnation_level)
            lines.append(
                f"{idx}. {p.nickname} {gender_icon} Lv.{p.level} {realm_name}  UID:{p.uid}  距离:{_dist(p)}"
            )

        await nearby_cmd.finish(message_add_head("\n".join(lines), event))
