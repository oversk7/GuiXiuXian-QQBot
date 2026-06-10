"""
公会每日任务 - 基于玩家触发的丹房产出生成
"""
from .guild_facility_service import GuildFacilityService


class GuildDailyTasks:
    """公会每日任务管理器"""

    @staticmethod
    async def check_and_generate_alchemy_production(session, guild_id: int) -> int:
        """检查并生成指定公会的丹房产出（如果需要的话）"""
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.guild_teleport_log_repository import GuildTeleportLogRepository
        from ..infrastructure.repositories.guild_alchemy_production_repository import GuildAlchemyProductionRepository
        from ..infrastructure.repositories.guild_warehouse_item_repository import GuildWarehouseItemRepository

        facility_service = GuildFacilityService(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            player_repo=PlayerRepository(session),
            item_repo=ItemRepository(session),
            teleport_log_repo=GuildTeleportLogRepository(session),
            alchemy_production_repo=GuildAlchemyProductionRepository(session),
            warehouse_item_repo=GuildWarehouseItemRepository(session),
        )
        return await facility_service.generate_daily_alchemy_production(guild_id)

    @staticmethod
    async def trigger_guild_daily_refresh(session, guild_id: int) -> dict:
        """触发公会每日刷新，返回刷新结果"""
        result = {
            "alchemy_generated": 0,
            "message": ""
        }

        # 检查并生成丹房产出
        generated = await GuildDailyTasks.check_and_generate_alchemy_production(session, guild_id)
        result["alchemy_generated"] = generated

        if generated > 0:
            result["message"] = f"丹房产出了{generated}个新丹药！"
        elif generated == -1:
            # 存储已满的特殊提示
            result["message"] = "⚠️ 丹房存储已满,请先兑换一些丹药"

        return result
