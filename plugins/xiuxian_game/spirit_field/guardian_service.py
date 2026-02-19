"""
诡兽守田服务
"""
from datetime import datetime
from typing import Tuple
from nonebot import logger

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.inventory import ItemInstance
from .config import GuardianBeastManager, GUARDIAN_HUNGRY_HOURS


class GuardianService:
    """诡兽守田服务"""

    def __init__(self):
        self.beast_manager = GuardianBeastManager()

    async def place_guardian(
        self, uow: UnitOfWork, player_id: str, beast_name: str
    ) -> Tuple[bool, str]:
        """放置诡兽"""
        field = await uow.spirit_fields.get_by_player_id(player_id)
        if not field:
            return False, "你还没有灵田"

        if field.guardian_beast_id:
            beast = self.beast_manager.get_beast_by_item_id(field.guardian_beast_id)
            current_name = beast.name if beast else "未知诡兽"
            return False, f"灵田已有诡兽【{current_name}】守田，请先收回"

        # 查找诡兽配置
        beast_config = self.beast_manager.get_beast_by_name(beast_name)
        if not beast_config:
            return False, f"未找到诡兽【{beast_name}】"

        # 检查背包中是否有该诡兽
        beast_count = await uow.items.get_material_total_quantity(player_id, beast_config.item_id)
        if beast_count < 1:
            return False, f"背包中没有【{beast_name}】"

        # 从背包移除
        await ItemInstance.consume_item(uow.session, player_id, beast_config.item_id, 1)

        # 放置诡兽
        field.guardian_beast_id = beast_config.item_id
        field.guardian_fed_at = datetime.now()
        await uow.spirit_fields.update(field)

        return True, (
            f"成功放置【{beast_config.name}】守田!\n"
            f"拦截率: {beast_config.intercept_rate}%\n"
            f"每日灵食费: {beast_config.daily_feed_cost}金"
        )

    async def remove_guardian(
        self, uow: UnitOfWork, player_id: str
    ) -> Tuple[bool, str]:
        """收回诡兽"""
        field = await uow.spirit_fields.get_by_player_id(player_id)
        if not field:
            return False, "你还没有灵田"

        if not field.guardian_beast_id:
            return False, "灵田没有守田诡兽"

        beast = self.beast_manager.get_beast_by_item_id(field.guardian_beast_id)
        beast_name = beast.name if beast else "未知诡兽"

        # 放回背包
        try:
            await ItemInstance.add_item(uow.session, player_id, field.guardian_beast_id, 1)
        except ValueError as e:
            return False, f"背包空间不足: {e}"

        field.guardian_beast_id = None
        field.guardian_fed_at = None
        await uow.spirit_fields.update(field)

        return True, f"已收回【{beast_name}】到背包"

    async def feed_guardian(
        self, uow: UnitOfWork, player_id: str
    ) -> Tuple[bool, str]:
        """喂养诡兽"""
        field = await uow.spirit_fields.get_by_player_id(player_id)
        if not field:
            return False, "你还没有灵田"

        if not field.guardian_beast_id:
            return False, "灵田没有守田诡兽"

        beast = self.beast_manager.get_beast_by_item_id(field.guardian_beast_id)
        if not beast:
            return False, "诡兽配置异常"

        player = await uow.players.get_by_id(player_id)
        if player.gold < beast.daily_feed_cost:
            return False, f"金币不足，喂养需要{beast.daily_feed_cost}金币"

        player.gold -= beast.daily_feed_cost
        await uow.players.update(player)

        field.guardian_fed_at = datetime.now()
        await uow.spirit_fields.update(field)

        return True, (
            f"已喂养【{beast.name}】\n"
            f"消耗: {beast.daily_feed_cost}金币\n"
            f"状态: 精力充沛"
        )

    async def auto_feed_all(self, uow: UnitOfWork) -> int:
        """定时任务: 自动扣除所有诡兽灵食费"""
        from sqlalchemy import select
        from ..models.spirit_field import SpiritField

        stmt = select(SpiritField).where(SpiritField.guardian_beast_id != None)
        result = await uow.session.execute(stmt)
        fields = result.scalars().all()

        fed_count = 0
        for field in fields:
            beast = self.beast_manager.get_beast_by_item_id(field.guardian_beast_id)
            if not beast:
                continue

            player = await uow.players.get_by_id(field.player_id)
            if not player:
                continue

            if player.gold >= beast.daily_feed_cost:
                player.gold -= beast.daily_feed_cost
                field.guardian_fed_at = datetime.now()
                await uow.players.update(player)
                await uow.spirit_fields.update(field)
                fed_count += 1
            # 金币不足不自动喂食，让诡兽进入饥饿状态

        return fed_count
