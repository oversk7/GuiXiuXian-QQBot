from datetime import datetime
from sqlalchemy import Integer, String, DateTime, JSON, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base
from .player import Player
from enum import Enum as PyEnum

class EquipSlot(str, PyEnum):
    """装备槽枚举。目前仅占位，后续可按头/身/武器等扩展"""
    HEAD = "HEAD"
    BODY = "BODY"
    WEAPON = "WEAPON"
    ACCESSORY = "ACCESSORY"

class EquipmentInstance(Base):
    """玩家持有的单件装备实例（不可叠放）。

    - template_id 对应 items.yaml 中的 item_id
    - durability 当前耐久度，耗尽后即销毁
    - extra_attrs 预留，用于后续强化/洗练产生的附加属性，JSON 字段
    """

    __tablename__ = "equipment_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(String(32), ForeignKey("player.id"), index=True, comment="拥有者平台 ID")
    template_id: Mapped[str] = mapped_column(String(32), index=True, comment="items.yaml 内物品模板 ID")
    durability: Mapped[int] = mapped_column(Integer, default=0, comment="当前耐久度")
    equipped: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", comment="是否已穿戴")
    on_market: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", comment="是否已上架交易市场")
    extra_attrs: Mapped[dict] = mapped_column(JSON, default=dict, comment="强化等附加属性")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="获得时间")

    # ORM 关系，方便访问
    owner: Mapped["Player"] = relationship("Player", backref="equip_instances")

    # -----------------------------
    #   帮助属性 / 方法
    # -----------------------------

    @property
    def template(self):
        """返回 YAML 中的 ItemConfig 模板"""
        from ..config import config
        return config.items_config["by_id"].get(self.template_id)

    def apply_attr_bonus(self, attrs: dict):
        """将此装备的属性加成应用到 attrs（就地修改）。
        attrs: 形如 {"hp": 100, "attack": 10} 的玩家基础属性 dict
        """
        tpl = self.template
        if not tpl or not self.equipped:
            return
        # 固定值
        key_map = {"hp": "max_hp", "mp": "max_mp"}
        for k, v in (tpl.attr_bonus or {}).items():
            key = key_map.get(k, k)
            attrs[key] = attrs.get(key, 0) + int(v)
        # 百分比
        for k, r in (tpl.attr_ratio or {}).items():
            key = key_map.get(k, k)
            attrs[key] = int(attrs.get(key, 0) * (1 + float(r)))
        # 额外属性（强化）
        for k, v in (self.extra_attrs or {}).items():
            if k.startswith("_"):
                continue  # 跳过内部字段，如 _persist_bonus
            if not isinstance(v, (int, float)):
                continue
            attrs[k] = attrs.get(k, 0) + int(v)

        # 叠加持久化 bonus（如果存在）
        persist = (self.extra_attrs or {}).get("_persist_bonus", {})
        for k, v in persist.items():
            if not isinstance(v, (int, float)):
                continue
            attrs[k] = attrs.get(k, 0) + int(v)
        return attrs

    def lose_durability(self, amount: int = 1) -> bool:
        """扣除耐久。返回 True 如果装备已损坏并应销毁。"""
        self.durability = max(0, self.durability - amount)
        return self.durability == 0 