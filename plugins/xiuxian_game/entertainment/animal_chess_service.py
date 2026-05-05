from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.animal_chess import (
    AnimalChessBet,
    AnimalChessGame,
    AnimalChessGameStatus,
    AnimalChessRoom,
    AnimalChessRoomStatus,
)
from ..models.player import Player


ANIMAL_ORDER = ["鼠", "猫", "狗", "狼", "豹", "虎", "狮", "象"]
ANIMAL_RANK = {name: index + 1 for index, name in enumerate(ANIMAL_ORDER)}
ANIMAL_ALIASES = {
    "rat": "鼠",
    "cat": "猫",
    "dog": "狗",
    "wolf": "狼",
    "leopard": "豹",
    "tiger": "虎",
    "lion": "狮",
    "elephant": "象",
}
PLAYER_SIDE = {"blue": "蓝方", "red": "红方"}
DIRECTION_DELTAS = {
    "上": (-1, 0),
    "下": (1, 0),
    "左": (0, -1),
    "右": (0, 1),
    "北": (-1, 0),
    "南": (1, 0),
    "西": (0, -1),
    "东": (0, 1),
}
DEN = {"red": (0, 3), "blue": (8, 3)}
TRAPS = {
    "red": {(0, 2), (0, 4), (1, 3)},
    "blue": {(8, 2), (8, 4), (7, 3)},
}
RIVER = {(3, 1), (3, 2), (4, 1), (4, 2), (5, 1), (5, 2), (3, 4), (3, 5), (4, 4), (4, 5), (5, 4), (5, 5)}
BOARD_ROWS = 9
BOARD_COLS = 7
TAX_RATE = 0.03


@dataclass
class MoveResult:
    success: bool
    message: str
    winner_id: str | None = None


class AnimalChessService:
    """斗兽棋房间、规则、下注结算服务。"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_room(self, player_id: str, group_id: str) -> tuple[bool, str, AnimalChessRoom | None]:
        existing = await self.find_player_active_room(player_id)
        if existing:
            return False, f"你已有进行中的斗兽棋房间：{existing.room_id}", None

        group_room = await self.find_group_active_room(group_id)
        if group_room:
            return False, f"本群已有斗兽棋房间：{group_room.room_id}", None

        room = AnimalChessRoom(
            room_id=uuid.uuid4().hex[:8],
            group_id=group_id,
            creator_id=player_id,
            player1_id=player_id,
        )
        self._session.add(room)
        await self._session.flush()
        return True, "房间创建成功", room

    async def join_group_room(self, player_id: str, group_id: str) -> tuple[bool, str, AnimalChessRoom | None]:
        existing = await self.find_player_active_room(player_id)
        if existing:
            return False, f"你已有进行中的斗兽棋房间：{existing.room_id}", None

        room = await self.find_group_active_room(group_id)
        if not room:
            return False, "本群暂无可加入的斗兽棋房间", None
        if room.status != AnimalChessRoomStatus.WAITING.value:
            return False, "当前房间不在等待加入阶段", None
        if room.player1_id == player_id:
            return False, "你已经在这个房间中了", None
        if room.is_full():
            return False, "房间已满", None

        room.player2_id = player_id
        room.status = AnimalChessRoomStatus.BETTING.value
        self._session.add(room)
        await self._session.flush()
        return True, "加入房间成功", room

    async def leave_room(self, player_id: str) -> tuple[bool, str]:
        room = await self.find_player_active_room(player_id)
        if not room:
            return False, "你不在任何斗兽棋房间中"
        if room.status not in (AnimalChessRoomStatus.WAITING.value, AnimalChessRoomStatus.BETTING.value):
            return False, "游戏开始后不能退出房间"

        await self.refund_room_bets(room.room_id)
        if room.player1_id == player_id:
            if room.player2_id:
                room.creator_id = room.player2_id
                room.player1_id = room.player2_id
                room.player2_id = None
                room.player1_gold_bet = room.player2_gold_bet
                room.player2_gold_bet = 0
                room.status = AnimalChessRoomStatus.WAITING.value
                self._session.add(room)
                return True, "已退出房间，房主已转移给另一位玩家"

            await self._session.delete(room)
            return True, "已退出并删除斗兽棋房间"

        if room.player2_id == player_id:
            room.player2_id = None
            room.player2_gold_bet = 0
            room.status = AnimalChessRoomStatus.WAITING.value
            self._session.add(room)
            return True, "已退出房间"

        return False, "你不在这个房间中"

    async def refund_room_bets(self, room_id: str) -> None:
        bets = await self.get_room_bets(room_id)
        if not bets:
            return

        players = await self._get_players([bet.bettor_id for bet in bets])
        for bet in bets:
            bettor = players.get(bet.bettor_id)
            if bettor:
                bettor.gold += bet.gold_amount
                self._session.add(bettor)
            await self._session.delete(bet)
        await self._session.flush()

    async def set_bet(self, player_id: str, gold: int) -> tuple[bool, str, dict[str, int | bool]]:
        if gold <= 0:
            return False, "筹码金币数必须大于0", {}

        room = await self.find_player_active_room(player_id)
        if not room or room.status != AnimalChessRoomStatus.BETTING.value:
            return False, "你不在斗兽棋筹码设置阶段", {}

        player = await self._session.get(Player, player_id)
        if not player:
            return False, "玩家不存在", {}
        if player.gold < gold:
            return False, f"金币不足！你有{player.gold}金币，需要{gold}金币", {}

        current_bet = room.player1_gold_bet if room.player1_id == player_id else room.player2_gold_bet
        opponent_bet = room.player2_gold_bet if room.player1_id == player_id else room.player1_gold_bet
        if opponent_bet > 0 and current_bet == 0 and gold < opponent_bet:
            return False, f"对手已下注 {opponent_bet} 金币，你的筹码至少需要相同", {}

        if room.player1_id == player_id:
            room.player1_gold_bet = gold
        else:
            room.player2_gold_bet = gold
        self._session.add(room)
        await self._session.flush()

        both_ready = room.player1_gold_bet > 0 and room.player2_gold_bet > 0
        total_pool = room.player1_gold_bet + room.player2_gold_bet
        details: dict[str, int | bool] = {
            "gold": gold,
            "opponent_gold": opponent_bet,
            "both_ready": both_ready,
            "total_pool": total_pool,
        }
        if both_ready:
            details["tax_amount"] = int(total_pool * TAX_RATE)
            details["final_reward"] = total_pool - int(total_pool * TAX_RATE)
        return True, "筹码设置成功", details

    async def start_game(self, player_id: str) -> tuple[bool, str, AnimalChessRoom | None, AnimalChessGame | None]:
        room = await self.find_player_active_room(player_id)
        if not room or room.status != AnimalChessRoomStatus.BETTING.value:
            return False, "你不在可开始的斗兽棋房间中", None, None
        if not room.is_full():
            return False, "房间人数不足", room, None
        if room.player1_gold_bet <= 0 or room.player2_gold_bet <= 0:
            return False, "双方都设置筹码后才能开始", room, None

        players = await self._get_players([room.player1_id, room.player2_id])
        player1 = players.get(room.player1_id)
        player2 = players.get(room.player2_id)
        if not player1 or not player2:
            return False, "玩家信息获取失败", room, None
        if player1.gold < room.player1_gold_bet:
            return False, f"蓝方金币不足：{player1.nickname}", room, None
        if player2.gold < room.player2_gold_bet:
            return False, f"红方金币不足：{player2.nickname}", room, None

        player1.gold -= room.player1_gold_bet
        player2.gold -= room.player2_gold_bet
        first_player_id = random.choice([room.player1_id, room.player2_id])
        game = AnimalChessGame(
            room_id=room.room_id,
            current_player_id=first_player_id,
            board_state=json.dumps(self.initial_board(), ensure_ascii=False),
            move_history="[]",
        )
        room.status = AnimalChessRoomStatus.PLAYING.value
        self._session.add_all([player1, player2, room, game])
        await self._session.flush()
        return True, "斗兽棋开始", room, game

    async def move_piece(self, player_id: str, animal_text: str, direction_text: str) -> MoveResult:
        room = await self.find_player_active_room(player_id)
        if not room or room.status != AnimalChessRoomStatus.PLAYING.value:
            return MoveResult(False, "你不在进行中的斗兽棋房间中")

        game = await self.find_active_game(room.room_id)
        if not game:
            return MoveResult(False, "游戏状态异常")
        if game.current_player_id != player_id:
            return MoveResult(False, "还没轮到你行动")

        animal = self.normalize_animal(animal_text)
        if animal not in ANIMAL_RANK:
            return MoveResult(False, "棋子名称无效，可用：鼠、猫、狗、狼、豹、虎、狮、象")

        direction = direction_text.strip()
        if direction not in DIRECTION_DELTAS:
            return MoveResult(False, "方向无效，可用：上、下、左、右")

        side = self.get_player_side(room, player_id)
        if side is None:
            return MoveResult(False, "你不在这个房间中")

        board = json.loads(game.board_state)
        piece = self.find_piece(board, side, animal)
        if not piece:
            return MoveResult(False, f"你的{animal}已经被吃掉，无法移动")

        start = tuple(piece["pos"])
        destination = self.resolve_destination(board, piece, direction)
        if destination is None:
            return MoveResult(False, "该方向不能移动：越界、河流限制或跳河被河中鼠阻挡")

        ok, reason = self.can_land(board, piece, destination)
        if not ok:
            return MoveResult(False, reason)

        captured = self.piece_at(board, destination)
        if captured:
            captured["alive"] = False
            captured["pos"] = None
        piece["pos"] = [destination[0], destination[1]]

        winner_id = self.check_winner(room, board, piece)
        move_record = {
            "turn": game.turn_count,
            "side": side,
            "animal": animal,
            "from": list(start),
            "to": list(destination),
            "captured": captured["animal"] if captured else None,
        }
        history = json.loads(game.move_history or "[]")
        history.append(move_record)
        game.move_history = json.dumps(history[-80:], ensure_ascii=False)
        game.last_move = json.dumps(move_record, ensure_ascii=False)
        game.board_state = json.dumps(board, ensure_ascii=False)

        if winner_id:
            game.status = AnimalChessGameStatus.FINISHED.value
            game.winner_id = winner_id
            room.status = AnimalChessRoomStatus.FINISHED.value
            self._session.add_all([room, game])
            success, reward_msg = await self.finish_game(room, winner_id)
            if not success:
                return MoveResult(False, reward_msg)
            return MoveResult(True, self.describe_move(move_record) + "\n" + reward_msg, winner_id)

        game.turn_count += 1
        game.current_player_id = room.get_opponent_id(player_id)
        self._session.add(game)
        await self._session.flush()
        return MoveResult(True, self.describe_move(move_record))

    async def place_bet(self, bettor_id: str, room: AnimalChessRoom, target_player_id: str, gold_amount: int) -> tuple[bool, str]:
        if gold_amount <= 0:
            return False, "下注金额必须大于0"
        if room.status != AnimalChessRoomStatus.BETTING.value:
            return False, "只能在双方匹配后、游戏开始前下注"
        if room.is_player_in_room(bettor_id):
            return False, "游戏参与者不能下注"
        if target_player_id not in (room.player1_id, room.player2_id):
            return False, "只能支持本局玩家"

        bettor = await self._session.get(Player, bettor_id)
        if not bettor:
            return False, "玩家不存在"
        if bettor.gold < gold_amount:
            return False, f"金币不足！你有{bettor.gold}金币，需要{gold_amount}金币"

        stmt = select(AnimalChessBet).where(
            AnimalChessBet.room_id == room.room_id,
            AnimalChessBet.bettor_id == bettor_id,
        )
        existing = (await self._session.execute(stmt)).scalars().first()
        if existing:
            return False, "你已经在这局下注了，每局只能下注一次"

        bettor.gold -= gold_amount
        self._session.add(
            AnimalChessBet(
                room_id=room.room_id,
                bettor_id=bettor_id,
                target_player_id=target_player_id,
                gold_amount=gold_amount,
            )
        )
        self._session.add(bettor)
        await self._session.flush()
        return True, "下注成功"

    async def finish_game(self, room: AnimalChessRoom, winner_id: str) -> tuple[bool, str]:
        loser_id = room.get_opponent_id(winner_id)
        if not loser_id:
            return False, "结算失败：找不到失败方"

        bets = await self.get_room_bets(room.room_id)
        winner_bets = [bet for bet in bets if bet.target_player_id == winner_id]
        loser_bets = [bet for bet in bets if bet.target_player_id == loser_id]

        winner_main_bet = room.player1_gold_bet if winner_id == room.player1_id else room.player2_gold_bet
        loser_main_bet = room.player1_gold_bet if loser_id == room.player1_id else room.player2_gold_bet
        winner_support_total = sum(bet.gold_amount for bet in winner_bets)
        loser_support_total = sum(bet.gold_amount for bet in loser_bets)
        total_winner_side = winner_main_bet + winner_support_total
        total_loser_side = loser_main_bet + loser_support_total
        if total_winner_side <= 0:
            return False, "结算失败：赢方投入异常"

        tax_amount = int(total_loser_side * TAX_RATE)
        distributable = total_loser_side - tax_amount
        winner_profit = int(distributable * winner_main_bet / total_winner_side)
        winner_payout = winner_main_bet + winner_profit

        player_ids = [room.player1_id, room.player2_id] + [bet.bettor_id for bet in bets]
        players = await self._get_players(player_ids)
        winner = players.get(winner_id)
        loser = players.get(loser_id)

        if winner:
            winner.gold += winner_payout
            winner.mini_game_score += 2
            self._session.add(winner)
        if loser:
            loser.mini_game_score += 1
            self._session.add(loser)

        lines = [
            "━━━━━━━━━━━━━",
            "🏆 斗兽棋胜负已分",
            f"胜者：{self.player_label(winner)}",
            f"败者：{self.player_label(loser)}",
            f"赢方总投入：{total_winner_side}金币（主押{winner_main_bet} + 支持者{winner_support_total}）",
            f"输方总资产：{total_loser_side}金币（主押{loser_main_bet} + 支持者{loser_support_total}）",
            f"系统税收：{tax_amount}金币（3%）",
            "━━━━━━━━━━━━━",
            "金币结算",
            f"{self.player_label(winner)} +{winner_payout}金币（本金{winner_main_bet} + 分红{winner_profit}）",
        ]

        for bet in winner_bets:
            profit = int(distributable * bet.gold_amount / total_winner_side)
            payout = bet.gold_amount + profit
            bettor = players.get(bet.bettor_id)
            if bettor:
                bettor.gold += payout
                self._session.add(bettor)
                lines.append(f"{self.player_label(bettor)} +{payout}金币（本金{bet.gold_amount} + 分红{profit}）")

        if loser_bets:
            lines.append("━━━━━━━━━━━━━")
            lines.append(f"落败方支持者共损失{loser_support_total}金币")
            for bet in loser_bets:
                bettor = players.get(bet.bettor_id)
                lines.append(f"{self.player_label(bettor)} -{bet.gold_amount}金币")

        await self._session.flush()
        return True, "\n".join(lines)

    async def get_room_bets(self, room_id: str) -> list[AnimalChessBet]:
        stmt = select(AnimalChessBet).where(AnimalChessBet.room_id == room_id)
        return list((await self._session.execute(stmt)).scalars().all())

    async def find_player_active_room(self, player_id: str) -> AnimalChessRoom | None:
        stmt = select(AnimalChessRoom).where(
            and_(
                or_(AnimalChessRoom.player1_id == player_id, AnimalChessRoom.player2_id == player_id),
                AnimalChessRoom.status.in_(
                    [
                        AnimalChessRoomStatus.WAITING.value,
                        AnimalChessRoomStatus.BETTING.value,
                        AnimalChessRoomStatus.PLAYING.value,
                    ]
                ),
            )
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def find_group_active_room(self, group_id: str) -> AnimalChessRoom | None:
        stmt = select(AnimalChessRoom).where(
            AnimalChessRoom.group_id == group_id,
            AnimalChessRoom.status.in_(
                [
                    AnimalChessRoomStatus.WAITING.value,
                    AnimalChessRoomStatus.BETTING.value,
                    AnimalChessRoomStatus.PLAYING.value,
                ]
            ),
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def find_active_game(self, room_id: str) -> AnimalChessGame | None:
        stmt = select(AnimalChessGame).where(
            AnimalChessGame.room_id == room_id,
            AnimalChessGame.status == AnimalChessGameStatus.PLAYING.value,
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def _get_players(self, player_ids: list[str | None]) -> dict[str, Player]:
        ids = [player_id for player_id in dict.fromkeys(player_ids) if player_id]
        if not ids:
            return {}
        stmt = select(Player).where(Player.id.in_(ids))
        players = (await self._session.execute(stmt)).scalars().all()
        return {player.id: player for player in players}

    @staticmethod
    def initial_board() -> list[dict[str, Any]]:
        return [
            {"side": "red", "animal": "狮", "pos": [0, 0], "alive": True},
            {"side": "red", "animal": "虎", "pos": [0, 6], "alive": True},
            {"side": "red", "animal": "狗", "pos": [1, 1], "alive": True},
            {"side": "red", "animal": "猫", "pos": [1, 5], "alive": True},
            {"side": "red", "animal": "鼠", "pos": [2, 0], "alive": True},
            {"side": "red", "animal": "豹", "pos": [2, 2], "alive": True},
            {"side": "red", "animal": "狼", "pos": [2, 4], "alive": True},
            {"side": "red", "animal": "象", "pos": [2, 6], "alive": True},
            {"side": "blue", "animal": "象", "pos": [6, 0], "alive": True},
            {"side": "blue", "animal": "狼", "pos": [6, 2], "alive": True},
            {"side": "blue", "animal": "豹", "pos": [6, 4], "alive": True},
            {"side": "blue", "animal": "鼠", "pos": [6, 6], "alive": True},
            {"side": "blue", "animal": "猫", "pos": [7, 1], "alive": True},
            {"side": "blue", "animal": "狗", "pos": [7, 5], "alive": True},
            {"side": "blue", "animal": "虎", "pos": [8, 0], "alive": True},
            {"side": "blue", "animal": "狮", "pos": [8, 6], "alive": True},
        ]

    @staticmethod
    def normalize_animal(text: str) -> str:
        stripped = text.strip().lower()
        return ANIMAL_ALIASES.get(stripped, text.strip()[:1])

    @staticmethod
    def get_player_side(room: AnimalChessRoom, player_id: str) -> str | None:
        if room.player1_id == player_id:
            return "blue"
        if room.player2_id == player_id:
            return "red"
        return None

    @staticmethod
    def opponent_side(side: str) -> str:
        return "red" if side == "blue" else "blue"

    @staticmethod
    def find_piece(board: list[dict[str, Any]], side: str, animal: str) -> dict[str, Any] | None:
        for piece in board:
            if piece["alive"] and piece["side"] == side and piece["animal"] == animal:
                return piece
        return None

    @staticmethod
    def piece_at(board: list[dict[str, Any]], pos: tuple[int, int]) -> dict[str, Any] | None:
        for piece in board:
            if piece["alive"] and piece["pos"] == [pos[0], pos[1]]:
                return piece
        return None

    def resolve_destination(self, board: list[dict[str, Any]], piece: dict[str, Any], direction: str) -> tuple[int, int] | None:
        row, col = piece["pos"]
        dr, dc = DIRECTION_DELTAS[direction]
        dest = (row + dr, col + dc)
        if not self.in_bounds(dest):
            return None

        animal = piece["animal"]
        if animal in ("狮", "虎") and dest in RIVER:
            while self.in_bounds(dest) and dest in RIVER:
                if self.has_rat_in_water(board, dest):
                    return None
                dest = (dest[0] + dr, dest[1] + dc)
            return dest if self.in_bounds(dest) else None

        if dest in RIVER and animal != "鼠":
            return None
        return dest

    @staticmethod
    def in_bounds(pos: tuple[int, int]) -> bool:
        return 0 <= pos[0] < BOARD_ROWS and 0 <= pos[1] < BOARD_COLS

    def has_rat_in_water(self, board: list[dict[str, Any]], pos: tuple[int, int]) -> bool:
        piece = self.piece_at(board, pos)
        return bool(piece and piece["animal"] == "鼠")

    def can_land(self, board: list[dict[str, Any]], piece: dict[str, Any], dest: tuple[int, int]) -> tuple[bool, str]:
        side = piece["side"]
        if dest == DEN[side]:
            return False, "不能进入自己的兽穴"

        target = self.piece_at(board, dest)
        if not target:
            return True, ""
        if target["side"] == side:
            return False, "目标位置已有己方棋子"
        if not self.can_capture(piece, target, dest):
            return False, f"{piece['animal']}不能吃对方的{target['animal']}"
        return True, ""

    def can_capture(self, attacker: dict[str, Any], defender: dict[str, Any], dest: tuple[int, int]) -> bool:
        if dest in TRAPS[attacker["side"]]:
            return True

        attack_animal = attacker["animal"]
        defend_animal = defender["animal"]
        start_in_water = tuple(attacker["pos"]) in RIVER
        dest_in_water = dest in RIVER
        if attack_animal == "鼠" and defend_animal == "象":
            return not start_in_water
        if attack_animal == "象" and defend_animal == "鼠":
            return False
        if attack_animal == "鼠" and defend_animal == "鼠":
            return start_in_water == dest_in_water
        if start_in_water or dest_in_water:
            return False
        return ANIMAL_RANK[attack_animal] >= ANIMAL_RANK[defend_animal]

    def check_winner(self, room: AnimalChessRoom, board: list[dict[str, Any]], moved_piece: dict[str, Any]) -> str | None:
        side = moved_piece["side"]
        if tuple(moved_piece["pos"]) == DEN[self.opponent_side(side)]:
            return room.player1_id if side == "blue" else room.player2_id

        red_alive = any(piece["alive"] and piece["side"] == "red" for piece in board)
        blue_alive = any(piece["alive"] and piece["side"] == "blue" for piece in board)
        if not red_alive:
            return room.player1_id
        if not blue_alive:
            return room.player2_id
        return None

    @staticmethod
    def describe_move(move: dict[str, Any]) -> str:
        captured = f"，吃掉{move['captured']}" if move["captured"] else ""
        return f"{PLAYER_SIDE[move['side']]}{move['animal']}：{AnimalChessService.coord_text(move['from'])} -> {AnimalChessService.coord_text(move['to'])}{captured}"

    @staticmethod
    def coord_text(pos: list[int] | tuple[int, int]) -> str:
        return f"{chr(ord('A') + int(pos[1]))}{int(pos[0]) + 1}"

    @staticmethod
    def player_label(player: Player | None) -> str:
        if not player:
            return "未知玩家"
        return f"{player.nickname}[UID:{player.uid}]"
