from __future__ import annotations

from sqlalchemy import String, Integer, BigInteger, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class PvpLog(Base):
    """荒野/诡域PVP日志

    仅记录非安全区（真实死斗）产生的战斗日志，用于玩家查询：
    - 谁在何时何地对谁发起攻击
    - 双方伤害与胜负
    - 掉落概要
    """

    __tablename__ = "pvp_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 时间戳（UNIX 秒）
    ts: Mapped[int] = mapped_column(BigInteger, index=True, comment="时间戳(秒)")

    # 地区与坐标
    region: Mapped[str] = mapped_column(String(32), default="", server_default="", comment="区域标识")
    x: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="坐标X")
    y: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="坐标Y")

    # 参与者（保存快照，便于历史回看）
    attacker_id: Mapped[str] = mapped_column(String(32), index=True)
    defender_id: Mapped[str] = mapped_column(String(32), index=True)
    attacker_uid: Mapped[int] = mapped_column(Integer, default=0, server_default="0", index=True)
    defender_uid: Mapped[int] = mapped_column(Integer, default=0, server_default="0", index=True)
    attacker_name: Mapped[str] = mapped_column(String(32), default="", server_default="")
    defender_name: Mapped[str] = mapped_column(String(32), default="", server_default="")

    # 战斗信息
    battle_type: Mapped[str] = mapped_column(String(8), default="荒野", server_default="荒野", comment="荒野/诡域")
    attacker_victory: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="进攻方是否胜利 1/0")
    attacker_damage: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    defender_damage: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # 掉落概要（多行文本，展示给双方）
    drop_summary: Mapped[str] = mapped_column(Text, default="")


Index("idx_pvp_defender_ts", PvpLog.defender_uid, PvpLog.ts)
Index("idx_pvp_attacker_ts", PvpLog.attacker_uid, PvpLog.ts)

