from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.guild import BuildingType, Guild, GuildBuilding
from ..models.player import Player
from .guild_building_service_new import GuildBuildingService


async def _backfill_missing_positions(session: AsyncSession, guild_id: int) -> None:
    """兼容旧公会建筑：首次使用基地建筑能力时补齐布局坐标。"""
    buildings = (await session.execute(
        select(GuildBuilding).where(GuildBuilding.guild_id == guild_id)
    )).scalars().all()
    occupied = {
        (building.plot_x, building.plot_y)
        for building in buildings
        if building.plot_x is not None and building.plot_y is not None
    }
    empty_positions = [
        (plot_x, plot_y)
        for plot_y in range(1, GuildBuildingService.GRID_SIZE + 1)
        for plot_x in range(1, GuildBuildingService.GRID_SIZE + 1)
        if (plot_x, plot_y) not in occupied
    ]

    for building in buildings:
        if building.plot_x is not None and building.plot_y is not None:
            continue
        if not empty_positions:
            return
        building.plot_x, building.plot_y = empty_positions.pop(0)
        session.add(building)

    await session.flush()


async def get_active_base_building_effects(
    session: AsyncSession,
    player: Player,
    building_type: BuildingType,
) -> tuple[dict, str]:
    """获取玩家在公会基地时可使用的指定建筑效果。"""
    if not player.guild_id or player.is_in_dungeon():
        return {}, ""

    guild = await session.get(Guild, player.guild_id)
    if not guild or guild.base_x is None or guild.base_y is None:
        return {}, ""

    current_x, current_y = player.get_current_coordinates()
    if current_x != guild.base_x or current_y != guild.base_y:
        return {}, ""

    await _backfill_missing_positions(session, player.guild_id)

    stmt = select(GuildBuilding).where(
        and_(
            GuildBuilding.guild_id == player.guild_id,
            GuildBuilding.building_type == building_type,
        )
    )
    building = (await session.execute(stmt)).scalars().first()
    if not building:
        return {}, ""

    effects = GuildBuildingService.get_effects_for_level(building_type, building.level)
    all_buildings = (await session.execute(
        select(GuildBuilding).where(GuildBuilding.guild_id == player.guild_id)
    )).scalars().all()
    adjacency_bonuses = GuildBuildingService.get_adjacency_bonuses(list(all_buildings))
    effects = dict(effects)
    if building_type == BuildingType.ARTIFACT_FORGE:
        effects["forge_gold_discount"] = min(
            0.25,
            effects.get("forge_gold_discount", 0.0) + adjacency_bonuses["forge_gold_discount"],
        )
    elif building_type == BuildingType.REFINING_PAVILION:
        effects["upgrade_success_bonus"] = min(
            0.15,
            effects.get("upgrade_success_bonus", 0.0) + adjacency_bonuses["upgrade_success_bonus"],
        )
    building_name = GuildBuildingService.BUILDING_CONFIGS[building_type]["name"]
    return effects, building_name
