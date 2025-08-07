from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg

from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head

# ----------------- 指令：附近玩家 -----------------
# 查看当前区域距离自己最近的前 5 位玩家
nearby_cmd = on_command("附近玩家", aliases={"附近人"}, block=True, priority=5)


@nearby_cmd.handle()
async def _(event: MessageEvent):
    async with safe_session() as session:
        # 获取当前玩家
        player: Player | None = await session.get(Player, event.get_user_id())
        if not player:
            await nearby_cmd.finish("⛔ 请先创建角色")

        # 查询同区域其他玩家
        stmt = select(Player).where(
            Player.region == player.region,
            Player.id != player.id  # 排除自己
        )
        others = (await session.execute(stmt)).scalars().all()

        if not others:
            await nearby_cmd.finish(message_add_head("📭 附近暂无其他玩家", event))

        # 按曼哈顿距离排序
        def _dist(p: Player) -> int:
            return abs(p.x - player.x) + abs(p.y - player.y)

        others.sort(key=_dist)
        top5 = others[:5]

        # 导入境界映射函数
        from ..player.info import realm_by_level

        # 构造回复
        header = f"📍 当前位置：{player.region} ({player.x},{player.y})"
        lines = [header, "🧑‍🤝‍🧑 附近玩家："]
        for idx, p in enumerate(top5, 1):
            gender_val = p.sex.value if hasattr(p.sex, "value") else str(p.sex)
            gender_icon = "♂" if gender_val == "男" else "♀"
            lines.append(
                f"{idx}. {p.nickname} {gender_icon} Lv.{p.level} {realm_by_level(p.level)}  UID:{p.uid}  距离:{_dist(p)}"
            )

        await nearby_cmd.finish(message_add_head("\n".join(lines), event)) 