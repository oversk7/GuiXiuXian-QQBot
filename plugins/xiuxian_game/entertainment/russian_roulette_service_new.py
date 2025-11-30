"""
恶魔轮盘赌房间管理服务 - DI架构版本

改造自原版russian_roulette_service.py，采用依赖注入模式：
1. 构造函数注入Repository依赖
2. 移除session参数，通过Repository访问数据
3. 移除内部commit()调用，由外部UnitOfWork控制事务
4. 所有静态方法转为实例方法

改造日期: 2025-11-29
"""
import json
import uuid
from typing import Optional, Tuple, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.russian_roulette import RussianRouletteRoom, RussianRouletteGame, RoomStatus, GameStatus
from ..models.player import Player
from ..infrastructure.repositories.russian_roulette_room_repository import RussianRouletteRoomRepository
from ..infrastructure.repositories.russian_roulette_game_repository import RussianRouletteGameRepository
from ..infrastructure.repositories.player_repository import PlayerRepository
from .russian_roulette_core import RussianRouletteCore, ItemType


class RussianRouletteService:
    """恶魔轮盘赌服务类（DI架构版本）

    通过构造函数注入所需的Repository，不再使用静态方法
    """

    def __init__(
        self,
        room_repo: RussianRouletteRoomRepository,
        game_repo: RussianRouletteGameRepository,
        player_repo: PlayerRepository
    ):
        """
        初始化恶魔轮盘赌服务

        Args:
            room_repo: 房间仓储
            game_repo: 游戏状态仓储
            player_repo: 玩家仓储
        """
        self._room_repo = room_repo
        self._game_repo = game_repo
        self._player_repo = player_repo

    async def create_room(
        self, creator_id: str, group_id: str
    ) -> Tuple[bool, str, Optional[RussianRouletteRoom]]:
        """创建游戏房间

        Args:
            creator_id: 创建者玩家ID
            group_id: 群组ID

        Returns:
            (成功标志, 消息, 房间对象)
        """
        # 检查玩家是否已在其他房间中
        existing_room = await self.get_player_active_room(creator_id)
        if existing_room:
            return False, "你已经在其他房间中了", None

        # 检查该群是否已有活跃房间
        existing_group_room = await self._room_repo.find_group_active_room(group_id)
        if existing_group_room:
            return False, "该群已有活跃的游戏房间", None

        # 生成房间ID
        room_id = str(uuid.uuid4())[:8]

        # 创建房间
        room = RussianRouletteRoom(
            room_id=room_id,
            group_id=group_id,
            creator_id=creator_id,
            player1_id=creator_id,
            status=RoomStatus.WAITING.value
        )

        created_room = await self._room_repo.create(room)

        return True, f"房间创建成功！房间ID: {room_id}", created_room

    async def join_room(
        self, player_id: str, room_id: str, group_id: str
    ) -> Tuple[bool, str]:
        """加入游戏房间

        Args:
            player_id: 玩家ID
            room_id: 房间ID
            group_id: 群组ID

        Returns:
            (成功标志, 消息)
        """
        # 检查玩家是否已在其他房间中
        existing_room = await self.get_player_active_room(player_id)
        if existing_room:
            return False, "你已经在其他房间中了"

        # 查找房间
        room = await self._room_repo.find_by_room_id_and_group(
            room_id, group_id, RoomStatus.WAITING.value
        )

        if not room:
            return False, "房间不存在或已开始游戏"

        if room.is_full():
            return False, "房间已满"

        if room.player1_id == player_id:
            return False, "你已经在这个房间中了"

        # 加入房间
        room.player2_id = player_id
        room.status = RoomStatus.BETTING.value

        await self._room_repo.update(room)

        return True, "成功加入房间！现在可以设置筹码"

    async def set_bet(
        self, player_id: str, room_id: str, gold: int, item_bets: List[dict]
    ) -> Tuple[bool, str, dict]:
        """设置筹码（只允许金币）

        Args:
            player_id: 玩家ID
            room_id: 房间ID
            gold: 金币数量
            item_bets: 道具筹码列表（已废弃，仅用于兼容性检查）

        Returns:
            (成功标志, 消息, 筹码详情)
        """
        # 查找房间
        room = await self.get_room_by_id(room_id)
        if not room or room.status != RoomStatus.BETTING.value:
            return False, "房间不存在或不在筹码设置阶段", {}

        if not room.is_player_in_room(player_id):
            return False, "你不在这个房间中", {}

        # 检查是否尝试使用道具或装备作为筹码
        if item_bets:
            return False, "恶魔轮盘已取消道具和装备筹码，只能使用金币作为筹码", {}

        # 检查金币数量限制
        if gold <= 0:
            return False, "筹码金币数必须大于0", {}

        # 检查玩家资源
        player = await self._player_repo.get_by_id(player_id)
        if not player:
            return False, "玩家不存在", {}

        if player.gold < gold:
            return False, f"金币不足！你有{player.gold}金币，需要{gold}金币", {}

        # 判断当前和对手的筹码情况
        if room.player1_id == player_id:
            current_bet = room.player1_gold_bet
            opponent_bet = room.player2_gold_bet or 0
        else:
            current_bet = room.player2_gold_bet
            opponent_bet = room.player1_gold_bet or 0

        # 第二位下注的玩家需要满足不低于对手的筹码
        if opponent_bet > 0 and current_bet == 0 and gold < opponent_bet:
            return False, f"对手已下注 {opponent_bet} 金币，你的筹码至少需要相同", {}

        # 设置筹码（只有金币，不再支持道具）
        if room.player1_id == player_id:
            room.player1_gold_bet = gold
            room.player1_items_bet = None  # 清空道具筹码
        elif room.player2_id == player_id:
            room.player2_gold_bet = gold
            room.player2_items_bet = None  # 清空道具筹码

        await self._room_repo.update(room)

        # 返回详细信息用于显示
        opponent_gold = 0
        if room.player1_id == player_id:
            opponent_gold = room.player2_gold_bet or 0
        else:
            opponent_gold = room.player1_gold_bet or 0

        both_ready = room.player1_gold_bet > 0 and room.player2_gold_bet > 0
        total_pool = room.player1_gold_bet + room.player2_gold_bet if both_ready else gold + opponent_gold

        bet_details = {
            "gold": gold,
            "opponent_gold": opponent_gold,
            "both_ready": both_ready,
            "total_pool": total_pool,
            "items": []  # 不再有道具
        }

        if both_ready:
            tax_rate = 0.03
            bet_details["tax_amount"] = int(total_pool * tax_rate)
            bet_details["final_reward"] = total_pool - bet_details["tax_amount"]

        return True, "筹码设置成功！", bet_details

    async def start_game(
        self, room_id: str
    ) -> Tuple[bool, str, Optional[RussianRouletteGame]]:
        """开始游戏

        Args:
            room_id: 房间ID

        Returns:
            (成功标志, 消息, 游戏对象)
        """
        room = await self.get_room_by_id(room_id)
        if not room or room.status != RoomStatus.BETTING.value:
            return False, "房间不存在或不在筹码设置阶段", None

        if not room.is_full():
            return False, "房间人数不足", None

        # 检查双方是否都设置了筹码（只检查金币）
        if room.player1_gold_bet == 0:
            return False, "玩家1未设置筹码", None

        if room.player2_gold_bet == 0:
            return False, "玩家2未设置筹码", None

        # 批量获取两个玩家（优化查询）
        players = await self._player_repo.get_many_by_ids([room.player1_id, room.player2_id])
        player1 = next((p for p in players if p.id == room.player1_id), None)
        player2 = next((p for p in players if p.id == room.player2_id), None)

        if not player1 or not player2:
            return False, "玩家信息获取失败", None

        # 扣除金币
        player1.gold -= room.player1_gold_bet
        player2.gold -= room.player2_gold_bet

        # 更新玩家数据
        await self._player_repo.update(player1)
        await self._player_repo.update(player2)

        # 生成游戏状态
        bullets = RussianRouletteCore.generate_bullets()  # 随机选择弹药配置(2+4, 3+3, 4+2)
        player1_items = RussianRouletteCore.generate_items(4)
        player2_items = RussianRouletteCore.generate_items(4)

        game = RussianRouletteGame(
            room_id=room_id,
            status=GameStatus.PLAYING.value,
            current_player_id=room.player1_id,  # 玩家1先手
            player1_hp=room.max_hp,
            player2_hp=room.max_hp,
            bullets=json.dumps(bullets),
            current_bullet_index=0,
            player1_items=json.dumps([item.value for item in player1_items]),
            player2_items=json.dumps([item.value for item in player2_items])
        )

        # 更新房间状态
        room.status = RoomStatus.PLAYING.value

        await self._room_repo.update(room)
        created_game = await self._game_repo.create(game)

        return True, "游戏开始！", created_game

    async def get_room_by_id(self, room_id: str) -> Optional[RussianRouletteRoom]:
        """根据ID获取房间

        Args:
            room_id: 房间ID

        Returns:
            房间对象或None
        """
        return await self._room_repo.find_by_room_id(room_id)

    async def get_player_active_room(self, player_id: str) -> Optional[RussianRouletteRoom]:
        """获取玩家当前活跃的房间

        Args:
            player_id: 玩家ID

        Returns:
            房间对象或None
        """
        return await self._room_repo.find_player_active_room(player_id)

    async def get_active_game(self, room_id: str) -> Optional[RussianRouletteGame]:
        """根据房间ID获取活跃的游戏状态

        Args:
            room_id: 房间ID

        Returns:
            游戏对象或None
        """
        return await self._game_repo.find_active_game_by_room(room_id)

    async def finish_game(
        self, room_id: str, winner_id: str
    ) -> Tuple[bool, str]:
        """结束游戏并分配奖励

        Args:
            room_id: 房间ID
            winner_id: 获胜者玩家ID

        Returns:
            (成功标志, 奖励消息)
        """
        room = await self.get_room_by_id(room_id)
        game = await self.get_active_game(room_id)

        if not room or not game:
            return False, "房间或游戏不存在"

        # 计算总金币奖池
        total_gold = room.player1_gold_bet + room.player2_gold_bet

        # 抽取3%税收
        tax_rate = 0.03
        tax_amount = int(total_gold * tax_rate)
        final_reward = total_gold - tax_amount

        # 批量获取获胜者和失败者（优化N+1查询）
        loser_id = room.player1_id if winner_id == room.player2_id else room.player2_id
        players = await self._player_repo.get_many_by_ids([winner_id, loser_id])
        winner = next((p for p in players if p.id == winner_id), None)
        loser = next((p for p in players if p.id == loser_id), None)

        if winner:
            winner.gold += final_reward
            # 获胜者获得2分小游戏积分
            winner.mini_game_score += 2
            await self._player_repo.update(winner)

        if loser:
            # 失败者获得1分小游戏积分
            loser.mini_game_score += 1
            await self._player_repo.update(loser)

        # 更新状态
        room.status = RoomStatus.FINISHED.value
        game.status = GameStatus.FINISHED.value

        await self._room_repo.update(room)
        await self._game_repo.update(game)

        # 构建奖励消息
        reward_msg = (
            f"💰 奖池总额：{total_gold}金币\n"
            f"💸 系统税收：{tax_amount}金币 (3%)\n"
            f"🏆 实际获得：{final_reward}金币\n"
            f"🎮 小游戏积分：获胜者+2分，失败者+1分"
        )

        return True, reward_msg
