from datetime import datetime, timedelta
from sqlalchemy import Integer, String, DateTime, Float, Boolean, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from .db import Base
import random
import json
from typing import Tuple, Dict

class AlchemyRecord(Base):
    """炼丹记录 - 简化版本，基于时间差计算"""

    __tablename__ = "alchemy_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), index=True)
    furnace_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("inventory.id", ondelete="SET NULL"))

    # 配方信息
    recipe_key: Mapped[str] = mapped_column(String(64))
    produce_item_id: Mapped[str] = mapped_column(String(32))
    produce_per: Mapped[int] = mapped_column(Integer)  # 每炉产出数量

    # 炼丹参数
    qty: Mapped[int] = mapped_column(Integer)  # 炉数
    success_rate: Mapped[float] = mapped_column(Float)  # 成功率
    duration_minutes: Mapped[int] = mapped_column(Integer)  # 总耗时(分钟)
    materials_used: Mapped[str] = mapped_column(Text, default="{}")  # 使用的材料JSON格式 {"item_id": quantity}

    # 时间记录
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())
    claimed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    def is_finished(self) -> bool:
        """检查是否已完成"""
        elapsed = datetime.now() - self.started_at
        return elapsed.total_seconds() >= self.duration_minutes * 60

    def get_remaining_seconds(self) -> int:
        """获取剩余秒数，如果已完成返回0"""
        if self.is_finished():
            return 0
        elapsed = datetime.now() - self.started_at
        total_seconds = self.duration_minutes * 60
        return max(0, int(total_seconds - elapsed.total_seconds()))

    def calculate_result(self) -> Tuple[int, int]:
        """计算炼丹结果 - 返回(成功炉数, 总产出数量)"""
        if not self.is_finished():
            return 0, 0

        # 使用记录ID作为随机种子，确保结果一致性
        rng = random.Random(self.id)
        success_count = 0
        for _ in range(self.qty):
            if rng.random() < self.success_rate:
                success_count += 1

        total_produce = success_count * self.produce_per
        return success_count, total_produce

    def get_finish_time(self) -> datetime:
        """获取完成时间"""
        if not self.started_at:
            self.started_at = datetime.now()
        return self.started_at + timedelta(minutes=self.duration_minutes)

    def get_materials_dict(self) -> Dict[str, int]:
        """获取使用的材料字典"""
        try:
            return json.loads(self.materials_used or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_materials_dict(self, materials: Dict[str, int]):
        """设置使用的材料字典"""
        self.materials_used = json.dumps(materials)