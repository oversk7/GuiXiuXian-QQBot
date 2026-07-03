from datetime import date
from sqlalchemy import Integer, String, Date, JSON, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.mutable import MutableDict
from .db import Base

# 使用绝对导入避免相对导入问题
try:
    from config import config
except ImportError:
    # 如果在 alembic 环境中运行，使用相对导入
    from ..config import config

from .inventory import ItemEffectType

class ElixirUsageLog(Base):
    """记录玩家每日服用丹药数量及实际属性变动"""
    __tablename__ = "elixir_usage_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True)
    item_id: Mapped[str] = mapped_column(String(32))
    use_date: Mapped[Date] = mapped_column(Date, index=True, default=date.today)
    quantity: Mapped[int] = mapped_column(Integer, default=0)

    # 累计实际属性变动: {"attack": 50, "max_hp": -30, ...}
    # 每次使用时累加实际变动值，不依赖配置反推
    attribute_changes: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON),
        default=dict,
        server_default='{}',
        comment="累计实际属性变动JSON"
    )

    def get_attribute_bonus(self) -> dict:
        """获取该记录对应的属性加成

        优先使用 attribute_changes（精确记录），无记录时降级为配置反推（兼容旧数据）
        """
        if self.attribute_changes:
            return dict(self.attribute_changes)

        # 降级：旧数据无 attribute_changes，用配置 × 次数反推
        item_cfg = config.items_config["by_id"].get(self.item_id)
        if not item_cfg:
            return {}

        # 仅对永久属性类丹药做旧数据反推，避免将恢复类道具误计入永久属性
        if item_cfg.effect_type not in {ItemEffectType.BUFF, ItemEffectType.BUFF_PERCENT}:
            return {}

        effect_params = item_cfg.effect_params or {}
        bonus = {}
        for attr, value in effect_params.items():
            if isinstance(value, (int, float)):
                bonus[attr] = int(value) * self.quantity

        return bonus

    def record_changes(self, changes: dict):
        """累加一次使用的实际属性变动

        Args:
            changes: 本次变动 {"attack": 10, "max_hp": -30, ...}
        """
        if not self.attribute_changes:
            self.attribute_changes = {}
        for attr, delta in changes.items():
            if isinstance(delta, (int, float)) and delta != 0:
                self.attribute_changes[attr] = self.attribute_changes.get(attr, 0) + int(delta)

    @classmethod
    async def get_or_create_log(cls, session, player_id: str, item_id: str, use_date: date = None):
        """获取或创建当日使用记录"""
        if use_date is None:
            use_date = date.today()

        from sqlalchemy import select
        stmt = select(cls).where(
            cls.player_id == player_id,
            cls.item_id == item_id,
            cls.use_date == use_date
        )
        log = (await session.execute(stmt)).scalars().first()

        if not log:
            log = cls(
                player_id=player_id,
                item_id=item_id,
                use_date=use_date,
                quantity=0,
                attribute_changes={}
            )
            session.add(log)

        return log

    @classmethod
    async def get_total_attribute_changes(cls, session, player_id: str, exclude_item_ids: set = None) -> dict:
        """获取玩家所有丹药的累计属性变动总和

        Args:
            exclude_item_ids: 排除的账目 id 集合（如本轮回有效的 REBIRTH_VOLATILE_LEDGER_IDS）
        """
        from sqlalchemy import select
        stmt = select(cls).where(cls.player_id == player_id)
        logs = (await session.execute(stmt)).scalars().all()

        total = {}
        for log in logs:
            if exclude_item_ids and log.item_id in exclude_item_ids:
                continue
            for attr, value in log.get_attribute_bonus().items():
                total[attr] = total.get(attr, 0) + value
        return total