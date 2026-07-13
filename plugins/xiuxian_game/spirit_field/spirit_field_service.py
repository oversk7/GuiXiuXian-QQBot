"""
灵田核心服务 - 开田/升级/种植/灌溉/收菜
"""
import random
import math
from datetime import datetime, timedelta
from typing import Tuple, List, Optional, Dict
from nonebot import logger
from sqlalchemy import select

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.spirit_field import SpiritField, SpiritFieldPlot
from ..models.inventory import ItemInstance
from ..models.player import Player
from .config import (
    FIELD_LEVEL_PLOTS, FIELD_UPGRADE_COST, FIELD_LEVEL_UNLOCK_RARITY,
    WATER_MAX_PER_DAY, WATER_COOLDOWN_MINUTES, WATER_TIME_REDUCE_PERCENT,
    HARVEST_SEED_RETURN_CHANCE, FIELD_CREATE_COST,
    RARITY_NAMES, RARITY_ICONS,
    CropManager, GuardianBeastManager,
)


def format_duration(seconds: float) -> str:
    """秒数 -> X小时Y分 / X小时 / Y分钟"""
    total_minutes = int(seconds // 60)
    if total_minutes <= 0:
        return "不足1分钟"
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours}小时{minutes}分"
    if hours:
        return f"{hours}小时"
    return f"{minutes}分钟"


class SpiritFieldService:
    """灵田核心服务"""

    def __init__(self):
        self.crop_manager = CropManager()
        self.beast_manager = GuardianBeastManager()

    # ==================== 阴宅联动加成 ====================

    @staticmethod
    def get_mansion_field_bonus(mansion_level: int) -> Tuple[float, float]:
        """
        根据阴宅等级计算灵田加成

        Returns:
            (成长加速百分比, 产量加成百分比)
        """
        if mansion_level <= 0:
            return 0.0, 0.0

        # 成长加速
        if mansion_level <= 5:
            growth_bonus = mansion_level * 5.0  # 5%/级
        elif mansion_level <= 10:
            growth_bonus = 25.0 + (mansion_level - 5) * 3.0  # 25% + 3%/级
        elif mansion_level <= 20:
            growth_bonus = 40.0 + (mansion_level - 10) * 2.0  # 40% + 2%/级
        else:
            growth_bonus = 60.0 + (mansion_level - 20) * 1.0  # 60% + 1%/级

        # 产量加成
        if mansion_level <= 5:
            yield_bonus = 0.0
        elif mansion_level <= 10:
            yield_bonus = (mansion_level - 5) * 5.0  # 5%/级
        elif mansion_level <= 20:
            yield_bonus = 25.0 + (mansion_level - 10) * 2.0  # 25% + 2%/级
        else:
            yield_bonus = 45.0 + (mansion_level - 20) * 1.0  # 45% + 1%/级

        return min(growth_bonus, 70.0), min(yield_bonus, 55.0)

    # ==================== 开辟灵田 ====================

    async def create_field(self, uow: UnitOfWork, player_id: str) -> Tuple[bool, str]:
        """开辟灵田"""
        # 检查是否已有灵田
        existing = await uow.spirit_fields.get_by_player_id(player_id)
        if existing:
            return False, "你已经拥有灵田了"

        # 检查金币
        player = await uow.players.get_by_id(player_id)
        if not player:
            return False, "玩家不存在"

        if player.gold < FIELD_CREATE_COST:
            return False, f"金币不足，开辟灵田需要{FIELD_CREATE_COST:,}金币"

        # 扣除金币
        player.gold -= FIELD_CREATE_COST
        await uow.players.update(player)

        # 创建灵田
        field = SpiritField(player_id=player_id, level=1)
        field = await uow.spirit_fields.add(field)

        # 创建初始地块
        initial_plots = FIELD_LEVEL_PLOTS[1]
        for i in range(1, initial_plots + 1):
            plot = SpiritFieldPlot(field_id=field.id, plot_index=i)
            await uow.spirit_field_plots.add(plot)

        return True, (
            f"# 🌾 灵田开辟\n***\n"
            f"灵田等级：1级 · 灵壤 {initial_plots} 块\n"
            f"可种品质：⚪ 白色灵种\n"
            f"消耗金币：{FIELD_CREATE_COST:,}\n\n"
            f"先在种子商店购入灵种，再用「种植 作物名」下地"
        )

    # ==================== 升级灵田 ====================

    async def upgrade_field(self, uow: UnitOfWork, player_id: str) -> Tuple[bool, str]:
        """升级灵田"""
        field = await uow.spirit_fields.get_by_player_id(player_id)
        if not field:
            return False, "你还没有灵田，使用【开辟灵田】创建"

        if field.level >= 9:
            return False, "灵田已达到最大等级(9级)"

        next_level = field.level + 1
        cost = FIELD_UPGRADE_COST.get(next_level, 0)

        player = await uow.players.get_by_id(player_id)
        if player.gold < cost:
            return False, f"金币不足，升级到{next_level}级需要{cost:,}金币"

        # 扣除金币
        player.gold -= cost
        await uow.players.update(player)

        old_plots = FIELD_LEVEL_PLOTS[field.level]
        new_plots = FIELD_LEVEL_PLOTS[next_level]

        # 升级
        field.level = next_level
        await uow.spirit_fields.update(field)

        # 创建新地块
        for i in range(old_plots + 1, new_plots + 1):
            plot = SpiritFieldPlot(field_id=field.id, plot_index=i)
            await uow.spirit_field_plots.add(plot)

        # 解锁信息
        unlocked = FIELD_LEVEL_UNLOCK_RARITY.get(next_level, ["white"])
        max_rarity = unlocked[-1]

        return True, (
            f"# 🌾 灵田升级\n***\n"
            f"等级：{field.level - 1}级 → {field.level}级\n"
            f"灵壤：{old_plots} 块 → {new_plots} 块\n"
            f"可种品质：{RARITY_ICONS[max_rarity]} {RARITY_NAMES[max_rarity]}及以下灵种\n"
            f"消耗金币：{cost:,}"
        )

    # ==================== 种植 ====================

    async def plant(
        self, uow: UnitOfWork, player_id: str,
        crop_name: str, plot_index: Optional[int] = None
    ) -> Tuple[bool, str]:
        """种植作物到指定地块"""
        field = await uow.spirit_fields.get_by_player_id(player_id)
        if not field:
            return False, "你还没有灵田，使用【开辟灵田】创建"

        # 查找作物
        crop = self.crop_manager.get_crop_by_name(crop_name)
        if not crop:
            return False, f"未找到作物【{crop_name}】"

        # 检查稀有度是否已解锁
        allowed = FIELD_LEVEL_UNLOCK_RARITY.get(field.level, ["white"])
        if crop.rarity not in allowed:
            return False, f"灵田等级不足，无法种植{RARITY_NAMES.get(crop.rarity, crop.rarity)}品质的作物"

        # 检查种子
        player = await uow.players.get_by_id(player_id)
        seed_count = await uow.items.get_material_total_quantity(player_id, crop.seed_id)
        if seed_count < 1:
            return False, f"没有【{crop.name}】的种子，使用【灵种商店】购买"

        # 获取目标地块
        if plot_index is not None:
            plot = await uow.spirit_field_plots.get_plot_by_field_and_index(field.id, plot_index)
            if not plot:
                return False, f"地块{plot_index}不存在"
            if plot.crop_id is not None:
                return False, f"地块{plot_index}已有作物"
            plots_to_plant = [plot]
        else:
            empty_plots = await uow.spirit_field_plots.get_empty_plots(field.id)
            if not empty_plots:
                return False, "没有空闲地块"
            plots_to_plant = [empty_plots[0]]

        # 计算实际成长时间（阴宅加成）
        mansion_level = getattr(player, 'mansion_level', 0)
        growth_bonus, yield_bonus = self.get_mansion_field_bonus(mansion_level)
        actual_grow_hours = crop.grow_hours * (1 - growth_bonus / 100.0)

        # 计算产量
        base_yield = random.randint(crop.min_yield, crop.max_yield)
        bonus_yield = math.floor(base_yield * yield_bonus / 100.0)
        total_yield = base_yield + bonus_yield

        now = datetime.now()
        mature_time = now + timedelta(hours=actual_grow_hours)

        # 消耗种子
        await ItemInstance.consume_item(uow.session, player_id, crop.seed_id, 1)

        # 种植
        plot = plots_to_plant[0]
        plot.crop_id = crop.crop_id
        plot.planted_at = now
        plot.mature_at = mature_time
        plot.is_mature = False
        plot.water_count = 0
        plot.last_water_at = None
        plot.yield_quantity = total_yield
        plot.stolen_quantity = 0
        await uow.spirit_field_plots.update(plot)

        # 格式化时间
        time_str = format_duration(actual_grow_hours * 3600)

        yield_str = f"{total_yield}（基础 {base_yield} · 阴宅 +{bonus_yield}）" if bonus_yield > 0 else str(total_yield)
        time_str_full = f"{time_str}（阴宅加速 {growth_bonus:.0f}%）" if growth_bonus > 0 else time_str
        msg = (
            f"# 🌱 种植 · {crop.name}\n***\n"
            f"地块：{plot.plot_index}号灵壤\n"
            f"预计产量：{yield_str}\n"
            f"成熟需时：{time_str_full}"
        )

        return True, msg

    # ==================== 一键种植 ====================

    async def plant_all(
        self, uow: UnitOfWork, player_id: str, crop_name: str
    ) -> Tuple[bool, str]:
        """全部空地块种植同一作物"""
        field = await uow.spirit_fields.get_by_player_id(player_id)
        if not field:
            return False, "你还没有灵田，使用【开辟灵田】创建"

        crop = self.crop_manager.get_crop_by_name(crop_name)
        if not crop:
            return False, f"未找到作物【{crop_name}】"

        allowed = FIELD_LEVEL_UNLOCK_RARITY.get(field.level, ["white"])
        if crop.rarity not in allowed:
            return False, f"灵田等级不足，无法种植{RARITY_NAMES.get(crop.rarity, crop.rarity)}品质的作物"

        empty_plots = await uow.spirit_field_plots.get_empty_plots(field.id)
        if not empty_plots:
            return False, "没有空闲地块"

        player = await uow.players.get_by_id(player_id)
        seed_count = await uow.items.get_material_total_quantity(player_id, crop.seed_id)
        if seed_count < 1:
            return False, f"没有【{crop.name}】的种子"

        plant_count = min(len(empty_plots), seed_count)

        mansion_level = getattr(player, 'mansion_level', 0)
        growth_bonus, yield_bonus = self.get_mansion_field_bonus(mansion_level)
        actual_grow_hours = crop.grow_hours * (1 - growth_bonus / 100.0)
        now = datetime.now()
        mature_time = now + timedelta(hours=actual_grow_hours)

        total_yield = 0
        total_base_yield = 0
        total_bonus_yield = 0
        for i in range(plant_count):
            base_yield = random.randint(crop.min_yield, crop.max_yield)
            bonus_yield = math.floor(base_yield * yield_bonus / 100.0)
            plot_yield = base_yield + bonus_yield
            total_yield += plot_yield
            total_base_yield += base_yield
            total_bonus_yield += bonus_yield

            plot = empty_plots[i]
            plot.crop_id = crop.crop_id
            plot.planted_at = now
            plot.mature_at = mature_time
            plot.is_mature = False
            plot.water_count = 0
            plot.last_water_at = None
            plot.yield_quantity = plot_yield
            plot.stolen_quantity = 0
            await uow.spirit_field_plots.update(plot)

        # 消耗种子
        await ItemInstance.consume_item(uow.session, player_id, crop.seed_id, plant_count)

        time_str = format_duration(actual_grow_hours * 3600)

        yield_str = f"{total_yield}（基础 {total_base_yield} · 阴宅 +{total_bonus_yield}）" if total_bonus_yield > 0 else str(total_yield)
        time_str_full = f"{time_str}（阴宅加速 {growth_bonus:.0f}%）" if growth_bonus > 0 else time_str

        return True, (
            f"# 🌱 一键种植 · {crop.name}\n***\n"
            f"种下：{plant_count} 块 · 消耗种子 {plant_count} 颗\n"
            f"预计总产量：{yield_str}\n"
            f"成熟需时：{time_str_full}"
        )

    # ==================== 灌溉 ====================

    async def water_plot(
        self, uow: UnitOfWork, player_id: str, plot_index: Optional[int] = None
    ) -> Tuple[bool, str]:
        """灌溉指定地块"""
        field = await uow.spirit_fields.get_by_player_id(player_id)
        if not field:
            return False, "你还没有灵田"

        if plot_index is not None:
            plot = await uow.spirit_field_plots.get_plot_by_field_and_index(field.id, plot_index)
            if not plot:
                return False, f"地块{plot_index}不存在"
            if plot.crop_id is None:
                return False, f"地块{plot_index}没有种植作物"
            plots = [plot]
        else:
            # 灌溉第一块可灌溉的
            planted = await uow.spirit_field_plots.get_planted_plots(field.id)
            plots = [p for p in planted if not p.is_mature and p.water_count < WATER_MAX_PER_DAY]
            if not plots:
                return False, "没有需要灌溉的地块"
            plots = [plots[0]]

        plot = plots[0]

        if plot.is_mature:
            return False, f"地块{plot.plot_index}的作物已成熟，无需灌溉"

        if plot.water_count >= WATER_MAX_PER_DAY:
            return False, f"地块{plot.plot_index}今日灌溉次数已达上限({WATER_MAX_PER_DAY}次)"

        now = datetime.now()
        if plot.last_water_at:
            elapsed = (now - plot.last_water_at).total_seconds() / 60
            if elapsed < WATER_COOLDOWN_MINUTES:
                remaining = int(WATER_COOLDOWN_MINUTES - elapsed)
                return False, f"灌溉冷却中，还需{remaining}分钟"

        # 计算减少的时间
        remaining_time = (plot.mature_at - now).total_seconds()
        if remaining_time <= 0:
            plot.is_mature = True
            await uow.spirit_field_plots.update(plot)
            return True, f"地块{plot.plot_index}的作物已经成熟了!"

        reduce_seconds = remaining_time * WATER_TIME_REDUCE_PERCENT
        new_mature_at = plot.mature_at - timedelta(seconds=reduce_seconds)

        plot.mature_at = new_mature_at
        plot.water_count += 1
        plot.last_water_at = now

        # 检查灌溉后是否成熟
        if new_mature_at <= now:
            plot.is_mature = True

        await uow.spirit_field_plots.update(plot)

        crop = self.crop_manager.get_crop(plot.crop_id)
        crop_name = crop.name if crop else "未知作物"

        remaining = (new_mature_at - now).total_seconds()
        time_msg = "已成熟 ✅" if remaining <= 0 else f"还需 {format_duration(remaining)}"

        return True, (
            f"# 💧 灌溉\n***\n"
            f"{plot.plot_index}号 {crop_name} · 今日 {plot.water_count}/{WATER_MAX_PER_DAY} 次\n"
            f"距离成熟：{time_msg}"
        )

    # ==================== 一键灌溉 ====================

    async def water_all(self, uow: UnitOfWork, player_id: str) -> Tuple[bool, str]:
        """灌溉所有已种地块"""
        field = await uow.spirit_fields.get_by_player_id(player_id)
        if not field:
            return False, "你还没有灵田"

        planted = await uow.spirit_field_plots.get_planted_plots(field.id)
        now = datetime.now()

        watered_lines = []  # 成功浇水的详情
        matured_lines = []  # 浇水后直接成熟的
        skipped = 0

        for plot in planted:
            crop = self.crop_manager.get_crop(plot.crop_id)
            crop_name = crop.name if crop else f"未知"

            if plot.is_mature:
                skipped += 1
                continue
            if plot.water_count >= WATER_MAX_PER_DAY:
                skipped += 1
                continue
            if plot.last_water_at:
                elapsed = (now - plot.last_water_at).total_seconds() / 60
                if elapsed < WATER_COOLDOWN_MINUTES:
                    skipped += 1
                    continue

            remaining_time = (plot.mature_at - now).total_seconds()
            if remaining_time <= 0:
                plot.is_mature = True
                await uow.spirit_field_plots.update(plot)
                matured_lines.append(f"✅ {plot.plot_index}号 {crop_name} · 已成熟")
                continue

            reduce_seconds = remaining_time * WATER_TIME_REDUCE_PERCENT
            new_mature_at = plot.mature_at - timedelta(seconds=reduce_seconds)
            plot.mature_at = new_mature_at
            plot.water_count += 1
            plot.last_water_at = now

            reduced_str = format_duration(reduce_seconds)

            if new_mature_at <= now:
                plot.is_mature = True
                matured_lines.append(f"✅ {plot.plot_index}号 {crop_name} · 提前 {reduced_str} · 已成熟")
            else:
                new_remaining = (new_mature_at - now).total_seconds()
                watered_lines.append(f"💧 {plot.plot_index}号 {crop_name} · 提前 {reduced_str} · 剩 {format_duration(new_remaining)}")

            await uow.spirit_field_plots.update(plot)

        total_watered = len(watered_lines) + len(matured_lines)
        if total_watered == 0:
            return False, "没有可灌溉的地块（可能已达今日上限或在冷却中）"

        msg = "# 💧 一键浇水\n***\n"
        for line in watered_lines:
            msg += line + "\n"
        for line in matured_lines:
            msg += line + "\n"
        msg += "***\n"
        summary_parts = [f"浇水 {total_watered} 块"]
        if skipped:
            summary_parts.append(f"跳过 {skipped} 块")
        msg += " · ".join(summary_parts)

        return True, msg

    # ==================== 收菜 ====================

    async def harvest(self, uow: UnitOfWork, player_id: str) -> Tuple[bool, str]:
        """收获所有成熟作物"""
        field = await uow.spirit_fields.get_by_player_id(player_id)
        if not field:
            return False, "你还没有灵田"

        # 先更新成熟状态
        planted = await uow.spirit_field_plots.get_planted_plots(field.id)
        now = datetime.now()
        for plot in planted:
            if not plot.is_mature and plot.mature_at and plot.mature_at <= now:
                plot.is_mature = True
                await uow.spirit_field_plots.update(plot)

        mature_plots = await uow.spirit_field_plots.get_mature_plots(field.id)
        if not mature_plots:
            return False, "没有成熟的作物可以收菜"

        harvest_results: Dict[str, int] = {}  # {crop_name: total_quantity}
        seed_returns: Dict[str, int] = {}
        total_harvested = 0

        for plot in mature_plots:
            crop = self.crop_manager.get_crop(plot.crop_id)
            if not crop:
                continue

            actual_yield = max(0, plot.yield_quantity - plot.stolen_quantity)
            if actual_yield > 0:
                # 添加收获物到背包
                try:
                    await ItemInstance.add_item(uow.session, player_id, crop.harvest_item_id, actual_yield)
                    harvest_results[crop.name] = harvest_results.get(crop.name, 0) + actual_yield
                    total_harvested += actual_yield
                except ValueError as e:
                    logger.warning(f"收菜失败(背包满?): {e}")

            # 10%概率返还种子
            if random.random() < HARVEST_SEED_RETURN_CHANCE:
                try:
                    await ItemInstance.add_item(uow.session, player_id, crop.seed_id, 1)
                    seed_returns[crop.name] = seed_returns.get(crop.name, 0) + 1
                except ValueError:
                    pass

            # 清空地块
            plot.crop_id = None
            plot.planted_at = None
            plot.mature_at = None
            plot.is_mature = False
            plot.water_count = 0
            plot.last_water_at = None
            plot.yield_quantity = 0
            plot.stolen_quantity = 0
            await uow.spirit_field_plots.update(plot)

        # 更新统计
        field.total_harvested += total_harvested
        await uow.spirit_fields.update(field)

        # 构建结果消息
        msg = "# 🧺 收获\n***\n"
        for name, qty in harvest_results.items():
            msg += f"{name} × {qty}\n"

        if seed_returns:
            for name, qty in seed_returns.items():
                msg += f"🌱 种子返还：{name}种子 × {qty}\n"

        msg += f"***\n共 {total_harvested} 株 · 灵田累计收获 {field.total_harvested:,}"

        return True, msg

    # ==================== 查看灵田状态 ====================

    async def get_field_status(self, uow: UnitOfWork, player_id: str) -> Tuple[bool, str]:
        """查看灵田状态"""
        field = await uow.spirit_fields.get_by_player_id(player_id)
        if not field:
            return False, "你还没有灵田，使用【开辟灵田】创建"

        player = await uow.players.get_by_id(player_id)
        plots = await uow.spirit_field_plots.get_plots_by_field_id(field.id)
        now = datetime.now()

        # 更新成熟状态
        for plot in plots:
            if not plot.is_mature and plot.mature_at and plot.mature_at <= now:
                plot.is_mature = True
                await uow.spirit_field_plots.update(plot)

        mansion_level = getattr(player, 'mansion_level', 0)
        growth_bonus, yield_bonus = self.get_mansion_field_bonus(mansion_level)

        total_plots = FIELD_LEVEL_PLOTS[field.level]
        empty_count = sum(1 for p in plots if p.crop_id is None)
        mature_count = sum(1 for p in plots if p.is_mature and p.crop_id is not None)
        growing_count = sum(1 for p in plots if p.crop_id is not None and not p.is_mature)

        msg = (
            f"# 🌾 我的灵田 · {field.level}级\n***\n"
            f"灵壤 {total_plots} 块｜空闲 {empty_count} · 生长 {growing_count} · 成熟 {mature_count}\n"
        )

        if mansion_level > 0:
            msg += f"阴宅加成：成长 -{growth_bonus:.0f}% · 产量 +{yield_bonus:.0f}%\n"

        # 诡兽信息
        if field.guardian_beast_id:
            beast = self.beast_manager.get_beast_by_item_id(field.guardian_beast_id)
            if beast:
                # 饥饿判定与偷菜结算保持同一口径：宠物系统按饱食度，旧系统按喂食时间
                is_hungry = False
                guarding_pet = await uow.pets.get_guarding_pet(field.player_id)
                if guarding_pet:
                    is_hungry = guarding_pet.hunger < 20
                elif field.guardian_fed_at:
                    hours_since_fed = (now - field.guardian_fed_at).total_seconds() / 3600
                    is_hungry = hours_since_fed >= 24
                rate = beast.intercept_rate
                if is_hungry:
                    rate = int(rate * 0.5)
                status = " · 饥饿中" if is_hungry else ""
                msg += f"守田：{beast.name} · 拦截 {rate}%{status}\n"

        msg += "***\n"
        msg += self._render_plot_lines(plots, now)

        if field.total_harvested > 0 or field.total_stolen_from > 0:
            msg += f"***\n累计收获 {field.total_harvested:,} · 累计被偷 {field.total_stolen_from:,}"

        return True, msg

    def _render_plot_lines(self, plots, now) -> str:
        """渲染地块清单（灵田状态/拜访共用）"""
        lines = ""
        for plot in plots:
            if plot.crop_id is None:
                lines += f"▫️ {plot.plot_index}号 · 空置\n"
                continue

            crop = self.crop_manager.get_crop(plot.crop_id)
            crop_name = crop.name if crop else "未知"
            remaining = (plot.mature_at - now).total_seconds() if plot.mature_at else 0

            if plot.is_mature or remaining <= 0:
                actual = max(0, plot.yield_quantity - plot.stolen_quantity)
                lines += f"✅ {plot.plot_index}号 {crop_name} · 可收 {actual}\n"
            else:
                lines += f"🌱 {plot.plot_index}号 {crop_name} · 剩 {format_duration(remaining)} · 产量 {plot.yield_quantity}\n"
        return lines

    # ==================== 拜访他人灵田 ====================

    async def visit_field(self, uow: UnitOfWork, visitor_id: str, target_uid: int) -> Tuple[bool, str]:
        """查看他人灵田状态（不需要有成熟作物）"""
        visitor = await uow.players.get_by_id(visitor_id)
        if not visitor:
            return False, "玩家不存在"

        stmt = select(Player).where(
            Player.uid == target_uid,
            Player.server_id == visitor.server_id
        )
        result = await uow.session.execute(stmt)
        target = result.scalar_one_or_none()
        if not target:
            return False, f"未找到UID为{target_uid}的玩家"

        if target.id == visitor_id:
            return False, "请使用【灵田】查看自己的灵田"

        field = await uow.spirit_fields.get_by_player_id(target.id)
        if not field:
            return False, f"{target.nickname}还没有灵田"

        plots = await uow.spirit_field_plots.get_plots_by_field_id(field.id)
        now = datetime.now()

        # 更新成熟状态
        for plot in plots:
            if not plot.is_mature and plot.mature_at and plot.mature_at <= now:
                plot.is_mature = True
                await uow.spirit_field_plots.update(plot)

        total_plots = FIELD_LEVEL_PLOTS[field.level]
        empty_count = sum(1 for p in plots if p.crop_id is None)
        mature_count = sum(1 for p in plots if p.is_mature and p.crop_id is not None)
        growing_count = sum(1 for p in plots if p.crop_id is not None and not p.is_mature)

        msg = (
            f"# 🏡 {target.nickname} 的灵田 · {field.level}级\n***\n"
            f"灵壤 {total_plots} 块｜空闲 {empty_count} · 生长 {growing_count} · 成熟 {mature_count}\n"
        )

        # 诡兽信息
        if field.guardian_beast_id:
            beast = self.beast_manager.get_beast_by_item_id(field.guardian_beast_id)
            if beast:
                msg += f"⚠ 守田：{beast.name} · 拦截 {beast.intercept_rate}%\n"

        msg += "***\n"
        msg += self._render_plot_lines(plots, now)

        if mature_count > 0:
            msg += f"***\n有 {mature_count} 块已成熟，发送「偷菜 {target_uid}」下手"

        return True, msg
