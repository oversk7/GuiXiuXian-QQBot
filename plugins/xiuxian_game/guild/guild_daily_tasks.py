"""
公会每日任务 - 基于玩家触发的丹房产出生成
"""
from datetime import datetime, date
from sqlalchemy import select
from ..models.db import safe_session
from ..models.guild import Guild, GuildBuilding, BuildingType
from .guild_facility_service import GuildFacilityService


class GuildDailyTasks:
    """公会每日任务管理器"""

    @staticmethod
    async def check_and_generate_alchemy_production(session, guild_id: int) -> int:
        """检查并生成指定公会的丹房产出（如果需要的话）"""
        return await GuildFacilityService.generate_daily_alchemy_production(session, guild_id)

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
