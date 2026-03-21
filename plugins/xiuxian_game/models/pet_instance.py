"""宠物实例模型"""
from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, Boolean, ForeignKey, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class PetInstance(Base):
    """宠物实例

    每只诡兽为一条记录，玩家可拥有多只，但只能激活1只伴侣。
    """
    __tablename__ = "pet_instance"
    __table_args__ = (
        Index("ix_pet_instance_player_active", "player_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    player_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("player.id"), index=True, comment="所属玩家ID"
    )
    beast_id: Mapped[str] = mapped_column(
        String(32), comment="诡兽种族ID(对应pet_config.yaml的beast_id)"
    )
    nickname: Mapped[str] = mapped_column(
        String(64), comment="玩家给宠物起的昵称"
    )

    # 养成属性
    level: Mapped[int] = mapped_column(Integer, default=1, server_default="1", comment="宠物等级")
    experience: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="当前经验值")
    affection: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="好感度(0-1000)")
    mood: Mapped[int] = mapped_column(Integer, default=80, server_default="80", comment="心情值(0-100)")
    hunger: Mapped[int] = mapped_column(Integer, default=100, server_default="100", comment="饱食度(0-100)")

    # 战斗属性加成（随等级成长）
    bonus_attack: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="攻击加成")
    bonus_defense: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="防御加成")
    bonus_hp: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="生命加成")
    bonus_crit_rate: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", comment="暴击率加成")
    bonus_dodge_rate: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", comment="闪避率加成")

    # 状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", comment="是否为当前伴侣")
    is_guarding: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", comment="是否正在守田")
    is_transformed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", comment="是否已化形")
    evolved_rarity: Mapped[str] = mapped_column(
        String(16), default="", server_default="",
        comment="进化后的稀有度(空=使用种族默认)"
    )
    transform_gender: Mapped[str] = mapped_column(
        String(8), default="", server_default="",
        comment="化形性别(male/female, 空=未选择)"
    )

    # 饰品（JSON存储已装备饰品ID列表）
    accessories: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="已装备饰品 {slot: accessory_id}")

    # 每日喂食计数（递减收益）
    daily_feed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="当日怨念喂食次数")
    daily_feed_date: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="喂食计数日期(YYYY-MM-DD)")

    # 时间戳
    last_fed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="上次喂食时间")
    last_interact_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="上次互动时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="获得时间")
