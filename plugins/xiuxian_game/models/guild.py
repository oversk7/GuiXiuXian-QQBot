from sqlalchemy import Integer, BigInteger, String, DateTime, Boolean, func, ForeignKey, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base
from enum import Enum as PyEnum
from datetime import datetime


class GuildPosition(str, PyEnum):
    """公会职位枚举"""
    PRESIDENT = "PRESIDENT"      # 会长
    VICE_PRESIDENT = "VICE_PRESIDENT"  # 副会长
    CORE_MEMBER = "CORE_MEMBER"  # 核心成员
    MEMBER = "MEMBER"            # 普通成员


class Guild(Base):
    __tablename__ = "guild"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    server_id: Mapped[int] = mapped_column(Integer, default=1, server_default='1', index=True, comment="所属区服ID")
    name: Mapped[str] = mapped_column(String(32), comment="公会名称")
    president_id: Mapped[str] = mapped_column(String(32), comment="会长的玩家平台ID")
    level: Mapped[int] = mapped_column(Integer, default=1, server_default='1', comment="公会等级")
    exp: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0', comment="公会经验/活跃度")
    treasury: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0', comment="公会资金库")
    notice: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="公会公告")
    base_x: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="公会基地X坐标")
    base_y: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="公会基地Y坐标")
    territory_range: Mapped[int] = mapped_column(Integer, default=3, server_default='3', comment="势力范围（以基地为中心的正方形边长）")
    boss_level: Mapped[int] = mapped_column(Integer, default=1, server_default='1', comment="镇诡凶戾度")
    boss_week_summons: Mapped[int] = mapped_column(Integer, default=0, server_default='0', comment="今日开坛次数（列名沿用week为历史原因）")
    boss_week_key: Mapped[str] = mapped_column(String(10), default="", server_default="", comment="开坛计数所属日期键YYYY-MM-DD")
    resentment_pool: Mapped[int] = mapped_column(BigInteger, default=0, server_default='0', comment="公会怨念池（成员献怨累积，血祭开坛消耗）")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")

    # 关联关系
    members: Mapped[list["GuildMember"]] = relationship("GuildMember", back_populates="guild", cascade="all, delete-orphan")
    buildings: Mapped[list["GuildBuilding"]] = relationship("GuildBuilding", back_populates="guild", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("server_id", "name", name="uq_guild_server_name"),
    )


class GuildMember(Base):
    """公会成员职位表"""
    __tablename__ = "guild_member"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer, ForeignKey("guild.id"), comment="公会ID")
    player_id: Mapped[str] = mapped_column(String(32), comment="玩家ID")
    position: Mapped[GuildPosition] = mapped_column(SQLEnum(GuildPosition), default=GuildPosition.MEMBER, comment="职位")
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), comment="加入时间")

    # 关联关系
    guild: Mapped["Guild"] = relationship("Guild", back_populates="members")

    # 唯一约束：一个玩家只能在一个公会中
    __table_args__ = (
        {"comment": "公会成员职位表"}
    )


class BuildingType(str, PyEnum):
    """公会建筑类型枚举"""
    EXPERIENCE_SHRINE = "EXPERIENCE_SHRINE"  # 经验神龛 - 提升经验转换倍率
    TREASURY_VAULT = "TREASURY_VAULT"        # 资金金库 - 增加资金上限
    TRAINING_GROUND = "TRAINING_GROUND"      # 训练场 - 提升成员修为加成
    SPIRIT_TOWER = "SPIRIT_TOWER"           # 灵塔 - 提升公会整体属性
    DEFENSE_WALL = "DEFENSE_WALL"           # 防御城墙 - 提升公会防御力
    TELEPORT_ARRAY = "TELEPORT_ARRAY"       # 传送阵 - 允许成员传送到公会基地
    ALCHEMY_ROOM = "ALCHEMY_ROOM"           # 丹房 - 随机产出低级丹药
    GUILD_WAREHOUSE = "GUILD_WAREHOUSE"     # 公会仓库 - 存放诡异道具
    ARTIFACT_FORGE = "ARTIFACT_FORGE"       # 铸器坊 - 允许在公会基地锻造装备
    REFINING_PAVILION = "REFINING_PAVILION" # 淬灵台 - 提升公会基地装备升阶


class GuildBuilding(Base):
    """公会建筑表"""
    __tablename__ = "guild_building"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer, ForeignKey("guild.id"), comment="公会ID")
    building_type: Mapped[BuildingType] = mapped_column(SQLEnum(BuildingType), comment="建筑类型")
    level: Mapped[int] = mapped_column(Integer, default=1, server_default='1', comment="建筑等级")
    plot_x: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="公会基地布局X坐标")
    plot_y: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="公会基地布局Y坐标")
    built_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), comment="建造时间")

    # 关联关系
    guild: Mapped["Guild"] = relationship("Guild", back_populates="buildings")

    __table_args__ = (
        {"comment": "公会建筑表"}
    )


class GuildWarehouseItem(Base):
    """公会仓库物品表"""
    __tablename__ = "guild_warehouse_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer, ForeignKey("guild.id"), comment="公会ID")
    item_id: Mapped[str] = mapped_column(String(32), comment="物品ID")
    quantity: Mapped[int] = mapped_column(Integer, default=1, comment="数量")
    deposited_by: Mapped[str] = mapped_column(String(32), comment="存入者玩家ID")
    deposited_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), comment="存入时间")

    __table_args__ = (
        {"comment": "公会仓库物品表"}
    )


class GuildAlchemyProduction(Base):
    """公会丹房产出记录表"""
    __tablename__ = "guild_alchemy_production"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer, ForeignKey("guild.id"), comment="公会ID")
    item_id: Mapped[str] = mapped_column(String(32), comment="产出的丹药ID")
    quantity: Mapped[int] = mapped_column(Integer, default=1, comment="数量")
    produced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), comment="产出时间")
    claimed: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已被领取")
    claimed_by: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="领取者玩家ID")
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="领取时间")

    __table_args__ = (
        {"comment": "公会丹房产出记录表"}
    )


class WarehouseLogType(str, PyEnum):
    """仓库操作类型枚举"""
    DEPOSIT = "DEPOSIT"      # 存入
    WITHDRAW = "WITHDRAW"    # 取出


class GuildWarehouseLog(Base):
    """公会仓库操作日志表"""
    __tablename__ = "guild_warehouse_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer, ForeignKey("guild.id"), comment="公会ID")
    player_id: Mapped[str] = mapped_column(String(32), comment="操作者玩家ID")
    player_name: Mapped[str] = mapped_column(String(32), default="", server_default="", comment="操作者昵称（冗余存储，避免查询）")
    operation: Mapped[WarehouseLogType] = mapped_column(SQLEnum(WarehouseLogType), comment="操作类型")
    item_id: Mapped[str] = mapped_column(String(32), comment="物品ID")
    item_name: Mapped[str] = mapped_column(String(64), default="", server_default="", comment="物品名称（冗余存储）")
    quantity: Mapped[int] = mapped_column(Integer, comment="数量")
    operated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), comment="操作时间")

    __table_args__ = (
        {"comment": "公会仓库操作日志表"}
    )


class GuildTeleportLog(Base):
    """公会传送记录表"""
    __tablename__ = "guild_teleport_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(Integer, ForeignKey("guild.id"), comment="公会ID")
    player_id: Mapped[str] = mapped_column(String(32), comment="传送者玩家ID")
    from_x: Mapped[int] = mapped_column(Integer, comment="传送前X坐标")
    from_y: Mapped[int] = mapped_column(Integer, comment="传送前Y坐标")
    to_x: Mapped[int] = mapped_column(Integer, comment="传送后X坐标")
    to_y: Mapped[int] = mapped_column(Integer, comment="传送后Y坐标")
    teleported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), comment="传送时间")

    __table_args__ = (
        {"comment": "公会传送记录表"}
    )
