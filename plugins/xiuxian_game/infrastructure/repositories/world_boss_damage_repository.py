"""
世界BOSS伤害记录仓储实现

提供世界BOSS伤害记录（WorldBossDamage）的数据访问抽象
"""

from typing import Optional, List, Tuple
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from ...domain.repositories.base import IRepository
from ...models.world_boss import WorldBossDamage
from ...models.player import Player


class WorldBossDamageRepository(IRepository[WorldBossDamage]):
    """世界BOSS伤害记录仓储实现"""

    def __init__(self, session: AsyncSession):
        """
        初始化世界BOSS伤害记录仓储

        Args:
            session: 数据库会话
        """
        self._session = session

    async def get_by_id(self, damage_id: int) -> Optional[WorldBossDamage]:
        """
        根据ID获取伤害记录

        Args:
            damage_id: 伤害记录ID

        Returns:
            伤害记录实例，不存在返回None
        """
        stmt = select(WorldBossDamage).where(WorldBossDamage.id == damage_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_cycle_and_player(
        self, cycle_id: int, player_id: str
    ) -> Optional[WorldBossDamage]:
        """
        根据周期和玩家获取伤害记录

        Args:
            cycle_id: 周期ID
            player_id: 玩家ID

        Returns:
            伤害记录实例，不存在返回None

        对应原代码:
            world_boss/service.py Line 311-316（查询伤害记录）
        """
        stmt = select(WorldBossDamage).where(
            and_(
                WorldBossDamage.cycle_id == cycle_id,
                WorldBossDamage.player_id == player_id
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(
        self, cycle_id: int, player_id: str
    ) -> WorldBossDamage:
        """
        获取或创建伤害记录

        Args:
            cycle_id: 周期ID
            player_id: 玩家ID

        Returns:
            伤害记录实例（已存在或新创建）

        对应原代码:
            world_boss/service.py Line 309-325（_get_or_create_damage_record方法）
        """
        existing = await self.get_by_cycle_and_player(cycle_id, player_id)
        if existing:
            return existing

        # 创建新记录
        record = WorldBossDamage(
            cycle_id=cycle_id,
            player_id=player_id,
            total_damage=0,
            last_attack_ts=0,
            attacks_today=0,
            attacks_reset_date=""
        )
        self._session.add(record)
        await self._session.flush()  # 刷新以获取生成的ID
        return record

    async def get_by_cycle(self, cycle_id: int) -> List[WorldBossDamage]:
        """
        获取周期内的所有伤害记录

        Args:
            cycle_id: 周期ID

        Returns:
            伤害记录列表

        对应原代码:
            world_boss/service.py Line 108-110（获取周期内所有记录）
        """
        stmt = select(WorldBossDamage).where(WorldBossDamage.cycle_id == cycle_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_ranking(
        self, cycle_id: int, limit: int = 50, server_id: int | None = None
    ) -> List[Tuple[WorldBossDamage, str, int, int]]:
        """
        获取排行榜（按伤害降序，预加载玩家信息；server_id 限定区服）

        Returns:
            排行榜列表 [(WorldBossDamage, nickname, uid, reincarnation_level), ...]
        """
        stmt = (
            select(WorldBossDamage, Player.nickname, Player.uid, Player.reincarnation_level)
            .join(Player, WorldBossDamage.player_id == Player.id)
            .where(WorldBossDamage.cycle_id == cycle_id)
        )
        if server_id is not None:
            stmt = stmt.where(Player.server_id == server_id)
        stmt = stmt.order_by(WorldBossDamage.total_damage.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return [(damage, nickname, uid, reincarnation_level) for damage, nickname, uid, reincarnation_level in result]

    async def get_summary(self, cycle_id: int, server_id: int) -> Tuple[int, int]:
        """本期本区的参与人数和总伤害（只统计伤害大于 0 的记录）"""
        stmt = (
            select(func.count(), func.coalesce(func.sum(WorldBossDamage.total_damage), 0))
            .join(Player, WorldBossDamage.player_id == Player.id)
            .where(
                WorldBossDamage.cycle_id == cycle_id,
                WorldBossDamage.total_damage > 0,
                Player.server_id == server_id,
            )
        )
        count, total = (await self._session.execute(stmt)).one()
        return int(count), int(total)

    async def get_player_names(self, player_ids: List[str]) -> dict[str, Tuple[str, int]]:
        """按主键批量查玩家昵称和 UID：{player_id: (nickname, uid)}"""
        if not player_ids:
            return {}
        stmt = select(Player.id, Player.nickname, Player.uid).where(Player.id.in_(player_ids))
        return {player_id: (nickname, uid) for player_id, nickname, uid in await self._session.execute(stmt)}

    async def update_damage(
        self, cycle_id: int, player_id: str, damage_delta: int
    ) -> WorldBossDamage:
        """
        增加伤害记录

        Args:
            cycle_id: 周期ID
            player_id: 玩家ID
            damage_delta: 增加的伤害量

        Returns:
            更新后的伤害记录

        对应原代码:
            world_boss/service.py Line 510（更新伤害）
        """
        record = await self.get_or_create(cycle_id, player_id)
        record.total_damage += damage_delta
        self._session.add(record)
        return record

    async def update_attack_info(
        self,
        cycle_id: int,
        player_id: str,
        attack_ts: int,
        attacks_today: int,
        attacks_reset_date: str
    ) -> WorldBossDamage:
        """
        更新攻击信息（时间戳、今日次数、重置日期）

        Args:
            cycle_id: 周期ID
            player_id: 玩家ID
            attack_ts: 攻击时间戳
            attacks_today: 今日攻击次数
            attacks_reset_date: 重置日期

        Returns:
            更新后的伤害记录

        对应原代码:
            world_boss/service.py Line 511-513（更新攻击状态）
        """
        record = await self.get_or_create(cycle_id, player_id)
        record.last_attack_ts = attack_ts
        record.attacks_today = attacks_today
        record.attacks_reset_date = attacks_reset_date
        self._session.add(record)
        return record

    async def get_player_total_damage(self, player_id: str) -> int:
        """
        获取玩家所有周期的总伤害

        Args:
            player_id: 玩家ID

        Returns:
            总伤害量

        Note:
            用于玩家统计信息展示
        """
        stmt = select(func.sum(WorldBossDamage.total_damage)).where(
            WorldBossDamage.player_id == player_id
        )
        result = await self._session.execute(stmt)
        total = result.scalar()
        return int(total) if total is not None else 0

    async def add(self, damage: WorldBossDamage) -> WorldBossDamage:
        """
        添加伤害记录

        Args:
            damage: 伤害记录实例

        Returns:
            添加后的记录（包含生成的ID）
        """
        self._session.add(damage)
        await self._session.flush()
        return damage

    async def update(self, damage: WorldBossDamage) -> WorldBossDamage:
        """
        更新伤害记录

        Args:
            damage: 伤害记录实例

        Returns:
            更新后的记录
        """
        self._session.add(damage)
        return damage

    async def delete(self, damage_id: int) -> bool:
        """
        删除伤害记录

        Args:
            damage_id: 伤害记录ID

        Returns:
            是否成功删除
        """
        damage = await self.get_by_id(damage_id)
        if damage:
            await self._session.delete(damage)
            return True
        return False

    async def exists(self, damage_id: int) -> bool:
        """
        检查伤害记录是否存在

        Args:
            damage_id: 伤害记录ID

        Returns:
            是否存在
        """
        damage = await self.get_by_id(damage_id)
        return damage is not None

    async def count(self) -> int:
        """
        获取伤害记录总数

        Returns:
            记录总数
        """
        stmt = select(WorldBossDamage)
        result = await self._session.execute(stmt)
        return len(result.scalars().all())
