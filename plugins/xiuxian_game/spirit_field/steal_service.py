"""
偷菜服务 - 偷菜逻辑+诡兽拦截
"""
import random
import math
import json
from datetime import datetime
from typing import Tuple, List, Optional
from nonebot import logger
from sqlalchemy import select

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.spirit_field import SpiritField, SpiritFieldPlot, SpiritFieldStealLog
from ..models.player import Player
from ..models.inventory import ItemInstance
from .config import (
    STEAL_MAX_PER_DAY, STEAL_COOLDOWN_MINUTES, STEAL_PERCENT,
    STEAL_TARGET_LIST_LIMIT,
    GUARDIAN_HUNGRY_HOURS, GUARDIAN_HUNGRY_RATE_PENALTY,
    CropManager, GuardianBeastManager,
)


class StealService:
    """偷菜服务"""

    def __init__(self):
        self.crop_manager = CropManager()
        self.beast_manager = GuardianBeastManager()

    async def get_steal_targets(self, uow: UnitOfWork, player_id: str) -> Tuple[bool, str]:
        """获取可偷目标列表（含未成熟作物概况）"""
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now()

        # 检查每日次数
        steal_count = await uow.spirit_field_steal_logs.get_today_steal_count(player_id, today)
        if steal_count >= STEAL_MAX_PER_DAY:
            return False, f"今日偷菜次数已用完({steal_count}/{STEAL_MAX_PER_DAY})"

        # 获取所有其他玩家灵田
        stmt = select(SpiritField).where(SpiritField.player_id != player_id)
        result = await uow.session.execute(stmt)
        all_fields = result.scalars().all()

        ready_targets = []   # 有成熟作物且可偷
        pending_targets = [] # 有在种作物但暂不可偷

        for field in all_fields:
            # 获取所有种植中的地块并更新成熟状态
            plots = await uow.spirit_field_plots.get_planted_plots(field.id)
            if not plots:
                continue

            for plot in plots:
                if not plot.is_mature and plot.mature_at and plot.mature_at <= now:
                    plot.is_mature = True
                    await uow.spirit_field_plots.update(plot)

            mature_plots = [p for p in plots if p.is_mature]
            growing_plots = [p for p in plots if not p.is_mature and p.mature_at]

            # 检查是否今日已偷过
            already_stolen = await uow.spirit_field_steal_logs.has_stolen_from_today(
                player_id, field.player_id, today
            )

            # 检查实际可偷数量（需≥5才能偷到1个）
            stealable_plots = sum(
                1 for p in mature_plots
                if math.floor(max(0, p.yield_quantity - p.stolen_quantity) * STEAL_PERCENT) >= 1
            )

            victim = await uow.players.get_by_id(field.player_id)
            if not victim:
                continue

            if mature_plots and not already_stolen and stealable_plots > 0:
                # 可立即偷取
                ready_targets.append({
                    "player": victim,
                    "field": field,
                    "mature_count": len(mature_plots),
                    "stealable_plots": stealable_plots,
                })
            else:
                # 暂不可偷：记录在种概况
                all_growing = growing_plots[:]
                # 已成熟但今日已偷或已被偷完的也算在内
                if mature_plots and (already_stolen or stealable_plots == 0):
                    all_growing = mature_plots + growing_plots

                if not all_growing and not mature_plots:
                    continue

                # 最早成熟时间（只看未成熟的）
                min_mature_at = None
                if growing_plots:
                    min_mature_at = min(p.mature_at for p in growing_plots)

                pending_targets.append({
                    "player": victim,
                    "field": field,
                    "growing_count": len(plots),  # 总种植数
                    "mature_count": len(mature_plots),
                    "min_mature_at": min_mature_at,
                    "already_stolen": already_stolen,
                    "stealable_plots": stealable_plots,
                })

        if not ready_targets and not pending_targets:
            return False, "当前没有任何玩家种有作物"

        remaining_chances = STEAL_MAX_PER_DAY - steal_count
        msg = f"『灵田侦查』今日剩余 {remaining_chances} 次\n"

        # 可立即偷取部分
        msg += "─────────────────\n"
        if ready_targets:
            msg += "✦ 可立即行窃\n"
            for t in ready_targets[:STEAL_TARGET_LIST_LIMIT]:
                p = t["player"]
                beast_line = ""
                if t["field"].guardian_beast_id:
                    beast = self.beast_manager.get_beast_by_item_id(t["field"].guardian_beast_id)
                    if beast:
                        beast_line = f"\n     └⚠ {beast.name}守田"
                msg += f"▸ {p.uid}·{p.nickname}  熟 {t['mature_count']} 块{beast_line}\n"
        else:
            msg += "✦ 可立即行窃  暂无目标\n"

        # 在种未成熟部分
        if pending_targets:
            msg += "─────────────────\n"
            msg += "✧ 暗中窥探\n"
            for t in pending_targets[:STEAL_TARGET_LIST_LIMIT]:
                p = t["player"]
                tags = []

                if t["already_stolen"]:
                    tags.append("今日已偷")
                elif t["stealable_plots"] == 0 and t["mature_count"] > 0:
                    tags.append("成熟量不足")

                if t["min_mature_at"]:
                    remaining = (t["min_mature_at"] - now).total_seconds()
                    if remaining > 0:
                        h = int(remaining // 3600)
                        m = int((remaining % 3600) // 60)
                        tags.append(f"{h}h{m}m后可偷" if h > 0 else f"{m}分钟后可偷")

                tag_str = f"  {'·'.join(tags)}" if tags else ""
                msg += f"▹ {p.uid}·{p.nickname}  种 {t['growing_count']} 块{tag_str}\n"

        msg += "─────────────────\n"
        msg += "发送「偷菜 UID」出手"

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
                f"『当场被抓』\n"
                f"─────────────────\n"
                f"{victim.nickname} 的{beast_name}扑了上来！\n"
                f"罚没金币：{actual_penalty:,}\n"
                f"─────────────────\n"
                f"这次偷鸡不成蚀把米..."
            )

        # 偷取成功 - 每种作物偷20%（向下取整，产量不足5个时可能偷不到）
        stolen_items = {}
        for plot in mature_plots:
            available = max(0, plot.yield_quantity - plot.stolen_quantity)
            if available <= 0:
                continue

            steal_qty = math.floor(available * STEAL_PERCENT)
            if steal_qty <= 0:
                continue

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

        if not stolen_items:
            return False, "没有可偷取的作物"

        # 写一条汇总日志（一次偷菜行为 = 一条记录）
        total_qty = sum(stolen_items.values())
        log = SpiritFieldStealLog(
            thief_id=thief_id,
            victim_id=victim.id,
            crop_id="",
            quantity=total_qty,
            stolen_summary=json.dumps(stolen_items, ensure_ascii=False),
            was_caught=False,
            penalty_gold=0,
            steal_date=today,
        )
        await uow.spirit_field_steal_logs.add(log)

        # 更新统计
        field.total_stolen_from += sum(stolen_items.values())
        await uow.spirit_fields.update(field)

        thief_field = await uow.spirit_fields.get_by_player_id(thief_id)
        if thief_field:
            thief_field.total_stolen_by_me += sum(stolen_items.values())
            await uow.spirit_fields.update(thief_field)

        msg = f"『夜袭得手』\n"
        msg += f"─────────────────\n"
        msg += f"目标：{victim.nickname}\n"
        for name, qty in stolen_items.items():
            msg += f"  {name}  ×{qty}\n"
        msg += f"─────────────────\n"
        msg += f"共获得 {total_qty} 株灵草"

        return True, msg

    async def get_steal_logs(
        self, uow: UnitOfWork, player_id: str, page: int = 1
    ) -> Tuple[bool, str]:
        """查看偷菜记录（支持分页，每页5条）"""
        PAGE_SIZE = 5
        offset = (page - 1) * PAGE_SIZE

        # 被偷记录
        total_victim = await uow.spirit_field_steal_logs.get_total_count_for_victim(player_id)
        stolen_from_logs = await uow.spirit_field_steal_logs.get_recent_logs_for_victim(player_id, PAGE_SIZE, offset)
        victim_pages = max(1, math.ceil(total_victim / PAGE_SIZE))

        # 偷别人记录
        total_thief = await uow.spirit_field_steal_logs.get_total_count_for_thief(player_id)
        stolen_by_logs = await uow.spirit_field_steal_logs.get_recent_logs_for_thief(player_id, PAGE_SIZE, offset)
        thief_pages = max(1, math.ceil(total_thief / PAGE_SIZE))

        msg = f"『灵田档案』第 {page} 页\n"
        msg += "─────────────────\n"

        if stolen_from_logs:
            msg += f"□ 我的损失  ({page}/{victim_pages}页)\n"
            for log in stolen_from_logs:
                thief = await uow.players.get_by_id(log.thief_id)
                thief_name = thief.nickname if thief else "未知"
                time_str = log.created_at.strftime("%m-%d %H:%M")
                if log.was_caught:
                    msg += f"  {time_str}  {thief_name} 被诡兽拦截 +{log.penalty_gold:,}金\n"
                elif log.stolen_summary:
                    items = json.loads(log.stolen_summary)
                    items_str = "  ".join(f"{name}×{qty}" for name, qty in items.items())
                    msg += f"  {time_str}  {thief_name} 偷走 {items_str}\n"
                else:
                    crop = self.crop_manager.get_crop(log.crop_id)
                    crop_name = crop.name if crop else "未知"
                    msg += f"  {time_str}  {thief_name} 偷走 {crop_name}×{log.quantity}\n"
        else:
            msg += "□ 我的损失  暂无记录\n"

        msg += "─────────────────\n"

        if stolen_by_logs:
            msg += f"■ 我的收获  ({page}/{thief_pages}页)\n"
            for log in stolen_by_logs:
                victim = await uow.players.get_by_id(log.victim_id)
                victim_name = victim.nickname if victim else "未知"
                time_str = log.created_at.strftime("%m-%d %H:%M")
                if log.was_caught:
                    msg += f"  {time_str}  偷 {victim_name} 被抓 -{log.penalty_gold:,}金\n"
                elif log.stolen_summary:
                    items = json.loads(log.stolen_summary)
                    items_str = "  ".join(f"{name}×{qty}" for name, qty in items.items())
                    msg += f"  {time_str}  偷 {victim_name}  {items_str}\n"
                else:
                    crop = self.crop_manager.get_crop(log.crop_id)
                    crop_name = crop.name if crop else "未知"
                    msg += f"  {time_str}  偷 {victim_name}  {crop_name}×{log.quantity}\n"
        else:
            msg += "■ 我的收获  暂无记录\n"

        msg += "─────────────────\n"
        msg += "发送「偷菜记录 页码」翻页"
        return True, msg
