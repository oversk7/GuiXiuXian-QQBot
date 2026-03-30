"""
统一属性计算器

提供单一职责的属性计算入口，组合多个属性来源
"""

from typing import List, Optional
import asyncio

from .interfaces import IAttributeSource, AttributeBonus, AttributeBreakdown


class AttributeCalculator:
    """
    统一属性计算器

    职责:
    1. 管理多个属性来源（装备、buff、丹药、VIP等）
    2. 并发计算各来源加成
    3. 汇总最终属性

    设计模式: 组合模式 + 策略模式
    """

    def __init__(self):
        self._sources: List[IAttributeSource] = []

    def add_source(self, source: IAttributeSource):
        """
        添加属性来源

        Args:
            source: 实现IAttributeSource接口的属性来源
        """
        self._sources.append(source)

    async def calculate_final_attributes(
        self,
        player,
        session,
        include_breakdown: bool = False
    ) -> AttributeBonus | AttributeBreakdown:
        """
        计算最终属性

        Args:
            player: Player实例
            session: 数据库会话
            include_breakdown: 是否返回详细分解

        Returns:
            AttributeBonus: 如果include_breakdown=False
            AttributeBreakdown: 如果include_breakdown=True
        """
        # 基础属性（包含丹药持久化的加成）
        base = self._calculate_base(player)

        if not self._sources:
            # 没有其他来源，直接返回基础属性
            if include_breakdown:
                return AttributeBreakdown(base=base, total=base)
            return base

        # 顺序计算各来源加成（避免session并发问题）
        # 注意：不能用asyncio.gather，因为多个source共享同一个session
        sources_bonuses = []
        for source in self._sources:
            bonus = await source.calculate_bonus(player, session)
            sources_bonuses.append(bonus)

        # 汇总（只累加未持久化的来源，已持久化的来源已经在base中了）
        # 例如：装备加成通过recalc写入player属性，buff加成是临时的
        total = base
        for i, source in enumerate(self._sources):
            if not source.is_persisted:
                total = total + sources_bonuses[i]

        if not include_breakdown:
            return total

        # 构建详细分解（假设来源顺序为: 装备、buff、丹药、VIP）
        breakdown = AttributeBreakdown(base=base)

        for i, source in enumerate(self._sources):
            bonus = sources_bonuses[i]
            source_name = source.source_name

            if "equipment" in source_name.lower() or "装备" in source_name:
                breakdown.equipment = bonus
            elif "buff" in source_name.lower():
                breakdown.buff = bonus
            elif "elixir" in source_name.lower() or "丹药" in source_name:
                breakdown.elixir = bonus
            elif "vip" in source_name.lower():
                breakdown.vip = bonus

        breakdown.total = total
        return breakdown

    def _calculate_base(self, player) -> AttributeBonus:
        """
        读取玩家当前属性作为base

        重要：base已经包含了所有持久化的加成（is_persisted=True的来源）
        - 装备加成：通过recalc_equipment_attributes写入player属性
        - 丹药加成：持久化的丹药加成也在player属性中

        因此，在calculate_final_attributes中，只需要累加临时加成（is_persisted=False）
        """
        return AttributeBonus(
            attack=getattr(player, 'attack', 0),
            defense=getattr(player, 'defense', 0),
            hp=getattr(player, 'hp', 0),
            max_hp=getattr(player, 'max_hp', 0),
            mp=getattr(player, 'mp', 0),
            max_mp=getattr(player, 'max_mp', 0),
            cultivation=getattr(player, 'cultivation', 0),
            realm=getattr(player, 'realm', 0),
            # Player模型字段名与AttributeBonus字段名的映射：
            # Player.critical_rate (int, 百分比) → AttributeBonus.crit_rate
            # Player.critical_power (int) → AttributeBonus.crit_damage
            # Player.dodge_rate (int, 百分比) → AttributeBonus.dodge_rate
            # Player.accuracy_rate (int, 百分比) → AttributeBonus.accuracy
            crit_rate=getattr(player, 'critical_rate', 0.0),
            crit_damage=getattr(player, 'critical_power', 0.0),
            dodge_rate=getattr(player, 'dodge_rate', 0.0),
            accuracy=getattr(player, 'accuracy_rate', 0.0),
            agility=getattr(player, 'agility', 0),
            luck=getattr(player, 'luck', 0),
            gold_multiplier=getattr(player, 'gold_multiplier', 1.0),
            exp_multiplier=getattr(player, 'exp_multiplier', 1.0),
        )

    async def calculate_simple(self, player, session) -> AttributeBonus:
        """
        简化接口: 计算最终属性（不含详细分解）

        这是最常用的接口，用于战斗、技能判定等场景
        """
        return await self.calculate_final_attributes(
            player,
            session,
            include_breakdown=False
        )

