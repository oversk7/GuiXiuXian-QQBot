"""
玩家面板查询模块 (CQRS Query Side)

查看他人面板时走纯只读路径，不经过 UoW。
"""

from dataclasses import dataclass, field
from collections import defaultdict
from typing import Dict

from sqlalchemy import select

from . import readonly_session
from ..models.player import Player
from ..models.inventory import ItemInstance
from ..models.guild import Guild
from ..domain.attributes import get_effective_attributes_v2
from ..config import config


@dataclass
class PlayerProfileDTO:
    """玩家面板展示数据"""
    player: Player
    effective_attrs: Dict[str, int | float]
    equipment_bonus: Dict[str, int]
    guild_name: str


async def query_player_profile(uid: int) -> PlayerProfileDTO | None:
    """纯只读路径查看他人面板

    Args:
        uid: 玩家 UID

    Returns:
        PlayerProfileDTO，未找到返回 None
    """
    async with readonly_session() as session:
        # 1. 查找玩家
        stmt = select(Player).where(Player.uid == uid)
        result = await session.execute(stmt)
        player = result.scalars().first()
        if not player:
            return None

        # 2. 获取有效属性
        effective_attrs = await get_effective_attributes_v2(player, session)

        # 3. 统计装备加成（用于面板显示）
        bonus: Dict[str, int] = defaultdict(int)
        equip_ids = config.items_config["by_type"]["EQUIPMENT"]
        eq_stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(equip_ids)
        )
        equipped_list = (await session.execute(eq_stmt)).scalars().all()
        for eq in equipped_list:
            delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
            for k, v in delta.items():
                bonus[k] += int(v)

        # 4. 获取公会名称
        guild_name = "无所属"
        if player.guild_id:
            g_obj = await session.get(Guild, player.guild_id)
            if g_obj:
                guild_name = g_obj.name

    return PlayerProfileDTO(
        player=player,
        effective_attrs=effective_attrs,
        equipment_bonus=dict(bonus),
        guild_name=guild_name,
    )
