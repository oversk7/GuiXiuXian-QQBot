"""
恶魔轮盘赌房间管理服务
"""
import json
import uuid
from typing import Optional, Tuple, List, Dict
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.russian_roulette import RussianRouletteRoom, RussianRouletteGame, RoomStatus, GameStatus
from ..models.player import Player
from ..models.inventory import ItemInstance
from .russian_roulette_core import RussianRouletteCore, ItemType


class RussianRouletteService:
    """恶魔轮盘赌服务类"""
    
    @staticmethod
    async def create_room(session: AsyncSession, creator_id: str, group_id: str) -> Tuple[bool, str, Optional[RussianRouletteRoom]]:
        """创建游戏房间"""
        # 检查玩家是否已在其他房间中
        existing_room = await RussianRouletteService.get_player_active_room(session, creator_id)
        if existing_room:
            return False, "你已经在其他房间中了", None
        
        # 检查该群是否已有活跃房间
        stmt = select(RussianRouletteRoom).where(
            and_(
                RussianRouletteRoom.group_id == group_id,
                RussianRouletteRoom.status.in_([RoomStatus.WAITING.value, RoomStatus.BETTING.value, RoomStatus.PLAYING.value])
            )
        )
        existing_group_room = (await session.execute(stmt)).scalars().first()
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
        
        session.add(room)
        await session.commit()
        
        return True, f"房间创建成功！房间ID: {room_id}", room
    
    @staticmethod
    async def join_room(session: AsyncSession, player_id: str, room_id: str, group_id: str) -> Tuple[bool, str]:
        """加入游戏房间"""
        # 检查玩家是否已在其他房间中
        existing_room = await RussianRouletteService.get_player_active_room(session, player_id)
        if existing_room:
            return False, "你已经在其他房间中了"
        
        # 查找房间
        stmt = select(RussianRouletteRoom).where(
            and_(
                RussianRouletteRoom.room_id == room_id,
                RussianRouletteRoom.group_id == group_id,
                RussianRouletteRoom.status == RoomStatus.WAITING.value
            )
        )
        room = (await session.execute(stmt)).scalars().first()
        
        if not room:
            return False, "房间不存在或已开始游戏"
        
        if room.is_full():
            return False, "房间已满"
        
        if room.player1_id == player_id:
            return False, "你已经在这个房间中了"
        
        # 加入房间
        room.player2_id = player_id
        room.status = RoomStatus.BETTING.value
        
        await session.commit()
        return True, "成功加入房间！现在可以设置筹码"
    
    @staticmethod
    async def set_bet(session: AsyncSession, player_id: str, room_id: str, gold: int, item_bets: List[dict]) -> Tuple[bool, str, dict]:
        """设置筹码"""
        from ..config import config

        # 查找房间
        room = await RussianRouletteService.get_room_by_id(session, room_id)
        if not room or room.status != RoomStatus.BETTING.value:
            return False, "房间不存在或不在筹码设置阶段", {}

        if not room.is_player_in_room(player_id):
            return False, "你不在这个房间中", {}

        # 检查玩家资源
        player = await session.get(Player, player_id)
        if not player:
            return False, "玩家不存在", {}

        if player.gold < gold:
            return False, f"金币不足！你有{player.gold}金币，需要{gold}金币", {}

        # 检查和转换道具
        validated_items = []
        if item_bets:
            for item_bet in item_bets:
                item_name = item_bet["name"]
                quantity = item_bet["quantity"]

                # 通过名称查找道具配置
                item_config = config.items_config["by_name"].get(item_name)
                if not item_config:
                    return False, f"未知道具：{item_name}", {}

                # 检查玩家是否有足够的道具
                item_count = await ItemInstance.get_item_count(session, player_id, item_config.item_id)
                if item_count < quantity:
                    return False, f"道具不足：{item_name}（需要{quantity}个，你有{item_count}个）", {}

                validated_items.append({
                    "item_id": item_config.item_id,
                    "name": item_name,
                    "quantity": quantity
                })

        # 设置筹码
        items_json = json.dumps(validated_items) if validated_items else None

        if room.player1_id == player_id:
            room.player1_gold_bet = gold
            room.player1_items_bet = items_json
        elif room.player2_id == player_id:
            room.player2_gold_bet = gold
            room.player2_items_bet = items_json

        await session.commit()

        # 返回详细信息用于显示
        bet_details = {
            "gold": gold,
            "items": validated_items
        }

        return True, "筹码设置成功！", bet_details
    
    @staticmethod
    async def start_game(session: AsyncSession, room_id: str) -> Tuple[bool, str, Optional[RussianRouletteGame]]:
        """开始游戏"""
        room = await RussianRouletteService.get_room_by_id(session, room_id)
        if not room or room.status != RoomStatus.BETTING.value:
            return False, "房间不存在或不在筹码设置阶段", None
        
        if not room.is_full():
            return False, "房间人数不足", None
        
        # 检查双方是否都设置了筹码
        if room.player1_gold_bet == 0 and not room.player1_items_bet:
            return False, "玩家1未设置筹码", None
        
        if room.player2_gold_bet == 0 and not room.player2_items_bet:
            return False, "玩家2未设置筹码", None
        
        # 扣除筹码
        player1 = await session.get(Player, room.player1_id)
        player2 = await session.get(Player, room.player2_id)
        
        # 扣除金币
        player1.gold -= room.player1_gold_bet
        player2.gold -= room.player2_gold_bet
        
        # 扣除道具
        if room.player1_items_bet:
            items = json.loads(room.player1_items_bet)
            for item_data in items:
                if isinstance(item_data, dict):
                    # 新格式：{"item_id": "xxx", "name": "xxx", "quantity": n}
                    item_id = item_data["item_id"]
                    quantity = item_data["quantity"]
                    await ItemInstance.consume_item(session, room.player1_id, item_id, quantity)
                else:
                    # 兼容旧格式：直接是item_id字符串
                    await ItemInstance.consume_item(session, room.player1_id, item_data, 1)

        if room.player2_items_bet:
            items = json.loads(room.player2_items_bet)
            for item_data in items:
                if isinstance(item_data, dict):
                    # 新格式：{"item_id": "xxx", "name": "xxx", "quantity": n}
                    item_id = item_data["item_id"]
                    quantity = item_data["quantity"]
                    await ItemInstance.consume_item(session, room.player2_id, item_id, quantity)
                else:
                    # 兼容旧格式：直接是item_id字符串
                    await ItemInstance.consume_item(session, room.player2_id, item_data, 1)
        
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
        
        session.add(game)
        await session.commit()
        
        return True, "游戏开始！", game
    
    @staticmethod
    async def get_room_by_id(session: AsyncSession, room_id: str) -> Optional[RussianRouletteRoom]:
        """根据ID获取房间"""
        stmt = select(RussianRouletteRoom).where(RussianRouletteRoom.room_id == room_id)
        return (await session.execute(stmt)).scalars().first()
    
    @staticmethod
    async def get_player_active_room(session: AsyncSession, player_id: str) -> Optional[RussianRouletteRoom]:
        """获取玩家当前活跃的房间"""
        stmt = select(RussianRouletteRoom).where(
            and_(
                or_(
                    RussianRouletteRoom.player1_id == player_id,
                    RussianRouletteRoom.player2_id == player_id
                ),
                RussianRouletteRoom.status.in_([RoomStatus.WAITING.value, RoomStatus.BETTING.value, RoomStatus.PLAYING.value])
            )
        )
        return (await session.execute(stmt)).scalars().first()
    
    @staticmethod
    async def get_game_by_room_id(session: AsyncSession, room_id: str) -> Optional[RussianRouletteGame]:
        """根据房间ID获取游戏状态"""
        stmt = select(RussianRouletteGame).where(
            and_(
                RussianRouletteGame.room_id == room_id,
                RussianRouletteGame.status.in_([GameStatus.LOADING.value, GameStatus.PLAYING.value])
            )
        )
        return (await session.execute(stmt)).scalars().first()
    
    @staticmethod
    async def finish_game(session: AsyncSession, room_id: str, winner_id: str) -> Tuple[bool, str]:
        """结束游戏并分配奖励"""
        room = await RussianRouletteService.get_room_by_id(session, room_id)
        game = await RussianRouletteService.get_game_by_room_id(session, room_id)
        
        if not room or not game:
            return False, "房间或游戏不存在"
        
        # 计算总奖励
        total_gold = room.player1_gold_bet + room.player2_gold_bet
        total_items = []

        if room.player1_items_bet:
            player1_items = json.loads(room.player1_items_bet)
            total_items.extend(player1_items)
        if room.player2_items_bet:
            player2_items = json.loads(room.player2_items_bet)
            total_items.extend(player2_items)

        # 分配奖励给获胜者
        winner = await session.get(Player, winner_id)
        if winner:
            winner.gold += total_gold

            # 分配道具（新格式包含item_id、name和quantity）
            for item_data in total_items:
                if isinstance(item_data, dict):
                    # 新格式：{"item_id": "xxx", "name": "xxx", "quantity": n}
                    item_id = item_data["item_id"]
                    quantity = item_data["quantity"]
                    await ItemInstance.add_item(session, winner_id, item_id, quantity)
                else:
                    # 兼容旧格式：直接是item_id字符串
                    await ItemInstance.add_item(session, winner_id, item_data, 1)

        # 更新状态
        room.status = RoomStatus.FINISHED.value
        game.status = GameStatus.FINISHED.value

        await session.commit()

        # 构建奖励消息
        reward_msg = f"🏆 获胜奖励：{total_gold}金币"
        if total_items:
            reward_msg += "\n🎒 道具奖励："
            for item_data in total_items:
                if isinstance(item_data, dict):
                    reward_msg += f"\n  • {item_data['name']} x{item_data['quantity']}"
                else:
                    # 兼容旧格式
                    reward_msg += f"\n  • {item_data} x1"

        return True, reward_msg
