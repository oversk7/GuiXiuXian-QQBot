from sqlalchemy import String, Integer, Boolean, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from enum import Enum
from .db import Base


class RoomStatus(Enum):
    """房间状态枚举"""
    WAITING = "waiting"      # 等待玩家加入
    BETTING = "betting"      # 设置筹码阶段
    PLAYING = "playing"      # 游戏进行中
    FINISHED = "finished"    # 游戏结束


class GameStatus(Enum):
    """游戏状态枚举"""
    LOADING = "loading"      # 装弹阶段
    PLAYING = "playing"      # 游戏进行中
    FINISHED = "finished"    # 游戏结束


class RussianRouletteRoom(Base):
    """恶魔轮盘赌房间表"""
    __tablename__ = "russian_roulette_room"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="房间ID")
    group_id: Mapped[str] = mapped_column(String(32), index=True, comment="绑定的QQ群ID")
    creator_id: Mapped[str] = mapped_column(String(32), index=True, comment="房主玩家ID")
    player1_id: Mapped[str] = mapped_column(String(32), index=True, comment="玩家1 ID")
    player2_id: Mapped[str] = mapped_column(String(32), nullable=True, index=True, comment="玩家2 ID")
    
    # 房间状态
    status: Mapped[str] = mapped_column(String(16), default=RoomStatus.WAITING.value, comment="房间状态")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    
    # 筹码设置
    player1_gold_bet: Mapped[int] = mapped_column(Integer, default=0, comment="玩家1金币投注")
    player2_gold_bet: Mapped[int] = mapped_column(Integer, default=0, comment="玩家2金币投注")
    player1_items_bet: Mapped[str] = mapped_column(Text, nullable=True, comment="玩家1道具投注(JSON)")
    player2_items_bet: Mapped[str] = mapped_column(Text, nullable=True, comment="玩家2道具投注(JSON)")
    
    # 游戏设置
    max_hp: Mapped[int] = mapped_column(Integer, default=3, comment="最大血量")
    
    def is_full(self) -> bool:
        """检查房间是否已满"""
        return self.player2_id is not None
    
    def get_opponent_id(self, player_id: str) -> str:
        """获取对手ID"""
        if self.player1_id == player_id:
            return self.player2_id
        elif self.player2_id == player_id:
            return self.player1_id
        return None
    
    def is_player_in_room(self, player_id: str) -> bool:
        """检查玩家是否在房间中"""
        return player_id in [self.player1_id, self.player2_id]


class RussianRouletteGame(Base):
    """恶魔轮盘赌游戏状态表"""
    __tablename__ = "russian_roulette_game"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[str] = mapped_column(String(32), index=True, comment="房间ID")
    
    # 游戏状态
    status: Mapped[str] = mapped_column(String(16), default=GameStatus.LOADING.value, comment="游戏状态")
    current_round: Mapped[int] = mapped_column(Integer, default=1, comment="当前回合数")
    current_player_id: Mapped[str] = mapped_column(String(32), comment="当前行动玩家ID")
    
    # 玩家血量
    player1_hp: Mapped[int] = mapped_column(Integer, default=3, comment="玩家1血量")
    player2_hp: Mapped[int] = mapped_column(Integer, default=3, comment="玩家2血量")
    
    # 霰弹枪状态
    bullets: Mapped[str] = mapped_column(Text, comment="弹药序列(JSON数组，true=实弹，false=空包弹)")
    current_bullet_index: Mapped[int] = mapped_column(Integer, default=0, comment="当前弹药索引")
    
    # 道具状态
    player1_items: Mapped[str] = mapped_column(Text, nullable=True, comment="玩家1道具(JSON)")
    player2_items: Mapped[str] = mapped_column(Text, nullable=True, comment="玩家2道具(JSON)")
    
    # 特殊状态
    is_sawed_off: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否使用了小刀(下次伤害翻倍)")
    handcuffed_player_id: Mapped[str] = mapped_column(String(32), nullable=True, comment="被手铐限制的玩家ID")
    
    # 预知信息存储(私密信息)
    magnifier_info: Mapped[str] = mapped_column(Text, nullable=True, comment="放大镜查看结果(JSON)")
    phone_info: Mapped[str] = mapped_column(Text, nullable=True, comment="电话预知结果(JSON)")
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    
    def get_current_bullet(self) -> bool:
        """获取当前弹药类型，True=实弹，False=空包弹"""
        import json
        bullets_list = json.loads(self.bullets)
        if self.current_bullet_index < len(bullets_list):
            return bullets_list[self.current_bullet_index]
        return False
    
    def advance_bullet(self):
        """推进到下一发弹药"""
        self.current_bullet_index += 1
    
    def is_magazine_empty(self) -> bool:
        """检查弹夹是否为空"""
        import json
        bullets_list = json.loads(self.bullets)
        return self.current_bullet_index >= len(bullets_list)
    
    def get_remaining_bullets_count(self) -> tuple[int, int]:
        """获取剩余弹药数量，返回(实弹数, 空包弹数)"""
        import json
        bullets_list = json.loads(self.bullets)
        remaining = bullets_list[self.current_bullet_index:]
        live_count = sum(1 for bullet in remaining if bullet)
        blank_count = sum(1 for bullet in remaining if not bullet)
        return live_count, blank_count
    
    def get_player_hp(self, player_id: str) -> int:
        """获取玩家血量"""
        if player_id == self.get_player1_id():
            return self.player1_hp
        elif player_id == self.get_player2_id():
            return self.player2_hp
        return 0
    
    def damage_player(self, player_id: str, damage: int = 1):
        """对玩家造成伤害"""
        if player_id == self.get_player1_id():
            self.player1_hp = max(0, self.player1_hp - damage)
        elif player_id == self.get_player2_id():
            self.player2_hp = max(0, self.player2_hp - damage)
    
    def heal_player(self, player_id: str, heal: int = 1):
        """治疗玩家"""
        # 需要从房间获取最大血量
        if player_id == self.get_player1_id():
            self.player1_hp = min(3, self.player1_hp + heal)  # 暂时硬编码最大血量为3
        elif player_id == self.get_player2_id():
            self.player2_hp = min(3, self.player2_hp + heal)
    
    def is_game_over(self) -> bool:
        """检查游戏是否结束"""
        return self.player1_hp <= 0 or self.player2_hp <= 0
    
    def get_winner_id(self) -> str:
        """获取获胜者ID"""
        if self.player1_hp <= 0:
            return self.get_player2_id()
        elif self.player2_hp <= 0:
            return self.get_player1_id()
        return None
    
    def get_player_ids_from_room(self, room: 'RussianRouletteRoom') -> tuple[str, str]:
        """从房间获取玩家ID"""
        return room.player1_id, room.player2_id
