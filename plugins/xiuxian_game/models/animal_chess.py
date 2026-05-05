from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class AnimalChessRoomStatus(str, Enum):
    """斗兽棋房间状态。"""

    WAITING = "waiting"
    BETTING = "betting"
    PLAYING = "playing"
    FINISHED = "finished"


class AnimalChessGameStatus(str, Enum):
    """斗兽棋游戏状态。"""

    PLAYING = "playing"
    FINISHED = "finished"


class AnimalChessRoom(Base):
    """斗兽棋房间表。"""

    __tablename__ = "animal_chess_room"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="房间ID")
    group_id: Mapped[str] = mapped_column(String(32), index=True, comment="绑定QQ群ID")
    creator_id: Mapped[str] = mapped_column(String(32), index=True, comment="房主玩家ID")
    player1_id: Mapped[str] = mapped_column(String(32), index=True, comment="蓝方玩家ID")
    player2_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True, comment="红方玩家ID")
    status: Mapped[str] = mapped_column(
        String(16),
        default=AnimalChessRoomStatus.WAITING.value,
        server_default=AnimalChessRoomStatus.WAITING.value,
        comment="房间状态",
    )
    player1_gold_bet: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="蓝方金币押注")
    player2_gold_bet: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="红方金币押注")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    def is_full(self) -> bool:
        return self.player2_id is not None

    def is_player_in_room(self, player_id: str) -> bool:
        return player_id in (self.player1_id, self.player2_id)

    def get_opponent_id(self, player_id: str) -> str | None:
        if self.player1_id == player_id:
            return self.player2_id
        if self.player2_id == player_id:
            return self.player1_id
        return None


class AnimalChessGame(Base):
    """斗兽棋游戏状态表。"""

    __tablename__ = "animal_chess_game"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(String(32), index=True, comment="房间ID")
    status: Mapped[str] = mapped_column(
        String(16),
        default=AnimalChessGameStatus.PLAYING.value,
        server_default=AnimalChessGameStatus.PLAYING.value,
        comment="游戏状态",
    )
    current_player_id: Mapped[str] = mapped_column(String(32), index=True, comment="当前行动玩家ID")
    board_state: Mapped[str] = mapped_column(Text, comment="棋盘状态JSON")
    move_history: Mapped[str] = mapped_column(Text, default="[]", comment="走子历史JSON")
    turn_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1", comment="当前回合数")
    winner_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True, comment="获胜玩家ID")
    last_move: Mapped[str | None] = mapped_column(Text, nullable=True, comment="最近一步JSON")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")


class AnimalChessBet(Base):
    """斗兽棋旁观者下注表。"""

    __tablename__ = "animal_chess_bet"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(String(32), index=True, comment="房间ID")
    bettor_id: Mapped[str] = mapped_column(String(32), index=True, comment="下注者玩家ID")
    target_player_id: Mapped[str] = mapped_column(String(32), index=True, comment="支持玩家ID")
    gold_amount: Mapped[int] = mapped_column(Integer, default=0, server_default="0", comment="下注金额")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="下注时间")
