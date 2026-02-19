"""
偷菜服务 - 偷菜逻辑+诡兽拦截
"""
import random
import math
from datetime import datetime, timedelta
from typing import Tuple, List, Optional
from nonebot import logger
from sqlalchemy import select, and_

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.spirit_field import SpiritField, SpiritFieldPlot, SpiritFieldStealLog
from ..models.player import Player
from ..models.inventory import ItemInstance
from .config import (
    STEAL_MAX_PER_DAY, STEAL_COOLDOWN_MINUTES, STEAL_PERCENT,
    STEAL_MIN_QUANTITY, STEAL_TARGET_ACTIVE_HOURS, STEAL_TARGET_LIST_LIMIT,
    GUARDIAN_HUNGRY_HOURS, GUARDIAN_HUNGRY_RATE_PENALTY,
    CropManager, GuardianBeastManager,
)


class StealService:
    """偷菜服务"""

    def __init__(self):
        self.crop_manager = CropManager()
        self.beast_manager = GuardianBeastManager()

    async def get_steal_targets(self, uow: UnitOfWork, player_id: str) -> Tuple[bool, str]:
        """获取可偷目标列表"""
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now()

        # 检查每日次数
        steal_count = await uow.spirit_field_steal_logs.get_today_steal_count(player_id, today)
        if steal_count >= STEAL_MAX_PER_DAY:
            return False, f"今日偷菜次数已用完({steal_count}/{STEAL_MAX_PER_DAY})"

        # 查找有成熟作物的活跃玩家
        active_threshold = now - timedelta(hours=STEAL_TARGET_ACTIVE_HOURS)

        # 获取所有灵田
        stmt = select(SpiritField).where(SpiritField.player_id != player_id)
        result = await uow.session.execute(stmt)
        all_fields = result.scalars().all()

        targets = []
        for field in all_fields:
            # 先更新成熟状态
            plots = await uow.spirit_field_plots.get_planted_plots(field.id)
            for plot in plots:
                if not plot.is_mature and plot.mature_at and plot.mature_at <= now:
                    plot.is_mature = True
                    await uow.spirit_field_plots.update(plot)

            mature_plots = await uow.spirit_field_plots.get_mature_plots(field.id)
            if not mature_plots:
                continue

            # 检查是否今日已偷过
            already_stolen = await uow.spirit_field_steal_logs.has_stolen_from_today(
                player_id, field.player_id, today
            )
            if already_stolen:
                continue

            # 检查可偷数量
            stealable = sum(
                max(0, p.yield_quantity - p.stolen_quantity)
                for p in mature_plots
            )
            if stealable <= 0:
                continue

            # 获取玩家信息
            victim = await uow.players.get_by_id(field.player_id)
            if not victim:
                continue

            targets.append({
                "player": victim,
                "field": field,
                "mature_count": len(mature_plots),
                "stealable": stealable,
            })

            if len(targets) >= STEAL_TARGET_LIST_LIMIT:
                break

        if not targets:
            return False, "当前没有可偷菜的目标"

        msg = f"可偷菜目标 ({steal_count}/{STEAL_MAX_PER_DAY}次已用)\n━━━━━━━━━━━━━\n"
        for t in targets:
            p = t["player"]
            beast_info = ""
            if t["field"].guardian_beast_id:
                beast = self.beast_manager.get_beast_by_item_id(t["field"].guardian_beast_id)
                if beast:
                    beast_info = f" [{beast.name}守田]"
            msg += f"UID:{p.uid} {p.nickname} - 成熟{t['mature_count']}块{beast_info}\n"

        msg += f"━━━━━━━━━━━━━\n使用【偷菜 UID】偷取"

        return True, msg

    async def steal_from(
        self, uow: UnitOfWork, thief_id: str, victim_uid: int
    ) -> Tuple[bool, str]:
        """执行偷菜"""
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now()

        # 检查冷却
        last_steal = await uow.spirit_field_steal_logs.get_last_steal_time(thief_id)
        if last_steal:
            elapsed = (now - last_steal.created_at).total_seconds() / 60
            if elapsed < STEAL_COOLDOWN_MINUTES:
                remaining = int(STEAL_COOLDOWN_MINUTES - elapsed)
                return False, f"偷菜冷却中，还需{remaining}分钟"

        # 检查每日次数
        steal_count = await uow.spirit_field_steal_logs.get_today_steal_count(thief_id, today)
        if steal_count >= STEAL_MAX_PER_DAY:
            return False, f"今日偷菜次数已用完({STEAL_MAX_PER_DAY}次)"

        # 查找目标
        stmt = select(Player).where(Player.uid == victim_uid)
        result = await uow.session.execute(stmt)
        victim = result.scalar_one_or_none()
        if not victim:
            return False, f"未找到UID为{victim_uid}的玩家"

        if victim.id == thief_id:
            return False, "不能偷自己的作物"

        # 检查今日是否已偷过
        already_stolen = await uow.spirit_field_steal_logs.has_stolen_from_today(
            thief_id, victim.id, today
        )
        if already_stolen:
            return False, f"今日已偷过{victim.nickname}，每人每日限偷1次"

        # 获取目标灵田
        field = await uow.spirit_fields.get_by_player_id(victim.id)
        if not field:
            return False, f"{victim.nickname}没有灵田"

        # 更新成熟状态并获取成熟地块
        planted = await uow.spirit_field_plots.get_planted_plots(field.id)
        for plot in planted:
            if not plot.is_mature and plot.mature_at and plot.mature_at <= now:
                plot.is_mature = True
                await uow.spirit_field_plots.update(plot)

        mature_plots = await uow.spirit_field_plots.get_mature_plots(field.id)
        if not mature_plots:
            return False, f"{victim.nickname}没有成熟的作物"

        # 检查诡兽拦截
        was_caught = False
        penalty_gold = 0
        if field.guardian_beast_id:
            beast = self.beast_manager.get_beast_by_item_id(field.guardian_beast_id)
            if beast:
                intercept_rate = beast.intercept_rate

                # 检查饥饿状态
                if field.guardian_fed_at:
                    hours_since_fed = (now - field.guardian_fed_at).total_seconds() / 3600
                    if hours_since_fed >= GUARDIAN_HUNGRY_HOURS:
                        intercept_rate = int(intercept_rate * GUARDIAN_HUNGRY_RATE_PENALTY)

                if random.randint(1, 100) <= intercept_rate:
                    was_caught = True
                    penalty_gold = beast.penalty_gold

        if was_caught:
            # 被拦截 - 扣罚金
            thief_player = await uow.players.get_by_id(thief_id)
            actual_penalty = min(penalty_gold, thief_player.gold)
            thief_player.gold -= actual_penalty
            await uow.players.update(thief_player)

            # 记录日志
            log = SpiritFieldStealLog(
                thief_id=thief_id,
                victim_id=victim.id,
                crop_id="",
                quantity=0,
                was_caught=True,
                penalty_gold=actual_penalty,
                steal_date=today,
            )
            await uow.spirit_field_steal_logs.add(log)

            beast = self.beast_manager.get_beast_by_item_id(field.guardian_beast_id)
            beast_name = beast.name if beast else "诡兽"

            return False, (
                f"偷菜失败!\n"
                f"{victim.nickname}的{beast_name}发现了你!\n"
                f"被罚金: {actual_penalty}金币"
            )

        # 偷取成功 - 每种作物偷20%
        stolen_items = {}
        for plot in mature_plots:
            available = max(0, plot.yield_quantity - plot.stolen_quantity)
            if available <= 0:
                continue

            steal_qty = max(STEAL_MIN_QUANTITY, math.floor(available * STEAL_PERCENT))
            steal_qty = min(steal_qty, available)

            crop = self.crop_manager.get_crop(plot.crop_id)
            if not crop:
                continue

            plot.stolen_quantity += steal_qty
            await uow.spirit_field_plots.update(plot)

            # 添加到偷菜者背包
            try:
                await ItemInstance.add_item(uow.session, thief_id, crop.harvest_item_id, steal_qty)
                stolen_items[crop.name] = stolen_items.get(crop.name, 0) + steal_qty
            except ValueError:
                pass

            # 记录日志
            log = SpiritFieldStealLog(
                thief_id=thief_id,
                victim_id=victim.id,
                crop_id=plot.crop_id,
                quantity=steal_qty,
                was_caught=False,
                penalty_gold=0,
                steal_date=today,
            )
            await uow.spirit_field_steal_logs.add(log)

        if not stolen_items:
            return False, "没有可偷取的作物"

        # 更新统计
        field.total_stolen_from += sum(stolen_items.values())
        await uow.spirit_fields.update(field)

        thief_field = await uow.spirit_fields.get_by_player_id(thief_id)
        if thief_field:
            thief_field.total_stolen_by_me += sum(stolen_items.values())
            await uow.spirit_fields.update(thief_field)

        msg = f"偷菜成功!\n从{victim.nickname}偷到:\n"
        for name, qty in stolen_items.items():
            msg += f"  {name} x{qty}\n"

        return True, msg

    async def get_steal_logs(
        self, uow: UnitOfWork, player_id: str
    ) -> Tuple[bool, str]:
        """查看偷菜记录"""
        # 被偷记录
        stolen_from_logs = await uow.spirit_field_steal_logs.get_recent_logs_for_victim(player_id, 5)
        # 偷别人记录
        stolen_by_logs = await uow.spirit_field_steal_logs.get_recent_logs_for_thief(player_id, 5)

        msg = "灵田记录\n━━━━━━━━━━━━━\n"

        if stolen_from_logs:
            msg += "被偷菜记录:\n"
            for log in stolen_from_logs:
                thief = await uow.players.get_by_id(log.thief_id)
                thief_name = thief.nickname if thief else "未知"
                if log.was_caught:
                    msg += f"  {thief_name} 被诡兽拦截 (罚{log.penalty_gold}金)\n"
                else:
                    crop = self.crop_manager.get_crop(log.crop_id)
                    crop_name = crop.name if crop else "未知"
                    msg += f"  {thief_name} 偷走{crop_name}x{log.quantity}\n"
        else:
            msg += "暂无被偷菜记录\n"

        msg += "━━━━━━━━━━━━━\n"

        if stolen_by_logs:
            msg += "我的偷菜记录:\n"
            for log in stolen_by_logs:
                victim = await uow.players.get_by_id(log.victim_id)
                victim_name = victim.nickname if victim else "未知"
                if log.was_caught:
                    msg += f"  偷{victim_name}失败 (罚{log.penalty_gold}金)\n"
                else:
                    crop = self.crop_manager.get_crop(log.crop_id)
                    crop_name = crop.name if crop else "未知"
                    msg += f"  偷{victim_name} {crop_name}x{log.quantity}\n"
        else:
            msg += "暂无偷菜记录\n"

        return True, msg
